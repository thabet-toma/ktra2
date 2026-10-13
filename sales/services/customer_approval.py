"""موافقة الزبون على فاتورة البيع والإرسالية وسند القبض — تنفيذٌ واحد للأنواع الثلاثة.

تطبيق المستودع الخارجي يجهّز المسودة ثم يوافق عليها الزبون أو يعترض من تطبيقه. كانت الموافقة
تُكتب ملاحظةً حرّة («وافق الزبون…») لا يراها أحد ولا تكشف تعديلاً جرى بعدها. هنا حالةٌ
صريحة على المستند + بصمة محتوى المال وقت القرار، فإن تغيّرت البنود/المبالغ بعد الموافقة
سقطت إلى «بانتظار» وسُجّل ذلك — الملاحظات لا تدخل البصمة فلا تُسقطها.

الترحيل يقرأ هذه الحالة في `approval_post_issue` / `assert_customer_approval_allows_post` (T3:
تحذير افتراضاً أو منع بحسب إعداد الشركة)؛ وما عدا ذلك لا أثر محاسبي ولا مخزني هنا.
المفردات والسجل مقتبسان من `docshare/services.py` (`record_decision`): قرار + اسم + ملاحظة.
"""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.models import Cheque
from core.activity import log_activity
from sales.models import (
    CustomerApprovalFields,
    CustomerPayment,
    DeliveryOrder,
    DeliveryOrderLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)

logger = logging.getLogger("sales.services")

#: ما يُضبط من الـAPI. `not_required` الافتراضي ولا يُعاد إليه.
SETTABLE_STATUSES = (
    CustomerApprovalFields.APPROVAL_PENDING,
    CustomerApprovalFields.APPROVAL_APPROVED,
    CustomerApprovalFields.APPROVAL_REJECTED,
)
BY_NAME_MAX = 150
NOTE_MAX = 500

_APPROVAL_FIELDS = (
    "customer_approval_status",
    "customer_approval_at",
    "customer_approval_by",
    "customer_approval_note",
    "customer_approval_fingerprint",
)

DROPPED_DESCRIPTION = "سقطت موافقة الزبون: عُدّل المستند بعد موافقته"


# ── البصمة ──

def _num(value) -> str:
    """رقم موحَّد: `100` و`100.00` و`1E+2` يعطون النصّ نفسه."""
    if value is None:
        return ""
    return format(Decimal(str(value)).normalize(), "f")


def _invoice_content(invoice) -> dict:
    # من القاعدة لا من ذاكرة prefetch — تكون قديمة بعد حفظ البنود.
    lines = SalesInvoiceLine.objects.filter(invoice_id=invoice.pk)
    rows = sorted(
        [
            line.product_id, _num(line.quantity), _num(line.unit_price),
            _num(line.line_discount), line.tax_rate_id, _num(line.line_tax_percent),
        ]
        for line in lines
    )
    return {
        "customer": invoice.customer_id,
        "currency": invoice.currency_id,
        "exchange_rate": _num(invoice.exchange_rate),
        "invoice_discount": _num(invoice.invoice_discount),
        "discount_percent": _num(invoice.discount_percent),
        "invoice_type": invoice.invoice_type,
        "prices_include_tax": bool(invoice.prices_include_tax),
        "source_discount_percent": _num(invoice.source_discount_percent_override),
        "source_discount_amount": _num(invoice.source_discount_amount_override),
        "lines": rows,
    }


def _delivery_content(delivery) -> dict:
    rows = sorted(
        [line.product_id, _num(line.quantity), line.warehouse_id or 0]
        for line in DeliveryOrderLine.objects.filter(delivery_id=delivery.pk)
    )
    return {"invoice": delivery.invoice_id, "partner": delivery.partner_id, "lines": rows}


def _payment_content(payment) -> dict:
    cheques = sorted(
        [c.cheque_number, _num(c.amount), c.due_date.isoformat() if c.due_date else ""]
        for c in Cheque.objects.filter(customer_payment_id=payment.pk)
    )
    return {
        "partner": payment.partner_id,
        "amount": _num(payment.amount),
        "currency": payment.currency_id,
        "exchange_rate": _num(payment.exchange_rate),
        "cash_or_bank_account": payment.cash_or_bank_account_id,
        "cheques": cheques,
    }


# ── مواصفات الأنواع الثلاثة: كل ما يختلف بينها في موضع واحد ──

def _invoice_partner_ids(invoice) -> list:
    return [invoice.customer_id]


def _delivery_partner_ids(delivery) -> list:
    if delivery.invoice_id:
        return [delivery.invoice.customer_id]
    return [delivery.partner_id] if delivery.partner_id else []


def _payment_partner_ids(payment) -> list:
    return [payment.partner_id]


_SPECS = {
    SalesInvoice: {
        "entity_type": "sales_invoice",
        "label": lambda d: d.invoice_number,
        "content": _invoice_content,
        "partner_ids": _invoice_partner_ids,
        "cancelled": SalesInvoice.STATUS_CANCELLED,
        "noun": "الفاتورة",
    },
    DeliveryOrder: {
        "entity_type": "sales_delivery_note",
        "label": lambda d: d.delivery_number or f"#{d.pk}",
        "content": _delivery_content,
        "partner_ids": _delivery_partner_ids,
        "cancelled": DeliveryOrder.STATUS_CANCELLED,
        "noun": "الإرسالية",
    },
    CustomerPayment: {
        "entity_type": "customer_payment",
        "label": lambda d: getattr(d, "payment_number", "") or f"#{d.pk}",
        "content": _payment_content,
        "partner_ids": _payment_partner_ids,
        "cancelled": None,
        "noun": "السند",
    },
}


def _spec(doc) -> dict:
    return _SPECS[type(doc)]


def approval_fingerprint(doc) -> str:
    """sha256 لمحتوى المال في المستند — الملاحظات والحالة وما يكتبه الترحيل خارجها."""
    payload = json.dumps(_spec(doc)["content"](doc), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── السجل ──

def _log(doc, *, description: str, old_status: str, by_name: str, note: str, request) -> None:
    spec = _spec(doc)
    log_activity(
        action="customer_approval",
        entity_type=spec["entity_type"],
        entity_id=doc.pk,
        entity_label=spec["label"](doc),
        description=description,
        metadata={
            "old_status": old_status,
            "new_status": doc.customer_approval_status,
            "by_name": by_name,
            "note": note,
        },
        partner_ids=spec["partner_ids"](doc),
        request=request,
    )
    logger.info(
        "customer_approval %s id=%s %s->%s user=%s",
        spec["entity_type"], doc.pk, old_status, doc.customer_approval_status,
        getattr(getattr(request, "user", None), "pk", None),
    )


def _decision_description(status: str, by_name: str, note: str) -> str:
    if status == CustomerApprovalFields.APPROVAL_PENDING:
        return "بانتظار موافقة الزبون"
    text = "وافق الزبون" if status == CustomerApprovalFields.APPROVAL_APPROVED else "اعترض الزبون"
    if by_name:
        text += f" ({by_name})"
    if note:
        text += f" — {note}"
    return text


# ── الخدمات ──

def _clean_text(value, *, label: str, max_length: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(f"{label} يجب أن يكون نصاً.")
    text = value.strip()
    if len(text) > max_length:
        raise ValidationError(f"{label} أطول من {max_length} حرفاً.")
    return text


def record_customer_approval(doc, *, status, by_name="", note="", request) -> None:
    """يسجّل قرار الزبون (بانتظار/موافقة/اعتراض) على المستند ويحفظ بصمة محتواه.

    مسموح على أيّ حالة غير الملغاة: الزبون يؤكّد استلام إرسالية بعد تسليمها، ويؤكّد دفعةً
    قبل ترحيلها أو بعده. يرفع `ValidationError` بعربية عند رفض المدخل.
    """
    spec = _spec(doc)
    if status not in SETTABLE_STATUSES:
        raise ValidationError("الحالة يجب أن تكون: pending أو approved أو rejected.")
    if spec["cancelled"] is not None and doc.status == spec["cancelled"]:
        raise ValidationError(f"لا يمكن تسجيل موافقة الزبون: {spec['noun']} ملغاة.")
    by_name = _clean_text(by_name, label="اسم الزبون", max_length=BY_NAME_MAX)
    note = _clean_text(note, label="الملاحظة", max_length=NOTE_MAX)

    old_status = doc.customer_approval_status
    decided = status != CustomerApprovalFields.APPROVAL_PENDING
    with transaction.atomic():
        doc.customer_approval_status = status
        doc.customer_approval_by = by_name
        doc.customer_approval_note = note
        doc.customer_approval_at = timezone.now() if decided else None
        doc.customer_approval_fingerprint = approval_fingerprint(doc) if decided else ""
        # `updated_at` في القائمة كي يتحرّك الـETag (T1) — وإلّا بقي توكن المستند القديم صالحاً.
        doc.save(update_fields=[*_APPROVAL_FIELDS, "updated_at"])
        _log(
            doc, description=_decision_description(status, by_name, note),
            old_status=old_status, by_name=by_name, note=note, request=request,
        )


def drop_approval_if_changed(doc, *, request) -> bool:
    """موافقةٌ تغيّر محتوى المال بعدها ⇒ «بانتظار». تُرجع `True` إن سقطت.

    من قرّر ومتى يبقيان في سجل النشاط (`metadata`) لا في الصفّ: صفٌّ «بانتظار» باسم من وافق
    على نسخةٍ ما عادت قائمة يضلّل من يقرؤه.
    """
    if doc.customer_approval_status != CustomerApprovalFields.APPROVAL_APPROVED:
        return False
    if approval_fingerprint(doc) == doc.customer_approval_fingerprint:
        return False
    old_status, by_name, note = (
        doc.customer_approval_status, doc.customer_approval_by, doc.customer_approval_note,
    )
    with transaction.atomic():
        doc.customer_approval_status = CustomerApprovalFields.APPROVAL_PENDING
        doc.customer_approval_at = None
        doc.customer_approval_by = ""
        doc.customer_approval_note = ""
        doc.customer_approval_fingerprint = ""
        doc.save(update_fields=[*_APPROVAL_FIELDS, "updated_at"])
        _log(
            doc, description=DROPPED_DESCRIPTION, old_status=old_status,
            by_name=by_name, note=note, request=request,
        )
    return True


# ── الترحيل (T3) ──

def approval_post_issue(doc) -> str | None:
    """سببٌ عربي لأن المستند يحتاج موافقة الزبون ولا يملك موافقةً سارية، وإلا `None`.

    `not_required` (كل مستندات المنصة) و«موافق ومحتواه كما وُوفق عليه» لا مشكلة فيهما. موافقةٌ
    بصمتها غير بصمة المحتوى الحالي تعني تعديلاً مرّ بمسارٍ لا يستدعي `drop_approval_if_changed`.
    """
    status = doc.customer_approval_status
    if status == CustomerApprovalFields.APPROVAL_PENDING:
        return _decision_description(status, "", "")
    if status == CustomerApprovalFields.APPROVAL_REJECTED:
        return _decision_description(status, doc.customer_approval_by, doc.customer_approval_note)
    if (
        status == CustomerApprovalFields.APPROVAL_APPROVED
        and approval_fingerprint(doc) != doc.customer_approval_fingerprint
    ):
        return "عُدّل بعد موافقة الزبون"
    return None


def current_approval_issue(doc) -> str | None:
    """`approval_post_issue` على حالةٍ طازجة من القاعدة — الكائن في يد المستدعي قد يسبق قرار الزبون."""
    if doc.pk:
        doc.refresh_from_db(fields=_APPROVAL_FIELDS)
    return approval_post_issue(doc)


def assert_customer_approval_allows_post(doc) -> None:
    """يرفع `ValidationError` عربياً إن كان المستند بلا موافقة سارية وإعداد الشركة يمنع الترحيل.

    في الخدمة لا في نقطة الترحيل: كل مسار (نقطة الترحيل، التحصيل، الترحيل التلقائي) بقاعدةٍ واحدة.
    السندات التي تنشئها الخدمات داخلياً (تسوية البيع النقدي، دفعة الطلبية…) `not_required` دائماً.
    """
    issue = current_approval_issue(doc)
    if not issue:
        return
    ss = SalesSettings.objects.filter(tenant_id=doc.tenant_id).first()
    policy = ss.customer_approval_post_policy if ss else SalesSettings.POLICY_ALLOW
    if SalesSettings.policy_blocks(policy, SalesSettings.STAGE_POST):
        raise ValidationError(
            f"{issue}. " + SalesSettings.policy_refusal(
                SalesSettings.CUSTOMER_APPROVAL_SETTING_LABEL, policy,
                SalesSettings.CUSTOMER_APPROVAL_POLICY_CHOICES,
            )
        )


def snapshot_customer_approval(doc) -> dict:
    """حقول الموافقة قبل أن يُستبدل الصفّ (الإرسالية تُعكس ثم تُنشأ من جديد عند التعديل)."""
    return {name: getattr(doc, name) for name in _APPROVAL_FIELDS}


def restore_customer_approval(doc, snapshot: dict, *, request) -> None:
    """يحمل الموافقة إلى الصفّ الجديد ثم يطبّق قاعدة الإسقاط على محتواه الجديد."""
    if snapshot["customer_approval_status"] == CustomerApprovalFields.APPROVAL_NOT_REQUIRED:
        return
    for name, value in snapshot.items():
        setattr(doc, name, value)
    doc.save(update_fields=[*_APPROVAL_FIELDS, "updated_at"])
    drop_approval_if_changed(doc, request=request)


__all__ = [
    "SETTABLE_STATUSES", "approval_fingerprint", "approval_post_issue",
    "current_approval_issue", "assert_customer_approval_allows_post",
    "record_customer_approval",
    "drop_approval_if_changed", "snapshot_customer_approval", "restore_customer_approval",
]
