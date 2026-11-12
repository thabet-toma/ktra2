"""توليدُ بنود الحركة من الورقة — #286/ج.

**ما يثبّته هذا الملفّ:**
- **المبلغُ والضريبةُ والطرفُ من الورقة**: الموظّفُ لا يكتب حساباً ولا رقماً،
  والحركةُ تُولَّد من `amount + tax_amount` وحدهما.
- **التوازنُ رياضيّاً** في المزدوج: مدينُ السطور = دائنُها في كل حالة، وسطرُ
  الضريبة (`2200`) في الطرف المقابل للاتجاه — دائنٌ للبيع والتقرير اليومي،
  مدينٌ للمشتريات والمصروف — **يحمل طرفَه وحده بلا `tax_base` ولا `tax_amount`**.
- **الضريبةُ مرّةً واحدة، وعلى سطر الوعاء**: `tax_base`/`tax_amount` على سطر
  الإيراد (`4100`) أو المشتريات (`5200`) أو المصروف (`5100`)، ومجموعُ `tax_amount`
  على السطور = ضريبةُ الورقة مرّةً واحدة — وهو **الموضعُ الذي يقرؤه**
  `book_reports.vat_from_book` (مبيعاتٌ من سطور الإيراد ومدخلاتٌ من الأصول
  والمصاريف)، وتكرارُها على سطرين يضاعف الإقرار.
- **ونسبةُ الورقة لا تُنسخ إلى السطر**: حقلُ السطر نسبةُ الخصم المعترف بها
  (`book_rates.recognised_vat_rate`) لا وصفَ الفاتورة — نسخُ 17٪ يخصم 17٪ وحدها.
- **الدفترُ البسيط: سطرٌ على حساب طبيعته** — إيرادٌ دائنٌ للبيع والتقرير اليومي،
  ومشترياتٌ/مصروفٌ مدينان بالصافي — لأن `_profit_rows` و`vat_from_book` يقرآن
  منها. **وسطرُ نقدٍ على `1100` بالإجمالي** للتقرير اليومي مديناً وللمصروف
  دائناً: `cash` يقرأ الأصولَ وحدها، فسطرُ الحساب وحده يُخرجه صفراً. والفاتورتان
  بلا سطر نقد (قد لا تكونان مدفوعتين)، وحركةُ البنك وحدها على البنك.
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

from accounting_office import book_reports, client_books, services
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

#: حسابُ الصندوق في شجرة البسيط — سطرُ النقد الذي يقرؤه تقريرُ القبض والدفع.
CASH_CODE = "1100"


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

    def test_a_sales_invoice_puts_the_tax_on_the_revenue_line_not_on_the_vat_line(self):
        """فاتورةُ بيعٍ (100 صافي + 17 ضريبة): الذممُ مدينةٌ بالإجمالي، والوعاءُ
        وضريبتُه على سطر الإيراد — وسطرُ `2200` طرفُه وحده.

        **والموضعُ هو القاعدةُ لا الذوق**: `book_reports.vat_from_book` يجمع
        `tax_amount` من سطور الإيراد (مبيعات) ومن سطور الأصول والمصاريف (مدخلات)،
        فسطرُ ضريبةٍ على `2200` (خصوم) يُتخطّى فيخرج الإقرارُ صفراً.
        """
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
        self.assertEqual(money(lines["4100"], "tax_amount"), Decimal("17.00"))
        self.assertEqual(money(lines["2200"], "credit"), Decimal("17.00"))
        self.assertEqual(money(lines["2200"], "tax_base"), Decimal("0.00"))
        self.assertEqual(money(lines["2200"], "tax_amount"), Decimal("0.00"))
        debit, credit, tax = self.totals(entry)
        self.assertEqual(debit, credit)
        self.assertEqual(debit, Decimal("117.00"))
        self.assertEqual(tax, Decimal("17.00"), "الضريبةُ مرّةً واحدة لا على سطرين")

    def test_an_expense_carries_the_tax_on_the_expense_and_only_the_side_on_vat(self):
        """مصروفٌ (200 + 34): 5100 مدينٌ بصافيه وضريبتِه، و2200 مدينٌ بالضريبة وحدها.

        والبديهيّ «5100 مدينٌ بالإجمالي و2200 مدينٌ بالضريبة» غيرُ متوازن:
        234 + 34 = 268 مقابل 268؟ لا — دائنُ الصندوق 234 وحده. فالتوازنُ يفرض
        أن يحمل سطرُ المصروف صافيه، و`tax_amount` عليه ليكون مدخلاتٍ يقرؤها
        `vat_from_book` من حساب مصروفٍ لا من حساب خصوم.
        """
        row = self.paper(amount="200", tax="34", party="مورّد الكهرباء")

        entry = self.generate([row], kind=BOOK_ENTRY_KIND_EXPENSE)

        lines = self.lines_by_code(entry)
        self.assertEqual(len(entry["lines"]), 3)
        self.assertEqual(money(lines["5100"], "debit"), Decimal("200.00"))
        self.assertEqual(money(lines["5100"], "tax_base"), Decimal("200.00"))
        self.assertEqual(money(lines["5100"], "tax_amount"), Decimal("34.00"))
        self.assertEqual(money(lines["2200"], "debit"), Decimal("34.00"))
        self.assertEqual(money(lines["2200"], "tax_base"), Decimal("0.00"))
        self.assertEqual(money(lines["2200"], "tax_amount"), Decimal("0.00"))
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
    """الدفترُ البسيط: سطرُ حساب طبيعته، ونقدٌ على `1100` لما قُبض أو دُفع."""

    def setUp(self):
        super().setUp()
        self.simple_client = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون الدفتر البسيط", responsible=self.accountant,
        )
        self.create_book(self.simple_client, kind=BOOK_KIND_SIMPLE)

    def test_a_sale_is_one_credit_line_on_revenue_with_the_tax_on_it(self):
        """البيعُ دائنٌ على `4100` لا على الصندوق: `_profit_rows` يقرأ الإيرادَ
        منها، وسطرُ الصندوق يمحوه ويقلب ذمّةَ الزبون في `_receivables`."""
        row = self.paper(
            amount="100", tax="17", party="زبون نقدي", client=self.simple_client,
        )

        entry = self.generate(
            [row], kind=BOOK_ENTRY_KIND_SALES_INVOICE, client=self.simple_client,
        )

        self.assertEqual(len(entry["lines"]), 1)
        line = entry["lines"][0]
        self.assertEqual(line["account_code"], "4100")
        self.assertEqual(money(line, "credit"), Decimal("100.00"))
        self.assertEqual(money(line, "debit"), Decimal("0.00"))
        self.assertEqual(money(line, "tax_base"), Decimal("100.00"))
        self.assertEqual(money(line, "tax_amount"), Decimal("17.00"))
        # ولا طرفَ على سطر البسيط: لا حسابَ ذمّي في شجرته، والبيعُ نقداً لا دَين.
        self.assertEqual(line["side_party"], "")

    def test_an_expense_is_a_debit_on_the_expense_plus_a_cash_credit(self):
        """المصروفُ مدينٌ على `5100` بالصافي وضريبته، ونقدُه دائنٌ على `1100`
        بالإجمالي — `cash` يقرأ الأصولَ وحدها فلا يرى صرفاً بلا سطر صندوق."""
        row = self.paper(amount="200", tax="34", client=self.simple_client)

        entry = self.generate(
            [row], kind=BOOK_ENTRY_KIND_EXPENSE, client=self.simple_client,
        )

        self.assertEqual(len(entry["lines"]), 2)
        lines = self.lines_by_code(entry)
        self.assertEqual(money(lines["5100"], "debit"), Decimal("200.00"))
        self.assertEqual(money(lines["5100"], "credit"), Decimal("0.00"))
        self.assertEqual(money(lines["5100"], "tax_base"), Decimal("200.00"))
        self.assertEqual(money(lines["5100"], "tax_amount"), Decimal("34.00"))
        # الضريبةُ على سطر المصروف وحده: سطرُ النقد بالإجمالي وبلا ضريبةٍ ولا طرف.
        self.assertEqual(money(lines[CASH_CODE], "debit"), Decimal("0.00"))
        self.assertEqual(money(lines[CASH_CODE], "credit"), Decimal("234.00"))
        self.assertEqual(money(lines[CASH_CODE], "tax_base"), Decimal("0.00"))
        self.assertEqual(money(lines[CASH_CODE], "tax_amount"), Decimal("0.00"))
        self.assertEqual(lines[CASH_CODE]["side_party"], "")

    def test_a_bank_movement_stays_one_line_on_the_bank_without_tax(self):
        """حركةُ البنك وحدها على البنك: لا إيرادَ ولا مصروفَ فيها، والضريبةُ عليها
        مرفوضةٌ أصلاً — فلا أساسَ خاضعٌ يُدخلها تقريرَ ض.ق.م بلا ضريبة."""
        row = self.paper(
            amount="500", party="تحويل داخلي", client=self.simple_client,
        )

        entry = self.generate(
            [row], kind=BOOK_ENTRY_KIND_BANK_MOVEMENT, client=self.simple_client,
        )

        self.assertEqual(len(entry["lines"]), 1)
        line = entry["lines"][0]
        self.assertEqual(line["account_code"], "1200")
        self.assertEqual(money(line, "debit"), Decimal("500.00"))
        self.assertEqual(money(line, "tax_base"), Decimal("0.00"))
        self.assertEqual(money(line, "tax_amount"), Decimal("0.00"))


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
        # الضريبةُ على سطور الوعاء (الإيراد) لا على سطر `2200`.
        self.assertEqual(taxes["4100"], Decimal("51.00"))
        self.assertEqual(taxes["2200"], Decimal("0.00"))
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


class GeneratedEntryReportsTest(BookEntryGenerationTestCase):
    """الحركةُ المولَّدة تصل تقاريرَ #287/#288: `_cash` و`vat_from_book` و`_profit_rows` و`_receivables`.

    **الموضعُ لا المبلغ**: `vat_from_book` يقرأ `tax_amount` من **سطور الإيراد**
    (مبيعات) ومن **سطور الأصول والمصاريف** (مدخلات)، و`_profit_rows` يقرأ الإيرادَ
    والمصروف من حسابيهما. فسطرُ ضريبةٍ على `2200` (خصوم) أو على الصندوق يُخرج
    الإقرارَ صفراً أو سالباً — والموظّفُ يؤكّد ذلك الرقمَ التزاماً على الزبون.
    **و`_cash` يقرأ الأصولَ وحدها**: حركةٌ قبضت أو دفعت بلا سطرِ `1100` تُقرأ صفراً
    في تقرير القبض والدفع، وسطرُ النقد يُكتب بالإجمالي (`amount + tax`) بلا ضريبة.
    """

    SPAN_START = datetime.date(THIS_YEAR, 1, 1)
    SPAN_END = datetime.date(THIS_YEAR, 12, 31)

    def setUp(self):
        super().setUp()
        self.simple_client = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونُ تقارير التوليد", responsible=self.accountant,
        )
        self.create_book(self.simple_client, kind=BOOK_KIND_SIMPLE)

    def vat(self, client):
        return book_reports.vat_from_book(
            client.book,
            period_start=self.SPAN_START, period_end=self.SPAN_END,
        )

    def report(self, client, kind):
        res = self.client.get(
            f"{BOOKS}{client.pk}/reports/{kind}/",
            {"from": self.SPAN_START.isoformat(), "to": self.SPAN_END.isoformat()},
            **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def simple_sale(self, *, party="زبون نقدي"):
        paper = self.paper(
            amount="100", tax="17", party=party, client=self.simple_client,
        )
        return self.generate(
            [paper], kind=BOOK_ENTRY_KIND_SALES_INVOICE, client=self.simple_client,
        )

    def simple_expense(self, *, amount="200", tax="34"):
        paper = self.paper(
            amount=amount, tax=tax, code="income_tax", client=self.simple_client,
        )
        return self.generate(
            [paper], kind=BOOK_ENTRY_KIND_EXPENSE, client=self.simple_client,
        )

    def simple_daily_report(self, *, amount="100", tax="17"):
        paper = self.paper(amount=amount, tax=tax, client=self.simple_client)
        return self.generate(
            [paper], kind=BOOK_ENTRY_KIND_DAILY_REPORT, client=self.simple_client,
        )

    # ── المزدوج ──────────────────────────────────────────────────────────
    def test_a_double_sale_reads_as_sales_tax_in_the_vat_report(self):
        self.generate(
            [self.paper(amount="100", tax="17", party="شركة الأمل")],
            kind=BOOK_ENTRY_KIND_SALES_INVOICE,
        )

        payload = self.vat(self.mine)

        self.assertEqual(payload["sales_tax"], "17.00")
        self.assertEqual(payload["input_tax"], "0.00")
        self.assertEqual(payload["vat_due"], "17.00")

    def test_a_double_sale_and_purchase_of_one_hundred_net_out_to_zero(self):
        self.generate(
            [self.paper(amount="100", tax="17", party="شركة الأمل")],
            kind=BOOK_ENTRY_KIND_SALES_INVOICE,
        )
        self.generate(
            [self.paper(
                amount="100", tax="17", party="مورد الأثاث", code="income_tax",
            )],
            kind=BOOK_ENTRY_KIND_PURCHASE_INVOICE,
        )

        payload = self.vat(self.mine)

        self.assertEqual(payload["sales_tax"], "17.00")
        self.assertEqual(payload["input_tax"], "17.00")
        self.assertEqual(payload["vat_due"], "0.00")

    def test_the_paper_rate_is_not_the_recognised_rate(self):
        """نسبةُ الفاتورة (17٪) وصفٌ لا خصم: 34 تُخصم كاملةً بنسبة الحساب (100%)."""
        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, True)
        self.generate(
            [self.paper(amount="200", tax="34", rate="17", party="مورد الكهرباء")],
            kind=BOOK_ENTRY_KIND_EXPENSE,
        )

        payload = self.vat(self.mine)

        self.assertEqual(payload["input_tax"], "34.00")
        self.assertEqual(payload["recognised_input"], "34.00")
        self.assertEqual(payload["non_deductible"], "0.00")

    # ── البسيط ───────────────────────────────────────────────────────────
    def test_a_simple_sale_reads_as_sales_tax_in_the_vat_report(self):
        self.simple_sale()

        payload = self.vat(self.simple_client)

        self.assertEqual(payload["sales_tax"], "17.00")
        self.assertEqual(payload["input_tax"], "0.00")
        self.assertEqual(payload["vat_due"], "17.00")

    def test_a_simple_sale_reads_as_revenue_in_the_income_report(self):
        self.simple_sale()

        payload = self.report(self.simple_client, "income")

        self.assertEqual(payload["totals"]["revenue"], "100.00")
        self.assertEqual(payload["totals"]["expense"], "0.00")
        self.assertEqual(payload["totals"]["profit"], "100.00")

    def test_a_simple_purchase_reads_as_input_tax_and_as_an_expense(self):
        self.generate(
            [self.paper(amount="200", tax="34", client=self.simple_client)],
            kind=BOOK_ENTRY_KIND_PURCHASE_INVOICE, client=self.simple_client,
        )

        payload = self.vat(self.simple_client)

        self.assertEqual(payload["sales_tax"], "0.00")
        self.assertEqual(payload["input_tax"], "34.00")
        self.assertEqual(payload["recognised_input"], "34.00")
        self.assertEqual(
            self.report(self.simple_client, "income")["totals"]["expense"], "200.00",
        )

    def test_a_simple_cash_sale_leaves_the_customer_no_debt(self):
        """البسيطُ لا حسابَ ذمّي فيه: بيعٌ نقديٌّ لا يُنشئ ذمّةً على الزبون."""
        self.simple_sale()

        payload = self.report(self.simple_client, "receivables")

        self.assertNotIn(
            "زبون نقدي", {row["side_party"] for row in payload["rows"]},
        )
        self.assertEqual(payload["totals"]["debit_total"], "0.00")
        self.assertEqual(payload["totals"]["credit_total"], "0.00")

    def test_a_simple_daily_report_reads_as_cash_and_still_as_revenue_and_vat(self):
        """التقريرُ اليوميُّ قبضٌ نقديّ: سطرُ `1100` مدينٌ بالإجمالي (117).

        سطرُ الإيراد وحده كان يُخرج `cash` صفراً (يقرأ الأصولَ وحدها)، والضريبةُ
        تبقى على سطر الإيراد وحده فيقرؤها `vat_from_book` مرّةً واحدة، ولا طرفَ
        على سطر النقد فلا ذمّةَ في `_receivables`.
        """
        entry = self.simple_daily_report()

        cash = self.lines_by_code(entry)[CASH_CODE]
        self.assertEqual(money(cash, "debit"), Decimal("117.00"))
        self.assertEqual(money(cash, "credit"), Decimal("0.00"))
        self.assertEqual(money(cash, "tax_base"), Decimal("0.00"))
        self.assertEqual(money(cash, "tax_amount"), Decimal("0.00"))
        self.assertEqual(cash["side_party"], "")

        payload = self.report(self.simple_client, "cash")
        rows = {row["kind"]: row for row in payload["rows"]}
        self.assertEqual(rows[BOOK_ENTRY_KIND_DAILY_REPORT]["count"], 1)
        self.assertEqual(rows[BOOK_ENTRY_KIND_DAILY_REPORT]["debit"], "117.00")
        self.assertEqual(rows[BOOK_ENTRY_KIND_DAILY_REPORT]["net"], "117.00")
        self.assertEqual(payload["totals"]["net"], "117.00")
        self.assertEqual(payload["totals"]["closing_balance"], "117.00")

        income = self.report(self.simple_client, "income")
        self.assertEqual(income["totals"]["revenue"], "100.00")
        self.assertEqual(income["totals"]["expense"], "0.00")
        vat = self.vat(self.simple_client)
        self.assertEqual(vat["sales_tax"], "17.00")
        self.assertEqual(vat["input_tax"], "0.00")
        self.assertEqual(self.report(self.simple_client, "receivables")["rows"], [])

    def test_a_simple_expense_reads_as_cash_out_and_still_as_expense_and_vat(self):
        """المصروفُ دفعٌ نقديّ: سطرُ `1100` دائنٌ بالإجمالي (234)، والمصروفُ 200
        في الأرباح والخسائر، وضريبتُه 34 مدخلات."""
        entry = self.simple_expense()

        cash = self.lines_by_code(entry)[CASH_CODE]
        self.assertEqual(money(cash, "debit"), Decimal("0.00"))
        self.assertEqual(money(cash, "credit"), Decimal("234.00"))
        self.assertEqual(money(cash, "tax_base"), Decimal("0.00"))
        self.assertEqual(money(cash, "tax_amount"), Decimal("0.00"))
        self.assertEqual(cash["side_party"], "")

        payload = self.report(self.simple_client, "cash")
        rows = {row["kind"]: row for row in payload["rows"]}
        self.assertEqual(rows[BOOK_ENTRY_KIND_EXPENSE]["count"], 1)
        self.assertEqual(rows[BOOK_ENTRY_KIND_EXPENSE]["credit"], "234.00")
        self.assertEqual(rows[BOOK_ENTRY_KIND_EXPENSE]["net"], "-234.00")
        self.assertEqual(payload["totals"]["net"], "-234.00")
        self.assertEqual(payload["totals"]["closing_balance"], "-234.00")

        income = self.report(self.simple_client, "income")
        self.assertEqual(income["totals"]["expense"], "200.00")
        vat = self.vat(self.simple_client)
        self.assertEqual(vat["sales_tax"], "0.00")
        self.assertEqual(vat["input_tax"], "34.00")
        self.assertEqual(self.report(self.simple_client, "receivables")["rows"], [])

    def test_a_simple_credit_sale_writes_no_cash_line(self):
        """الفاتورةُ قد لا تكون مدفوعة: لا سطرَ `1100` ولا قبضَ في `cash`.

        سطرُ صندوقٍ على فاتورةٍ آجلة يُقبض بيعاً لم يُدفع، وسطرُ الإيراد وحده هو
        الصحيح: النقدُ حركةٌ مستقلّةٌ حين يُدفع.
        """
        entry = self.simple_sale()

        self.assertEqual(len(entry["lines"]), 1)
        self.assertNotIn(CASH_CODE, self.lines_by_code(entry))
        self.assertEqual(money(entry["lines"][0], "credit"), Decimal("100.00"))
        self.assertEqual(money(entry["lines"][0], "tax_amount"), Decimal("17.00"))

        payload = self.report(self.simple_client, "cash")
        self.assertEqual(payload["totals"]["debit"], "0.00")
        self.assertEqual(payload["totals"]["credit"], "0.00")
        self.assertEqual(payload["totals"]["net"], "0.00")
        self.assertEqual(payload["totals"]["closing_balance"], "0.00")
        self.assertEqual({row["count"] for row in payload["rows"]}, {0})

    def test_the_cash_report_reads_exactly_the_cash_lines_of_each_entry(self):
        """**سطرُ النقد هو ما يقرؤه التقرير**: مجموعُ `1100` في الحركة الواحدة =
        قبضُها/دفعُها في `cash`، والختامُ صافيَ الحركتين مجتمعين — أرضيةٌ ثابتةٌ
        لا `opening + net`، فتلك معادلةٌ تحسبها `_cash` نفسُها فلا تسقط أبداً."""
        daily = self.simple_daily_report()
        expense = self.simple_expense()

        payload = self.report(self.simple_client, "cash")
        rows = {row["kind"]: row for row in payload["rows"]}
        self.assertEqual(
            self.sums_by_code(daily, "debit")[CASH_CODE],
            money(rows[BOOK_ENTRY_KIND_DAILY_REPORT], "debit"),
        )
        self.assertEqual(
            self.sums_by_code(expense, "credit")[CASH_CODE],
            money(rows[BOOK_ENTRY_KIND_EXPENSE], "credit"),
        )
        # قيمٌ حرفيّة: 117 قبضاً و234 دفعاً ⇒ صافٍ −117 وختامٌ −117 على أرضيةٍ صفر.
        self.assertEqual(payload["totals"]["opening_balance"], "0.00")
        self.assertEqual(payload["totals"]["net"], "-117.00")
        self.assertEqual(payload["totals"]["closing_balance"], "-117.00")

    def test_a_simple_entry_with_tax_is_short_by_the_tax_on_purpose(self):
        """**القيدُ البسيط بضريبةٍ ناقصُ طرفِه المقابل بمقدار الضريبة — عن قصد.**

        الضريبةُ في البسيط بياناتٌ على سطر الطبيعة (`tax_base`/`tax_amount`) لا
        سطرُ `2200`، وشجرةُ البسيط بلا `2200` أصلاً. فللتقرير اليومي مدينُه 117
        (سطرُ `1100`) ودائنُه 100 (سطرُ الإيراد)، وللمصروف مدينُه 200 ودائنُه
        234: والفرقُ في الحالين هو الضريبةُ نفسُها (17 و34) لا خطأُ جمع.

        **ولا يُصلَح هذا بسطر ضريبةٍ أو بموازنة القيد البسيط**: سجلُّ البسيط
        أحاديٌّ لا مزدوج، و`_assert_balanced` لا تسأله عن التوازن أصلاً، وسطرُ
        `2200` هنا يُخرج `_profit_rows` و`vat_from_book` عن موضعهما. القصدُ
        مثبَّتٌ هنا حتى لا «يُصلحه» أحدٌ لاحقاً.
        """
        daily = self.simple_daily_report()
        expense = self.simple_expense()

        self.assertEqual(daily["total_debit"], "117.00")
        self.assertEqual(daily["total_credit"], "100.00")
        self.assertEqual(expense["total_debit"], "200.00")
        self.assertEqual(expense["total_credit"], "234.00")

    def test_a_simple_daily_report_without_tax_reads_one_hundred_each_way(self):
        """التقريرُ اليوميُّ بلا ضريبة (100 و0): سطرُ `1100` مدينٌ 100 والإيرادُ
        100، وصافي `cash` 100 وختامُه 100 — ولا ضريبةَ تُخرج الطرفين."""
        entry = self.simple_daily_report(amount="100", tax="0")

        cash = self.lines_by_code(entry)[CASH_CODE]
        self.assertEqual(money(cash, "debit"), Decimal("100.00"))

        income = self.report(self.simple_client, "income")
        self.assertEqual(income["totals"]["revenue"], "100.00")

        payload = self.report(self.simple_client, "cash")
        self.assertEqual(payload["totals"]["net"], "100.00")
        self.assertEqual(payload["totals"]["closing_balance"], "100.00")

        vat = self.vat(self.simple_client)
        self.assertEqual(vat["sales_tax"], "0.00")

    def test_a_simple_expense_without_tax_reads_two_hundred_out(self):
        """المصروفُ بلا ضريبة (200 و0): سطرُ `1100` دائنٌ 200 والمصروفُ 200 في
        الأرباح والخسائر، وصافي `cash` −200 — دفعٌ كاملٌ بلا ضريبةٍ تُخرجه."""
        entry = self.simple_expense(amount="200", tax="0")

        cash = self.lines_by_code(entry)[CASH_CODE]
        self.assertEqual(money(cash, "credit"), Decimal("200.00"))

        income = self.report(self.simple_client, "income")
        self.assertEqual(income["totals"]["expense"], "200.00")

        payload = self.report(self.simple_client, "cash")
        self.assertEqual(payload["totals"]["net"], "-200.00")


class PaperRateIsDisplayOnlyTest(BookEntryGenerationTestCase):
    """نسبةُ الورقة **وصفٌ للعرض لا نسبةُ السطر**: لا تُنسخ ولو فُعّل الإعداد."""

    def test_the_paper_rate_is_never_written_on_a_line(self):
        """حقلُ السطر نسبةُ الخصم المعترف بها (`recognised_vat_rate`) لا نسبةُ
        الفاتورة: نسخُ 17٪ يخصم 17٪ من ضريبة المدخلات وحدها — إقرارٌ ناقص."""
        off = self.paper(amount="100", tax="17", rate="17", month=1)

        without_setting = self.generate([off])

        services.set_office_setting(self.tenant, client_books.LINE_RATE_KEY, True)
        on = self.paper(amount="100", tax="17", rate="17", month=2, code="income_tax")

        with_setting = self.generate([on])

        for entry in (without_setting, with_setting):
            for line in entry["lines"]:
                self.assertIsNone(line["vat_rate"])
                self.assertEqual(line["vat_rate_reason"], "")


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
