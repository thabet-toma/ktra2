"""CHQ-2 — معيار المالك لدورة الشيك الوارد، وحارس إلغاء ترحيل السند.

**المعيار (ثنائي):** شيك وارد يُستلَم ثم يُودَع ثم يرتدّ يترك **ثلاثة قيود
متوازنة**، ورصيد العميل يعود إلى ما كان عليه قبل الاستلام بالضبط:

    1) ترحيل سند القبض : مدين «شيكات في المحفظة» 1109 ÷ دائن ذمم العميل
    2) الإيداع          : مدين «شيكات برسم التحصيل» 1107 ÷ دائن 1109
    3) الارتداد         : مدين ذمم العميل ÷ دائن 1107

**والعطل الذي يغلقه الحارس:** كان إلغاء ترحيل السند يحذف قيده ويعيد فقط
الشيكات التي ما تزال `Under_Collection` إلى `Draft` — فشيكٌ وصل `Collected`
(أو أُودِع فصار له قيد `CHEQUE_DEPOSIT` مستقل) يبقى كما هو بينما يختفي القيد
الذي مدّن حساب الشيكات: الحساب يصير سالباً والعميل يعود مديناً رغم أن النقد في
البنك. لا شيء كان يمنع ذلك.
"""
import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from accounting.models import (
    Account,
    Cheque,
    ChequeMovement,
    FiscalPeriod,
    JournalHeader,
    JournalLine,
)
from accounting.services import post_journal, transfer_cheque
from partners.models import Partner
from sales.models import CustomerPayment, SupplierPayment
from sales.services import (
    post_customer_payment,
    post_supplier_payment,
    unpost_customer_payment,
    unpost_supplier_payment,
)
from tenants.models import Currency, Tenant

pytestmark = pytest.mark.django_db

WHEN = dt.date(2026, 7, 5)
OPENING = Decimal("1000.00")
CHEQUE_AMOUNT = Decimal("200.00")


class _Books:
    """شركة بشجرة معيارية مصغّرة — ما تحتاجه دورة الشيك ولا شيء غيره."""

    def __init__(self, tenant_id):
        self.tenant = Tenant.objects.create(
            TenantID=tenant_id, CompanyName=f"Cheque Criterion {tenant_id}")
        self.currency, _ = Currency.objects.get_or_create(
            CurrencyID=1,
            defaults={"Code": "ILS", "Symbol": "₪", "IsBaseCurrency": True},
        )
        FiscalPeriod.objects.create(
            tenant=self.tenant, name="2026", start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 12, 31), is_closed=False)
        mk = lambda code, name, kind: Account.objects.create(  # noqa: E731
            tenant=self.tenant, code=code, name=name,
            account_type=kind, is_active=True)
        self.cash = mk("1110", "صندوق", "Asset")
        self.ar = mk("1101", "ذمم عملاء", "Asset")
        self.uc = mk("1107", "شيكات برسم التحصيل", "Asset")
        self.in_hand = mk("1109", "شيكات في المحفظة (Cheques in Hand)", "Asset")
        self.ap = mk("2101", "ذمم موردين", "Liability")
        self.payable = mk("2111", "شيكات برسم الدفع", "Liability")
        self.revenue = mk("4101", "إيرادات", "Revenue")
        self.customer = Partner.objects.create(
            tenant=self.tenant, name="زبون", partner_type="Customer",
            linked_account=self.ar)
        self.supplier = Partner.objects.create(
            tenant=self.tenant, name="مورد", partner_type="Supplier",
            linked_account=self.ap)

    def open_customer_balance(self, amount=OPENING):
        """رصيد افتتاحي مدين على العميل — نقطة العودة التي يقيس عليها المعيار."""
        post_journal(
            tenant_id=self.tenant.TenantID,
            transaction_date=dt.date(2026, 6, 1),
            reference_type="OPENING", reference_id=1,
            description="رصيد افتتاحي",
            lines_data=[
                {"account": self.ar.pk, "partner": self.customer.pk,
                 "debit": amount, "credit": Decimal("0"), "description": "افتتاحي"},
                {"account": self.revenue.pk, "partner": None,
                 "debit": Decimal("0"), "credit": amount, "description": "افتتاحي"},
            ],
            currency=self.currency,
        )

    def customer_balance(self):
        rows = JournalLine.objects.filter(
            tenant=self.tenant, account=self.ar, partner=self.customer)
        return sum(
            (Decimal(str(r.debit)) - Decimal(str(r.credit)) for r in rows),
            Decimal("0"),
        ).quantize(Decimal("0.01"))

    def account_balance(self, account):
        rows = JournalLine.objects.filter(tenant=self.tenant, account=account)
        return sum(
            (Decimal(str(r.debit)) - Decimal(str(r.credit)) for r in rows),
            Decimal("0"),
        ).quantize(Decimal("0.01"))

    def incoming_voucher(self, amount=CHEQUE_AMOUNT, *, number="CHQ-CRIT"):
        payment = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, payment_date=WHEN,
            amount=amount, currency=self.currency,
            cash_or_bank_account=self.cash)
        cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number=number, amount=amount,
            currency=self.currency, due_date=dt.date(2026, 9, 1),
            partner=self.customer, direction="Incoming", status="Draft",
            customer_payment=payment)
        return payment, cheque

    def outgoing_voucher(self, amount=CHEQUE_AMOUNT, *, number="OUT-CRIT"):
        payment = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, payment_date=WHEN,
            amount=amount, currency=self.currency,
            cash_or_bank_account=self.cash)
        cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number=number, amount=amount,
            currency=self.currency, due_date=dt.date(2026, 9, 1),
            partner=self.supplier, direction="Outgoing", status="Draft",
            supplier_payment=payment)
        return payment, cheque


def _cycle_journals(books):
    """قيود دورة الشيك وحدها — بلا القيد الافتتاحي."""
    return list(
        JournalHeader.objects.filter(tenant=books.tenant)
        .exclude(reference_type="OPENING")
        .order_by("id")
    )


def _assert_balanced(journal):
    lines = list(journal.lines.all())
    debit = sum((Decimal(str(l.debit)) for l in lines), Decimal("0"))
    credit = sum((Decimal(str(l.credit)) for l in lines), Decimal("0"))
    assert debit == credit, f"قيد غير متوازن {journal.reference_type}: {debit} ≠ {credit}"
    assert debit > 0


def _sides(journal):
    """(أكواد حسابات المدين، أكواد حسابات الدائن) لقيدٍ واحد."""
    lines = journal.lines.select_related("account")
    return (
        {l.account.code for l in lines if Decimal(str(l.debit)) > 0},
        {l.account.code for l in lines if Decimal(str(l.credit)) > 0},
    )


def test_incoming_receive_deposit_bounce_three_journals_ar_restored():
    """المعيار: استلام ← إيداع ← ارتداد = ثلاثة قيود، ورصيد العميل كما كان."""
    books = _Books(48101)
    books.open_customer_balance()
    before = books.customer_balance()
    assert before == OPENING

    # 1) الاستلام — ترحيل سند القبض: الورقة تدخل المحفظة (1109) لا البنك.
    payment, cheque = books.incoming_voucher()
    payment = post_customer_payment(payment)
    cheque.refresh_from_db()
    assert cheque.status == "Received"
    assert books.customer_balance() == (OPENING - CHEQUE_AMOUNT)
    assert books.account_balance(books.in_hand) == CHEQUE_AMOUNT

    # أهمّ حدث في حياة الشيك — دخوله الدفاتر — صار له صفّ حركة مربوط بقيده.
    receive = ChequeMovement.objects.get(cheque=cheque, movement_type="receive")
    assert receive.journal_id == payment.journal_id

    # 2) الإيداع — قيد مستقل: 1107 ÷ 1109، بلا أثر على العميل.
    transfer_cheque(cheque.pk, "deposit", movement_date=dt.date(2026, 7, 10))
    cheque.refresh_from_db()
    assert cheque.status == "Under_Collection"
    assert books.customer_balance() == (OPENING - CHEQUE_AMOUNT)
    assert books.account_balance(books.in_hand) == Decimal("0.00")
    assert books.account_balance(books.uc) == CHEQUE_AMOUNT

    # 3) الارتداد — الذمّة تعود على العميل والورقة تخرج من 1107.
    transfer_cheque(cheque.pk, "bounce", movement_date=dt.date(2026, 9, 2))
    cheque.refresh_from_db()
    assert cheque.status == "Bounced"

    journals = _cycle_journals(books)
    assert [j.reference_type for j in journals] == [
        "CUSTOMER_PAYMENT", "CHEQUE_DEPOSIT", "CHEQUE_BOUNCE",
    ], [j.reference_type for j in journals]
    for j in journals:
        _assert_balanced(j)
    assert _sides(journals[0]) == ({"1109"}, {"1101"})
    assert _sides(journals[1]) == ({"1107"}, {"1109"})
    assert _sides(journals[2]) == ({"1101"}, {"1107"})

    # المعيار نفسه: العودة إلى ما قبل الاستلام بالضبط — لا فلساً أكثر ولا أقل.
    assert books.customer_balance() == before
    assert books.account_balance(books.in_hand) == Decimal("0.00")
    assert books.account_balance(books.uc) == Decimal("0.00")


def test_unposting_a_voucher_whose_cheque_was_collected_is_rejected():
    """العطل المالي: القيد يُحذف والشيك محصَّل ⇒ حساب الشيكات سالب."""
    books = _Books(48102)
    books.open_customer_balance()
    payment, cheque = books.incoming_voucher(number="CHQ-COLLECTED")
    payment = post_customer_payment(payment)
    transfer_cheque(cheque.pk, "deposit", movement_date=dt.date(2026, 7, 10))
    transfer_cheque(cheque.pk, "collect", movement_date=dt.date(2026, 9, 2))
    cheque.refresh_from_db()
    assert cheque.status == "Collected"

    with pytest.raises(ValidationError) as err:
        unpost_customer_payment(payment)
    assert "CHQ-COLLECTED" in str(err.value)

    payment.refresh_from_db()
    assert payment.is_posted is True
    assert JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=payment.pk).exists()


def test_unposting_a_voucher_whose_cheque_was_only_deposited_is_rejected():
    """الحالة الخبيثة: الشيك ما زال `Under_Collection` لكن له قيد إيداع مستقل."""
    books = _Books(48103)
    books.open_customer_balance()
    payment, cheque = books.incoming_voucher(number="CHQ-DEPOSITED")
    payment = post_customer_payment(payment)
    transfer_cheque(cheque.pk, "deposit", movement_date=dt.date(2026, 7, 10))
    cheque.refresh_from_db()
    assert cheque.status == "Under_Collection"

    with pytest.raises(ValidationError) as err:
        unpost_customer_payment(payment)
    assert "CHQ-DEPOSITED" in str(err.value)


def test_unposting_a_voucher_whose_cheque_never_moved_still_works():
    """الحارس ليس سدّاً: شيك لم يتحرك بعد يعود مسودةً ويُسجَّل رجوعه."""
    books = _Books(48104)
    books.open_customer_balance()
    payment, cheque = books.incoming_voucher(number="CHQ-UNTOUCHED")
    payment = post_customer_payment(payment)
    assert books.customer_balance() == (OPENING - CHEQUE_AMOUNT)

    unpost_customer_payment(payment)

    cheque.refresh_from_db()
    assert cheque.status == "Draft"
    assert books.customer_balance() == OPENING
    assert books.account_balance(books.in_hand) == Decimal("0.00")
    assert ChequeMovement.objects.filter(
        cheque=cheque, movement_type="revert").exists()


def test_outgoing_voucher_posts_on_2111_and_records_its_movement():
    """الصادر يبقى على «شيكات برسم الدفع» — وله الآن صفّ حركة نظامي."""
    books = _Books(48105)
    payment, cheque = books.outgoing_voucher()
    payment = post_supplier_payment(payment)

    cheque.refresh_from_db()
    assert cheque.status == "Under_Collection"
    issue = ChequeMovement.objects.get(cheque=cheque, movement_type="issue")
    assert issue.journal_id == payment.journal_id
    assert books.account_balance(books.payable) == -CHEQUE_AMOUNT

    unpost_supplier_payment(payment)
    cheque.refresh_from_db()
    assert cheque.status == "Draft"
    assert ChequeMovement.objects.filter(
        cheque=cheque, movement_type="revert").exists()


def test_unposting_a_supplier_voucher_whose_cheque_was_cashed_is_rejected():
    """مرآة الجانب الوارد: شيك صادر صُرف من البنك لا يُلغى سنده."""
    books = _Books(48106)
    payment, cheque = books.outgoing_voucher(number="OUT-CASHED")
    payment = post_supplier_payment(payment)
    transfer_cheque(cheque.pk, "collect", movement_date=dt.date(2026, 9, 2))
    cheque.refresh_from_db()
    assert cheque.status == "Collected"

    with pytest.raises(ValidationError) as err:
        unpost_supplier_payment(payment)
    assert "OUT-CASHED" in str(err.value)
    payment.refresh_from_db()
    assert payment.is_posted is True


def test_legacy_cheque_already_under_collection_keeps_posting_on_1107():
    """قاعدة الـcutover: الورقة التي في البنك أصلاً لا تُقيَّد على المحفظة."""
    books = _Books(48107)
    books.open_customer_balance()
    payment, cheque = books.incoming_voucher(number="CHQ-LEGACY")
    Cheque.objects.filter(pk=cheque.pk).update(status="Under_Collection")

    payment = post_customer_payment(payment)

    cheque.refresh_from_db()
    assert cheque.status == "Under_Collection"
    assert books.account_balance(books.uc) == CHEQUE_AMOUNT
    assert books.account_balance(books.in_hand) == Decimal("0.00")
