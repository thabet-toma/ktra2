"""الرواتب — **متابعةُ الاستحقاق وحدها**: أين ومتى يستحقّ، ولا حسابَ راتبٍ هنا (#279).

**القواعد المحسومة التي يثبتها هذا الملف:**

1. **دوريةُ 102 وביטוח לאומי تتبع دورية خدمة الزبون** (`cadence="service"` في
   نسخة اللائحة): شهريةٌ ⇒ التزامٌ لكل شهر، وكلُّ شهرين ⇒ التزامٌ لكل شهرين
   (#264 «دورية 102 حسب ملفه»).
2. **نصف سنويّ دوريةٌ في اللائحة لا دوريةَ خدمة**: `126 חציוני` بتاريخه القانونيّ
   18 يوليو عن يناير–يونيو، و18 يناير عن يوليو–ديسمبر (والتقريرُ المقدَّمُ في
   يناير يشمل السنةَ كلَّها) — والزحزحةُ بعد ذلك وحدها.
3. **الكشفُ السنويُّ الفلسطيني «راجع»**: لا يومَ منشوراً في النصّ (§٤-ب من البحث)،
   فيُولَّد بـ30 نيسان موسوماً ولا يُقدَّم تاريخُه صامتاً على أنه مؤكَّد.
4. **الضمانُ الاجتماعي الفلسطيني لا يُولَّد** — `is_generated=False` تبقى.
5. **إعدادُ «الالتزامات التي تولّدها خدمة الرواتب»** يُطبَّق في **مكانٍ واحد**
   (`rule_applies`)، فيقرأ التوليدُ والتقويمُ قراراً واحداً — وأما «اليوم» فيقرأ
   الصفوف المحفوظة، وما وُلد قبل تقليص الإعداد يبقى حتى يحسمه المكتب.
6. **دوريةُ الرواتب شهريةٌ أو كل شهرين** — رفضٌ برسالةٍ واحدة من المسارَين.
7. **أوراقُ الرواتب بندين لا بند**: «كشف رواتب الشهر» مطلوب، و«تغييرات الموظفين»
   يبدأ «مش لازمة» فلا يُشعل «ناقصه أوراق».
8. **هجرة `0009`**: إسرائيل v2 وفلسطين v3 وأربعةُ بنود — إضافةٌ لا تعديل، وعكسُها
   يحذف ما أنشأته وحدها.
"""
import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase, TestCase

from accounting_office import deadlines, services, settings_registry
from accounting_office.models import (
    CLIENT_SERVICE_FREQUENCY_CHOICES,
    DEADLINE_CADENCE_CHOICES,
    DOCUMENT_STATUS_NOT_NEEDED,
    DOCUMENT_STATUS_REQUIRED,
    OFFICE_CUSTOM_RULE_CADENCE_CHOICES,
    ClientService,
    DeadlineSchedule,
    DocumentChecklistItem,
    Obligation,
    OfficeClient,
    OfficeDocumentItem,
    PlatformDocumentItem,
    TaxCard,
)
from accounting_office.tests.test_documents import seed_document_catalog
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency
from tenants.services import create_company

#: هجرةُ الرواتب — تُستدعى بدالّتيها كما هي (نمط `test_obligations.py`).
PAYROLL_MIGRATION = "accounting_office.migrations.0009_payroll_due_dates"
#: هجرةُ #277 — تسبقها في سلسلة الهجرات، فلسطينُ فيها v2 ⇒ نسخةُ #279 لها v3.
RULE_OVERRIDE_MIGRATION = "accounting_office.migrations.0007_office_rule_override"

JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
FEB_FIRST = datetime.date(2026, 2, 1)
FEB_END = datetime.date(2026, 2, 28)
MAR_FIRST = datetime.date(2026, 3, 1)
JUN_END = datetime.date(2026, 6, 30)
JUL_FIRST = datetime.date(2026, 7, 1)
DEC_END = datetime.date(2026, 12, 31)
YEAR_2027 = datetime.date(2027, 1, 1)

#: أكوادُ الرواتب في النسختين — تُقرأ من السجلّ في اختبار الانحراف لا هنا، وهذه
#: للتسمية في الاختبارات وحدها.
ISRAEL_PAYROLL_CODES = ("il_withholding_102", "il_bl_employees")

PAYROLL_FREQUENCY_ERROR = "دوريةُ الرواتب شهريةٌ أو كل شهرين."


def payroll_migration():
    return importlib.import_module(PAYROLL_MIGRATION)


def seed_rule_override_schedules():
    """v2 الفلسطينية من #277 — بلا زرعها تصير فلسطينُ v2 من #279 (والصحيحُ v3)."""
    migration = importlib.import_module(RULE_OVERRIDE_MIGRATION)
    migration.seed_event_schedules(django_apps, None)


def seed_payroll_schedules():
    payroll_migration().seed_payroll_schedules(django_apps, None)


def seed_payroll_document_items():
    payroll_migration().seed_payroll_document_items(django_apps, None)


class SemiannualCadenceTest(SimpleTestCase):
    """نصفُ سنويّ: دوريةُ لائحةٍ تُسقط فترتين في السنة — ولا دوريةَ خدمة (#279/D1)."""

    def test_the_half_year_periods_are_january_to_june_and_july_to_december(self):
        self.assertEqual(
            deadlines.periods_for("semiannual", JAN_START, DEC_END),
            [(JAN_START, JUN_END), (JUL_FIRST, DEC_END)],
        )

    def test_it_is_a_deadline_cadence_and_not_a_service_frequency(self):
        self.assertIn(("semiannual", "نصف سنوي"), DEADLINE_CADENCE_CHOICES)
        self.assertNotIn(
            "semiannual", [value for value, _label in CLIENT_SERVICE_FREQUENCY_CHOICES],
            "نصفُ سنويٍّ صار دوريةَ خدمةٍ — وهو دوريةُ سطرٍ في اللائحة وحدها",
        )
        self.assertNotIn(
            "semiannual",
            [value for value, _label in OFFICE_CUSTOM_RULE_CADENCE_CHOICES],
            "نصفُ سنويٍّ دخل دوريات التزام المكتب — القرارُ خارج نطاق #279",
        )

    def test_its_internal_lead_days_come_from_the_quarterly_setting(self):
        self.assertEqual(
            services.INTERNAL_LEAD_SETTING_BY_CADENCE.get("semiannual"),
            "internal_lead_days_quarterly",
        )


class PayrollTestCase(TestCase):
    """مكتبٌ إسرائيليٌّ بنسخة اللائحة v2 وكتالوجه وورقاته."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_rule_override_schedules()
        seed_payroll_schedules()
        seed_document_catalog()
        seed_payroll_document_items()
        cls.owner = User.objects.create_user(username="pay_owner", password="x")
        cls.tenant = create_company(
            "مكتب الرواتب", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def make_client(self, name="زبون الرواتب", **card):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=self.owner,
        )
        fields = {"annual_sales": Decimal("0"), "vat_classification": "authorized"}
        fields.update(card)
        TaxCard.objects.create(client=client, **fields)
        return client

    def add_service(
        self, client, code, *, frequency="monthly", starts_on=JAN_START,
    ):
        return services.add_client_service(
            client=client,
            service=self.catalog[code],
            starts_on=starts_on,
            responsible_from=starts_on,
            frequency=frequency,
        )

    def refresh(self, day):
        return services.refresh_office(self.tenant, day=day)

    def obligations(self, code, *, client=None):
        queryset = Obligation.objects.filter(rule_code=code)
        if client is not None:
            queryset = queryset.filter(client=client)
        return queryset.order_by("period_start", "pk")


class MonthlyPayrollTest(PayrollTestCase):
    """102 وביטוח לאומי يتبعان دوريةَ خدمة الزبون — لا دوريةً محفورة."""

    def test_a_monthly_israeli_payroll_client_gets_both_lines_every_month(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(MAR_FIRST)

        for code in ISRAEL_PAYROLL_CODES:
            rows = list(self.obligations(code))
            self.assertEqual(
                [row.period_end for row in rows], [JAN_END, FEB_END],
                f"{code}: شهرٌ ناقصٌ أو زائد — لم تُتبع دوريةُ الخدمة الشهرية",
            )
            self.assertEqual(rows[0].rule.cadence, "service")
            self.assertEqual(rows[0].rule.schedule.version, 2)

    def test_a_bimonthly_payroll_client_gets_one_obligation_for_two_months(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll", frequency="bimonthly")

        self.refresh(MAR_FIRST)

        for code in ISRAEL_PAYROLL_CODES:
            rows = list(self.obligations(code))
            self.assertEqual(
                len(rows), 1,
                f"{code}: التزامٌ لكل شهرٍ لخدمةٍ كلَّ شهرين — الدوريّةُ لم تُتبع",
            )
            self.assertEqual((rows[0].period_start, rows[0].period_end), (JAN_START, FEB_END))


class SemiannualFormTest(PayrollTestCase):
    """`טופס 126 חציוני`: قاعدتُه 18 من الشهر التالي، والزحزحةُ بعده وحده."""

    def test_the_legal_day_is_the_eighteenth_of_the_following_month(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(JUL_FIRST)

        half = self.obligations("il_bl_126_semiannual").get()
        self.assertEqual((half.period_start, half.period_end), (JAN_START, JUN_END))
        self.assertEqual(
            half.legal_date, datetime.date(2026, 7, 18),
            "التاريخُ بالقاعدة (18 يوليو) لا بعد الزحزحة — الحقلُ القانونيّ هو الحَكَم",
        )
        self.assertEqual(half.rule.cadence, "semiannual")
        self.assertEqual(half.rule.conditions, {"has_employees": True})

    def test_the_second_half_falls_on_eighteen_january_of_the_next_year(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(YEAR_2027)

        rows = list(self.obligations("il_bl_126_semiannual"))
        self.assertEqual([row.period_end for row in rows], [JUN_END, DEC_END])
        self.assertEqual(rows[1].period_start, JUL_FIRST)
        self.assertEqual(rows[1].legal_date, datetime.date(2027, 1, 18))

    def test_a_client_without_employees_gets_no_semiannual_form(self):
        client = self.make_client(has_employees=False)
        self.add_service(client, "payroll")

        self.refresh(YEAR_2027)

        self.assertFalse(Obligation.objects.exists())


class PalestinianPayrollTest(PayrollTestCase):
    """فلسطين: اقتطاعٌ شهريّ في 15 من التالي، وكشفٌ سنويٌّ في 30 نيسان «راجع»."""

    def setUp(self):
        ready_office(self.tenant, "PS")

    def test_the_monthly_withholding_is_due_on_the_fifteenth_of_the_next_month(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(MAR_FIRST)

        rows = list(self.obligations("ps_payroll_withholding"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].actual_deadline, datetime.date(2026, 2, 15))
        self.assertEqual(rows[1].actual_deadline, datetime.date(2026, 3, 15))

    def test_the_annual_statement_is_due_on_april_thirtieth_and_needs_review(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(YEAR_2027)

        row = self.obligations("ps_payroll_annual_statement").get()
        self.assertEqual((row.period_start, row.period_end), (JAN_START, DEC_END))
        self.assertEqual(row.actual_deadline, datetime.date(2027, 4, 30))
        self.assertEqual(row.rule.cadence, "annual")
        self.assertTrue(
            row.rule.needs_review,
            "الكشفُ السنويُّ بلا يومٍ منشور في النصّ — يجب أن يُعلَّم «راجع»",
        )

    def test_the_social_security_line_never_generates_an_obligation(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(YEAR_2027)

        self.assertFalse(
            Obligation.objects.filter(rule_code="ps_social_security").exists(),
            "الضمانُ الاجتماعي الموقوف بقرار 4/2019 ولّد التزاماً",
        )
        line = DeadlineSchedule.objects.get(
            tax_system="PS", year=2026, version=3,
        ).rules.get(code="ps_social_security")
        self.assertFalse(line.is_generated)


class PayrollObligationsSettingTest(PayrollTestCase):
    """إعدادُ «الالتزامات التي تولّدها خدمة الرواتب» — قرارُ مكتبٍ يُخصَّص لزبون."""

    def test_a_client_level_setting_drops_one_rule_for_that_client_only(self):
        first = self.make_client("الزبون الأول", has_employees=True)
        second = self.make_client("الزبون الثاني", has_employees=True)
        self.add_service(first, "payroll")
        self.add_service(second, "payroll")
        enabled = [
            code for code in settings_registry.PAYROLL_OBLIGATION_LABELS
            if code != "il_bl_employees"
        ]
        services.set_client_setting(first, "payroll_obligations", enabled)

        self.refresh(MAR_FIRST)

        self.assertFalse(
            self.obligations("il_bl_employees", client=first).exists(),
            "بندٌ أُخرِج من إعداد الزبون ووُلد له",
        )
        self.assertTrue(self.obligations("il_bl_employees", client=second).exists())
        self.assertTrue(
            self.obligations("il_withholding_102", client=first).exists(),
            "إخراجُ بندٍ أسقط البنودَ الأخرى معه",
        )

    def test_the_calendar_follows_the_same_decision(self):
        first = self.make_client("زبون التقويم", has_employees=True)
        self.add_service(first, "payroll")
        enabled = [
            code for code in settings_registry.PAYROLL_OBLIGATION_LABELS
            if code != "il_bl_employees"
        ]
        services.set_client_setting(first, "payroll_obligations", enabled)

        rows = services.client_deadlines(first, start=JAN_START, end=DEC_END)

        codes = {row["code"] for row in rows}
        self.assertNotIn("il_bl_employees", codes)
        self.assertIn("il_withholding_102", codes)


class PayrollFrequencyTest(PayrollTestCase):
    """دوريةُ الرواتب شهريةٌ أو كل شهرين — قاعدةٌ واحدة في المسارَين."""

    def test_a_quarterly_payroll_service_is_rejected_with_the_message(self):
        client = self.make_client(has_employees=True)

        with self.assertRaises(DjangoValidationError) as caught:
            self.add_service(client, "payroll", frequency="quarterly")

        self.assertEqual(
            caught.exception.message_dict["frequency"], [PAYROLL_FREQUENCY_ERROR],
        )
        self.assertFalse(ClientService.objects.exists())

    def test_monthly_and_bimonthly_payroll_services_are_accepted(self):
        for frequency in ("monthly", "bimonthly"):
            client = self.make_client(f"زبون {frequency}", has_employees=True)
            row = self.add_service(client, "payroll", frequency=frequency)
            self.assertEqual(row.frequencies.get().frequency, frequency)

    def test_changing_the_payroll_frequency_to_quarterly_is_rejected(self):
        client = self.make_client(has_employees=True)
        row = self.add_service(client, "payroll")

        with self.assertRaises(DjangoValidationError) as caught:
            services.change_client_service_frequency(
                row, frequency="quarterly", effective_from=FEB_FIRST, today=JAN_START,
            )

        self.assertEqual(
            caught.exception.message_dict["frequency"], [PAYROLL_FREQUENCY_ERROR],
        )
        self.assertEqual(row.frequencies.count(), 1)

    def test_another_service_keeps_a_quarterly_frequency(self):
        client = self.make_client("زبون الدفاتر")

        row = self.add_service(client, "bookkeeping", frequency="quarterly")

        self.assertEqual(row.frequencies.get().frequency, "quarterly")


class PayrollDocumentsTest(PayrollTestCase):
    """أوراقُ الرواتب: كشفٌ مطلوب وتغييراتُ موظفين «مش لازمة»."""

    def test_the_monthly_sheet_exists_only_for_the_payroll_service(self):
        payroll = self.make_client("زبون الرواتب", has_employees=True)
        self.add_service(payroll, "payroll")
        books = self.make_client("زبون الدفاتر")
        self.add_service(books, "bookkeeping")

        self.refresh(FEB_FIRST)

        row = DocumentChecklistItem.objects.get(
            client=payroll, item_code="il_payroll_sheet", period_start=JAN_START,
        )
        self.assertEqual(row.name, "كشف رواتب الشهر")
        self.assertEqual(row.status, DOCUMENT_STATUS_REQUIRED)
        self.assertEqual(row.service_codes, ["payroll"])
        self.assertFalse(
            DocumentChecklistItem.objects.filter(
                client=books, item_code="il_payroll_sheet",
            ).exists(),
            "بندُ رواتبٍ وُلد لزبونٍ بلا خدمة رواتب",
        )

    def test_the_employee_changes_row_is_not_needed_and_never_missing_docs(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")

        self.refresh(FEB_FIRST)

        changes = DocumentChecklistItem.objects.get(
            client=client, item_code="il_employee_changes", period_start=JAN_START,
        )
        self.assertEqual(changes.status, DOCUMENT_STATUS_NOT_NEEDED)
        self.assertEqual(changes.name, "تغييرات الموظفين (تعيين، ترك، تغيير راتب)")

        obligation = self.obligations("il_withholding_102").get()
        progress = services.document_progress(self.tenant, [obligation])[obligation.pk]
        self.assertEqual(
            progress["required"], 1,
            "صفُّ «مش لازمة» عُدَّ ورقةً مطلوبة — يُشعل «ناقصه أوراق» زوراً",
        )
        self.assertTrue(progress["missing"])

        sheet = DocumentChecklistItem.objects.get(
            client=client, item_code="il_payroll_sheet", period_start=JAN_START,
        )
        services.set_document_status(
            sheet, status="received", channel="whatsapp", actor=self.owner,
            day=FEB_FIRST,
        )
        progress = services.document_progress(self.tenant, [obligation])[obligation.pk]
        self.assertEqual(progress["required"], 1)
        self.assertFalse(progress["missing"])

    def test_an_office_item_still_starts_required(self):
        client = self.make_client(has_employees=True)
        self.add_service(client, "payroll")
        row = OfficeDocumentItem.objects.create(
            tenant=self.tenant, tax_system="IL", name="ورقة المكتب",
            cadence="monthly", service_codes=["payroll"],
        )

        self.refresh(FEB_FIRST)

        created = DocumentChecklistItem.objects.get(client=client, item_code=row.code)
        self.assertEqual(created.status, DOCUMENT_STATUS_REQUIRED)


class PayrollScheduleMigrationTest(PayrollTestCase):
    """هجرةُ 0009: النسخةُ الأعلى تُنسخ حرفاً وتُضاف، والعكسُ يحذف ما أنشأته وحدها."""

    def test_israel_version_two_copies_every_line_and_follows_the_service(self):
        for year in (2026, 2027):
            old = DeadlineSchedule.objects.get(tax_system="IL", year=year, version=1)
            new = DeadlineSchedule.objects.get(tax_system="IL", year=year, version=2)
            self.assertEqual(
                set(new.rules.values_list("code", flat=True)),
                set(old.rules.values_list("code", flat=True)) | {"il_bl_126_semiannual"},
            )
            for code in ISRAEL_PAYROLL_CODES:
                before = old.rules.get(code=code)
                after = new.rules.get(code=code)
                self.assertEqual(after.cadence, "service")
                self.assertEqual(
                    (
                        after.name, after.service_code, after.rule_kind, after.rule_day,
                        after.rule_month, after.conditions,
                        after.electronic_extension_days, after.period_overrides,
                        after.needs_review, after.source_url, after.event_kind,
                    ),
                    (
                        before.name, before.service_code, before.rule_kind, before.rule_day,
                        before.rule_month, before.conditions,
                        before.electronic_extension_days, before.period_overrides,
                        before.needs_review, before.source_url, before.event_kind,
                    ),
                    f"{code}: حقلٌ من حقول السطر تبدّل في النسخة الجديدة",
                )
            half = new.rules.get(code="il_bl_126_semiannual")
            self.assertEqual(half.name, "טופס 126 חציוני לביטוח לאומי")
            self.assertEqual(half.cadence, "semiannual")
            self.assertEqual(half.rule_kind, "day_of_next_month")
            self.assertEqual(half.rule_day, 18)
            self.assertEqual(half.conditions, {"has_employees": True})
            self.assertTrue(half.is_generated)
            self.assertFalse(half.needs_review)
            self.assertEqual(half.electronic_extension_days, 0)
            self.assertEqual(
                half.source_url, "https://www.btl.gov.il/Insurance/Maasik/Pages/Tofes126.aspx",
            )
            self.assertEqual(new.published_on, datetime.date(2026, 11, 5))
            self.assertIn("v2", new.note)
        self.assertEqual(DeadlineSchedule.objects.filter(tax_system="IL").count(), 4)

    def test_palestine_version_three_adds_the_annual_statement(self):
        for year in (2026, 2027):
            new = DeadlineSchedule.objects.get(tax_system="PS", year=year, version=3)
            self.assertEqual(new.rules.count(), 7)
            row = new.rules.get(code="ps_payroll_annual_statement")
            self.assertEqual(row.name, "الكشف السنوي للرواتب")
            self.assertEqual(row.service_code, "payroll")
            self.assertEqual(row.cadence, "annual")
            self.assertEqual(row.rule_kind, "month_day_next_year")
            self.assertEqual(row.rule_month, 4)
            self.assertEqual(row.rule_day, 30)
            self.assertEqual(row.conditions, {"has_employees": True})
            self.assertTrue(row.is_generated)
            self.assertTrue(row.needs_review)
            self.assertEqual(
                row.source_url, "http://muqtafi.birzeit.edu/pg/getleg.asp?id=16349",
            )
            self.assertIn("v3", new.note)
        self.assertEqual(DeadlineSchedule.objects.filter(tax_system="PS").count(), 6)

    def test_the_four_payroll_document_items_are_seeded(self):
        expected = {
            ("PS", "ps_payroll_sheet"): DOCUMENT_STATUS_REQUIRED,
            ("PS", "ps_employee_changes"): DOCUMENT_STATUS_NOT_NEEDED,
            ("IL", "il_payroll_sheet"): DOCUMENT_STATUS_REQUIRED,
            ("IL", "il_employee_changes"): DOCUMENT_STATUS_NOT_NEEDED,
        }
        for (system, code), status in expected.items():
            row = PlatformDocumentItem.objects.get(tax_system=system, code=code)
            self.assertEqual(row.cadence, "monthly")
            self.assertEqual(row.service_codes, ["payroll"])
            self.assertEqual(row.card_conditions, {})
            self.assertEqual(row.default_status, status)
        # «آخرَ بنود الشهريّ» في كل نظام: الترتيبُ يتبع التسلسلَ القائم لا يقطعه.
        for system, codes in (
            ("PS", {"ps_payroll_sheet", "ps_employee_changes"}),
            ("IL", {"il_payroll_sheet", "il_employee_changes"}),
        ):
            monthly = list(
                PlatformDocumentItem.objects
                .filter(tax_system=system, cadence="monthly")
                .order_by("sort_order", "name", "id")
                .values_list("code", flat=True),
            )
            self.assertEqual(set(monthly[-2:]), codes, monthly)
        self.assertEqual(
            PlatformDocumentItem.objects.get(tax_system="PS", code="ps_payroll_sheet").name,
            "كشف رواتب الشهر",
        )

    def test_the_reverse_deletes_only_what_it_created(self):
        migration = payroll_migration()
        before = set(
            DeadlineSchedule.objects.values_list("tax_system", "year", "version"),
        )
        before_items = set(
            PlatformDocumentItem.objects.values_list("tax_system", "code"),
        )

        migration.unseed_payroll_schedules(django_apps, None)
        migration.unseed_payroll_document_items(django_apps, None)

        self.assertEqual(
            set(DeadlineSchedule.objects.values_list("tax_system", "year", "version")),
            {
                (system, year, version)
                for system, year, version in before
                if not (system == "IL" and version == 2)
                and not (system == "PS" and version == 3)
            },
            "العكسُ مسّ نسخةً لم تنشئها الهجرة",
        )
        self.assertTrue(
            DeadlineSchedule.objects.filter(tax_system="PS", version=2).exists(),
            "v2 الفلسطينية (من #277) مُحيت مع عكس #279",
        )
        self.assertTrue(DeadlineSchedule.objects.filter(tax_system="IL", version=1).exists())
        self.assertFalse(
            PlatformDocumentItem.objects.filter(
                code__in=[
                    "ps_payroll_sheet", "ps_employee_changes",
                    "il_payroll_sheet", "il_employee_changes",
                ],
            ).exists(),
        )
        self.assertEqual(
            set(PlatformDocumentItem.objects.values_list("tax_system", "code")),
            {
                pair for pair in before_items
                if pair not in {
                    ("PS", "ps_payroll_sheet"), ("PS", "ps_employee_changes"),
                    ("IL", "il_payroll_sheet"), ("IL", "il_employee_changes"),
                }
            },
        )

        # عكسُ العكس يُعيدها — الهجرةُ أثرٌ لا يُعاد بيد.
        migration.seed_payroll_schedules(django_apps, None)
        migration.seed_payroll_document_items(django_apps, None)
        self.assertEqual(
            set(DeadlineSchedule.objects.values_list("tax_system", "year", "version")),
            before,
        )
        self.assertEqual(
            set(PlatformDocumentItem.objects.values_list("tax_system", "code")),
            before_items,
        )


class PayrollObligationsRegistryTest(PayrollTestCase):
    """حارسُ انحراف: اختياراتُ الإعداد = أكوادُ الرواتب غير الحدثية في أحدث نسخ اللائحة."""

    def latest_payroll_rules(self):
        """أكوادُ الرواتب **الدورية** في النسخة السارية لكل (نظام، سنة).

        **وسطرُ الحدث خارج المقارنة**: سطرُ الاقتطاع (`cadence="event"`) يحكمه
        إعدادُ «أنواع الأحداث المفعّلة» (`enabled_event_kinds`) لا إعدادُ بنود
        الرواتب، فمقارنتُه هنا تُنذر بانحرافٍ ليس انحرافاً.
        """
        rules = {}
        for system in ("PS", "IL"):
            for year in (
                DeadlineSchedule.objects
                .filter(tax_system=system)
                .values_list("year", flat=True)
                .distinct()
            ):
                schedule = (
                    DeadlineSchedule.objects
                    .filter(tax_system=system, year=year)
                    .order_by("-version")
                    .first()
                )
                rules.update({
                    rule.code: rule
                    for rule in schedule.rules.all()
                    if rule.service_code == "payroll" and rule.cadence != "event"
                })
        return rules

    def test_the_registry_choices_are_the_payroll_codes_of_the_latest_schedules(self):
        definition = settings_registry.get_definition("payroll_obligations")

        self.assertEqual(
            set(definition.choices), set(self.latest_payroll_rules()),
            "الإعدادُ ولائحةُ المواعيد افترقا — بندُ رواتبٍ دوريٍّ بلا اختيارٍ أو اختيارٌ بلا بند",
        )
        self.assertEqual(definition.kind, settings_registry.KIND_MULTI_CHOICE)
        self.assertIn(settings_registry.LEVEL_OFFICE, definition.levels)
        self.assertIn(settings_registry.LEVEL_CLIENT, definition.levels)
        self.assertEqual(list(definition.default), list(definition.choices))

    def test_every_choice_carries_its_schedule_line_name_as_the_label(self):
        labels = {
            option["value"]: option["label"]
            for option in settings_registry.get_definition(
                "payroll_obligations",
            ).choice_options()
        }
        for code, rule in self.latest_payroll_rules().items():
            self.assertEqual(labels[code], rule.name, code)
