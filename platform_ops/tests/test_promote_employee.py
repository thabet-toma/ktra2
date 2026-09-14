"""«اجعله موظّفَ منصّة» — البابُ الثاني إلى الفريق (212-Q4).

طلبُ المالك: يريد أن يجعل حساباً قائماً موظّفَ منصّةٍ بضغطة. وقبل هذه التذكرة
كان الطريقُ الوحيدُ إلى صفِّ `PlatformEmployee` هو `accept_job_invitation`:
إعلانُ وظيفةٍ ← متقدّمٌ ← دعوةٌ بمهلة ← قبولٌ يُنشئ الحسابَ والصفَّ معاً. فمن
له حسابٌ على المنصّة أصلاً — شريكٌ أو مؤسِّسٌ أو موظّفٌ قديمٌ عاد — لا يُضَمُّ
إلّا باختلاق إعلانٍ وهميٍّ ودعوةٍ لنفسه، أو بكتابةِ صفٍّ من الـshell.

والصفُّ ليس تفصيلاً إداريّاً: `is_platform_employee` هو ما يفتح `/staff` كلَّها
(القشرةُ والمهامُّ والحضورُ والمحفظة)، فبابُ الضمِّ المفقود كان يعني أنّ مساحةَ
الموظّف لا يدخلها إلّا من مرّ ببوّابة التوظيف.
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from platform_ops.models import PlatformEmployee
from platform_ops.services import PlatformOpsError, promote_user_to_platform_employee

User = get_user_model()

PROMOTE = "/api/platform/ops/employees/promote/"

FRONTEND = Path(__file__).resolve().parents[2] / "frontend_v2"
HIRING_API = FRONTEND / "services" / "platformHiringApi.ts"
PROMOTE_PANEL = FRONTEND / "components" / "platform" / "PromoteEmployeePanel.tsx"
DASHBOARD = FRONTEND / "components" / "platform" / "PlatformOpsDashboard.tsx"


class PromoteUserToPlatformEmployeeServiceTest(TestCase):
    """قواعدُ الضمِّ في الخدمة — لا في الـview وحدَه."""

    def setUp(self):
        self.user = User.objects.create_user(username="rami", email="rami@ktra.local", password="x")

    def test_a_plain_user_becomes_an_active_platform_employee(self):
        employee, created = promote_user_to_platform_employee(user=self.user, specialty="operations")
        self.assertTrue(created)
        self.assertEqual(employee.status, PlatformEmployee.Status.ACTIVE)
        self.assertEqual(employee.specialty, "operations")
        self.assertEqual(employee.user_id, self.user.pk)

    def test_the_specialty_is_cut_to_the_column_not_to_the_database(self):
        """التخصّصُ مفتاحُ `PolicyProfile`، والعمودُ مئةُ محرف.

        نصٌّ أطولُ يُبتَر صامتاً على SQLite ويُخطئ على MySQL — والقاعدةُ نفسُها
        مكتوبةٌ في باب الدعوة، فلا يكفي أن يحرسها بابٌ واحد.
        """
        employee, _ = promote_user_to_platform_employee(user=self.user, specialty="ع" * 300)
        self.assertEqual(len(employee.specialty), 100)

    def test_promoting_an_active_employee_is_refused_not_duplicated(self):
        promote_user_to_platform_employee(user=self.user)
        with self.assertRaises(PlatformOpsError) as caught:
            promote_user_to_platform_employee(user=self.user)
        self.assertEqual(caught.exception.code, "already_platform_employee")
        self.assertEqual(PlatformEmployee.objects.filter(user=self.user).count(), 1)

    def test_someone_who_left_comes_back_to_the_same_row(self):
        """عودةُ من غادر إحياءٌ لا صفٌّ ثانٍ — تاريخُه كلُّه معلّقٌ بهذا الصفّ."""
        employee, _ = promote_user_to_platform_employee(user=self.user, specialty="operations")
        employee.status = PlatformEmployee.Status.OFFBOARDED
        employee.save(update_fields=["status"])

        again, created = promote_user_to_platform_employee(user=self.user)
        self.assertFalse(created)
        self.assertEqual(again.pk, employee.pk)
        self.assertEqual(again.status, PlatformEmployee.Status.ACTIVE)

    def test_a_blank_specialty_on_return_keeps_the_old_one(self):
        """وإلّا عاد بسياسةِ تقييمٍ افتراضيّةٍ بلا أن يلاحظ أحد، ودرجتُه مالٌ."""
        employee, _ = promote_user_to_platform_employee(user=self.user, specialty="operations")
        employee.status = PlatformEmployee.Status.ON_LEAVE
        employee.save(update_fields=["status"])

        again, _ = promote_user_to_platform_employee(user=self.user, specialty="")
        self.assertEqual(again.specialty, "operations")

    def test_a_disabled_account_is_refused(self):
        """حسابٌ معطَّلٌ لا يدخل: صفٌّ يُعَدُّ في اللوحة ولا يستطيع صاحبُه الدخول."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertRaises(PlatformOpsError) as caught:
            promote_user_to_platform_employee(user=self.user)
        self.assertEqual(caught.exception.code, "inactive_user")

    def test_the_promotion_does_not_create_an_account(self):
        """بابُ إنشاء الحسابات هو الدعوةُ وحدَها — هنا المستخدمُ قائمٌ ويدخل بما يعرفه."""
        before = User.objects.count()
        promote_user_to_platform_employee(user=self.user)
        self.assertEqual(User.objects.count(), before)


class PromoteEndpointIsForTheManagerAloneTest(TestCase):
    """النقطةُ على `employees/` وهو viewset يقرؤه الموظّفُ أيضاً — فالحارسُ داخليّ."""

    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_superuser(username="owner", email="o@ktra.local", password="x")
        self.staff_user = User.objects.create_user(username="worker", password="x")
        self.staff = PlatformEmployee.objects.create(
            user=self.staff_user, status=PlatformEmployee.Status.ACTIVE,
        )
        self.candidate = User.objects.create_user(username="nour", email="nour@ktra.local", password="x")

    def test_the_manager_adds_a_registered_user_by_username(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(PROMOTE, {"identifier": "nour", "specialty": "sales"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["created"])
        self.assertTrue(PlatformEmployee.objects.filter(user=self.candidate).exists())

    def test_the_email_works_as_the_identifier_too(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(PROMOTE, {"identifier": "NOUR@ktra.local"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_an_unknown_identifier_is_a_named_refusal_not_a_new_account(self):
        self.client.force_authenticate(self.manager)
        before = User.objects.count()
        response = self.client.post(PROMOTE, {"identifier": "who@nowhere.local"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), before)

    def test_a_platform_employee_cannot_add_himself_a_colleague(self):
        """الموظّفُ يقرأ هذا الـviewset (صفَّه هو)، فبلا حارسٍ داخليٍّ يكتب فيه."""
        self.client.force_authenticate(self.staff_user)
        response = self.client.post(PROMOTE, {"identifier": "nour"}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data.get("code"), "manager_only")
        self.assertFalse(PlatformEmployee.objects.filter(user=self.candidate).exists())

    def test_an_outsider_gets_nothing(self):
        self.client.force_authenticate(self.candidate)
        response = self.client.post(PROMOTE, {"identifier": "nour"}, format="json")
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(PlatformEmployee.objects.filter(user=self.candidate).exists())

    def test_bringing_someone_back_answers_two_hundred_not_two_hundred_and_one(self):
        """الفرقُ يقرؤه المستعمِل: «أُعيد إلى الفريق» لا «أُضيف»."""
        employee = PlatformEmployee.objects.create(
            user=self.candidate, status=PlatformEmployee.Status.OFFBOARDED,
        )
        self.client.force_authenticate(self.manager)
        response = self.client.post(PROMOTE, {"identifier": "nour"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["created"])
        employee.refresh_from_db()
        self.assertEqual(employee.status, PlatformEmployee.Status.ACTIVE)


class ThePromotionDoorIsActuallyMountedTest(SimpleTestCase):
    """نقطةٌ بلا زرٍّ بابٌ ميّت — وهو العطبُ المتكرّر في هذا المستودع.

    وثلاثةُ أبوابٍ سبقت هذه وُثِّقت مكتوبةً بلا مستدعٍ: `assignWorkOrder`
    و`changeWorkOrderPriority` (210-E) و«مساحة موظّف المنصّة» كلُّها. فالحارسُ
    هنا يسأل عن **التركيب** لا عن وجود الدالّة.
    """

    def test_the_client_function_exists_and_targets_the_endpoint(self):
        source = HIRING_API.read_text(encoding="utf-8")
        violations = []
        if "export const promoteUserToPlatformEmployee" not in source:
            violations.append("لا دالّةَ ضمٍّ في عميل الـAPI")
        if "employees/promote/" not in source:
            violations.append("الدالّةُ لا تصيب نقطةَ الضمّ")
        if "identifier" not in source:
            violations.append("الضمُّ لا يرسل معرّفاً نصّيّاً — والشاشةُ لا تعرف معرّفات المستخدمين")
        self.assertEqual(violations, [], f"عميلُ الضمّ ناقص: {violations}")

    def test_a_component_actually_calls_it(self):
        panel = PROMOTE_PANEL.read_text(encoding="utf-8")
        violations = []
        if "promoteUserToPlatformEmployee(" not in panel:
            violations.append("اللوحةُ لا تنادي الضمَّ")
        # **النداءُ لا الاسم**: `onPromoted` يبقى مكتوباً في واجهة الخصائص وفي
        # التفكيك بعد حذف النداء نفسِه، فحارسٌ يسأل عن الاسم يمرّ أخضرَ على لوحةٍ
        # تضمّ ولا تُحدِّث الفريقَ أمام عينَي المدير. قِيس ذلك بالتخريب.
        if "onPromoted();" not in panel:
            violations.append("اللوحةُ لا تُعلِم مستضيفَها بالنجاح — فالفريقُ لا يُحدَّث")
        self.assertEqual(violations, [], f"لوحةُ الضمّ لا تعمل: {violations}")

    def test_the_panel_is_mounted_on_the_command_centre(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        violations = []
        if "<PromoteEmployeePanel" not in dashboard:
            violations.append("اللوحةُ غيرُ مركَّبةٍ في مركز القيادة")
        if "PromoteEmployeePanel" in dashboard and "onPromoted={" not in dashboard:
            violations.append("مركَّبةٌ بلا إعادةِ تحميلٍ بعد الضمّ")
        self.assertEqual(violations, [], f"بابٌ مكتوبٌ بلا مدخل: {violations}")

    def test_the_door_sits_before_the_empty_team_message(self):
        """أوّلُ من يحتاج زرَّ الضمّ فريقٌ فارغ — فلو سكن داخلَ فرع «يوجد موظفون»
        لاختفى في الحالة الوحيدة التي لا غنى فيه عنها."""
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        mount = dashboard.find("<PromoteEmployeePanel")
        empty = dashboard.find("لا يوجد موظفون مطابقون للشروط الحالية")
        self.assertNotEqual(mount, -1, "اللوحةُ غيرُ مركَّبة.")
        self.assertNotEqual(empty, -1, "رسالةُ الفريق الفارغ اختفت — الحارسُ يقيس العدم.")
        self.assertLess(mount, empty, "زرُّ الضمّ بعد شرط «لا يوجد موظفون» — يختفي حين يلزم.")
