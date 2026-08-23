"""T-TRIAL — الخطة التجريبية وتاريخ انتهاء الاشتراك.

ثلاث حقائق تُحرَس هنا:

1. الخطة التجريبية تعطي حدود Pro — لا حدود الأساسية (الخطة المجهولة كانت
   تُعامَل كالأساسية بصمت، فلولا هذا الاختبار لَمرّت «تجريبية» بحدّ 200 فاتورة).
2. التاريخ **شامل**: يوم الانتهاء يومُ عملٍ كامل، والقراءة-فقط تبدأ في اليوم
   التالي له. حدٌّ واحد يفصل بين «يعمل» و«ممنوع»، فيُختبر من طرفيه.
3. انتهاء الاشتراك يمنع **الكتابة وحدها**: القراءة والطباعة والتصدير تبقى،
   والسوبر أدمن لا يُمنع (وإلا لَما استطاع تجديد الاشتراك الذي انتهى).
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APITestCase

from accountant_portal.models import AccountantProfile
from accountant_portal.services import (
    accept_company_invitation, create_company_invitation,
)
from core.models import ActivityLog, TenantModule
from core.modules import invalidate_module_cache
from core.permissions import TenantRolePermission
from core.plans import (
    PLAN_DEFAULTS, TRIAL_PERIOD_DAYS, limit_value, subscription_expiry,
    trial_end_date,
)
from tenants.models import Tenant, UserCompanyMembership


class TrialPlanLimitsTest(APITestCase):
    """الخطة التجريبية خطةٌ معروفة بحدود Pro، لا مجهولةٌ تسقط على الأساسية."""

    def test_trial_is_a_known_plan_with_pro_limits(self):
        self.assertEqual(PLAN_DEFAULTS["Trial"], PLAN_DEFAULTS["Pro"])
        tenant = Tenant.objects.create(
            CompanyName="شركة مجرِّبة", SubscriptionPlan="Trial", Status="Trial")
        self.assertEqual(limit_value(tenant, "sales.invoices"),
                         PLAN_DEFAULTS["Pro"]["sales.invoices"])
        self.assertNotEqual(limit_value(tenant, "sales.invoices"),
                            PLAN_DEFAULTS["Basic"]["sales.invoices"])

    def test_trial_end_date_is_the_configured_period_ahead(self):
        self.assertEqual(
            trial_end_date(), timezone.localdate() + timedelta(days=TRIAL_PERIOD_DAYS))


class NewCompanyStartsOnTrialTest(APITestCase):
    """الشركة الجديدة تبدأ تجريبية بمدّتها — لا `Enterprise` بلا حدود ولا انتهاء.

    كانت `create_company` تُنشئ كل شركة `Enterprise/Active`، فلا تبدأ التجربة
    لأحد إلا بتدخّل يدوي من السوبر أدمن — أي أن وجود الخطة التجريبية نفسه كان
    بلا أثر على مسار التسجيل.
    """

    def test_a_company_created_from_the_app_is_a_running_trial(self):
        from tenants.services import create_company

        creator = User.objects.create_user(username="fresh-owner", password="x")
        tenant = create_company("شركة جديدة", creator)

        self.assertEqual(tenant.SubscriptionPlan, "Trial")
        self.assertEqual(tenant.subscription_ends_at, trial_end_date())
        state = subscription_expiry(tenant)
        self.assertFalse(state["expired"])
        self.assertEqual(state["days_left"], TRIAL_PERIOD_DAYS)
        # وحدودها حدود Pro لا الأساسية — التجربة تُظهر المنتج بكامل قوّته.
        self.assertEqual(limit_value(tenant, "sales.invoices"),
                         PLAN_DEFAULTS["Pro"]["sales.invoices"])


class SubscriptionExpiryBoundaryTest(APITestCase):
    """طرفا الحدّ: يوم الانتهاء يعمل، وتاليه لا."""

    def _tenant(self, ends_at):
        return Tenant.objects.create(
            CompanyName="شركة", SubscriptionPlan="Trial", Status="Trial",
            subscription_ends_at=ends_at,
        )

    def test_no_date_means_no_expiry(self):
        state = subscription_expiry(self._tenant(None))
        self.assertEqual(
            (state["expired"], state["days_left"], state["expiring_soon"]),
            (False, None, False),
        )

    def test_last_day_is_still_a_working_day(self):
        state = subscription_expiry(self._tenant(timezone.localdate()))
        self.assertFalse(state["expired"])
        self.assertEqual(state["days_left"], 0)
        self.assertTrue(state["expiring_soon"])

    def test_day_after_the_end_date_is_expired(self):
        state = subscription_expiry(
            self._tenant(timezone.localdate() - timedelta(days=1)))
        self.assertTrue(state["expired"])
        self.assertEqual(state["days_left"], -1)

    def test_warning_window_is_the_last_seven_days_only(self):
        self.assertTrue(subscription_expiry(
            self._tenant(timezone.localdate() + timedelta(days=7)))["expiring_soon"])
        self.assertFalse(subscription_expiry(
            self._tenant(timezone.localdate() + timedelta(days=8)))["expiring_soon"])

    def test_tenant_id_alone_resolves_the_same_state(self):
        tenant = self._tenant(timezone.localdate() - timedelta(days=3))
        self.assertTrue(subscription_expiry(tenant.pk)["expired"])


class ExpiredSubscriptionWriteGuardTest(APITestCase):
    """انتهاء الاشتراك = قراءة فقط، بحارسٍ واحد يمرّ عليه كل طلب DRF."""

    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(username="trial-member", password="x")
        cls.root = User.objects.create_superuser(
            username="trial-root", email="trial-root@example.com", password="x")
        cls.expired = Tenant.objects.create(
            CompanyName="شركة انتهت تجربتها", SubscriptionPlan="Trial",
            Status="Trial", subscription_ends_at=timezone.localdate() - timedelta(days=1),
        )
        cls.running = Tenant.objects.create(
            CompanyName="شركة تجربتها سارية", SubscriptionPlan="Trial",
            Status="Trial", subscription_ends_at=timezone.localdate(),
        )
        for tenant in (cls.expired, cls.running):
            UserCompanyMembership.objects.create(
                user=cls.member, tenant=tenant, role="manager")

    def _allows(self, user, tenant, method="post"):
        request = getattr(RequestFactory(), method)(
            "/api/partners/", HTTP_X_TENANT_ID=str(tenant.pk))
        request.user = user
        return TenantRolePermission().has_permission(request, None)

    def test_write_is_blocked_after_the_end_date(self):
        self.assertFalse(self._allows(self.member, self.expired))

    def test_read_still_passes_after_the_end_date(self):
        self.assertTrue(self._allows(self.member, self.expired, method="get"))

    def test_last_day_still_allows_writing(self):
        self.assertTrue(self._allows(self.member, self.running))

    def test_super_admin_is_not_locked_out_of_an_expired_company(self):
        self.assertTrue(self._allows(self.root, self.expired))

    def test_api_write_returns_403_with_the_renewal_message(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            "/api/partners/", {"name": "عميل", "partner_type": "Customer"},
            format="json", HTTP_X_TENANT_ID=str(self.expired.pk),
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("انتهى اشتراك الشركة", str(response.json()))

    def test_api_write_passes_in_a_company_whose_subscription_runs(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            "/api/partners/", {"name": "عميل", "partner_type": "Customer"},
            format="json", HTTP_X_TENANT_ID=str(self.running.pk),
        )
        self.assertEqual(response.status_code, 201, response.content)


class AccountantPortalExpiryTest(APITestCase):
    """البوابة تستبدل `permission_classes` فلا يمرّ بها الحارس العام — تُفحص وحدها.

    بلا هذا الاختبار يبقى للكتابة بابٌ خلفي: كل مسار في `/api/accountant/` داخل
    شركةٍ ينبني على `TenantScopedView` الذي يعلن `[IsAuthenticated]` وحدها.
    """

    def setUp(self):
        self.manager = User.objects.create_user("trial-portal-manager")
        self.accountant = User.objects.create_user(
            "trial-portal-accountant", email="trial-portal@example.com")
        self.tenant = Tenant.objects.create(
            CompanyName="شركة بوابة منتهية", SubscriptionPlan="Trial", Status="Trial",
            subscription_ends_at=timezone.localdate() - timedelta(days=1),
        )
        TenantModule.objects.create(
            tenant=self.tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.tenant.pk)
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        AccountantProfile.objects.create(
            user=self.accountant, professional_type="accountant",
            tax_registration_number="TAX-TRIAL-1", business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        _engagement, token = create_company_invitation(
            tenant=self.tenant, manager=self.manager, accountant=self.accountant,
            scope=["review.query.create"],
        )
        accept_company_invitation(accountant=self.accountant, token=token)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def test_portal_write_is_blocked_after_the_end_date(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.post(
            "/api/accountant/review/queries/",
            {"title": "استفسار", "body": "نص", "severity": "info",
             "entity_type": "sales_invoice", "entity_id": 1},
            format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("انتهى اشتراك الشركة", str(response.content, "utf-8"))

    def test_portal_read_still_works_after_the_end_date(self):
        self.client.force_authenticate(self.accountant)
        response = self.client.get("/api/accountant/review/queries/", **self.headers)
        self.assertEqual(response.status_code, 200, response.content)


class PlatformSubscriptionDateTest(APITestCase):
    """ضبط التاريخ من لوحة المنصة — بمن فيهم من نسي أن يكتبه."""

    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username="plan-root", email="plan-root@example.com", password="x")
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة اللوحة", SubscriptionPlan="Basic", Status="Active")

    def setUp(self):
        self.client.force_authenticate(user=self.root)
        self.url = f"/api/platform/companies/{self.tenant.pk}/"

    def test_switching_to_trial_without_a_date_fills_the_default_period(self):
        response = self.client.patch(self.url, {"plan": "Trial"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.subscription_ends_at, trial_end_date())
        self.assertEqual(response.json()["subscription_days_left"], TRIAL_PERIOD_DAYS)

    def test_an_explicit_date_is_kept_as_sent(self):
        wanted = timezone.localdate() + timedelta(days=45)
        response = self.client.patch(
            self.url, {"plan": "Trial", "subscription_ends_at": wanted.isoformat()},
            format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.subscription_ends_at, wanted)

    def test_clearing_the_date_makes_the_subscription_permanent(self):
        self.tenant.subscription_ends_at = timezone.localdate()
        self.tenant.save(update_fields=["subscription_ends_at"])
        response = self.client.patch(
            self.url, {"subscription_ends_at": None}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.subscription_ends_at)
        self.assertIsNone(response.json()["subscription_days_left"])

    def test_a_malformed_date_is_refused(self):
        response = self.client.patch(
            self.url, {"subscription_ends_at": "٢٠٢٦/٠٩/٠١"}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.subscription_ends_at)

    def test_the_change_is_written_to_the_company_activity_log(self):
        wanted = timezone.localdate() + timedelta(days=30)
        self.client.patch(
            self.url, {"subscription_ends_at": wanted.isoformat()}, format="json")
        event = (
            ActivityLog.objects
            .filter(tenant=self.tenant, entity_type="tenant")
            .order_by("-id").first()
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.metadata["event_code"], "SUBSCRIPTION_END_CHANGED")
        self.assertEqual(event.metadata["new"], wanted.isoformat())
