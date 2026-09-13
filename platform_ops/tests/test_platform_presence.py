"""عدّادُ الوقت على المنصّة وأثرُه في التقييم (#212 212-D).

قرارُ المالك حرفيّاً: «لازم يبين عداد على الموظف ويبين بالطاولة فوق صورتو ويكون
بالسجل بشكل يومي توتال الوقت الي قعدو عالمنصة ... وبالتقييم يكون واضح ... بدي
التحديث يكون كل دقيقة». وأثرُه: «حدٌّ أدنى ٣ ساعات، وما زاد علاماتٌ أكثر، وما
قلّ خصم».
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from platform_ops.models import PlatformEmployee, PlatformPresenceDay
from platform_ops.services import (
    PRESENCE_MAX_SECONDS_PER_BEAT,
    presence_discipline_factor,
    record_presence_heartbeat,
)

User = get_user_model()


def make_staff_employee(username: str):
    """موظّفُ منصّةٍ نشط — صلاحيّةُ `IsPlatformOperationsStaff` تُشتقّ من الصفّ."""
    user = User.objects.create_user(
        username=username, email=f"{username}@platform.local", password="SecurePassword2026!",
    )
    employee = PlatformEmployee.objects.create(
        user=user, specialty="operations", status=PlatformEmployee.Status.ACTIVE,
    )
    return user, employee


def make_manager(username: str):
    return User.objects.create_user(
        username=username, email=f"{username}@platform.local",
        password="AdminPass2026!", is_superuser=True, is_staff=True,
    )

HEARTBEAT = "/api/platform/ops/presence/heartbeat/"
LOG = "/api/platform/ops/presence/log/"


class HeartbeatCountsRealGapsTest(TestCase):
    """الجمعُ بالفجوات لا بالنبضات — وهذا ما يمنع مضاعفةَ الساعات بلسانٍ ثانٍ."""

    def setUp(self):
        _, self.employee = make_staff_employee("presence_gaps")
        self.start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)

    def test_the_first_beat_starts_the_day_at_zero_seconds(self):
        """أوّلُ نبضةٍ تفتح اليومَ ولا تمنح وقتاً لم يمرّ بعد."""
        row = record_presence_heartbeat(employee=self.employee, now=self.start)
        self.assertEqual(row.active_seconds, 0)
        self.assertEqual(row.first_seen_at, self.start)

    def test_consecutive_minute_beats_accumulate_the_elapsed_seconds(self):
        record_presence_heartbeat(employee=self.employee, now=self.start)
        for minute in range(1, 4):
            row = record_presence_heartbeat(
                employee=self.employee, now=self.start + datetime.timedelta(minutes=minute),
            )
        self.assertEqual(row.active_seconds, 180)

    def test_two_tabs_beating_at_the_same_moment_do_not_double_the_hours(self):
        """**عيبُ العدّ بالنبضات**: `+60` لكلّ نبضةٍ يجعل عددَ الألسنة مضروبَ الوقت."""
        record_presence_heartbeat(employee=self.employee, now=self.start)
        first = self.start + datetime.timedelta(minutes=1)
        record_presence_heartbeat(employee=self.employee, now=first)   # اللسان الأول
        row = record_presence_heartbeat(employee=self.employee, now=first)  # اللسان الثاني
        self.assertEqual(
            row.active_seconds, 60,
            "لسانان ينبضان في اللحظة نفسِها ضاعفا الوقت — الجمعُ صار بالنبضات لا بالفجوات.",
        )

    def test_a_long_absence_is_not_counted_as_presence(self):
        """من نبض صباحاً وعاد عند المغيب لم يحضر يوماً كاملاً."""
        record_presence_heartbeat(employee=self.employee, now=self.start)
        row = record_presence_heartbeat(
            employee=self.employee, now=self.start + datetime.timedelta(hours=8),
        )
        self.assertEqual(
            row.active_seconds, PRESENCE_MAX_SECONDS_PER_BEAT,
            "فجوةُ ثماني ساعاتٍ احتُسبت حضوراً — الفرقُ بين أوّل نبضةٍ وآخرِها ليس حضوراً.",
        )

    def test_a_clock_that_moved_backwards_does_not_subtract_seconds(self):
        record_presence_heartbeat(employee=self.employee, now=self.start)
        record_presence_heartbeat(employee=self.employee, now=self.start + datetime.timedelta(minutes=5))
        row = record_presence_heartbeat(employee=self.employee, now=self.start)
        self.assertGreaterEqual(row.active_seconds, 0)

    def test_one_row_per_employee_per_day(self):
        for minute in range(3):
            record_presence_heartbeat(
                employee=self.employee, now=self.start + datetime.timedelta(minutes=minute),
            )
        self.assertEqual(PlatformPresenceDay.objects.filter(employee=self.employee).count(), 1)


class PresenceFactorFollowsTheOwnersRuleTest(TestCase):
    """«حدٌّ أدنى ٣ ساعات، وما زاد علاماتٌ أكثر، وما قلّ خصم»."""

    def setUp(self):
        _, self.employee = make_staff_employee("presence_factor")
        self.day = timezone.localdate()

    def _day(self, date, hours):
        moment = timezone.now()
        PlatformPresenceDay.objects.create(
            employee=self.employee, date=date, active_seconds=int(hours * 3600),
            first_seen_at=moment, last_seen_at=moment,
        )

    def test_exactly_the_threshold_is_a_neutral_factor(self):
        self._day(self.day, 3)
        result = presence_discipline_factor(employee=self.employee)
        self.assertTrue(result["is_applicable"])
        self.assertEqual(result["factor"], 1.0)

    def test_below_the_threshold_deducts(self):
        self._day(self.day, 1.5)
        self.assertEqual(presence_discipline_factor(employee=self.employee)["factor"], 0.5)

    def test_above_the_threshold_adds_but_never_past_the_cap(self):
        self._day(self.day, 9)  # ثلاثةُ أضعاف العتبة
        result = presence_discipline_factor(employee=self.employee)
        self.assertEqual(
            result["factor"], 1.25,
            "يومٌ طويلٌ تجاوز سقفَ السياسة — «الانضباط» صار مقياسَ نَهَمٍ لا انتظام.",
        )

    def test_a_day_with_no_heartbeat_is_not_counted_as_a_zero(self):
        """الدفترُ لا يعرف العطلةَ من الإجازة، فاحتسابُ الجُمَع أصفاراً يجعل
        الانضباطَ دالّةَ التقويم لا دالّةَ الموظّف."""
        self._day(self.day, 3)
        result = presence_discipline_factor(employee=self.employee)
        self.assertEqual(result["days_counted"], 1)
        self.assertEqual(result["factor"], 1.0)

    def test_no_days_at_all_means_no_judgement_not_a_zero_score(self):
        result = presence_discipline_factor(employee=self.employee)
        self.assertFalse(result["is_applicable"])
        self.assertEqual(result["factor"], 1.0, "غيابُ المعلومة صار خصماً كاملاً.")

    def test_a_zero_threshold_switches_the_whole_effect_off(self):
        self._day(self.day, 0.25)
        result = presence_discipline_factor(employee=self.employee, min_hours_per_day=0)
        self.assertFalse(result["is_applicable"])
        self.assertEqual(result["factor"], 1.0)

    def test_the_policy_threshold_and_cap_are_honoured_not_hard_coded(self):
        self._day(self.day, 4)
        result = presence_discipline_factor(
            employee=self.employee, min_hours_per_day=8, day_cap_percent=150,
        )
        self.assertEqual(result["factor"], 0.5)
        self.assertEqual(result["min_hours_per_day"], 8.0)
        self.assertEqual(result["day_cap_percent"], 150)

    def test_days_outside_the_period_are_excluded(self):
        self._day(self.day, 3)
        self._day(self.day - datetime.timedelta(days=40), 0.1)
        result = presence_discipline_factor(
            employee=self.employee,
            start_date=self.day - datetime.timedelta(days=5), end_date=self.day,
        )
        self.assertEqual(result["days_counted"], 1)
        self.assertEqual(result["factor"], 1.0)


class PresenceEndpointsTest(APITestCase):
    def setUp(self):
        self.user, self.employee = make_staff_employee("presence_api")
        self.other_user, self.other = make_staff_employee("presence_api_other")

    def test_an_employee_beats_for_himself_and_reads_his_own_counter(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post(HEARTBEAT, {}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["recorded"])
        log = self.client.get(LOG)
        self.assertEqual(log.status_code, 200, log.content)
        self.assertEqual(log.json()["employee_id"], self.employee.pk)

    def test_the_heartbeat_takes_no_employee_parameter_so_nobody_beats_for_another(self):
        """**لا انتحالَ حضور**: النبضةُ مشتقّةٌ من `request.user` وحدَه."""
        self.client.force_authenticate(user=self.user)
        self.client.post(HEARTBEAT, {"employee": self.other.pk}, format="json")
        self.assertEqual(
            PlatformPresenceDay.objects.filter(employee=self.other).count(), 0,
            "نبضةٌ باسم موظّفٍ آخر سُجِّلت — معامِلٌ من الطلب يُصدَّق.",
        )
        self.assertEqual(PlatformPresenceDay.objects.filter(employee=self.employee).count(), 1)

    def test_an_employee_cannot_read_a_colleagues_presence_log(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(LOG, {"employee": self.other.pk})
        self.assertEqual(res.status_code, 403, res.content)

    def test_a_manager_can_read_an_employees_presence_log(self):
        self.client.force_authenticate(user=make_manager("presence_manager"))
        res = self.client.get(LOG, {"employee": self.employee.pk})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["employee_id"], self.employee.pk)

    def test_an_anonymous_caller_is_refused(self):
        self.assertIn(self.client.post(HEARTBEAT, {}, format="json").status_code, (401, 403))
        self.assertIn(self.client.get(LOG).status_code, (401, 403))
