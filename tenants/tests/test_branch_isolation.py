"""task11 M4 — Branch feature: shared COA, isolated invoices/numbering/journals.

Pins the decisive definition:
  - Branch shares the parent company's chart of accounts (tenant-level).
  - Invoice sequences are independent per branch (TenantBook branch dimension).
  - Sales invoices are filtered by the active branch (X-Branch-Id).
  - A branch belonging to another company is rejected.
  - Branch creation is manager-only; main branch cannot be deactivated.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from sales.services import next_invoice_number
from tenants.models import Branch, Tenant, UserCompanyMembership
from tenants.services import create_branch, create_company


class BranchApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="mgr", password="x")
        cls.staff = User.objects.create_user(username="stf", password="x")
        cls.tenant = create_company("شركة الفروع", cls.manager)
        UserCompanyMembership.objects.create(user=cls.staff, tenant=cls.tenant, role="staff")

        cls.other_owner = User.objects.create_user(username="other", password="x")
        cls.other_tenant = create_company("شركة أخرى", cls.other_owner)

    def _as(self, user, tenant=None, branch=None):
        self.client.force_authenticate(user=user)
        self._headers = {
            "HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID),
            **({"HTTP_X_BRANCH_ID": str(branch.pk)} if branch else {}),
        }

    def test_company_creation_seeds_main_branch(self):
        main = Branch.objects.get(tenant=self.tenant, is_main=True)
        assert main.code == "MAIN"

    def test_manager_can_create_branch_staff_cannot(self):
        self._as(self.manager)
        res = self.client.post(
            "/api/tenants/branches/", {"name": "فرع نابلس", "code": "NAB"},
            format="json", **self._headers)
        assert res.status_code == 201, res.content

        self._as(self.staff)
        res = self.client.post(
            "/api/tenants/branches/", {"name": "فرع آخر", "code": "XX"},
            format="json", **self._headers)
        assert res.status_code == 403

    def test_branch_shares_parent_coa(self):
        branch = create_branch(self.tenant, "فرع جنين", "JEN")
        # No accounts were created for the branch — COA is tenant-level (shared)
        coa_count_before = Account.objects.filter(tenant=self.tenant).count()
        assert coa_count_before > 0
        assert not hasattr(branch, "accounts")  # no branch-level COA relation

    def test_invoice_numbering_independent_per_branch(self):
        b1 = create_branch(self.tenant, "فرع ١", "BR1")
        b2 = create_branch(self.tenant, "فرع ٢", "BR2")
        tid = self.tenant.TenantID

        n_company = next_invoice_number(tid)         # company-level sequence
        n_b1_first = next_invoice_number(tid, branch=b1)
        n_b2_first = next_invoice_number(tid, branch=b2)
        n_b1_second = next_invoice_number(tid, branch=b1)

        assert n_b1_first == f"SI-{tid}-BR1-1"
        assert n_b2_first == f"SI-{tid}-BR2-1"   # b2 starts at 1 — independent
        assert n_b1_second == f"SI-{tid}-BR1-2"  # b1 continues its own sequence
        assert n_company.startswith(f"SI-{tid}-") and "BR" not in n_company

    def test_foreign_branch_header_rejected(self):
        foreign_branch = Branch.objects.get(tenant=self.other_tenant, is_main=True)
        self._as(self.manager, branch=foreign_branch)
        res = self.client.get("/api/sales/invoices/", **self._headers)
        assert res.status_code == 403

    def test_main_branch_cannot_be_deactivated(self):
        main = Branch.objects.get(tenant=self.tenant, is_main=True)
        self._as(self.manager)
        res = self.client.delete(f"/api/tenants/branches/{main.pk}/", **self._headers)
        assert res.status_code == 400

    def test_branch_list_scoped_to_tenant(self):
        create_branch(self.tenant, "فرع ظاهر", "VIS")
        self._as(self.other_owner, tenant=self.other_tenant)
        res = self.client.get("/api/tenants/branches/", **self._headers)
        assert res.status_code == 200
        codes = [b["code"] for b in res.json()]
        assert "VIS" not in codes
        assert "MAIN" in codes
