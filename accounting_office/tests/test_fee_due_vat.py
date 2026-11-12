"""«اللي عليه» يطابق ذمّةَ الدفاتر — **بالضريبة، وبالترخيص مفعّلاً** (#292).

**القواعدُ التي يسقط عندها الاختبار** (كلُّها بمكتبٍ مشتغلٍ مرخّص — الافتراض —
فالضريبةُ 16٪ على مسودّة 300 تساوي 48، والإجماليُّ 348):

1. **المستحقُّ إجماليُ الفاتورة الصادرة** لا مجموعُ مسودّتها: `client_due` تساوي
   ذمّةَ الطرف في `accounting` بالضريبة، والفرقُ صفر. وإطفاءُ الترخيص هو ما كان
   يُخفي العيبَ في `ReceivableReconciliationTest` القائم.
2. **دفعُ الإجمالي يُصفّر الاثنين**: لا رصيدَ دائن وهميّ من فرقِ الضريبة،
   والتخصيصُ يبلغ 348 لا 300.
3. الجزئيُّ 200 على 348 ⇒ المتلقّى 200 والمتبقّي 148.
4. **الإشعارُ الدائن يخصم من المستحقّ** كما يخصم من الذمّة: 348 − 100 = 248.
5. **التكميلية تدخل المستحقّ ولها قيدها** — متوازنٌ، بمرجعه، ومرّةً واحدة.
6. **إلغاءُ فاتورةٍ عليها تخصيصٌ حيّ ⇒ 409** برسالةٍ تسمّي الدفعة، والورقةُ تبقى
   صادرةً ولا قيدَ عكس — لا حذفَ صامتٌ لتخصيصٍ.
7. **إلغاءُ فاتورةٍ بلا تخصيص ⇒ قيدُ عكسٍ متوازن** بتاريخ الإلغاء، والورقةُ
   ملغاة، و«اللي عليه» لا يحسبها، **وقيدُها الأصليُّ باقٍ** (لا حذفَ لقيد).
8. **إعادةُ الاعتماد بعد الإلغاء لا تُرحّل قيداً ثانياً للأصل**: العكسُ مرّةٌ
   واحدة، والورقةُ الجديدةُ برقمٍ جديدٍ لها قيدُها وحدها.
9. **نظيرُ `ReceivableReconciliationTest` بالترخيص مفعّلاً** (الأصلُ يبقى كما هو
   بإطفائه) — فالمطابقةُ لم تعد تقع حيث لا ضريبة.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting import services as accounting_services
from accounting.models import FiscalPeriod, JournalHeader
from accounting_office import fees, office_journal, payments, services
from accounting_office.models import (
    FeeDraft,
    FeeInvoice,
    FeePayment,
    FeePaymentAllocation,
    OfficeClient,
    TaxCard,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency
from tenants.services import create_company

BASE = "/api/accounting-office/"
INVOICES = f"{BASE}fees/invoices/"
PAYMENTS = f"{BASE}fees/payments/"

#: مسودّةُ 300 بالضريبة الافتراضية 16٪ — الأرقامُ الثلاثةُ تتكرّر في كل اختبار.
NET = Decimal("300.00")
TAX = Decimal("48.00")
GROSS = Decimal("348.00")


def decimal_of(value) -> Decimal:
    return Decimal(str(value))


class FeeDueWithVatTestCase(APITestCase):
    """مكتبٌ بقالب `accounting_office` — **مرخّصٌ افتراضاً**، فورقتُه بالضريبة."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.owner = User.objects.create_user(
            username="fee_due_vat_owner", password="x",
        )
        cls.tenant = create_company(
            "مكتب اللي عليه بالضريبة", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    # ── أدواتٌ مشتركة ────────────────────────────────────────────────────
    def make_client(self, name="زبون الضريبة"):
        client = OfficeClient.objects.create(tenant=self.tenant, name=name)
        TaxCard.objects.create(client=client)
        return client

    def make_draft(self, client, *, total=NET, year=2026, month=3):
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
        return fees.approve_fee_draft(draft, actor=self.owner)

    def issued_invoice(self, client) -> FeeInvoice:
        """مسودّةٌ 300 تُعتمد فتُصدَر ورقتُها بالإجمالي 348."""
        draft = self.make_draft(client)
        self.approve(draft)
        return FeeInvoice.objects.get(
            tenant=self.tenant, source_draft=draft, cancelled_at__isnull=True,
        )

    def pay(self, client, amount, *, paid_at="2026-03-20", **extra):
        payload = {
            "client": client.pk,
            "amount": amount,
            "method": extra.pop("method", "cash"),
            "paid_at": paid_at,
        }
        payload.update(extra)
        return self.client.post(PAYMENTS, payload, format="json", **self.headers())

    def ledger_balance(self, client) -> Decimal:
        """رصيدُ ذمّة الطرف في `accounting` (مدين − دائن) — لقطةُ الدفاتر."""
        partner_id = OfficeClient.objects.get(pk=client.pk).partner_id
        self.assertIsNotNone(partner_id, "لا طرفَ في الدفاتر لهذا الزبون")
        debit, credit = accounting_services.partner_posted_balance(
            self.tenant.pk, partner_id,
        )
        return decimal_of(debit) - decimal_of(credit)

    def journals_of(self, *, reference_type, reference_id):
        return JournalHeader.objects.filter(
            tenant=self.tenant,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    def assertBalanced(self, journal):
        """مدينٌ = دائنٌ في القيد — الشرطُ الذي يجعل الذمّةَ تقرأ ما يُطالَب به."""
        totals = journal.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        self.assertEqual(totals["debit"], totals["credit"], "قيدٌ غير متوازن")
        return totals


class DueIncludesVatTest(FeeDueWithVatTestCase):
    """المستحقُّ إجماليُ الورقة الصادرة — لا مجموعُ مسودّتها."""

    def test_the_due_is_the_gross_invoice_and_matches_the_ledger(self):
        client = self.make_client()
        invoice = self.issued_invoice(client)

        # الورقةُ نفسها: 300 صافياً و48 ضريبةً و348 إجمالاً.
        self.assertEqual(decimal_of(invoice.total), GROSS)
        self.assertEqual(decimal_of(invoice.tax_total), TAX)

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, GROSS, "«اللي عليه» أسقط الضريبة")
        self.assertEqual(due.invoices_total, GROSS)
        self.assertEqual(due.paid_total, Decimal("0.00"))
        self.assertEqual(due.unpaid_count, 1)

        ledger = self.ledger_balance(client)
        self.assertEqual(ledger, GROSS)
        self.assertEqual(due.due - ledger, Decimal("0.00"), "«اللي عليه» يخالف الدفاتر")

    def test_the_receipt_payload_carries_the_gross_due(self):
        """إشعارُ القبض يطلب الإجماليَّ نفسَه: لا رقمَ ثانياً في الورقة."""
        client = self.make_client()
        self.issued_invoice(client)

        payload = payments.client_due_payload(self.tenant, client, user=self.owner)
        self.assertEqual(decimal_of(payload["due"]), GROSS)


class FullPaymentClearsTest(FeeDueWithVatTestCase):
    def test_paying_the_gross_clears_the_due_and_leaves_no_phantom_credit(self):
        client = self.make_client()
        invoice = self.issued_invoice(client)

        res = self.pay(client, "348.00")
        self.assertEqual(res.status_code, 201, res.content)
        payment = FeePayment.objects.get(pk=res.data["id"])

        allocated = sum(
            (decimal_of(row.amount) for row in payment.allocations.all()),
            Decimal("0.00"),
        )
        self.assertEqual(allocated, GROSS, "التخصيصُ توقّف عند الصافي فبقي فرقُ الضريبة")

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, Decimal("0.00"))
        self.assertEqual(due.credit, Decimal("0.00"), "رصيدٌ دائنٌ وهميّ من فرق الضريبة")
        self.assertEqual(due.paid_total, GROSS)

        # الدفاترُ صفرٌ أيضاً: إذنُ الذمّة 348 وقبضُها 348.
        self.assertEqual(self.ledger_balance(client), Decimal("0.00"))
        self.assertIsNotNone(invoice.pk)


class PartialPaymentTest(FeeDueWithVatTestCase):
    def test_a_partial_payment_leaves_the_rest_of_the_gross(self):
        client = self.make_client()
        self.issued_invoice(client)

        res = self.pay(client, "200.00")
        self.assertEqual(res.status_code, 201, res.content)

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.paid_total, Decimal("200.00"))
        self.assertEqual(due.due, Decimal("148.00"))
        self.assertEqual(due.credit, Decimal("0.00"))
        self.assertEqual(self.ledger_balance(client), Decimal("148.00"))


class CreditNoteLowersDueTest(FeeDueWithVatTestCase):
    def test_a_credit_note_lowers_the_due_as_it_lowers_the_ledger(self):
        client = self.make_client()
        invoice = self.issued_invoice(client)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "100.00", "reason": "خدمةٌ لم تُؤدَّ"},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, Decimal("248.00"), "الإشعارُ الدائن لم يخصم من المستحقّ")
        self.assertEqual(self.ledger_balance(client), Decimal("248.00"))

        # وصفُّ الفاتورة يقول الأرقام نفسها: 348 − 100 = 248، والإشعارُ ظاهرٌ فيه.
        ledger = payments.ledger_payload(
            self.tenant, user=self.owner, params={"client": client.pk},
        )
        row = ledger["invoices"]["results"][0]
        self.assertEqual(decimal_of(row["total"]), GROSS)
        self.assertEqual(decimal_of(row["credited_amount"]), Decimal("100.00"))
        self.assertEqual(decimal_of(row["remaining"]), Decimal("248.00"))

        # ولا يُشطب على الزبون أكثرُ من الباقي بعد الإشعار.
        with self.assertRaises(ValidationError):
            payments.write_off_fee_draft(
                invoice.source_draft,
                amount="300.00",
                reason="تنازل",
                actor=self.owner,
            )


class SupplementaryIsDueTest(FeeDueWithVatTestCase):
    def test_a_supplementary_invoice_is_due_and_posted_once(self):
        client = self.make_client()
        invoice = self.issued_invoice(client)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/supplementary/",
            {"amount": "50.00", "reason": "خدمةٌ نُسيت"},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        extra = FeeInvoice.objects.get(pk=res.data["id"])

        # مبلغُ التصحيح **إجماليُّ الورقة** كما في الإشعار الدائن: 50 منها 6.90 ضريبة.
        self.assertEqual(decimal_of(extra.total), Decimal("50.00"))
        self.assertEqual(decimal_of(extra.tax_total), Decimal("6.90"))
        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, Decimal("398.00"), "التكميليةُ لم تدخل المستحقّ")
        self.assertEqual(self.ledger_balance(client), Decimal("398.00"))

        journals = self.journals_of(
            reference_type=office_journal.REFERENCE_INVOICE, reference_id=extra.pk,
        )
        self.assertEqual(journals.count(), 1, "التكميليةُ بلا قيدٍ واحد")
        journal = journals.get()
        totals = self.assertBalanced(journal)
        self.assertEqual(decimal_of(totals["debit"]), Decimal("50.00"))

        # النداءُ الثاني لا يُكرّر: `post_journal` بـ`idempotent` على المرجع نفسه.
        office_journal.post_invoice_journal(extra, actor=self.owner)
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE, reference_id=extra.pk,
            ).count(),
            1,
            "قيدُ التكميلية تُرحّل مرّتين",
        )


class CancelWithAllocationRefusedTest(FeeDueWithVatTestCase):
    def test_cancelling_an_invoice_with_a_live_allocation_is_a_conflict(self):
        client = self.make_client()
        invoice = self.issued_invoice(client)
        payment = self.pay(client, "348.00")
        self.assertEqual(payment.status_code, 201, payment.content)
        receipt_number = payment.data["receipt_number"]
        self.assertTrue(
            FeePaymentAllocation.objects.filter(draft__client=client).exists(),
        )

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 409, res.content)
        self.assertIn(receipt_number, str(res.data), "الرسالةُ لم تسمّ الدفعة")
        invoice.refresh_from_db()
        self.assertIsNone(invoice.cancelled_at, "الفاتورةُ أُلغيت رغم التخصيص")
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE_CANCEL,
                reference_id=invoice.pk,
            ).count(),
            0,
            "قيدُ عكسٍ كُتب لفاتورةٍ رُفض إلغاؤها",
        )
        # «اللي عليه» لم يتغيّر: الورقةُ قائمةٌ والدفعةُ مخصَّصة.
        self.assertEqual(payments.client_due(self.tenant, client).due, Decimal("0.00"))


class CancelReversesJournalTest(FeeDueWithVatTestCase):
    def test_cancelling_an_unpaid_invoice_posts_a_balanced_reversal_and_keeps_the_original(
        self,
    ):
        client = self.make_client()
        invoice = self.issued_invoice(client)
        original = self.journals_of(
            reference_type=office_journal.REFERENCE_INVOICE, reference_id=invoice.pk,
        ).get()

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/",
            {"reason": "أُصدرت بالغلط"},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.cancelled_at)

        reversal = self.journals_of(
            reference_type=office_journal.REFERENCE_INVOICE_CANCEL,
            reference_id=invoice.pk,
        )
        self.assertEqual(reversal.count(), 1, "لا قيدَ عكسٍ لإلغاء فاتورةٍ صادرة")
        journal = reversal.get()
        self.assertBalanced(journal)
        self.assertEqual(
            journal.transaction_date, timezone.localdate(), "تاريخُ العكس يومُ الإلغاء",
        )

        # بنودُ الفاتورة معكوسةً: دائنُ ذمّةٍ بالإجمالي، مدينُ إيرادٍ وضريبة.
        receivables = [line for line in journal.lines.all() if line.partner_id]
        self.assertEqual(len(receivables), 1, "وسمُ الطرف على سطر الذمّة وحده")
        self.assertEqual(decimal_of(receivables[0].credit), GROSS)
        self.assertEqual(decimal_of(receivables[0].debit), Decimal("0.00"))
        self.assertEqual(decimal_of(journal.lines.aggregate(debit=Sum("debit"))["debit"]), GROSS)

        # ولا حذفَ لقيد: الأصلُ باقٍ مرحّلاً كما هو.
        original.refresh_from_db()
        self.assertTrue(original.is_posted)
        self.assertEqual(original.lines.count(), 3)

        # والذمّةُ سقطت والورقةُ لا تُحسب في «اللي عليه».
        self.assertEqual(self.ledger_balance(client), Decimal("0.00"))
        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, Decimal("0.00"))
        self.assertEqual(due.invoices_total, Decimal("0.00"))
        self.assertEqual(due.unpaid_count, 0)

    def test_the_draft_returns_to_pending_after_the_cancellation(self):
        client = self.make_client()
        draft = self.make_draft(client)
        self.approve(draft)
        invoice = FeeInvoice.objects.get(
            tenant=self.tenant, source_draft=draft, cancelled_at__isnull=True,
        )

        self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        draft.refresh_from_db()
        self.assertEqual(draft.status, FeeDraft.STATUS_DRAFT)


class CancelCornerCasesTest(FeeDueWithVatTestCase):
    """حالتان لا تُغطّيهما الموانعُ الثلاثة لكنّهما مالٌ حيّ أيضاً."""

    def test_cancelling_a_credit_note_returns_the_due_with_the_opposite_sign(self):
        """عكسُ الإشعار مدينٌ للذمّة: الأصلُ يعود 348 لا −100."""
        client = self.make_client()
        invoice = self.issued_invoice(client)
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "100.00", "reason": "خصم"},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        note_id = res.data["id"]

        cancelled = self.client.post(
            f"{INVOICES}{note_id}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.content)

        reversal = self.journals_of(
            reference_type=office_journal.REFERENCE_INVOICE_CANCEL,
            reference_id=note_id,
        )
        self.assertEqual(reversal.count(), 1)
        receivables = [line for line in reversal.get().lines.all() if line.partner_id]
        self.assertEqual(decimal_of(receivables[0].debit), Decimal("100.00"))

        self.assertEqual(payments.client_due(self.tenant, client).due, GROSS)
        self.assertEqual(self.ledger_balance(client), GROSS)

    def test_a_closed_period_rolls_the_whole_cancellation_back(self):
        """فشلُ العكس (فترةٌ مقفلة) يُرجع الإلغاءَ كلَّه: لا ورقةَ ملغاةً بذمّةٍ قائمة."""
        client = self.make_client()
        invoice = self.issued_invoice(client)
        day = timezone.localdate()
        closed = FiscalPeriod.objects.filter(
            tenant=self.tenant, start_date__lte=day, end_date__gte=day,
        ).update(status="Closed", is_closed=True)
        self.assertEqual(closed, 1, "لا فترةَ مالية تغطي اليوم")

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("مغلقة", str(res.data))
        invoice.refresh_from_db()
        self.assertIsNone(invoice.cancelled_at, "الإلغاءُ نُفِّذ رغم فشل القيد")
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE_CANCEL,
                reference_id=invoice.pk,
            ).count(),
            0,
        )
        # والورقةُ لا تزال مستحقّةً: «اللي عليه» 348 كما كانت.
        self.assertEqual(payments.client_due(self.tenant, client).due, GROSS)

    def test_an_invoice_that_was_never_posted_is_cancelled_without_a_reversal(self):
        """الترحيلُ كان مطفأً وقتَ الإصدار ⇒ لا قيدَ أصليّ ⇒ لا عكسَ يُدائن ذمّاً لم تُدَن."""
        services.set_office_setting(self.tenant, "office_journal_enabled", False)
        client = self.make_client()
        invoice = self.issued_invoice(client)
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE, reference_id=invoice.pk,
            ).count(),
            0,
        )
        services.set_office_setting(self.tenant, "office_journal_enabled", True)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.cancelled_at)
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE_CANCEL,
                reference_id=invoice.pk,
            ).count(),
            0,
            "عكسٌ لورقةٍ لم تُرحَّل قطّ",
        )
        # ولا طرفَ في الدفاتر أصلاً (لا قيدَ كُتب قطّ) — فالذمّةُ صفرٌ بلا رصيدٍ سالب.
        self.assertIsNone(OfficeClient.objects.get(pk=client.pk).partner_id)
        self.assertEqual(payments.client_due(self.tenant, client).due, Decimal("0.00"))


class ReapprovalDoesNotDoublePostTest(FeeDueWithVatTestCase):
    def test_re_approval_posts_no_second_journal_for_the_cancelled_invoice(self):
        client = self.make_client()
        draft = self.make_draft(client)
        self.approve(draft)
        first = FeeInvoice.objects.get(
            tenant=self.tenant, source_draft=draft, cancelled_at__isnull=True,
        )
        self.client.post(
            f"{INVOICES}{first.pk}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE, reference_id=first.pk,
            ).count(),
            1,
            "قيدُ الأصل غُيّر أو تكرّر قبل إعادة الاعتماد",
        )

        # إعادةُ الاعتماد تُصدر ورقةً **جديدةً برقمٍ جديد** — ولها وحدها قيدُها.
        self.approve(draft)
        second = FeeInvoice.objects.get(
            tenant=self.tenant, source_draft=draft, cancelled_at__isnull=True,
        )
        self.assertNotEqual(second.pk, first.pk)
        self.assertNotEqual(second.number, first.number)

        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE, reference_id=first.pk,
            ).count(),
            1,
            "إعادةُ الاعتماد رحّلت قيداً ثانياً للورقة الملغاة",
        )
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE_CANCEL,
                reference_id=first.pk,
            ).count(),
            1,
            "قيدُ العكس تكرّر",
        )
        self.assertEqual(
            self.journals_of(
                reference_type=office_journal.REFERENCE_INVOICE, reference_id=second.pk,
            ).count(),
            1,
            "الورقةُ الجديدةُ بلا قيد",
        )

        # ثلاثُ قيودٍ لا رابع: فاتورة، عكسُها، فاتورةٌ جديدة.
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant=self.tenant,
                reference_type__in=(
                    office_journal.REFERENCE_INVOICE,
                    office_journal.REFERENCE_INVOICE_CANCEL,
                ),
            ).count(),
            3,
        )
        self.assertEqual(payments.client_due(self.tenant, client).due, GROSS)


class LicensedReconciliationTest(FeeDueWithVatTestCase):
    """**نظيرُ `ReceivableReconciliationTest` بالترخيص مفعّلاً** (#292/٩).

    الأصلُ في `test_office_invoice_journal` يبقى بإطفاء الترخيص كما هو؛ وهذا يثبت
    أنّ المطابقةَ لا تقع في الحالة التي لا ضريبةَ فيها وحدها.
    """

    def test_the_live_licensed_receivable_equals_client_due(self):
        client = self.make_client()
        invoice = self.issued_invoice(client)
        self.assertEqual(decimal_of(invoice.total), GROSS)

        before = payments.client_due(self.tenant, client)
        self.assertEqual(before.due, self.ledger_balance(client))
        self.assertEqual(before.due, GROSS)

        res = self.pay(client, "348.00", paid_at="2026-03-20")
        self.assertEqual(res.status_code, 201, res.content)

        after = payments.client_due(self.tenant, client)
        self.assertEqual(after.due, Decimal("0.00"))
        self.assertEqual(after.due, self.ledger_balance(client))
        self.assertEqual(after.credit, Decimal("0.00"))

    def test_the_statement_closing_balance_equals_the_due(self):
        """كشفُ الحساب يرسل الإجماليَّ حركةً — فلا يطلب 300 و«اللي عليه» 348."""
        client = self.make_client()
        self.issued_invoice(client)
        self.pay(client, "148.00", paid_at="2026-04-10")

        payload = payments.statement_payload(
            self.tenant, client, period_to=datetime.date(2027, 1, 1),
        )
        self.assertEqual(
            decimal_of(payload["closing_balance"]),
            payments.client_due(self.tenant, client).due,
        )
        self.assertEqual(decimal_of(payload["due"]), Decimal("200.00"))
        self.assertEqual(
            decimal_of(payload["groups"]["invoices"][0]["total"]), GROSS,
        )
