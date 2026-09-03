"""issue #56 — سند مصروف: مستند مصاريف عام لكل الشركات.

قبل هذا الملف لا وجود لمستند مصروفٍ للشركة: فاتورة الشراء تلزمها 1104 مخزون
وترفض بدونه، وسند الصرف (`SupplierPayment`) يلزمه مورّدٌ بـ`PROTECT`. هذه
الاختبارات تحرس **الأثر عند الـHTTP** — أسطر القيد وأرصدة الحسابات وحالة
المستند — لا الاستدعاء الداخلي (المستند يفشل في أربعة أماكن لا واحد: الصلاحية،
عزل الشركة، الترقيم من الدفتر، والترحيل).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, ExpenseVoucher, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency, TenantBook, UserCompanyMembership
from tenants.services import create_company

ACC = "/api/accounting"
D = lambda v: Decimal(str(v))


class ExpenseVoucherApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="expmgr", password="x", email="e@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة سندات المصروف", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.electricity = Account.objects.get(tenant=cls.tenant, code="5203")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مستفيد سند المصروف", partner_type="Supplier")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _payload(self, **over):
        body = {
            "date": "2026-06-10",
            "expense_account": self.electricity.pk,
            "amount": "500.00",
            "currency": self.ils.pk,
            "payment_method": "cash",
            "cash_or_bank_account": self.cash.pk,
        }
        body.update(over)
        return body

    # ── معيار القبول: كهرباء نقداً بلا مورّد وبلا فاتورة شراء ─────────────
    def test_cash_electricity_expense_without_supplier_or_invoice(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/", self._payload(), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertTrue(body["is_posted"])
        self.assertIsNone(body["beneficiary_partner"])

        voucher = ExpenseVoucher.objects.get(pk=body["id"])
        self.assertTrue(voucher.is_posted)
        self.assertIsNone(voucher.beneficiary_partner_id)
        lines = list(voucher.journal.lines.select_related("account"))
        debit = next(ln for ln in lines if ln.debit > 0)
        credit = next(ln for ln in lines if ln.credit > 0)
        self.assertEqual(debit.account_id, self.electricity.pk)
        self.assertEqual(debit.debit, D("500.00"))
        self.assertEqual(credit.account_id, self.cash.pk)
        self.assertEqual(credit.credit, D("500.00"))

    def test_expense_account_can_be_created_by_name_under_52(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/",
            self._payload(expense_account=None, expense_account_name="اشتراك إنترنت"),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        acc = Account.objects.get(tenant=self.tenant, name="اشتراك إنترنت")
        self.assertTrue(acc.code.startswith("52"))
        self.assertEqual(acc.account_type, "Expense")

    # ── معيار القبول: شيك على 2111 ─────────────────────────────────────
    def test_cheque_expense_posts_to_2111(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/",
            self._payload(payment_method="cheque", cash_or_bank_account=None),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = ExpenseVoucher.objects.get(pk=res.json()["id"])
        credit = voucher.journal.lines.get(credit__gt=0)
        self.assertEqual(credit.account.code, "2111")

    # ── معيار القبول: على الحساب على 2101 (بلا مستفيد) ────────────────
    def test_on_account_without_beneficiary_posts_to_2101(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/",
            self._payload(payment_method="on_account", cash_or_bank_account=None),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = ExpenseVoucher.objects.get(pk=res.json()["id"])
        credit = voucher.journal.lines.get(credit__gt=0)
        self.assertEqual(credit.account.code, "2101")
        self.assertIsNone(credit.partner_id)

    def test_on_account_with_partner_beneficiary_credits_partner_ap_account(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/",
            self._payload(
                payment_method="on_account", cash_or_bank_account=None,
                beneficiary_partner=self.supplier.pk,
            ),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = ExpenseVoucher.objects.get(pk=res.json()["id"])
        credit = voucher.journal.lines.get(credit__gt=0)
        self.supplier.refresh_from_db()
        self.assertIsNotNone(self.supplier.linked_account_id)
        self.assertEqual(credit.account_id, self.supplier.linked_account_id)
        self.assertEqual(credit.partner_id, self.supplier.pk)

    # ── معيار القبول: ضريبة على 1105 ───────────────────────────────────
    def test_vat_portion_posts_to_1105(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/",
            self._payload(amount="580.00", tax_amount="80.00"),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = ExpenseVoucher.objects.get(pk=res.json()["id"])
        lines = list(voucher.journal.lines.select_related("account"))
        vat_line = next(ln for ln in lines if ln.account.code == "1105")
        expense_line = next(ln for ln in lines if ln.account_id == self.electricity.pk)
        self.assertEqual(vat_line.debit, D("80.00"))
        self.assertEqual(expense_line.debit, D("500.00"))

    # ── issue #80: مرتجعٌ بمبلغٍ موجب يقلب الاتجاه ───────────────────────
    def test_return_kind_flips_journal_direction_with_positive_amount(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/", self._payload(kind="return"), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["kind"], "return")
        self.assertEqual(D(body["amount"]), D("500.00"))  # موجب دوماً

        voucher = ExpenseVoucher.objects.get(pk=body["id"])
        lines = list(voucher.journal.lines.select_related("account"))
        # عاديّ: مدين المصروف / دائن الصندوق — مرتجع: العكس تماماً، بلا سالب.
        cash_line = next(ln for ln in lines if ln.account_id == self.cash.pk)
        expense_line = next(ln for ln in lines if ln.account_id == self.electricity.pk)
        self.assertEqual(cash_line.debit, D("500.00"))
        self.assertEqual(cash_line.credit, D("0.00"))
        self.assertEqual(expense_line.credit, D("500.00"))
        self.assertEqual(expense_line.debit, D("0.00"))
        for ln in lines:
            self.assertGreaterEqual(ln.debit, D("0.00"))
            self.assertGreaterEqual(ln.credit, D("0.00"))

    def test_invalid_kind_rejected(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/", self._payload(kind="bogus"), format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)

    # ── معيار القبول: إلغاء الترحيل يعيد الأرصدة حرفياً ─────────────────
    def test_unpost_reverses_balances_exactly(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/", self._payload(), format="json", **self._auth())
        voucher_id = res.json()["id"]

        unpost = self.client.post(
            f"{ACC}/expense-vouchers/{voucher_id}/unpost/", {}, format="json", **self._auth())
        self.assertEqual(unpost.status_code, 200, unpost.content)
        voucher = ExpenseVoucher.objects.get(pk=voucher_id)
        self.assertFalse(voucher.is_posted)
        self.assertIsNone(voucher.journal_id)
        self.assertFalse(
            JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="EXPENSE_VOUCHER", reference_id=voucher_id,
            ).exists()
        )

    # ── فخّ الدفاتر: شركة قائمة لا دفتر لها من نوع expense_voucher ────────
    def test_existing_company_without_a_pre_seeded_book_can_still_issue_a_voucher(self):
        """`create_company` تزرع الدفاتر عند الإنشاء فقط — نحاكي شركةً بُذرت
        قبل هذا التذكرة بحذف دفتر `expense_voucher` بعد الإنشاء."""
        TenantBook.objects.filter(tenant=self.tenant, document_type="expense_voucher").delete()
        self.assertFalse(
            TenantBook.objects.filter(tenant=self.tenant, document_type="expense_voucher").exists()
        )
        res = self.client.post(
            f"{ACC}/expense-vouchers/", self._payload(), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(
            TenantBook.objects.filter(
                tenant=self.tenant, document_type="expense_voucher", book_number=0,
            ).exists()
        )

    def test_tenant_isolation_hides_other_companies_vouchers(self):
        other_user = User.objects.create_user(username="expother", password="x", email="o@x.co")
        other = create_company("شركة أخرى لسند المصروف", other_user)
        create_fiscal_year(other, 2026)
        other_cash = Account.objects.get(tenant=other, code="1101")
        other_electricity = Account.objects.get(tenant=other, code="5203")
        self.client.force_authenticate(user=other_user)
        self.client.post(
            f"{ACC}/expense-vouchers/",
            {
                "date": "2026-06-10", "expense_account": other_electricity.pk,
                "amount": "10.00", "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": other_cash.pk,
            },
            format="json", HTTP_X_TENANT_ID=str(other.TenantID),
        )

        res = self.client.post(
            f"{ACC}/expense-vouchers/", self._payload(), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)

        listing = self.client.get(f"{ACC}/expense-vouchers/", **self._auth())
        ids = {row["id"] for row in listing.json()["results"]} if isinstance(
            listing.json(), dict) and "results" in listing.json() else {
            row["id"] for row in listing.json()}
        self.assertTrue(ExpenseVoucher.objects.filter(tenant=other).exists())
        self.assertNotIn(
            ExpenseVoucher.objects.get(tenant=other).id, ids)


class ExpenseVoucherPermissionTest(APITestCase):
    """المفاتيح الجديدة تُنفَّذ خادمياً — إخفاء الزرّ ليس حماية."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="expowner", password="x", email="ow@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة صلاحيات المصروف", cls.owner)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.electricity = Account.objects.get(tenant=cls.tenant, code="5203")

    def _viewer(self):
        viewer = User.objects.create_user(username="expviewer", password="x", email="v@x.co")
        UserCompanyMembership.objects.create(user=viewer, tenant=self.tenant, role="viewer")
        self.client.force_authenticate(user=viewer)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_viewer_cannot_create_expense_voucher(self):
        res = self.client.post(
            f"{ACC}/expense-vouchers/",
            {
                "date": "2026-06-10", "expense_account": self.electricity.pk,
                "amount": "50.00", "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": self.cash.pk,
            },
            format="json", **self._viewer())
        self.assertEqual(res.status_code, 403, res.content)

    def test_viewer_cannot_unpost(self):
        self.client.force_authenticate(user=self.owner)
        created = self.client.post(
            f"{ACC}/expense-vouchers/",
            {
                "date": "2026-06-10", "expense_account": self.electricity.pk,
                "amount": "50.00", "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": self.cash.pk,
            },
            format="json", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        voucher_id = created.json()["id"]

        headers = self._viewer()
        res = self.client.post(
            f"{ACC}/expense-vouchers/{voucher_id}/unpost/", {}, format="json", **headers)
        self.assertEqual(res.status_code, 403, res.content)
