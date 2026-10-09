"""سعر صرف الدفع من داخل فاتورة شراء أجنبية، وعربون الطلبية (M4).

كان سند الصرف يأخذ `invoice.exchange_rate or 1` والعربون سعر الطلبية — بلا سعر يوم الدفع.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from logistics.models import PurchaseInvoice
from logistics.tests import test_purchase_invoice_pay as pay_base  # وحدةٌ لا صنف: لا إعادة جمع
from sales.models import SupplierPayment
from sales.services import record_order_deposit
from sales.tests import test_sales_orders as order_base
from sales.services import convert_quotation_to_order
from tenants.models import Currency


class PurchasePayRateTest(APITestCase):
    setUpTestData = classmethod(pay_base.PurchaseInvoicePayTest.setUpTestData.__func__)
    _auth = pay_base.PurchaseInvoicePayTest._auth
    _invoice = pay_base.PurchaseInvoicePayTest._invoice
    _pay = pay_base.PurchaseInvoicePayTest._pay

    def _usd(self, number, rate, **kw):
        usd, _ = Currency.objects.get_or_create(Code="USD", defaults={"Name": "دولار"})
        inv = self._invoice(number, **kw)
        PurchaseInvoice.objects.filter(pk=inv.pk).update(currency=usd, exchange_rate=Decimal(rate))
        inv.refresh_from_db()
        return inv

    def test_credit_invoice_payment_needs_the_day_rate(self):
        inv = self._usd("PINV-FX-1", "3.6")
        body = {"post_invoice": True, "cash": "100.00", "cash_account_id": self.cash.id}
        res = self._pay(inv, body)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("سعر صرف USD", res.json()["error"])
        self.assertFalse(SupplierPayment.objects.filter(purchase_invoice=inv).exists())

        res = self._pay(inv, {**body, "exchange_rate": "3.7"})
        self.assertEqual(res.status_code, 200, res.content)
        pay = SupplierPayment.objects.get(purchase_invoice=inv)
        self.assertEqual(pay.exchange_rate, Decimal("3.7"))


class OrderDepositRateTest(APITestCase):
    setUpTestData = classmethod(order_base.SalesOrderFlowTest.setUpTestData.__func__)
    setUp = order_base.SalesOrderFlowTest.setUp
    _quotation = order_base.SalesOrderFlowTest._quotation

    def test_foreign_order_deposit_needs_the_day_rate(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        usd, _ = Currency.objects.get_or_create(Code="USD", defaults={"Symbol": "$"})
        type(order).objects.filter(pk=order.pk).update(currency=usd, exchange_rate=Decimal("3.6"))
        order.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "سعر صرف USD"):
            record_order_deposit(order, amount=Decimal("100"), cash_account_id=self.cash.pk,
                                 user=self.user)
        payment = record_order_deposit(order, amount=Decimal("100"), cash_account_id=self.cash.pk,
                                       user=self.user, exchange_rate="3.7")
        self.assertEqual(payment.exchange_rate, Decimal("3.7"))

    def test_shekel_order_deposit_needs_no_rate(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        payment = record_order_deposit(order, amount=Decimal("100"), cash_account_id=self.cash.pk,
                                       user=self.user)
        self.assertEqual(payment.exchange_rate, Decimal("1"))
