"""قائمة الأوراق: الكتالوج والتوليد والحالات وشارة «ناقصه أوراق» — #278.

**القواعد المحسومة التي يثبتها هذا الملف:**

1. **بندٌ واحدٌ لخدمتين**: «فواتير المشتريات» يظهر مرّةً واحدة لزبونٍ عنده مسك
   دفاتر وقيمة مضافة — لا بندان (معيار القبول ١).
2. **التوليدُ داخل محرّك «حدّث المكتب» وidempotent**: الشهرُ M يُحفظ في أوّل
   M+1، والسنةُ Y في 1 يناير Y+1، وتشغيلُ اليوم نفسه مرّتين لا يكتب صفّاً.
3. **ثلاثُ طبقاتٍ للقائمة**: أساسُ المنصّة، ثم خيارُ المكتب، ثم **خيارُ الزبون
   الذي يغلب الجميع** — إدخالاً وإخراجاً.
4. **شرطُ البطاقة يمنع**: بندُ «تقرير مدقق» لشركةٍ لا يظهر لفرد، وبطاقةٌ ناقصة
   القيمة لا تطابق شرطاً أبداً.
5. **الحالاتُ الأربع**: «وصلت» تسجّل الفاعل والتاريخ والقناة، و«وصلت ناقصة»
   تُبقي «ناقصه أوراق» و«وصلت» و«مش لازمة» تُسقطانها.
6. **مددُ الحفظ بياناتُ منصّةٍ** لكل نظام، لا ثابتاً في الكود.
7. **هجرةُ البذرة** تُزرع من الدالّة نفسها (نمط `test_obligations.py`) — فلا نسخةً
   ثانية للقائمة في الاختبار.
"""
import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounting_office import services
from accounting_office.models import (
    DOCUMENT_STATUS_NOT_NEEDED,
    DOCUMENT_STATUS_PARTIAL,
    DOCUMENT_STATUS_RECEIVED,
    DOCUMENT_STATUS_REQUIRED,
    ClientDocumentItemChoice,
    ClientService,
    DeadlineRule,
    DocumentChecklistItem,
    DocumentRetentionRule,
    Obligation,
    OfficeClient,
    OfficeDocumentItem,
    OfficeDocumentItemChoice,
    PeriodTask,
    PlatformDocumentItem,
    TaxCard,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency
from tenants.services import create_company

#: هجرةُ بيانات الكتالوج — تُستدعى بدالّتها كما هي (نمط `test_obligations.py`).
DOCUMENTS_MIGRATION = "accounting_office.migrations.0008_document_checklist"
#: بنداتُ الرواتب (#279) — هجرةٌ تالية، تُزرع يدوياً في الاختبارين اللذين
#: يقيسانها ولا تُضاف إلى `seed_document_catalog`، فتبقى بقيّةُ هذا الملفّ تقيس
#: `0008` وحده.
PAYROLL_DOCUMENTS_MIGRATION = "accounting_office.migrations.0009_payroll_due_dates"

JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
FEB_FIRST = datetime.date(2026, 2, 1)
FEB_END = datetime.date(2026, 2, 28)
MAR_FIRST = datetime.date(2026, 3, 1)
MAR_END = datetime.date(2026, 3, 31)
APR_FIRST = datetime.date(2026, 4, 1)
YEAR_2025_START = datetime.date(2025, 1, 1)
YEAR_2025_END = datetime.date(2025, 12, 31)
YEAR_2026_START = datetime.date(2026, 1, 1)


def seed_document_catalog():
    """بنداتُ المنصّة ومددُ الحفظ **من هجرة البيانات نفسها**."""
    migration = importlib.import_module(DOCUMENTS_MIGRATION)
    migration.seed_document_catalog(django_apps, None)


def seed_payroll_document_items():
    """بنداتُ الرواتب الأربعة من هجرة `0009` — تُزرع في اختبارها وحدها."""
    migration = importlib.import_module(PAYROLL_DOCUMENTS_MIGRATION)
    migration.seed_payroll_document_items(django_apps, None)


class DocumentsTestCase(TestCase):
    """مكتبٌ إسرائيليٌّ بلائحته وكتالوجه، وزبونُ بطاقةٍ كاملة."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_document_catalog()
        cls.owner = User.objects.create_user(username="doc_owner", password="x")
        cls.tenant = create_company(
            "مكتب الأوراق", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def setUp(self):
        # كلُّ اختبارٍ يبني ما يفحصه: صفوفُ المحرّك وكتالوج المكتب تُصفَّر.
        DocumentChecklistItem.objects.all().delete()
        OfficeDocumentItem.objects.all().delete()
        OfficeDocumentItemChoice.objects.all().delete()
        ClientDocumentItemChoice.objects.all().delete()
        Obligation.objects.all().delete()
        PeriodTask.objects.all().delete()

    # ── البناء ────────────────────────────────────────────────────────────
    def make_client(self, name="زبون الأوراق", *, system=None, **card):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=self.owner,
        )
        fields = {
            "annual_sales": Decimal("0"),
            "vat_classification": "authorized",
            "entity_type": "company",
        }
        fields.update(card)
        TaxCard.objects.create(client=client, **fields)
        if system is not None:
            services.set_client_setting(client, "tax_system", system)
        return client

    def add_service(
        self, client, code, *,
        frequency="monthly",
        starts_on=JAN_START,
        responsible_from=None,
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

    def rows(self, client, *, cadence=None, period_start=None):
        queryset = DocumentChecklistItem.objects.filter(client=client)
        if cadence is not None:
            queryset = queryset.filter(cadence=cadence)
        if period_start is not None:
            queryset = queryset.filter(period_start=period_start)
        return queryset

    def row(self, client, item_code, period_start=JAN_START):
        return DocumentChecklistItem.objects.get(
            client=client, item_code=item_code, period_start=period_start,
        )

    def add_obligation(
        self, client, *, period_start=JAN_START, period_end=JAN_END,
        status=Obligation.STATUS_PENDING, client_service=None,
    ):
        """صفٌّ محفوظٌ بيدٍ — لا محرّك ولا شغلةَ توليد.

        الشغلةُ بـ`get_or_create` لأن المحرّكَ قد يكون ولّد شغلتَها للفترة نفسها.
        """
        service_row = client_service or client.services.first()
        task, _created = PeriodTask.objects.get_or_create(
            client_service=service_row,
            period_start=period_start,
            period_end=period_end,
            defaults={
                "tenant": self.tenant,
                "client": client,
                "internal_deadline": period_end,
            },
        )
        rule = DeadlineRule.objects.filter(
            schedule__tax_system="IL", schedule__year=2026,
        ).first()
        # `update_or_create` لأن المحرّكَ قد يكون ولّد التزامَ الفترة نفسها.
        obligation, _created = Obligation.objects.update_or_create(
            client_service=service_row,
            rule_code=rule.code,
            period_end=period_end,
            defaults={
                "tenant": self.tenant,
                "client": client,
                "task": task,
                "rule": rule,
                "name": rule.name,
                "period_start": period_start,
                "legal_date": period_end,
                "official_date": period_end,
                "actual_deadline": period_end,
                "internal_deadline": period_end,
                "status": status,
            },
        )
        return obligation


class GenerationTest(DocumentsTestCase):
    """ما يُولَّد ومتى — بندٌ واحدٌ لكل خدمة، والشهرُ بعد انتهائه."""

    def test_purchase_invoices_is_one_row_for_bookkeeping_and_vat(self):
        client = self.make_client(system="PS", vat_classification="licensed")
        self.add_service(client, "bookkeeping")
        self.add_service(client, "vat")

        self.refresh(FEB_FIRST)

        self.assertEqual(
            self.rows(client, period_start=JAN_START)
            .filter(item_code="ps_purchase_invoices").count(),
            1,
        )

    def test_a_month_is_saved_on_the_first_day_of_the_next_month(self):
        client = self.make_client()
        self.add_service(client, "bookkeeping")

        self.refresh(JAN_END)
        self.assertFalse(self.rows(client).exists())

        self.refresh(FEB_FIRST)
        self.assertTrue(
            self.rows(client, period_start=JAN_START).exists(),
        )

    def test_the_annual_list_is_saved_on_january_first_of_the_next_year(self):
        client = self.make_client()
        self.add_service(
            client, "annual_accounts", frequency="annual",
            starts_on=YEAR_2025_START,
        )

        self.refresh(YEAR_2025_END)
        self.assertFalse(self.rows(client, cadence="annual").exists())

        self.refresh(YEAR_2026_START)
        self.assertTrue(
            self.rows(
                client, cadence="annual", period_start=YEAR_2025_START,
            ).exists(),
        )

    def test_refreshing_twice_the_same_day_creates_nothing(self):
        client = self.make_client()
        self.add_service(client, "bookkeeping")
        self.add_service(client, "vat")

        self.refresh(MAR_FIRST)
        count = self.rows(client).count()
        self.assertGreater(count, 0)

        self.refresh(MAR_FIRST)
        self.assertEqual(self.rows(client).count(), count)

    def test_only_services_the_office_is_responsible_for_drive_the_list(self):
        """خدمةٌ تبدأ في آذار لا تُطلب أوراقُها في كانون الثاني."""
        client = self.make_client()
        self.add_service(client, "bookkeeping", starts_on=MAR_FIRST)

        self.refresh(FEB_FIRST)

        self.assertFalse(self.rows(client).exists())

    def test_a_disclaimed_last_period_removes_that_services_items(self):
        """#278 جولة ١: `skip` يصل إلى البنود، وفترةُ الخدمة **تحتوي** شهرَ المستندات.

        خدمةُ القيمة المضافة رُبعيةٌ انتهت بـ«آخر فترة ليست علينا»: فترتُها
        (كانون الثاني–آذار) تحتوي شباطَ ولا تساويه، وبنودُها وحدها تسقط — وبنودُ
        مسك الدفاتر تبقى. والزبونُ الثاني شاهدٌ: بالخدمة نفسها بلا رفعٍ تظهر بنودُها.
        """
        client = self.make_client()
        self.add_service(client, "bookkeeping")
        stopped = self.add_service(client, "vat", frequency="quarterly")
        services.stop_client_service(
            stopped, ends_on=MAR_END, last_period_ours=False,
        )
        control = self.make_client("زبونُ المقارنة")
        self.add_service(control, "bookkeeping")
        kept = self.add_service(control, "vat", frequency="quarterly")
        services.stop_client_service(kept, ends_on=MAR_END)

        self.refresh(APR_FIRST)

        february = self.rows(client, period_start=FEB_FIRST)
        self.assertTrue(february.filter(item_code="il_bank_statements").exists())
        self.assertFalse(february.filter(item_code="il_zero_rate_docs").exists())
        self.assertTrue(
            self.rows(control, period_start=FEB_FIRST)
            .filter(item_code="il_zero_rate_docs").exists(),
        )


class LayersTest(DocumentsTestCase):
    """الطبقات الثلاث: المنصّة ← المكتب ← الزبون، والأخيرُ يغلب."""

    def test_office_exclusion_removes_a_platform_item(self):
        client = self.make_client()
        self.add_service(client, "bookkeeping")
        OfficeDocumentItemChoice.objects.create(
            tenant=self.tenant, item_code="il_bank_statements", included=False,
        )

        self.refresh(FEB_FIRST)

        self.assertFalse(
            self.rows(client).filter(item_code="il_bank_statements").exists(),
        )
        self.assertTrue(self.rows(client).filter(item_code="il_receipts").exists())

    def test_client_choice_forces_an_item_its_conditions_reject(self):
        client = self.make_client(entity_type="individual")
        self.add_service(client, "annual_accounts", frequency="annual",
                         starts_on=YEAR_2025_START)
        ClientDocumentItemChoice.objects.create(
            client=client, item_code="il_audited_statements", included=True,
        )

        self.refresh(YEAR_2026_START)

        self.assertTrue(
            self.rows(client).filter(item_code="il_audited_statements").exists(),
        )

    def test_client_choice_can_remove_an_included_item(self):
        client = self.make_client()
        self.add_service(client, "bookkeeping")
        ClientDocumentItemChoice.objects.create(
            client=client, item_code="il_receipts", included=False,
        )

        self.refresh(FEB_FIRST)

        self.assertFalse(self.rows(client).filter(item_code="il_receipts").exists())
        self.assertTrue(
            self.rows(client).filter(item_code="il_bank_statements").exists(),
        )

    def test_a_company_only_item_is_absent_for_an_individual(self):
        client = self.make_client(entity_type="individual")
        self.add_service(client, "annual_accounts", frequency="annual",
                         starts_on=YEAR_2025_START)

        self.refresh(YEAR_2026_START)

        self.assertFalse(
            self.rows(client).filter(item_code="il_audited_statements").exists(),
        )
        self.assertTrue(
            self.rows(client).filter(item_code="il_year_end_bank").exists(),
        )

    def test_a_blank_card_value_never_matches_a_condition(self):
        """بطاقةٌ بلا `vat_classification` لا تفي بشرط «مشتغل مرخّص»."""
        client = self.make_client(vat_classification="")
        self.add_service(client, "vat")

        self.refresh(FEB_FIRST)

        self.assertFalse(
            self.rows(client).filter(item_code="il_zero_rate_docs").exists(),
        )


class StatusTest(DocumentsTestCase):
    """الحالاتُ الأربع: مَن ومتى وكيف — والتفريغُ عند التراجع."""

    def setUp(self):
        super().setUp()
        self.client_row = self.make_client()
        self.add_service(self.client_row, "bookkeeping")
        self.refresh(FEB_FIRST)
        self.row = self.row(self.client_row, "il_bank_statements")

    def test_received_stores_actor_date_and_channel(self):
        day = datetime.date(2026, 2, 3)

        services.set_document_status(
            self.row, status=DOCUMENT_STATUS_RECEIVED,
            channel="whatsapp", actor=self.owner, day=day,
        )

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, DOCUMENT_STATUS_RECEIVED)
        self.assertEqual(self.row.received_on, day)
        self.assertEqual(self.row.received_by_id, self.owner.pk)
        self.assertEqual(self.row.channel, "whatsapp")
        self.assertEqual(self.row.updated_by_id, self.owner.pk)

    def test_a_missing_channel_is_rejected(self):
        with self.assertRaises(DjangoValidationError) as caught:
            services.set_document_status(
                self.row, status=DOCUMENT_STATUS_RECEIVED, channel="",
                actor=self.owner, day=FEB_FIRST,
            )
        self.assertIn("channel", caught.exception.message_dict)

    def test_an_unknown_status_is_rejected(self):
        with self.assertRaises(DjangoValidationError) as caught:
            services.set_document_status(
                self.row, status="maybe", channel="paper",
                actor=self.owner, day=FEB_FIRST,
            )
        self.assertIn("status", caught.exception.message_dict)

    def test_required_and_not_needed_clear_the_receipt(self):
        services.set_document_status(
            self.row, status=DOCUMENT_STATUS_PARTIAL, channel="paper",
            actor=self.owner, day=FEB_FIRST,
        )

        services.set_document_status(
            self.row, status=DOCUMENT_STATUS_NOT_NEEDED, actor=self.owner,
            day=FEB_FIRST,
        )

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, DOCUMENT_STATUS_NOT_NEEDED)
        self.assertIsNone(self.row.received_on)
        self.assertIsNone(self.row.received_by_id)
        self.assertEqual(self.row.channel, "")

        services.set_document_status(
            self.row, status=DOCUMENT_STATUS_REQUIRED, actor=self.owner,
            day=FEB_FIRST,
        )
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, DOCUMENT_STATUS_REQUIRED)

    def test_the_annual_row_says_year_not_month(self):
        self.assertEqual(
            services.document_status_label(DOCUMENT_STATUS_NOT_NEEDED, "annual"),
            "مش لازمة هالسنة",
        )
        self.assertEqual(
            services.document_status_label(DOCUMENT_STATUS_NOT_NEEDED, "monthly"),
            "مش لازمة هالشهر",
        )


class MissingDocsBadgeTest(DocumentsTestCase):
    """«ناقصه أوراق» مشتقّةٌ من بنود خدمة الالتزام وفترته — ولا تُخزَّن."""

    def setUp(self):
        super().setUp()
        self.client_row = self.make_client()
        self.add_service(self.client_row, "bookkeeping")
        self.add_service(self.client_row, "vat")
        self.refresh(MAR_FIRST)
        # الالتزامُ على **خدمة القيمة المضافة** وحدها: بنودُها هي المقيسة هنا.
        self.vat_service = self.client_row.services.get(service=self.catalog["vat"])
        self.obligation = self.add_obligation(
            self.client_row, client_service=self.vat_service,
        )

    def _missing(self, obligation=None):
        """الشارةُ من `document_progress` وحدها — لا دالّةَ ثانيةً تُشتقّ منها.

        وغيابُ الصفّ من التقدّم يعني «لا صفوفَ تُحسب»، وهو «غيرُ ناقص» لا «ناقص».
        """
        obligation = obligation or self.obligation
        row = services.document_progress(self.tenant, [obligation]).get(obligation.pk)
        return bool(row and row["missing"])

    def _vat_rows(self):
        """كلُّ صفوفُ كانون الثاني التي تخصّ خدمة القيمة المضافة — بلا قائمةٍ ثانية."""
        return [
            row for row in self.rows(self.client_row, period_start=JAN_START)
            if "vat" in (row.service_codes or [])
        ]

    def _set(self, row, status):
        services.set_document_status(
            row, status=status, channel="paper", actor=self.owner,
            day=FEB_FIRST,
        )
        return row

    def test_required_marks_the_obligation_as_missing_documents(self):
        self.assertTrue(self._vat_rows())
        self.assertTrue(self._missing())

    def test_partial_keeps_it_missing(self):
        for row in self._vat_rows():
            self._set(row, DOCUMENT_STATUS_NOT_NEEDED)
        self.assertFalse(self._missing())

        target = self._vat_rows()[0]
        self._set(target, DOCUMENT_STATUS_PARTIAL)
        self.assertTrue(self._missing())

    def test_received_clears_it(self):
        rows = self._vat_rows()
        for row in rows[1:]:
            self._set(row, DOCUMENT_STATUS_NOT_NEEDED)
        self._set(rows[0], DOCUMENT_STATUS_RECEIVED)

        self.assertFalse(self._missing())

    def test_not_needed_clears_it(self):
        for row in self._vat_rows():
            self._set(row, DOCUMENT_STATUS_NOT_NEEDED)

        self.assertFalse(self._missing())

    def test_a_row_outside_the_obligation_period_does_not_count(self):
        DocumentChecklistItem.objects.create(
            tenant=self.tenant, client=self.client_row,
            item_code="feb_only_paper", name="ورقة شباط",
            service_codes=["vat"], cadence="monthly",
            period_start=FEB_FIRST, period_end=FEB_END,
            status=DOCUMENT_STATUS_REQUIRED,
        )
        DocumentChecklistItem.objects.filter(
            client=self.client_row, period_start=JAN_START,
        ).delete()

        obligation = self.add_obligation(
            self.client_row,
            period_start=JAN_START, period_end=JAN_END,
            client_service=self.vat_service,
        )

        self.assertFalse(self._missing(obligation))

    def test_rows_with_no_service_never_drive_the_badge(self):
        DocumentChecklistItem.objects.filter(client=self.client_row).delete()
        DocumentChecklistItem.objects.create(
            tenant=self.tenant, client=self.client_row,
            item_code="general_papers", name="أوراق عامة",
            service_codes=[], cadence="monthly",
            period_start=JAN_START, period_end=JAN_END,
            status=DOCUMENT_STATUS_REQUIRED,
        )

        self.assertFalse(self._missing())

    def test_a_pending_obligation_only(self):
        submitted = self.add_obligation(
            self.client_row, status=Obligation.STATUS_SUBMITTED,
        )
        self.assertNotIn(
            submitted.pk,
            services.document_progress(self.tenant, [submitted]),
        )


class ProgressTest(DocumentsTestCase):
    """عدّادُ `وصل / مطلوب`: `م` بلا «مش لازمة»، و`ن` ما وصل منها."""

    def test_progress_counts_received_out_of_required(self):
        client = self.make_client()
        self.add_service(client, "vat")
        self.refresh(MAR_FIRST)
        obligation = self.add_obligation(client)

        rows = list(
            DocumentChecklistItem.objects.filter(
                client=client, period_start=JAN_START,
            ),
        )
        received = rows[0]
        services.set_document_status(
            received, status=DOCUMENT_STATUS_RECEIVED, channel="paper",
            actor=self.owner, day=FEB_FIRST,
        )
        services.set_document_status(
            rows[1], status=DOCUMENT_STATUS_NOT_NEEDED, actor=self.owner,
            day=FEB_FIRST,
        )

        progress = services.document_progress(self.tenant, [obligation])[
            obligation.pk
        ]

        self.assertEqual(progress["required"], len(rows) - 1)
        self.assertEqual(progress["received"], 1)
        self.assertTrue(progress["missing"])

    def test_rows_outside_every_pending_period_are_not_fetched(self):
        """#278 جولة ١: القراءةُ مقيَّدةٌ بمدى الالتزامات المنتظِرة — لا كلِّ الزبائن.

        شباط مُولَّدٌ لصفوفٍ حقيقية، وفترةُ الالتزام كانون الثاني: الاستعلامُ يجب
        أن يحمل الحدَّين، وإلا قرأ المكتبُ تاريخَ الزبون كلَّه لعدّ شهرٍ واحد.
        """
        client = self.make_client()
        self.add_service(client, "vat")
        self.refresh(MAR_FIRST)
        obligation = self.add_obligation(client)

        with CaptureQueriesContext(connection) as captured:
            services.document_progress(self.tenant, [obligation])

        checklist = [
            query["sql"] for query in captured.captured_queries
            if "documentchecklistitem" in query["sql"].lower()
        ]
        self.assertEqual(len(checklist), 1, checklist)
        self.assertRegex(checklist[0], r'period_start["`]?\s*>=')
        self.assertRegex(checklist[0], r'period_end["`]?\s*<=')
        self.assertIn(JAN_START.isoformat(), checklist[0])
        self.assertIn(JAN_END.isoformat(), checklist[0])


class CatalogTest(DocumentsTestCase):
    """بذرةُ الكتالوج ومددُ الحفظ — بياناتُ منصّةٍ لا أرقامٌ في الكود."""

    def test_every_seeded_code_is_unique_per_system(self):
        codes = list(
            PlatformDocumentItem.objects.values_list("tax_system", "code"),
        )
        self.assertEqual(len(codes), len(set(codes)))

    def test_seed_counts_per_system_and_cadence(self):
        # بنداتُ الرواتب (#279) تُضاف إلى الشهريّ وحده: بندان لكل نظام.
        seed_payroll_document_items()

        def count(system, cadence):
            return PlatformDocumentItem.objects.filter(
                tax_system=system, cadence=cadence,
            ).count()

        self.assertEqual(count("PS", "monthly"), 12)
        self.assertEqual(count("PS", "annual"), 8)
        self.assertEqual(count("IL", "monthly"), 13)
        self.assertEqual(count("IL", "annual"), 8)

    def test_the_payroll_items_are_seeded_with_their_services_and_defaults(self):
        """#279: بندان لكل نظام — كشفٌ مطلوب، وتغييراتُ موظفين «مش لازمة»."""
        seed_payroll_document_items()

        expected = {
            ("PS", "ps_payroll_sheet"): "required",
            ("PS", "ps_employee_changes"): "not_needed",
            ("IL", "il_payroll_sheet"): "required",
            ("IL", "il_employee_changes"): "not_needed",
        }
        for (system, code), status in expected.items():
            row = PlatformDocumentItem.objects.get(tax_system=system, code=code)
            self.assertEqual(row.cadence, "monthly")
            self.assertEqual(row.service_codes, ["payroll"])
            self.assertEqual(row.card_conditions, {})
            self.assertEqual(row.default_status, status)
        self.assertEqual(
            PlatformDocumentItem.objects.get(
                tax_system="IL", code="il_payroll_sheet",
            ).name,
            "كشف رواتب الشهر",
        )
        self.assertEqual(
            PlatformDocumentItem.objects.get(
                tax_system="IL", code="il_employee_changes",
            ).name,
            "تغييرات الموظفين (تعيين، ترك، تغيير راتب)",
        )

    def test_one_item_carries_two_services(self):
        row = PlatformDocumentItem.objects.get(
            tax_system="PS", code="ps_purchase_invoices",
        )
        self.assertEqual(sorted(row.service_codes), ["bookkeeping", "vat"])

    def test_the_seed_reverse_deletes_exactly_its_own_codes(self):
        migration = importlib.import_module(DOCUMENTS_MIGRATION)
        PlatformDocumentItem.objects.create(
            tax_system="IL", code="manual_extra", name="يدوي",
            cadence="monthly", service_codes=["bookkeeping"], sort_order=999,
        )

        migration.unseed_document_catalog(django_apps, None)

        self.assertEqual(
            list(PlatformDocumentItem.objects.values_list("code", flat=True)),
            ["manual_extra"],
        )

        seed_document_catalog()
        # ٣٧ بندَ بذرةٍ + البندُ اليدويّ الذي أضفناه: العكسُ لم يمسّه.
        self.assertEqual(PlatformDocumentItem.objects.count(), 38)

    def test_retention_rules_are_seeded_per_system(self):
        palestine = DocumentRetentionRule.objects.filter(tax_system="PS")
        israel = DocumentRetentionRule.objects.filter(tax_system="IL")
        self.assertEqual(palestine.count(), 1)
        self.assertEqual(israel.count(), 2)

        books = palestine.get()
        self.assertEqual(books.years, 5)
        self.assertEqual(books.basis, "year_end")
        self.assertIn("mjr.ogb.gov.ps", books.source_url)

        mandatory = israel.get(code="il_mandatory_documents")
        self.assertEqual(mandatory.years, 7)
        self.assertEqual(mandatory.alt_years, 6)
        self.assertEqual(mandatory.basis, "later_of_year_end_or_filing")
        self.assertIn("wikisource.org", mandatory.source_url)

        optional = israel.get(code="il_optional_documents")
        self.assertEqual(optional.years, 3)
        self.assertEqual(optional.basis, "filing")

    def test_retention_payload_is_composed_for_the_client_system(self):
        client = self.make_client(system="IL")

        payload = services.document_retention_payload(client)

        self.assertEqual(len(payload), 2)
        self.assertTrue(all(row["source_url"] for row in payload))
        self.assertTrue(all(row["text"] for row in payload))
        self.assertTrue(all(row["basis_label"] for row in payload))

    def test_an_office_custom_item_is_offered_from_its_own_code(self):
        client = self.make_client()
        self.add_service(client, "bookkeeping")
        row = OfficeDocumentItem.objects.create(
            tenant=self.tenant, tax_system="IL", name="عقد إيجار المكتب",
            cadence="monthly", service_codes=[],
        )

        self.refresh(FEB_FIRST)

        created = DocumentChecklistItem.objects.get(client=client, item_code=row.code)
        self.assertEqual(row.code, f"office_doc_{row.pk}")
        self.assertEqual(created.name, "عقد إيجار المكتب")
