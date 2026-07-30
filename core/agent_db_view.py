"""
واجهة برمجية للـ AI Agent للتحكم بقاعدة البيانات عن بُعد بمفتاح واحد.
- القراءة: SELECT فقط عبر /api/agent/query/ (لا تعديل ولا حذف بالـ SQL).
- الكتابة: عبر الـ ORM فقط (/api/agent/invoices/draft/) كي تمرّ بكل قواعد
  الترقيم والضرائب والمخزون — لا كتابة SQL خام إطلاقاً.
- يتطلب مفتاح API في الهيدر: X-Agent-Key
- الحد الأقصى للنتائج: 200 صف لكل استعلام.
"""

import logging
import re
from functools import wraps

from django.conf import settings
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

MAX_ROWS = 200

# الكلمات المحجوزة التي يجب أن لا تظهر في الاستعلام (حماية من التلاعب)
_FORBIDDEN_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|GRANT|REVOKE'
    r'|LOAD\s+DATA|INTO\s+OUTFILE|EXEC|EXECUTE|CALL|XP_|SP_|SLEEP|BENCHMARK'
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
    return None


def agent_endpoint(view):
    """مسارات الوكيل مفتوحة لأي دومين (Origin: *) — لأن الهوية هنا هي مفتاح
    X-Agent-Key لا مصدر الطلب، ولا تُستخدم كوكيز جلسة إطلاقاً فلا خطر CSRF.
    هذا لا يمسّ CORS لبقية المسارات (الواجهة تبقى على قائمتها المحددة)،
    ويشمل ردّ preflight لأن هيدر X-Agent-Key هيدر مخصص يستدعي OPTIONS مسبقاً.
    """
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if request.method == "OPTIONS":
            response = Response(status=status.HTTP_200_OK)
        else:
            response = view(request, *args, **kwargs)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, X-Agent-Key"
        response["Access-Control-Max-Age"] = "86400"
        return response

    return _wrapped


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


@api_view(["POST", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint
def agent_query(request):
    """
    POST /api/agent/query/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body:    {"sql": "SELECT ...", "params": [...]}
    Response: {"columns": [...], "rows": [...], "count": N}
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    sql = str(request.data.get("sql") or "").strip()
    params = request.data.get("params") or []

    # ─── التحقق من سلامة الاستعلام ───
    err = _validate_sql(sql)
    if err:
        return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)

    # ─── إضافة LIMIT تلقائية إن لم تكن موجودة ───
    if not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
        sql = f"{sql.rstrip(';')} LIMIT {MAX_ROWS}"

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

        logger.info("[AgentQuery] rows=%d sql_start=%s", len(result_rows), sql[:80])
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


@api_view(["POST", "OPTIONS"])
@authentication_classes([])
@permission_classes([])
@agent_endpoint
def agent_create_draft_invoice(request):
    """
    POST /api/agent/invoices/draft/
    Headers: X-Agent-Key: <AGENT_DB_API_KEY>
    Body:    {"tenant_id": 1, "branch_id": 2, "customer": 12,
              "invoice_date": "2026-07-30", "currency": 1,
              "lines": [{"product": 345, "quantity": "2", "unit_price": "150.00"}]}

    ينشئ فاتورة مبيعات **مسوّدة دائماً** — لا ترحيل تلقائي ولا قيود محاسبية،
    لأن الترحيل يبقى قراراً بشرياً من الواجهة. الترقيم والضرائب وفحص المخزون
    تمرّ عبر SalesInvoiceSerializer نفسه المستخدَم في الواجهة.
    """
    unauthorized = _check_agent_key(request)
    if unauthorized is not None:
        return unauthorized

    from core.activity import log_activity
    from sales.serializers import SalesInvoiceSerializer
    from tenants.models import Branch

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
