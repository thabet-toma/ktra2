"""نقاط الوكيل الخاصة بالأطراف — `/api/agent/suppliers/` و`/api/agent/customers/`.

**لماذا هنا لا في `core/`:** تستعمل `partners.serializers`، و`.importlinter` يمنع
`core` من استيراد داخليات app آخر. فتسكن النقطة في الـapp المالكة لبياناتها
ليصير الاستيراد داخلياً ومشروعاً — بدل استثناء في `ignore_imports` تمنعه قاعدة
الصيانة هناك صراحةً. المسارات العامة لم تتغيّر بحرف.

الحراسة: مفتاح `X-Agent-Key` وحده — لا مسار تعديل ولا حذف على أي منهما.
"""
import logging

from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response
from rest_framework import status

from core.agent_db_view import (
    MAX_ROWS,
    _check_agent_key,
    _resolve_agent_tenant,
    agent_endpoint,
)

logger = logging.getLogger(__name__)


@api_view(["GET", "POST", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint("GET, POST, OPTIONS")
def agent_suppliers(request):
    """
    GET  /api/agent/suppliers/?tenant_id=1&search=...
    POST /api/agent/suppliers/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body: {"tenant_id": 1, "name": "مورد جديد", "phone": "...", "email": "...",
           "tax_number": "...", "credit_limit": "0"}

    partner_type ثابت دائماً على "Supplier" بغضّ النظر عمّا يُرسَل — لا مسار
    لإضافة عملاء أو تعديل/حذف موردين عبر واجهة الوكيل.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from partners.models import Partner
    from partners.serializers import PartnerListSerializer, PartnerSerializer

    if request.method == "GET":
        tenant, err = _resolve_agent_tenant(request.query_params.get("tenant_id"))
        if tenant is None:
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
        qs = Partner.objects.filter(
            tenant_id=tenant.TenantID, partner_type="Supplier",
        ).order_by("name")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        try:
            limit = min(max(int(request.query_params.get("limit", MAX_ROWS)), 1), MAX_ROWS)
        except (TypeError, ValueError):
            limit = MAX_ROWS
        rows = PartnerListSerializer(qs[:limit], many=True).data
        return Response({"results": rows, "count": len(rows)})

    from core.activity import log_activity

    tenant, err = _resolve_agent_tenant((request.data or {}).get("tenant_id"))
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    payload = {k: v for k, v in (request.data or {}).items() if k != "tenant_id"}
    payload["partner_type"] = "Supplier"
    if not str(payload.get("name") or "").strip():
        return Response({"error": "اسم المورد مطلوب."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = PartnerSerializer(data=payload)
    if not serializer.is_valid():
        return Response(
            {"error": "بيانات غير صالحة.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    supplier = serializer.save(tenant=tenant)
    log_activity(
        action="create", entity_type="partner", entity_id=supplier.id,
        entity_label=supplier.name, description="إضافة مورد عبر واجهة الوكيل",
        partner_ids=[supplier.id], tenant=tenant, request=request,
    )
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "POST", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint("GET, POST, OPTIONS")
def agent_customers(request):
    """
    GET  /api/agent/customers/?tenant_id=1&search=...
    POST /api/agent/customers/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body: {"tenant_id": 1, "name": "عميل جديد", "phone": "...", "email": "...",
           "tax_number": "...", "credit_limit": "0"}

    partner_type ثابت دائماً على "Customer" بغضّ النظر عمّا يُرسَل — مرآة
    agent_suppliers للطرف الآخر. لا مسار تعديل أو حذف على واجهة الوكيل.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from partners.models import Partner
    from partners.serializers import PartnerListSerializer, PartnerSerializer

    if request.method == "GET":
        tenant, err = _resolve_agent_tenant(request.query_params.get("tenant_id"))
        if tenant is None:
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
        qs = Partner.objects.filter(
            tenant_id=tenant.TenantID, partner_type="Customer",
        ).order_by("name")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        try:
            limit = min(max(int(request.query_params.get("limit", MAX_ROWS)), 1), MAX_ROWS)
        except (TypeError, ValueError):
            limit = MAX_ROWS
        rows = PartnerListSerializer(qs[:limit], many=True).data
        return Response({"results": rows, "count": len(rows)})

    from core.activity import log_activity

    tenant, err = _resolve_agent_tenant((request.data or {}).get("tenant_id"))
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    payload = {k: v for k, v in (request.data or {}).items() if k != "tenant_id"}
    payload["partner_type"] = "Customer"
    if not str(payload.get("name") or "").strip():
        return Response({"error": "اسم العميل مطلوب."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = PartnerSerializer(data=payload)
    if not serializer.is_valid():
        return Response(
            {"error": "بيانات غير صالحة.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    customer = serializer.save(tenant=tenant)
    log_activity(
        action="create", entity_type="partner", entity_id=customer.id,
        entity_label=customer.name, description="إضافة عميل عبر واجهة الوكيل",
        partner_ids=[customer.id], tenant=tenant, request=request,
    )
    return Response(serializer.data, status=status.HTTP_201_CREATED)
