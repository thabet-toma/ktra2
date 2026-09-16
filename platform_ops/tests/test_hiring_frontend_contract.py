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
    ApplicantMeeting,
    ApplicantMeetingAttendee,
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
        """فحص جميع واجهات التوظيف والفوترة الـ ١٥ مقابل حمولات الخادم الحقيقية."""
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

        # 14. ApplicantMeeting + 15. ApplicantMeetingAttendee (212-S1)
        meeting = ApplicantMeeting.objects.create(
            title="مقابلة الدفعة الأولى",
            start=timezone.now() + datetime.timedelta(days=1),
            end=timezone.now() + datetime.timedelta(days=1, hours=1),
        )
        ApplicantMeetingAttendee.objects.create(meeting=meeting, guest_name="ضيفٌ بتوصية")
        resp = self.super_client.get("/api/platform/ops/applicant-meetings/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        meetings = (
            resp.data["results"]
            if isinstance(resp.data, dict) and "results" in resp.data
            else resp.data
        )
        self.assertTrue(meetings, "لا اجتماعات في الاستجابة")
        self._assert_declared_fields_exist(
            interface="ApplicantMeeting",
            declared=_interface_fields(hiring_src, "ApplicantMeeting"),
            actual=meetings[0].keys(),
        )
        self.assertTrue(meetings[0]["attendees"], "الاجتماعُ عاد بلا حاضرين")
        self._assert_declared_fields_exist(
            interface="ApplicantMeetingAttendee",
            declared=_interface_fields(hiring_src, "ApplicantMeetingAttendee"),
            actual=meetings[0]["attendees"][0].keys(),
        )

        # 16. شبكةُ الحضور: المصفوفةُ وعمودُها وصفُّها وخليّتُها (#213-ج).
        # **إسقاطٌ مبنيٌّ بيدٍ لا مُسلسِلُ نموذج**: حقلٌ يُعاد تسميتُه في الخدمة لا
        # يسقط له اختبارُ مُسلسِل، والشبكةُ كلُّها تُصيَّر من هذه المفاتيح.
        resp = self.super_client.get(
            "/api/platform/ops/applicant-meetings/attendance-matrix/"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self._assert_declared_fields_exist(
            interface="ApplicantAttendanceMatrix",
            declared=_interface_fields(hiring_src, "ApplicantAttendanceMatrix"),
            actual=resp.data.keys(),
        )
        self.assertTrue(resp.data["meetings"], "الشبكةُ عادت بلا أعمدة")
        self._assert_declared_fields_exist(
            interface="ApplicantAttendanceColumn",
            declared=_interface_fields(hiring_src, "ApplicantAttendanceColumn"),
            actual=resp.data["meetings"][0].keys(),
        )
        self.assertTrue(resp.data["rows"], "الشبكةُ عادت بلا صفوف")
        self._assert_declared_fields_exist(
            interface="ApplicantAttendanceRow",
            declared=_interface_fields(hiring_src, "ApplicantAttendanceRow"),
            actual=resp.data["rows"][0].keys(),
        )
        first_cell = next(iter(resp.data["rows"][0]["cells"].values()))
        self._assert_declared_fields_exist(
            interface="ApplicantAttendanceCell",
            declared=_interface_fields(hiring_src, "ApplicantAttendanceCell"),
            actual=first_cell.keys(),
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


MATRIX_UI = REPO_ROOT / "frontend_v2" / "components" / "platform-hiring" / "ApplicantAttendanceMatrix.tsx"
MEETINGS_TAB = REPO_ROOT / "frontend_v2" / "components" / "platform-hiring" / "PlatformMeetingsTab.tsx"
APPLICANTS_TAB = REPO_ROOT / "frontend_v2" / "components" / "platform-hiring" / "PlatformApplicantsTab.tsx"
HIRING_SCREEN = REPO_ROOT / "frontend_v2" / "components" / "platform-hiring" / "PlatformHiringScreen.tsx"

#: أصنافُ القشرة الفاتحة: تختفي أو تُقرأ بالكاد فوق الكحليّ. المطابقةُ على
#: **الرمز كاملاً** (`fullmatch` بعد `split` ونزعِ سوابقِ التنويع) لا بحدودِ
#: كلماتٍ نمطيّة — كُتب هذا الحارسُ أوّلَ مرّةٍ بحدِّ كلمةٍ فأكلت الكتابةُ الشرطةَ
#: وصار في المصدر محرفُ تراجعٍ حقيقيّ، فما طابق شيئاً قطّ: تأكيدٌ لا يستطيع
#: السقوط. أُمسك بحقنِ `bg-white` عمداً والتحقّقِ من سقوطه.
LIGHT_SKIN_CLASS = re.compile(
    r"(bg-white|bg-slate-(50|100|200)|text-slate-[5-9]00"
    r"|text-amber-[6-9]00|border-slate-[12]00)"
)

#: سوابقُ التنويع تُنزع قبل المطابقة: `hover:bg-white` أبيضُ أيضاً عند التحويم،
#: و`sm:` و`focus:` مثلُها — ولولا النزعُ لمرّ الفاتحُ متخفّياً خلف سابقة.
VARIANT_PREFIX = re.compile(r"^([a-z0-9-]+:)+")

#: شاشاتُ التوظيف التي **يراها موظّفُ المنصّة** فتلبس الجلدَ الداكن. وما ليس
#: فيها يراه المتقدّمُ للوظيفة (`PlatformPublicJobPage` · `PlatformInvitationPage`
#: · `PublicApplicantTrackingPanel`) فيبقى فاتحاً بقرارِ علامةٍ تجاريّة — ولذلك
#: تُسمّى هنا بأسمائها ولا يُمسَح المجلّدُ كلُّه بـglob.
OPERATOR_HIRING_SCREENS = (
    "PlatformHiringScreen.tsx",
    "PlatformJobsTab.tsx",
    "PlatformApplicantsTab.tsx",
    "PlatformApplicantPanel.tsx",
    "PlatformMeetingsTab.tsx",
    "PlatformMeetingDetail.tsx",
    "PlatformRecruitersTab.tsx",
    "ApplicantAttendanceMatrix.tsx",
)


class TheAttendanceGridSaysTheTruthTest(TestCase):
    """شبكةُ الحضور (#213-ج): تقول عن كلِّ شخصٍ ما يقوله الخادم، وتُفتَح في كلّ مرّة.

    **كلُّ تأكيدٍ هنا مكتوبٌ على عطبٍ وقع فعلاً** في تسليم الواجهة ومُثبَتٌ سقوطُه
    عليه قبل الإصلاح، أبرزُها:

    ١. `attendanceIcon` قارنت النصَّ الحرَّ `"ATTENDED"`/`"ABSENT"` وقيمُ الخادم
       صغيرة، فكانت المقارنتان كاذبتين دائماً و**كلُّ خليّةٍ ترسم ساعةَ «مدعوّ»** —
       أي أنّ الشبكةَ التي وُجدت لتُقرأ نظرةً واحدةً كانت تقول الشيءَ نفسَه عن
       الجميع. و`tsc` صامتٌ لأنّ حقلَ الحالة كان `string`.
    ٢. طلبُ الفتح كان يُلجَم بمتغيّرٍ يتذكّر آخرَ معرّفٍ نُفِّذ، فالضغطةُ الثانية
       على الاسم نفسِه تنقل التبويبَ ولا تفتح شيئاً.
    ٣. البحثُ الذي طلبه المالكُ نصّاً لم يكن موجوداً، وفتحُ اجتماعٍ كان يفكّك
       الشبكةَ فيضيع المدى، واليومُ المعروضُ كان يومَ UTC لا يومَ القارئ.
    """

    def setUp(self):
        self.matrix_src = MATRIX_UI.read_text(encoding="utf-8")
        self.api_src = HIRING_API.read_text(encoding="utf-8")
        self.screen_src = HIRING_SCREEN.read_text(encoding="utf-8")
        self.applicants_src = APPLICANTS_TAB.read_text(encoding="utf-8")
        self.meetings_src = MEETINGS_TAB.read_text(encoding="utf-8")

    def _backend_statuses(self) -> list[str]:
        return [value for value, _label in ApplicantMeetingAttendee.Status.choices]

    def test_every_backend_status_has_its_own_icon(self):
        """لكلّ حالةِ حضورٍ في الخادم مفتاحٌ في `ATTENDANCE_ICON` بحروفها نفسِها."""
        match = re.search(
            r"const ATTENDANCE_ICON: Record<ApplicantAttendanceStatus, React\.ReactNode> = \{(.*?)\n\};",
            self.matrix_src,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "شبكةُ الحضور لا تحمل خريطةَ أيقوناتٍ شاملةً على النوع "
            "(`Record<ApplicantAttendanceStatus, React.ReactNode>`) — وبغيرها "
            "تعود مقارنةُ النصّ الحرّ التي جعلت كلَّ خليّةٍ ترسم الأيقونةَ نفسَها",
        )
        keys = re.findall(r"^\s{2}(\w+):", match.group(1), re.MULTILINE)
        self.assertEqual(
            sorted(keys),
            sorted(self._backend_statuses()),
            "مفاتيحُ `ATTENDANCE_ICON` لا تطابق قيمَ "
            "`ApplicantMeetingAttendee.Status` حرفاً بحرف — خليّةٌ بلا أيقونتها",
        )
        for icon in ("Check", "X", "Clock"):
            self.assertEqual(
                match.group(1).count(f"<{icon} "),
                1,
                f"الأيقونة `{icon}` تتكرّر أو تغيب في `ATTENDANCE_ICON` — "
                "حالتان متمايزتان ترسمان الشكلَ نفسَه",
            )

    def test_the_cell_status_is_a_union_not_a_free_string(self):
        """حقلُ الحالة نوعٌ مُغلَقٌ في `platformHiringApi.ts` كي يمسك `tsc` الخطأَ القادم."""
        declared = re.search(
            r'export type ApplicantAttendanceStatus = ([^;]+);',
            self.api_src,
        )
        self.assertIsNotNone(declared, "لا يوجد نوعٌ مُغلَقٌ لحالة الحضور")
        members = sorted(re.findall(r'"([^"]+)"', declared.group(1)))
        self.assertEqual(
            members,
            sorted(self._backend_statuses()),
            "أعضاءُ `ApplicantAttendanceStatus` لا تطابق حالاتِ الخادم",
        )
        for interface in ("ApplicantAttendanceCell", "ApplicantMeetingAttendee"):
            body = re.search(
                rf"export interface {interface} \{{(.*?)\n\}}",
                self.api_src,
                re.DOTALL,
            )
            self.assertIsNotNone(body, f"واجهة {interface} غير موجودة")
            self.assertIn(
                "status: ApplicantAttendanceStatus;",
                body.group(1),
                f"حالةُ {interface} ما زالت `string` — فمقارنةٌ بحروفٍ خاطئةٍ "
                "تمرّ صامتةً من `tsc` كما مرّت أوّلَ مرّة",
            )

    def test_opening_the_same_applicant_twice_still_opens_him(self):
        """طلبُ الفتح يُفرَغ بعد تنفيذه، فلا يُلجَم بتذكُّرِ آخرِ معرّف."""
        self.assertNotIn(
            "handledFocusApplicantId",
            self.applicants_src,
            "عاد اللجامُ الذي يجعل الضغطةَ الثانية على الاسم نفسِه بلا أثر",
        )
        self.assertIn(
            "onFocusHandled?.();",
            self.applicants_src,
            "تبويبُ المتقدّمين لا يُبلغ الأبَ بأنّ الطلبَ نُفِّذ",
        )
        self.assertRegex(
            self.screen_src,
            r"onFocusHandled=\{handleApplicantFocusHandled\}",
            "شاشةُ التوظيف لا تمرّر مُفرِغَ الطلب",
        )
        self.assertRegex(
            self.screen_src,
            r"const handleApplicantFocusHandled = useCallback\(\(\) => setApplicantFocus\(null\), \[\]\)",
            "الأبُ لا يُفرِغ `applicantFocus` بعد التنفيذ — فيبقى المعرّفُ عالقاً",
        )

    def test_every_handle_in_the_grid_is_a_real_button(self):
        """«كلّ شي كليكبل»: الاجتماعُ والخليّةُ والاسمُ أزرارٌ لا نصوصٌ عليها `onClick`."""
        for handler in (
            r"onOpenMeeting\(meeting\.id\)",
            r"onOpenMeeting\(cell\.meeting\)",
            r"onOpenApplicant\(row\.applicant\)",
        ):
            self.assertRegex(
                self.matrix_src,
                rf"<button[^<]*{handler}",
                f"المقبضُ {handler} ليس داخلَ <button> — لا يصله لوحُ المفاتيح",
            )
        self.assertRegex(
            self.meetings_src,
            r"onOpenApplicant=\{onOpenApplicant\}",
            "تبويبُ الاجتماعات لا يمرّر فتحَ ملفّ المتقدّم إلى الشبكة",
        )

    def test_the_grid_has_the_search_the_owner_asked_for(self):
        """«وابحث بالاحترافي» — حقلُ بحثٍ في الشبكة، بدالّة التصفية المشتركة نفسِها."""
        self.assertIn(
            'type="search"',
            self.matrix_src,
            "شبكةُ الحضور بلا حقلِ بحث — والمالكُ طلبه نصّاً: «وابحث بالاحترافي»",
        )
        self.assertIn(
            "filterPlatformApplicants(matrix?.rows ?? [], search)",
            self.matrix_src,
            "الشبكةُ تصفّي بقاعدةٍ خاصّةٍ بها لا بـ`filterPlatformApplicants` "
            "المشتركة المختبَرة — قاعدتا بحثٍ تفترقان",
        )
        self.assertIn(
            "visibleRows.map((row)",
            self.matrix_src,
            "الجدولُ يرسم `matrix.rows` كلَّها ويتجاهل نتيجةَ البحث",
        )

    def test_the_grid_survives_opening_a_meeting(self):
        """فتحُ اجتماعٍ يُخفي الشبكةَ ولا يفكّكها — وإلا ضاع المدى والعرضُ عند العودة."""
        self.assertNotIn(
            "if (selectedMeeting) {",
            self.meetings_src,
            "عادت العودةُ المبكّرة التي تفكّك الشبكةَ فتمحو مدى التواريخ "
            "وتُرجع العرضَ إلى «قائمة»",
        )
        self.assertIn(
            "hidden={selectedMeeting !== null}",
            self.meetings_src,
            "جسمُ التبويب لا يُخفى بل يُستبدَل — فتُفقَد حالةُ الشبكة",
        )
        self.assertIn(
            "refreshToken={gridRefresh}",
            self.meetings_src,
            "الشبكةُ الباقيةُ مركَّبةً لا تُعاد قراءتُها بعد تسجيل حضورٍ في "
            "تفصيل الاجتماع — فتعرض خلايا قديمة",
        )
        self.assertIn(
            "setGridRefresh((token) => token + 1);",
            self.meetings_src,
            "العودةُ من تفصيل الاجتماع لا تطلب تحديثَ الشبكة",
        )

    def test_the_focus_waits_for_the_unfiltered_list(self):
        """لا يُبحَث عن المطلوب في نتيجةِ فلترٍ قديم، فيُعلَن مفقوداً وهو موجود."""
        self.assertIn(
            "setLoadedFilters({ job: jobFilter, status: statusFilter });",
            self.applicants_src,
            "لا يُسجَّل أيُّ فلترٍ أنتج القائمةَ المحمَّلة",
        )
        self.assertIn(
            "if (loadedFilters.job || loadedFilters.status) return;",
            self.applicants_src,
            "أثرُ الفتح يقرأ القائمةَ قبل أن تصلها الفلاترُ المُفرَغة — "
            "فيرى نتيجةَ الفلتر القديم ويعلن المتقدّمَ مفقوداً ثمّ يُلغي الطلب",
        )

    def test_the_meeting_day_is_the_readers_day_not_utc(self):
        """عمودُ الشبكة يعرض يومَ القارئ — لا يومَ UTC المقتطَعَ من النصّ."""
        self.assertIn(
            "const meetingDay = (start: string): string => formatDateValue(new Date(start));",
            self.matrix_src,
            "يومُ العمود لا يمرّ بـ`Date` — فاجتماعُ آخرِ الليل يظهر في الشبكة "
            "بيومٍ وفي قائمة الاجتماعات بيومٍ آخر",
        )
        self.assertNotIn(
            "formatDateValue(meeting.start)",
            self.matrix_src,
            "ما زال يُقتطع النصُّ ISO مباشرةً ليوم العمود",
        )

    def test_the_meeting_status_is_a_union_too(self):
        """حالةُ الاجتماع نوعٌ مُغلَقٌ — العمودُ يقارنها ليُظهر الملغى."""
        declared = re.search(
            r"export type ApplicantMeetingStatus = ([^;]+);",
            self.api_src,
        )
        self.assertIsNotNone(declared, "لا يوجد نوعٌ مُغلَقٌ لحالة الاجتماع")
        self.assertEqual(
            sorted(re.findall(r'"([^"]+)"', declared.group(1))),
            sorted(value for value, _ in ApplicantMeeting.Status.choices),
            "أعضاءُ `ApplicantMeetingStatus` لا تطابق حالاتِ الخادم",
        )
        column = re.search(
            r"export interface ApplicantAttendanceColumn \{(.*?)\n\}",
            self.api_src,
            re.DOTALL,
        )
        self.assertIsNotNone(column, "واجهة عمود الشبكة غير موجودة")
        self.assertIn(
            "status: ApplicantMeetingStatus;",
            column.group(1),
            "حالةُ العمود ما زالت `string` — فمقارنةُ `!== \"scheduled\"` "
            "بحروفٍ خاطئةٍ تمرّ صامتةً من `tsc`",
        )

    def test_the_row_carries_the_applicant_status_the_server_sends(self):
        """«نظرةٌ واحدة»: حالةُ المتقدّم تُعرض في صفّه — الخادمُ يرسلها سلفاً.

        كان التأكيدُ الثاني مربوطاً باسم `applicantStatusBadgeClass` حرفيّاً،
        وتلك دالّةُ **أصنافٍ فاتحةٍ** زالت حين دخلت الشبكةُ الغلافَ الداكن —
        فكانت الشارةُ رقعةً باهتةً على الكحليّ، والحالةُ الواحدةُ يلبسها لونان
        بين هذه الشبكة وتبويب المتقدّمين. والاسمُ عَرَضٌ: المقصودُ أن **النصَّ
        الذي يرسله الخادمُ يُعرض ملوَّناً بنغمة حالته**، لا أن تُستدعى دالّةٌ
        بعينها. فيُقاس ذلك: النصُّ معروضٌ، ونغمتُه من المصدر الواحد.
        """
        self.assertIn(
            "row.applicant_status_display",
            self.matrix_src,
            "`row.applicant_status_display` غيرُ معروضٍ — حقلٌ يرسله الخادمُ "
            "ولا تستهلكه الشبكة",
        )
        self.assertIn(
            "applicantStatusTone(row.applicant_status)",
            self.matrix_src,
            "حالةُ الصفّ تُعرض بلا نغمةٍ مشتقّةٍ منها، أو بنغمةٍ من خريطةٍ "
            "محلّيّةٍ ثانيةٍ تتباعد عن `utils/platformHiring.ts`",
        )
        self.assertRegex(
            self.matrix_src,
            r"<CcPill[\s\S]{0,120}row\.applicant_status_display",
            "الشارةُ ليست `CcPill` — فألوانُها لا تتبع رموزَ القشرة الداكنة",
        )

    def test_the_applicant_row_opens_from_the_keyboard(self):
        """صفُّ المتقدّم كان `onClick` وحدَه — بابٌ للفأرة وحدَها."""
        self.assertRegex(
            self.applicants_src,
            r"<button[^<]*setSelectedApplicant\(applicant\)",
            "اسمُ المتقدّم ليس داخلَ <button> — فمن لا يستعمل الفأرةَ لا يصل "
            "إلى بطاقته أصلاً، ونقرُ الصفِّ وحدَه لا يُنقَل بلوحة المفاتيح",
        )

    def test_the_operator_hiring_screens_wear_the_dark_skin_and_keep_no_dead_light_pair(self):
        """كان هذا يفرض لكلِّ صنفٍ فاتحٍ مقابلاً `dark:` — عقدَ شاشةٍ ثنائيّةِ القشرة.

        والعقدُ **انتهى**: صارت شاشةُ التوظيف تُصيَّر داخلَ `platform-surface
        ops-shell` فهي داكنةٌ دائماً، لا تنقلب مع تفضيل النظام. فالمزاوجةُ التي
        كانت شرطَ قراءةٍ صارت نصفَ أصنافٍ ميّتاً: `text-slate-700` لا يظهر أبداً،
        و`dark:` لاحقةٌ لا تُفعَّل أبداً — وكلاهما يكذب على قارئ الملفّ بعدنا.

        فيُقاس ما صار صحيحاً: **لا صنفَ فاتحاً على سطحٍ داكنٍ، ولا لاحقةَ
        `dark:` ميّتة.** والحدُّ الأدنى للتباين يبقى محروساً بالمنع لا بالمزاوجة.
        """
        dead_pairs: list[str] = []
        light_on_dark: list[str] = []
        for name in OPERATOR_HIRING_SCREENS:
            source = (HIRING_SCREEN.parent / name).read_text(encoding="utf-8")
            for value in re.findall(r'className="([^"]*)"', source):
                for token in value.split():
                    if token.startswith("dark:"):
                        dead_pairs.append(f"{name}: {token}")
                    bare = VARIANT_PREFIX.sub("", token)
                    if LIGHT_SKIN_CLASS.fullmatch(bare):
                        light_on_dark.append(f"{name}: {token}")

        self.assertEqual(
            dead_pairs,
            [],
            f"لواحقُ `dark:` ميّتةٌ فوق سطحٍ داكنٍ دائماً: {dead_pairs}",
        )
        # أسطحٌ ونصوصٌ من القشرة الفاتحة: تختفي أو تُقرأ بالكاد فوق الكحليّ.
        self.assertEqual(
            light_on_dark,
            [],
            f"أصنافٌ من القشرة الفاتحة في شاشات التوظيف: {light_on_dark}",
        )

        # والغلافُ نفسُه شرطُ كلِّ ما سبق: بلا `ops-shell` لا رموزَ جلدٍ أصلاً.
        self.assertIn(
            "platform-surface ops-shell",
            self.screen_src,
            "شاشةُ التوظيف لا تلبس غلافَ سطح المنصّة، فترجع بيضاءَ كما كانت",
        )

    def test_the_job_filter_request_is_consumed_like_the_focus_request(self):
        """فلترُ الوظيفة طلبٌ يُنفَّذ مرّةً ثمّ يُفرَغ — لا حالةٌ تبقى عند الأب.

        بقاؤه كان يُعيد فرضَ فلترٍ قديمٍ في كلّ عودةٍ إلى التبويب بزرّه، على من
        مسحه بيده — والتبويبُ يُفصَل عند التبديل فيقرأ المعرَّفَ من جديد.
        """
        self.assertIn(
            "onJobFilterHandled?.();",
            self.applicants_src,
            "فلترُ الوظيفة لا يُبلَّغ الأبُ بتطبيقه، فيبقى معرّفُه عالقاً عنده "
            "— ثمّ لا يتغيّر فلا يشتغل الأثرُ فلا يُطبَّق الفلتر",
        )
        self.assertIn(
            "if (initialJobFilter == null) return;",
            self.applicants_src,
            "شرطُ الأثر ما زال `if (initialJobFilter)` — لا يميّز الفراغَ من الصفر",
        )
        self.assertRegex(
            self.screen_src,
            r"const handleApplicantJobFilterHandled = useCallback\(\(\) => setApplicantJobFilter\(null\), \[\]\)",
            "الأبُ لا يُفرِغ `applicantJobFilter` بعد تطبيقه",
        )
        self.assertRegex(
            self.screen_src,
            r"onJobFilterHandled=\{handleApplicantJobFilterHandled\}",
            "شاشةُ التوظيف لا تمرّر مُفرِغَ فلتر الوظيفة",
        )
