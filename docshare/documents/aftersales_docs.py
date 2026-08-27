"""بطاقة الكفالة وأمر الصيانة — جمهورهما **الزبون**، ووحدتهما **مرخَّصة**.

`after_sales` وحدةٌ مرخَّصة في `core/modules.py`، فالنوعان يحملان `module`
تفرضه `docshare/views.py` **قبل** الصلاحية. و`require_module` يردّ **404 لا
403** — قرارٌ قائم في المستودع: الوحدة غير المرخّصة تختفي كمسارٍ غير موجود بدل
أن تُعلن عن نفسها بـ«ممنوع». وترتيبُ الفحصين هو ما يجعل ذلك صادقاً: لو سبقت
الصلاحيةُ الترخيصَ لردّ السطح 403 على شركةٍ لا تملك الوحدة — وهو إقرارٌ بوجودها.

**وما لا يخرج إلى الزبون:** `supplier` و`supplier_warranty_end_date` و
`supplier_claim*` — أن القطعة ما زالت تحت كفالة مورّدنا شأنٌ بيننا وبينه،
وعرضُه للزبون يفتح تفاوضاً على من يتحمّل الكلفة لا شأن له به. و`technician`
و`billing_waived_reason` و`estimated_amount` قبل الاعتماد كذلك.
"""
from after_sales.models import ServiceOrder, WarrantyCard
from docshare.documents._contract import (
    AUDIENCE_CUSTOMER,
    TONE_DANGER,
    TONE_MUTED,
    TONE_OK,
    TONE_WARN,
    VALUE_DATE,
    VALUE_QTY,
    meta,
    payload,
    tone_for,
    total,
)

_ORDER_TONES = {
    "received": TONE_MUTED,
    "in_diagnosis": TONE_MUTED,
    "awaiting_approval": TONE_WARN,
    "in_repair": TONE_MUTED,
    "ready": TONE_OK,
    "delivered": TONE_OK,
    "cancelled": TONE_DANGER,
}


def _customer_of(record):
    """الطرف صفٌّ أو اسمٌ مكتوب — زبونُ الكاونتر قد لا يكون له بطاقة طرف.

    `after_sales` يحفظ `customer_name` و`customer_phone` نصّاً لهذه الحالة،
    وورقةٌ بلا اسمِ صاحبها لا تُسلَّم لأحد.
    """
    if record.partner_id:
        return record.partner
    return record.customer_name or None


# ── بطاقة الكفالة ───────────────────────────────────────────────────────────

def load_warranty_card(tenant_id: int, doc_id: int):
    return (
        WarrantyCard.objects
        .select_related("partner", "product")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(
            "id", "tenant_id", "device_name", "serial", "start_date",
            "end_date", "duration_months", "notes", "customer_name",
            "customer_phone",
            "partner__name", "partner__street_address", "partner__city",
            "partner__phone", "partner__tax_number",
            "product__name_ar", "product__name_en",
        )
        .first()
    )


def build_warranty_card(card) -> dict:
    from django.utils import timezone

    device = (
        card.device_name
        or (card.product.name_ar or card.product.name_en if card.product_id else "")
        or ""
    )
    active = card.end_date >= timezone.localdate()
    return payload(
        kind="warranty_card",
        title="بطاقة كفالة",
        number=f"#{card.pk}",
        date=card.start_date,
        status_label="سارية" if active else "منتهية",
        status_tone=TONE_OK if active else TONE_DANGER,
        party_title="الكفالة باسم",
        party=_customer_of(card),
        currency=None,
        meta_rows=[
            meta("الجهاز", device),
            meta("الرقم التسلسلي", card.serial),
            meta("تبدأ من", card.start_date, VALUE_DATE),
            meta("تنتهي في", card.end_date, VALUE_DATE),
            meta("المدة (شهر)", card.duration_months or "", VALUE_QTY),
            # `supplier` و`supplier_warranty_end_date` **لا يخرجان**: كفالةُ
            # مورّدنا شأنٌ بيننا وبينه لا بيننا وبين الزبون.
        ],
        show_lines=False,
        totals_rows=[],
        notes=card.notes,
        valid_until=card.end_date,
    )


# ── أمر الصيانة ─────────────────────────────────────────────────────────────

def load_service_order(tenant_id: int, doc_id: int):
    return (
        ServiceOrder.objects
        .select_related("partner", "product")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(
            "id", "tenant_id", "order_number", "order_date", "status",
            "outcome", "serial", "device_description", "received_condition",
            "accessories", "complaint", "diagnosis", "resolution",
            "estimated_amount", "approved_at", "delivered_at",
            "customer_name", "customer_phone", "notes",
            "partner__name", "partner__street_address", "partner__city",
            "partner__phone", "partner__tax_number",
            "product__name_ar", "product__name_en",
        )
        .first()
    )


def build_service_order(order) -> dict:
    device = (
        order.device_description
        or (order.product.name_ar or order.product.name_en if order.product_id else "")
        or ""
    )
    # التقدير يظهر **بعد اعتماده** وحده: رقمٌ داخليّ قبل الاعتماد يقرؤه الزبون
    # التزاماً، ثم يتغيّر بعد التشخيص فيصير خُلفاً في وعد.
    estimate = order.estimated_amount if order.approved_at else None

    return payload(
        kind="service_order",
        title="أمر صيانة",
        number=order.order_number or f"#{order.pk}",
        date=order.order_date,
        status_label=order.get_status_display(),
        status_tone=tone_for(_ORDER_TONES, order.status),
        party_title="الجهاز باسم",
        party=_customer_of(order),
        currency=None,
        meta_rows=[
            meta("التاريخ", order.order_date, VALUE_DATE),
            meta("الجهاز", device),
            meta("الرقم التسلسلي", order.serial),
            meta("الملحقات المستلمة", order.accessories),
            meta("حالة الجهاز عند الاستلام", order.received_condition),
            meta("الشكوى", order.complaint),
            meta("التشخيص", order.diagnosis),
            meta("ما تمّ", order.resolution),
            meta("النتيجة", order.get_outcome_display() if order.outcome else ""),
            meta("تاريخ التسليم", order.delivered_at, VALUE_DATE),
            # `technician` و`supplier_claim*` و`billing_waived_reason` لا تخرج.
        ],
        show_lines=False,
        totals_rows=(
            [total("التقدير المعتمد", estimate, strong=True)] if estimate else []
        ),
        grand_total=estimate or 0,
        notes=order.notes,
    )


AFTERSALES_DOC_TYPES = {
    "warranty_card": {
        "label": "بطاقة كفالة",
        "loader": load_warranty_card,
        "builder": build_warranty_card,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        #: بوابة الترخيص قبل الصلاحية — انظر رأس الملف.
        "module": "after_sales",
    },
    "service_order": {
        "label": "أمر صيانة",
        "loader": load_service_order,
        "builder": build_service_order,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        "module": "after_sales",
    },
}
