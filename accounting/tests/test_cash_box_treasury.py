"""T-CASHBOX: الخزينة كوحدة — الإنشاء الذرّي، سلّم الحلّ، الكشف، التحويل، الجرد.

الحارس المركزي هنا هو `test_resolver_returns_a_real_box_not_generic_cash`:
شركةٌ لها صناديق فعلية كانت كل سنداتها تقع على «1101 النقدية» العامّ، لأن
سلسلة الأكواد القديمة تطابق `code="1110"` تماماً و«1110» أبُ الصناديق لا صندوق.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import (
    Account, CashBoxLedgerAccount, CashBoxUserDefault, CashCount, JournalHeader,
)
from accounting.services import (
    cash_box_adjustment, cash_box_balance, cash_box_statement, create_cash_box,
    create_cash_transfer, post_cash_count, resolve_cash_account,
    resolve_default_cash_account, set_default_cash_box, update_cash_box,
)
from accounting.services import create_fiscal_year
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class CashBoxCreationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="box", password="x", email="b@x.co")
        cls.tenant = create_company("شركة الصناديق", cls.user)
        create_fiscal_year(cls.tenant, 2026)

    def test_create_makes_account_under_1110_with_sub_type(self):
        box = create_cash_box(tenant=self.tenant, name="الصندوق الرئيسي",
                              currency_code="ILS", user=self.user)
        self.assertTrue(box.account_id)
        self.assertEqual(box.account.sub_type, "cash_box")
        self.assertEqual(box.account.name, "الصندوق الرئيسي")
        # الكود ابنٌ للأب المعياري 1110 بصيغة <أب>B<تسلسل>
        self.assertTrue(box.account.code.startswith("1110B"), box.account.code)
        self.assertEqual(box.account.parent.code, "1110")

    def test_external_id_is_generated_when_absent(self):
        box = create_cash_box(tenant=self.tenant, name="صندوق بلا معرّف", user=self.user)
        self.assertTrue(box.external_id)

    def test_first_box_becomes_default_and_default_is_unique(self):
        a = create_cash_box(tenant=self.tenant, name="أول", user=self.user)
        self.assertTrue(a.is_default)
        b = create_cash_box(tenant=self.tenant, name="ثانٍ", is_default=True, user=self.user)
        a.refresh_from_db()
        self.assertFalse(a.is_default)
        self.assertTrue(b.is_default)
        set_default_cash_box(a)
        b.refresh_from_db()
        self.assertFalse(b.is_default)
        self.assertEqual(
            CashBoxLedgerAccount.objects.filter(tenant=self.tenant, is_default=True).count(), 1,
        )

    def test_rename_syncs_the_tree_account(self):
        box = create_cash_box(tenant=self.tenant, name="اسم قديم", user=self.user)
        update_cash_box(box, name="اسم جديد")
        box.account.refresh_from_db()
        self.assertEqual(box.account.name, "اسم جديد")

    def test_long_name_is_rejected_not_silently_truncated(self):
        with self.assertRaises(ValidationError):
            create_cash_box(tenant=self.tenant, name="ص" * 101, user=self.user)

    def test_duplicate_external_id_is_refused(self):
        create_cash_box(tenant=self.tenant, name="واحد", external_id="dup", user=self.user)
        before = Account.objects.filter(tenant=self.tenant).count()
        with self.assertRaises(ValidationError):
            create_cash_box(tenant=self.tenant, name="اثنان", external_id="dup", user=self.user)
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), before)

    def test_creation_is_atomic_no_orphan_account(self):
        """فشلٌ **بعد** إنشاء الحساب لا يترك حساباً يتيماً في الشجرة.

        هذا هو العطب الذي كان يعيش في الواجهة: نداءان لا معاملة تجمعهما، فيبقى
        صندوقٌ بلا حساب (أو حسابٌ بلا صندوق) متى سقط الثاني.
        """
        from unittest.mock import patch

        before = Account.objects.filter(tenant=self.tenant).count()
        with patch.object(
            CashBoxLedgerAccount.objects, "create", side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                create_cash_box(tenant=self.tenant, name="سيفشل", user=self.user)
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), before)


class CashResolverLadderTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="res", password="x", email="r@x.co")
        cls.other = User.objects.create_user(username="res2", password="x", email="r2@x.co")
        cls.tenant = create_company("شركة السلّم", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ils = create_cash_box(tenant=cls.tenant, name="صندوق الشيقل",
                                  currency_code="ILS", is_default=True, user=cls.user)
        cls.usd = create_cash_box(tenant=cls.tenant, name="صندوق الدولار",
                                  currency_code="USD", user=cls.user)

    def test_resolver_returns_a_real_box_not_generic_cash(self):
        """الحارس: شركةٌ لها صناديق لا يجوز أن تسقط على «1101 النقدية»."""
        acc = resolve_cash_account(self.tenant.pk)
        self.assertEqual(acc.pk, self.ils.account_id)
        self.assertNotEqual(acc.code, "1101")

    def test_explicit_choice_wins(self):
        acc = resolve_cash_account(self.tenant.pk, explicit_account_id=self.usd.account_id)
        self.assertEqual(acc.pk, self.usd.account_id)

    def test_explicit_account_from_another_tenant_is_refused(self):
        stranger = create_company("شركة أخرى", self.other)
        foreign = create_cash_box(tenant=stranger, name="صندوق غريب", user=self.other)
        with self.assertRaises(ValidationError):
            resolve_cash_account(self.tenant.pk, explicit_account_id=foreign.account_id)

    def test_currency_steers_the_choice(self):
        acc = resolve_cash_account(self.tenant.pk, currency_code="USD")
        self.assertEqual(acc.pk, self.usd.account_id)

    def test_user_default_beats_company_default(self):
        CashBoxUserDefault.objects.create(
            tenant=self.tenant, user=self.user, cash_box=self.usd)
        acc = resolve_cash_account(self.tenant.pk, user=self.user)
        self.assertEqual(acc.pk, self.usd.account_id)
        # ومستخدمٌ بلا تفضيل يبقى على افتراضي الشركة
        self.assertEqual(
            resolve_cash_account(self.tenant.pk, user=self.other).pk, self.ils.account_id,
        )

    def test_user_default_is_skipped_when_currency_conflicts(self):
        CashBoxUserDefault.objects.create(
            tenant=self.tenant, user=self.user, cash_box=self.usd)
        acc = resolve_cash_account(self.tenant.pk, user=self.user, currency_code="ILS")
        self.assertEqual(acc.pk, self.ils.account_id)

    def test_inactive_box_is_never_resolved(self):
        update_cash_box(self.ils, is_active=False)
        acc = resolve_cash_account(self.tenant.pk)
        self.assertEqual(acc.pk, self.usd.account_id)
        update_cash_box(self.ils, is_active=True)

    def test_legacy_wrapper_returns_none_instead_of_raising(self):
        empty_user = User.objects.create_user(username="empty", password="x", email="e@x.co")
        empty = create_company("شركة فارغة", empty_user)
        Account.objects.filter(tenant=empty).delete()
        self.assertIsNone(resolve_default_cash_account(empty.pk))
        with self.assertRaises(ValidationError):
            resolve_cash_account(empty.pk)


class CashBoxStatementTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="stmt", password="x", email="s@x.co")
        cls.tenant = create_company("شركة الكشف", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.box = create_cash_box(tenant=cls.tenant, name="صندوق الكشف", user=cls.user)

    def _move(self, direction, amount, date):
        return cash_box_adjustment(
            self.box, direction=direction, amount=amount, date=date, user=self.user)

    def test_running_balance_follows_debits_and_credits(self):
        self._move("in", 1000, "2026-06-01")
        self._move("in", 500, "2026-06-05")
        self._move("out", 200, "2026-06-10")
        stmt = cash_box_statement(self.box)
        self.assertEqual([r["balance"] for r in stmt["rows"]],
                         [D("1000.00"), D("1500.00"), D("1300.00")])
        self.assertEqual(stmt["closing_balance"], D("1300.00"))
        # والكشف يطابق دالة الرصيد — مصدرٌ واحد لا مصدران
        self.assertEqual(cash_box_balance(self.box), D("1300.00"))

    def test_opening_excludes_in_range_rows(self):
        self._move("in", 1000, "2026-06-01")
        self._move("in", 300, "2026-06-20")
        stmt = cash_box_statement(self.box, start_date="2026-06-15")
        self.assertEqual(stmt["opening_balance"], D("1000.00"))
        self.assertEqual(len(stmt["rows"]), 1)
        self.assertEqual(stmt["closing_balance"], D("1300.00"))

    def test_withdraw_beyond_balance_is_refused(self):
        self._move("in", 100, "2026-06-01")
        with self.assertRaises(ValidationError):
            self._move("out", 500, "2026-06-02")


class CashTransferTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="trf", password="x", email="t@x.co")
        cls.tenant = create_company("شركة التحويل", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.a = create_cash_box(tenant=cls.tenant, name="صندوق أ", currency_code="ILS", user=cls.user)
        cls.b = create_cash_box(tenant=cls.tenant, name="صندوق ب", currency_code="ILS", user=cls.user)
        cls.usd = create_cash_box(tenant=cls.tenant, name="صندوق الدولار",
                                  currency_code="USD", user=cls.user)

    def test_transfer_moves_balance_with_one_balanced_journal(self):
        cash_box_adjustment(self.a, direction="in", amount=1000,
                            date="2026-06-01", user=self.user)
        transfer = create_cash_transfer(
            tenant=self.tenant, transfer_date="2026-06-02", amount=400,
            from_cash_box=self.a, to_cash_box=self.b, user=self.user)
        self.assertIsNotNone(transfer.journal_id)
        self.assertEqual(cash_box_balance(self.a), D("600.00"))
        self.assertEqual(cash_box_balance(self.b), D("400.00"))
        jh = JournalHeader.objects.get(pk=transfer.journal_id)
        self.assertTrue(jh.is_posted)
        self.assertEqual(
            sum(l.debit for l in jh.lines.all()), sum(l.credit for l in jh.lines.all()),
        )

    def test_transfer_beyond_balance_is_refused(self):
        with self.assertRaises(ValidationError):
            create_cash_transfer(
                tenant=self.tenant, transfer_date="2026-06-02", amount=999,
                from_cash_box=self.b, to_cash_box=self.a, user=self.user)

    def test_transfer_to_self_is_refused(self):
        with self.assertRaises(ValidationError):
            create_cash_transfer(
                tenant=self.tenant, transfer_date="2026-06-02", amount=10,
                from_cash_box=self.a, to_cash_box=self.a, user=self.user)

    def test_transfer_to_fx_box_creates_a_fifo_lot(self):
        cash_box_adjustment(self.a, direction="in", amount=3000,
                            date="2026-06-01", user=self.user)
        transfer = create_cash_transfer(
            tenant=self.tenant, transfer_date="2026-06-03", amount=3000,
            from_cash_box=self.a, to_cash_box=self.usd, rate=3, user=self.user)
        self.assertIsNotNone(transfer.journal_id)
        lot = self.usd.fx_lots.get()
        self.assertEqual(lot.remaining_fc, D("1000.0000"))
        self.assertEqual(lot.rate, D("3"))
        self.assertEqual(cash_box_balance(self.a), D("0.00"))


class CashCountTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cnt", password="x", email="c@x.co")
        cls.tenant = create_company("شركة الجرد", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.box = create_cash_box(tenant=cls.tenant, name="صندوق الجرد", user=cls.user)

    def _count(self, counted):
        cash_box_adjustment(self.box, direction="in", amount=1000,
                            date="2026-06-01", user=self.user)
        return CashCount.objects.create(
            tenant=self.tenant, cash_box=self.box, count_date="2026-06-02",
            counted_total=D(counted))

    def test_shortage_posts_to_expense_and_lowers_the_box(self):
        count = post_cash_count(self._count(950), user=self.user)
        self.assertEqual(count.book_balance, D("1000.00"))
        self.assertEqual(count.difference, D("-50.00"))
        self.assertIsNotNone(count.journal_id)
        jh = JournalHeader.objects.get(pk=count.journal_id)
        self.assertTrue(jh.lines.filter(account=self.box.account, credit=D("50.00")).exists())
        self.assertTrue(jh.lines.filter(account__code="5206", debit=D("50.00")).exists())
        self.assertEqual(cash_box_balance(self.box), D("950.00"))

    def test_overage_posts_to_revenue(self):
        count = post_cash_count(self._count(1120), user=self.user)
        self.assertEqual(count.difference, D("120.00"))
        jh = JournalHeader.objects.get(pk=count.journal_id)
        self.assertTrue(jh.lines.filter(account=self.box.account, debit=D("120.00")).exists())
        self.assertTrue(jh.lines.filter(account__code="4202", credit=D("120.00")).exists())
        self.assertEqual(cash_box_balance(self.box), D("1120.00"))

    def test_matching_count_posts_no_journal(self):
        count = post_cash_count(self._count(1000), user=self.user)
        self.assertEqual(count.difference, D("0.00"))
        self.assertIsNone(count.journal_id)
        self.assertEqual(count.status, CashCount.STATUS_POSTED)

