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
    terms["nav.results"] = "النتيجة والضريبة"
    terms["nav.settings"] = "الإعدادات"
    # ISSUE #271: بيانُ موديول مكتب المحاسبة — مجموعةُ الزبائن وإعداداتُ المكتب
    # وإجراؤه الأول. مفاتيحُ مصطلحاتٍ لا شاشات، كأخواتها أعلاه.
    terms["nav.office_clients"] = "الزبائن"
    terms["nav.office_settings"] = "إعدادات المكتب"
    # #274: مجموعةُ التقويم ومفتاحُ شاشته («تسميةُ الشاشة» في `Sidebar.tsx`
    # محليّةٌ كأخواتها، والمصطلحُ هنا لمجموعة البيان).
    terms["nav.office_calendar"] = "التقويم"
    # #275: مجموعةُ «اليوم» — أوّلُ مجموعات البيان، وشاشتُها الافتتاحية لاحقاً.
    terms["nav.office_today"] = "اليوم"
    # #280/ب: مجموعةُ «جاهز للإرسال» — الشاشةُ الثانية بعد «اليوم» في البيان.
    terms["nav.office_ready_to_send"] = "جاهز للإرسال"
    # #282/أ٢/٢: مجموعةُ «المسودّات» — مسودّاتُ الأتعاب وأفعالُ اعتمادها.
    terms["nav.office_fee_drafts"] = "المسودّات"
    # #289: مجموعةُ «لوحة المكتب» — شاشةُ صاحب المكتب وحدَه.
    terms["nav.office_dashboard"] = "لوحة المكتب"
    terms["action.add_office_client"] = "أضف زبون"
    terms["empty.office_shell"] = "لا زبائن بعد — أضف أول زبون ليبدأ ملفّه."
    terms["action.document_coding"] = "ترميز مستندات"
    terms["empty.shell"] = "لا يوجد شيء هنا بعد."
    return terms


# ISSUE #291: كان هنا تجاوزان لقالبَي المكتب القديمين (`accounting_firm`:
# «فاتورة أتعاب»/«خدمة»، و`client_book`: «خدمة») — حُذف القالبان مع طبقة المكتب
# في `accountant_portal`، فلم يبقَ قالبٌ يتجاوز معجم البذرة التجارية. السِجلّ
# يبقى فارغاً هنا لأنه نقطةُ الوصل التي يقرؤها `term()`/`terms_payload()`؛
# واسمُ مستند الأتعاب في الموديول الجديد له ثابتُه المستقلّ تحت
# (`OFFICE_FEE_INVOICE_LABEL`) ولا يُربط بمفتاح `doc.sales_invoice`.
TEMPLATE_TERM_OVERRIDES: dict[str, dict[str, str]] = {}


#: #282/أ٢/١: اسمُ مستند فاتورة الأتعاب الورقية — **ثابتٌ واحدٌ هنا** (وهذا
#: الملفّ مصدرُ المعجم، ومستثنى في حارس #82 بوصفه مصدراً لا نسخة) تستورده
#: النماذجُ وسجلُّ `docshare` ووحدةُ الورقة، فلا نسخةَ حرفية في ثلاثة ملفات.
#:
#: **ولا يُربط بمفتاح `doc.sales_invoice`**: ذاك اسمُ *فاتورة البيع* في القالب
#: (وقيمتُه في قالب `accounting_firm` هي هذه الكلمة نفسها)، والاسمُ هنا اسمُ نوع
#: مستندٍ مستقلّ في وحدة مكتب المحاسبة. تصادمُ الاسمين في قالب المكتب مسألةُ
#: تسميةٍ للمالك، ولا تُحلّ في الكود.
OFFICE_FEE_INVOICE_LABEL = "فاتورة أتعاب"


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
