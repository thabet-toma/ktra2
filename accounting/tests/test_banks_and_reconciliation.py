"""T-BANKS — البنوك وفروعها وحساباتها والمطابقة البنكية.

قبل هذا العمل لم يكن في النظام كيان «بنك» أصلاً: الشيك يحمل اسم بنك نصياً،
والحركة البنكية تُرحَّل على حساب «1102 البنوك» العام بلا تفصيل ولا مطابقة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import (
    Account, Bank, BankAccount, BankBranch, BankReconciliation,
    BankReconciliationLine, Cheque, JournalHeader, JournalLine,
)
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership
from tenants.services import create_company


class BankApiTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bank-mgr", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة البنوك", cls.user)
        create_fiscal_year(cls.tenant, 2026)

    def auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def make_bank(self, name="بنك فلسطين"):
        return Bank.objects.create(tenant=self.tenant, name=name)

    def make_account(self, bank=None, name="الحساب الجاري", currency=None):
        from accounting.services import create_bank_account
        return create_bank_account(
            tenant=self.tenant, bank=bank or self.make_bank(), name=name,
            currency=currency or self.ils,
        )


class BankCrudTest(BankApiTestBase):
    def test_create_bank_with_branch_and_account_provisions_gl_under_1102(self):
        h = self.auth()
        res = self.client.post("/api/accounting/banks/", {
            "name": "بنك القدس", "swift_code": "QUBKPS22",
        }, format="json", **h)
        self.assertEqual(res.status_code, 201, res.data)
        bank_id = res.data["id"]

        res = self.client.post("/api/accounting/bank-branches/", {
            "bank": bank_id, "name": "فرع رام الله", "branch_code": "902",
        }, format="json", **h)
        self.assertEqual(res.status_code, 201, res.data)
        branch_id = res.data["id"]

        res = self.client.post("/api/accounting/bank-accounts/", {
            "bank": bank_id, "branch": branch_id, "name": "جاري شيكل",
            "account_number": "12345", "currency": self.ils.CurrencyID,
        }, format="json", **h)
        self.assertEqual(res.status_code, 201, res.data)
        ba = BankAccount.objects.get(pk=res.data["id"])
        # حساب مستقل في الشجرة تحت «1102 البنوك» — لا ترحيل على الحساب العام.
        self.assertEqual(ba.account.parent.code, "1102")
        self.assertTrue(ba.account.code.startswith("1102K"))
        self.assertIn("جاري شيكل", ba.account.name)

    def test_second_account_gets_distinct_gl_code(self):
        bank = self.make_bank()
        a1 = self.make_account(bank=bank, name="جاري شيكل")
        a2 = self.make_account(bank=bank, name="جاري دولار", currency=self.usd)
        self.assertNotEqual(a1.account.code, a2.account.code)
        self.assertEqual(a2.currency.Code, "USD")

    def test_every_bank_account_lands_under_1102_with_a_distinct_code(self):
        """الضمان الذي يسأل عنه المالك: لا حساب بنكي بلا حساب في الشجرة تحت «البنوك»."""
        h = self.auth()
        bank = self.make_bank("بنك الاختبار")
        codes = set()
        for i in range(5):
            res = self.client.post("/api/accounting/bank-accounts/", {
                "bank": bank.pk, "name": f"حساب {i}", "currency": self.ils.CurrencyID,
            }, format="json", **h)
            self.assertEqual(res.status_code, 201, res.data)
            ba = BankAccount.objects.get(pk=res.data["id"])
            self.assertIsNotNone(ba.account_id)
            self.assertEqual(ba.account.parent.code, "1102")
            self.assertEqual(ba.account.account_type, "Asset")
            self.assertTrue(ba.account.is_active)
            codes.add(ba.account.code)
        self.assertEqual(len(codes), 5)
        # كل حسابات البنك أبناء «1102» مباشرةً — لا حساب يتيم ولا في مكان آخر.
        parent = Account.objects.get(tenant=self.tenant, code="1102")
        self.assertEqual(parent.children.count(), 5)

    def test_bank_alone_creates_no_ledger_account(self):
        """البنك سجلّ تعريفي — الحساب في الشجرة يخص الحساب البنكي لا البنك."""
        before = Account.objects.filter(tenant=self.tenant).count()
        self.make_bank("بنك بلا حسابات")
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), before)

    def test_missing_1102_is_created_under_current_assets(self):
        """شركة قديمة بلا حساب «البنوك»: يُنشأ تحت «11» لا في جذر الشجرة."""
        Account.objects.filter(tenant=self.tenant, code="1102").delete()
        ba = self.make_account(name="جاري بعد الحذف")
        parent = ba.account.parent
        self.assertEqual(parent.code, "1102")
        self.assertEqual(parent.parent.code, "11")
        self.assertEqual(parent.account_type, "Asset")

    def test_bank_account_cannot_exist_without_ledger_account(self):
        """ضمان بنيوي: العمود إلزامي في قاعدة البيانات لا في الخدمة وحدها."""
        self.assertFalse(BankAccount._meta.get_field("account").null)

    def test_branch_of_other_bank_is_rejected(self):
        h = self.auth()
        bank_a = self.make_bank("بنك أ")
        bank_b = self.make_bank("بنك ب")
        branch_b = BankBranch.objects.create(tenant=self.tenant, bank=bank_b, name="فرع ب")
        res = self.client.post("/api/accounting/bank-accounts/", {
            "bank": bank_a.pk, "branch": branch_b.pk, "name": "حساب",
            "currency": self.ils.CurrencyID,
        }, format="json", **h)
        self.assertEqual(res.status_code, 400, res.data)

    def test_bank_account_with_movement_cannot_be_deleted(self):
        h = self.auth()
        ba = self.make_account()
        journal = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-06-01",
            description="إيداع", is_posted=True, exchange_rate=1,
        )
        JournalLine.objects.create(
            tenant=self.tenant, journal=journal, account=ba.account,
            debit=Decimal("100.00"), credit=Decimal("0.00"),
        )
        res = self.client.delete(f"/api/accounting/bank-accounts/{ba.pk}/", **h)
        self.assertEqual(res.status_code, 400, getattr(res, "data", None))
        self.assertTrue(BankAccount.objects.filter(pk=ba.pk).exists())

    def test_tenant_isolation(self):
        other_user = User.objects.create_user(username="other-bank", password="x")
        other = create_company("شركة أخرى", other_user)
        Bank.objects.create(tenant=other, name="بنك الغير")
        self.make_bank("بنك شركتي")
        h = self.auth()
        res = self.client.get("/api/accounting/banks/", **h)
        self.assertEqual(res.status_code, 200)
        names = [b["name"] for b in (res.data if isinstance(res.data, list) else res.data["results"])]
        self.assertEqual(names, ["بنك شركتي"])


class BankStatementAndReconciliationTest(BankApiTestBase):
    def setUp(self):
        super().setUp()
        self.ba = self.make_account(name="جاري التشغيل")
        self.cash = Account.objects.get(tenant=self.tenant, code="1101")

    def _movement(self, date, debit="0", credit="0", description="حركة"):
        journal = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date=date, description=description,
            is_posted=True, exchange_rate=1,
        )
        line = JournalLine.objects.create(
            tenant=self.tenant, journal=journal, account=self.ba.account,
            debit=Decimal(debit), credit=Decimal(credit), description=description,
        )
        JournalLine.objects.create(
            tenant=self.tenant, journal=journal, account=self.cash,
            debit=Decimal(credit), credit=Decimal(debit), description=description,
        )
        return line

    def test_statement_lists_movements_with_running_balance(self):
        h = self.auth()
        self._movement("2026-06-01", debit="1000", description="إيداع")
        self._movement("2026-06-05", credit="400", description="سحب")
        res = self.client.get(f"/api/accounting/bank-accounts/{self.ba.pk}/statement/", **h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data["rows"]), 2)
        self.assertEqual(Decimal(str(res.data["book_balance"])), Decimal("600.00"))
        self.assertEqual(Decimal(str(res.data["rows"][-1]["balance"])), Decimal("600.00"))
        self.assertFalse(res.data["rows"][0]["is_cleared"])

    def test_reconciliation_clears_lines_and_closes_at_zero_difference(self):
        h = self.auth()
        l1 = self._movement("2026-06-01", debit="1000", description="إيداع")
        l2 = self._movement("2026-06-05", credit="400", description="شيك صادر")

        res = self.client.post("/api/accounting/bank-reconciliations/", {
            "bank_account": self.ba.pk, "statement_date": "2026-06-30",
            "statement_balance": "1000.00",
        }, format="json", **h)
        self.assertEqual(res.status_code, 201, res.data)
        rec_id = res.data["id"]

        # الشيك الصادر لم يُصرف بعد في البنك ⇒ يبقى غير مؤشَّر.
        res = self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/toggle-line/",
                               {"journal_line": l1.pk, "cleared": True}, format="json", **h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(str(res.data["cleared_balance"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(res.data["difference"])), Decimal("0.00"))
        self.assertEqual(res.data["uncleared_count"], 1)

        res = self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/close/",
                               {}, format="json", **h)
        self.assertEqual(res.status_code, 200, res.data)
        rec = BankReconciliation.objects.get(pk=rec_id)
        self.assertEqual(rec.status, BankReconciliation.STATUS_CLOSED)
        self.assertIsNotNone(rec.closed_at)
        # ولا تُعدَّل بعد الإقفال.
        res = self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/toggle-line/",
                               {"journal_line": l2.pk, "cleared": True}, format="json", **h)
        self.assertEqual(res.status_code, 400, res.data)

    def test_close_is_refused_while_difference_remains(self):
        h = self.auth()
        self._movement("2026-06-01", debit="1000")
        res = self.client.post("/api/accounting/bank-reconciliations/", {
            "bank_account": self.ba.pk, "statement_date": "2026-06-30",
            "statement_balance": "1000.00",
        }, format="json", **h)
        rec_id = res.data["id"]
        res = self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/close/",
                               {}, format="json", **h)
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(BankReconciliation.objects.get(pk=rec_id).status,
                         BankReconciliation.STATUS_OPEN)

    def test_toggle_off_removes_clearing(self):
        h = self.auth()
        line = self._movement("2026-06-01", debit="1000")
        res = self.client.post("/api/accounting/bank-reconciliations/", {
            "bank_account": self.ba.pk, "statement_date": "2026-06-30",
            "statement_balance": "1000.00",
        }, format="json", **h)
        rec_id = res.data["id"]
        self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/toggle-line/",
                         {"journal_line": line.pk, "cleared": True}, format="json", **h)
        self.assertTrue(BankReconciliationLine.objects.filter(journal_line=line).exists())
        res = self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/toggle-line/",
                               {"journal_line": line.pk, "cleared": False}, format="json", **h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertFalse(BankReconciliationLine.objects.filter(journal_line=line).exists())
        self.assertEqual(Decimal(str(res.data["cleared_balance"])), Decimal("0.00"))

    def test_line_of_another_account_is_rejected(self):
        h = self.auth()
        journal = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-06-01", description="غير بنكي",
            is_posted=True, exchange_rate=1,
        )
        foreign = JournalLine.objects.create(
            tenant=self.tenant, journal=journal, account=self.cash,
            debit=Decimal("50.00"), credit=Decimal("0.00"),
        )
        res = self.client.post("/api/accounting/bank-reconciliations/", {
            "bank_account": self.ba.pk, "statement_date": "2026-06-30",
            "statement_balance": "0.00",
        }, format="json", **h)
        rec_id = res.data["id"]
        res = self.client.post(f"/api/accounting/bank-reconciliations/{rec_id}/toggle-line/",
                               {"journal_line": foreign.pk, "cleared": True}, format="json", **h)
        self.assertEqual(res.status_code, 400, res.data)

    def test_only_one_open_reconciliation_per_account(self):
        h = self.auth()
        payload = {
            "bank_account": self.ba.pk, "statement_date": "2026-06-30",
            "statement_balance": "0.00",
        }
        self.assertEqual(
            self.client.post("/api/accounting/bank-reconciliations/", payload,
                             format="json", **h).status_code, 201)
        self.assertEqual(
            self.client.post("/api/accounting/bank-reconciliations/", payload,
                             format="json", **h).status_code, 400)


class ChequeBankLinkTest(BankApiTestBase):
    def test_cheque_snapshots_bank_name_from_link(self):
        bank = self.make_bank("البنك العربي")
        branch = BankBranch.objects.create(tenant=self.tenant, bank=bank, name="فرع نابلس")
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل", partner_type="Customer")
        chq = Cheque.objects.create(
            tenant=self.tenant, cheque_number="C-1", amount=Decimal("300.00"),
            currency=self.ils, partner=customer, direction="Incoming",
            bank=bank, bank_branch_ref=branch,
        )
        chq.refresh_from_db()
        self.assertEqual(chq.bank_name, "البنك العربي")
        self.assertEqual(chq.bank_branch, "فرع نابلس")
