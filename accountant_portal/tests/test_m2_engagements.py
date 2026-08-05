from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from accounting.models import AccountingAuditLog
from accountant_portal.models import AccountantEngagement, AccountantProfile, PortalSettings
from accountant_portal.services import (
    EngagementConflict,
    accept_company_invitation,
    approve_accountant_request,
    create_company_invitation,
    resume_engagement,
    revoke_engagement,
    suspend_engagement,
)
from core.models import TenantModule
from core.modules import invalidate_module_cache
from tenants.models import MemberPermission, Tenant, UserCompanyMembership


class EngagementServiceTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("m2-manager")
        self.accountant = User.objects.create_user("m2-accountant", email="accountant@example.com")
        self.tenant = Tenant.objects.create(CompanyName="شركة M2")
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        TenantModule.objects.create(tenant=self.tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.tenant.pk)
        self.profile = AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-M2-200",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )

    def _invite(self, scope=None):
        return create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=scope or ["sales.invoice.view", "tax.period.view"],
            note="راجع الحسابات",
        )

    def test_invitation_token_is_hashed_single_use_and_accepts_once(self):
        engagement, token = self._invite()

        self.assertNotEqual(engagement.invitation_token_hash, token)
        self.assertNotIn(token, engagement.invitation_token_hash)
        accepted = accept_company_invitation(accountant=self.accountant, token=token)

        self.assertEqual(accepted.status, "active")
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        self.assertEqual(membership.role, "legal_accountant")
        with self.assertRaises(EngagementConflict) as used:
            accept_company_invitation(accountant=self.accountant, token=token)
        self.assertEqual(used.exception.code, "invitation_used")
        self.assertEqual(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).count(), 1)

    def test_expired_invitation_returns_410(self):
        engagement, token = self._invite()
        AccountantEngagement.objects.filter(pk=engagement.pk).update(
            invitation_expires_at=timezone.now() - timedelta(seconds=1),
        )

        with self.assertRaises(EngagementConflict) as expired:
            accept_company_invitation(accountant=self.accountant, token=token)

        self.assertEqual(expired.exception.code, "invitation_expired")
        self.assertEqual(expired.exception.status_code, 410)

    def test_revoked_invitation_cannot_be_accepted(self):
        engagement, token = self._invite()
        revoke_engagement(engagement=engagement, actor=self.manager, reason="سحب الدعوة")

        with self.assertRaises(EngagementConflict) as revoked:
            accept_company_invitation(accountant=self.accountant, token=token)

        self.assertEqual(revoked.exception.code, "invitation_used")

    def test_suspend_then_resume_restores_exact_scope(self):
        engagement, token = self._invite(["sales.invoice.view", "tax.period.approve"])
        accept_company_invitation(accountant=self.accountant, token=token)
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        before = set(
            MemberPermission.objects.filter(membership=membership, allowed=True).values_list("permission_key", flat=True)
        )

        suspend_engagement(engagement=engagement, actor=self.manager, reason="مراجعة داخلية")
        self.assertFalse(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).exists())
        resume_engagement(engagement=engagement, actor=self.manager)

        restored = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        after = set(
            MemberPermission.objects.filter(membership=restored, allowed=True).values_list("permission_key", flat=True)
        )
        self.assertEqual(after, before)

    def test_revoke_is_immediate_final_and_does_not_delete_auth_token(self):
        from rest_framework.authtoken.models import Token

        engagement, invitation = self._invite()
        accept_company_invitation(accountant=self.accountant, token=invitation)
        auth_token = Token.objects.create(user=self.accountant)

        revoke_engagement(engagement=engagement, actor=self.manager, reason="انتهاء العقد")

        self.assertFalse(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).exists())
        self.assertTrue(Token.objects.filter(pk=auth_token.pk).exists())
        with self.assertRaises(EngagementConflict) as final:
            resume_engagement(engagement=engagement, actor=self.manager)
        self.assertEqual(final.exception.code, "already_revoked")

    def test_barred_profile_cannot_be_approved(self):
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="accountant",
            requested_by=self.accountant,
        )
        self.profile.verification_status = "barred"
        self.profile.save(update_fields=["verification_status"])

        with self.assertRaises(EngagementConflict) as barred:
            approve_accountant_request(
                engagement=engagement,
                manager=self.manager,
                scope=["sales.invoice.view"],
            )

        self.assertEqual(barred.exception.code, "accountant_barred")
        self.assertEqual(barred.exception.status_code, 422)

    def test_max_active_engagements_is_enforced_on_activation(self):
        other_tenant = Tenant.objects.create(CompanyName="شركة أخرى")
        PortalSettings.objects.create(tenant=other_tenant, max_active_engagements=1)
        AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=other_tenant,
            initiated_by="company",
            status="active",
        )
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="accountant",
        )
        PortalSettings.objects.create(tenant=self.tenant, max_active_engagements=1)

        with self.assertRaises(EngagementConflict) as limited:
            approve_accountant_request(
                engagement=engagement,
                manager=self.manager,
                scope=["sales.invoice.view"],
            )
        self.assertEqual(limited.exception.code, "max_engagements_reached")


class EngagementApiTest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("api-manager")
        self.accountant = User.objects.create_user("api-accountant", email="api-accountant@example.com")
        self.tenant = Tenant.objects.create(CompanyName="شركة API")
        TenantModule.objects.create(tenant=self.tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.tenant.pk)
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-M2-API",
            business_address="بيت لحم",
            email_verified_at=timezone.now(),
        )

    def test_accountant_request_then_manager_approval_writes_exact_scope(self):
        self.client.force_authenticate(self.accountant)
        requested = self.client.post(
            "/api/accountant/engagements/request/",
            {"tenant_id": self.tenant.pk, "note": "طلب مراجعة"},
            format="json",
        )
        self.assertEqual(requested.status_code, 201, requested.content)

        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            f"/api/accountant/company/engagements/{requested.data['engagement']['id']}/approve/",
            {"scope": ["sales.invoice.view", "tax.period.approve"]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(approved.status_code, 200, approved.content)
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        allowed = set(
            MemberPermission.objects.filter(membership=membership, allowed=True).values_list("permission_key", flat=True)
        )
        self.assertEqual(allowed, {"sales.invoice.view", "tax.period.approve"})

    def test_company_scope_rejects_forbidden_permission(self):
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="accountant",
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/accountant/company/engagements/{engagement.pk}/approve/",
            {"scope": ["inventory.doc.post"]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.data["code"], "forbidden_permission_key")
        self.assertFalse(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).exists())

    def test_general_member_endpoint_cannot_create_orphan_legal_membership(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/tenants/companies/{self.tenant.pk}/members/",
            {"username_or_email": self.accountant.email, "role": "legal_accountant"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).exists())

    def test_internal_member_keeps_their_internal_role_after_approval(self):
        """قرار المالك: العضوية الداخلية لا تمنع الارتباط. والشرط أن الارتباط
        **لا يمسّ العضوية** — فلا تفقد الشركة مديرها ولا تُمحى تخصيصاته."""
        membership = UserCompanyMembership.objects.create(
            user=self.accountant, tenant=self.tenant, role="manager",
        )
        MemberPermission.objects.create(
            membership=membership, permission_key="sales.invoice.post", allowed=True,
        )
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="accountant",
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/accountant/company/engagements/{engagement.pk}/approve/",
            {"scope": ["sales.invoice.view"]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 200, response.content)
        membership.refresh_from_db()
        self.assertEqual(membership.role, "manager")
        self.assertEqual(
            list(membership.permission_overrides.values_list("permission_key", flat=True)),
            ["sales.invoice.post"],
        )

    def test_request_is_accepted_for_an_internal_member(self):
        UserCompanyMembership.objects.create(
            user=self.accountant, tenant=self.tenant, role="staff",
        )
        self.client.force_authenticate(self.accountant)

        response = self.client.post(
            "/api/accountant/engagements/request/",
            {"tenant_id": self.tenant.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(
            AccountantEngagement.objects.filter(accountant=self.accountant, tenant=self.tenant).exists()
        )
        self.assertEqual(
            UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant).role,
            "staff",
        )

    def test_internal_member_opens_their_own_company_as_a_client_file(self):
        """رحلة المالك كاملةً: مدير الشركة يطلب ملفها في مكتبه ← يوافق ← يفتح الملف."""
        UserCompanyMembership.objects.create(
            user=self.accountant, tenant=self.tenant, role="manager",
        )
        self.client.force_authenticate(self.accountant)
        requested = self.client.post(
            "/api/accountant/engagements/request/",
            {"tenant_id": self.tenant.pk},
            format="json",
        )
        self.assertEqual(requested.status_code, 201, requested.content)

        approved = self.client.post(
            f"/api/accountant/company/engagements/{requested.data['engagement']['id']}/approve/",
            {},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(approved.status_code, 200, approved.content)

        summary = self.client.get(
            "/api/accountant/client/summary/?from=2026-08-01&to=2026-08-31",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(summary.status_code, 200, summary.content)
        self.assertEqual(summary.data["company_name"], self.tenant.CompanyName)
        self.assertEqual(
            UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant).role,
            "manager",
        )

    def test_revoking_an_internal_member_engagement_keeps_the_membership(self):
        """إلغاء الارتباط يحذف عضوية المحاسب الخارجي — أما العضو الداخلي فعضويته
        ليست من صنع الارتباط، فحذفها يطرده من شركته."""
        UserCompanyMembership.objects.create(
            user=self.accountant, tenant=self.tenant, role="manager",
        )
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant, tenant=self.tenant, initiated_by="accountant",
        )
        approve_accountant_request(engagement=engagement, manager=self.manager)

        revoke_engagement(engagement=engagement, actor=self.manager, reason="انتهى")

        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        self.assertEqual(membership.role, "manager")

    def test_cost_view_grant_is_blocked_when_the_company_forbids_it(self):
        PortalSettings.objects.create(tenant=self.tenant, allow_grant_cost_view=False)
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="accountant",
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/accountant/company/engagements/{engagement.pk}/approve/",
            {"scope": ["sales.invoice.view", "inventory.cost.view"]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.data["code"], "cost_view_not_allowed")
        self.assertFalse(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).exists())

    def test_scope_change_requires_password_reauth(self):
        self.manager.set_password("Manager-Pass-4931")
        self.manager.save(update_fields=["password"])
        engagement, token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["sales.invoice.view"],
        )
        accept_company_invitation(accountant=self.accountant, token=token)
        self.client.force_authenticate(self.manager)

        denied = self.client.patch(
            f"/api/accountant/company/engagements/{engagement.pk}/scope/",
            {"scope": ["sales.invoice.view", "tax.period.approve"]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        allowed = self.client.patch(
            f"/api/accountant/company/engagements/{engagement.pk}/scope/",
            {
                "scope": ["sales.invoice.view", "tax.period.approve"],
                "reauth_password": "Manager-Pass-4931",
            },
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(denied.data["code"], "reauth_required")
        self.assertEqual(allowed.status_code, 200, allowed.content)
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        self.assertIn(
            "tax.period.approve",
            set(
                MemberPermission.objects.filter(membership=membership, allowed=True)
                .values_list("permission_key", flat=True)
            ),
        )

    def test_invitation_cannot_be_accepted_after_the_license_is_revoked(self):
        engagement, token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["sales.invoice.view"],
        )
        TenantModule.objects.filter(tenant=self.tenant, module_key="accountant_portal").update(enabled=False)
        invalidate_module_cache(self.tenant.pk)

        with self.assertRaises(EngagementConflict) as disabled:
            accept_company_invitation(accountant=self.accountant, token=token)

        self.assertEqual(disabled.exception.code, "company_not_found")
        self.assertEqual(disabled.exception.status_code, 404)
        self.assertFalse(UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).exists())

    def test_company_portal_settings_read_and_update_is_audited(self):
        self.manager.set_password("Manager-Pass-4931")
        self.manager.save(update_fields=["password"])
        self.client.force_authenticate(self.manager)

        read = self.client.get(
            "/api/accountant/company/settings/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        updated = self.client.patch(
            "/api/accountant/company/settings/",
            {"invitation_expiry_days": 7, "allow_grant_cost_view": False},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(read.status_code, 200, read.content)
        self.assertEqual(read.data["settings"]["invitation_expiry_days"], 14)
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data["settings"]["invitation_expiry_days"], 7)
        self.assertFalse(updated.data["settings"]["allow_grant_cost_view"])
        self.assertTrue(
            AccountingAuditLog.objects.filter(
                tenant=self.tenant,
                action="PORTAL_CFG_SET",
                model_name="PortalSettings",
            ).exists()
        )

    def test_accountant_cannot_read_or_change_portal_settings(self):
        engagement, token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["sales.invoice.view"],
        )
        accept_company_invitation(accountant=self.accountant, token=token)
        self.client.force_authenticate(self.accountant)

        response = self.client.get(
            "/api/accountant/company/settings/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 403, response.content)

    def test_revoke_blocks_the_very_next_tenant_request(self):
        engagement, token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["sales.invoice.view"],
        )
        accept_company_invitation(accountant=self.accountant, token=token)
        self.client.force_authenticate(self.accountant)
        before = self.client.get(
            "/api/accountant/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        revoke_engagement(engagement=engagement, actor=self.manager, reason="انتهاء العقد")
        after = self.client.get(
            "/api/accountant/",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(before.status_code, 200, before.content)
        self.assertEqual(after.status_code, 404, after.content)


class DefaultGrantScopeTest(APITestCase):
    """موافقة الشركة وحدها تكفي ليعمل المحاسب — بلا تأشير يدوي لكل مفتاح."""

    def setUp(self):
        self.manager = User.objects.create_user("default-scope-manager")
        self.accountant = User.objects.create_user("default-scope-accountant", email="ds@example.com")
        self.tenant = Tenant.objects.create(CompanyName="شركة الافتراضي")
        TenantModule.objects.create(tenant=self.tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.tenant.pk)
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="licensed_auditor",
            tax_registration_number="TAX-DEFAULT-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        self.engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.tenant,
            initiated_by="accountant",
        )
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def _allowed(self):
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        return set(
            MemberPermission.objects.filter(membership=membership, allowed=True)
            .values_list("permission_key", flat=True)
        )

    def test_approval_without_a_scope_grants_the_routine_professional_set(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/accountant/company/engagements/{self.engagement.pk}/approve/",
            {},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        allowed = self._allowed()
        # يقرأ الفواتير والقيود والتقارير ⇒ يُخرج الميزانية وورقة الضريبة فوراً.
        for key in (
            "sales.invoice.view", "purchase.invoice.view",
            "accounting.journal.view", "accounting.report.view",
            "tax.period.view", "finance.export.package",
        ):
            self.assertIn(key, allowed, key)
        # ولا يمسّ المخزون ولا الإدارة بحال.
        for key in ("inventory.item.view", "inventory.doc.post", "admin.settings.manage"):
            self.assertNotIn(key, allowed, key)

    def test_an_explicit_empty_scope_stays_empty(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/accountant/company/engagements/{self.engagement.pk}/approve/",
            {"scope": []},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._allowed(), set())

    def test_catalog_exposes_the_defaults_and_the_three_profiles(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(
            "/api/accountant/company/engagements/scope-catalog/", **self.headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("accounting.report.view", response.data["defaults"])
        self.assertEqual(response.data["active_profile"], "review_only")
        self.assertIn("sales.invoice.post", response.data["profiles"]["full_accounting"])
        self.assertNotIn("inventory.doc.post", response.data["profiles"]["full_accounting"])


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "engagement-request-throttle-test",
        }
    },
)
class EngagementRequestThrottleTest(APITestCase):
    """الحصة تحمي الشركات من إغراقها بطلبات ارتباط — لا تعاقب المحاسب على محاولة
    مرفوضة ولا على بحثٍ عن شركة."""

    def setUp(self):
        cache.clear()
        self.accountant = User.objects.create_user(
            "throttle-accountant", email="throttle-accountant@example.com",
        )
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="licensed_auditor",
            tax_registration_number="TAX-THROTTLE-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        # شركة لها ارتباط سابق — طلبها يُرفض بـ409 بلا إنشاء
        self.taken_company = self._licensed_tenant("شركة الارتباط السابق")
        AccountantEngagement.objects.create(
            accountant=self.accountant, tenant=self.taken_company, initiated_by="accountant",
        )
        self.first_client = self._licensed_tenant("شركة النور")
        self.second_client = self._licensed_tenant("شركة الفجر")
        self.client.force_authenticate(self.accountant)

    def _licensed_tenant(self, name):
        tenant = Tenant.objects.create(CompanyName=name)
        TenantModule.objects.create(tenant=tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(tenant.pk)
        return tenant

    def _rates(self, request_rate="1/minute"):
        return patch.object(
            ScopedRateThrottle,
            "THROTTLE_RATES",
            {
                "accountant_engagement_request": request_rate,
                "accountant_company_lookup": "60/hour",
            },
        )

    def _request(self, tenant):
        return self.client.post(
            "/api/accountant/engagements/request/",
            {"tenant_id": tenant.pk, "note": "طلب ملف"},
            format="json",
        )

    def test_rejected_request_does_not_consume_the_quota(self):
        with self._rates():
            rejected = self._request(self.taken_company)
            accepted = self._request(self.first_client)

        self.assertEqual(rejected.status_code, 409, rejected.content)
        self.assertEqual(rejected.data["code"], "engagement_exists")
        self.assertEqual(accepted.status_code, 201, accepted.content)

    def test_company_lookup_does_not_consume_the_request_quota(self):
        with self._rates():
            for _ in range(3):
                found = self.client.get("/api/accountant/companies/lookup/?q=شركة النور")
                self.assertEqual(found.status_code, 200, found.content)
            accepted = self._request(self.first_client)

        self.assertEqual(accepted.status_code, 201, accepted.content)

    def test_successful_requests_still_consume_the_quota(self):
        with self._rates():
            first = self._request(self.first_client)
            second = self._request(self.second_client)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 429, second.content)
        self.assertEqual(second.data["code"], "throttled")

    def test_throttle_message_says_minutes_not_raw_seconds(self):
        with self._rates():
            self._request(self.first_client)
            throttled = self._request(self.second_client)

        self.assertEqual(throttled.status_code, 429, throttled.content)
        self.assertIn("دقيقة", throttled.data["detail"])
        self.assertNotIn("ثواني", throttled.data["detail"])
