"""issue #80 — سند إيراد: مرآة سند المصروف (issue #56) بعكس الاتجاه.

قبل هذا الملف لا وجود لمستند إيرادٍ عامّ للشركة: عمولةٌ عارضة أو إيجارٌ نحصّله
لا فاتورة بيع له ولا عميل. الاختبارات تحرس **الأثر عند الـHTTP** — أسطر القيد
وأرصدة الحسابات وحالة المستند — على نمط `test_expense_voucher_api.py` حرفياً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, RevenueVoucher, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency, TenantBook, UserCompanyMembership
from tenants.services import create_company

ACC = "/api/accounting"
D = lambda v: Decimal(str(v))


class RevenueVoucherApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="revmgr", password="x", email="r@x.co")
        cls.ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة سندات الإيراد", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.commission = Account.objects.create(
            tenant=cls.tenant, code="4210", name="عمولات محصّلة", account_type="Revenue",
            parent=Account.objects.get(tenant=cls.tenant, code="42"), is_active=True,
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="دافع سند الإيراد", partner_type="Customer")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _payload(self, **over):
        body = {
            "date": "2026-06-10",
            "revenue_account": self.commission.pk,
            "amount": "500.00",
            "currency": self.ils.pk,
            "payment_method": "cash",
            "cash_or_bank_account": self.cash.pk,
        }
        body.update(over)
        return body

    # ── معيار القبول: عمولة نقداً بلا دافع وبلا فاتورة بيع ───────────────
    def test_cash_commission_revenue_without_payer_or_invoice(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertTrue(body["is_posted"])
        self.assertIsNone(body["payer_partner"])
        self.assertEqual(body["kind"], "normal")

        voucher = RevenueVoucher.objects.get(pk=body["id"])
        self.assertTrue(voucher.is_posted)
        self.assertIsNone(voucher.payer_partner_id)
        lines = list(voucher.journal.lines.select_related("account"))
        debit = next(ln for ln in lines if ln.debit > 0)
        credit = next(ln for ln in lines if ln.credit > 0)
        self.assertEqual(debit.account_id, self.cash.pk)
        self.assertEqual(debit.debit, D("500.00"))
        self.assertEqual(credit.account_id, self.commission.pk)
        self.assertEqual(credit.credit, D("500.00"))

    def test_revenue_account_can_be_created_by_name_under_42(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/",
            self._payload(revenue_account=None, revenue_account_name="إيراد استشارات عابرة"),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        acc = Account.objects.get(tenant=self.tenant, name="إيراد استشارات عابرة")
        self.assertTrue(acc.code.startswith("42"))
        self.assertEqual(acc.account_type, "Revenue")

    # ── معيار القبول: شيك على 1107 ────────────────────────────────────
    def test_cheque_revenue_posts_to_1107(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/",
            self._payload(payment_method="cheque", cash_or_bank_account=None),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = RevenueVoucher.objects.get(pk=res.json()["id"])
        debit = voucher.journal.lines.get(debit__gt=0)
        self.assertEqual(debit.account.code, "1107")

    # ── معيار القبول: على الحساب على 1103 (بلا دافع) ───────────────────
    def test_on_account_without_payer_posts_to_1103(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/",
            self._payload(payment_method="on_account", cash_or_bank_account=None),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = RevenueVoucher.objects.get(pk=res.json()["id"])
        debit = voucher.journal.lines.get(debit__gt=0)
        self.assertEqual(debit.account.code, "1103")
        self.assertIsNone(debit.partner_id)

    # ── معيار القبول: على الحساب يَدين ذمّة العميل باسمه ────────────────
    def test_on_account_with_partner_payer_debits_partner_ar_account(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/",
            self._payload(
                payment_method="on_account", cash_or_bank_account=None,
                payer_partner=self.customer.pk,
            ),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = RevenueVoucher.objects.get(pk=res.json()["id"])
        debit = voucher.journal.lines.get(debit__gt=0)
        self.customer.refresh_from_db()
        self.assertIsNotNone(self.customer.linked_account_id)
        self.assertEqual(debit.account_id, self.customer.linked_account_id)
        self.assertEqual(debit.partner_id, self.customer.pk)

    # ── معيار القبول: ضريبة مخرجات على 2104 ─────────────────────────────
    def test_vat_portion_posts_to_2104(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/",
            self._payload(amount="580.00", tax_amount="80.00"),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        voucher = RevenueVoucher.objects.get(pk=res.json()["id"])
        lines = list(voucher.journal.lines.select_related("account"))
        vat_line = next(ln for ln in lines if ln.account.code == "2104")
        revenue_line = next(ln for ln in lines if ln.account_id == self.commission.pk)
        self.assertEqual(vat_line.credit, D("80.00"))
        self.assertEqual(revenue_line.credit, D("500.00"))

    # ── معيار القبول: مرتجعٌ بمبلغٍ موجب يقلب الاتجاه ───────────────────
    def test_return_kind_flips_journal_direction_with_positive_amount(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(kind="return"), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["kind"], "return")
        self.assertEqual(D(body["amount"]), D("500.00"))  # موجب دوماً

        voucher = RevenueVoucher.objects.get(pk=body["id"])
        lines = list(voucher.journal.lines.select_related("account"))
        # عاديّ: مدين الصندوق / دائن الإيراد — مرتجع: العكس تماماً، بلا سالب.
        cash_line = next(ln for ln in lines if ln.account_id == self.cash.pk)
        revenue_line = next(ln for ln in lines if ln.account_id == self.commission.pk)
        self.assertEqual(cash_line.credit, D("500.00"))
        self.assertEqual(cash_line.debit, D("0.00"))
        self.assertEqual(revenue_line.debit, D("500.00"))
        self.assertEqual(revenue_line.credit, D("0.00"))
        for ln in lines:
            self.assertGreaterEqual(ln.debit, D("0.00"))
            self.assertGreaterEqual(ln.credit, D("0.00"))

    def test_invalid_kind_rejected(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(kind="bogus"), format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)

    # ── معيار القبول: إلغاء الترحيل يعيد الأرصدة حرفياً ─────────────────
    def test_unpost_reverses_balances_exactly(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(), format="json", **self._auth())
        voucher_id = res.json()["id"]

        unpost = self.client.post(
            f"{ACC}/revenue-vouchers/{voucher_id}/unpost/", {}, format="json", **self._auth())
        self.assertEqual(unpost.status_code, 200, unpost.content)
        voucher = RevenueVoucher.objects.get(pk=voucher_id)
        self.assertFalse(voucher.is_posted)
        self.assertIsNone(voucher.journal_id)
        self.assertFalse(
            JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="REVENUE_VOUCHER", reference_id=voucher_id,
            ).exists()
        )

    # ── فخّ الدفاتر: شركة قائمة لا دفتر لها من نوع revenue_voucher ────────
    def test_existing_company_without_a_pre_seeded_book_can_still_issue_a_voucher(self):
        TenantBook.objects.filter(tenant=self.tenant, document_type="revenue_voucher").delete()
        self.assertFalse(
            TenantBook.objects.filter(tenant=self.tenant, document_type="revenue_voucher").exists()
        )
        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(
            TenantBook.objects.filter(
                tenant=self.tenant, document_type="revenue_voucher", book_number=0,
            ).exists()
        )

    def test_tenant_isolation_hides_other_companies_vouchers(self):
        other_user = User.objects.create_user(username="revother", password="x", email="ro@x.co")
        other = create_company("شركة أخرى لسند الإيراد", other_user)
        create_fiscal_year(other, 2026)
        other_cash = Account.objects.get(tenant=other, code="1101")
        other_commission = Account.objects.get(tenant=other, code="4202")
        self.client.force_authenticate(user=other_user)
        self.client.post(
            f"{ACC}/revenue-vouchers/",
            {
                "date": "2026-06-10", "revenue_account": other_commission.pk,
                "amount": "10.00", "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": other_cash.pk,
            },
            format="json", HTTP_X_TENANT_ID=str(other.TenantID),
        )

        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(), format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)

        listing = self.client.get(f"{ACC}/revenue-vouchers/", **self._auth())
        ids = {row["id"] for row in listing.json()["results"]} if isinstance(
            listing.json(), dict) and "results" in listing.json() else {
            row["id"] for row in listing.json()}
        self.assertTrue(RevenueVoucher.objects.filter(tenant=other).exists())
        self.assertNotIn(
            RevenueVoucher.objects.get(tenant=other).id, ids)

    # ── ما لا يُفعل: لا PATCH ولا DELETE بعد الإنشاء ────────────────────
    def test_patch_and_delete_are_rejected(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/", self._payload(), format="json", **self._auth())
        voucher_id = res.json()["id"]

        patch = self.client.patch(
            f"{ACC}/revenue-vouchers/{voucher_id}/", {"amount": "1.00"}, format="json",
            **self._auth())
        self.assertEqual(patch.status_code, 405, patch.content)

        delete = self.client.delete(f"{ACC}/revenue-vouchers/{voucher_id}/", **self._auth())
        self.assertEqual(delete.status_code, 405, delete.content)


class RevenueVoucherPermissionTest(APITestCase):
    """المفاتيح الجديدة تُنفَّذ خادمياً — إخفاء الزرّ ليس حماية."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="revowner", password="x", email="ro2@x.co")
        cls.ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة صلاحيات الإيراد", cls.owner)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.commission = Account.objects.create(
            tenant=cls.tenant, code="4210", name="عمولات محصّلة", account_type="Revenue",
            parent=Account.objects.get(tenant=cls.tenant, code="42"), is_active=True,
        )

    def _viewer(self):
        viewer = User.objects.create_user(username="revviewer", password="x", email="rv@x.co")
        UserCompanyMembership.objects.create(user=viewer, tenant=self.tenant, role="viewer")
        self.client.force_authenticate(user=viewer)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_viewer_cannot_create_revenue_voucher(self):
        res = self.client.post(
            f"{ACC}/revenue-vouchers/",
            {
                "date": "2026-06-10", "revenue_account": self.commission.pk,
                "amount": "50.00", "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": self.cash.pk,
            },
            format="json", **self._viewer())
        self.assertEqual(res.status_code, 403, res.content)

    def test_viewer_cannot_unpost(self):
        self.client.force_authenticate(user=self.owner)
        created = self.client.post(
            f"{ACC}/revenue-vouchers/",
            {
                "date": "2026-06-10", "revenue_account": self.commission.pk,
                "amount": "50.00", "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": self.cash.pk,
            },
            format="json", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        voucher_id = created.json()["id"]

        headers = self._viewer()
        res = self.client.post(
            f"{ACC}/revenue-vouchers/{voucher_id}/unpost/", {}, format="json", **headers)
        self.assertEqual(res.status_code, 403, res.content)
