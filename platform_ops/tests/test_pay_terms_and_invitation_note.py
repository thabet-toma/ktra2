"""راتبُ الموظّف في صفحته، وشرحُ الدعوة قبل الدخول — بلاغا المالك #214-ج و#214-د.

**‏214-ج:** «بدي بصفحة الموظفين الشخصية خيار اسمو الراتب الذي يُصرف للموظف
يبيّنلو». كان الموظّف يرى حصيلةَ شهره في المحفظة ولا يرى **القاعدة** التي
تُحتسب بها: `base_salary` و`acquisition_commission_amount` محروسان بالمدير
وحدَه — فالرقمُ الذي يُصرف له مشتقٌّ من أرقامٍ لا تُعرَض عليه.

**‏214-د:** «ويبين لما يجي يوخذ رابط الانضمام قبل لا يعمل تسجيل دخول يكون نصي
ورقم لأنو ممكن يكون في شرح بالموضوع». كانت صفحةُ الدعوة أربعَ جملٍ ثابتةً ولا
موضعَ في النموذج كلِّه لكلمةٍ يكتبها المدير.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import (
    EmployeeCompensationPolicy,
    JobApplicant,
    PlatformEmployee,
)
from platform_ops.services import (
    create_applicant_invitation,
    create_job_posting,
    get_active_employee_compensation_policy,
    get_employee_pay_terms,
    resolve_public_invitation,
    submit_application,
    transition_applicant_status,
)

User = get_user_model()


def _policy(*, employee=None, version, base_salary, commission):
    return EmployeeCompensationPolicy.objects.create(
        version=version,
        status=EmployeeCompensationPolicy.Status.ACTIVE,
        employee=employee,
        base_salary=Decimal(base_salary),
        acquisition_commission_amount=Decimal(commission),
        effective_from=timezone.now() - datetime.timedelta(days=1),
        activation_reason="اختبار",
    )


class EmployeePayTermsTests(TestCase):
    """‏#214-ج — الموظّف يقرأ القاعدةَ التي يُصرف بها راتبُه، لا حصيلتَها فقط."""

    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_superuser(
            username="ops_manager", email="m@p.local", password="ManagerPass123!")
        self.user = User.objects.create_user(username="worker_one", password="WorkerPass123!")
        self.other_user = User.objects.create_user(username="worker_two", password="WorkerPass123!")
        self.employee = PlatformEmployee.objects.create(user=self.user, specialty="محاسبة")
        self.other = PlatformEmployee.objects.create(user=self.other_user, specialty="دعم")

    def _url(self, employee):
        return f"/api/platform/ops/employees/{employee.pk}/pay-terms/"

    # ── الخدمة ───────────────────────────────────────────────────────────────

    def test_without_a_published_policy_the_pilot_defaults_apply(self):
        """حالُ الـpilot قبل أوّل نشر — ويجب أن يُقال إنّها افتراضاتٌ لا اتّفاق."""
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["source"], "default")
        self.assertIsNone(terms["policy_version"])
        self.assertEqual(
            terms["base_salary"],
            EmployeeCompensationPolicy._meta.get_field("base_salary").default,
        )

    def test_the_platform_policy_applies_when_no_personal_one_exists(self):
        _policy(version=1, base_salary="600.00", commission="120.00")
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["source"], "platform")
        self.assertEqual(terms["base_salary"], Decimal("600.00"))
        self.assertEqual(terms["policy_version"], 1)

    def test_a_personal_policy_beats_the_platform_one(self):
        """وهذا الفرقُ هو ما يريد الموظّفُ أن يراه: أرقامُه هو لا أرقامُ الجميع."""
        _policy(version=1, base_salary="600.00", commission="120.00")
        _policy(employee=self.employee, version=2, base_salary="900.00", commission="150.00")
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["source"], "employee")
        self.assertEqual(terms["base_salary"], Decimal("900.00"))
        # وزميلُه يبقى على سياسة المنصّة — لا تسري عليه نسخةُ غيره.
        self.assertEqual(get_employee_pay_terms(employee=self.other)["source"], "platform")

    def test_the_displayed_rule_is_the_one_the_engine_accrues_by(self):
        """**مصدرٌ واحدٌ لا نسختان.**

        لو قُرئت السياسةُ هنا بنسخةٍ ثانيةٍ لافترق ما يُعرَض عمّا يُصرَف يومَ
        تتغيّر القاعدة — وهو أسوأُ من ألّا يُعرض شيء.
        """
        _policy(employee=self.employee, version=7, base_salary="777.00", commission="77.00")
        engine_policy = get_active_employee_compensation_policy(self.employee)
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["base_salary"], engine_policy.base_salary)
        self.assertEqual(
            terms["acquisition_commission_amount"], engine_policy.acquisition_commission_amount)
        self.assertEqual(terms["policy_version"], engine_policy.version)

    # ── النقطة ───────────────────────────────────────────────────────────────

    def test_the_employee_reads_his_own_pay_terms(self):
        _policy(employee=self.employee, version=3, base_salary="850.50", commission="130.00")
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(self.employee))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["base_salary"], "850.50")
        self.assertEqual(response.data["acquisition_commission_amount"], "130.00")
        self.assertEqual(response.data["source"], "employee")

    def test_the_amounts_travel_as_plain_strings(self):
        """تعريبُ جانغو يقلب النقطةَ العشريّةَ فاصلةً في التصيير، و`formatNumber`
        في الواجهة يلزمها رقمٌ نظيفٌ لا مُعرَّب."""
        _policy(employee=self.employee, version=4, base_salary="1234.50", commission="10.00")
        self.client.force_authenticate(user=self.user)
        data = self.client.get(self._url(self.employee)).data
        self.assertIsInstance(data["base_salary"], str)
        self.assertNotIn("،", data["base_salary"])
        self.assertIn(".", data["base_salary"])

    def test_one_employee_cannot_read_another_employees_salary(self):
        """`get_queryset` تحصر غيرَ المدير في صفّه، فتردّ ٤٠٤ قبل حارسِ الفعل.

        والحارسُ داخل الفعل حزامٌ فوق الحمّالة **مقصودٌ ومذكورٌ في مكانه**: لو
        وُسّعت تلك الدالّةُ يوماً لغرضٍ آخر لا يصير راتبُ الناس مكشوفاً بأثرٍ
        جانبيّ. والمقيسُ هنا السلوكُ الملحوظ: لا رقمَ يخرج البتّة.
        """
        _policy(employee=self.other, version=5, base_salary="999.00", commission="99.00")
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(self.other))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("999", str(response.data))

    def test_the_manager_reads_any_employees_pay_terms(self):
        _policy(employee=self.other, version=6, base_salary="999.00", commission="99.00")
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(self._url(self.other))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["base_salary"], "999.00")

    def test_an_anonymous_visitor_reads_nothing(self):
        response = self.client.get(self._url(self.employee))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class InvitationNoteTests(TestCase):
    """‏#214-د — شرحٌ ورقمُ تواصلٍ يقرؤهما المدعوُّ قبل أن يُنشئ حسابه."""

    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_superuser(
            username="hiring_admin", email="h@p.local", password="AdminPass123!")
        self.job = create_job_posting(title="مسؤول دعم", description="وصفُ الوظيفة.")
        self.applicant = submit_application(
            job=self.job, name="سائل", phone="0790000000", email="s@x.local")
        for stage in (
            JobApplicant.Status.SCREENING,
            JobApplicant.Status.INTERVIEW,
            JobApplicant.Status.OFFERED,
        ):
            self.applicant = transition_applicant_status(
                applicant=self.applicant, target_status=stage)

    def _public(self, raw_token):
        return self.client.get(f"/api/careers/invitations/{raw_token}/")

    def test_the_invitee_reads_the_explanation_before_creating_an_account(self):
        """قلبُ البلاغ: نصٌّ ورقمٌ على الصفحة العامّة قبل أيّ تسجيل دخول."""
        invitation, raw = create_applicant_invitation(
            applicant=self.applicant,
            created_by=self.manager,
            note="الدوام من التاسعة، والمباشرة أوّل الشهر.",
            contact_phone="0791234567",
        )
        response = self._public(raw)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["note"], "الدوام من التاسعة، والمباشرة أوّل الشهر.")
        self.assertEqual(response.data["contact_phone"], "0791234567")

    def test_the_explanation_keeps_the_paragraphs_the_manager_typed(self):
        """الصفحةُ تعرضه نصَّ فقرات؛ وطيُّ الأسطر يمحو تقسيماً كُتب قصداً."""
        invitation, raw = create_applicant_invitation(
            applicant=self.applicant, created_by=self.manager,
            note="السطر الأول.\nالسطر الثاني.",
        )
        self.assertEqual(self._public(raw).data["note"], "السطر الأول.\nالسطر الثاني.")

    def test_an_invitation_without_an_explanation_is_still_a_valid_invitation(self):
        """اختياريٌّ لا إلزاميّ — فلا يُكسَر نداءٌ قائمٌ ولا تُفرَض كتابةٌ على من
        لا شيءَ عنده."""
        invitation, raw = create_applicant_invitation(
            applicant=self.applicant, created_by=self.manager)
        response = self._public(raw)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["note"], "")
        self.assertEqual(response.data["contact_phone"], "")

    def test_the_recruiters_private_notes_never_reach_the_invitee(self):
        """‏`JobApplicant.notes` ملاحظاتُ الفرز الداخليّةُ **عن الشخص نفسِه**.

        الحقلان متجاوران في الاسم والمعنى، وخلطُهما يُري المدعوَّ ما كُتب عنه.
        """
        self.applicant.notes = "مرشّحٌ ضعيفٌ لكنّه أرخصُ المتاح."
        self.applicant.save(update_fields=["notes"])
        invitation, raw = create_applicant_invitation(
            applicant=self.applicant, created_by=self.manager, note="أهلاً بك.")
        body = str(self._public(raw).data)
        self.assertIn("أهلاً بك", body)
        self.assertNotIn("أرخصُ المتاح", body)

    def test_a_runaway_explanation_is_capped_not_rejected(self):
        """رفضُ الدعوة كلِّها لأنّ الشرحَ طويلٌ يُضيّع الدعوة؛ والقصُّ يُبقيها."""
        invitation, raw = create_applicant_invitation(
            applicant=self.applicant, created_by=self.manager, note="ا" * 5000)
        self.assertEqual(len(invitation.note), 2000)

    def test_the_issuer_is_told_exactly_what_the_invitee_will_read(self):
        """يعود في الردّ **بعد** القصّ والتشذيب لا كما كُتب في الحقل."""
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            f"/api/platform/ops/job-applicants/{self.applicant.pk}/invite/",
            {"note": "   مرحباً بك في الفريق.   ", "contact_phone": " 0799999999 "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["note"], "مرحباً بك في الفريق.")
        self.assertEqual(response.data["contact_phone"], "0799999999")
        invitation = resolve_public_invitation(response.data["token"])
        self.assertEqual(invitation.note, "مرحباً بك في الفريق.")
