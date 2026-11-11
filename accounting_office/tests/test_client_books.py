"""دفتر الزبون — الجزء أ: الخادم (#286).

**ما يثبّته هذا الملفّ:**
- الترقيمُ بلا فجوات وتحت قفل (`ClientBookSequence`)، وأنّ الرقم لا يُقرأ من
  `MAX(number)+1` ولا من `count()+1` ولا من كائنٍ محفوظٍ في بايثون.
- لا حذف: التصحيحُ حركةٌ عكسية يشير إليها `reverses`، والأصلُ يبقى.
- الدفترُ يوجد فقط مع خدمة مسك الدفاتر (`status_on` القائمة)، ويصير للقراءة
  وحدها بعد إيقافها.
- الشجرةُ تُنسخ نسخةً واحدة عند الإنشاء، فلا مرجعَ حيّ إلى القالب.
- نوعُ الدفتر وانتقالُه من بداية سنة.
- «للإدخال» مشتقٌّ: ورقةٌ واصلةٌ بلا `BookEntry` — بلا عمودِ حالةٍ ثانٍ.
- **وحارسُ الاستثناء المعماريّ**: كودُ الدفتر لا يمسّ `accounting.services.post_journal`
  ولا `JournalHeader`/`JournalLine` (القرار في `docs/decisions/client_books.md`).

مكتبان في كل صنف تقريباً: العزلُ يُقاس بـ**404 لا 403** — الثاني لا يقول شيئاً.
"""
import ast
import datetime
import importlib
import pathlib
import threading
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, connections, transaction
from django.db.models.query import QuerySet
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.models import (
    BOOK_ACCOUNT_TYPE_CHOICES,
    BOOK_ENTRY_KIND_CHOICES,
    BOOK_KIND_CHOICES,
    BOOK_KIND_DOUBLE,
    BOOK_KIND_SIMPLE,
    ClientBook,
    ClientBookAccount,
    ClientBookSequence,
    DOCUMENT_CADENCE_MONTHLY,
    DOCUMENT_STATUS_RECEIVED,
    DOCUMENT_STATUS_REQUIRED,
    BookAccountTemplate,
    BookEntry,
    BookEntryDocument,
    BookEntryLine,
    DocumentChecklistItem,
    OfficeBookAccount,
    OfficeClient,
    TaxCard,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
BOOKS = f"{BASE}client-books/"
PENDING = f"{BOOKS}pending-entry/"

#: هجرةُ البيانات تُنفَّذ يدوياً: `pytest.ini` يشغّل `--nomigrations`، فلا
#: بياناتَ أولية في قاعدة الاختبار إلا ما يزرعه الاختبارُ بنفسه (نمط
#: `seed_deadline_schedules` في `test_obligations.py`).
BOOKS_MIGRATION = "accounting_office.migrations.0011_client_books"

#: السنةُ الجارية — **من `timezone.localdate()`** لا `date.today()`: الخادم يعمل
#: بتوقيت المكتب، و`date.today()` تاريخُ نظامه (UTC في CI) فيسقط اختبارُ نوع
#: الدفتر كلَّ يومٍ بين 21:00 ومنتصف الليل.
THIS_YEAR = timezone.localdate().year
#: حركةُ سنةٍ سابقة: نوعُ الدفتر يُغيَّر من بداية سنةٍ لا هذه.
LAST_YEAR_DAY = datetime.date(THIS_YEAR - 1, 3, 5)
#: بدايةُ خدمةٍ قديمةٍ في كل الاختبارات: التاريخ لا يغيّر حكماً هنا.
SERVICE_START = datetime.date(2020, 1, 1)

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
CLIENT_BOOKS_MODULE = APP_DIR / "client_books.py"
BOOK_MODELS_MODULE = APP_DIR / "models.py"


def seed_book_account_templates():
    """شجرةُ المنصّة **من هجرة البيانات نفسها** — لا زرعٌ يدويٌّ موازٍ لها."""
    migration = importlib.import_module(BOOKS_MIGRATION)
    migration.seed_book_account_templates(django_apps, None)


def month_bounds(year, month):
    first = datetime.date(year, month, 1)
    nxt = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - datetime.timedelta(days=1)


def make_client(*, tenant, catalog, name, responsible, bookkeeping=True):
    client = OfficeClient.objects.create(
        tenant=tenant, name=name, responsible=responsible,
    )
    TaxCard.objects.create(
        client=client, vat_classification="authorized", annual_sales=Decimal("0"),
    )
    if bookkeeping:
        services.add_client_service(
            client=client,
            service=catalog["bookkeeping"],
            starts_on=SERVICE_START,
            responsible_from=SERVICE_START,
            frequency="monthly",
        )
    return client


def make_document(client, *, year, month, status=DOCUMENT_STATUS_RECEIVED, code="vat_return"):
    start, end = month_bounds(year, month)
    return DocumentChecklistItem.objects.create(
        client=client,
        item_code=code,
        name="ورقة",
        cadence=DOCUMENT_CADENCE_MONTHLY,
        period_start=start,
        period_end=end,
        status=status,
    )


class ClientBookTestCase(APITestCase):
    """مكتبٌ مرخَّصٌ بمالكه ومحاسبٍ وزميل، وزبونٌ بمسك دفاتر، ومكتبٌ ثانٍ للعزل."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()

        cls.owner = User.objects.create_user(username="cb_owner", password="x")
        cls.tenant = create_company(
            "مكتب الدفاتر", cls.owner, template="accounting_office",
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

        cls.accountant = member("cb_accountant", "accountant")
        cls.colleague = member("cb_colleague", "accountant")
        #: دورٌ قراءةٌ فقط: يرى زبونَه ولا يملك `office.clients.write`.
        cls.viewer = member("cb_viewer", "viewer")

        cls.manager_b = User.objects.create_user(username="cb_manager_b", password="x")
        cls.tenant_b = create_company(
            "مكتب الدفاتر الثاني", cls.manager_b, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant_b.pk)
        ready_office(cls.tenant_b, "IL")
        cls.catalog_b = catalog(cls.tenant_b)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبوني", responsible=self.accountant,
        )
        self.outside = make_client(
            tenant=self.tenant_b, catalog=self.catalog_b,
            name="زبون المكتب الثاني", responsible=self.manager_b,
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    # ── أفعالٌ مشتركة: تُثبت خطوةٌ نجاحَها، فلا كلُّ اختبارٍ يبني الحمولة ──

    def create_book(self, client, *, kind=BOOK_KIND_DOUBLE, opened_on=None, expect=201):
        payload = {"client_id": client.pk, "kind": kind}
        if opened_on is not None:
            payload["opened_on"] = opened_on.isoformat()
        res = self.client.post(BOOKS, payload, format="json", **self.headers())
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def add_entry(
        self, client, *, lines, entry_date=LAST_YEAR_DAY, kind="sales_invoice",
        memo="", documents=None, expect=201,
    ):
        res = self.client.post(
            f"{BOOKS}{client.pk}/entries/",
            {
                "entry_date": entry_date.isoformat(),
                "kind": kind,
                "memo": memo,
                "documents": documents or [],
                "lines": lines,
            },
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def balanced(self, amount="100.00", *, debit_code="1100", credit_code="4100"):
        """بندان متوازنان: الأصولُ مديناً والإيرادُ دائناً."""
        return [
            {"account_code": debit_code, "debit": amount},
            {"account_code": credit_code, "credit": amount},
        ]

    def stop_bookkeeping(self, client):
        service = client.services.get(service__code="bookkeeping")
        service.ends_on = datetime.date(2020, 12, 31)
        service.save(update_fields=["ends_on"])
        return service


class BookCreationTest(ClientBookTestCase):
    def test_a_book_is_created_and_the_platform_tree_is_copied(self):
        row = self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

        self.assertEqual(row["client_id"], self.mine.pk)
        self.assertEqual(row["kind"], BOOK_KIND_DOUBLE)
        self.assertEqual(row["kind_label"], "مزدوج")
        book = ClientBook.objects.get(client=self.mine)
        expected = BookAccountTemplate.objects.filter(
            tax_system="IL", book_kind=BOOK_KIND_DOUBLE,
        ).count()
        self.assertGreater(expected, 0)
        self.assertEqual(ClientBookAccount.objects.filter(client=self.mine).count(), expected)

    def test_a_client_without_a_bookkeeping_service_is_400(self):
        client = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون بلا مسك دفاتر", responsible=self.accountant, bookkeeping=False,
        )

        self.create_book(client, expect=400)

        self.assertFalse(ClientBook.objects.filter(client=client).exists())

    def test_a_second_book_for_the_same_client_is_400(self):
        self.create_book(self.mine)

        self.create_book(self.mine, expect=400)

        self.assertEqual(ClientBook.objects.filter(client=self.mine).count(), 1)

    def test_an_unknown_kind_is_400(self):
        res = self.client.post(
            BOOKS,
            {"client_id": self.mine.pk, "kind": "triple"},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_deleting_a_book_is_405(self):
        self.create_book(self.mine)

        res = self.client.delete(f"{BOOKS}{self.mine.pk}/", **self.headers())

        self.assertEqual(res.status_code, 405, res.content)
        self.assertTrue(ClientBook.objects.filter(client=self.mine).exists())

    def test_a_client_of_another_office_is_404(self):
        self.as_user(self.manager_b)

        res = self.client.post(
            BOOKS,
            {"client_id": self.mine.pk, "kind": BOOK_KIND_SIMPLE},
            format="json",
            **self.headers(tenant=self.tenant_b),
        )

        self.assertEqual(res.status_code, 404, res.content)
        self.assertFalse(ClientBook.objects.filter(client=self.mine).exists())

    def test_writing_needs_the_write_key(self):
        """الكتابةُ بمفتاحها: عضوٌ يرى الزبون ولا يملك `office.clients.write` 403.

        والزبونُ مسؤوليّتُه ليجعله `visible_clients` مرئياً — وإلا سبق الـ404ُ
        الـ403 فصار الاختبار يقيس الرؤية لا المفتاح.
        """
        mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون المشاهد", responsible=self.viewer,
        )
        self.as_user(self.viewer)

        res = self.client.post(
            BOOKS,
            {"client_id": mine.pk, "kind": BOOK_KIND_SIMPLE},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 403, res.content)
        self.assertFalse(ClientBook.objects.filter(client=mine).exists())

    def test_the_book_list_carries_the_entry_method_from_the_settings_resolver(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE)

        res = self.client.get(BOOKS, **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["client_id"]: row for row in res.data}
        self.assertEqual(rows[self.mine.pk]["entry_method"], "document")
        self.assertEqual(rows[self.mine.pk]["entry_method_label"], "ورقة ورقة")


class BookRowChoicesTest(ClientBookTestCase):
    """تسمياتُ الأنواع في سطر الدفتر من النموذج لا من جدولٍ ثانٍ.

    سقوطُ `_book_row` صامتاً (نسيانُ حقلٍ أو إعادةُ تسميته) لا يراه `tsc` ولا
    `pytest`: الحقلُ اختياريٌّ في الواجهة (`?? []`)، فيصير منتقي نوع الحركة
    فارغاً وزرُّ «أدخل الحركة» مقفلاً أبداً. فالاختبارُ يقارن القائمتين بنموذجيهما
    حرفاً بحرف — لا بعددٍ ولا بوجودِ مفتاح.
    """

    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

    def test_the_single_book_row_carries_the_lists_with_their_model_labels(self):
        res = self.client.get(f"{BOOKS}{self.mine.pk}/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            res.data["entry_kind_choices"],
            [{"value": value, "label": label} for value, label in BOOK_ENTRY_KIND_CHOICES],
        )
        self.assertEqual(
            res.data["account_type_choices"],
            [{"value": value, "label": label} for value, label in BOOK_ACCOUNT_TYPE_CHOICES],
        )
        # `kind` في السطر نوعُ الدفتر لا الحركة: الاسمُ القديم كان مضلّلاً.
        self.assertNotIn("kind_choices", res.data)

    def test_the_choices_endpoint_returns_the_three_lists_from_the_models(self):
        res = self.client.get(f"{BOOKS}choices/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            res.data,
            {
                "book_kinds": [
                    {"value": value, "label": label} for value, label in BOOK_KIND_CHOICES
                ],
                "entry_kinds": [
                    {"value": value, "label": label} for value, label in BOOK_ENTRY_KIND_CHOICES
                ],
                "account_types": [
                    {"value": value, "label": label}
                    for value, label in BOOK_ACCOUNT_TYPE_CHOICES
                ],
            },
        )

    def test_the_choices_endpoint_needs_no_write_key(self):
        """من يفتح تبويب «الدفتر» يقرأ التسميات — وإن لم يملك إنشاءَ دفتر."""
        self.as_user(self.viewer)

        res = self.client.get(f"{BOOKS}choices/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("book_kinds", res.data)


class TreeCopyTest(ClientBookTestCase):
    def test_the_office_tree_wins_over_the_platform_template(self):
        OfficeBookAccount.objects.create(
            tenant=self.tenant, tax_system="IL", book_kind=BOOK_KIND_SIMPLE,
            code="1100", name="صندوق المكتب", account_type="asset", is_edited=True,
        )

        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE)

        row = ClientBookAccount.objects.get(client=self.mine, code="1100")
        self.assertEqual(row.name, "صندوق المكتب")
        self.assertEqual(ClientBookAccount.objects.filter(client=self.mine).count(), 1)

    def test_editing_the_template_later_does_not_change_an_existing_tree(self):
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)
        BookAccountTemplate.objects.filter(
            tax_system="IL", book_kind=BOOK_KIND_DOUBLE, code="1100",
        ).update(name="اسمٌ جديدٌ في المنصّة")

        row = ClientBookAccount.objects.get(client=self.mine, code="1100")

        self.assertNotEqual(row.name, "اسمٌ جديدٌ في المنصّة")


class AccountsApiTest(ClientBookTestCase):
    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

    def test_the_tree_is_read_flat_with_parent_codes(self):
        res = self.client.get(f"{BOOKS}{self.mine.pk}/accounts/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["code"]: row for row in res.data}
        self.assertEqual(rows["1100"]["parent_code"], "1000")
        self.assertEqual(rows["1000"]["parent_code"], None)
        self.assertEqual(rows["1100"]["account_type_label"], "أصول")
        codes = [row["code"] for row in res.data]
        self.assertEqual(codes, sorted(codes))

    def test_a_custom_account_is_added_under_its_parent(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/",
            {"code": "1150", "name": "صندوق فرعي", "parent_code": "1100", "account_type": "asset"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["parent_code"], "1100")
        self.assertFalse(res.data["is_system"])
        row = ClientBookAccount.objects.get(client=self.mine, code="1150")
        self.assertEqual(row.parent.code, "1100")

    def test_a_duplicate_code_is_400(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/",
            {"code": "1100", "name": "مكرَّر", "account_type": "asset"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_an_unknown_parent_is_400(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/",
            {"code": "1199", "name": "تحت أبٍ لا وجود له", "parent_code": "9999", "account_type": "asset"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_an_unknown_account_type_is_400(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/",
            {"code": "1198", "name": "نوعٌ مخترَع", "account_type": "goodwill"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_another_office_tree_is_404(self):
        self.as_user(self.manager_b)

        res = self.client.get(
            f"{BOOKS}{self.mine.pk}/accounts/", **self.headers(tenant=self.tenant_b),
        )

        self.assertEqual(res.status_code, 404, res.content)

    def test_adding_an_account_to_a_stopped_service_is_400(self):
        self.stop_bookkeeping(self.mine)

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/accounts/",
            {"code": "1151", "name": "بعد الإيقاف", "account_type": "asset"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)


class EntryNumberingTest(ClientBookTestCase):
    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

    def test_numbers_start_at_one_and_have_no_gaps(self):
        numbers = [
            self.add_entry(self.mine, lines=self.balanced())["number"] for _ in range(3)
        ]

        self.assertEqual(numbers, [1, 2, 3])
        self.assertEqual(
            ClientBookSequence.objects.get(client=self.mine, year=LAST_YEAR_DAY.year).last_number,
            3,
        )

    def test_the_number_comes_from_the_sequence_not_from_count_or_max(self):
        """`MAX+1` و`count()+1` كانا يعطيان 2 — والقفل يعطي 42.

        الرقمُ يُقرأ من صفّ العدّاد المقفول داخل المعاملة، لا من لقطةٍ محفوظةٍ في
        بايثون ولا من عدد الصفوف. تُدفع `last_number` إلى 41 بين الحركتين، فمن
        يقرأ العدّاد فعلاً يكتب 42، ومن يعيد الحساب يكتب 2.
        """
        self.add_entry(self.mine, lines=self.balanced())
        sequence = ClientBookSequence.objects.get(
            client=self.mine, year=LAST_YEAR_DAY.year,
        )
        stale = sequence.last_number
        ClientBookSequence.objects.filter(pk=sequence.pk).update(last_number=41)

        row = self.add_entry(self.mine, lines=self.balanced())

        self.assertEqual(stale, 1)
        self.assertEqual(row["number"], 42)

    def test_the_sequence_row_is_read_and_bumped_before_the_entry_is_inserted(self):
        """**ترتيبُ الأحداث** لا مجرّد انتظار: القفلُ والزيادةُ يسبقان الكتابة."""
        with CaptureQueriesContext(connection) as captured:
            self.add_entry(self.mine, lines=self.balanced())

        sql = [query["sql"].lower() for query in captured.captured_queries]
        sequence_select = next(
            index for index, statement in enumerate(sql)
            if statement.lstrip().startswith("select") and "clientbooksequence" in statement
        )
        sequence_update = next(
            index for index, statement in enumerate(sql)
            if statement.lstrip().startswith("update") and "clientbooksequence" in statement
        )
        entry_insert = next(
            index for index, statement in enumerate(sql)
            if statement.lstrip().startswith("insert") and "bookentry" in statement
        )
        self.assertLess(sequence_select, sequence_update)
        self.assertLess(sequence_update, entry_insert)

    def test_the_allocation_asks_for_a_row_lock_on_the_sequence(self):
        """`select_for_update` على صفّ `ClientBookSequence` — القفلُ نفسه لا أثرُه.

        SQLite لا تدعم `FOR UPDATE` فتسقط الجملةُ من الـSQL في الاختبار، ويبقى
        الطلبُ في الشجرة مرئياً للمِسبار: من ينزع القفل يسقط هذا الاختبار.
        """
        original = QuerySet.select_for_update
        with mock.patch.object(
            QuerySet, "select_for_update", autospec=True, side_effect=original,
        ) as spy:
            self.add_entry(self.mine, lines=self.balanced())

        self.assertTrue(spy.called, "لا قفلَ على العدّاد — الترقيم بلا حارس")
        locked_models = [call.args[0].model for call in spy.call_args_list]
        self.assertIn(ClientBookSequence, locked_models)

    def test_the_database_refuses_a_duplicate_number_for_the_same_client_and_year(self):
        """الطبقةُ الثانية: القفلُ يُسانَد بفرادةٍ في القاعدة لا يُستبدَل بها.

        `IntegrityError` لا نصَّ رسالة: نصُّ «UNIQUE» في SQLite و«Duplicate entry»
        في MySQL، واختبارٌ يقيس كلمات محرّكٍ واحد يكذب على غيره.
        """
        self.add_entry(self.mine, lines=self.balanced())
        book = ClientBook.objects.get(client=self.mine)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BookEntry.objects.create(
                    client_book=book, client=self.mine, year=LAST_YEAR_DAY.year,
                    number=1, entry_date=LAST_YEAR_DAY, kind="expense",
                )


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentNumberingTest(TransactionTestCase):
    """إدخالان متزامنان على اتصالين — الرقمُ لا يتكرّر، والعكسُ لا يُكتب مرّتين.
    يُتخطّى على SQLite.

    `select_for_update` لا وجودَ له في SQLite (صفريّ)، فالاختبارُ هنا **يُعلن
    تخطّيه** بدل أن يوهم بمرور. ويُثبَت الحملُ نفسُه بلا تزامنٍ في
    `EntryNumberingTest` و`EntryApiTest` (ترتيبُ الأحداث وطلبُ القفل وفرادةُ
    القاعدة).
    """

    def _book(self):
        """مكتبٌ وزبونٌ بدفترٍ بسيطٍ وشجرته — `(user, book, account)`."""
        from django.contrib.auth.models import User as AuthUser

        from accounting_office import client_books

        user = AuthUser.objects.create_user(username="cb_race", password="x")
        tenant = create_company("مكتب التزامن", user, template="accounting_office")
        invalidate_module_cache(tenant.pk)
        ready_office(tenant)
        # `TransactionTestCase` لا يرث `setUpTestData`، و`--nomigrations` لا تزرع
        # بيانات الهجرة: بلا هذا النداء لا شجرةَ في القاعدة و`get(code=…)` يرمي.
        seed_book_account_templates()
        client = make_client(
            tenant=tenant, catalog=catalog(tenant),
            name="زبون التزامن", responsible=user,
        )
        book = ClientBook.objects.create(
            client=client, kind=BOOK_KIND_SIMPLE, opened_on=SERVICE_START,
        )
        client_books.ensure_client_tree(client, BOOK_KIND_SIMPLE)
        account = ClientBookAccount.objects.get(client=client, code="1100")
        return user, book, account

    def test_two_concurrent_writers_never_take_the_same_number(self):
        from accounting_office import client_books

        user, book, account = self._book()
        client = book.client

        numbers, errors = [], []
        barrier = threading.Barrier(2)

        def writer():
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    entry = client_books.create_entry(
                        book, entry_date=LAST_YEAR_DAY, kind="expense",
                        lines=[{"account": account, "debit": Decimal("5.00"), "credit": None}],
                        actor=user,
                    )
                    numbers.append(entry.number)
            except Exception as exc:  # noqa: BLE001 — التقريرُ يريد السبب لا النوع
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=writer) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(numbers), [1, 2])
        self.assertEqual(BookEntry.objects.filter(client=client).count(), 2)
        self.assertEqual(
            len({row.number for row in BookEntry.objects.filter(client=client)}), 2,
        )

    def test_two_concurrent_reversals_of_the_same_entry_write_one(self):
        """طلبا عكسٍ متقاربان: واحدٌ يُكتب والآخرُ `ValidationError` (400) لا حركةٌ ثانية."""
        from django.core.exceptions import ValidationError

        from accounting_office import client_books

        user, book, account = self._book()
        original = client_books.create_entry(
            book, entry_date=LAST_YEAR_DAY, kind="expense",
            lines=[{"account": account, "debit": Decimal("5.00"), "credit": None}],
            actor=user,
        )

        reversals, refused, unexpected = [], [], []
        barrier = threading.Barrier(2)

        def reverser():
            try:
                entry = BookEntry.objects.select_related("client_book").get(pk=original.pk)
                barrier.wait(timeout=10)
                reversals.append(client_books.reverse_entry(entry, actor=user).pk)
            except ValidationError as exc:
                refused.append(exc)
            except Exception as exc:  # noqa: BLE001 — التقريرُ يريد السبب لا النوع
                unexpected.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=reverser) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(unexpected, [])
        self.assertEqual(len(reversals), 1)
        self.assertEqual(len(refused), 1)
        self.assertEqual(BookEntry.objects.filter(reverses=original).count(), 1)


class EntryApiTest(ClientBookTestCase):
    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

    def test_a_balanced_entry_is_created_with_its_lines(self):
        row = self.add_entry(
            self.mine, lines=self.balanced("250.00"), memo="فاتورة بيع",
        )

        self.assertEqual(row["number"], 1)
        self.assertEqual(row["year"], LAST_YEAR_DAY.year)
        self.assertEqual(row["kind_label"], "فاتورة بيع")
        self.assertEqual(row["total_debit"], "250.00")
        self.assertEqual(row["total_credit"], "250.00")
        self.assertEqual(len(row["lines"]), 2)
        self.assertEqual(BookEntryLine.objects.filter(entry_id=row["id"]).count(), 2)

    def test_an_unbalanced_double_entry_is_400(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": LAST_YEAR_DAY.isoformat(),
                "kind": "sales_invoice",
                "lines": [
                    {"account_code": "1100", "debit": "100.00"},
                    {"account_code": "4100", "credit": "90.00"},
                ],
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_an_entry_without_lines_is_400(self):
        self.add_entry(self.mine, lines=[], expect=400)
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_line_with_both_sides_is_400(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": LAST_YEAR_DAY.isoformat(),
                "kind": "sales_invoice",
                "lines": [{"account_code": "1100", "debit": "10.00", "credit": "10.00"}],
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_an_unknown_account_code_is_400(self):
        self.add_entry(
            self.mine,
            lines=[
                {"account_code": "7777", "debit": "100.00"},
                {"account_code": "4100", "credit": "100.00"},
            ],
            expect=400,
        )

    def test_an_unknown_kind_is_400(self):
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": LAST_YEAR_DAY.isoformat(),
                "kind": "grocery",
                "lines": self.balanced(),
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_more_than_a_hundred_documents_is_400_before_the_service(self):
        """الحدُّ في الـserializer: الخدمةُ لا تُنادى فلا تقفل صفّاً واحداً.

        معرّفاتٌ لا وجود لها تردّ 400 من الخدمة أيضاً، فالـ400 وحده لا يُثبت الحدّ —
        المِسبارُ أن `create_entry` لم تُنادَ.
        """
        from accounting_office import client_books

        with mock.patch.object(
            client_books, "create_entry",
            side_effect=AssertionError("الخدمةُ نوديت — الحدُّ لم يُفحص في الـserializer"),
        ) as service:
            res = self.client.post(
                f"{BOOKS}{self.mine.pk}/entries/",
                {
                    "entry_date": LAST_YEAR_DAY.isoformat(),
                    "kind": "expense",
                    "lines": self.balanced(),
                    "documents": list(range(1, 102)),
                },
                format="json",
                **self.headers(),
            )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("documents", res.data)
        service.assert_not_called()

    def test_a_reversal_mirrors_the_lines_and_keeps_the_original(self):
        original = self.add_entry(self.mine, lines=self.balanced("100.00"))

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {"memo": "خطأُ إدخال"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["reverses"], original["id"])
        self.assertEqual(res.data["number"], original["number"] + 1)
        sides = {
            (line["account_code"], line["debit"], line["credit"]) for line in res.data["lines"]
        }
        self.assertEqual(sides, {("1100", "0.00", "100.00"), ("4100", "100.00", "0.00")})
        self.assertTrue(BookEntry.objects.filter(pk=original["id"]).exists())
        self.assertEqual(BookEntry.objects.get(pk=original["id"]).reverses_id, None)

    def test_reversing_a_reversal_is_400(self):
        original = self.add_entry(self.mine, lines=self.balanced())
        reversal = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {}, format="json", **self.headers(),
        ).data

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{reversal['id']}/reverse/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_reversing_the_same_entry_twice_is_400(self):
        original = self.add_entry(self.mine, lines=self.balanced())
        self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {}, format="json", **self.headers(),
        )

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(BookEntry.objects.filter(reverses_id=original["id"]).count(), 1)

    def test_a_reversal_locks_the_original_before_looking_for_a_reversal(self):
        """**ترتيبُ الأحداث**: قفلُ صفّ الأصل يسبق فحصَ «لها عكسٌ بالفعل».

        فحصٌ قبل القفل يمرّ لطلبين متقاربين معاً فتُكتب حركتان عكسيّتان. وSQLite
        تُسقط `FOR UPDATE` من الـSQL، فالمِسبارُ على الشجرة: من ينزع القفلَ أو
        يؤخّره بعد الفحص يسقط هذا الاختبار.
        """
        original = self.add_entry(self.mine, lines=self.balanced())
        events = []
        real_lock, real_exists = QuerySet.select_for_update, QuerySet.exists

        def lock(queryset, *args, **kwargs):
            events.append(("lock", queryset.model))
            return real_lock(queryset, *args, **kwargs)

        def exists(queryset):
            events.append(("exists", queryset.model))
            return real_exists(queryset)

        with (
            mock.patch.object(QuerySet, "select_for_update", autospec=True, side_effect=lock),
            mock.patch.object(QuerySet, "exists", autospec=True, side_effect=exists),
        ):
            res = self.client.post(
                f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
                {}, format="json", **self.headers(),
            )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertIn(("lock", BookEntry), events, "لا قفلَ على الأصل — العكسُ المزدوج بلا حارس")
        self.assertIn(("exists", BookEntry), events)
        self.assertLess(
            events.index(("lock", BookEntry)), events.index(("exists", BookEntry)),
        )

    def test_the_database_refuses_a_second_reversal_of_the_same_entry(self):
        """الطبقةُ الثانية: `reverses` فريدٌ في القاعدة (`OneToOneField`).

        يُكتب العكسُ الثاني مباشرةً متجاوزاً الخدمة — ما كان يكتبه طلبٌ فحصَ بلا
        قفل — فلا يقف أمامه إلا القيد. `IntegrityError` لا نصَّ رسالة: النصُّ
        يختلف بين SQLite وMySQL.
        """
        original = self.add_entry(self.mine, lines=self.balanced())
        first = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)
        entry = BookEntry.objects.get(pk=original["id"])

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BookEntry.objects.create(
                    client_book=entry.client_book, client=self.mine, year=entry.year,
                    number=99, entry_date=entry.entry_date, kind=entry.kind,
                    reverses=entry,
                )

        self.assertEqual(BookEntry.objects.filter(reverses_id=original["id"]).count(), 1)

    def test_deleting_an_entry_is_405(self):
        row = self.add_entry(self.mine, lines=self.balanced())

        res = self.client.delete(
            f"{BOOKS}{self.mine.pk}/entries/{row['id']}/", **self.headers(),
        )

        self.assertEqual(res.status_code, 405, res.content)
        self.assertTrue(BookEntry.objects.filter(pk=row["id"]).exists())

    def test_updating_an_entry_is_405(self):
        row = self.add_entry(self.mine, lines=self.balanced())

        res = self.client.patch(
            f"{BOOKS}{self.mine.pk}/entries/{row['id']}/",
            {"memo": "تعديل"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 405, res.content)

    def test_the_same_document_is_entered_once_and_the_second_link_is_400(self):
        document = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        row = self.add_entry(
            self.mine, lines=self.balanced(), documents=[document.pk],
        )

        self.assertEqual(row["documents"], [document.pk])
        self.assertTrue(
            BookEntryDocument.objects.filter(
                entry_id=row["id"], document=document,
            ).exists(),
        )
        error = self.add_entry(
            self.mine, lines=self.balanced(), documents=[document.pk], expect=400,
        )

        self.assertIn("documents", error)
        self.assertEqual(BookEntryDocument.objects.filter(document=document).count(), 1)

    def test_the_same_document_twice_in_one_request_is_400(self):
        document = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)

        error = self.add_entry(
            self.mine, lines=self.balanced(), documents=[document.pk, document.pk],
            expect=400,
        )

        self.assertIn("documents", error)
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_document_is_entered_again_after_its_entry_is_reversed(self):
        """عكسُ الحركة يُعيد الورقةَ **قابلةً للإدخال** — لا إلى «للإدخال» وحدها.

        `_documents_for` تستثني الحركاتِ المعكوسة؛ لو عدّت كلَّ رابطٍ لظهرت الورقةُ
        في «للإدخال» وردّ كلُّ إدخالٍ لها 400 — قائمةٌ لا تُصفَّر أبداً.
        """
        document = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        first = self.add_entry(
            self.mine, lines=self.balanced(), documents=[document.pk],
        )
        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{first['id']}/reverse/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        again = self.add_entry(
            self.mine, lines=self.balanced("120.00"), documents=[document.pk],
        )

        self.assertEqual(again["documents"], [document.pk])
        self.assertEqual(BookEntryDocument.objects.filter(document=document).count(), 2)

    def test_a_document_of_another_client_is_400(self):
        document = make_document(self.outside, year=LAST_YEAR_DAY.year, month=3)

        self.add_entry(
            self.mine, lines=self.balanced(), documents=[document.pk], expect=400,
        )

    def test_one_entry_can_carry_a_whole_month_of_documents(self):
        """طريقةُ «إدخال الشهر»: أوراقُ الشهر في حركةٍ واحدة — والربطُ قائمة."""
        first = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3, code="vat")
        second = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3, code="income")

        row = self.add_entry(
            self.mine, lines=self.balanced(), documents=[first.pk, second.pk],
        )

        self.assertEqual(sorted(row["documents"]), sorted([first.pk, second.pk]))
        self.assertEqual(
            BookEntryDocument.objects.filter(entry_id=row["id"]).count(), 2,
        )
        pending = self.client.get(PENDING, **self.headers())
        self.assertEqual(pending.data["total"], 0)

    def test_writing_an_entry_on_a_stopped_service_is_400(self):
        self.stop_bookkeeping(self.mine)

        self.add_entry(self.mine, lines=self.balanced(), expect=400)

        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_the_book_stays_readable_after_the_service_is_stopped(self):
        row = self.add_entry(self.mine, lines=self.balanced())
        self.stop_bookkeeping(self.mine)

        res = self.client.get(f"{BOOKS}{self.mine.pk}/entries/", **self.headers())
        listing = self.client.get(BOOKS, **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([entry["id"] for entry in res.data], [row["id"]])
        self.assertEqual(listing.data[0]["writable"], False)

    def test_the_amounts_are_masked_for_a_member_without_the_amounts_key(self):
        """قناعُ المبالغ: من يرى الزبون ولا يملك `office.amounts.view` يصله `None`.

        والقناعُ يطال **المجموعين المشتقّين** أيضاً: قنعُ المدين والدائن وحدهما
        يترك الرقمَ في `total_debit` — وهو الرقمُ نفسه.
        """
        self.add_entry(self.mine, lines=self.balanced("100.00"))
        self.as_user(self.accountant)

        res = self.client.get(f"{BOOKS}{self.mine.pk}/entries/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        entry = res.data[0]
        self.assertIsNone(entry["total_debit"])
        self.assertIsNone(entry["total_credit"])
        for line in entry["lines"]:
            self.assertIsNone(line["debit"])
            self.assertIsNone(line["credit"])
            self.assertTrue(line["account_code"], "الشكلُ يبقى: الحسابُ لا يُقنَّع")

    def test_the_amounts_decision_is_taken_once_for_the_whole_list(self):
        """قرارُ القناع مرّةٌ للقائمة لا لكل حركة: خمسُ حركاتٍ لا تكلّف أكثر من واحدة.

        `can_see_amounts` تقرأ العضوية ثم تجاوزَ الدور ثم تجاوزَ العضو؛ سؤالُها
        داخل `entry_row` كان يجعل ألفَ حركةٍ خمسةَ آلاف استعلام. يحرسه عددُ
        الاستعلامات نفسه لا السلوك (السلوكُ كان سليماً والحملُ خاطئ).
        """
        self.add_entry(self.mine, lines=self.balanced())
        # محاسبٌ لا مدير: `user_permissions` له تقرأ تجاوزَ الدور والعضو فعلاً،
        # فسؤالُها لكل صفّ يظهر في العدّ (المدير يخرج من الفحص مبكراً).
        self.as_user(self.accountant)
        with CaptureQueriesContext(connection) as one:
            self.client.get(f"{BOOKS}{self.mine.pk}/entries/", **self.headers())

        # الإدخالُ بمفتاح الكتابة — للمالك؛ والقراءةُ التي تُقاس للمحاسب.
        self.as_user(self.owner)
        for _ in range(4):
            self.add_entry(self.mine, lines=self.balanced())
        self.as_user(self.accountant)
        with CaptureQueriesContext(connection) as five:
            listing = self.client.get(f"{BOOKS}{self.mine.pk}/entries/", **self.headers())

        self.assertEqual(len(listing.data), 5)
        self.assertEqual(
            len(five), len(one),
            f"{len(one)} استعلاماً لحركةٍ و{len(five)} لخمس — القناعُ يُسأل لكل صفّ",
        )

    def test_writing_an_entry_needs_the_amounts_key(self):
        """ومن لا يرى المبالغ لا يكتبها — الحركةُ مبلغٌ بيد من يكتبها، والردُّ 403.

        يُمنح المحاسبُ مفتاحَ الكتابة وحده (تجاوزُ عضو): يمرّ من `require_write`
        ويسقط في حارس المبلغ — فالاختبارُ يقيس القناعَ لا المفتاح. و403 عقدُ
        الموديول (`reject_amount_writes`)، لا 400.
        """
        membership = UserCompanyMembership.objects.get(
            user=self.accountant, tenant=self.tenant,
        )
        MemberPermission.objects.create(
            membership=membership,
            permission_key="office.clients.write",
            allowed=True,
        )
        self.as_user(self.accountant)

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": LAST_YEAR_DAY.isoformat(),
                "kind": "sales_invoice",
                "lines": self.balanced(),
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 403, res.content)
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_another_office_entries_are_404(self):
        row = self.add_entry(self.mine, lines=self.balanced())
        self.as_user(self.manager_b)

        res = self.client.get(
            f"{BOOKS}{self.mine.pk}/entries/", **self.headers(tenant=self.tenant_b),
        )
        write = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {"entry_date": LAST_YEAR_DAY.isoformat(), "kind": "expense", "lines": self.balanced()},
            format="json",
            **self.headers(tenant=self.tenant_b),
        )

        self.assertEqual(res.status_code, 404, res.content)
        self.assertEqual(write.status_code, 404, write.content)
        self.assertTrue(BookEntry.objects.filter(pk=row["id"]).exists())

    def test_an_entry_of_another_client_in_the_same_office_is_404(self):
        """عزلٌ داخل المكتب: زبونان، وحركةُ أحدهما لا تُعكس باسم الآخر."""
        other = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونٌ آخر", responsible=self.accountant,
        )
        self.create_book(other, kind=BOOK_KIND_DOUBLE)
        row = self.add_entry(self.mine, lines=self.balanced())

        res = self.client.post(
            f"{BOOKS}{other.pk}/entries/{row['id']}/reverse/", {}, format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 404, res.content)


class KindChangeTest(ClientBookTestCase):
    def change(self, client, kind, expect=200):
        res = self.client.post(
            f"{BOOKS}{client.pk}/kind/", {"kind": kind}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def book_with_history(self):
        """دفترٌ فُتح السنة الماضية **بسيطاً** بحركةِ طرفٍ واحد، ثم انتقل للمزدوج.

        هذا هو التاريخ الذي كان يُكسر: التوازنُ يُفحص بالنوع الحالي فيرفض عكسَ
        حركةٍ قُبلت، ويُجبِر ورقةً متأخّرةً على قيدٍ مزدوج.
        """
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)
        original = self.add_entry(
            self.mine,
            lines=[{"account_code": "1100", "debit": "100.00"}],
            entry_date=LAST_YEAR_DAY,
        )
        self.change(self.mine, BOOK_KIND_DOUBLE)
        return original

    def test_switching_to_double_adds_the_missing_accounts_with_their_parents(self):
        """الانتقالُ يُكمل الشجرة: بلا ذاك يُرفض أوّل بندِ ضريبةٍ أو آجل."""
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)
        self.assertFalse(
            ClientBookAccount.objects.filter(client=self.mine, code="2200").exists(),
        )

        self.change(self.mine, BOOK_KIND_DOUBLE)

        vat = ClientBookAccount.objects.get(client=self.mine, code="2200")
        self.assertEqual(vat.parent.code, "2000")
        # أبو `1300` **قائمٌ** من شجرة البسيط (`known`) لا مضافٌ معه.
        receivable = ClientBookAccount.objects.get(client=self.mine, code="1300")
        self.assertEqual(receivable.parent.code, "1000")

    def test_switching_to_double_keeps_the_accounts_already_there(self):
        """الإكمالُ **يضيف** ولا ينسخ: الحسابُ القائم يبقى صفّاً واحداً."""
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)

        self.change(self.mine, BOOK_KIND_DOUBLE)

        self.assertEqual(
            ClientBookAccount.objects.filter(client=self.mine, code="1100").count(), 1,
        )

    def test_a_single_sided_entry_in_a_simple_year_is_still_accepted(self):
        """نوعُ الحركة نوعُ عهدها: سنةُ البسيط تبقى تُدخَل بطرفٍ واحد."""
        self.book_with_history()

        row = self.add_entry(
            self.mine,
            lines=[{"account_code": "1100", "debit": "30.00"}],
            entry_date=LAST_YEAR_DAY,
        )

        self.assertEqual(row["total_debit"], "30.00")
        self.assertEqual(row["total_credit"], "0.00")

    def test_a_single_sided_entry_in_the_double_year_is_400(self):
        self.book_with_history()

        self.add_entry(
            self.mine,
            lines=[{"account_code": "1100", "debit": "30.00"}],
            entry_date=datetime.date(THIS_YEAR, 1, 5),
            expect=400,
        )

    def test_a_simple_year_entry_is_still_reversible_after_the_change(self):
        """العكسُ بتاريخ الأصل يُقاس بنوع عهده — يُقبل ولو صار الدفتر مزدوجاً."""
        original = self.book_with_history()

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["reverses"], original["id"])

    def test_a_simple_year_entry_reversed_into_the_double_year_is_400(self):
        """العكسُ يُقاس **بنوع تاريخه**: مؤرَّخاً في سنة المزدوج يُفحص بتوازنها.

        إعفاءُ العكس كان يكتب هنا بنداً دائناً وحيداً في سنةٍ مزدوجة فيختلّ ميزانُها.
        """
        original = self.book_with_history()

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{original['id']}/reverse/",
            {"entry_date": datetime.date(THIS_YEAR, 1, 5).isoformat()},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("lines", res.data)
        self.assertFalse(BookEntry.objects.filter(reverses_id=original["id"]).exists())
        self.assertEqual(BookEntryLine.objects.filter(entry__client=self.mine).count(), 1)

    def test_switching_to_double_is_400_when_the_book_opened_this_year(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=datetime.date(THIS_YEAR, 1, 2))

        self.change(self.mine, BOOK_KIND_DOUBLE, expect=400)

        self.assertEqual(ClientBook.objects.get(client=self.mine).kind, BOOK_KIND_SIMPLE)

    def test_switching_to_double_is_400_when_this_year_has_entries(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)
        self.add_entry(
            self.mine,
            lines=[{"account_code": "1100", "debit": "10.00"}],
            entry_date=datetime.date(THIS_YEAR, 1, 5),
        )

        self.change(self.mine, BOOK_KIND_DOUBLE, expect=400)

        self.assertEqual(ClientBook.objects.get(client=self.mine).kind, BOOK_KIND_SIMPLE)

    def test_switching_to_double_is_allowed_from_the_start_of_a_later_year(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)
        self.add_entry(
            self.mine, lines=[{"account_code": "1100", "debit": "10.00"}],
        )

        row = self.change(self.mine, BOOK_KIND_DOUBLE)

        self.assertEqual(row["kind"], BOOK_KIND_DOUBLE)
        self.assertEqual(row["kind_changed_on"], timezone.localdate().isoformat())

    def test_switching_back_to_simple_is_always_400(self):
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE, opened_on=LAST_YEAR_DAY)

        self.change(self.mine, BOOK_KIND_SIMPLE, expect=400)

        self.assertEqual(ClientBook.objects.get(client=self.mine).kind, BOOK_KIND_DOUBLE)

    def test_an_unknown_kind_in_the_body_is_400(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)

        self.change(self.mine, "triple", expect=400)

    def test_a_kind_change_on_a_stopped_service_is_400(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)
        self.stop_bookkeeping(self.mine)

        self.change(self.mine, BOOK_KIND_DOUBLE, expect=400)


class PendingEntryTest(ClientBookTestCase):
    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

    def rows(self):
        res = self.client.get(PENDING, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def test_a_received_document_without_an_entry_is_pending(self):
        make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)

        payload = self.rows()

        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(payload["rows"]), 1)
        row = payload["rows"][0]
        self.assertEqual(row["client_id"], self.mine.pk)
        self.assertEqual(row["month"], f"{LAST_YEAR_DAY.year}-03")
        self.assertEqual(row["month_label"], "آذار")
        self.assertEqual(row["count"], 1)

    def test_a_document_that_has_not_arrived_is_not_pending(self):
        make_document(
            self.mine, year=LAST_YEAR_DAY.year, month=3, status=DOCUMENT_STATUS_REQUIRED,
        )

        self.assertEqual(self.rows()["total"], 0)

    def test_an_entered_document_leaves_the_pending_list(self):
        """«إدخالُ الشهر» منجزةٌ بالاشتقاق: لا عمودَ حالةٍ يُكتب، الورقةُ تخرج وحدها."""
        document = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        self.assertEqual(self.rows()["total"], 1)

        self.add_entry(self.mine, lines=self.balanced(), documents=[document.pk])

        self.assertEqual(self.rows()["total"], 0)

    def test_reversing_an_entry_returns_its_documents_to_pending(self):
        """الورقةُ تعود لأن الربطَ **يُقرأ**: حركةٌ معكوسةٌ ليست «مُدخلة» (د9).

        بالعمود الفريد كانت الورقةُ تبقى «انأدخلت» أبداً بعد العكس، فلا يمكن
        ربطُها بالحركة الصحيحة — شهرٌ يبدو منجزاً وصافيه صفر.
        """
        document = make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        row = self.add_entry(
            self.mine, lines=self.balanced(), documents=[document.pk],
        )
        self.assertEqual(self.rows()["total"], 0)

        self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/{row['id']}/reverse/",
            {}, format="json", **self.headers(),
        )

        self.assertEqual(self.rows()["total"], 1)

    def test_a_stopped_client_does_not_stay_in_the_pending_list(self):
        """دفترٌ صار للقراءة لا يُطلب إدخالُه: كلُّ إدخالٍ له 400، فلا يُصفَّر أبداً."""
        make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        self.assertEqual(self.rows()["total"], 1)

        self.stop_bookkeeping(self.mine)

        self.assertEqual(self.rows()["total"], 0)

    def test_a_client_without_a_book_is_not_listed(self):
        other = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونٌ بلا دفتر", responsible=self.accountant, bookkeeping=False,
        )
        make_document(other, year=LAST_YEAR_DAY.year, month=4)

        self.assertEqual(self.rows()["total"], 0)

    def test_two_months_of_one_client_are_two_rows(self):
        make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        make_document(self.mine, year=LAST_YEAR_DAY.year, month=4)

        payload = self.rows()

        self.assertEqual(payload["total"], 2)
        self.assertEqual(
            [row["month"] for row in payload["rows"]],
            [f"{LAST_YEAR_DAY.year}-03", f"{LAST_YEAR_DAY.year}-04"],
        )

    def test_the_count_does_not_add_a_query_per_client(self):
        """عدٌّ باستعلامٍ واحد: الزبائنُ يزدادون والاستعلاماتُ لا."""
        make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        with CaptureQueriesContext(connection) as one_client:
            self.rows()

        for index in range(3):
            extra = make_client(
                tenant=self.tenant, catalog=self.catalog,
                name=f"زبونٌ {index}", responsible=self.accountant,
            )
            self.create_book(extra, kind=BOOK_KIND_SIMPLE)
            make_document(extra, year=LAST_YEAR_DAY.year, month=3)
        with CaptureQueriesContext(connection) as four_clients:
            payload = self.rows()

        self.assertEqual(payload["total"], 4)
        self.assertEqual(len(four_clients), len(one_client))

    def test_another_office_sees_no_rows(self):
        make_document(self.mine, year=LAST_YEAR_DAY.year, month=3)
        self.as_user(self.manager_b)

        res = self.client.get(PENDING, **self.headers(tenant=self.tenant_b))

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["total"], 0)


#: أسماءُ ما لا يُستورد في كود دفتر الزبون — القاعدةُ في
#: `docs/decisions/client_books.md`، والقرارُ في التذكرة #286/د13.
FORBIDDEN_NAMES = frozenset({"post_journal", "JournalHeader", "JournalLine"})
GENERAL_JOURNAL_MODULE = "accounting"


def journal_references(source: str, *, label: str) -> list[str]:
    """كلُّ ذِكرٍ لمحرّك القيود العام في مصدرٍ ما — نواةُ المسح، تُختبَر وحدها."""
    hits: list[str] = []

    def is_general_journal(module: str) -> bool:
        # `accounting_office.…` ليس `accounting`: البادئةُ وحدها كانت ستُسقطه.
        return module == GENERAL_JOURNAL_MODULE or module.startswith(
            f"{GENERAL_JOURNAL_MODULE}.",
        )

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if is_general_journal(module):
                hits.append(f"{label}: from {module} import …")
            hits.extend(
                f"{label}: {alias.name}" for alias in node.names
                if alias.name in FORBIDDEN_NAMES
            )
        elif isinstance(node, ast.Import):
            hits.extend(
                f"{label}: import {alias.name}" for alias in node.names
                if is_general_journal(alias.name)
            )
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            hits.append(f"{label}: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            hits.append(f"{label}: .{node.attr}")
    return hits


class JournalExceptionGuardTest(APITestCase):
    """حارسُ الاستثناء المعماريّ: دفترُ الزبون لا يكتب في دفتر المكتب."""

    def test_the_book_module_exists(self):
        self.assertTrue(
            CLIENT_BOOKS_MODULE.exists(),
            f"وحدةُ دفتر الزبون مفقودة: {CLIENT_BOOKS_MODULE}",
        )

    def test_the_book_code_never_touches_the_general_journal(self):
        offenders: list[str] = []
        for path in (CLIENT_BOOKS_MODULE, BOOK_MODELS_MODULE):
            offenders.extend(
                journal_references(
                    path.read_text(encoding="utf-8"), label=path.name,
                ),
            )

        self.assertEqual(
            offenders, [],
            "دفترُ الزبون استورد محرّكَ القيود العام — القاعدةُ في "
            "`docs/decisions/client_books.md`:\n  " + "\n  ".join(offenders),
        )

    def test_the_guard_falls_on_a_synthetic_violation(self):
        """لو صار المسحُ أعمى (نمطٌ خاطئ أو قائمةٌ فارغة) يسقط هذا الاختبار."""
        self.assertEqual(
            journal_references(
                "from accounting.services import post_journal", label="probe",
            ),
            ["probe: from accounting.services import …", "probe: post_journal"],
        )
        self.assertTrue(
            journal_references("from accounting.models import JournalLine", label="probe"),
        )
        self.assertTrue(
            journal_references("rows = JournalHeader.objects.all()", label="probe"),
        )
        # والجارُ المشروعُ لا يُمسَك: `accounting_office` يبدأ بـ`accounting` حرفياً.
        self.assertEqual(
            journal_references(
                "from accounting_office.services import resolve_setting\n"
                "from accounting_office.models import BookEntry\n",
                label="probe",
            ),
            [],
        )
