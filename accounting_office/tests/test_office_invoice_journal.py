"""قيدُ الفاتورة الورقية وقيدُ الإشعار الدائن في دفاتر المكتب (#284، الجزء ب).

**القواعدُ التي يسقط عندها الاختبار:**
1. اعتمادُ مسودّةٍ يُرحّل قيداً **متوازناً**: مدينٌ الذمّمُ المدينة (`1103`) بإجمالي
   الفاتورة ووسمِ الطرف على سطرها وحده، دائنٌ الإيراد (`4102`) بالصافي، دائنٌ
   ض.ق.م المخرجات (`2104`) بالضريبة — ثلاثةُ أسطر لمكتبٍ مشتغلٍ مرخّص.
2. مكتبٌ غيرُ مرخّص ⇒ **سطران**: لا ضريبةَ على الورقة ولا في القيد.
3. `office_journal_enabled` مطفأ ⇒ **لا قيدَ ولا خطأ**: الفاتورةُ تُصدَر عاديًّا.
4. النداءُ الثاني لا يُكرّر القيد (`idempotent` على `(النوع، المعرّف)`).
5. فترةٌ مقفلة ⇒ **400** و**لا فاتورةَ ولا رقمَ مستهلكاً** — الذرّية: القيدُ داخل
   معاملة الإصدار، وفشلُه يُرجع الاعتمادَ كلَّه.
6. الإشعارُ الدائن **عكسُ** قيد الفاتورة: مدينٌ الإيرادُ والضريبة، دائنٌ الذمّمُ
   المدينة بوسم الطرف — والمرجعُ `office_fee_credit_note`.
7. **المطابقةُ الصريحة**: رصيدُ ذمّة الطرف في `accounting` (مدين − دائن) يساوي
   `payments.client_due` عند اليوم حين يكون الترحيلُ مفعّلاً.
8. حسابُ الضريبة غائبٌ أو معطَّل ⇒ 400 يُسمّي الكود «2104» ولا صفَّ فاتورة.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting import services as accounting_services
from accounting.models import Account, FiscalPeriod, JournalHeader
from accounting_office import fee_invoices, fees, office_journal, payments, services
from accounting_office.models import (
    FeeDraft,
    FeeInvoice,
    FeeInvoiceSequence,
    FeePayment,
    OfficeClient,
    TaxCard,
)
from core.modules import invalidate_module_cache
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

BASE = "/api/accounting-office/"
DRAFTS = f"{BASE}fees/drafts/"
INVOICES = f"{BASE}fees/invoices/"
PAYMENTS = f"{BASE}fees/payments/"

#: الإجماليُّ قبل الضريبة في المسودّة، والنسبةُ الافتراضية للشركة 16٪ ⇒ 160.
NET = Decimal("1000.00")
TAX = Decimal("160.00")
GROSS = Decimal("1160.00")


def decimal_of(value) -> Decimal:
    return Decimal(str(value))


class InvoiceJournalTestCase(APITestCase):
    """مكتبٌ بقالب `accounting_office`، بزبونٍ ومسودّةٍ معتمدةٍ وبلا فاتورةِ قيد."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.owner = User.objects.create_user(username="invoice_journal_owner", password="x")
        cls.tenant = create_company(
            "مكتب قيود الفواتير", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")
        cls.receivable = Account.objects.get(tenant=cls.tenant, code="1103")
        cls.revenue = Account.objects.get(tenant=cls.tenant, code="4102")
        cls.tax_output = Account.objects.get(tenant=cls.tenant, code="2104")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def make_client(self, name="زبون الفواتير"):
        client = OfficeClient.objects.create(tenant=self.tenant, name=name)
        TaxCard.objects.create(client=client)
        return client

    def make_draft(self, client, *, total=NET, year=2026, month=3):
        """مسودّةٌ **منتظرة** — الإصدارُ يقع بالاعتماد وحده، كالمسار الحقيقي."""
        return FeeDraft.objects.create(
            tenant=self.tenant,
            client=client,
            year=year,
            month=month,
            subtotal=Decimal(str(total)),
            total=Decimal(str(total)),
            status=FeeDraft.STATUS_DRAFT,
        )

    def approve(self, draft):
        """اعتمادٌ برمجيٌّ يُصدر الورقة وقيدَها في المعاملة نفسها."""
        return fees.approve_fee_draft(draft, actor=self.owner)

    def live_invoice_of(self, draft) -> FeeInvoice:
        return FeeInvoice.objects.get(
            tenant=self.tenant, source_draft=draft, cancelled_at__isnull=True,
        )

    def journal_of(self, *, reference_type, reference_id):
        return JournalHeader.objects.get(
            tenant=self.tenant,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    def lines_of(self, journal):
        """أسطرُ القيد مفهرسةً بمعرّف الحساب — والوسمُ في كائن السطر."""
        return {line.account_id: line for line in journal.lines.all()}


class InvoiceJournalTest(InvoiceJournalTestCase):
    def test_approval_posts_a_balanced_journal_that_mirrors_the_sheet(self):
        client = self.make_client()
        draft = self.make_draft(client)

        self.approve(draft)
        invoice = self.live_invoice_of(draft)

        # الورقةُ صادرةٌ بضريبتها والعقدُ الماليُّ سليم قبل القيد.
        self.assertEqual(decimal_of(invoice.total), GROSS)
        self.assertEqual(decimal_of(invoice.tax_total), TAX)

        journal = self.journal_of(
            reference_type="office_fee_invoice", reference_id=invoice.pk,
        )
        self.assertTrue(journal.is_posted)
        self.assertEqual(journal.created_by_id, self.owner.pk)
        self.assertEqual(
            journal.transaction_date, timezone.localdate(invoice.issued_at),
        )
        self.assertIn(invoice.number, journal.description)
        self.assertIn(client.name, journal.description)

        lines = self.lines_of(journal)
        self.assertEqual(len(lines), 3, "قيدُ فاتورةٍ مرخّصةٍ ثلاثةُ أسطر: ذمّة وإيراد وضريبة")
        receivable = lines[self.receivable.pk]
        revenue = lines[self.revenue.pk]
        tax = lines[self.tax_output.pk]
        self.assertEqual(decimal_of(receivable.debit), GROSS)
        self.assertEqual(decimal_of(receivable.credit), Decimal("0.00"))
        self.assertEqual(decimal_of(revenue.debit), Decimal("0.00"))
        self.assertEqual(decimal_of(revenue.credit), NET)
        self.assertEqual(decimal_of(tax.debit), Decimal("0.00"))
        self.assertEqual(decimal_of(tax.credit), TAX)

        # وسمُ الطرف على سطر الذمّم وحده (`post_journal` نفسه يرفض وسمَ غيره).
        partner = Partner.objects.get(tenant=self.tenant, pk=receivable.partner_id)
        self.assertEqual(partner.name, client.name)
        self.assertIsNone(revenue.partner_id)
        self.assertIsNone(tax.partner_id)

        totals = journal.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        self.assertEqual(totals["debit"], totals["credit"], "قيدٌ غير متوازن")
        self.assertEqual(decimal_of(totals["debit"]), decimal_of(invoice.total))
        self.assertEqual(decimal_of(totals["credit"]), decimal_of(invoice.total))

    def test_an_unlicensed_office_posts_two_lines_and_no_tax(self):
        services.set_office_setting(self.tenant, "office_licensed_dealer", False)
        client = self.make_client("زبون مكتبٍ غير مرخّص")
        draft = self.make_draft(client)

        self.approve(draft)
        invoice = self.live_invoice_of(draft)

        self.assertEqual(decimal_of(invoice.tax_total), Decimal("0.00"))
        journal = self.journal_of(
            reference_type="office_fee_invoice", reference_id=invoice.pk,
        )
        lines = self.lines_of(journal)
        self.assertEqual(len(lines), 2, "مكتبٌ غيرُ مرخّص: ذمّةٌ وإيرادٌ بلا سطر ضريبة")
        self.assertNotIn(self.tax_output.pk, lines)
        self.assertEqual(decimal_of(lines[self.receivable.pk].debit), NET)
        self.assertEqual(decimal_of(lines[self.revenue.pk].credit), NET)

    def test_disabling_the_journal_issues_the_invoice_without_a_journal(self):
        services.set_office_setting(self.tenant, "office_journal_enabled", False)
        client = self.make_client()
        draft = self.make_draft(client)

        self.approve(draft)

        self.assertTrue(
            FeeInvoice.objects.filter(tenant=self.tenant, source_draft=draft).exists(),
        )
        self.assertFalse(JournalHeader.objects.filter(tenant=self.tenant).exists())

    def test_posting_the_same_invoice_again_returns_the_same_journal(self):
        client = self.make_client()
        draft = self.make_draft(client)
        self.approve(draft)
        invoice = self.live_invoice_of(draft)
        first = self.journal_of(
            reference_type="office_fee_invoice", reference_id=invoice.pk,
        )

        again = office_journal.post_invoice_journal(invoice, actor=self.owner)

        self.assertEqual(again.pk, first.pk)
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant=self.tenant,
                reference_type="office_fee_invoice",
                reference_id=invoice.pk,
            ).count(),
            1,
        )

    def test_a_disabled_tax_account_is_a_400_naming_the_code_and_rolls_back(self):
        """الحسابُ الضريبيُّ لا إعدادَ له: كودُه ثابتُ `accounting.services`،
        ومعطَّلُه يردّ 400 يسمّيه ويُسقط الإصدارَ كلَّه."""
        self.assertEqual(office_journal.TAX_OUTPUT_ACCOUNT_CODE, "2104")
        Account.objects.filter(tenant=self.tenant, code="2104").update(is_active=False)
        client = self.make_client()
        self.make_draft(client)
        draft = FeeDraft.objects.get(client=client)

        res = self.client.post(f"{DRAFTS}{draft.pk}/approve/", {}, format="json", **self.headers())

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("2104", str(res.data))
        self.assertFalse(FeeInvoice.objects.filter(tenant=self.tenant).exists())
        draft.refresh_from_db()
        self.assertEqual(draft.status, FeeDraft.STATUS_DRAFT)


class ZeroInvoiceTest(InvoiceJournalTestCase):
    def test_a_zero_total_invoice_is_issued_without_a_journal(self):
        """إجماليُ صفرٍ لا يُقيَّد: `post_journal` يرفض قيداً صفريّاً، والورقةُ
        الصفريّةُ لا أثرَ لها في الدفاتر — فلا تُسقِط الإصدارَ برسالةٍ إنجليزية."""
        client = self.make_client("زبونٌ بإجمالي صفر")
        draft = self.make_draft(client, total="0")

        self.approve(draft)

        invoice = self.live_invoice_of(draft)
        self.assertEqual(decimal_of(invoice.total), Decimal("0.00"))
        self.assertFalse(JournalHeader.objects.filter(tenant=self.tenant).exists())


class BatchApprovalJournalTest(InvoiceJournalTestCase):
    """**«اعتمد الكل» يُرحّل قيدَ كلّ فاتورةٍ صادرة** — المسارُ الجماعيُّ لا يترك
    صفَّ مالٍ بلا قيد.

    كان القيدُ في المسار المفرد وحده، ففواتيرُ «اعتمد الكل» تخرج بلا قيودها
    وتُدائن ذمّةُ الطرف بدفعاتٍ عليها بلا إدانتِها — دفاترُ غيرُ متوازنةٍ بزرٍّ
    واحد. والقيدُ اليوم لكل صفٍّ **داخل المعاملة نفسها**: إمّا تصدر الفواتيرُ
    بقيودها كلّها أو لا تصدر واحدة.
    """

    def approve_all(self):
        res = self.client.post(
            f"{DRAFTS}approve-all/", {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res

    def test_every_invoice_of_the_batch_gets_its_balanced_journal(self):
        first = self.make_client("زبون أول")
        second = self.make_client("زبون ثانٍ")
        self.make_draft(first)
        self.make_draft(second, month=4)

        res = self.approve_all()

        self.assertEqual(res.data["approved"], 2)
        invoices = list(
            FeeInvoice.objects.filter(tenant=self.tenant).order_by("id"),
        )
        self.assertEqual(len(invoices), 2, "«اعتمد الكل» لم يُصدر ورقتين")
        journals = JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="office_fee_invoice",
        )
        self.assertEqual(journals.count(), 2, "فاتورةٌ جماعيّةٌ بلا قيدها")
        for invoice in invoices:
            journal = journals.get(reference_id=invoice.pk)
            self.assertTrue(journal.is_posted)
            totals = journal.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
            self.assertEqual(
                totals["debit"], totals["credit"],
                f"قيدُ الفاتورة {invoice.number} غيرُ متوازن",
            )
            self.assertEqual(
                decimal_of(totals["debit"]), decimal_of(invoice.total),
            )
            # وسمُ الطرف على سطر الذمّم وحده في القيد الجماعيّ أيضاً.
            tagged = list(journal.lines.filter(partner__isnull=False))
            self.assertEqual(len(tagged), 1)
            self.assertEqual(tagged[0].account_id, self.receivable.pk)

    def test_the_receivable_reconciles_after_a_batch_approval_too(self):
        """**المطابقةُ بعد «اعتمد الكل»** — لا بعد الاعتماد المفرد وحده.

        (مكتبٌ غيرُ مشتغلٍ مرخّص: بلا ضريبة، للسبب المكتوب في
        `ReceivableReconciliationTest` — `client_due` لا يرى الضريبة.)
        """
        services.set_office_setting(self.tenant, "office_licensed_dealer", False)
        first = self.make_client("زبونٌ جماعيٌّ أول")
        second = self.make_client("زبونٌ جماعيٌّ ثانٍ")
        self.make_draft(first)
        self.make_draft(second, month=4)

        self.approve_all()
        paid = self.client.post(
            PAYMENTS,
            {
                "client": second.pk,
                "amount": "400.00",
                "method": "cash",
                "paid_at": "2026-03-20",
            },
            format="json",
            **self.headers(),
        )
        self.assertEqual(paid.status_code, 201, paid.content)

        for client, expected in ((first, NET), (second, NET - Decimal("400.00"))):
            with self.subTest(client=client.name):
                partner_id = OfficeClient.objects.get(pk=client.pk).partner_id
                self.assertIsNotNone(partner_id)
                debit, credit = accounting_services.partner_posted_balance(
                    self.tenant.pk, partner_id,
                )
                ledger_balance = decimal_of(debit) - decimal_of(credit)
                self.assertEqual(ledger_balance, expected)
                self.assertEqual(
                    payments.client_due(self.tenant, client).due, ledger_balance,
                )

    def test_disabling_the_journal_leaves_the_batch_without_journals(self):
        services.set_office_setting(self.tenant, "office_journal_enabled", False)
        self.make_draft(self.make_client("زبون أول"))
        self.make_draft(self.make_client("زبون ثانٍ"), month=4)

        res = self.approve_all()

        self.assertEqual(res.data["approved"], 2)
        self.assertEqual(FeeInvoice.objects.filter(tenant=self.tenant).count(), 2)
        self.assertFalse(JournalHeader.objects.filter(tenant=self.tenant).exists())

    def test_a_closed_period_rolls_back_the_whole_batch(self):
        """الذرّيةُ الجماعيّة: فشلُ قيدٍ واحدٍ لا يترك فواتيرَ ناقصةَ القيود."""
        day = timezone.localdate()
        closed = FiscalPeriod.objects.filter(
            tenant=self.tenant, start_date__lte=day, end_date__gte=day,
        ).update(status="Closed", is_closed=True)
        self.assertEqual(closed, 1, "لا فترةَ مالية تغطي اليوم")
        self.make_draft(self.make_client("زبون أول"))
        self.make_draft(self.make_client("زبون ثانٍ"), month=4)

        res = self.client.post(
            f"{DRAFTS}approve-all/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(FeeInvoice.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(JournalHeader.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(
            FeeDraft.objects.filter(
                tenant=self.tenant, status=FeeDraft.STATUS_APPROVED,
            ).exists(),
            "بقيت مسودّةٌ معتمدةٌ بلا ورقةٍ ولا قيد",
        )


class CreditNoteJournalTest(InvoiceJournalTestCase):
    def test_a_credit_note_reverses_the_invoice_journal(self):
        client = self.make_client()
        draft = self.make_draft(client)
        self.approve(draft)
        invoice = self.live_invoice_of(draft)

        note = fee_invoices.issue_credit_note(
            invoice, actor=self.owner, amount="580.00", reason="خصمُ خدمةٍ لم تُنفَّذ",
        )

        journal = self.journal_of(
            reference_type="office_fee_credit_note", reference_id=note.pk,
        )
        self.assertTrue(journal.is_posted)
        self.assertEqual(
            journal.transaction_date, timezone.localdate(note.issued_at),
        )
        self.assertIn(note.number, journal.description)
        lines = self.lines_of(journal)
        self.assertEqual(len(lines), 3, "إشعارٌ دائنٌ مرخّص: إيرادٌ وضريبةٌ وذمّة")
        self.assertEqual(decimal_of(lines[self.revenue.pk].debit), Decimal("500.00"))
        self.assertEqual(decimal_of(lines[self.tax_output.pk].debit), Decimal("80.00"))
        receivable = lines[self.receivable.pk]
        self.assertEqual(decimal_of(receivable.credit), decimal_of(note.total))
        self.assertEqual(
            receivable.partner_id,
            OfficeClient.objects.get(pk=client.pk).partner_id,
        )
        self.assertIsNone(lines[self.revenue.pk].partner_id)
        totals = journal.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        self.assertEqual(totals["debit"], totals["credit"])
        self.assertEqual(decimal_of(totals["debit"]), decimal_of(note.total))

    def test_a_credit_note_on_an_unlicensed_invoice_posts_two_lines(self):
        services.set_office_setting(self.tenant, "office_licensed_dealer", False)
        client = self.make_client()
        draft = self.make_draft(client)
        self.approve(draft)
        invoice = self.live_invoice_of(draft)

        note = fee_invoices.issue_credit_note(
            invoice, actor=self.owner, amount="200.00", reason="تصحيح",
        )

        lines = self.lines_of(self.journal_of(
            reference_type="office_fee_credit_note", reference_id=note.pk,
        ))
        self.assertEqual(len(lines), 2)
        self.assertEqual(decimal_of(lines[self.revenue.pk].debit), Decimal("200.00"))
        self.assertEqual(decimal_of(lines[self.receivable.pk].credit), Decimal("200.00"))


class ClosedPeriodRollbackTest(InvoiceJournalTestCase):
    def test_a_closed_period_is_a_400_that_leaves_no_invoice_and_no_burnt_number(self):
        client = self.make_client()
        draft = self.make_draft(client)
        day = timezone.localdate()
        closed = FiscalPeriod.objects.filter(
            tenant=self.tenant, start_date__lte=day, end_date__gte=day,
        ).update(status="Closed", is_closed=True)
        self.assertEqual(closed, 1, "لا فترةَ مالية تغطي اليوم")

        res = self.client.post(
            f"{DRAFTS}{draft.pk}/approve/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("مغلقة", str(res.data))
        # القيدُ داخل معاملة الإصدار: الفاتورةُ والرقمُ وحالةُ المسودّة ترجع كلُّها.
        self.assertFalse(FeeInvoice.objects.filter(tenant=self.tenant).exists())
        draft.refresh_from_db()
        self.assertEqual(draft.status, FeeDraft.STATUS_DRAFT)
        sequence = FeeInvoiceSequence.objects.filter(tenant=self.tenant).first()
        # الصفُّ يرجع مع المعاملة: إمّا لا عدّادَ أصلاً، وإمّا عدّادٌ لم يزد.
        self.assertTrue(
            sequence is None or sequence.last_number == 0,
            "رُقّم رقمُ فاتورةٍ لورقةٍ لم تصدر",
        )


class ReceivableReconciliationTest(InvoiceJournalTestCase):
    """**المطابقةُ الصريحة**: ذمّةُ الطرف في الدفاتر = «اللي عليه» في المكتب.

    **والمكتبُ هنا غيرُ مرخّص — بلا ضريبة، قصْداً**: `client_due` يقرأ مالَ
    الأتعاب من مسودّاتها (`FeeDraft.total`)، وفاتورةُ المكتب المرخّص تُضيف الضريبة
    فوقه (`total = net + tax_total`). فالمطابقةُ التامّةُ تقع حيث لا ضريبة، وهي
    الحالةُ التي تُثبت أن القيدَ يحمل إجماليَّ الورقة نفسِه إلى ذمّة الطرف. وأثرُ
    الضريبة على «اللي عليه» **ثغرةٌ مسجَّلة** لا تُخفيها هذه التطابقة.
    """

    def test_the_accounting_receivable_equals_client_due(self):
        services.set_office_setting(self.tenant, "office_licensed_dealer", False)
        client = self.make_client()
        draft = self.make_draft(client)
        self.approve(draft)
        res = self.client.post(
            PAYMENTS,
            {
                "client": client.pk,
                "amount": "500.00",
                "method": "cash",
                "paid_at": "2026-03-20",
            },
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(FeePayment.objects.filter(tenant=self.tenant).exists())

        partner_id = OfficeClient.objects.get(pk=client.pk).partner_id
        self.assertIsNotNone(partner_id)
        debit, credit = accounting_services.partner_posted_balance(
            self.tenant.pk, partner_id,
        )
        ledger_balance = decimal_of(debit) - decimal_of(credit)
        self.assertEqual(ledger_balance, NET - Decimal("500.00"))

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, ledger_balance)
