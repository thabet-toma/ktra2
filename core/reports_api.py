"""T-REPORTS: نقطتا قسم التقارير.

`GET /api/reports/`        → فهرس التقارير مجمَّعاً بالفئات (يُصفَّى بصلاحيات المستخدم)
`GET /api/reports/<key>/`  → تشغيل تقرير: أعمدة + صفوف + إجماليات

النقطتان رقيقتان عمداً — كل المعرفة في `core.reports`، فالتقرير الجديد لا يمسّ
هذا الملف ولا الروابط.
"""
import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.access import require_perm, user_has_perm
from core.reports import REPORTS, report_catalog, run_report
from core.tenant_utils import get_tenant

logger = logging.getLogger(__name__)


@api_view(["GET"])
def reports_catalog(request):
    """فهرس التقارير — لا يعرض ما لا يملك المستخدم صلاحيته."""
    tenant = get_tenant(request)
    if not tenant:
        return Response({"categories": []})
    user = getattr(request, "user", None)
    categories = []
    for category in report_catalog():
        allowed = [
            report for report in category["reports"]
            if not report["permission"] or user_has_perm(user, tenant, report["permission"])
        ]
        if allowed:
            categories.append({**category, "reports": allowed})
    return Response({"categories": categories})


@api_view(["GET"])
def report_run(request, key: str):
    spec = REPORTS.get(key)
    if spec is None:
        return Response({"error": "تقرير غير معروف."}, status=404)
    tenant = get_tenant(request)
    if not tenant:
        return Response({"error": "لا يوجد شركة (tenant)."}, status=400)
    if spec.permission:
        require_perm(request, spec.permission, tenant=tenant)
    try:
        payload = run_report(key, tenant.TenantID, request.query_params.dict())
    except Exception:
        logger.exception("reports.run_failed key=%s tenant=%s", key, tenant.TenantID)
        return Response({"error": f"تعذّر توليد تقرير «{spec.title}»."}, status=500)
    return Response(payload)
