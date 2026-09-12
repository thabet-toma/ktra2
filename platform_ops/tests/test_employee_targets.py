"""مستهدفا الموظّف: بابُ كتابتهما، وفصلُ سُلَّميهما (التذكرة 210-ز).

`capacity_target` و`monthly_units_target` رقمان يقيسان **جنسين مختلفين**:
الأوّلُ يُقارَن بمجموع وحدات حِمل الشركات المرتبطة (١/٢/٣ للشركة) وبعدد أوامر
العمل النشطة، والثاني بوحدات الكتالوج للمستندات في الشهر. وقبل هذه التذكرة كانا
حقلاً واحداً، فرقمٌ صالحٌ لأحد السُلَّمين يُعطّل الآخرَ بصمت — وكلاهما بلا بابٍ
في النظام أصلاً: لا نقطة ولا شاشة ولا `admin.py`، فالـshell أو لا شيء.
"""
import datetime
import json
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import PlatformActivityLog, PlatformEmployee, WorkOrder
from platform_ops.services import (
    PlatformOpsError,
    calculate_employee_pilot_performance,
    capture_pilot_performance_snapshot,
    recapture_performance_after_accepted_review,
    request_performance_review,
    resolve_performance_review,
    set_employee_targets,
    suggest_monthly_units_targets,
)
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class TargetScalesAreSeparateTest(PilotScenarioBase):
    """السببُ الذي انفصل الحقلان لأجله — وهو ما يسقط إن أُعيدا واحداً."""

    def _completion_axis(self):
        now = timezone.now()
        return calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )["axes"]["task_completion"]

    def test_assignment_capacity_does_not_cap_the_completion_denominator(self):
        """قيمةُ إسنادٍ معقولةٌ (١٠ شركاتٍ موزونة) كانت تقصّ مقامَ الوحدات إلى ١٠.

        وحداتُ الشهر مئاتٌ وطاقةُ الإسناد آحادٌ — فرقمٌ صحيحٌ في بابه كان يرفع
        الدرجةَ في بابٍ آخر بلا عملٍ إضافيٍّ واحد.
        """
        self._activate_multi_unit_catalog()
        now = timezone.now()
        self._work_order_with_lines(received_at=now - datetime.timedelta(minutes=5), line_count=3, approve=True)
        self._work_order_with_lines(received_at=now - datetime.timedelta(minutes=4), line_count=3, approve=False)
        before = self._completion_axis()

        set_employee_targets(employee=self.employee, capacity_target=Decimal("1.00"), actor=self.admin)
        self.employee.refresh_from_db()

        after = self._completion_axis()
        self.assertEqual(after["denominator"], before["denominator"], "طاقةُ الإسناد قصّت مقامَ الوحدات.")
        self.assertEqual(after["score"], before["score"])

    def test_the_units_target_is_what_caps_the_completion_denominator(self):
        self._activate_multi_unit_catalog()
        now = timezone.now()
        self._work_order_with_lines(received_at=now - datetime.timedelta(minutes=5), line_count=3, approve=True)
        self._work_order_with_lines(received_at=now - datetime.timedelta(minutes=4), line_count=3, approve=False)
        self.assertEqual(self._completion_axis()["denominator"], 5.0)

        set_employee_targets(employee=self.employee, monthly_units_target=Decimal("2.00"), actor=self.admin)
        self.employee.refresh_from_db()
        self.assertEqual(self._completion_axis()["denominator"], 2.0)

    def test_setting_one_target_leaves_the_other_untouched(self):
        set_employee_targets(employee=self.employee, capacity_target=Decimal("7.00"), actor=self.admin)
        set_employee_targets(employee=self.employee, monthly_units_target=Decimal("150.00"), actor=self.admin)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.capacity_target, Decimal("7.00"), "ضبطُ المقام مسح طاقةَ الإسناد.")
        self.assertEqual(self.employee.monthly_units_target, Decimal("150.00"))


class SetEmployeeTargetsTest(PilotScenarioBase):
    def test_a_negative_target_is_refused(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            set_employee_targets(employee=self.employee, monthly_units_target=Decimal("-1.00"), actor=self.admin)
        self.assertEqual(ctx.exception.code, "invalid_target")

    def test_a_non_numeric_target_is_refused(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            set_employee_targets(employee=self.employee, capacity_target="عشرة", actor=self.admin)
        self.assertEqual(ctx.exception.code, "invalid_target")

    def test_a_call_with_no_target_is_refused(self):
        """نداءٌ فارغٌ يكتب سجلَّ نشاطٍ بلا تغييرٍ فيلوّث دفترَ المراجعة."""
        with self.assertRaises(PlatformOpsError) as ctx:
            set_employee_targets(employee=self.employee, actor=self.admin)
        self.assertEqual(ctx.exception.code, "no_target_provided")
        self.assertFalse(PlatformActivityLog.objects.filter(entity_type="employee_targets").exists())

    def test_the_change_is_logged_with_before_and_after(self):
        """مقامٌ يتغيّر بلا «قبلُ وبعدُ» يجعل كلَّ درجةٍ قديمةٍ غيرَ قابلةٍ للمراجعة."""
        set_employee_targets(employee=self.employee, monthly_units_target=Decimal("120.00"), actor=self.admin)
        log = PlatformActivityLog.objects.filter(entity_type="employee_targets").order_by("-id").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details.get("operation"), "set_employee_targets")
        self.assertEqual(log.details.get("actor_user_id"), self.admin.pk)
        self.assertEqual(log.details["before"]["monthly_units_target"], "0.00")
        self.assertEqual(log.details["after"]["monthly_units_target"], "120.00")
        self.assertNotIn("capacity_target", log.details["after"], "سُجِّل حقلٌ لم يُمَسّ.")


class MonthlyUnitsSuggestionTest(PilotScenarioBase):
    """المقاديرُ الثلاثةُ تُشتقّ من إنتاجٍ وقع — لا من ثوابتَ مخترَعة."""

    def _assign_units_in(self, year: int, month: int, *, line_count: int, approve: bool = True):
        """أمرُ عملٍ **مُسنَدٌ** يُؤرَّخ استلامُه في شهرٍ مضى.

        المستهدَفُ سقفٌ على المقام، والمقامُ يُقاس بـ`received_at` على العمل المُسنَد
        — فالتأريخُ هنا على أمر العمل لا على حدث الاستخدام.
        """
        self._activate_multi_unit_catalog()
        now = timezone.now()
        work_order, _link = self._work_order_with_lines(
            received_at=now - datetime.timedelta(minutes=5), line_count=line_count, approve=approve,
        )
        stamp = timezone.make_aware(datetime.datetime(year, month, 15, 12, 0))
        WorkOrder.objects.filter(pk=work_order.pk).update(received_at=stamp)
        return work_order

    def test_targets_come_from_the_employees_own_complete_months(self):
        moment = timezone.localtime()
        months = []
        y, m = moment.year, moment.month
        for _ in range(3):
            m -= 1
            if m == 0:
                y, m = y - 1, 12
            months.append((y, m))
        # ثلاثةُ أشهرَ بإنتاجٍ مختلف: 1+3×0.5=2.5 · 1+7×0.5=4.5 · 1+1×0.5=1.5
        for (year, month), lines in zip(months, (3, 7, 1)):
            self._assign_units_in(year, month, line_count=lines)

        suggestion = suggest_monthly_units_targets(self.employee, at=moment)
        self.assertEqual(suggestion["basis"], "self")
        self.assertEqual(suggestion["targets"]["low"], 1.5, "الأدنى ليس أضعفَ أشهره.")
        self.assertEqual(suggestion["targets"]["medium"], 2.5)
        self.assertEqual(suggestion["targets"]["high"], 4.5, "الأعلى ليس أقوى أشهره.")

    def test_targets_are_measured_on_the_denominator_not_the_numerator(self):
        """المستهدَفُ سقفٌ على المقام — فعيّنتُه وحداتُ المُسنَد لا وحداتُ المعتمَد.

        المعتمَدُ بسطٌ يقع دائماً دون المقام، فاقتراحٌ مبنيٌّ عليه يَربِط عبر
        `min()` في كلّ شهرٍ ويرفع كلَّ درجةٍ بلا عملٍ إضافيٍّ واحد.
        """
        moment = timezone.localtime()
        previous_month = (moment.year, moment.month - 1) if moment.month > 1 else (moment.year - 1, 12)
        # أمرانِ مُسندانِ بـ2.50 لكلٍّ = 5.00 مقاماً، وواحدٌ وحدَه أُنجز = 2.50 بسطاً.
        self._assign_units_in(*previous_month, line_count=3)
        idle = self._assign_units_in(*previous_month, line_count=3, approve=False)
        self.assertIsNotNone(idle)

        suggestion = suggest_monthly_units_targets(self.employee, at=moment)
        self.assertEqual(
            suggestion["targets"]["high"], 5.0,
            "الاقتراحُ مبنيٌّ على البسط (2.50) لا على المقام (5.00) — يَربِط فيرفع الدرجة.",
        )

    def test_the_current_incomplete_month_is_not_measured(self):
        """الشهرُ الجاري ناقصٌ — قياسُه يقترح مقاماً أصغرَ من الحقيقة فيرفع الدرجة."""
        moment = timezone.localtime()
        self._assign_units_in(moment.year, moment.month, line_count=9)
        suggestion = suggest_monthly_units_targets(self.employee, at=moment)
        # **المدى أوّلاً**: `no_history` وحدَها تصدق أيضاً لو انكسرت قراءةُ الوحدات
        # كلُّها، فلا تُثبت أنّ الشهرَ الجاريَ استُبعد لسببه.
        self.assertNotIn(
            {"year": moment.year, "month": moment.month}, suggestion["months"],
            "الشهرُ الجاري داخلَ مدى القياس.",
        )
        self.assertEqual(suggestion["basis"], "no_history")
        self.assertIsNone(suggestion["targets"])

    def test_a_new_employee_borrows_the_distribution_of_peers(self):
        moment = timezone.localtime()
        previous_month = (moment.year, moment.month - 1) if moment.month > 1 else (moment.year - 1, 12)
        self._assign_units_in(*previous_month, line_count=5)

        newcomer_user = self.admin  # مستخدمٌ آخرُ بلا `PlatformEmployee` بعد
        newcomer = PlatformEmployee.objects.create(
            user=newcomer_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        suggestion = suggest_monthly_units_targets(newcomer, at=moment)
        self.assertEqual(suggestion["basis"], "peers", "موظّفٌ جديدٌ تُرك بلا مقاديرَ ولزملائه تاريخ.")
        self.assertEqual(suggestion["targets"]["high"], 3.5)

    def test_no_history_anywhere_invents_nothing(self):
        """لا أرقامَ من الهواء في مقامِ درجةٍ تقرّر راتباً."""
        suggestion = suggest_monthly_units_targets(self.employee, at=timezone.localtime())
        self.assertEqual(suggestion["basis"], "no_history")
        self.assertIsNone(suggestion["targets"])
        self.assertEqual(len(suggestion["months"]), 3)


class TargetIsFrozenWithTheSnapshotTest(PilotScenarioBase):
    """«لا أثر رجعي» (210-د) يشمل المستهدَف لا الأوزانَ وحدَها.

    مقامُ محور الإنجاز مقصوصٌ بـ`monthly_units_target`، فتركُه حيّاً يعني أنّ ضبطَه
    اليومَ يُعيد تسعيرَ كلّ شهرٍ يُعاد التقاطُه — وإعادةُ الالتقاط صارت زرّاً في
    الشاشة منذ 210-و، فما كان بعيدَ المنال صار نقرةً.
    """

    def test_recapture_uses_the_target_frozen_with_the_month(self):
        now = timezone.now()
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=20))
        set_employee_targets(employee=self.employee, monthly_units_target=Decimal("4.00"), actor=self.admin)
        self.employee.refresh_from_db()

        frozen = capture_pilot_performance_snapshot(
            employee=self.employee, period_year=now.year, period_month=now.month, captured_by=self.admin,
        )
        denominator_before = (frozen.axes_data or {})["task_completion"]["denominator"]
        self.assertEqual(
            frozen.policy_snapshot.get("monthly_units_target"), "4.00",
            "اللقطةُ لم تُجمّد المستهدَف، فليس في الصفّ ما يُحتكَم إليه.",
        )

        # مستهدَفٌ جديدٌ يُضبط **بعد** اللقطة — لا شأنَ له بشهرٍ مضى.
        set_employee_targets(employee=self.employee, monthly_units_target=Decimal("1.00"), actor=self.admin)

        accepted = resolve_performance_review(
            review_request=request_performance_review(
                employee=self.employee, period_year=now.year, period_month=now.month,
                reason="وحدةٌ اعتُمدت لغيري",
            ),
            accepted=True, resolution_note="صحيح — سيُصحَّح المصدر.", actor=self.admin,
        )
        refreshed = recapture_performance_after_accepted_review(review_request=accepted, actor=self.admin)
        self.assertEqual(
            (refreshed.axes_data or {})["task_completion"]["denominator"], denominator_before,
            "أُعيد تسعيرُ الشهر بمستهدَفٍ ضُبط بعده — أثرٌ رجعيّ.",
        )


class EmployeeTargetsEndpointTest(PilotScenarioBase):
    def _url(self, employee=None):
        return reverse("platform-ops-employees-targets", args=[(employee or self.employee).pk])

    def test_writing_is_manager_only(self):
        """الموظّفُ الذي يخفض مقامَه يرفع درجتَه، ودرجتُه مالٌ في المحفظة."""
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        denied = client.patch(self._url(), {"monthly_units_target": "1.00"}, format="json")
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied.data["code"], "manager_only")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.monthly_units_target, Decimal("0.00"))

        client.force_authenticate(user=self.admin)
        ok = client.patch(self._url(), {"monthly_units_target": "140.00"}, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        # **على السلك لا في `response.data`**: الأخيرةُ تُقرأ قبل الترميز فتُظهر
        # `Decimal` سليماً، ومُرمِّزُ DRF يحوّله `float` — وواجهةُ TypeScript تُعلنه
        # نصّاً وتستدعي عليه `trim()`. فالتأكيدُ على الحمولة المُرمَّزة وحدَها يمسك هذا.
        wire = json.loads(ok.content.decode("utf-8"))
        self.assertIsInstance(wire["monthly_units_target"], str)
        self.assertEqual(wire["monthly_units_target"], "140.00")
        self.assertIsInstance(wire["capacity_target"], str)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.monthly_units_target, Decimal("140.00"))

    def test_an_employee_reads_their_own_targets_but_not_the_suggestion(self):
        """بديلُ الزملاء يشتقّ المقاديرَ من إنتاج زملائه — و§١٠ تمنع أرقامَ غيره عنه."""
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        response = client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["employee_id"], self.employee.pk)
        self.assertIn("monthly_units_suggestion", response.data)
        self.assertIsNone(response.data["monthly_units_suggestion"], "وصلت الموظّفَ أرقامُ زملائه.")

        client.force_authenticate(user=self.admin)
        manager_view = client.get(self._url())
        self.assertIsNotNone(manager_view.data["monthly_units_suggestion"])

    def test_an_employee_cannot_read_another_employees_targets(self):
        other_user = self.admin
        other = PlatformEmployee.objects.create(
            user=other_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        response = client.get(self._url(other))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_negative_target_is_refused_with_its_code(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.patch(self._url(), {"capacity_target": "-3"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_target")


class TargetsFrontendContractTest(SimpleTestCase):
    """حمولةُ النقطة وواجهةُ TypeScript تُقرآن معاً أو تنحرفان بصمت.

    `tsc` لا يرى الخادم، والاختبارُ الخادميُّ لا يرى الواجهة — فحقلٌ يُعاد تسميتُه
    هنا يبقى أخضرَ في الطرفين ويصل المتصفحَ `undefined`.
    """

    INTERFACE = Path(settings.BASE_DIR) / "frontend_v2" / "services" / "platformEmployeeTargetsApi.ts"

    #: مفاتيحُ الحمولة كما تكتبها `PlatformEmployeeViewSet.targets`.
    PAYLOAD_KEYS = {
        "employee_id",
        "employee_name",
        "capacity_target",
        "monthly_units_target",
        "monthly_units_suggestion",
    }

    def test_the_interface_declares_exactly_the_payload_keys(self):
        source = self.INTERFACE.read_text(encoding="utf-8")
        block = re.search(r"export interface EmployeeTargets \{(.+?)\n\}", source, re.S)
        self.assertIsNotNone(block, "واجهةُ `EmployeeTargets` غائبةٌ أو تغيّر شكلُها.")
        declared = set(re.findall(r"^\s*(\w+)\??:", block.group(1), re.M))
        self.assertEqual(declared, self.PAYLOAD_KEYS)

    def test_the_suggestion_basis_union_matches_the_server(self):
        """`basis` ثلاثةُ قيمٍ يكتبها الخادم — ورابعةٌ في الواجهة فرعٌ ميّت."""
        source = self.INTERFACE.read_text(encoding="utf-8")
        union = re.search(r"export type SuggestionBasis =([^;]+);", source)
        self.assertIsNotNone(union)
        declared = set(re.findall(r'"([^"]+)"', union.group(1)))
        self.assertEqual(declared, {"self", "peers", "no_history"})
