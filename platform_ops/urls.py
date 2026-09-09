"""مسارات عمليات المنصة."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import PlatformEmployeeViewSet, ServiceSubscriptionViewSet

router = SimpleRouter()
router.register("employees", PlatformEmployeeViewSet, basename="platform-ops-employees")
router.register("subscriptions", ServiceSubscriptionViewSet, basename="platform-ops-subscriptions")

urlpatterns = [
    path("", include(router.urls)),
]
