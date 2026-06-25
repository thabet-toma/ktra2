"""صندوق الدولار FIFO (المرحلة 3): تمويل بطبقات + استهلاك FIFO + الرصيد.

مثال المالك: حوّل 1000$ بسعر 3، ثم 500$ بسعر 4؛ كل دفع يسحب من الأقدم أولاً
والتكلفة بالشيقل بسعر الطبقة (3 حتى تنفد الـ1000).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.cashbox import get_cash_box_parent_account, get_cash_box_capital_account
from accounting.fx_fifo import (
    fund_box_from_capital, transfer_ils_to_fx, consume_fifo,
    box_fc_balance, box_ils_value,
)
from accounting.models import Account, CashBoxFxLot, CashBoxLedgerAccount, JournalHeader
from accounting.services import create_fiscal_year
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class FxFifoTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="fx", password="x", email="fx@x.co")
        cls.tenant = create_company("شركة الدولار", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        parent = get_cash_box_parent_account(cls.tenant)
        usd_acc = Account.objects.create(
            tenant=cls.tenant, code="USDBOX", name="صندوق الدولار",
            parent=parent, account_type="Asset", is_active=True)
        ils_acc = Account.objects.create(
            tenant=cls.tenant, code="ILSBOX", name="صندوق الشيقل",
            parent=parent, account_type="Asset", is_active=True)
        cls.usd = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=usd_acc)
        cls.ils = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="ils1", name="صندوق الشيقل",
            currency_code="ILS", account=ils_acc)

    def test_fund_from_capital_creates_lot_and_journal(self):
        lot = fund_box_from_capital(self.usd, 1000, 3, date="2026-06-20", user=self.user)
        self.assertEqual(lot.remaining_fc, D("1000"))
        self.assertEqual(lot.rate, D("3"))
        jh = JournalHeader.objects.get(reference_type="FX_FUND_CAPITAL", reference_id=lot.id)
        self.assertTrue(jh.is_posted)
        capital = get_cash_box_capital_account(self.tenant)
        # مدين الصندوق 3000 / دائن رأس المال 3000
        self.assertTrue(jh.lines.filter(account=self.usd.account, debit=D("3000.00")).exists())
        self.assertTrue(jh.lines.filter(account=capital, credit=D("3000.00")).exists())

    def test_transfer_from_ils_credits_ils_box(self):
        lot = transfer_ils_to_fx(self.usd, self.ils, 500, 4, date="2026-06-20", user=self.user)
        jh = JournalHeader.objects.get(reference_type="FX_FUND_TRANSFER", reference_id=lot.id)
        self.assertTrue(jh.lines.filter(account=self.usd.account, debit=D("2000.00")).exists())
        self.assertTrue(jh.lines.filter(account=self.ils.account, credit=D("2000.00")).exists())

    def test_fifo_consume_order_and_cost(self):
        fund_box_from_capital(self.usd, 1000, 3, date="2026-06-20", user=self.user)
        fund_box_from_capital(self.usd, 500, 4, date="2026-06-21", user=self.user)
        # ادفع 1200$ → 1000×3 + 200×4 = 3800 شيقل
        ils_cost, breakdown = consume_fifo(self.usd, 1200)
        self.assertEqual(ils_cost, D("3800.00"))
        self.assertEqual(len(breakdown), 2)
        lots = list(self.usd.fx_lots.order_by("lot_date", "id"))
        self.assertEqual(lots[0].remaining_fc, D("0"))       # الطبقة الأولى نفدت
        self.assertEqual(lots[1].remaining_fc, D("300"))     # تبقّى 300 من الثانية
        self.assertEqual(box_fc_balance(self.usd), D("300.0000"))
        self.assertEqual(box_ils_value(self.usd), D("1200.00"))  # 300 × 4

    def test_consume_insufficient_raises(self):
        fund_box_from_capital(self.usd, 100, 3, date="2026-06-20", user=self.user)
        with self.assertRaises(ValidationError):
            consume_fifo(self.usd, 200)

    def test_fund_rejects_nonpositive(self):
        with self.assertRaises(ValidationError):
            fund_box_from_capital(self.usd, 0, 3, date="2026-06-20", user=self.user)
        with self.assertRaises(ValidationError):
            fund_box_from_capital(self.usd, 100, 0, date="2026-06-20", user=self.user)

    # ── endpoint ──
    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_fund_capital_endpoint(self):
        resp = self.client.post(
            f"/api/accounting/cash-box-accounts/{self.usd.id}/fund-capital/",
            {"amount": "1000", "rate": "3", "date": "2026-06-20"},
            format="json", **self._auth())
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(CashBoxFxLot.objects.filter(cash_box=self.usd).count(), 1)
        lots = self.client.get(
            f"/api/accounting/cash-box-accounts/{self.usd.id}/fx-lots/", **self._auth()).json()
        self.assertEqual(lots["fc_balance"], "1000.0000")
        self.assertEqual(lots["ils_value"], "3000.00")
