"""تقاريرُ دفتر الزبون — الجزء (أ) من #288: محسوبةً على الخادم.

**ما يثبّته هذا الملفّ:**
- **ميزانُ المراجعة متوازنٌ بالضبط** على قيدٍ مزدوجٍ مبنيٍّ بيد: Σمدين = Σدائن،
  وميزانيةٌ مجموعاها متساويان (أصول = خصوم + حقوق + ربح الفترة).
- **الحركةُ المعكوسةُ وعكسُها لا يدخلان مجموعاً**: قيدٌ ثم عكسُه ⇒ كلُّ المجاميع
  صفر — لأن التقريرَ يقرأ الحركةَ الحيّةَ وحدها (`_live_entries`).
- **العزل**: زبونُ مكتبٍ آخر **404**، وزبونُ زميلٍ لا يراه العضو **404**.
- **القناع**: عضوٌ بلا `office.amounts.view` لا يصله مبلغٌ في أيّ تقرير، والبنيةُ
  والتسمياتُ تبقى.
- **الفترة**: حركةٌ خارج `from`/`to` لا تدخل، والافتراضُ من بداية السنة إلى اليوم.
- **`watermark`** في كل استجابة، والأنواعُ المتاحةُ تتبع نوعَ الدفتر (البسيطُ لا
  يعطي ميزانَ مراجعة، والمزدوجُ لا يعطي قبضاً ودفعاً).
- **`vat` غيرُ مبنيٍّ في هذا الجزء** — نسبتُه تحتاج قراراً (لا نوعَ حسابٍ ضريبيٍّ
  في النماذج اليوم)، والاختبارُ يثبّت غيابَه صراحةً كي لا يُظنّ سقوطاً.
- كشفُ الحساب: بحسابٍ أو بطرف، وبرصيدٍ جارٍ يبدأ من أرضية ما قبل الفترة.

كلُّ تقريرٍ يُقرأ بالـAPI كما تقرؤه الواجهة: `client-books/<client_id>/reports/…`.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office.book_reports import REPORT_AMOUNT_KEYS
from accounting_office.models import (
    BOOK_KIND_DOUBLE,
    BOOK_KIND_SIMPLE,
    BookEntry,
    BookEntryLine,
    ClientBook,
    ClientBookAccount,
)
from accounting_office.tests.test_client_books import (
    LAST_YEAR_DAY,
    make_client,
    seed_book_account_templates,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.models import TenantModule
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
BOOKS = f"{BASE}client-books/"
THIS_YEAR = timezone.localdate().year
WATERMARK = "نسخة عمل"

SIMPLE_KINDS = ["cash", "income", "receivables"]
DOUBLE_KINDS = ["trial_balance", "profit_loss", "balance_sheet", "statement"]
ENTRY_KINDS = [
    "sales_invoice", "purchase_invoice", "expense", "bank_movement", "daily_report",
]


def reports_url(client, kind=None):
    """فهرسُ التقارير أو تقريرٌ واحد — المسارُ معرّفُ الزبون لا الدفتر."""
    root = f"{BOOKS}{client.pk}/reports/"
    return root if kind is None else f"{root}{kind}/"


def money_values(payload):
    """كلُّ قيمةٍ تحت مفتاحِ مبلغٍ في حمولةٍ متداخلة — بنيةً لا نصّاً."""
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in REPORT_AMOUNT_KEYS:
                found.append(value)
            else:
                found.extend(money_values(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(money_values(item))
    return found


def rows_by_code(rows):
    return {row["account_code"]: row for row in rows}


class BookReportsTestCase(APITestCase):
    """مكتبٌ مرخَّصٌ بمالكه ومحاسبٍ وزميل، وزبونٌ بمسك دفاتر، ومكتبٌ ثانٍ للعزل."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_book_account_templates()

        cls.owner = User.objects.create_user(username="br_owner", password="x")
        cls.tenant = create_company(
            "مكتب تقارير الدفاتر", cls.owner, template="accounting_office",
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

        #: المحاسبُ يرى زبونَه (مسؤولٌ عنه) ولا يملك `office.amounts.view`.
        cls.accountant = member("br_accountant", "accountant")
        #: زميلٌ لا يرى زبونَ المحاسب — العزلُ داخل المكتب الواحد.
        cls.colleague = member("br_colleague", "accountant")
        cls.viewer = member("br_viewer", "viewer")

        cls.manager_b = User.objects.create_user(username="br_manager_b", password="x")
        cls.tenant_b = create_company(
            "مكتب التقارير الثاني", cls.manager_b, template="accounting_office",
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

    # ── أفعالٌ مشتركة ────────────────────────────────────────────────────
    def create_book(self, client, *, kind=BOOK_KIND_DOUBLE, opened_on=None, expect=201):
        payload = {"client_id": client.pk, "kind": kind}
        if opened_on is not None:
            payload["opened_on"] = opened_on.isoformat()
        res = self.client.post(BOOKS, payload, format="json", **self.headers())
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def add_entry(
        self, client, *, lines, entry_date, kind="sales_invoice", memo="",
        expect=201,
    ):
        res = self.client.post(
            f"{BOOKS}{client.pk}/entries/",
            {
                "entry_date": entry_date.isoformat(),
                "kind": kind,
                "memo": memo,
                "lines": lines,
            },
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def reverse_entry(self, client, entry_id, *, expect=201):
        res = self.client.post(
            f"{BOOKS}{client.pk}/entries/{entry_id}/reverse/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def change_kind(self, client, kind, *, expect=200):
        res = self.client.post(
            f"{BOOKS}{client.pk}/kind/", {"kind": kind}, format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def balanced(self, amount="100.00", *, debit_code="1100", credit_code="4100"):
        return [
            {"account_code": debit_code, "debit": amount},
            {"account_code": credit_code, "credit": amount},
        ]

    def get_report(self, client, kind, *, params=None, expect=200, tenant=None):
        res = self.client.get(
            reports_url(client, kind), params or {}, **self.headers(tenant=tenant),
        )
        self.assertEqual(res.status_code, expect, res.content)
        # 404 لهذا المسار ردُّ Django لا ردُّ DRF، فلا `.data` له.
        return getattr(res, "data", None)

    def kinds_of(self, client):
        res = self.client.get(reports_url(client), **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        return [row["kind"] for row in res.data["reports"]]

    def break_the_balance(self, *, amount="10.00", number=99):
        """قيدٌ مكسورٌ يُدسّ في القاعدة مباشرةً — الخدمةُ ترفضه، فيبقى اختبارُ الصرخة."""
        book = ClientBook.objects.get(client=self.mine)
        entry = BookEntry.objects.create(
            client_book=book,
            client=self.mine,
            year=THIS_YEAR,
            number=number,
            entry_date=datetime.date(THIS_YEAR, 3, 10),
            kind="daily_report",
        )
        BookEntryLine.objects.create(
            entry=entry,
            account=ClientBookAccount.objects.get(client=self.mine, code="1100"),
            debit=Decimal(amount),
        )
        return entry


class ReportsIndexTest(BookReportsTestCase):
    """الفهرسُ يتبع نوعَ الدفتر، ويحمل العلامةَ المائية نفسَها."""

    def test_a_simple_book_offers_the_three_simple_reports_only(self):
        self.create_book(self.mine, kind=BOOK_KIND_SIMPLE)

        kinds = self.kinds_of(self.mine)

        self.assertEqual(kinds, SIMPLE_KINDS)
        self.assertNotIn("trial_balance", kinds)

    def test_a_double_book_offers_the_four_double_reports_only(self):
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

        kinds = self.kinds_of(self.mine)

        self.assertEqual(kinds, DOUBLE_KINDS)
        self.assertNotIn("cash", kinds)

    def test_the_index_carries_the_watermark_client_and_titles(self):
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

        res = self.client.get(reports_url(self.mine), **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["watermark"], WATERMARK)
        self.assertEqual(res.data["client"], "زبوني")
        self.assertEqual(res.data["book_kind"], BOOK_KIND_DOUBLE)
        self.assertEqual(
            [row["title"] for row in res.data["reports"]],
            ["ميزان مراجعة", "أرباح وخسائر", "ميزانية", "كشف حساب"],
        )

    def test_the_index_needs_no_write_key(self):
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)
        self.as_user(self.accountant)

        self.assertEqual(self.kinds_of(self.mine), DOUBLE_KINDS)

    def test_vat_is_not_offered_in_this_part(self):
        """نسبةُ الضريبة تحتاج قراراً (لا نوعَ حسابٍ ضريبيٍّ في النماذج) — لا بناءَ الآن."""
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

        self.assertNotIn("vat", self.kinds_of(self.mine))
        self.get_report(self.mine, "vat", expect=404)

    def test_a_report_of_a_client_without_a_book_is_404(self):
        self.get_report(self.mine, "cash", expect=404)

    def test_posting_to_a_report_is_405(self):
        """قراءةٌ فقط: `POST` على التقرير لا ينشئ شيئاً."""
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

        res = self.client.post(
            reports_url(self.mine, "trial_balance"), {}, format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 405, res.content)

    def test_the_report_routes_are_behind_the_module_licence(self):
        """الطلبُ على **المكتب نفسه** يردّ 200، ويصير 404 لحظةَ إطفاء الترخيص.

        ولم يُطلب من شركةٍ أخرى عمداً: 404 هناك تأتي من العزل في `_book` ولو حُذف
        `require_module`، فيمرّ الاختبار بلا أن يقيس ما في اسمه.

        **والزبونُ مسؤولُه المالكُ نفسُه** لا المحاسب: `office.clients.all` مقيَّدٌ
        بالموديول، فإطفاءُ الترخيص يُسقطه من صلاحيات المالك، وزبونُ المحاسب كان
        يردّ 404 من `visible_clients` في `_book` ولو غاب `require_module` —
        فالاختبارُ كان يمرّ بلا حارس. مسؤولُه المالكُ يبقى مرئياً للمالك
        بالمسؤولية وحدها، فلا يُسقطه إلا البوّابةُ.
        """
        owned = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون المالك", responsible=self.owner,
        )
        self.create_book(owned, kind=BOOK_KIND_SIMPLE)
        paths = (reports_url(owned), reports_url(owned, "cash"))
        for path in paths:
            with self.subTest(path=path, licensed=True):
                self.assertEqual(
                    self.client.get(path, **self.headers()).status_code, 200,
                )

        TenantModule.objects.filter(
            tenant=self.tenant, module_key="accounting_office",
        ).update(enabled=False)
        invalidate_module_cache(self.tenant.pk)

        for path in paths:
            with self.subTest(path=path, licensed=False):
                self.assertEqual(
                    self.client.get(path, **self.headers()).status_code, 404,
                )


class DoubleBookTestCase(BookReportsTestCase):
    """دفترٌ مزدوج بقيدٍ متوازنٍ من كل نوع: بيعٌ نقديّ، مصروفٌ نقديّ، وشراءٌ بالآجل.

    الأرقامُ المختارةُ تُعطي ربحاً موجباً (٧٠) كي يُختبر إقفالُه في الميزانية.
    """

    def setUp(self):
        super().setUp()
        self.day = datetime.date(THIS_YEAR, 3, 10)
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE, opened_on=LAST_YEAR_DAY)
        self.add_entry(
            self.mine, entry_date=self.day, kind="sales_invoice",
            lines=[
                {"account_code": "1100", "debit": "200.00"},
                {"account_code": "4100", "credit": "200.00"},
            ],
        )
        self.add_entry(
            self.mine, entry_date=self.day, kind="expense",
            lines=[
                {"account_code": "5100", "debit": "80.00"},
                {"account_code": "1100", "credit": "80.00"},
            ],
        )
        self.add_entry(
            self.mine, entry_date=self.day, kind="purchase_invoice",
            lines=[
                {"account_code": "5200", "debit": "50.00"},
                {"account_code": "2100", "credit": "50.00"},
            ],
        )


class TrialBalanceTest(DoubleBookTestCase):
    """ميزانُ المراجعة: لكل حسابٍ Σمدين وΣدائن والرصيد، والمجموعان متساويان."""

    def test_the_trial_balance_is_balanced(self):
        payload = self.get_report(self.mine, "trial_balance")

        self.assertEqual(payload["kind"], "trial_balance")
        self.assertEqual(payload["title"], "ميزان مراجعة")
        self.assertEqual(payload["client"], "زبوني")
        self.assertTrue(payload["totals"]["balanced"])
        self.assertEqual(payload["totals"]["debit"], "330.00")
        self.assertEqual(payload["totals"]["credit"], "330.00")

    def test_every_account_carries_its_two_sides_and_its_balance(self):
        payload = self.get_report(self.mine, "trial_balance")

        rows = rows_by_code(payload["rows"])
        self.assertEqual(sorted(rows), ["1100", "2100", "4100", "5100", "5200"])
        self.assertEqual(rows["1100"]["debit"], "200.00")
        self.assertEqual(rows["1100"]["credit"], "80.00")
        self.assertEqual(rows["1100"]["balance"], "120.00")
        self.assertEqual(rows["4100"]["credit"], "200.00")
        self.assertEqual(rows["4100"]["balance"], "-200.00")
        self.assertEqual(rows["2100"]["account_type"], "liability")
        self.assertEqual(rows["2100"]["account_type_label"], "خصوم")
        self.assertEqual(rows["5200"]["balance"], "50.00")

    def test_the_amounts_are_decimal_strings_not_floats(self):
        """المبالغُ نصٌّ بخانتين — لا `float` يخسر هللةً على مجموعٍ كبير."""
        payload = self.get_report(self.mine, "trial_balance")

        self.assertIsInstance(payload["totals"]["debit"], str)
        self.assertIsInstance(payload["rows"][0]["debit"], str)
        self.assertEqual(payload["rows"][0]["debit"], "200.00")

    def test_an_unbalanced_book_is_an_explicit_error(self):
        self.break_the_balance()

        payload = self.get_report(self.mine, "trial_balance", expect=409)

        self.assertFalse(payload["totals"]["balanced"])
        self.assertEqual(payload["totals"]["debit"], "340.00")
        self.assertEqual(payload["totals"]["credit"], "330.00")
        self.assertIn("متوازن", payload["detail"])

    def test_the_report_does_not_add_a_query_per_entry_or_per_account(self):
        """التجميعُ صفٌّ لكل حساب: حركاتٌ وحساباتٌ جديدة لا تعني استعلاماً جديداً."""
        with CaptureQueriesContext(connection) as one:
            self.get_report(self.mine, "trial_balance")
        # الحسابان 1300 و2200 جديدان — صفّان يزيدان في التجميع لا استعلامان.
        for code in ("1300", "1300", "2200", "2200"):
            self.add_entry(
                self.mine, entry_date=self.day,
                lines=[
                    {"account_code": code, "debit": "10.00"},
                    {"account_code": "4100", "credit": "10.00"},
                ],
            )
        with CaptureQueriesContext(connection) as many:
            listing = self.get_report(self.mine, "trial_balance")

        rows = rows_by_code(listing["rows"])
        self.assertEqual(listing["totals"]["debit"], "370.00")
        self.assertIn("1300", rows)
        self.assertIn("2200", rows)
        self.assertEqual(
            len(many), len(one),
            f"{len(one)} استعلاماً و{len(many)} بعد أربع حركاتٍ وحسابين — صفٌّ لكل صفّ",
        )


class BalanceSheetTest(DoubleBookTestCase):
    """الميزانية: أصولٌ مقابل خصومٍ وحقوقِ ملكيةٍ وربحِ الفترة — والمجموعان متساويان."""

    def test_the_balance_sheet_balances(self):
        payload = self.get_report(self.mine, "balance_sheet")

        totals = payload["totals"]
        self.assertEqual(totals["assets"], "120.00")
        self.assertEqual(totals["liabilities"], "50.00")
        self.assertEqual(totals["equity"], "0.00")
        self.assertEqual(totals["profit"], "70.00")
        self.assertEqual(totals["liabilities_and_equity"], "120.00")
        self.assertEqual(totals["difference"], "0.00")
        self.assertEqual(
            Decimal(totals["assets"]), Decimal(totals["liabilities_and_equity"]),
        )

    def test_the_sheet_lists_balance_accounts_only(self):
        """الإيراداتُ والمصاريفُ لا صفوفَ لها في الميزانية — ربحُها في المجاميع."""
        payload = self.get_report(self.mine, "balance_sheet")

        rows = rows_by_code(payload["rows"])
        self.assertEqual(sorted(rows), ["1100", "2100"])
        self.assertEqual(rows["1100"]["balance"], "120.00")
        self.assertEqual(rows["1100"]["account_type_label"], "أصول")
        self.assertEqual(rows["2100"]["balance"], "50.00")

    def test_an_unbalanced_book_breaks_the_sheet_too(self):
        self.break_the_balance(number=98)

        payload = self.get_report(self.mine, "balance_sheet", expect=409)

        self.assertNotEqual(Decimal(payload["totals"]["difference"]), Decimal("0"))

    def test_a_capital_entry_from_the_previous_year_is_in_the_sheet(self):
        """ميزانيةُ اليوم رصيدٌ تراكميّ: رأسُ المال من سنةٍ سابقة لا يسقط.

        بُني التقريرُ على حركة الفترة أوّلاً، فكان يُسقط `3000` وكلَّ نقدٍ سابق
        ويبدو متوازناً بأرقامٍ ناقصة.
        """
        self.add_entry(
            self.mine, entry_date=LAST_YEAR_DAY, kind="daily_report",
            lines=[
                {"account_code": "1100", "debit": "1000.00"},
                {"account_code": "3000", "credit": "1000.00"},
            ],
        )

        payload = self.get_report(self.mine, "balance_sheet")

        totals = payload["totals"]
        self.assertEqual(totals["assets"], "1120.00")
        self.assertEqual(totals["equity"], "1000.00")
        self.assertEqual(totals["profit"], "70.00")
        self.assertEqual(totals["liabilities_and_equity"], "1120.00")
        self.assertEqual(totals["difference"], "0.00")
        self.assertIn("3000", rows_by_code(payload["rows"]))
        self.assertEqual(payload["from"], LAST_YEAR_DAY.isoformat())
        # لم يُقصّ شيء: الميزانيةُ تبدأ من العهد بطبيعتها، والملاحظةُ تقول ذلك.
        self.assertFalse(payload["clipped"])
        self.assertIn(str(LAST_YEAR_DAY.year), payload["period_note"])
        self.assertIn("رصيد", payload["period_note"])


class ProfitLossTest(DoubleBookTestCase):
    def test_profit_and_loss_subtracts_expenses_from_revenue(self):
        payload = self.get_report(self.mine, "profit_loss")

        self.assertEqual(payload["title"], "أرباح وخسائر")
        self.assertEqual(payload["totals"]["revenue"], "200.00")
        self.assertEqual(payload["totals"]["expense"], "130.00")
        self.assertEqual(payload["totals"]["profit"], "70.00")
        rows = rows_by_code(payload["rows"])
        self.assertEqual(sorted(rows), ["4100", "5100", "5200"])
        self.assertEqual(rows["4100"]["amount"], "200.00")
        self.assertEqual(rows["5100"]["amount"], "80.00")
        self.assertEqual(rows["5200"]["amount"], "50.00")


class DoubleEraTest(BookReportsTestCase):
    """الدفترُ المحوَّل: بدايةُ التقارير المزدوجة عهدُها المزدوج لا تاريخُ فتحها."""

    def setUp(self):
        super().setUp()
        self.create_book(
            self.mine, kind=BOOK_KIND_SIMPLE,
            opened_on=datetime.date(THIS_YEAR - 2, 1, 5),
        )
        # طرفٌ واحدٌ في العهد البسيط — مشروعٌ يومَها وغيرُ متوازن بالتصميم.
        self.add_entry(
            self.mine, entry_date=LAST_YEAR_DAY,
            lines=[{"account_code": "1100", "debit": "500.00"}],
        )
        # الانتقالُ يقع اليوم، فيبدأ العهدُ المزدوج من 1 يناير من هذه السنة.
        self.change_kind(self.mine, BOOK_KIND_DOUBLE)
        self.era_start = datetime.date(THIS_YEAR, 1, 1)
        self.add_entry(
            self.mine, entry_date=datetime.date(THIS_YEAR, 2, 10),
            lines=self.balanced("100.00"),
        )

    def test_a_period_before_the_transition_is_clipped_not_a_409(self):
        """فترةٌ تسبق الانتقال تُقصُّ وتُعلن، ولا تُرجع 409 على بياناتٍ سليمة."""
        payload = self.get_report(
            self.mine, "trial_balance",
            params={
                "from": datetime.date(LAST_YEAR_DAY.year, 1, 1).isoformat(),
                "to": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(payload["from"], self.era_start.isoformat())
        self.assertTrue(payload["clipped"])
        self.assertIn(str(THIS_YEAR), payload["period_note"])
        self.assertEqual(payload["totals"]["debit"], "100.00")
        self.assertEqual(payload["totals"]["credit"], "100.00")
        self.assertTrue(payload["totals"]["balanced"])
        # لو تسرّب قيدُ الطرف الواحد (500) لدخل هنا وصار 600.
        self.assertEqual(rows_by_code(payload["rows"])["1100"]["debit"], "100.00")

    def test_profit_and_loss_is_clipped_too(self):
        payload = self.get_report(
            self.mine, "profit_loss",
            params={"from": datetime.date(LAST_YEAR_DAY.year, 1, 1).isoformat()},
        )

        self.assertTrue(payload["clipped"])
        self.assertEqual(payload["totals"]["revenue"], "100.00")
        self.assertEqual(payload["totals"]["expense"], "0.00")

    def test_the_balance_sheet_starts_at_the_double_era(self):
        payload = self.get_report(self.mine, "balance_sheet")

        self.assertEqual(payload["from"], self.era_start.isoformat())
        self.assertEqual(payload["totals"]["assets"], "100.00")
        self.assertEqual(payload["totals"]["difference"], "0.00")

    def test_the_balance_sheet_clips_when_asked_before_the_era(self):
        """`from` أقدمَ من العهد ⇒ قصٌّ معلَن (`clipped`) وليس 409."""
        payload = self.get_report(
            self.mine, "balance_sheet",
            params={"from": datetime.date(LAST_YEAR_DAY.year, 1, 1).isoformat()},
        )

        self.assertEqual(payload["from"], self.era_start.isoformat())
        self.assertTrue(payload["clipped"])
        self.assertIn(str(THIS_YEAR), payload["period_note"])

    def test_a_period_ending_before_the_era_is_400(self):
        """ميزانيةٌ بلا مدى تُعيد صفحةً فارغةً «متوازنة» كذباً — فهي 400 لا 200."""
        for kind in ("trial_balance", "balance_sheet"):
            with self.subTest(kind=kind):
                payload = self.get_report(
                    self.mine, kind,
                    params={
                        "from": datetime.date(LAST_YEAR_DAY.year, 1, 1).isoformat(),
                        "to": LAST_YEAR_DAY.isoformat(),
                    },
                    expect=400,
                )
                self.assertIn("to", payload)

    def test_a_real_imbalance_still_returns_409(self):
        """القصُّ لفترةٍ لا يُخفي خللاً حقيقياً: قيدٌ مكسورٌ داخل العهد المزدوج 409."""
        self.break_the_balance()

        self.get_report(self.mine, "trial_balance", expect=409)


class UnconvertedDoubleBookTest(BookReportsTestCase):
    """دفترٌ مفتوحٌ مزدوجاً **لا عهدَ له**: `opened_on` ليست حدَّ عهد.

    افتراضُها يومُ إنشاء الدفتر، وقيودُ ما قبلها هي **المسارُ العادي** لاستقبال
    زبون (دفترٌ يُفتح في منتصف السنة ثم تُدخل حركاتُ يناير). ومصدرُ العهد الوحيد
    `kind_changed_on`: فالدفترُ الذي لم يتحوّل لا يُقصّ ولا يُحجب منه شيء.
    """

    def setUp(self):
        super().setUp()
        self.opened = datetime.date(THIS_YEAR, 3, 1)
        self.capital_day = datetime.date(THIS_YEAR, 1, 15)
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE, opened_on=self.opened)
        self.add_entry(
            self.mine, entry_date=self.capital_day, kind="daily_report",
            lines=self.balanced("1000.00", debit_code="1100", credit_code="3000"),
        )

    def test_a_capital_entry_before_opened_on_is_in_the_balance_sheet(self):
        payload = self.get_report(self.mine, "balance_sheet")

        totals = payload["totals"]
        self.assertEqual(totals["assets"], "1000.00")
        self.assertEqual(totals["equity"], "1000.00")
        self.assertEqual(totals["difference"], "0.00")
        self.assertFalse(payload["clipped"])
        # `from` الصادقة: بدايةُ الدفتر = أقدمُ ما فيه (قيدُ يناير لا `opened_on`).
        self.assertEqual(payload["from"], self.capital_day.isoformat())

    def test_the_default_trial_balance_is_not_clipped(self):
        payload = self.get_report(self.mine, "trial_balance")

        self.assertFalse(payload["clipped"])
        self.assertIsNone(payload["period_note"])
        self.assertEqual(payload["from"], datetime.date(THIS_YEAR, 1, 1).isoformat())
        self.assertEqual(payload["totals"]["debit"], "1000.00")
        self.assertEqual(payload["totals"]["credit"], "1000.00")

    def test_a_period_before_opened_on_is_200_not_400(self):
        """يناير–فبراير تسبق `opened_on`: الطلبُ سليمٌ والبياناتُ موجودة."""
        params = {
            "from": datetime.date(THIS_YEAR, 1, 1).isoformat(),
            "to": datetime.date(THIS_YEAR, 2, 28).isoformat(),
        }
        for kind in ("trial_balance", "profit_loss"):
            with self.subTest(kind=kind):
                payload = self.get_report(self.mine, kind, params=params)
                self.assertFalse(payload["clipped"])
                self.assertEqual(payload["from"], params["from"])
        trial = self.get_report(self.mine, "trial_balance", params=params)
        self.assertEqual(trial["totals"]["debit"], "1000.00")

    def test_a_balance_sheet_ending_before_the_first_entry_is_empty_not_400(self):
        payload = self.get_report(
            self.mine, "balance_sheet",
            params={"to": datetime.date(THIS_YEAR - 1, 12, 31).isoformat()},
        )

        self.assertEqual(payload["totals"]["assets"], "0.00")
        self.assertEqual(payload["rows"], [])
        # الملاحظةُ تصف الفراغ لا تدّعي بدايةً لم تحدث.
        self.assertIn("تسبق بداية الدفتر", payload["period_note"])


class ConvertedBookOpenedAfterTheEraTest(BookReportsTestCase):
    """دفترٌ محوَّلٌ `opened_on` فيه **بعد** سنة التحويل: القيودُ بينهما لا تسقط.

    `change_kind` لا يمنع إلا سنةَ الفتح نفسَها، فدفترٌ فُتح بتاريخ سنةٍ قادمة
    ثم تحوّل اليوم عهدُه المزدوجُ من 1 يناير من هذه السنة — لا من `opened_on`.
    """

    def setUp(self):
        super().setUp()
        self.create_book(
            self.mine, kind=BOOK_KIND_SIMPLE,
            opened_on=datetime.date(THIS_YEAR + 1, 1, 5),
        )
        self.change_kind(self.mine, BOOK_KIND_DOUBLE)
        self.entry_day = datetime.date(THIS_YEAR, 2, 10)
        self.add_entry(
            self.mine, entry_date=self.entry_day, lines=self.balanced("100.00"),
        )

    def test_a_double_entry_between_the_conversion_year_and_opened_on_stays(self):
        trial = self.get_report(self.mine, "trial_balance")

        self.assertEqual(trial["from"], datetime.date(THIS_YEAR, 1, 1).isoformat())
        self.assertEqual(trial["totals"]["debit"], "100.00")
        self.assertEqual(trial["totals"]["credit"], "100.00")

    def test_the_balance_sheet_keeps_it_too(self):
        sheet = self.get_report(self.mine, "balance_sheet")

        self.assertEqual(sheet["from"], datetime.date(THIS_YEAR, 1, 1).isoformat())
        self.assertEqual(sheet["totals"]["assets"], "100.00")
        self.assertEqual(sheet["totals"]["difference"], "0.00")


class ReversalTest(DoubleBookTestCase):
    """الحركةُ المعكوسةُ وعكسُها لا يدخلان مجموعاً — القاعدةُ في `_live_entries`."""

    def test_a_reversed_pair_adds_nothing_to_the_trial_balance(self):
        entry = self.add_entry(
            self.mine, entry_date=self.day, kind="daily_report",
            lines=self.balanced("40.00"),
        )
        self.reverse_entry(self.mine, entry["id"])

        payload = self.get_report(self.mine, "trial_balance")

        self.assertEqual(payload["totals"]["debit"], "330.00")
        self.assertEqual(payload["totals"]["credit"], "330.00")
        rows = rows_by_code(payload["rows"])
        self.assertEqual(rows["1100"]["debit"], "200.00")
        self.assertEqual(rows["1100"]["credit"], "80.00")

    def test_reversing_everything_leaves_zero_totals(self):
        """قيدٌ ثم عكسُه وحده: الصفوفُ فارغةٌ وكلُّ المجاميع صفر."""
        lonely = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونٌ بقيدٍ واحد", responsible=self.accountant,
        )
        self.create_book(lonely, kind=BOOK_KIND_DOUBLE, opened_on=LAST_YEAR_DAY)
        entry = self.add_entry(lonely, entry_date=self.day, lines=self.balanced("250.00"))
        self.reverse_entry(lonely, entry["id"])

        trial = self.get_report(lonely, "trial_balance")

        self.assertEqual(trial["rows"], [])
        self.assertEqual(trial["totals"]["debit"], "0.00")
        self.assertEqual(trial["totals"]["credit"], "0.00")
        self.assertTrue(trial["totals"]["balanced"])

    def test_a_reversed_pair_is_absent_from_the_statement(self):
        entry = self.add_entry(
            self.mine, entry_date=self.day, kind="daily_report",
            lines=[
                {"account_code": "1300", "debit": "40.00"},
                {"account_code": "4100", "credit": "40.00"},
            ],
        )
        self.reverse_entry(self.mine, entry["id"])

        payload = self.get_report(self.mine, "statement", params={"account": "1300"})

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["totals"]["debit"], "0.00")
        self.assertEqual(payload["totals"]["closing_balance"], "0.00")


class PeriodTest(DoubleBookTestCase):
    """الفترة: ما خارجها لا يدخل، والافتراضُ من بداية السنة إلى اليوم."""

    def test_an_entry_outside_the_period_is_excluded(self):
        outside = datetime.date(THIS_YEAR, 7, 15)
        self.add_entry(
            self.mine, entry_date=outside,
            lines=[
                {"account_code": "1100", "debit": "999.00"},
                {"account_code": "4100", "credit": "999.00"},
            ],
        )

        inside = self.get_report(
            self.mine, "trial_balance",
            params={"from": self.day.isoformat(), "to": self.day.isoformat()},
        )
        other = self.get_report(
            self.mine, "trial_balance",
            params={"from": outside.isoformat(), "to": outside.isoformat()},
        )

        self.assertEqual(inside["from"], self.day.isoformat())
        self.assertEqual(inside["totals"]["debit"], "330.00")
        self.assertEqual(other["totals"]["debit"], "999.00")
        self.assertEqual(sorted(rows_by_code(other["rows"])), ["1100", "4100"])

    def test_the_default_period_starts_at_the_start_of_the_year(self):
        """حركةُ سنةٍ سابقة لا تدخل الافتراضيَّ (من بداية السنة إلى اليوم)."""
        self.add_entry(
            self.mine, entry_date=LAST_YEAR_DAY, lines=self.balanced("40.00"),
        )

        default = self.get_report(self.mine, "trial_balance")
        explicit = self.get_report(
            self.mine, "trial_balance",
            params={
                "from": datetime.date(LAST_YEAR_DAY.year, 1, 1).isoformat(),
                "to": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(default["totals"]["debit"], "330.00")
        self.assertEqual(default["from"], datetime.date(THIS_YEAR, 1, 1).isoformat())
        self.assertEqual(explicit["totals"]["debit"], "370.00")

    def test_a_reversed_period_is_400(self):
        self.get_report(
            self.mine, "trial_balance",
            params={"from": "2026-05-01", "to": "2026-04-01"},
            expect=400,
        )

    def test_a_malformed_date_is_400(self):
        payload = self.get_report(
            self.mine, "trial_balance", params={"from": "2026-02-30"}, expect=400,
        )

        self.assertIn("from", payload)


class StatementTest(DoubleBookTestCase):
    """كشفُ الحساب: بحسابٍ أو بطرف، برصيدٍ جارٍ يبدأ من أرضية ما قبل الفترة."""

    def test_the_statement_lists_one_account_with_a_running_balance(self):
        payload = self.get_report(self.mine, "statement", params={"account": "1100"})

        self.assertEqual(payload["title"], "كشف حساب")
        self.assertEqual([row["debit"] for row in payload["rows"]], ["200.00", "0.00"])
        self.assertEqual([row["credit"] for row in payload["rows"]], ["0.00", "80.00"])
        self.assertEqual(
            [row["balance"] for row in payload["rows"]], ["200.00", "120.00"],
        )
        self.assertEqual(payload["totals"]["debit"], "200.00")
        self.assertEqual(payload["totals"]["credit"], "80.00")
        self.assertEqual(payload["totals"]["net"], "120.00")
        self.assertEqual(payload["totals"]["closing_balance"], "120.00")

    def test_the_statement_can_be_read_by_party(self):
        self.add_entry(
            self.mine, entry_date=self.day, kind="daily_report",
            lines=[
                {"account_code": "5100", "debit": "30.00", "side_party": "مورد الأثاث"},
                {"account_code": "1100", "credit": "30.00"},
            ],
        )

        payload = self.get_report(self.mine, "statement", params={"party": "مورد الأثاث"})

        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["side_party"], "مورد الأثاث")
        self.assertEqual(payload["rows"][0]["debit"], "30.00")

    def test_the_statement_needs_an_account_or_a_party(self):
        self.get_report(self.mine, "statement", expect=400)

    def test_both_an_account_and_a_party_is_400(self):
        self.get_report(
            self.mine, "statement",
            params={"account": "1100", "party": "مورد الأثاث"}, expect=400,
        )

    def test_an_account_outside_the_tree_is_400(self):
        """حسابٌ لا وجودَ له في شجرة الزبون — 400 لا كشفٌ فارغ."""
        self.get_report(self.mine, "statement", params={"account": "7777"}, expect=400)


class SimpleReportsTest(BookReportsTestCase):
    """التقاريرُ الثلاثةُ البسيطة على دفترٍ بسيط — قيودٌ بطرفٍ واحد."""

    def setUp(self):
        super().setUp()
        self.day = datetime.date(THIS_YEAR, 5, 12)
        self.create_book(
            self.mine, kind=BOOK_KIND_SIMPLE,
            opened_on=datetime.date(THIS_YEAR - 1, 1, 5),
        )
        self.add_entry(
            self.mine, entry_date=self.day,
            lines=[{"account_code": "1100", "debit": "300.00"}],
        )
        self.add_entry(
            self.mine, entry_date=self.day, kind="expense",
            lines=[{"account_code": "1100", "credit": "120.00"}],
        )
        self.add_entry(
            self.mine, entry_date=self.day, kind="expense",
            lines=[{"account_code": "5100", "debit": "60.00"}],
        )
        self.add_entry(
            self.mine, entry_date=self.day, kind="daily_report",
            lines=[{"account_code": "4100", "credit": "400.00"}],
        )

    def test_cash_sums_receipts_and_payments_per_entry_kind(self):
        """القبضُ والدفع على **الصندوق والبنك** وحدهما: 300 داخل و120 خارج ⇒ 180.

        ومصروفُ 5100 (60 مديناً) وإيرادُ 4100 (400 دائناً) ليسا نقداً فلا يدخلان:
        جمعُهما كان يُظهر −160 ورصيدُ الصندوق 180.
        """
        payload = self.get_report(self.mine, "cash")

        self.assertEqual(payload["title"], "قبض ودفع")
        rows = {row["kind"]: row for row in payload["rows"]}
        self.assertEqual(sorted(rows), sorted(ENTRY_KINDS))
        self.assertEqual(rows["sales_invoice"]["kind_label"], "فاتورة بيع")
        self.assertEqual(rows["sales_invoice"]["count"], 1)
        self.assertEqual(rows["sales_invoice"]["debit"], "300.00")
        self.assertEqual(rows["sales_invoice"]["net"], "300.00")
        # حركتا المصروف: واحدةٌ مدفوعةٌ من الصندوق وأخرى على حساب 5100 بلا نقد.
        self.assertEqual(rows["expense"]["count"], 1)
        self.assertEqual(rows["expense"]["debit"], "0.00")
        self.assertEqual(rows["expense"]["credit"], "120.00")
        self.assertEqual(rows["expense"]["net"], "-120.00")
        # الإيرادُ الدائنُ ليس دفعةً نقدية: لا يدخل جهة الدفع.
        self.assertEqual(rows["daily_report"]["count"], 0)
        self.assertEqual(rows["daily_report"]["credit"], "0.00")
        self.assertEqual(rows["bank_movement"]["debit"], "0.00")
        self.assertEqual(payload["totals"]["debit"], "300.00")
        self.assertEqual(payload["totals"]["credit"], "120.00")
        self.assertEqual(payload["totals"]["net"], "180.00")
        self.assertEqual(payload["totals"]["opening_balance"], "0.00")
        self.assertEqual(payload["totals"]["closing_balance"], "180.00")

    def test_the_cash_floor_is_what_came_before_the_period(self):
        self.add_entry(
            self.mine, entry_date=LAST_YEAR_DAY,
            lines=[{"account_code": "1100", "debit": "75.00"}],
        )

        payload = self.get_report(self.mine, "cash")

        self.assertEqual(payload["rows"][0]["kind"], "sales_invoice")
        self.assertEqual(payload["totals"]["opening_balance"], "75.00")
        self.assertEqual(payload["totals"]["closing_balance"], "255.00")

    def test_income_reads_the_account_types(self):
        payload = self.get_report(self.mine, "income")

        self.assertEqual(payload["title"], "إيرادات ومصاريف")
        rows = rows_by_code(payload["rows"])
        self.assertEqual(sorted(rows), ["4100", "5100"])
        self.assertEqual(rows["4100"]["account_type"], "revenue")
        self.assertEqual(rows["4100"]["account_type_label"], "إيرادات")
        self.assertEqual(rows["4100"]["amount"], "400.00")
        self.assertEqual(rows["5100"]["amount"], "60.00")
        self.assertEqual(payload["totals"]["revenue"], "400.00")
        self.assertEqual(payload["totals"]["expense"], "60.00")
        self.assertEqual(payload["totals"]["profit"], "340.00")

    def test_an_unpaid_sales_invoice_is_a_positive_balance_for_us(self):
        """فاتورةُ بيعٍ غيرُ مدفوعة: 4100 دائن 300 والطرفُ X ⇒ **+300** لنا عليه.

        `side_party` هو الطرفُ **المقابل** للبند، فالحسابُ من منظور الطرف: مدينُه
        Σ`credit` للبند ودائنُه Σ`debit` — بحساب `debit − credit` الخام كانت
        الفاتورةُ غيرُ المدفوعة تظهر **−300** والـdocstring يقول «الموجبُ لنا».
        """
        self.add_entry(
            self.mine, entry_date=self.day, kind="sales_invoice",
            lines=[
                {"account_code": "4100", "credit": "300.00", "side_party": "الطرف X"},
            ],
        )

        payload = self.get_report(self.mine, "receivables")

        rows = {row["side_party"]: row for row in payload["rows"]}
        self.assertEqual(rows["الطرف X"]["balance"], "300.00")
        self.assertEqual(rows["الطرف X"]["debit"], "300.00")
        self.assertEqual(rows["الطرف X"]["credit"], "0.00")

    def test_a_collection_from_the_party_clears_the_balance(self):
        """ثم قبضٌ 1100 مدين 300 من X ⇒ الرصيدُ **0**: دفع X لنا ما عليه."""
        self.add_entry(
            self.mine, entry_date=self.day, kind="sales_invoice",
            lines=[
                {"account_code": "4100", "credit": "300.00", "side_party": "الطرف X"},
            ],
        )
        self.add_entry(
            self.mine, entry_date=self.day, kind="daily_report",
            lines=[
                {"account_code": "1100", "debit": "300.00", "side_party": "الطرف X"},
            ],
        )

        payload = self.get_report(self.mine, "receivables")

        row = {row["side_party"]: row for row in payload["rows"]}["الطرف X"]
        self.assertEqual(row["debit"], "300.00")
        self.assertEqual(row["credit"], "300.00")
        self.assertEqual(row["balance"], "0.00")

    def test_receivables_are_the_party_balances_up_to_the_end(self):
        """الذممُ من **الطرف** لا من الحساب: الشجرةُ البسيطة بلا 1300/2100.

        ورصيدُ الطرف تراكميٌّ حتى `to`، فحركةُ سنةٍ سابقة تبقى في رصيده — و`from`
        المعروضةُ **بدايةُ الدفتر** لا `from` المطلوبة، كي لا يحمل الرأسُ تاريخاً لا
        يصف البيانات.
        """
        self.add_entry(
            self.mine, entry_date=self.day, kind="sales_invoice",
            lines=[
                {"account_code": "4100", "credit": "300.00", "side_party": "زبون الأثاث"},
            ],
        )
        # قبضٌ جزئيٌّ من سنةٍ سابقة (75 مدين على الصندوق من الطرف).
        self.add_entry(
            self.mine, entry_date=LAST_YEAR_DAY, kind="daily_report",
            lines=[
                {"account_code": "1100", "debit": "75.00", "side_party": "زبون الأثاث"},
            ],
        )

        payload = self.get_report(
            self.mine, "receivables",
            params={"from": datetime.date(THIS_YEAR, 5, 1).isoformat()},
        )

        self.assertEqual(payload["title"], "ذمم")
        rows = {row["side_party"]: row for row in payload["rows"]}
        self.assertEqual(sorted(rows), ["زبون الأثاث"])
        self.assertEqual(rows["زبون الأثاث"]["debit"], "300.00")
        self.assertEqual(rows["زبون الأثاث"]["credit"], "75.00")
        self.assertEqual(rows["زبون الأثاث"]["balance"], "225.00")
        self.assertEqual(payload["totals"]["debit_total"], "300.00")
        self.assertEqual(payload["totals"]["credit_total"], "75.00")
        self.assertNotIn("assets", payload["totals"])
        self.assertNotIn("liabilities", payload["totals"])
        self.assertTrue(payload["period_note"])
        # بدايةُ الدفتر (`opened_on` هنا أقدمُ من كل حركة) لا `from` المطلوبة.
        self.assertEqual(
            payload["from"], datetime.date(THIS_YEAR - 1, 1, 5).isoformat(),
        )
        self.assertFalse(payload["clipped"])

    def test_receivables_start_at_the_first_entry_when_it_precedes_opened_on(self):
        """`from` المعروضةُ `min(opened_on, أوّل حركةٍ حيّة)` لا `opened_on` وحدها."""
        late = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="دفترٌ فُتح متأخراً", responsible=self.accountant,
        )
        first = datetime.date(THIS_YEAR, 1, 15)
        self.create_book(
            late, kind=BOOK_KIND_SIMPLE, opened_on=datetime.date(THIS_YEAR, 3, 1),
        )
        self.add_entry(
            late, entry_date=first, kind="sales_invoice",
            lines=[{"account_code": "4100", "credit": "50.00", "side_party": "الطرف Y"}],
        )

        payload = self.get_report(late, "receivables")

        self.assertEqual(payload["from"], first.isoformat())
        self.assertEqual(payload["rows"][0]["balance"], "50.00")

    def test_a_line_without_a_party_is_not_a_receivable(self):
        """بنودُ الصندوق والبنك بلا طرفٍ ليست ذمماً — ولا صفَّ فارغاً في القائمة."""
        payload = self.get_report(self.mine, "receivables")

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["totals"]["debit_total"], "0.00")
        self.assertEqual(payload["totals"]["credit_total"], "0.00")

    def test_the_three_simple_reports_mask_the_amounts(self):
        """القناعُ في التقارير البسيطة أيضاً: `None` في الصفوف والمجاميع."""
        self.as_user(self.accountant)

        for kind in SIMPLE_KINDS:
            with self.subTest(kind=kind):
                payload = self.get_report(self.mine, kind)
                values = money_values(payload)
                self.assertTrue(values, f"{kind}: لم يُختبر مفتاحُ مبلغٍ واحد")
                self.assertEqual({value for value in values}, {None}, kind)
                self.assertEqual(payload["watermark"], WATERMARK)

    def test_a_double_report_on_a_simple_book_is_404(self):
        for kind in DOUBLE_KINDS:
            with self.subTest(kind=kind):
                self.get_report(self.mine, kind, expect=404)


class IsolationTest(BookReportsTestCase):
    """لا تقريرَ لزبونٍ لا يراه العضو — 404 لا 403."""

    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE, opened_on=LAST_YEAR_DAY)
        self.add_entry(
            self.mine, entry_date=datetime.date(THIS_YEAR, 4, 4),
            lines=self.balanced("500.00"),
        )

    def test_another_office_client_is_404(self):
        """مديرُ المكتب الثاني يطلب تقريرَ زبونٍ لا يراه — **404** لا 403."""
        self.as_user(self.manager_b)

        for kind in ("trial_balance", "profit_loss", "balance_sheet"):
            with self.subTest(kind=kind):
                self.get_report(self.mine, kind, tenant=self.tenant_b, expect=404)
                res = self.client.get(
                    reports_url(self.mine), **self.headers(tenant=self.tenant_b),
                )
                self.assertEqual(res.status_code, 404, res.content)

    def test_a_member_who_does_not_see_the_client_is_404(self):
        self.as_user(self.colleague)

        self.get_report(self.mine, "trial_balance", expect=404)
        self.assertEqual(
            self.client.get(reports_url(self.mine), **self.headers()).status_code, 404,
        )


class MaskTest(BookReportsTestCase):
    """القناع: لا مبلغَ ولا مجموعَ لعضوٍ بلا `office.amounts.view`، والبنيةُ تبقى."""

    def setUp(self):
        super().setUp()
        self.day = datetime.date(THIS_YEAR, 6, 6)
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE, opened_on=LAST_YEAR_DAY)
        self.add_entry(
            self.mine, entry_date=self.day,
            lines=[
                {"account_code": "1100", "debit": "777.00"},
                {"account_code": "4100", "credit": "777.00"},
            ],
        )

    def test_no_report_shows_an_amount_to_a_member_without_the_key(self):
        for kind, params in (
            ("trial_balance", {}),
            ("profit_loss", {}),
            ("balance_sheet", {}),
            ("statement", {"account": "1100"}),
        ):
            with self.subTest(kind=kind):
                self.as_user(self.owner)
                full = self.get_report(self.mine, kind, params=params)
                self.as_user(self.accountant)
                masked = self.get_report(self.mine, kind, params=params)

                values = money_values(masked)
                self.assertTrue(values, f"{kind}: لم يُختبر مفتاحُ مبلغٍ واحد")
                self.assertEqual({value for value in values}, {None}, kind)
                # البنيةُ والتسمياتُ لا تُقنَّع: عددُ الصفوف وترتيبُ الأكواد نفسُه.
                self.assertEqual(len(masked["rows"]), len(full["rows"]), kind)
                self.assertEqual(
                    [row.get("account_code") for row in masked["rows"]],
                    [row.get("account_code") for row in full["rows"]],
                    kind,
                )
                self.assertEqual(masked["title"], full["title"], kind)
                self.assertEqual(masked["watermark"], WATERMARK)

    def test_the_statement_keeps_its_dates_and_numbers_under_the_mask(self):
        self.as_user(self.accountant)

        masked = self.get_report(self.mine, "statement", params={"account": "1100"})

        self.assertEqual(len(masked["rows"]), 1)
        self.assertEqual(masked["rows"][0]["entry_date"], self.day.isoformat())
        self.assertEqual(masked["rows"][0]["number"], 1)
        self.assertIsNone(masked["rows"][0]["debit"])
        self.assertIsNone(masked["totals"]["closing_balance"])

    def test_an_imbalance_does_not_leak_the_totals_to_a_masked_member(self):
        """حتى رسالةُ 409 تحمل `None` بدل المبلغ — الرقمُ نفسُه مبلغٌ يُقنَّع."""
        self.break_the_balance()
        self.as_user(self.accountant)

        payload = self.get_report(self.mine, "trial_balance", expect=409)

        self.assertIsNone(payload["totals"]["debit"])
        self.assertIsNone(payload["totals"]["credit"])
        self.assertFalse(payload["totals"]["balanced"])


class ReportShapeTest(DoubleBookTestCase):
    """العقدُ المشترك: كلُّ استجابةٍ تحمل العلامةَ والفترةَ ونوعَ الدفتر."""

    def test_every_report_carries_its_header(self):
        # ميزانُ المراجعة وأرباحُ وخسائر يبدآن من السنة الجارية، والميزانيةُ من
        # بداية العهد المزدوج (تاريخ فتح الدفتر هنا) لأنها رصيدٌ لا حركةَ فترة.
        starts = {
            "trial_balance": datetime.date(THIS_YEAR, 1, 1),
            "profit_loss": datetime.date(THIS_YEAR, 1, 1),
            "balance_sheet": LAST_YEAR_DAY,
            "statement": datetime.date(THIS_YEAR, 1, 1),
        }
        for kind, params in (
            ("trial_balance", {}),
            ("profit_loss", {}),
            ("balance_sheet", {}),
            ("statement", {"account": "1100"}),
        ):
            with self.subTest(kind=kind):
                payload = self.get_report(self.mine, kind, params=params)

                self.assertEqual(payload["kind"], kind)
                self.assertEqual(payload["client"], "زبوني")
                self.assertEqual(payload["book_kind"], BOOK_KIND_DOUBLE)
                self.assertEqual(payload["book_kind_label"], "مزدوج")
                self.assertEqual(payload["watermark"], WATERMARK)
                self.assertEqual(payload["from"], starts[kind].isoformat())
                self.assertEqual(payload["to"], timezone.localdate().isoformat())
                self.assertIsInstance(payload["rows"], list)
                self.assertIsInstance(payload["totals"], dict)
                self.assertIsInstance(payload["clipped"], bool)

    def test_the_balance_sheet_declares_the_book_start(self):
        """دفترٌ لم يتحوّل لا عهدَ له: الميزانيةُ تعلن بدايتَها **من بداية الدفتر**.

        ولا تُسمّى ذلك «قصّاً» ولا تنسبه إلى «العهد المزدوج» — ذاك للمحوَّل وحده
        (`DoubleEraTest`).
        """
        payload = self.get_report(self.mine, "balance_sheet")

        self.assertEqual(payload["from"], LAST_YEAR_DAY.isoformat())
        self.assertFalse(payload["clipped"])
        self.assertIn(str(LAST_YEAR_DAY.year), payload["period_note"])
        self.assertIn("بداية الدفتر", payload["period_note"])
        self.assertNotIn("العهد المزدوج", payload["period_note"])

    def test_a_period_inside_the_double_era_is_not_clipped(self):
        payload = self.get_report(self.mine, "trial_balance")

        self.assertFalse(payload["clipped"])
        self.assertIsNone(payload["period_note"])

    def test_the_simple_reports_have_the_same_header_shape(self):
        other = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونٌ بسيط", responsible=self.accountant,
        )
        self.create_book(other, kind=BOOK_KIND_SIMPLE, opened_on=LAST_YEAR_DAY)

        for kind in SIMPLE_KINDS:
            with self.subTest(kind=kind):
                payload = self.get_report(other, kind)

                self.assertEqual(payload["kind"], kind)
                self.assertEqual(payload["client"], "زبونٌ بسيط")
                self.assertEqual(payload["book_kind"], BOOK_KIND_SIMPLE)
                self.assertEqual(payload["book_kind_label"], "بسيط")
                self.assertEqual(payload["watermark"], WATERMARK)
                self.assertIsInstance(payload["rows"], list)
                self.assertIsInstance(payload["totals"], dict)
