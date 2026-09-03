"""issue #84 (#77 القسم ٧) — نقطة الحفظ الدفعي وقواعد الترميز.

كل صفٍّ سندَ إيرادٍ أو مصروف بمعاملته الذرّية الخاصة — صفٌّ سقط لا يُسقط
البقية. وقاعدة الترميز (شركة، طرف) ← حساب تُكتب عند الحفظ لا عند الاقتراح،
وتُقترح في الصفّ التالي قابلةً للتجاوز بلا سؤال، ويراها المحاسب ويعدّلها
ويحذفها.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import (
    Account, ExpenseVoucher, JournalHeader, PartnerAccountCodingRule, RevenueVoucher,
)
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

ACC = "/api/accounting"
D = lambda v: Decimal(str(v))


class VoucherBatchSaveApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="batchmgr", password="x", email="b@x.co")
        cls.ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الترميز الدفعي", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.electricity = Account.objects.get(tenant=cls.tenant, code="5203")
        cls.rent = Account.objects.get(tenant=cls.tenant, code="5201")
        cls.commission = Account.objects.create(
            tenant=cls.tenant, code="4210", name="عمولات محصّلة", account_type="Revenue",
            parent=Account.objects.get(tenant=cls.tenant, code="42"), is_active=True,
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الترميز الدفعي", partner_type="Supplier")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _row(self, **over):
        row = {
            "direction": "expense",
            "date": "2026-06-10",
            "account": self.electricity.pk,
            "amount": "50.00",
            "currency": self.ils.pk,
            "payment_method": "cash",
            "cash_or_bank_account": self.cash.pk,
        }
        row.update(over)
        return row

    def _rules(self, headers):
        listing = self.client.get(f"{ACC}/coding-rules/", **headers)
        data = listing.json()
        return data["results"] if isinstance(data, dict) and "results" in data else data

    # ── معيار القبول: عشرون صفّاً بحفظٍ واحد تُنتج عشرين قيداً ────────────
    def test_twenty_rows_in_one_save_produce_twenty_journals(self):
        rows = [self._row() for _ in range(20)]
        res = self.client.post(
            f"{ACC}/vouchers/batch-save/", {"rows": rows}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["succeeded"], 20)
        self.assertEqual(body["failed"], 0)
        self.assertEqual(len(body["rows"]), 20)
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="EXPENSE_VOUCHER").count(),
            20,
        )

    # ── معيار القبول: صفٌّ خاطئ وسط عشرين — تسعة عشر تُحفظ ─────────────────
    def test_one_bad_row_among_twenty_still_saves_nineteen(self):
        rows = [self._row() for _ in range(20)]
        rows[10] = self._row(amount="0")  # يرفضه create_expense_voucher (≤ صفر)
        res = self.client.post(
            f"{ACC}/vouchers/batch-save/", {"rows": rows}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["succeeded"], 19)
        self.assertEqual(body["failed"], 1)
        bad = next(r for r in body["rows"] if r["index"] == 10)
        self.assertFalse(bad["success"])
        self.assertIn("error", bad)
        for r in body["rows"]:
            if r["index"] != 10:
                self.assertTrue(r["success"], r)
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="EXPENSE_VOUCHER").count(),
            19,
        )

    def test_mixed_direction_rows_each_create_their_own_kind(self):
        expense_row = self._row()
        revenue_row = self._row(direction="revenue", account=self.commission.pk)
        res = self.client.post(
            f"{ACC}/vouchers/batch-save/", {"rows": [expense_row, revenue_row]},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["succeeded"], 2)
        self.assertTrue(ExpenseVoucher.objects.filter(tenant=self.tenant).exists())
        self.assertTrue(RevenueVoucher.objects.filter(tenant=self.tenant).exists())

    # ── معيار القبول: طرفٌ رُمِّز مرّة يُقترح حسابه في المرة التالية ──────
    def test_coding_rule_written_on_save_and_visible_for_suggestion(self):
        headers = self._auth()
        res = self.client.post(
            f"{ACC}/vouchers/batch-save/",
            {"rows": [self._row(partner=self.supplier.pk)]}, format="json", **headers)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["succeeded"], 1)

        rules = self._rules(headers)
        rule = next(r for r in rules if r["partner"] == self.supplier.pk)
        self.assertEqual(rule["account"], self.electricity.pk)

    # ── معيار القبول: الاقتراح يُتجاوَز بلا سؤال ───────────────────────────
    def test_row_can_override_suggested_account_without_asking(self):
        headers = self._auth()
        first = self._row(partner=self.supplier.pk, account=self.electricity.pk)
        self.client.post(f"{ACC}/vouchers/batch-save/", {"rows": [first]}, format="json", **headers)

        second = self._row(partner=self.supplier.pk, account=self.rent.pk)
        res = self.client.post(
            f"{ACC}/vouchers/batch-save/", {"rows": [second]}, format="json", **headers)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["succeeded"], 1)

        rules = self._rules(headers)
        rule = next(r for r in rules if r["partner"] == self.supplier.pk)
        self.assertEqual(rule["account"], self.rent.pk)  # استُبدلت لا تراكمت
        self.assertEqual(
            PartnerAccountCodingRule.objects.filter(
                tenant=self.tenant, partner=self.supplier).count(),
            1,
        )

    # ── معيار القبول: المحاسب يرى قواعده ويعدّلها ويحذفها ──────────────────
    def test_accountant_can_edit_and_delete_coding_rule(self):
        headers = self._auth()
        self.client.post(
            f"{ACC}/vouchers/batch-save/",
            {"rows": [self._row(partner=self.supplier.pk)]}, format="json", **headers)
        rule = PartnerAccountCodingRule.objects.get(tenant=self.tenant, partner=self.supplier)

        patch = self.client.patch(
            f"{ACC}/coding-rules/{rule.id}/", {"account": self.rent.pk}, format="json", **headers)
        self.assertEqual(patch.status_code, 200, patch.content)
        rule.refresh_from_db()
        self.assertEqual(rule.account_id, self.rent.pk)

        delete = self.client.delete(f"{ACC}/coding-rules/{rule.id}/", **headers)
        self.assertEqual(delete.status_code, 204, delete.content)
        self.assertFalse(PartnerAccountCodingRule.objects.filter(pk=rule.id).exists())

    def test_tenant_isolation_hides_other_companies_coding_rules(self):
        other_user = User.objects.create_user(username="batchother", password="x", email="bo2@x.co")
        other = create_company("شركة أخرى للترميز الدفعي", other_user)
        create_fiscal_year(other, 2026)
        other_cash = Account.objects.get(tenant=other, code="1101")
        other_electricity = Account.objects.get(tenant=other, code="5203")
        other_supplier = Partner.objects.create(
            tenant=other, name="مورد شركة أخرى", partner_type="Supplier")
        self.client.force_authenticate(user=other_user)
        self.client.post(
            f"{ACC}/vouchers/batch-save/",
            {"rows": [{
                "direction": "expense", "date": "2026-06-10",
                "account": other_electricity.pk, "amount": "10.00",
                "currency": self.ils.pk, "payment_method": "cash",
                "cash_or_bank_account": other_cash.pk, "partner": other_supplier.pk,
            }]},
            format="json", HTTP_X_TENANT_ID=str(other.TenantID),
        )

        rules = self._rules(self._auth())
        self.assertFalse(any(r["partner"] == other_supplier.pk for r in rules))


class VoucherBatchSavePermissionTest(APITestCase):
    """المفاتيح الجديدة تُنفَّذ خادمياً — إخفاء الزرّ ليس حماية."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="batchowner", password="x", email="bo@x.co")
        cls.ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة صلاحيات الترميز الدفعي", cls.owner)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.electricity = Account.objects.get(tenant=cls.tenant, code="5203")

    def _sales_employee(self):
        """دورٌ يتجاوز حارس «مستعرض قراءة فقط» العام لكنه بلا `finance.*` —
        يحرس فحص الصلاحية **داخل** الحفظ الدفعي نفسه لا الحارس العام فقط."""
        employee = User.objects.create_user(username="batchsales", password="x", email="bs@x.co")
        UserCompanyMembership.objects.create(user=employee, tenant=self.tenant, role="sales")
        self.client.force_authenticate(user=employee)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _row(self):
        return {
            "direction": "expense", "date": "2026-06-10", "account": self.electricity.pk,
            "amount": "50.00", "currency": self.ils.pk, "payment_method": "cash",
            "cash_or_bank_account": self.cash.pk,
        }

    def test_row_without_finance_permission_fails_with_permission_message(self):
        headers = self._sales_employee()
        res = self.client.post(
            f"{ACC}/vouchers/batch-save/", {"rows": [self._row()]}, format="json", **headers)
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["succeeded"], 0)
        self.assertEqual(body["failed"], 1)
        self.assertIn("صلاحية", body["rows"][0]["error"])
        self.assertFalse(ExpenseVoucher.objects.filter(tenant=self.tenant).exists())

    def test_role_without_coding_rule_permission_cannot_edit_or_delete(self):
        self.client.force_authenticate(user=self.owner)
        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورد صلاحيات الترميز", partner_type="Supplier")
        row = self._row()
        row["partner"] = supplier.pk
        self.client.post(
            f"{ACC}/vouchers/batch-save/", {"rows": [row]}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        rule = PartnerAccountCodingRule.objects.get(tenant=self.tenant, partner=supplier)

        headers = self._sales_employee()
        patch = self.client.patch(
            f"{ACC}/coding-rules/{rule.id}/", {"account": self.electricity.pk},
            format="json", **headers)
        self.assertEqual(patch.status_code, 403, patch.content)
        delete = self.client.delete(f"{ACC}/coding-rules/{rule.id}/", **headers)
        self.assertEqual(delete.status_code, 403, delete.content)
