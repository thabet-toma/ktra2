"""T-REPORTS: نقطتا قسم التقارير.

`GET /api/reports/`        → فهرس التقارير مجمَّعاً بالفئات (يُصفَّى بصلاحيات المستخدم)
`GET /api/reports/<key>/`  → تشغيل تقرير: أعمدة + صفوف + إجماليات

النقطتان رقيقتان عمداً — كل المعرفة في `core.reports`، فالتقرير الجديد لا يمسّ
هذا الملف ولا الروابط.
"""
import hashlib
import json
import logging
import os

from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.access import require_perm, user_has_perm
from core.reports import REPORTS, report_catalog, run_drill, run_report
from core.tenant_utils import get_tenant

logger = logging.getLogger(__name__)

# P2-3 (SCALABILITY_AUDIT): لم يكن على أي تقرير سطر كاش واحد — وإعادة تشغيل
# التقرير نفسه (تغيير الفرز، رجوع، طباعة) تُعيد تنفيذ كل استعلاماته من الصفر.
# النافذة قصيرة عمداً وعلى نمط الداشبورد الموجود أصلاً (60ث): تكفي لابتلاع
# إعادة التشغيل المتلاحقة، ولا تُبقي تقريراً مالياً قديماً بعد ترحيل مستند.
# المفتاح يحمل المستخدم أيضاً لأن التقارير محكومة بالصلاحيات — لا تُقدَّم
# نسخة مستخدمٍ لآخر مهما تطابقت المعاملات. صفر يعطّل الكاش كلياً.
REPORT_CACHE_SECONDS = int(os.environ.get("REPORT_CACHE_SECONDS", "60"))


def _report_cache_version(tenant_id) -> int:
    """ختم نسخة تقارير الشركة — يُبطِل كاشَها كلّه بزيادةٍ واحدة.

    الكاش ملفّي (`core/cache_backends.py`، لا Redis) فلا حذف بنمط مفتاح: المفتاح
    الوحيد الذي يمكن مسحه هو مفتاحٌ نعرف نصّه. فالنسخة تدخل في **كل** مفتاح
    تقرير، وزيادتها تجعل المفاتيح القديمة غير قابلة للإصابة فتنتهي بمهلتها.
    """
    try:
        return int(cache.get(f"reports:ver:{tenant_id}") or 1)
    except Exception:
        # الكاش مُسرِّع لا مصدر حقيقة — تعثّره لا يُسقط طلباً (قاعدة core.md 4).
        return 1


def invalidate_tenant_reports(tenant_id) -> None:
    """يُبطِل تقارير شركةٍ فوراً بعد كتابةٍ تغيّر أرقامها.

    بدونه كان المستخدم يضغط «تثبيت الحدود المقترَحة» ثم يُعاد تشغيل التقرير
    فيعود **من الكاش** بأرقامه القديمة لستّين ثانية — فيبدو الزرّ معطّلاً
    ويُضغط ثانيةً وثالثة. الفعل الذي يغيّر الأرقام يجب أن يُبطل نسختها.
    """
    try:
        cache.set(f"reports:ver:{tenant_id}", _report_cache_version(tenant_id) + 1, None)
    except Exception:
        logger.warning("reports.cache_invalidate_failed tenant=%s", tenant_id, exc_info=True)


def _report_cache_key(key, tenant_id, user_id, params):
    payload = json.dumps(
        {"k": key, "t": tenant_id, "u": user_id, "p": params},
        sort_keys=True, ensure_ascii=False,
    )
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
    return f"report:{tenant_id}:{_report_cache_version(tenant_id)}:{key}:{digest}"


def _validation_message(exc: ValidationError) -> str:
    """رسالة واحدة من تفصيل DRF — قائمةً كان أو قاموساً أو نصّاً."""
    detail = exc.detail
    while isinstance(detail, (list, tuple, dict)):
        if not detail:
            return "مُدخل غير صالح."
        detail = next(iter(detail.values())) if isinstance(detail, dict) else detail[0]
    return str(detail)


def _user_display(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    return user.get_full_name() or user.username


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


def _authorize(request, key: str):
    """حارسٌ واحد للتشغيل وللتنقيب — `(spec, tenant, None)` أو `(None, None, رد)`.

    التنقيب نافذةٌ على نفس بيانات التقرير، فلا يجوز أن يكون بابه أوسع من بابه:
    نسخُ الحارس كان يعني أن أي تشديدٍ لاحق يُطبَّق على نقطةٍ وينسى الأخرى.
    """
    spec = REPORTS.get(key)
    if spec is None:
        return None, None, Response({"error": "تقرير غير معروف."}, status=404)
    tenant = get_tenant(request)
    if not tenant:
        return None, None, Response({"error": "لا يوجد شركة (tenant)."}, status=400)
    # الترخيص قبل الصلاحية — تقرير وحدةٍ غير مرخّصة «غير معروف» لا «ممنوع»،
    # فلا يكشف ردُّه وجودها (نفس ترتيب `after_sales/views.py::initial`).
    if spec.module:
        from core.modules import module_enabled

        if not module_enabled(tenant, spec.module):
            return None, None, Response({"error": "تقرير غير معروف."}, status=404)
    if spec.permission:
        require_perm(request, spec.permission, tenant=tenant)
    return spec, tenant, None


@api_view(["GET"])
def report_run(request, key: str):
    spec, tenant, denied = _authorize(request, key)
    if denied is not None:
        return denied
    params = request.query_params.dict()
    cache_key = None
    if REPORT_CACHE_SECONDS > 0:
        cache_key = _report_cache_key(
            key, tenant.TenantID, getattr(request.user, "id", None), params,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
    try:
        payload = run_report(key, tenant.TenantID, params)
    except ValidationError as exc:
        # مُدخل مرفوض لا عطل: تقريرٌ يحرس فترته (كشف الساعات يرفض ما فوق 31
        # يوماً) كان يظهر للمستخدم «تعذّر توليد التقرير» — رسالة عطلٍ عن خطأٍ
        # يستطيع إصلاحه بنفسه. تعود رسالته كما كتبها التقرير.
        return Response({"error": _validation_message(exc)}, status=400)
    except Exception:
        logger.exception("reports.run_failed key=%s tenant=%s", key, tenant.TenantID)
        return Response({"error": f"تعذّر توليد تقرير «{spec.title}»."}, status=500)
    # مَن ولّد التقرير — يُطبع في ترويسته وملفّه. آمن داخل الكاش: مفتاحه يحمل
    # المستخدم أصلاً، فلا تُقدَّم نسخة مستخدمٍ لآخر.
    payload["generated_by"] = _user_display(getattr(request, "user", None))
    if cache_key is not None:
        cache.set(cache_key, payload, REPORT_CACHE_SECONDS)
    return Response(payload)


@api_view(["GET"])
def report_drill(request, key: str):
    """`GET /api/reports/<key>/drill/` — الأسطر التي كوّنت صفّاً مجمَّعاً.

    نفس فلاتر التشغيل تُرسَل كما هي، ومعها مفاتيح الصفّ (`spec.drill_keys`).
    وبلا كاش عمداً: التنقيب فعلُ تحقّقٍ من رقمٍ ظهر للتوّ، فتقديم نسخةٍ مخزَّنة
    له يُفسد بالضبط السببَ الذي فُتح لأجله.
    """
    spec, tenant, denied = _authorize(request, key)
    if denied is not None:
        return denied
    if spec.drill is None:
        return Response({"error": f"التقرير «{spec.title}» لا يُنقَّب."}, status=400)
    params = request.query_params.dict()
    try:
        payload = run_drill(key, tenant.TenantID, params)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=400)
    except Exception:
        logger.exception("reports.drill_failed key=%s tenant=%s", key, tenant.TenantID)
        return Response({"error": "تعذّر فتح تفصيل السطر."}, status=500)
    return Response(payload)
