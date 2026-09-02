"""ISSUE #64 — تبديل قالب شركة قائمة (القرار 4: يرفع القناع ولا ينزع المزروع).

الملاحظة على الأثر — أي حسابٍ ودفترٍ وُجد بعد التبديل، وأي رصيدٍ في
`JournalLine` — لا على استدعاء `switch_company_template` مباشرة أو شكلها
الداخلي.
"""
from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, AccountingAuditLog, JournalLine
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesSettings
from tenants.company_templates import ACCOUNTING_FIRM_COA, ACCOUNTING_FIRM_DOCUMENT_TYPES
from tenants.models import Tenant, TenantBook, UserCompanyMembership
from tenants.services import COA_DATA, create_company

COMPANIES_URL = "/api/tenants/companies/"


def _switch_url(tenant_id):
    return f"{COMPANIES_URL}{tenant_id}/set-template/"


class TemplateSwitchApiTestBase(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="tpl-switch-mgr", password="x")
        self.tenant = create_company("شركة قابلة للتبديل", self.manager, template="general")
        # شركة ثانية تمنع الحلّ التلقائي أحادي الشركة في بعض الاختبارات.
        Tenant.objects.create(CompanyName="شركة أخرى — تبديل", SubscriptionPlan="Pro", Status="Active")

    def _auth(self, user=None):
        self.client.force_authenticate(user=user or self.manager)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _switch(self, template, user=None):
        return self.client.post(
            _switch_url(self.tenant.TenantID), {"template": template},
            format="json", **self._auth(user),
        )


class NoRowDeletedTest(TemplateSwitchApiTestBase):
    """general → accounting_firm: صفر حسابٍ محذوف، صفر دفترٍ محذوف."""

    def test_switch_general_to_accounting_firm_deletes_nothing(self):
        before_account_codes = set(
            Account.objects.filter(tenant=self.tenant).values_list("code", flat=True))
        before_book_types = set(
            TenantBook.objects.filter(tenant=self.tenant).values_list("document_type", flat=True))
        self.assertEqual(before_account_codes, {row[0] for row in COA_DATA})

        res = self._switch("accounting_firm")
        self.assertEqual(res.status_code, 200, res.content)

        after_account_codes = set(
            Account.objects.filter(tenant=self.tenant).values_list("code", flat=True))
        after_book_types = set(
            TenantBook.objects.filter(tenant=self.tenant).values_list("document_type", flat=True))

        # لا حذف: كل ما كان موجوداً قبل التبديل ما زال موجوداً.
        self.assertTrue(before_account_codes.issubset(after_account_codes))
        self.assertTrue(before_book_types.issubset(after_book_types))

        # الناقص من بذرة القالب الجديد زُرع فوق الموجود.
        self.assertTrue({row[0] for row in ACCOUNTING_FIRM_COA}.issubset(after_account_codes))
        self.assertTrue(set(ACCOUNTING_FIRM_DOCUMENT_TYPES).issubset(after_book_types))

    def test_existing_account_is_not_renamed_by_the_new_seed(self):
        """4102 موجودٌ باسم general («مبيعات الخدمات») — التبديل لا يُعيد تسميته
        على اسم accounting_firm («إيرادات الخدمات»): لا تعديل على الموجود."""
        before_name = Account.objects.get(tenant=self.tenant, code="4102").name
        res = self._switch("accounting_firm")
        self.assertEqual(res.status_code, 200, res.content)
        after = Account.objects.get(tenant=self.tenant, code="4102")
        self.assertEqual(after.name, before_name)

    def test_no_account_is_deactivated_by_the_switch(self):
        res = self._switch("accounting_firm")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(
            Account.objects.filter(tenant=self.tenant, is_active=False).exists())

    def test_switching_back_to_general_restores_the_dropped_seed(self):
        """شركةٌ وُلدت `accounting_firm` (لم تُزرع لها 1104/1201/2106/4101
        إطلاقاً) ثم تحوّلت إلى `general`: تلك الحسابات تُزرع الآن — لا رجوعاً
        عن حذف (لم يقع حذف)، بل زرعاً للناقص من بذرة الوجهة الجديدة."""
        firm_tenant = create_company("مكتب وُلد مكتباً", self.manager, template="accounting_firm")
        codes = set(Account.objects.filter(tenant=firm_tenant).values_list("code", flat=True))
        for dropped in ("1104", "1201", "2106", "4101"):
            self.assertNotIn(dropped, codes)

        self.client.force_authenticate(user=self.manager)
        res = self.client.post(
            _switch_url(firm_tenant.TenantID), {"template": "general"},
            format="json", HTTP_X_TENANT_ID=str(firm_tenant.TenantID),
        )
        self.assertEqual(res.status_code, 200, res.content)
        codes = set(Account.objects.filter(tenant=firm_tenant).values_list("code", flat=True))
        self.assertTrue({row[0] for row in COA_DATA}.issubset(codes))


class IdempotentSwitchTest(TemplateSwitchApiTestBase):
    def test_switching_to_the_same_target_twice_creates_nothing_the_second_time(self):
        first = self._switch("accounting_firm")
        self.assertEqual(first.status_code, 200, first.content)
        self.assertTrue(first.json()["accounts_created"] or first.json()["book_types_created"])

        before_accounts = Account.objects.filter(tenant=self.tenant).count()
        before_books = TenantBook.objects.filter(tenant=self.tenant).count()

        second = self._switch("accounting_firm")
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()["accounts_created"], [])
        self.assertEqual(second.json()["book_types_created"], [])
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), before_accounts)
        self.assertEqual(TenantBook.objects.filter(tenant=self.tenant).count(), before_books)


class TemplateSwitchAccessTest(TemplateSwitchApiTestBase):
    def test_non_manager_cannot_switch(self):
        staff = User.objects.create_user(username="tpl-switch-staff", password="x")
        UserCompanyMembership.objects.create(user=staff, tenant=self.tenant, role="staff")
        res = self._switch("accounting_firm", user=staff)
        self.assertIn(res.status_code, (403, 404))

    def test_unknown_template_key_is_rejected_in_arabic(self):
        res = self._switch("not-a-real-template")
        self.assertEqual(res.status_code, 400, res.content)
        body = res.json()
        self.assertIn("template", body)
        self.assertIn("غير معروف", str(body["template"]))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.template, "general")


class TemplateSwitchAuditLogTest(TemplateSwitchApiTestBase):
    def test_switch_writes_an_audit_log_row(self):
        res = self._switch("accounting_firm")
        self.assertEqual(res.status_code, 200, res.content)
        row = AccountingAuditLog.objects.filter(
            tenant=self.tenant, action="TEMPLATE_SWITCH").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.user_id, self.manager.pk)
        self.assertIn("accounting_firm", row.change_details)


class TemplateSwitchMaskInvalidationTest(TemplateSwitchApiTestBase):
    """القناع يجب أن يتبدّل فوراً — حتى في النشر أحادي الشركة (بلا ترويسة)."""

    def setUp(self):
        # هذا الاختبار وحده يحتاج شركةً واحدة في القاعدة كلها.
        self.manager = User.objects.create_user(username="tpl-switch-single", password="x")
        self.tenant = create_company("شركة وحيدة — تبديل", self.manager, template="general")

    def test_mask_applies_immediately_without_the_tenant_header(self):
        from core.tenant_utils import invalidate_tenant_cache
        invalidate_tenant_cache()
        self.client.force_authenticate(user=self.manager)

        res_before = self.client.get("/api/inventory/products/")
        self.assertNotEqual(res_before.status_code, 404, res_before.content)

        switch = self._switch("accounting_firm")
        self.assertEqual(switch.status_code, 200, switch.content)

        res_after = self.client.get("/api/inventory/products/")
        self.assertEqual(res_after.status_code, 404, res_after.content)


class TemplateSwitchBalancesIntactTest(TemplateSwitchApiTestBase):
    """أرصدة دليل الحسابات مطابقةٌ حرفياً قبل التبديل وبعده — على قيدٍ فعلي."""

    def setUp(self):
        super().setUp()
        create_fiscal_year(self.tenant, 2026)
        cash = Account.objects.get(tenant=self.tenant, code="1101")
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل التبديل", partner_type="Customer")
        SalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"default_cash_account": cash})
        from tenants.models import Currency
        ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        res = self.client.post(
            "/api/sales/payments/",
            {
                "partner": customer.pk,
                "payment_date": "2026-08-20",
                "amount": "500.00",
                "currency": ils.pk,
                "cash_or_bank_account": cash.pk,
                "auto_post": True,
            },
            format="json", **self._auth(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIsNone(res.data.get("auto_post_error"), res.data)

    def _balance_snapshot(self):
        return list(
            JournalLine.objects.filter(tenant_id=self.tenant.pk)
            .values("account_id")
            .annotate(debit=Sum("debit"), credit=Sum("credit"))
            .order_by("account_id")
        )

    def test_balances_are_byte_identical_after_switch(self):
        before = self._balance_snapshot()
        res = self._switch("accounting_firm")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._balance_snapshot(), before)
