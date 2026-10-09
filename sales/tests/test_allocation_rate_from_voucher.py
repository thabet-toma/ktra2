"""توزيع سند بعملةٍ على فاتورةٍ بعملةٍ أخرى — بسعر السند المُدخَل لا بجدول أسعار الصرف (M3).

كان `convert_amount` بلا سعر صريح يقرأ جدول الأسعار بتاريخ الدفعة: سند دولار بسعر 3.7
على فاتورة شيكل يُطفئ منها بسعر الجدول (4 هنا) لا بالسعر الذي كتبه المستخدم.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import Account, ExchangeRate
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import CustomerPayment, PaymentAllocation, SalesInvoice
from sales.services import allocate_customer_payment, post_customer_payment
from tenants.models import Currency
from tenants.services import create_company


class AllocationRateFromVoucherTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alloc_rate", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$")
        cls.tenant = create_company("شركة توزيع بالسعر", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-R", name="ذمم", account_type="Asset", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1000-R", name="صندوق", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل السعر", partner_type="Customer", linked_account=cls.ar)
        # سعر الجدول مختلف عن سعر السند عمداً — يجب ألا يُقرأ.
        for frm, to, rate in ((cls.usd, cls.ils, "4"), (cls.ils, cls.usd, "0.25")):
            ExchangeRate.objects.create(tenant=cls.tenant, from_currency=frm, to_currency=to,
                                        rate=Decimal(rate), effective_date="2026-01-01")

    def _invoice(self, number, total, currency):
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            currency=currency, invoice_date="2026-06-15",
            invoice_type=SalesInvoice.INVOICE_CREDIT, grand_total=Decimal(total),
            status=SalesInvoice.STATUS_POSTED)

    def _receipt(self, currency, rate, amount):
        return CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, currency=currency,
            exchange_rate=Decimal(rate), amount=Decimal(amount),
            cash_or_bank_account=self.cash, payment_date="2026-06-20")

    def test_allocation_at_posting_uses_the_voucher_rate(self):
        inv = self._invoice("SI-R-1", "1000", self.ils)
        pay = self._receipt(self.usd, "3.7", "100")
        PaymentAllocation.objects.create(
            tenant=self.tenant, payment=pay, invoice=inv, amount=Decimal("100"))
        post_customer_payment(pay)
        alloc = PaymentAllocation.objects.get(payment=pay)
        self.assertEqual(alloc.amount_in_invoice_currency, Decimal("370.00"))
        self.assertEqual(alloc.conversion_rate, Decimal("3.7"))
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal("370.00"))

    def test_late_allocation_uses_the_voucher_rate(self):
        inv = self._invoice("SI-R-2", "1000", self.ils)
        pay = post_customer_payment(self._receipt(self.usd, "3.7", "100"))
        allocate_customer_payment(pay, [{"invoice": inv.pk, "amount": "50"}])
        alloc = PaymentAllocation.objects.get(payment=pay)
        self.assertEqual(alloc.amount_in_invoice_currency, Decimal("185.00"))

    def test_shekel_receipt_on_dollar_invoice_needs_the_dollar_amount_stated(self):
        inv = self._invoice("SI-R-3", "500", self.usd)
        pay = post_customer_payment(self._receipt(self.ils, "1", "370"))
        with self.assertRaisesMessage(ValidationError, "USD"):
            allocate_customer_payment(pay, [{"invoice": inv.pk, "amount": "370"}])
        allocate_customer_payment(
            pay, [{"invoice": inv.pk, "amount": "370", "amount_in_invoice_currency": "100"}])
        alloc = PaymentAllocation.objects.get(payment=pay)
        self.assertEqual(alloc.amount_in_invoice_currency, Decimal("100.00"))
