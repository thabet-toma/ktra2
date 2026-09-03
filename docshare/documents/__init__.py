"""سجلّ أنواع المستندات القابلة للمشاركة — نقطة التمدّد الوحيدة.

كل نوع يعرّف: كيف يُحمَّل من القاعدة (بأعمدة محصورة)، كيف يُحوَّل إلى حمولة
عامة (بمفاتيح محصورة)، لمن يُشارَك (`audience`)، أي صلاحية تلزم لمشاركته،
وهل يقبل قراراً من المستلم.

**حزمةٌ لا ملف** — على نمط `logistics/views/` و`core/reports/`: العقد في
`_contract.py` بلا استيراد نموذجٍ واحد، والأنواع في وحدةٍ لكل جمهور. الفائدة
ليست الحجم بل أن **حدود الجمهور صارت حدود ملف**: من يراجع «ماذا يرى المورّد؟»
يقرأ `purchase_docs.py` كاملاً في جلسة، بدل أن يتتبّع فروعاً متشابكة في ملفٍ
واحد يخدم الجمهورين.

`DOC_TYPES` تُجمَّع هنا من الوحدات، ويُرفض أي مفتاح مكرَّر عند الاستيراد:
نوعان بنفس الاسم في وحدتين يعني أن أحدهما يبتلع الآخر بصمت — وأيُّهما يبتلع
الآخر يتبع ترتيب الجمع، وهو أسوأ سلوكٍ ممكن لسطحٍ أمني.
"""
from docshare.documents._contract import (  # noqa: F401  (سطح عام مُعاد التصدير)
    AUDIENCE_CUSTOMER,
    AUDIENCE_SUPPLIER,
    AUDIENCES,
    COMPANY_FIELDS,
    DECISION_DISPLAY_KEYS,
    DECISION_LOGIC_KEYS,
    PAYLOAD_FIELDS,
    QUOTE_DISPLAY_KEYS,
    QUOTE_LOGIC_KEYS,
    TONE_DANGER,
    TONE_MUTED,
    TONE_OK,
    TONE_WARN,
    TONES,
    VALUE_DATE,
    VALUE_MONEY,
    VALUE_QTY,
    VALUE_TEXT,
    company_card,
    decision_display,
    line_row,
    meta,
    money,
    payload,
    quote_display,
    total,
)
from docshare.documents.aftersales_docs import (  # noqa: F401
    AFTERSALES_DOC_TYPES,
    build_service_order,
    build_warranty_card,
    load_service_order,
    load_warranty_card,
)
from docshare.documents.purchase_docs import (  # noqa: F401
    PURCHASE_DOC_TYPES,
    QUOTE_PURCHASE_RFQ,
    build_local_purchase_invoice,
    build_logistics_deal,
    build_purchase_invoice,
    build_purchase_order,
    build_purchase_rfq,
    build_supplier_quotation,
    load_local_purchase_invoice,
    load_logistics_deal,
    load_purchase_invoice,
    load_purchase_order,
    load_purchase_rfq,
    load_supplier_quotation,
)
from docshare.documents.voucher_docs import (  # noqa: F401
    VOUCHER_DOC_TYPES,
    build_credit_debit_note,
    build_customer_payment,
    build_delivery_order,
    build_sales_order,
    build_supplier_payment,
    load_credit_debit_note,
    load_customer_payment,
    load_delivery_order,
    load_sales_order,
    load_supplier_payment,
)
from docshare.documents.sales_docs import (  # noqa: F401
    DECISION_QUOTATION,
    SALES_DOC_TYPES,
    SHAREABLE_INVOICE_KINDS,
    build_sales_invoice,
    build_sales_quotation,
    load_sales_invoice,
    load_sales_quotation,
)

def _merge(*registries) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for registry in registries:
        clash = set(registry) & set(merged)
        if clash:
            raise RuntimeError(f"مفتاح نوعٍ مكرَّر بين وحدتين: {sorted(clash)}")
        merged.update(registry)
    return merged


DOC_TYPES: dict[str, dict] = _merge(
    SALES_DOC_TYPES, PURCHASE_DOC_TYPES, VOUCHER_DOC_TYPES, AFTERSALES_DOC_TYPES,
)
