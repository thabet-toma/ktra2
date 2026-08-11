from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CreditDebitNoteViewSet,
    CustomerPaymentViewSet,
    CustomerPriceListViewSet,
    DeliveryOrderViewSet,
    SalesInvoiceViewSet,
    SalesOrderViewSet,
    SalesQuotationViewSet,
    SalesReportViewSet,
    SalesSettingsViewSet,
)

router = DefaultRouter()
router.register(r"invoices", SalesInvoiceViewSet, basename="sales-invoices")
router.register(r"quotations", SalesQuotationViewSet, basename="sales-quotations")
router.register(r"orders", SalesOrderViewSet, basename="sales-orders")
router.register(r"delivery-orders", DeliveryOrderViewSet, basename="sales-delivery-orders")
router.register(r"payments", CustomerPaymentViewSet, basename="customer-payments")
router.register(r"settings", SalesSettingsViewSet, basename="sales-settings")
router.register(r"credit-debit-notes", CreditDebitNoteViewSet, basename="credit-debit-notes")
router.register(r"customer-price-list", CustomerPriceListViewSet, basename="customer-price-list")

report_list = SalesReportViewSet.as_view({"get": "aging"})
report_dormant = SalesReportViewSet.as_view({"get": "dormant_customers_report"})
report_reserved = SalesReportViewSet.as_view({"get": "reserved_stock_report"})

urlpatterns = [
    path("", include(router.urls)),
    path("reports/aging/", report_list, name="sales-reports-aging"),
    path(
        "reports/dormant-customers/",
        report_dormant,
        name="sales-reports-dormant-customers",
    ),
    path(
        "reports/reserved-stock/",
        report_reserved,
        name="sales-reports-reserved-stock",
    ),
]
