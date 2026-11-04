"""تعديل المكتب على اللائحة والتمديد والتزامات المكتب والأحداث — #277.

**ما يثبتها هذا الملف:**

1. **تعديلُ المكتب سجلٌّ إلحاقيّ**: صفٌّ جديد لكل تعديل، والساري أحدثُ صفّ
   (`-created_at, -id`)، و«رجّع للمنصة» صفٌّ `cleared=True` — فلا صفَّ يُعدَّل.
2. **إعادةُ الحساب دالّةٌ واحدة**: تعديلُ سطرٍ يُعيد حساب المنتظِر و«مش لازم»
   **دون المقدَّم**، ويكتب `ObligationDateChange` لما تغيّر فعلاً، ويحمل
   `platform_official_date` حين يختلف موعدُ المكتب عن موعد المنصة.
3. **التمديد يحرّك الأحمر**: `due_date = extended_to or actual_deadline` وحده
   يقرؤه الأحمرُ ونافذةُ `week` وتنبيهُ `obligation_late` — والأصفرُ يبقى على
   `task.internal_deadline`.
4. **تحديثُ المنصة = نسخةٌ أحدث**: السطرُ غيرُ المعدَّل يتبع الجديد، والمعدَّلُ
   يبقى مع تنبيه «تُبقي تاريخك أم تأخذ الجديد؟»، والمقدَّمُ لا يُمسّ.
5. **التزامُ المكتب** يُولَّد كالرسميّ بعلامة «من المكتب»، ويُعطَّل فيوقف الجديد.
6. **الحدث** يُولّد التزامه من سطر `days_after_event`: اقتطاعٌ بتاريخ X ⇒ X+30.
"""
import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounting_office import services
from accounting_office.models import (
    CADENCE_EVENT,
    EVENT_KIND_WITHHOLDING,
    FREQUENCY_MONTHLY,
    RULE_KIND_DAYS_AFTER_EVENT,
    ClientEvent,
    DeadlineRule,
    DeadlineSchedule,
    Obligation,
    ObligationDateChange,
    OfficeAlert,
    OfficeCustomRule,
    OfficeRuleOverride,
    PeriodTask,
)
from accounting_office.tests.test_obligations import (
    APR_FIRST,
    FEB_END,
    FEB_FIRST,
    JAN_END,
    JAN_START,
    MAR_END,
    OfficeTestCase,
    ready_office,
)

#: هجرةُ بيانات اللائحة (#277) — تُستدعى دالّتُها كما هي، ويُختبَر عكسُها.
SCHEDULES_V2_MIGRATION = "accounting_office.migrations.0007_office_rule_override"

#: يومُ «صار حدث»: اقتطاعٌ في منتصف شباط، فالتزامُه بعد ثلاثين يوماً.
EVENT_DAY = datetime.date(2026, 2, 10)


def migration():
    return importlib.import_module(SCHEDULES_V2_MIGRATION)


def seed_event_schedules():
    """بياناتُ هجرة 0007 كما تُطبَّق في الإنتاج — الهجراتُ معطَّلةٌ في الاختبار."""
    migration().seed_event_schedules(django_apps, None)


def platform_rule(system, year, code, version=None):
    """سطرُ اللائحة — و`version` يُثبَّت حيث تعددت النسخ (فلسطين لها v2)."""
    query = DeadlineRule.objects.filter(
        schedule__tax_system=system, schedule__year=year, code=code,
    )
    if version is not None:
        query = query.filter(schedule__version=version)
    return query.order_by("schedule__version").first()


def publish_new_version(system, year, *, rule_days=None, drop=(), cadence=None):
    """**تحديث المنصة**: نسخةٌ أحدثُ تنسخ الأسطر وتُعدّل ما يطلبه الاختبار.

    النسخةُ القائمة لا تُعدَّل — التصحيحُ يُضاف بـ`version` أعلى، وهذا ما يقرؤه
    `schedule_for` فيلتقطه التحديثُ وحده.
    """
    current, _estimated = services.schedule_for(system, year)
    new = DeadlineSchedule.objects.create(
        tax_system=system,
        year=year,
        version=current.version + 1,
        source_url=current.source_url,
        published_on=datetime.date(2026, 11, 5),
        rest_day_policy=current.rest_day_policy,
        authority_closed_days=list(current.authority_closed_days),
        note="v2 للاختبار",
    )
    for rule in current.rules.all():
        if rule.code in drop:
            continue
        DeadlineRule.objects.create(
            schedule=new,
            code=rule.code,
            name=rule.name,
            service_code=rule.service_code,
            cadence=(cadence or {}).get(rule.code, rule.cadence),
            rule_kind=rule.rule_kind,
            rule_day=(rule_days or {}).get(rule.code, rule.rule_day),
            rule_month=rule.rule_month,
            conditions=dict(rule.conditions),
            is_generated=rule.is_generated,
            electronic_extension_days=rule.electronic_extension_days,
            period_overrides=dict(rule.period_overrides),
            needs_review=rule.needs_review,
            source_url=rule.source_url,
            position=rule.position,
            event_kind=rule.event_kind,
        )
    return new


def dates_of(obligation):
    return (
        obligation.legal_date,
        obligation.official_date,
        obligation.actual_deadline,
        obligation.internal_deadline,
    )


class OverrideTestCase(OfficeTestCase):
    """مكتبٌ إسرائيليٌّ بزبون ق.م شهريّ — التزامُه في كانون الثاني والموعدُ في شباط."""

    def setUp(self):
        self.client_row = self.make_client("زبون ق.م", vat_classification="authorized")
        self.add_service(self.client_row, "vat")

    def refresh_all(self, day=APR_FIRST):
        return services.refresh_office(self.tenant, day=day)

    def obligation(self, client=None, *, period_end=JAN_END, code="il_vat_periodic"):
        return Obligation.objects.get(
            client=client or self.client_row, rule_code=code, period_end=period_end,
        )

    def january(self):
        return self.obligation()

    def february(self):
        return self.obligation(period_end=FEB_END)

    def override(self, **kwargs):
        return services.set_rule_override(
            self.tenant,
            tax_system="IL",
            rule_code="il_vat_periodic",
            actor=self.owner,
            **kwargs,
        )


class RuleOverrideTest(OverrideTestCase):
    """تعديلُ المكتب على سطر: صفٌّ جديد، وإعادةُ حساب غير المقدَّم وحده."""

    def test_the_pending_and_not_required_move_but_the_submitted_never_does(self):
        self.refresh_all()
        january = self.january()
        february = self.february()
        march = self.obligation(period_end=MAR_END)
        services.mark_obligation_not_required(february, actor=self.owner)
        services.submit_obligation(march, actor=self.owner)
        saved_submitted = dates_of(march)
        saved_pending = dates_of(january)

        result = self.override(rule_day=20, note="تأجيل المكتب")

        january.refresh_from_db()
        february.refresh_from_db()
        march.refresh_from_db()
        self.assertEqual(result["changed_obligations"], 2)
        self.assertEqual(january.legal_date, datetime.date(2026, 2, 20))
        self.assertNotEqual(dates_of(january), saved_pending)
        self.assertEqual(february.legal_date, datetime.date(2026, 3, 20))
        self.assertEqual(
            dates_of(march), saved_submitted, "المقدَّم مُسّ بتعديل اللائحة",
        )
        self.assertEqual(
            ObligationDateChange.objects.filter(reason="office_override").count(), 2,
        )

    def test_the_platform_date_is_kept_beside_the_office_one(self):
        self.refresh_all()
        january = self.january()
        self.assertIsNone(january.platform_official_date)

        self.override(rule_day=20, note="تأجيل المكتب")

        january.refresh_from_db()
        february = self.february()
        # المنصة على يومها (15) بسياسة إسرائيل: 15/2/2026 أحدٌ لا عطلةَ فيه.
        self.assertEqual(january.platform_official_date, datetime.date(2026, 2, 15))
        self.assertNotEqual(february.official_date, february.platform_official_date)

    def test_an_override_ignores_the_platform_published_date(self):
        """قرارُ المكتب يغلب نشرةَ المنصة: `period_overrides` تُتجاهل حين يُعدَّل السطر."""
        self.refresh_all()
        self.override(rule_day=15, note="بلا تغييرٍ في اليوم")

        february = self.february()
        # المنصة تُزيح شباط 2026 إلى 26/3 بالنشرة؛ وتعديلُ المكتب يُسقطها فيبقى 15.
        self.assertEqual(february.legal_date, datetime.date(2026, 3, 15))
        self.assertEqual(february.official_date, datetime.date(2026, 3, 15))
        self.assertEqual(february.platform_official_date, datetime.date(2026, 3, 26))

    def test_clearing_returns_to_the_platform_date_and_nulls_the_copy(self):
        self.refresh_all()
        self.override(rule_day=15, note="بلا تغييرٍ في اليوم")
        before = dates_of(self.february())

        cleared = services.clear_rule_override(
            self.tenant, tax_system="IL", rule_code="il_vat_periodic", actor=self.owner,
        )

        self.assertEqual(cleared["changed_obligations"], 2)
        february = self.february()
        self.assertNotEqual(dates_of(february), before)
        self.assertEqual(february.official_date, datetime.date(2026, 3, 26))
        self.assertIsNone(february.platform_official_date)

    def test_the_log_is_append_only_and_the_active_row_is_the_last(self):
        self.override(rule_day=18, note="أول")
        self.override(rule_day=20, note="ثانٍ")
        services.clear_rule_override(
            self.tenant, tax_system="IL", rule_code="il_vat_periodic", actor=self.owner,
        )

        rows = OfficeRuleOverride.objects.filter(
            tenant=self.tenant, rule_code="il_vat_periodic",
        ).order_by("created_at", "id")
        self.assertEqual(rows.count(), 3)
        self.assertEqual([row.rule_day for row in rows], [18, 20, None])
        self.assertEqual([row.cleared for row in rows], [False, False, True])
        # «مَن وإمتى» لا يُفقدان: كلُّ صفٍّ يحمل فاعلَه ووقته.
        self.assertEqual({row.created_by for row in rows}, {self.owner})
        self.assertTrue(all(row.created_at is not None for row in rows))
        self.assertEqual(
            services.active_rule_overrides(self.tenant), {},
            "صفٌّ «رجّع للمنصة» بقي سارياً",
        )

    def test_the_estimated_threshold_warning_survives_a_recompute(self):
        """#277: التحذيرُ يُركَّب داخل المدخلات الواحدة، فلا تمحوه الإعادة."""
        client = self.make_client(
            "زبون السقف", vat_classification="authorized",
            annual_sales=Decimal("600000"),
        )
        self.add_service(client, "vat", starts_on=datetime.date(2027, 1, 1))
        self.refresh_all(datetime.date(2027, 4, 1))
        row = Obligation.objects.get(
            client=client, rule_code="il_vat_detailed",
            period_end=datetime.date(2027, 1, 31),
        )
        self.assertIn("تقديري: سقف 2026", row.warnings)

        services.set_rule_override(
            self.tenant, tax_system="IL", rule_code="il_vat_detailed",
            rule_day=25, note="تأجيل المكتب", actor=self.owner,
        )

        row.refresh_from_db()
        self.assertIn(
            "تقديري: سقف 2026", row.warnings,
            "الإعادة محت تحذيرَ السقف التقديري — وهو جزءٌ من نتيجة المحرّك",
        )
        self.assertEqual(row.legal_date, datetime.date(2027, 2, 25))

    def test_the_listing_marks_the_line_awaiting_a_decision(self):
        """#277: `awaiting_decision` يُحسب للسطر نفسه لا بمطابقة نصّ التنبيه."""
        self.refresh_all()
        rows = services.deadline_rules_payload("IL", tenant=self.tenant)["rules"]
        row = next(item for item in rows if item["code"] == "il_vat_periodic")
        self.assertEqual(row["rule_code"], "il_vat_periodic")
        self.assertFalse(row["awaiting_decision"])

        self.override(rule_day=25, note="تأجيل المكتب")
        publish_new_version("IL", 2026, rule_days={"il_vat_periodic": 18})
        self.refresh_all(datetime.date(2026, 4, 2))

        rows = services.deadline_rules_payload("IL", tenant=self.tenant)["rules"]
        row = next(item for item in rows if item["code"] == "il_vat_periodic")
        self.assertTrue(
            row["awaiting_decision"],
            "السطرُ ينتظر قراراً والحمولةُ لا تقولها",
        )

        services.keep_rule_override(
            self.tenant, tax_system="IL", rule_code="il_vat_periodic", actor=self.owner,
        )

        rows = services.deadline_rules_payload("IL", tenant=self.tenant)["rules"]
        row = next(item for item in rows if item["code"] == "il_vat_periodic")
        self.assertFalse(row["awaiting_decision"])

    def test_the_calendar_row_carries_the_platform_date(self):
        """#277: «المنصة: …» في التقويم قيمةٌ مثبتةٌ لا `None` دائماً."""
        self.refresh_all()
        self.override(rule_day=15, note="بلا تغييرٍ في اليوم")

        items = services.client_deadlines(
            self.client_row, start=datetime.date(2026, 3, 1), end=MAR_END,
        )
        row = next(
            item for item in items
            if item["code"] == "il_vat_periodic" and item["result"].period_end == FEB_END
        )
        self.assertEqual(
            services.calendar_row(row)["platform_official_date"],
            "2026-03-26",
            "تاريخُ المنصة لم يُحمل في سطر التقويم",
        )

    def test_the_override_applies_to_every_client_of_the_office(self):
        other = self.make_client("زبون ثانٍ", vat_classification="authorized")
        self.add_service(other, "vat")
        self.refresh_all()

        self.override(rule_day=20, note="لكل الزبائن")

        self.assertEqual(
            {
                row.legal_date
                for row in Obligation.objects.filter(
                    rule_code="il_vat_periodic", client=other,
                )
            },
            {
                datetime.date(2026, 2, 20), datetime.date(2026, 3, 20),
                datetime.date(2026, 4, 20),
            },
        )

    def test_the_override_recomputes_only_its_own_tax_system(self):
        """#277: تعديلُ سطرٍ في نظامٍ لا يمسّ التزاماً بالكود نفسه في النظام الآخر."""
        palestinian = self.make_client("زبون فلسطيني", vat_classification="licensed")
        services.set_client_setting(palestinian, "tax_system", "PS")
        self.add_service(palestinian, "vat")
        self.refresh_all()
        # النظامُ الآخر يحمل في نسخته السارية سطراً **بالكود نفسه** وللمكتب عليه التزام.
        ps_rule = services.schedule_for("PS", 2026)[0].rules.get(code="ps_vat_periodic")
        DeadlineRule.objects.filter(pk=ps_rule.pk).update(code="il_vat_periodic")
        Obligation.objects.filter(rule=ps_rule).update(rule_code="il_vat_periodic")
        other =Obligation.objects.get(client=palestinian, period_end=JAN_END)
        # تواريخُه المحفوظة لا تطابق ما يحسبه المحرّك: إعادةٌ تمسّه تكشف نفسها.
        Obligation.objects.filter(pk=other.pk).update(
            legal_date=datetime.date(2026, 2, 3),
            official_date=datetime.date(2026, 2, 3),
            actual_deadline=datetime.date(2026, 2, 3),
        )
        other.refresh_from_db()
        saved = (dates_of(other), other.updated_at)

        self.override(rule_day=20, note="تأجيل المكتب")

        other.refresh_from_db()
        self.assertEqual(
            (dates_of(other), other.updated_at), saved,
            "تعديلُ سطرٍ إسرائيليٍّ أعاد حسابَ التزامٍ فلسطينيٍّ بالكود نفسه",
        )
        self.assertFalse(
            ObligationDateChange.objects.filter(obligation=other).exists(),
        )
        self.assertEqual(self.january().legal_date, datetime.date(2026, 2, 20))

    def test_an_unknown_code_and_out_of_range_values_are_refused(self):
        for system, kwargs in (
            ("IL", {"rule_code": "no_such_rule"}),
            ("IL", {"rule_code": "il_vat_periodic", "rule_day": 32}),
            ("IL", {"rule_code": "il_vat_periodic", "rule_day": 0}),
            ("IL", {"rule_code": "il_vat_periodic", "electronic_extension_days": 61}),
            ("PS", {"rule_code": "ps_annual_return", "rule_month": 13}),
            ("JO", {"rule_code": "il_vat_periodic"}),
        ):
            with self.assertRaises(DjangoValidationError):
                services.set_rule_override(
                    self.tenant, tax_system=system, actor=self.owner, **kwargs,
                )

    def test_a_day_on_an_end_of_period_line_is_refused(self):
        """#277: «آخر يوم في الفترة» لا يومَ فيه — قبولُ اليوم كتابةٌ لا أثرَ لها."""
        with self.assertRaises(DjangoValidationError) as raised:
            services.set_rule_override(
                self.tenant, tax_system="PS", rule_code="ps_income_advances",
                rule_day=20, note="يوم لا يُقرأ", actor=self.owner,
            )
        self.assertIn("rule_day", raised.exception.message_dict)
        self.assertFalse(
            OfficeRuleOverride.objects.filter(
                tenant=self.tenant, rule_code="ps_income_advances",
            ).exists(),
        )

        # وأيامُ التمديد الإلكتروني وحدها تبقى قابلةً للتعديل على هذا السطر.
        result = services.set_rule_override(
            self.tenant, tax_system="PS", rule_code="ps_income_advances",
            electronic_extension_days=5, note="تمديد المكتب", actor=self.owner,
        )
        self.assertEqual(result["override"]["electronic_extension_days"], 5)

    def test_a_missing_note_is_refused(self):
        """#277: التعديلُ على مسؤوليّة المكتب — وبلا سببٍ مكتوبٍ لا يُقبل."""
        with self.assertRaises(DjangoValidationError) as raised:
            services.set_rule_override(
                self.tenant, tax_system="IL", rule_code="il_vat_periodic",
                rule_day=20, note="   ", actor=self.owner,
            )
        self.assertIn("note", str(raised.exception))

    def test_clear_and_keep_refuse_an_unknown_system(self):
        for call in (services.clear_rule_override, services.keep_rule_override):
            with self.assertRaises(DjangoValidationError) as raised:
                call(
                    self.tenant, tax_system="JO", rule_code="il_vat_periodic",
                    actor=self.owner,
                )
            self.assertIn(
                "system", str(raised.exception),
                "الرفضُ جاء من غياب السطر لا من نظامٍ مجهول",
            )

    def test_the_recompute_cost_does_not_grow_with_the_obligations(self):
        """الإعادةُ دفعةٌ واحدة: عددُ الاستعلامات ثابتٌ مهما كثرت الالتزامات."""
        self.refresh_all()
        with CaptureQueriesContext(connection) as few:
            self.override(rule_day=20, note="أول")
        few_count = len(few.captured_queries)

        for index in range(4):
            client = self.make_client(f"زبون {index}", vat_classification="authorized")
            self.add_service(client, "vat")
        services.refresh_office(self.tenant, day=APR_FIRST)
        self.assertEqual(Obligation.objects.count(), 15)

        with CaptureQueriesContext(connection) as many:
            self.override(rule_day=21, note="ثانٍ")

        self.assertGreaterEqual(few_count, 1)
        self.assertLessEqual(
            len(many.captured_queries), few_count + 2,
            "كلفةُ إعادة الحساب كبرت بعدد الالتزامات — لا بدّ من دفعةٍ واحدة",
        )


class PlatformUpdateTest(OverrideTestCase):
    """«التحديث» = نسخةٌ أحدث: غيرُ المعدَّل يتبعها، والمعدَّلُ يبقى، والمقدَّمُ لا يُمسّ."""

    def test_an_untouched_line_takes_the_new_version_and_raises_one_alert(self):
        self.refresh_all()
        january = self.january()
        february = self.february()
        march = self.obligation(period_end=MAR_END)
        services.mark_obligation_not_required(february, actor=self.owner)
        services.submit_obligation(march, actor=self.owner)
        submitted_dates = dates_of(march)

        new_version = publish_new_version("IL", 2026, rule_days={"il_vat_periodic": 20})
        self.refresh_all(datetime.date(2026, 4, 2))

        january.refresh_from_db()
        february.refresh_from_db()
        march.refresh_from_db()
        self.assertEqual(january.rule.schedule_id, new_version.pk)
        self.assertEqual(january.legal_date, datetime.date(2026, 2, 20))
        self.assertEqual(
            february.legal_date, datetime.date(2026, 3, 20),
            "«مش لازم هالفترة» غيرُ المقدَّم — يأخذ الجديد أيضاً",
        )
        self.assertNotEqual(march.rule.schedule_id, new_version.pk, "المقدَّم مُسّ")
        self.assertEqual(dates_of(march), submitted_dates)

        alert = OfficeAlert.objects.get(
            tenant=self.tenant, kind="schedule_dates_changed",
        )
        self.assertEqual(alert.ref_key, f"schedule:{new_version.pk}")
        self.assertIn("2", alert.message)
        self.assertIsNone(alert.client_id)
        self.assertEqual(alert.recipient, self.owner)

    def test_a_second_refresh_does_not_repeat_the_schedule_alert(self):
        client = self.make_client("زبون الرواتب", has_employees=True)
        self.add_service(client, "payroll")
        self.refresh_all(FEB_FIRST)
        publish_new_version("IL", 2026, rule_days={"il_withholding_102": 20})

        self.refresh_all(datetime.date(2026, 4, 2))
        self.refresh_all(datetime.date(2026, 4, 3))

        self.assertEqual(
            OfficeAlert.objects.filter(
                tenant=self.tenant, kind="schedule_dates_changed",
            ).count(),
            1,
            "تنبيهُ تغيّر اللائحة تكرّر بتشغيلٍ ثانٍ",
        )

    def test_a_line_that_left_the_new_version_only_warns(self):
        self.refresh_all()
        before = dates_of(self.january())
        publish_new_version("IL", 2026, drop={"il_vat_periodic"})

        self.refresh_all(datetime.date(2026, 4, 2))

        january = self.january()
        self.assertEqual(dates_of(january), before)
        self.assertTrue(
            any("لم يعد" in warning for warning in january.warnings),
            january.warnings,
        )
        self.assertFalse(
            OfficeAlert.objects.filter(kind="schedule_dates_changed").exists(),
            "تنبيهٌ على صفر التزامٍ متغيّر",
        )

    def test_the_missing_line_warning_survives_an_override_recompute(self):
        """#277: التحذيرُ يُكتب في التحديث، فلا تمحوه إعادةُ حسابٍ لاحقة."""
        self.refresh_all()
        publish_new_version("IL", 2026, drop={"il_vat_periodic"})
        self.refresh_all(datetime.date(2026, 4, 2))
        self.assertIn(
            services.PLATFORM_MISSING_LINE_WARNING, self.january().warnings,
        )

        self.override(rule_day=25, note="تأجيل المكتب")

        self.assertIn(
            services.PLATFORM_MISSING_LINE_WARNING, self.january().warnings,
            "إعادةُ الحساب محت تحذير «السطر لم يعد في لائحة المنصة»",
        )

    def test_the_missing_line_warning_goes_when_a_later_version_restores_the_line(self):
        self.refresh_all()
        returning = platform_rule("IL", 2026, "il_vat_periodic")
        publish_new_version("IL", 2026, drop={"il_vat_periodic"})
        self.refresh_all(datetime.date(2026, 4, 2))
        restored = publish_new_version("IL", 2026)
        returning.pk = None
        returning.schedule = restored
        returning.save()

        self.refresh_all(datetime.date(2026, 4, 3))

        self.assertNotIn(
            services.PLATFORM_MISSING_LINE_WARNING, self.january().warnings,
            "السطرُ عاد في نسخةٍ أحدث والتحذيرُ بقي",
        )

    def test_an_overridden_line_keeps_the_office_date_and_asks(self):
        self.refresh_all()
        self.override(rule_day=25, note="تأجيل المكتب")
        january = self.january()
        office_dates = dates_of(january)
        publish_new_version("IL", 2026, rule_days={"il_vat_periodic": 18})

        self.refresh_all(datetime.date(2026, 4, 2))

        january = self.january()
        self.assertEqual(dates_of(january), office_dates, "تاريخُ المكتب تبدّل بتحديث المنصة")
        override = services.active_rule_overrides(self.tenant)[("IL", "il_vat_periodic")]
        alert = OfficeAlert.objects.get(
            tenant=self.tenant, kind="override_platform_changed",
        )
        self.assertEqual(
            alert.ref_key, f"override:{override.pk}:schedule:{january.rule.schedule_id}",
        )
        self.assertIn("تُبقي", alert.message)
        self.assertEqual(services.alert_row(alert)["badge"], "late_internal")

    def test_keeping_my_date_drops_the_alert_and_clearing_takes_the_new_one(self):
        self.refresh_all()
        self.override(rule_day=25, note="تأجيل المكتب")
        new_version = publish_new_version("IL", 2026, rule_days={"il_vat_periodic": 18})
        self.refresh_all(datetime.date(2026, 4, 2))

        def prompt_alert():
            return any(
                row["kind"] == "override_platform_changed"
                for row in services.alerts_payload(
                    self.tenant, user=self.owner, day=datetime.date(2026, 4, 2),
                )["rows"]
            )

        self.assertTrue(prompt_alert(), "لا تنبيهَ «تُبقي تاريخك أم تأخذ الجديد؟»")

        services.keep_rule_override(
            self.tenant, tax_system="IL", rule_code="il_vat_periodic", actor=self.owner,
        )

        january = self.january()
        self.assertEqual(
            january.legal_date, datetime.date(2026, 2, 25), "تاريخ المكتب تبدّل",
        )
        active = services.active_rule_overrides(self.tenant)[("IL", "il_vat_periodic")]
        self.assertFalse(active.cleared)
        self.assertEqual(
            active.based_on["rule_day"], 18, "اللقطةُ لم تأخذ نسخة المنصة الجديدة",
        )
        self.assertFalse(
            prompt_alert(),
            "«أُبقي تاريخي» لم يُسقط تنبيه «تُبقي أم تأخذ الجديد»",
        )

        services.clear_rule_override(
            self.tenant, tax_system="IL", rule_code="il_vat_periodic", actor=self.owner,
        )
        january = self.january()
        self.assertEqual(january.legal_date, datetime.date(2026, 2, 18))
        self.assertEqual(january.rule.schedule_id, new_version.pk)

    def test_the_override_alert_appears_without_any_unsubmitted_obligation(self):
        """#277: التنبيهُ قرارُ مكتبٍ لا نتيجةَ نقلِ التزام، فيظهر ولو قُدِّم الكلّ."""
        self.refresh_all()
        services.close_prior_obligations(
            self.client_row, before=datetime.date(2026, 4, 1), actor=self.owner,
        )
        self.assertFalse(
            Obligation.objects.filter(
                client=self.client_row, status=Obligation.STATUS_PENDING,
            ).exists(),
        )
        self.override(rule_day=25, note="تأجيل المكتب")
        publish_new_version("IL", 2026, rule_days={"il_vat_periodic": 18})

        self.refresh_all(datetime.date(2026, 4, 2))

        self.assertEqual(
            OfficeAlert.objects.filter(
                tenant=self.tenant, kind="override_platform_changed",
            ).count(),
            1,
            "لا تنبيهَ «تُبقي تاريخك أم تأخذ الجديد؟» حين لا يبقى التزامٌ غيرُ مقدَّم",
        )
        # ولا تكرار بتشغيلٍ ثانٍ.
        self.refresh_all(datetime.date(2026, 4, 3))
        self.assertEqual(
            OfficeAlert.objects.filter(
                tenant=self.tenant, kind="override_platform_changed",
            ).count(),
            1,
        )


class ExtensionTest(OverrideTestCase):
    """التمديد: `due_date` وحده يقرؤه الأحمر، والأصفرُ يبقى على الموعد الداخليّ."""

    def test_extending_moves_the_red_badge_and_keeps_the_internal_one(self):
        self.refresh_all()
        january = self.january()
        red_day = january.actual_deadline + datetime.timedelta(days=1)
        self.assertEqual(
            services._badge_keys(january, red_day, task=january.task), ["late"],
        )

        until = january.actual_deadline + datetime.timedelta(days=40)
        services.extend_obligation(
            january, until=until, note="مدّدنا التقديم", actor=self.owner,
        )
        january.refresh_from_db()

        self.assertEqual(january.due_date, until)
        self.assertNotEqual(
            services._badge_keys(january, red_day, task=january.task), ["late"],
            "التمديد لم يُنقل الأحمر من الفعليّ إلى الممدَّد",
        )
        self.assertEqual(
            services._badge_keys(
                january, until + datetime.timedelta(days=1), task=january.task,
            ),
            ["late"],
        )
        # والأصفرُ يبقى على `task.internal_deadline` كما في #276.
        self.assertEqual(
            services._badge_keys(
                january, january.task.internal_deadline + datetime.timedelta(days=1),
                task=january.task,
            ),
            ["late_internal"],
        )

    def test_the_week_window_follows_the_extension(self):
        self.refresh_all()
        january = self.january()
        until = january.actual_deadline + datetime.timedelta(days=40)
        services.extend_obligation(
            january, until=until, note="مدّدنا", actor=self.owner,
        )
        january.refresh_from_db()

        self.assertFalse(
            services._in_near_window(january, until - datetime.timedelta(days=7)),
        )
        self.assertTrue(
            services._in_near_window(january, until - datetime.timedelta(days=6)),
        )

    def test_the_extension_is_refused_for_submitted_earlier_dates_and_empty_notes(self):
        self.refresh_all()
        january = self.january()
        max_day = january.actual_deadline
        later = max_day + datetime.timedelta(days=3)

        with self.assertRaises(DjangoValidationError) as raised:
            services.extend_obligation(
                january, until=max_day, note="نفس اليوم", actor=self.owner,
            )
        self.assertIn("الموعد الفعلي", str(raised.exception))

        with self.assertRaises(DjangoValidationError) as raised:
            services.extend_obligation(
                january, until=later, note="  ", actor=self.owner,
            )
        self.assertIn("note", str(raised.exception))

        services.mark_obligation_not_required(january, actor=self.owner)
        with self.assertRaises(DjangoValidationError) as raised:
            services.extend_obligation(
                january, until=later, note="مدّدنا", actor=self.owner,
            )
        self.assertIn("رجّعها", str(raised.exception))

        services.reopen_obligation(january, actor=self.owner)
        services.submit_obligation(january, actor=self.owner)
        with self.assertRaises(DjangoValidationError) as raised:
            services.extend_obligation(
                january, until=later, note="مدّدنا", actor=self.owner,
            )
        self.assertIn(services.SUBMITTED_LOCKED, str(raised.exception))

    def test_extending_drops_the_late_alert_from_the_bell(self):
        self.refresh_all()
        january = self.january()
        red_day = january.actual_deadline + datetime.timedelta(days=1)
        services.refresh_office(self.tenant, day=red_day)
        alert_key = f"obligation:{january.pk}"
        self.assertTrue(
            OfficeAlert.objects.filter(
                tenant=self.tenant, kind="obligation_late", ref_key=alert_key,
            ).exists(),
        )
        self.assertTrue(any(
            row["obligation_id"] == january.pk
            for row in services.alerts_payload(
                self.tenant, user=self.owner, day=red_day,
            )["rows"]
        ))

        services.extend_obligation(
            january,
            until=january.actual_deadline + datetime.timedelta(days=40),
            note="مدّدنا",
            actor=self.owner,
        )

        self.assertFalse(any(
            row["obligation_id"] == january.pk
            for row in services.alerts_payload(
                self.tenant, user=self.owner, day=red_day,
            )["rows"]
        ), "تنبيهُ التأخير بقي بعد التمديد")
        self.assertTrue(
            OfficeAlert.objects.filter(
                tenant=self.tenant, kind="obligation_late", ref_key=alert_key,
            ).exists(),
            "الصفُّ مُحي — والقراءةُ وحدها تُسقط المحسوم",
        )

    def test_clearing_returns_to_the_actual_date_and_logs_it(self):
        self.refresh_all()
        january = self.january()
        actual = january.actual_deadline
        services.extend_obligation(
            january,
            until=actual + datetime.timedelta(days=40),
            note="مدّدنا",
            actor=self.owner,
        )

        services.clear_obligation_extension(january, actor=self.owner)

        january.refresh_from_db()
        self.assertIsNone(january.extended_to)
        self.assertEqual(january.extension_note, "")
        self.assertEqual(january.due_date, actual)
        self.assertEqual(
            set(
                ObligationDateChange.objects
                .filter(obligation=january)
                .values_list("reason", flat=True),
            ),
            {"extension", "extension_cleared"},
        )


class OfficeCustomRuleTest(OverrideTestCase):
    """التزامُ المكتب: يُولَّد كالرسميّ، بعلامة «من المكتب»، ويُعطَّل ولا يُحذف."""

    def custom_rule(self, **kwargs):
        payload = {
            "tenant": self.tenant,
            "name": "تقرير داخلي شهري",
            "service": self.catalog["bookkeeping"],
            "cadence": FREQUENCY_MONTHLY,
            "rule_kind": "day_of_next_month",
            "rule_day": 10,
            "actor": self.owner,
        }
        payload.update(kwargs)
        return services.create_custom_rule(**payload)

    def test_the_office_obligation_appears_in_today_and_the_calendar_marked_office(self):
        rule = self.custom_rule()
        self.add_service(self.client_row, "bookkeeping")
        self.refresh_all()

        obligation = (
            Obligation.objects
            .filter(rule_code=rule.code)
            .order_by("period_end")
            .first()
        )
        self.assertEqual(obligation.origin, Obligation.ORIGIN_OFFICE)
        self.assertIsNone(obligation.rule_id)
        self.assertEqual(obligation.custom_rule_id, rule.pk)
        self.assertEqual(obligation.legal_date, datetime.date(2026, 2, 10))

        office_row = next(
            row for row in services.today_payload(
                self.tenant, user=self.owner, day=JAN_START,
            )["rows"]
            if row["origin"] == "office"
        )
        self.assertEqual(office_row["origin"], "office")
        self.assertEqual(office_row["origin_label"], "من المكتب")

        calendar = services.client_deadlines(
            self.client_row, start=JAN_START, end=MAR_END,
        )
        office_rows = [item for item in calendar if item["origin"] == "office"]
        self.assertTrue(office_rows)
        self.assertEqual(office_rows[0]["code"], rule.code)
        self.assertEqual(
            services.calendar_row(office_rows[0])["origin_label"], "من المكتب",
        )

    def test_a_new_office_rule_reaches_today_without_waiting_for_the_next_refresh(self):
        """#277: التوليدُ لا ينتظر الغد — `ensure_office_refreshed` لا تعيد يوماً مسجَّلاً."""
        self.add_service(self.client_row, "bookkeeping")

        rule = self.custom_rule(day=APR_FIRST)

        office_rows = [
            row for row in services.today_payload(
                self.tenant, user=self.owner, day=APR_FIRST,
            )["rows"]
            if row["origin"] == "office"
        ]
        self.assertEqual(len(office_rows), 3, "التزامُ المكتب لم يُولَّد عند إنشاء قاعدته")
        # وتشغيلٌ لاحقٌ لا يكرّر ما حُفظ.
        self.refresh_all()
        self.assertEqual(Obligation.objects.filter(rule_code=rule.code).count(), 3)

    def test_creating_a_rule_for_a_service_nobody_has_generates_nothing(self):
        rule = self.custom_rule(day=APR_FIRST)

        self.assertFalse(Obligation.objects.filter(rule_code=rule.code).exists())

    def test_reactivating_a_rule_generates_its_periods(self):
        self.add_service(self.client_row, "bookkeeping")
        rule = self.custom_rule(is_active=False, day=APR_FIRST)
        self.assertFalse(
            Obligation.objects.filter(rule_code=rule.code).exists(),
            "قاعدةٌ معطَّلةٌ ولّدت التزامات",
        )

        services.update_custom_rule(rule, is_active=True, actor=self.owner, day=APR_FIRST)

        self.assertEqual(Obligation.objects.filter(rule_code=rule.code).count(), 3)

    def test_disabling_stops_only_the_new_periods(self):
        rule = self.custom_rule()
        self.add_service(self.client_row, "bookkeeping")
        self.refresh_all()
        self.assertEqual(Obligation.objects.filter(rule_code=rule.code).count(), 3)

        services.update_custom_rule(rule, is_active=False, actor=self.owner)
        self.refresh_all(datetime.date(2026, 5, 2))

        self.assertEqual(
            Obligation.objects.filter(rule_code=rule.code).count(), 3,
            "التعطيل ولّد فتراتٍ جديدة",
        )
        self.assertTrue(OfficeCustomRule.objects.filter(pk=rule.pk).exists())

    def test_editing_an_office_rule_recomputes_only_the_unsubmitted(self):
        rule = self.custom_rule()
        self.add_service(self.client_row, "bookkeeping")
        self.refresh_all()
        submitted = (
            Obligation.objects.filter(rule_code=rule.code).order_by("period_end").first()
        )
        services.submit_obligation(submitted, actor=self.owner)
        saved = dates_of(submitted)

        services.update_custom_rule(rule, rule_day=25, actor=self.owner)

        submitted.refresh_from_db()
        self.assertEqual(dates_of(submitted), saved)
        pending = Obligation.objects.filter(
            rule_code=rule.code, status=Obligation.STATUS_PENDING,
        )
        self.assertEqual(pending.count(), 2)
        self.assertEqual(
            {row.legal_date for row in pending},
            {datetime.date(2026, 3, 25), datetime.date(2026, 4, 25)},
        )
        self.assertEqual(
            ObligationDateChange.objects.filter(reason="office_override").count(), 2,
        )


class ClientEventTest(OverrideTestCase):
    """«صار حدث»: الاقتطاع يولّد التزامه من سطر اللائحة — X + 30."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        seed_event_schedules()

    def setUp(self):
        super().setUp()
        ready_office(self.tenant, "PS")
        self.event_client = self.make_client(
            "زبون فلسطين", vat_classification="licensed", has_employees=True,
        )
        self.add_service(self.event_client, "payroll")

    def event(self, client=None, **kwargs):
        payload = {
            "kind": EVENT_KIND_WITHHOLDING,
            "occurred_on": EVENT_DAY,
            "note": "اقتطاع شباط",
            "actor": self.owner,
        }
        payload.update(kwargs)
        return services.record_client_event(client or self.event_client, **payload)

    def test_a_withholding_event_on_x_gives_a_deadline_on_x_plus_thirty(self):
        event, obligations = self.event()

        self.assertIsInstance(event, ClientEvent)
        self.assertEqual(len(obligations), 1)
        obligation = obligations[0]
        self.assertEqual(obligation.rule_code, "ps_withholding_event")
        self.assertEqual(
            obligation.legal_date, EVENT_DAY + datetime.timedelta(days=30),
        )
        self.assertEqual(obligation.origin, "event")
        self.assertEqual(obligation.event_id, event.pk)
        self.assertEqual(obligation.period_end, EVENT_DAY)
        self.assertEqual(obligation.period_start, EVENT_DAY)
        self.assertGreaterEqual(obligation.internal_deadline, EVENT_DAY)

    def test_editing_the_event_line_moves_an_existing_event_obligation(self):
        """#277: فترةُ الحدث ليست في أيّ مجرى، فالإعادةُ تفصله على أصلِه."""
        _event, obligations = self.event()
        saved = obligations[0]
        self.assertEqual(
            saved.legal_date, EVENT_DAY + datetime.timedelta(days=30),
        )

        services.set_rule_override(
            self.tenant, tax_system="PS", rule_code="ps_withholding_event",
            rule_day=45, note="تمدّد المكتب 45 يوماً", actor=self.owner,
        )

        saved.refresh_from_db()
        self.assertEqual(
            saved.legal_date, EVENT_DAY + datetime.timedelta(days=45),
            "تعديلُ سطر الحدث لم يحرّك التزامَ حدثٍ قائم",
        )
        self.assertTrue(
            ObligationDateChange.objects.filter(
                obligation=saved, reason="office_override",
            ).exists(),
            "التاريخُ تحرّك بلا صفٍّ في سجلّ التغيّر",
        )

    def test_a_disabled_kind_is_refused(self):
        services.set_office_setting(self.tenant, "enabled_event_kinds", [])

        with self.assertRaises(DjangoValidationError) as raised:
            self.event()
        self.assertIn("غير مفعّل", str(raised.exception))

    def test_a_client_without_the_payroll_service_is_refused(self):
        lonely = self.make_client("زبون بلا رواتب", vat_classification="licensed")

        with self.assertRaises(DjangoValidationError) as raised:
            services.record_client_event(
                lonely, kind=EVENT_KIND_WITHHOLDING, occurred_on=EVENT_DAY,
                note="", actor=self.owner,
            )
        self.assertIn("رواتب", str(raised.exception))

    def test_a_future_event_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            self.event(occurred_on=datetime.date(2099, 1, 1))

    def test_a_duplicate_event_on_the_same_day_makes_one_obligation(self):
        _first_event, first = self.event()
        _second_event, second = self.event(note="سجلٌّ ثانٍ")

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0].pk, second[0].pk)
        self.assertEqual(
            Obligation.objects.filter(rule_code="ps_withholding_event").count(), 1,
        )
        self.assertEqual(ClientEvent.objects.count(), 2, "السجلُّ يبقى لكل تسجيل")

    def test_israel_has_no_event_line(self):
        ready_office(self.tenant, "IL")
        client = self.make_client("زبون إسرائيل", vat_classification="authorized")

        with self.assertRaises(DjangoValidationError) as raised:
            services.record_client_event(
                client, kind=EVENT_KIND_WITHHOLDING, occurred_on=EVENT_DAY,
                note="", actor=self.owner,
            )
        self.assertIn("لا قاعدة", str(raised.exception))

    def test_event_lines_are_never_generated_periodically(self):
        self.refresh_all()
        self.assertFalse(
            Obligation.objects.filter(rule_code="ps_withholding_event").exists(),
            "سطرُ الحدث وُلّد دورياً — وهو يُولَّد من الحدث وحده",
        )


class EventSeedMigrationTest(OverrideTestCase):
    """هجرةُ 0007: فلسطين v2 فيها ستة أسطر، ونقلُها للالتزامات القائمة بلا أثر."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        seed_event_schedules()

    def test_palestine_version_two_copies_the_five_and_adds_the_event_line(self):
        for year in (2026, 2027):
            schedule = DeadlineSchedule.objects.get(
                tax_system="PS", year=year, version=2,
            )
            rows = list(schedule.rules.order_by("position", "id"))
            self.assertEqual(len(rows), 6)
            event_row = schedule.rules.get(code="ps_withholding_event")
            self.assertEqual(event_row.cadence, CADENCE_EVENT)
            self.assertEqual(event_row.rule_kind, RULE_KIND_DAYS_AFTER_EVENT)
            self.assertEqual(event_row.rule_day, 30)
            self.assertEqual(event_row.event_kind, EVENT_KIND_WITHHOLDING)
            self.assertEqual(event_row.service_code, "payroll")
            self.assertFalse(event_row.needs_review)
            self.assertEqual(event_row.electronic_extension_days, 0)
            self.assertEqual(event_row.conditions, {})
            self.assertEqual(event_row.source_url, rows[0].source_url)
            self.assertEqual(schedule.published_on, datetime.date(2026, 11, 4))
            self.assertIn("v2", schedule.note)

        self.assertEqual(
            DeadlineSchedule.objects.filter(tax_system="PS").count(), 4,
            "النسخُ القائمة عُدِّلت أو مُحيت — v2 تُضاف ولا تستبدل",
        )

    def test_the_existing_palestinian_obligations_move_to_v2_without_a_change(self):
        ready_office(self.tenant, "PS")
        client = self.make_client("زبون فلسطين", vat_classification="licensed")
        self.add_service(client, "vat")
        old = platform_rule("PS", 2026, "ps_vat_periodic", version=1)
        service_row = client.services.get()
        task = PeriodTask.objects.create(
            tenant=self.tenant, client=client,
            client_service=service_row,
            period_start=JAN_START, period_end=JAN_END,
            internal_deadline=datetime.date(2026, 2, 10),
        )
        saved = Obligation.objects.create(
            tenant=self.tenant, client=client,
            client_service=service_row, task=task, rule=old,
            rule_code=old.code, name=old.name,
            period_start=JAN_START, period_end=JAN_END,
            legal_date=datetime.date(2026, 2, 15),
            official_date=datetime.date(2026, 2, 15),
            actual_deadline=datetime.date(2026, 2, 15),
            internal_deadline=datetime.date(2026, 2, 10),
        )

        self.refresh_all(datetime.date(2026, 3, 2))

        saved.refresh_from_db()
        self.assertEqual(saved.rule.schedule.version, 2)
        self.assertEqual(
            dates_of(saved),
            (
                datetime.date(2026, 2, 15), datetime.date(2026, 2, 15),
                datetime.date(2026, 2, 15), datetime.date(2026, 2, 10),
            ),
        )
        self.assertFalse(
            OfficeAlert.objects.filter(kind="schedule_dates_changed").exists(),
            "تنبيهُ تغيّرٍ على صفر التزامٍ تغيّر تاريخه",
        )

    def test_the_reverse_deletes_only_the_versions_it_created(self):
        before = set(
            DeadlineSchedule.objects.filter(tax_system="PS", version=1)
            .values_list("year", flat=True),
        )
        migration().unseed_event_schedules(django_apps, None)

        self.assertFalse(
            DeadlineSchedule.objects.filter(tax_system="PS", version=2).exists(),
        )
        self.assertEqual(
            set(
                DeadlineSchedule.objects.filter(tax_system="PS", version=1)
                .values_list("year", flat=True),
            ),
            before,
        )
        self.assertEqual(DeadlineSchedule.objects.filter(tax_system="IL").count(), 2)
        # وعكسُ العكس يُعيدها — الهجرةُ أثرٌ لا يُعاد بيد.
        migration().seed_event_schedules(django_apps, None)
        self.assertEqual(
            DeadlineSchedule.objects.filter(tax_system="PS", version=2).count(), 2,
        )


class ClientEventsCostTest(OfficeTestCase):
    """حمولةُ الأحداث **استعلاماتٌ ثابتة**: لا استعلامَ لكل حدثٍ ولا لكل التزام."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        seed_event_schedules()

    def setUp(self):
        ready_office(self.tenant, "PS")
        self.event_client = self.make_client(
            "زبون الأحداث", vat_classification="licensed", has_employees=True,
        )
        self.add_service(self.event_client, "payroll")

    def add_event(self, day):
        return services.record_client_event(
            self.event_client, kind=EVENT_KIND_WITHHOLDING, occurred_on=day,
            note="", actor=self.owner,
        )

    def test_the_payload_cost_does_not_grow_with_the_events(self):
        self.add_event(datetime.date(2026, 2, 10))
        with CaptureQueriesContext(connection) as few:
            payload = services.client_events_payload(self.event_client, user=self.owner)
        self.assertEqual(len(payload["events"]), 1)

        for offset in range(2, 6):
            self.add_event(datetime.date(2026, 2, 10 + offset))
        self.assertEqual(ClientEvent.objects.count(), 5)

        with CaptureQueriesContext(connection) as many:
            payload = services.client_events_payload(self.event_client, user=self.owner)

        self.assertEqual(len(payload["events"]), 5)
        self.assertLessEqual(
            len(many.captured_queries), len(few.captured_queries),
            "كلفةُ حمولة الأحداث كبرت بعددها: "
            f"{len(few.captured_queries)} ⇒ {len(many.captured_queries)}",
        )
