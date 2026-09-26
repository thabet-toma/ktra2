"""توزيع الإشعار المدين/الدائن **المسوّي** — رصيدٌ للطرف يُوزَّع كالسند.

المسوّي: إشعارٌ مدينٌ على دائن (خصمٌ منه: Dr ذمّته) أو دائنٌ على عميل (Cr ذمّته) — كلاهما
يُنقص ما يُستحق فيعمل عمل الدفعة بلا نقد. يُوزَّع على:

- فواتير شراء الدائن ← `sales.CreditDebitNoteAllocation.purchase_invoice`
- مستحقّاته اللوجستية (تخليص/شحن/إرسالية) ← `logistics.LogisticsAccrualAllocation.note`
- فواتير مبيع العميل ← `sales.CreditDebitNoteAllocation.sales_invoice` (ويزيد `amount_paid`)

ربطٌ بلا قيد: الترحيل قيّد الذمّة أصلاً. ما لم يُوزَّع «تحت الحساب» في بطاقة الطرف.
الإشعار المعاكس (دائنٌ على دائن، مدينٌ على عميل) يزيد المستحق فلا يُوزَّع — ربطه بمستحقٍّ
لوجستي أو فاتورة شراء يرفع مستحقّها كما كان.

عند الترحيل يُوزَّع المسوّي المربوط على مستنده تلقائياً بحدّ متبقّيه (`auto_allocate_linked`)،
وإلغاء الترحيل يفكّ كل توزيعاته في المعاملة نفسها (`release_note_allocations`).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from accounting.services import convert_amount, create_audit_log
from sales.models import CreditDebitNote, CreditDebitNoteAllocation, SalesInvoice

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")
ZERO = Decimal("0.00")
#: أصناف المستحقّات اللوجستية — `logistics.domain.party_accruals.KINDS`.
ACCRUAL_KINDS = ("clearance", "freight", "local")
TARGET_KINDS = ("sales_invoice", "purchase_invoice", *ACCRUAL_KINDS)


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(DEC)


def _rate(note) -> Decimal:
    return Decimal(str(note.exchange_rate or 1)) or Decimal("1")


def note_is_creditor(note) -> bool:
    from partners.models import is_creditor_party

    return is_creditor_party(note.partner)


def note_settles(note) -> bool:
    """الإشعار يُنقص ما يُستحق (فيُوزَّع كالسند): مدينٌ على دائن، أو دائنٌ على عميل."""
    return (note.note_type == CreditDebitNote.TYPE_DEBIT) == note_is_creditor(note)


def note_allocated(note) -> Decimal:
    """ما وُزِّع من الإشعار بعملته — على الفواتير والمستحقّات اللوجستية معاً."""
    from logistics.models import LogisticsAccrualAllocation

    return (
        _money(CreditDebitNoteAllocation.objects.filter(note=note).aggregate(t=Sum("amount"))["t"])
        + _money(LogisticsAccrualAllocation.objects.filter(note=note).aggregate(t=Sum("amount"))["t"])
    )


def note_unallocated(note) -> Decimal:
    """ما بقي من الإشعار المسوّي المرحَّل «تحت الحساب» بعملته — صفرٌ لغيره."""
    if note.status != CreditDebitNote.STATUS_POSTED or not note_settles(note):
        return ZERO
    return max(_money(note.amount) - note_allocated(note), ZERO)


def posted_note_allocations_total(invoice_id: int) -> Decimal:
    """ما أطفأته الإشعارات المرحّلة من فاتورة بيع (بعملتها) — شريك `posted_allocations_total`
    في عقد `amount_paid`. منفصلٌ عنه عمداً: ذاك نقدٌ دخل فعلاً ويبني سقف الردّ النقدي للمرتجع."""
    total = CreditDebitNoteAllocation.objects.filter(
        sales_invoice_id=invoice_id, note__status=CreditDebitNote.STATUS_POSTED,
    ).aggregate(t=Sum("amount_in_invoice_currency"))["t"]
    return _money(total)


def posted_invoice_settled_total(invoice_id: int) -> Decimal:
    """كل ما أطفأ فاتورة البيع: توزيعات السندات المرحّلة + توزيعات الإشعارات المرحّلة."""
    from .flow import posted_allocations_total

    return (posted_allocations_total(invoice_id) + posted_note_allocations_total(invoice_id)).quantize(DEC)


def _note_label(note) -> str:
    return f"الإشعار {note.note_number}"


def _sales_invoice_open(inv) -> Decimal:
    from .calc import linked_return_credit_summary

    return _money(linked_return_credit_summary([inv])[inv.pk]["collectible"])


def _to_invoice_currency(note, inv, amount: Decimal) -> Decimal:
    if note.currency_id == inv.currency_id:
        return amount
    converted, _rate_used = convert_amount(
        amount=amount, from_currency_id=note.currency_id, to_currency_id=inv.currency_id,
        tenant_id=note.tenant_id, effective_date=note.note_date,
    )
    return _money(converted)


def _allocate_to_sales_invoice(note, inv_id: int, amount: Decimal) -> str:
    from .flow import guard_invoice_allocation_total

    inv = SalesInvoice.objects.select_for_update().filter(pk=inv_id, tenant_id=note.tenant_id).first()
    if inv is None:
        raise ValidationError(f"فاتورة البيع #{inv_id} غير موجودة في هذه الشركة.")
    if note_is_creditor(note):
        raise ValidationError("إشعار الدائن يُوزَّع على فواتير شرائه ومستحقّاته، لا على فواتير البيع.")
    if inv.customer_id != note.partner_id:
        raise ValidationError(f"الفاتورة #{inv.invoice_number} لا تخصّ طرف الإشعار.")
    if inv.status != SalesInvoice.STATUS_POSTED:
        raise ValidationError(f"الفاتورة #{inv.invoice_number} غير مرحّلة.")
    if inv.invoice_kind != SalesInvoice.INVOICE_KIND_SALE:
        raise ValidationError(f"الإشعار لا يُوزَّع على مرتجع البيع #{inv.invoice_number}.")
    in_invoice = _to_invoice_currency(note, inv, amount)
    remaining = _sales_invoice_open(inv)
    if in_invoice > remaining + DEC:
        raise ValidationError(
            f"مبلغ التوزيع ({in_invoice}) يتجاوز المتبقّي على الفاتورة #{inv.invoice_number} ({remaining}).")
    guard_invoice_allocation_total(inv, incoming=in_invoice)
    CreditDebitNoteAllocation.objects.create(
        tenant_id=note.tenant_id, note=note, sales_invoice=inv, amount=amount,
        amount_in_invoice_currency=in_invoice, amount_base=_money(amount * _rate(note)),
    )
    inv.amount_paid = _money(inv.amount_paid) + in_invoice
    inv.save(update_fields=["amount_paid"])
    return inv.invoice_number


def _allocate_to_purchase_invoice(note, inv_id: int, amount: Decimal) -> str:
    from logistics.models import PurchaseInvoice
    from logistics.services import purchase_invoice_payment_summary

    inv = PurchaseInvoice.objects.select_for_update().filter(pk=inv_id, tenant_id=note.tenant_id).first()
    if inv is None:
        raise ValidationError(f"فاتورة الشراء #{inv_id} غير موجودة في هذه الشركة.")
    if not note_is_creditor(note):
        raise ValidationError("إشعار العميل يُوزَّع على فواتير مبيعه، لا على فواتير الشراء.")
    if inv.partner_id != note.partner_id:
        raise ValidationError(f"فاتورة الشراء #{inv.invoice_number} لا تخصّ طرف الإشعار.")
    if not inv.is_posted:
        raise ValidationError(f"فاتورة الشراء #{inv.invoice_number} غير مرحّلة.")
    if inv.is_return:
        raise ValidationError(f"الإشعار لا يُوزَّع على مرتجع الشراء #{inv.invoice_number}.")
    in_invoice = _to_invoice_currency(note, inv, amount)
    remaining = _money(purchase_invoice_payment_summary(inv)["remaining_balance"])
    if in_invoice > remaining + DEC:
        raise ValidationError(
            f"مبلغ التوزيع ({in_invoice}) يتجاوز المتبقّي على فاتورة الشراء #{inv.invoice_number} ({remaining}).")
    CreditDebitNoteAllocation.objects.create(
        tenant_id=note.tenant_id, note=note, purchase_invoice=inv, amount=amount,
        amount_in_invoice_currency=in_invoice, amount_base=_money(amount * _rate(note)),
    )
    return inv.invoice_number


def _allocate_to_accrual(note, kind: str, pk: int, amount: Decimal) -> str:
    from logistics.domain.party_accruals import allocate_note_to_accrual

    if not note_is_creditor(note):
        raise ValidationError("إشعار العميل لا يُوزَّع على مستحقّات التخليص والشحن والنقل.")
    return allocate_note_to_accrual(note, kind, pk, amount, base=_money(amount * _rate(note)))


def _parse_rows(allocations) -> list[tuple[str, int, Decimal]]:
    rows = []
    for a in allocations or []:
        try:
            kind = str(a["kind"])
            rows.append((kind, int(a["id"]), _money(a.get("amount"))))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ValidationError("صفّ توزيع غير صالح.")
        if kind not in TARGET_KINDS:
            raise ValidationError(f"نوع مستند غير معروف: {kind}")
    if not rows:
        raise ValidationError("لا توزيعات مُرسَلة.")
    if any(amount <= 0 for _k, _i, amount in rows):
        raise ValidationError("مبلغ التوزيع يجب أن يكون أكبر من صفر.")
    return rows


def allocate_note(note, allocations: list[dict], *, user=None):
    """توزيع إشعارٍ مسوٍّ مرحَّل على مستندات طرفه — مرآة `allocate_supplier_payment`.

    `allocations`: ``[{"kind": "sales_invoice"|"purchase_invoice"|"clearance"|"freight"|"local",
    "id": <pk>, "amount": <بعملة الإشعار>}]``.
    """
    rows = _parse_rows(allocations)
    with transaction.atomic():
        note = CreditDebitNote.objects.select_for_update().select_related("partner").get(pk=note.pk)
        if note.status != CreditDebitNote.STATUS_POSTED:
            raise ValidationError("رحّل الإشعار أولاً — التوزيع لإشعارٍ مرحَّل.")
        if not note_settles(note):
            raise ValidationError(
                "هذا الإشعار يزيد ما يُستحق للطرف أو عليه — لا يُوزَّع. التوزيع للمدين على دائنٍ "
                "وللدائن على عميل.")
        total_new = sum((amount for _k, _i, amount in rows), ZERO)
        free = note_unallocated(note)
        if total_new > free + DEC:
            raise ValidationError(f"مجموع التوزيعات ({total_new}) يتجاوز غير الموزَّع من الإشعار ({free}).")
        labels = []
        for kind, pk, amount in rows:
            if kind == "sales_invoice":
                labels.append(_allocate_to_sales_invoice(note, pk, amount))
            elif kind == "purchase_invoice":
                labels.append(_allocate_to_purchase_invoice(note, pk, amount))
            else:
                labels.append(_allocate_to_accrual(note, kind, pk, amount))
            logger.info("credit_debit_note.allocate note=%s %s=%s amount=%s", note.id, kind, pk, amount)
        create_audit_log(
            tenant=note.tenant, user=user, action="ALLOCATE", model_name="CreditDebitNote",
            object_id=note.id, change_details=f"Allocated {total_new} to {', '.join(labels)}",
        )
    return note


def _release_sales_allocations(allocations) -> None:
    """يُنقص `amount_paid` بما أطفأه كل توزيعٍ على فاتورة بيع ثم يحذفه — تحت قفل الفاتورة."""
    by_invoice: dict[int, Decimal] = {}
    for alloc in allocations:
        by_invoice[alloc.sales_invoice_id] = by_invoice.get(alloc.sales_invoice_id, ZERO) + _money(
            alloc.amount_in_invoice_currency)
    for inv in SalesInvoice.objects.select_for_update().filter(pk__in=sorted(by_invoice)).order_by("pk"):
        inv.amount_paid = max(_money(inv.amount_paid) - by_invoice[inv.pk], ZERO)
        inv.save(update_fields=["amount_paid"])
    CreditDebitNoteAllocation.objects.filter(pk__in=[a.pk for a in allocations]).delete()


def deallocate_note(note, *, allocation_kind: str, allocation_id: int, user=None):
    """فكّ توزيعٍ واحد — المبلغ يعود «تحت الحساب» على الإشعار.

    `allocation_kind`: ``invoice`` (فاتورة بيع أو شراء) أو ``accrual`` (مستحقٌّ لوجستي).
    """
    from logistics.models import LogisticsAccrualAllocation

    with transaction.atomic():
        note = CreditDebitNote.objects.select_for_update().get(pk=note.pk)
        if allocation_kind == "accrual":
            alloc = LogisticsAccrualAllocation.objects.select_for_update().filter(
                pk=allocation_id, note=note).first()
            if alloc is None:
                raise ValidationError("التوزيع غير موجود على هذا الإشعار.")
            amount = alloc.amount
            alloc.delete()
        elif allocation_kind == "invoice":
            alloc = CreditDebitNoteAllocation.objects.select_for_update().filter(
                pk=allocation_id, note=note).first()
            if alloc is None:
                raise ValidationError("التوزيع غير موجود على هذا الإشعار.")
            amount = alloc.amount
            if alloc.sales_invoice_id:
                _release_sales_allocations([alloc])
            else:
                alloc.delete()
        else:
            raise ValidationError("نوع توزيع غير معروف.")
        create_audit_log(
            tenant=note.tenant, user=user, action="DEALLOCATE", model_name="CreditDebitNote",
            object_id=note.id, change_details=f"Deallocated {amount} ({allocation_kind} #{allocation_id})",
        )
    logger.info("credit_debit_note.deallocate note=%s %s=%s amount=%s", note.id, allocation_kind,
                allocation_id, amount)
    return note


def note_allocation_rows(note) -> list[dict]:
    """توزيعات الإشعار للعرض: {allocation_kind, allocation_id, kind, id, label, amount}."""
    from logistics.domain.party_accruals import note_accrual_allocation_rows

    rows = []
    for alloc in CreditDebitNoteAllocation.objects.filter(note=note).select_related(
        "sales_invoice", "purchase_invoice",
    ).order_by("id"):
        inv = alloc.sales_invoice or alloc.purchase_invoice
        rows.append({
            "allocation_kind": "invoice", "allocation_id": alloc.pk,
            "kind": "sales_invoice" if alloc.sales_invoice_id else "purchase_invoice",
            "id": inv.pk, "label": inv.invoice_number, "amount": str(alloc.amount),
        })
    return rows + note_accrual_allocation_rows(note)


def release_note_allocations(note) -> list[str]:
    """يفكّ كل توزيعات الإشعار — داخل معاملة المستدعي (إلغاء الترحيل). يُرجع وسوم ما فُكّ."""
    from logistics.models import LogisticsAccrualAllocation

    released = [f"{r['label']} ({r['amount']})" for r in note_allocation_rows(note)]
    sales_allocs = list(CreditDebitNoteAllocation.objects.filter(note=note, sales_invoice__isnull=False))
    if sales_allocs:
        _release_sales_allocations(sales_allocs)
    CreditDebitNoteAllocation.objects.filter(note=note).delete()
    LogisticsAccrualAllocation.objects.filter(note=note).delete()
    return released


def note_open_targets(note) -> list[dict]:
    """مستندات طرف الإشعار المفتوحة بعملته — ترتيب FIFO (الأقدم أولاً).

    {kind, id, label, date, remaining} — المتبقّي بعملة الإشعار. الفواتير بعملته وحدها
    (التحويل يبقى متاحاً بالتوزيع اليدوي عبر `allocate_note`)؛ والمستحقّات اللوجستية
    بالأساس تُقسم على سعر الإشعار.
    """
    rows: list[dict] = []
    if not note_settles(note):
        return rows
    if note_is_creditor(note):
        from logistics.domain.party_accruals import party_open_accruals
        from logistics.models import PurchaseInvoice
        from logistics.services import annotate_purchase_invoice_payment_summary

        for inv in annotate_purchase_invoice_payment_summary(PurchaseInvoice.objects.filter(
            tenant_id=note.tenant_id, partner_id=note.partner_id, is_posted=True, is_return=False,
            currency_id=note.currency_id,
        )):
            remaining = _money(inv.list_remaining_balance)
            if remaining > 0:
                date = inv.due_date or inv.invoice_date
                rows.append({"kind": "purchase_invoice", "id": inv.pk, "label": inv.invoice_number,
                             "date": date.isoformat() if date else None, "remaining": str(remaining)})
        rate = _rate(note)
        for acc in party_open_accruals(note.tenant_id, note.partner_id):
            rows.append({"kind": acc["kind"], "id": acc["id"], "label": acc["label"], "date": acc["date"],
                         "remaining": str(_money(Decimal(acc["remaining"]) / rate))})
    else:
        from .calc import linked_return_credit_summary

        invoices = list(SalesInvoice.objects.filter(
            tenant_id=note.tenant_id, customer_id=note.partner_id, status=SalesInvoice.STATUS_POSTED,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE, currency_id=note.currency_id,
        ))
        summaries = linked_return_credit_summary(invoices)
        for inv in invoices:
            remaining = _money(summaries[inv.pk]["collectible"])
            if remaining > 0:
                date = inv.due_date or inv.invoice_date
                rows.append({"kind": "sales_invoice", "id": inv.pk, "label": inv.invoice_number,
                             "date": date.isoformat() if date else None, "remaining": str(remaining)})
    rows.sort(key=lambda r: (r["date"] or "9999-12-31", TARGET_KINDS.index(r["kind"]), r["id"]))
    return rows


def suggest_note_fifo(note) -> list[dict]:
    """توزيع غير الموزَّع على مستندات الطرف من الأقدم — مرآة `suggest_accrual_fifo`."""
    left = note_unallocated(note)
    out = []
    for row in note_open_targets(note):
        if left <= 0:
            break
        take = min(Decimal(row["remaining"]), left)
        out.append({"kind": row["kind"], "id": row["id"], "label": row["label"], "amount": str(take)})
        left -= take
    return out


#: حقل الربط ← صنف الهدف في `allocate_note`.
_LINK_TARGET = (
    ("related_invoice", "sales_invoice"),
    ("related_purchase_invoice", "purchase_invoice"),
    ("related_clearance", "clearance"),
    ("related_shipment", "freight"),
    ("related_local_shipment", "local"),
)


def linked_document_remaining(note) -> Decimal | None:
    """متبقّي المستند المربوط بعملة الإشعار — `None` بلا ربط، وصفرٌ لمستندٍ لا يقبل
    توزيعه (غير مرحَّل، أو فاتورةٌ بعملةٍ أخرى — تُوزَّع يدوياً)."""
    for field, kind in _LINK_TARGET:
        doc = getattr(note, field) if getattr(note, f"{field}_id") else None
        if doc is None:
            continue
        if kind == "sales_invoice":
            if doc.status != SalesInvoice.STATUS_POSTED or doc.invoice_kind != SalesInvoice.INVOICE_KIND_SALE \
                    or doc.currency_id != note.currency_id:
                return ZERO
            return _sales_invoice_open(doc)
        if kind == "purchase_invoice":
            from logistics.services import purchase_invoice_payment_summary

            if not doc.is_posted or doc.is_return or doc.currency_id != note.currency_id:
                return ZERO
            return _money(purchase_invoice_payment_summary(doc)["remaining_balance"])
        from logistics.domain.party_accruals import accrual_remaining

        return _money(accrual_remaining(kind, doc) / _rate(note))
    return None


def auto_allocate_linked(note, *, user=None) -> Decimal:
    """يُوزِّع الإشعار المسوّي المرحَّل على مستنده المربوط بحدّ متبقّيه — والزائد يبقى
    «تحت الحساب». داخل معاملة الترحيل. يُرجع ما وُزِّع (صفرٌ بلا ربطٍ أو بلا متبقٍّ)."""
    if not note_settles(note):
        return ZERO
    for field, kind in _LINK_TARGET:
        doc_id = getattr(note, f"{field}_id")
        if not doc_id:
            continue
        take = min(note_unallocated(note), linked_document_remaining(note) or ZERO)
        if take <= 0:
            return ZERO
        allocate_note(note, [{"kind": kind, "id": doc_id, "amount": take}], user=user)
        logger.info("credit_debit_note.auto_allocate note=%s %s=%s amount=%s", note.id, kind, doc_id, take)
        return take
    return ZERO


__all__ = [
    "note_settles", "note_allocated", "note_unallocated", "posted_note_allocations_total",
    "posted_invoice_settled_total", "allocate_note", "deallocate_note", "note_allocation_rows",
    "release_note_allocations", "note_open_targets", "suggest_note_fifo", "auto_allocate_linked",
    "linked_document_remaining",
]
