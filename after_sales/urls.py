from rest_framework.routers import SimpleRouter

from after_sales.views import WarrantyCardViewSet

# SimpleRouter لا DefaultRouter: جذر الـAPI القابل للتصفح صفحةٌ غير محروسة
# بـ`require_module`، فيكشف وجود الوحدة لشركةٍ غير مرخّصة.
router = SimpleRouter()
router.register(r"warranties", WarrantyCardViewSet, basename="warranty-card")

urlpatterns = router.urls
