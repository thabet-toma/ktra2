from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CreditDebitNoteViewSet,
    CustomerPaymentViewSet,
    DeliveryOrderViewSet,
    SalesInvoiceViewSet,
    SalesQuotationViewSet,
    SalesReportViewSet,
    SalesSettingsViewSet,
)

router = DefaultRouter()
router.register(r"invoices", SalesInvoiceViewSet, basename="sales-invoices")
router.register(r"quotations", SalesQuotationViewSet, basename="sales-quotations")
router.register(r"delivery-orders", DeliveryOrderViewSet, basename="sales-delivery-orders")
router.register(r"payments", CustomerPaymentViewSet, basename="customer-payments")
router.register(r"settings", SalesSettingsViewSet, basename="sales-settings")
router.register(r"credit-debit-notes", CreditDebitNoteViewSet, basename="credit-debit-notes")

report_list = SalesReportViewSet.as_view({"get": "aging"})

urlpatterns = [
    path("", include(router.urls)),
    path("reports/aging/", report_list, name="sales-reports-aging"),
]
