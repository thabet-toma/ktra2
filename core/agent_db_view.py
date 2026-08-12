"""
واجهة برمجية للـ AI Agent للتحكم بقاعدة البيانات عن بُعد.

- القراءة الحرة: SELECT فقط عبر /api/agent/query/ (لا تعديل ولا حذف بالـ SQL).
- فواتير المبيعات/المشتريات (مسوّدات + مرحّلة): /api/agent/invoices/...
- الموردون: /api/agent/suppliers/ — العملاء: /api/agent/customers/
  — الأصناف: /api/agent/products/
  كل الكتابة تمر بالـ ORM (نفس السيريالايزرز المستخدَمة بالواجهة) — لا SQL
  خام إطلاقاً. مسار الحذف الوحيد على كل واجهة الوكيل هو
  DELETE /api/agent/invoices/draft/<id>/ — ويُرفض إن لم تكن الفاتورة
  بحالة draft (لا حذف على المرحّل أو الملغى).
- الحد الأقصى للنتائج: 200 صف لكل استعلام/قائمة.

── تفاوت الحراسة بين نقطة SQL الخام وبقية النقاط (مقصود) ──
نقاط الـORM أعلاه محصورة بنيوياً (سيريالايزر محدّد، شركة محدّدة، بلا حذف إلا
للمسوّدات) فحارسها مفتاح `X-Agent-Key` وحده. أما `/api/agent/query/` فتنفّذ SQL
حرّاً على كامل القاعدة، ولها حراسة أشد:

تقييد أمني (الجلسة الأمنية 2026-08-11 — P0-2 في docs/SCALABILITY_AUDIT.md):
كانت النقطة بلا مصادقة إطلاقاً وبحارس وحيد = مفتاح ثابت مشترك + قائمة سوداء
regex قابلة للتجاوز ⇒ قراءة بيانات كل الشركات لمن يملك المفتاح (المكشوف قديماً
في تاريخ git). الآن ثلاث طبقات، كلها fail-closed:

1. مصادقة Token لمستخدم **superuser** (وكيل المنصة يُعطى توكن superuser).
2. مفتاح `X-Agent-Key` يطابق `AGENT_DB_API_KEY` (غيابه من البيئة = 401 دائماً).
3. تحليل نحوي بـsqlglot: **عبارة واحدة** من نوع SELECT (مع WITH/UNION) بلا
   INTO — القائمة السوداء القديمة تبقى طبقة رابعة لا الحارس الوحيد.

- مسموح فقط بالقراءة، والحد الأقصى للنتائج: 200 صف لكل استعلام.
- throttle مخصص: DEFAULT_THROTTLE_RATES["agent_query"].
"""

import logging
import re
from functools import wraps

from django.conf import settings
from django.db import connection
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework import status

logger = logging.getLogger(__name__)

MAX_ROWS = 200


class IsSuperUser(BasePermission):
    """نقطة SQL الخام لمشغّل المنصة فقط — لا staff ولا مدراء شركات."""

    message = "هذه النقطة تتطلب مستخدم superuser."

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and u.is_superuser)


class AgentQueryThrottle(UserRateThrottle):
    scope = "agent_query"


# الكلمات المحجوزة التي يجب أن لا تظهر في الاستعلام (طبقة دفاع إضافية —
# الحارس الأساسي هو التحليل النحوي أدناه)
_FORBIDDEN_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|GRANT|REVOKE'
    r'|LOAD\s+DATA|LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE|EXEC|EXECUTE|CALL'
    r'|XP_|SP_|SLEEP|BENCHMARK'
    r'|INFORMATION_SCHEMA\.SCHEMATA|SHOW\s+DATABASES)\b',
    re.IGNORECASE,
)

# يجب أن يبدأ الاستعلام بـ SELECT أو WITH (CTE)
_ALLOWED_START = re.compile(r'^\s*(SELECT|WITH)\b', re.IGNORECASE)


def _validate_sql(sql: str) -> str | None:
    """إرجاع رسالة خطأ إذا كان الاستعلام غير مسموح به، أو None إن كان آمناً."""
    cleaned = sql.strip()
    if not cleaned:
        return "الاستعلام فارغ."
    if not _ALLOWED_START.match(cleaned):
        return "مسموح فقط بـ SELECT أو WITH … SELECT. الاستعلام يجب أن يبدأ بـ SELECT."
    match = _FORBIDDEN_KEYWORDS.search(cleaned)
    if match:
        return f"الكلمة المحجوزة «{match.group()}» غير مسموح بها في استعلامات القراءة."

    # الحارس الأساسي: تحليل نحوي — عبارة واحدة نوعها قراءة، بلا INTO.
    # (regex القائمة السوداء وحدها قابلة للتجاوز — P0-2.)
    try:
        import sqlglot
        from sqlglot import exp
    except Exception:  # pragma: no cover — sqlglot في requirements
        return "تعذّر تحميل محلّل SQL على الخادم."
    try:
        statements = [s for s in sqlglot.parse(cleaned, read="mysql") if s is not None]
    except Exception:
        return "تعذّر تحليل الاستعلام — مسموح فقط بـSELECT صالح النحو."
    if len(statements) != 1:
        return "مسموح بعبارة واحدة فقط في كل استعلام."
    stmt = statements[0]
    read_types = tuple(
        t for t in (
            getattr(exp, "Select", None),
            getattr(exp, "Union", None),
            getattr(exp, "Intersect", None),
            getattr(exp, "Except", None),
        ) if t is not None
    )
    if not isinstance(stmt, read_types):
        return "مسموح فقط باستعلامات SELECT."
    if stmt.find(exp.Into) is not None:
        return "INTO غير مسموح في استعلامات القراءة."
    # FOR UPDATE / LOCK IN SHARE MODE يأخذ أقفالاً على صفوف — ممنوع على نقطة قراءة.
    lock_type = getattr(exp, "Lock", None)
    if lock_type is not None and stmt.find(lock_type) is not None:
        return "FOR UPDATE / قفل الصفوف غير مسموح — النقطة للقراءة فقط."
    return None


def _enforce_row_cap(sql: str) -> str:
    """يضمن سقف الصفوف بنيوياً (لا نصّياً): إن لم يكن للاستعلام LIMIT علوي،
    يُغلَّف في استعلام فرعي بسقف — فلا يتجاوزه تعليق سطري لاحق ولا FOR UPDATE.
    (الإلحاق النصّي القديم كان يُبتلع داخل `-- comment` أو يكسر ترتيب FOR UPDATE.)
    """
    import sqlglot
    try:
        stmt = sqlglot.parse_one(sql, read="mysql")
    except Exception:
        stmt = None
    has_top_limit = stmt is not None and stmt.args.get("limit") is not None
    if has_top_limit:
        return sql
    # سطر جديد قبل الإغلاق يُنهي أي تعليق سطري زائف داخل الاستعلام.
    return f"SELECT * FROM (\n{sql.rstrip(';')}\n) AS _agent_capped LIMIT {MAX_ROWS}"


def agent_endpoint(methods="POST, OPTIONS"):
    """مسارات الوكيل مفتوحة لأي دومين (Origin: *) — لأن الهوية هنا هي مفتاح
    X-Agent-Key لا مصدر الطلب، ولا تُستخدم كوكيز جلسة إطلاقاً فلا خطر CSRF.
    هذا لا يمسّ CORS لبقية المسارات (الواجهة تبقى على قائمتها المحددة)،
    ويشمل ردّ preflight لأن هيدر X-Agent-Key هيدر مخصص يستدعي OPTIONS مسبقاً.

    ملاحظة: `agent_query` **لا** يستعمل هذا المُزخرِف — حراستها أشد (P0-2).
    """
    def _decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if request.method == "OPTIONS":
                response = Response(status=status.HTTP_200_OK)
            else:
                response = view(request, *args, **kwargs)
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = methods
            response["Access-Control-Allow-Headers"] = "Content-Type, X-Agent-Key"
            response["Access-Control-Max-Age"] = "86400"
            return response

        return _wrapped

    return _decorator


def _check_agent_key(request):
    """إرجاع Response بـ 401 إذا كان المفتاح ناقصاً/خاطئاً، أو None إن كان صحيحاً."""
    expected_key = getattr(settings, "AGENT_DB_API_KEY", "")
    provided_key = request.headers.get("X-Agent-Key", "").strip()
    if not expected_key or provided_key != expected_key:
        return Response(
            {"error": "Unauthorized — مفتاح API غير صحيح أو غير موجود."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return None


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsSuperUser])
@throttle_classes([AgentQueryThrottle])
def agent_query(request):
    """
    POST /api/agent/query/
    Headers: Authorization: Token <superuser-token> · X-Agent-Key: <AGENT_DB_API_KEY>
    Body:    {"sql": "SELECT ...", "params": [...]}
    Response: {"columns": [...], "rows": [...], "count": N}

    بخلاف بقية نقاط الوكيل، هذه ليست CORS-مفتوحة ولا بمفتاح وحده: التوكن
    (superuser) شرط أول، فالمفتاح، فالتحليل النحوي — P0-2.
    """
    # ─── الطبقة الثانية: مفتاح API (fail-closed: غياب الضبط = رفض دائم) ───
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    sql = str(request.data.get("sql") or "").strip()
    params = request.data.get("params") or []

    # ─── التحقق من سلامة الاستعلام ───
    err = _validate_sql(sql)
    if err:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    # ─── فرض سقف الصفوف بنيوياً (comment-proof) ───
    sql = _enforce_row_cap(sql)

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(MAX_ROWS)

        # تحويل القيم غير القابلة للتسلسل (Decimal, date, …)
        def _safe(v):
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return v

        result_rows = [[_safe(cell) for cell in row] for row in rows]

        logger.info(
            "[AgentQuery] user=%s rows=%d sql_start=%s",
            request.user.pk, len(result_rows), sql[:80],
        )
        return Response(
            {
                "columns": columns,
                "rows": result_rows,
                "count": len(result_rows),
            }
        )

    except Exception as exc:
        logger.warning("[AgentQuery] SQL error: %s | sql=%s", exc, sql[:200])
        return Response(
            {"error": f"خطأ في تنفيذ الاستعلام: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _resolve_agent_tenant(tenant_id):
    """يحل الشركة من الجسم، أو الشركة الوحيدة إن كانت واحدة فقط بالنظام."""
    from tenants.models import Tenant

    if tenant_id not in (None, "", 0, "0"):
        try:
            return Tenant.objects.get(TenantID=int(tenant_id)), None
        except (Tenant.DoesNotExist, ValueError, TypeError):
            return None, f"الشركة غير موجودة: {tenant_id}"
    tenants = list(Tenant.objects.all()[:2])
    if len(tenants) == 1:
        return tenants[0], None
    return None, "حدّد الشركة عبر tenant_id في جسم الطلب."


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


@api_view(["GET", "POST", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint("GET, POST, OPTIONS")
def agent_products(request):
    """
    GET  /api/agent/products/?tenant_id=1&search=...
    POST /api/agent/products/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body: {"tenant_id": 1, "name_ar": "صنف جديد", "sku": "اختياري"}

    رقم الصنف (sku) يُولَّد خادمياً عند غيابه (نفس منطق شاشة الأصناف) —
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
                {"error": "رقم الصنف مستخدم مسبقاً لهذه الشركة."},
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
                {"error": "تعذّر توليد رقم صنف — أعد المحاولة."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    log_activity(
        action="create", entity_type="product", entity_id=product.id,
        entity_label=str(product), description="إضافة صنف عبر واجهة الوكيل",
        tenant=tenant, request=request,
    )
    return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)
