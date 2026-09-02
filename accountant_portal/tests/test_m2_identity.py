from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from accountant_portal.identity import make_email_verification_token
from accountant_portal.models import AccountantProfile


@override_settings(
    ACCOUNTANT_REQUIRE_EMAIL_VERIFICATION=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.TokenAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_THROTTLE_RATES": {
            "accountant_verify": "10/hour",
        },
    },
)
class AccountantIdentityApiTest(APITestCase):
    def test_email_token_is_single_use(self):
        user = User.objects.create_user("verify@example.com", email="verify@example.com")
        AccountantProfile.objects.create(
            user=user,
            professional_type="accountant",
            tax_registration_number="TAX-M2-102",
            business_address="الخليل",
        )
        token = make_email_verification_token(user)

        verified = self.client.post("/api/accountant/verify-email/", {"token": token}, format="json")
        used = self.client.post("/api/accountant/verify-email/", {"token": token}, format="json")

        self.assertEqual(verified.status_code, 200, verified.content)
        self.assertTrue(verified.data["verified"])
        self.assertEqual(used.status_code, 400, used.content)
        self.assertEqual(used.data["code"], "token_used")

    def test_me_requires_verified_email_and_can_submit_complete_profile(self):
        user = User.objects.create_user("profile@example.com", email="profile@example.com")
        profile = AccountantProfile.objects.create(
            user=user,
            professional_type="licensed_auditor",
            tax_registration_number="TAX-M2-103",
            business_address="نابلس",
            license_number="LIC-22",
            license_authority="وزارة الاقتصاد",
        )
        self.client.force_authenticate(user)

        denied = self.client.get("/api/accountant/me/")
        profile.email_verified_at = profile.created_at
        profile.save(update_fields=["email_verified_at"])
        allowed = self.client.get("/api/accountant/me/")
        submitted = self.client.post("/api/accountant/me/submit-verification/", {}, format="json")

        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(denied.data["code"], "email_unverified")
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(submitted.status_code, 202, submitted.content)
        profile.refresh_from_db()
        self.assertEqual(profile.verification_status, "pending_review")


class AccountantProfileWithoutEmailVerificationTest(APITestCase):
    """قرار المالك: تحقق البريد غير مطلوب — الملف المهني جاهز فور إنشائه."""

    def _make_profile(self):
        from django.utils import timezone

        user = User.objects.create_user("sami@example.com", email="sami@example.com")
        return user, AccountantProfile.objects.create(
            user=user,
            professional_type="licensed_auditor",
            tax_registration_number="TAX-NOVERIFY-1",
            business_address="الخليل",
            email_verified_at=timezone.now(),
        )

    def test_profile_and_engagement_request_work_without_any_verification(self):
        from core.models import TenantModule
        from core.modules import invalidate_module_cache
        from tenants.models import Tenant

        user, _profile = self._make_profile()
        tenant = Tenant.objects.create(CompanyName="شركة بلا تحقق")
        TenantModule.objects.create(tenant=tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(tenant.pk)
        self.client.force_authenticate(user)

        profile = self.client.get("/api/accountant/me/")
        requested = self.client.post(
            "/api/accountant/engagements/request/",
            {"tenant_id": tenant.pk, "note": "طلب"},
            format="json",
        )

        self.assertEqual(profile.status_code, 200, profile.content)
        self.assertEqual(requested.status_code, 201, requested.content)


class AccountantSignupRouteClosedTest(APITestCase):
    """ISSUE #60 — الباب المنفصل أُغلق على الخادم أيضاً: القالب `accounting_firm` حلّ محلّه."""

    def test_signup_endpoint_no_longer_exists(self):
        response = self.client.post(
            "/api/accountant/signup/",
            {"fullName": "لن يُسجَّل", "email": "closed@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.content)
