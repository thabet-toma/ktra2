"""التأخيرُ بدرجتين والتنبيهاتُ الداخلية — #276.

**ما يثبته هذا الملف:**

1. **درجتان مشتقّتان عند القراءة ولا تُخزَّنان**: أحمر `late` = منتظرٌ و
   `actual_deadline < day`، وأصفر `late_internal` = منتظرٌ وشغلتُه
   `internal_deadline < day` وليس أحمر، و`near` دونهما — **شارةٌ واحدةٌ لكل صفّ**.
2. **التنبيهُ يُولَّد مرّةً واحدةً لكل (مستلِم، نوع، مرجع)** بفرادةٍ غير مشروطة،
   ولا يتكرّر بيومٍ لاحق، و`created_alerts` عدّادُ ما أنشأه النداء وحده.
3. **المستلِمُ من الإعداد**: «المسؤول» = `effective_assignee`، وإن غاب فصاحبُ
   المكتب، و«صاحب المكتب» = عضوٌ نشطٌ بدور `manager` (التعريفُ القائم)، ومستلِمٌ
   واحدٌ لا يُكرَّر إن جمعهما.
4. **المحسومُ يُستبعد عند القراءة ولا يُحذف**: «انقدّم» و«مش لازم هالفترة»
   يُسقطان التنبيه من الجرس والصفُّ في القاعدة يبقى.
5. **العدّاداتُ الأربعة قبل الفلتر**، وفلترا `late`/`late_internal` منفصلان.
6. **كلفةُ التوليد لا تكبر بعدد الالتزامات** (استعلاماتٌ ثابتة).
"""
import datetime
import io
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounting_office import services
from accounting_office.models import (
    OBLIGATION_BADGE_LATE,
    OBLIGATION_BADGE_LATE_INTERNAL,
    OBLIGATION_BADGE_NEAR,
    DeadlineRule,
    Obligation,
    OfficeAlert,
    OfficeClient,
    OfficeService,
    PeriodTask,
    TaxCard,
)
from accounting_office.services import set_office_setting
from accounting_office.tests.test_obligations import OfficeTestCase, catalog, ready_office
from core.modules import invalidate_module_cache
from tenants.models import UserCompanyMembership
from tenants.services import create_company

#: يومٌ صريح: بين الموعد الداخليّ لالتزامٍ والموعد الرسميّ — فيظهر الصفّ أصفرَ لا أحمر.
DAY = datetime.date(2026, 2, 12)
JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
FEB_START = datetime.date(2026, 2, 1)
FEB_END = datetime.date(2026, 2, 28)


def office_client_without_periods(tenant, name, *, responsible=None):
    """زبونٌ خدمتُه تبدأ يومَ التشغيل: لا فترةَ تنتهي قبله فيُولّدها المحرّك.

    فما يُزرع في الاختبار وحدَه هو ما يولّد تنبيهاتٍ — والنتيجةُ محسوبةٌ لا عشوائية.
    """
    client = OfficeClient.objects.create(
        tenant=tenant, name=name, responsible=responsible,
    )
    TaxCard.objects.create(
        client=client, vat_classification="authorized",
        annual_sales=Decimal("0"),
    )
    services.add_client_service(
        client=client,
        service=OfficeService.objects.get(tenant=tenant, code="vat"),
        starts_on=DAY,
        responsible_from=DAY,
        frequency="monthly",
    )
    return client


def add_obligation_row(
    *, tenant, client, rule, actual, internal,
    status=Obligation.STATUS_PENDING, assignee=None, task=None,
    period_start=JAN_START, period_end=JAN_END,
):
    """شغلةٌ والتزامُها بيومٍ صريح — لا ساعةَ ولا محرّك."""
    row = client.services.get()
    if task is None:
        task = PeriodTask.objects.create(
            tenant=tenant,
            client=client,
            client_service=row,
            period_start=period_start,
            period_end=period_end,
            internal_deadline=internal,
            assignee=assignee,
        )
    return Obligation.objects.create(
        tenant=tenant,
        client=client,
        client_service=row,
        task=task,
        rule=rule,
        rule_code=rule.code,
        name=rule.name,
        period_start=period_start,
        period_end=period_end,
        legal_date=actual,
        official_date=actual,
        actual_deadline=actual,
        internal_deadline=internal,
        status=status,
    )


class AlertsTestCase(OfficeTestCase):
    """مكتبٌ بلائحته ومالكٍ له، ومحاسبٌ مسؤولٌ عن زبائن، ومالكٌ ثانٍ في المكتب."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.accountant = User.objects.create_user(username="al_accountant", password="x")
        UserCompanyMembership.objects.create(
            user=cls.accountant, tenant=cls.tenant, role="accountant",
        )
        # عضويّةُ `create_company` دورُها `manager` — أي صاحبُ المكتب (التعريف القائم).
        cls.owner_two = User.objects.create_user(username="al_owner_two", password="x")
        UserCompanyMembership.objects.create(
            user=cls.owner_two, tenant=cls.tenant, role="manager",
        )
        cls.rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )

    def make_alert_client(self, name, *, responsible=None):
        return office_client_without_periods(
            self.tenant, name, responsible=responsible,
        )

    def add_row(self, client, **fields):
        return add_obligation_row(
            tenant=self.tenant, client=client, rule=self.rule, **fields,
        )

    def generate(self, tenant=None, *, day=DAY):
        return services._generate_late_alerts(tenant or self.tenant, day=day)

    def recipients(self, kind):
        return set(
            OfficeAlert.objects.filter(kind=kind).values_list("recipient_id", flat=True),
        )


class TwoTierBadgeTest(AlertsTestCase):
    """الدرجتان: الأصفرُ قبل الرسميّ، والأحمرُ بعده، والأولويةُ محسومة."""

    def test_a_task_past_its_internal_deadline_is_yellow_and_not_red(self):
        client = self.make_alert_client("زبون أصفر", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=20),
            internal=DAY - datetime.timedelta(days=2),
        )

        row = services.today_payload(
            self.tenant, user=self.owner, day=DAY,
        )["rows"][0]

        self.assertEqual(
            [badge["key"] for badge in row["badges"]],
            [OBLIGATION_BADGE_LATE_INTERNAL],
        )
        self.assertEqual(row["badges"][0]["label"], "متأخّر داخلي")

    def test_the_red_badge_wins_and_arrives_alone(self):
        client = self.make_alert_client("زبون أحمر", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=2),
            internal=DAY - datetime.timedelta(days=9),
        )

        row = services.today_payload(
            self.tenant, user=self.owner, day=DAY,
        )["rows"][0]

        self.assertEqual([badge["key"] for badge in row["badges"]], [OBLIGATION_BADGE_LATE])
        self.assertEqual(
            row["badges"][0]["label"], "متأخّر رسمي",
            "الأحمرُ كلمةٌ واحدة في الشاشة: عدّادُ «اليوم» يقول «متأخّر رسمي»",
        )

    def test_the_yellow_badge_wins_over_near(self):
        client = self.make_alert_client("زبون أصفر قريب", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=1),
        )

        row = services.today_payload(
            self.tenant, user=self.owner, day=DAY,
        )["rows"][0]

        self.assertEqual(
            [badge["key"] for badge in row["badges"]],
            [OBLIGATION_BADGE_LATE_INTERNAL],
        )

    def test_near_survives_only_while_the_internal_deadline_is_ahead(self):
        client = self.make_alert_client("زبون قريب", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=5),
            internal=DAY + datetime.timedelta(days=1),
        )

        row = services.today_payload(
            self.tenant, user=self.owner, day=DAY,
        )["rows"][0]

        self.assertEqual([badge["key"] for badge in row["badges"]], [OBLIGATION_BADGE_NEAR])

    def test_a_resolved_row_carries_no_badge_at_all(self):
        client = self.make_alert_client("زبون محسوم", responsible=self.owner)
        for index, status in enumerate(
            (Obligation.STATUS_SUBMITTED, Obligation.STATUS_NOT_REQUIRED),
        ):
            with self.subTest(status=status):
                # فترةٌ لكل حالة: فرادةُ الالتزام على (الخدمة، الكود، نهاية الفترة).
                self.add_row(
                    client,
                    actual=DAY - datetime.timedelta(days=4),
                    internal=DAY - datetime.timedelta(days=9),
                    status=status,
                    period_start=JAN_START,
                    period_end=JAN_END + datetime.timedelta(days=31 * index),
                )

        payload = services.today_payload(self.tenant, user=self.owner, day=DAY)

        self.assertEqual(payload["rows"], [])
        self.assertEqual(
            payload["counters"],
            # #278: `missing_docs` خامسةُ العدّادات — صفرٌ حيث لا صفوفَ أوراق.
            {"late": 0, "late_internal": 0, "week": 0, "missing_docs": 0, "all": 0},
        )
        self.assertEqual(
            sorted(Obligation.objects.values_list("status", flat=True)),
            sorted([Obligation.STATUS_SUBMITTED, Obligation.STATUS_NOT_REQUIRED]),
            "قراءةُ الحالة المشتقّة كتبت في القاعدة — وهي تُحسب عند القراءة وحدها",
        )


class GenerationTest(AlertsTestCase):
    """التنبيهُ يُولَّد من `refresh_office`، ومستلِمُه من الإعداد."""

    def test_the_internal_alert_goes_to_the_assignee_alone_by_default(self):
        client = self.make_alert_client("زبون الداخلي", responsible=self.accountant)
        obligation = self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=20),
            internal=DAY - datetime.timedelta(days=5),
        )

        created = self.generate()

        self.assertEqual(created, 1)
        self.assertEqual(
            self.recipients(OfficeAlert.KIND_TASK_LATE_INTERNAL),
            {self.accountant.pk},
            "الافتراضُ «المسؤول» وحده — صاحبُ المكتب لا يستلم الأصفر",
        )
        alert = OfficeAlert.objects.get(kind=OfficeAlert.KIND_TASK_LATE_INTERNAL)
        self.assertEqual(alert.ref_key, f"task:{obligation.task_id}")
        self.assertEqual(alert.client_id, client.pk)
        self.assertEqual(alert.task_id, obligation.task_id)
        self.assertIsNone(alert.obligation_id)
        self.assertEqual(alert.day, DAY)
        self.assertIsNone(alert.seen_at)

    def test_the_official_alert_goes_to_the_assignee_and_the_owners_by_default(self):
        client = self.make_alert_client("زبون الرسمي", responsible=self.accountant)
        obligation = self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )

        self.generate()

        self.assertEqual(
            self.recipients(OfficeAlert.KIND_OBLIGATION_LATE),
            {self.accountant.pk, self.owner.pk, self.owner_two.pk},
            "الافتراضُ «المسؤول وصاحبُ المكتب» — وكلُّ عضوٍ نشطٍ بدور manager",
        )
        self.assertEqual(
            self.recipients(OfficeAlert.KIND_TASK_LATE_INTERNAL),
            {self.accountant.pk},
            "الشغلةُ صارت حمراء فهي تأخذ الأحمر أيضاً، والداخليُّ يبقى للمسؤول",
        )
        official = OfficeAlert.objects.get(
            kind=OfficeAlert.KIND_OBLIGATION_LATE, recipient=self.owner,
        )
        self.assertEqual(official.ref_key, f"obligation:{obligation.pk}")
        self.assertEqual(official.obligation_id, obligation.pk)

    def test_the_owner_setting_keeps_the_red_alert_away_from_the_assignee(self):
        set_office_setting(self.tenant, "late_official_alert_to", "owner")
        client = self.make_alert_client("زبون المالك", responsible=self.accountant)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )

        self.generate()

        self.assertEqual(
            self.recipients(OfficeAlert.KIND_OBLIGATION_LATE),
            {self.owner.pk, self.owner_two.pk},
        )
        self.assertEqual(
            self.recipients(OfficeAlert.KIND_TASK_LATE_INTERNAL),
            {self.accountant.pk},
            "إعدادُ الأحمر لا يمسّ الأصفر — إعدادان لا واحد",
        )

    def test_the_assignee_setting_keeps_the_red_alert_away_from_the_owner(self):
        set_office_setting(self.tenant, "late_official_alert_to", "assignee")
        client = self.make_alert_client("زبون المسؤول", responsible=self.accountant)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )

        self.generate()

        self.assertEqual(
            self.recipients(OfficeAlert.KIND_OBLIGATION_LATE), {self.accountant.pk},
        )

    def test_a_client_without_a_responsible_falls_back_to_the_owners(self):
        client = self.make_alert_client("زبون بلا مسؤول")
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        set_office_setting(self.tenant, "late_internal_alert_to", "assignee")

        self.generate()

        self.assertEqual(
            self.recipients(OfficeAlert.KIND_OBLIGATION_LATE),
            {self.owner.pk, self.owner_two.pk},
        )
        self.assertEqual(
            self.recipients(OfficeAlert.KIND_TASK_LATE_INTERNAL),
            {self.owner.pk, self.owner_two.pk},
            "«المسؤول» الغائب يذهب لصاحب المكتب بدلاً منه",
        )

    def test_one_alert_when_the_assignee_is_also_the_owner(self):
        client = self.make_alert_client("زبون المالك نفسه", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )

        created = self.generate()

        self.assertEqual(
            created,
            3,
            "أحمرُ لصاحبَي المكتب (هو وزميلُه العضو الآخر بدور manager) وأصفرُ له وحده",
        )
        self.assertEqual(
            OfficeAlert.objects.filter(
                kind=OfficeAlert.KIND_OBLIGATION_LATE, recipient=self.owner,
            ).count(),
            1,
            "من هو المسؤولُ وصاحبُ المكتب معاً يأخذ تنبيهاً واحداً لا اثنين",
        )
        self.assertEqual(
            self.recipients(OfficeAlert.KIND_TASK_LATE_INTERNAL), {self.owner.pk},
        )

    def test_the_alert_message_carries_the_client_and_the_period_without_an_amount(self):
        client = self.make_alert_client("أبو أحمد", responsible=self.accountant)
        obligation = self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        services.set_obligation_amount(obligation, amount=Decimal("620"), direction="due")

        self.generate()

        alert = OfficeAlert.objects.get(
            kind=OfficeAlert.KIND_OBLIGATION_LATE, recipient=self.accountant,
        )
        self.assertIn("أبو أحمد", alert.message)
        self.assertIn(obligation.name, alert.message)
        self.assertNotIn("620", alert.message)
        self.assertNotIn("₪", alert.message)


class IdempotenceTest(AlertsTestCase):
    """«مرّةٌ لكل مرجع»: لا تكرارَ في اليوم نفسه ولا في الأيام التالية."""

    def test_refresh_reports_created_alerts_and_never_duplicates_them(self):
        client = self.make_alert_client("زبون التكرار", responsible=self.owner)
        overdue = self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )

        first = services.refresh_office(self.tenant, day=DAY)

        # صاحبُ المكتب هو المسؤول: أحمرُ لصاحبَي المكتب، وأصفرُ له وحده.
        self.assertEqual(first["created_alerts"], 3)
        self.assertEqual(OfficeAlert.objects.count(), 3)

        second = services.refresh_office(self.tenant, day=DAY)

        self.assertEqual(second["created_alerts"], 0)
        self.assertEqual(OfficeAlert.objects.count(), 3)

        # ويومٌ لاحق: الشارةُ تقول الحال، والتنبيهُ لا يُولَّد ثانيةً للمرجع نفسه.
        later = services.refresh_office(self.tenant, day=DAY + datetime.timedelta(days=1))

        self.assertEqual(later["created_alerts"], 0)
        self.assertEqual(
            OfficeAlert.objects.filter(ref_key=f"obligation:{overdue.pk}").count(),
            2,
        )
        self.assertEqual(
            OfficeAlert.objects
            .filter(ref_key=f"obligation:{overdue.pk}")
            .values("recipient_id").distinct().count(),
            2,
            "التنبيهُ تكرّر لمستلِمٍ نفسه في يومٍ لاحق — الفرادةُ على (مستلِم، نوع، مرجع)",
        )

    def test_a_new_overdue_obligation_still_gets_its_alert_on_a_later_day(self):
        client = self.make_alert_client("زبون الجديد", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        services.refresh_office(self.tenant, day=DAY)
        fresh = self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=1),
            internal=DAY - datetime.timedelta(days=8),
            period_start=FEB_START,
            period_end=FEB_END,
        )

        counts = services.refresh_office(self.tenant, day=DAY + datetime.timedelta(days=1))

        self.assertEqual(counts["created_alerts"], 3)
        self.assertTrue(
            OfficeAlert.objects.filter(ref_key=f"obligation:{fresh.pk}").exists(),
        )


class ReadTimeExclusionTest(AlertsTestCase):
    """المحسومُ يُسقط من الجرس عند القراءة — والصفُّ يبقى في القاعدة."""

    def test_submitting_empties_the_bell_without_deleting_the_rows(self):
        client = self.make_alert_client("زبون محسوم", responsible=self.owner)
        obligation = self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        self.generate()
        # تنبيهان لصاحب المكتب: الأحمرُ (هو والمالك الثاني) والأصفرُ له وحده.
        self.assertEqual(
            len(services.alerts_payload(self.tenant, user=self.owner)["rows"]), 2,
        )

        services.submit_obligation(obligation, actor=self.owner)

        payload = services.alerts_payload(self.tenant, user=self.owner)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["unseen"], 0)
        self.assertEqual(OfficeAlert.objects.count(), 3, "المحسومُ يُستبعد لا يُحذف")

    def test_not_required_empties_the_internal_alert_and_reopen_restores_it(self):
        client = self.make_alert_client("زبون مش لازم", responsible=self.owner)
        obligation = self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=20),
            internal=DAY - datetime.timedelta(days=5),
        )
        self.generate()
        self.assertEqual(
            len(services.alerts_payload(self.tenant, user=self.owner)["rows"]), 1,
        )

        services.mark_obligation_not_required(obligation, actor=self.owner)
        self.assertEqual(services.alerts_payload(self.tenant, user=self.owner)["rows"], [])

        # و«رجّعها» تُعيده: التنبيهُ لم يُحذف، فالحالُ وحدها تغيّرت.
        services.reopen_obligation(obligation, actor=self.owner)
        self.assertEqual(
            len(services.alerts_payload(self.tenant, user=self.owner)["rows"]), 1,
        )

    def test_a_task_keeps_its_alert_while_another_obligation_of_it_is_pending(self):
        client = self.make_alert_client("زبون التزامين", responsible=self.owner)
        first = self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=20),
            internal=DAY - datetime.timedelta(days=5),
        )
        second = self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=25),
            internal=DAY - datetime.timedelta(days=5),
            task=first.task,
            period_start=JAN_START,
            period_end=JAN_END + datetime.timedelta(days=1),
        )
        self.generate()
        # تنبيهٌ واحدٌ للشغلة الواحدة — التزامان فيها لا يضاعفانه.
        self.assertEqual(
            len(services.alerts_payload(self.tenant, user=self.owner)["rows"]), 1,
        )

        services.submit_obligation(first, actor=self.owner)

        self.assertEqual(
            len(services.alerts_payload(self.tenant, user=self.owner)["rows"]),
            1,
            "الشغلةُ فيها التزامٌ منتظرٌ بعد — فتنبيهُها قائم",
        )

        services.submit_obligation(second, actor=self.owner)

        self.assertEqual(services.alerts_payload(self.tenant, user=self.owner)["rows"], [])


class SeenTest(AlertsTestCase):
    """«شفته» يُنقص العدّاد، و«شفتهم كلهم» يُصفّره — لكل مستلِمٍ على حِدة."""

    def setUp(self):
        self.client_row = self.make_alert_client("زبون الشوفة", responsible=self.owner)
        self.first = self.add_row(
            self.client_row,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        self.second = self.add_row(
            self.client_row,
            actual=DAY - datetime.timedelta(days=2),
            internal=DAY - datetime.timedelta(days=9),
            period_start=FEB_START,
            period_end=FEB_END,
        )
        self.generate()

    def test_seen_lowers_the_counter_and_seen_all_zeroes_it(self):
        payload = services.alerts_payload(self.tenant, user=self.owner)
        self.assertEqual(payload["unseen"], 4)

        services.mark_alert_seen(
            OfficeAlert.objects.filter(recipient=self.owner).first(), user=self.owner,
        )

        self.assertEqual(
            services.alerts_payload(self.tenant, user=self.owner)["unseen"], 3,
        )

        marked = services.mark_all_alerts_seen(self.tenant, user=self.owner)

        self.assertEqual(marked, 3)
        payload = services.alerts_payload(self.tenant, user=self.owner)
        self.assertEqual(payload["unseen"], 0)
        self.assertTrue(all(row["seen"] for row in payload["rows"]))
        self.assertEqual(
            services.mark_all_alerts_seen(self.tenant, user=self.owner), 0,
        )

    def test_marking_one_member_does_not_touch_another_members_alerts(self):
        services.mark_all_alerts_seen(self.tenant, user=self.owner)

        payload = services.alerts_payload(self.tenant, user=self.owner_two)

        self.assertEqual(payload["unseen"], 2)
        self.assertTrue(all(not row["seen"] for row in payload["rows"]))

    def test_the_payload_row_carries_the_agreed_keys(self):
        row = services.alerts_payload(self.tenant, user=self.owner)["rows"][0]

        self.assertEqual(
            set(row),
            {
                "id", "kind", "kind_label", "badge", "opens", "message", "client",
                "task_id", "obligation_id", "day", "seen", "created_at",
            },
        )
        self.assertEqual(set(row["client"]), {"id", "name"})
        self.assertIn(
            row["kind_label"],
            ("شغلة تجاوزت موعدها الداخلي", "التزام تجاوز موعده الرسمي ولم يُقدَّم"),
        )
        self.assertIn(row["badge"], ("late", "late_internal"))
        self.assertEqual(row["day"], DAY.isoformat())


class CountersAndFiltersTest(AlertsTestCase):
    """العدّاداتُ الأربعة قبل الفلتر، ونافذةُ `week` مستقلّةٌ عن الشارة."""

    def setUp(self):
        red = self.make_alert_client("زبون أحمر", responsible=self.owner)
        self.red = self.add_row(
            red,
            actual=DAY - datetime.timedelta(days=2),
            internal=DAY - datetime.timedelta(days=9),
        )
        yellow = self.make_alert_client("زبون أصفر", responsible=self.owner)
        self.yellow = self.add_row(
            yellow,
            actual=DAY + datetime.timedelta(days=20),
            internal=DAY - datetime.timedelta(days=2),
        )
        near = self.make_alert_client("زبون قريب", responsible=self.owner)
        self.near = self.add_row(
            near,
            actual=DAY + datetime.timedelta(days=3),
            internal=DAY + datetime.timedelta(days=3),
        )
        # أصفرُ داخل نافذة «قريب»: شارتُه صفراء (الأولوية) لكنّ عدّادَ `week`
        # يعدّه — النافذةُ على `actual_deadline` لا على الشارة (#276).
        both = self.make_alert_client("زبون أصفر قريب", responsible=self.owner)
        self.both = self.add_row(
            both,
            actual=DAY + datetime.timedelta(days=4),
            internal=DAY - datetime.timedelta(days=1),
        )

    def rows(self, filter=""):
        return services.today_payload(
            self.tenant, user=self.owner, day=DAY, filter=filter,
        )

    def test_the_five_counters_are_computed_before_the_filter(self):
        payload = self.rows()

        self.assertEqual(
            payload["counters"],
            # #278: خامسةُ العدّادات — ولا صفوفَ أوراقٍ في هذه المكتبة.
            {"late": 1, "late_internal": 2, "week": 2, "missing_docs": 0, "all": 4},
        )
        self.assertEqual(len(payload["rows"]), 4)

    def test_the_week_window_is_independent_of_the_badge(self):
        week = self.rows(filter="week")

        self.assertEqual(
            {row["client"]["id"] for row in week["rows"]},
            {self.near.client_id, self.both.client_id},
            "النافذةُ تُعدّ الصفَّ الأصفرَ الذي يقع موعدُه الفعليُّ داخل الأسبوع",
        )
        badges = {
            row["client"]["id"]: [badge["key"] for badge in row["badges"]]
            for row in week["rows"]
        }
        self.assertEqual(
            badges[self.both.client_id], ["late_internal"],
            "دخولُ النافذة لا يغيّر الشارة — شارةٌ واحدةٌ بالأولوية",
        )
        self.assertEqual(badges[self.near.client_id], ["near"])

    def test_the_red_and_yellow_filters_are_disjoint(self):
        red = self.rows(filter="late")
        yellow = self.rows(filter="late_internal")

        self.assertEqual([row["client"]["id"] for row in red["rows"]], [self.red.client_id])
        self.assertEqual(
            {row["client"]["id"] for row in yellow["rows"]},
            {self.yellow.client_id, self.both.client_id},
        )
        self.assertEqual(yellow["counters"], red["counters"])

    def test_an_unknown_filter_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            self.rows(filter="someday")


class CostTest(AlertsTestCase):
    """عددُ الاستعلامات لا يكبر بعدد الالتزامات المتأخّرة."""

    def build_office(self, name, overdue):
        owner = User.objects.create_user(username=f"al_cost_{name}", password="x")
        tenant = create_company(f"مكتب {name}", owner, template="accounting_office")
        invalidate_module_cache(tenant.pk)
        ready_office(tenant, "IL")
        catalog(tenant)
        client = office_client_without_periods(tenant, f"زبون {name}", responsible=owner)
        row = client.services.get()
        rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )
        for index in range(overdue):
            start = datetime.date(2025, 1, 1) + datetime.timedelta(days=30 * index)
            end = start + datetime.timedelta(days=27)
            task = PeriodTask.objects.create(
                tenant=tenant, client=client, client_service=row,
                period_start=start, period_end=end,
                internal_deadline=DAY - datetime.timedelta(days=10 + index),
            )
            Obligation.objects.create(
                tenant=tenant, client=client, client_service=row, task=task,
                rule=rule, rule_code=rule.code, name=rule.name,
                period_start=start, period_end=end,
                legal_date=DAY - datetime.timedelta(days=3),
                official_date=DAY - datetime.timedelta(days=3),
                actual_deadline=DAY - datetime.timedelta(days=3),
                internal_deadline=DAY - datetime.timedelta(days=10 + index),
            )
        return tenant

    def test_the_queries_do_not_grow_with_the_overdue_rows(self):
        one = self.build_office("one", 1)
        five = self.build_office("five", 5)

        with CaptureQueriesContext(connection) as few:
            self.assertEqual(self.generate(one), 2)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self.generate(five), 10)

        self.assertEqual(
            len(many.captured_queries), len(few.captured_queries),
            "عددُ استعلامات التوليد كبر بعدد الالتزامات",
        )


class CommandTest(AlertsTestCase):
    """الأمرُ يطبع عددَ التنبيهات التي أنشأها في سطره."""

    def test_the_command_prints_the_created_alerts(self):
        client = self.make_alert_client("زبون الأمر", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=1),
            internal=DAY - datetime.timedelta(days=5),
        )
        out = io.StringIO()

        call_command(
            "refresh_accounting_offices", "--day", DAY.isoformat(), stdout=out,
        )

        line = out.getvalue()
        self.assertIn("تنبيهات 3", line)
        self.assertIn(DAY.isoformat(), line)


class IsolationTest(AlertsTestCase):
    """تنبيهُ مكتبٍ آخر لا يظهر في جرس هذا المكتب — والمستلِمُ نفسُه في المكتبين.

    **الاختبارُ كان يمرّ بلا فلتر `tenant`**: المستلِمُ في المكتب الآخر كان
    مستخدماً مختلفاً، فيكفي `recipient` للفصل. هنا صاحبُ المكتب عضوٌ في المكتبين
    ومستلِمُ التنبيهَين، فلا يفصل بينهما إلا شركةُ الصفّ.
    """

    def test_another_office_alerts_never_reach_this_bell(self):
        outside_owner = User.objects.create_user(username="al_outside", password="x")
        outside = create_company(
            "مكتب الجرس الآخر", outside_owner, template="accounting_office",
        )
        invalidate_module_cache(outside.pk)
        ready_office(outside, "IL")
        catalog(outside)
        UserCompanyMembership.objects.create(
            user=self.owner, tenant=outside, role="accountant",
        )
        client = office_client_without_periods(
            outside, "زبون المكتب الآخر", responsible=self.owner,
        )
        row = client.services.get()
        rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )
        task = PeriodTask.objects.create(
            tenant=outside, client=client, client_service=row,
            period_start=JAN_START, period_end=JAN_END,
            internal_deadline=DAY - datetime.timedelta(days=9),
        )
        Obligation.objects.create(
            tenant=outside, client=client, client_service=row, task=task,
            rule=rule, rule_code=rule.code, name=rule.name,
            period_start=JAN_START, period_end=JAN_END,
            legal_date=DAY - datetime.timedelta(days=3),
            official_date=DAY - datetime.timedelta(days=3),
            actual_deadline=DAY - datetime.timedelta(days=3),
            internal_deadline=DAY - datetime.timedelta(days=9),
        )

        self.generate(outside)
        self.assertEqual(
            OfficeAlert.objects.filter(
                tenant=outside, recipient=self.owner,
            ).count(),
            2,
            "المستلِمُ نفسُه نُبِّه في المكتب الآخر — وإلا فالاختبارُ لا يقيس العزل",
        )
        # وتنبيهٌ **بلا زبون** للمستخدم نفسِه في المكتب الآخر: شرطُ `client__isnull`
        # يمرّره (نوعٌ لاحقٌ لا يُسقطه المحسوم)، فلا يفصله عن هذا الجرس إلا `tenant`.
        foreign = OfficeAlert.objects.create(
            tenant=outside,
            recipient=self.owner,
            kind="future_kind",
            ref_key="future:1",
            message="نوعٌ لاحقٌ بلا زبون",
            day=DAY,
        )

        payload = services.alerts_payload(self.tenant, user=self.owner)

        self.assertEqual(
            payload["rows"], [],
            "تنبيهُ مكتبٍ آخر ظهر في هذا الجرس — فشرطُ `tenant` غائب",
        )
        self.assertEqual(payload["unseen"], 0)
        self.assertEqual(
            services.mark_all_alerts_seen(self.tenant, user=self.owner), 0,
        )
        foreign.refresh_from_db()
        self.assertIsNone(foreign.seen_at, "«شفتهم كلهم» كتب في مكتبٍ آخر")
        self.assertEqual(
            OfficeAlert.objects.filter(tenant=outside, seen_at__isnull=True).count(), 4,
            "«شفتهم كلهم» في المكتب الآخر لم يُمسّ — ولا تَدخُل تنبيهاتُه عدّادَ هنا",
        )


class NoAmountTest(AlertsTestCase):
    """التنبيهُ لا يحمل مفتاحَ مبلغٍ ولا حقلاً عشرياً — فلا مسّ لحارس المبالغ."""

    def test_the_alert_carries_no_amount_key(self):
        client = self.make_alert_client("زبون بلا مبلغ", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=2),
            internal=DAY - datetime.timedelta(days=9),
        )
        self.generate()

        row = services.alerts_payload(self.tenant, user=self.owner)["rows"][0]

        self.assertEqual(set(row) & services.AMOUNT_KEYS, set())
        self.assertEqual(
            [
                field.name for field in OfficeAlert._meta.get_fields()
                if getattr(field, "get_internal_type", lambda: "")() == "DecimalField"
            ],
            [],
        )


class VisibilityTest(AlertsTestCase):
    """التنبيهُ يتبع رؤية الزبون: ما لم يعد يراه العضو لا يظهر في جرسه."""

    def test_an_alert_leaves_the_bell_when_its_client_leaves_the_visibility(self):
        client = self.make_alert_client("زبون يُحوَّل", responsible=self.accountant)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        self.generate()
        self.assertEqual(
            len(services.alerts_payload(self.tenant, user=self.accountant)["rows"]), 2,
        )

        # الزبونُ صار لغير المحاسب ولا شغلةَ محوَّلةً له ⇒ لا يراه.
        client.responsible = self.owner_two
        client.save(update_fields=["responsible"])

        payload = services.alerts_payload(self.tenant, user=self.accountant)

        self.assertEqual(
            payload["rows"], [],
            "تنبيهُ زبونٍ لم يعد يراه العضو ظهر في جرسه",
        )
        self.assertEqual(payload["unseen"], 0)
        self.assertEqual(
            OfficeAlert.objects.filter(recipient=self.accountant).count(), 2,
            "الاستبعادُ عند القراءة لا بالحذف",
        )


class SeenScopeTest(AlertsTestCase):
    """«شفتهم كلهم» يكتب على المعروض وحده — فالمحسومُ يعود غيرَ مقروء إن رجع."""

    def test_seen_all_does_not_mark_a_resolved_alert(self):
        client = self.make_alert_client("زبون يُرجّع", responsible=self.owner)
        obligation = self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        self.generate()
        services.mark_obligation_not_required(obligation, actor=self.owner)
        self.assertEqual(services.alerts_payload(self.tenant, user=self.owner)["rows"], [])

        self.assertEqual(services.mark_all_alerts_seen(self.tenant, user=self.owner), 0)

        services.reopen_obligation(obligation, actor=self.owner)
        payload = services.alerts_payload(self.tenant, user=self.owner)

        self.assertEqual(
            payload["unseen"], 2,
            "«شفتهم كلهم» كتب على تنبيهٍ محسوم فعاد مقروءاً",
        )
        self.assertTrue(all(not row["seen"] for row in payload["rows"]))

    def test_seen_all_never_updates_through_a_subquery_on_its_own_table(self):
        """MySQL يرفض `UPDATE t … WHERE id IN (SELECT … FROM t)` (خطأ 1093).

        SQLite يقبلها فتمرّ الاختبارات الخضراء ويسقط الإنتاج — فيُفحص شكلُ
        الاستعلام نفسِه: لا `UPDATE` يحمل `SELECT` من جدول التنبيهات.
        """
        client = self.make_alert_client("زبون 1093", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        self.generate()

        with CaptureQueriesContext(connection) as captured:
            marked = services.mark_all_alerts_seen(self.tenant, user=self.owner)

        self.assertEqual(marked, 2)
        updates = [
            query["sql"] for query in captured.captured_queries
            if query["sql"].lstrip().upper().startswith("UPDATE")
        ]
        self.assertTrue(updates, "لم يُكتب `UPDATE` — الاختبارُ لا يقيس شيئاً")
        for sql in updates:
            self.assertNotRegex(
                sql.lower(),
                r"(?s)select\b.*\bfrom\s+[\"`]?accounting_office_officealert",
                "UPDATE بمجموعةٍ فرعيةٍ على الجدول نفسه — MySQL 1093",
            )


class ResolvedBadgeTest(AlertsTestCase):
    """الشارةُ تُشتقّ من الحالة أيضاً — والملفُّ يعرض كلَّ الحالات لا المنتظِرَ وحده."""

    def test_a_resolved_late_row_carries_no_badge_in_the_client_file(self):
        client = self.make_alert_client("زبون محسوم", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=4),
            internal=DAY - datetime.timedelta(days=9),
            status=Obligation.STATUS_SUBMITTED,
        )
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=4),
            internal=DAY - datetime.timedelta(days=9),
            status=Obligation.STATUS_NOT_REQUIRED,
            period_start=JAN_START,
            period_end=JAN_END + datetime.timedelta(days=31),
        )

        payload = services.client_obligations_payload(client, user=self.owner, day=DAY)
        rows = [
            obligation
            for task in payload["tasks"]
            for obligation in task["obligations"]
        ]

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row["badges"] for row in rows], [[], []],
            "صفٌّ مُقدَّمٌ أو مُستثنى متأخّرٌ حمل شارةَ تأخير",
        )


class ExtensionTest(AlertsTestCase):
    """التمديدُ الإلكترونيّ داخل آخر موعدٍ فعليّ — لا أحمرَ ولا تنبيهَ رسميّ قبله."""

    def test_the_electronic_extension_is_not_late(self):
        client = self.make_alert_client("زبون التمديد", responsible=self.owner)
        obligation = self.add_row(
            client,
            actual=DAY + datetime.timedelta(days=3),
            internal=DAY + datetime.timedelta(days=1),
        )
        # الموعدُ الرسميُّ مضى والفعليُّ (بالتمديد) لم يبلغ بعد.
        obligation.official_date = DAY - datetime.timedelta(days=2)
        obligation.save(update_fields=["official_date"])

        row = services.today_payload(self.tenant, user=self.owner, day=DAY)["rows"][0]

        self.assertEqual([badge["key"] for badge in row["badges"]], ["near"])
        self.assertEqual(self.generate(), 0, "تنبيهٌ على التزامٍ داخل تمديده")
        self.assertFalse(
            OfficeAlert.objects.filter(kind=OfficeAlert.KIND_OBLIGATION_LATE).exists(),
        )

        # ويومُ آخر موعدٍ فعليٍّ نفسِه ليس تأخيراً بعد (`< day` لا `<=`).
        on_deadline = services.today_payload(
            self.tenant, user=self.owner, day=obligation.actual_deadline,
        )["rows"][0]
        self.assertNotIn("late", [badge["key"] for badge in on_deadline["badges"]])


class AlertBadgeFieldTest(AlertsTestCase):
    """`badge` مفتاحُ الشارة يُرسله الخادم من خريطة الأنواع — لا معرفةَ أنواعٍ في الواجهة."""

    def test_the_row_carries_the_badge_key_of_its_kind(self):
        client = self.make_alert_client("زبون الشارة", responsible=self.owner)
        self.add_row(
            client,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY - datetime.timedelta(days=10),
        )
        self.generate()

        rows = services.alerts_payload(self.tenant, user=self.owner)["rows"]
        mapping = {
            row["kind"]: row["badge"] for row in rows
        }

        self.assertEqual(
            mapping,
            {
                OfficeAlert.KIND_OBLIGATION_LATE: "late",
                OfficeAlert.KIND_TASK_LATE_INTERNAL: "late_internal",
            },
        )

    def test_an_unknown_kind_gets_a_neutral_badge_key(self):
        OfficeAlert.objects.create(
            tenant=self.tenant,
            recipient=self.owner,
            kind="future_kind",
            ref_key="future:1",
            message="نوعٌ لم تعرفه الشارة بعد",
            day=DAY,
        )

        row = services.alerts_payload(self.tenant, user=self.owner)["rows"][0]

        self.assertEqual(row["badge"], "")
