"""فكّ ترحيل دفعةٍ دُفعت من صندوق دولار FIFO يرجّع طبقاتها (`CashBoxFxConsumption`).

كان `consume_fifo` يُنقص `remaining_fc` ولا يحفظ من أيّ طبقةٍ أخذ، وفكّ الترحيل يعكس
القيد وحده — فإعادة الترحيل تستهلك الطبقات ثانيةً ورصيد الدولار الدفتري ينقص بلا سبب.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.cashbox import get_cash_box_parent_account
from accounting.fx_fifo import box_fc_balance, box_ils_value, fund_box_from_capital
from accounting.models import (
    Account, CashBoxFxConsumption, CashBoxLedgerAccount, ExchangeRate, JournalHeader, JournalLine,
)
from accounting.services import create_fiscal_year
from logistics.models import (
    LogisticsClearance, LogisticsClearancePayment, LogisticsDeal, LogisticsPayment, LogisticsShipment,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class _FifoBox(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="fifo-r", password="x", email="fr@x.co",
                                            is_staff=True)
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة الطبقات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        ExchangeRate.objects.create(
            tenant=cls.tenant, from_currency=cls.usd, to_currency=cls.ils,
            rate=D("3.5"), effective_date="2026-01-01")
        parent = get_cash_box_parent_account(cls.tenant)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-FR", name="ذمم مورد",
                                    account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier", linked_account=ap)
        usd_acc = Account.objects.create(tenant=cls.tenant, code="USDBOX", name="صندوق الدولار",
                                         parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=usd_acc)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        # طبقتان بسعرين: الدفعة تمتدّ عليهما.
        self.lot1 = fund_box_from_capital(self.box, 600, 3, date="2026-06-01", user=self.user)
        self.lot2 = fund_box_from_capital(self.box, 1000, D("3.2"), date="2026-06-02", user=self.user)

    def _account_balance(self):
        agg = JournalLine.objects.filter(
            account=self.box.account, journal__is_posted=True,
        ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D(0)) - (agg["c"] or D(0))

    def _state(self):
        self.lot1.refresh_from_db()
        self.lot2.refresh_from_db()
        return {
            "fc": box_fc_balance(self.box), "ils": box_ils_value(self.box),
            "account": self._account_balance(),
            "lots": (self.lot1.remaining_fc, self.lot2.remaining_fc),
        }


class DealPaymentUnpostRestoresLotsTest(_FifoBox):
    def setUp(self):
        super().setUp()
        self.deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-FR", partner=self.partner,
            order_date="2026-06-20", total_amount=D("10000"))
        self.pay = LogisticsPayment.objects.create(
            deal=self.deal, title="P1", amount=D("1000"), transfer_cost=D("20"),
            status="Confirmed", usd_to_ils=D("3.5"), transfer_date="2026-06-20")

    def _post(self):
        resp = self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/post_payment/{self.pay.pk}/",
            {"cash_box_external_id": "usd1"}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)

    def _unpost(self):
        return self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/unpost_payment/{self.pay.pk}/",
            {}, format="json", **self.h)

    def test_post_unpost_post_keeps_box_state(self):
        before = self._state()
        self._post()
        after_post = self._state()
        # 1000$ + 20$ عمولة: 600 من الأولى و420 من الثانية.
        self.assertEqual(after_post["lots"], (D("0"), D("580")))
        self.assertEqual(after_post["ils"], after_post["account"])
        resp = self._unpost()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), before)  # كل طبقة رجعت لها حصتها، والعمولة معها
        LogisticsPayment.objects.filter(pk=self.pay.pk).update(status="Confirmed")  # الفكّ يعيدها Pending
        self._post()
        self.assertEqual(self._state(), after_post)

    def test_consumption_rows_are_marked_restored_not_deleted(self):
        self._post()
        rows = CashBoxFxConsumption.objects.filter(
            reference_type="LOGISTICS_PAYMENT", reference_id=self.pay.pk)
        self.assertEqual(sum((r.fc for r in rows), D(0)), D("1020"))
        self._unpost()
        self.assertEqual(rows.count(), 3)  # الدفعة على طبقتين + العمولة
        self.assertFalse(rows.filter(restored_at__isnull=True).exists())

    def test_legacy_payment_without_consumption_record_is_refused(self):
        self._post()
        CashBoxFxConsumption.objects.filter(reference_id=self.pay.pk).delete()  # ترحيلٌ قبل السجل
        journals = JournalHeader.objects.count()
        resp = self._unpost()
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("طبقات", resp.json()["error"])
        self.pay.refresh_from_db()
        self.assertTrue(self.pay.is_posted)
        self.assertEqual(JournalHeader.objects.count(), journals)

    def test_payment_posted_before_the_box_had_lots_unposts_freely(self):
        # إنتاج كترا: الدفعات القديمة رُحّلت والصندوق بلا طبقات — لا استهلاك يُرجَع.
        CashBoxFxConsumption.objects.all().delete()
        self.lot1.delete()
        self.lot2.delete()
        self._post()
        fund_box_from_capital(self.box, 500, 3, date="2026-06-25", user=self.user)  # طبقة لاحقة
        resp = self._unpost()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(box_fc_balance(self.box), D("500"))

    def test_whole_deal_unpost_restores_lots(self):
        before = self._state()
        self._post()
        resp = self.client.post(f"/api/logistics/deals/{self.deal.pk}/unpost/", {},
                                format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), before)


class ClearancePaymentUnpostRestoresLotsTest(_FifoBox):
    def setUp(self):
        super().setUp()
        shipment = LogisticsShipment.objects.create(tenant=self.tenant, shipment_number="SH-FR")
        self.clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=shipment, customs_broker=self.partner)

    def _pay(self):
        resp = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/pay_from_cashbox/",
            {"payment_kind": "clearance", "amount": "800", "currency_id": self.usd.pk,
             "cash_box_external_id": "usd1", "payment_date": "2026-06-20"},
            format="json", **self.h)
        self.assertEqual(resp.status_code, 201, resp.content)
        return LogisticsClearancePayment.objects.get(clearance=self.clearance, is_posted=True)

    def test_unpost_payment_restores_lots(self):
        before = self._state()
        pay = self._pay()
        self.assertEqual(self._state()["lots"], (D("0"), D("800")))
        resp = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/unpost-payment/",
            {"payment_id": pay.pk}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), before)

    def test_whole_clearance_unpost_restores_lots(self):
        before = self._state()
        self._pay()
        resp = self.client.post(f"/api/logistics/clearances/{self.clearance.pk}/unpost/", {},
                                format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._state(), before)
