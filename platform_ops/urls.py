"""مسارات عمليات المنصة."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    IntegrationKeyViewSet,
    PlatformEmployeeViewSet,
    ServiceSubscriptionViewSet,
    WorkOrderIntakeView,
    WorkOrderViewSet,
)

router = SimpleRouter()
router.register("employees", PlatformEmployeeViewSet, basename="platform-ops-employees")
router.register("subscriptions", ServiceSubscriptionViewSet, basename="platform-ops-subscriptions")
router.register("work-orders", WorkOrderViewSet, basename="platform-ops-work-orders")
router.register("integration-keys", IntegrationKeyViewSet, basename="platform-ops-integration-keys")

urlpatterns = [
    path("intake/", WorkOrderIntakeView.as_view(), name="platform-ops-intake"),
    path("", include(router.urls)),
]
