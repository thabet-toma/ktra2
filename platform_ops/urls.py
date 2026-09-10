"""مسارات عمليات المنصة."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    IntegrationKeyViewSet,
    PerformanceSnapshotViewSet,
    PlatformEmployeeViewSet,
    PolicyProfileViewSet,
    ServiceSubscriptionViewSet,
    WorkOrderIntakeView,
    WorkOrderViewSet,
)

router = SimpleRouter()
router.register("employees", PlatformEmployeeViewSet, basename="platform-ops-employees")
router.register("subscriptions", ServiceSubscriptionViewSet, basename="platform-ops-subscriptions")
router.register("work-orders", WorkOrderViewSet, basename="platform-ops-work-orders")
router.register("integration-keys", IntegrationKeyViewSet, basename="platform-ops-integration-keys")
router.register("policy-profiles", PolicyProfileViewSet, basename="platform-ops-policy-profiles")
router.register("performance-snapshots", PerformanceSnapshotViewSet, basename="platform-ops-performance-snapshots")

urlpatterns = [
    path("intake/", WorkOrderIntakeView.as_view(), name="platform-ops-intake"),
    path("", include(router.urls)),
]

