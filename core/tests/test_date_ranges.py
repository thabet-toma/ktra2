"""حارس المدى الزمني المحلّي — ولماذا `__date` ممنوعة على أعمدة الوقت.

الاختبارات هنا تحرس شيئين لا يحرسهما شيء آخر:

1. **دلالة المدى** — حدود اليوم/الأسبوع/الشهر، والحدّ الأعلى المفتوح.
2. **حارس ساكن ضد الارتداد** — لا `__date` جديدة على `DateTimeField` في كود
   المشروع. لا يمكن للاختبارات كشف هذا ديناميكياً: المجموعة تعمل على SQLite
   حيث `__date` تعمل تماماً، بينما تنهار على MySQL بلا جداول مناطق زمنية
   (`CONVERT_TZ` → `NULL` → صفر صفوف بصمت). فالحارس ساكن بالضرورة.
"""
import datetime as dt
import pathlib
import re

from django.apps import apps
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core.date_ranges import (
    RANGE_PRESETS, day_bounds, filter_local_date_range, local_day_start, resolve_preset,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class LocalDayBoundsTests(SimpleTestCase):
    def test_day_start_is_local_midnight_and_aware(self):
        start = local_day_start(dt.date(2026, 8, 27))
        self.assertIsNotNone(start.tzinfo)
        local = timezone.localtime(start)
        self.assertEqual((local.hour, local.minute, local.second), (0, 0, 0))
        self.assertEqual(local.date(), dt.date(2026, 8, 27))

    def test_bounds_are_half_open_so_last_microsecond_is_included(self):
        """`<= 23:59:59` يُسقط كسور `datetime(6)`؛ `< غدٍ 00:00` لا يُسقط شيئاً."""
        day = dt.date(2026, 8, 27)
        start, end = day_bounds(day, day)
        self.assertEqual(end - start, dt.timedelta(days=1))
        last = start + dt.timedelta(days=1) - dt.timedelta(microseconds=1)
        self.assertLess(last, end)

    def test_open_ended_bounds(self):
        self.assertEqual(day_bounds(None, None), (None, None))


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class ResolvePresetTests(SimpleTestCase):
    TODAY = dt.date(2026, 8, 27)  # خميس

    def test_today_and_yesterday(self):
        self.assertEqual(resolve_preset("today", self.TODAY), (self.TODAY, self.TODAY))
        y = dt.date(2026, 8, 26)
        self.assertEqual(resolve_preset("yesterday", self.TODAY), (y, y))

    def test_week_starts_on_saturday(self):
        start, end = resolve_preset("week", self.TODAY)
        self.assertEqual(start, dt.date(2026, 8, 22))
        self.assertEqual(start.strftime("%A"), "Saturday")
        self.assertEqual(end, self.TODAY)

    def test_week_on_saturday_itself_is_a_single_day(self):
        saturday = dt.date(2026, 8, 22)
        self.assertEqual(resolve_preset("week", saturday), (saturday, saturday))

    def test_month_quarter_year(self):
        self.assertEqual(resolve_preset("month", self.TODAY)[0], dt.date(2026, 8, 1))
        self.assertEqual(resolve_preset("quarter", self.TODAY)[0], dt.date(2026, 7, 1))
        self.assertEqual(resolve_preset("year", self.TODAY)[0], dt.date(2026, 1, 1))

    def test_all_has_no_bounds(self):
        self.assertEqual(resolve_preset("all", self.TODAY), (None, None))

    def test_unknown_preset_falls_back_to_today(self):
        self.assertEqual(resolve_preset("nonsense", self.TODAY), (self.TODAY, self.TODAY))

    def test_every_advertised_preset_resolves(self):
        for name in RANGE_PRESETS:
            with self.subTest(preset=name):
                resolve_preset(name, self.TODAY)  # لا يرمي


class FilterCompilesWithoutConvertTzTests(TestCase):
    """الاستعلام المولَّد يجب ألّا يحوي `CONVERT_TZ` — هي مصدر العطل نفسه."""

    def test_sql_has_no_convert_tz(self):
        from core.models import ActivityLog

        qs = filter_local_date_range(
            ActivityLog.objects.all(), "timestamp",
            date_from=dt.date(2026, 8, 1), date_to=dt.date(2026, 8, 27),
        )
        sql = str(qs.query).upper()
        self.assertNotIn("CONVERT_TZ", sql)
        self.assertNotIn("DATE(", sql)


class NoDateLookupOnDateTimeFieldTests(SimpleTestCase):
    """حارس ارتداد ساكن: `__date` على عمود وقت = صفوف مبتلَعة بصمت في الإنتاج."""

    # الوحدات المفحوصة — كود المشروع دون venv/الهجرات/الاختبارات.
    APPS = (
        "accountant_portal", "accounting", "after_sales", "core", "device_registry",
        "docshare", "hr", "import_file", "inventory", "logistics", "partners",
        "sales", "store", "tenants",
    )
    PATTERN = re.compile(r"(\w+)__date(?:__(?:gte|lte|gt|lt|range|exact|in))?\s*=")
    # الملفّان اللذان يشرحان النمط الممنوع نصّاً — لا يستعملانه.
    EXEMPT = {"core/date_ranges.py", "core/reports/_framework.py"}

    def _datetime_field_names(self) -> set[str]:
        names = set()
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if getattr(field, "get_internal_type", None) is None:
                    continue
                if field.get_internal_type() == "DateTimeField":
                    names.add(field.name)
        return names

    def test_no_new_date_lookup_on_datetime_columns(self):
        datetime_fields = self._datetime_field_names()
        offenders = []
        for app in self.APPS:
            for path in (REPO_ROOT / app).rglob("*.py"):
                parts = set(path.parts)
                if "migrations" in parts or "tests" in parts:
                    continue
                if path.relative_to(REPO_ROOT).as_posix() in self.EXEMPT:
                    continue
                for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1,
                ):
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    for match in self.PATTERN.finditer(line):
                        field = match.group(1).split("__")[-1]
                        if field in datetime_fields:
                            offenders.append(
                                f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}",
                            )
        self.assertEqual(
            offenders, [],
            "استعمال `__date` على عمود DateTimeField ينهار على MySQL بلا جداول "
            "مناطق زمنية (CONVERT_TZ → NULL → صفر صفوف بلا خطأ). استعمل "
            "core.date_ranges.filter_local_date_range بدلاً منه:\n"
            + "\n".join(offenders),
        )
