"""سعر صرف التحصيل من داخل فاتورة بعملةٍ أجنبية (M4).

كان سند القبض يأخذ `invoice.exchange_rate or 1` بلا معامل: يوم التحصيل بسعر يوم الفاتورة،
وفاتورةٌ أجنبية حُفظت بسعر 1 تُحصَّل بالشيكل. الآن: الآجلة تطلب سعر يوم التحصيل، والنقدية
تُحصَّل لحظتها بسعرها الذي أُدخل للتو — وبسعر 1 تُرفض.
"""
from decimal import Decimal

from sales.models import CustomerPayment, SalesInvoice
from sales.tests import test_invoice_collect as base  # وحدةٌ لا صنف: لا يُعاد جمع اختباراتها هنا
from tenants.models import Currency
from rest_framework.test import APITestCase


class CollectPaymentRateTest(APITestCase):
    setUpTestData = classmethod(base.InvoiceCollectTest.setUpTestData.__func__)
    setUp = base.InvoiceCollectTest.setUp
    _draft = base.InvoiceCollectTest._draft
    _collect = base.InvoiceCollectTest._collect

    def _usd_draft(self, number, rate, invoice_type=SalesInvoice.INVOICE_CREDIT):
        usd, _ = Currency.objects.get_or_create(Code="USD", defaults={"Symbol": "$"})
        inv = self._draft(number, invoice_type=invoice_type)
        SalesInvoice.objects.filter(pk=inv.pk).update(currency=usd, exchange_rate=Decimal(rate))
        inv.refresh_from_db()
        return inv

    def test_credit_invoice_collection_needs_the_day_rate(self):
        inv = self._usd_draft("SI-FX-1", "3.6")
        res = self._collect(inv, {"cash": "100", "post_invoice": True})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("سعر صرف USD", res.json()["error"])
        inv.refresh_from_db()
        self.assertNotEqual(inv.status, SalesInvoice.STATUS_POSTED)  # الكلّ أو لا شيء

        res = self._collect(inv, {"cash": "100", "post_invoice": True, "exchange_rate": "3.7"})
        self.assertEqual(res.status_code, 200, res.content)
        pay = CustomerPayment.objects.get(allocations__invoice=inv)
        self.assertEqual(pay.exchange_rate, Decimal("3.7"))

    def test_cash_invoice_is_collected_at_its_own_rate(self):
        inv = self._usd_draft("SI-FX-2", "3.6", invoice_type=SalesInvoice.INVOICE_CASH)
        res = self._collect(inv, {"cash": "100", "post_invoice": True})
        self.assertEqual(res.status_code, 200, res.content)
        pay = CustomerPayment.objects.get(allocations__invoice=inv)
        self.assertEqual(pay.exchange_rate, Decimal("3.6"))

    def test_foreign_cash_invoice_saved_at_one_is_refused(self):
        """يُرفض من قيد الفاتورة نفسها (حارس `post_journal`) قبل أن يُحصَّل بالشيكل."""
        inv = self._usd_draft("SI-FX-3", "1", invoice_type=SalesInvoice.INVOICE_CASH)
        res = self._collect(inv, {"cash": "100", "post_invoice": True})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("USD", res.json()["error"])
        self.assertFalse(CustomerPayment.objects.filter(allocations__invoice=inv).exists())
