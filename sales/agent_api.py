"""نقاط الوكيل الخاصة بالمبيعات — `/api/agent/invoices/...` و`/api/agent/last-price/`.

**لماذا هنا لا في `core/`:** هذه النقاط تستعمل `sales.serializers` و`sales.models`،
و`.importlinter` يمنع `core` من استيراد داخليات app آخر (عقد
`no-cross-app-internals`). فلمّا أُعيدت نقاط الوكيل من فرع الخادم كسرت العقد،
والحلّ ليس استثناءً في `ignore_imports` (ممنوع صراحةً هناك لتمرير كود جديد) بل
أن تسكن كل نقطة في الـapp **المالكة لبياناتها** — فيصير الاستيراد داخلياً ومشروعاً.

المسارات العامة لم تتغيّر بحرف (`/api/agent/...`): البوت الخارجي يناديها بهذه
الصيغة، وتغييرها يكسره فوراً.

الحراسة: مفتاح `X-Agent-Key` وحده — النقاط محصورة بنيوياً (سيريالايزر محدّد،
شركة محدّدة، والحذف للمسوّدات فقط). هذا لا يشمل `/api/agent/query/` (SQL خام)
التي تبقى في `core/agent_db_view.py` بحراسة superuser — P0-2.
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
def agent_create_draft_invoice(request):
    """
    GET  /api/agent/invoices/draft/?tenant_id=1&customer=12&limit=50
         يعرض المسوّدات (status=draft) فقط.
    POST /api/agent/invoices/draft/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body:    {"tenant_id": 1, "branch_id": 2, "customer": 12,
              "invoice_date": "2026-07-30", "currency": 1,
              "lines": [{"product": 345, "quantity": "2", "unit_price": "150.00"}]}

    الإنشاء ينتج فاتورة مبيعات **مسوّدة دائماً** — لا ترحيل تلقائي ولا قيود
    محاسبية، لأن الترحيل يبقى قراراً بشرياً من الواجهة. الترقيم والضرائب
    وفحص المخزون تمرّ عبر SalesInvoiceSerializer نفسه المستخدَم في الواجهة.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from sales.models import SalesInvoice
    from sales.serializers import SalesInvoiceListSerializer, SalesInvoiceSerializer
    from tenants.models import Branch

    if request.method == "GET":
        tenant, err = _resolve_agent_tenant(request.query_params.get("tenant_id"))
        if tenant is None:
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
        qs = SalesInvoice.objects.filter(
            tenant_id=tenant.TenantID, status=SalesInvoice.STATUS_DRAFT,
        ).select_related("customer", "currency").order_by("-id")
        customer_id = request.query_params.get("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        try:
            limit = min(max(int(request.query_params.get("limit", MAX_ROWS)), 1), MAX_ROWS)
        except (TypeError, ValueError):
            limit = MAX_ROWS
        rows = SalesInvoiceListSerializer(qs[:limit], many=True).data
        return Response({"results": rows, "count": len(rows)})

    from core.activity import log_activity

    payload = {k: v for k, v in (request.data or {}).items()
               if k not in {"tenant_id", "branch_id", "auto_post", "status"}}

    tenant, err = _resolve_agent_tenant((request.data or {}).get("tenant_id"))
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    branch = None
    branch_id = (request.data or {}).get("branch_id")
    if branch_id not in (None, "", 0, "0"):
        branch = Branch.objects.filter(pk=branch_id, tenant_id=tenant.TenantID).first()
        if branch is None:
            return Response(
                {"error": f"الفرع غير موجود أو لا يتبع الشركة: {branch_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    serializer = SalesInvoiceSerializer(data=payload)
    if not serializer.is_valid():
        return Response(
            {"error": "بيانات غير صالحة.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        invoice = serializer.save(tenant=tenant, branch=branch, created_by=None)
    except Exception as exc:  # noqa: BLE001 — نعيد سبب الرفض للوكيل بدل 500
        logger.warning("[AgentDraftInvoice] create failed: %s", exc)
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    log_activity(
        action="create", entity_type="sales_invoice", entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        description="إنشاء فاتورة مسوّدة عبر واجهة الوكيل",
        partner_ids=[invoice.customer_id], tenant=tenant, request=request,
    )
    logger.info(
        "[AgentDraftInvoice] tenant=%s invoice=%s total=%s",
        tenant.TenantID, invoice.invoice_number, invoice.grand_total,
    )
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint("GET, PATCH, DELETE, OPTIONS")
def agent_draft_invoice_detail(request, pk):
    """
    GET    /api/agent/invoices/draft/<id>/?tenant_id=1   — عرض فاتورة واحدة.
    PATCH  /api/agent/invoices/draft/<id>/                — تعديل مسوّدة فقط.
    DELETE /api/agent/invoices/draft/<id>/?tenant_id=1    — حذف مسوّدة فقط.
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>

    التعديل والحذف مرفوضان إن كانت الفاتورة مرحّلة أو ملغاة (نفس قاعدة
    الواجهة) — هذا هو مسار الحذف الوحيد على كامل واجهة الوكيل، ومحصور
    بالمسوّدات حصراً.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from sales.models import SalesInvoice
    from sales.serializers import SalesInvoiceSerializer

    tenant_id = (
        request.query_params.get("tenant_id")
        if request.method in ("GET", "DELETE")
        else (request.data or {}).get("tenant_id")
    )
    tenant, err = _resolve_agent_tenant(tenant_id)
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    invoice = SalesInvoice.objects.filter(pk=pk, tenant_id=tenant.TenantID).first()
    if invoice is None:
        return Response({"error": "الفاتورة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(SalesInvoiceSerializer(invoice).data)

    from core.activity import log_activity

    if request.method == "DELETE":
        if invoice.status != SalesInvoice.STATUS_DRAFT:
            return Response(
                {"error": "لا يمكن حذف فاتورة مرحّلة أو ملغاة عبر واجهة الوكيل — المسوّدات فقط."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice_number = invoice.invoice_number
        customer_id = invoice.customer_id
        invoice.delete()
        log_activity(
            action="delete", entity_type="sales_invoice", entity_id=pk,
            entity_label=invoice_number,
            description="حذف فاتورة مسوّدة عبر واجهة الوكيل",
            partner_ids=[customer_id], tenant=tenant, request=request,
        )
        logger.info(
            "[AgentDraftInvoice] deleted tenant=%s invoice=%s", tenant.TenantID, invoice_number,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    if invoice.status != SalesInvoice.STATUS_DRAFT:
        return Response(
            {"error": "لا يمكن تعديل فاتورة مرحّلة أو ملغاة عبر واجهة الوكيل."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payload = {k: v for k, v in (request.data or {}).items()
               if k not in {"tenant_id", "branch_id", "auto_post", "status"}}
    serializer = SalesInvoiceSerializer(invoice, data=payload, partial=True)
    if not serializer.is_valid():
        return Response(
            {"error": "بيانات غير صالحة.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        invoice = serializer.save()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AgentDraftInvoice] update failed: %s", exc)
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    log_activity(
        action="update", entity_type="sales_invoice", entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        description="تعديل فاتورة مسوّدة عبر واجهة الوكيل",
        partner_ids=[invoice.customer_id], tenant=tenant, request=request,
    )
    return Response(serializer.data)


@api_view(["GET", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint("GET, OPTIONS")
def agent_list_invoices(request):
    """
    GET /api/agent/invoices/?tenant_id=1&status=posted&invoice_kind=sale
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>

    عرض الفواتير — بيع أو شراء، مسوّدة أو مرحّلة — بلا أي كتابة. invoice_kind:
    sale / sale_return / purchase / purchase_return (نفس نموذج SalesInvoice
    يغطّي الأربعة — لا يوجد نموذج منفصل لفواتير الشراء في هذا النظام).
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from sales.models import SalesInvoice
    from sales.serializers import SalesInvoiceListSerializer

    tenant, err = _resolve_agent_tenant(request.query_params.get("tenant_id"))
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    qs = SalesInvoice.objects.filter(tenant_id=tenant.TenantID).select_related(
        "customer", "currency",
    ).order_by("-invoice_date", "-id")
    status_param = request.query_params.get("status")
    if status_param:
        qs = qs.filter(status=status_param)
    kind_param = request.query_params.get("invoice_kind")
    if kind_param:
        qs = qs.filter(invoice_kind=kind_param)
    partner_id = request.query_params.get("customer") or request.query_params.get("supplier")
    if partner_id:
        qs = qs.filter(customer_id=partner_id)
    try:
        limit = min(max(int(request.query_params.get("limit", MAX_ROWS)), 1), MAX_ROWS)
    except (TypeError, ValueError):
        limit = MAX_ROWS
    rows = SalesInvoiceListSerializer(qs[:limit], many=True).data
    return Response({"results": rows, "count": len(rows)})


@api_view(["GET", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint("GET, OPTIONS")
def agent_last_price(request):
    """
    GET /api/agent/last-price/?tenant_id=6&product=<id>[&customer=<id>]
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Response: {"unit_price": "123.45", "invoice_number": ..., "invoice_date": ...}
              أو {"unit_price": null, ...} إن لم يسبق بيع المنتج إطلاقاً.

    يفوّض إلى `sales.services.last_sale_price` — **نفس** الدالة التي تُغذّي
    اقتراح السعر في الواجهة وبطاقة المنتج (`inventory.services`). القاعدة لا
    تُكتب هنا مرة ثانية عمداً: نسخة ثانية من قاعدة تسعير هي خطأ تباعُد مؤجَّل،
    وقد صار للبوت والواجهة مصدر واحد.

    سلوكها المعتمَد هنا: بوجود `customer` يُفضَّل آخر سعر لذلك العميل، فإن لم
    يسبق له شراء المنتج رجعت إلى آخر سعر عام — وهذا مقصود لأن البوت يحتاج رقماً
    يقترحه لا فراغاً. ومحصورة ببيع **مرحَّل** (`invoice_kind='sale'`) وبترتيب
    حتمي (تاريخ الفاتورة تنازلياً ثم المعرّف).

    العزل عبر `_resolve_agent_tenant` — المنتج والعميل يُفلتران بشركته لا
    بمعرّف يُصدَّق من الطلب.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from sales.services import last_sale_price

    tenant, err = _resolve_agent_tenant(request.query_params.get("tenant_id"))
    if tenant is None:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    product_id = str(request.query_params.get("product") or "").strip()
    if not product_id.isdigit():
        return Response(
            {"error": "باراميتر product مطلوب (معرّف رقمي)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    customer_id = str(request.query_params.get("customer") or "").strip()
    data = last_sale_price(
        tenant_id=tenant.TenantID,
        product_id=int(product_id),
        customer_id=int(customer_id) if customer_id.isdigit() else None,
    )
    return Response(data)
