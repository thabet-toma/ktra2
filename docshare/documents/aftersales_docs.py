"""بطاقة الكفالة وأمر الصيانة — جمهورهما **الزبون**، ووحدتهما **مرخَّصة**.

`after_sales` وحدةٌ مرخَّصة في `core/modules.py`، فالنوعان يحملان `module`
تفرضه `docshare/views.py` **قبل** الصلاحية. و`require_module` يردّ **404 لا
403** — قرارٌ قائم في المستودع: الوحدة غير المرخّصة تختفي كمسارٍ غير موجود بدل
أن تُعلن عن نفسها بـ«ممنوع». وترتيبُ الفحصين هو ما يجعل ذلك صادقاً: لو سبقت
الصلاحيةُ الترخيصَ لردّ السطح 403 على شركةٍ لا تملك الوحدة — وهو إقرارٌ بوجودها.

**وما لا يخرج إلى الزبون:** `supplier` و`supplier_warranty_end_date` و
`supplier_claim*` — أن القطعة ما زالت تحت كفالة مورّدنا شأنٌ بيننا وبينه،
وعرضُه للزبون يفتح تفاوضاً على من يتحمّل الكلفة لا شأن له به. و`technician`
و`billing_waived_reason` و`estimated_amount` قبل الاعتماد كذلك. و**ملاحظاتُ
بطاقة الكفالة** (#222 بند ٦): `WarrantyCardViewSet.extend` يُلحق بها سجلَّ
التمديد بسببه الحرّ الذي يكتبه الموظف لنفسه، فنشرُه على الرابط العام إرسالٌ
لمذكّرةٍ داخلية إلى صاحب الشأن.

**وحالةُ البطاقة من `WarrantyCard.status_on` لا من مقارنة تاريخ** (#222 بند ٧):
بطاقةُ جهازٍ أُرجع تبقى نهايتُها في المستقبل، فـ`end_date >= today` وحدها كانت
تختمها «سارية» بالأخضر على شهادةٍ لم تعد لصاحبها. وسببُ الانتهاء **لا يخرج**:
الحالة وحدها، كما في قرار رابط التحقّق.
"""
from after_sales.certificates import (
    LAYOUT_INVOICE,
    certificate_context,
    render_certificate,
    single_card_layout,
)
from after_sales.models import ServiceOrder, WarrantyCard
from after_sales.services import ISSUE_CHANNEL_SHARE, mark_card_issued
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
from sales.models import SalesInvoice

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
            "end_date", "duration_months", "customer_name",
            "customer_phone", "ended_on", "end_reason", "voided_at",
            "partner__name", "partner__street_address", "partner__city",
            "partner__phone", "partner__tax_number",
            "product__name_ar", "product__name_en",
        )
        .first()
    )


def warranty_card_expired(card) -> bool:
    """«غير سارية» للصفحة العامة — الواقعة والتاريخ معاً في جوابٍ واحد.

    يقرؤها `docshare/views.py` (`_page_context`) بدل مقارنة `valid_until`
    باليوم: مدّةُ البطاقة ليست وحدها ما يجعلها سارية منذ #222.
    """
    return card.status_on() != WarrantyCard.STATUS_ACTIVE


def build_warranty_card(card) -> dict:
    device = (
        card.device_name
        or (card.product.name_ar or card.product.name_en if card.product_id else "")
        or ""
    )
    active = not warranty_card_expired(card)
    return payload(
        kind="warranty_card",
        title="بطاقة كفالة",
        number=f"#{card.pk}",
        date=card.start_date,
        # سببُ الانتهاء لا يُنشر — «سارية» أو «منتهية» وحدهما.
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
        # `card.notes` **لا يخرج** — انظر رأس الملف (#222 بند ٦).
        notes="",
        valid_until=card.end_date,
    )


def page_warranty_card(document, share):
    """صفحة المشاركة = بطاقة الشهادة المطبوعة نفسها (#238) لا القالب العام.

    المنتهية (`ended_on`) لا تُطبع فلا تُصيَّر شهادةً هنا أيضاً: يعيد `None`
    فتسقط الصفحة إلى القالب العام الذي يختمها «منتهي الصلاحية».
    """
    card = (
        WarrantyCard.objects
        .select_related(
            "tenant", "partner", "product", "sales_invoice", "manufacturer_warrantor",
            "origin_service_order",
        )
        .filter(pk=document.pk, tenant_id=document.tenant_id, ended_on__isnull=True)
        .first()
    )
    if card is None:
        return None
    context = certificate_context(
        [card], layout=single_card_layout(card), user=share.created_by, mark_reprint=False,
    )
    return render_certificate(context)


# ── شهادة الفاتورة ──────────────────────────────────────────────────────────

def _printable_invoice_cards(tenant_id: int, invoice_id: int):
    """بطاقات الفاتورة القابلة للطباعة — نفس تصفية `POST warranties/print/`."""
    return WarrantyCard.objects.filter(
        tenant_id=tenant_id, sales_invoice_id=invoice_id, ended_on__isnull=True,
    )


def load_warranty_certificate(tenant_id: int, doc_id: int):
    """فاتورة البيع التي عليها بطاقةٌ غير منتهية واحدة على الأقل، وإلا `None`.

    فاتورةٌ بلا شهادةٍ تُطبع لا تُشارَك: رابطٌ يفتح صفحةً فارغة.
    """
    if not _printable_invoice_cards(tenant_id, doc_id).exists():
        return None
    return (
        SalesInvoice.objects
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only("id", "tenant_id", "invoice_number", "invoice_date")
        .first()
    )


def build_warranty_certificate(invoice) -> dict:
    # الصفحة تُصيَّر من `page_warranty_certificate` لا من القالب العام، فهذه
    # الحمولة تحرس القائمة البيضاء وحدها ولا تحمل غير رقم الفاتورة وتاريخها.
    return payload(
        kind="warranty_certificate",
        title="شهادة كفالة",
        number=invoice.invoice_number,
        date=invoice.invoice_date,
        status_label="",
        status_tone=TONE_MUTED,
        party_title="",
        party=None,
        currency=None,
        show_lines=False,
    )


def page_warranty_certificate(document, share):
    cards = list(
        _printable_invoice_cards(document.tenant_id, document.pk)
        .select_related(
            "tenant", "partner", "product", "sales_invoice", "manufacturer_warrantor",
        )
        .order_by("pk")
    )
    if not cards:
        return None
    context = certificate_context(
        cards, layout=LAYOUT_INVOICE, user=share.created_by, mark_reprint=False,
    )
    return render_certificate(context)


def issue_on_share(invoice, user=None) -> None:
    """إنشاء الرابط = إصدار الشهادة: `issued` بقناة المشاركة لكل بطاقة، مرةً واحدة.

    `mark_card_issued` يتجاهل ما صدر من قبل (طباعةً كان أو مشاركةً سابقة).
    """
    for card in _printable_invoice_cards(invoice.tenant_id, invoice.pk).order_by("pk"):
        mark_card_issued(card, ISSUE_CHANNEL_SHARE, user=user)


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
        #: مفتاحٌ اختياريّ: النوع يقرّر متى تنتهي صلاحيته بدل مقارنة تاريخٍ
        #: عامّة لا تعرف واقعة الانتهاء (#222 بند ٧).
        "expired": warranty_card_expired,
        #: مفتاحٌ اختياريّ: النوع يُصيِّر صفحته بنفسه بدل القالب العام (#239).
        "page": page_warranty_card,
    },
    "warranty_certificate": {
        "label": "شهادة كفالة",
        "loader": load_warranty_certificate,
        "builder": build_warranty_certificate,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        "module": "after_sales",
        "page": page_warranty_certificate,
        #: مفتاحٌ اختياريّ: يُستدعى عند إنشاء رابطٍ جديد (`create_share`).
        "on_share": issue_on_share,
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
