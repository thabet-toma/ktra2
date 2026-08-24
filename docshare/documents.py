"""سجلّ أنواع المستندات القابلة للمشاركة — نقطة التمدّد الوحيدة.

كل نوع يعرّف ثلاثة أشياء: كيف يُحمَّل من القاعدة (بأعمدة محصورة)، كيف يُحوَّل
إلى حمولة عامة (بمفاتيح محصورة)، وأي صلاحية تلزم لمشاركته. إضافة نوع رابع
سطرٌ في `DOC_TYPES` ودالتان — بلا هجرة وبلا لمس الـviews.

**القائمة البيضاء إيجابية لا سلبية.** «كل شيء عدا التكلفة» كان سينشر أي حقل
يُضاف مستقبلاً إلى `SalesInvoice` — وقد أُضيف إليها فعلاً `attached_cash_amount`
و`source_discount_amount_override` و`vat_statement`، ولا واحد منها للزبون.
لذلك تُبنى الحمولة حقلاً حقلاً، ويحرس ذلك `docshare/tests/test_public_leakage.py`
بمساواة **مجموعة** المفاتيح لا بغياب فردي.

**ولماذا بانٍ صريح لا `serializers.Serializer`:** هذا السطح يُصيَّر HTML لا JSON
(زاحف واتساب لا ينفّذ JavaScript فالصفحة خادمية بالكامل)، فلا مدخلات تُتحقَّق
ولا تمثيل يُتفاوض عليه — والسيريالايزر هنا طبقةٌ بلا عمل. الضمانة نفسها:
مفتاحٌ لا يُكتب هنا لا يخرج، والاختبار يقيس المجموعة.
"""
from decimal import Decimal

from sales.models import SalesInvoice, SalesQuotation
from sales.services import posted_allocations_total

#: أنواع الفواتير التي يجوز أن تُشارَك. `SalesInvoice` يخدم أربعة أنواع —
#: ومنها **فاتورة الشراء ومرجعها**. مشاركة سجلّ شراء تسرّب اسم المورّد وسعر
#: التكلفة إلى زبون. الحصر إيجابي عمداً لهذا السبب بالذات.
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

_LINE_RELATIONS = ("product", "product__uom", "tax_rate")


def _money(value) -> Decimal:
    return Decimal(value or 0)


def _party(doc) -> dict:
    """بطاقة الطرف كما تُطبع على الورقة — لا رصيده ولا سقفه الائتماني."""
    customer = doc.customer
    address = " — ".join(
        part for part in (customer.street_address, customer.city) if part
    )
    return {
        "customer_name": customer.name,
        "customer_address": address,
        "customer_phone": customer.phone or "",
        "customer_tax_number": customer.tax_number or "",
    }


def _currency(doc) -> dict:
    currency = doc.currency
    return {
        "currency_code": currency.Code,
        "currency_symbol": currency.Symbol or currency.Code,
    }


def _tax_percent(line) -> Decimal:
    """نسبة الضريبة المعروضة — تجاوز السطر مقدَّم على نسبة الضريبة المرتبطة."""
    override = getattr(line, "line_tax_percent", None)
    if override is not None:
        return Decimal(override)
    return Decimal(line.tax_rate.rate) if line.tax_rate_id else Decimal(0)


def _product_names(line) -> tuple[str, str]:
    product = line.product
    return (product.name_ar or product.name_en or ""), (product.name_en or "")


# ── فاتورة البيع ────────────────────────────────────────────────────────────

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
        name_ar, name_en = _product_names(line)
        lines.append({
            "name": name_ar,
            "name_en": name_en,
            "catalog_no": line.catalog_no or "",
            # `internal_note` **لا يخرج أبداً** — الفصل بنيوي في `sales.models`
            # (`SalesInvoiceLine`) والطباعة تقرأ `customer_note` وحده.
            "note": line.customer_note or "",
            "unit": line.unit or (line.product.uom.name_ar if line.product.uom_id else ""),
            "quantity": _money(line.quantity),
            "unit_price": _money(line.unit_price),
            "line_discount": _money(line.line_discount),
            "tax_percent": _tax_percent(line),
            "line_total": _money(line.line_total_excl_tax) + _money(line.line_tax_amount),
        })

    # `amount_paid` ليس مصدر حقيقة في هذا المستودع: المصدر هو مجموع التوزيعات
    # المرحّلة. قراءته من العمود تُظهر للزبون رقماً يخالف ما في شاشة الموظف.
    paid = posted_allocations_total(invoice.pk)
    grand_total = _money(invoice.grand_total)

    payload = {
        "kind": "invoice",
        "title": (
            "فاتورة بيع"
            if invoice.invoice_kind == SalesInvoice.INVOICE_KIND_SALE
            else "مرجع بيع"
        ),
        "number": invoice.invoice_number,
        "date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "valid_until": None,
        "status": invoice.status,
        "status_label": invoice.get_status_display(),
        "notes": invoice.notes or "",
        "lines": lines,
        "totals": {
            "subtotal": _money(invoice.subtotal_excl_tax),
            "discount": _money(invoice.invoice_discount),
            "tax": _money(invoice.tax_amount),
            "grand_total": grand_total,
            "paid": paid,
            "remaining": grand_total - paid,
        },
        "show_payment": True,
        "can_decide": False,
    }
    payload.update(_party(invoice))
    payload.update(_currency(invoice))
    return payload


# ── عرض السعر ───────────────────────────────────────────────────────────────

#: الحالات التي يبقى فيها القرار مفتوحاً. ما عداها يُعرض للقراءة بشارة حالته.
QUOTATION_DECIDABLE_STATUSES = (SalesQuotation.STATUS_SENT,)


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
        name_ar, name_en = _product_names(line)
        lines.append({
            "name": name_ar,
            "name_en": name_en,
            "catalog_no": "",
            "note": "",
            "unit": line.product.uom.name_ar if line.product.uom_id else "",
            "quantity": _money(line.quantity),
            "unit_price": _money(line.unit_price),
            "line_discount": _money(line.line_discount),
            "tax_percent": _tax_percent(line),
            "line_total": _money(line.line_total),
        })

    payload = {
        "kind": "quotation",
        "title": "عرض سعر",
        "number": quotation.quotation_number,
        "date": quotation.quotation_date,
        "due_date": None,
        "valid_until": quotation.valid_until,
        "status": quotation.status,
        "status_label": quotation.get_status_display(),
        "notes": quotation.notes or "",
        "lines": lines,
        "totals": {
            "subtotal": _money(quotation.subtotal),
            "discount": _money(quotation.discount_amount),
            "tax": _money(quotation.tax_amount),
            "grand_total": _money(quotation.grand_total),
            "paid": Decimal(0),
            "remaining": Decimal(0),
        },
        # عرض السعر ليس مستنداً مُحصَّلاً — «المدفوع/المتبقي» عليه كذبة.
        "show_payment": False,
        "can_decide": quotation.status in QUOTATION_DECIDABLE_STATUSES,
    }
    payload.update(_party(quotation))
    payload.update(_currency(quotation))
    return payload


# ── بطاقة الشركة ────────────────────────────────────────────────────────────

#: هوية الشركة كما تُطبع في ترويسة المستند — لا إعداداتها ولا فترتها المالية
#: ولا نسبها الافتراضية. هذه أيضاً قائمة بيضاء يقيسها اختبار التسريب.
COMPANY_FIELDS = (
    "company_name_primary", "company_name_sub", "address", "po_box",
    "phone", "fax", "email", "logo_url",
    "licensed_dealer_no", "income_tax_file_no",
)


def company_card(tenant) -> dict:
    """ترويسة المستند. شركة بلا صفّ إعدادات تُعرض باسمها المسجَّل لا فارغة."""
    tenant_settings = getattr(tenant, "settings", None)
    if tenant_settings is None:
        return {field: "" for field in COMPANY_FIELDS} | {
            "company_name_primary": tenant.CompanyName or "",
        }
    card = {
        field: (getattr(tenant_settings, field, None) or "")
        for field in COMPANY_FIELDS
    }
    if not card["company_name_primary"]:
        card["company_name_primary"] = tenant.CompanyName or ""
    return card


#: `doc_type` ← كيف يُحمَّل، كيف يُبنى، وأي صلاحية تلزم لمشاركته.
DOC_TYPES = {
    "sales_invoice": {
        "label": "فاتورة بيع",
        "loader": load_sales_invoice,
        "builder": build_sales_invoice,
        "permission": "sales.document.share",
    },
    "sales_quotation": {
        "label": "عرض سعر",
        "loader": load_sales_quotation,
        "builder": build_sales_quotation,
        "permission": "sales.document.share",
    },
}
