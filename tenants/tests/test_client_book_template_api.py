"""ISSUE #81 — قالب «دفتر عميل» (القسم ١ من #77): البذرة والدفاتر والقناع.

مرآة `test_company_template_api.py` و`test_company_template_mask_api.py`
لقالب `accounting_firm`، ومعها اختبار أثرٍ فعلي: سند إيراد وسند مصروف
يُرحَّلان داخل دفترٍ بهذا القالب (معيار قبول التذكرة).
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, ExpenseVoucher, RevenueVoucher
from accounting.services import create_fiscal_year, create_expense_voucher, create_revenue_voucher
from tenants.company_templates import CLIENT_BOOK_COA, CLIENT_BOOK_DOCUMENT_TYPES
from tenants.models import Currency, Tenant, TenantBook
from tenants.services import create_company

URL = "/api/tenants/companies/"


class ClientBookTemplateSeedApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cb-owner", password="x")
        self.client.force_authenticate(user=self.user)

    def test_seeds_the_stated_tree_with_no_inventory_or_cogs_account(self):
        res = self.client.post(
            URL, {"CompanyName": "دفتر عميل تجريبي", "template": "client_book"},
            format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["template"], "client_book")

        tenant = Tenant.objects.get(pk=body["TenantID"])
        codes = set(Account.objects.filter(tenant=tenant).values_list("code", flat=True))
        self.assertEqual(codes, {row[0] for row in CLIENT_BOOK_COA})

        # القاعدة: لا حساب مخزون ولا حساب تكلفة بضاعة مباعة.
        self.assertNotIn("1104", codes)  # المخزون
        self.assertNotIn("5101", codes)  # تكلفة البضاعة المباعة (كود القالب العام)

        # ثلاثة عشر بنداً تحت المصاريف التشغيلية بالضبط.
        operating = Account.objects.filter(tenant=tenant, parent__code="52")
        self.assertEqual(operating.count(), 13)

    def test_seeds_only_its_five_document_types(self):
        res = self.client.post(
            URL, {"CompanyName": "دفتر عميل ثانٍ", "template": "client_book"},
            format="json")
        self.assertEqual(res.status_code, 201, res.content)
        tenant = Tenant.objects.get(pk=res.json()["TenantID"])

        seeded_types = set(
            TenantBook.objects.filter(tenant=tenant).values_list("document_type", flat=True)
        )
        self.assertEqual(seeded_types, set(CLIENT_BOOK_DOCUMENT_TYPES))
        self.assertEqual(len(CLIENT_BOOK_DOCUMENT_TYPES), 5)
        self.assertEqual(
            TenantBook.objects.filter(tenant=tenant).count(),
            len(CLIENT_BOOK_DOCUMENT_TYPES) * 10,
        )


class ClientBookMaskedApiTest(APITestCase):
    """طلبٌ إلى مسارٍ مقنَّع يُردّ من الخادم — معيار القبول الثاني."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cb-mask", password="x")
        cls.tenant = create_company("دفتر عميل مقنَّع", cls.user, template="client_book")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_inventory_and_logistics_are_404(self):
        for path in (
            "/api/inventory/products/",
            "/api/logistics/deals/",
            "/api/logistics/purchase-invoices/",
            "/api/store/admin/settings/",
        ):
            with self.subTest(path=path):
                res = self.client.get(path, **self._auth())
                self.assertEqual(res.status_code, 404, res.content)

    def test_sales_invoicing_and_goods_screens_are_404(self):
        """القسم الذي يزيده هذا القالب فوق قناع `accounting_firm`: لا فواتير
        بيع، لا أوامر بيع، لا عروض أسعار، لا إرساليات، لا محجوزات."""
        for path in (
            "/api/sales/invoices/",
            "/api/sales/quotations/",
            "/api/sales/orders/",
            "/api/sales/delivery-orders/",
            "/api/sales/reports/reserved-stock/",
        ):
            with self.subTest(path=path):
                res = self.client.get(path, **self._auth())
                self.assertEqual(res.status_code, 404, res.content)

    def test_receipt_and_payment_vouchers_stay_open(self):
        """أحد الدفاتر الخمسة المزروعة — سند القبض (`CustomerPayment`) وسند
        الصرف (`SupplierPayment`، يعيش تحت اللوجستيات لأسبابٍ تاريخية)."""
        for path in ("/api/sales/payments/", "/api/logistics/supplier-payments/"):
            with self.subTest(path=path):
                res = self.client.get(path, **self._auth())
                self.assertEqual(res.status_code, 200, res.content)

    def test_unrelated_endpoints_stay_open(self):
        for path in ("/api/accounting/accounts/", "/api/partners/"):
            with self.subTest(path=path):
                res = self.client.get(path, **self._auth())
                self.assertNotEqual(res.status_code, 404, res.content)

    def test_permissions_me_reports_the_template(self):
        res = self.client.get("/api/permissions/me/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["template"], "client_book")


class ClientBookVouchersPostTest(APITestCase):
    """معيار القبول الثالث: سند إيراد وسند مصروف يعملان داخل الدفتر ويُرحَّلان."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cb-vouchers", password="x")
        Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("دفتر عميل بسندات", cls.user, template="client_book")
        create_fiscal_year(cls.tenant, 2026)
        cls.currency = Currency.objects.filter(IsBaseCurrency=True).first()
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.rent = Account.objects.get(tenant=cls.tenant, code="5201")
        cls.sales_revenue = Account.objects.get(tenant=cls.tenant, code="4101")

    def test_expense_voucher_posts_and_balances(self):
        voucher = create_expense_voucher(
            tenant=self.tenant, date=date(2026, 6, 10), amount=Decimal("300.00"),
            currency=self.currency, payment_method=ExpenseVoucher.PAYMENT_CASH,
            expense_account=self.rent, cash_or_bank_account_id=self.cash.pk,
            user=self.user,
        )
        self.assertTrue(voucher.is_posted)
        lines = list(voucher.journal.lines.select_related("account"))
        debit = next(ln for ln in lines if ln.debit > 0)
        credit = next(ln for ln in lines if ln.credit > 0)
        self.assertEqual(debit.account_id, self.rent.pk)
        self.assertEqual(credit.account_id, self.cash.pk)
        self.assertEqual(debit.debit, credit.credit)

    def test_revenue_voucher_posts_and_balances(self):
        voucher = create_revenue_voucher(
            tenant=self.tenant, date=date(2026, 6, 10), amount=Decimal("450.00"),
            currency=self.currency, payment_method=RevenueVoucher.PAYMENT_CASH,
            revenue_account=self.sales_revenue, cash_or_bank_account_id=self.cash.pk,
            user=self.user,
        )
        self.assertTrue(voucher.is_posted)
        lines = list(voucher.journal.lines.select_related("account"))
        debit = next(ln for ln in lines if ln.debit > 0)
        credit = next(ln for ln in lines if ln.credit > 0)
        self.assertEqual(debit.account_id, self.cash.pk)
        self.assertEqual(credit.account_id, self.sales_revenue.pk)
        self.assertEqual(debit.debit, credit.credit)


class GeneralAndAccountingFirmUnaffectedTest(APITestCase):
    """معيار القبول الرابع: `general` و`accounting_firm` بلا أي تغيير."""

    def test_general_unaffected(self):
        user = User.objects.create_user(username="cb-gen-guard", password="x")
        tenant = create_company("شركة عامة بعد #81", user)
        self.assertEqual(tenant.template, "general")
        from tenants.services import COA_DATA
        self.assertEqual(Account.objects.filter(tenant=tenant).count(), len(COA_DATA))

    def test_accounting_firm_unaffected(self):
        from tenants.company_templates import ACCOUNTING_FIRM_COA

        user = User.objects.create_user(username="cb-firm-guard", password="x")
        tenant = create_company("مكتب محاسبة بعد #81", user, template="accounting_firm")
        codes = set(Account.objects.filter(tenant=tenant).values_list("code", flat=True))
        self.assertEqual(codes, {row[0] for row in ACCOUNTING_FIRM_COA})


class ClientBookAccountantPortalLicenseTest(APITestCase):
    """ISSUE #87 (مراجعة) — شاشة «الوضع المالي» تُردّ 404 بلا هذا الترخيص، وكانت
    شاشة بداية `client_book` معطوبة من أول يوم لأن `create_company` لم يكن
    يزرعه. `general` و`accounting_firm` لا يُلمَسان (اللوحة الأخيرة هوياتيّة
    النطاق ولا تمرّ بـ`guard_module_surface` أصلاً)."""

    def _auth(self, tenant):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(tenant.TenantID)}

    def setUp(self):
        self.user = User.objects.create_user(username="cb-license", password="x")

    def test_client_book_licenses_accountant_portal_on_creation(self):
        from core.modules import module_enabled

        tenant = create_company("دفتر عميل مرخَّص", self.user, template="client_book")
        self.assertTrue(module_enabled(tenant, "accountant_portal"))

    def test_financial_position_endpoints_return_200_not_404(self):
        tenant = create_company("دفتر عميل — نقاط الوضع المالي", self.user, template="client_book")
        headers = self._auth(tenant)
        res = self.client.get(
            "/api/accountant/client/summary/?from=2026-01-01&to=2026-01-31", **headers)
        self.assertEqual(res.status_code, 200, res.content)
        res = self.client.get("/api/accountant/client/trend/?months=6", **headers)
        self.assertEqual(res.status_code, 200, res.content)

    def test_general_is_not_licensed(self):
        from core.modules import module_enabled

        tenant = create_company("شركة عامة — بلا ترخيص", self.user)
        self.assertFalse(module_enabled(tenant, "accountant_portal"))

    def test_accounting_firm_is_not_licensed(self):
        """لوحة المكتب لا تحتاج الترخيص أصلاً (بلا `X-Tenant-Id`)، فلا داعي لزرعه هنا."""
        from core.modules import module_enabled

        tenant = create_company("مكتب محاسبة — بلا ترخيص إضافي", self.user, template="accounting_firm")
        self.assertFalse(module_enabled(tenant, "accountant_portal"))

    def test_switching_template_to_client_book_does_not_retroactively_license(self):
        """نقطة زرعٍ واحدة (القرار 8 في #46) — `switch_company_template` لا
        تمنح تراخيص وحدات، فدفترٌ حوّل قالبه لاحقاً يبقى غير مرخَّص حتى يُفعَّل
        يدوياً من لوحة المنصة."""
        from core.modules import module_enabled
        from tenants.services import switch_company_template

        tenant = create_company("شركة تبدّل قالبها", self.user)
        self.assertFalse(module_enabled(tenant, "accountant_portal"))
        switch_company_template(tenant, "client_book")
        self.assertFalse(module_enabled(tenant, "accountant_portal"))
