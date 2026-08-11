from rest_framework.routers import SimpleRouter

from device_registry.views import SensitiveDeviceViewSet

# SimpleRouter لا DefaultRouter: جذر الـAPI القابل للتصفح صفحةٌ غير محروسة
# بـ`require_module`، فيكشف وجود الوحدة لشركةٍ غير مرخّصة.
router = SimpleRouter()
router.register(r"records", SensitiveDeviceViewSet, basename="sensitive-device")

urlpatterns = router.urls
