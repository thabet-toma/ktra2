"""T-PLANLIMITS: حدود الخطة — الافتراضي، التجاوز، الحارس عند الإنشاء."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import TenantLimit
from core.plans import (
    LIMITS,
    check_limit,
    current_usage,
    invalidate_limit_cache,
    limit_rows,
    limit_value,
    plan_default,
)
from inventory.models import Warehouse
from tenants.models import Tenant, UserCompanyMembership


class PlanLimitEngineTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.basic = Tenant.objects.create(
            CompanyName="شركة أساسية", SubscriptionPlan="Basic", Status="Active",
        )
        cls.enterprise = Tenant.objects.create(
            CompanyName="شركة مؤسسية", SubscriptionPlan="Enterprise", Status="Active",
        )

    def setUp(self):
        invalidate_limit_cache(self.basic.pk)
        invalidate_limit_cache(self.enterprise.pk)

    def test_plan_default_drives_the_effective_limit(self):
        self.assertEqual(
            limit_value(self.basic, "inventory.warehouses"),
            plan_default("Basic", "inventory.warehouses"),
        )
        self.assertIsNone(limit_value(self.enterprise, "inventory.warehouses"))

    def test_company_override_beats_plan_default_and_delete_restores_it(self):
        TenantLimit.objects.create(
            tenant=self.basic, limit_key="inventory.warehouses", max_value=4,
        )
        invalidate_limit_cache(self.basic.pk)
        self.assertEqual(limit_value(self.basic, "inventory.warehouses"), 4)

        TenantLimit.objects.filter(tenant=self.basic).delete()
        invalidate_limit_cache(self.basic.pk)
        self.assertEqual(
            limit_value(self.basic, "inventory.warehouses"),
            plan_default("Basic", "inventory.warehouses"),
        )

    def test_null_override_means_unlimited_not_zero(self):
        TenantLimit.objects.create(
            tenant=self.basic, limit_key="inventory.warehouses", max_value=None,
        )
        invalidate_limit_cache(self.basic.pk)
        self.assertIsNone(limit_value(self.basic, "inventory.warehouses"))
        self.assertIsNone(check_limit(self.basic, "inventory.warehouses"))

    def test_check_limit_blocks_only_when_the_next_one_exceeds(self):
        TenantLimit.objects.create(
            tenant=self.basic, limit_key="inventory.warehouses", max_value=2,
        )
        invalidate_limit_cache(self.basic.pk)
        Warehouse.objects.create(tenant=self.basic, name="مستودع 1")
        self.assertIsNone(check_limit(self.basic, "inventory.warehouses"))

        Warehouse.objects.create(tenant=self.basic, name="مستودع 2")
        message = check_limit(self.basic, "inventory.warehouses")
        self.assertIsNotNone(message)
        self.assertIn("المستودعات", message)

    def test_usage_counts_only_the_same_company(self):
        Warehouse.objects.create(tenant=self.basic, name="مستودع الشركة")
        Warehouse.objects.create(tenant=self.enterprise, name="مستودع شركة أخرى")
        self.assertEqual(current_usage(self.basic, "inventory.warehouses"), 1)

    def test_limit_rows_cover_every_declared_limit(self):
        rows = {row["key"] for row in limit_rows(self.basic)}
        self.assertEqual(rows, set(LIMITS))


class PlanLimitGuardTest(APITestCase):
    """الحارس على نقاط الإنشاء الحقيقية عبر الـAPI."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة الحدود", SubscriptionPlan="Basic", Status="Active",
        )
        cls.manager = User.objects.create_user(username="limit-manager", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.tenant, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.tenant.pk)
        self.client.force_authenticate(user=self.manager)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_warehouse_creation_is_blocked_at_the_limit(self):
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="inventory.warehouses", max_value=1,
        )
        invalidate_limit_cache(self.tenant.pk)

        first = self.client.post(
            "/api/inventory/warehouses/", {"name": "الرئيسي"}, format="json",
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            "/api/inventory/warehouses/", {"name": "الثاني"}, format="json",
        )
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("plan_limit", second.data)
        self.assertEqual(Warehouse.objects.filter(tenant=self.tenant).count(), 1)

    def test_sales_invoice_creation_is_blocked_at_the_monthly_limit(self):
        """حدّ فواتير البيع الشهري — الطلب المُتخطّي لا يُحفظ أصلاً."""
        from inventory.models import Product
        from partners.models import Partner
        from sales.models import SalesInvoice
        from tenants.models import Currency

        currency = Currency.objects.create(
            Code="LIM", Name="عملة الحدود", IsBaseCurrency=False,
        )
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل الحدود", partner_type="Customer",
        )
        product = Product.objects.create(
            tenant=self.tenant, sku="LIMIT-1", name_ar="منتج الحدود",
            quantity_on_hand=10, avg_cost=1,
        )
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="sales.invoices", max_value=1,
        )
        invalidate_limit_cache(self.tenant.pk)
        body = {
            "customer": customer.id,
            "currency": currency.CurrencyID,
            "invoice_date": "2026-07-01",
            "auto_post": False,
            "lines": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "10",
                "line_discount": "0",
            }],
        }

        first = self.client.post("/api/sales/invoices/", body, format="json")
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post("/api/sales/invoices/", body, format="json")
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("plan_limit", second.data)
        self.assertEqual(SalesInvoice.objects.filter(tenant=self.tenant).count(), 1)

    def test_partner_creation_is_blocked_at_the_limit(self):
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="partners.records", max_value=0,
        )
        invalidate_limit_cache(self.tenant.pk)

        response = self.client.post(
            "/api/partners/",
            {"name": "عميل جديد", "partner_type": "Customer"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("plan_limit", response.data)


class PlatformLimitApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="limits-root", email="limits-root@example.com", password="x",
        )
        cls.member = User.objects.create_user(username="limits-member", password="x")
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة اللوحة", SubscriptionPlan="Basic", Status="Active",
        )
        UserCompanyMembership.objects.create(
            user=cls.member, tenant=cls.tenant, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.tenant.pk)

    def url(self):
        return f"/api/platform/companies/{self.tenant.pk}/limits/"

    def test_company_manager_is_denied(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_super_admin_reads_defaults_with_usage(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["plan"], "Basic")
        rows = {row["key"]: row for row in response.data["results"]}
        self.assertEqual(set(rows), set(LIMITS))
        warehouses = rows["inventory.warehouses"]
        self.assertEqual(
            warehouses["plan_default"], plan_default("Basic", "inventory.warehouses"),
        )
        self.assertFalse(warehouses["has_override"])
        self.assertEqual(warehouses["usage"], 0)

    def test_super_admin_sets_then_resets_an_override(self):
        self.client.force_authenticate(self.superuser)

        setting = self.client.post(
            self.url(),
            {"limit_key": "company.members", "max_value": 25, "note": "اتفاق خاص"},
            format="json",
        )
        self.assertEqual(setting.status_code, 200, setting.content)
        self.assertEqual(limit_value(self.tenant, "company.members"), 25)

        reset = self.client.post(
            self.url(), {"limit_key": "company.members", "reset": True}, format="json",
        )
        self.assertEqual(reset.status_code, 200, reset.content)
        self.assertFalse(
            TenantLimit.objects.filter(
                tenant=self.tenant, limit_key="company.members",
            ).exists()
        )
        self.assertEqual(
            limit_value(self.tenant, "company.members"),
            plan_default("Basic", "company.members"),
        )

    def test_unknown_limit_key_is_rejected(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            self.url(), {"limit_key": "made.up", "max_value": 5}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
