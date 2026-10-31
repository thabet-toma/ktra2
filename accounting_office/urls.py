"""مسارات مكتب المحاسبة — كلها تحت `/api/accounting-office/`.

`SimpleRouter` لا `DefaultRouter`: الأخير يولّد فهرساً على الجذر غير محروسٍ
بـ`require_module` فيكشف وجود الوحدة لشركةٍ لم تشترها.
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from accounting_office.views import (
    OfficeClientViewSet,
    OfficeContactViewSet,
    OfficeSettingsViewSet,
)

router = SimpleRouter()
router.register("clients", OfficeClientViewSet, basename="accounting-office-clients")
router.register("contacts", OfficeContactViewSet, basename="accounting-office-contacts")
router.register("settings", OfficeSettingsViewSet, basename="accounting-office-settings")

urlpatterns = [
    path("", include(router.urls)),
]
