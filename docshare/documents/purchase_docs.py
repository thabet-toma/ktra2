"""مستندات جانب الشراء — جمهورها **المورّد**.

**لماذا يجوز نشر «سعر التكلفة» هنا وهو ممنوعٌ هناك:** الرقم على مستند الشراء
هو السعر الذي كتبه المورّد لنا، فهو يعرفه قبلنا. والحارس على جانب البيع
(`sales_docs.SHAREABLE_INVOICE_KINDS`) **لم يُرفَع** مع هذا التوسيع: مشاركةُ
سجلّ شراءٍ **كفاتورة بيع** تبقى مستحيلة، وهذه الوحدة مرآتُه لا نقضُه.

**وما لا يخرج إلى المورّد** — لأنه سرُّنا لا سرُّه:
- `fees_percentage` و`shipping_cost_estimate` و`remaining_amount` على الصفقة:
  نسبةُ ربحنا وتقديرُنا وخطّةُ سيولتنا.
- `alibaba_link` و`price_offer_id` و`original_offer_number`: من أين جئنا به،
  وبكم عرضه علينا غيرُه.
- `import_deal_remaining_rate` و`import_use_cost_lines` و`attached_cash_*`
  و`cash_or_bank_account` و`journal`: توزيعُ التكلفة المستوردة ودفاترُنا.
- `landed_*` على البنود: التكلفة النهائية بعد الشحن والتخليص.
- `received_quantity` و`warehouse` و`serials`: ما جرى للبضاعة عندنا بعد وصولها.

كلُّ ذلك محروسٌ بالبناء لا بالتعداد: البانِي يكتب ما يخرج حقلاً حقلاً،
و`payload()` تقيس المجموعة، و`tests/test_purchase_leakage.py` يزرع القيم
الحسّاسة ويبحث عنها حرفياً في الصفحة المُصيَّرة.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError

from docshare.documents._contract import (
    AUDIENCE_SUPPLIER,
    TONE_DANGER,
    TONE_MUTED,
    TONE_OK,
    TONE_WARN,
    VALUE_DATE,
    VALUE_QTY,
    VALUE_TEXT,
    decision_display,
    line_row,
    meta,
    money,
    payload,
    product_names,
    quote_display,
    tax_percent,
    tone_for,
    total,
)
from logistics.models import (
    LogisticsDeal,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseRFQ,
    SupplierQuotation,
)
from sales.models import SalesInvoice

# ── نبرات الحالة ────────────────────────────────────────────────────────────

_INVOICE_TONES = {
    "draft": TONE_WARN,
    "incomplete": TONE_WARN,
    "completed": TONE_OK,
    "fully_paid": TONE_OK,
    "deposit_paid": TONE_MUTED,
    "partially_paid": TONE_MUTED,
    "archived": TONE_MUTED,
}

_ORDER_TONES = {
    "draft": TONE_WARN,
    "confirmed": TONE_OK,
    "converted": TONE_OK,
    "cancelled": TONE_DANGER,
}

_OFFER_TONES = {
    "draft": TONE_WARN,
    "sent": TONE_MUTED,
    "pending_info": TONE_MUTED,
    "under_discussion": TONE_MUTED,
    "accepted": TONE_OK,
    "converted": TONE_OK,
    "rejected": TONE_DANGER,
    "cancelled": TONE_DANGER,
    "expired": TONE_DANGER,
}

_DEAL_TONES = {
    "Open": TONE_WARN,
    "Shipped": TONE_MUTED,
    "Cleared": TONE_MUTED,
    "Closed": TONE_OK,
    "Cancelled": TONE_DANGER,
}

#: **الحالة تُترجَم هنا لا تُقرأ من `get_status_display`.** `LogisticsDeal` و
#: `SupplierQuotation` يحملان `choices` بعناوين **إنجليزية** (`('Open','Open')`)،
#: فالصفحة العربية كانت تعرض «Open» و«Draft» على ورقةٍ تُرسَل إلى مصنع. وتصحيحُ
#: النموذج نفسه يمسّ شاشاتٍ وتقاريرَ تعتمد نصّه — فالترجمة تسكن حيث تُعرض.
_DEAL_STATUS_AR = {
    "Open": "مفتوحة",
    "Shipped": "شُحنت",
    "Cleared": "خُلِّصت",
    "Closed": "مُغلقة",
    "Cancelled": "ملغاة",
}

_OFFER_STATUS_AR = {
    "draft": "مسودة",
    "sent": "أُرسل",
    "pending_info": "بانتظار معلومات",
    "under_discussion": "قيد المناقشة",
    "accepted": "مقبول",
    "rejected": "مرفوض",
    "expired": "منتهٍ",
    "cancelled": "ملغى",
    "converted": "حُوِّل",
}


def _status_ar(mapping: dict, document) -> str:
    """العنوان العربي، وإلّا فما يقوله النموذج — لا فراغ."""
    return mapping.get(document.status) or document.get_status_display()


def _shipping_terms(doc) -> list:
    """شروط الشحن كما اتّفق عليها الطرفان — يقرؤها المورّد ليعرف ما التزم به.

    مشتركةٌ بين الصفقة وعرض المورّد وأمر الشراء لأنها **حقيقة واحدة** في
    الأصل: نسخُها ثلاث مرات كان يعني أن يُصلَح مصطلحٌ في موضعٍ ويبقى في اثنين.
    """
    return [
        meta("الشروط التجارية", getattr(doc, "incoterms", "") or ""),
        meta("طريقة الشحن", getattr(doc, "shipping_method", "") or ""),
        meta("طريقة الدفع", getattr(doc, "payment_method", "") or ""),
        meta("أيام الإنتاج", getattr(doc, "production_days", 0) or "", VALUE_QTY),
        meta("أيام التسليم", getattr(doc, "delivery_days", 0) or "", VALUE_QTY),
    ]


# ── فاتورة الشراء (الفاتورة الدولية) ────────────────────────────────────────

_PURCHASE_INVOICE_COLUMNS = (
    "id", "tenant_id", "invoice_number", "invoice_name", "invoice_date",
    "due_date", "status", "invoice_type", "is_return", "notes",
    "supplier_invoice_number",
    "subtotal", "discount_amount", "tax_amount", "shipping_cost", "grand_total",
    "partner__name", "partner__street_address", "partner__city",
    "partner__phone", "partner__tax_number",
    "currency__Code", "currency__Symbol",
)


def load_purchase_invoice(tenant_id: int, doc_id: int):
    return (
        PurchaseInvoice.objects
        .select_related("partner", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_PURCHASE_INVOICE_COLUMNS)
        .first()
    )


def build_purchase_invoice(invoice) -> dict:
    lines = []
    line_qs = (
        invoice.items
        .select_related("product", "product__uom")
        .only(
            "id", "invoice_id", "name", "name_snapshot", "catalog_number",
            "description_line", "unit", "quantity", "unit_price",
            "discount_amount", "vat_percent", "total_price", "notes",
            "product__name_ar", "product__name_en", "product__uom__name_ar",
        )
        .order_by("seq", "id")
    )
    for line in line_qs:
        name_ar, name_en = product_names(line)
        lines.append(line_row(
            name=name_ar or line.name,
            name_en=name_en,
            catalog_no=line.catalog_number,
            note=line.description_line or line.notes,
            unit=line.unit or (line.product.uom.name_ar if line.product_id and line.product.uom_id else ""),
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_discount=line.discount_amount,
            tax_percent=line.vat_percent,
            line_total=line.total_price,
        ))

    grand_total = money(invoice.grand_total)
    return payload(
        kind="purchase_invoice",
        title="مرجع شراء" if invoice.is_return else "فاتورة شراء",
        number=invoice.invoice_number,
        date=invoice.invoice_date,
        status_label=invoice.get_status_display(),
        status_tone=tone_for(_INVOICE_TONES, invoice.status),
        party_title="المورّد",
        party=invoice.partner,
        currency=invoice.currency,
        meta_rows=[
            meta("التاريخ", invoice.invoice_date, VALUE_DATE),
            meta("تاريخ الاستحقاق", invoice.due_date, VALUE_DATE),
            meta("اسم الفاتورة", invoice.invoice_name),
            # رقم الفاتورة عند المورّد — رقمُه هو، وهو ما يبحث به في دفاتره.
            meta("رقم فاتورتكم", invoice.supplier_invoice_number),
            meta("العملة", invoice.currency.Code if invoice.currency_id else ""),
        ],
        lines=lines,
        totals_rows=[
            total("المجموع", invoice.subtotal),
            total("الخصم", invoice.discount_amount),
            total("الضريبة", invoice.tax_amount),
            total("الشحن", invoice.shipping_cost),
            total("الإجمالي", grand_total, strong=True),
        ],
        grand_total=grand_total,
        notes=invoice.notes,
    )


# ── أمر الشراء ──────────────────────────────────────────────────────────────

_PURCHASE_ORDER_COLUMNS = (
    "id", "tenant_id", "order_number", "order_date", "expected_delivery_date",
    "status", "notes",
    "subtotal", "discount_amount", "tax_amount", "shipping_cost", "grand_total",
    "shipping_method", "payment_method", "delivery_days",
    "supplier__name", "supplier__street_address", "supplier__city",
    "supplier__phone", "supplier__tax_number",
    "currency__Code", "currency__Symbol",
)


def load_purchase_order(tenant_id: int, doc_id: int):
    return (
        PurchaseOrder.objects
        .select_related("supplier", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_PURCHASE_ORDER_COLUMNS)
        .first()
    )


def build_purchase_order(order) -> dict:
    lines = []
    line_qs = (
        order.lines
        .select_related("product", "product__uom")
        .only(
            "id", "order_id", "name_snapshot", "description_line",
            "quantity", "unit_price", "line_total",
            "product__name_ar", "product__name_en", "product__uom__name_ar",
        )
        .order_by("seq", "id")
    )
    for line in line_qs:
        name_ar, name_en = product_names(line)
        lines.append(line_row(
            name=name_ar,
            name_en=name_en,
            note=line.description_line,
            unit=line.product.uom.name_ar if line.product_id and line.product.uom_id else "",
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line.line_total,
        ))

    grand_total = money(order.grand_total)
    return payload(
        kind="purchase_order",
        title="أمر شراء",
        number=order.order_number,
        date=order.order_date,
        status_label=order.get_status_display(),
        status_tone=tone_for(_ORDER_TONES, order.status),
        party_title="أمر إلى",
        party=order.supplier,
        currency=order.currency,
        meta_rows=[
            meta("التاريخ", order.order_date, VALUE_DATE),
            meta("تاريخ التسليم المتوقّع", order.expected_delivery_date, VALUE_DATE),
            *_shipping_terms(order),
            meta("العملة", order.currency.Code if order.currency_id else ""),
        ],
        lines=lines,
        totals_rows=[
            total("المجموع", order.subtotal),
            total("الخصم", order.discount_amount),
            total("الضريبة", order.tax_amount),
            total("الشحن", order.shipping_cost),
            total("الإجمالي", grand_total, strong=True),
        ],
        grand_total=grand_total,
        notes=order.notes,
        decision=decision_display(DECISION_PURCHASE_ORDER, order),
    )


# ── قرار المورّد على أمر الشراء ─────────────────────────────────────────────

def _apply_purchase_order_decision(order, accepted: bool) -> None:
    """قبولُ المورّد **يؤكّد** الطلبية؛ ورفضُه **لا يُلغيها**.

    القبول يمرّ من `logistics/services.py` (`confirm_purchase_order`) — نفس
    القاعدة التي يمرّ منها زرّ «تأكيد» في الشاشة، لا نسخةٌ ثانية منها.

    **ولماذا لا يُلغي الرفضُ الطلبيةَ** رغم أن Odoo يفعل: `cancelled` في هذا
    المستودع **طريقٌ بلا رجعة** — لا مسار «إلغاء الإلغاء» في الشاشة ولا في
    الخدمات، والطلبية الملغاة لا تُحوَّل إلى فاتورة. فجعلُ ضغطةٍ واحدة من رابطٍ
    بلا تحقّق هويّة تُغلق الباب نهائياً مخاطرةٌ لا يقابلها مكسب: الرفض يُسجَّل
    باسمه وسببه وتوقيته على الرابط وفي `ActivityLog`، **والإلغاء قرارُ صاحب
    الطلبية** يتّخذه في شاشته وهو يرى السبب. (‏بوابة Odoo خلف حساب مورّدٍ
    معروف؛ وهذا رابطٌ يحمله من يحمله.)
    """
    if accepted:
        from logistics.services import confirm_purchase_order

        confirm_purchase_order(order)


DECISION_PURCHASE_ORDER = {
    "title": "قراركم على أمر الشراء",
    "hint": "اكتب اسمك ثم اختر. يُسجَّل القرار بتاريخه ولا يمكن تغييره بعد إرساله.",
    "accept_label": "قبول الطلبية",
    "reject_label": "رفض الطلبية",
    "settled_accepted": "تم قبول أمر الشراء",
    "settled_rejected": "تم رفض أمر الشراء",
    "expired_note": "انتهت صلاحية هذا الأمر.",
    # المسودة وحدها تقبل القرار — مرآةُ شرط `confirm_purchase_order`.
    "is_open": lambda doc: (
        doc.status == PurchaseOrder.STATUS_DRAFT and doc.lines.exists()
    ),
    "closed_reason": lambda doc: (
        "لا يمكن اتخاذ قرارٍ على أمر شراءٍ بلا بنود."
        if doc.status == PurchaseOrder.STATUS_DRAFT
        else f"لم يعد هذا الأمر قابلاً للقرار (حالته: {doc.get_status_display()})."
    ),
    "apply": _apply_purchase_order_decision,
    "entity_type": "purchase_order",
    "entity_label": lambda doc: doc.order_number,
}


# ── الصفقة ──────────────────────────────────────────────────────────────────

_DEAL_COLUMNS = (
    "id", "tenant_id", "ref_number", "order_date", "status", "notes",
    "pi_number", "description", "short_name", "factory_name",
    "supplier_invoice_number",
    "incoterms", "shipping_method", "payment_method",
    "production_days", "delivery_days", "total_cbm", "total_weight",
    "certificates", "warranty_duration",
    "subtotal", "discount_amount", "tax_amount", "total_amount",
    "partner__name", "partner__street_address", "partner__city",
    "partner__phone", "partner__tax_number",
    "currency__Code", "currency__Symbol",
)


def load_logistics_deal(tenant_id: int, doc_id: int):
    #: `objects` مديرُ الحذف الناعم (`core/base_models.py`) — صفقةٌ محذوفة
    #: لا تُحمَّل، فرابطُها يردّ 404 لا صفحةً لمستندٍ ألغاه صاحبه.
    return (
        LogisticsDeal.objects
        .select_related("partner", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_DEAL_COLUMNS)
        .first()
    )


def build_logistics_deal(deal) -> dict:
    lines = []
    line_qs = (
        deal.items
        .select_related("product", "product__uom")
        .only(
            "id", "deal_id", "name_snapshot", "catalog_number",
            "description_line", "unit", "quantity", "unit_price", "notes",
            "product__name_ar", "product__name_en", "product__uom__name_ar",
        )
        .order_by("seq", "id")
    )
    for line in line_qs:
        name_ar, name_en = product_names(line)
        lines.append(line_row(
            name=name_ar,
            name_en=name_en,
            catalog_no=line.catalog_number,
            note=line.description_line or line.notes,
            unit=line.unit or (line.product.uom.name_ar if line.product_id and line.product.uom_id else ""),
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=money(line.quantity) * money(line.unit_price),
        ))

    grand_total = money(deal.total_amount)
    return payload(
        kind="deal",
        title="صفقة استيراد",
        number=deal.ref_number,
        date=deal.order_date,
        status_label=_status_ar(_DEAL_STATUS_AR, deal),
        status_tone=tone_for(_DEAL_TONES, deal.status),
        party_title="المورّد",
        party=deal.partner,
        currency=deal.currency,
        meta_rows=[
            meta("التاريخ", deal.order_date, VALUE_DATE),
            meta("رقم الفاتورة المبدئية", deal.pi_number),
            meta("الوصف", deal.description or deal.short_name),
            meta("المصنع", deal.factory_name),
            meta("رقم فاتورتكم", deal.supplier_invoice_number),
            *_shipping_terms(deal),
            meta("الحجم (CBM)", deal.total_cbm or "", VALUE_QTY),
            meta("الوزن", deal.total_weight or "", VALUE_QTY),
            meta("الشهادات", deal.certificates),
            meta(
                "مدة الكفالة (شهر)",
                deal.warranty_duration or "", VALUE_QTY,
            ),
            meta("العملة", deal.currency.Code if deal.currency_id else ""),
        ],
        lines=lines,
        # لا `remaining_amount` ولا `fees_percentage` ولا `shipping_cost_estimate`:
        # المتبقّي علينا وخطّة أقساطنا ونسبةُ ربحنا ليست من شأن المورّد.
        totals_rows=[
            total("المجموع", deal.subtotal),
            total("الخصم", deal.discount_amount),
            total("الضريبة", deal.tax_amount),
            total("الإجمالي", grand_total, strong=True),
        ],
        grand_total=grand_total,
        notes=deal.notes,
    )


# ── عرض سعر المورّد ─────────────────────────────────────────────────────────

_SUPPLIER_QUOTATION_COLUMNS = (
    "id", "tenant_id", "quotation_number", "quotation_date", "valid_until",
    "status", "notes", "order_name", "order_description",
    "supplier_draft_name",
    "incoterms", "shipping_method", "payment_method",
    "production_days", "delivery_days", "total_cbm", "total_weight_kg",
    "subtotal", "discount_amount", "tax_amount", "shipping_cost_estimate",
    "grand_total",
    "supplier__name", "supplier__street_address", "supplier__city",
    "supplier__phone", "supplier__tax_number",
    "currency__Code", "currency__Symbol",
)


def load_supplier_quotation(tenant_id: int, doc_id: int):
    return (
        SupplierQuotation.objects
        .select_related("supplier", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_SUPPLIER_QUOTATION_COLUMNS)
        .first()
    )


def build_supplier_quotation(offer) -> dict:
    lines = []
    line_qs = (
        offer.lines
        .select_related("product", "product__uom")
        .only(
            "id", "quotation_id", "name_snapshot", "description_line",
            "quantity", "unit_price", "line_total",
            "product__name_ar", "product__name_en", "product__uom__name_ar",
        )
        .order_by("seq", "id")
    )
    for line in line_qs:
        name_ar, name_en = product_names(line)
        lines.append(line_row(
            name=name_ar,
            name_en=name_en,
            note=line.description_line,
            unit=line.product.uom.name_ar if line.product_id and line.product.uom_id else "",
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line.line_total,
        ))

    # مورّدٌ مبدئيّ بالاسم وحده قبل أن يتجسّد صفّاً (`task68`) — الاسم يكفي
    # لورقةٍ تُرسَل، ومستندٌ بلا طرفٍ ورقةٌ مجهولة.
    party = offer.supplier if offer.supplier_id else (offer.supplier_draft_name or None)

    return payload(
        kind="supplier_quotation",
        title="عرض سعر مورّد",
        number=offer.quotation_number,
        date=offer.quotation_date,
        status_label=_status_ar(_OFFER_STATUS_AR, offer),
        status_tone=tone_for(_OFFER_TONES, offer.status),
        party_title="من المورّد",
        party=party,
        currency=offer.currency,
        meta_rows=[
            meta("التاريخ", offer.quotation_date, VALUE_DATE),
            meta("صالح حتى", offer.valid_until, VALUE_DATE),
            meta("اسم الطلبية", offer.order_name),
            meta("الوصف", offer.order_description, VALUE_TEXT),
            *_shipping_terms(offer),
            meta("الحجم (CBM)", offer.total_cbm or "", VALUE_QTY),
            meta("الوزن (كغ)", offer.total_weight_kg or "", VALUE_QTY),
            meta("العملة", offer.currency.Code if offer.currency_id else ""),
        ],
        lines=lines,
        totals_rows=[
            total("المجموع", offer.subtotal),
            total("الخصم", offer.discount_amount),
            total("الضريبة", offer.tax_amount),
            total("تقدير الشحن", offer.shipping_cost_estimate),
            total("الإجمالي", offer.grand_total, strong=True),
        ],
        grand_total=offer.grand_total,
        notes=offer.notes,
        valid_until=offer.valid_until,
    )


# ── فاتورة الشراء المحلّية ومرجعها ──────────────────────────────────────────

#: مرآةُ `sales_docs.SHAREABLE_INVOICE_KINDS`. الحصر إيجابيّ على الجانبين:
#: نوعٌ لا يُذكر في إحدى القائمتين لا يُشارَك من أيٍّ منهما.
LOCAL_PURCHASE_KINDS = (
    SalesInvoice.INVOICE_KIND_PURCHASE,
    SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
)


def load_local_purchase_invoice(tenant_id: int, doc_id: int):
    from docshare.documents.sales_docs import _INVOICE_COLUMNS

    return (
        SalesInvoice.objects
        .select_related("customer", "currency")
        .filter(
            pk=doc_id,
            tenant_id=tenant_id,
            invoice_kind__in=LOCAL_PURCHASE_KINDS,
        )
        .only(*_INVOICE_COLUMNS)
        .first()
    )


def build_local_purchase_invoice(invoice) -> dict:
    """`SalesInvoice` بنوعِ شراء: الطرفُ في `customer` وهو **المورّد**.

    النموذج موحَّد منذ `N8-T11` والحقل احتفظ باسمه القديم، فاسمُ الحقل هنا
    يقول «زبون» ومحتواه مورّد — ولذلك تحمل الحمولة `party_*` لا `customer_*`.
    """
    lines = []
    line_qs = (
        invoice.lines
        .select_related("product", "product__uom", "tax_rate")
        .only(
            "id", "invoice_id", "quantity", "unit_price", "line_discount",
            "line_total_excl_tax", "line_tax_amount", "line_tax_percent",
            "unit", "catalog_no", "customer_note",
            "product__name_ar", "product__name_en", "product__uom__name_ar",
            "tax_rate__rate",
        )
        .order_by("id")
    )
    for line in line_qs:
        name_ar, name_en = product_names(line)
        lines.append(line_row(
            name=name_ar,
            name_en=name_en,
            catalog_no=line.catalog_no,
            # `internal_note` لا يخرج هنا أيضاً — ملاحظةُ الموظف لنفسه ليست
            # للمورّد كما ليست للزبون.
            note=line.customer_note,
            unit=line.unit or (line.product.uom.name_ar if line.product.uom_id else ""),
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_discount=line.line_discount,
            tax_percent=tax_percent(line),
            line_total=money(line.line_total_excl_tax) + money(line.line_tax_amount),
        ))

    grand_total = money(invoice.grand_total)
    is_return = invoice.invoice_kind == SalesInvoice.INVOICE_KIND_PURCHASE_RETURN
    return payload(
        kind="local_purchase_invoice",
        title="مرجع شراء" if is_return else "فاتورة شراء",
        number=invoice.invoice_number,
        date=invoice.invoice_date,
        status_label=invoice.get_status_display(),
        status_tone=tone_for(
            {"posted": TONE_OK, "cancelled": TONE_DANGER, "draft": TONE_WARN},
            invoice.status,
        ),
        party_title="المورّد",
        party=invoice.customer,
        currency=invoice.currency,
        meta_rows=[
            meta("التاريخ", invoice.invoice_date, VALUE_DATE),
            meta("تاريخ الاستحقاق", invoice.due_date, VALUE_DATE),
            meta("العملة", invoice.currency.Code),
        ],
        lines=lines,
        # لا «مدفوع/متبقٍ»: ما دفعناه للمورّد يشمل دفعاتٍ على مستنداتٍ أخرى،
        # ورقمٌ جزئيّ على ورقةٍ واحدة يقرؤه المورّد كشفَ حساب فيُنازع عليه.
        totals_rows=[
            total("المجموع قبل الضريبة", invoice.subtotal_excl_tax),
            total("الخصم", invoice.invoice_discount),
            total("الضريبة", invoice.tax_amount),
            total("الإجمالي", grand_total, strong=True),
        ],
        grand_total=grand_total,
        notes=invoice.notes,
    )


# ── طلب عرض سعر (RFQ) — رابط المورّد الخاص (ISSUE #115) ────────────────────
#
# **مسارٌ يكتب لا يقبل قراراً فقط**: المورّد يرى بنوده وكمياته ووحداتِه
# ومواصفاتِه، ويكتب سعراً أمام كل بند — لا `estimated_price` ولا «أقل سعر»
# يخرجان إليه إطلاقاً (مواصفة #108 §٥). سطر الجدول هنا **ليس** `line_row()`
# العام: ذاك يحمل `unit_price`/`line_discount`/`tax_percent`/`line_total`
# وكلّها لا معنى لها على طلبيةٍ بلا سعر — فمجموعة مفاتيحه قائمة سماحٍ ثانية
# (`RFQ_LINE_WHITELIST` في `tests/test_public_leakage.py`)، مطابقةً حرفياً
# لِـ`SUPPLIER_ALLOWED_KEYS` في `frontend_v2/utils/procurementColumns.ts`:
# تسلسل · الصنف · المواصفات · الكمية · وحدة القياس — لا أكثر.

_RFQ_COLUMNS = (
    "id", "tenant_id", "rfq_number", "rfq_date", "status", "scope", "notes",
    "reply_deadline",
)


def load_purchase_rfq(tenant_id: int, doc_id: int):
    return (
        PurchaseRFQ.objects
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_RFQ_COLUMNS)
        .first()
    )


def build_purchase_rfq(rfq) -> dict:
    lines = []
    line_qs = (
        rfq.lines
        .select_related("product")
        .only(
            "id", "rfq_id", "seq", "name_snapshot", "specs", "quantity",
            "unit_of_measure", "product__name_ar", "product__name_en",
            # `estimated_price` **لا** يُذكر هنا: العمود لا يُحمَّل من القاعدة
            # أصلاً، فلا تسريب ممكن حتى بخطأ عرضٍ لاحق —
            # `tests/test_purchase_leakage.py` يقيس ذلك بـ`get_deferred_fields`.
        )
        .order_by("seq", "id")
    )
    for line in line_qs:
        name_ar, _name_en = product_names(line)
        lines.append({
            "id": line.id,
            "seq": line.seq,
            "name": name_ar,
            "specs": line.specs or "",
            "quantity": money(line.quantity),
            "unit": line.unit_of_measure or "",
        })

    # لا طرفَ واحداً على المستند نفسه: الطلبية تخرج لعدّة موردين، وكلٌّ منهم
    # يفتحها من رابطه الخاص (`PurchaseRFQRecipient.share`) — الشركةُ لا المورّد
    # هي «الطرف» الذي يُخاطَب، فبطاقة الطرف فارغة عمداً.
    return payload(
        kind="purchase_rfq",
        title="طلب عرض سعر",
        number=rfq.rfq_number or "",
        date=rfq.rfq_date,
        status_label=rfq.get_status_display(),
        status_tone={
            PurchaseRFQ.STATUS_DRAFT: TONE_WARN,
            PurchaseRFQ.STATUS_SENT: TONE_MUTED,
            PurchaseRFQ.STATUS_AWARDED: TONE_OK,
            PurchaseRFQ.STATUS_CANCELLED: TONE_DANGER,
        }.get(rfq.status, TONE_MUTED),
        party_title="",
        party=None,
        currency=None,
        meta_rows=[
            meta("التاريخ", rfq.rfq_date, VALUE_DATE),
            meta("آخر موعد للردّ", rfq.reply_deadline, VALUE_DATE),
        ],
        lines=lines,
        # والجدولُ العامّ يُطفأ: جدولُ التسعير أدناه يمرّ على `doc.lines` نفسِها،
        # فتركُ الاثنين يجعل المورّدَ يرى كلّ صنفٍ **مرّتين**. القالبُ كان يفترض
        # هذا الإطفاء ويقوله في تعليقه، والباني لم يكن يمرّره.
        show_lines=False,
        # لا جدول أسعار عام على هذه الصفحة — سعرُ كل مورّدٍ خانةٌ فارغة يملؤها
        # هو في كتلة التسعير أدناه، لا عموداً ثابتاً في الجدول.
        show_line_prices=False,
        totals_rows=[],
        grand_total=Decimal(0),
        notes=rfq.notes,
        quote=quote_display(QUOTE_PURCHASE_RFQ, rfq),
    )


def _rfq_quote_is_open(rfq) -> bool:
    """مفتوحةٌ للتسعير ما دامت «مُرسَلة» — البابُ يقفل بالترسية أو الإلغاء."""
    return rfq.status == PurchaseRFQ.STATUS_SENT


def _rfq_quote_closed_reason(rfq) -> str:
    if rfq.status == PurchaseRFQ.STATUS_AWARDED:
        return "أُرسيت هذه الطلبية على مورّدٍ آخر ولم تعد تقبل أسعاراً."
    if rfq.status == PurchaseRFQ.STATUS_CANCELLED:
        return "أُلغيت هذه الطلبية."
    return "لم تعد هذه الطلبية تقبل الأسعار."


def _apply_purchase_rfq_quote(rfq, *, name, prices, request, share, ip):
    """يربط الأسعار بمستقبِل هذا الرابط تحديداً — لا بالطلبية عموماً.

    الاتجاه **`PurchaseRFQRecipient.share → DocumentShare`** لا العكس: هذه
    الدالّة وحدها (لا `docshare/services.py` العامّة) تعرف بوجود `PurchaseRFQ`
    و`PurchaseRFQRecipient` — نفس نمط `_apply_purchase_order_decision` أعلاه
    التي تستدعي `logistics.services.confirm_purchase_order`.
    """
    from logistics.models import PurchaseRFQRecipient
    from logistics.services import submit_rfq_supplier_quote

    recipient = (
        PurchaseRFQRecipient.objects
        .select_related("supplier")
        .filter(share_id=share.pk, rfq_id=rfq.pk)
        .first()
    )
    if recipient is None:
        raise ValidationError("هذا الرابط غير مربوطٍ بمورّدٍ على هذه الطلبية.")
    submit_rfq_supplier_quote(recipient, name=name, prices=prices, ip=ip)


def _rfq_quote_prefill(rfq, share) -> dict:
    """أسعارُ **هذا المورّد وحده** كما أرسلها آخر مرّة — لتعبئة خاناته حين يعود.

    بلا هذا يجد المورّدُ خاناتٍ فارغةً كلَّها فيضطرّ أن يعيد كتابة كلّ سعرٍ كي
    يصحّح واحداً — و«يمكنكم التعديل» تصير وعداً لا يُوفى عملياً.

    وهي **دالّةُ عرضٍ لا بناء**: لا تدخل `build_purchase_rfq` ولا حمولتَه
    المدقَّقة بالقائمة البيضاء. تُستدعى في طبقة العرض حيث الرابطُ معروف، فما
    يظهر هو سعرُ صاحب الرابط نفسِه — لا سعرُ منافسه، ولا رقمٌ من دفترنا.
    """
    from logistics.models import PurchaseRFQRecipient

    recipient = (
        PurchaseRFQRecipient.objects
        .filter(share_id=share.pk, rfq_id=rfq.pk)
        .select_related("quotation")
        .first()
    )
    if recipient is None or recipient.quotation_id is None:
        return {}
    by_seq = {
        line.seq: line.unit_price
        for line in recipient.quotation.lines.only("id", "quotation_id", "seq", "unit_price")
    }
    return {
        line.id: by_seq[line.seq]
        for line in rfq.lines.only("id", "rfq_id", "seq")
        if line.seq in by_seq
    }


QUOTE_PURCHASE_RFQ = {
    "title": "أسعاركم على هذه الطلبية",
    "hint": (
        "اكتبوا السعر أمام كل بند، ثم اسمكم، وأكّدوا. يمكنكم تعديل الأسعار "
        "بإرسال النموذج مجدداً ما دامت الطلبية مفتوحة."
    ),
    "price_label": "السعر",
    "confirm_label": "إرسال الأسعار",
    "submitted_note": "أُرسلت أسعاركم. يمكنكم تعديلها ما دامت الطلبية مفتوحة.",
    "closed_note": "لم يعد بالإمكان إرسال الأسعار أو تعديلها.",
    "is_open": _rfq_quote_is_open,
    "closed_reason": _rfq_quote_closed_reason,
    "apply": _apply_purchase_rfq_quote,
    # مفتاحٌ **اختياريّ** (ليس في `QUOTE_LOGIC_KEYS`) — نوعٌ لا يعرضه لا يُخفق.
    "prefill": _rfq_quote_prefill,
    "entity_type": "purchase_rfq",
    "entity_label": lambda doc: doc.rfq_number or f"RFQ-draft-{doc.pk}",
}


PURCHASE_DOC_TYPES = {
    "purchase_invoice": {
        "label": "فاتورة شراء",
        "loader": load_purchase_invoice,
        "builder": build_purchase_invoice,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": None,
    },
    "purchase_order": {
        "label": "أمر شراء",
        "loader": load_purchase_order,
        "builder": build_purchase_order,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": DECISION_PURCHASE_ORDER,
    },
    "logistics_deal": {
        "label": "صفقة استيراد",
        "loader": load_logistics_deal,
        "builder": build_logistics_deal,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": None,
    },
    "supplier_quotation": {
        "label": "عرض سعر مورّد",
        "loader": load_supplier_quotation,
        "builder": build_supplier_quotation,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": None,
    },
    "local_purchase_invoice": {
        "label": "فاتورة شراء محلّية",
        "loader": load_local_purchase_invoice,
        "builder": build_local_purchase_invoice,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": None,
    },
    "purchase_rfq": {
        "label": "طلب عرض سعر",
        "loader": load_purchase_rfq,
        "builder": build_purchase_rfq,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": None,
        "quote": QUOTE_PURCHASE_RFQ,
    },
}
