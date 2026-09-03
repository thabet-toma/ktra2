"""ISSUE #82 — المعجم: مصدر التسمية الخادمي الوحيد.

القرار 8 (#46، مؤكَّد في خريطة #66): **لا آلية ثالثة** — المعجم يُسلَّم على
حمولة `/api/permissions/me` نفسها التي تحمل `modules` و`template`، لا نقطة
API مستقلة.

مفاتيح المعجم مصطلحاتٌ لا شاشات (`doc.*`، `line.*`) كي يخدم المصطلح كل موضعٍ
يُستعمل فيه — لا نسخة لكل شاشة. القيمة الافتراضية لكل `doc.<نوع>` تُقرأ من
`TenantBook.DOCUMENT_TYPES` (`tenants/models.py`) نفسها لا نسخة موازية —
فمفتاح نوع المستند يبقى المرجع الوحيد لاسمه العام، والمعجم يضيف فوقه فقط ما
يتبدّل بالقالب. **مفتاح نوع المستند (`sales_invoice`) لا يُمسّ أبداً مهما
تغيّر اسمه** — `sales/services/calc.py` يطابق `4102` رقماً لا اسماً.

لا يشمل هذا المعجم أوصاف سجلّ النشاط المخزَّنة (`core/activity.py`) — حقيقةٌ
تاريخية والبحث يجري على نصّها، فتغيير وزنها رجعياً حسب قالبٍ لاحقٍ يكذب على
الأرشيف.
"""


def _default_terms() -> dict[str, str]:
    from tenants.models import TenantBook

    doc_labels = dict(TenantBook.DOCUMENT_TYPES)
    terms = {f"doc.{key}": label for key, label in doc_labels.items()}
    # ISSUE #48: الافتراضي التجاري — تُستبدَل «خدمة» في قوالب المكتب أدناه.
    terms["line.item"] = "منتج"
    # ISSUE #83: تسميات بيان الشريط (`core/shell_manifest.py`) — مجموعاته
    # وإجراؤه الأول ونصّ حالته الفارغة. مفاتيح لا شاشات، كأخواتها أعلاه.
    terms["nav.home"] = "الرئيسية"
    terms["nav.clients"] = "عملائي"
    terms["nav.fees"] = "الأتعاب"
    terms["nav.treasury"] = "الخزينة والمصاريف"
    terms["nav.office_accounting"] = "محاسبة المكتب"
    terms["nav.reports"] = "التقارير"
    terms["nav.office"] = "المكتب"
    terms["nav.entry"] = "الإدخال"
    terms["nav.receipt_payment"] = "القبض والدفع"
    terms["nav.parties"] = "الأطراف"
    terms["nav.accounts"] = "الحسابات"
    terms["nav.declarations"] = "الإقرارات"
    terms["nav.settings"] = "الإعدادات"
    terms["action.document_coding"] = "ترميز مستندات"
    terms["empty.shell"] = "لا يوجد شيء هنا بعد."
    return terms


# ISSUE #48: الكلمتان محسومتان ولا تُفتحان — «فاتورة أتعاب» و«خدمة» بدل
# «منتج» في المكتب. `client_book` بلا `doc.sales_invoice`: القناع الحيّ
# (`tenants/company_templates.py`) يخفي فاتورة المبيعات عن هذا القالب أصلاً.
TEMPLATE_TERM_OVERRIDES: dict[str, dict[str, str]] = {
    "accounting_firm": {
        "doc.sales_invoice": "فاتورة أتعاب",
        "line.item": "خدمة",
        # ISSUE #83: نصّ الحالة الفارغة لبيان الشريط.
        "empty.shell": "لم تُصدر فاتورة أتعابٍ بعد — ابدأ من هنا.",
    },
    "client_book": {
        "line.item": "خدمة",
        "empty.shell": "لا مستندات مرمّزة بعد — ابدأ بترميز أول مستند.",
    },
}


def term(tenant, key: str) -> str:
    """المصطلح الفعلي لهذه الشركة — مفتاحٌ غائب يسقط للافتراضي بلا رمي."""
    template = getattr(tenant, "template", None) or "general"
    overrides = TEMPLATE_TERM_OVERRIDES.get(template, {})
    if key in overrides:
        return overrides[key]
    return _default_terms().get(key, key)


def terms_payload(tenant) -> dict[str, str]:
    """القاموس كاملاً بعد قناع القالب — يُسلَّم على حمولة `/api/permissions/me`."""
    template = getattr(tenant, "template", None) or "general"
    merged = _default_terms()
    merged.update(TEMPLATE_TERM_OVERRIDES.get(template, {}))
    return merged
