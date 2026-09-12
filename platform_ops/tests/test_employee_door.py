"""بابُ موظّف المنصّة — من رابط الدعوة إلى مساحته (211-A · 211-B).

ثلاثُ عُقَدٍ كانت تقطع الطريقَ على موظّفٍ عُيِّن للتوّ، وهذا الملفُّ يحرسُ فكَّ اثنتين
منها (الثالثةُ في `App.tsx` وهي خارجَ هذه الدفعة):

1. **قبولُ الدعوة كان يردّ اسمَ المستخدم ولا يردّ جلسة.** فيُنشأ الحسابُ ثمّ يُترك
   صاحبُه أمام بابٍ لا يعرف مكانَه. صار القبولُ يُصدر الجلسةَ بالمسار نفسِه الذي
   يسلكه الدخولُ العادي (`hr.auth_api.issue_login_session`) لا بنسخةٍ ثانيةٍ منه.
2. **والخادمُ يقبل اسمَ المستخدم في الدخول، والواجهةُ كانت تمنع كتابتَه**: حقلُ
   `type="email"` داخلَ `<form>` يجعل المتصفّحَ نفسَه يرفض إرسالَ قيمةٍ ليست بريداً،
   فاسمُ المستخدم الذي تطلبه شاشةُ الدعوة لا يمكن استعمالُه أصلاً. والحارسُ هنا
   ساكنٌ بالضرورة: `npm test` يشغّل `utils/*.test.ts` بـ`node --test` ولا يُصيّر
   مكوّناً واحداً، فلا اختبارَ ديناميكيٌّ يرى خاصيّةَ JSX.
"""
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from hr.models import UserDevice
from platform_ops.models import JobApplicant, PlatformEmployee
from platform_ops.services import create_applicant_invitation, create_job_posting

User = get_user_model()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOGIN_PAGE = REPO_ROOT / "frontend_v2" / "components" / "LoginPage.tsx"
INVITATION_PAGE = (
    REPO_ROOT / "frontend_v2" / "components" / "platform-hiring" / "PlatformInvitationPage.tsx"
)
ROUTER = REPO_ROOT / "frontend_v2" / "index.tsx"
STAFF_LOGIN = REPO_ROOT / "frontend_v2" / "components" / "platform" / "StaffLoginPage.tsx"
LANDING_PAGE = REPO_ROOT / "frontend_v2" / "components" / "LandingPage.tsx"
PUBLIC_NAVBAR = REPO_ROOT / "frontend_v2" / "components" / "layout" / "PublicNavbar.tsx"


class InvitationAcceptanceIssuesSessionTest(TestCase):
    """القبولُ يُدخِل صاحبَه، لا يكتفي بإخباره أنّ حسابَه أُنشئ."""

    def setUp(self):
        cache_free_admin = User.objects.create_user(
            username="ops_admin_door",
            email="ops_admin_door@platform.local",
            password="AdminPass2026!",
            is_superuser=True,
            is_staff=True,
        )
        self.admin_user = cache_free_admin
        self.job = create_job_posting(
            title="مُدخل بيانات",
            specialty="operations",
            description="إدخالُ مستندات الزبائن ومراجعتُها.",
            created_by=self.admin_user,
        )
        self.applicant = JobApplicant.objects.create(
            job=self.job,
            name="ليان عوض",
            phone="0599000111",
            email="layan@platform.local",
            reference_code="REF-DOOR-01",
            status=JobApplicant.Status.OFFERED,
        )
        _, self.raw_token = create_applicant_invitation(
            applicant=self.applicant,
            created_by=self.admin_user,
        )
        self.client = APIClient()

    def _accept(self, username="layan_ops", password="SecurePassword2026!"):
        return self.client.post(
            f"/api/careers/invitations/{self.raw_token}/accept/",
            {"username": username, "password": password},
            format="json",
        )

    def test_accept_returns_a_token_that_actually_authenticates(self):
        """الرمزُ العائدُ يفتح نقطةً مصادَقاً عليها فوراً — لا يُطلَب دخولٌ ثانٍ."""
        response = self._accept()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        token = response.data.get("token")
        self.assertTrue(token, "قبولُ الدعوة لم يُصدر رمزَ جلسة.")

        probe = APIClient()
        probe.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        me = probe.get("/api/platform-staff/me/")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        # والجلسةُ لصاحبها لا لغيره: الموظّفُ المُنشأُ للتوّ يُعرَف موظّفَ منصّة.
        self.assertTrue(me.data.get("is_platform_employee"))
        self.assertFalse(me.data.get("is_platform_admin"))

    def test_accept_registers_the_device_for_the_new_user(self):
        """الجلسةُ جهازٌ مسجَّلٌ باسم صاحبِ الحساب الجديد، لا رمزٌ طليق."""
        response = self._accept()
        user = User.objects.get(username="layan_ops")
        device = UserDevice.objects.get(key=response.data["token"])
        self.assertEqual(device.user_id, user.pk)
        self.assertIsNotNone(device.last_active_at)

    def test_accept_payload_carries_the_user_the_frontend_stores(self):
        """الحمولةُ تحمل `user.id` لأنّ الواجهةَ تخزّنه مع الرمز كما تفعل عند الدخول."""
        response = self._accept()
        payload_user = response.data.get("user") or {}
        user = User.objects.get(username="layan_ops")
        self.assertEqual(str(payload_user.get("id")), str(user.pk))
        self.assertEqual(payload_user.get("email"), "layan@platform.local")
        # ولا يُرقّى الموظّفُ الجديد إلى مدير بأيّ حال.
        self.assertFalse(payload_user.get("isSuperAdmin", False))

    def test_a_consumed_invitation_issues_no_second_session(self):
        """الرابطُ يُستهلَك مرّةً: محاولةٌ ثانيةٌ ترد 410 بلا رمزٍ جديد."""
        self.assertEqual(self._accept().status_code, status.HTTP_200_OK)
        devices_after_first = UserDevice.objects.count()

        again = self._accept(username="layan_ops_2")
        self.assertEqual(again.status_code, status.HTTP_410_GONE)
        self.assertIsNone(again.data.get("token"))
        self.assertEqual(UserDevice.objects.count(), devices_after_first)


class HiredEmployeeCanLogInWithTheUsernameTest(TestCase):
    """ما تطلبه شاشةُ الدعوة (اسمُ مستخدم) يجب أن يعمل في شاشة الدخول."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rami_ops",
            email="rami@platform.local",
            password="SecurePassword2026!",
        )
        PlatformEmployee.objects.create(
            user=self.user,
            specialty="operations",
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.client = APIClient()

    def _login(self, identifier):
        return self.client.post(
            "/api/hr/auth/login/",
            {"email": identifier, "password": "SecurePassword2026!"},
            format="json",
        )

    def test_login_accepts_the_username(self):
        response = self._login("rami_ops")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json().get("token"))

    def test_login_still_accepts_the_email(self):
        response = self._login("rami@platform.local")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json().get("token"))


class EmployeeDoorFrontendContractTest(SimpleTestCase):
    """حارسٌ ساكنٌ على الواجهة — `npm test` لا يُصيّر مكوّناً فلا يرى شيئاً من هذا."""

    def test_login_identifier_field_is_not_typed_as_email(self):
        """`type="email"` على حقل الهويّة يجعل المتصفّحَ يرفض اسمَ المستخدم قبل الإرسال."""
        source = LOGIN_PAGE.read_text(encoding="utf-8")
        # **يُفحَص العنصرُ لا الملفُّ**: البحثُ عن النصّ في الملفّ كلِّه يصطاد
        # التعليقَ الذي يشرح لماذا لا يجوز النوع، فيسقط الاختبارُ على وجود شرحه.
        blocks = [chunk for chunk in source.split("<input") if "value={email}" in chunk]
        self.assertEqual(len(blocks), 1, "لم أجد حقلَ الهويّة الوحيد في شاشة الدخول.")
        # `assertFalse` لا `assertNotIn`: الثانيةُ تطبع المقطعَ كلَّه في رسالة الفشل.
        self.assertFalse(
            'type="email"' in blocks[0].split(">")[0],
            "حقلُ الدخول عاد إلى `type=\"email\"` — المتصفّحُ سيمنع اسمَ المستخدم "
            "الذي تُنشئه دعوةُ التوظيف من الإرسال أصلاً.",
        )

    def test_login_label_names_both_accepted_identifiers(self):
        """الخادمُ يقبل الاثنين (`Q(username) | Q(email)`) فالتسميةُ تقول ذلك صراحةً."""
        source = LOGIN_PAGE.read_text(encoding="utf-8")
        self.assertTrue(
            "اسم المستخدم" in source,
            "تسميةُ حقل الدخول لا تذكر اسمَ المستخدم رغم أنّ الخادمَ يقبله.",
        )

    def test_invitation_page_persists_the_session_it_receives(self):
        """شاشةُ الدعوة تخزّن الرمزَ والمعرّفَ بمفتاحَي الدخول نفسِهما، وإلا ضاعت الجلسة."""
        source = INVITATION_PAGE.read_text(encoding="utf-8")
        for key in ('"token"', '"userId"'):
            self.assertTrue(
                key in source,
                f"شاشةُ الدعوة لا تكتب {key} — الجلسةُ العائدةُ من القبول تُهدَر.",
            )
        self.assertTrue(
            re.search(r"localStorage\.setItem", source),
            "شاشةُ الدعوة لا تحفظ الجلسة في التخزين المحلّي.",
        )

class StaffLoginRouteIsPrivateTest(SimpleTestCase):
    """بابُ `/staff` موجودٌ ويوصل إلى مساحة الموظّف — **وغيرُ معلَنٍ في أيّ سطحٍ عامّ** (211-C)."""

    def test_the_route_is_registered(self):
        router = ROUTER.read_text(encoding="utf-8")
        self.assertTrue(
            'path="/staff"' in router,
            "مسارُ `/staff` غير مسجَّلٍ في `frontend_v2/index.tsx`.",
        )

    def test_the_route_sits_outside_the_provider_tree(self):
        """كبقيّةِ الصفحات القائمة بذاتها: لو دخل شجرةَ المزوّدات لابتلعه حارسُ الشركة."""
        router = ROUTER.read_text(encoding="utf-8")
        line = next(ln for ln in router.splitlines() if 'path="/staff"' in ln)
        for provider in ("ApplicationBoundary", "CompanyProvider", "AuthProvider"):
            self.assertFalse(
                provider in line,
                f"مسارُ `/staff` لُفَّ بـ{provider} — سيبتلعه حارسُ الشركة قبل أن يُرسَم.",
            )

    def test_the_page_lands_the_employee_on_their_own_space(self):
        page = STAFF_LOGIN.read_text(encoding="utf-8")
        self.assertTrue(
            "/platform/employee-space" in page,
            "بابُ الفريق لا يوصل إلى مساحة الموظّف.",
        )
        # والوجهةُ تُقرَّر بجواب الخادم لا بتخمينٍ من الواجهة.
        self.assertTrue("getPlatformStaffCapabilities" in page)

    def test_the_route_is_not_advertised_on_any_public_surface(self):
        """«خصوصيّ» شرطٌ يُفحَص: ذكرُه في الهبوط أو الشريط العامّ يُبطل الغرض."""
        for name, file in (("صفحة الهبوط", LANDING_PAGE), ("الشريط العام", PUBLIC_NAVBAR)):
            self.assertFalse(
                "/staff" in file.read_text(encoding="utf-8"),
                f"مسارُ `/staff` صار معلَناً في {name} — والمالكُ طلبه خصوصيّاً.",
            )

    def test_platform_space_is_exempt_from_the_company_gate(self):
        """موظّفٌ بلا عضويّةِ شركةٍ يجب ألاّ يُطلَب منه إنشاءُ شركة."""
        router = ROUTER.read_text(encoding="utf-8")
        self.assertTrue(
            "platformTenantlessPath" in router,
            "حارسُ الشركة في `ApplicationBoundary` ما زال يبتلع مساراتِ المنصّة.",
        )
        self.assertTrue("'/platform/employee-space'" in router)
