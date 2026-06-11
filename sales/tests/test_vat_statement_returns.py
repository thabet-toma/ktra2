"""task11 R2-A2 — كشف الضريبة يجب أن يخصم المراجيع لا أن يجمعها.

قبل الإصلاح: مرجع البيع كان يُضاف إلى ضريبة المخرجات (+) بدل خصمه (−)،
ومرجع الشراء يُضاف إلى ضريبة المدخلات — فيتضخم الكشف من الجهتين.
"""
from decimal import Decimal

from django.test import TestCase

from partners.models import Partner
from sales.models import SalesInvoice
from sales.services import build_vat_statement
from tenants.models import Currency, Tenant


class VatStatementReturnsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=150, CompanyName="VAT Returns")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer")

    def _invoice(self, number, kind, tax):
        return SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=number,
            customer=self.customer,
            currency=self.ils,
            invoice_date="2026-03-15",
            invoice_kind=kind,
            status=SalesInvoice.STATUS_POSTED,
            tax_amount=Decimal(tax),
            grand_total=Decimal(tax) * 7,  # غير مهم للكشف
        )

    def test_returns_are_netted_not_added(self):
        self._invoice("S-1", SalesInvoice.INVOICE_KIND_SALE, "160.00")
        self._invoice("SR-1", SalesInvoice.INVOICE_KIND_SALE_RETURN, "32.00")
        self._invoice("P-1", SalesInvoice.INVOICE_KIND_PURCHASE, "80.00")
        self._invoice("PR-1", SalesInvoice.INVOICE_KIND_PURCHASE_RETURN, "16.00")

        stmt = build_vat_statement(
            tenant_id=self.tenant.TenantID,
            period_from="2026-03-01",
            period_to="2026-03-31",
        )

        # مبيعات: 160 − 32 = 128 · مشتريات: 80 − 16 = 64 · صافي = 64
        self.assertEqual(stmt.total_sales_vat, Decimal("128.00"))
        self.assertEqual(stmt.total_purchase_vat, Decimal("64.00"))
        self.assertEqual(stmt.net_vat, Decimal("64.00"))
