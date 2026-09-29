"""شهادة الكفالة المطبوعة A5 (#238) — سياقٌ بقائمة بيضاء وقالبٌ لا يقرأ غيره.

`certificate_context` هو الحدّ الوحيد بين البطاقة والورقة: لا يمرّ إلى القالب
حقلٌ لم يُكتب هنا بالاسم، فسعرٌ أو مورّدٌ أو ملاحظةٌ داخلية أو رقمٌ ضريبي يُضاف
إلى البطاقة لاحقاً لا يصل الزبون بصمت. والحالات كلها تُسأل من `status_on` ومن
دوال الطبقتين — لا يُعاد اشتقاقها في القالب.
"""
import re
from datetime import date

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe

from tenants.letterhead import company_card

from .models import WarrantyCard, WarrantyCardEvent
from .verify import TEXT_EXPIRED, TEXT_VOIDED, qr_svg
from .verify import _device as device_label

LAYOUT_INVOICE = "invoice"
LAYOUT_CARD = "card"
LAYOUT_REFERRAL = "referral_slip"

#: قالبُ كل تخطيط. فرع الصيانة (#244) يُضاف هنا بقالبٍ جديد وتخطيطٍ جديد دون
#: المساس بما سواهما.
TEMPLATES = {
    LAYOUT_INVOICE: "after_sales/certificates/certificate_invoice.html",
    LAYOUT_CARD: "after_sales/certificates/certificate_card.html",
    LAYOUT_REFERRAL: "after_sales/certificates/referral_slip.html",
}

QR_MM_SINGLE = 25
QR_MM_ROW = 14

#: ترويسة الشهادة: هوية الشركة وحدها. الأرقام الضريبية (`income_tax_file_no`
#: ورقم المشتغل المرخّص `licensed_dealer_no`) لا تُطبع أبداً.
_LETTERHEAD_PRINTED = (
    "company_name_primary", "company_name_sub", "address", "po_box", "phone",
    "fax", "email", "logo_url",
)

_VOID_LABELS = dict(WarrantyCard.VOID_REASON_CHOICES)
_SHOP_DAYS_CODES = (
    WarrantyCardEvent.EXTEND_REASON_SHOP_DAYS,
    WarrantyCardEvent.EXTEND_REASON_SHOP_DAYS_REVERSED,
)


def _fmt(day: date | None) -> str:
    return day.strftime("%d/%m/%Y") if day else ""


def _months_text(months: int) -> str:
    if months <= 0:
        return ""
    if months == 1:
        return "شهر واحد"
    if months == 2:
        return "شهران"
    return f"{months} أشهر" if months <= 10 else f"{months} شهراً"


def _from_text(start: date | None, base_date: date | None) -> str:
    """«من …» فقط حين تختلف بداية الكفالة عن تاريخ الفاتورة."""
    if start is None or start == base_date:
        return ""
    return _fmt(start)


def _page_head(title: str) -> str:
    """عنوانُ رأس صفحة التتمّة يدخل نصَّ CSS — أي محرفٍ غير حرفٍ أو رقمٍ أو فاصلٍ مألوف يُسقَط."""
    return re.sub(r"[^\w\s#\-./—·()]", "", title)


def _issuer_name(user) -> str:
    if user is None or not getattr(user, "is_authenticated", False):
        return ""
    return user.get_full_name() or user.get_username()


def _dealer_block(card, today, base_date, extension_days) -> dict:
    if card.duration_months == 0 and card.end_date <= card.start_date:
        return {"kind": "none"}
    status = card.status_on(today)
    if status == WarrantyCard.STATUS_VOIDED:
        voided_on = timezone.localtime(card.voided_at).date() if card.voided_at else None
        return {
            "kind": "voided", "text": TEXT_VOIDED, "date": _fmt(voided_on),
            "reason": _VOID_LABELS.get(card.void_reason, ""),
        }
    block = {
        "kind": "dates", "to": _fmt(card.end_date),
        "months": _months_text(card.duration_months),
        "from_": _from_text(card.start_date, base_date),
        "extended_days": extension_days, "expired": False,
    }
    if status in (WarrantyCard.STATUS_EXPIRED, WarrantyCard.STATUS_ENDED):
        block["expired"] = True
        block["expired_text"] = TEXT_EXPIRED
    return block


def _manufacturer_block(card, today, base_date, refs) -> dict:
    status = card.manufacturer_status_on(today)
    if status is None or card.manufacturer_end_date is None:
        return {"kind": "none"}
    ref = refs.setdefault(card.manufacturer_warrantor_id, len(refs) + 1)
    block = {
        "kind": "dates", "to": _fmt(card.manufacturer_end_date),
        "months": _months_text(card.manufacturer_duration_months),
        "from_": _from_text(card.manufacturer_start_date, base_date),
        "ref": ref, "expired": status in (WarrantyCard.STATUS_EXPIRED, WarrantyCard.STATUS_ENDED),
    }
    if block["expired"]:
        block["expired_text"] = TEXT_EXPIRED
    return block


def _extension_days_by_card(cards) -> dict:
    """صافي أيام التمديد بسبب أيام الصيانة (`shop_days` مطروحاً منها عكسها) لكل بطاقة."""
    events = WarrantyCardEvent.objects.filter(
        tenant_id=cards[0].tenant_id,
        card_id__in=[card.pk for card in cards],
        event_type=WarrantyCardEvent.TYPE_EXTEND,
        reason_code__in=_SHOP_DAYS_CODES,
    ).values_list("card_id", "old_end_date", "new_end_date")
    net: dict = {}
    for card_id, old, new in events:
        if old is not None and new is not None:
            net[card_id] = net.get(card_id, 0) + (new - old).days
    return {card_id: days for card_id, days in net.items() if days > 0}


def _terms_groups(cards, layout) -> list:
    groups: dict = {}
    for index, card in enumerate(cards, start=1):
        lines = tuple(
            line.strip() for line in (card.terms_text or "").splitlines() if line.strip()
        )
        if lines:
            groups.setdefault(lines, []).append(index)
    result = []
    for lines, indexes in groups.items():
        applies = ""
        if layout == LAYOUT_INVOICE:
            applies = (
                f"تسري على الجهاز {indexes[0]}." if len(indexes) == 1
                else "تسري على الأجهزة " + " و".join(str(i) for i in indexes) + "."
            )
        result.append({"lines": list(lines), "applies": applies})
    return result


def _customer_key(card) -> tuple:
    """هوية الزبون: الطرف المرتبط إن وُجد، وإلا الاسم والهاتف بعد التطبيع."""
    if card.partner_id:
        return ("partner", card.partner_id)
    name = " ".join((card.customer_name or "").split()).casefold()
    phone = "".join(ch for ch in (card.customer_phone or "") if ch.isdigit())
    return ("walk_in", name, phone)


def ensure_single_customer(cards) -> None:
    """شهادةٌ واحدة لا تُصدَر لأكثر من زبون — ترويستها تحمل اسم زبونٍ واحد."""
    if len({_customer_key(card) for card in cards}) > 1:
        raise ValidationError("البطاقات لزبائن مختلفين — اطبع كل زبون على حدة.")


def certificate_context(cards, *, layout, user, today=None, mark_reprint=True) -> dict:
    """كل ما يراه القالب — القائمة البيضاء الوحيدة. `cards` بطاقاتٌ قابلةٌ للطباعة (غير منتهية).

    `mark_reprint=False` لصفحة المشاركة: فتحُ الزبون للرابط ليس «إعادة طباعة».
    """
    cards = list(cards)
    today = today or timezone.localdate()
    tenant = cards[0].tenant
    letterhead = company_card(tenant)
    company = {key: letterhead[key] for key in _LETTERHEAD_PRINTED}

    invoices = {card.sales_invoice_id for card in cards}
    invoice = cards[0].sales_invoice if len(invoices) == 1 and cards[0].sales_invoice_id else None
    base_of = {
        card.pk: (card.sales_invoice.invoice_date if card.sales_invoice_id else card.start_date)
        for card in cards
    }

    extension = _extension_days_by_card(cards)
    qr_mm = QR_MM_ROW if layout == LAYOUT_INVOICE else QR_MM_SINGLE
    refs: dict = {}
    warrantors: dict = {}
    items = []
    for index, card in enumerate(cards, start=1):
        base_date = base_of[card.pk]
        is_quantity = card.quantity > 0 and not card.serial
        manufacturer = _manufacturer_block(card, today, base_date, refs)
        if manufacturer["kind"] == "dates":
            warrantor = card.manufacturer_warrantor
            warrantors.setdefault(manufacturer["ref"], {
                "ref": manufacturer["ref"], "name": warrantor.name,
                "address": warrantor.service_center_address, "phone": warrantor.phone,
            })
        items.append({
            "index": index,
            "device": device_label(card),
            "serial": "" if is_quantity else card.serial,
            "is_quantity": is_quantity,
            "covered_quantity": card.covered_quantity if is_quantity else None,
            "original_quantity": card.quantity if is_quantity else None,
            "partly_returned": is_quantity and card.returned_quantity > 0,
            # ورقة الإحالة لا تذكر كفالة التاجر ولا سبب إلغائها (#218): الوكيل يفحص بنفسه.
            "dealer": (
                {"kind": "hidden"} if layout == LAYOUT_REFERRAL
                else _dealer_block(card, today, base_date, extension.get(card.pk))
            ),
            "manufacturer": manufacturer,
            "qr": mark_safe(qr_svg(card, qr_mm)),
        })

    reprint = mark_reprint and WarrantyCardEvent.objects.filter(
        tenant_id=cards[0].tenant_id, card_id__in=[card.pk for card in cards],
        event_type=(
            WarrantyCardEvent.TYPE_REFERRED if layout == LAYOUT_REFERRAL
            else WarrantyCardEvent.TYPE_ISSUED
        ),
    ).exists()

    first = cards[0]
    seller_label = "البائع — التوقيع وختم المحل"
    if layout == LAYOUT_REFERRAL:
        title = f"ورقة إحالة إلى الوكيل — #{first.pk}"
        doc_kind = "ورقة إحالة إلى الوكيل"
        doc_number = f"#{first.pk}"
        seller_label = "المحل"
        signer_label = "مركز الخدمة — استلام"
    elif layout == LAYOUT_INVOICE:
        title = "شهادة كفالة" + (f" — {invoice.invoice_number}" if invoice else "")
        doc_kind = "شهادة كفالة"
        doc_number = ""
        signer_label = "الزبون — استلمت الأجهزة وقرأت الشروط"
    else:
        title = f"بطاقة كفالة — #{first.pk}"
        doc_kind = "بطاقة كفالة"
        doc_number = f"#{first.pk}"
        signer_label = "الزبون — استلمت الجهاز وقرأت الشروط"

    customer_name = first.customer_name or (first.partner.name if first.partner_id else "")
    customer_phone = first.customer_phone or (first.partner.phone if first.partner_id else "")
    return {
        "layout": layout,
        "title": title,
        "page_head": _page_head(title),
        "doc_kind": doc_kind,
        "doc_number": doc_number,
        "company": company,
        "invoice_number": invoice.invoice_number if invoice else "",
        "invoice_date": (
            _fmt(invoice.invoice_date) if invoice
            else "" if layout == LAYOUT_INVOICE else _fmt(base_of[first.pk])
        ),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "items": items,
        "item": items[0],
        "warrantors": sorted(warrantors.values(), key=lambda row: row["ref"]),
        "terms_groups": [] if layout == LAYOUT_REFERRAL else _terms_groups(cards, layout),
        "reprint_date": _fmt(today) if reprint else "",
        "issuer": _issuer_name(user),
        "seller_label": seller_label,
        "customer_label": signer_label,
    }


def render_certificate(context: dict) -> str:
    return render_to_string(TEMPLATES[context["layout"]], context)
