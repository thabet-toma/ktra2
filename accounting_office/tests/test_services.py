"""كتالوج الخدمات والباقات وخدمات الزبون — #273.

**القواعد المحسومة التي يثبتها هذا الملف:**

1. **التغيير يسري من تاريخٍ ولقدّام**: تغييرُ الدورية من نيسان لا يغيّر آذار —
   الصفوفُ مؤرَّخة، و`frequency_on` تقرأ الصفَّ ذا أكبر `effective_from <= اليوم`.
   (الحالاتُ التي تقارن باليوم — `FrequencyHistoryTest` وما يؤكّد «نشطة»/«موقوفة» —
   نسبيّةٌ من اليوم كي لا تتعفّن؛ والباقي بتواريخ مطلقة لا تمسّ «اليوم».)
2. **الإيقاف لا يمحو**: `ends_on` يُكتب، والصفُّ يبقى في التاريخ ويُعرض «موقوفة».
3. **الباقة نسخٌ لا ربط**: تعبّئ خدمات الزبون مرّةً، ثم لا يمسّ أحدُ الطرفين الآخر.
4. **الاقتراح يتبع البطاقة والسقف المؤرَّخ** لا رقماً في الكود: نظامان، وسقفان في
   سنتين، وسنةٌ بلا سقف منشور تأخذ آخر سقفٍ سابق وتقول «تقديري».
5. **السقوف بياناتُ منصّةٍ مؤرَّخة** (`TaxThreshold`) لا أرقامٌ مبثوثة.
6. **الصلاحيات والرؤية كما في #272**: زبونُ غيرك 404، والقارئ 403 على كل كتابة،
   و`office.amounts.view` وحدها تُظهر `suggested_price` وكتابتُه بدونها 403.
"""
import datetime
import importlib
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.models import (
    ClientService,
    OfficeClient,
    OfficeService,
    ServicePackage,
    TaxCard,
    TaxThreshold,
)
from accounting_office.services import set_office_setting
from core.modules import invalidate_module_cache
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"
SERVICES = f"{BASE}services/"
PACKAGES = f"{BASE}packages/"

#: أرقام البحث المنشورة (`research/acct-tax-il`) — **ثوابت الاختبار** التي تُقاس
#: عليها بياناتُ الهجرة. تُزرع بدالّة الهجرة نفسها لا يدوياً، فيسقط هذا الملفّ إن
#: تغيّر رقمٌ فيها (انظر `PublishedThresholdsTest`).
IL_MONTHLY_2026 = Decimal("1775000")
IL_MONTHLY_2027 = Decimal("1805000")
IL_EXEMPT_2026 = Decimal("122833")

MONTHLY_CEILING_2026_URL = (
    "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/"
    "procedures_03-2025/he/vat_procedures_03-2025.docx"
)
MONTHLY_CEILING_2027_URL = (
    "https://www.gov.il/BlobFolder/dynamiccollectorresultitem/"
    "procedures_03-2026/he/vat_procedures_03-2026.docx"
)
EXEMPT_CEILING_2026_URL = "https://www.gov.il/he/pages/vat-rate-amount-new"

#: هجرةُ بيانات السقوف — تُستدعى كما هي، فلا نسخةَ ثانية من الأرقام في الاختبار.
THRESHOLDS_MIGRATION = "accounting_office.migrations.0003_services_packages_thresholds"


def ready_office(tenant, tax_system="PS"):
    """يُكمل أول تشغيل — الإنشاء مرفوضٌ قبله (قرار #271)."""
    set_office_setting(tenant, "tax_system", tax_system)
    set_office_setting(tenant, "office_size", "small")


def make_client(tenant, name, *, annual_sales=Decimal("0"), vat_classification="",
                responsible=None):
    client = OfficeClient.objects.create(
        tenant=tenant, name=name, responsible=responsible,
    )
    TaxCard.objects.create(
        client=client, annual_sales=annual_sales,
        vat_classification=vat_classification,
    )
    return client


def catalog(tenant):
    return {row.code: row for row in services.ensure_default_services(tenant)}


def seed_published_thresholds():
    """السقوفُ المنشورة **من هجرة البيانات نفسها** — لا زرعٌ يدويٌّ موازٍ لها.

    `core.test_settings` يعطّل الهجرات فلا تُنفَّذ هجرةُ البيانات تلقائياً؛ فتُستدعى
    دالّتُها هنا بالوسائط التي تتوقّعها (`apps`)، ويبقى مصدرُ الأرقام واحداً.
    """
    migration = importlib.import_module(THRESHOLDS_MIGRATION)
    migration.seed_tax_thresholds(django_apps, None)


class OfficeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        cls.owner = User.objects.create_user(username="svc_owner", password="x")
        cls.tenant = create_company(
            "مكتب الخدمات", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        # مبيعاتٌ تحت سقف 2026 ⇒ اقتراحُ ق.م «كل شهرين»: يثبت أن الموظف حين يختار
        # «شهري» يُسجَّل المقترحُ في تاريخ الصفّ كما كان.
        cls.client_row = make_client(
            cls.tenant, "زبون الخدمات",
            annual_sales=Decimal("400000"), vat_classification="authorized",
        )
        cls.catalog = catalog(cls.tenant)


class PublishedThresholdsTest(OfficeTestCase):
    """بياناتُ الهجرة محروسةٌ حرفاً: رقمٌ يتغيّر فيها يسقط هنا."""

    def test_the_seeded_ceilings_are_the_published_ones(self):
        rows = {
            (row.tax_system, row.kind, row.year): row
            for row in TaxThreshold.objects.all()
        }
        self.assertEqual(
            set(rows),
            {
                ("IL", "vat_monthly_reporting", 2026),
                ("IL", "vat_monthly_reporting", 2027),
                ("IL", "vat_exempt_dealer", 2026),
            },
        )
        self.assertEqual(
            rows[("IL", "vat_monthly_reporting", 2026)].amount, IL_MONTHLY_2026,
        )
        self.assertEqual(
            rows[("IL", "vat_monthly_reporting", 2027)].amount, IL_MONTHLY_2027,
        )
        self.assertEqual(
            rows[("IL", "vat_exempt_dealer", 2026)].amount, IL_EXEMPT_2026,
        )
        self.assertEqual(
            rows[("IL", "vat_monthly_reporting", 2026)].source_url,
            MONTHLY_CEILING_2026_URL,
        )
        self.assertEqual(
            rows[("IL", "vat_monthly_reporting", 2027)].source_url,
            MONTHLY_CEILING_2027_URL,
        )
        self.assertEqual(
            rows[("IL", "vat_exempt_dealer", 2026)].source_url,
            EXEMPT_CEILING_2026_URL,
        )


class DefaultServicesTest(OfficeTestCase):
    """`ensure_default_services` زرعٌ idempotent بخمسة أكوادٍ ثابتة."""

    def test_the_five_defaults_come_with_their_fixed_codes(self):
        rows = OfficeService.objects.filter(tenant=self.tenant)
        self.assertEqual(rows.count(), 5)
        self.assertEqual(
            sorted(rows.values_list("code", flat=True)),
            ["annual_accounts", "bookkeeping", "consulting", "payroll", "vat"],
        )
        self.assertEqual(catalog(self.tenant)["bookkeeping"].name, "مسك دفاتر")
        self.assertEqual(catalog(self.tenant)["vat"].name, "قيمة مضافة")
        self.assertEqual(catalog(self.tenant)["payroll"].name, "رواتب")
        self.assertEqual(catalog(self.tenant)["annual_accounts"].name, "ميزانية وتدقيق")
        self.assertEqual(catalog(self.tenant)["consulting"].name, "استشارات ومعاملات")

    def test_calling_it_twice_still_leaves_five(self):
        services.ensure_default_services(self.tenant)
        services.ensure_default_services(self.tenant)
        self.assertEqual(OfficeService.objects.filter(tenant=self.tenant).count(), 5)

    def test_a_service_added_by_the_office_is_not_builtin_and_gets_its_code(self):
        row = services.create_office_service(self.tenant, name="اعتراضات ضريبية")
        self.assertFalse(row.is_builtin)
        self.assertTrue(row.code)
        # وكودُه لا يصطدم بكودٍ قائم — الفرادةُ (tenant, code) في القاعدة.
        second = services.create_office_service(self.tenant, name="اعتراضات ضريبية")
        self.assertNotEqual(row.code, second.code)

    def test_the_generated_code_skips_one_that_already_exists(self):
        """التصادم: كودٌ مولَّدٌ مأخوذٌ يُعاد توليده — لا `IntegrityError` من القاعدة."""
        OfficeService.objects.create(
            tenant=self.tenant, code="custom-aaaaaaaa", name="كودٌ محجوز",
        )
        taken = mock.Mock()
        taken.hex = "aaaaaaaa11112222"
        free = mock.Mock()
        free.hex = "bbbbbbbb33334444"
        with mock.patch.object(services, "uuid4", side_effect=[taken, free]):
            row = services.create_office_service(self.tenant, name="خدمة جديدة")
        self.assertEqual(row.code, "custom-bbbbbbbb")

    def test_the_catalog_list_seeds_the_defaults(self):
        other = create_company("مكتبٌ جديد", self.owner, template="accounting_office")
        invalidate_module_cache(other.pk)
        self.assertEqual(OfficeService.objects.filter(tenant=other).count(), 0)
        payload = services.services_catalog_payload(other)
        self.assertEqual(len(payload), 5)
        self.assertEqual(OfficeService.objects.filter(tenant=other).count(), 5)


class FrequencyHistoryTest(OfficeTestCase):
    """**التغيير يسري من تاريخٍ ولقدّام** — الاختبارُ القاطع في التذكرة."""

    def setUp(self):
        self.today = timezone.localdate()
        # بدايةُ الخدمة و«نيسان» اللذان يقعان في ماضيها: التاريخُ في القاعدة حقيقة،
        # فيُبنى الاختبار عليه لا على سنةٍ تُكتَب فيُتعفّن بمرور الزمن.
        self.start = self.today - datetime.timedelta(days=300)
        self.april = self.today - datetime.timedelta(days=90)
        self.service = catalog(self.tenant)["vat"]
        self.row = services.add_client_service(
            client=self.client_row,
            service=self.service,
            starts_on=self.start,
            responsible_from=self.start,
            frequency="monthly",
        )

    def test_changing_the_frequency_from_april_does_not_change_march(self):
        services.change_client_service_frequency(
            self.row, frequency="quarterly", effective_from=self.april,
        )
        before = self.april - datetime.timedelta(days=1)
        self.assertEqual(services.frequency_on(self.row, before).frequency, "monthly")
        self.assertEqual(services.frequency_on(self.row, self.start).frequency, "monthly")
        self.assertEqual(services.frequency_on(self.row, self.april).frequency, "quarterly")
        self.assertEqual(services.frequency_on(self.row, self.today).frequency, "quarterly")

    def test_the_old_row_is_never_edited_it_stays_in_the_history(self):
        services.change_client_service_frequency(
            self.row, frequency="annual", effective_from=self.april,
        )
        rows = list(self.row.frequencies.order_by("effective_from"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].effective_from, self.start)
        self.assertEqual(rows[0].frequency, "monthly")
        # والاقتراحُ وقت الإضافة محفوظٌ للتمييز بين «قبله» و«غيّره»: مبيعاتٌ تحت
        # السقف تقترح «كل شهرين»، والموظف اختار «شهري».
        self.assertEqual(rows[0].suggested, "bimonthly")

    def test_a_frequency_change_before_the_start_is_rejected(self):
        with self.assertRaises(ValidationError):
            services.change_client_service_frequency(
                self.row, frequency="annual",
                effective_from=self.start - datetime.timedelta(days=1),
            )

    def test_a_duplicate_past_date_is_rejected(self):
        with self.assertRaises(ValidationError):
            services.change_client_service_frequency(
                self.row, frequency="annual", effective_from=self.start,
            )

    def test_a_duplicate_future_date_replaces_its_row_only(self):
        future = self.today + datetime.timedelta(days=60)
        services.change_client_service_frequency(
            self.row, frequency="annual", effective_from=future,
        )
        services.change_client_service_frequency(
            self.row, frequency="quarterly", effective_from=future,
        )
        self.assertEqual(self.row.frequencies.count(), 2)
        self.assertEqual(services.frequency_on(self.row, future).frequency, "quarterly")


class StopServiceTest(OfficeTestCase):
    def test_a_stopped_service_stays_in_the_history_with_its_date(self):
        # «موقوفة» نسبةً لليوم ⇒ الإيقافُ في ماضٍ نسبيّ لا في تاريخٍ مطلق.
        today = timezone.localdate()
        ended = today - datetime.timedelta(days=30)
        row = services.add_client_service(
            client=self.client_row,
            service=catalog(self.tenant)["payroll"],
            starts_on=today - datetime.timedelta(days=120),
        )
        services.stop_client_service(row, ends_on=ended)

        fresh = ClientService.objects.get(pk=row.pk)
        self.assertEqual(fresh.ends_on, ended)
        entry = services.client_services_payload(
            self.client_row, user=self.owner,
        )["services"][0]
        self.assertFalse(entry["is_active"])
        self.assertEqual(entry["status_label"], "موقوفة")
        self.assertEqual(entry["ends_on"], ended.isoformat())

    def test_the_stop_date_cannot_precede_the_start(self):
        row = services.add_client_service(
            client=self.client_row,
            service=catalog(self.tenant)["payroll"],
            starts_on=datetime.date(2026, 3, 1),
        )
        with self.assertRaises(ValidationError):
            services.stop_client_service(row, ends_on=datetime.date(2026, 2, 28))

    def test_a_service_is_not_re_added_while_active_but_is_after_stopping(self):
        payroll = catalog(self.tenant)["payroll"]
        row = services.add_client_service(
            client=self.client_row, service=payroll,
            starts_on=datetime.date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            services.add_client_service(
                client=self.client_row, service=payroll,
                starts_on=datetime.date(2026, 5, 1),
            )
        services.stop_client_service(row, ends_on=datetime.date(2026, 4, 30))
        again = services.add_client_service(
            client=self.client_row, service=payroll,
            starts_on=datetime.date(2026, 5, 1),
        )
        self.assertNotEqual(again.pk, row.pk)

    def test_a_frequency_cannot_change_after_the_stop_date(self):
        """خدمةٌ موقوفة لا تُعدَّل دوريتها **بعد** `ends_on` — والحدُّ نفسه مسموح."""
        row = services.add_client_service(
            client=self.client_row,
            service=catalog(self.tenant)["bookkeeping"],
            starts_on=datetime.date(2026, 1, 1),
            frequency="monthly",
        )
        services.stop_client_service(row, ends_on=datetime.date(2026, 6, 30))
        with self.assertRaises(ValidationError):
            services.change_client_service_frequency(
                row, frequency="annual", effective_from=datetime.date(2026, 7, 1),
            )
        self.assertEqual(row.frequencies.count(), 1)

        services.change_client_service_frequency(
            row, frequency="annual", effective_from=datetime.date(2026, 6, 30),
        )
        self.assertEqual(
            services.frequency_on(row, datetime.date(2026, 6, 30)).frequency, "annual",
        )
        self.assertEqual(row.frequencies.count(), 2)

    def test_a_future_stop_date_leaves_the_service_active_today(self):
        """«تنتهي في 31/12» ليست «موقوفة» اليوم — الحالةُ نسبةً لليوم لا لوجود تاريخ."""
        today = timezone.localdate()
        row = services.add_client_service(
            client=self.client_row,
            service=catalog(self.tenant)["consulting"],
            starts_on=today - datetime.timedelta(days=30),
            frequency="on_demand",
        )
        future = today + datetime.timedelta(days=30)
        services.stop_client_service(row, ends_on=future)

        entry = services.client_services_payload(
            self.client_row, user=self.owner,
        )["services"][0]
        self.assertTrue(entry["is_active"])
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["status_label"], "نشطة")
        self.assertEqual(entry["ends_on"], future.isoformat())
        # وقبل اليوم التالي لـ`ends_on` تبقى نشطة، ثم تصير موقوفة.
        self.assertEqual(row.status_on(future), "active")
        self.assertEqual(
            row.status_on(future + datetime.timedelta(days=1)), "stopped",
        )

    def test_adding_before_or_on_the_stop_date_is_refused_but_after_it_is_allowed(self):
        """الإيقافُ المستقبليّ لا يفتح فترةً متداخلة — كان `ends_on__isnull` يفتحها."""
        payroll = catalog(self.tenant)["payroll"]
        row = services.add_client_service(
            client=self.client_row, service=payroll,
            starts_on=datetime.date(2026, 1, 1),
        )
        services.stop_client_service(row, ends_on=datetime.date(2026, 6, 30))
        for starts_on in (datetime.date(2026, 6, 1), datetime.date(2026, 6, 30)):
            with self.subTest(starts_on=starts_on.isoformat()):
                with self.assertRaises(ValidationError):
                    services.add_client_service(
                        client=self.client_row, service=payroll,
                        starts_on=starts_on,
                    )
        allowed = services.add_client_service(
            client=self.client_row, service=payroll,
            starts_on=datetime.date(2026, 7, 1),
        )
        self.assertEqual(allowed.starts_on, datetime.date(2026, 7, 1))

    def test_a_service_cannot_be_stopped_twice(self):
        """الإيقافُ مرّةٌ واحدة: كتابةُ تاريخٍ ثانٍ كانت تمحو الأول بلا أثر."""
        row = services.add_client_service(
            client=self.client_row,
            service=catalog(self.tenant)["payroll"],
            starts_on=datetime.date(2026, 1, 1),
        )
        services.stop_client_service(row, ends_on=datetime.date(2026, 6, 30))
        with self.assertRaises(ValidationError):
            services.stop_client_service(row, ends_on=datetime.date(2026, 7, 31))
        self.assertEqual(
            ClientService.objects.get(pk=row.pk).ends_on, datetime.date(2026, 6, 30),
        )

    def test_the_stop_date_cannot_precede_a_recorded_frequency_change(self):
        row = services.add_client_service(
            client=self.client_row,
            service=catalog(self.tenant)["bookkeeping"],
            starts_on=datetime.date(2026, 1, 1),
        )
        services.change_client_service_frequency(
            row, frequency="annual", effective_from=datetime.date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            services.stop_client_service(row, ends_on=datetime.date(2026, 8, 31))
        services.stop_client_service(row, ends_on=datetime.date(2026, 9, 1))
        self.assertEqual(
            ClientService.objects.get(pk=row.pk).ends_on, datetime.date(2026, 9, 1),
        )


class PackageTest(OfficeTestCase):
    """الباقةُ تقرأ الخدمات ثم تنسخ — وبعدها لا يمسّ أحدُ الطرفين الآخر."""

    def setUp(self):
        self.today = timezone.localdate()
        self.package = ServicePackage.objects.create(
            tenant=self.tenant, name="باقة صغيرة", suggested_price=Decimal("900.00"),
        )
        self.package.services.set([
            catalog(self.tenant)["bookkeeping"],
            catalog(self.tenant)["vat"],
            catalog(self.tenant)["payroll"],
        ])

    def test_the_package_fills_the_client_services(self):
        result = services.apply_package(self.client_row, self.package)
        self.assertEqual(len(result["added"]), 3)
        self.assertEqual(result["skipped"], [])
        self.assertEqual(ClientService.objects.filter(client=self.client_row).count(), 3)
        # كلُّ صفٍّ وله دوريتُه الأولى مؤرَّخةً من يوم البدء.
        for row in ClientService.objects.filter(client=self.client_row):
            self.assertEqual(row.frequencies.count(), 1)
            self.assertEqual(
                row.frequencies.get().effective_from, row.starts_on,
            )

    def test_a_service_the_client_already_has_is_skipped_not_duplicated(self):
        vat = catalog(self.tenant)["vat"]
        existing = services.add_client_service(
            client=self.client_row, service=vat,
            starts_on=datetime.date(2026, 1, 1),
        )
        result = services.apply_package(self.client_row, self.package)
        self.assertEqual(len(result["added"]), 2)
        self.assertEqual(
            [entry["service_id"] for entry in result["skipped"]], [existing.service_id],
        )
        self.assertEqual(
            ClientService.objects.filter(
                client=self.client_row, service=existing.service,
            ).count(),
            1,
        )

    def test_a_package_re_adds_a_service_the_client_had_stopped(self):
        """«ليست نشطةً عند الزبون» تشمل الموقوفة: التطبيقُ يُعيدها بتاريخٍ جديد."""
        vat = catalog(self.tenant)["vat"]
        stopped = services.add_client_service(
            client=self.client_row, service=vat,
            starts_on=datetime.date(2026, 1, 1),
        )
        services.stop_client_service(stopped, ends_on=datetime.date(2026, 3, 31))

        result = services.apply_package(self.client_row, self.package)

        self.assertIn(vat.pk, [entry["service_id"] for entry in result["added"]])
        self.assertEqual(
            ClientService.objects.filter(
                client=self.client_row, service=vat,
            ).count(),
            2,
        )
        # واحدةٌ موقوفةٌ في التاريخ وأخرى نشطةٌ الآن — لا صفٌّ يُطوى ولا يتضاعف.
        self.assertEqual(
            ClientService.objects.filter(
                client=self.client_row, service=vat, ends_on__isnull=True,
            ).count(),
            1,
        )

    def test_a_service_without_a_suggestion_falls_to_on_demand(self):
        """فرعُ `None` **فعلاً**: فلسطينيٌّ غيرُ مسجّل ⇒ لا اقتراح ⇒ «عند الطلب».

        لا `consulting` (اقتراحُها `on_demand` أصلاً) — ذاك كان يمرّ بلا أن يمسّ
        فرعَ «لا اقتراح».
        """
        client = make_client(
            self.tenant, "غير مسجّل", vat_classification="unregistered",
        )
        services.set_client_setting(client, "tax_system", "PS")
        package = ServicePackage.objects.create(tenant=self.tenant, name="ق.م بلا اقتراح")
        package.services.set([catalog(self.tenant)["vat"]])

        result = services.apply_package(client, package)

        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(result["added"][0]["frequency"], "on_demand")
        row = ClientService.objects.get(client=client)
        self.assertEqual(services.frequency_on(row, self.today).frequency, "on_demand")
        # ولا اقتراحَ محفوظ: الفرعُ كان `None`، لا `on_demand` مقترحاً.
        self.assertEqual(row.frequencies.get().suggested, "")

    def test_a_disabled_package_service_is_reported_not_silently_dropped(self):
        """المعطَّلةُ في الكتالوج تُبلَّغ بسببها — كانت تختفي من الردّ كلَّه."""
        consulting = catalog(self.tenant)["consulting"]
        services.update_office_service(consulting, is_active=False)
        package = ServicePackage.objects.create(tenant=self.tenant, name="باقة فيها معطَّلة")
        package.services.set([consulting])

        result = services.apply_package(self.client_row, package)

        self.assertEqual(result["added"], [])
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["service_id"], consulting.pk)
        self.assertEqual(result["skipped"][0]["reason"], "معطَّلة في كتالوج المكتب")
        self.assertFalse(
            ClientService.objects.filter(
                client=self.client_row, service=consulting,
            ).exists(),
        )

    def test_a_future_stopped_service_is_skipped_as_overlapping(self):
        """إيقافٌ مستقبليّ لا يفتح فترةً متداخلة — التطبيقُ يتخطّى ويقول السبب."""
        vat = catalog(self.tenant)["vat"]
        row = services.add_client_service(
            client=self.client_row, service=vat,
            starts_on=datetime.date(2026, 1, 1),
        )
        services.stop_client_service(
            row, ends_on=self.today + datetime.timedelta(days=30),
        )

        result = services.apply_package(self.client_row, self.package)

        skipped = {entry["service_id"]: entry["reason"] for entry in result["skipped"]}
        self.assertIn(vat.pk, skipped)
        self.assertIn("متداخلة", skipped[vat.pk])
        self.assertEqual(
            ClientService.objects.filter(
                client=self.client_row, service=vat,
            ).count(),
            1,
        )

    def test_a_package_linked_to_another_offices_service_is_refused_whole(self):
        """دفاعٌ في العمق: `_insert_client_service` يفحص شركة الخدمة لا الباقةَ وحدها."""
        other = create_company("مكتبٌ آخر", self.owner, template="accounting_office")
        invalidate_module_cache(other.pk)
        foreign = catalog(other)["vat"]
        package = ServicePackage.objects.create(tenant=self.tenant, name="باقة مُلوَّثة")
        # الربطُ برمجيٌّ يتجاوز الـserializer الذي يرفض هذا أصلاً.
        package.services.set([catalog(self.tenant)["bookkeeping"], foreign])

        with self.assertRaises(ValidationError):
            services.apply_package(self.client_row, package)

        self.assertFalse(ClientService.objects.filter(client=self.client_row).exists())

    def test_editing_the_client_services_does_not_change_the_package(self):
        services.apply_package(self.client_row, self.package)
        row = ClientService.objects.filter(client=self.client_row).first()
        services.stop_client_service(
            row, ends_on=self.today + datetime.timedelta(days=30),
        )
        self.assertEqual(self.package.services.count(), 3)
        self.assertEqual(
            ServicePackage.objects.get(pk=self.package.pk).services.count(), 3,
        )

    def test_editing_the_package_does_not_change_the_client_services(self):
        services.apply_package(self.client_row, self.package)
        before = ClientService.objects.filter(client=self.client_row).count()
        self.package.services.set([catalog(self.tenant)["consulting"]])
        self.assertEqual(
            ClientService.objects.filter(client=self.client_row).count(), before,
        )
        self.assertFalse(
            ClientService.objects.filter(
                client=self.client_row, service__code="consulting",
            ).exists(),
        )


class SuggestFrequencyTest(OfficeTestCase):
    """الاقتراح من البطاقة ومن السقف المؤرَّخ — لا رقمٍ في الكود."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        ps_tenant = create_company(
            "مكتب فلسطين", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(ps_tenant.pk)
        ready_office(ps_tenant, "PS")
        cls.ps_tenant = ps_tenant

        # مبيعاتٌ بين سقف 2026 وسقف 2027: شهريّ في 2026 وكل شهرين في 2027.
        cls.il_between = make_client(
            cls.tenant, "إسرائيلي بين السقفين",
            annual_sales=Decimal("1800000"), vat_classification="authorized",
        )
        cls.il_exempt = make_client(
            cls.tenant, "עוסק פטור", vat_classification="exempt",
        )
        # معفى تجاوز سقف עוסק פטור (122,833 لسنة 2026) — تصنيفُه موضعُ مراجعة.
        cls.il_exempt_over = make_client(
            cls.tenant, "עוסק פטור فوق السقف",
            annual_sales=Decimal("150000"), vat_classification="exempt",
        )
        cls.ps_licensed = make_client(
            ps_tenant, "فلسطيني مرخّص", vat_classification="licensed",
        )
        cls.ps_exempt = make_client(
            ps_tenant, "فلسطيني معفى", vat_classification="exempt",
        )
        cls.ps_unregistered = make_client(
            ps_tenant, "فلسطيني غير مسجّل", vat_classification="unregistered",
        )

    def test_israeli_between_the_two_ceilings_is_monthly_in_2026(self):
        frequency, _reason = services.suggest_frequency(
            self.il_between, "vat", datetime.date(2026, 12, 31),
        )
        self.assertEqual(frequency, "monthly")

    def test_the_same_client_is_bimonthly_in_2027(self):
        frequency, _reason = services.suggest_frequency(
            self.il_between, "vat", datetime.date(2027, 1, 15),
        )
        self.assertEqual(frequency, "bimonthly")

    def test_an_authorized_dealer_below_the_ceiling_reports_bimonthly(self):
        frequency, _reason = services.suggest_frequency(
            self.client_row, "vat", datetime.date(2026, 6, 1),
        )
        self.assertEqual(frequency, "bimonthly")

    def test_israeli_exempt_dealer_declares_annually(self):
        frequency, reason = services.suggest_frequency(
            self.il_exempt, "vat", datetime.date(2026, 6, 1),
        )
        self.assertEqual(frequency, "annual")
        self.assertIn("עוסק פטור", reason)
        # تحت السقف: لا تحذير — الصمتُ هنا جزءٌ من العقد.
        self.assertNotIn("راجع التصنيف", reason)

    def test_an_exempt_dealer_over_the_ceiling_is_flagged_without_numbers(self):
        """سقفُ עוסק פטור يُقرأ لا يُترك خاملاً: تجاوزُه تحذيرٌ بلا أرقام مبالغ."""
        frequency, reason = services.suggest_frequency(
            self.il_exempt_over, "vat", datetime.date(2026, 6, 1),
        )
        self.assertEqual(frequency, "annual")
        self.assertIn("راجع التصنيف", reason)
        self.assertIn("2026", reason)
        for amount in ("122833", "122,833", "150000", "150,000"):
            with self.subTest(amount=amount):
                self.assertNotIn(amount, reason)

    def test_a_year_without_an_exempt_ceiling_marks_the_warning_estimated(self):
        """السقوفُ المؤرَّخة نفسها: سنةٌ بلا صفٍّ تأخذ آخر سابق وتقول «تقديري»."""
        frequency, reason = services.suggest_frequency(
            self.il_exempt_over, "vat", datetime.date(2030, 6, 1),
        )
        self.assertEqual(frequency, "annual")
        self.assertIn("راجع التصنيف", reason)
        self.assertIn("تقديري", reason)
        self.assertIn("2026", reason)

    def test_an_authorized_dealer_without_sales_is_told_so(self):
        """صفرُ مبيعاتٍ ليس «في حدوده»: النتيجةُ نفسها والسببُ يقول الحقيقة."""
        no_sales = make_client(
            self.tenant, "بلا مبيعات", vat_classification="authorized",
        )
        frequency, reason = services.suggest_frequency(
            no_sales, "vat", datetime.date(2026, 6, 1),
        )
        self.assertEqual(frequency, "bimonthly")
        self.assertIn("لا مبيعات سنوية في البطاقة", reason)
        self.assertNotIn("في حدوده", reason)

    def test_a_year_before_the_oldest_ceiling_has_no_suggestion(self):
        """سنةٌ قبل أقدم سقف: لا سقفَ سابقٌ يُستعار ⇒ `None` وسببُه."""
        frequency, reason = services.suggest_frequency(
            self.il_between, "vat", datetime.date(2025, 6, 1),
        )
        self.assertIsNone(frequency)
        self.assertIn("لا سقف", reason)
        # وبلا دوريةٍ مُرسَلةٍ تُرفض الإضافةُ بطلب اختيارٍ صريح.
        with self.assertRaises(ValidationError):
            services.add_client_service(
                client=self.il_between, service=catalog(self.tenant)["vat"],
                starts_on=datetime.date(2025, 6, 1),
            )

    def test_a_year_without_a_published_ceiling_uses_the_last_one_and_says_estimated(self):
        frequency, reason = services.suggest_frequency(
            self.il_between, "vat", datetime.date(2030, 3, 1),
        )
        # آخر سقفٍ منشور قبل 2030 هو سقف 2027، و1,800,000 دونه ⇒ كل شهرين.
        self.assertEqual(frequency, "bimonthly")
        self.assertIn("تقديري", reason)
        self.assertIn("2027", reason)

    def test_the_reason_carries_no_amount(self):
        _frequency, reason = services.suggest_frequency(
            self.il_between, "vat", datetime.date(2026, 6, 1),
        )
        self.assertNotIn("1775000", reason)
        self.assertNotIn("1,775,000", reason)
        self.assertNotIn("1800000", reason)
        self.assertNotIn("1,800,000", reason)
        # ويذكر النظام والتصنيف — مصدرُ التسميات سجلُّ البطاقة لا نسخةٌ هنا.
        self.assertIn("إسرائيلي", reason)
        self.assertIn("עוסק מורשה", reason)

    def test_palestinian_licensed_dealer_reports_monthly(self):
        self.assertEqual(
            services.suggest_frequency(
                self.ps_licensed, "vat", datetime.date(2026, 6, 1),
            )[0],
            "monthly",
        )

    def test_palestinian_exempt_dealer_reports_monthly(self):
        self.assertEqual(
            services.suggest_frequency(
                self.ps_exempt, "vat", datetime.date(2026, 6, 1),
            )[0],
            "monthly",
        )

    def test_palestinian_unregistered_gets_no_suggestion(self):
        frequency, reason = services.suggest_frequency(
            self.ps_unregistered, "vat", datetime.date(2026, 6, 1),
        )
        self.assertIsNone(frequency)
        self.assertIn("غير مسجّل", reason)

    def test_the_non_vat_services_follow_their_nature(self):
        today = datetime.date(2026, 6, 1)
        self.assertEqual(
            services.suggest_frequency(self.client_row, "payroll", today)[0], "monthly",
        )
        self.assertEqual(
            services.suggest_frequency(self.client_row, "bookkeeping", today)[0],
            "monthly",
        )
        self.assertEqual(
            services.suggest_frequency(self.client_row, "annual_accounts", today)[0],
            "annual",
        )
        self.assertEqual(
            services.suggest_frequency(self.client_row, "consulting", today)[0],
            "on_demand",
        )

    def test_a_service_the_office_added_is_on_demand(self):
        added = services.create_office_service(self.tenant, name="اعتراضات")
        self.assertEqual(
            services.suggest_frequency(
                self.client_row, added.code, datetime.date(2026, 6, 1),
            )[0],
            "on_demand",
        )

    def test_the_suggestion_follows_the_client_tax_system_not_the_office(self):
        """زبونٌ إسرائيليّ في مكتبٍ فلسطينيّ: الحكم بطاقته لا إعداد المكتب."""
        client = make_client(
            self.ps_tenant, "زبون بطاقته إسرائيلية",
            annual_sales=Decimal("300000"), vat_classification="authorized",
        )
        services.set_client_setting(client, "tax_system", "IL")
        self.assertEqual(
            services.suggest_frequency(
                client, "vat", datetime.date(2026, 6, 1),
            )[0],
            "bimonthly",
        )


class ServicesApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        cls.owner = User.objects.create_user(username="svc_api_owner", password="x")
        cls.tenant = create_company(
            "مكتب خدمات الـAPI", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("svc_api_accountant", "accountant")
        cls.colleague = member("svc_api_colleague", "accountant")
        cls.viewer = member("svc_api_viewer", "viewer")
        # مديرُ مكتبٍ يملك مفاتيح المكتب كلَّها — يُسحب منه «يرى المبالغ» بتجاوز
        # عضوٍ في اختبار القناع، فيبقى مفتاحُ الإعدادات ممرّاً للكتابة.
        cls.office_manager = member("svc_api_office_manager", "office_manager")

        cls.mine = make_client(
            cls.tenant, "زبون المحاسب", responsible=cls.accountant,
            annual_sales=Decimal("1800000"), vat_classification="authorized",
        )
        cls.other = make_client(
            cls.tenant, "زبون الزميل", responsible=cls.colleague,
        )
        # القارئُ بلا `office.clients.all` لا يرى إلا زبونه — كسائر نقاط #272.
        cls.viewed = make_client(
            cls.tenant, "زبون القارئ", responsible=cls.viewer,
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def post(self, path, payload=None):
        return self.client.post(path, payload or {}, format="json", **self.headers())

    def add_service(self, client, code="vat", **extra):
        body = {"service": catalog(self.tenant)[code].pk, **extra}
        return self.post(f"{CLIENTS}{client.pk}/services/", body)


class ServicesVisibilityTest(ServicesApiTest):
    def test_someone_elses_client_is_404_on_every_service_point(self):
        self.as_user(self.accountant)
        foreign = self.other.pk
        for path in ("services/", "services/suggest/?service=vat"):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(
                        f"{CLIENTS}{foreign}/{path}", **self.headers(),
                    ).status_code,
                    404,
                )
        self.assertEqual(self.add_service(self.other).status_code, 404)
        self.assertEqual(
            self.post(f"{CLIENTS}{foreign}/services/1/frequency/", {
                "frequency": "annual", "effective_from": "2026-05-01",
            }).status_code,
            404,
        )
        self.assertEqual(
            self.post(f"{CLIENTS}{foreign}/services/1/stop/", {
                "ends_on": "2026-05-01",
            }).status_code,
            404,
        )
        self.assertEqual(
            self.post(f"{CLIENTS}{foreign}/apply-package/", {"package": 1}).status_code,
            404,
        )

    def test_the_reader_role_is_refused_every_write(self):
        """يثبت منعَ **الدور**: `TenantRolePermission` يردّ 403 للقارئ على كل كتابة.

        الهدفُ زبونُ القارئ نفسه (`viewed`) كي لا يرجع 404 بدل 403 لو تجاوز الطلبُ
        حارسَ الدور. أمّا حارسُ **مفتاح المكتب** فيثبته `ServicesPermissionsTest`.
        """
        self.as_user(self.viewer)
        mine = self.viewed.pk
        self.assertEqual(self.add_service(self.viewed).status_code, 403)
        self.assertEqual(
            self.post(f"{CLIENTS}{mine}/services/1/frequency/", {
                "frequency": "annual", "effective_from": "2026-05-01",
            }).status_code,
            403,
        )
        self.assertEqual(
            self.post(f"{CLIENTS}{mine}/services/1/stop/", {
                "ends_on": "2026-05-01",
            }).status_code,
            403,
        )
        self.assertEqual(
            self.post(f"{CLIENTS}{mine}/apply-package/", {"package": 1}).status_code,
            403,
        )
        self.assertEqual(self.post(SERVICES, {"name": "خدمة جديدة"}).status_code, 403)
        self.assertEqual(self.post(PACKAGES, {"name": "باقة"}).status_code, 403)

    def test_the_reader_reads_the_catalog_and_the_client_services(self):
        self.as_user(self.viewer)
        self.assertEqual(self.client.get(SERVICES, **self.headers()).status_code, 200)
        res = self.client.get(
            f"{CLIENTS}{self.viewed.pk}/services/", **self.headers(),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            [choice["value"] for choice in res.data["frequency_choices"]],
            ["monthly", "bimonthly", "quarterly", "annual", "on_demand"],
        )
        self.assertEqual(res.data["frequency_choices"][0]["label"], "شهري")


class ServicesPermissionsTest(ServicesApiTest):
    """**كلُّ كتابةٍ تُحرَس بمفتاحها لا بدورٍ يمنع الكتابة كلَّها.**

    القارئُ (`viewer`) يمنعه `core.permissions.TenantRolePermission` من كل كتابةٍ
    في المنصّة قبل أن تصل النقطة، فاختبارُه لا يُثبت أن مفتاحَ المكتب هو الحارس.
    هنا عضوان **يكتبان فعلاً**: محاسبٌ يملك `office.clients.write` ولا يملك
    `office.settings.manage`، وعضوٌ مبيعاتٍ مُنح `office.clients.all` (فيرى
    الزبون) ولا يملك مفتاحَ الكتابة — فيسقط هذان الاختباران إن أُزيل الحارس.
    """

    def test_an_accountant_cannot_write_the_catalog_or_the_packages(self):
        self.as_user(self.accountant)
        self.assertEqual(
            self.post(SERVICES, {"name": "خدمة المحاسب"}).status_code, 403,
        )
        package = ServicePackage.objects.create(
            tenant=self.tenant, name="باقة المحاسب",
        )
        self.assertEqual(
            self.client.patch(
                f"{SERVICES}{catalog(self.tenant)['vat'].pk}/",
                {"is_active": False}, format="json", **self.headers(),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"{PACKAGES}{package.pk}/", {"name": "اسم مسروق"},
                format="json", **self.headers(),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"{PACKAGES}{package.pk}/", **self.headers()).status_code,
            403,
        )
        # ولا شيءَ كُتب: الرفضُ قبل الخدمة لا بعدها.
        self.assertFalse(OfficeService.objects.filter(name="خدمة المحاسب").exists())
        package.refresh_from_db()
        self.assertEqual(package.name, "باقة المحاسب")

    def test_a_member_who_sees_the_client_without_the_write_key_is_refused(self):
        sales = User.objects.create_user(username="svc_api_sales", password="x")
        membership = UserCompanyMembership.objects.create(
            user=sales, tenant=self.tenant, role="sales",
        )
        # «يرى زبائن غيره» وحدها: فيرى الزبون ويصل إلى النقطة، ولا يكتبها.
        MemberPermission.objects.create(
            membership=membership, permission_key="office.clients.all", allowed=True,
        )
        self.as_user(sales)
        self.assertEqual(
            self.client.get(
                f"{CLIENTS}{self.mine.pk}/services/", **self.headers(),
            ).status_code,
            200,
        )
        self.assertEqual(self.add_service(self.mine).status_code, 403)
        self.assertFalse(ClientService.objects.filter(client=self.mine).exists())


class ServicesAmountsTest(ServicesApiTest):
    def test_suggested_price_is_null_for_a_member_without_the_amounts_key(self):
        self.as_user(self.owner)
        created = self.post(PACKAGES, {
            "name": "باقة بمبلغ", "suggested_price": "1750.00",
            "services": [catalog(self.tenant)["vat"].pk],
        })
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["suggested_price"], "1750.00")

        self.as_user(self.accountant)
        rows = self.client.get(PACKAGES, **self.headers()).data
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["suggested_price"])
        self.assertTrue(rows[0]["services"])

    def test_writing_a_price_without_the_amounts_key_is_403(self):
        """**مفتاحُ الإعدادات يمرّ والقناعُ يردّ** — لا دورٌ يمنع الكتابة كلَّها.

        `office_manager` يملك مفاتيح المكتب كلَّها، فيُسحب منه «يرى المبالغ» بتجاوز
        عضوٍ صريح: لو حُذف `reject_amount_writes` لمرّت الكتابةُ 201/200 وسقط
        الاختبار. (القارئُ لا يصل إلى هنا أصلاً — `TenantRolePermission` يمنع كل
        كتابةٍ لدور `viewer`، فاختبارُه لا يُثبت حارسَ المبلغ.)
        """
        membership = UserCompanyMembership.objects.get(
            user=self.office_manager, tenant=self.tenant,
        )
        MemberPermission.objects.create(
            membership=membership,
            permission_key="office.amounts.view", allowed=False,
        )
        self.as_user(self.office_manager)

        created = self.post(PACKAGES, {
            "name": "باقة بلا رؤية", "suggested_price": "99.00",
        })
        self.assertEqual(created.status_code, 403)
        self.assertFalse(ServicePackage.objects.exists())

        package = ServicePackage.objects.create(tenant=self.tenant, name="باقة القناع")
        patched = self.client.patch(
            f"{PACKAGES}{package.pk}/", {"suggested_price": "50.00"},
            format="json", **self.headers(),
        )
        self.assertEqual(patched.status_code, 403)
        package.refresh_from_db()
        self.assertIsNone(package.suggested_price)

        # واسمٌ وحده يمرّ: القناعُ على المبلغ لا على الباقة كلّها.
        renamed = self.client.patch(
            f"{PACKAGES}{package.pk}/", {"name": "باقة مُعاد تسميتها"},
            format="json", **self.headers(),
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.data["name"], "باقة مُعاد تسميتها")


class PackagesQueryCountTest(OfficeTestCase):
    """قائمةُ الباقات: قرارُ القناع مرّةً واحدة — العددُ لا يكبر بعدد الباقات."""

    def _queries_for(self, count):
        ServicePackage.objects.all().delete()
        for index in range(count):
            package = ServicePackage.objects.create(
                tenant=self.tenant, name=f"باقة {index}",
                suggested_price=Decimal("10.00"),
            )
            package.services.set([catalog(self.tenant)["vat"]])
        with CaptureQueriesContext(connection) as captured:
            rows = services.packages_payload(self.tenant, user=self.owner)
        self.assertEqual(len(rows), count)
        return len(captured)

    def test_the_query_count_does_not_grow_with_the_packages(self):
        self.assertEqual(self._queries_for(1), self._queries_for(3))


class ServicesApiFlowTest(ServicesApiTest):
    def test_adding_a_service_uses_the_suggestion_when_the_frequency_is_omitted(self):
        self.as_user(self.owner)
        res = self.add_service(self.mine, starts_on="2026-01-01")
        self.assertEqual(res.status_code, 201)
        entry = res.data["services"][0]
        self.assertEqual(entry["frequency"], "monthly")
        # «من أيّ فترةٍ المكتب مسؤول» افتراضُها أولُ الشهر الحالي.
        self.assertEqual(
            entry["responsible_from"],
            timezone.localdate().replace(day=1).isoformat(),
        )

    def test_responsible_from_is_stored_as_the_first_of_the_month(self):
        """إرسالُ 17/5 يُخزَّن 1/5 — المكتبُ مسؤولٌ عن فترةٍ كاملة أو لا."""
        self.as_user(self.owner)
        res = self.add_service(
            self.mine, starts_on="2026-01-01", responsible_from="2026-05-17",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["services"][0]["responsible_from"], "2026-05-01")
        stored = ClientService.objects.get(client=self.mine)
        self.assertEqual(stored.responsible_from, datetime.date(2026, 5, 1))

    def test_the_suggestion_endpoint_answers_with_a_reason(self):
        self.as_user(self.owner)
        res = self.client.get(
            f"{CLIENTS}{self.mine.pk}/services/suggest/?service=vat&on=2027-02-01",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["frequency"], "bimonthly")
        self.assertTrue(res.data["reason"])
        self.assertEqual(res.data["frequency_choices"][0]["value"], "monthly")

    def test_a_missing_suggestion_demands_a_choice_instead_of_guessing(self):
        self.as_user(self.owner)
        unregistered = make_client(
            self.tenant, "غير مسجّل", responsible=self.accountant,
            vat_classification="unregistered",
        )
        # تصنيفٌ فلسطينيّ على زبونٍ في مكتبٍ إسرائيليّ: الحكم بطاقته وحده.
        services.set_client_setting(unregistered, "tax_system", "PS")
        res = self.add_service(unregistered)
        self.assertEqual(res.status_code, 400)
        self.assertIn("frequency", res.data)

    def test_the_api_records_the_frequency_history(self):
        self.as_user(self.owner)
        created = self.add_service(
            self.mine, starts_on="2026-01-01", responsible_from="2026-01-01",
            frequency="monthly",
        )
        service_id = created.data["services"][0]["id"]
        changed = self.post(f"{CLIENTS}{self.mine.pk}/services/{service_id}/frequency/", {
            "frequency": "quarterly", "effective_from": "2026-04-01",
        })
        self.assertEqual(changed.status_code, 200)
        entry = changed.data["services"][0]
        self.assertEqual(entry["frequency"], "quarterly")
        self.assertEqual(entry["frequency_from"], "2026-04-01")
        self.assertEqual(
            [row["frequency"] for row in entry["frequencies"]],
            ["monthly", "quarterly"],
        )

    def test_stopping_a_service_keeps_it_listed(self):
        self.as_user(self.owner)
        # «موقوفة» نسبةً لليوم ⇒ الإيقافُ في ماضٍ نسبيّ، والبدءُ قبله.
        today = timezone.localdate()
        started = today - datetime.timedelta(days=120)
        ended = today - datetime.timedelta(days=30)
        created = self.add_service(self.mine, starts_on=started.isoformat())
        service_id = created.data["services"][0]["id"]
        stopped = self.post(
            f"{CLIENTS}{self.mine.pk}/services/{service_id}/stop/",
            {"ends_on": ended.isoformat()},
        )
        self.assertEqual(stopped.status_code, 200)
        entry = stopped.data["services"][0]
        self.assertEqual(entry["ends_on"], ended.isoformat())
        self.assertEqual(entry["status_label"], "موقوفة")

    def test_applying_a_package_returns_what_was_added_and_what_was_skipped(self):
        self.as_user(self.owner)
        package = self.post(PACKAGES, {
            "name": "باقة البدء",
            "services": [
                catalog(self.tenant)["bookkeeping"].pk,
                catalog(self.tenant)["vat"].pk,
            ],
        })
        self.assertEqual(package.status_code, 201)
        self.add_service(self.mine)
        res = self.post(
            f"{CLIENTS}{self.mine.pk}/apply-package/", {"package": package.data["id"]},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["added"]), 1)
        self.assertEqual(len(res.data["skipped"]), 1)

    def test_the_office_can_add_a_service_and_toggle_it_but_not_delete_it(self):
        self.as_user(self.owner)
        created = self.post(SERVICES, {"name": "خدمة خاصة"})
        self.assertEqual(created.status_code, 201)
        self.assertFalse(created.data["is_builtin"])
        patched = self.client.patch(
            f"{SERVICES}{created.data['id']}/",
            {"is_active": False, "name": "خدمة خاصة معدّلة"},
            format="json",
            **self.headers(),
        )
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(patched.data["is_active"])
        self.assertEqual(patched.data["name"], "خدمة خاصة معدّلة")
        self.assertEqual(
            self.client.delete(
                f"{SERVICES}{created.data['id']}/", **self.headers(),
            ).status_code,
            405,
        )

    def test_a_package_is_deletable(self):
        self.as_user(self.owner)
        created = self.post(PACKAGES, {"name": "باقة تُحذف"})
        self.assertEqual(
            self.client.delete(
                f"{PACKAGES}{created.data['id']}/", **self.headers(),
            ).status_code,
            204,
        )

    def test_the_catalog_isolation_holds_between_two_offices(self):
        other = create_company("مكتب مغاير", self.owner, template="accounting_office")
        invalidate_module_cache(other.pk)
        mine = catalog(self.tenant)["vat"]
        self.as_user(self.owner)
        res = self.client.patch(
            f"{SERVICES}{mine.pk}/", {"name": "اسم مسروق"},
            format="json", HTTP_X_TENANT_ID=str(other.pk),
        )
        self.assertEqual(res.status_code, 404)
        mine.refresh_from_db()
        self.assertEqual(mine.name, "قيمة مضافة")
