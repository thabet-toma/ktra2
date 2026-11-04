"""محرّك المواعيد ولائحة المواعيد والتقويم — #274.

**القواعد المحسومة التي يثبتها هذا الملف:**

1. **لا تاريخ قانوني في الكود** (`accounting_office/deadlines.py`): كلُّ يومٍ
   تقرؤه الدالّة من سطر اللائحة، ولا رقمَ حرفياً إلا `0` و`1` و`12` (أعدادُ
   التقويم). يحرسه مسحُ `ast` في `NoLegalDateInCodeTest`.
2. **فلسطين بلا زحزحة**: الموعدُ يُحسب من النصّ كما هو، ويُنبَّه إذا وقع في يوم
   عطلة السلطة — لا تأجيلَ صامتاً، لأنّ البحث لم يجد نصاً يؤجّله.
3. **إسرائيل تُؤجّل بعد يوم راحة الزبون**: الموعدُ القانونيُّ الواقع في يوم راحة
   المكلَّف أو يوم إغلاق السلطة يُزحزَح يوماً بيوم حتى يوم عمل.
4. **اللائحة بياناتٌ مؤرَّخة**: النسخةُ السارية لسنةٍ هي أكبر `version`، وسنةٌ بلا
   نسخةٍ تأخذ آخر سنةٍ سابقة وتُعلَن «تقديرية» فتُتجاهل تعديلاتها المنشورة.
5. **الخدمة × البطاقة = الالتزامات**: شروطُ كل سطرٍ على اللائحة لا في الكود.
6. **التقويم محسوبٌ لا محفوظ**: قراءةٌ خالصة، وتغييرُ سطرٍ في القاعدة يغيّر ما
   يعرضه الطلبُ التالي فوراً.
"""
import ast
import calendar as calendar_module
import datetime
import importlib
import pathlib
import re
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.deadlines import (
    ALL_DAYS_CLOSED_WARNING,
    DeadlineResult,
    compute_deadline,
    period_label,
    periods_for,
    service_periods,
)
from accounting_office.models import (
    CADENCE_ANNUAL,
    CADENCE_QUARTERLY,
    CONDITION_KEYS,
    DeadlineRule,
    DeadlineSchedule,
    OfficeClient,
    REST_DAY_POLICY_POSTPONE_CLIENT,
    REST_DAY_POLICY_WARN,
    RULE_KIND_DAY_OF_NEXT_MONTH,
    RULE_KIND_END_OF_PERIOD,
    RULE_KIND_MONTH_DAY_NEXT_YEAR,
    TaxCard,
    TaxThreshold,
)
from accounting_office.services import set_client_setting, set_office_setting
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
CALENDAR = f"{BASE}calendar/"
RULES = f"{BASE}deadline-rules/"
CLIENTS = f"{BASE}clients/"

#: هجرةُ بيانات اللائحة — تُستدعى بدالّتها كما هي (نمط `seed_published_thresholds`)،
#: فلا نسخةَ ثانية من التواريخ في الاختبار.
SCHEDULES_MIGRATION = "accounting_office.migrations.0004_deadline_schedules"
THRESHOLDS_MIGRATION = "accounting_office.migrations.0003_services_packages_thresholds"

#: أرقام البحث المنشورة (`research/acct-tax-*`) — **ثوابت الاختبار** التي تُقاس
#: عليها بياناتُ الهجرة. رقمٌ يتغيّر فيها يسقط هنا لا في الإنتاج.
PS_LAW_URL = "http://muqtafi.birzeit.edu/pg/getleg.asp?id=18929"
IL_2026_URL = "https://www.gov.il/he/pages/pa151025-2"
IL_2027_URL = "https://www.gov.il/he/pages/pa131026-1"
IL_DETAILED_URL = "https://www.gov.il/he/pages/pa130725-2"

#: `date.weekday()`: الاثنين = 0.
MONDAY, TUESDAY, WEDNESDAY = 0, 1, 2
THURSDAY, FRIDAY, SATURDAY, SUNDAY = 3, 4, 5, 6

WEEKDAY_KEYS_BY_INDEX: tuple[str, ...] = (
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
)


def seed_published_thresholds():
    migration = importlib.import_module(THRESHOLDS_MIGRATION)
    migration.seed_tax_thresholds(django_apps, None)


def seed_deadline_schedules():
    """بياناتُ اللائحة **من هجرة البيانات نفسها** — لا زرعٌ يدويٌّ موازٍ لها."""
    migration = importlib.import_module(SCHEDULES_MIGRATION)
    migration.seed_deadline_schedules(django_apps, None)


def first_of_next_month(day):
    """أولُ يومٍ في الشهر التالي — بحسابٍ لا بتاريخٍ مفترض."""
    return (day.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)


def last_of_month(day):
    _first, last = calendar_module.monthrange(day.year, day.month)
    return day.replace(day=last)


def find_month(year, weekday, rule_day=15):
    """شهرٌ يقع يومه `rule_day` من الشهر التالي في يوم الأسبوع المطلوب.

    يُحسب في الاختبار ولا يُفترض: تقويمُ سنةٍ ما يُقرأ من `calendar` لا من ذاكرة
    كاتب الاختبار.
    """
    for month in range(1, 13):
        candidate = first_of_next_month(datetime.date(year, month, 1)).replace(
            day=rule_day,
        )
        if candidate.weekday() == weekday:
            return month
    raise AssertionError(f"لا شهر في {year} يقع يوم {rule_day} من التالي في {weekday}.")


def ready_office(tenant, tax_system="PS"):
    set_office_setting(tenant, "tax_system", tax_system)
    set_office_setting(tenant, "office_size", "small")


def catalog(tenant):
    return {row.code: row for row in services.ensure_default_services(tenant)}


def step_back(actual, lead, office_rest_days=("fri",)):
    """الموعدُ الداخليّ المتوقَّع: الفعليُّ ناقصَ الإعداد ثم رجوعٌ عن عطلة المكتب.

    يُحسب في الاختبار كما ينصّ المحرّك — لا تاريخاً مفترضاً يخفي انزياحاً.
    """
    day = actual - datetime.timedelta(days=lead)
    while WEEKDAY_KEYS_BY_INDEX[day.weekday()] in office_rest_days:
        day -= datetime.timedelta(days=1)
    return day


# ── الدالّة النقيّة: بلا قاعدة، وبأسطرٍ غير محفوظة ──────────────────────────
class PureDeadlineTestCase(SimpleTestCase):
    """يبني أسطر اللائحة في الذاكرة — لا صفَّ في القاعدة ولا استعلام."""

    def rule(self, **overrides):
        fields = {
            "code": "probe",
            "rule_kind": RULE_KIND_DAY_OF_NEXT_MONTH,
            "rule_day": 15,
            "rule_month": None,
            "cadence": CADENCE_QUARTERLY,
            "electronic_extension_days": 0,
            "period_overrides": {},
            "is_generated": True,
            "needs_review": False,
            "conditions": {},
        }
        fields.update(overrides)
        return DeadlineRule(**fields)

    def compute(self, rule, period_end, **options):
        values = {
            "period_start": period_end.replace(day=1),
            "period_end": period_end,
            "estimated": False,
            "client_rest_days": [],
            "office_rest_days": [],
            "filing_method": "manual",
            "internal_lead_days": 0,
            "schedule_policy": REST_DAY_POLICY_WARN,
            "authority_closed_days": ["fri"],
        }
        values.update(options)
        return compute_deadline(rule, **values)

    def israeli(self, rule, period_end, **overrides):
        """النسخةُ «التقديرية» الإسرائيلية: سياسةُ التأجيل ويومُ إغلاق السبت."""
        values = {
            "schedule_policy": REST_DAY_POLICY_POSTPONE_CLIENT,
            "authority_closed_days": ["sat"],
            "estimated": True,
        }
        values.update(overrides)
        return self.compute(rule, period_end, **values)


class PalestinianDeadlineTest(PureDeadlineTestCase):
    """فلسطين: الموعدُ من النصّ كما هو، والتنبيهُ بدل الزحزحة."""

    def test_the_january_vat_report_is_due_on_february_fifteenth(self):
        result = self.compute(self.rule(), datetime.date(2026, 1, 31))

        self.assertEqual(result.legal_date, datetime.date(2026, 2, 15))
        self.assertEqual(result.official_date, datetime.date(2026, 2, 15))
        self.assertEqual(result.actual_deadline, datetime.date(2026, 2, 15))
        self.assertFalse(result.postponed)
        self.assertEqual(result.period_start, datetime.date(2026, 1, 1))
        self.assertEqual(result.period_end, datetime.date(2026, 1, 31))
        self.assertEqual(result.rule_code, "probe")
        self.assertFalse(result.estimated)

    def test_a_friday_deadline_stays_where_it_is_with_a_warning(self):
        """«تنبيه بلا زحزحة» — البحثُ لم يجد نصاً يؤجّل موعداً وقع في عطلة."""
        month = find_month(2026, FRIDAY)
        period_end = last_of_month(datetime.date(2026, month, 1))
        result = self.compute(self.rule(), period_end)

        self.assertEqual(result.legal_date.weekday(), FRIDAY)
        self.assertEqual(result.official_date, result.legal_date)
        self.assertFalse(result.postponed)
        self.assertTrue(
            any("الموعد يوم الجمعة" in warning for warning in result.warnings),
            result.warnings,
        )

    def test_a_deadline_outside_the_rest_day_carries_no_warning(self):
        month = find_month(2026, WEDNESDAY)
        period_end = last_of_month(datetime.date(2026, month, 1))
        result = self.compute(self.rule(), period_end)

        self.assertEqual(result.official_date, result.legal_date)
        self.assertEqual(result.warnings, [])

    def test_the_period_end_rule_is_the_last_day_of_the_period(self):
        rule = self.rule(rule_kind=RULE_KIND_END_OF_PERIOD, cadence=CADENCE_QUARTERLY)
        result = self.compute(rule, datetime.date(2026, 3, 31))

        self.assertEqual(result.legal_date, datetime.date(2026, 3, 31))

    def test_the_annual_return_is_the_month_and_day_of_the_next_year(self):
        rule = self.rule(
            rule_kind=RULE_KIND_MONTH_DAY_NEXT_YEAR,
            rule_month=4,
            rule_day=30,
            cadence=CADENCE_ANNUAL,
        )
        result = self.compute(rule, datetime.date(2026, 12, 31))

        self.assertEqual(result.legal_date, datetime.date(2027, 4, 30))


class IsraeliPostponementTest(PureDeadlineTestCase):
    """إسرائيل: التأجيلُ بعد يوم راحة الزبون، ثم يوم إغلاق السلطة."""

    def test_a_muslim_client_moves_from_friday_to_sunday(self):
        month = find_month(2026, FRIDAY)
        result = self.israeli(
            self.rule(),
            last_of_month(datetime.date(2026, month, 1)),
            client_rest_days=["fri"],
        )

        self.assertEqual(result.legal_date.weekday(), FRIDAY)
        self.assertEqual(result.official_date.weekday(), SUNDAY)
        self.assertTrue(result.postponed)

    def test_a_jewish_client_moves_from_saturday_to_sunday(self):
        month = find_month(2026, SATURDAY)
        result = self.israeli(
            self.rule(),
            last_of_month(datetime.date(2026, month, 1)),
            client_rest_days=["sat"],
        )

        self.assertEqual(result.legal_date.weekday(), SATURDAY)
        self.assertEqual(result.official_date.weekday(), SUNDAY)

    def test_a_christian_client_moves_from_sunday_to_monday(self):
        month = find_month(2026, SUNDAY)
        result = self.israeli(
            self.rule(),
            last_of_month(datetime.date(2026, month, 1)),
            client_rest_days=["sun"],
        )

        self.assertEqual(result.legal_date.weekday(), SUNDAY)
        self.assertEqual(result.official_date.weekday(), MONDAY)
        self.assertTrue(result.postponed)

    def test_a_jewish_client_keeps_a_sunday_deadline(self):
        """اليومُ المحسوبُ نفسه يعتمد على دين المكلَّف لا على إعداد المكتب."""
        month = find_month(2026, SUNDAY)
        result = self.israeli(
            self.rule(),
            last_of_month(datetime.date(2026, month, 1)),
            client_rest_days=["sat"],
        )

        self.assertEqual(result.official_date, result.legal_date)
        self.assertFalse(result.postponed)

    def test_the_authority_closed_day_defers_even_without_a_client_rest_day(self):
        month = find_month(2026, SATURDAY)
        result = self.israeli(
            self.rule(),
            last_of_month(datetime.date(2026, month, 1)),
            client_rest_days=[],
        )

        self.assertEqual(result.official_date.weekday(), SUNDAY)
        self.assertTrue(result.postponed)


class PublishedOverrideTest(PureDeadlineTestCase):
    """تعديلات النشرة: ما سببه يوم الراحة وحده يُعاد حسابه، وغيره يُؤخذ كما هو."""

    def override_rule(self, rest_day_only):
        return self.rule(period_overrides={
            "2026-03": {"date": "2026-04-27", "rest_day_only": rest_day_only},
        })

    def test_a_published_holiday_postponement_is_taken_as_published(self):
        result = self.israeli(
            self.override_rule(rest_day_only=False),
            datetime.date(2026, 3, 31),
            client_rest_days=[],
            estimated=False,
        )

        self.assertEqual(result.legal_date, datetime.date(2026, 4, 15))
        self.assertEqual(result.official_date, datetime.date(2026, 4, 27))
        self.assertTrue(result.postponed)

    def test_a_rest_day_only_postponement_is_recomputed_from_the_client(self):
        """الوسم (4) وحده: التاريخُ المنشور لزبونٍ راحتُه غير الجمعة لا يعنيه."""
        result = self.israeli(
            self.override_rule(rest_day_only=True),
            datetime.date(2026, 3, 31),
            client_rest_days=["sun"],
            estimated=False,
        )

        self.assertEqual(result.official_date, datetime.date(2026, 4, 15))
        self.assertFalse(result.postponed)

    def test_an_estimated_schedule_ignores_every_published_override(self):
        """«تقديري»: تعديلاتُ سنةٍ أخرى لا تنطبق على سنةٍ بلا لائحة."""
        result = self.israeli(
            self.override_rule(rest_day_only=False),
            datetime.date(2026, 3, 31),
            client_rest_days=[],
            estimated=True,
        )

        self.assertEqual(result.official_date, datetime.date(2026, 4, 15))


class ActualAndInternalDeadlineTest(PureDeadlineTestCase):
    def test_the_electronic_window_extends_the_actual_deadline(self):
        rule = self.rule(electronic_extension_days=4)
        period_end = datetime.date(2026, 1, 31)

        electronic = self.compute(rule, period_end, filing_method="electronic")
        manual = self.compute(rule, period_end, filing_method="manual")

        official = datetime.date(2026, 2, 15)
        self.assertEqual(electronic.actual_deadline, official + datetime.timedelta(days=4))
        self.assertEqual(manual.actual_deadline, official)

    def test_the_engine_uses_the_lead_days_it_is_given(self):
        """المحرّك لا يعرف اسماً لإعداد: يأخذ العددَ جاهزاً ويطرحه من الفعليّ."""
        period_end = datetime.date(2026, 1, 31)
        official = datetime.date(2026, 2, 15)

        for lead in (5, 7, 30):
            with self.subTest(lead=lead):
                result = self.compute(
                    self.rule(), period_end, internal_lead_days=lead,
                )
                self.assertEqual(
                    result.internal_deadline, official - datetime.timedelta(days=lead),
                )

    def test_the_internal_deadline_steps_back_before_the_office_rest_day(self):
        """الموعدُ الداخليّ يقع يوم جمعة (عطلة المكتب) ⇒ يرجع للخميس."""
        month = find_month(2026, FRIDAY)
        result = self.compute(
            self.rule(),
            last_of_month(datetime.date(2026, month, 1)),
            office_rest_days=["fri"],
        )

        self.assertEqual(result.actual_deadline.weekday(), FRIDAY)
        self.assertEqual(result.internal_deadline.weekday(), THURSDAY)
        self.assertEqual(
            result.internal_deadline, result.actual_deadline - datetime.timedelta(days=1),
        )

    def test_a_week_that_is_closed_end_to_end_is_announced_not_looped_forever(self):
        """إعداداتٌ تقول «كل الأيام عطلة» تُنبّه بدل أن تُعلّق الطلب."""
        every_day = list(WEEKDAY_KEYS_BY_INDEX)
        result = self.compute(
            self.rule(),
            datetime.date(2026, 1, 31),
            office_rest_days=every_day,
        )

        self.assertIn(ALL_DAYS_CLOSED_WARNING, result.warnings)

    def test_a_closed_week_does_not_hang_the_engine(self):
        every_day = list(WEEKDAY_KEYS_BY_INDEX)
        result = self.compute(
            self.rule(),
            datetime.date(2026, 1, 31),
            office_rest_days=every_day,
            client_rest_days=every_day,
            schedule_policy=REST_DAY_POLICY_POSTPONE_CLIENT,
            authority_closed_days=every_day,
        )

        self.assertIn(ALL_DAYS_CLOSED_WARNING, result.warnings)


class PeriodsForTest(SimpleTestCase):
    """محاذاةُ الفترات للتقويم — لا موعدَ هنا، فتراتٌ فقط."""

    YEAR_START = datetime.date(2026, 1, 1)
    YEAR_END = datetime.date(2026, 12, 31)

    def test_bimonthly_is_aligned_to_january_february(self):
        periods = periods_for("bimonthly", self.YEAR_START, self.YEAR_END)

        self.assertEqual(len(periods), 6)
        self.assertEqual(
            [(start.month, end.month) for start, end in periods],
            [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)],
        )
        self.assertEqual(periods[0], (self.YEAR_START, datetime.date(2026, 2, 28)))

    def test_quarterly_is_four_calendar_quarters(self):
        periods = periods_for("quarterly", self.YEAR_START, self.YEAR_END)

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)),
                (datetime.date(2026, 4, 1), datetime.date(2026, 6, 30)),
                (datetime.date(2026, 7, 1), datetime.date(2026, 9, 30)),
                (datetime.date(2026, 10, 1), datetime.date(2026, 12, 31)),
            ],
        )

    def test_annual_is_the_calendar_year(self):
        self.assertEqual(
            periods_for("annual", self.YEAR_START, self.YEAR_END),
            [(self.YEAR_START, self.YEAR_END)],
        )

    def test_monthly_gives_every_intersecting_month(self):
        periods = periods_for(
            "monthly", datetime.date(2026, 3, 15), datetime.date(2026, 5, 2),
        )

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)),
                (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30)),
                (datetime.date(2026, 5, 1), datetime.date(2026, 5, 31)),
            ],
        )

    def test_on_demand_has_no_periods(self):
        self.assertEqual(periods_for("on_demand", self.YEAR_START, self.YEAR_END), [])
        self.assertEqual(periods_for("service", self.YEAR_START, self.YEAR_END), [])
        self.assertEqual(periods_for(None, self.YEAR_START, self.YEAR_END), [])

    def test_a_single_day_range_still_gives_its_bucket(self):
        day = datetime.date(2026, 4, 9)
        self.assertEqual(periods_for("quarterly", day, day), [
            (datetime.date(2026, 4, 1), datetime.date(2026, 6, 30)),
        ])


class ServicePeriodsTest(SimpleTestCase):
    """فتراتُ خدمةٍ دوريتُها تتغيّر — **حزمٌ محاذاةٌ للتقويم، بلا فجوة ولا تداخل**.

    يُحقَن `frequency_of_month` في الاختبار: الدالّةُ نقيّة ولا تعرف خدمةً ولا
    قاعدة، وإنما تسأل «ما الدورية السارية في هذا الشهر؟».
    """

    @staticmethod
    def _monthly_then_bimonthly(change_on):
        def frequency(month):
            return "bimonthly" if month >= change_on else "monthly"

        return frequency

    @staticmethod
    def _always(cadence):
        def frequency(month):
            return cadence

        return frequency

    def test_a_frequency_change_in_april_opens_a_short_april_and_then_its_buckets(self):
        periods = service_periods(
            self._monthly_then_bimonthly(datetime.date(2026, 4, 1)),
            datetime.date(2026, 1, 1),
            datetime.date(2026, 12, 31),
        )

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), "monthly"),
                (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28), "monthly"),
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31), "monthly"),
                # نيسان وحدَه: الجزءُ المتبقّي من حزمة آذار–نيسان بعد التغيير.
                (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), "bimonthly"),
                (datetime.date(2026, 5, 1), datetime.date(2026, 6, 30), "bimonthly"),
                (datetime.date(2026, 7, 1), datetime.date(2026, 8, 31), "bimonthly"),
                (datetime.date(2026, 9, 1), datetime.date(2026, 10, 31), "bimonthly"),
                (datetime.date(2026, 11, 1), datetime.date(2026, 12, 31), "bimonthly"),
            ],
        )

    @staticmethod
    def _changing_at(before, after, change_on):
        def frequency(month):
            return after if month >= change_on else before

        return frequency

    def test_a_shortening_bimonthly_to_monthly_cuts_the_bucket_before_the_change(self):
        """كل شهرين حتى آذار ثم شهرية من نيسان: آذار وحده، ولا يُبتلع نيسان."""
        periods = service_periods(
            self._changing_at("bimonthly", "monthly", datetime.date(2026, 4, 1)),
            datetime.date(2026, 1, 1),
            datetime.date(2026, 6, 30),
        )

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 1, 1), datetime.date(2026, 2, 28), "bimonthly"),
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31), "bimonthly"),
                (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), "monthly"),
                (datetime.date(2026, 5, 1), datetime.date(2026, 5, 31), "monthly"),
                (datetime.date(2026, 6, 1), datetime.date(2026, 6, 30), "monthly"),
            ],
        )

    def test_a_shortening_annual_to_monthly_gives_january_alone_then_every_month(self):
        """سنوية حتى كانون الثاني ثم شهرية من شباط: كانت فترةً واحدةً بلا شهرية."""
        periods = service_periods(
            self._changing_at("annual", "monthly", datetime.date(2026, 2, 1)),
            datetime.date(2026, 1, 1),
            datetime.date(2026, 12, 31),
        )

        self.assertEqual(
            periods[0], (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), "annual"),
        )
        self.assertEqual(len(periods), 12, periods)
        self.assertEqual(
            [(start.month, end.month, frequency) for start, end, frequency in periods[1:]],
            [(month, month, "monthly") for month in range(2, 13)],
        )
        self.assertEqual(periods[-1][1], datetime.date(2026, 12, 31))

    def test_a_lengthening_monthly_to_annual_runs_from_the_change_to_the_year_end(self):
        periods = service_periods(
            self._changing_at("monthly", "annual", datetime.date(2026, 4, 1)),
            datetime.date(2026, 1, 1),
            datetime.date(2026, 12, 31),
        )

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), "monthly"),
                (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28), "monthly"),
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31), "monthly"),
                (datetime.date(2026, 4, 1), datetime.date(2026, 12, 31), "annual"),
            ],
        )

    def test_the_same_month_gives_the_same_bucket_whatever_the_requested_range(self):
        """الربعُ لا يتغيّر بحسب ما تعرضه الشاشة — لا مؤشّرَ من `start` في الحساب."""
        quarterly = self._always("quarterly")

        from_april = service_periods(
            quarterly, datetime.date(2024, 4, 1), datetime.date(2026, 5, 31),
        )
        from_march = service_periods(
            quarterly, datetime.date(2024, 3, 1), datetime.date(2026, 5, 31),
        )

        shared = [period for period in from_april if period[0].year == 2026]
        self.assertEqual(
            shared, [period for period in from_march if period[0].year == 2026],
        )
        self.assertEqual(
            shared,
            [
                (datetime.date(2026, 1, 1), datetime.date(2026, 3, 31), "quarterly"),
                (datetime.date(2026, 4, 1), datetime.date(2026, 6, 30), "quarterly"),
            ],
        )

    def test_a_month_without_a_frequency_is_skipped_and_the_next_is_tried(self):
        """`None` (قبل أول صفّ دورية) يُتخطّى شهراً شهراً حتى تُعرَف الدورية."""
        starts = datetime.date(2026, 3, 1)

        def frequency(month):
            return None if month < starts else "monthly"

        periods = service_periods(
            frequency, datetime.date(2026, 1, 1), datetime.date(2026, 4, 30),
        )

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31), "monthly"),
                (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30), "monthly"),
            ],
        )

    def test_on_demand_and_an_unknown_frequency_give_nothing(self):
        anchor = datetime.date(2026, 1, 1)
        self.assertEqual(service_periods(self._always("on_demand"), anchor, anchor), [])
        self.assertEqual(service_periods(self._always(None), anchor, anchor), [])


class PeriodLabelTest(SimpleTestCase):
    """تسميةُ الفترة تُبنى في الخادم — والشاشة لا تخترع اسماً ثانياً."""

    def test_a_month_quarter_and_year(self):
        self.assertEqual(
            period_label(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)),
            "كانون الثاني 2026",
        )
        self.assertEqual(
            period_label(datetime.date(2026, 1, 1), datetime.date(2026, 2, 28)),
            "كانون الثاني–شباط 2026",
        )
        self.assertEqual(
            period_label(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)),
            "2026",
        )

    def test_a_period_crossing_the_year_names_both(self):
        self.assertEqual(
            period_label(datetime.date(2027, 12, 1), datetime.date(2028, 1, 31)),
            "كانون الأول 2027–كانون الثاني 2028",
        )


class DeadlineResultShapeTest(PureDeadlineTestCase):
    def test_the_result_carries_the_documented_fields(self):
        result = self.compute(self.rule(), datetime.date(2026, 1, 31))

        self.assertIsInstance(result, DeadlineResult)
        for name in (
            "legal_date", "official_date", "actual_deadline", "internal_deadline",
            "estimated", "postponed", "warnings", "rule_code",
            "period_start", "period_end",
        ):
            self.assertTrue(hasattr(result, name), name)


# ── الحارس: لا تاريخ قانوني في محرّك المواعيد ───────────────────────────────
DEADLINES_MODULE = pathlib.Path(__file__).resolve().parent.parent / "deadlines.py"

#: أعدادُ التقويم وحدها: الصفرُ الافتراضي، والواحدُ في حساب الشهر، والسنةُ
#: الميلادية (اثنا عشر شهراً). أيُّ عددٍ آخر في المحرّك تاريخٌ قانونيٌّ مكتوبٌ بيدٍ.
CALENDAR_NUMBERS = frozenset({0, 1, 12})


def numeric_constants(source: str) -> list[int | float]:
    """كلُّ ثابتٍ عدديٍّ في نصّ بايثون — نواةُ الحارس، تُختبَر وحدها.

    ويُقرأ **السالبُ** كثابتٍ أيضاً: `-15` عقدةُ `UnaryOp(USub, Constant(15))`،
    ومسحُ `Constant` وحدها كان يمرّر «15- يوماً» من الباب الخلفيّ.
    """
    tree = ast.parse(source)
    # `-15` عقدتان: `UnaryOp(USub)` وتحتها `Constant(15)`. يُقرأ السالبُ مرّةً،
    # ويُستثنى الثابتُ الداخلي حتى لا يُحسب `15` و`-15` معاً.
    negated = {
        id(node.operand)
        for node in ast.walk(tree)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
    }
    numbers: list[int | float] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))
            and not isinstance(node.operand.value, bool)
        ):
            numbers.append(-node.operand.value)
        elif (
            id(node) not in negated
            and isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            numbers.append(node.value)
    return numbers


class NoLegalDateInCodeTest(SimpleTestCase):
    def test_the_engine_carries_no_numeric_constant_outside_the_calendar_ones(self):
        source = DEADLINES_MODULE.read_text(encoding="utf-8")
        offenders = sorted(set(numeric_constants(source)) - CALENDAR_NUMBERS)

        self.assertEqual(
            offenders, [],
            "تاريخٌ قانونيٌّ مكتوبٌ في محرّك المواعيد — لتكن قاعدتُه من اللائحة: "
            f"{offenders}",
        )

    def test_the_guard_falls_when_a_legal_date_is_written_in_the_engine(self):
        """لو صار المسح أعمى يمرّ المحرّك بتاريخٍ محفور — هذا يفشل حينها."""
        source = DEADLINES_MODULE.read_text(encoding="utf-8") + "\nLEGAL_DAY = 15\n"

        self.assertEqual(
            set(numeric_constants(source)) - CALENDAR_NUMBERS, {15},
        )

    def test_the_ast_scan_sees_literals_inside_functions_too(self):
        probe = "def f():\n    return 15\n"
        self.assertEqual(numeric_constants(probe), [15])

    def test_the_guard_reads_a_negative_literal_as_a_literal(self):
        """`-15` عقدةُ `UnaryOp` — مسحُ `Constant` وحدها كان يمرّرها."""
        probe = "def f():\n    return -15\n"
        self.assertEqual(numeric_constants(probe), [-15])
        self.assertEqual(
            set(numeric_constants(probe)) - CALENDAR_NUMBERS, {-15},
        )
        source = DEADLINES_MODULE.read_text(encoding="utf-8") + "\nLEAD = -15\n"
        self.assertEqual(
            set(numeric_constants(source)) - CALENDAR_NUMBERS, {-15},
        )


# ── مع القاعدة: اللائحة والزرع والربط ─────────────────────────────────────
class ScheduleTestCase(TestCase):
    """مكتبٌ إسرائيليّ وفلسطينيّ، وخدماتُ زبونهما — واللائحةُ منزرعةٌ بهجرتها."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="dl_owner", password="x")
        cls.tenant = create_company(
            "مكتب المواعيد", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def make_client(self, name, *, system="IL", **card):
        client = OfficeClient.objects.create(tenant=self.tenant, name=name)
        fields = {"annual_sales": Decimal("0"), "vat_classification": ""}
        fields.update(card)
        TaxCard.objects.create(client=client, **fields)
        set_client_setting(client, "tax_system", system)
        return client

    def add_service(self, client, code, *, frequency, starts_on, ends_on=None):
        row = services.add_client_service(
            client=client,
            service=self.catalog[code],
            starts_on=starts_on,
            responsible_from=starts_on,
            frequency=frequency,
        )
        if ends_on is not None:
            row.ends_on = ends_on
            row.save(update_fields=["ends_on"])
        return row

    def deadlines(self, client, *, start, end):
        return services.client_deadlines(client, start=start, end=end)

    def rule_codes(self, rows):
        return {row["rule"].code for row in rows}


class SeededScheduleTest(ScheduleTestCase):
    """بياناتُ الهجرة محروسةٌ حرفاً: سطرٌ يتغيّر فيها يسقط هنا."""

    def test_every_schedule_has_its_published_rows(self):
        counts = {}
        for rule in DeadlineRule.objects.select_related("schedule"):
            key = (rule.schedule.tax_system, rule.schedule.year)
            counts[key] = counts.get(key, 0) + 1

        self.assertEqual(
            counts,
            {("PS", 2026): 5, ("PS", 2027): 5, ("IL", 2026): 10, ("IL", 2027): 10},
        )
        self.assertEqual(DeadlineSchedule.objects.count(), 4)

    def test_the_schedule_carries_its_source_and_its_rest_day_policy(self):
        ps = DeadlineSchedule.objects.get(tax_system="PS", year=2026, version=1)
        self.assertEqual(ps.rest_day_policy, REST_DAY_POLICY_WARN)
        self.assertEqual(ps.authority_closed_days, ["fri"])
        self.assertEqual(ps.source_url, PS_LAW_URL)

        il_2026 = DeadlineSchedule.objects.get(tax_system="IL", year=2026, version=1)
        self.assertEqual(il_2026.rest_day_policy, REST_DAY_POLICY_POSTPONE_CLIENT)
        self.assertEqual(il_2026.authority_closed_days, ["sat"])
        self.assertEqual(il_2026.source_url, IL_2026_URL)

        il_2027 = DeadlineSchedule.objects.get(tax_system="IL", year=2027, version=1)
        self.assertEqual(il_2027.source_url, IL_2027_URL)

    def test_the_palestinian_rules_are_the_researched_ones(self):
        vat = DeadlineRule.objects.get(
            schedule__tax_system="PS", schedule__year=2026, code="ps_vat_periodic",
        )
        self.assertEqual(vat.rule_kind, RULE_KIND_DAY_OF_NEXT_MONTH)
        self.assertEqual(vat.rule_day, 15)
        self.assertEqual(vat.cadence, "service")
        self.assertEqual(vat.conditions, {"vat_classification_in": ["licensed", "exempt"]})
        self.assertEqual(vat.service_code, "vat")
        self.assertEqual(vat.electronic_extension_days, 0)

        income = DeadlineRule.objects.get(
            schedule__tax_system="PS", schedule__year=2026, code="ps_income_advances",
        )
        self.assertEqual(income.rule_kind, RULE_KIND_END_OF_PERIOD)
        self.assertEqual(income.cadence, CADENCE_QUARTERLY)

        annual = DeadlineRule.objects.get(
            schedule__tax_system="PS", schedule__year=2026, code="ps_annual_return",
        )
        self.assertEqual(annual.rule_kind, RULE_KIND_MONTH_DAY_NEXT_YEAR)
        self.assertEqual((annual.rule_month, annual.rule_day), (4, 30))

        social = DeadlineRule.objects.get(
            schedule__tax_system="PS", schedule__year=2026, code="ps_social_security",
        )
        self.assertFalse(social.is_generated)

    def test_the_israeli_rules_are_the_researched_ones(self):
        vat = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )
        self.assertEqual(vat.electronic_extension_days, 4)
        self.assertEqual(vat.rule_day, 15)
        self.assertEqual(
            vat.conditions, {"vat_classification_in": ["authorized", "nonprofit"]},
        )

        detailed = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_detailed",
        )
        self.assertEqual(detailed.rule_day, 23)
        self.assertEqual(
            detailed.conditions["annual_sales_above"], "vat_detailed_reporting",
        )

        withholding = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_withholding_102",
        )
        self.assertEqual(withholding.rule_day, 16)

        for code in ("il_annual_1301", "il_annual_1214"):
            self.assertTrue(
                DeadlineRule.objects.get(
                    schedule__tax_system="IL", schedule__year=2026, code=code,
                ).needs_review,
                code,
            )
        self.assertTrue(DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_annual_1301",
        ).source_url.startswith("https://www.gov.il/"))
        self.assertTrue(DeadlineRule.objects.get(
            schedule__tax_system="PS", schedule__year=2026, code="ps_vat_periodic",
        ).source_url, "سطرٌ بلا مصدرٍ يصير رأياً")

    def test_the_published_israeli_dates_are_literal(self):
        vat_2026 = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        ).period_overrides
        self.assertEqual(
            vat_2026["2026-03"], {"date": "2026-04-27", "rest_day_only": False},
        )
        self.assertEqual(
            vat_2026["2026-02"], {"date": "2026-03-26", "rest_day_only": False},
        )
        self.assertEqual(
            vat_2026["2026-01"], {"date": "2026-02-16", "rest_day_only": True},
        )

        vat_2027 = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2027, code="il_vat_periodic",
        ).period_overrides
        self.assertEqual(
            vat_2027["2027-09"], {"date": "2027-10-28", "rest_day_only": False},
        )
        self.assertEqual(
            vat_2027["2027-02"], {"date": "2027-03-18", "rest_day_only": False},
        )

        detailed_2026 = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_detailed",
        ).period_overrides
        # شباط 2026: التأجيل الطارئ يسري على الأعمدة الثلاثة.
        self.assertEqual(
            detailed_2026["2026-02"], {"date": "2026-03-26", "rest_day_only": False},
        )
        # حزيران 2026: (7) وفيه بندٌ غير يوم الراحة ⇒ يُؤخذ كما نُشر.
        self.assertEqual(
            detailed_2026["2026-06"], {"date": "2026-07-27", "rest_day_only": False},
        )
        # نيسان 2026: (4+7) — البندان معاً، فلا يُعاد حسابه من يوم الراحة وحده.
        self.assertEqual(
            detailed_2026["2026-04"], {"date": "2026-05-26", "rest_day_only": False},
        )

        withholding_2026 = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_withholding_102",
        ).period_overrides
        self.assertEqual(
            withholding_2026["2026-02"], {"date": "2026-03-26", "rest_day_only": False},
        )
        self.assertEqual(
            withholding_2026["2026-09"], {"date": "2026-10-19", "rest_day_only": True},
        )

    def test_the_detailed_report_threshold_is_seeded(self):
        row = TaxThreshold.objects.get(
            tax_system="IL", kind="vat_detailed_reporting", year=2026,
        )
        self.assertEqual(row.amount, Decimal("500000"))
        self.assertEqual(row.source_url, IL_DETAILED_URL)


class ScheduleLookupTest(ScheduleTestCase):
    def test_the_effective_version_is_the_highest_one(self):
        row, estimated = services.schedule_for("IL", 2026)
        self.assertEqual((row.year, row.version), (2026, 1))
        self.assertFalse(estimated)

        DeadlineSchedule.objects.create(
            tax_system="IL", year=2026, version=2,
            source_url="https://www.gov.il/he/pages/pa151025-2",
            published_on=datetime.date(2026, 1, 2),
            rest_day_policy=REST_DAY_POLICY_POSTPONE_CLIENT,
            authority_closed_days=["sat"],
        )
        row, estimated = services.schedule_for("IL", 2026)
        self.assertEqual((row.year, row.version), (2026, 2))
        self.assertFalse(estimated)

    def test_a_year_without_a_schedule_takes_the_last_one_and_says_estimated(self):
        row, estimated = services.schedule_for("IL", 2028)
        self.assertEqual((row.year, row.version), (2027, 1))
        self.assertTrue(estimated)

    def test_an_unknown_system_has_no_schedule(self):
        self.assertEqual(services.schedule_for("JO", 2026), (None, False))


class RuleApplicabilityTest(ScheduleTestCase):
    def rule(self, code, *, year=2026, system="IL"):
        return DeadlineRule.objects.get(
            schedule__tax_system=system, schedule__year=year, code=code,
        )

    def card(self, **fields):
        client = self.make_client("بطاقة", **fields)
        return client.tax_card

    def ctx(self, card, day=datetime.date(2026, 12, 31), system="IL"):
        return services.ThresholdContext(tax_system=system, day=day)

    def test_an_exempt_dealer_only_gets_the_annual_declaration(self):
        """עוסק פטור: التصريحُ السنويّ وحده — لا تقرير دوريّ."""
        card = self.card(vat_classification="exempt")
        ctx = self.ctx(card)

        self.assertTrue(services.rule_applies(
            self.rule("il_vat_exempt_declaration"), card, ctx,
        ))
        self.assertFalse(services.rule_applies(
            self.rule("il_vat_periodic"), card, ctx,
        ))
        self.assertFalse(services.rule_applies(
            self.rule("il_vat_detailed"), card, ctx,
        ))

    def test_the_detailed_report_follows_the_published_sales_ceiling(self):
        above = self.card(
            vat_classification="authorized", annual_sales=Decimal("500001"),
        )
        below = self.card(
            vat_classification="authorized", annual_sales=Decimal("500000"),
        )
        rule = self.rule("il_vat_detailed")

        self.assertTrue(services.rule_applies(rule, above, self.ctx(above)))
        self.assertFalse(services.rule_applies(rule, below, self.ctx(below)))

    def test_employees_and_self_employment_conditions(self):
        rule = self.rule("il_withholding_102")
        employed = self.card(has_employees=True)
        alone = self.card(has_employees=False)

        self.assertTrue(services.rule_applies(rule, employed, self.ctx(employed)))
        self.assertFalse(services.rule_applies(rule, alone, self.ctx(alone)))

    def test_the_self_employed_rule_applies_only_to_the_self_employed(self):
        rule = self.rule("il_bl_self_employed")
        self_employed = self.card(is_self_employed=True)
        salaried = self.card(is_self_employed=False)

        self.assertTrue(
            services.rule_applies(rule, self_employed, self.ctx(self_employed)),
        )
        self.assertFalse(
            services.rule_applies(rule, salaried, self.ctx(salaried)),
        )

    def test_the_annual_return_follows_the_entity_type(self):
        """1301 لفردٍ أو تضامنٍ، و1214 لشركةٍ أو غير ربحية — لا العكس."""
        individual = self.rule("il_annual_1301")
        company = self.rule("il_annual_1214")
        sole = self.card(entity_type="individual")
        limited = self.card(entity_type="company")

        self.assertTrue(services.rule_applies(individual, sole, self.ctx(sole)))
        self.assertFalse(services.rule_applies(company, sole, self.ctx(sole)))
        self.assertTrue(services.rule_applies(company, limited, self.ctx(limited)))
        self.assertFalse(services.rule_applies(individual, limited, self.ctx(limited)))

    def test_an_ungenerated_rule_never_applies(self):
        rule = self.rule("ps_social_security", system="PS")
        card = self.card(has_employees=True)

        self.assertFalse(rule.is_generated)
        self.assertFalse(
            services.rule_applies(rule, card, self.ctx(card, system="PS")),
        )

    def test_an_unknown_condition_key_is_refused(self):
        rule = self.rule("ps_vat_periodic", system="PS")
        rule.conditions = {"annual_sales_abovee": "vat_exempt_dealer"}
        with self.assertRaises(DjangoValidationError):
            rule.clean()
        self.assertNotIn("annual_sales_abovee", CONDITION_KEYS)

    def test_the_known_condition_keys_are_the_documented_five(self):
        self.assertEqual(
            CONDITION_KEYS,
            frozenset({
                "vat_classification_in", "entity_type_in", "has_employees",
                "is_self_employed", "annual_sales_above",
            }),
        )


class ClientDeadlinesTest(ScheduleTestCase):
    def test_an_exempt_dealer_generates_the_declaration_and_not_the_periodic(self):
        client = self.make_client(
            "עוסק פטור", vat_classification="exempt", annual_sales=Decimal("90000"),
        )
        self.add_service(
            client, "vat", frequency="annual",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = self.deadlines(
            client, start=datetime.date(2026, 1, 1), end=datetime.date(2027, 12, 31),
        )
        codes = self.rule_codes(rows)

        self.assertIn("il_vat_exempt_declaration", codes)
        self.assertNotIn("il_vat_periodic", codes)
        declaration = next(
            row for row in rows if row["rule"].code == "il_vat_exempt_declaration"
        )
        self.assertEqual(declaration["result"].legal_date, datetime.date(2027, 1, 31))

    def test_the_detailed_report_appears_only_above_the_ceiling(self):
        def codes(annual_sales):
            client = self.make_client(
                f"مبيعات {annual_sales}", vat_classification="authorized",
                annual_sales=annual_sales,
            )
            self.add_service(
                client, "vat", frequency="monthly",
                starts_on=datetime.date(2026, 1, 1),
            )
            return self.rule_codes(self.deadlines(
                client, start=datetime.date(2026, 1, 1),
                end=datetime.date(2026, 12, 31),
            ))

        self.assertIn("il_vat_detailed", codes(Decimal("600000")))
        self.assertNotIn("il_vat_detailed", codes(Decimal("400000")))

    def test_a_year_without_a_schedule_is_estimated_and_ignores_the_overrides(self):
        """«تقديري»: تعديلٌ منشورٌ لـ2027 **لا** يُقرأ لفترة 2028 — ولو طابق شهرَها.

        التعديلُ يُزرع هنا بمفتاح `2028-01` عمداً: بمفاتيح 2027 وحدها كان
        الاختبارُ يمرّ لأن لا مفتاحَ يطابق، فلا يسقط لو قُرئت التعديلاتُ في التقديريّ.
        """
        rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2027, code="il_vat_periodic",
        )
        rule.period_overrides = {
            **rule.period_overrides,
            "2028-01": {"date": "2028-02-28", "rest_day_only": False},
        }
        rule.save(update_fields=["period_overrides"])

        client = self.make_client(
            "سنة بلا لائحة", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2028, 1, 1),
        )
        rows = self.deadlines(
            client, start=datetime.date(2028, 1, 1), end=datetime.date(2028, 12, 31),
        )
        vat = [row for row in rows if row["rule"].code == "il_vat_periodic"]
        january = next(
            row for row in vat
            if row["result"].period_start == datetime.date(2028, 1, 1)
        )

        self.assertTrue(january["result"].estimated)
        self.assertEqual(january["result"].legal_date, datetime.date(2028, 2, 15))
        self.assertNotEqual(
            january["result"].official_date, datetime.date(2028, 2, 28),
            "قُرئ تعديلُ 2027 على فترة 2028 — والتقديريّ يتجاهل التعديلات كلَّها",
        )

    def test_the_palestinian_social_security_is_never_generated(self):
        client = self.make_client("مكتب فلسطين", system="PS", has_employees=True)
        self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        codes = self.rule_codes(self.deadlines(
            client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31),
        ))

        self.assertIn("ps_payroll_withholding", codes)
        self.assertNotIn("ps_social_security", codes)

    def test_a_stopped_service_has_no_period_ending_after_its_end(self):
        client = self.make_client("زبون توقّف", has_employees=True)
        self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
            ends_on=datetime.date(2026, 3, 31),
        )
        rows = self.deadlines(
            client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31),
        )
        periods = [
            row["result"].period_end for row in rows
            if row["rule"].code == "il_withholding_102"
        ]

        self.assertEqual(
            periods,
            [datetime.date(2026, 1, 31), datetime.date(2026, 2, 28),
             datetime.date(2026, 3, 31)],
        )

    def test_no_period_ends_before_the_office_is_responsible_or_before_the_start(self):
        client = self.make_client("زبون بدأ متأخراً", has_employees=True)
        row = self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 4, 1),
        )
        row.responsible_from = datetime.date(2026, 6, 1)
        row.save(update_fields=["responsible_from"])

        periods = [
            item["result"].period_end
            for item in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31),
            )
            if item["rule"].code == "il_withholding_102"
        ]
        self.assertTrue(all(day >= datetime.date(2026, 6, 1) for day in periods), periods)
        self.assertIn(datetime.date(2026, 6, 30), periods)

    def test_a_frequency_change_in_april_moves_the_periods(self):
        """الدوريةُ مؤرَّخة: آذار يبقى شهرياً، ونيسان يصير حزمةً محاذاةً بلا فجوة."""
        client = self.make_client(
            "دورية متغيّرة", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        service = self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        services.change_client_service_frequency(
            service, frequency="bimonthly", effective_from=datetime.date(2026, 4, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2027, 3, 31),
            )
            if row["rule"].code == "il_vat_periodic"
        ]
        periods = [
            (row["result"].period_start, row["result"].period_end) for row in rows
        ]

        self.assertEqual(
            periods,
            [
                (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)),
                (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28)),
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)),
                # نيسان وحدَه: بقيّةُ حزمة آذار–نيسان بعد التغيير — ولا فجوة.
                (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30)),
                (datetime.date(2026, 5, 1), datetime.date(2026, 6, 30)),
                (datetime.date(2026, 7, 1), datetime.date(2026, 8, 31)),
                (datetime.date(2026, 9, 1), datetime.date(2026, 10, 31)),
                (datetime.date(2026, 11, 1), datetime.date(2026, 12, 31)),
                (datetime.date(2027, 1, 1), datetime.date(2027, 2, 28)),
            ],
        )

    def vat_periods(self, client, *, start, end):
        return [
            (row["result"].period_start, row["result"].period_end)
            for row in self.deadlines(client, start=start, end=end)
            if row["rule"].code == "il_vat_periodic"
        ]

    def test_an_annual_service_made_monthly_in_february_gets_january_alone_then_each_month(self):
        """التقصير: سنويةٌ حتى كانون الثاني ثم شهرية — كانت فترةً واحدةً بلا شهرية."""
        client = self.make_client(
            "سنوية ثم شهرية", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        service = self.add_service(
            client, "vat", frequency="annual",
            starts_on=datetime.date(2026, 1, 1),
        )
        services.change_client_service_frequency(
            service, frequency="monthly", effective_from=datetime.date(2026, 2, 1),
        )

        self.assertEqual(
            self.vat_periods(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2027, 1, 31),
            ),
            [(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))]
            + [
                (datetime.date(2026, month, 1), last_of_month(datetime.date(2026, month, 1)))
                for month in range(2, 13)
            ],
        )

    def test_a_truncated_period_takes_the_lead_days_of_the_cadence_it_was_read_in(self):
        """شهرية ثم سنوية من نيسان: نيسان–كانون الأول (9 أشهر) سنويةٌ بـ30 يوماً لا شهرية بـ5."""
        client = self.make_client(
            "شهرية ثم سنوية", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        service = self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        services.change_client_service_frequency(
            service, frequency="annual", effective_from=datetime.date(2026, 4, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2027, 1, 31),
            )
            if row["rule"].code == "il_vat_periodic"
            and row["result"].period_start == datetime.date(2026, 4, 1)
        ]

        self.assertEqual(len(rows), 1)
        result = rows[0]["result"]
        self.assertEqual(result.period_end, datetime.date(2026, 12, 31))
        annual_lead = services.resolve_setting(
            self.tenant, "internal_lead_days_annual", client=client,
        )
        self.assertEqual(annual_lead, 30)
        self.assertEqual(
            result.internal_deadline, step_back(result.actual_deadline, annual_lead),
        )

    def test_a_context_built_for_one_client_still_resolves_another_clients_settings(self):
        """سياقٌ لمجموعةٍ لا يُسقط زبوناً خارجها: كان يُعيد `None` ⇒ تقويماً فارغاً."""
        first = self.make_client("زبون المجموعة", vat_classification="authorized")
        outsider = self.make_client("زبون خارج المجموعة", vat_classification="authorized")
        set_client_setting(outsider, "internal_lead_days_monthly", 9)
        for client in (first, outsider):
            self.add_service(
                client, "vat", frequency="monthly",
                starts_on=datetime.date(2026, 1, 1),
            )
        window = {"start": datetime.date(2026, 1, 1), "end": datetime.date(2026, 2, 28)}

        alone = services.client_deadlines(outsider, **window)
        via_context = services.client_deadlines(
            outsider, **window, context=services.calendar_context(self.tenant, [first]),
        )

        self.assertTrue(alone)
        self.assertEqual(
            [(row["rule"].code, row["result"]) for row in via_context],
            [(row["rule"].code, row["result"]) for row in alone],
        )
        self.assertTrue(all(
            row["result"].internal_deadline
            == step_back(row["result"].actual_deadline, 9)
            for row in via_context
        ))

    def test_an_estimated_ceiling_is_announced_on_the_row_that_reads_it(self):
        """سقفُ 2027 غير منشور ⇒ يُقرأ سقفُ 2026 ويُعلَن على سطر التقرير المفصّل."""
        client = self.make_client(
            "مبيعات فوق السقف", vat_classification="authorized",
            annual_sales=Decimal("600000"),
        )
        self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2027, 12, 31),
            )
            if row["rule"].code == "il_vat_detailed"
        ]
        estimated_warning = "تقديري: سقف 2026"
        in_2027 = [row for row in rows if row["result"].period_end.year == 2027]
        in_2026 = [row for row in rows if row["result"].period_end.year == 2026]

        self.assertTrue(in_2027)
        self.assertTrue(in_2026)
        for row in in_2027:
            self.assertIn(estimated_warning, row["result"].warnings)
        for row in in_2026:
            self.assertNotIn(estimated_warning, row["result"].warnings)

    def test_an_on_demand_service_generates_no_service_cadence_line(self):
        """`on_demand` بلا فترات خدمة: سطرُ ‎vat‎ الدوريّ لا يُولَّد، والشهريُّ الثابت يُولَّد."""
        client = self.make_client(
            "عند الطلب", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        for code in ("vat", "bookkeeping"):
            self.add_service(
                client, code, frequency="on_demand",
                starts_on=datetime.date(2026, 1, 1),
            )
        codes = self.rule_codes(self.deadlines(
            client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31),
        ))
        service_cadence_codes = set(
            DeadlineRule.objects.filter(cadence="service", service_code="vat")
            .values_list("code", flat=True),
        )

        self.assertIn("il_vat_periodic", service_cadence_codes)
        self.assertEqual(codes & service_cadence_codes, set())
        self.assertIn("il_income_advances", codes)

    def test_a_service_started_mid_month_still_has_its_month(self):
        """`frequency_on` تُقرأ عند **آخر** الشهر: بدايةٌ في 15/2 لا تُسقط شباط."""
        client = self.make_client(
            "بدأت في منتصف شباط", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 2, 15),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 2, 1), end=datetime.date(2026, 4, 30),
            )
            if row["rule"].code == "il_vat_periodic"
        ]

        self.assertIn(
            (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28)),
            [(row["result"].period_start, row["result"].period_end) for row in rows],
        )

    def test_the_same_quarter_is_the_same_whatever_the_displayed_range(self):
        """خدمةٌ رُبعية بدأت 2023: الربعُ لا يتغيّر بمدى العرض ولا ببدايته.

        المدى الثالث (من آذار) هو ما يُسقط محاذاةً تبدأ من مؤشّر الطلب: مؤشّرُه
        آذار 2024 فيُنتج آذار–أيار 2026، والمديان الآخران مؤشّرُهما نيسان 2024
        فيُنتجان كانون الثاني–آذار — فتُظهر الشاشةُ ربعاً مختلفاً للشهر نفسه.
        """
        client = self.make_client(
            "خدمة قديمة رُبعية", system="PS", vat_classification="licensed",
        )
        self.add_service(
            client, "vat", frequency="quarterly",
            starts_on=datetime.date(2023, 1, 15),
        )

        def quarter_rows(start, end):
            return [
                (
                    row["result"].period_start.isoformat(),
                    row["result"].period_end.isoformat(),
                    row["result"].actual_deadline.isoformat(),
                )
                for row in self.deadlines(client, start=start, end=end)
                if row["rule"].code == "ps_vat_periodic"
            ]

        windows = (
            (datetime.date(2026, 4, 1), datetime.date(2026, 5, 31)),
            (datetime.date(2026, 4, 15), datetime.date(2026, 6, 14)),
            (datetime.date(2026, 3, 1), datetime.date(2026, 5, 31)),
        )
        results = [quarter_rows(start, end) for start, end in windows]

        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        self.assertEqual(results[0], [("2026-01-01", "2026-03-31", "2026-04-15")])

    def test_the_rows_are_inside_the_requested_range_only(self):
        client = self.make_client("زبون المدى", vat_classification="authorized")
        self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = self.deadlines(
            client, start=datetime.date(2026, 3, 1), end=datetime.date(2026, 4, 30),
        )

        self.assertTrue(rows)
        for row in rows:
            self.assertGreaterEqual(row["result"].actual_deadline, datetime.date(2026, 3, 1))
            self.assertLessEqual(row["result"].actual_deadline, datetime.date(2026, 4, 30))

    def test_the_electronic_extension_is_used_for_the_israeli_client(self):
        client = self.make_client(
            "زبون إلكتروني", vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        set_client_setting(client, "filing_method", "electronic")
        self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 2, 28),
            )
            if row["rule"].code == "il_vat_periodic"
        ]

        self.assertEqual(len(rows), 1)
        result = rows[0]["result"]
        # الوسمُ (4) في شباط 2026 وحده سببُ التأجيل ⇒ يُعاد حسابه لزبونٍ راحتُه
        # الجمعة، ثم يمنح التقديمُ الإلكترونيّ أربعة أيام.
        self.assertEqual(result.official_date, result.legal_date)
        self.assertEqual(
            result.actual_deadline,
            result.official_date + datetime.timedelta(days=4),
        )

    def test_the_internal_lead_days_come_from_the_cadence(self):
        client = self.make_client("زبون داخلي", has_employees=True)
        self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 2, 28),
            )
            if row["rule"].code == "il_withholding_102"
        ]

        self.assertEqual(
            rows[0]["result"].internal_deadline,
            step_back(rows[0]["result"].actual_deadline, 5),
        )

    def test_the_quarterly_rule_takes_the_quarterly_lead_days(self):
        client = self.make_client(
            "زبون ربعي", system="PS", vat_classification="licensed",
        )
        self.add_service(
            client, "bookkeeping", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31),
            )
            if row["rule"].code == "ps_income_advances"
        ]
        first = min(rows, key=lambda row: row["result"].period_end)

        self.assertEqual(first["result"].period_end, datetime.date(2026, 3, 31))
        self.assertEqual(
            first["result"].internal_deadline,
            step_back(first["result"].actual_deadline, 7),
        )

    def test_the_annual_rule_takes_the_annual_lead_days(self):
        client = self.make_client("زبون سنوي", has_employees=True)
        self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = [
            row for row in self.deadlines(
                client, start=datetime.date(2027, 1, 1), end=datetime.date(2027, 12, 31),
            )
            if row["rule"].code == "il_annual_126_856"
        ]

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["result"].internal_deadline,
            step_back(rows[0]["result"].actual_deadline, 30),
        )

    def test_a_client_customising_the_lead_days_changes_the_internal_deadline(self):
        client = self.make_client("زبون خصّص الأيام", has_employees=True)
        self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        before = [
            row for row in self.deadlines(
                client, start=datetime.date(2027, 1, 1), end=datetime.date(2027, 12, 31),
            )
            if row["rule"].code == "il_annual_126_856"
        ][0]["result"]

        set_client_setting(client, "internal_lead_days_annual", 10)
        after = [
            row for row in self.deadlines(
                client, start=datetime.date(2027, 1, 1), end=datetime.date(2027, 12, 31),
            )
            if row["rule"].code == "il_annual_126_856"
        ][0]["result"]

        self.assertEqual(after.actual_deadline, before.actual_deadline)
        self.assertEqual(after.internal_deadline, step_back(after.actual_deadline, 10))
        self.assertNotEqual(after.internal_deadline, before.internal_deadline)


class FixedCadencePeriodsTest(ScheduleTestCase):
    """أسطرُ الدورية الثابتة: فتراتُها من **قاعدتها** لا من دورية الخدمة.

    كان الزبون ذو الرواتب الشهرية يولّد التقريرَ السنوي **اثنتَي عشرة مرّةً**،
    والرُّبعيُّ شهرياً، وتصريحَ المعفى شهرياً — كلُّها في تاريخٍ واحد.
    """

    def rows_of(self, client, code, *, start, end):
        return [
            row for row in self.deadlines(client, start=start, end=end)
            if row["rule"].code == code
        ]

    def test_the_annual_withholding_report_is_generated_once_per_year(self):
        client = self.make_client("رواتب شهرية", has_employees=True)
        self.add_service(
            client, "payroll", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = self.rows_of(
            client, "il_annual_126_856",
            start=datetime.date(2027, 1, 1), end=datetime.date(2027, 12, 31),
        )

        self.assertEqual(len(rows), 1, [row["result"].period_end for row in rows])
        result = rows[0]["result"]
        self.assertEqual(
            (result.period_start, result.period_end),
            (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)),
        )
        self.assertEqual(result.legal_date, datetime.date(2027, 4, 30))

    def test_the_quarterly_income_advances_stay_quarterly_with_a_monthly_service(self):
        client = self.make_client(
            "دفاتر شهرية", system="PS", vat_classification="licensed",
        )
        self.add_service(
            client, "bookkeeping", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = self.rows_of(
            client, "ps_income_advances",
            start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31),
        )

        self.assertEqual(
            [row["result"].period_end for row in rows],
            [
                datetime.date(2026, 3, 31), datetime.date(2026, 6, 30),
                datetime.date(2026, 9, 30), datetime.date(2026, 12, 31),
            ],
        )

    def test_the_exempt_declaration_is_generated_once_for_the_year(self):
        client = self.make_client(
            "معفى شهري", vat_classification="exempt", annual_sales=Decimal("90000"),
        )
        self.add_service(
            client, "vat", frequency="monthly",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = self.rows_of(
            client, "il_vat_exempt_declaration",
            start=datetime.date(2026, 1, 1), end=datetime.date(2027, 12, 31),
        )

        self.assertEqual(len(rows), 1, [row["result"].period_end for row in rows])
        self.assertEqual(rows[0]["result"].legal_date, datetime.date(2027, 1, 31))

    def test_a_fixed_cadence_is_generated_even_for_an_on_demand_service(self):
        """`on_demand` لا تولّد فتراتِ خدمة — ولا تُسقط سطراً قاعدتُه سنوية."""
        client = self.make_client("خدمة عند الطلب", has_employees=True)
        self.add_service(
            client, "payroll", frequency="on_demand",
            starts_on=datetime.date(2026, 1, 1),
        )
        rows = self.rows_of(
            client, "il_annual_126_856",
            start=datetime.date(2027, 1, 1), end=datetime.date(2027, 12, 31),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["result"].period_end, datetime.date(2026, 12, 31),
        )


class DeadlineRulesPayloadCostTest(ScheduleTestCase):
    """قائمةُ اللائحة استعلامان لا استعلامان لكل سنة."""

    def test_the_rules_listing_is_two_queries_whatever_the_years(self):
        with CaptureQueriesContext(connection) as captured:
            payload = services.deadline_rules_payload("IL")

        selects = [
            query["sql"] for query in captured.captured_queries
            if query["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(len(payload["rules"]), 20)
        self.assertEqual(len(selects), 2, selects)


# ── الإعدادات الجديدة ─────────────────────────────────────────────────────
class ScheduleSettingsTest(ScheduleTestCase):
    def test_the_defaults_are_the_agreed_ones(self):
        self.assertEqual(services.resolve_setting(self.tenant, "internal_lead_days_monthly"), 5)
        self.assertEqual(services.resolve_setting(self.tenant, "internal_lead_days_quarterly"), 7)
        self.assertEqual(services.resolve_setting(self.tenant, "internal_lead_days_annual"), 30)
        self.assertEqual(services.resolve_setting(self.tenant, "calendar_months_ahead"), 12)

    def test_a_client_customises_the_lead_days(self):
        client = self.make_client("زبون أيام")
        set_client_setting(client, "internal_lead_days_quarterly", 9)

        self.assertEqual(
            services.resolve_setting(
                self.tenant, "internal_lead_days_quarterly", client=client,
            ),
            9,
        )
        self.assertEqual(
            services.resolve_setting(self.tenant, "internal_lead_days_quarterly"), 7,
        )

    def test_a_negative_number_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            set_office_setting(self.tenant, "internal_lead_days_monthly", -1)
        with self.assertRaises(DjangoValidationError):
            set_office_setting(self.tenant, "calendar_months_ahead", -3)

    def test_the_calendar_range_is_an_office_setting_only(self):
        client = self.make_client("زبون المدى")
        with self.assertRaises(DjangoValidationError):
            set_client_setting(client, "calendar_months_ahead", 6)


# ── الـAPI: تقويمٌ لا يحفظ، ولائحةٌ للقراءة ────────────────────────────────
class DeadlineApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="dl_api_owner", password="x")
        cls.tenant = create_company(
            "مكتب تقويم الـAPI", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("dl_api_accountant", "accountant")
        cls.colleague = member("dl_api_colleague", "accountant")

        def make(name, responsible, **fields):
            client = OfficeClient.objects.create(
                tenant=cls.tenant, name=name, responsible=responsible,
            )
            TaxCard.objects.create(client=client, **fields)
            return client

        cls.mine = make(
            "زبون المحاسب", cls.accountant,
            vat_classification="authorized", annual_sales=Decimal("400000"),
        )
        cls.other = make(
            "زبون الزميل", cls.colleague,
            vat_classification="authorized", annual_sales=Decimal("400000"),
        )
        cls.palestinian = make(
            "زبون فلسطين", cls.accountant,
            vat_classification="licensed", annual_sales=Decimal("400000"),
        )
        set_client_setting(cls.palestinian, "tax_system", "PS")
        for client in (cls.mine, cls.other):
            services.add_client_service(
                client=client, service=cls.catalog["vat"],
                starts_on=datetime.date(2026, 1, 1),
                responsible_from=datetime.date(2026, 1, 1),
                frequency="monthly",
            )
        services.add_client_service(
            client=cls.palestinian, service=cls.catalog["vat"],
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
            frequency="monthly",
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def calendar(self, **query):
        params = {"from": "2026-01-01", "to": "2026-02-28", **query}
        return self.client.get(CALENDAR, params, **self.headers())

    def model_row_counts(self):
        return {
            model.__name__: model.objects.count()
            for model in django_apps.get_app_config("accounting_office").get_models()
        }


class CalendarApiTest(DeadlineApiTestCase):
    def test_the_calendar_reads_without_writing_a_single_row(self):
        self.as_user(self.accountant)
        before = self.model_row_counts()

        res = self.calendar(client=self.palestinian.pk)

        after = self.model_row_counts()
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(before, after, "التقويم كتب صفّاً — وهو محسوبٌ لا محفوظ")

    def test_the_row_carries_the_agreed_fields_and_nothing_monetary(self):
        self.as_user(self.accountant)
        res = self.calendar(client=self.mine.pk)
        row = res.data["rows"][0]

        self.assertEqual(
            set(row),
            {
                "client", "service", "rule", "period_start", "period_end",
                "period_label", "legal_date", "official_date", "actual_deadline",
                "internal_deadline", "estimated", "postponed", "warnings", "expected",
                "origin", "origin_label", "platform_official_date",
            },
        )
        self.assertTrue(row["expected"])
        self.assertEqual(set(row["client"]), {"id", "name"})
        self.assertEqual(set(row["service"]), {"code", "name"})
        self.assertEqual(set(row["rule"]), {"code", "name", "needs_review"})
        self.assertTrue(row["period_label"])

    def test_editing_a_rule_changes_the_calendar_at_once(self):
        self.as_user(self.accountant)
        before = self.calendar(client=self.palestinian.pk)
        self.assertEqual(before.status_code, 200)

        rule = DeadlineRule.objects.get(
            schedule__tax_system="PS", schedule__year=2026, code="ps_vat_periodic",
        )
        rule.rule_day = 20
        rule.save(update_fields=["rule_day"])

        after = self.calendar(client=self.palestinian.pk)
        self.assertNotEqual(
            [row["legal_date"] for row in before.data["rows"]],
            [row["legal_date"] for row in after.data["rows"]],
            "تغييرُ سطرٍ في اللائحة لم يظهر في الطلب التالي",
        )
        self.assertIn("2026-02-20", [row["legal_date"] for row in after.data["rows"]])

    def test_someone_elses_client_is_not_in_the_calendar(self):
        self.as_user(self.accountant)
        res = self.calendar(client=self.other.pk)

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["rows"], [])

    def test_the_member_and_client_and_rule_filters_work(self):
        self.as_user(self.owner)
        by_member = self.calendar(member=self.colleague.pk)
        self.assertTrue(by_member.data["rows"])
        self.assertEqual(
            {row["client"]["id"] for row in by_member.data["rows"]}, {self.other.pk},
        )

        by_client = self.calendar(client=self.mine.pk)
        self.assertEqual(
            {row["client"]["id"] for row in by_client.data["rows"]}, {self.mine.pk},
        )

        by_rule = self.calendar(rule="ps_vat_periodic")
        self.assertTrue(by_rule.data["rows"])
        self.assertEqual(
            {row["rule"]["code"] for row in by_rule.data["rows"]}, {"ps_vat_periodic"},
        )

    def test_each_client_row_carries_that_clients_own_lead_days_through_the_bulk_context(self):
        """زبونان في طلبٍ واحد: أيامُ إعداد أحدهما المخصَّصة لا تتسرّب للآخر ولا تضيع."""
        set_client_setting(self.mine, "internal_lead_days_monthly", 9)
        self.as_user(self.owner)

        res = self.calendar()

        self.assertEqual(res.status_code, 200, res.content)
        lead_by_client = {self.mine.pk: 9, self.other.pk: 5}
        checked = set()
        for row in res.data["rows"]:
            lead = lead_by_client.get(row["client"]["id"])
            if lead is None or row["rule"]["code"] != "il_vat_periodic":
                continue
            checked.add(row["client"]["id"])
            self.assertEqual(
                datetime.date.fromisoformat(row["internal_deadline"]),
                step_back(datetime.date.fromisoformat(row["actual_deadline"]), lead),
                row["client"],
            )
        self.assertEqual(checked, set(lead_by_client))

    def test_a_client_without_a_tax_card_keeps_the_unconditional_lines_only(self):
        """بطاقةٌ شُطبت يدوياً: لا 500، وما لا شرطَ له يبقى وما شرطُه التصنيف يسقط."""
        services.add_client_service(
            client=self.palestinian, service=self.catalog["bookkeeping"],
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
            frequency="monthly",
        )
        TaxCard.objects.filter(client=self.palestinian).delete()
        self.as_user(self.accountant)

        res = self.calendar(
            client=self.palestinian.pk, **{"from": "2026-03-01", "to": "2026-03-31"},
        )

        self.assertEqual(res.status_code, 200, res.content)
        codes = {row["rule"]["code"] for row in res.data["rows"]}
        self.assertIn("ps_income_advances", codes)
        self.assertNotIn("ps_vat_periodic", codes)

    def _client_ids_of_the_services_query(self, **query):
        with CaptureQueriesContext(connection) as captured:
            res = self.calendar(**query)
        self.assertEqual(res.status_code, 200, res.content)
        for entry in captured.captured_queries:
            sql = entry["sql"]
            if 'FROM "accounting_office_clientservice"' not in sql:
                continue
            match = re.search(r'"client_id" IN \(([^)]*)\)', sql)
            if match:
                return {int(value) for value in match.group(1).split(",")}
        self.fail("لم يُجلب استعلامُ خدمات الزبائن بقائمة زبائن")

    def test_filtering_by_client_fetches_only_that_clients_services(self):
        """الفلترةُ في الاستعلام لا في بايثون: خدماتُ باقي الزبائن لا تُجلب أصلاً."""
        self.as_user(self.owner)

        self.assertEqual(
            self._client_ids_of_the_services_query(client=self.mine.pk), {self.mine.pk},
        )
        self.assertEqual(
            self._client_ids_of_the_services_query(member=self.colleague.pk),
            {self.other.pk},
        )

    def test_a_long_range_is_refused(self):
        self.as_user(self.accountant)
        res = self.calendar(**{"from": "2026-01-01", "to": "2026-06-30"})
        self.assertEqual(res.status_code, 400, res.content)

        res = self.calendar(**{"from": "2026-03-01", "to": "2026-01-01"})
        self.assertEqual(res.status_code, 400, res.content)

    def test_a_range_beyond_the_calendar_horizon_is_refused(self):
        """الـ400 من **الأفق** لا من حدّ 62 يوماً: المدى عشرةُ أيامٍ لكنه بعده."""
        self.as_user(self.accountant)
        today = timezone.localdate()
        start = (today + datetime.timedelta(days=380)).isoformat()
        end = (today + datetime.timedelta(days=390)).isoformat()

        res = self.calendar(**{"from": start, "to": end})

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("أفق", res.content.decode())

    def test_the_boundary_range_is_accepted(self):
        self.as_user(self.accountant)
        res = self.calendar(**{"from": "2026-01-01", "to": "2026-03-04"})
        self.assertEqual(res.status_code, 200, res.content)

    def test_the_calendar_horizon_comes_from_the_office_setting(self):
        self.as_user(self.accountant)
        today = timezone.localdate()
        start = (today - datetime.timedelta(days=10)).isoformat()
        far = (today + datetime.timedelta(days=40)).isoformat()
        near = (today + datetime.timedelta(days=5)).isoformat()

        self.assertEqual(
            self.calendar(**{"from": start, "to": far}).status_code, 200,
        )

        set_office_setting(self.tenant, "calendar_months_ahead", 0)
        self.assertEqual(
            self.calendar(**{"from": start, "to": far}).status_code, 400,
        )
        self.assertEqual(
            self.calendar(**{"from": start, "to": near}).status_code, 400,
        )
        self.assertEqual(
            self.calendar(**{"from": start, "to": today.isoformat()}).status_code, 200,
        )

    def test_a_missing_or_bad_date_is_refused(self):
        self.as_user(self.accountant)
        self.assertEqual(
            self.client.get(CALENDAR, {"from": "2026-01-01"}, **self.headers()).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                CALENDAR, {"from": "x", "to": "2026-01-31"}, **self.headers(),
            ).status_code,
            400,
        )

    def test_an_impossible_date_is_a_400_not_a_server_error(self):
        """`2026-02-30` صحيحُ الشكل فاسدُ اليوم — كان يرمي `ValueError` (500)."""
        self.as_user(self.accountant)

        res = self.calendar(**{"from": "2026-02-30", "to": "2026-03-31"})
        self.assertEqual(res.status_code, 400, res.content)

        res = self.client.get(
            f"{CLIENTS}{self.palestinian.pk}/services/suggest/",
            {"service": "vat", "on": "2026-02-30"},
            **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)


class CalendarQueryCostTest(APITestCase):
    """تكلفةُ التقويم لا تكبر بعدد الزبائن — سياقٌ واحدٌ يُبنى قبل الحلقة.

    كلُّ ما يُحلّ لكل زبون (نظامُه، يومُ راحته، طريقةُ تقديمه، أيامُ إعداده،
    وخدماتُه ودورياتُها) يُحلّ **مرّةً** للطلب: `resolve_setting_for_clients`
    للمفاتيح القابلة للتخصيص، و`prefetch_related` لخدمات الزبائن.
    """

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="dl_cost_owner", password="x")
        cls.tenant = create_company(
            "مكتب تكلفة التقويم", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)
        cls.first = cls._make_client("زبون أول")

    @classmethod
    def _make_client(cls, name):
        client = OfficeClient.objects.create(
            tenant=cls.tenant, name=name, responsible=cls.owner,
        )
        TaxCard.objects.create(
            client=client, vat_classification="authorized",
            annual_sales=Decimal("400000"),
        )
        services.add_client_service(
            client=client, service=cls.catalog["vat"],
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
            frequency="monthly",
        )
        return client

    def _queries(self, window):
        with CaptureQueriesContext(connection) as captured:
            res = self.client.get(
                CALENDAR, window, HTTP_X_TENANT_ID=str(self.tenant.pk),
            )
        self.assertEqual(res.status_code, 200, res.content)
        return captured.captured_queries, len(res.data["rows"])

    def test_the_query_count_does_not_grow_with_the_client_count(self):
        self.client.force_authenticate(user=self.owner)
        window = {"from": "2026-01-01", "to": "2026-02-28"}
        # إحماءُ الكاشات (صلاحياتٌ وترخيص) قبل القياس.
        self.client.get(CALENDAR, window, HTTP_X_TENANT_ID=str(self.tenant.pk))

        small, one_client_rows = self._queries(window)
        self.assertTrue(one_client_rows)

        for index in range(4):
            self._make_client(f"زبون إضافي {index}")

        big, five_client_rows = self._queries(window)

        self.assertEqual(five_client_rows, one_client_rows * 5)
        self.assertEqual(
            len(big), len(small),
            f"عددُ استعلامات التقويم كبر بعدد الزبائن: {len(small)} ⇒ {len(big)}",
        )


class DeadlineRulesApiTest(DeadlineApiTestCase):
    def test_the_rules_of_both_systems_are_listed_for_every_year(self):
        self.as_user(self.accountant)
        res = self.client.get(RULES, {"system": "PS"}, **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        rows = res.data["rules"]
        self.assertEqual({row["year"] for row in rows}, {2026, 2027})
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            set(rows[0]),
            {
                "code", "name", "service_code", "is_generated", "needs_review",
                "year", "version", "source_url",
                "platform", "override", "history",
                "rule_code", "awaiting_decision",
            },
        )
        social = next(row for row in rows if row["code"] == "ps_social_security")
        self.assertFalse(social["is_generated"])

    def test_an_unknown_system_is_refused(self):
        self.as_user(self.accountant)
        self.assertEqual(
            self.client.get(RULES, {"system": "JO"}, **self.headers()).status_code, 400,
        )
        self.assertEqual(
            self.client.get(RULES, {}, **self.headers()).status_code, 400,
        )

    def test_the_israeli_rules_mark_the_ones_under_review(self):
        self.as_user(self.accountant)
        rows = self.client.get(RULES, {"system": "IL"}, **self.headers()).data["rules"]

        reviewed = {row["code"] for row in rows if row["needs_review"]}
        self.assertEqual(reviewed, {"il_annual_1301", "il_annual_1214"})

    def test_listing_the_rules_writes_nothing(self):
        self.as_user(self.accountant)
        before = self.model_row_counts()
        self.client.get(RULES, {"system": "IL"}, **self.headers())
        self.assertEqual(before, self.model_row_counts())
