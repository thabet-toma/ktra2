"""مسارات مكتب المحاسبة — كلها تحت `/api/accounting-office/`.

`SimpleRouter` لا `DefaultRouter`: الأخير يولّد فهرساً على الجذر غير محروسٍ
بـ`require_module` فيكشف وجود الوحدة لشركةٍ لم تشترها.
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from accounting_office.views import (
    OfficeCalendarViewSet,
    OfficeClientViewSet,
    OfficeContactViewSet,
    OfficeDeadlineRuleViewSet,
    OfficeObligationViewSet,
    OfficePackageViewSet,
    OfficeServiceViewSet,
    OfficeSettingsViewSet,
    OfficeTaskViewSet,
    OfficeTodayViewSet,
)

router = SimpleRouter()
router.register("clients", OfficeClientViewSet, basename="accounting-office-clients")
router.register("contacts", OfficeContactViewSet, basename="accounting-office-contacts")
router.register("services", OfficeServiceViewSet, basename="accounting-office-services")
router.register("packages", OfficePackageViewSet, basename="accounting-office-packages")
router.register("settings", OfficeSettingsViewSet, basename="accounting-office-settings")
# #274: قراءتان — التقويم المحسوب، ولائحة المواعيد التي يقرؤها.
router.register("calendar", OfficeCalendarViewSet, basename="accounting-office-calendar")
router.register(
    "deadline-rules", OfficeDeadlineRuleViewSet, basename="accounting-office-deadline-rules",
)
# #275: شاشةُ «اليوم» (تُشغّل التحديث اليوميّ أوّلاً) وأفعالُ الالتزامات والشغلات.
router.register("today", OfficeTodayViewSet, basename="accounting-office-today")
router.register(
    "obligations", OfficeObligationViewSet, basename="accounting-office-obligations",
)
router.register("tasks", OfficeTaskViewSet, basename="accounting-office-tasks")

urlpatterns = [
    path("", include(router.urls)),
]
