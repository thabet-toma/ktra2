"""كشفُ الحساب يسمّي مرتجعَ البيع باسمه — بلاغُ المالك الثاني في #214-ب.

**البلاغ حرفيّاً:** «المرتجع … بتعامل على أساس إنّه فاتورة مبيعات — يعني لمّا
أضغط عليه بتبيّن كلمة فاتورة مبيعات بالعنوان».

**السبب:** قيدُ مرتجع البيع يُكتب بـ`reference_type="SALES_INVOICE"` — **كالبيعة
حرفاً**، لأنّ المرتجع فعلاً صفُّ `SalesInvoice` بنوعٍ آخر. والواجهةُ تشتقّ اسمَ
الحركة من هذا الحقل وحدَه (`referenceTypeLabel`)، فليس عندها ما تفرّق به.

**والعلاجُ في طبقة العرض لا في القيد:** تغييرُ `reference_type` على القيود يمسّ
مفتاحَ الـidempotency الذي يبني عليه فكُّ الترحيل وسلّةُ المحذوفات — ثمنٌ فادحٌ
لتصحيح كلمة. فالحمولةُ تحمل النوعَ الحقيقيَّ في حقلٍ بجانبه، **بلا استعلامٍ
إضافيّ**: الدالّةُ تسأل `SalesInvoice` عن أرقام المستندات أصلاً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import partner_account_statement
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice
from tenants.models import Currency
from tenants.services import create_company


class StatementReturnNamingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="stmt_kind", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة تسمية المرتجع", cls.user)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-K", name="ذمم", account_type="Asset", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-K", name="صندوق", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل التسمية", partner_type="Customer", linked_account=cls.ar)

    def _invoice(self, number, *, kind, original=None, date="2026-06-01"):
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            invoice_date=date, currency=self.ils, exchange_rate=Decimal("1"),
            grand_total=Decimal("100"), status=SalesInvoice.STATUS_POSTED,
            invoice_kind=kind, original_invoice=original)

    def _journal(self, reference_id, *, debit, credit, date="2026-06-01"):
        header = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date=date, is_posted=True,
            exchange_rate=Decimal("1"),
            reference_type="SALES_INVOICE", reference_id=reference_id)
        JournalLine.objects.create(
            tenant=self.tenant, journal=header, account=self.ar,
            debit=Decimal(str(debit)), credit=Decimal(str(credit)), partner=self.customer)
        return header

    def _statement(self):
        return partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.customer.id,
            is_supplier=False, ordering="oldest")["results"]

    def test_the_statement_tells_a_return_apart_from_a_sale(self):
        """قلبُ البلاغ: صفّان بنفس `reference_type` ويجب أن يُقرآ مستندَين."""
        sale = self._invoice("SI-K1", kind=SalesInvoice.INVOICE_KIND_SALE)
        ret = self._invoice("SR-K1", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
                            original=sale, date="2026-06-05")
        self._journal(sale.id, debit=100, credit=0)
        self._journal(ret.id, debit=0, credit=100, date="2026-06-05")

        rows = self._statement()
        # الحقلُ الذي كانت الواجهةُ عمياءَ بدونه — والنوعان متطابقان فيه سلفاً.
        self.assertEqual(rows[0]["reference_type"], rows[1]["reference_type"])
        by_number = {row["document_number"]: row for row in rows}
        self.assertEqual(by_number["SI-K1"]["reference_kind"], "sale")
        self.assertEqual(by_number["SR-K1"]["reference_kind"], "sale_return")

    def test_every_row_carries_the_field_even_when_it_has_no_kind(self):
        """حقلٌ يظهر أحياناً يجعل الواجهةَ تخمّن غيابَه — يُرسَل دائماً ولو `None`."""
        payment = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, payment_date="2026-06-07",
            amount=Decimal("50"), currency=self.ils, exchange_rate=Decimal("1"),
            cash_or_bank_account=self.cash, is_posted=True)
        header = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-06-07", is_posted=True,
            exchange_rate=Decimal("1"),
            reference_type="CUSTOMER_PAYMENT", reference_id=payment.id)
        JournalLine.objects.create(
            tenant=self.tenant, journal=header, account=self.ar,
            debit=Decimal("0"), credit=Decimal("50"), partner=self.customer)

        rows = self._statement()
        self.assertEqual(len(rows), 1)
        self.assertIn("reference_kind", rows[0])
        self.assertIsNone(rows[0]["reference_kind"])

    def test_naming_the_return_does_not_unhook_it_from_its_original(self):
        """المرتجعُ يرسو على أصله منذ #167 — والتسميةُ لا تمسّ الإرساء.

        الحقلان يُقرآن من الاستعلام نفسِه، فتعديلُ أحدهما يُغري بكسر الآخر.
        """
        sale = self._invoice("SI-K2", kind=SalesInvoice.INVOICE_KIND_SALE)
        ret = self._invoice("SR-K2", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
                            original=sale, date="2026-06-06")
        self._journal(sale.id, debit=100, credit=0)
        self._journal(ret.id, debit=0, credit=100, date="2026-06-06")

        by_number = {row["document_number"]: row for row in self._statement()}
        anchor = f"SALES_INVOICE:{sale.id}"
        self.assertEqual(by_number["SI-K2"]["link_key"], anchor)
        self.assertEqual(by_number["SR-K2"]["link_key"], anchor)

    def test_a_return_without_an_original_is_still_named_a_return(self):
        """الإرساءُ يمرّ بـ`original_invoice`، والتسميةُ لا تلزمها — ولو اشتُقّت
        منه لصار مرتجعٌ بلا أصلٍ يُقرأ بيعةً."""
        ret = self._invoice("SR-K3", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN)
        self._journal(ret.id, debit=0, credit=100)
        rows = self._statement()
        self.assertEqual(rows[0]["reference_kind"], "sale_return")
