from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from unittest.mock import patch

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
            "accountant_signup": "5/hour",
            "accountant_verify": "10/hour",
        },
    },
)
class AccountantIdentityApiTest(APITestCase):
    signup_url = "/api/accountant/signup/"

    def signup_payload(self, **overrides):
        payload = {
            "fullName": "ليان محاسب",
            "email": "layan@example.com",
            "password": "UniquePass-4931",
            "professional_type": "accountant",
            "tax_registration_number": "TAX-M2-100",
            "business_address": "رام الله",
            "phone": "0599000000",
        }
        payload.update(overrides)
        return payload

    def test_signup_creates_profile_without_membership_and_sends_verification(self):
        response = self.client.post(self.signup_url, self.signup_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email="layan@example.com")
        profile = AccountantProfile.objects.get(user=user)
        self.assertIsNone(profile.email_verified_at)
        self.assertEqual(user.company_memberships.count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("UniquePass-4931", mail.outbox[0].body)

    def test_duplicate_email_is_indistinguishable_and_returns_201(self):
        User.objects.create_user(
            username="layan@example.com",
            email="layan@example.com",
            password="ExistingPass-4931",
        )

        response = self.client.post(self.signup_url, self.signup_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.filter(email="layan@example.com").count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_accountant_password_policy_is_ten_characters_and_not_common(self):
        short = self.client.post(
            self.signup_url,
            self.signup_payload(password="Abc12345"),
            format="json",
        )
        common = self.client.post(
            self.signup_url,
            self.signup_payload(password="password123", email="other@example.com", tax_registration_number="TAX-M2-101"),
            format="json",
        )

        self.assertEqual(short.status_code, 400, short.content)
        self.assertEqual(short.data["code"], "weak_password")
        self.assertEqual(common.status_code, 400, common.content)
        self.assertEqual(common.data["code"], "weak_password")

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


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountantSignupWithoutEmailVerificationTest(APITestCase):
    """قرار المالك: تحقق البريد غير مطلوب — الحساب جاهز فور التسجيل بلا رسالة."""

    def payload(self):
        return {
            "fullName": "سامي محاسب",
            "email": "sami@example.com",
            "password": "UniquePass-7712",
            "professional_type": "licensed_auditor",
            "tax_registration_number": "TAX-NOVERIFY-1",
            "business_address": "الخليل",
        }

    def test_signup_activates_the_profile_immediately_and_sends_no_mail(self):
        response = self.client.post("/api/accountant/signup/", self.payload(), format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.data["email_verification_required"])
        profile = AccountantProfile.objects.get(user__email="sami@example.com")
        self.assertIsNotNone(profile.email_verified_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_profile_and_engagement_request_work_without_any_verification(self):
        from core.models import TenantModule
        from core.modules import invalidate_module_cache
        from tenants.models import Tenant

        self.client.post("/api/accountant/signup/", self.payload(), format="json")
        user = User.objects.get(email="sami@example.com")
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


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "accountant-throttle-test",
        }
    },
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.TokenAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
        "DEFAULT_THROTTLE_RATES": {"accountant_signup": "1/minute"},
    },
)
class AccountantSignupThrottleTest(APITestCase):
    def setUp(self):
        cache.clear()

    def payload(self, email, tax_number):
        return {
            "fullName": "اختبار الثروتل",
            "email": email,
            "password": "UniquePass-9931",
            "professional_type": "accountant",
            "tax_registration_number": tax_number,
            "business_address": "رام الله",
        }

    def test_signup_throttle_returns_429(self):
        with patch.object(
            ScopedRateThrottle,
            "THROTTLE_RATES",
            {"accountant_signup": "1/minute"},
        ):
            first = self.client.post(
                "/api/accountant/signup/",
                self.payload("rate-one@example.com", "TAX-RATE-1"),
                format="json",
            )
            second = self.client.post(
                "/api/accountant/signup/",
                self.payload("rate-two@example.com", "TAX-RATE-2"),
                format="json",
            )

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 429, second.content)
