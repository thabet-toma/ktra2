"""إعدادُ الشركة يحسم: اسمٌ حرّ يُنبت حساباً، أم ربطٌ بحسابٍ قائم.

بلاغ المالك: «لما أسجّل مصروف أو إيراد بدي إعداد إنه أربطه بحساب ولا تكست فري
عكيفي — بالإعدادات أظبط أكثر».

قبل هذا الإعداد كان `expense_account_name`/`revenue_account_name` مقبولاً دائماً
(issue #56/#80): تكتب «اشتراك إنترنت» فيُفتح حسابٌ تحت «52»، بلا طريقٍ لشركةٍ
تريد شجرةً مضبوطة أن توقف ذلك. `TenantSettings.voucher_account_entry_mode`
يفصل، والافتراضي `free` — أي أن كل شركةٍ قائمة تبقى على سلوكها حرفياً.

الحارس **خادميّ**: إخفاءُ الحقل في الواجهة تجميلٌ لا تصريح، فالاختبار على
رمز استجابة الـHTTP لا على شرطٍ في مكوّن React.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, ExpenseVoucher, RevenueVoucher
from accounting.services import create_fiscal_year
from tenants.models import Currency, TenantSettings
from tenants.services import create_company

ACC = "/api/accounting"


class VoucherAccountEntryModeTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="entrymode", password="x")
        cls.ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة وضع الإدخال", cls.owner)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _set_mode(self, mode):
        TenantSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"voucher_account_entry_mode": mode})

    def _expense(self, **over):
        body = {
            "date": "2026-06-10", "amount": "80.00", "currency": self.ils.pk,
            "payment_method": "cash", "cash_or_bank_account": self.cash.pk,
        }
        body.update(over)
        return self.client.post(
            f"{ACC}/expense-vouchers/", body, format="json", **self.headers)

    def _revenue(self, **over):
        body = {
            "date": "2026-06-10", "amount": "80.00", "currency": self.ils.pk,
            "payment_method": "cash", "cash_or_bank_account": self.cash.pk,
        }
        body.update(over)
        return self.client.post(
            f"{ACC}/revenue-vouchers/", body, format="json", **self.headers)

    # ── الافتراضي: نصٌّ حرّ (السلوك القائم، لا تراجع فيه) ──────────────

    def test_free_text_expense_still_works_by_default(self):
        res = self._expense(expense_account_name="اشتراك إنترنت")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(
            Account.objects.filter(tenant=self.tenant, name="اشتراك إنترنت").exists())

    def test_free_text_revenue_still_works_by_default(self):
        res = self._revenue(revenue_account_name="عمولة وساطة")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(
            Account.objects.filter(tenant=self.tenant, name="عمولة وساطة").exists())

    # ── الوضع الملزِم: الشجرة أو لا شيء ────────────────────────────────

    def test_linked_mode_refuses_free_text_expense(self):
        self._set_mode(TenantSettings.VOUCHER_ACCOUNT_ENTRY_LINKED)
        res = self._expense(expense_account_name="مصروف مخترَع")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(
            Account.objects.filter(tenant=self.tenant, name="مصروف مخترَع").exists())
        self.assertEqual(ExpenseVoucher.objects.filter(tenant=self.tenant).count(), 0)

    def test_linked_mode_refuses_free_text_revenue(self):
        self._set_mode(TenantSettings.VOUCHER_ACCOUNT_ENTRY_LINKED)
        res = self._revenue(revenue_account_name="إيراد مخترَع")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(
            Account.objects.filter(tenant=self.tenant, name="إيراد مخترَع").exists())
        self.assertEqual(RevenueVoucher.objects.filter(tenant=self.tenant).count(), 0)

    def test_linked_mode_still_accepts_an_account_from_the_tree(self):
        """الوضع يمنع النبات لا الإدخال — حسابٌ قائمٌ يمرّ كما كان."""
        self._set_mode(TenantSettings.VOUCHER_ACCOUNT_ENTRY_LINKED)
        expense_account = Account.objects.create(
            tenant=self.tenant, code="5299", name="مصروف قائم",
            account_type="Expense",
            parent=Account.objects.get(tenant=self.tenant, code="52"),
            is_active=True,
        )
        res = self._expense(expense_account=expense_account.pk)
        self.assertEqual(res.status_code, 201, res.content)

    def test_the_setting_reaches_the_client_on_settings_current(self):
        """الواجهة تقرأ الوضع من نفس ردّ الإعدادات — بلا نداءٍ ثانٍ."""
        self._set_mode(TenantSettings.VOUCHER_ACCOUNT_ENTRY_LINKED)
        res = self.client.get("/api/tenants/settings/current/", **self.headers)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json().get("voucher_account_entry_mode"), "linked")
