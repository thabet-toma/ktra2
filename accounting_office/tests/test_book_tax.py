"""نسبُ المصاريف والإهلاك والإقفال — #287 (دفتر الزبون، الجزء ٢).

**ما يثبّته هذا الملفّ، بنداً ببندٍ من التذكرة:**

1. **لائحةُ المنصّة** (`book_rates.rates_payload`): كلُّ صفٍّ يحمل مصدرَه ومستوى
   دليله وتاريخَ سريانه، و«راجع» لا يُملأ بصمت — وصفٌّ بلا نصّ يبقى `rate=None`.
   وتعديلُ المكتب عليها **سجلٌّ إلحاقيّ**: قبلُ وبعدُ وسببٌ ومَن، وثانٍ لا يمحو
   الأوّل، وسببٌ فارغٌ 400.
2. **نسبتا حساب المصروف**: افتراضُهما 100% بلا تصنيف، ومن اللائحة بتصنيف،
   و**نسبةُ السطر المخالفة** لا تُكتب بلا إعدادٍ مفعّلٍ ولا بلا سبب.
3. **الإهلاكُ بالقسط الثابت**: أثاثٌ بـ10,000 في فلسطين ⇒ 1,000 للسنة (10%)،
   وفي إسرائيل ⇒ 600 (6%)؛ وصنفٌ «راجع» لا يُهلَّك ويُعلَن ناقصاً.
4. **المبلغُ من الدفتر**: ض.ق.م = مبيعات − مدخلاتٍ بنسبتها المعترف بها. الرقمُ من
   التذكرة: فاتورةُ أثاثٍ ضريبتُها 170 ونسبةُ حسابها 2/3 ⇒ يُخصم 113.33 والباقي
   كلفة؛ وبتصنيف الأثاث في لائحة المنصّة (100%) ⇒ تُخصم 100%. والمحسوبُ
   والمعدَّلُ يُحفظان كلٌّ على حدة، والموظفُ يؤكّد.
5. **الإقفال**: «انقدّم» يقفل فترةَ الدفتر (إعدادٌ مفعّل)، والإدخالُ داخلها 400
   برسالةٍ مسمّاة، والفتحُ للمدير/صاحب المكتب بسببٍ يُسجَّل — لا للمحاسب.
6. **نتيجةُ الفترة**: ربحٌ أخضر وخسارةٌ حمراء وحدٌّ رماديّ، وتظهر في سطر الدفتر
   (ملفّ الزبون) وفي إشعار الدفع لمن عنده دفتر.
7. **سقوفُ الإقرار السنوي**: تنبيهٌ لا رفض، يُحسب من مجموع البنود الموسومة،
   وسقفٌ «راجع» يُعلَن ولا يُسكَت عنه.
"""
import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import book_rates, book_reports, client_books, services
from accounting_office.models import (
    BOOK_KIND_DOUBLE,
    RATE_KIND_DEPRECIATION,
    RATE_KIND_INCOME,
    RATE_KIND_VAT,
    BookExpenseRate,
    BookExpenseRateChange,
    BookPeriodLock,
    ClientBook,
    ClientBookAccount,
    DeadlineRule,
    Obligation,
    PeriodTask,
)
from accounting_office.tests.test_client_books import (
    make_client,
    seed_book_account_templates,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
BOOKS = f"{BASE}client-books/"
OBLIGATIONS = f"{BASE}obligations/"
THIS_YEAR = timezone.localdate().year
JAN_START = datetime.date(THIS_YEAR, 1, 1)
JAN_END = datetime.date(THIS_YEAR, 1, 31)

#: هجرةُ البيانات التي تُزرع اللائحة — تُنادى كما ينادي `seed_book_account_templates`
#: هجرةَ الشجرة: قاعدةُ الاختبار تُنشئ الجداول من النماذج ولا تُشغّل الهجرات،
#: فبلا هذا النداء تكون اللائحةُ فارغةً ويمرّ الاختبارُ على لا شيء.
RATES_MIGRATION = "accounting_office.migrations.0022_book_rates_and_period_lock"


def seed_platform_rates():
    """اللائحةُ والسقوفُ **من هجرة البيانات نفسها** — لا زرعٌ يدويٌّ موازٍ لها."""
    migration = importlib.import_module(RATES_MIGRATION)
    migration.seed_rates(django_apps, None)


def rate_of(tax_system, code, kind) -> Decimal | None:
    """قيمةُ صفٍّ من لائحة المنصّة كما زُرعت بالهجرة — مرجعُ الأرقام في التوقّعات."""
    row = BookExpenseRate.objects.filter(
        tax_system=tax_system, code=code, rate_kind=kind,
    ).first()
    return None if row is None else row.rate


class RatesListTestCase(APITestCase):
    """لائحةُ المنصّة: المصدرُ والدليلُ والسريانُ و«راجع» (بند ١)."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="rt_owner", password="x")
        cls.tenant = create_company(
            "مكتب لائحة النسب", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def rates(self, system):
        res = self.client.get(
            f"{BOOKS}rates/", {"tax_system": system}, **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def test_every_value_carries_its_source_evidence_and_effective_date(self):
        for system in ("PS", "IL"):
            for row in self.rates(system)["rows"]:
                with self.subTest(system=system, row=row["code"] + "/" + row["rate_kind"]):
                    self.assertTrue(row["source_note"], "صفٌّ بلا نصٍّ حاكم")
                    self.assertIn(
                        row["evidence"], ("official", "secondary", "inferred"),
                    )
                    self.assertTrue(row["evidence_label"])
                    self.assertRegex(row["effective_from"], r"^\d{4}-\d{2}-\d{2}$")

    def test_a_review_value_is_never_filled_silently(self):
        """«راجع» بلا نصّ يبقى `None` — لا صفراً ولا تخميناً."""
        for system in ("PS", "IL"):
            for row in self.rates(system)["rows"]:
                if row["needs_review"] and row["rate"] is None:
                    self.assertFalse(row["usable"])
                if row["rate"] is None:
                    with self.subTest(system=system, row=row["code"] + "/" + row["rate_kind"]):
                        self.assertTrue(row["needs_review"])
                        self.assertFalse(row["usable"])

    def test_the_documented_numbers_are_the_ones_seeded(self):
        """أرقامُ البحث نفسها — والحرسُ على ما لا نصَّ عليه."""
        # الإهلاك: أثاث 6% إسرائيليّ و10% فلسطينيّ (#287/٣).
        self.assertEqual(rate_of("IL", "furniture", RATE_KIND_DEPRECIATION), Decimal("6"))
        self.assertEqual(rate_of("PS", "furniture", RATE_KIND_DEPRECIATION), Decimal("10"))
        # ضيافة فلسطينية: ض.ق.م 0% (منعٌ تامّ، م44).
        self.assertEqual(rate_of("PS", "hospitality", RATE_KIND_VAT), Decimal("0"))
        # ضيافة إسرائيلية: 0% في الاثنين.
        self.assertEqual(rate_of("IL", "hospitality", RATE_KIND_VAT), Decimal("0"))
        # نسبةُ مديرٍ للاستخدام المزدوج: لا رقمَ في القانون ⇒ فراغٌ و«راجع».
        self.assertIsNone(rate_of("PS", "dual_use", RATE_KIND_VAT))
        self.assertIsNone(rate_of("IL", "vehicle_fuel", RATE_KIND_INCOME))
        # سقفُ الهدايا الإسرائيلي ليس نسبةً ⇒ لا يدخل خانة ضريبة الدخل.
        self.assertIsNone(rate_of("IL", "gifts", RATE_KIND_INCOME))

    def test_an_unknown_tax_system_is_rejected(self):
        res = self.client.get(
            f"{BOOKS}rates/", {"tax_system": "XX"}, **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_an_office_edit_is_logged_and_appended_not_overwritten(self):
        """تعديلُ المكتب بسجلّ: صفٌّ إلحاقيٌّ لكل تغيير، والسببُ ملزم (بند ١)."""
        url = f"{BOOKS}rates/furniture/{RATE_KIND_VAT}/"
        first = self.client.post(
            url,
            {"tax_system": "IL", "rate": "100", "needs_review": False,
             "reason": "قرأنا النصّ: لا منعَ على الأثاث"},
            format="json", **self.headers(),
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(BookExpenseRateChange.objects.count(), 1)
        edited = {
            (row["code"], row["rate_kind"]): row for row in first.data["rows"]
        }[("furniture", RATE_KIND_VAT)]
        self.assertEqual(edited["source"], "office")

        second = self.client.post(
            url,
            {"tax_system": "IL", "rate": "0", "needs_review": True,
             "reason": "المدير قرّر خلاف ذلك"},
            format="json", **self.headers(),
        )
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(BookExpenseRateChange.objects.count(), 2)
        logged = BookExpenseRateChange.objects.order_by("id")
        self.assertEqual(logged[0].after["rate"], "100.0000")
        self.assertEqual(logged[1].before["rate"], "100.0000")
        self.assertEqual(logged[1].after["rate"], "0.0000")
        self.assertEqual(logged[1].reason, "المدير قرّر خلاف ذلك")
        self.assertEqual(logged[1].changed_by, self.owner)

    def test_an_edit_without_a_reason_is_rejected(self):
        res = self.client.post(
            f"{BOOKS}rates/furniture/{RATE_KIND_VAT}/",
            {"tax_system": "IL", "rate": "50", "reason": "  "},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("reason", res.data)
        self.assertEqual(BookExpenseRateChange.objects.count(), 0)


class BookRatesTestCase(APITestCase):
    """نسبتا المصروف على الحساب، ونسبةُ السطر المخالفة (بند ٢)."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="brt_owner", password="x")
        cls.tenant = create_company(
            "مكتب نسب الدفتر", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)
        cls.accountant = User.objects.create_user(username="brt_acc", password="x")
        UserCompanyMembership.objects.create(
            user=cls.accountant, tenant=cls.tenant, role="accountant",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون النسب", responsible=self.owner,
        )
        self.client.post(
            BOOKS,
            {"client_id": self.mine.pk, "kind": BOOK_KIND_DOUBLE},
            format="json", **self.headers(),
        )
        self.book = ClientBook.objects.get(client=self.mine)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def account(self, code):
        return ClientBookAccount.objects.get(client=self.mine, code=code)

    def add_entry(self, lines, *, entry_date=None, kind="purchase_invoice", expect=201):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": (entry_date or datetime.date(THIS_YEAR, 2, 1)).isoformat(),
                "kind": kind,
                "lines": lines,
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    # ── ٢أ: الافتراضُ 100% والتصنيفُ من اللائحة ─────────────────────────────
    def test_both_rates_default_to_one_hundred_without_a_category(self):
        account = self.account("5200") if ClientBookAccount.objects.filter(
            client=self.mine, code="5200",
        ).exists() else self.account("5300")
        rows = book_rates.account_rows(
            account, tenant=self.tenant, tax_system="IL",
        )
        self.assertEqual(rows[RATE_KIND_VAT]["rate"], "100.0000")
        self.assertEqual(rows[RATE_KIND_INCOME]["rate"], "100.0000")
        self.assertEqual(rows[RATE_KIND_VAT]["source"], book_rates.SOURCE_DEFAULT)
        # والإهلاكُ لا افتراضَ له: لا نسبةَ إهلاكٍ لحسابٍ بلا فئة.
        self.assertIsNone(rows[RATE_KIND_DEPRECIATION]["rate"])
        self.assertFalse(rows[RATE_KIND_DEPRECIATION]["usable"])

    def test_a_category_brings_the_platform_rates(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/5200/rates/",
            {"rate_category": "furniture"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["rates"][RATE_KIND_VAT]["rate"], "100.0000")
        self.assertEqual(res.data["rates"][RATE_KIND_VAT]["source"], "platform")
        self.assertEqual(res.data["rates"][RATE_KIND_DEPRECIATION]["rate"], "6.0000")

    def test_an_explicit_null_returns_the_account_to_the_list(self):
        """`null` صريحٌ يُفرّغ النسبةَ فيعود الحسابُ إلى اللائحة — 200 والقراءةُ تُثبته.

        `set_account_rates` كان يقرأ «الحقلُ مُرسَل» بـ`if value is not None`،
        فـ`null` يمرّ صامتاً ويبقى الحسابُ على نسبته الصريحة — **لا طريقَ لإرجاعه**.
        """
        set_ok = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/5200/rates/",
            {"vat_rate": "66.6667"}, format="json", **self.headers(),
        )
        self.assertEqual(set_ok.status_code, 200, set_ok.content)
        self.assertEqual(set_ok.data["rates"][RATE_KIND_VAT]["source"], "account")

        cleared = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/5200/rates/",
            {"vat_rate": None}, format="json", **self.headers(),
        )

        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(self.account("5200").vat_rate)
        # وقراءةُ الشجرة تقول الشيء نفسه: مصدرُ النسبة صار الافتراضَ لا الحساب.
        tree = self.client.get(f"{BOOKS}{self.mine.pk}/accounts/", **self.headers())
        self.assertEqual(tree.status_code, 200, tree.content)
        row = next(row for row in tree.data if row["code"] == "5200")
        self.assertEqual(row["rates"][RATE_KIND_VAT]["source"], book_rates.SOURCE_DEFAULT)
        self.assertEqual(row["rates"][RATE_KIND_VAT]["rate"], "100.0000")

    def test_an_unknown_category_is_rejected(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/5200/rates/",
            {"rate_category": "spaceship"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("rate_category", res.data)

    def test_a_reviewed_category_is_declared_and_not_used(self):
        """تصنيفٌ «راجع» في اللائحة لا يعطي نسبةً تُحسب."""
        client_books.set_account_rates(
            self.account("5200"), tenant=self.tenant, rate_category="dual_use",
        )
        rows = book_rates.account_rows(
            self.account("5200"), tenant=self.tenant, tax_system="IL",
        )
        # هاتفُ الاستخدام المزدوج في إسرائيل: النسبةُ يقدّرها المكتب ⇒ راجع.
        self.assertFalse(rows[RATE_KIND_VAT]["usable"] or rows[RATE_KIND_VAT]["rate"])

    # ── ٢ب: نسبةُ السطر — بإعدادٍ وسبب ─────────────────────────────────────
    def test_a_line_rate_needs_the_setting_and_a_reason(self):
        lines = [
            {"account_code": "5200", "debit": "1000", "tax_amount": "170",
             "vat_rate": "66.6667"},
            {"account_code": "1100", "credit": "1000"},
        ]
        refused = self.add_entry(lines, expect=400)
        self.assertIn("غير مفعّل", str(refused))

        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, True)
        without_reason = self.add_entry(lines, expect=400)
        self.assertIn("سبباً", str(without_reason))

        lines[0]["rate_reason"] = "أثاثٌ استُعمل جزءٌ منه في البيت"
        created = self.add_entry(lines)
        line = created["lines"][0]
        self.assertEqual(line["vat_rate"], "66.6667")
        self.assertEqual(line["vat_rate_reason"], "أثاثٌ استُعمل جزءٌ منه في البيت")

    def test_an_accountant_can_still_write_without_a_line_rate(self):
        """الإعدادُ مطفأ لا يمنع الحركة العادية — يمنع النسبةَ المخالفة وحدها."""
        self.add_entry([
            {"account_code": "5200", "debit": "1000"},
            {"account_code": "1100", "credit": "1000"},
        ])

    def test_reversing_a_line_rate_entry_survives_the_setting_being_turned_off(self):
        """العكسُ يحمل نسبةَ الأصل وسببَه: إطفاءُ الإعداد بعدها لا يمنع التصحيح."""
        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, True)
        created = self.add_entry([
            {"account_code": "5200", "debit": "1000", "tax_amount": "170",
             "vat_rate": "66.6667", "rate_reason": "أثاثٌ مشترك"},
            {"account_code": "1100", "credit": "1000"},
        ])
        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, False)

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{created['id']}/reverse/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["lines"][0]["vat_rate"], "66.6667")
        self.assertEqual(res.data["lines"][0]["vat_rate_reason"], "أثاثٌ مشترك")


class DepreciationTestCase(APITestCase):
    """الإهلاكُ بالقسط الثابت للسنة (بند ٣)."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="dp_owner", password="x")
        cls.tenant = create_company(
            "مكتب الإهلاك", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.ps = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون فلسطيني", responsible=self.owner,
        )
        services.set_client_setting(self.ps, "tax_system", "PS")
        self.il = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون إسرائيلي", responsible=self.owner,
        )
        for client in (self.ps, self.il):
            res = self.client.post(
                BOOKS, {"client_id": client.pk, "kind": BOOK_KIND_DOUBLE},
                format="json", **self.headers(),
            )
            self.assertEqual(res.status_code, 201, res.content)
            # حسابُ أصلٍ ثابتٍ للاختبار: الشجرةُ المبذورة `1200` بنكٌ لا أثاث.
            added = self.client.post(
                f"{BOOKS}{client.pk}/accounts/",
                {"code": "1400", "name": "أثاث", "parent_code": "1000",
                 "account_type": "asset"},
                format="json", **self.headers(),
            )
            self.assertEqual(added.status_code, 201, added.content)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def buy_furniture(self, client, *, amount="10000.00", day=None):
        """أصلُ أثاثٍ بكلفته — الحركةُ بالدفع من الصندوق."""
        return self.client.post(
            f"{BOOKS}{client.pk}/entries/",
            {
                "entry_date": (day or datetime.date(THIS_YEAR, 1, 15)).isoformat(),
                "kind": "purchase_invoice",
                "lines": [
                    {"account_code": "1400", "debit": amount},
                    {"account_code": "1100", "credit": amount},
                ],
            },
            format="json", **self.headers(),
        )

    def set_category(self, client, code="1400", category="furniture"):
        res = self.client.post(
            f"{BOOKS}{client.pk}/accounts/{code}/rates/",
            {"rate_category": category}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def depreciation(self, client, *, raw_to=None):
        book = ClientBook.objects.get(client=client)
        return book_reports.depreciation_payload(book, raw_to=raw_to)

    def test_a_ten_thousand_furniture_asset_depreciates_one_thousand_in_palestine(self):
        self.assertEqual(self.buy_furniture(self.ps).status_code, 201)
        self.set_category(self.ps)

        payload = self.depreciation(
            self.ps, raw_to=datetime.date(THIS_YEAR, 12, 31).isoformat(),
        )

        self.assertEqual(payload["rows"][0]["cost"], "10000.00")
        self.assertEqual(payload["rows"][0]["rate"], "10.0000")
        self.assertEqual(payload["rows"][0]["depreciation"], "1000.00")
        self.assertEqual(payload["totals"]["depreciation"], "1000.00")
        self.assertEqual(payload["review_count"], 0)

    def test_the_book_row_carries_the_annual_depreciation_to_the_api(self):
        """الإهلاكُ يصل الواجهةَ في سطر الدفتر — كما يصل `annual_alerts` (بند ٣).

        كان `depreciation_payload` لا مستدعيَ له إلا الاختبار: رقمٌ محسوبٌ في
        الخادم لا يراه المحاسبُ في أيّ شاشة.
        """
        self.assertEqual(self.buy_furniture(self.ps).status_code, 201)
        self.set_category(self.ps)

        res = self.client.get(f"{BOOKS}{self.ps.pk}/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        payload = res.data["depreciation"]
        self.assertEqual(payload["tax_system"], "PS")
        row = payload["rows"][0]
        self.assertEqual(row["account_code"], "1400")
        self.assertEqual(row["rate_category"], "furniture")
        self.assertEqual(row["rate_category_label"], "أثاث ومفروشات")
        self.assertEqual(row["rate"], "10.0000")
        self.assertEqual(row["cost"], "10000.00")
        self.assertEqual(row["depreciation"], "1000.00")
        self.assertEqual(payload["totals"]["depreciation"], "1000.00")

    def test_the_same_asset_depreciates_six_percent_in_israel(self):
        self.assertEqual(self.buy_furniture(self.il).status_code, 201)
        self.set_category(self.il)

        payload = self.depreciation(self.il)

        self.assertEqual(payload["totals"]["depreciation"], "600.00")

    def test_a_review_category_is_declared_not_depreciated(self):
        """صنفُ آلاتٍ فلسطينيّ (5%–12% بحسب الصناعة) لا نسبةَ واحدةَ له."""
        self.buy_furniture(self.ps)
        self.set_category(self.ps, category="machinery")

        payload = self.depreciation(self.ps)

        self.assertIsNone(payload["rows"][0]["depreciation"])
        self.assertTrue(payload["rows"][0]["needs_review"])
        self.assertEqual(payload["review_count"], 1)
        self.assertEqual(payload["totals"]["depreciation"], "0.00")


class AmountFromBookTestCase(APITestCase):
    """مبلغُ الالتزام من الدفتر (بند ٤) — الرقمُ من التذكرة."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="afb_owner", password="x")
        cls.tenant = create_company(
            "مكتب مبلغ الدفتر", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)
        cls.accountant = User.objects.create_user(username="afb_acc", password="x")
        UserCompanyMembership.objects.create(
            user=cls.accountant, tenant=cls.tenant, role="accountant",
        )
        cls.rule = DeadlineRule.objects.order_by("pk").first()

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون ض.ق.م", responsible=self.accountant,
        )
        res = self.client.post(
            BOOKS, {"client_id": self.mine.pk, "kind": BOOK_KIND_DOUBLE},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.book = ClientBook.objects.get(client=self.mine)
        self.obligation = self.add_obligation()

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def add_obligation(self):
        task = PeriodTask.objects.create(
            tenant=self.tenant,
            client=self.mine,
            client_service=self.mine.services.get(),
            period_start=JAN_START,
            period_end=JAN_END,
            internal_deadline=JAN_END,
        )
        return Obligation.objects.create(
            tenant=self.tenant,
            client=self.mine,
            client_service_id=task.client_service_id,
            task=task,
            rule=self.rule,
            rule_code=self.rule.code,
            name=self.rule.name,
            period_start=JAN_START,
            period_end=JAN_END,
            legal_date=JAN_END,
            official_date=JAN_END,
            actual_deadline=JAN_END,
            internal_deadline=JAN_END,
        )

    def add_purchase(self, *, tax="170", rate=None):
        """فاتورةُ أثاثٍ: الأصلُ مدينٌ بكلفته + الضريبة، والصندوقُ دائنٌ بالمجموع.

        الضريبةُ **مسجَّلةٌ على بند الأصل** (`tax_base`/`tax_amount`) كما يفعل
        `book_imports`، والمدينُ يساوي الدائنَ فيبقى القيدُ المزدوجُ متوازناً.
        """
        total = str(Decimal("1000") + Decimal(tax))
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": JAN_START.isoformat(),
                "kind": "purchase_invoice",
                "lines": [
                    {"account_code": "1200", "debit": total, "tax_amount": tax,
                     "tax_base": "1000"},
                    {"account_code": "1100", "credit": total},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

    def compute(self, *, expect=200):
        res = self.client.post(
            f"{OBLIGATIONS}{self.obligation.pk}/amount/from-book/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def test_two_thirds_of_the_furniture_tax_is_deducted_and_the_rest_is_cost(self):
        """١٧٠ ضريبةً بنسبة 2/3 ⇒ ١١٣.٣٣ تُخصم والباقي كلفة (رقمُ التذكرة)."""
        self.add_purchase(tax="170")
        client_books.set_account_rates(
            ClientBookAccount.objects.get(client=self.mine, code="1200"),
            tenant=self.tenant, vat_rate="66.6667",
        )
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )

        data = self.compute()

        details = data["computed_details"]
        self.assertEqual(details["input_tax"], "170.00")
        self.assertEqual(details["recognised_input"], "113.33")
        self.assertEqual(details["non_deductible"], "56.67")
        # لا مبيعاتٍ في الفترة ⇒ المستحقُّ سالب (له رصيدُ مدخلات).
        self.assertEqual(details["vat_due"], "-113.33")
        self.assertEqual(data["computed_amount"], "-113.33")
        # والمعدَّلُ لم يُمسّ: التأكيدُ فعلٌ ثانٍ.
        self.assertIsNone(data["amount"])

    def test_a_line_rate_beats_the_account_rate_in_the_calculation(self):
        """نسبةُ السطر **تُحسب** لا تُخزَّن فقط: الحسابُ 100% والسطرُ 2/3 ⇒ 113.33."""
        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, True)
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": JAN_START.isoformat(),
                "kind": "purchase_invoice",
                "lines": [
                    {"account_code": "1200", "debit": "1170", "tax_amount": "170",
                     "tax_base": "1000", "vat_rate": "66.6667",
                     "rate_reason": "جزءٌ من الأثاث للبيت"},
                    {"account_code": "1100", "credit": "1170"},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        details = self.compute()["computed_details"]

        self.assertEqual(details["recognised_input"], "113.33")
        self.assertEqual(details["review_lines"], 0)

    def test_the_platform_list_gives_one_hundred_percent(self):
        """تصنيفُ الأثاث في لائحة المنصّة (100%) ⇒ تُخصم كلُّ الضريبة."""
        self.add_purchase(tax="170")
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/1200/rates/",
            {"rate_category": "furniture"}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )

        details = self.compute()["computed_details"]

        self.assertEqual(details["recognised_input"], "170.00")
        self.assertEqual(details["non_deductible"], "0.00")
        self.assertEqual(details["vat_due"], "-170.00")

    def test_sales_tax_minus_recognised_input_is_the_due(self):
        """ض.ق.م = ضريبةُ المبيعات − المدخلات المعترف بها."""
        # بيعٌ بـ1,000 وضريبة 170.
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": JAN_START.isoformat(),
                "kind": "sales_invoice",
                "lines": [
                    {"account_code": "1100", "debit": "1170"},
                    {"account_code": "4100", "credit": "1170",
                     "tax_base": "1000", "tax_amount": "170"},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.add_purchase(tax="170")
        client_books.set_account_rates(
            ClientBookAccount.objects.get(client=self.mine, code="1200"),
            tenant=self.tenant, vat_rate="66.6667",
        )
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )

        details = self.compute()["computed_details"]

        self.assertEqual(details["sales_tax"], "170.00")
        self.assertEqual(details["vat_due"], "56.67")

    def test_confirming_keeps_both_the_computed_and_the_adjusted(self):
        self.add_purchase(tax="170")
        client_books.set_account_rates(
            ClientBookAccount.objects.get(client=self.mine, code="1200"),
            tenant=self.tenant, vat_rate="66.6667",
        )
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )
        self.compute()

        res = self.client.post(
            f"{OBLIGATIONS}{self.obligation.pk}/amount/confirm/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["amount"], "113.33")
        self.assertEqual(res.data["computed_amount"], "-113.33")
        self.assertEqual(res.data["direction"], "refund")

    def test_a_member_without_the_amounts_key_cannot_read_the_details(self):
        """`computed_details` حمولةُ مبالغ: قنعُ السطر وحده كان يتركها مكشوفة."""
        self.add_purchase(tax="170")
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )
        self.client.force_authenticate(user=self.accountant)

        res = self.client.post(
            f"{OBLIGATIONS}{self.obligation.pk}/amount/from-book/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 403, res.content)
        self.assertIn("المبالغ", str(res.data))
        self.assertIsNone(Obligation.objects.get(pk=self.obligation.pk).computed_amount)

    def test_the_setting_gates_the_calculation(self):
        self.add_purchase()
        data = self.compute(expect=400)
        self.assertIn("غير مفعّل", str(data))

    def test_a_client_without_a_book_is_a_named_refusal(self):
        no_book = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون بلا دفتر", responsible=self.owner, bookkeeping=False,
        )
        # خدمةُ الزبون بلا دفترٍ في خدمةٍ أخرى وفترةٍ أخرى: فرادةُ الشغلة على
        # (الخدمة، البداية، النهاية) — والشغلةُ هنا ليست موضوعَ الاختبار.
        service = self.mine.services.get()
        task = PeriodTask.objects.create(
            tenant=self.tenant,
            client=no_book,
            client_service=service,
            period_start=datetime.date(THIS_YEAR, 2, 1),
            period_end=datetime.date(THIS_YEAR, 2, 28),
            internal_deadline=datetime.date(THIS_YEAR, 2, 28),
        )
        obligation = Obligation.objects.create(
            tenant=self.tenant,
            client=no_book,
            client_service_id=task.client_service_id,
            task=task,
            rule=self.rule,
            rule_code=self.rule.code,
            name=self.rule.name,
            period_start=task.period_start,
            period_end=task.period_end,
            legal_date=task.period_end,
            official_date=task.period_end,
            actual_deadline=task.period_end,
            internal_deadline=task.period_end,
        )
        services.set_office_setting(
            self.tenant, services.OBLIGATION_FROM_BOOK_KEY, True,
        )
        res = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/amount/from-book/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("لا دفتر", str(res.data))


class PeriodLockTestCase(APITestCase):
    """الإقفالُ عند التقديم والفتحُ بسبب (بند ٥)."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="pl_owner", password="x")
        cls.tenant = create_company(
            "مكتب الإقفال", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)
        cls.accountant = User.objects.create_user(username="pl_acc", password="x")
        UserCompanyMembership.objects.create(
            user=cls.accountant, tenant=cls.tenant, role="accountant",
        )
        cls.rule = DeadlineRule.objects.order_by("pk").first()

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون مقفل", responsible=self.accountant,
        )
        res = self.client.post(
            BOOKS, {"client_id": self.mine.pk, "kind": BOOK_KIND_DOUBLE},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.book = ClientBook.objects.get(client=self.mine)
        task = PeriodTask.objects.create(
            tenant=self.tenant,
            client=self.mine,
            client_service=self.mine.services.get(),
            period_start=JAN_START,
            period_end=JAN_END,
            internal_deadline=JAN_END,
        )
        self.obligation = Obligation.objects.create(
            tenant=self.tenant,
            client=self.mine,
            client_service_id=task.client_service_id,
            task=task,
            rule=self.rule,
            rule_code=self.rule.code,
            name=self.rule.name,
            period_start=JAN_START,
            period_end=JAN_END,
            legal_date=JAN_END,
            official_date=JAN_END,
            actual_deadline=JAN_END,
            internal_deadline=JAN_END,
        )

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def submit(self, *, expect=200):
        res = self.client.post(
            f"{OBLIGATIONS}{self.obligation.pk}/submit/",
            {"submitted_on": datetime.date(THIS_YEAR, 2, 1).isoformat()},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def add_entry(self, *, day, expect=201):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": day.isoformat(),
                "kind": "manual",
                "lines": [
                    {"account_code": "1100", "debit": "100"},
                    {"account_code": "4100", "credit": "100"},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def add_second_obligation(self):
        """التزامٌ ثانٍ بالفترة نفسها — ق.م ورواتبُ يناير في الشهر الواحد."""
        return Obligation.objects.create(
            tenant=self.tenant,
            client=self.mine,
            client_service_id=self.obligation.client_service_id,
            task=self.obligation.task,
            rule=self.rule,
            rule_code="jan_payroll",
            name="رواتب يناير",
            period_start=JAN_START,
            period_end=JAN_END,
            legal_date=JAN_END,
            official_date=JAN_END,
            actual_deadline=JAN_END,
            internal_deadline=JAN_END,
        )

    def test_submitting_closes_the_book_period_by_default(self):
        # الافتراضُ «مفعّل» (قرار المالك): التقديمُ يقفل بلا ضبطٍ سابق.
        self.submit()

        lock = BookPeriodLock.objects.get(client_book=self.book)
        self.assertEqual(lock.period_start, JAN_START)
        self.assertEqual(lock.period_end, JAN_END)
        self.assertIsNone(lock.unlocked_on)

    def test_an_explicit_off_keeps_the_book_period_open(self):
        # والإطفاءُ الصريح هو ما يمنع القفل — لا الصمت.
        services.set_client_setting(
            self.mine, client_books.CLOSE_ON_SUBMIT_KEY, False,
        )

        self.submit()

        self.assertEqual(BookPeriodLock.objects.count(), 0)

    def test_two_submissions_of_one_period_share_a_single_active_lock(self):
        """ق.م ورواتبُ يناير → قفلٌ نشطٌ واحد — والفحصُ في الخدمة لا في قيدٍ قاعدةٍ.

        القيدُ على (الدفتر، البداية، النهاية) حُذف ليفتح الطريق لصفٍّ جديد بعد
        الفتح، فصار هذا الفحصُ هو الحارسَ الوحيد — وهو لا يسقط بأيّ اختبارٍ آخر.
        """
        self.submit()
        second = self.add_second_obligation()

        res = self.client.post(
            f"{OBLIGATIONS}{second.pk}/submit/",
            {"submitted_on": datetime.date(THIS_YEAR, 2, 1).isoformat()},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            BookPeriodLock.objects.filter(
                client_book=self.book, unlocked_on__isnull=True,
            ).count(),
            1,
        )
        self.assertEqual(BookPeriodLock.objects.filter(client_book=self.book).count(), 1)

    def test_a_second_submission_after_reopening_locks_a_new_row_and_keeps_the_log(self):
        """الفتحُ لا يُعيد القفلَ على الصفّ القديم: صفٌّ جديدٌ نشطٌ والأوّلُ شاهد."

        القيدُ القديم على (الدفتر، البداية، النهاية) كان يُعيد الصفَّ المفتوح من
        `get_or_create` فيبقى الدفترُ مفتوحاً بعد فتحٍ ثم تقديمٍ ثانٍ للفترة نفسها.
        """
        self.submit()
        first = BookPeriodLock.objects.get(client_book=self.book)
        client_books.reopen_period(
            first, reason="قيدُ يناير وصل متأخّراً", actor=self.owner,
        )

        second = self.add_second_obligation()
        res = self.client.post(
            f"{OBLIGATIONS}{second.pk}/submit/",
            {"submitted_on": datetime.date(THIS_YEAR, 2, 1).isoformat()},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)

        locks = BookPeriodLock.objects.filter(client_book=self.book).order_by("pk")
        self.assertEqual(locks.count(), 2)
        # الأوّلُ باقٍ في السجلّ بفتحه، والثاني نشطٌ هو ما يقفل الفترة.
        self.assertEqual(locks[0].pk, first.pk)
        self.assertIsNotNone(locks[0].unlocked_on)
        self.assertEqual(locks[0].unlock_reason, "قيدُ يناير وصل متأخّراً")
        self.assertIsNone(locks[1].unlocked_on)
        self.assertEqual(locks[1].period_start, JAN_START)
        self.assertEqual(locks[1].period_end, JAN_END)
        refused = self.add_entry(day=datetime.date(THIS_YEAR, 1, 15), expect=400)
        self.assertIn("مقفلة", str(refused))

    def test_an_enabled_setting_locks_the_period_and_blocks_entries_inside_it(self):
        services.set_office_setting(self.tenant, client_books.CLOSE_ON_SUBMIT_KEY, True)
        self.submit()
        lock = BookPeriodLock.objects.get(client_book=self.book)
        self.assertEqual(lock.period_start, JAN_START)
        self.assertEqual(lock.period_end, JAN_END)
        self.assertEqual(lock.obligation_id, self.obligation.pk)

        refused = self.add_entry(day=datetime.date(THIS_YEAR, 1, 15), expect=400)
        self.assertIn("مقفلة", str(refused))
        self.assertIn("2026-01-01", str(refused))
        # وخارجها يبقى مفتوحاً.
        self.add_entry(day=datetime.date(THIS_YEAR, 2, 15))

    def test_only_the_manager_or_owner_reopens_with_a_logged_reason(self):
        services.set_office_setting(self.tenant, client_books.CLOSE_ON_SUBMIT_KEY, True)
        self.submit()
        lock = BookPeriodLock.objects.get(client_book=self.book)
        url = f"{BOOKS}{self.mine.pk}/periods/{lock.pk}/reopen/"

        self.client.force_authenticate(user=self.accountant)
        refused = self.client.post(url, {"reason": "خطأٌ في القيد"}, format="json",
                                   **self.headers())
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertIsNone(BookPeriodLock.objects.get(pk=lock.pk).unlocked_on)

        self.client.force_authenticate(user=self.owner)
        empty = self.client.post(url, {"reason": "   "}, format="json",
                                 **self.headers())
        self.assertEqual(empty.status_code, 400, empty.content)

        opened = self.client.post(
            url, {"reason": "قيدُ يناير وصل متأخّراً"}, format="json",
            **self.headers(),
        )
        self.assertEqual(opened.status_code, 200, opened.content)
        self.assertEqual(opened.data["unlock_reason"], "قيدُ يناير وصل متأخّراً")
        self.assertEqual(opened.data["unlocked_by"], services.user_display_name(self.owner))
        # والحركةُ تمرّ بعد الفتح.
        self.add_entry(day=datetime.date(THIS_YEAR, 1, 20))

    def test_the_book_row_lists_the_locked_periods(self):
        services.set_office_setting(self.tenant, client_books.CLOSE_ON_SUBMIT_KEY, True)
        self.submit()
        res = self.client.get(f"{BOOKS}{self.mine.pk}/", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.data["locked_periods"]), 1)
        self.assertEqual(res.data["locked_periods"][0]["period_end"], "2026-01-31")


class PeriodResultTestCase(APITestCase):
    """نتيجةُ الفترة بلونها في الدفتر وفي إشعار الدفع (بند ٦)."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="pr_owner", password="x")
        cls.tenant = create_company(
            "مكتب نتيجة الفترة", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون النتيجة", responsible=self.owner,
        )
        res = self.client.post(
            BOOKS, {"client_id": self.mine.pk, "kind": BOOK_KIND_DOUBLE},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.book = ClientBook.objects.get(client=self.mine)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def sale(self, amount, *, day=None):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": (day or datetime.date(THIS_YEAR, 3, 1)).isoformat(),
                "kind": "sales_invoice",
                "lines": [
                    {"account_code": "1100", "debit": amount},
                    {"account_code": "4100", "credit": amount},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

    def spend(self, amount, *, day=None):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": (day or datetime.date(THIS_YEAR, 3, 2)).isoformat(),
                "kind": "expense",
                "lines": [
                    {"account_code": "5200", "debit": amount},
                    {"account_code": "1100", "credit": amount},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

    def test_the_result_tone_follows_the_sign_and_the_gray_threshold(self):
        self.assertEqual(
            book_reports.period_result_tone(Decimal("500"), Decimal("10")), "profit",
        )
        self.assertEqual(
            book_reports.period_result_tone(Decimal("-500"), Decimal("10")), "loss",
        )
        self.assertEqual(
            book_reports.period_result_tone(Decimal("10"), Decimal("10")), "neutral",
        )
        self.assertEqual(
            book_reports.period_result_tone(Decimal("-10"), Decimal("10")), "neutral",
        )

    def test_profit_is_green_loss_is_red_and_small_is_gray_in_the_book_row(self):
        self.sale("1000")
        self.spend("400")

        res = self.client.get(f"{BOOKS}{self.mine.pk}/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        result = res.data["period_result"]
        self.assertEqual(result["revenue"], "1000.00")
        self.assertEqual(result["expense"], "400.00")
        self.assertEqual(result["profit"], "600.00")
        self.assertEqual(result["tone"], "profit")
        self.assertEqual(result["tone_label"], "ربح")

        self.spend("700")  # إجماليُّ المصاريف 1,100 ⇒ خسارة
        res = self.client.get(f"{BOOKS}{self.mine.pk}/", **self.headers())
        self.assertEqual(res.data["period_result"]["tone"], "loss")

    def test_the_payment_notice_carries_the_result_for_a_client_with_a_book(self):
        self.sale("1000")
        self.spend("400")

        from accounting_office import appointments

        notice = appointments.payment_notice(
            self.tenant, client_id=self.mine.pk,
            due=datetime.date(THIS_YEAR, 3, 15), gray_threshold=Decimal("10"),
        )
        self.assertIsNotNone(notice["result"])
        self.assertEqual(notice["result"]["profit"], "600.00")
        self.assertEqual(notice["result"]["tone"], "profit")
        item = appointments.payment_notice_item(notice)
        self.assertEqual(item["result"]["tone_label"], "ربح")

    def test_a_client_without_a_book_has_no_result_line(self):
        from accounting_office import appointments

        bookless = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون بلا دفتر", responsible=self.owner, bookkeeping=False,
        )
        notice = appointments.payment_notice(
            self.tenant, client_id=bookless.pk,
            due=datetime.date(THIS_YEAR, 3, 15),
        )
        self.assertIsNone(notice["result"])
        self.assertIsNone(appointments.payment_notice_item(notice)["result"])


class AnnualThresholdsTestCase(APITestCase):
    """سقوفُ الإقرار السنوي — تنبيهٌ لا رفض (بند ٧)."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()
        seed_platform_rates()
        cls.owner = User.objects.create_user(username="at_owner", password="x")
        cls.tenant = create_company(
            "مكتب السقوف", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.ps = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون ضيافة", responsible=self.owner,
        )
        services.set_client_setting(self.ps, "tax_system", "PS")
        res = self.client.post(
            BOOKS, {"client_id": self.ps.pk, "kind": BOOK_KIND_DOUBLE},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def spend_on(self, code, amount, *, day=None):
        res = self.client.post(
            f"{BOOKS}{self.ps.pk}/entries/",
            {
                "entry_date": (day or datetime.date(THIS_YEAR, 4, 1)).isoformat(),
                "kind": "expense",
                "lines": [
                    {"account_code": code, "debit": amount},
                    {"account_code": "1100", "credit": amount},
                ],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

    def tag(self, account_code, category):
        res = self.client.post(
            f"{BOOKS}{self.ps.pk}/accounts/{account_code}/rates/",
            {"rate_category": category}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)

    def alerts(self):
        return book_reports.annual_alerts_payload(
            ClientBook.objects.get(client=self.ps), year=THIS_YEAR,
        )

    def test_the_tagged_expenses_are_summed_and_compared_with_the_published_cap(self):
        self.tag("5200", "hospitality")
        self.spend_on("5200", "160000")

        payload = self.alerts()
        row = {item["code"]: item for item in payload["rows"]}["hospitality"]

        self.assertEqual(row["total"], "160000.00")
        self.assertEqual(row["cap"], "150000.00")
        self.assertTrue(row["exceeded"])
        self.assertFalse(row["needs_review"])
        self.assertTrue(payload["any_exceeded"])
        self.assertTrue(row["source_url"])

    def test_within_the_cap_it_is_an_alert_not_a_refusal(self):
        self.tag("5200", "hospitality")
        self.spend_on("5200", "90000")

        payload = self.alerts()
        row = {item["code"]: item for item in payload["rows"]}["hospitality"]

        self.assertFalse(row["exceeded"])
        self.assertFalse(payload["any_exceeded"])
        # والحركةُ نفسُها لم تُرفض: السقفُ تنبيه.
        self.assertEqual(payload["rows"][0]["total"], "90000.00")

    def test_an_indexed_cap_is_declared_review_but_still_alerts(self):
        """سقفُ الهدايا الإسرائيلي مؤشَّرٌ سنوياً: يُنبَّه عليه ويُعلَن «راجع»."""
        services.set_client_setting(self.ps, "tax_system", "IL")
        self.tag("5200", "gifts")
        self.spend_on("5200", "3000")

        payload = self.alerts()
        row = {item["code"]: item for item in payload["rows"]}["gifts"]

        self.assertTrue(row["exceeded"])
        self.assertTrue(row["needs_review"])
        self.assertEqual(row["cap"], "2300.00")
        self.assertIn("2,300", row["cap_note"])

    def test_an_untagged_account_is_not_counted(self):
        self.spend_on("5200", "160000")
        payload = self.alerts()
        row = {item["code"]: item for item in payload["rows"]}["hospitality"]
        self.assertEqual(row["total"], "0.00")
        self.assertFalse(row["exceeded"])

    def test_the_book_row_carries_the_alerts(self):
        self.tag("5200", "hospitality")
        self.spend_on("5200", "160000")
        res = self.client.get(f"{BOOKS}{self.ps.pk}/", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.data["annual_alerts"]["any_exceeded"])
        self.assertEqual(res.data["annual_alerts"]["year"], THIS_YEAR)
