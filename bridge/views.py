import json
import logging
import re
import uuid

from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token

from .models import FirestoreMirrorDoc

logger = logging.getLogger(__name__)

# Collections that are NOT company-scoped (auth / public content only).
# Everything else stored through /api/mapper/ belongs to exactly one company.
# task11 M7: «tasks» أصبحت tenant-scoped — كانت global فظهرت مهام الشركة
# القديمة في الصفحة الرئيسية لأي شركة جديدة.
# الجلسة الأمنية 2026-08-11 (P0-3): أُخرجت بيانات الحضور والنقاط والأقسام من
# القائمة العالمية — كانت مقروءة عبر كل الشركات لأي مستخدم. الواجهة تقرأها من
# Firebase مباشرةً لا من الـmapper، فالنسخة هنا دفاعية والتقييد بلا كسر مستهلك.
GLOBAL_COLLECTIONS = {
    'users',
    'publicGallery',
    'aboutLinks',
}

# Collections that can be read by unauthenticated users (GET only)
PUBLIC_COLLECTIONS = {
    'publicGallery',
    'aboutLinks',
}


def _root_collection(path: str) -> str:
    return path.strip('/').split('/')[0] if path else ''


def _is_tenant_scoped(path: str) -> bool:
    return _root_collection(path) not in GLOBAL_COLLECTIONS


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


def _sync_partner_from_mirror_supplier(supplier_data: dict, tenant) -> None:
    """
    Ensure SQL Partner exists for a mirror supplier doc, so accounting COA tree works.
    This keeps frontend_v2 mirror suppliers and accounting partners in sync.
    """
    try:
        from partners.models import Partner
        from tenants.models import Currency

        if tenant is None:
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

        credit_limit = supplier_data.get("creditLimit") or None

        defaults = {
            "legal_name": legal_name,
            "partner_type": partner_type,
            "phone": phone,
            "email": email,
            "opening_balance": opening_balance,
            "opening_balance_date": opening_balance_date,
            "currency": currency,
            "credit_limit": credit_limit,
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
        logger.warning("mapper: supplier→partner sync failed", exc_info=True)
        return


def _sync_product_from_mirror_item(item_data: dict, tenant, doc_id: str) -> None:
    """
    Ensure SQL Product exists for a mirror item doc.
    """
    try:
        from inventory.models import Product
        from inventory.services import generate_next_sku

        if tenant is None:
            return

        name = (item_data.get("name_ar") or item_data.get("name") or "New Item").strip()
        
        # Generate SKU if not provided or if it's a firebase UUID
        sku = item_data.get("sku")
        if not sku or sku.startswith("FB-"):
            sku = generate_next_sku(tenant)
            
        defaults = {
            "name_ar": name,
            "sku": sku,
            "uom_primary": item_data.get("uom_primary") or "عدد",
        }

        # Check by mirror doc_id stored in a field, or just match by name/sku if we didn't store it.
        # But wait, the simplest is matching by SKU if it was passed, or create new.
        sql_id = item_data.get("sqlProductId")

        if sql_id:
            Product.objects.update_or_create(id=sql_id, tenant=tenant, defaults=defaults)
        else:
            # If no sql_id, try to find by SKU, else create
            p = Product.objects.filter(tenant=tenant, sku=sku).first()
            if p:
                for k, v in defaults.items():
                    setattr(p, k, v)
                p.save()
            else:
                p = Product.objects.create(tenant=tenant, **defaults)
            
            # Optionally write back sqlProductId to the dict so caller knows?
            # We are in the mapper, we can mutate doc.data before save? Yes, if we hook before save.
            item_data["sqlProductId"] = p.id
            item_data["sku"] = p.sku

    except Exception:
        logger.warning("mapper: item→product sync failed", exc_info=True)
        return


def _parse_ordering(request):
    raw = request.GET.get('ordering', '-createdAt')
    if raw.startswith('-'):
        return raw[1:], 'desc'
    return raw, 'asc'


def _filter_value_matches(doc_value, query_value: str) -> bool:
    """Coerce-compare a JSON doc value against a query-string value.

    Query params always arrive as strings ("true", "5") while mirror docs hold
    real JSON types (True, 5). Direct == comparison silently filtered
    everything out (the archive's isHistorical filter never matched).
    """
    if isinstance(doc_value, bool):
        return str(doc_value).lower() == str(query_value).strip().lower()
    if doc_value is None:
        return query_value in ('', 'null', 'None')
    return str(doc_value) == str(query_value)


def _list_under_prefix(prefix: str, request, tenant):
    base = prefix.rstrip('/')
    pattern = re.compile(r'^' + re.escape(base) + r'/([^/]+)$')
    qs = FirestoreMirrorDoc.objects.filter(path__startswith=f'{base}/')
    if _is_tenant_scoped(base):
        qs = qs.filter(tenant=tenant)

    include_deleted = request.GET.get('include_deleted') == '1'

    rows = []
    for row in qs:
        m = pattern.match(row.path)
        if not m:
            continue
        payload = dict(row.data)
        if not include_deleted and payload.get('deleted'):
            continue
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
        if key in ('ordering', 'limit', 'include_deleted'):
            continue
        if '__' not in key:
            continue
        field, op = key.split('__', 1)
        if op == 'exact':
            filters[field] = request.GET.get(key)

    if filters:
        out = [
            r for r in out
            if all(_filter_value_matches(r.get(k), v) for k, v in filters.items())
        ]

    lim = request.GET.get('limit')
    if lim:
        try:
            out = out[: int(lim)]
        except ValueError:
            pass
    return out


def _resolve_user(request):
    """Attach the token's user to the request so tenant membership checks work.

    MapperView is a plain Django View (no DRF authentication), so request.user
    would otherwise stay AnonymousUser and get_tenant() would skip the
    membership validation entirely.
    """
    token_key = request.headers.get('Authorization', '').replace('Token ', '').strip()
    if not token_key:
        return None
    token = Token.objects.select_related('user').filter(key=token_key).first()
    if token is None:
        return None
    request.user = token.user
    return token.user


def _resolve_tenant(request):
    """Tenant for this mapper request (validated against membership)."""
    from django.core.exceptions import PermissionDenied
    from core.tenant_utils import get_tenant
    try:
        return get_tenant(request), None
    except PermissionDenied as e:
        return None, JsonResponse({'detail': str(e)}, status=403)


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
    """Firestore-style document API over MySQL.

    Tenant rules:
      - Business collections (anything not in GLOBAL_COLLECTIONS) are scoped to
        the request tenant (X-Tenant-Id header, membership-validated).
      - Reading/writing/deleting a doc owned by another tenant → 404.
    Data safety:
      - DELETE is always a soft-delete (data.deleted = true). Lists exclude
        deleted docs unless ?include_deleted=1. No hard-delete path exists.
    """

    def _gate(self, request, path: str):
        """Auth + tenant resolution. Returns (tenant, error_response)."""
        user = _resolve_user(request)
        
        root_col = _root_collection(path)
        is_public_read = request.method == 'GET' and root_col in PUBLIC_COLLECTIONS

        if user is None and not is_public_read:
            # فرّق بين «لا توكن أصلاً» و«توكن أُبطل» — الرسالة الموحّدة السابقة
            # كانت تُظهر «لم يتم تزويد بيانات الدخول» حتى لو أرسل العميل توكناً
            # محذوفاً (خروج من تبويب آخر)، فيتعذّر تشخيص المشكلة.
            sent_token = bool(request.headers.get('Authorization', '').strip())
            return None, JsonResponse(
                {'detail': 'انتهت الجلسة. الرجاء تسجيل الدخول من جديد.'
                 if sent_token else 'Authentication credentials were not provided.'},
                status=401,
            )
            
        tenant, err = _resolve_tenant(request)
        # If public read and unauthenticated, tenant will be None. We only care about tenant errors if not public.
        if err is not None and not is_public_read:
            return None, err
            
        if _is_tenant_scoped(path) and tenant is None and not is_public_read:
            return None, JsonResponse(
                {'detail': 'لم يتم تحديد الشركة. أرسل X-Tenant-Id في الهيدر.'}, status=400
            )
        return tenant, None

    def _get_doc_checked(self, path: str, tenant):
        """Fetch a doc enforcing tenant ownership. Returns (doc, error_response)."""
        try:
            doc = FirestoreMirrorDoc.objects.get(path=path)
        except FirestoreMirrorDoc.DoesNotExist:
            return None, JsonResponse({'detail': 'Not found'}, status=404)
        # P0-4 (الجلسة الأمنية 2026-08-11): وثيقة مُنطاقة بلا مالك (tenant NULL)
        # لا تخصّ أحداً — لا تُعرَض ولا يجوز لأي شركة الاستيلاء عليها. المملوكة
        # تُطابَق مع شركة المستدعي فقط. (كان NULL يمرّ لأي شركة = خرق عزل.)
        if _is_tenant_scoped(path):
            if doc.tenant_id is None or tenant is None or doc.tenant_id != tenant.pk:
                return None, JsonResponse({'detail': 'Not found'}, status=404)
        return doc, None

    def get(self, request, subpath):
        path = subpath.strip('/')
        tenant, err = self._gate(request, path)
        if err:
            return err

        segments = [s for s in path.split('/') if s]
        if not segments:
            return JsonResponse({'detail': 'Not found'}, status=404)

        # The legacy users mirror is platform-global. Never expose its
        # collection to company users, and only allow a user to read their own
        # mirror document. Company member discovery belongs to the tenant-
        # scoped /companies/{id}/members endpoint.
        if segments[0] == 'users' and not request.user.is_superuser:
            if len(segments) == 1:
                return JsonResponse({'detail': 'Forbidden'}, status=403)
            if len(segments) == 2 and segments[1] != str(request.user.pk):
                return JsonResponse({'detail': 'Not found'}, status=404)

        if len(segments) % 2 == 1:
            rows = _list_under_prefix('/'.join(segments), request, tenant)
            return JsonResponse(rows, safe=False)

        doc, err = self._get_doc_checked(path, tenant)
        if err:
            return err
        if doc.data.get('deleted') and request.GET.get('include_deleted') != '1':
            return JsonResponse({'detail': 'Not found'}, status=404)
        return JsonResponse(doc.data)

    def post(self, request, subpath):
        prefix = subpath.strip('/')
        tenant, err = self._gate(request, prefix)
        if err:
            return err

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

        existing = FirestoreMirrorDoc.objects.filter(path=full_path).first()
        # P0-4: لا كتابة فوق وثيقة مُنطاقة تخصّ شركة أخرى أو بلا مالك.
        if existing is not None and _is_tenant_scoped(full_path) and (
            existing.tenant_id is None or tenant is None
            or existing.tenant_id != tenant.pk
        ):
            return JsonResponse({'detail': 'Not found'}, status=404)

        # Auto-sync mirror suppliers to SQL partners
        if segments[0] == "suppliers":
            _sync_partner_from_mirror_supplier(data, tenant)
        elif segments[0] == "items":
            _sync_product_from_mirror_item(data, tenant, doc_id)
        
        FirestoreMirrorDoc.objects.update_or_create(
            path=full_path,
            defaults={'data': data, 'tenant': tenant if _is_tenant_scoped(full_path) else None},
        )
        return JsonResponse({'id': doc_id})

    def put(self, request, subpath):
        return self._write(request, subpath, merge=False)

    def patch(self, request, subpath):
        return self._write(request, subpath, merge=True)

    def _write(self, request, subpath, merge: bool):
        path = subpath.strip('/')
        tenant, err = self._gate(request, path)
        if err:
            return err

        segments = [s for s in path.split('/') if s]
        if len(segments) % 2 != 0:
            return JsonResponse({'detail': 'Document path must have even segment count'}, status=400)
        try:
            body = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({'detail': 'Document body must be a JSON object'}, status=400)

        doc = FirestoreMirrorDoc.objects.filter(path=path).first()
        if doc is not None:
            # P0-4: وثيقة مُنطاقة تخصّ شركة أخرى أو يتيمة (NULL) لا تُكتَب — لا
            # استيلاء. الوثيقة الجديدة (else) تولَد مملوكة لشركة المستدعي مباشرةً.
            if _is_tenant_scoped(path) and (
                doc.tenant_id is None or tenant is None
                or doc.tenant_id != tenant.pk
            ):
                return JsonResponse({'detail': 'Not found'}, status=404)
        else:
            doc = FirestoreMirrorDoc(
                path=path,
                data={},
                tenant=tenant if _is_tenant_scoped(path) else None,
            )

        if merge:
            doc.data = {**doc.data, **body}
        else:
            doc.data = body

        _sync_django_user_active_from_user_mirror(path, doc.data)
        # Auto-sync mirror suppliers to SQL partners
        if segments and segments[0] == "suppliers" and len(segments) == 2:
            _sync_partner_from_mirror_supplier(doc.data, tenant)
        elif segments and segments[0] == "items" and len(segments) == 2:
            _sync_product_from_mirror_item(doc.data, tenant, segments[1])

        doc.save()
        return JsonResponse({'ok': True, 'id': segments[-1]})

    def delete(self, request, subpath):
        path = subpath.strip('/')
        tenant, err = self._gate(request, path)
        if err:
            return err

        doc, err = self._get_doc_checked(path, tenant)
        if err:
            # Deleting a non-existent doc was previously a silent no-op success;
            # keep that contract so callers don't break on retries.
            return JsonResponse({'ok': True})

        # Data safety: soft-delete only. Financial/business documents are never
        # physically removed through the API.
        doc.data = {**doc.data, 'deleted': True, 'deletedAt': timezone.now().isoformat()}
        doc.save(update_fields=['data', 'updated_at'])
        logger.info(
            "mapper soft-delete: path=%s tenant=%s user=%s",
            path, getattr(tenant, 'pk', None), getattr(request.user, 'username', '?'),
        )
        return JsonResponse({'ok': True, 'soft_deleted': True})
