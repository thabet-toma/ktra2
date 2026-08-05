from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from rest_framework.test import APITestCase

from accountant_portal.audit import AUDIT_ACTION_CODES
from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    PortalSettings,
)
from accountant_portal.permissions import LEGAL_ACCOUNTANT_FORBIDDEN
from core.access import ROLE_DEFAULTS, role_default_permissions, user_permissions
from core.models import TenantModule
from core.modules import invalidate_module_cache
from core.tenant_utils import _validate_user_tenant_access, get_tenant
from tenants.models import MemberPermission, Tenant, UserCompanyMembership


LEGAL_ACCOUNTANT_DEFAULTS = {
    "sales.invoice.view",
    "purchase.invoice.view",
    "sales.customer.view",
    "purchase.supplier.view",
    "accounting.journal.view",
    "accounting.report.view",
    "tax.period.view",
    "tax.period.prepare",
    "review.query.create",
    "finance.export.package",
}


class AccountantPortalModelsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("external-accountant")
        self.tenant = Tenant.objects.create(CompanyName="شركة ألف")

    def test_profile_tax_registration_number_is_unique(self):
        AccountantProfile.objects.create(
            user=self.user,
            professional_type="accountant",
            tax_registration_number="TAX-100",
            business_address="رام الله",
        )
        other = User.objects.create_user("other-accountant")

        with self.assertRaises(IntegrityError), transaction.atomic():
            AccountantProfile.objects.create(
                user=other,
                professional_type="licensed_auditor",
                tax_registration_number="TAX-100",
                business_address="نابلس",
            )

    def test_profile_choices_reject_unknown_values(self):
        profile = AccountantProfile(
            user=self.user,
            professional_type="unknown",
            tax_registration_number="TAX-101",
            business_address="الخليل",
            verification_status="unknown",
        )

        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_engagement_is_unique_per_accountant_and_tenant(self):
        AccountantEngagement.objects.create(
            accountant=self.user,
            tenant=self.tenant,
            initiated_by="accountant",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            AccountantEngagement.objects.create(
                accountant=self.user,
                tenant=self.tenant,
                initiated_by="company",
            )

    def test_portal_settings_defaults_match_the_plan(self):
        settings = PortalSettings.objects.create(tenant=self.tenant)

        self.assertEqual(settings.tax_jurisdiction, "PS")
        self.assertFalse(settings.strict_invoice_field_validation)
        self.assertEqual(settings.clearance_mode, "manual")
        self.assertFalse(settings.is_israeli_registered_dealer)
        self.assertTrue(settings.require_reauth_for_sensitive)
        self.assertEqual(settings.reauth_window_minutes, 15)
        self.assertEqual(settings.engagement_retention_years, 5)
        # ق8 — المنح مسموح افتراضاً، والصلاحية نفسها غير ممنوحة لأي ارتباط.
        self.assertTrue(settings.allow_grant_cost_view)
        self.assertNotIn("inventory.cost.view", ROLE_DEFAULTS["legal_accountant"])
        self.assertEqual(settings.invitation_expiry_days, 14)
        self.assertEqual(settings.max_active_engagements, 0)
        self.assertTrue(settings.lock_blocks_posting)
        self.assertEqual(settings.default_grant_profile, "review_only")
        self.assertEqual(settings.tax_period_type, "monthly")
        self.assertEqual(settings.filing_due_days, 15)
        self.assertEqual(settings.input_vat_window_months, 6)
        self.assertFalse(settings.allow_accountant_reopen)
        self.assertEqual(settings.export_formats, ["csv", "pdf"])
        self.assertTrue(settings.notify_company_on_accountant_action)

    def test_invitation_expiry_range_is_validated(self):
        for days in (0, 91):
            with self.subTest(days=days):
                settings = PortalSettings(tenant=self.tenant, invitation_expiry_days=days)
                with self.assertRaises(ValidationError):
                    settings.full_clean()


class AccountantPortalAccessTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.accountant = User.objects.create_user("legal")
        self.manager = User.objects.create_user("manager")
        self.tenant_a = Tenant.objects.create(CompanyName="شركة أ")
        self.tenant_b = Tenant.objects.create(CompanyName="شركة ب")
        for tenant in (self.tenant_a, self.tenant_b):
            TenantModule.objects.create(
                tenant=tenant,
                module_key="accountant_portal",
                enabled=True,
            )
            invalidate_module_cache(tenant.pk)
        self.membership = UserCompanyMembership.objects.create(
            user=self.accountant,
            tenant=self.tenant_a,
            role="legal_accountant",
        )
        self.engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant_a,
            initiated_by="company",
            status="active",
        )

    def _request(self, user, tenant):
        request = self.factory.get(
            "/api/accountant/workspace/companies/",
            HTTP_X_TENANT_ID=str(tenant.pk),
        )
        request.user = user
        return request

    def test_active_engagement_allows_its_tenant_and_hides_another(self):
        self.client.force_login(self.accountant)
        allowed = self.client.get(
            "/api/accountant/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        denied = self.client.get(
            "/api/accountant/",
            HTTP_X_TENANT_ID=str(self.tenant_b.pk),
        )

        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(denied.status_code, 404, denied.content)

    def test_inactive_or_missing_engagement_invalidates_legal_membership(self):
        request = self._request(self.accountant, self.tenant_a)
        self.engagement.status = "suspended"
        self.engagement.save(update_fields=["status"])

        with self.assertRaises(PermissionDenied):
            _validate_user_tenant_access(request, self.tenant_a)

    def test_disabled_module_invalidates_an_existing_legal_engagement(self):
        TenantModule.objects.filter(tenant=self.tenant_a).update(enabled=False)
        invalidate_module_cache(self.tenant_a.pk)
        request = self._request(self.accountant, self.tenant_a)

        with self.assertRaises(PermissionDenied):
            _validate_user_tenant_access(request, self.tenant_a)

        self.client.force_login(self.accountant)
        response = self.client.get(
            "/api/permissions/me/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_signup_alone_has_no_company_access(self):
        unlinked = User.objects.create_user("unlinked")
        request = self._request(unlinked, self.tenant_a)

        self.assertEqual(unlinked.company_memberships.count(), 0)
        with self.assertRaises(PermissionDenied):
            _validate_user_tenant_access(request, self.tenant_a)

    def test_same_user_keeps_manager_rights_separate_from_legal_role(self):
        UserCompanyMembership.objects.create(
            user=self.accountant,
            tenant=self.tenant_b,
            role="manager",
        )

        self.assertEqual(
            set(user_permissions(self.accountant, self.tenant_a)),
            LEGAL_ACCOUNTANT_DEFAULTS,
        )
        self.assertIn(
            "admin.permissions.manage",
            user_permissions(self.accountant, self.tenant_b),
        )

    def test_forbidden_permissions_are_removed_after_member_overrides(self):
        MemberPermission.objects.create(
            membership=self.membership,
            permission_key="inventory.doc.post",
            allowed=True,
        )
        MemberPermission.objects.create(
            membership=self.membership,
            permission_key="hr.tasks.manage",
            allowed=True,
        )

        effective = user_permissions(self.accountant, self.tenant_a)

        self.assertNotIn("inventory.doc.post", effective)
        self.assertNotIn("hr.tasks.manage", effective)
        self.assertEqual(set(role_default_permissions("legal_accountant")), LEGAL_ACCOUNTANT_DEFAULTS)
        self.assertIn("inventory.doc.post", LEGAL_ACCOUNTANT_FORBIDDEN)


class AccountantPortalPermissionApiTest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("scope-manager")
        self.accountant = User.objects.create_user("scope-accountant")
        self.tenant = Tenant.objects.create(CompanyName="شركة النطاق")
        TenantModule.objects.create(
            tenant=self.tenant,
            module_key="accountant_portal",
            enabled=True,
        )
        invalidate_module_cache(self.tenant.pk)
        UserCompanyMembership.objects.create(
            user=self.manager,
            tenant=self.tenant,
            role="manager",
        )
        self.membership = UserCompanyMembership.objects.create(
            user=self.accountant,
            tenant=self.tenant,
            role="legal_accountant",
        )
        AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="company",
            status="active",
        )
        self.client.force_authenticate(self.manager)

    def test_module_catalog_and_role_are_visible_only_when_licensed(self):
        enabled_roles = self.client.get(
            "/api/permissions/roles/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        enabled = self.client.get(
            "/api/permissions/matrix/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(enabled.status_code, 200, enabled.content)
        self.assertEqual(enabled_roles.status_code, 200, enabled_roles.content)
        self.assertIn("legal_accountant", [r["key"] for r in enabled_roles.data])
        self.assertIn("legal_accountant", [r["key"] for r in enabled.data["roles"]])
        self.assertEqual(
            set(enabled.data["defaults"]["legal_accountant"]),
            LEGAL_ACCOUNTANT_DEFAULTS,
        )
        self.assertEqual(
            len([p for p in enabled.data["permissions"] if p.get("module") == "accountant_portal"]),
            11,
        )

        TenantModule.objects.filter(tenant=self.tenant).update(enabled=False)
        invalidate_module_cache(self.tenant.pk)
        disabled = self.client.get(
            "/api/permissions/matrix/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        disabled_roles = self.client.get(
            "/api/permissions/roles/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(disabled.status_code, 200, disabled.content)
        self.assertEqual(disabled_roles.status_code, 200, disabled_roles.content)
        self.assertNotIn("legal_accountant", [r["key"] for r in disabled_roles.data])
        self.assertNotIn("legal_accountant", [r["key"] for r in disabled.data["roles"]])
        self.assertFalse(any(p.get("module") == "accountant_portal" for p in disabled.data["permissions"]))

    def test_manager_cannot_grant_an_absolute_forbidden_permission(self):
        response = self.client.patch(
            "/api/permissions/member/",
            {
                "membership_id": self.membership.pk,
                "changes": [
                    {"permission_key": "inventory.doc.post", "allowed": True},
                ],
            },
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 422, response.content)
        self.assertFalse(MemberPermission.objects.filter(membership=self.membership).exists())

    def test_grant_all_and_role_matrix_cannot_bypass_absolute_forbidden_set(self):
        grant_all = self.client.patch(
            "/api/permissions/member/",
            {"membership_id": self.membership.pk, "grant_all": True},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        matrix = self.client.patch(
            "/api/permissions/matrix/",
            {
                "changes": [
                    {
                        "role": "legal_accountant",
                        "permission_key": "inventory.doc.post",
                        "allowed": True,
                    },
                ],
            },
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(grant_all.status_code, 422, grant_all.content)
        self.assertEqual(matrix.status_code, 422, matrix.content)
        self.assertFalse(MemberPermission.objects.filter(membership=self.membership).exists())

    def test_rejected_permission_batch_is_atomic(self):
        response = self.client.patch(
            "/api/permissions/member/",
            {
                "membership_id": self.membership.pk,
                "changes": [
                    {"permission_key": "tax.period.approve", "allowed": True},
                    {"permission_key": "inventory.doc.post", "allowed": True},
                ],
            },
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 422, response.content)
        self.assertFalse(MemberPermission.objects.filter(membership=self.membership).exists())

    def test_operational_api_families_are_forbidden(self):
        self.client.force_authenticate(self.accountant)
        requests = (
            ("get", "/api/inventory/products/", None),
            ("get", "/api/hr/personal-expenses/", None),
            ("get", "/api/logistics/deals/", None),
            ("post", "/api/sales/quotations/", {}),
            ("post", f"/api/tenants/companies/{self.tenant.pk}/members/", {}),
            ("patch", "/api/tenants/settings/current/", {}),
        )

        for method, path, payload in requests:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(
                    path,
                    data=payload,
                    format="json" if payload is not None else None,
                    HTTP_X_TENANT_ID=str(self.tenant.pk),
                )
                self.assertEqual(response.status_code, 403, response.content)

        missing_header = self.client.get("/api/hr/personal-expenses/")
        self.assertEqual(missing_header.status_code, 403, missing_header.content)

        missing_header_write = self.client.post(
            "/api/sales/quotations/",
            {},
            format="json",
        )
        self.assertEqual(missing_header_write.status_code, 403, missing_header_write.content)


class TenantFallbackAccessTest(TestCase):
    def setUp(self):
        from core import tenant_utils

        tenant_utils._single_tenant_cache = None
        tenant_utils._single_tenant_checked = False
        self.tenant = Tenant.objects.create(CompanyName="الشركة الوحيدة")
        self.user = User.objects.create_user("fallback-unlinked")

    def test_single_tenant_fallback_still_requires_membership(self):
        request = RequestFactory().get("/api/accounting/accounts/")
        request.user = self.user

        with self.assertRaises(PermissionDenied):
            get_tenant(request)


class AccountantPortalAuditCodesTest(TestCase):
    def test_all_codes_fit_the_existing_mysql_column(self):
        self.assertTrue(AUDIT_ACTION_CODES)
        self.assertLessEqual(max(map(len, AUDIT_ACTION_CODES)), 20)
