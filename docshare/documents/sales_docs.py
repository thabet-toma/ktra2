"""مستندات جانب البيع — جمهورها **الزبون**.

لا تكلفةَ شراءٍ ولا هامشَ ربحٍ ولا اسمَ مورّدٍ على أيٍّ من هذه الصفحات، ولا
ملاحظةً داخلية: `SalesInvoiceLine` يحمل ملاحظتين والفصل بينهما بنيويّ في
`sales/models.py` — `internal_note` للموظف و`customer_note` تُطبع.
"""
from docshare.documents._contract import (
    AUDIENCE_CUSTOMER,
    TONE_DANGER,
    TONE_OK,
    TONE_WARN,
    VALUE_DATE,
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
from sales.models import SalesInvoice, SalesQuotation
from sales.services import posted_allocations_total

#: نبرة شارة الحالة لمستندات المبيعات — مفرداتها مشتركة بين الفاتورة والعرض.
SALES_TONES = {
    "posted": TONE_OK,
    "accepted": TONE_OK,
    "delivered": TONE_OK,
    "cancelled": TONE_DANGER,
    "rejected": TONE_DANGER,
    "draft": TONE_WARN,
}

_LINE_RELATIONS = ("product", "product__uom", "tax_rate")


# ── فاتورة البيع ────────────────────────────────────────────────────────────

#: أنواع الفواتير التي تُشارَك تحت `sales_invoice`. `SalesInvoice` يخدم أربعة
#: أنواع — ومنها **الشراء ومرجعه**. مشاركتها هنا تسرّب المورّد والتكلفة إلى
#: زبون، فالحصر إيجابي عمداً. ولجانب الشراء نوعُه الخاص بجمهوره الخاص في
#: `purchase_docs.py` — الحارس لم يُرفَع مع التوسيع، بل قُرِن بمرآته.
SHAREABLE_INVOICE_KINDS = (
    SalesInvoice.INVOICE_KIND_SALE,
    SalesInvoice.INVOICE_KIND_SALE_RETURN,
)

_INVOICE_COLUMNS = (
    "id", "tenant_id", "invoice_number", "invoice_date", "due_date",
    "status", "invoice_kind", "invoice_type", "notes",
    "subtotal_excl_tax", "invoice_discount", "tax_amount", "grand_total",
    "customer__name", "customer__street_address", "customer__city",
    "customer__phone", "customer__tax_number",
    "currency__Code", "currency__Symbol",
)

_QUOTATION_COLUMNS = (
    "id", "tenant_id", "quotation_number", "quotation_date", "valid_until",
    "status", "notes",
    "subtotal", "discount_amount", "tax_amount", "grand_total",
    "customer__name", "customer__street_address", "customer__city",
    "customer__phone", "customer__tax_number",
    "currency__Code", "currency__Symbol",
)


def load_sales_invoice(tenant_id: int, doc_id: int):
    return (
        SalesInvoice.objects
        .select_related("customer", "currency")
        .filter(
            pk=doc_id,
            tenant_id=tenant_id,
            invoice_kind__in=SHAREABLE_INVOICE_KINDS,
        )
        .only(*_INVOICE_COLUMNS)
        .first()
    )


def build_sales_invoice(invoice) -> dict:
    lines = []
    line_qs = (
        invoice.lines
        .select_related(*_LINE_RELATIONS)
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
            # `internal_note` **لا يخرج أبداً** — الفصل بنيوي في `sales.models`
            # (`SalesInvoiceLine`) والطباعة تقرأ `customer_note` وحده.
            note=line.customer_note,
            unit=line.unit or (line.product.uom.name_ar if line.product.uom_id else ""),
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_discount=line.line_discount,
            tax_percent=tax_percent(line),
            line_total=money(line.line_total_excl_tax) + money(line.line_tax_amount),
        ))

    # `amount_paid` ليس مصدر حقيقة في هذا المستودع: المصدر هو مجموع التوزيعات
    # المرحّلة. قراءته من العمود تُظهر للزبون رقماً يخالف ما في شاشة الموظف.
    paid = posted_allocations_total(invoice.pk)
    grand_total = money(invoice.grand_total)
    is_return = invoice.invoice_kind == SalesInvoice.INVOICE_KIND_SALE_RETURN

    return payload(
        kind="invoice",
        title="مرجع بيع" if is_return else "فاتورة بيع",
        number=invoice.invoice_number,
        date=invoice.invoice_date,
        status_label=invoice.get_status_display(),
        status_tone=tone_for(SALES_TONES, invoice.status),
        party_title="فاتورة إلى",
        party=invoice.customer,
        currency=invoice.currency,
        meta_rows=[
            meta("التاريخ", invoice.invoice_date, VALUE_DATE),
            meta("تاريخ الاستحقاق", invoice.due_date, VALUE_DATE),
            meta("العملة", invoice.currency.Code),
        ],
        lines=lines,
        totals_rows=[
            total("المجموع قبل الضريبة", invoice.subtotal_excl_tax),
            total("الخصم", invoice.invoice_discount),
            total("الضريبة", invoice.tax_amount),
            total("الإجمالي", grand_total, strong=True),
            total("المدفوع", paid),
            total("المتبقي", grand_total - paid, strong=True),
        ],
        grand_total=grand_total,
        notes=invoice.notes,
    )


# ── عرض السعر ───────────────────────────────────────────────────────────────

def _send_draft_quotation(quotation) -> None:
    """مشاركةُ عرضٍ ما زال مسودة **تُرسله**.

    بدون ذلك يضغط الزبون «موافق» فيسقط على آلة حالات `SalesQuotation`: القبول
    لا يجوز إلا من «أُرسل». وهذا هو معنى الإرسال نفسه في Odoo وZoho — مشاركةُ
    العرض هي إرساله — ونافذة المشاركة تُعلنه قبل الضغط.
    """
    if quotation.status == SalesQuotation.STATUS_DRAFT:
        quotation.status = SalesQuotation.STATUS_SENT
        quotation.save(update_fields=["status", "updated_at"])


def _apply_quotation_decision(quotation, accepted: bool) -> None:
    quotation.status = (
        SalesQuotation.STATUS_ACCEPTED if accepted else SalesQuotation.STATUS_REJECTED
    )
    quotation.save(update_fields=["status", "updated_at"])


#: قرار عرض السعر. `is_open` تقرأ آلة الحالات في `sales/models.py`
#: (`SalesQuotation._assert_valid_workflow_transition`): القبول لا يجوز إلا من
#: «أُرسل»، فالبابُ مفتوحٌ هناك وحده.
DECISION_QUOTATION = {
    "title": "قرارك على هذا العرض",
    "hint": "اكتب اسمك ثم اختر. يُسجَّل القرار بتاريخه ولا يمكن تغييره بعد إرساله.",
    "accept_label": "موافق على العرض",
    "reject_label": "رفض العرض",
    "settled_accepted": "تمت الموافقة على هذا العرض",
    "settled_rejected": "تم رفض هذا العرض",
    "expired_note": "انتهت صلاحية هذا العرض.",
    "is_open": lambda doc: doc.status == SalesQuotation.STATUS_SENT,
    "closed_reason": lambda doc: (
        f"لم يعد هذا العرض قابلاً للقرار (حالته: {doc.get_status_display()})."
    ),
    "apply": _apply_quotation_decision,
    "entity_type": "sales_quotation",
    "entity_label": lambda doc: doc.quotation_number,
}


def load_sales_quotation(tenant_id: int, doc_id: int):
    return (
        SalesQuotation.objects
        .select_related("customer", "currency")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_QUOTATION_COLUMNS)
        .first()
    )


def build_sales_quotation(quotation) -> dict:
    lines = []
    line_qs = (
        quotation.lines
        .select_related(*_LINE_RELATIONS)
        .only(
            "id", "quotation_id", "quantity", "unit_price", "line_discount",
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

    return payload(
        kind="quotation",
        title="عرض سعر",
        number=quotation.quotation_number,
        date=quotation.quotation_date,
        status_label=quotation.get_status_display(),
        status_tone=tone_for(SALES_TONES, quotation.status),
        party_title="مقدَّم إلى",
        party=quotation.customer,
        currency=quotation.currency,
        meta_rows=[
            meta("التاريخ", quotation.quotation_date, VALUE_DATE),
            meta("صالح حتى", quotation.valid_until, VALUE_DATE),
            meta("العملة", quotation.currency.Code),
        ],
        lines=lines,
        # عرض السعر ليس مستنداً مُحصَّلاً — «المدفوع/المتبقي» عليه كذبة، فلا
        # يُبنى صفُّهما أصلاً بدل أن يُبنى ثم يُخفى بعَلَم.
        totals_rows=[
            total("المجموع قبل الضريبة", quotation.subtotal),
            total("الخصم", quotation.discount_amount),
            total("الضريبة", quotation.tax_amount),
            total("الإجمالي", quotation.grand_total, strong=True),
        ],
        grand_total=quotation.grand_total,
        notes=quotation.notes,
        valid_until=quotation.valid_until,
        decision=decision_display(DECISION_QUOTATION, quotation),
    )


#: أنواع جانب البيع. `permission` تُقرأ فعلاً في `docshare/views.py`.
SALES_DOC_TYPES = {
    "sales_invoice": {
        "label": "فاتورة بيع",
        "loader": load_sales_invoice,
        "builder": build_sales_invoice,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
    },
    "sales_quotation": {
        "label": "عرض سعر",
        "loader": load_sales_quotation,
        "builder": build_sales_quotation,
        "permission": "sales.document.share",
        "audience": AUDIENCE_CUSTOMER,
        "decision": DECISION_QUOTATION,
        "on_share": _send_draft_quotation,
    },
}
