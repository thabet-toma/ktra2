"""حارسُ العقد بين حمولات التوظيف والفوترة وأنواع الواجهة التي تقرؤها (#207 م٨).

يفحص أن كلّ حقلٍ تعلنه أنواعُ الواجهة في:
- `services/platformHiringApi.ts`
- `services/myAgentApi.ts` (QuotaUsage)
- `services/platformOpsApi.ts` (SubscriptionBillingRecordRow)
موجودٌ فعلاً في حمولةٍ حقيقيّةٍ يبنيها الخادم.
"""
import datetime
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import (
    JobApplicant,
    JobPosting,
    PlatformEmployee,
    PlatformRecruiter,
    PolicyProfile,
    ServiceSubscription,
    SubscriptionBillingRecord,
)
from platform_ops.services import create_job_posting
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields
from sales.models import SalesInvoice
from tenants.models import Currency, Tenant, UserCompanyMembership
from partners.models import Partner

import re

User = get_user_model()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HIRING_API = REPO_ROOT / "frontend_v2" / "services" / "platformHiringApi.ts"
MY_AGENT_API = REPO_ROOT / "frontend_v2" / "services" / "myAgentApi.ts"
OPS_API = REPO_ROOT / "frontend_v2" / "services" / "platformOpsApi.ts"
HIRING_UTIL = REPO_ROOT / "frontend_v2" / "utils" / "platformHiring.ts"


class PlatformHiringFrontendContractTest(TestCase):
    """كلّ حقلٍ في واجهات التوظيف والفوترة بالـ frontend مطابق لحمولة الخادم."""

    def setUp(self):
        cache.clear()

        self.superadmin = User.objects.create_user(
            username="contract_superadmin",
            email="superadmin@ktra.local",
            is_staff=True,
            is_superuser=True,
        )

        self.recruiter_user = User.objects.create_user(
            username="contract_recruiter",
            email="recruiter@ktra.local",
            first_name="منى",
            last_name="التوظيف",
        )
        self.recruiter = PlatformRecruiter.objects.create(
            user=self.recruiter_user,
            is_active=True,
        )

        self.tenant = Tenant.objects.create(
            TenantID=8801,
            CompanyName="شركة عقد الفوترة والتوظيف",
        )
        self.owner = User.objects.create_user(
            username="contract_billing_owner",
            email="owner@billing.local",
        )
        UserCompanyMembership.objects.create(
            user=self.owner,
            tenant=self.tenant,
            role="manager",
        )

        self.currency, _ = Currency.objects.get_or_create(
            Code="ILS",
            defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        self.partner = Partner.objects.create(
            tenant=self.tenant,
            name="عميل الفوترة",
            partner_type="Customer",
        )

        self.sub = ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            monthly_fee=Decimal("200.00"),
            included_quota=100,
            consumed_quota=130,
            overage_unit_price=Decimal("3.00"),
            billing_customer=self.partner,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
        )

        self.invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number="INV-CONTRACT-8801",
            customer=self.partner,
            invoice_date=datetime.date(2026, 8, 31),
            currency=self.currency,
        )

        self.billing_record = SubscriptionBillingRecord.objects.create(
            subscription=self.sub,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            invoice=self.invoice,
            monthly_fee=Decimal("200.00"),
            included_quota=100,
            consumed_quota=130,
            overage_units=30,
            overage_unit_price=Decimal("3.00"),
            overage_fee=Decimal("90.00"),
            total_amount=Decimal("290.00"),
        )

        self.policy_profile = PolicyProfile.objects.create(
            name="محاسب منصة تجريبي",
            specialty="accountant",
            is_active=True,
        )

        self.job = create_job_posting(
            title="محاسب تكاليف متقدم",
            specialty="accountant",
            description="وصف الوظيفة",
            requirements="شروط الوظيفة",
            location="عمان",
            employment_type=JobPosting.EmploymentType.FULL_TIME,
            salary_range="600-800",
            created_by=self.superadmin,
        )

        self.applicant = JobApplicant.objects.create(
            job=self.job,
            name="طارق المرشح",
            phone="0799999999",
            email="tareq@applicant.local",
            about="سيرة مختصرة",
            status=JobApplicant.Status.OFFERED,
        )

        self.super_client = APIClient()
        self.super_client.force_authenticate(user=self.superadmin)

        self.owner_client = APIClient()
        self.owner_client.force_authenticate(user=self.owner)
        self.owner_client.credentials(HTTP_X_TENANT_ID=str(self.tenant.pk))

        self.public_client = APIClient()

    def _assert_declared_fields_exist(self, *, interface: str, declared: set[str], actual, note: str = ""):
        self.assertTrue(
            declared,
            f"لم يُعثَر على `interface {interface}` — هل أُعيدت تسميتُه؟",
        )
        missing = declared - set(actual)
        self.assertEqual(
            missing,
            set(),
            f"`{interface}` يعلن حقولاً لا يرسلها الخادم: {sorted(missing)}. {note}",
        )

    def test_hiring_and_billing_interfaces_match_real_payloads(self):
        """فحص جميع واجهات التوظيف والفوترة الـ ١٣ مقابل حمولات الخادم الحقيقية."""
        hiring_src = HIRING_API.read_text(encoding="utf-8")
        my_agent_src = MY_AGENT_API.read_text(encoding="utf-8")
        ops_src = OPS_API.read_text(encoding="utf-8")

        # 1. PlatformStaffCapabilities
        resp = self.super_client.get("/api/platform-staff/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self._assert_declared_fields_exist(
            interface="PlatformStaffCapabilities",
            declared=_interface_fields(hiring_src, "PlatformStaffCapabilities"),
            actual=resp.data.keys(),
        )

        # 2. PlatformJobPosting
        resp = self.super_client.get("/api/platform/ops/job-postings/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        jobs = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertTrue(jobs, "لا توجد وظائف في الاستجابة")
        self._assert_declared_fields_exist(
            interface="PlatformJobPosting",
            declared=_interface_fields(hiring_src, "PlatformJobPosting"),
            actual=jobs[0].keys(),
        )

        # 3. PlatformJobApplicant & 4. ApplicantNextStatus
        resp = self.super_client.get("/api/platform/ops/job-applicants/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        applicants = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertTrue(applicants, "لا يوجد متقدمون في الاستجابة")
        self._assert_declared_fields_exist(
            interface="PlatformJobApplicant",
            declared=_interface_fields(hiring_src, "PlatformJobApplicant"),
            actual=applicants[0].keys(),
        )
        self.assertTrue(applicants[0]["next_statuses"], "قائمة next_statuses فارغة")
        self._assert_declared_fields_exist(
            interface="ApplicantNextStatus",
            declared=_interface_fields(hiring_src, "ApplicantNextStatus"),
            actual=applicants[0]["next_statuses"][0].keys(),
        )

        # 5. ApplicantInvitation
        resp = self.super_client.post(
            f"/api/platform/ops/job-applicants/{self.applicant.pk}/invite/",
            {"expires_in_hours": 48},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self._assert_declared_fields_exist(
            interface="ApplicantInvitation",
            declared=_interface_fields(hiring_src, "ApplicantInvitation"),
            actual=resp.data.keys(),
        )
        invitation_token = resp.data["token"]

        # 6. PlatformRecruiter
        resp = self.super_client.get("/api/platform/ops/recruiters/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        recruiters = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertTrue(recruiters, "لا يوجد مسؤولو توظيف في الاستجابة")
        self._assert_declared_fields_exist(
            interface="PlatformRecruiter",
            declared=_interface_fields(hiring_src, "PlatformRecruiter"),
            actual=recruiters[0].keys(),
        )

        # 7. PublicPlatformJob
        resp = self.public_client.get(f"/api/careers/jobs/{self.job.token}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self._assert_declared_fields_exist(
            interface="PublicPlatformJob",
            declared=_interface_fields(hiring_src, "PublicPlatformJob"),
            actual=resp.data.keys(),
        )

        # 8. PublicApplicationReceipt
        resp = self.public_client.post(
            f"/api/careers/jobs/{self.job.token}/apply/",
            {
                "name": "متقدم جديد للعقد",
                "phone": "0788888888",
                "email": "applicant.contract@ktra.local",
                "about": "معلومات إضافية",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self._assert_declared_fields_exist(
            interface="PublicApplicationReceipt",
            declared=_interface_fields(hiring_src, "PublicApplicationReceipt"),
            actual=resp.data.keys(),
        )

        # 9. PublicInvitationDetail
        resp = self.public_client.get(f"/api/careers/invitations/{invitation_token}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self._assert_declared_fields_exist(
            interface="PublicInvitationDetail",
            declared=_interface_fields(hiring_src, "PublicInvitationDetail"),
            actual=resp.data.keys(),
        )

        # 10. InvitationAcceptance
        resp = self.public_client.post(
            f"/api/careers/invitations/{invitation_token}/accept/",
            {
                "password": "ValidPassword998!",
                "username": "accepted_candidate",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self._assert_declared_fields_exist(
            interface="InvitationAcceptance",
            declared=_interface_fields(hiring_src, "InvitationAcceptance"),
            actual=resp.data.keys(),
        )

        # 11. PolicyProfileOption
        resp = self.super_client.get("/api/platform/ops/policy-profiles/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        profiles = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertTrue(profiles, "لا توجد ملفات سياسة في الاستجابة")
        self._assert_declared_fields_exist(
            interface="PolicyProfileOption",
            declared=_interface_fields(hiring_src, "PolicyProfileOption"),
            actual=profiles[0].keys(),
        )

        # 12. QuotaUsage
        resp = self.owner_client.get("/api/my-agent/quota/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self._assert_declared_fields_exist(
            interface="QuotaUsage",
            declared=_interface_fields(my_agent_src, "QuotaUsage"),
            actual=resp.data.keys(),
        )

        # 13. SubscriptionBillingRecordRow
        resp = self.super_client.get("/api/platform/ops/billing-records/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        records = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertTrue(records, "لا توجد سجلات فوترة في الاستجابة")
        self._assert_declared_fields_exist(
            interface="SubscriptionBillingRecordRow",
            declared=_interface_fields(ops_src, "SubscriptionBillingRecordRow"),
            actual=records[0].keys(),
        )

    def test_frontend_hiring_options_match_backend_choices(self):
        """ج١. مطابقة خيارات حالات المتقدمين وأنواع الدوام في الواجهة لتسميات الخادم choices بالتساوي."""
        self.assertTrue(HIRING_UTIL.exists(), f"ملف الواجهة {HIRING_UTIL} غير موجود")
        util_src = HIRING_UTIL.read_text(encoding="utf-8")

        def _extract_options(source: str, const_name: str) -> list[tuple[str, str]]:
            pattern = rf"export\s+const\s+{const_name}\s*=\s*\[(.*?)\]\s*(?:as\s*const)?;"
            match = re.search(pattern, source, re.DOTALL)
            if not match:
                return []
            block = match.group(1)
            item_pattern = r"\{\s*value:\s*['\"]([^'\"]+)['\"]\s*,\s*label:\s*['\"]([^'\"]+)['\"]\s*\}"
            return re.findall(item_pattern, block)

        applicant_status_options = _extract_options(util_src, "APPLICANT_STATUS_OPTIONS")
        employment_type_options = _extract_options(util_src, "EMPLOYMENT_TYPE_OPTIONS")

        backend_status_choices = list(JobApplicant.Status.choices)
        backend_employment_choices = list(JobPosting.EmploymentType.choices)

        self.assertEqual(
            applicant_status_options,
            backend_status_choices,
            f"خيارات حالات المتقدمين في الواجهة لا تطابق خيارات الخادم: {applicant_status_options} != {backend_status_choices}",
        )
        self.assertEqual(
            employment_type_options,
            backend_employment_choices,
            f"خيارات أنواع الدوام في الواجهة لا تطابق خيارات الخادم: {employment_type_options} != {backend_employment_choices}",
        )

