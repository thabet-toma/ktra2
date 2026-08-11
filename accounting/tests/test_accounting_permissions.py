"""T-PERM المرحلة 2 (البند 2) — إنفاذ صلاحيات المحاسبة.

كانت مفاتيح `accounting.*` في الكتالوج بلا نقاط إنفاذ: أي عضو غير مستعرض كان
ينشئ قيداً يدوياً ويرحّله ويعكسه ويعبث بشجرة الحسابات وبالفترات المالية.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from tenants.models import UserCompanyMembership
from tenants.services import create_company


class AccountingPermissionsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="acc-boss", password="x")
        cls.seller = User.objects.create_user(username="acc-seller", password="x")
        cls.accountant = User.objects.create_user(username="acc-keeper", password="x")
        cls.tenant = create_company("شركة صلاحيات المحاسبة", cls.boss)
        UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")
        UserCompanyMembership.objects.create(
            user=cls.accountant, tenant=cls.tenant, role="accountant")

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── القيود اليدوية ──
    def test_sales_employee_cannot_touch_journals(self):
        h = self._as(self.seller)
        assert self.client.post(
            "/api/accounting/journals/", {"description": "قيد"}, format="json",
            **h).status_code == 403
        assert self.client.post(
            "/api/accounting/journals/1/post/", {}, format="json", **h).status_code == 403
        assert self.client.post(
            "/api/accounting/journals/1/reverse/", {}, format="json", **h).status_code == 403

    def test_accountant_is_not_blocked_from_journals(self):
        h = self._as(self.accountant)
        assert self.client.post(
            "/api/accounting/journals/1/post/", {}, format="json", **h).status_code != 403
        assert self.client.post(
            "/api/accounting/journals/1/reverse/", {}, format="json", **h).status_code != 403

    def test_journal_reading_stays_open_to_every_member(self):
        for user in (self.seller, self.accountant, self.boss):
            assert self.client.get(
                "/api/accounting/journals/", **self._as(user)).status_code == 200

    # ── شجرة الحسابات ──
    def test_sales_employee_cannot_manage_the_chart_of_accounts(self):
        res = self.client.post(
            "/api/accounting/accounts/",
            {"code": "9999", "name": "حساب", "account_type": "Asset"},
            format="json", **self._as(self.seller))
        assert res.status_code == 403

    def test_accountant_manages_the_chart_of_accounts(self):
        res = self.client.post(
            "/api/accounting/accounts/",
            {"code": "9998", "name": "حساب المحاسب", "account_type": "Asset"},
            format="json", **self._as(self.accountant))
        assert res.status_code in (200, 201), res.content

    # ── الفترات المالية والإغلاق ──
    def test_sales_employee_cannot_close_periods(self):
        h = self._as(self.seller)
        assert self.client.post(
            "/api/accounting/fiscal-periods/1/close/", {}, format="json",
            **h).status_code == 403
        assert self.client.post(
            "/api/accounting/fiscal-periods/year-end-close/", {}, format="json",
            **h).status_code == 403
