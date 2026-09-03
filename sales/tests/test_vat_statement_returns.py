"""task11 R2-A2 — كشف الضريبة يجب أن يخصم المراجيع لا أن يجمعها.

قبل الإصلاح: مرجع البيع كان يُضاف إلى ضريبة المخرجات (+) بدل خصمه (−)،
ومرجع الشراء يُضاف إلى ضريبة المدخلات — فيتضخم الكشف من الجهتين.

issue #79: `build_vat_statement` صار يقرأ الدفتر لا `SalesInvoice.tax_amount` —
الفواتير هنا مرفقة بقيود حقيقية على حسابي الضريبة المشتقّين (`TaxRate.tax_account`
و`SalesSettings.vat_input_account`) بدل فواتير خام بلا أثر محاسبي.
"""
from decimal import Decimal

from django.test import TestCase

from accounting.models import Account, JournalHeader, JournalLine, TaxRate
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings
from sales.services import build_vat_statement
from tenants.models import Currency, Tenant


class VatStatementReturnsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=150, CompanyName="VAT Returns")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer")
        cls.output_vat_account = Account.objects.create(
            tenant=cls.tenant, code="2104", name="ضريبة القيمة المضافة - مخرجات",
            account_type="Liability",
        )
        cls.input_vat_account = Account.objects.create(
            tenant=cls.tenant, code="1105", name="ضريبة القيمة المضافة - مدخلات",
            account_type="Asset",
        )
        cls.contra_account = Account.objects.create(
            tenant=cls.tenant, code="1103", name="ذمم — اختبار", account_type="Asset",
        )
        TaxRate.objects.create(
            tenant=cls.tenant, name="ض.ق.م مخرجات", code="VAT-OUT",
            rate=Decimal("16.00"), tax_account=cls.output_vat_account, direction="sales",
        )
        SalesSettings.objects.create(tenant=cls.tenant, vat_input_account=cls.input_vat_account)

    def _invoice(self, number, kind, tax):
        invoice = SalesInvoice.objects.create(
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
        self._tax_journal(invoice)
        return invoice

    def _tax_journal(self, invoice):
        amount = Decimal(str(invoice.tax_amount or 0))
        if amount == 0:
            return
        kind = invoice.invoice_kind
        if kind == SalesInvoice.INVOICE_KIND_SALE:
            vat_debit, vat_credit, account = Decimal("0"), amount, self.output_vat_account
        elif kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
            vat_debit, vat_credit, account = amount, Decimal("0"), self.output_vat_account
        elif kind == SalesInvoice.INVOICE_KIND_PURCHASE:
            vat_debit, vat_credit, account = amount, Decimal("0"), self.input_vat_account
        else:  # purchase_return
            vat_debit, vat_credit, account = Decimal("0"), amount, self.input_vat_account
        header = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date=invoice.invoice_date,
            description=f"ضريبة — {invoice.invoice_number}", is_posted=True,
        )
        JournalLine.objects.create(
            tenant=self.tenant, journal=header, account=account,
            debit=vat_debit, credit=vat_credit,
        )
        JournalLine.objects.create(
            tenant=self.tenant, journal=header, account=self.contra_account,
            debit=vat_credit, credit=vat_debit,
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
