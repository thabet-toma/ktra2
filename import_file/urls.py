from rest_framework.routers import SimpleRouter

from import_file.views import (
    DealImportFileViewSet,
    ImportFileDocumentViewSet,
    ImportFileItemViewSet,
)

# SimpleRouter لا DefaultRouter: جذر الـAPI القابل للتصفح صفحةٌ غير محروسة
# بـ`require_module`، فيكشف وجود الوحدة لشركةٍ غير مرخّصة.
router = SimpleRouter()
router.register(r"deals", DealImportFileViewSet, basename="import-file-deal")
router.register(r"items", ImportFileItemViewSet, basename="import-file-item")
router.register(r"documents", ImportFileDocumentViewSet, basename="import-file-document")

urlpatterns = router.urls
