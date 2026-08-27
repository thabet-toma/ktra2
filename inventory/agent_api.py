"""نقطة الوكيل الخاصة بالمنتجات — `/api/agent/products/`.

**لماذا هنا لا في `core/`:** تستعمل `inventory.serializers`، و`.importlinter` يمنع
`core` من استيراد داخليات app آخر. فتسكن النقطة في الـapp المالكة لبياناتها
ليصير الاستيراد داخلياً ومشروعاً. المسار العام لم يتغيّر بحرف.

ولا تستورد هذه الوحدة `sales` ولا `logistics` — عقد «الاتجاه المعكوس» في
`.importlinter` يمنع `inventory` من الاعتماد عليهما.

الحراسة: مفتاح `X-Agent-Key` وحده — لا مسار تعديل ولا حذف.
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
def agent_products(request):
    """
    GET  /api/agent/products/?tenant_id=1&search=...
    POST /api/agent/products/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body: {"tenant_id": 1, "name_ar": "منتج جديد", "sku": "اختياري"}

    رقم المنتج (sku) يُولَّد خادمياً عند غيابه (نفس منطق شاشة المنتجات) —
    لا مسار تعديل أو حذف على واجهة الوكيل.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from inventory.models import Product
    from inventory.serializers import ProductLookupSerializer, ProductSerializer
    from inventory.services import generate_next_sku

    if request.method == "GET":
        tenant, err = _resolve_agent_tenant(request.query_params.get("tenant_id"))
        if tenant is None:
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
        qs = Product.objects.filter(tenant_id=tenant.TenantID).order_by("name_ar", "name_en")
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(sku__icontains=search) | Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
            )
        try:
            limit = min(max(int(request.query_params.get("limit", MAX_ROWS)), 1), MAX_ROWS)
        except (TypeError, ValueError):
            limit = MAX_ROWS
        rows = ProductLookupSerializer(qs[:limit], many=True).data
        return Response({"results": rows, "count": len(rows)})

    from core.activity import log_activity

    tenant, err = _resolve_agent_tenant((request.data or {}).get("tenant_id"))
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    payload = {k: v for k, v in (request.data or {}).items() if k != "tenant_id"}
    serializer = ProductSerializer(data=payload)
    if not serializer.is_valid():
        return Response(
            {"error": "بيانات غير صالحة.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    explicit_sku = (serializer.validated_data.get("sku") or "").strip()
    if explicit_sku:
        if Product.objects.filter(tenant=tenant, sku=explicit_sku).exists():
            return Response(
                {"error": "رقم المنتج مستخدم مسبقاً لهذه الشركة."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = serializer.save(tenant=tenant, sku=explicit_sku)
    else:
        from django.db import IntegrityError, transaction as _tx
        product = None
        for _ in range(5):
            try:
                with _tx.atomic():
                    product = serializer.save(tenant=tenant, sku=generate_next_sku(tenant))
                break
            except IntegrityError:
                continue
        if product is None:
            return Response(
                {"error": "تعذّر توليد رقم منتج — أعد المحاولة."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    log_activity(
        action="create", entity_type="product", entity_id=product.id,
        entity_label=str(product), description="إضافة منتج عبر واجهة الوكيل",
        tenant=tenant, request=request,
    )
    return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)
