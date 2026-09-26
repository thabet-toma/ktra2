"""فائض الطرف «تحت الحساب» واستردادُه نقداً — مصدرٌ واحدٌ للقائمة والتحقّق.

الفائض ما لم يُوزَّع من رصيدٍ مرحَّلٍ للطرف:
- الدائن (مورد/مخلّص/وكيل/ناقل): سندات صرفه والإشعارات المدينة عليه.
- العميل: سندات قبضه والإشعارات الدائنة له.

يُوزَّع على مستنداته (السند كما كان، والإشعار عبر `note_allocation.py`) أو يُستردّ نقداً
بسندٍ قائمٍ أصلاً في بطاقة الطرف — `CustomerPayment`: «سند قبض (استرداد)» من الدائن
(Dr صندوق / Cr ذمّته) و«سند صرف (ردّ)» للعميل (Dr ذمّته / Cr صندوق). `PartyRefundAllocation`
يقول أيّ فائضٍ استهلكه السند؛ ويُحتسب ما دام السند مرحَّلاً.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from sales.models import CustomerPayment, PartyRefundAllocation

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")
ZERO = Decimal("0.00")
#: مصدر الفائض ← حقله في `PartyRefundAllocation`.
SOURCE_FIELDS = {
    "note": "source_note",
    "supplier_payment": "source_supplier_payment",
    "customer_payment": "source_customer_payment",
}
SOURCE_LABELS = {"note": "إشعار", "supplier_payment": "سند صرف", "customer_payment": "سند قبض"}


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(DEC)


def refunded_totals(source: str, ids) -> dict[int, Decimal]:
    """{المصدر: ما استردّته منه سنداتٌ مرحّلة} بعملته — استعلامٌ واحد."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    field = f"{SOURCE_FIELDS[source]}_id"
    rows = PartyRefundAllocation.objects.filter(
        **{f"{field}__in": ids}, refund__is_posted=True,
    ).values(field).annotate(t=Sum("amount")).values_list(field, "t")
    return {source_id: _money(total) for source_id, total in rows}


def refunded_total(source: str, source_id: int) -> Decimal:
    return refunded_totals(source, [source_id]).get(source_id, ZERO)


def _row(source: str, obj, free: Decimal, *, number: str, date) -> dict:
    return {
        "source": source,
        "id": obj.pk,
        "label": f"{SOURCE_LABELS[source]} {number}",
        "date": date.isoformat() if date else None,
        "amount": str(_money(obj.amount)),
        "unallocated": str(free),
        "currency": obj.currency_id,
        "currency_code": getattr(obj.currency, "Code", None),
        "exchange_rate": str(obj.exchange_rate or 1),
    }


def party_surplus_rows(tenant_id: int, partner) -> list[dict]:
    """فائض الطرف مصدراً مصدراً، الأقدم أولاً — ما تعرضه نافذة الاسترداد ويتحقّق منه الحفظ."""
    from logistics.domain.party_accruals import party_unallocated_notes, party_unallocated_vouchers
    from partners.models import is_creditor_party
    from sales.models import CreditDebitNote, PaymentAllocation

    rows = []
    if is_creditor_party(partner):
        for voucher, free, _base in party_unallocated_vouchers(tenant_id, partner.pk):
            rows.append(_row("supplier_payment", voucher, free, number=f"#{voucher.pk}",
                             date=voucher.payment_date))
        note_type = CreditDebitNote.TYPE_DEBIT
    else:
        receipts = list(CustomerPayment.objects.filter(
            tenant_id=tenant_id, partner_id=partner.pk, is_posted=True,
            kind=CustomerPayment.KIND_RECEIPT,
        ).select_related("currency").order_by("payment_date", "id"))
        used = dict(PaymentAllocation.objects.filter(payment__in=receipts).values("payment_id").annotate(
            t=Sum("amount")).values_list("payment_id", "t"))
        refunded = refunded_totals("customer_payment", [r.pk for r in receipts])
        for receipt in receipts:
            free = max(_money(receipt.amount) - _money(used.get(receipt.pk)) - refunded.get(receipt.pk, ZERO), ZERO)
            if free > 0:
                rows.append(_row("customer_payment", receipt, free, number=f"#{receipt.pk}",
                                 date=receipt.payment_date))
        note_type = CreditDebitNote.TYPE_CREDIT
    for note, free, _base in party_unallocated_notes(tenant_id, partner.pk, note_type=note_type):
        rows.append(_row("note", note, free, number=note.note_number, date=note.note_date))
    rows.sort(key=lambda r: (r["date"] or "9999-12-31", r["source"], r["id"]))
    return rows


def _expected_kind(partner) -> str:
    from partners.models import is_creditor_party

    return CustomerPayment.KIND_RECEIPT if is_creditor_party(partner) else CustomerPayment.KIND_REFUND


def _check_against_surplus(payment, rows: list[tuple[str, int, Decimal]]) -> None:
    available = {(r["source"], r["id"]): r for r in party_surplus_rows(payment.tenant_id, payment.partner)}
    for source, source_id, amount in rows:
        row = available.get((source, source_id))
        if row is None:
            raise ValidationError(f"{SOURCE_LABELS[source]} #{source_id} ليس فائضاً مرحَّلاً لهذا الطرف.")
        if row["currency"] != payment.currency_id:
            raise ValidationError(f"{row['label']} بعملةٍ غير عملة السند — استردّه بعملته.")
        if amount > Decimal(row["unallocated"]) + DEC:
            raise ValidationError(
                f"المسترَدّ من {row['label']} ({amount}) يتجاوز فائضه ({row['unallocated']}).")


def attach_refund_sources(payment, sources, *, user=None) -> None:
    """يربط سند الاسترداد الجديد بما يُطفئه من الفائض — داخل معاملة إنشائه.

    `sources`: ``[{"source": "note"|"supplier_payment"|"customer_payment", "id": N, "amount": X}]``.
    الدائن يُستردّ منه بسند قبض، والعميل يُردّ له بسند صرف (ردّ دفعة) — وإلا رُفض.
    """
    from accounting.services import create_audit_log

    rows = []
    for s in sources or []:
        try:
            source = str(s["source"])
            rows.append((source, int(s["id"]), _money(s.get("amount"))))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ValidationError("مصدر فائضٍ غير صالح.")
        if source not in SOURCE_FIELDS:
            raise ValidationError(f"مصدر فائضٍ غير معروف: {source}")
    if not rows:
        return
    if any(amount <= 0 for _s, _i, amount in rows):
        raise ValidationError("المبلغ المسترَدّ من كل مصدرٍ يجب أن يكون أكبر من صفر.")
    kind = payment.kind or CustomerPayment.KIND_RECEIPT
    if kind != _expected_kind(payment.partner):
        raise ValidationError(
            "استرداد فائض الدائن بسند قبض، وردّ فائض العميل بسند صرف (ردّ دفعة).")
    if payment.allocations.exists():
        raise ValidationError("سند الاسترداد لا يُوزَّع على فواتير — يُطفئ الفائض وحده.")
    total = sum((amount for _s, _i, amount in rows), ZERO)
    if total > _money(payment.amount) + DEC:
        raise ValidationError(f"مجموع المسترَدّ ({total}) يتجاوز مبلغ السند ({payment.amount}).")
    _check_against_surplus(payment, rows)
    rate = Decimal(str(payment.exchange_rate or 1)) or Decimal("1")
    for source, source_id, amount in rows:
        PartyRefundAllocation.objects.create(
            tenant_id=payment.tenant_id, refund=payment, amount=amount,
            amount_base=_money(amount * rate), **{f"{SOURCE_FIELDS[source]}_id": source_id},
        )
        logger.info("party_refund.attach payment=%s %s=%s amount=%s", payment.id, source, source_id, amount)
    create_audit_log(
        tenant=payment.tenant, user=user, action="ALLOCATE", model_name="CustomerPayment",
        object_id=payment.id, change_details=f"Refund of surplus {total} from {len(rows)} source(s)",
    )


def guard_refund_sources(payment) -> None:
    """عند ترحيل سند الاسترداد: ما يُطفئه لا يزال فائضاً — سندٌ آخر قد استهلكه منذ الحفظ."""
    rows = [
        (source, getattr(a, f"{field}_id"), _money(a.amount))
        for a in PartyRefundAllocation.objects.filter(refund=payment)
        for source, field in SOURCE_FIELDS.items() if getattr(a, f"{field}_id")
    ]
    if rows:
        _check_against_surplus(payment, rows)


def refund_sources_total(payment) -> Decimal:
    """ما خصّصه سند الاسترداد من مبلغه للفائض — لا يبقى «تحت الحساب» على السند نفسه."""
    return _money(PartyRefundAllocation.objects.filter(refund=payment).aggregate(t=Sum("amount"))["t"])


__all__ = [
    "party_surplus_rows", "attach_refund_sources", "guard_refund_sources", "refunded_totals",
    "refunded_total", "refund_sources_total",
]
