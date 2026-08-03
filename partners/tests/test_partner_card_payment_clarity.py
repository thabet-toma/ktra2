"""وضوح الدفع في بطاقة الشريك: حالة كل فاتورة + ربط الحركة بمستندها في كشف الحساب.

الهدف القابل للتحقق:
- partners/<id>/invoices/ يعيد payment_status مطابقاً لشاشة الفواتير
  (مدفوعة/جزئياً/غير مدفوعة) لفواتير البيع والشراء معاً.
- كشف الحساب يعطي لكل حركة link_key: الفاتورة مرساة، وسند القبض الموزَّع عليها
  يحمل المفتاح نفسه ⇒ تُعرَضان متجاورتين. سند على فاتورتين يبقى بلا مرساة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import partner_account_statement
from partners.models import Partner
from sales.models import CustomerPayment, PaymentAllocation, SalesInvoice
from tenants.models import Currency
from tenants.services import create_company


class PartnerCardPaymentClarityTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pcard", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة وضوح الدفع", cls.user)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-P", name="ذمم", account_type="Asset", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-P", name="صندوق", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل البطاقة", partner_type="Customer",
            linked_account=cls.ar)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, total, paid):
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            invoice_date="2026-06-01", currency=self.ils, exchange_rate=Decimal("1"),
            grand_total=Decimal(str(total)), amount_paid=Decimal(str(paid)),
            status=SalesInvoice.STATUS_POSTED)

    def _payment(self, amount):
        return CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, payment_date="2026-06-05",
            amount=Decimal(str(amount)), currency=self.ils, exchange_rate=Decimal("1"),
            cash_or_bank_account=self.cash, is_posted=True)

    def _journal(self, reference_type, reference_id, *, debit, credit, date="2026-06-01"):
        jh = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date=date, is_posted=True,
            exchange_rate=Decimal("1"),
            reference_type=reference_type, reference_id=reference_id)
        JournalLine.objects.create(
            tenant=self.tenant, journal=jh, account=self.ar,
            debit=Decimal(str(debit)), credit=Decimal(str(credit)), partner=self.customer)
        return jh

    def test_partner_invoices_expose_payment_status(self):
        self._invoice("SI-A", 100, 0)
        self._invoice("SI-B", 100, 40)
        self._invoice("SI-C", 100, 100)

        res = self.client.get(
            f"/api/partners/{self.customer.id}/invoices/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        by_number = {row["document_number"]: row for row in res.json()}
        self.assertEqual(by_number["SI-A"]["payment_status"], "unpaid")
        self.assertEqual(by_number["SI-B"]["payment_status"], "partially_paid")
        self.assertEqual(by_number["SI-B"]["payment_status_display"], "مدفوعة جزئياً")
        self.assertEqual(by_number["SI-B"]["remaining_balance"], "60.00")
        self.assertEqual(by_number["SI-C"]["payment_status"], "paid")

    def test_statement_links_payment_to_its_invoice(self):
        invoice = self._invoice("SI-LINK", 100, 100)
        payment = self._payment(100)
        PaymentAllocation.objects.create(
            tenant=self.tenant, payment=payment, invoice=invoice,
            amount=Decimal("100"), amount_in_invoice_currency=Decimal("100"))
        self._journal("SALES_INVOICE", invoice.id, debit=100, credit=0)
        self._journal("CUSTOMER_PAYMENT", payment.id, debit=0, credit=100,
                      date="2026-06-05")

        st = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.customer.id,
            is_supplier=False, ordering="oldest")
        rows = st["results"]
        self.assertEqual(len(rows), 2)
        expected_key = f"SALES_INVOICE:{invoice.id}"
        self.assertEqual(rows[0]["link_key"], expected_key)
        self.assertEqual(rows[0]["document_number"], "SI-LINK")
        # سند القبض ينضمّ لمجموعة الفاتورة ويحمل رقمها كعنوان للربط.
        self.assertEqual(rows[1]["link_key"], expected_key)
        self.assertEqual(rows[1]["link_label"], "SI-LINK")
        self.assertEqual(rows[1]["link_count"], 1)

    def test_payment_split_over_two_invoices_has_no_single_anchor(self):
        first = self._invoice("SI-1", 100, 60)
        second = self._invoice("SI-2", 100, 40)
        payment = self._payment(100)
        for invoice, amount in ((first, 60), (second, 40)):
            PaymentAllocation.objects.create(
                tenant=self.tenant, payment=payment, invoice=invoice,
                amount=Decimal(str(amount)),
                amount_in_invoice_currency=Decimal(str(amount)))
        self._journal("CUSTOMER_PAYMENT", payment.id, debit=0, credit=100)

        st = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.customer.id,
            is_supplier=False)
        row = st["results"][0]
        self.assertIsNone(row["link_key"])
        self.assertEqual(row["link_count"], 2)
        self.assertEqual(row["link_label"], "2 فواتير")

    def test_unlinked_movement_keeps_empty_link_fields(self):
        self._journal("PARTNER_OPENING", None, debit=50, credit=0)
        st = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.customer.id,
            is_supplier=False)
        row = st["results"][0]
        self.assertIsNone(row["link_key"])
        self.assertIsNone(row["document_number"])
        self.assertEqual(row["link_count"], 0)
