from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SupplierQuotationViewSet, PurchaseOrderViewSet,
    LogisticsDealViewSet, LogisticsShipmentViewSet,
    LogisticsClearanceViewSet,
    LogisticsPaymentViewSet, PurchaseInvoiceViewSet,
    SupplierPaymentViewSet,
    LandedCostReportViewSet, LocalShipmentViewSet,
    PurchaseSettingsViewSet, GoodsReceiptViewSet,
    ImportJourneyViewSet,
)

router = DefaultRouter()
router.register(r'supplier-quotations', SupplierQuotationViewSet, basename='supplier-quotations')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='purchase-orders')
router.register(r'deals', LogisticsDealViewSet)
router.register(r'shipments', LogisticsShipmentViewSet)
router.register(r'clearances', LogisticsClearanceViewSet)
router.register(r'payments', LogisticsPaymentViewSet)
router.register(r'purchase-invoices', PurchaseInvoiceViewSet, basename='purchase-invoices')
router.register(r'supplier-payments', SupplierPaymentViewSet, basename='supplier-payments')
router.register(r'local-shipments', LocalShipmentViewSet, basename='local-shipments')
router.register(r'import-journey', ImportJourneyViewSet, basename='import-journey')
router.register(r'reports/landed-cost', LandedCostReportViewSet, basename='landed-cost-report')
router.register(r'purchase-settings', PurchaseSettingsViewSet, basename='purchase-settings')
router.register(r'goods-receipts', GoodsReceiptViewSet, basename='goods-receipts')

urlpatterns = [
    path('', include(router.urls)),
]
