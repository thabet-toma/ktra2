"""الالتزامات والشغلات ومحرّك «حدّث المكتب ليوم X» — #275.

**القواعد المحسومة التي يثبتها هذا الملف:**

1. **«حدّث المكتب ليوم X» idempotent ولا يقرأ ساعةً**: كلُّ نداءٍ بيومه الصريح،
   ولا تُحفظ إلا فترةٌ **انتهت قبل اليوم** — فق.م كانون الثاني تظهر في 1 شباط
   ولا تظهر في 31 كانون الثاني.
2. **محرّكٌ واحد**: التقويمُ والتحديثُ يقرآن المولّدَ نفسه للفترات والقواعد، فلا
   نسختان تفترقان عند أول تعديل. والتحديثُ **يُلحق ما فات** بلا سقف 24 شهراً.
3. **المشتقُّ يُحسب عند القراءة** («قريب»، «متأخّر») ولا يُخزَّن في عمود.
4. **«انقدّم» نهائيٌّ لا يُتراجَع عنه، والمبلغُ يُقفل عنده**، و«مش لازم هالفترة»
   تُفتح من جديد.
5. **الإيقافُ لا يمحو التاريخ، و`last_period_ours` تُسقط آخر فترةٍ للأبد.**
6. **الشغلةُ المحوَّلة تُري زبونها لصاحبها** بلا `office.clients.all` — من
   `visible_clients` وحدها.
"""
import datetime
import importlib
import io
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from accounting_office import services
from accounting_office.models import (
    ClientService,
    DeadlineRule,
    Obligation,
    OfficeClient,
    OfficeRefreshRun,
    PeriodTask,
    TaxCard,
)
from accounting_office.services import set_office_setting
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

#: هجرةُ بيانات اللائحة والسقوف — تُستدعى بدالّتها كما هي (نمط `test_deadlines.py`).
SCHEDULES_MIGRATION = "accounting_office.migrations.0004_deadline_schedules"
THRESHOLDS_MIGRATION = "accounting_office.migrations.0003_services_packages_thresholds"

JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
FEB_END = datetime.date(2026, 2, 28)
FEB_FIRST = datetime.date(2026, 2, 1)
MAR_END = datetime.date(2026, 3, 31)
APR_FIRST = datetime.date(2026, 4, 1)


def seed_published_thresholds():
    migration = importlib.import_module(THRESHOLDS_MIGRATION)
    migration.seed_tax_thresholds(django_apps, None)


def seed_deadline_schedules():
    """بياناتُ اللائحة **من هجرة البيانات نفسها** — لا زرعٌ يدويٌّ موازٍ لها."""
    migration = importlib.import_module(SCHEDULES_MIGRATION)
    migration.seed_deadline_schedules(django_apps, None)


def ready_office(tenant, tax_system="IL"):
    set_office_setting(tenant, "tax_system", tax_system)
    set_office_setting(tenant, "office_size", "small")


def catalog(tenant):
    return {row.code: row for row in services.ensure_default_services(tenant)}


def codes(*obligations):
    return sorted(row.rule_code for row in obligations)


class OfficeTestCase(TestCase):
    """مكتبٌ إسرائيليٌّ بلائحته المنزرعة، وخدماتُ كتالوجه الخمسة."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="ob_owner", password="x")
        cls.tenant = create_company(
            "مكتب الالتزامات", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def make_client(self, name, *, responsible=None, **card):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=responsible or self.owner,
        )
        fields = {"annual_sales": Decimal("0"), "vat_classification": "authorized"}
        fields.update(card)
        TaxCard.objects.create(client=client, **fields)
        return client

    def add_service(
        self, client, code, *,
        frequency="monthly", starts_on=JAN_START, responsible_from=None,
    ):
        return services.add_client_service(
            client=client,
            service=self.catalog[code],
            starts_on=starts_on,
            responsible_from=responsible_from or starts_on,
            frequency=frequency,
        )

    def refresh(self, day):
        return services.refresh_office(self.tenant, day=day)

    def rows(self, day, filter=""):
        return services.today_payload(
            self.tenant, user=self.owner, day=day, filter=filter,
        )


class IdempotenceTest(OfficeTestCase):
    """التشغيلُ مرّتين لليوم نفسه = مرّة: لا صفَّ مكرّرٌ ولا سجلَّان."""

    def test_running_it_twice_for_the_same_day_creates_nothing_the_second_time(self):
        client = self.make_client("زبون الرواتب", has_employees=True)
        self.add_service(client, "payroll")

        first = self.refresh(FEB_FIRST)
        # العدّادُ المسجَّلُ لليوم هو ما أنشأه أوّلُ تشغيل — والثاني لا يكتب صفّاً.
        self.assertEqual(first["created_obligations"], Obligation.objects.count())
        self.assertEqual(
            first["created_obligations"],
            OfficeRefreshRun.objects.get(tenant=self.tenant, day=FEB_FIRST)
            .created_obligations,
        )
        tasks = PeriodTask.objects.count()
        obligations = Obligation.objects.count()

        second = self.refresh(FEB_FIRST)

        self.assertEqual(second["created_obligations"], 0)
        self.assertEqual(second["created_tasks"], 0)
        self.assertEqual(PeriodTask.objects.count(), tasks)
        self.assertEqual(Obligation.objects.count(), obligations)
        self.assertEqual(
            OfficeRefreshRun.objects.filter(tenant=self.tenant, day=FEB_FIRST).count(), 1,
        )

    def test_ensure_does_not_refresh_a_day_already_recorded(self):
        """`refresh_office` تُسجّل الصفَّ وهي مُتساوية التكرار، فعدُّ الصفوف لا يثبت `ensure`."""
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")

        with mock.patch(
            "accounting_office.services.refresh_office", wraps=services.refresh_office,
        ) as refresh:
            services.ensure_office_refreshed(self.tenant, day=FEB_FIRST)
            obligations = Obligation.objects.count()
            services.ensure_office_refreshed(self.tenant, day=FEB_FIRST)

        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(Obligation.objects.count(), obligations)
        self.assertEqual(OfficeRefreshRun.objects.filter(tenant=self.tenant).count(), 1)


class DueDatesTest(OfficeTestCase):
    """ما «حان وقته» = فترةٌ انتهت قبل اليوم — بأوّل يومٍ بعد نهايتها."""

    def test_the_january_vat_appears_on_the_first_of_february(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")

        self.refresh(JAN_END)
        self.assertEqual(
            Obligation.objects.filter(rule_code="il_vat_periodic").count(), 0,
            "ق.م كانون الثاني ظهرت في 31 كانون الثاني — والفترة لم تنتهِ بعد",
        )

        self.refresh(FEB_FIRST)
        january = Obligation.objects.get(rule_code="il_vat_periodic")
        self.assertEqual(january.period_end, JAN_END)

    def test_running_it_for_a_later_day_catches_up_every_missed_period(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")

        self.refresh(APR_FIRST)

        self.assertEqual(
            sorted(
                row.period_end
                for row in Obligation.objects.filter(rule_code="il_vat_periodic")
            ),
            [JAN_END, FEB_END, MAR_END],
        )

    def test_a_monthly_payroll_client_makes_one_task_with_two_obligations(self):
        client = self.make_client("زبون الرواتب", has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(FEB_FIRST)

        tasks = list(PeriodTask.objects.all())
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual((task.period_start, task.period_end), (JAN_START, JAN_END))
        self.assertEqual(
            codes(*task.obligations.all()), ["il_bl_employees", "il_withholding_102"],
        )
        self.assertEqual(
            task.internal_deadline,
            min(row.internal_deadline for row in task.obligations.all()),
        )

    def test_the_annual_payroll_report_gets_its_own_task_in_the_next_year(self):
        client = self.make_client("زبون الرواتب", has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(datetime.date(2027, 1, 1))

        task = PeriodTask.objects.get(
            period_start=JAN_START, period_end=datetime.date(2026, 12, 31),
        )
        self.assertEqual(codes(*task.obligations.all()), ["il_annual_126_856"])

    def test_an_estimated_year_is_saved_with_the_flag(self):
        client = self.make_client("زبون 2028", vat_classification="authorized")
        self.add_service(client, "vat", starts_on=datetime.date(2028, 1, 1))

        self.refresh(datetime.date(2028, 2, 1))

        row = Obligation.objects.get(rule_code="il_vat_periodic")
        self.assertEqual(row.period_end, datetime.date(2028, 1, 31))
        self.assertTrue(row.estimated, "سنةٌ بلا لائحةٍ منشورة تُحفظ «تقديرية»")


class OneEngineTest(OfficeTestCase):
    """التحديثُ والتقويمُ مولّدٌ واحد: تغييرُ سطرٍ في اللائحة لا يمسّ المحفوظ."""

    def test_an_existing_obligation_is_never_updated(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")
        self.refresh(FEB_FIRST)
        january = Obligation.objects.get(rule_code="il_vat_periodic")
        saved = (
            january.official_date, january.actual_deadline, january.internal_deadline,
        )

        rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )
        rule.rule_day = 20
        rule.electronic_extension_days = 0
        rule.save(update_fields=["rule_day", "electronic_extension_days"])

        self.refresh(APR_FIRST)

        january.refresh_from_db()
        self.assertEqual(
            (january.official_date, january.actual_deadline, january.internal_deadline),
            saved,
            "صفٌّ محفوظٌ تغيّرت تواريخه بتعديل اللائحة — والتحديثُ لا يحدّث صفّاً قائماً",
        )
        february = Obligation.objects.get(
            rule_code="il_vat_periodic", period_end=FEB_END,
        )
        # شباط حُسب **بالسطر المعدَّل** (يوم 20 من الشهر التالي): التاريخُ بالقاعدة
        # دليلُه، وأيُّ سطرٍ آخر كان يعطي 15. ومقارنةُ تاريخين لشهرين مختلفين كانت
        # تخضرّ ولو لم يُقرأ التعديلُ أصلاً.
        self.assertEqual(february.legal_date, datetime.date(2026, 3, 20))

    def test_the_calendar_still_computes_and_saves_nothing(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")

        before = Obligation.objects.count()
        rows = services.client_deadlines(client, start=FEB_FIRST, end=FEB_END)

        self.assertTrue(rows)
        self.assertEqual(Obligation.objects.count(), before)


class DerivedStatusTest(OfficeTestCase):
    """«قريب» و«متأخّر» و«متأخّر داخلي» تُحسب من اليوم المعطى — ولا عمودَ لها."""

    def test_the_badges_are_computed_at_read_time_without_touching_the_database(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")
        self.refresh(FEB_FIRST)
        row = Obligation.objects.get(rule_code="il_vat_periodic")
        actual = row.actual_deadline
        internal = row.internal_deadline
        snapshot = list(
            Obligation.objects.values(
                "status", "official_date", "actual_deadline", "internal_deadline",
            ),
        )

        # #276: يومُ الموعد الداخليّ نفسِه — لم يتجاوزه بعدُ فهو «قريب» لا أصفر.
        self.assertEqual(
            [badge["key"] for badge in self.rows(internal)["rows"][0]["badges"]],
            ["near"],
        )
        # وبعدَه بيوم: الشغلةُ تجاوزت داخليَّها ⇒ أصفرُ، و«قريب» لا تُعرض معه.
        self.assertEqual(
            [badge["key"] for badge in self.rows(
                internal + datetime.timedelta(days=1),
            )["rows"][0]["badges"]],
            ["late_internal"],
        )
        self.assertEqual(
            [badge["key"] for badge in self.rows(
                actual + datetime.timedelta(days=1),
            )["rows"][0]["badges"]],
            ["late"],
        )
        self.assertEqual(
            self.rows(actual - datetime.timedelta(days=40))["rows"][0]["badges"], [],
        )
        self.assertEqual(
            list(
                Obligation.objects.values(
                    "status", "official_date", "actual_deadline", "internal_deadline",
                ),
            ),
            snapshot,
            "قراءةُ الحالة المشتقّة كتبت في القاعدة — وهي تُحسب عند القراءة وحدها",
        )


class StatusFlowTest(OfficeTestCase):
    """«انقدّم» نهائيٌّ، و«مش لازم هالفترة» تُفتح، والمبلغُ يُقفل عند الإرسال."""

    def setUp(self):
        self.client_row = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(self.client_row, "vat")
        self.refresh(FEB_FIRST)
        self.obligation = Obligation.objects.get(rule_code="il_vat_periodic")

    def test_the_amount_is_locked_after_submission(self):
        services.set_obligation_amount(
            self.obligation, amount=Decimal("620"), direction="due",
        )
        services.submit_obligation(
            self.obligation, actor=self.owner, submitted_on=FEB_FIRST, number="4417",
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.amount, Decimal("620"))
        self.assertEqual(self.obligation.status, Obligation.STATUS_SUBMITTED)
        self.assertEqual(self.obligation.submitted_by, self.owner)
        self.assertEqual(self.obligation.submitted_on, FEB_FIRST)
        self.assertEqual(self.obligation.submission_number, "4417")

        with self.assertRaises(DjangoValidationError) as raised:
            services.set_obligation_amount(
                self.obligation, amount=Decimal("1"), direction="due",
            )
        self.assertIn("انقدّم", str(raised.exception))

        services.set_obligation_client_paid(self.obligation, paid=True)
        self.obligation.refresh_from_db()
        self.assertTrue(self.obligation.client_paid)

    def test_submitted_cannot_be_undone_and_not_required_reopens(self):
        services.submit_obligation(self.obligation, actor=self.owner)

        for attempt in (
            lambda: services.reopen_obligation(self.obligation, actor=self.owner),
            lambda: services.mark_obligation_not_required(
                self.obligation, actor=self.owner,
            ),
        ):
            with self.assertRaises(DjangoValidationError) as raised:
                attempt()
            self.assertIn("انقدّم لا يُتراجَع عنه", str(raised.exception))

    def test_not_required_reopens_to_pending(self):
        services.mark_obligation_not_required(self.obligation, actor=self.owner)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, Obligation.STATUS_NOT_REQUIRED)

        services.reopen_obligation(self.obligation, actor=self.owner)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, Obligation.STATUS_PENDING)

    def test_a_future_submission_date_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            services.submit_obligation(
                self.obligation, actor=self.owner,
                submitted_on=datetime.date(2099, 1, 1),
            )

    def test_the_direction_is_required_with_the_amount(self):
        with self.assertRaises(DjangoValidationError):
            services.set_obligation_amount(
                self.obligation, amount=Decimal("620"), direction="",
            )
        with self.assertRaises(DjangoValidationError):
            services.set_obligation_amount(
                self.obligation, amount=Decimal("-1"), direction="due",
            )

    def test_the_prior_button_refuses_a_future_date(self):
        client = self.make_client("زبون مستقبل", vat_classification="authorized")
        self.add_service(client, "vat")
        self.refresh(APR_FIRST)

        with self.assertRaises(DjangoValidationError) as raised:
            services.close_prior_obligations(
                client, before=datetime.date(2099, 1, 1), actor=self.owner,
            )

        self.assertIn("before", str(raised.exception))
        self.assertEqual(
            Obligation.objects.filter(
                client=client, status=Obligation.STATUS_PENDING,
            ).count(),
            3,
            "تاريخٌ مستقبليٌّ أغلق التزاماتٍ لم تنتهِ فترتُها بعد",
        )

    def test_the_prior_button_closes_only_pending_obligations_before_the_date(self):
        client = self.make_client("زبون قديم", vat_classification="authorized")
        self.add_service(client, "vat")
        self.refresh(APR_FIRST)
        january = Obligation.objects.get(
            client=client, rule_code="il_vat_periodic", period_end=JAN_END,
        )
        february = Obligation.objects.get(
            client=client, rule_code="il_vat_periodic", period_end=FEB_END,
        )
        march = Obligation.objects.get(
            client=client, rule_code="il_vat_periodic", period_end=MAR_END,
        )
        services.mark_obligation_not_required(february, actor=self.owner)

        closed = services.close_prior_obligations(
            client, before=datetime.date(2026, 3, 1), actor=self.owner,
        )

        self.assertEqual(closed, 1)
        january.refresh_from_db()
        february.refresh_from_db()
        march.refresh_from_db()
        self.assertEqual(january.status, Obligation.STATUS_SUBMITTED)
        self.assertTrue(january.prior_to_office)
        self.assertIsNone(january.submitted_on)
        self.assertEqual(january.submitted_by, self.owner)
        self.assertEqual(february.status, Obligation.STATUS_NOT_REQUIRED)
        self.assertEqual(march.status, Obligation.STATUS_PENDING)


class StopAndEndTest(OfficeTestCase):
    """الإيقافُ يُبقي المنقضيَ ويقطع ما بعده، و`last_period_ours` تُسقط الأخيرة."""

    def test_stopping_on_the_last_of_march_keeps_march_and_drops_april(self):
        client = self.make_client("زبون موقوف", vat_classification="authorized")
        service_row = self.add_service(client, "vat")

        services.stop_client_service(service_row, ends_on=MAR_END)
        self.refresh(APR_FIRST)

        self.assertEqual(
            sorted(
                row.period_end
                for row in Obligation.objects.filter(rule_code="il_vat_periodic")
            ),
            [JAN_END, FEB_END, MAR_END],
            "تقريرُ آذار المستحقُّ في نيسان يجب أن يُولَّد، ونيسانُ لا",
        )

    def test_last_period_ours_false_is_not_generated_on_refresh(self):
        client = self.make_client("زبون مسكّت", vat_classification="authorized")
        service_row = self.add_service(client, "vat")

        services.stop_client_service(
            service_row, ends_on=MAR_END, last_period_ours=False,
        )
        self.refresh(APR_FIRST)

        service_row.refresh_from_db()
        self.assertFalse(service_row.last_period_ours)
        self.assertEqual(
            sorted(
                row.period_end
                for row in Obligation.objects.filter(rule_code="il_vat_periodic")
            ),
            [JAN_END, FEB_END],
            "آخرُ فترةٍ رُفع عنها «علينا» — لا تُولَّد",
        )

    def test_last_period_ours_false_closes_a_pending_last_period(self):
        client = self.make_client("زبون مسكّت", vat_classification="authorized")
        service_row = self.add_service(client, "vat")
        self.refresh(APR_FIRST)
        march = Obligation.objects.get(
            rule_code="il_vat_periodic", period_end=MAR_END,
        )
        self.assertEqual(march.status, Obligation.STATUS_PENDING)

        services.stop_client_service(
            service_row, ends_on=MAR_END, last_period_ours=False,
        )

        march.refresh_from_db()
        self.assertEqual(march.status, Obligation.STATUS_NOT_REQUIRED)

    def test_an_ended_client_gets_no_period_after_its_ending(self):
        client = self.make_client("زبون منتهٍ", vat_classification="authorized")
        self.add_service(client, "vat")
        services.end_office_client(client, on=datetime.date(2026, 2, 15))

        self.refresh(APR_FIRST)

        self.assertEqual(
            sorted(
                row.period_end
                for row in Obligation.objects.filter(rule_code="il_vat_periodic")
            ),
            [JAN_END],
        )

    def test_stopping_records_the_flag_on_the_service_row(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        service_row = self.add_service(client, "vat")

        services.stop_client_service(service_row, ends_on=MAR_END, last_period_ours=False)

        self.assertTrue(ClientService.objects.filter(pk=service_row.pk).exists())
        service_row.refresh_from_db()
        self.assertEqual(service_row.ends_on, MAR_END)
        self.assertFalse(service_row.last_period_ours)


class LastPeriodHelperTest(SimpleTestCase):
    """دالّةُ «آخر فترةٍ في سلسلة» — نقيّةٌ بلا قاعدة ولا ساعة."""

    MONTHS = [
        (JAN_START, JAN_END),
        (datetime.date(2026, 2, 1), FEB_END),
        (datetime.date(2026, 3, 1), MAR_END),
        (APR_FIRST, datetime.date(2026, 4, 30)),
    ]

    def test_the_last_period_is_the_one_whose_next_ends_after_the_stop(self):
        self.assertEqual(
            services.last_period_of_stream(self.MONTHS, ends_on=MAR_END),
            (datetime.date(2026, 3, 1), MAR_END),
        )
        self.assertEqual(
            services.last_period_of_stream(
                self.MONTHS, ends_on=datetime.date(2026, 4, 30),
            ),
            (APR_FIRST, datetime.date(2026, 4, 30)),
        )

    def test_a_stop_inside_a_period_leaves_the_previous_one_as_last(self):
        self.assertEqual(
            services.last_period_of_stream(
                self.MONTHS, ends_on=datetime.date(2026, 2, 15),
            ),
            (JAN_START, JAN_END),
        )

    def test_no_period_ending_before_the_stop_means_no_last_period(self):
        self.assertIsNone(
            services.last_period_of_stream(
                self.MONTHS, ends_on=datetime.date(2025, 12, 31),
            ),
        )


class AssignmentTest(OfficeTestCase):
    """الشغلةُ تُحوَّل لعضوٍ من المكتب وحده، وترى صاحبَها الزبونَ بلا مفتاح الكل."""

    def setUp(self):
        self.accountant = User.objects.create_user(username="ob_accountant", password="x")
        UserCompanyMembership.objects.create(
            user=self.accountant, tenant=self.tenant, role="accountant",
        )
        self.colleague = User.objects.create_user(username="ob_colleague", password="x")
        UserCompanyMembership.objects.create(
            user=self.colleague, tenant=self.tenant, role="accountant",
        )
        self.client_row = self.make_client(
            "زبون محوَّل", responsible=self.colleague, vat_classification="authorized",
        )
        self.add_service(self.client_row, "vat")
        self.refresh(FEB_FIRST)
        self.task = PeriodTask.objects.get()

    def visible_ids(self, user):
        return set(
            services.visible_clients(self.tenant, user).values_list("pk", flat=True),
        )

    def test_the_client_is_invisible_before_the_transfer_and_visible_after(self):
        self.assertNotIn(self.client_row.pk, self.visible_ids(self.accountant))

        services.assign_task(self.task, assignee=self.accountant)

        self.assertIn(self.client_row.pk, self.visible_ids(self.accountant))
        self.assertEqual(
            services.visible_clients(self.tenant, self.accountant).count(), 1,
        )

    def test_a_member_of_another_office_is_refused(self):
        outsider = User.objects.create_user(username="ob_outsider", password="x")
        with self.assertRaises(DjangoValidationError):
            services.assign_task(self.task, assignee=outsider)

    def test_none_goes_back_to_inheriting_from_the_client(self):
        services.assign_task(self.task, assignee=self.accountant)
        services.assign_task(self.task, assignee=None)

        self.task.refresh_from_db()
        self.assertIsNone(self.task.assignee)
        self.assertEqual(self.task.effective_assignee, self.colleague)


class RefreshCommandTest(OfficeTestCase):
    """الأمرُ اليوميّ: المكتبُ المرخَّص وحده، واليومُ يُمرَّر، والتاريخُ الفاسدُ خطأ."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.general_owner = User.objects.create_user(username="ob_general", password="x")
        cls.general = create_company("شركة عامة", cls.general_owner)
        invalidate_module_cache(cls.general.pk)
        ready_office(cls.general, "IL")
        general_catalog = catalog(cls.general)
        general_client = OfficeClient.objects.create(
            tenant=cls.general, name="زبون الشركة العامة",
        )
        TaxCard.objects.create(
            client=general_client, vat_classification="authorized",
            annual_sales=Decimal("0"),
        )
        services.add_client_service(
            client=general_client,
            service=general_catalog["vat"],
            starts_on=JAN_START,
            responsible_from=JAN_START,
            frequency="monthly",
        )

    def test_it_refreshes_only_the_licensed_offices(self):
        client = self.make_client("زبون مرخَّص", vat_classification="authorized")
        self.add_service(client, "vat")

        out = io.StringIO()
        call_command("refresh_accounting_offices", "--day", "2026-02-01", stdout=out)

        self.assertTrue(
            OfficeRefreshRun.objects.filter(tenant=self.tenant, day=FEB_FIRST).exists(),
        )
        self.assertFalse(
            OfficeRefreshRun.objects.filter(tenant=self.general).exists(),
            "أمرُ التحديث شمل شركةً بلا ترخيص الوحدة",
        )
        self.assertEqual(
            Obligation.objects.filter(client__tenant=self.general).count(), 0,
        )

    def test_the_day_option_is_used_as_given(self):
        client = self.make_client("زبون مُبكّر", vat_classification="authorized")
        self.add_service(client, "vat")

        call_command("refresh_accounting_offices", "--day", "2026-04-01")

        self.assertEqual(
            sorted(row.period_end for row in Obligation.objects.filter(client=client)),
            [JAN_END, FEB_END, MAR_END],
        )

    def test_a_bad_date_is_a_command_error(self):
        with self.assertRaises(CommandError):
            call_command("refresh_accounting_offices", "--day", "2026-02-30")


class RowShapeTest(OfficeTestCase):
    """سطرُ «اليوم» بالحقول المحسومة وحدها، والقناعُ يمرّ عليه."""

    def test_the_row_carries_the_agreed_fields(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")
        self.refresh(FEB_FIRST)

        row = self.rows(FEB_FIRST)["rows"][0]

        self.assertEqual(
            set(row),
            {
                "id", "client", "task", "name", "rule_code", "origin", "origin_label",
                "period_label", "official_date", "actual_deadline", "internal_deadline",
                "estimated", "warnings", "badges", "amount", "direction",
                "direction_label", "client_paid", "status", "status_label",
                "due_date", "extended_to", "extension_note", "platform_official_date",
                # #278: `docs` = `{received, required}` أو `null`.
                "docs",
            },
        )
        self.assertEqual(set(row["client"]), {"id", "name"})
        self.assertEqual(set(row["task"]), {"id", "internal_deadline", "assignee"})
        self.assertEqual(row["origin"], Obligation.ORIGIN_OFFICIAL)
        self.assertEqual(row["origin_label"], "رسمي")
        self.assertEqual(row["status"], Obligation.STATUS_PENDING)
        self.assertEqual(row["status_label"], "لسا ما انقدّم")

    def test_the_amount_is_masked_for_a_member_without_the_amounts_key(self):
        client = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(client, "vat")
        self.refresh(FEB_FIRST)
        obligation = Obligation.objects.get(rule_code="il_vat_periodic")
        services.set_obligation_amount(
            obligation, amount=Decimal("620"), direction="due",
        )
        member = User.objects.create_user(username="ob_masked", password="x")
        UserCompanyMembership.objects.create(
            user=member, tenant=self.tenant, role="accountant",
        )
        services.assign_task(obligation.task, assignee=member)

        masked = services.today_payload(
            self.tenant, user=member, day=FEB_FIRST, filter="",
        )["rows"][0]
        full = self.rows(FEB_FIRST)["rows"][0]

        self.assertIsNone(masked["amount"])
        self.assertEqual(full["amount"], "620.00")
        self.assertEqual(full["direction_label"], "عليه")


class CountersAndFiltersTest(OfficeTestCase):
    """العدّاداتُ قبل الفلتر، والفلاترُ المحسومة، والفلترُ المجهول 400."""

    def setUp(self):
        self.client_row = self.make_client("زبون العدّاد", vat_classification="authorized")
        self.add_service(self.client_row, "vat")
        self.refresh(APR_FIRST)
        january = Obligation.objects.get(rule_code="il_vat_periodic", period_end=JAN_END)
        # #276: النافذةُ مستقلّةٌ عن الشارة — يومُ #275 نفسُه (`actual − 3`): الشارةُ
        # صفراءُ لأن الموعدَ الداخليَّ مضى، والعدّادُ `week` يعدّه لأن الفعليَّ داخل
        # النافذة. والشرطُ على `actual_deadline` وحده.
        self.near_day = january.actual_deadline - datetime.timedelta(days=3)
        last = max(row.actual_deadline for row in Obligation.objects.all())
        self.late_day = last + datetime.timedelta(days=1)

    def test_counters_are_computed_before_the_filter(self):
        window = self.rows(self.near_day)
        late = self.rows(self.late_day)

        self.assertEqual(
            window["counters"],
            # #278: `missing_docs` خامسةُ العدّادات — صفرٌ هنا: لا صفوفَ أوراق.
            {"late": 0, "late_internal": 1, "week": 1, "missing_docs": 0, "all": 3},
        )
        self.assertEqual(
            late["counters"],
            {"late": 3, "late_internal": 0, "week": 0, "missing_docs": 0, "all": 3},
        )
        self.assertEqual(len(late["rows"]), 3)

    def test_the_week_window_and_the_two_late_filters_narrow_the_rows(self):
        week = self.rows(self.near_day, filter="week")
        yellow = self.rows(self.near_day, filter="late_internal")
        late = self.rows(self.late_day, filter="late")

        self.assertEqual(len(week["rows"]), 1)
        self.assertEqual(
            len(yellow["rows"]), 1,
            "الصفُّ نفسُه يظهر تحت النافذة وتحت الأصفر — وهذه هي المسألة",
        )
        self.assertEqual(
            week["rows"][0]["id"], yellow["rows"][0]["id"],
            "نافذةُ `week` لا تُسقط الصفَّ الأصفرَ الواقعَ داخلها",
        )
        self.assertEqual(len(late["rows"]), 3)
        self.assertEqual(week["counters"], self.rows(self.near_day)["counters"])

    def test_the_mine_filter_follows_the_effective_assignee(self):
        other = User.objects.create_user(username="ob_other", password="x")
        UserCompanyMembership.objects.create(
            user=other, tenant=self.tenant, role="accountant",
        )
        # بلا `assignee` ترث الشغلةُ مسؤولَ الزبون — وهو هذا العضو.
        self.assertEqual(len(self.rows(self.near_day, filter="mine")["rows"]), 3)

        for task in PeriodTask.objects.all():
            services.assign_task(task, assignee=other)

        self.assertEqual(len(self.rows(self.near_day, filter="mine")["rows"]), 0)

    def test_an_unknown_filter_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            self.rows(self.near_day, filter="someday")


class TransitionGuardTest(OfficeTestCase):
    """كلُّ انتقالٍ يبدأ من حالةٍ واحدة (#275): لا «انقدّم» عن «مش لازم» ولا العكس."""

    def setUp(self):
        self.client_row = self.make_client("زبون الانتقالات", vat_classification="authorized")
        self.add_service(self.client_row, "vat")
        self.refresh(APR_FIRST)
        rows = list(Obligation.objects.order_by("period_end"))
        self.pending, self.not_required, self.submitted = rows
        services.mark_obligation_not_required(self.not_required, actor=self.owner)
        services.submit_obligation(self.submitted, actor=self.owner)

    def test_submitting_a_not_required_obligation_is_refused_first(self):
        with self.assertRaises(DjangoValidationError) as raised:
            services.submit_obligation(self.not_required, actor=self.owner)
        self.assertIn("رجّعها", str(raised.exception))

    def test_marking_an_already_not_required_obligation_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            services.mark_obligation_not_required(self.not_required, actor=self.owner)

    def test_reopening_a_pending_obligation_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            services.reopen_obligation(self.pending, actor=self.owner)

    def test_leaving_submitted_keeps_the_locked_message(self):
        for attempt in (
            lambda: services.submit_obligation(self.submitted, actor=self.owner),
            lambda: services.mark_obligation_not_required(self.submitted, actor=self.owner),
            lambda: services.reopen_obligation(self.submitted, actor=self.owner),
        ):
            with self.assertRaises(DjangoValidationError) as raised:
                attempt()
            self.assertIn(services.SUBMITTED_LOCKED, str(raised.exception))


class RefreshCostTest(TestCase):
    """كلفةُ التحديث لا تكبر بتاريخٍ محفوظ (#275): القائمُ يُقرأ استعلامين لا بنداً بنداً.

    والمدى نفسُه في الحالتين (سنواتُ اللائحة المقروءة واحدة)، والفارقُ عددُ
    الفترات المحفوظة وحده — فما زاد استعلاماً واحداً فالمفتاح لا يعمل.
    """

    DAY1 = datetime.date(2026, 12, 31)
    DAY2 = datetime.date(2027, 1, 5)

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()

    def make_office(self, name, starts_on):
        owner = User.objects.create_user(username=f"cost_{name}", password="x")
        tenant = create_company(f"مكتب {name}", owner, template="accounting_office")
        invalidate_module_cache(tenant.pk)
        ready_office(tenant, "IL")
        client = OfficeClient.objects.create(
            tenant=tenant, name=f"زبون {name}", responsible=owner,
        )
        TaxCard.objects.create(
            client=client, vat_classification="authorized",
            annual_sales=Decimal("0"),
        )
        services.add_client_service(
            client=client,
            service=catalog(tenant)["vat"],
            starts_on=starts_on,
            responsible_from=starts_on,
            frequency="monthly",
        )
        return tenant

    def test_the_refresh_cost_does_not_grow_with_the_saved_history(self):
        short = self.make_office("قصير", datetime.date(2026, 10, 1))
        long = self.make_office("طويل", datetime.date(2026, 1, 1))
        for tenant in (short, long):
            services.refresh_office(tenant, day=self.DAY1)
            # الصفُّ يُسجَّل هنا، فالقياسُ أدناه لا يدفع كتابةَ سجلٍّ في إحدى الحالتين.
            services.refresh_office(tenant, day=self.DAY2)

        self.assertEqual(Obligation.objects.filter(client__tenant=short).count(), 3)
        self.assertEqual(Obligation.objects.filter(client__tenant=long).count(), 12)

        with CaptureQueriesContext(connection) as few:
            services.refresh_office(short, day=self.DAY2)
        with CaptureQueriesContext(connection) as many:
            services.refresh_office(long, day=self.DAY2)

        self.assertEqual(
            len(many.captured_queries), len(few.captured_queries),
            "كلفةُ التحديث كبرت بتاريخ الزبون — القائمُ يُقرأ مرّةً لا بنداً بنداً",
        )
