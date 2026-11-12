# #282fix/٤ — ينقل ترقيم فواتير الأتعاب من عدّاد الموديول (`FeeInvoiceSequence`)
# إلى دفاتر الترقيم القائمة (`TenantBook.get_next_number`)، فلا رقمَ يُفقد في
# الإنتاج: كلُّ `last_number` سابقٍ يصير بدايةَ الدفتر الذي يقرؤه الكودُ الجديد.
#
# **والعدّادُ القديم يبقى في مكانه**: حذفُه هجرةٌ حاذفة، والتذكرةُ تمنعه؛ فالهجرةُ
# تقرؤه ولا تحذفه، والكودُ لا يستعمله بعد اليوم.
#
# **والحدُّ الأقصى لا الأخير**: صفوفُ العدّاد لكل سنة (`أتعاب-2025`، `أتعاب-2026`)،
# والدفتر لا سنةَ فيه — فالمأخوذُ أكبرُ ما استُهلك في أيّ سنة، وإلا أُعيد رقمٌ من
# سنةٍ سابقة. **وثمّ أرضيةٌ ثانية من أرقام الفواتير نفسها**: صفُّ عدّادٍ ضاع لا
# يُنقص السلسلةَ تحت رقمٍ صدر فعلاً.
from django.db import migrations

#: نوعا مستندَي الأتعاب — أُضيفا إلى `TenantBook.DOCUMENT_TYPES` في
#: `tenants/migrations/0038_alter_tenantbook_document_type.py`.
DOC_TYPE_INVOICE = "fee_invoice"
DOC_TYPE_CREDIT_NOTE = "fee_credit_note"
DOC_TYPE_LABELS = {
    DOC_TYPE_INVOICE: "فاتورة أتعاب",
    DOC_TYPE_CREDIT_NOTE: "إشعار دائن أتعاب",
}
#: الدفترُ على مستوى الشركة (لا فرع) — نفسُ افتراض `get_next_number`.
BOOK_NUMBER = 0
#: بادئةُ سلسلة الإشعار الدائن. الفاتورةُ والتكميليةُ على `أتعاب-{السنة}`؛
#: والإشعارُ على `إشعار-أتعاب-{السنة}` (انظر `accounting_office.models`).
CREDIT_SERIES_PREFIX = "إشعار-"
INVOICE_KIND_CREDIT_NOTE = "credit_note"


def _doc_type_of_series(series) -> str:
    """سلسلةُ العدّاد القديم ← نوعُ الدفتر — «إشعار» تُفحص أوّلاً فتشمل «أتعاب»."""
    text = str(series or "").strip()
    return DOC_TYPE_CREDIT_NOTE if text.startswith(CREDIT_SERIES_PREFIX) else DOC_TYPE_INVOICE


def _doc_type_of_kind(kind) -> str:
    """نوعُ المستند ← دفتره: الإشعارُ على سلسلته، والفاتورةُ والتكميليةُ على الرئيسية."""
    return DOC_TYPE_CREDIT_NOTE if kind == INVOICE_KIND_CREDIT_NOTE else DOC_TYPE_INVOICE


def _counter_of(number) -> int:
    """عدّادُ رقمٍ صادر: المقطعُ الأخير بعد الشرطة (`أتعاب-2026-00007` ← 7)."""
    tail = str(number or "").rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _carry_sequence_numbers(apps, schema_editor=None):
    """يُعلي `last_used_number` لكل دفتر إلى أكبرِ ما استُهلك فيه — **ولا يُنقصه**.

    `max` لا إسنادٌ مباشر: دفترٌ أنشأه الكودُ الجديد قبل الهجرة برقمٍ أعلى يجب
    أن يبقى عليه، وإلا أُعيد رقمٌ صدر بالفعل.
    """
    TenantBook = apps.get_model("tenants", "TenantBook")
    FeeInvoiceSequence = apps.get_model("accounting_office", "FeeInvoiceSequence")
    FeeInvoice = apps.get_model("accounting_office", "FeeInvoice")

    counters: dict[tuple[int, str], int] = {}
    for tenant_id, series, last_number in FeeInvoiceSequence.objects.values_list(
        "tenant_id", "series", "last_number",
    ):
        key = (tenant_id, _doc_type_of_series(series))
        counters[key] = max(counters.get(key, 0), int(last_number or 0))

    for tenant_id, kind, number in FeeInvoice.objects.values_list(
        "tenant_id", "kind", "number",
    ):
        key = (tenant_id, _doc_type_of_kind(kind))
        counters[key] = max(counters.get(key, 0), _counter_of(number))

    for (tenant_id, doc_type), last_number in sorted(counters.items()):
        if last_number <= 0:
            continue
        # `filter().first()` لا `get_or_create`: `branch=None` لا تحرسه فرادةٌ في
        # MySQL (تعليق `TenantBook`)، وصفوفٌ مكرّرة كانت ستُسقِط الهجرة في
        # الإنتاج بـ`MultipleObjectsReturned`. والأقدمُ يُقرأ والذي يزيد يُكتب.
        book = (
            TenantBook.objects
            .filter(
                tenant_id=tenant_id,
                branch=None,
                document_type=doc_type,
                book_number=BOOK_NUMBER,
            )
            .order_by("pk")
            .first()
        )
        if book is None:
            TenantBook.objects.create(
                tenant_id=tenant_id,
                branch=None,
                document_type=doc_type,
                book_number=BOOK_NUMBER,
                name=f"{DOC_TYPE_LABELS[doc_type]} — دفتر {BOOK_NUMBER}",
                last_used_number=last_number,
                is_active=True,
            )
            continue
        if book.last_used_number < last_number:
            book.last_used_number = last_number
            book.save(update_fields=["last_used_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounting_office", "0024_office_self_obligation_and_export_alert"),
        ("tenants", "0038_alter_tenantbook_document_type"),
    ]

    operations = [
        # عكسُها `noop`: الأرقامُ لا تُستهلك بالرجوع، وإعادةُ العدّاد إلى الخلف
        # هجرةٌ إلى الأمام كانت ستُكرّر أرقاماً صادرة.
        migrations.RunPython(_carry_sequence_numbers, migrations.RunPython.noop),
    ]
