"""ISSUE #51 — القناع الحيّ: قالب الشركة يخفي مسارات كاملة (404) لا واجهة فقط.

الملاحظة على الأثر — كود الاستجابة على `X-Tenant-Id` فعلي — لا على استدعاء
`TemplateSurfacePermission` أو `template_hides_path` مباشرة.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from tenants.services import create_company


class AccountingFirmMaskedApiTest(APITestCase):
    """شركة `accounting_firm`: نقاط API المخزون واللوجستيات والمتجر تردّ 404."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="firm-mask", password="x")
        cls.tenant = create_company(
            "مكتب محاسبة مقنَّع", cls.user, template="accounting_firm")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_inventory_products_endpoint_is_404(self):
        res = self.client.get("/api/inventory/products/", **self._auth())
        self.assertEqual(res.status_code, 404, res.content)

    def test_inventory_warehouses_endpoint_is_404(self):
        res = self.client.get("/api/inventory/warehouses/", **self._auth())
        self.assertEqual(res.status_code, 404, res.content)

    def test_logistics_deals_endpoint_is_404(self):
        res = self.client.get("/api/logistics/deals/", **self._auth())
        self.assertEqual(res.status_code, 404, res.content)

    def test_purchase_flows_under_logistics_are_404(self):
        for path in (
            "/api/logistics/purchase-invoices/",
            "/api/logistics/purchase-orders/",
            "/api/logistics/goods-receipts/",
            "/api/logistics/shipments/",
        ):
            with self.subTest(path=path):
                res = self.client.get(path, **self._auth())
                self.assertEqual(res.status_code, 404, res.content)

    def test_supplier_payment_voucher_stays_open_under_logistics(self):
        """سند الصرف يعيش تحت `/api/logistics/` لأسبابٍ تاريخية، والتذكرة
        تُبقي «سندات القبض والصرف» صراحةً — فقناعٌ ببادئة `/api/logistics/`
        كاملةً كان يمنع المكتب من الدفع لأحد، ويقطع الطريق على تسديد ذمّة
        `2101` التي يفتحها سند المصروف."""
        res = self.client.get("/api/logistics/supplier-payments/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)

    def test_store_admin_settings_endpoint_is_404(self):
        res = self.client.get("/api/store/admin/settings/", **self._auth())
        self.assertEqual(res.status_code, 404, res.content)

    def test_unrelated_endpoints_stay_open(self):
        """القناع طرحيٌّ بمسارات مسمّاة — لا يعمّ ما لم يُذكر (المحاسبة والمبيعات والشركاء)."""
        for path in ("/api/accounting/accounts/", "/api/sales/invoices/", "/api/partners/"):
            with self.subTest(path=path):
                res = self.client.get(path, **self._auth())
                self.assertNotEqual(res.status_code, 404, res.content)

    def test_permissions_me_reports_the_template(self):
        res = self.client.get("/api/permissions/me/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["template"], "accounting_firm")

    def test_mask_holds_when_the_tenant_header_is_omitted(self):
        """حذف `X-Tenant-Id` لا يفتح المسار — هذا هو ثقب الـ`curl` بعينه.

        `core/tenant_utils.py` (`get_tenant`) تحلّ الشركة من ثلاثة مصادر لا
        مصدرٍ واحد: الترويسة، ثم شركة المستخدم الافتراضية، ثم النشر أحادي
        الشركة. فحارسٌ يكتفي بغياب الترويسة ليمرّر الطلب يُفتَح بحذفها بينما
        المنظر داخل العرض يحلّ الشركة ويخدم البيانات.
        """
        from core.tenant_utils import invalidate_tenant_cache
        invalidate_tenant_cache()  # شركةٌ واحدة في هذا الاختبار ⇒ حلٌّ تلقائي
        self.client.force_authenticate(user=self.user)
        res = self.client.get("/api/inventory/products/")
        self.assertEqual(res.status_code, 404, res.content)


class GeneralTemplateApiRegressionTest(APITestCase):
    """شركة `general`: صفر تغيير — نفس النقاط تعمل كما اليوم بلا حجب."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="gen-mask", password="x")
        cls.tenant = create_company("شركة عامة غير مقنَّعة", cls.user)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_inventory_products_endpoint_is_not_masked(self):
        res = self.client.get("/api/inventory/products/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)

    def test_logistics_deals_endpoint_is_not_masked(self):
        res = self.client.get("/api/logistics/deals/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)

    def test_store_admin_settings_endpoint_is_not_masked(self):
        res = self.client.get("/api/store/admin/settings/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)

    def test_permissions_me_reports_general_template(self):
        res = self.client.get("/api/permissions/me/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["template"], "general")
