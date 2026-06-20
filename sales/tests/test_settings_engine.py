"""Phase 8 (T-S2/T-S3): محرّك الإعدادات — حقل تنبيه التكرار + استعادة خريطة القيد.

`create_company` يبذر شجرة حسابات احترافية تلقائياً، فنعتمد عليها بدل إنشاء حسابات.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from sales.models import SalesSettings
from tenants.models import Currency
from tenants.services import create_company


class SettingsEngineTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="seteng", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الإعدادات", cls.user)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_warn_on_duplicate_defaults_true_and_is_exposed(self):
        res = self.client.get("/api/sales/settings/current/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["warn_on_duplicate_item"])

    def test_warn_on_duplicate_can_be_patched(self):
        res = self.client.patch(
            "/api/sales/settings/current/",
            {"warn_on_duplicate_item": False}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()["warn_on_duplicate_item"])
        self.assertFalse(SalesSettings.objects.get(tenant=self.tenant).warn_on_duplicate_item)

    def test_restore_defaults_maps_accounts_by_type(self):
        res = self.client.post("/api/sales/settings/restore-defaults/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        # كل الحسابات الأساسية أُعيد ضبطها (غير فارغة) ومن النوع الصحيح.
        for field, expected_type in [
            ("default_cash_account", "Asset"),
            ("default_revenue_account_product", "Revenue"),
            ("default_inventory_account", "Asset"),
            ("default_cogs_account", "Expense"),
        ]:
            self.assertIsNotNone(data[field], f"{field} لم يُحَل")
            acc = Account.objects.get(id=data[field])
            self.assertEqual(acc.account_type, expected_type, f"{field} → {acc.code} {acc.account_type}")
