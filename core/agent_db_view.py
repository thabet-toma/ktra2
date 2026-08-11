"""
واجهة برمجية للـ AI Agent لتنفيذ استعلامات SELECT على قاعدة البيانات.

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
    """
    # ─── الطبقة الثانية: مفتاح API (fail-closed: غياب الضبط = رفض دائم) ───
    expected_key = getattr(settings, "AGENT_DB_API_KEY", "")
    provided_key = request.headers.get("X-Agent-Key", "").strip()
    if not expected_key or provided_key != expected_key:
        return Response(
            {"error": "Unauthorized — مفتاح API غير صحيح أو غير موجود."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

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
