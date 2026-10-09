"""دفع التخليص والنقل المحلي: الشيكل كما هو، وغيره بسعر يوم الدفع من الطلب (M6).

كان التخليص يقرأ جدول الأسعار بتاريخ الدفعة، والنقل يأخذ `shipment.exchange_rate or 1`،
وصندوق الدولار يدفع «شيكلاً» بسعر 1 متخطّياً FIFO. والسعر يُحفظ على دفعة التخليص فتقرؤه
التكلفة المستوردة (`landed_cost.clearance_payment_amount_ils`).
"""
from decimal import Decimal

from accounting.fx_fifo import fund_box_from_capital
from accounting.models import Account, CashBoxLedgerAccount, ExchangeRate
from logistics.accruals import post_clearance_accrual
from logistics.landed_cost import clearance_payment_amount_ils
from logistics.models import LocalShipment, LocalShipmentPayment, LogisticsClearance, LogisticsClearancePayment
from logistics.tests.test_overpayment_split import _Base
from tenants.models import Currency

D = lambda v: Decimal(str(v))


class ImportPaymentRateTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        # سعر جدولٍ مختلف عمداً — يجب ألا يُقرأ.
        ExchangeRate.objects.create(tenant=cls.tenant, from_currency=cls.usd, to_currency=cls.ils,
                                    rate=D("4"), effective_date="2026-01-01")

    def test_shekel_clearance_payment_is_unchanged_and_stores_rate_one(self):
        self._accrue_clearance()
        res = self._pay_clearance(1000)
        self.assertEqual(res.status_code, 201, res.content)
        pay = LogisticsClearancePayment.objects.get(clearance=self.clearance)
        self.assertEqual(pay.exchange_rate, D("1"))

    def test_foreign_clearance_payment_needs_and_keeps_the_day_rate(self):
        self._accrue_clearance()
        res = self._pay_clearance(100, currency_id=self.usd.pk)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("سعر صرف USD", res.json()["error"])
        self.assertFalse(LogisticsClearancePayment.objects.filter(clearance=self.clearance).exists())

        res = self._pay_clearance(100, currency_id=self.usd.pk, exchange_rate="3.7")
        self.assertEqual(res.status_code, 201, res.content)
        pay = LogisticsClearancePayment.objects.get(clearance=self.clearance)
        self.assertEqual(pay.exchange_rate, D("3.7"))
        self.assertEqual(pay.journal.exchange_rate, D("3.7"))
        # التكلفة المستوردة بسعر الدفعة لا بسعر الشحنة الممرَّر ولا بالجدول.
        self.assertEqual(clearance_payment_amount_ils(pay, D("3.5")), D("370.00"))

    def test_dollar_box_cannot_pay_in_shekels(self):
        self._accrue_clearance()
        usd_cash = Account.objects.create(
            tenant=self.tenant, code="BOX-USD", name="صندوق دولار", account_type="Asset", is_active=True)
        box = CashBoxLedgerAccount.objects.create(
            tenant=self.tenant, external_id="usd-box", name="صندوق دولار", currency_code="USD",
            account=usd_cash)
        fund_box_from_capital(box, D("1000"), D("3.6"), date="2026-06-01")
        res = self._pay_clearance(100, cash_box_external_id="usd-box")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("صندوق دولار", res.json()["error"])

    def test_local_shipment_in_dollars_needs_the_day_rate(self):
        LocalShipment.objects.filter(pk=self.local.pk).update(currency=self.usd, exchange_rate=D("3.6"))
        url = f"/api/logistics/local-shipments/{self.local.pk}/pay_from_cashbox/"
        body = {"amount": "100", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-02"}
        res = self.client.post(url, body, format="json", **self.h)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("سعر صرف USD", res.json()["error"])

        res = self.client.post(url, {**body, "exchange_rate": "3.7"}, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(LocalShipmentPayment.objects.get(local_shipment=self.local).exchange_rate, D("3.7"))
