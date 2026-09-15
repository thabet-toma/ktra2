"""شرحُ شروط الصرف الذي يقرؤه الموظّف مع أرقامه — بلاغُ المالك الثاني في #214-ج.

**البلاغ حرفيّاً:** «الراتب لازم عليه شرح لأنو ممكن الأساسي قليل يكون عمولات
عالتسويق، مو رقم وخلص».

وهو بلاغٌ عن **صدقٍ بالسكوت** لا عن حقلٍ ناقص: الشاشةُ كانت تعرض «٤٠٠ شيكل»
وتصمت، فيقرأ صاحبُها أنّ هذا كلُّ ما له — بينما الأساسيُّ صغيرٌ لأنّ فوقه عمولةَ
تسويقٍ وحافزَ اكتساب. والرقمُ الصحيحُ المعروضُ وحدَه يضلّل.

ومكانُ الشرح **على نسخة السياسة** لا على الموظّف: النسخةُ مؤرَّخةٌ ولا تُعدَّل
بعد تفعيلها، فيُحفَظ الشرحُ مع الأرقام التي يشرحها ويتقاعد معها.
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
    EmployeeCompensationPolicyEvent,
    PlatformEmployee,
)
from platform_ops.services import (
    clone_employee_compensation_policy_to_draft,
    create_employee_compensation_policy_draft,
    get_employee_pay_terms,
    update_employee_compensation_policy_draft,
)

User = get_user_model()

NOTE = "الأساسي 400، وفوقه عمولة تسويق 5٪ على كل اشتراك تجلبه."


class PayTermsNoteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_superuser(
            username="pay_note_admin", email="a@p.local", password="AdminPass123!")
        self.user = User.objects.create_user(username="pay_note_worker", password="WorkerPass123!")
        self.employee = PlatformEmployee.objects.create(user=self.user, specialty="تسويق")

    def _activate(self, policy):
        policy.status = EmployeeCompensationPolicy.Status.ACTIVE
        policy.effective_from = timezone.now() - datetime.timedelta(days=1)
        policy.save(update_fields=["status", "effective_from"])
        return policy

    # ── الشرح يصل صاحبَه ─────────────────────────────────────────────────────

    def test_the_employee_reads_the_explanation_with_his_numbers(self):
        """قلبُ البلاغ: الشرحُ يظهر للموظّف في صفحته لا للمدقّق وحدَه."""
        self._activate(create_employee_compensation_policy_draft(
            employee=self.employee, base_salary=Decimal("400.00"), pay_terms_note=NOTE))
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/platform/ops/employees/{self.employee.pk}/pay-terms/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pay_terms_note"], NOTE)
        self.assertEqual(response.data["base_salary"], "400.00")

    def test_the_explanation_keeps_the_paragraphs_the_manager_typed(self):
        """يُعرَض نصَّ فقرات؛ وطيُّ الأسطر يمحو تقسيماً كُتب قصداً."""
        self._activate(create_employee_compensation_policy_draft(
            employee=self.employee, pay_terms_note="الأساسي 400.\nالعمولة 5٪."))
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["pay_terms_note"], "الأساسي 400.\nالعمولة 5٪.")

    def test_without_any_policy_the_note_is_empty_not_missing(self):
        """حالُ الـpilot قبل أوّل نشر — والمفتاحُ موجودٌ فارغاً لا غائباً:
        حقلٌ يظهر أحياناً يجعل الواجهةَ تخمّن غيابَه."""
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["source"], "default")
        self.assertEqual(terms["pay_terms_note"], "")

    def test_the_note_travels_with_the_version_that_carries_the_numbers(self):
        """نسخةٌ خاصّةٌ تغلب العامّة — **وشرحُها يغلب شرحَها معها**.

        لو عُلِّق الشرحُ على الموظّف بدل النسخة لبقي شرحُ المنصّة العامّ معلّقاً
        فوق أرقامٍ خاصّةٍ تخالفه، ولا شيءَ يشتكي.
        """
        self._activate(create_employee_compensation_policy_draft(
            base_salary=Decimal("500.00"), pay_terms_note="شرح المنصّة العام."))
        self._activate(create_employee_compensation_policy_draft(
            employee=self.employee, base_salary=Decimal("400.00"), pay_terms_note=NOTE))
        terms = get_employee_pay_terms(employee=self.employee)
        self.assertEqual(terms["source"], "employee")
        self.assertEqual(terms["pay_terms_note"], NOTE)

    def test_a_colleague_cannot_read_another_employees_explanation(self):
        """الشرحُ يصف راتباً، فيُحرَس بما يُحرَس به الراتب لا بأقلّ منه."""
        other_user = User.objects.create_user(username="pay_note_other", password="P@ss12345")
        other = PlatformEmployee.objects.create(user=other_user, specialty="دعم")
        self._activate(create_employee_compensation_policy_draft(
            employee=other, pay_terms_note="سرٌّ يخصّ زميلاً."))
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/platform/ops/employees/{other.pk}/pay-terms/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("سرٌّ يخصّ زميلاً", str(response.data))

    # ── الكتابة والتدقيق ─────────────────────────────────────────────────────

    def test_the_manager_writes_the_note_on_a_draft(self):
        draft = create_employee_compensation_policy_draft(employee=self.employee)
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            f"/api/platform/ops/compensation-policies/{draft.pk}/update-draft/",
            {"pay_terms_note": "  شرحٌ جديد.  "}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        draft.refresh_from_db()
        self.assertEqual(draft.pay_terms_note, "شرحٌ جديد.")

    def test_an_empty_note_erases_a_written_one(self):
        """محوُ الشرح فعلٌ مقصودٌ كإثباته: شرحٌ صار كاذباً يجب أن يُسحَب.

        وبلا `allow_blank` في المُسلسِل يردّ الحقلُ الفارغ ٤٠٠ — فيبقى الشرحُ
        القديمُ معروضاً على الموظّف بلا باب لسحبه.
        """
        draft = create_employee_compensation_policy_draft(
            employee=self.employee, pay_terms_note=NOTE)
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            f"/api/platform/ops/compensation-policies/{draft.pk}/update-draft/",
            {"pay_terms_note": ""}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        draft.refresh_from_db()
        self.assertEqual(draft.pay_terms_note, "")

    def test_cloning_a_policy_carries_its_explanation_forward(self):
        """المسودّةُ المستنسَخةُ تبدأ من حيث انتهت سابقتُها — والشرحُ من الشروط
        لا زينةٌ فوقها، فنسيانُه يُنشئ نسخةً بأرقامٍ مشروحةٍ وشرحٍ فارغ."""
        source = self._activate(create_employee_compensation_policy_draft(
            employee=self.employee, pay_terms_note=NOTE))
        clone = clone_employee_compensation_policy_to_draft(policy=source)
        self.assertEqual(clone.pay_terms_note, NOTE)

    def test_a_runaway_note_is_capped_not_rejected(self):
        """رفضُ النسخة كلِّها لأنّ شرحَها طويل يُضيّع الأرقامَ معه."""
        policy = create_employee_compensation_policy_draft(
            employee=self.employee, pay_terms_note="ش" * 9000)
        self.assertEqual(len(policy.pay_terms_note), 4000)

    def test_editing_the_note_is_recorded_in_the_audit_trail(self):
        """نصٌّ يقرؤه الناس عن رواتبهم — تغييرُه حدثٌ يُسجَّل كتغيير الأرقام."""
        draft = create_employee_compensation_policy_draft(
            employee=self.employee, pay_terms_note="قبل.")
        update_employee_compensation_policy_draft(
            policy=draft, actor=self.manager, pay_terms_note="بعد.")
        event = (EmployeeCompensationPolicyEvent.objects
                 .filter(policy=draft, action=EmployeeCompensationPolicyEvent.Action.UPDATED)
                 .latest("id"))
        self.assertEqual(event.details["before"]["pay_terms_note"], "قبل.")
        self.assertEqual(event.details["after"]["pay_terms_note"], "بعد.")

    def test_the_note_is_not_the_activation_reason(self):
        """حقلان لجمهورين: `activation_reason` **للمدقّق** ولا يُعرَض على أحد،
        و`pay_terms_note` **للموظّف**. خلطُهما يُري الموظّفَ مبرّراتٍ إداريّةً
        كُتبت عنه، أو يُخفي عنه شرحَه لأنّه كُتب في الحقل الآخر."""
        self._activate(create_employee_compensation_policy_draft(
            employee=self.employee, pay_terms_note=NOTE))
        policy = EmployeeCompensationPolicy.objects.filter(employee=self.employee).latest("version")
        policy.activation_reason = "قرار الإدارة رقم ٧ — لا يخصّ الموظّف."
        policy.save(update_fields=["activation_reason"])

        self.client.force_authenticate(user=self.user)
        body = str(self.client.get(
            f"/api/platform/ops/employees/{self.employee.pk}/pay-terms/").data)
        self.assertIn("عمولة تسويق", body)
        self.assertNotIn("قرار الإدارة رقم ٧", body)
