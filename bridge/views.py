import json
import re
import uuid

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token

from .models import FirestoreMirrorDoc


def _map_supplier_type_to_partner_type(supplier_type: str | None) -> str:
    """
    Map frontend v2 supplier.type to SQL partner_type.
    """
    return {
        "shipping_agent": "FreightForwarder",
        "international_trader": "CustomsBroker",
        "factory": "Supplier",
        "local_company": "Supplier",
        "service_provider": "Supplier",
    }.get(supplier_type or "factory", "Supplier")


def _sync_partner_from_mirror_supplier(supplier_data: dict) -> None:
    """
    Ensure SQL Partner exists for a mirror supplier doc, so accounting COA tree works.
    This keeps frontend_v2 mirror suppliers and accounting partners in sync.
    """
    try:
        from partners.models import Partner
        from tenants.models import Tenant, Currency

        tenant = Tenant.objects.first()
        if not tenant:
            return

        supplier_type = supplier_data.get("type")
        partner_type = _map_supplier_type_to_partner_type(supplier_type)

        name = (supplier_data.get("tradeName") or "").strip()
        if not name:
            name = (supplier_data.get("supplierId") or "").strip()
        if not name:
            name = "New Partner"

        legal_name = (supplier_data.get("alias") or "").strip() or None
        phone = supplier_data.get("phone") or None
        email = supplier_data.get("email") or None
        opening_balance = supplier_data.get("openingBalance") or 0
        opening_balance_date = supplier_data.get("balanceDate") or None

        currency_code = supplier_data.get("currency") or None
        currency = None
        if currency_code:
            currency = Currency.objects.filter(Code=currency_code).first()

        defaults = {
            "legal_name": legal_name,
            "partner_type": partner_type,
            "phone": phone,
            "email": email,
            "opening_balance": opening_balance,
            "opening_balance_date": opening_balance_date,
            "currency": currency,
        }

        existing = (
            Partner.objects.filter(
                tenant=tenant,
                partner_type=partner_type,
                name__iexact=name,
            )
            .order_by("id")
            .first()
        )

        if existing:
            for k, v in defaults.items():
                setattr(existing, k, v)
            existing.save()
        else:
            Partner.objects.create(tenant=tenant, name=name, **defaults)
    except Exception:
        # Never break mapper writes due to sync problems.
        return


def _parse_ordering(request):
    raw = request.GET.get('ordering', '-createdAt')
    if raw.startswith('-'):
        return raw[1:], 'desc'
    return raw, 'asc'


def _list_under_prefix(prefix: str, request):
    base = prefix.rstrip('/')
    pattern = re.compile(r'^' + re.escape(base) + r'/([^/]+)$')
    qs = FirestoreMirrorDoc.objects.filter(path__startswith=f'{base}/')
    rows = []
    for row in qs:
        m = pattern.match(row.path)
        if not m:
            continue
        payload = dict(row.data)
        payload.setdefault('id', m.group(1))
        rows.append((row, payload))

    order_field, direction = _parse_ordering(request)
    rev = direction == 'desc'

    def sort_key(item):
        row, payload = item
        v = payload.get(order_field)
        if v is None:
            v = row.updated_at.isoformat() if row.updated_at else ''
        return str(v)

    rows.sort(key=sort_key, reverse=rev)
    out = [p for _, p in rows]

    filters = {}
    for key in request.GET.keys():
        if key in ('ordering', 'limit'):
            continue
        if '__' not in key:
            continue
        field, op = key.split('__', 1)
        if op == 'exact':
            filters[field] = request.GET.get(key)

    if filters:
        out = [r for r in out if all(r.get(k) == v for k, v in filters.items())]

    lim = request.GET.get('limit')
    if lim:
        try:
            out = out[: int(lim)]
        except ValueError:
            pass
    return out


def _auth_ok(request):
    token_key = request.headers.get('Authorization', '').replace('Token ', '').strip()
    return bool(token_key and Token.objects.filter(key=token_key).exists())


def _sync_django_user_active_from_user_mirror(path: str, data: dict) -> None:
    """
    Approval in the UI updates `users/<pk>` mirror JSON (`isApproved`) via /api/mapper/.
    Login still enforces Django auth_user.is_active — keep them aligned.
    """
    if not data or "isApproved" not in data:
        return
    segments = [s for s in path.strip("/").split("/") if s]
    if len(segments) != 2 or segments[0] != "users":
        return
    try:
        uid = int(segments[1])
    except (TypeError, ValueError):
        return
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.filter(pk=uid).first()
        if not user:
            return
        want_active = bool(data["isApproved"])
        if user.is_active != want_active:
            user.is_active = want_active
            user.save(update_fields=["is_active"])
    except Exception:
        return


@method_decorator(csrf_exempt, name='dispatch')
class MapperView(View):
    def get(self, request, subpath):
        if not _auth_ok(request):
            return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=401)

        path = subpath.strip('/')
        segments = [s for s in path.split('/') if s]
        if not segments:
            return JsonResponse({'detail': 'Not found'}, status=404)

        if len(segments) % 2 == 1:
            rows = _list_under_prefix('/'.join(segments), request)
            return JsonResponse(rows, safe=False)

        try:
            doc = FirestoreMirrorDoc.objects.get(path=path)
        except FirestoreMirrorDoc.DoesNotExist:
            return JsonResponse({'detail': 'Not found'}, status=404)
        return JsonResponse(doc.data)

    def post(self, request, subpath):
        if not _auth_ok(request):
            return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=401)

        prefix = subpath.strip('/')
        segments = [s for s in prefix.split('/') if s]
        if len(segments) % 2 != 1:
            return JsonResponse({'detail': 'Collection POST requires odd segment path'}, status=400)
        try:
            body = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({'detail': 'POST body must be a JSON object'}, status=400)

        doc_id = body.get('id') or str(uuid.uuid4())
        full_path = f'{prefix}/{doc_id}'
        data = {k: v for k, v in body.items() if k != 'id'}
        data['id'] = doc_id
        FirestoreMirrorDoc.objects.update_or_create(path=full_path, defaults={'data': data})
        # Auto-sync mirror suppliers to SQL partners
        if prefix == "suppliers":
            _sync_partner_from_mirror_supplier(data)
        return JsonResponse({'id': doc_id})

    def put(self, request, subpath):
        return self._write(request, subpath, merge=False)

    def patch(self, request, subpath):
        return self._write(request, subpath, merge=True)

    def _write(self, request, subpath, merge: bool):
        if not _auth_ok(request):
            return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=401)

        path = subpath.strip('/')
        segments = [s for s in path.split('/') if s]
        if len(segments) % 2 != 0:
            return JsonResponse({'detail': 'Document path must have even segment count'}, status=400)
        try:
            body = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({'detail': 'Document body must be a JSON object'}, status=400)

        doc, _ = FirestoreMirrorDoc.objects.get_or_create(path=path, defaults={'data': {}})
        if merge:
            doc.data = {**doc.data, **body}
        else:
            doc.data = body
        doc.save()
        _sync_django_user_active_from_user_mirror(path, doc.data)
        # Auto-sync mirror suppliers to SQL partners
        if segments and segments[0] == "suppliers" and len(segments) == 2:
            _sync_partner_from_mirror_supplier(doc.data)
        return JsonResponse({'ok': True, 'id': segments[-1]})

    def delete(self, request, subpath):
        if not _auth_ok(request):
            return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=401)
        path = subpath.strip('/')
        FirestoreMirrorDoc.objects.filter(path=path).delete()
        return JsonResponse({'ok': True})
