"""حارسُ عزلٍ لموظّف المنصّة: «يرى صفوفَه هو، لا صفوفَ زميله» (211-D).

`platform_ops` استثناءٌ موثَّقٌ من قاعدة `tenant FK` — نماذجُها تخدم المنصّةَ
نفسَها لا شركةَ زبونٍ بعينها (راجع رأس `platform_ops/views.py`). فحارسُ عزل
الشركة المعتاد لا يحمي هذه المسارات إطلاقاً؛ يحميها حارسان مختلفان:

- `IsPlatformOperationsManager` (سوبر أدمن) يرى **الجميع** بحكم موقعه.
- `IsPlatformOperationsStaff` (موظّفٌ عاديّ) يُقبَل على المسار ثمّ يُضيَّق يدوياً
  داخل `get_queryset` — وهذا التضييق **غيرُ مرئيّ حين يُنسى**: المسارُ يستمرّ
  في العمل، ويعمل للجميع.

هذا الملفُّ يعدّ كلَّ مسارٍ يقبل `IsPlatformOperationsStaff` من الـURLconf نفسِه
(لا قائمةً مكتوبةً يدوياً — القائمةُ اليدويّةُ تتقادم بصمتٍ كما تقادمت
`core/tests/test_platform_admin.py::_platform_routes` لولا أنّها محسوبة)، ثمّ
يُثبت لكلّ مسارِ قائمةٍ قابلٍ للتنفيذ أنّ موظّفاً غيرَ مديرٍ لا يرى صفَّ زميله.
"""
import datetime
import inspect
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.permissions import OperandHolder
from rest_framework.test import APIClient

from core.urls import urlpatterns as core_urlpatterns
from tenants.models import Tenant

from platform_ops.models import (
    DailyRating,
    Engagement,
    PerformanceReviewRequest,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformMeeting,
    PlatformMeetingAttendance,
    PlatformNotification,
    ServiceSubscription,
    WorkOrder,
)
from platform_ops.permissions import IsPlatformOperationsStaff

User = get_user_model()


# ==============================================================================
# التعداد — من الـURLconf لا من قائمةٍ يدويّة
# ==============================================================================


def _contains_staff_permission(entry) -> bool:
    """هل `IsPlatformOperationsStaff` حاضرةٌ في عنصر `permission_classes`؟

    العنصرُ قد يكون الصنفَ ذاتَه، أو تركيبَ OR (`A | B`) الذي يُنتج **كائن**
    `OperandHolder` (لا صنفاً) بحقلَي `op1_class`/`op2_class` — وأحدُهما قد يكون
    `OperandHolder` مُتداخلاً (`A | B | C`)، فالفحصُ تعاوديّ.
    """
    if isinstance(entry, OperandHolder):
        return (
            _contains_staff_permission(entry.op1_class)
            or _contains_staff_permission(entry.op2_class)
        )
    return entry is IsPlatformOperationsStaff


def _walk(patterns, prefix=""):
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if hasattr(entry, "url_patterns"):
            yield from _walk(entry.url_patterns, route)
        else:
            yield route, entry


def _staff_permitted_routes():
    """كل مسار تحت `/api/platform/ops/` تقبله `IsPlatformOperationsStaff` — محسوبٌ من `core.urls`.

    نفسُ منهج `core/tests/test_platform_admin.py::_platform_routes`: المشيُ على
    `core.urls.urlpatterns` الحقيقيّ لا استيراد `platform_ops.urls` مباشرة، فلو
    تغيّرت بادئةُ التركيب (`include`) يظهر أثرُها هنا كما تظهر في أيّ طلبٍ حقيقي.
    """
    routes = []
    for route, entry in _walk(core_urlpatterns):
        clean = route.replace("^", "").replace("$", "")
        if not clean.startswith("api/platform/ops/"):
            continue
        callback = entry.callback
        view_cls = getattr(callback, "cls", None)
        permission_classes = getattr(view_cls, "permission_classes", None) if view_cls else None
        if not permission_classes:
            continue
        if not any(_contains_staff_permission(p) for p in permission_classes):
            continue
        clean = re.sub(r"<int:[^>]+>", "1", clean)
        clean = re.sub(r"<str:[^>]+>", "x", clean)
        clean = re.sub(r"\(\?P<\w+>[^)]+\)", "1", clean)
        routes.append("/" + clean)
    return sorted(set(routes))


#: البادئاتُ الثلاثُ التي تخدم منها الوحدةُ جمهوراً مختلفاً (راجع `core/urls.py`)؛
#: التضييقُ المخفيُّ قد يعيش تحت أيّها لا تحت `ops/` وحدها.
PLATFORM_PREFIXES = ("api/platform/", "api/my-agent/", "api/platform-staff/")


def _views_narrowing_on_staff_identity():
    """كلُّ view يفرّق بين موظّفِ منصّةٍ وغيرِه **داخل جسمه** لا في `permission_classes`.

    التعدادُ الأوّل (`_staff_permitted_routes`) يسأل: «من تسمح له اللائحةُ بالدخول؟».
    وهذا يسأل سؤالاً آخرَ لا يُغنيه الأوّل: «من يقرّر داخلَه ماذا يُري الموظّفَ؟».
    والفرقُ ليس نظرياً: `DailyRatingViewSet` لائحتُه `[IsAuthenticated]` وحدها —
    فلا يراه التعدادُ الأوّل إطلاقاً — بينما `get_queryset` فيه يضيّق للموظّف بسطرٍ
    واحدٍ حذفُه يكشف تقييماتِ كلِّ زميلٍ عند كلِّ زبون. تعدادٌ يقيس بابَ الدخول
    وحدَه يترك هذا البابَ الخلفيَّ بلا حارس.

    ولأنّ الشرطَ سلوكٌ لا تصريح، يُقرأ **مصدرُ الصنف** نفسِه: الـmixins الموروثةُ
    تدخل بالتبعيّة عبر `inspect.getsource` على الصنف المُعرَّف، وهو ما نريد.
    """
    found = {}
    for route, entry in _walk(core_urlpatterns):
        clean = route.replace("^", "").replace("$", "")
        if not clean.startswith(PLATFORM_PREFIXES):
            continue
        view_cls = getattr(entry.callback, "cls", None)
        if view_cls is None:
            continue
        permission_classes = getattr(view_cls, "permission_classes", None) or []
        if any(_contains_staff_permission(p) for p in permission_classes):
            continue  # محسوبٌ في التعداد الأوّل
        try:
            source = inspect.getsource(view_cls)
        except (OSError, TypeError):  # pragma: no cover - أصنافٌ مولَّدةٌ بلا مصدر
            continue
        # الهويّةُ نفسُها تُكتَب بوجهين: صنفَ صلاحيّةٍ (`IsPlatformOperationsStaff`)
        # أو الدالّةَ المساعدة (`is_platform_employee`) — والثاني أخفى من الأوّل
        # لأنّه لا يشبه صلاحيّةً أصلاً، فيلزم عدُّه معه لا بعده.
        if not any(token in source for token in ("IsPlatformOperationsStaff", "is_platform_employee")):
            continue
        found.setdefault(view_cls.__name__, set()).add("/" + clean)
    return found


#: مصيرُ كلّ view ذي تضييقٍ مخفيّ — يُنفَّذ عليه فحصُ ملكيّةٍ، أو يُستثنى بسببٍ صريح.
NARROWING_VIEWS_ACCOUNTED_FOR = {
    "DailyRatingViewSet":
        "مُنفَّذ — `DailyRatingScopeTest` أدناه يُثبت أنّ الموظّفَ لا يرى تقييمَ زميله.",
    "PlatformStaffCapabilitiesView":
        "مُستثنى — لا يردّ صفوفاً بل بواليناتٍ عن **صاحب الجلسة نفسِه** "
        "(`is_platform_employee(user)`)، فلا ملكيّةَ صفٍّ تُفحَص.",
    "CustomerProfitabilityView":
        "مُستثنى — لائحتُه `[IsPlatformOperationsManager]`، والذكرُ في **شرحه** لا في كوده: "
        "يقول صراحةً «فلا `IsPlatformOperationsStaff` هنا» لأنّ الصفَّ يحمل تكلفةَ الموظّف "
        "البشريّة. والكشفُ هنا موجبُ الخطأ عمداً: تضييقُ الكاشف ليُسقِط ذكرَ الشرح يُسقِط "
        "معه تضييقاً حقيقياً كُتب بأسلوبٍ غيرِ متوقَّع — وثمنُ السطر الزائد كلمةٌ، وثمنُ "
        "السطر الناقص تسريب.",
}


#: مسارٌ لا يمكن تنفيذُه بفحص «لا صفَّ زميل» — كتابةٌ لا قراءة، أو فعلٌ تفصيليّ
#: على صفٍّ واحدٍ يحتاج pk (والحارسُ عليه مزدوجٌ أصلاً: `get_object()` يعتمد
#: `get_queryset()` المضيَّقة نفسَها المُثبَتة على المسار الأساسي)، مع السبب.
EXCUSED_ROUTES = {
    "/api/platform/ops/champions/":
        "لوحةٌ جماعيّةٌ مُجمَّعةٌ بالتصميم (§١٠ — جمهورُها كلُّ الموظّفين المسجَّلين)؛ "
        "لا صفَّ فرديّاً يُنسَب لموظّفٍ فتُفحَص ملكيّتُه.",
    "/api/platform/ops/employees/1/activity/":
        "فعلٌ تفصيليٌّ بـpk يعتمد `get_object()` على نفس `get_queryset()` المضيَّقة "
        "المُثبَتة في `employees/<pk>/`، ويُضيف تحقّقاً صريحاً ثانياً (`emp.user_id != request.user.id`).",
    "/api/platform/ops/employees/1/performance/":
        "فعلٌ تفصيليٌّ بـpk — نفس عزل `activity/` أعلاه بالضبط (تعليقُ الكود يقول ذلك حرفياً).",
    "/api/platform/ops/employees/1/pilot-performance/":
        "فعلٌ تفصيليٌّ بـpk — نفس عزل `activity/` أعلاه بالضبط.",
    "/api/platform/ops/employees/1/targets/":
        "فعلٌ تفصيليٌّ بـpk، والقراءةُ منه مضيَّقةٌ بنفس `get_queryset()`؛ والكتابةُ (PATCH) للمدير وحده أصلاً.",
    "/api/platform/ops/employees/1/wallet/":
        "فعلٌ تفصيليٌّ بـpk — نفس عزل `activity/` أعلاه بالضبط.",
    "/api/platform/ops/work-orders/create/":
        "فعلُ إنشاءٍ (POST) لا قراءةَ قائمة.",
    "/api/platform/ops/work-orders/1/assign/":
        "فعلٌ تفصيليٌّ بـpk، وكتابةٌ (POST) لمدير العمليات وحده.",
    "/api/platform/ops/work-orders/1/change-priority/":
        "فعلٌ تفصيليٌّ بـpk، وكتابةٌ (POST) لمدير العمليات وحده.",
    "/api/platform/ops/work-orders/1/comments/":
        "فعلٌ تفصيليٌّ بـpk أمرِ عملٍ واحد؛ محكومٌ بـ`get_object()` على نفس القائمة المضيَّقة.",
    "/api/platform/ops/work-orders/1/deliverables/":
        "فعلٌ تفصيليٌّ بـpk أمرِ عملٍ واحد؛ محكومٌ بـ`get_object()` على نفس القائمة المضيَّقة.",
    "/api/platform/ops/work-orders/1/document-links/":
        "فعلٌ تفصيليٌّ بـpk أمرِ عملٍ واحد؛ محكومٌ بـ`get_object()` على نفس القائمة المضيَّقة.",
    "/api/platform/ops/work-orders/1/link-document/":
        "فعلٌ تفصيليٌّ بـpk، وكتابةٌ (POST).",
    "/api/platform/ops/work-orders/1/deliverables/1/review/":
        "فعلٌ تفصيليٌّ بمعرّفَين (pk أمر العمل، ومعرّف المُسلَّم)، وكتابةٌ.",
    "/api/platform/ops/work-orders/1/transition/":
        "فعلٌ تفصيليٌّ بـpk، وكتابةٌ (POST).",
    "/api/platform/ops/policy-profiles/":
        "بياناتُ سياسةٍ عامّةٍ مشتركةٌ حسب التخصّص (`specialty`) لا حسب موظّف — لا "
        "`get_queryset` مخصَّص هنا أصلاً، ولا حقلَ ملكيّةٍ على النموذج.",
    "/api/platform/ops/policy-profiles/1/":
        "نفسُ سبب `policy-profiles/` أعلاه — تفصيلاً على بيانةٍ مشتركة.",
    "/api/platform/ops/performance-snapshots/capture/":
        "فعلٌ تفصيليٌّ (POST) لالتقاط لقطةٍ — لمدير العمليات وحده.",
    "/api/platform/ops/notifications/mark-all-read/":
        "فعلُ كتابةٍ (POST) لا قراءةَ قائمة.",
    "/api/platform/ops/notifications/unread-count/":
        "عددٌ إجماليٌّ لا صفوف؛ يعتمد نفس فلتر `recipient=request.user` المُثبَت "
        "على `notifications/` فلا يضيف شيئاً يُفحص على مستوى الصفّ.",
    "/api/platform/ops/notifications/1/mark-read/":
        "فعلٌ تفصيليٌّ (POST) بـpk.",
    "/api/platform/ops/performance-review-requests/open/":
        "فعلُ كتابةٍ (POST)؛ والموظّفُ يُشتقّ من الجلسة (`request.user`) لا من معاملٍ يمكن تزويرُه.",
    "/api/platform/ops/performance-review-requests/1/recapture/":
        "فعلٌ تفصيليٌّ (POST) بـpk — لمدير العمليات وحده.",
    "/api/platform/ops/performance-review-requests/1/resolve/":
        "فعلٌ تفصيليٌّ (POST) بـpk — لمدير العمليات وحده.",
    "/api/platform/ops/meetings/create/":
        "فعلُ إنشاءٍ (POST) — مدير العمليات وحده (`_require_manager`).",
    "/api/platform/ops/meetings/1/update/":
        "فعلٌ تفصيليٌّ (POST) — مدير العمليات وحده.",
    "/api/platform/ops/meetings/1/cancel/":
        "فعلٌ تفصيليٌّ (POST) — مدير العمليات وحده.",
    "/api/platform/ops/meetings/1/invite/":
        "فعلٌ تفصيليٌّ (POST) — مدير العمليات وحده؛ لا صفَّ فرديّاً يُملَك بل قائمةُ مدعوّين.",
    "/api/platform/ops/meetings/1/attendance/":
        "فعلٌ تفصيليٌّ (GET) — دفترُ الحضور كاملاً لمدير العمليات وحده.",
    "/api/platform/ops/meetings/1/decide-excuse/":
        "فعلٌ تفصيليٌّ (POST) — مدير العمليات وحده.",
}

#: المسارات التي يُنفَّذ عليها فحصُ «لا صفَّ زميل» فعلياً في هذه المجموعة —
#: تُقرأ كنظيرةٍ لِـ`EXCUSED_ROUTES` عند فحص اكتمال التعداد.
EXERCISED_ROUTES = frozenset({
    "/api/platform/ops/companies/1/health/",
    "/api/platform/ops/dashboard/",
    "/api/platform/ops/champions/",  # مُستثنى ملكيّةً لكنّه يُطلَب فعلياً في اختبار توفّره
    "/api/platform/ops/employees/",
    "/api/platform/ops/employees/my-companies/",
    "/api/platform/ops/employees/ranking/",
    "/api/platform/ops/employees/1/",
    "/api/platform/ops/work-orders/",
    "/api/platform/ops/work-orders/queue/",
    "/api/platform/ops/work-orders/1/",
    "/api/platform/ops/performance-snapshots/",
    "/api/platform/ops/performance-snapshots/1/",
    "/api/platform/ops/notifications/",
    "/api/platform/ops/notifications/1/",
    "/api/platform/ops/activity-logs/",
    "/api/platform/ops/activity-logs/1/",
    "/api/platform/ops/performance-review-requests/",
    "/api/platform/ops/performance-review-requests/1/",
    "/api/platform/ops/meetings/",
    "/api/platform/ops/meetings/1/",
    "/api/platform/ops/meetings/1/check-in/",
    "/api/platform/ops/meetings/1/excuse/",
})
# `champions/` مذكورةٌ في القائمتين معاً بقصد: هي مُستثناةٌ من فحص الملكيّة
# (لوحةٌ جماعيّة لا صفَّ فرديّاً) لكنّ الاختبار يستدعيها فعلياً ليثبت أنّها
# مُتاحةٌ لموظّفٍ عاديّ لا لمديرٍ وحده — فهي "مُستثناة" و"مُنفَّذة" معاً لا "منسيّة"،
# والاتحادُ بينهما (لا الفرقُ) هو ما يُقارَن بالتعداد الكامل.


class StaffScopeGuardCensusTest(TestCase):
    """اكتمالُ التعداد: كلُّ مسارٍ يُقرَّر مصيرُه — يُنفَّذ أو يُستثنى بسببٍ صريح."""

    def test_census_is_non_empty_and_meets_a_minimum_count(self):
        """حارسٌ ضدّ توقّف منطق الجمع بصمت — لو عاد فارغاً لمرّت كلّ الاختبارات التالية كذباً."""
        routes = _staff_permitted_routes()
        self.assertGreaterEqual(
            len(routes), 30, f"التعدادُ أصغرُ من المتوقَّع كثيراً — احتمالُ عطبٍ في منطق الجمع: {routes}",
        )
        self.assertIn("/api/platform/ops/employees/", routes)
        self.assertIn("/api/platform/ops/work-orders/", routes)

    def test_every_censused_route_is_exercised_or_explicitly_excused(self):
        """لا مسارَ يُنسى: اتحادُ (المُنفَّذ ∪ المُستثنى) يساوي التعدادَ الكامل تماماً."""
        census = set(_staff_permitted_routes())
        accounted_for = set(EXCUSED_ROUTES) | EXERCISED_ROUTES

        forgotten = census - accounted_for
        self.assertEqual(
            forgotten, set(),
            f"مسارٌ جديدٌ يقبل IsPlatformOperationsStaff ولم يُقرَّر مصيرُه (نفَّذ أو استثنِ): {forgotten}",
        )

        stale = accounted_for - census
        self.assertEqual(
            stale, set(),
            f"مسارٌ في قوائم هذا الملفّ لم يعد ضمن التعداد الحالي — وثّقه بلا مسوّغ: {stale}",
        )

    def test_every_view_narrowing_on_staff_identity_is_accounted_for(self):
        """التضييقُ المخفيُّ خارجَ `permission_classes` يُقرَّر مصيرُه هو الآخر.

        بلا هذا الفحص يبقى البابُ الخلفيُّ مفتوحاً: viewُ لائحتُه `[IsAuthenticated]`
        يضيّق للموظّف في `get_queryset` فلا يظهر في التعداد الأوّل ولا يحرسه أحد.
        """
        views = _views_narrowing_on_staff_identity()
        self.assertNotEqual(views, {}, "لم يُعثر على أيّ تضييقٍ مخفيّ — احتمالُ عطبٍ في قراءة المصدر.")

        forgotten = set(views) - set(NARROWING_VIEWS_ACCOUNTED_FOR)
        self.assertEqual(
            forgotten, set(),
            "viewٌ يفرّق بين موظّفِ المنصّة وغيرِه داخلَ جسمه ولم يُقرَّر مصيرُه "
            f"(نفِّذ عليه فحصَ ملكيّةٍ أو استثنِه بسبب): {forgotten}",
        )

        stale = set(NARROWING_VIEWS_ACCOUNTED_FOR) - set(views)
        self.assertEqual(
            stale, set(),
            f"viewٌ في قائمة هذا الملفّ لم يعد يضيّق على هويّة الموظّف: {stale}",
        )


class _StaffScopeFixture(TestCase):
    """موظّفان بشركتين منفصلتين تماماً — كلُّ صفٍّ يُنشَأ للمنطقة (أ) له نظيرٌ في (ب)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(CompanyName="شركة عزل أ")
        cls.tenant_b = Tenant.objects.create(CompanyName="شركة عزل ب")
        for tenant in (cls.tenant_a, cls.tenant_b):
            ServiceSubscription.objects.create(tenant=tenant, status=ServiceSubscription.Status.ACTIVE)

        cls.user_a = User.objects.create_user(
            username="guard_layan", email="layan@platform.local", password="x",
        )
        cls.user_b = User.objects.create_user(
            username="guard_rami", email="rami@platform.local", password="x",
        )
        cls.employee_a = PlatformEmployee.objects.create(
            user=cls.user_a, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        cls.employee_b = PlatformEmployee.objects.create(
            user=cls.user_b, specialty="review", status=PlatformEmployee.Status.ACTIVE,
        )
        cls.manager = User.objects.create_superuser(
            username="guard_manager", email="manager@platform.local", password="x",
        )

        Engagement.objects.create(
            employee=cls.employee_a, tenant=cls.tenant_a, status=Engagement.Status.ACTIVE,
        )
        Engagement.objects.create(
            employee=cls.employee_b, tenant=cls.tenant_b, status=Engagement.Status.ACTIVE,
        )

        cls.wo_a = WorkOrder.objects.create(
            tenant=cls.tenant_a, title="أمرُ عملٍ لشركة أ", assignee=cls.employee_a,
        )
        cls.wo_b = WorkOrder.objects.create(
            tenant=cls.tenant_b, title="أمرُ عملٍ لشركة ب", assignee=cls.employee_b,
        )

        cls.snap_a = PerformanceSnapshot.objects.create(
            employee=cls.employee_a, period_year=2026, period_month=1,
        )
        cls.snap_b = PerformanceSnapshot.objects.create(
            employee=cls.employee_b, period_year=2026, period_month=1,
        )

        cls.notif_a = PlatformNotification.objects.create(
            recipient=cls.user_a, tenant=cls.tenant_a,
            notification_type=PlatformNotification.NotificationType.SLA_BREACH,
            title="تجاوزُ أجلٍ — أ", message="تفصيلٌ.",
        )
        cls.notif_b = PlatformNotification.objects.create(
            recipient=cls.user_b, tenant=cls.tenant_b,
            notification_type=PlatformNotification.NotificationType.SLA_BREACH,
            title="تجاوزُ أجلٍ — ب", message="تفصيلٌ.",
        )

        cls.log_a = PlatformActivityLog.objects.create(
            employee=cls.employee_a, tenant=cls.tenant_a,
            action=PlatformActivityLog.Action.OTHER, description="نشاطٌ — أ",
        )
        cls.log_b = PlatformActivityLog.objects.create(
            employee=cls.employee_b, tenant=cls.tenant_b,
            action=PlatformActivityLog.Action.OTHER, description="نشاطٌ — ب",
        )

        cls.review_a = PerformanceReviewRequest.objects.create(
            employee=cls.employee_a, period_year=2026, period_month=1, reason="اعتراضٌ — أ",
        )
        cls.review_b = PerformanceReviewRequest.objects.create(
            employee=cls.employee_b, period_year=2026, period_month=1, reason="اعتراضٌ — ب",
        )

        now = timezone.now()
        cls.meeting_a = PlatformMeeting.objects.create(
            title="اجتماعٌ — أ", start=now, end=now + datetime.timedelta(hours=1),
            meeting_link="https://meet.example.test/a",
        )
        cls.meeting_b = PlatformMeeting.objects.create(
            title="اجتماعٌ — ب", start=now, end=now + datetime.timedelta(hours=1),
            meeting_link="https://meet.example.test/b",
        )
        cls.attendance_a = PlatformMeetingAttendance.objects.create(
            meeting=cls.meeting_a, employee=cls.employee_a,
        )
        cls.attendance_b = PlatformMeetingAttendance.objects.create(
            meeting=cls.meeting_b, employee=cls.employee_b,
        )

    def setUp(self):
        self.client = APIClient()

    def _ids(self, response):
        payload = response.data
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        return {row["id"] for row in rows}


class WorkOrdersScopeTest(_StaffScopeFixture):
    """`work-orders/` — الملكيّةُ بـ`tenant` مشتقّةً من ارتباطات الموظّف، لا بـ`assignee` مباشرة."""

    def test_list_hides_a_colleague_company_order(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/work-orders/"))
        self.assertIn(self.wo_a.pk, ids)
        self.assertNotIn(self.wo_b.pk, ids)

    def test_list_shows_every_company_to_the_manager(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/work-orders/"))
        self.assertIn(self.wo_a.pk, ids)
        self.assertIn(self.wo_b.pk, ids)

    def test_detail_404s_on_a_colleague_company_order(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/work-orders/{self.wo_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/work-orders/{self.wo_a.pk}/").status_code, 200,
        )

    def test_queue_hides_a_colleague_assignment(self):
        """ملكيّةُ الطابور بـ`assignee` — `list_employee_work_order_queue` يفلتر `assignee__user=request.user`."""
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/work-orders/queue/"))
        self.assertIn(self.wo_a.pk, ids)
        self.assertNotIn(self.wo_b.pk, ids)


class PerformanceSnapshotsScopeTest(_StaffScopeFixture):
    """`performance-snapshots/` — الملكيّةُ بـ`employee`."""

    def test_list_hides_a_colleague_row(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/performance-snapshots/"))
        self.assertIn(self.snap_a.pk, ids)
        self.assertNotIn(self.snap_b.pk, ids)

    def test_list_shows_both_to_the_manager(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/performance-snapshots/"))
        self.assertIn(self.snap_a.pk, ids)
        self.assertIn(self.snap_b.pk, ids)

    def test_detail_404s_on_a_colleague_row(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/performance-snapshots/{self.snap_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/performance-snapshots/{self.snap_a.pk}/").status_code, 200,
        )


class NotificationsScopeTest(_StaffScopeFixture):
    """`notifications/` — الملكيّةُ بـ`recipient`، وهي الوحيدةُ التي **لا** تفتح للمدير كذلك.

    `get_queryset` هنا يفلتر `recipient=self.request.user` بلا استثناءٍ للمدير (الإشعارُ
    شخصيٌّ حتى للمدير) — فلا فحصَ رجوعٍ «المديرُ يرى الاثنين» على هذا المسار تحديداً؛
    إثباتُ أنّ القائمة ليست فارغةً للجميع يأتي من ظهور صفّ (أ) نفسِه في استجابة (أ).
    """

    def test_list_hides_a_colleague_notification(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/notifications/"))
        self.assertIn(self.notif_a.pk, ids)
        self.assertNotIn(self.notif_b.pk, ids)

    def test_detail_404s_on_a_colleague_notification(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/notifications/{self.notif_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/notifications/{self.notif_a.pk}/").status_code, 200,
        )


class ActivityLogsScopeTest(_StaffScopeFixture):
    """`activity-logs/` — الملكيّةُ بـ`employee`."""

    def test_list_hides_a_colleague_entry(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/activity-logs/"))
        self.assertIn(self.log_a.pk, ids)
        self.assertNotIn(self.log_b.pk, ids)

    def test_list_shows_both_to_the_manager(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/activity-logs/"))
        self.assertIn(self.log_a.pk, ids)
        self.assertIn(self.log_b.pk, ids)

    def test_detail_404s_on_a_colleague_entry(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/activity-logs/{self.log_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/activity-logs/{self.log_a.pk}/").status_code, 200,
        )


class PerformanceReviewRequestsScopeTest(_StaffScopeFixture):
    """`performance-review-requests/` — الملكيّةُ بـ`employee`."""

    def test_list_hides_a_colleague_request(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/performance-review-requests/"))
        self.assertIn(self.review_a.pk, ids)
        self.assertNotIn(self.review_b.pk, ids)

    def test_list_shows_both_to_the_manager(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/performance-review-requests/"))
        self.assertIn(self.review_a.pk, ids)
        self.assertIn(self.review_b.pk, ids)

    def test_detail_404s_on_a_colleague_request(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/performance-review-requests/{self.review_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/performance-review-requests/{self.review_a.pk}/").status_code, 200,
        )


class MeetingsScopeTest(_StaffScopeFixture):
    """`meetings/` — الملكيّةُ مشتقّةٌ من صفوف الحضور لا من عمود على النموذج نفسه.

    خلافاً لبقيّة الموارد هنا، اجتماعٌ واحدٌ قد يدعو موظّفَين معاً فلا يصحّ فحصُ
    «صفّان منفصلان لا يتقاطعان» — الثابتةُ الحارسة هنا اجتماعان منفصلان تماماً،
    كلٌّ منهما مدعوٌّ إليه موظّفٌ واحد فقط، فيثبت عزل الرؤية والدخول والاعتذار معاً.
    """

    def test_list_hides_a_colleague_meeting(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/meetings/"))
        self.assertIn(self.meeting_a.pk, ids)
        self.assertNotIn(self.meeting_b.pk, ids)

    def test_list_shows_both_to_the_manager(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/meetings/"))
        self.assertIn(self.meeting_a.pk, ids)
        self.assertIn(self.meeting_b.pk, ids)

    def test_detail_404s_on_a_colleague_meeting(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/meetings/{self.meeting_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/meetings/{self.meeting_a.pk}/").status_code, 200,
        )

    def test_check_in_cannot_be_performed_on_a_meeting_not_invited_to(self):
        """(ب) لا يستطيع الدخولَ على اجتماع (أ) — 404 يمنعه قبل بلوغ الخدمة أصلاً."""
        self.client.force_authenticate(self.user_b)
        response = self.client.post(f"/api/platform/ops/meetings/{self.meeting_a.pk}/check-in/")
        self.assertEqual(response.status_code, 404, response.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT)

    def test_check_in_records_only_the_caller_own_row(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.post(f"/api/platform/ops/meetings/{self.meeting_a.pk}/check-in/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["meeting_link"], self.meeting_a.meeting_link)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ATTENDED)
        self.attendance_b.refresh_from_db()
        self.assertEqual(self.attendance_b.status, PlatformMeetingAttendance.Status.ABSENT)

    def test_excuse_cannot_be_submitted_on_a_meeting_not_invited_to(self):
        self.client.force_authenticate(self.user_b)
        response = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting_a.pk}/excuse/", {"note": "سببٌ."},
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT)


class EmployeesScopeTest(_StaffScopeFixture):
    """`employees/` — الملكيّةُ بـ`user`، وفروعُ `my-companies/` و`ranking/`."""

    def test_list_hides_a_colleague_row(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/employees/"))
        self.assertIn(self.employee_a.pk, ids)
        self.assertNotIn(self.employee_b.pk, ids)

    def test_list_shows_both_to_the_manager(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/employees/"))
        self.assertIn(self.employee_a.pk, ids)
        self.assertIn(self.employee_b.pk, ids)

    def test_detail_404s_on_a_colleague_row(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/employees/{self.employee_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/employees/{self.employee_a.pk}/").status_code, 200,
        )

    def test_my_companies_excludes_a_colleague_engagement(self):
        """الملكيّةُ هنا بـ`Engagement.employee__user` — الشركةُ تُشتقّ من ارتباط الموظّف لا من الطلب."""
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/platform/ops/employees/my-companies/")
        self.assertEqual(response.status_code, 200, response.content)
        tenant_ids = {row["tenant_id"] for row in response.data}
        self.assertIn(self.tenant_a.pk, tenant_ids)
        self.assertNotIn(self.tenant_b.pk, tenant_ids)

    def test_ranking_refuses_staff_and_admits_the_manager(self):
        """`ranking/` مقبولةٌ على المسار (`IsPlatformOperationsStaff` في permission_classes) لكنّها مُغلقةٌ داخلياً على المدير وحده."""
        self.client.force_authenticate(self.user_a)
        self.assertEqual(self.client.get("/api/platform/ops/employees/ranking/").status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get("/api/platform/ops/employees/ranking/").status_code, 200)


class DashboardScopeTest(_StaffScopeFixture):
    """`dashboard/` — جسمٌ واحدٌ لا قائمة، لكنّ فيه مصفوفتَين مضيَّقتَين: `employees` و`companies`."""

    def test_employee_and_company_cards_are_scoped_to_the_caller(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/platform/ops/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)
        employee_user_ids = {row["user_id"] for row in response.data["employees"]}
        company_ids = {row["id"] for row in response.data["companies"]}
        self.assertIn(self.user_a.pk, employee_user_ids)
        self.assertNotIn(self.user_b.pk, employee_user_ids)
        self.assertIn(self.tenant_a.pk, company_ids)
        self.assertNotIn(self.tenant_b.pk, company_ids)

    def test_manager_sees_both_employees_and_both_companies(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/platform/ops/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)
        employee_user_ids = {row["user_id"] for row in response.data["employees"]}
        company_ids = {row["id"] for row in response.data["companies"]}
        self.assertIn(self.user_a.pk, employee_user_ids)
        self.assertIn(self.user_b.pk, employee_user_ids)
        self.assertIn(self.tenant_a.pk, company_ids)
        self.assertIn(self.tenant_b.pk, company_ids)


class CompanyHealthScopeTest(_StaffScopeFixture):
    """`companies/<tenant_id>/health/` — مسارُ تفصيلٍ يقبل معاملاً حقيقياً فيُنفَّذ لا يُستثنى.

    الملكيّةُ هنا بارتباطٍ نشطٍ (`Engagement`) بين الموظّف والشركة المطلوبة — شركةٌ
    خارج ارتباطات الموظّف تُعيد 404 لا 403 (لا تلميح بوجودها، كما يوثّق `CompanyHealthView`).
    """

    def test_staff_sees_own_engaged_company_and_404s_on_a_colleague_company(self):
        self.client.force_authenticate(self.user_a)
        own = self.client.get(f"/api/platform/ops/companies/{self.tenant_a.pk}/health/")
        self.assertEqual(own.status_code, 200, own.content)
        foreign = self.client.get(f"/api/platform/ops/companies/{self.tenant_b.pk}/health/")
        self.assertEqual(foreign.status_code, 404, foreign.content)

    def test_manager_sees_every_company(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get(f"/api/platform/ops/companies/{self.tenant_b.pk}/health/")
        self.assertEqual(response.status_code, 200, response.content)


class ChampionsBoardAvailabilityTest(_StaffScopeFixture):
    """`champions/` مُستثناةٌ من فحص الملكيّة (لوحةٌ جماعيّة) لكنّ توفّرها لموظّفٍ عاديّ يُثبَت فعلياً."""

    def test_a_plain_staff_member_reaches_the_shared_board(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/platform/ops/champions/")
        self.assertEqual(response.status_code, 200, response.content)


class DailyRatingScopeTest(_StaffScopeFixture):
    """`/api/my-agent/daily-ratings/` — البابُ الخلفيُّ: خارجَ `/api/platform/ops/` ولائحتُه `[IsAuthenticated]`.

    التقييمُ شهادةُ الزبون على الموظّف. فلو سقط التضييقُ رأى كلُّ موظّفٍ شهاداتِ
    كلِّ زميلٍ عند كلِّ زبون — وهو أكشفُ ما في الوحدة، ومع ذلك لا يبلغه تعدادُ
    `permission_classes` لأنّ لائحتَه لا تذكر `IsPlatformOperationsStaff` إطلاقاً.
    """

    URL = "/api/my-agent/daily-ratings/"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        service_date = datetime.date(2026, 1, 15)
        cls.rating_a = DailyRating.objects.create(
            tenant=cls.tenant_a, employee=cls.employee_a,
            service_date=service_date, stars=5, note="شهادةُ شركة أ.",
        )
        cls.rating_b = DailyRating.objects.create(
            tenant=cls.tenant_b, employee=cls.employee_b,
            service_date=service_date, stars=2, note="شهادةُ شركة ب.",
        )

    def test_list_hides_a_colleague_rating(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        ids = self._ids(response)
        self.assertIn(self.rating_a.id, ids, "الموظّفُ لا يرى شهادتَه هو — التضييقُ أوسعُ من اللازم.")
        self.assertNotIn(
            self.rating_b.id, ids,
            "تسريب: الموظّفُ يرى تقييمَ زميله عند زبونٍ لا يخدمه.",
        )

    def test_detail_404s_on_a_colleague_rating(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get(f"{self.URL}{self.rating_b.id}/")
        self.assertEqual(
            response.status_code, 404,
            "تسريب: صفُّ الزميل مقروءٌ تفصيلاً رغم غيابه عن القائمة.",
        )

    def test_manager_sees_both_ratings(self):
        """بلا هذا لَمَرَّ الفحصُ أعلاه كذباً على مسارٍ لا يردّ شيئاً لأحد."""
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get(self.URL))
        self.assertIn(self.rating_a.id, ids)
        self.assertIn(self.rating_b.id, ids)
