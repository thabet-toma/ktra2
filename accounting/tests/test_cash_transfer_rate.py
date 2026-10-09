"""التحويل بين الصناديق بعملتين — السعر من الطلب، والاتجاه الصحيح (M7).

كان `rate or 1` يُعطّل حارس السعر، وصندوق الدولار ← صندوق الشيكل يمرّ بـ`transfer_ils_to_fx`
معكوساً (طبقةٌ على صندوق الشيكل، وقسمةٌ بدل ضرب)، والبنك الأجنبي يُقرأ شيكلاً (`code` لا
`Code`) فيُرحَّل 1:1.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.fx_fifo import fund_box_from_capital
from accounting.models import Account, Bank, BankAccount, JournalHeader
from accounting.services import cash_box_adjustment, create_cash_transfer
from accounting.tests import test_cash_box_treasury as base  # وحدةٌ لا صنف
from tenants.models import Currency

D = lambda v: Decimal(str(v))


class CashTransferRateTest(APITestCase):
    setUpTestData = classmethod(base.CashTransferTest.setUpTestData.__func__)

    def _transfer(self, **kw):
        return create_cash_transfer(tenant=self.tenant, transfer_date="2026-06-03",
                                    user=self.user, **kw)

    def test_shekel_to_dollar_box_needs_a_real_rate(self):
        cash_box_adjustment(self.a, direction="in", amount=3000, date="2026-06-01", user=self.user)
        for rate in (None, "", "0", "1"):
            with self.subTest(rate=rate):
                with self.assertRaisesMessage(ValidationError, "سعر صرف USD"):
                    self._transfer(amount=370, from_cash_box=self.a, to_cash_box=self.usd, rate=rate)
        self.assertFalse(self.usd.fx_lots.exists())

    def test_dollar_box_to_shekel_box_consumes_fifo_with_realized_difference(self):
        fund_box_from_capital(self.usd, D("1000"), D("3.6"), date="2026-06-01")
        transfer = self._transfer(amount=100, from_cash_box=self.usd, to_cash_box=self.a, rate="3.7")
        lines = {l.account_id: l for l in JournalHeader.objects.get(pk=transfer.journal_id).lines.all()}
        self.assertEqual(lines[self.a.account_id].debit, D("370.00"))
        self.assertEqual(lines[self.usd.account_id].credit, D("360.00"))  # تكلفة FIFO
        self.assertEqual(sum(l.credit for l in lines.values()), D("370.00"))  # + ربح 10
        lot = self.usd.fx_lots.get()
        self.assertEqual(lot.remaining_fc, D("900.0000"))
        self.assertFalse(self.a.fx_lots.exists())

    def test_shekel_box_to_dollar_bank_carries_the_dollar_amount(self):
        usd = Currency.objects.get(Code="USD")
        ledger = Account.objects.create(tenant=self.tenant, code="1203-USD", name="بنك دولار",
                                        account_type="Asset", is_active=True)
        bank = BankAccount.objects.create(
            tenant=self.tenant, bank=Bank.objects.create(tenant=self.tenant, name="بنك"),
            name="جاري دولار", currency=usd, account=ledger)
        cash_box_adjustment(self.a, direction="in", amount=1000, date="2026-06-01", user=self.user)
        with self.assertRaisesMessage(ValidationError, "سعر صرف USD"):
            self._transfer(amount=370, from_cash_box=self.a, to_bank_account=bank)
        transfer = self._transfer(amount=370, from_cash_box=self.a, to_bank_account=bank, rate="3.7")
        line = JournalHeader.objects.get(pk=transfer.journal_id).lines.get(account=ledger)
        self.assertEqual((line.debit, line.amount_currency, line.currency_code),
                         (D("370.00"), D("100.00"), "USD"))
