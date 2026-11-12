"""توليدُ بنود الحركة من الورقة — #286/ج.

**ما يثبّته هذا الملفّ:**
- **المبلغُ والضريبةُ والطرفُ من الورقة**: الموظّفُ لا يكتب حساباً ولا رقماً،
  والحركةُ تُولَّد من `amount + tax_amount` وحدهما.
- **التوازنُ رياضيّاً** في المزدوج: مدينُ السطور = دائنُها في كل حالة، والضريبةُ
  على حسابها (`2200`) في الطرف المقابل للاتجاه — دائنةٌ للبيع والتقرير اليومي،
  مدينةٌ للمشتريات والمصروف.
- **الضريبةُ مرّةً واحدة**: مجموعُ `tax_amount` على السطور = ضريبةُ الورقة، وهو
  ما تقرؤه تقاريرُ #287 — تكرارُها على سطرين يضاعف الإقرار.
- **الدفترُ البسيط سطرٌ واحد** بمبلغه الإجمالي وضريبتِه عليه.
- **الرفضُ برسالته**: ورقةٌ بلا مبلغ، وأوراقٌ من شهرين، وحركةُ بنكٍ بضريبة،
  وشجرةٌ بلا حساب ضريبة، وورقةٌ أُدخلت سابقاً أو لزبونٍ آخر.
- **القناعُ والحارس**: بلا `office.amounts.view` لا توليدَ ولا كتابةَ مبلغِ ورقة
  (**403**)، والقراءةُ مقنَّعة.
- **والقيدُ اليدويُّ القائم** (`entries/` بـ`lines`) يعمل كما كان.

الأوراقُ من الشهر نفسه (`period_start` متساوٍ)، وتاريخُ الحركة افتراضاً
`period_end` لذلك الشهر.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError

from accounting_office import client_books, services
from accounting_office.models import (
    BOOK_ENTRY_KIND_BANK_MOVEMENT,
    BOOK_ENTRY_KIND_DAILY_REPORT,
    BOOK_ENTRY_KIND_EXPENSE,
    BOOK_ENTRY_KIND_MANUAL,
    BOOK_ENTRY_KIND_OPENING,
    BOOK_ENTRY_KIND_PURCHASE_INVOICE,
    BOOK_ENTRY_KIND_SALES_INVOICE,
    BOOK_KIND_DOUBLE,
    BOOK_KIND_SIMPLE,
    BookEntry,
    BookEntryLine,
    ClientBookAccount,
)
from accounting_office.tests.test_client_books import (
    BOOKS,
    ClientBookTestCase,
    THIS_YEAR,
    make_client,
    make_document,
    month_bounds,
)

#: نهايةُ شهر الاختبار — تاريخُ الحركة الافتراضيّ. والسنةُ الجارية كي يقع الترقيمُ
#: في سنةٍ واحدة واضحة.
_, JAN_END = month_bounds(THIS_YEAR, 1)

#: حسابُ الضريبة في شجرة الزبون — الكودُ الذي يُقرأ ولا يُصطنع له صفّ.
VAT_CODE = "2200"


def money(line, key):
    """قيمةُ مدين/دائن/ضريبةٍ في سطرٍ كنصٍّ من خانتين — مقارنةً لا حساباً."""
    return Decimal(line[key]).quantize(Decimal("0.01"))


class BookEntryGenerationTestCase(ClientBookTestCase):
    """مكتبٌ وزبونٌ ودفترٌ مزدوجٌ — والأوراقُ تُنشأ في كل اختبار بما يحتاجه."""

    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)

    # ── أفعالٌ مشتركة ────────────────────────────────────────────────────

    def paper(
        self, *, amount=None, tax=None, rate=None, party="", month=1,
        code="vat_return", name="فاتورة", client=None,
    ):
        """ورقةٌ واصلةٌ بقيمها — والحقولُ الغائبةُ تبقى فارغةً عمداً."""
        row = make_document(
            client or self.mine, year=THIS_YEAR, month=month, code=code,
        )
        row.name = name
        row.amount = None if amount is None else Decimal(amount)
        row.tax_amount = None if tax is None else Decimal(tax)
        row.vat_rate = None if rate is None else Decimal(rate)
        row.side_party = party
        row.save(update_fields=[
            "name", "amount", "tax_amount", "vat_rate", "side_party",
        ])
        return row

    def generate(
        self, papers, *, kind=BOOK_ENTRY_KIND_SALES_INVOICE, entry_date=None,
        memo="", expect=201, client=None,
    ):
        payload = {"kind": kind, "documents": [row.pk for row in papers]}
        if entry_date is not None:
            payload["entry_date"] = entry_date.isoformat()
        if memo:
            payload["memo"] = memo
        res = self.client.post(
            f"{BOOKS}{(client or self.mine).pk}/entries/from-documents/",
            payload, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def lines_by_code(self, entry):
        return {line["account_code"]: line for line in entry["lines"]}

    def sums_by_code(self, entry, key):
        """مجموعُ مبلغٍ لكل حساب — حركةُ شهرٍ فيها سطران بالحساب نفسه (ورقتان)."""
        totals = {}
        for line in entry["lines"]:
            totals[line["account_code"]] = (
                totals.get(line["account_code"], Decimal("0")) + money(line, key)
            )
        return totals

    def totals(self, entry):
        debit = sum(money(line, "debit") for line in entry["lines"])
        credit = sum(money(line, "credit") for line in entry["lines"])
        tax = sum(money(line, "tax_amount") for line in entry["lines"])
        return debit, credit, tax

    def status_of(self, paper, *, payload, expect=200, tenant=None):
        return self.client.post(
            f"/api/accounting-office/documents/{paper.pk}/status/",
            payload, format="json", **self.headers(tenant=tenant),
        )


class DoubleBookGenerationTest(BookEntryGenerationTestCase):
    """النوعُ المزدوج: سطرا الحسابين وسطرُ الضريبة، بالطرف المقابل للاتجاه."""

    def test_a_sales_invoice_is_three_balanced_lines_with_the_party_on_receivables(self):
        """فاتورةُ بيعٍ (100 صافي + 17 ضريبة): الذممُ مدينةٌ بالإجمالي والإيرادُ دائنٌ بالصافي."""
        row = self.paper(
            amount="100", tax="17", party="شركة الأمل",
            name="فاتورة بيع يناير",
        )

        entry = self.generate([row], kind=BOOK_ENTRY_KIND_SALES_INVOICE)

        self.assertEqual(entry["kind"], BOOK_ENTRY_KIND_SALES_INVOICE)
        self.assertEqual(len(entry["lines"]), 3)
        lines = self.lines_by_code(entry)
        self.assertEqual(set(lines), {"1300", "4100", VAT_CODE})
        self.assertEqual(money(lines["1300"], "debit"), Decimal("117.00"))
        self.assertEqual(money(lines["1300"], "credit"), Decimal("0.00"))
        self.assertEqual(lines["1300"]["side_party"], "شركة الأمل")
        self.assertEqual(money(lines["4100"], "credit"), Decimal("100.00"))
        self.assertEqual(money(lines["4100"], "tax_base"), Decimal("100.00"))
        self.assertEqual(money(lines["2200"], "credit"), Decimal("17.00"))
        self.assertEqual(money(lines["2200"], "tax_amount"), Decimal("17.00"))
        debit, credit, tax = self.totals(entry)
        self.assertEqual(debit, credit)
        self.assertEqual(debit, Decimal("117.00"))
        self.assertEqual(tax, Decimal("17.00"), "الضريبةُ مرّةً واحدة لا على سطرين")

    def test_an_expense_debits_the_expense_and_the_tax_and_credits_the_cash_in_full(self):
        """مصروفٌ (200 + 34): 5100 مدينٌ بالصافي و2200 مدينٌ بالضريبة و1100 دائنٌ بالإجمالي.

        والبديهيّ «5100 مدينٌ بالإجمالي و2200 مدينٌ بالضريبة» غيرُ متوازن:
        234 + 34 = 268 مقابل 268؟ لا — دائنُ الصندوق 234 وحده. فالتوازنُ يفرض
        أن يحمل سطرُ المصروف صافيه وأن يجمع الدائنُ الصافيَ والضريبة.
        """
        row = self.paper(amount="200", tax="34", party="مورّد الكهرباء")

        entry = self.generate([row], kind=BOOK_ENTRY_KIND_EXPENSE)

        lines = self.lines_by_code(entry)
        self.assertEqual(len(entry["lines"]), 3)
        self.assertEqual(money(lines["5100"], "debit"), Decimal("200.00"))
        self.assertEqual(money(lines["5100"], "tax_base"), Decimal("200.00"))
        self.assertEqual(money(lines["2200"], "debit"), Decimal("34.00"))
        self.assertEqual(money(lines["2200"], "tax_amount"), Decimal("34.00"))
        self.assertEqual(money(lines["1100"], "credit"), Decimal("234.00"))
        self.assertEqual(lines["5100"]["side_party"], "مورّد الكهرباء")
        debit, credit, tax = self.totals(entry)
        self.assertEqual(debit, Decimal("200.00") + Decimal("34.00"))
        self.assertEqual(credit, Decimal("234.00"))
        self.assertEqual(debit, credit)
        self.assertEqual(tax, Decimal("34.00"))

    def test_a_purchase_invoice_credits_payables_in_full_and_carries_the_party_there(self):
        row = self.paper(
            amount="100", tax="17", party="مورد الأثاث",
            name="فاتورة شراء",
        )

        entry = self.generate([row], kind=BOOK_ENTRY_KIND_PURCHASE_INVOICE)

        lines = self.lines_by_code(entry)
        self.assertEqual(money(lines["5200"], "debit"), Decimal("100.00"))
        self.assertEqual(money(lines["2200"], "debit"), Decimal("17.00"))
        self.assertEqual(money(lines["2100"], "credit"), Decimal("117.00"))
        self.assertEqual(lines["2100"]["side_party"], "مورد الأثاث")
        debit, credit, tax = self.totals(entry)
        self.assertEqual((debit, credit), (Decimal("117.00"), Decimal("117.00")))
        self.assertEqual(tax, Decimal("17.00"))

    def test_a_daily_report_credits_revenue_and_vat(self):
        row = self.paper(amount="100", tax="17")

        entry = self.generate([row], kind=BOOK_ENTRY_KIND_DAILY_REPORT)

        lines = self.lines_by_code(entry)
        self.assertEqual(money(lines["1100"], "debit"), Decimal("117.00"))
        self.assertEqual(money(lines["4100"], "credit"), Decimal("100.00"))
        self.assertEqual(money(lines["2200"], "credit"), Decimal("17.00"))
        debit, credit, tax = self.totals(entry)
        self.assertEqual((debit, credit), (Decimal("117.00"), Decimal("117.00")))
        self.assertEqual(tax, Decimal("17.00"))

    def test_a_bank_movement_without_tax_is_two_lines_on_the_bank_and_the_cash(self):
        row = self.paper(amount="500", party="تحويل داخلي")

        entry = self.generate([row], kind=BOOK_ENTRY_KIND_BANK_MOVEMENT)

        lines = self.lines_by_code(entry)
        self.assertEqual(money(lines["1200"], "debit"), Decimal("500.00"))
        self.assertEqual(money(lines["1100"], "credit"), Decimal("500.00"))


class SimpleBookGenerationTest(BookEntryGenerationTestCase):
    """الدفترُ البسيط: طرفٌ واحد — سطرٌ واحدٌ بالإجمالي والضريبةُ عليه."""

    def setUp(self):
        super().setUp()
        self.simple_client = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون الدفتر البسيط", responsible=self.accountant,
        )
        self.create_book(self.simple_client, kind=BOOK_KIND_SIMPLE)

    def test_a_sale_is_one_debit_line_carrying_the_total_and_the_tax(self):
        row = self.paper(
            amount="100", tax="17", party="زبون نقدي", client=self.simple_client,
        )

        entry = self.generate(
            [row], kind=BOOK_ENTRY_KIND_SALES_INVOICE, client=self.simple_client,
        )

        self.assertEqual(len(entry["lines"]), 1)
        line = entry["lines"][0]
        self.assertEqual(line["account_code"], "1100")
        self.assertEqual(money(line, "debit"), Decimal("117.00"))
        self.assertEqual(money(line, "credit"), Decimal("0.00"))
        self.assertEqual(money(line, "tax_base"), Decimal("100.00"))
        self.assertEqual(money(line, "tax_amount"), Decimal("17.00"))
        self.assertEqual(line["side_party"], "زبون نقدي")

    def test_an_expense_is_one_credit_line_carrying_the_total(self):
        row = self.paper(amount="200", tax="34", client=self.simple_client)

        entry = self.generate(
            [row], kind=BOOK_ENTRY_KIND_EXPENSE, client=self.simple_client,
        )

        self.assertEqual(len(entry["lines"]), 1)
        line = entry["lines"][0]
        self.assertEqual(line["account_code"], "1100")
        self.assertEqual(money(line, "credit"), Decimal("234.00"))
        self.assertEqual(money(line, "tax_base"), Decimal("200.00"))
        self.assertEqual(money(line, "tax_amount"), Decimal("34.00"))


class PaperValidationTest(BookEntryGenerationTestCase):
    """الرفضُ برسالته: لا رقمَ مصطنعٌ ولا حركةٌ نصفها مكتوب."""

    def test_a_paper_without_an_amount_is_400_naming_the_paper(self):
        row = self.paper(amount=None, tax="17", name="فاتورة ناقصة")

        error = self.generate([row], expect=400)

        self.assertIn("فاتورة ناقصة", str(error))
        self.assertIn("بلا مبلغ", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_papers_from_two_months_are_400(self):
        january = self.paper(amount="100", month=1, code="vat_return")
        february = self.paper(amount="100", month=2, code="vat_return")

        error = self.generate([january, february], expect=400)

        self.assertIn("أشهرٍ مختلفة", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_bank_movement_with_tax_is_400(self):
        row = self.paper(amount="100", tax="17")

        error = self.generate([row], kind=BOOK_ENTRY_KIND_BANK_MOVEMENT, expect=400)

        self.assertIn("حركةُ بنكٍ بلا ضريبة", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_tree_without_the_vat_account_is_400_naming_the_missing_account(self):
        ClientBookAccount.objects.filter(client=self.mine, code=VAT_CODE).delete()
        row = self.paper(amount="100", tax="17")

        error = self.generate([row], expect=400)

        self.assertIn(VAT_CODE, str(error))
        self.assertIn("شجرة الزبون", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_paper_already_entered_is_400(self):
        row = self.paper(amount="100")
        self.generate([row])

        error = self.generate([row], expect=400)

        self.assertIn("مُدخلة", str(error))
        self.assertEqual(BookEntry.objects.filter(client=self.mine).count(), 1)

    def test_a_paper_of_another_client_is_400(self):
        other = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونٌ آخر", responsible=self.accountant,
        )
        row = self.paper(amount="100", client=other)

        error = self.generate([row], expect=400)

        self.assertIn("لهذا الزبون", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_negative_amount_is_400(self):
        row = self.paper(amount="-100")

        error = self.generate([row], expect=400)

        self.assertIn("سالب", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())


class MonthBatchTest(BookEntryGenerationTestCase):
    """الشهرُ كلُّه في حركةٍ واحدة: بندٌ لكل ورقة، والضريبةُ مجموعةٌ مرةً واحدة."""

    def test_two_papers_of_one_month_become_one_entry_and_both_are_marked_entered(self):
        first = self.paper(amount="100", tax="17", month=1, code="vat_return")
        second = self.paper(amount="200", tax="34", month=1, code="income_tax")

        entry = self.generate([first, second])

        self.assertEqual(entry["entry_date"], JAN_END.isoformat())
        self.assertEqual(sorted(entry["documents"]), sorted([first.pk, second.pk]))
        # بندان لكل ورقة: سطرا حسابَيها وسطرُ ضريبتها — لا حركةٌ ثانية.
        self.assertEqual(len(entry["lines"]), 6)
        debits = self.sums_by_code(entry, "debit")
        credits = self.sums_by_code(entry, "credit")
        taxes = self.sums_by_code(entry, "tax_amount")
        self.assertEqual(debits["1300"], Decimal("351.00"))
        self.assertEqual(credits["4100"], Decimal("300.00"))
        self.assertEqual(credits["2200"], Decimal("51.00"))
        self.assertEqual(taxes["2200"], Decimal("51.00"))
        debit, credit, tax = self.totals(entry)
        self.assertEqual(debit, credit)
        self.assertEqual(tax, Decimal("17.00") + Decimal("34.00"))
        self.assertEqual(
            BookEntryLine.objects.filter(entry_id=entry["id"]).count(), 6,
        )

        pending = self.client.get(f"{BOOKS}pending-entry/", **self.headers())
        self.assertEqual(pending.status_code, 200, pending.content)
        self.assertEqual(pending.data["total"], 0)
        self.assertEqual(pending.data["rows"], [])

    def test_an_explicit_entry_date_is_honoured(self):
        row = self.paper(amount="100", month=1)
        explicit = datetime.date(THIS_YEAR, 1, 15)

        entry = self.generate([row], entry_date=explicit)

        self.assertEqual(entry["entry_date"], explicit.isoformat())


class PaperAmountsApiTest(BookEntryGenerationTestCase):
    """حقولُ الورقة تُكتب وتُقرأ بمساراتها — والمبلغُ يصل مقنَّعاً لمن لا يراه."""

    def test_the_amounts_are_written_with_the_status_and_come_back_on_the_row(self):
        row = self.paper(amount=None)

        res = self.status_of(row, payload={
            "status": "received",
            "channel": "whatsapp",
            "amount": "100.00",
            "tax_amount": "17.00",
            "vat_rate": "17.00",
            "side_party": "شركة الأمل",
        })

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Decimal(res.data["amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(res.data["tax_amount"]), Decimal("17.00"))
        self.assertEqual(res.data["side_party"], "شركة الأمل")
        row.refresh_from_db()
        self.assertEqual(row.amount, Decimal("100.00"))
        self.assertEqual(row.side_party, "شركة الأمل")

    def test_a_member_without_the_amounts_key_cannot_write_the_paper_amount(self):
        """**403 لا 400**: الحركةُ مبلغٌ، ومن لا يراه لا يكتبه (عقدُ الموديول)."""
        row = self.paper(amount=None)
        self.as_user(self.accountant)

        res = self.status_of(row, payload={
            "status": "received", "channel": "paper", "amount": "100.00",
        })

        self.assertEqual(res.status_code, 403, res.content)
        row.refresh_from_db()
        self.assertIsNone(row.amount)

    def test_the_paper_amounts_are_masked_for_a_member_without_the_amounts_key(self):
        row = self.paper(amount="100", tax="17", party="شركة الأمل")
        self.as_user(self.accountant)

        res = self.status_of(row, payload={
            "status": "received", "channel": "paper",
        })

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNone(res.data["amount"])
        self.assertIsNone(res.data["tax_amount"])
        self.assertEqual(res.data["side_party"], "شركة الأمل")

    def test_an_entered_paper_refuses_amount_edits_and_says_to_reverse(self):
        row = self.paper(amount="100")
        self.generate([row])

        res = self.status_of(row, payload={
            "status": "received", "channel": "paper", "amount": "999.00",
        })

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("عكسية", str(res.data))
        row.refresh_from_db()
        self.assertEqual(row.amount, Decimal("100.00"))


class GenerationPermissionTest(BookEntryGenerationTestCase):
    """بلا `office.amounts.view` لا توليدَ من الورقة — 403 لا 400."""

    def test_generating_from_a_paper_needs_the_amounts_key(self):
        row = self.paper(amount="100")
        self.as_user(self.accountant)

        error = self.generate([row], expect=403)

        self.assertIn("المبالغ", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_the_paper_of_another_office_is_404(self):
        self.as_user(self.manager_b)

        res = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/from-documents/",
            {"kind": BOOK_ENTRY_KIND_SALES_INVOICE, "documents": [1]},
            format="json", **self.headers(tenant=self.tenant_b),
        )

        self.assertEqual(res.status_code, 404, res.content)

    def test_manual_and_opening_are_not_generated_from_papers(self):
        row = self.paper(amount="100")

        # الـAPI يرفض النوعَ من قائمته قبل أن يصل الخدمة.
        self.generate([row], kind=BOOK_ENTRY_KIND_MANUAL, expect=400)
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

        # والخدمةُ ترفضه برسالتها: نداءٌ برمجيٌّ يمرّ من هنا لا من المسلسِل.
        with self.assertRaises(DjangoValidationError) as caught:
            client_books.generate_entry_lines(
                self.mine.book, kind=BOOK_ENTRY_KIND_OPENING,
                papers=[row], entry_date=JAN_END,
            )
        self.assertIn("بأيديهما", str(caught.exception))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())


class LineRateFromPaperTest(BookEntryGenerationTestCase):
    """نسبةُ الورقة على سطرها — **بإعدادٍ وسبب**، ومطفأً تبقى فارغةً لا رفضاً."""

    def test_the_paper_rate_is_written_with_its_reason_only_when_the_setting_is_on(self):
        off = self.paper(amount="100", tax="17", rate="17", month=1)

        without = self.generate([off])

        line = self.lines_by_code(without)["2200"]
        self.assertIsNone(line["vat_rate"])
        self.assertEqual(line["vat_rate_reason"], "")

        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, True)
        on = self.paper(
            amount="100", tax="17", rate="17", month=2, code="income_tax",
        )

        with_rate = self.generate([on])

        line = self.lines_by_code(with_rate)["2200"]
        self.assertEqual(Decimal(line["vat_rate"]), Decimal("17.0000"))
        self.assertEqual(line["vat_rate_reason"], "من الورقة")


class ManualEntryRegressionTest(BookEntryGenerationTestCase):
    """القيدُ اليدويُّ القائم (`entries/` بـ`lines`) لم يتغيّر — ولا يُولَّد من ورقة."""

    def test_the_manual_entry_with_explicit_lines_still_works(self):
        lines = [
            {
                "account_code": "5100", "debit": "150.00", "tax_base": "150.00",
                "side_party": "كهرباء",
            },
            {"account_code": "1100", "credit": "150.00"},
        ]

        entry = self.add_entry(
            self.mine, lines=lines, kind=BOOK_ENTRY_KIND_MANUAL,
            entry_date=JAN_END,
        )

        self.assertEqual(entry["kind"], BOOK_ENTRY_KIND_MANUAL)
        self.assertEqual(entry["documents"], [])
        self.assertEqual(len(entry["lines"]), 2)
        self.assertEqual(
            Decimal(self.lines_by_code(entry)["5100"]["debit"]), Decimal("150.00"),
        )
        self.assertEqual(money(self.lines_by_code(entry)["5100"], "tax_base"),
                         Decimal("150.00"))
