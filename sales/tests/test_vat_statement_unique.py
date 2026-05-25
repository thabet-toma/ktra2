"""P-H-6: VatStatement uniqueness constraint per (tenant, period_from, period_to)."""
from django.db import IntegrityError
from django.test import TestCase

from sales.models import VatStatement
from tenants.models import Tenant


class VatStatementUniqueTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=140, CompanyName="VAT Uniq")

    def test_unique_period_constraint(self):
        VatStatement.objects.create(
            tenant=self.tenant,
            statement_number="VS-001",
            period_from="2026-01-01",
            period_to="2026-01-31",
        )
        with self.assertRaises(IntegrityError):
            VatStatement.objects.create(
                tenant=self.tenant,
                statement_number="VS-002",
                period_from="2026-01-01",
                period_to="2026-01-31",
            )

    def test_different_tenant_same_period_allowed(self):
        other_tenant = Tenant.objects.create(TenantID=141, CompanyName="Other Co")
        VatStatement.objects.create(
            tenant=self.tenant,
            statement_number="VS-001",
            period_from="2026-01-01",
            period_to="2026-01-31",
        )
        try:
            VatStatement.objects.create(
                tenant=other_tenant,
                statement_number="VS-001",
                period_from="2026-01-01",
                period_to="2026-01-31",
            )
        except IntegrityError:
            self.fail("Different tenant same period should be allowed")

    def test_same_tenant_different_period_allowed(self):
        VatStatement.objects.create(
            tenant=self.tenant,
            statement_number="VS-001",
            period_from="2026-01-01",
            period_to="2026-01-31",
        )
        try:
            VatStatement.objects.create(
                tenant=self.tenant,
                statement_number="VS-002",
                period_from="2026-02-01",
                period_to="2026-02-28",
            )
        except IntegrityError:
            self.fail("Same tenant different period should be allowed")
