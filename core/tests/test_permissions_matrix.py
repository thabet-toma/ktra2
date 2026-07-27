"""T-PERM — محرّك الصلاحيات: كتالوج واحد + مصفوفة افتراضية لكل دور + تجاوزات
لكل شركة، مفروضة على الخادم (لا على الواجهة فقط).

السؤال الذي يجيب عنه هذا الملف: «مَن يقدر يتراجع عن الترحيل ومَن لا؟»
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.access import (
    PERMISSIONS,
    ROLE_DEFAULTS,
    permission_keys,
    user_has_perm,
    user_permissions,
    user_tenant_role,
)
from partners.models import Partner
from tenants.models import RolePermission, UserCompanyMembership
from tenants.services import create_company


class PermissionCatalogTest(APITestCase):
    def test_catalog_entries_are_well_formed(self):
        keys = permission_keys()
        assert len(keys) == len(PERMISSIONS)  # لا تكرار
        for p in PERMISSIONS:
            assert p["key"] and p["label"] and p["group"], p

    def test_role_defaults_reference_known_keys(self):
        keys = permission_keys()
        for role, granted in ROLE_DEFAULTS.items():
            if granted == "*":
                continue
            unknown = set(granted) - keys
            assert not unknown, f"{role} يمنح مفاتيح غير موجودة: {unknown}"


class RoleDefaultsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="perm-boss", password="x")
        cls.seller = User.objects.create_user(username="perm-seller", password="x")
        cls.buyer = User.objects.create_user(username="perm-buyer", password="x")
        cls.watcher = User.objects.create_user(username="perm-watcher", password="x")
        cls.tenant = create_company("شركة الصلاحيات", cls.boss)
        for user, role in ((cls.seller, "sales"), (cls.buyer, "procurement"),
                           (cls.watcher, "viewer")):
            UserCompanyMembership.objects.create(user=user, tenant=cls.tenant, role=role)

    def test_manager_holds_every_permission(self):
        assert user_permissions(self.boss, self.tenant) == permission_keys()
        assert user_tenant_role(self.boss, self.tenant) == "manager"

    def test_sales_employee_posts_but_cannot_unpost(self):
        """طلب المالك الصريح: موظف المبيعات يرحّل ولا يتراجع عن الترحيل."""
        assert user_has_perm(self.seller, self.tenant, "sales.invoice.post")
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.delete")

    def test_sales_employee_has_no_purchase_side(self):
        assert not user_has_perm(self.seller, self.tenant, "purchase.invoice.create")
        assert not user_has_perm(self.seller, self.tenant, "purchase.invoice.unpost")

    def test_procurement_employee_mirrors_on_the_purchase_side(self):
        assert user_has_perm(self.buyer, self.tenant, "purchase.invoice.post")
        assert not user_has_perm(self.buyer, self.tenant, "purchase.invoice.unpost")
        assert not user_has_perm(self.buyer, self.tenant, "sales.invoice.create")

    def test_viewer_holds_no_write_permission(self):
        perms = user_permissions(self.watcher, self.tenant)
        assert not any(
            k.endswith((".create", ".edit", ".delete", ".post", ".unpost", ".manage"))
            for k in perms
        ), perms

    def test_nobody_but_manager_manages_permissions(self):
        assert user_has_perm(self.boss, self.tenant, "admin.permissions.manage")
        for u in (self.seller, self.buyer, self.watcher):
            assert not user_has_perm(u, self.tenant, "admin.permissions.manage")


class RoleOverrideTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="ovr-boss", password="x")
        cls.seller = User.objects.create_user(username="ovr-seller", password="x")
        cls.tenant = create_company("شركة التجاوزات", cls.boss)
        cls.other = create_company("شركة أخرى", cls.boss)
        UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")
        UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.other, role="sales")

    def test_grant_override_adds_permission_for_that_company_only(self):
        RolePermission.objects.create(
            tenant=self.tenant, role="sales",
            permission_key="sales.invoice.unpost", allowed=True)
        assert user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")
        # لا تسرّب لشركة أخرى — الصلاحيات مُنطاقة بالشركة
        assert not user_has_perm(self.seller, self.other, "sales.invoice.unpost")

    def test_deny_override_removes_a_default_permission(self):
        RolePermission.objects.create(
            tenant=self.tenant, role="sales",
            permission_key="sales.invoice.post", allowed=False)
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.post")

    def test_manager_cannot_be_stripped_by_an_override(self):
        """المدير يبقى مالك الشركة — لا يُقفل نفسه خارج نظامه."""
        RolePermission.objects.create(
            tenant=self.tenant, role="manager",
            permission_key="admin.permissions.manage", allowed=False)
        assert user_has_perm(self.boss, self.tenant, "admin.permissions.manage")


class PermissionsApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="api-boss", password="x")
        cls.seller = User.objects.create_user(username="api-seller", password="x")
        cls.tenant = create_company("شركة منفذ الصلاحيات", cls.boss)
        UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_me_returns_role_and_effective_permissions(self):
        res = self.client.get("/api/permissions/me/", **self._as(self.seller))
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["role"] == "sales"
        assert "sales.invoice.post" in body["permissions"]
        assert "sales.invoice.unpost" not in body["permissions"]

    def test_matrix_is_manager_only(self):
        assert self.client.get(
            "/api/permissions/matrix/", **self._as(self.seller)).status_code == 403
        res = self.client.get("/api/permissions/matrix/", **self._as(self.boss))
        assert res.status_code == 200, res.content
        body = res.json()
        assert len(body["permissions"]) == len(PERMISSIONS)
        assert body["matrix"]["sales"]["sales.invoice.unpost"] is False
        assert body["matrix"]["manager"]["sales.invoice.unpost"] is True

    def test_manager_edits_the_matrix_and_resets_it(self):
        h = self._as(self.boss)
        res = self.client.put(
            "/api/permissions/matrix/",
            {"changes": [
                {"role": "sales", "permission_key": "sales.invoice.unpost", "allowed": True},
            ]},
            format="json", **h)
        assert res.status_code == 200, res.content
        assert res.json()["matrix"]["sales"]["sales.invoice.unpost"] is True
        assert user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")

        res = self.client.post("/api/permissions/matrix/reset/", {}, format="json", **h)
        assert res.status_code == 200, res.content
        assert RolePermission.objects.filter(tenant=self.tenant).count() == 0
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")

    def test_matrix_rejects_unknown_permission_key(self):
        res = self.client.put(
            "/api/permissions/matrix/",
            {"changes": [{"role": "sales", "permission_key": "made.up.key", "allowed": True}]},
            format="json", **self._as(self.boss))
        assert res.status_code == 400, res.content


class InvoiceSaveAndPostPermissionTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from inventory.models import Product
        from sales.services import get_or_create_sales_settings
        from tenants.models import Currency

        cls.boss = User.objects.create_user(username="sap-boss", password="x")
        cls.staff = User.objects.create_user(username="sap-staff", password="x")
        cls.tenant = create_company("شركة حفظ وترحيل", cls.boss)
        UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role="staff")
        cls.currency = Currency.objects.create(
            Code="SAP-ILS", Name="شيكل حفظ وترحيل", IsBaseCurrency=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل حفظ وترحيل", partner_type="Customer")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SAP-1", name_ar="صنف", quantity_on_hand=10, avg_cost=1)
        settings = get_or_create_sales_settings(cls.tenant)
        settings.auto_post_invoices = True
        settings.save(update_fields=["auto_post_invoices"])

    def _as_staff(self):
        self.client.force_authenticate(user=self.staff)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _body(self, *, auto_post):
        return {
            "customer": self.customer.id,
            "currency": self.currency.CurrencyID,
            "invoice_date": "2026-07-01",
            "auto_post": auto_post,
            "lines": [{
                "product": self.product.id,
                "quantity": "1",
                "unit_price": "10",
                "line_discount": "0",
            }],
        }

    def test_save_explicitly_stays_draft_even_when_company_auto_post_is_enabled(self):
        res = self.client.post(
            "/api/sales/invoices/", self._body(auto_post=False),
            format="json", **self._as_staff())
        assert res.status_code == 201, res.content
        assert res.json()["status"] == "draft"

    def test_explicit_save_and_post_is_blocked_without_post_permission(self):
        res = self.client.post(
            "/api/sales/invoices/", self._body(auto_post=True),
            format="json", **self._as_staff())
        assert res.status_code == 403, res.content


class UnpostEnforcementTest(APITestCase):
    """الإنفاذ الحقيقي على الخادم — لا حجب بالواجهة وحدها."""

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from sales.models import SalesInvoice
        from tenants.models import Currency

        cls.boss = User.objects.create_user(username="enf-boss", password="x")
        cls.seller = User.objects.create_user(username="enf-seller", password="x")
        cls.tenant = create_company("شركة الإنفاذ", cls.boss)
        UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")
        ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer")
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-PERM-1", customer=customer,
            currency=ils, invoice_date="2026-07-01", grand_total=Decimal("100"),
            status=SalesInvoice.STATUS_POSTED,
        )

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_sales_employee_is_blocked_from_unposting(self):
        res = self.client.post(
            f"/api/sales/invoices/{self.invoice.id}/unpost/", {}, format="json",
            **self._as(self.seller))
        assert res.status_code == 403, res.content

    def test_manager_is_not_blocked_by_permissions(self):
        res = self.client.post(
            f"/api/sales/invoices/{self.invoice.id}/unpost/", {}, format="json",
            **self._as(self.boss))
        assert res.status_code != 403, res.content

    def test_granting_the_permission_unblocks_the_sales_employee(self):
        RolePermission.objects.create(
            tenant=self.tenant, role="sales",
            permission_key="sales.invoice.unpost", allowed=True)
        res = self.client.post(
            f"/api/sales/invoices/{self.invoice.id}/unpost/", {}, format="json",
            **self._as(self.seller))
        assert res.status_code != 403, res.content
