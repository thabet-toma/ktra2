from django.urls import path
from rest_framework.routers import SimpleRouter

from after_sales.views import (
    AfterSalesSettingsView,
    ManufacturerWarrantorViewSet,
    PurchaseLineWarrantyView,
    ServiceOrderViewSet,
    WarrantyCardViewSet,
    WarrantyPolicyViewSet,
)

# SimpleRouter لا DefaultRouter: جذر الـAPI القابل للتصفح صفحةٌ غير محروسة
# بـ`require_module`، فيكشف وجود الوحدة لشركةٍ غير مرخّصة.
router = SimpleRouter()
router.register(r"warranties", WarrantyCardViewSet, basename="warranty-card")
router.register(r"service-orders", ServiceOrderViewSet, basename="service-order")
router.register(
    r"manufacturer-warrantors", ManufacturerWarrantorViewSet, basename="manufacturer-warrantor",
)
router.register(r"warranty-policies", WarrantyPolicyViewSet, basename="warranty-policy")

# `settings/` صفٌّ مفرد بلا `pk` — خارج الراوتر عمداً (#230)، على نمط
# `SalesSettingsViewSet.current` بمسارٍ صريح بدل فعل قائمة/تفصيل يُخمَّن.
urlpatterns = router.urls + [
    path("settings/", AfterSalesSettingsView.as_view(), name="after-sales-settings"),
    path(
        "purchase-line-warranties/", PurchaseLineWarrantyView.as_view(),
        name="purchase-line-warranties",
    ),
]
