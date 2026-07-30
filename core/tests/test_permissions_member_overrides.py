"""T-PERM المرحلة 2 (البند 3) — تجاوز الصلاحيات على مستوى **العضو** فوق دوره.

الترتيب: افتراضي الدور ← تجاوز الدور (للشركة) ← تجاوز العضو (الأعلى أولوية).
المدير يبقى محصّناً في كل الطبقات.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.access import permission_keys, user_has_perm, user_permissions
from tenants.models import MemberPermission, RolePermission, UserCompanyMembership
from tenants.services import create_company


class MemberOverrideTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="mo-boss", password="x")
        cls.seller = User.objects.create_user(username="mo-seller", password="x")
        cls.seller2 = User.objects.create_user(username="mo-seller2", password="x")
        cls.tenant = create_company("شركة تجاوز العضو", cls.boss)
        cls.m1 = UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")
        cls.m2 = UserCompanyMembership.objects.create(
            user=cls.seller2, tenant=cls.tenant, role="sales")

    def test_member_grant_beats_role_default(self):
        MemberPermission.objects.create(
            membership=self.m1, permission_key="sales.invoice.unpost", allowed=True)
        assert user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")
        # زميله بنفس الدور لا يتأثّر — التجاوز فردي
        assert not user_has_perm(self.seller2, self.tenant, "sales.invoice.unpost")

    def test_member_deny_beats_role_grant(self):
        RolePermission.objects.create(
            tenant=self.tenant, role="sales",
            permission_key="sales.invoice.unpost", allowed=True)
        MemberPermission.objects.create(
            membership=self.m1, permission_key="sales.invoice.unpost", allowed=False)
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")
        assert user_has_perm(self.seller2, self.tenant, "sales.invoice.unpost")

    def test_member_override_of_the_manager_is_ignored(self):
        boss_m = UserCompanyMembership.objects.get(user=self.boss, tenant=self.tenant)
        MemberPermission.objects.create(
            membership=boss_m, permission_key="sales.invoice.unpost", allowed=False)
        assert user_has_perm(self.boss, self.tenant, "sales.invoice.unpost")

    def test_unknown_key_in_overrides_is_ignored(self):
        MemberPermission.objects.create(
            membership=self.m1, permission_key="made.up.key", allowed=True)
        assert "made.up.key" not in user_permissions(self.seller, self.tenant)


class MemberPermissionsApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="mapi-boss", password="x")
        cls.seller = User.objects.create_user(
            username="mapi-seller", password="x", first_name="سائد")
        cls.tenant = create_company("شركة منفذ العضو", cls.boss)
        cls.m = UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_members_listing_is_manager_only(self):
        assert self.client.get(
            "/api/permissions/members/", **self._as(self.seller)).status_code == 403
        res = self.client.get("/api/permissions/members/", **self._as(self.boss))
        assert res.status_code == 200, res.content
        rows = {r["membership_id"]: r for r in res.json()}
        assert rows[self.m.id]["role"] == "sales"
        assert rows[self.m.id]["overrides"] == {}
        assert "sales.invoice.post" in rows[self.m.id]["effective"]

    def test_manager_grants_then_clears_a_member_override(self):
        h = self._as(self.boss)
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "changes": [
                {"permission_key": "sales.invoice.unpost", "allowed": True}]},
            format="json", **h)
        assert res.status_code == 200, res.content
        assert res.json()["overrides"] == {"sales.invoice.unpost": True}
        assert user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")

        # allowed=null ⇒ حذف التجاوز والعودة لافتراضي الدور
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "changes": [
                {"permission_key": "sales.invoice.unpost", "allowed": None}]},
            format="json", **h)
        assert res.status_code == 200, res.content
        assert res.json()["overrides"] == {}
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")

    def test_manager_membership_cannot_be_edited(self):
        boss_m = UserCompanyMembership.objects.get(user=self.boss, tenant=self.tenant)
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": boss_m.id, "changes": [
                {"permission_key": "sales.invoice.unpost", "allowed": False}]},
            format="json", **self._as(self.boss))
        assert res.status_code == 400, res.content

    def test_membership_from_another_company_is_rejected(self):
        other = create_company("شركة غريبة", self.boss)
        stranger = UserCompanyMembership.objects.create(
            user=self.seller, tenant=other, role="sales")
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": stranger.id, "changes": [
                {"permission_key": "sales.invoice.unpost", "allowed": True}]},
            format="json", **self._as(self.boss))
        assert res.status_code == 400, res.content


class MemberGrantAllTest(APITestCase):
    """T-PERMBOX: خانة «كل الصلاحيات» لعضو بعينه — منح شامل بلا تبديل دوره."""

    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="mall-boss", password="x")
        cls.seller = User.objects.create_user(username="mall-seller", password="x")
        cls.tenant = create_company("شركة منح الكل", cls.boss)
        cls.m = UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_grant_all_gives_the_member_every_permission(self):
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "grant_all": True},
            format="json", **self._as(self.boss))
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["grant_all"] is True
        assert set(body["effective"]) == set(permission_keys())
        assert user_permissions(self.seller, self.tenant) == permission_keys()
        # الدور لم يتبدّل — المنح فرديّ لا ترقية دور
        self.m.refresh_from_db()
        assert self.m.role == "sales"

    def test_clearing_grant_all_returns_the_member_to_role_defaults(self):
        h = self._as(self.boss)
        self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "grant_all": True},
            format="json", **h)
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "grant_all": False},
            format="json", **h)
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["grant_all"] is False
        assert body["overrides"] == {}
        assert MemberPermission.objects.filter(membership=self.m).count() == 0
        assert not user_has_perm(self.seller, self.tenant, "sales.invoice.unpost")

    def test_members_listing_reports_grant_all_state(self):
        h = self._as(self.boss)
        rows = {r["membership_id"]: r for r in self.client.get(
            "/api/permissions/members/", **h).json()}
        assert rows[self.m.id]["grant_all"] is False
        self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "grant_all": True},
            format="json", **h)
        rows = {r["membership_id"]: r for r in self.client.get(
            "/api/permissions/members/", **h).json()}
        assert rows[self.m.id]["grant_all"] is True

    def test_grant_all_is_rejected_for_a_manager_membership(self):
        boss_m = UserCompanyMembership.objects.get(user=self.boss, tenant=self.tenant)
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": boss_m.id, "grant_all": True},
            format="json", **self._as(self.boss))
        assert res.status_code == 400, res.content

    def test_grant_all_is_manager_only(self):
        res = self.client.put(
            "/api/permissions/member/",
            {"membership_id": self.m.id, "grant_all": True},
            format="json", **self._as(self.seller))
        assert res.status_code == 403, res.content


class MemberOverrideEnforcementTest(APITestCase):
    """التجاوز الفردي يفتح/يغلق المنفذ الحقيقي لا الواجهة فقط."""

    @classmethod
    def setUpTestData(cls):
        from decimal import Decimal

        from partners.models import Partner
        from sales.models import SalesInvoice
        from tenants.models import Currency

        cls.boss = User.objects.create_user(username="moe-boss", password="x")
        cls.seller = User.objects.create_user(username="moe-seller", password="x")
        cls.tenant = create_company("شركة إنفاذ العضو", cls.boss)
        cls.m = UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")
        ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer")
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-MO-1", customer=customer,
            currency=ils, invoice_date="2026-07-01", grand_total=Decimal("100"),
            status=SalesInvoice.STATUS_POSTED,
        )

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_individual_grant_unblocks_only_that_member(self):
        url = f"/api/sales/invoices/{self.invoice.id}/unpost/"
        assert self.client.post(
            url, {}, format="json", **self._as(self.seller)).status_code == 403
        MemberPermission.objects.create(
            membership=self.m, permission_key="sales.invoice.unpost", allowed=True)
        assert self.client.post(
            url, {}, format="json", **self._as(self.seller)).status_code != 403
