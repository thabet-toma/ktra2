"""عمولات حوالات مرحّلة قبل أن يكتبها قيد الدفعة (ee6a0c7a) — `post_unbooked_transfer_fees`.

إنتاج كترا: 126 دفعة بـ2,611.45$ عمولات خرجت من صندوق الدولار ولا قيد لها، فرصيده
الدفتري أعلى من الحقيقي. التسوية بتاريخ اليوم (لا إعادة كتابة 2024–2026)، قيدٌ لكل
دفعة يعرفه الترحيل فلا تُقيَّد عمولتها مرتين إن أُعيد ترحيلها.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.cashbox import get_cash_box_parent_account
from accounting.fx_fifo import box_fc_balance, fund_box_from_capital
from accounting.models import Account, CashBoxLedgerAccount, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from logistics.models import LogisticsDeal, LogisticsPayment
from logistics.payment_posting import (
    BANK_CHARGES_ACCOUNT_NAME,
    TRANSFER_FEE_ADJUST_REFERENCE,
    build_usd_payment_journal,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class UnbookedTransferFeesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="fee-bf", password="x", email="fee@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة العمولات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        parent = get_cash_box_parent_account(cls.tenant)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-FEE", name="ذمم مورد",
                                    account_type="Liability", is_active=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier", linked_account=ap)
        cls.usd_acc = Account.objects.create(tenant=cls.tenant, code="USDBOX", name="صندوق الدولار",
                                             parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=cls.usd_acc)
        cls.plain = Account.objects.create(tenant=cls.tenant, code="BANK-PLAIN", name="بنك",
                                           account_type="Asset", is_active=True)
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-FEE", partner=cls.supplier,
            order_date="2026-06-20", total_amount=D("10000"))

    def _legacy(self, box_account, fee="20", amount="1000", date="2026-06-20"):
        """دفعة رحّلها الكود السابق: الذمة والصندوق بلا سطر عمولة."""
        pay = LogisticsPayment.objects.create(
            deal=self.deal, title="P", amount=D(amount), transfer_cost=D(fee),
            status="Confirmed", usd_to_ils=D("3.5"), transfer_date=date)
        jh = post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-06-20",
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk, description="قديم",
            idempotent=False,
            lines_data=[
                {"account": self.supplier.linked_account_id, "debit": D(3500), "credit": D(0),
                 "partner": self.supplier.pk, "description": "قديم"},
                {"account": box_account.pk, "debit": D(0), "credit": D(3500), "description": "قديم"},
            ])
        LogisticsPayment.objects.filter(pk=pay.pk).update(
            is_posted=True, journal=jh, bank_account=box_account)
        pay.refresh_from_db()
        return pay

    def _run(self, *args):
        out = StringIO()
        call_command("post_unbooked_transfer_fees", "--tenant", str(self.tenant.pk),
                     "--date", "2026-10-07", *args, stdout=out)
        return out.getvalue()

    def _fee_journal(self, pay):
        return JournalHeader.objects.get(
            reference_type=TRANSFER_FEE_ADJUST_REFERENCE, reference_id=pay.pk)

    def _net(self, journal, account):
        agg = JournalLine.objects.filter(journal=journal, account=account).aggregate(
            d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D(0)) - (agg["c"] or D(0))

    def test_report_writes_nothing_and_estimates_fifo_cost(self):
        fund_box_from_capital(self.box, 1100, 3, date="2026-06-19", user=self.user)
        self._legacy(self.usd_acc)
        before = JournalHeader.objects.count()
        out = self._run()
        self.assertIn("20.00", out)   # الدولار
        self.assertIn("60.00", out)   # تقدير FIFO: 20$ × 3
        self.assertEqual(JournalHeader.objects.count(), before)
        self.assertEqual(box_fc_balance(self.box), D("1100"))

    def test_apply_consumes_fifo_and_books_bank_charge_once(self):
        fund_box_from_capital(self.box, 1100, 3, date="2026-06-19", user=self.user)
        pay = self._legacy(self.usd_acc)
        self._run("--apply")
        jh = self._fee_journal(pay)
        charges = Account.objects.get(tenant=self.tenant, name=BANK_CHARGES_ACCOUNT_NAME)
        self.assertEqual(str(jh.transaction_date), "2026-10-07")
        self.assertEqual(self._net(jh, charges), D("60.00"))     # تكلفة الطبقة لا سعر 3.5
        self.assertEqual(self._net(jh, self.usd_acc), D("-60.00"))
        self.assertEqual(box_fc_balance(self.box), D("1080"))
        count = JournalHeader.objects.count()
        self._run("--apply")
        self.assertEqual(JournalHeader.objects.count(), count)  # تشغيل ثانٍ لا يكرّر

    def test_plain_box_uses_payment_rate(self):
        pay = self._legacy(self.plain, fee="10")
        self._run("--apply")
        jh = self._fee_journal(pay)
        self.assertEqual(self._net(jh, self.plain), D("-35.00"))

    def test_reposting_an_adjusted_payment_does_not_book_the_fee_again(self):
        pay = self._legacy(self.plain, fee="10")
        self._run("--apply")
        lines, _currency, _rate = build_usd_payment_journal(
            pay, debit_account_id=self.supplier.linked_account_id, partner_id=self.supplier.pk,
            box_account=self.plain, tenant=self.tenant, description="إعادة")
        charges = Account.objects.get(tenant=self.tenant, name=BANK_CHARGES_ACCOUNT_NAME)
        self.assertFalse([ln for ln in lines if ln["account"] == charges.pk])

    def test_payment_already_booked_by_new_posting_is_skipped(self):
        pay = LogisticsPayment.objects.create(
            deal=self.deal, title="جديد", amount=D("100"), transfer_cost=D("10"),
            status="Confirmed", usd_to_ils=D("3.5"), transfer_date="2026-06-20")
        resp = self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/post_payment/{pay.pk}/",
            {"bank_account_id": self.plain.pk}, format="json",
            **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        self._run("--apply")
        self.assertFalse(JournalHeader.objects.filter(
            reference_type=TRANSFER_FEE_ADJUST_REFERENCE, reference_id=pay.pk).exists())

    def test_cash_count_on_the_box_blocks_apply_until_confirmed(self):
        pay = self._legacy(self.plain, fee="10")
        shortage = Account.objects.get(tenant=self.tenant, code="5206")  # عجز الصندوق
        post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-08-01",
            reference_type="CASH_COUNT", reference_id=1, description="جرد", idempotent=False,
            lines_data=[
                {"account": shortage.pk, "debit": D(35), "credit": D(0), "description": "عجز"},
                {"account": self.plain.pk, "debit": D(0), "credit": D(35), "description": "عجز"},
            ])
        self.assertIn("جرد", self._run())
        with self.assertRaisesMessage(CommandError, "--confirm-not-absorbed"):
            self._run("--apply")
        self.assertFalse(JournalHeader.objects.filter(
            reference_type=TRANSFER_FEE_ADJUST_REFERENCE).exists())
        self._run("--apply", "--confirm-not-absorbed")
        self.assertTrue(JournalHeader.objects.filter(
            reference_type=TRANSFER_FEE_ADJUST_REFERENCE, reference_id=pay.pk).exists())

    def test_insufficient_fifo_dollars_refuse_the_whole_apply(self):
        fund_box_from_capital(self.box, 10, 3, date="2026-06-19", user=self.user)
        self._legacy(self.usd_acc, fee="20")
        with self.assertRaisesMessage(CommandError, "غير كافٍ"):
            self._run("--apply")
        self.assertEqual(box_fc_balance(self.box), D("10"))

    def test_odd_payment_dates_are_flagged(self):
        self._legacy(self.plain, fee="10", date="0005-01-10")
        self.assertIn("تاريخ شاذ", self._run())

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
