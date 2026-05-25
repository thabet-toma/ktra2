"""P-H-7: Account overrides — product-level, category-level, and fallback chain."""
from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import Account
from inventory.services import _resolve_line_account
from tenants.models import Tenant


class AccountOverridesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=150, CompanyName="Ovrd Test")

    def _make_mock_product(self, override_field=None, override_value=None, cat_rev_acc=None):
        tid = self.tenant.TenantID
        product = MagicMock()
        product.tenant_id = tid
        product.sku = "OVR-PROD"
        product.name = "Override Product"
        if override_field and override_value:
            setattr(product, override_field, override_value)
        else:
            product.sale_account_override = None
            product.ending_inventory_account_override = None
            product.purchase_account_override = None
        if cat_rev_acc is not None:
            cat = MagicMock()
            cat.revenue_account = cat_rev_acc
            cat.cogs_account = None
            cat.inventory_account = None
        else:
            cat = MagicMock()
            cat.revenue_account = None
            cat.cogs_account = None
            cat.inventory_account = None
        product.category = cat
        return product

    def test_fallback_to_code_4101_for_revenue(self):
        Account.objects.create(
            tenant=self.tenant, code="4101", name="إيرادات مبيعات",
            account_type="Revenue", is_active=True,
        )
        product = self._make_mock_product()
        account = _resolve_line_account(product, "revenue", tenant_id=self.tenant.TenantID)
        self.assertEqual(account.code, "4101")

    def test_product_level_override_takes_priority(self):
        override = Account.objects.create(
            tenant=self.tenant, code="4105", name="إيرادات خاصة",
            account_type="Revenue", is_active=True,
        )
        Account.objects.create(
            tenant=self.tenant, code="4101", name="إيرادات مبيعات",
            account_type="Revenue", is_active=True,
        )
        product = self._make_mock_product("sale_account_override", override)
        account = _resolve_line_account(product, "revenue", tenant_id=self.tenant.TenantID)
        self.assertEqual(account.id, override.id)

    def test_purchase_account_override_active(self):
        override = Account.objects.create(
            tenant=self.tenant, code="1104", name="مخزون بضاعة",
            account_type="Asset", is_active=True,
        )
        product = self._make_mock_product("purchase_account_override", override)
        account = _resolve_line_account(product, "purchase", tenant_id=self.tenant.TenantID)
        self.assertEqual(account.id, override.id)

    def test_inventory_account_override(self):
        override = Account.objects.create(
            tenant=self.tenant, code="1104", name="مخزون بضاعة",
            account_type="Asset", is_active=True,
        )
        product = self._make_mock_product("ending_inventory_account_override", override)
        account = _resolve_line_account(product, "inventory", tenant_id=self.tenant.TenantID)
        self.assertEqual(account.id, override.id)

    def test_no_account_raises(self):
        product = self._make_mock_product()
        with self.assertRaises(ValidationError):
            _resolve_line_account(product, "revenue", tenant_id=self.tenant.TenantID)
