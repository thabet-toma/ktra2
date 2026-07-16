"""شجرة الحسابات تجمع الشريك المرتبط دفعة واحدة وبنطاق الشركة."""
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account
from partners.models import Partner
from tenants.models import Tenant, UserCompanyMembership


class AccountListPerformanceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="account_list_perf", password="x")
        cls.tenant_two = Tenant.objects.create(CompanyName="شركة حسابين")
        cls.tenant_six = Tenant.objects.create(CompanyName="شركة ستة حسابات")
        cls.other_tenant = Tenant.objects.create(CompanyName="شركة حسابات أخرى")
        for tenant in (cls.tenant_two, cls.tenant_six):
            UserCompanyMembership.objects.create(
                user=cls.owner, tenant=tenant, role="manager",
            )
        for tenant, count in ((cls.tenant_two, 2), (cls.tenant_six, 6)):
            for i in range(count):
                account = Account.objects.create(
                    tenant=tenant, code=f"A-{tenant.pk}-{i}",
                    name=f"حساب {i}", account_type="Asset",
                )
                Partner.objects.create(
                    tenant=tenant, name=f"شريك {tenant.pk}-{i}",
                    legal_name=f"قانوني {tenant.pk}-{i}", partner_type="Supplier",
                    linked_account=account,
                )

        cls.first_six_account = Account.objects.filter(
            tenant=cls.tenant_six,
        ).order_by("id").first()
        Partner.objects.create(
            tenant=cls.other_tenant, name="شريك أجنبي",
            partner_type="Supplier", linked_account=cls.first_six_account,
        )

    def _list(self, tenant):
        self.client.force_authenticate(user=self.owner)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                "/api/accounting/accounts/",
                HTTP_X_TENANT_ID=str(tenant.TenantID),
            )
            assert response.status_code == 200, response.content[:300]
        return response.json(), len(ctx.captured_queries)

    def test_linked_partner_query_count_is_constant_and_tenant_scoped(self):
        two_rows, q_two = self._list(self.tenant_two)
        six_rows, q_six = self._list(self.tenant_six)

        assert len(two_rows) == 2
        assert len(six_rows) == 6
        assert q_six == q_two
        assert all(row["linked_partner"] for row in six_rows)
        assert all(
            row["linked_partner"]["trade_name"] != "شريك أجنبي"
            for row in six_rows
        )
