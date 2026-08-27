"""سندات وإشعارات — مستنداتٌ **بلا جدول بنود**.

سندُ القبض ليس فاتورةً بأصنافٍ وكمياتٍ وأسعار: هو مبلغٌ واحد، وما يقابله
قائمةُ الفواتير التي سدّدها. لذلك يُبنى بـ`show_lines=False`، وتنزل التوزيعات
**صفوفَ بيانات** (`meta_rows`) لا صفوفَ جدولٍ بأعمدةٍ لا معنى لها هنا («الوحدة»
و«الكمية» و«ض.%» فوق إيصالِ قبض ضجيجٌ يُربك من يقرؤه).

**ولماذا سندُ القبض أصلاً:** هو ما يطلبه الزبون فعلاً بعد أن يدفع — ونظيرُه
عند Zoho *payment receipt* في بوابة الزبون و*payments received* في بوابة
المورّد. الطلب لم يسمّه، وهو من أكثر ما يُسأل عنه على واتساب.

**والسند غير المرحَّل لا يُشارَك**: ورقةُ إيصالٍ بيد الزبون على دفعةٍ لم تدخل
الدفاتر بعد تُنازَع لاحقاً، ولا سبيل لسحبها من هاتفه.
"""
from docshare.documents._contract import (
    AUDIENCE_CUSTOMER,
    AUDIENCE_SUPPLIER,
    TONE_DANGER,
    TONE_OK,
    TONE_WARN,
    VALUE_DATE,
    VALUE_MONEY,
    decision_display,
    line_row,
    meta,
    money,
    payload,
    product_names,
    tax_percent,
    tone_for,
    total,
)
from sales.models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    SalesOrder,
    SupplierPayment,
)

_ORDER_TONES = {
    "draft": TONE_WARN,
    "confirmed": TONE_OK,
    "converted": TONE_OK,
    "cancelled": TONE_DANGER,
}

_DELIVERY_TONES = {
    "pending": TONE_WARN,
    "delivered": TONE_OK,
    "cancelled": TONE_DANGER,
}

_NOTE_TONES = {
    "draft": TONE_WARN,
    "posted": TONE_OK,
    "cancelled": TONE_DANGER,
}


def _posted_only(queryset):
    """السند غير المرحَّل ليس مستنداً بعد — والرابط عليه وعدٌ لا يقابله قيد."""
    return queryset.filter(is_posted=True)


# ── طلبية الزبون ────────────────────────────────────────────────────────────

_ORDER_COLUMNS = (
    "id", "tenant_id", "order_number", "order_date", "delivery_date",
    "status", "notes",
    "subtotal", "discount_amount", "tax_amount", "grand_total", "deposit_amount",
    "customer__name", "customer__street_address", "customer__city",
    "customer__phone", "customer__tax_number",
    "currency__Code", "currency__Symbol",
)


def load_sales_order(tenant_id: int, doc_id: int):
    return (
        SalesOrder.objects
        .select_related("customer", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_ORDER_COLUMNS)
        .first()
    )


def build_sales_order(order) -> dict:
    lines = []
    line_qs = (
        order.lines
        .select_related("product", "product__uom", "tax_rate")
        .only(
            "id", "order_id", "quantity", "unit_price", "line_discount",
            "line_total",
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
            unit=line.product.uom.name_ar if line.product.uom_id else "",
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_discount=line.line_discount,
            tax_percent=tax_percent(line),
            line_total=line.line_total,
        ))

    grand_total = money(order.grand_total)
    deposit = money(order.deposit_amount)
    totals = [
        total("المجموع قبل الضريبة", order.subtotal),
        total("الخصم", order.discount_amount),
        total("الضريبة", order.tax_amount),
        total("الإجمالي", grand_total, strong=True),
    ]
    # العربون يُعرض متى وُجد — والزبون الذي دفعه يريد أن يراه على ورقته.
    if deposit:
        totals += [
            total("العربون المدفوع", deposit),
            total("المتبقي عند التسليم", grand_total - deposit, strong=True),
        ]

    return payload(
        kind="sales_order",
        title="طلبية زبون",
        number=order.order_number,
        date=order.order_date,
        status_label=order.get_status_display(),
        status_tone=tone_for(_ORDER_TONES, order.status),
        party_title="طلبية إلى",
        party=order.customer,
        currency=order.currency,
        meta_rows=[
            meta("التاريخ", order.order_date, VALUE_DATE),
            meta("تاريخ التسليم", order.delivery_date, VALUE_DATE),
            meta("العملة", order.currency.Code if order.currency_id else ""),
        ],
        lines=lines,
        totals_rows=totals,
        grand_total=grand_total,
        notes=order.notes,
        decision=decision_display(DECISION_SALES_ORDER, order),
    )


# ── قرار الزبون على الطلبية ─────────────────────────────────────────────────

def _apply_sales_order_decision(order, accepted: bool) -> None:
    """تأكيدُ الزبون **يحجز الكمية**؛ ورفضُه **لا يُلغي الطلبية**.

    القبول يمرّ من `sales/services/orders.py` (`confirm_sales_order`) — نفس
    القاعدة التي يمرّ منها زرّ «تأكيد وحجز» في الشاشة: تقفل الطلبية والمنتجات،
    وتطرح حجوزات الطلبيات المؤكدة الأخرى، **وترفض التأكيد إن لم تكفِ الكمية**.
    ذلك الرفض `ValidationError` تحوّله `services.record_decision` إلى رسالةٍ
    عربية في مكانها من الصفحة (409) لا إلى خطأ خادم.

    **والحجزُ أثرٌ مقصود لا أثرٌ جانبيّ**: أن يؤكّد الزبون الطلبية معناه أن
    تُحجَز له البضاعة — وهو ما يفعله Odoo حرفياً حين يؤكّد الزبون من البوابة.
    ولا قيد محاسبياً هنا: الطلبية بلا قيد، والعربون وحده حدثٌ ماليّ.

    **ولماذا لا يُلغي الرفضُ الطلبيةَ:** `cancelled` طريقٌ بلا رجعة في هذا
    المستودع، وإلغاؤها **يُفرِج عن الكمية المحجوزة** — أثرٌ في المخزون من ضغطةٍ
    على رابطٍ بلا تحقّق هويّة. الرفض يُسجَّل باسمه وسببه، والإلغاء قرارُ صاحب
    الطلبية في شاشته وهو يرى السبب.
    """
    if accepted:
        from sales.services import confirm_sales_order

        confirm_sales_order(order)


DECISION_SALES_ORDER = {
    "title": "تأكيد الطلبية",
    "hint": "اكتب اسمك ثم اختر. التأكيد يحجز لك البضاعة، ولا يمكن تغيير القرار بعد إرساله.",
    "accept_label": "تأكيد الطلبية",
    "reject_label": "رفض الطلبية",
    "settled_accepted": "تم تأكيد الطلبية وحجز الكمية",
    "settled_rejected": "تم رفض الطلبية",
    "expired_note": "انتهت صلاحية هذه الطلبية.",
    # المسودة وحدها: المؤكَّدة محجوزةٌ أصلاً، والمحوَّلة والملغاة نهائيتان.
    "is_open": lambda doc: doc.status == SalesOrder.STATUS_DRAFT,
    "closed_reason": lambda doc: (
        f"لم تعد هذه الطلبية قابلة للقرار (حالتها: {doc.get_status_display()})."
    ),
    "apply": _apply_sales_order_decision,
    "entity_type": "sales_order",
    "entity_label": lambda doc: doc.order_number,
}


# ── سند التسليم ─────────────────────────────────────────────────────────────

_DELIVERY_COLUMNS = (
    "id", "tenant_id", "delivery_number", "delivery_date", "status",
    "notes", "customer_ref",
    "partner__name", "partner__street_address", "partner__city",
    "partner__phone", "partner__tax_number",
)


def load_delivery_order(tenant_id: int, doc_id: int):
    return (
        DeliveryOrder.objects
        .select_related("partner")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_DELIVERY_COLUMNS)
        .first()
    )


def build_delivery_order(delivery) -> dict:
    """سند التسليم **كمياتٌ بلا أسعار** — وهذا ليس إغفالاً بل تعريفُه.

    من يستلم البضاعة في المستودع ليس بالضرورة من يعرف أسعارها (سائقٌ أو
    مندوبُ زبون)، وطباعةُ الأسعار على ورقة التسليم تنشرها على من لا شأن له
    بها. نفس فصل *delivery slip* عن *invoice* في Odoo وZoho.
    """
    lines = []
    line_qs = (
        delivery.lines
        .select_related("product", "product__uom")
        .only(
            "id", "delivery_id", "quantity",
            "product__name_ar", "product__name_en", "product__uom__name_ar",
        )
        .order_by("id")
    )
    for line in line_qs:
        name_ar, name_en = product_names(line)
        lines.append(line_row(
            name=name_ar,
            name_en=name_en,
            unit=line.product.uom.name_ar if line.product.uom_id else "",
            quantity=line.quantity,
        ))

    return payload(
        kind="delivery_order",
        title="سند تسليم",
        number=delivery.delivery_number,
        date=delivery.delivery_date,
        status_label=delivery.get_status_display(),
        status_tone=tone_for(_DELIVERY_TONES, delivery.status),
        party_title="تسليم إلى",
        party=delivery.partner,
        currency=None,
        meta_rows=[
            meta("تاريخ التسليم", delivery.delivery_date, VALUE_DATE),
            meta("مرجعكم", delivery.customer_ref),
        ],
        lines=lines,
        show_line_prices=False,
        # لا إجماليات على ورقة تسليم: لا أسعار فيها أصلاً، ومجموعُ الكميات
        # عبر أصنافٍ مختلفة رقمٌ بلا معنى.
        totals_rows=[],
        notes=delivery.notes,
    )


# ── سندا القبض والصرف ───────────────────────────────────────────────────────

_PAYMENT_COLUMNS = (
    "id", "tenant_id", "payment_date", "amount", "notes", "is_posted",
    "partner__name", "partner__street_address", "partner__city",
    "partner__phone", "partner__tax_number",
    "currency__Code", "currency__Symbol",
)


def _allocation_rows(allocations) -> tuple[list, "object"]:
    """الفواتير التي سدّدها هذا السند — صفوفَ بيانات لا صفوفَ جدول.

    وتُعاد معها جملةُ الموزَّع، ليُشتقّ «على الحساب» طرحاً بدل قراءة عمودٍ
    ثانٍ قد يخالفه ([[customer-payment-on-account]]).
    """
    rows, allocated = [], money(0)
    for alloc in allocations:
        allocated += money(alloc.amount)
        rows.append(meta(
            f"سُدِّد على الفاتورة {alloc.invoice.invoice_number}",
            alloc.amount, VALUE_MONEY,
        ))
    return rows, allocated


def _build_payment(payment, *, kind, title, party_title, allocations) -> dict:
    alloc_rows, allocated = _allocation_rows(allocations)
    amount = money(payment.amount)
    on_account = amount - allocated

    totals = [total("المبلغ", amount, strong=True)]
    # «على الحساب» يُعرض متى وُجد: دفعةٌ بلا توزيع رصيدٌ لصاحبها، وإخفاؤها
    # تجعله يظنّ المبلغ ضاع.
    if on_account > 0:
        totals += [
            total("الموزَّع على الفواتير", allocated),
            total("على الحساب", on_account),
        ]

    return payload(
        kind=kind,
        title=title,
        number=f"#{payment.pk}",
        date=payment.payment_date,
        status_label="مرحّل",
        status_tone=TONE_OK,
        party_title=party_title,
        party=payment.partner,
        currency=payment.currency,
        meta_rows=[
            meta("التاريخ", payment.payment_date, VALUE_DATE),
            meta("العملة", payment.currency.Code if payment.currency_id else ""),
            *alloc_rows,
        ],
        # لا جدول بنود على سند: المبلغ واحدٌ، وما يقابله قائمةُ فواتيرَ أعلاه.
        show_lines=False,
        totals_rows=totals,
        grand_total=amount,
        notes=payment.notes,
    )


def load_customer_payment(tenant_id: int, doc_id: int):
    return (
        _posted_only(CustomerPayment.objects)
        .select_related("partner", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_PAYMENT_COLUMNS)
        .first()
    )


def build_customer_payment(payment) -> dict:
    allocations = (
        payment.allocations
        .select_related("invoice")
        .only("id", "payment_id", "amount", "invoice__invoice_number")
        .order_by("id")
    )
    return _build_payment(
        payment,
        kind="customer_payment",
        title="سند قبض",
        party_title="استلمنا من",
        allocations=allocations,
    )


def load_supplier_payment(tenant_id: int, doc_id: int):
    return (
        _posted_only(SupplierPayment.objects)
        .select_related("partner", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_PAYMENT_COLUMNS)
        .first()
    )


def build_supplier_payment(payment) -> dict:
    allocations = (
        payment.allocations
        .select_related("invoice")
        .only("id", "payment_id", "amount", "invoice__invoice_number")
        .order_by("id")
    )
    return _build_payment(
        payment,
        kind="supplier_payment",
        title="سند صرف",
        party_title="دُفع إلى",
        allocations=allocations,
    )


# ── الإشعار الدائن/المدين ───────────────────────────────────────────────────

_NOTE_COLUMNS = (
    "id", "tenant_id", "note_number", "note_date", "note_type", "amount",
    "reason", "status",
    "customer__name", "customer__street_address", "customer__city",
    "customer__phone", "customer__tax_number",
)


def load_credit_debit_note(tenant_id: int, doc_id: int):
    return (
        CreditDebitNote.objects
        .select_related("customer", "related_invoice")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_NOTE_COLUMNS, "related_invoice__invoice_number")
        .first()
    )


def build_credit_debit_note(note) -> dict:
    is_credit = note.note_type == "credit"
    return payload(
        kind="credit_debit_note",
        title="إشعار دائن" if is_credit else "إشعار مدين",
        number=note.note_number,
        date=note.note_date,
        status_label=note.get_status_display(),
        status_tone=tone_for(_NOTE_TONES, note.status),
        party_title="إلى",
        party=note.customer,
        currency=None,
        meta_rows=[
            meta("التاريخ", note.note_date, VALUE_DATE),
            meta(
                "على الفاتورة",
                note.related_invoice.invoice_number if note.related_invoice_id else "",
            ),
        ],
        show_lines=False,
        totals_rows=[total("المبلغ", note.amount, strong=True)],
        grand_total=note.amount,
        # السبب هو متن الإشعار كلّه — لا «ملاحظة» على هامشه.
        notes=note.reason,
    )


VOUCHER_DOC_TYPES = {
    "sales_order": {
        "label": "طلبية زبون",
        "loader": load_sales_order,
        "builder": build_sales_order,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": DECISION_SALES_ORDER,
    },
    "delivery_order": {
        "label": "سند تسليم",
        "loader": load_delivery_order,
        "builder": build_delivery_order,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
    },
    "customer_payment": {
        "label": "سند قبض",
        "loader": load_customer_payment,
        "builder": build_customer_payment,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
    },
    "supplier_payment": {
        "label": "سند صرف",
        "loader": load_supplier_payment,
        "builder": build_supplier_payment,
        "permission": "purchase.document.share",
        "audience": AUDIENCE_SUPPLIER,
        "decision": None,
    },
    "credit_debit_note": {
        "label": "إشعار دائن/مدين",
        "loader": load_credit_debit_note,
        "builder": build_credit_debit_note,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
    },
}
