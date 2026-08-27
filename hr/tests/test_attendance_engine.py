"""M2 — محرّك الحضور: السياج الجغرافي، حدود اليوم، الورديات، اشتقاق اليوم.

الاختبارات هنا تقيس **الحساب** لا الـAPI: قبولُ البصمة ونسبتُها ليومها
واشتقاقُ دقائقها هي ما يتحوّل إلى مالٍ في مسير الرواتب لاحقاً، فأي انزياح
هنا انزياحٌ في راتب.

**التوقيت مثبَّت على `Asia/Hebron`** في كل اختبار يمسّ حدود اليوم: القيمة
تأتي من `DJANGO_TIME_ZONE` في الإنتاج، واختبارٌ يقرأها من البيئة يمرّ أخضر
على جهازٍ ويسقط على آخر.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from hr.attendance import (
    evaluate_punch, haversine_meters, ip_is_allowed, open_check_in, pair_events,
    record_punch, recompute_attendance_day, resolve_attendance_date, scheduled_minutes,
    shift_for,
)
from hr.models import (
    AttendanceDay, CheckEvent, Employee, Shift, ShiftAssignment, WorkLocation,
)
from tenants.models import Tenant, TenantSettings

HEBRON = ZoneInfo("Asia/Hebron")

# مقرّ الشركة ونقطتان حوله: واحدة على بُعد ~60م والأخرى على بُعد ~1.1كم.
OFFICE_LAT = Decimal("31.532570")
OFFICE_LNG = Decimal("35.095390")
NEAR_LAT, NEAR_LNG = Decimal("31.533100"), Decimal("35.095390")
FAR_LAT, FAR_LNG = Decimal("31.542570"), Decimal("35.095390")


def at(year, month, day, hour, minute=0):
    """لحظةٌ واعية بتوقيت الخليل — لا `datetime` ساذجة في هذا الملف."""
    return datetime(year, month, day, hour, minute, tzinfo=HEBRON)


class AttendanceTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الحضور")
        self.user = User.objects.create_user("punch-user", password="x")
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000, user=self.user)
        self.location = WorkLocation.objects.create(
            tenant=self.tenant, name="المقر", latitude=OFFICE_LAT, longitude=OFFICE_LNG,
            radius_m=150)

    def make_shift(self, **overrides):
        values = dict(
            tenant=self.tenant, name=overrides.pop("name", "صباحي"),
            start1=time(9, 0), end1=time(17, 0), grace_minutes=0,
            overtime_after_minutes=0, weekly_off_days=[4],
        )
        values.update(overrides)
        return Shift.objects.create(**values)

    def assign(self, shift, start=date(2026, 1, 1), end=None):
        return ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=shift,
            start_date=start, end_date=end)

    def punch(self, kind, moment, **kwargs):
        return record_punch(self.employee, kind=kind, moment=moment, **kwargs)


class HaversineTest(TestCase):
    def test_known_distance_is_within_one_percent(self):
        """درجةُ خط عرضٍ واحدة ≈ 111.2 كم — مرجعٌ لا يعتمد على تنفيذنا."""
        metres = haversine_meters(Decimal("31.0"), Decimal("35.0"), Decimal("32.0"), Decimal("35.0"))
        self.assertAlmostEqual(metres, 111_195, delta=1_200)

    def test_same_point_is_zero(self):
        self.assertEqual(haversine_meters(31, 35, 31, 35), 0.0)


class IpAllowlistTest(TestCase):
    def test_empty_allowlist_means_no_network_restriction(self):
        """قائمةٌ فارغة = «بلا قيد» لا «امنع الجميع» — الفرق يقفل الشركة كلها."""
        self.assertTrue(ip_is_allowed("8.8.8.8", ""))

    def test_single_address_and_cidr_range(self):
        self.assertTrue(ip_is_allowed("192.168.1.7", "192.168.1.0/24"))
        self.assertFalse(ip_is_allowed("10.0.0.5", "192.168.1.0/24"))
        self.assertTrue(ip_is_allowed("10.0.0.5", "192.168.1.0/24, 10.0.0.5"))

    def test_unparsable_entries_are_ignored_not_fatal(self):
        """نصٌّ ملصوق في مربّع الإعدادات لا يجوز أن يُسقط بصمةً صحيحة."""
        self.assertTrue(ip_is_allowed("192.168.1.7", "hello\n192.168.1.0/24\n\n"))

    def test_malformed_client_ip_is_rejected_against_a_real_list(self):
        self.assertFalse(ip_is_allowed("", "192.168.1.0/24"))


class GeofenceTest(AttendanceTestBase):
    def test_inside_radius_is_accepted(self):
        decision = evaluate_punch(self.employee, latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.location, self.location)
        self.assertLess(decision.distance_m, 150)

    def test_outside_radius_is_rejected_with_a_reason_and_distance(self):
        decision = evaluate_punch(self.employee, latitude=FAR_LAT, longitude=FAR_LNG)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, CheckEvent.REJECT_OUT_OF_RANGE)
        self.assertGreater(decision.distance_m, 900)

    def test_rejected_punch_is_still_recorded(self):
        """المحاولة المرفوضة واقعةٌ إدارية — محوُها يمحو الدليل."""
        event = self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9), latitude=FAR_LAT, longitude=FAR_LNG)
        self.assertFalse(event.accepted)
        self.assertEqual(event.reject_reason, CheckEvent.REJECT_OUT_OF_RANGE)
        self.assertEqual(CheckEvent.objects.count(), 1)
        # ولا تُدخل يوماً في الحساب.
        self.assertFalse(AttendanceDay.objects.exists())

    def test_missing_geo_is_rejected_when_the_location_requires_it(self):
        decision = evaluate_punch(self.employee)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, CheckEvent.REJECT_NO_GEO)

    def test_allowed_ip_rescues_a_punch_without_coordinates(self):
        self.location.ip_allowlist = "192.168.10.0/24"
        self.location.save(update_fields=["ip_allowlist"])
        decision = evaluate_punch(self.employee, ip="192.168.10.44")
        self.assertTrue(decision.accepted)

    def test_allowed_ip_rescues_a_punch_outside_the_radius(self):
        self.location.ip_allowlist = "192.168.10.0/24"
        self.location.save(update_fields=["ip_allowlist"])
        decision = evaluate_punch(
            self.employee, latitude=FAR_LAT, longitude=FAR_LNG, ip="192.168.10.44")
        self.assertTrue(decision.accepted)

    def test_ip_fallback_can_be_switched_off(self):
        self.location.ip_allowlist = "192.168.10.0/24"
        self.location.allow_ip_fallback = False
        self.location.save(update_fields=["ip_allowlist", "allow_ip_fallback"])
        decision = evaluate_punch(
            self.employee, latitude=FAR_LAT, longitude=FAR_LNG, ip="192.168.10.44")
        self.assertFalse(decision.accepted)

    def test_blocked_network_rejects_a_punch_that_is_inside_the_radius(self):
        self.location.ip_allowlist = "192.168.10.0/24"
        self.location.save(update_fields=["ip_allowlist"])
        decision = evaluate_punch(
            self.employee, latitude=NEAR_LAT, longitude=NEAR_LNG, ip="10.0.0.9")
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, CheckEvent.REJECT_IP_BLOCKED)

    def test_required_photo_blocks_a_punch_without_one(self):
        self.location.require_photo = True
        self.location.save(update_fields=["require_photo"])
        decision = evaluate_punch(self.employee, latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, CheckEvent.REJECT_PHOTO_REQUIRED)
        allowed = evaluate_punch(
            self.employee, latitude=NEAR_LAT, longitude=NEAR_LNG,
            photo_url="https://example.test/a.jpg")
        self.assertTrue(allowed.accepted)

    def test_company_without_locations_accepts_every_punch(self):
        """شركةٌ لم تضبط مواقعها بعد يجب أن تستطيع تشغيل الحضور."""
        self.location.delete()
        self.assertTrue(evaluate_punch(self.employee).accepted)

    def test_employee_bound_to_a_location_is_measured_against_it_alone(self):
        far_site = WorkLocation.objects.create(
            tenant=self.tenant, name="المستودع", latitude=FAR_LAT, longitude=FAR_LNG,
            radius_m=150)
        self.employee.work_location = far_site
        self.employee.save(update_fields=["work_location"])
        # واقفٌ عند المقر — لكنه مربوط بالمستودع، فالبصمة خارج نطاقه.
        decision = evaluate_punch(self.employee, latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.location, far_site)

    def test_unbound_employee_is_matched_to_the_nearest_site(self):
        """من يتنقّل بين فرعين يُنسب لأقربهما لا لأول ما وُجد في الجدول."""
        WorkLocation.objects.create(
            tenant=self.tenant, name="المستودع", latitude=FAR_LAT, longitude=FAR_LNG,
            radius_m=150)
        decision = evaluate_punch(self.employee, latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.location, self.location)


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class AttendanceDateBoundaryTest(AttendanceTestBase):
    """حدود اليوم — أخطر ما في المحرّك، وأخفّه ظهوراً حين يخطئ."""

    def test_day_shift_punches_belong_to_their_own_calendar_day(self):
        self.assign(self.make_shift())
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 2, 9)), date(2026, 3, 2))
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 2, 23, 59)), date(2026, 3, 2))

    def test_overnight_shift_keeps_the_start_day(self):
        """من دخل العاشرة مساءً وخرج السادسة صباحاً عمل يوماً واحداً لا يومين."""
        night = self.make_shift(name="ليلي", start1=time(22, 0), end1=time(6, 0))
        self.assign(night)
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 2, 22, 5)), date(2026, 3, 2))
        # 00:30 و06:00 من اليوم التالي ما زالتا من مناوبة أمس.
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 3, 0, 30)), date(2026, 3, 2))
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 3, 6, 0)), date(2026, 3, 2))

    def test_late_departure_within_grace_still_belongs_to_the_previous_day(self):
        self.assign(self.make_shift(name="ليلي", start1=time(22, 0), end1=time(6, 0)))
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 3, 9, 0)), date(2026, 3, 2))

    def test_beyond_the_overnight_grace_a_new_day_begins(self):
        self.assign(self.make_shift(name="ليلي", start1=time(22, 0), end1=time(6, 0)))
        self.assertEqual(
            resolve_attendance_date(self.employee, at(2026, 3, 3, 11, 0)), date(2026, 3, 3))

    def test_overnight_shift_computes_one_day_of_work(self):
        self.assign(self.make_shift(name="ليلي", start1=time(22, 0), end1=time(6, 0)))
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 22, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 3, 6, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)

        days = AttendanceDay.objects.all()
        self.assertEqual(days.count(), 1, "الوردية الليلية يومٌ واحد لا يومان")
        row = days.first()
        self.assertEqual(row.date, date(2026, 3, 2))
        self.assertEqual(row.worked_minutes, 8 * 60)
        self.assertEqual(row.scheduled_minutes, 8 * 60)
        self.assertEqual(row.status, AttendanceDay.STATUS_PRESENT)

    def test_dst_spring_forward_day_keeps_its_scheduled_minutes(self):
        """يوم تقديم الساعة: 09:00→17:00 تبقى ثماني ساعات لأن القفزة قبلها."""
        self.assign(self.make_shift())
        shift = Shift.objects.get(name="صباحي")
        self.assertEqual(scheduled_minutes(shift, date(2026, 3, 28)), 8 * 60)


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class DayComputationTest(AttendanceTestBase):
    def test_present_day_has_no_lateness(self):
        self.assign(self.make_shift())
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 17, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)

        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.status, AttendanceDay.STATUS_PRESENT)
        self.assertEqual(row.late_minutes, 0)
        self.assertEqual(row.worked_minutes, 480)
        self.assertEqual(row.absence_days, Decimal("0"))

    def test_grace_period_absorbs_a_small_delay(self):
        self.assign(self.make_shift(grace_minutes=15))
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 10), latitude=NEAR_LAT, longitude=NEAR_LNG)

        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.late_minutes, 0)
        self.assertEqual(row.status, AttendanceDay.STATUS_PRESENT)

    def test_delay_past_the_grace_counts_only_the_excess(self):
        """التأخير يُقاس من نهاية السماح لا من بداية الدوام."""
        self.assign(self.make_shift(grace_minutes=15))
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 40), latitude=NEAR_LAT, longitude=NEAR_LNG)

        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.late_minutes, 25)
        self.assertEqual(row.status, AttendanceDay.STATUS_LATE)

    def test_two_period_day_sums_both_and_marks_early_leave(self):
        self.assign(self.make_shift(
            name="فترتان", start1=time(9, 0), end1=time(13, 0),
            start2=time(16, 0), end2=time(20, 0)))
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 13, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 16, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 19, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)

        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.scheduled_minutes, 8 * 60)
        self.assertEqual(row.worked_minutes, 7 * 60)
        self.assertEqual(row.early_leave_minutes, 60)

    def test_overtime_counts_only_beyond_the_declared_threshold(self):
        self.assign(self.make_shift(overtime_after_minutes=30))
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 19, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)

        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.worked_minutes, 600)
        # ساعتان زائدتان ناقص عتبة النصف ساعة.
        self.assertEqual(row.overtime_minutes, 90)

    def test_weekly_off_day_is_never_an_absence(self):
        self.assign(self.make_shift(weekly_off_days=[4]))  # الجمعة
        friday = date(2026, 3, 6)
        self.assertEqual(friday.weekday(), 4)
        row = recompute_attendance_day(self.employee, friday)
        self.assertEqual(row.status, AttendanceDay.STATUS_OFF)
        self.assertEqual(row.absence_days, Decimal("0"))

    def test_scheduled_workday_without_punches_is_an_absence(self):
        self.assign(self.make_shift())
        row = recompute_attendance_day(self.employee, date(2026, 3, 2))
        self.assertEqual(row.status, AttendanceDay.STATUS_ABSENT)
        self.assertEqual(row.absence_days, Decimal("1"))

    def test_day_without_a_shift_is_unscheduled_not_absent(self):
        """الشركة التي لم تبنِ جداولها لا تستيقظ على موظفيها كلّهم غائبين."""
        row = recompute_attendance_day(self.employee, date(2026, 3, 2))
        self.assertEqual(row.status, AttendanceDay.STATUS_UNSCHEDULED)
        self.assertEqual(row.absence_days, Decimal("0"))

    def test_strict_company_marks_unscheduled_empty_days_as_absent(self):
        TenantSettings.objects.create(tenant=self.tenant, hr_absence_requires_shift=False)
        row = recompute_attendance_day(self.employee, date(2026, 3, 2))
        self.assertEqual(row.status, AttendanceDay.STATUS_ABSENT)
        self.assertEqual(row.absence_days, Decimal("1"))

    def test_unscheduled_day_with_punches_still_records_minutes(self):
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 14, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.status, AttendanceDay.STATUS_UNSCHEDULED)
        self.assertEqual(row.worked_minutes, 300)
        self.assertEqual(row.late_minutes, 0, "بلا وردية لا وقتَ متوقَّعاً فلا تأخير")

    def test_recompute_is_idempotent(self):
        """الحتميّة شرط: الاستدعاء العاشر كالأول، ولا صفَّ ثانياً لليوم نفسه."""
        self.assign(self.make_shift())
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 20), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 17, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)

        first = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        snapshot = (first.status, first.worked_minutes, first.late_minutes, first.overtime_minutes)
        for _ in range(3):
            recompute_attendance_day(self.employee, date(2026, 3, 2))
        again = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(
            (again.status, again.worked_minutes, again.late_minutes, again.overtime_minutes),
            snapshot)
        self.assertEqual(AttendanceDay.objects.filter(date=date(2026, 3, 2)).count(), 1)

    def test_manual_override_survives_recomputation(self):
        """من صحّح يوماً بيده أعلن أن البصمات لا تحكيه."""
        self.assign(self.make_shift())
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 11, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        row.status = AttendanceDay.STATUS_PRESENT
        row.late_minutes = 0
        row.is_manual_override = True
        row.save()

        recompute_attendance_day(self.employee, date(2026, 3, 2))
        row.refresh_from_db()
        self.assertEqual(row.status, AttendanceDay.STATUS_PRESENT)
        self.assertEqual(row.late_minutes, 0)

    def test_voided_events_leave_the_computation(self):
        self.assign(self.make_shift())
        entry = self.punch(
            CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 17, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        entry.is_voided = True
        entry.save(update_fields=["is_voided"])
        recompute_attendance_day(self.employee, date(2026, 3, 2))

        row = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(row.worked_minutes, 0)
        self.assertTrue(CheckEvent.objects.filter(pk=entry.pk).exists(), "المُبطَل يبقى في السجل")


class EventPairingTest(AttendanceTestBase):
    def _event(self, kind, moment):
        return CheckEvent(
            employee=self.employee, kind=kind, ts=moment, attendance_date=moment.date())

    def test_duplicate_check_in_keeps_the_first(self):
        """أول دخولٍ هو لحظة الوصول التي يُقاس عليها التأخير."""
        events = [
            self._event(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0)),
            self._event(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 5)),
            self._event(CheckEvent.KIND_OUT, at(2026, 3, 2, 17, 0)),
        ]
        pairs = pair_events(events)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0].ts, at(2026, 3, 2, 9, 0))

    def test_checkout_without_a_check_in_is_ignored(self):
        events = [self._event(CheckEvent.KIND_OUT, at(2026, 3, 2, 17, 0))]
        self.assertEqual(pair_events(events), [])

    def test_unclosed_check_in_contributes_no_minutes(self):
        events = [self._event(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0))]
        self.assertEqual(pair_events(events), [])


class ShiftResolutionTest(AttendanceTestBase):
    def test_latest_assignment_wins_on_overlap(self):
        """المناوبة الجديدة تنسخ ما قبلها لا تتصارع معه."""
        morning = self.make_shift(name="صباحي")
        evening = self.make_shift(name="مسائي", start1=time(16, 0), end1=time(23, 0))
        self.assign(morning, start=date(2026, 1, 1))
        self.assign(evening, start=date(2026, 3, 1))

        self.assertEqual(shift_for(self.employee, date(2026, 2, 10)), morning)
        self.assertEqual(shift_for(self.employee, date(2026, 3, 10)), evening)

    def test_closed_assignment_stops_covering_after_its_end(self):
        morning = self.make_shift(name="صباحي")
        self.assign(morning, start=date(2026, 1, 1), end=date(2026, 1, 31))
        self.assertEqual(shift_for(self.employee, date(2026, 1, 15)), morning)
        self.assertIsNone(shift_for(self.employee, date(2026, 2, 1)))


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class OpenCheckInTest(AttendanceTestBase):
    def test_open_check_in_is_the_source_of_the_live_counter(self):
        moment = timezone.now() - timedelta(hours=2)
        self.punch(CheckEvent.KIND_IN, moment, latitude=NEAR_LAT, longitude=NEAR_LNG)

        current = open_check_in(self.employee)
        self.assertIsNotNone(current)
        self.assertEqual(current.kind, CheckEvent.KIND_IN)
        # اليوم يُقاس من لحظة البصمة لا من لحظة القراءة: من بصم 23:00 ثم قرأ
        # عدّاده 01:00 ما زال في دوام أمس — ولهذا يمتدّ البحث يوماً للوراء.
        self.assertEqual(current.attendance_date, timezone.localdate(moment))

    def test_checkout_closes_the_counter(self):
        self.punch(
            CheckEvent.KIND_IN, timezone.now() - timedelta(hours=2),
            latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, timezone.now(), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.assertIsNone(open_check_in(self.employee))

    def test_a_rejected_punch_never_opens_the_counter(self):
        self.punch(CheckEvent.KIND_IN, timezone.now(), latitude=FAR_LAT, longitude=FAR_LNG)
        self.assertIsNone(open_check_in(self.employee))


class FinancialInertnessTest(AttendanceTestBase):
    """المعلم الثاني لا يمسّ ديناراً — المال يبدأ من الرواتب في المعلم السابع."""

    def test_recording_attendance_creates_no_journal_and_no_account(self):
        from accounting.models import Account, JournalHeader, JournalLine

        before = (Account.objects.count(), JournalHeader.objects.count(), JournalLine.objects.count())
        self.assign(self.make_shift())
        self.punch(CheckEvent.KIND_IN, at(2026, 3, 2, 9, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        self.punch(CheckEvent.KIND_OUT, at(2026, 3, 2, 17, 0), latitude=NEAR_LAT, longitude=NEAR_LNG)
        recompute_attendance_day(self.employee, date(2026, 3, 2))

        after = (Account.objects.count(), JournalHeader.objects.count(), JournalLine.objects.count())
        self.assertEqual(before, after)
