from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LogisticsDealViewSet, LogisticsShipmentViewSet,
    LogisticsClearanceViewSet, LogisticsExpenseViewSet,
    LogisticsPaymentViewSet, PurchaseInvoiceViewSet,
    LandedCostReportViewSet, LocalShipmentViewSet,
)

router = DefaultRouter()
router.register(r'deals', LogisticsDealViewSet)
router.register(r'shipments', LogisticsShipmentViewSet)
router.register(r'clearances', LogisticsClearanceViewSet)
router.register(r'expenses', LogisticsExpenseViewSet)
router.register(r'payments', LogisticsPaymentViewSet)
router.register(r'purchase-invoices', PurchaseInvoiceViewSet, basename='purchase-invoices')
router.register(r'local-shipments', LocalShipmentViewSet, basename='local-shipments')
router.register(r'reports/landed-cost', LandedCostReportViewSet, basename='landed-cost-report')

urlpatterns = [
    path('', include(router.urls)),
]
