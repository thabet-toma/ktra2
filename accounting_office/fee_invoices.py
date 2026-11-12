"""فاتورةُ الأتعاب الورقية — الترقيمُ والإلغاءُ والإشعارُ الدائن والورقة (#282، أ٢/١).

**المنطقُ كلُّه هنا**، والـ`views.py` يترجم فقط: قرارُ رقمٍ أو لونٍ أو نصٍّ يعيش في
موضعٍ واحد يُقرأ ويُختبر، لا في نقطة API تُنسخ قاعدتُها عند أول استعمالٍ ثانٍ.

**وهذه الوحدةُ لا تحسب أتعاباً**: مصدرُ المبالغ `FeeDraft` المعتمدة (أ١)، والقناعُ
`fees.amounts_masked`. ما تضيفه هنا **المستند**: رقمٌ من دفتر ترقيمٍ مقفول، وتاريخ،
وعنوانٌ لقطة، وضريبةٌ مؤرَّخة على الصفّ، وسلسلةٌ ثانيةٌ للإشعار الدائن.

**أربعُ قواعدَ لا خامسة:**

1. **الترقيمُ على دفتر الترقيم القائم** (`TenantBook.get_next_number`): القفلُ
   `select_for_update` على صفّ الدفتر داخل `transaction.atomic`، والزيادةُ تُكتب
   في المعاملة نفسها فلا فجوةَ ولا تكرار، والفرادةُ `(tenant, number)` طبقةٌ
   ثانية تُساند القفل. **وشاشةُ الدفاتر تضبط بدايةَ السلسلة** — لا عدّادَ خاصّاً
   بالموديول (`FeeInvoiceSequence` بقي أثراً تاريخياً لا يُقرأ: حذفُه هجرةٌ
   حاذفة). ودفتران: `fee_invoice` للفاتورة والتكميلية ببادئة `أتعاب-{السنة}`،
   و`fee_credit_note` للإشعار الدائن ببادئة `إشعار-أتعاب-{السنة}` — فإشعارٌ
   برقمٍ من سلسلة الفواتير يقرأ فاتورةً ثانية في كشف الزبون.
2. **لا حذفَ ولا تعديل**: `DELETE`/`PUT`/`PATCH` مُغلقةٌ في الـ`http_method_names`،
   والإلغاءُ `POST` يكتب `cancelled_at` **قبل الإرسال** فقط — و«أُرسلت» يقيسها
   `invoice_was_sent` (تذكيرٌ صادرٌ غيرُ مُبطَل، أو مشاهدةٌ على الرابط)، **لا
   وجودُ صفّ المشاركة** الذي يُنشأ من مجرّد فتح «جاهز للإرسال».
3. **الإلغاءُ يعيد المسودّةَ مسودّةً** (`approved → draft`) فتُعتمد ثانيةً وتُصدر
   ورقةً جديدةً برقمٍ جديد؛ والصفُّ الملغى يبقى أثراً (`source_draft` FK لا
   `OneToOne`) — وإلا صار الشهرُ لا يُفاتر أبداً: مسودّةٌ معتمدةٌ بلا ورقة،
   ولا فاتورةَ ثانيةً لمسودّةٍ واحدة، ولا مولّدَ يعيد المسودّة. **وعكسُ القيد
   شرطُه**: ورقةٌ عليها تخصيصُ دفعةٍ أو شطبٌ حيّ لا تُلغى (409)، وغيرُ ذلك
   يُرحَّل عكسُ قيدها (`office_journal.post_invoice_reversal_journal`) بتاريخ
   الإلغاء — فالقيدُ لا يُحذف ولا يُعدَّل، والذمّةُ تعود كما كانت (#292).
4. **«ليست فاتورة ضريبية» ثابتة**: `is_tax_invoice` خاصيّةٌ `False` في النموذج لا
   حقلاً، وسطرُ النفي يُصيَّر من `FEE_INVOICE_NOT_TAX_LINES` في كل ورقة — لا
   إعدادَ يُطفئه ولا فرعَ قالبٍ يحذفه. **وعنوانُ الورقة لا يدّعيها**: عبارتا
   الرسمية الضريبية في `core.terminology` تُرفض عند الكتابة وتُقرأ افتراضيًّا
   عند العرض (#282fix/٣).

**والقناعُ يحجب الرابطَ لا المبلغَ وحده** (#282fix/١): ورقةُ `/s/` تُفتح بلا
دخول وبكل مبالغها، فمن لا يملك `office.amounts.view` لا يُسلَّم رابطاً ولا
تُنشأ له مشاركة، وبطاقاتُ المسودّات وتفصيلُ الفاتورة وقائمةُ المشاركات تُرجع
فراغاً بدل توكن.

**واللقطاتُ لا القراءةُ الحيّة:** `tax_system` و`tax_percent` و`title` تُخزَّن على
الصفّ عند الإصدار، وكلُّ عرضٍ يقرأ منها — فتغييرُ نظام المكتب أو نسبته أو عنوانه
لا يقلب ورقةً خرجت. ومصدرُ حقول الورقة ونسبتها **نظامُ المُصدِر** (المكتب) لا
نظامُ الزبون: المكتبُ هو من يُصدر الورقة ويحصّل ضريبتها.

**وثلاثةُ إعداداتٍ تُقرأ لحظةَ الإصدار ولا تُستنتَج:** `tax_system` (نظامُ الورقة)،
و`office_licensed_dealer` («المكتب مشتغل مرخّص» — يُظهر سطرَ الضريبة، افتراضُه
مفعّل)، و`fee_invoice_title` (نصُّ العنوان؛ الفارغُ يعني الافتراضيّ بحسب النظام).
**ولا يُشتقّ الترخيصُ من وجود رقم تسجيل**: عوسيك بطور قد يحمل رقماً وهو غير مشتغلٍ
مرخّص، فيُطبع سطرُ מע"מ ويُحصَّل ما لا يجب تحصيله.
"""
import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Sum
from django.utils import timezone

from accounting_office import deadlines, fees, office_journal, services, settings_registry
from accounting_office.models import (
    EXTERNAL_NUMBER_MAX_LENGTH,
    FEE_INVOICE_CREDIT_TITLES,
    FEE_INVOICE_KIND_CREDIT_NOTE,
    FEE_INVOICE_KIND_INVOICE,
    FEE_INVOICE_KIND_LABELS,
    FEE_INVOICE_KIND_SUPPLEMENTARY,
    FEE_INVOICE_NOT_TAX_LINE_PS,
    FEE_INVOICE_NOT_TAX_LINES,
    FEE_INVOICE_TITLES,
    FEE_LINE_SOURCE_LABELS,
    REMINDER_BALANCE,
    REMINDER_DOCUMENTS,
    REMINDER_KIND_MANUAL,
    REMINDER_KIND_SENT,
    FeeDraft,
    FeeInvoice,
    FeePaymentAllocation,
    FeeWriteOff,
    fee_invoice_credit_series,
    fee_invoice_number,
    fee_invoice_series,
)
from core.access import user_has_perm
from tenants.letterhead import company_card
from tenants.models import TenantBook

AMOUNT_QUANTUM = Decimal("0.01")

#: **استحقاقُ فاتورة الأتعاب**: سبعةُ أيامٍ من إصدارها. رقمُ منتجٍ لا إعداد: مكتبٌ
#: يمنح سبعةً وآخر ثلاثين، والمرحلةُ الأولى سبعةٌ ثابتةٌ حتى يُطلب إعدادُها.
INVOICE_DUE_DAYS = 7

#: رسالةٌ واحدةٌ للفاتورة: بعد إرسالها (أو تنحيتها) يسقط بندُها من «جاهز للإرسال».
#: ولا عدّادَ «س من ن» لسقفٍ لا إعدادَ له — والسقفُ `1` بنيويّ كتذكير الموعد.
INVOICE_REMINDER_MAX = 1

TAX_SYSTEM_PS = "PS"
TAX_SYSTEM_IL = "IL"

#: وحدةُ الكمية في سطر الفاتورة: فاتورةُ أتعابٍ خدمةٌ واحدةٌ لكل سطر، والعمودُ
#: القانونيّ الرابع في م4/1 يطلب «النوع، الكمية، الوحدة، سعر الوحدة، ونسبة الضريبة».
LINE_QUANTITY = Decimal("1")
LINE_UNIT_PS = "خدمة"
LINE_UNIT_IL = "שירות"


def unit_for(tax_system: str) -> str:
    """وحدةُ الكمية بلغة الورقة — **خيارٌ واحد** يقرؤه كلُّ بانٍ للسطر."""
    return LINE_UNIT_IL if tax_system == TAX_SYSTEM_IL else LINE_UNIT_PS

#: الحقولُ التي يقنّعها `mask_amounts` في صفّ الفاتورة — من `AMOUNT_KEYS` العامّ
#: وفيه `tax_total`، والثابتُ المحلّي يسمّي المستعملَ هنا وحده.
INVOICE_AMOUNT_KEYS: tuple[str, ...] = ("total", "tax_total")

#: مفاتيحُ الإعدادات التي تُقرأ **لحظةَ الإصدار** لا وقتَ العرض.
OFFICE_LICENSED_DEALER_KEY = "office_licensed_dealer"
FEE_INVOICE_TITLE_KEY = "fee_invoice_title"


# ── النظام والترخيص والعنوان: إعداداتٌ لا تُستنتَج ────────────────────────────
def office_tax_system(tenant) -> str:
    """نظامُ **المُصدِر** الضريبيّ — مصدرُ حقول الورقة ونسبتها (#282/أ٢).

    لا نظامُ الزبون: المكتبُ يُصدر الورقةَ ويحصّل ضريبتها، وورقةُ مكتبٍ فلسطينيٍّ
    لزبونٍ إسرائيليّ تُطبع بحقول فلسطين.
    """
    value = services.resolve_setting(tenant, services.TAX_SYSTEM_KEY)
    return value if value in (TAX_SYSTEM_PS, TAX_SYSTEM_IL) else TAX_SYSTEM_PS


def office_is_licensed(tenant) -> bool:
    """هل المكتبُ «مشتغلٌ مرخّص»؟ — **إعدادٌ لا استنتاج** (#266، #282/أ٢).

    سطرُ الضريبة على ورقة الأتعاب يظهر حين يُفعَّل ويغيب كاملاً حين يُطفأ،
    وافتراضُه مفعّل. **ولا يُشتقّ من وجود رقم تسجيل**: رقماً قد يحمله غيرُ
    مشتغلٍ مرخّص، فيُطبع سطرُ ضريبةٍ لا يجب تحصيلها.
    """
    value = services.resolve_setting(tenant, OFFICE_LICENSED_DEALER_KEY)
    return True if value is None else bool(value)


def archived_rate(tenant) -> Decimal:
    """نسبةُ الضريبة السارية **لحظةَ الإصدار** — تُؤرَّخ على الصفّ في `tax_percent`.

    المصدرُ نسبةُ الشركة الافتراضية (`TenantSettings.default_vat_rate`). ولا جدولَ
    نسبٍ مؤرَّخةٍ لكل نظامٍ في المستودع — **قيدٌ معروفٌ باسم «نسبةُ الضريبة غير
    مؤرَّخة»** في `docs/modules/accounting_office.md`، ولا يُخترَع جدولٌ له هنا.
    """
    tenant_settings = getattr(tenant, "settings", None)
    rate = getattr(tenant_settings, "default_vat_rate", None)
    if rate is None:
        return Decimal("0")
    return Decimal(rate)


def not_tax_line(tax_system: str) -> str:
    """سطرُ النفي بلغة الورقة — **ثابتٌ لا إعداد**، ويُصيَّر في كل صفحة."""
    return FEE_INVOICE_NOT_TAX_LINES.get(tax_system, FEE_INVOICE_NOT_TAX_LINE_PS)


def invoice_title(tenant, tax_system: str, *, kind=FEE_INVOICE_KIND_INVOICE) -> str:
    """عنوانُ الورقة: نصُّ الإعداد، وإلا الافتراضيّ بحسب نظام المكتب.

    **وللإشعار الدائن عنوانُه**: «إشعار دائن أتعاب» / «הודעת זיכוי» — ورقةٌ تحمل
    عنوانَ الفاتورة على مبلغٍ دائنٍ تُقرأ مطالبةً. ولا يُبدَّل هذا بإعداد:
    الإعدادُ عنوانُ الفاتورة وحدها.

    **وعنوانٌ يدّعي الرسميةَ الضريبية يُسقط إلى الافتراضيّ** (#282fix/٣): الحارسُ
    يردّه عند الكتابة، وهذه تحرس قيمةً مخزَّنةً قديمةً — فورقةٌ تحمل ادّعاءَ
    رسميةٍ ضريبية تُقرأ ورقةً رسميةً وهي ليست كذلك.
    """
    if kind == FEE_INVOICE_KIND_CREDIT_NOTE:
        return FEE_INVOICE_CREDIT_TITLES.get(
            tax_system, FEE_INVOICE_CREDIT_TITLES[TAX_SYSTEM_PS],
        )
    configured = settings_registry.readable_text(
        FEE_INVOICE_TITLE_KEY, services.resolve_setting(tenant, FEE_INVOICE_TITLE_KEY),
    )
    if configured:
        return configured
    return FEE_INVOICE_TITLES.get(tax_system, FEE_INVOICE_TITLES[TAX_SYSTEM_PS])


def printed_title(invoice) -> str:
    """عنوانُ الورقة كما يُعرض ويُطبع — **ولقطةٌ محرّمة تسقط إلى الافتراضيّ**.

    `title` على الصفّ لقطةٌ لا تتغيّر، وهو المطلوب لورقةٍ خرجت. لكن صفّاً صدر قبل
    حارس العنوان (#282fix/٣) قد يحمل ادّعاءَ الرسمية الضريبية نصّاً — وعرضُه كما
    هو يعني ورقةً تطبعه. فالقراءةُ تمرّ بالقاعدة نفسها التي تحكم الإعداد
    (`settings_registry.readable_text`)، والصفُّ لا يُعدَّل.
    """
    title = settings_registry.readable_text(FEE_INVOICE_TITLE_KEY, invoice.title)
    if title:
        return title
    if invoice.kind == FEE_INVOICE_KIND_CREDIT_NOTE:
        return FEE_INVOICE_CREDIT_TITLES.get(
            invoice.tax_system, FEE_INVOICE_CREDIT_TITLES[TAX_SYSTEM_PS],
        )
    return FEE_INVOICE_TITLES.get(
        invoice.tax_system, FEE_INVOICE_TITLES[TAX_SYSTEM_PS],
    )


def _tax_of(net, *, rate: Decimal) -> Decimal:
    """نصيبُ الضريبة من مبلغٍ قبل الضريبة — بغورةٍ واحدةٍ ونصفٍ للأعلى."""
    if rate <= 0:
        return Decimal("0")
    return (Decimal(net) * rate / 100).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def _net_of(gross, *, rate: Decimal) -> Decimal:
    """المبلغُ قبل الضريبة من إجماليٍّ شاملٍ لها — عكسُ `_tax_of`."""
    if rate <= 0:
        return Decimal(gross).quantize(AMOUNT_QUANTUM)
    return (Decimal(gross) * 100 / (100 + rate)).quantize(
        AMOUNT_QUANTUM, rounding=ROUND_HALF_UP,
    )


def _local_day(moment) -> date:
    return timezone.localdate(moment)


def _issued_at(day=None) -> datetime:
    """لحظةُ الإصدار: منتصفُ نهار يومٍ صريح، أو ساعتُ النظام.

    والمنتصفُ نهاراً كـ`fees._generated_at`: استحقاقُ سبعة أيامٍ يُقاس بتاريخ
    الإصدار، ويومٌ ماضٍ يُكتب بتاريخه لا بتاريخ اليوم.
    """
    if day is None:
        return timezone.now()
    return timezone.make_aware(datetime.combine(day, time(hour=12)))


# ── الترقيم: دفترُ الترقيم القائم لا عدّاداً خاصاً بالموديول ───────────────────
#: دفترُ الأتعاب في `TenantBook` — الدفتر 0 على مستوى الشركة كما في بقية أنواع
#: المستندات: سلسلةٌ واحدةٌ لكل نوع، وبادئتُها تحمل السنة (`أتعاب-{السنة}`).
FEE_BOOK_NUMBER = 0
FEE_BOOK_INVOICE = "fee_invoice"
FEE_BOOK_CREDIT_NOTE = "fee_credit_note"


def _book_document_type(*, kind) -> str:
    """دفترُ المستند: الإشعارُ الدائنُ على سلسلته، والفاتورةُ والتكميليةُ على الرئيسية."""
    return (
        FEE_BOOK_CREDIT_NOTE
        if kind == FEE_INVOICE_KIND_CREDIT_NOTE
        else FEE_BOOK_INVOICE
    )


def _next_number(tenant, *, kind, year) -> str:
    """**الرقمُ من دفتر الترقيم المقفول** — لا `MAX(number)+1` ولا عدّادَ موديول.

    `TenantBook.get_next_number` يقفل صفَّ الدفتر (`select_for_update`) داخل
    معاملة، فالزيادةُ تُكتب في المعاملة نفسها: إصدارٌ يتعطّل (فترةٌ مقفلة، قيدٌ
    غيرُ متوازن، حسابٌ معطَّل) يُرجع رقمَه معه فلا فجوةَ في السلسلة. والبادئةُ
    `أتعاب-{السنة}` كما كانت — والسنةُ في **النصّ** لا في عدّادٍ منفصل.
    """
    series = (
        fee_invoice_credit_series(year)
        if kind == FEE_INVOICE_KIND_CREDIT_NOTE
        else fee_invoice_series(year)
    )
    counter = TenantBook.get_next_number(
        tenant.pk, _book_document_type(kind=kind), FEE_BOOK_NUMBER,
    )
    return fee_invoice_number(series, counter)


# ── الإصدار: بعد الاعتماد، ومرّةً واحدة لكل مسودّةٍ حيّة ──────────────────────
def _live_invoice_for(draft):
    """الفاتورةُ **الحيّة** لمسودّةٍ — والملغاةُ أثرٌ تاريخيّ لا يمنع إصداراً جديداً.

    `select_for_update` هنا هو حارسُ «لا فاتورتان حيّتان لمسودّةٍ واحدة» بعد أن
    صار `source_draft` FK غيرَ فريد: الاعتمادُ يقفل صفَّ المسودّة أصلاً
    (`fees._locked_draft`)، وهذا القفلُ يحرس صفوفَ الفواتير معه.
    """
    return (
        FeeInvoice.objects
        .select_for_update()
        .select_related("client", "tenant")
        .filter(source_draft=draft, cancelled_at__isnull=True)
        .first()
    )


def issue_for_draft(draft, *, actor=None, day=None) -> FeeInvoice:
    """يُصدر فاتورةَ المسودّة المعتمدة — **متكرِّرةُ الأمان** على الحيّة منها.

    نداءٌ ثانٍ (أو اعتمادٌ متزامنٌ اجتاز قفلَه) يعيد الصفَّ الحيّ ولا يُرقّم
    ثانياً. والرقمُ يُستهلك **داخل** المعاملة، فمسودّةٌ تفشل كتابتُها لا تُحرق
    رقماً من السلسلة. وإعادةُ الاعتماد بعد إلغاءٍ تُصدر ورقةً جديدةً برقمٍ جديد.
    """
    tenant = draft.tenant
    with transaction.atomic():
        existing = _live_invoice_for(draft)
        if existing is not None:
            return existing
        tax_system = office_tax_system(tenant)
        rate = archived_rate(tenant) if office_is_licensed(tenant) else Decimal("0")
        net = Decimal(draft.total)
        tax_total = _tax_of(net, rate=rate)
        issued_at = _issued_at(day)
        year = _local_day(issued_at).year
        invoice = FeeInvoice.objects.create(
            tenant=tenant,
            client=draft.client,
            source_draft=draft,
            kind=FEE_INVOICE_KIND_INVOICE,
            number=_next_number(
                tenant, kind=FEE_INVOICE_KIND_INVOICE, year=year,
            ),
            title=invoice_title(tenant, tax_system),
            tax_system=tax_system,
            total=net + tax_total,
            tax_total=tax_total,
            tax_percent=rate,
            issued_at=issued_at,
            issued_by=actor if getattr(actor, "pk", None) else None,
        )
        # #284/ب: القيدُ في المعاملة نفسها **بعد حفظ الصفّ** — فشلُه (فترةٌ
        # مقفلة، حسابٌ معطَّل، توازن) يُرجع الفاتورةَ والرقمَ والاعتمادَ معها:
        # لا ورقةَ مرقَّمةً بلا قيدها. والقولُ نفسه في `payments.create_payment`.
        office_journal.post_invoice_journal(invoice, actor=actor)
        return invoice


def _stamp_invoice_ids(tenant, invoices) -> None:
    """يُثبت معرّفات صفوفٍ أُنشئت بـ`bulk_create` حين لا تُعيدها القاعدة.

    **MySQL لا تُعيد صفوفَ الإدراج الجماعيّ** (`can_return_rows_from_bulk_insert`
    مطفأةٌ عندها، بخلاف SQLite التي تُشغّلها الاختبارات)، فالفواتيرُ تخرج بلا
    `pk`. وقيدٌ بمرجعٍ `None` لا يمنع التكرار ولا يُقرأ لاحقاً بفاتورته. فالقراءةُ
    بالرقم الفريد `(tenant, number)` — استعلامٌ واحدٌ لا يكبر بعدد الصفوف — تعيد
    المعرّفات، والصفوفُ في الذاكرة تبقى هي هي بمبالغها وعميلها. ولا تُقرأ بنودُ
    أيّ مسودّةٍ هنا.
    """
    missing = [invoice for invoice in invoices if invoice.pk is None]
    if not missing:
        return
    ids = dict(
        FeeInvoice.objects
        .filter(tenant=tenant, number__in=[invoice.number for invoice in missing])
        .values_list("number", "pk"),
    )
    for invoice in missing:
        invoice.pk = ids[invoice.number]


def issue_for_drafts(drafts, *, actor=None, day=None) -> list[FeeInvoice]:
    """يُصدر فواتيرَ مجموعةِ مسودّاتٍ **دفعةً واحدة** — مسارُ «اعتمد الكل».

    **قراءةُ المسودّات ثابتةٌ لا تكبر بعددها**: الحيّ منها استعلامٌ واحد،
    والبنودُ تُقرأ بـ`prefetch_related` في الاعتماد لا هنا، و`bulk_create` واحد.
    والأرقامُ من دفتر الترقيم صفّاً صفّاً (زيادةٌ وقفلٌ على صفّ الدفتر نفسه) —
    وهذا ما يقيسه
    `test_fees.test_approve_all_does_not_read_the_lines_of_each_draft_separately`
    بـ**قراءات البنود** لا بمجموع الاستعلامات.

    **وأمّا القيودُ فنداءٌ لكل فاتورة** (#284/ب): `post_invoice_journal` يُرحّل
    قيدَ الصفّ نفسه — صافيَه وضريبتَه من `total`/`tax_total` على الصفّ، بلا قراءة
    بنودِ مسودّةٍ واحدة. فهو النموُّ الوحيدُ في الكلفة، وثمنُ «لا فاتورةَ
    مرقَّمةً بلا قيدها»: القيدُ صفٌّ ماليٌّ لكل مستند، ولا `post_journal` جماعيّاً
    في المستودع. وفشلُ قيدٍ واحدٍ يُرجع الدفعةَ كلَّها لأن النداءَ داخل المعاملة.

    والمسودّاتُ التي لها فاتورةٌ حيّةٌ تُتخطّى، فالنداءُ متكرِّرُ الأمان كذلك.
    """
    drafts = [draft for draft in drafts if getattr(draft, "pk", None)]
    if not drafts:
        return []
    tenant = drafts[0].tenant
    already = set(
        FeeInvoice.objects
        .filter(
            source_draft_id__in=[draft.pk for draft in drafts],
            cancelled_at__isnull=True,
        )
        .values_list("source_draft_id", flat=True),
    )
    pending = [draft for draft in drafts if draft.pk not in already]
    if not pending:
        return []
    issued_at = _issued_at(day)
    year = _local_day(issued_at).year
    tax_system = office_tax_system(tenant)
    rate = archived_rate(tenant) if office_is_licensed(tenant) else Decimal("0")
    title = invoice_title(tenant, tax_system)
    issued_by = actor if getattr(actor, "pk", None) else None
    with transaction.atomic():
        rows = []
        for draft in pending:
            net = Decimal(draft.total)
            tax_total = _tax_of(net, rate=rate)
            rows.append(FeeInvoice(
                tenant=tenant,
                client=draft.client,
                source_draft=draft,
                kind=FEE_INVOICE_KIND_INVOICE,
                # رقمٌ لكل صفّ من دفتر الترقيم نفسه: أوّلُ نداءٍ ينشئ الدفتر ويقفله،
                # وكلُّ نداءٍ بعده يقرأ الزيادةَ داخل المعاملة نفسها — فتخرج
                # الأرقامُ متسلسلةً بلا فجوة. والتخصيصُ المسبق بالأرقام
                # (`last_number + offset`) كان على عدّاد الموديول لا على الدفتر.
                number=_next_number(
                    tenant, kind=FEE_INVOICE_KIND_INVOICE, year=year,
                ),
                title=title,
                tax_system=tax_system,
                total=net + tax_total,
                tax_total=tax_total,
                tax_percent=rate,
                issued_at=issued_at,
                issued_by=issued_by,
            ))
        FeeInvoice.objects.bulk_create(rows)
        # #284/ب: **قيدٌ لكل فاتورةٍ في المسار الجماعيّ أيضاً** — وإلا خرج زرُّ
        # «اعتمد الكل» بفواتيرَ بلا قيودها فتُدائن دفعاتٌ ذمّاً لم تُدَن. والمعرّفاتُ
        # تُثبَّت قبل النداء لأن MySQL لا تُعيدها من الإدراج الجماعيّ.
        _stamp_invoice_ids(tenant, rows)
        for invoice in rows:
            office_journal.post_invoice_journal(invoice, actor=actor)
    return rows


# ── الإلغاء: قبل الإرسال وحده، ويعيد المسودّةَ مسودّةً ────────────────────────
class LiveCreditNoteConflict(Exception):
    """إلغاءُ فاتورةٍ عليها **مستندٌ حيٌّ** يمنع — **تعارضٌ مع حالةٍ قائمة**.

    ليس خطأَ مدخلات: الطلبُ صحيحٌ وحقولُه صحيحة، لكنّ صفّاً آخر قائماً يمنع —
    فيُترجم **409** لا 400.

    **والاسمُ على أوّل حالةٍ أمسكها (الإشعارُ الدائن)، والصنفُ صار الأصلَ**: الـview
    يلتقط `LiveCreditNoteConflict` بعينه، والدفعةُ المخصَّصةُ/الشطبُ الحيّ يرثانه
    (`LiveAllocationConflict`) — فلا نقطةُ التقاطٍ ثانية في `views.py` ولا فرعٌ
    جديدٌ في الـAPI لكل حالةِ تعارضٍ تُكتشف.

    وإلغاءُ الأصل يترك إشعاراً دائناً حيّاً يخصم ورقةً لم تصدر، وهو ما لا يُقرأ في
    كشف الزبون.
    """

    def __init__(self, numbers=(), *, message=None):
        self.numbers = list(numbers)
        if message is None:
            message = (
                "للفاتورة إشعارٌ دائنٌ حيّ ("
                + "، ".join(self.numbers)
                + "). ألغِ الإشعارَ الدائن أوّلًا ثم ألغِ الفاتورة."
            )
        super().__init__(message)


class LiveAllocationConflict(LiveCreditNoteConflict):
    """على مسودّة الورقة **تخصيصُ دفعةٍ حيّ أو شطبٌ حيّ** — 409 كتعارض الإشعار.

    **ولا حذفَ صامتاً للتخصيص** (#292): الدفعةُ مالٌ قُبض وصفٌّ يُقرأ، وإلغاءُ
    الفاتورة تحته يُخفيها من «اللي عليه» ومن الرصيد الدائن معاً ويقلب كشفَ الحساب
    سالباً. فالرسالةُ تسمّي الدفعةَ/الشطبَ وتطلب عكسَه أوّلًا — والإلغاءُ لا يقع.
    """

    def __init__(self, message):
        super().__init__(message=message)


def _locked(invoice) -> FeeInvoice:
    """إعادةُ قراءة الصفّ بقفلٍ — قرارُ الإلغاء يُبنى على حالته الآنية لا لقطة."""
    return (
        FeeInvoice.objects
        .select_for_update()
        .select_related("client", "tenant", "issued_by")
        .get(pk=invoice.pk)
    )


def invoice_was_sent(invoice) -> bool:
    """هل خرجت الورقةُ إلى الزبون فعلاً؟ — **حاجزُ الإلغاء** (#282/أ٢).

    **وجودُ صفّ المشاركة ليس إرسالاً**: `attach_invoice_links` يُنشئ الرابط من
    مجرّد قراءة «جاهز للإرسال»، فلو كان وجودُ الصفّ هو المقياس لصار الإلغاء
    مستحيلاً بمجرّد فتح الشاشة. يُعدّ مُرسَلاً إذا:

    - صفُّ تذكيرٍ **غيرُ مُبطَل** من الأنواع المحسوبة بمفتاح هذه الفاتورة
      (`issued_on .. due_on`) — إرسالاً أو مكالمةً (لا تنحيةً ولا تصحيحاً)، أو
    - رابطُ فاتورتها سُجّلت له **مشاهدةٌ بشرية** (`view_count > 0`).
    """
    from accounting_office.models import ReminderLog
    from docshare.models import DOC_FEE_INVOICE, DocumentShare

    period_start, period_end = reminder_period(invoice)
    reverted = ReminderLog.objects.filter(reverts=OuterRef("pk"))
    sent = (
        ReminderLog.objects
        .filter(
            tenant_id=invoice.tenant_id,
            client_id=invoice.client_id,
            reminder_type=invoice_reminder_type(invoice),
            period_start=period_start,
            period_end=period_end,
            kind__in=(REMINDER_KIND_SENT, REMINDER_KIND_MANUAL),
        )
        .annotate(reverted=Exists(reverted))
        .filter(reverted=False)
        .exists()
    )
    if sent:
        return True
    return (
        DocumentShare.objects
        .filter(
            tenant_id=invoice.tenant_id,
            doc_type=DOC_FEE_INVOICE,
            doc_id=invoice.pk,
            view_count__gt=0,
        )
        .exists()
    )


def _reopen_draft(invoice) -> None:
    """`approved → draft` لمسودّة الورقة الملغاة — **بلا حذفِ رقمٍ ولا صفّ**.

    شهرٌ ملغى كان يبقى معتمداً بلا ورقة، والاعتمادُ يرفض غير «مسودّة»، والورقةُ
    الثانيةُ لمسودّةٍ واحدة ممنوعة ⇒ كان الشهرُ لا يُفاتر أبداً. فالإلغاءُ قبل
    الإرسال يعني «لم تُصدَر»: تعود المسودّةُ قابلةً للاعتماد، وتأخذ ورقةً جديدةً
    برقمٍ جديد، والملغاةُ تبقى أثراً.
    """
    if invoice.source_draft_id is None:
        return
    draft = FeeDraft.objects.select_for_update().get(pk=invoice.source_draft_id)
    if draft.status != FeeDraft.STATUS_APPROVED:
        return
    draft.status = FeeDraft.STATUS_DRAFT
    draft.approved_by = None
    draft.approved_at = None
    draft.approved_note = ""
    draft.save(update_fields=[
        "status", "approved_by", "approved_at", "approved_note",
    ])


def _live_settlements(invoice):
    """تخصيصُ دفعةٍ حيّ أو شطبٌ حيّ على مسودّة الورقة — الأقدمُ أوّلًا.

    **على المسودّة لا على الورقة**: التخصيصُ والشطبُ صفوفٌ على `FeeDraft` (مصدرُ
    المستحقّ في `payments`)، والورقةُ تمرّ إلى مسودّتها بـ`source_draft`. وللتصحيح
    (إشعارٍ دائنٍ أو تكميلية) مسودّةٌ فارغةٌ فلا تخصيصَ عليه ولا شطب.
    """
    if invoice.source_draft_id is None:
        return [], []
    allocations = list(
        FeePaymentAllocation.objects
        .filter(draft_id=invoice.source_draft_id)
        .select_related("payment")
        .order_by("payment__paid_at", "payment_id"),
    )
    write_offs = list(
        FeeWriteOff.objects
        .filter(draft_id=invoice.source_draft_id)
        .order_by("created_at", "id"),
    )
    return allocations, write_offs


def _settled_conflict_message(invoice, allocations, write_offs) -> str:
    """رسالةُ 409 التي **تسمّي** الدفعةَ/الشطبَ — لا «تعذّر الإلغاء» مجهولةً.

    أرقامُ الإشعارات تكفي للوصول إلى الدفعة في الشاشة، ومبلغُ كلٍّ منها يمنع
    الالتباس بين دفعتين في اليوم نفسه.
    """
    parts = [
        f"تخصيصُ دفعة {allocation.payment.receipt_number} "
        f"بمبلغ {Decimal(allocation.amount):.2f}"
        for allocation in allocations
    ]
    parts += [f"شطبٌ بمبلغ {Decimal(write_off.amount):.2f}" for write_off in write_offs]
    return (
        f"لا تُلغى الفاتورة {invoice.number} وعليها "
        + " و".join(parts)
        + " — اعكسِ المالَ أوّلًا، أو أصدِر إشعارًا دائنًا بدل الإلغاء."
    )


def cancel_invoice(invoice, *, actor, reason="") -> FeeInvoice:
    """`issued → cancelled` **قبل الإرسال وحده**، والصفُّ يبقى في التاريخ.

    **والصلاحيةُ صلاحيةُ الاعتماد** (`manager`/`office_manager`): الإلغاءُ فعلٌ
    على قرارِ اعتمادٍ سابق، لا كتابةُ زبونٍ — محاسبٌ لا يعتمد لا يُلغي.

    **وقبل أيّ كتابة**: ورقةٌ خرجت لا تُلغى، وورقةٌ صدر لها إشعارٌ دائنٌ حيّ لا
    تُلغى إمّا (`LiveCreditNoteConflict` ⇒ 409)، وورقةٌ عليها **تخصيصُ دفعةٍ أو
    شطبٌ حيّ** لا تُلغى كذلك (`LiveAllocationConflict` ⇒ 409): مالُ الزبون صفٌّ
    يُقرأ، ولا يُحذف صامتاً بضغطة إلغاء.

    **والقيدُ يُعكس ولا يُحذف** (#292): بعد اجتياز الحواجز يُرحَّل قيدُ عكسٍ عبر
    `office_journal.post_invoice_reversal_journal` **قبل** تعليم الصفّ ملغى —
    وكلُّه في المعاملة نفسها، ففشلُ العكس (فترةٌ مقفلة، حسابٌ معطَّل) يُرجع
    الإلغاءَ كلَّه: لا ورقةَ ملغاةً وذمّتُها قائمةٌ في الدفاتر.
    """
    fees._assert_approver(invoice.tenant, actor)
    with transaction.atomic():
        invoice = _locked(invoice)
        if invoice.is_cancelled:
            raise ValidationError({"invoice": "الفاتورةُ ملغاةٌ من قبل."})
        if invoice_was_sent(invoice):
            raise ValidationError({
                "invoice": (
                    "لا تُلغى فاتورةٌ أُرسلت إلى الزبون أو شوهد رابطُها. "
                    "أصدِر إشعاراً دائناً بدلاً من الإلغاء."
                ),
            })
        live_notes = list(
            FeeInvoice.objects
            .filter(
                related_invoice=invoice,
                kind=FEE_INVOICE_KIND_CREDIT_NOTE,
                cancelled_at__isnull=True,
            )
            .order_by("number")
            .values_list("number", flat=True)
        )
        if live_notes:
            raise LiveCreditNoteConflict(live_notes)
        allocations, write_offs = _live_settlements(invoice)
        if allocations or write_offs:
            raise LiveAllocationConflict(
                _settled_conflict_message(invoice, allocations, write_offs),
            )
        office_journal.post_invoice_reversal_journal(invoice, actor=actor)
        invoice.cancelled_at = timezone.now()
        invoice.cancelled_by = actor if getattr(actor, "pk", None) else None
        invoice.cancel_reason = (reason or "").strip()[:300]
        invoice.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason"])
        _reopen_draft(invoice)
    return invoice


# ── التصحيح: إشعارٌ دائنٌ بسقفٍ تراكميّ، وتكميليةٌ بلا سقف ───────────────────
def _assert_correctable(invoice) -> None:
    if invoice.kind != FEE_INVOICE_KIND_INVOICE:
        raise ValidationError({
            "invoice": "التصحيحُ لفاتورةٍ أصل، لا لإشعارٍ دائنٍ أو تكميلية.",
        })
    if invoice.is_cancelled:
        raise ValidationError({"invoice": "الفاتورةُ ملغاة — لا تصحيحَ لها."})


def _credit_note_cap(invoice) -> Decimal:
    """سقفُ الإشعار الدائن **تراكميّاً**: إجماليُ الأصل ناقصَ ما صُرف عليه.

    ومجموعُ ما صُرف يُقرأ **بقفلِ صفوفه** (`select_for_update` ثم جمعٌ في
    بايثون) لا بـ`aggregate` مع القفل — و`aggregate` عليه يُرفَض في جانغو،
    وقراءةٌ بلا قفلٍ تُجيز إشعارين يبلغان معاً أكثر من الأصل.
    """
    issued = sum(
        (
            FeeInvoice.objects
            .select_for_update()
            .filter(
                related_invoice=invoice,
                kind=FEE_INVOICE_KIND_CREDIT_NOTE,
                cancelled_at__isnull=True,
            )
            .values_list("total", flat=True)
        ),
        Decimal("0"),
    )
    return max(invoice.total - issued, Decimal("0"))


def _issued_credit_total(invoice) -> Decimal:
    """للقراءة وحدها (بلاغات/عرض) — مجموعُ الإشعارات الدائنة الحيّة."""
    return (
        FeeInvoice.objects
        .filter(
            related_invoice=invoice,
            kind=FEE_INVOICE_KIND_CREDIT_NOTE,
            cancelled_at__isnull=True,
        )
        .aggregate(total=Sum("total"))["total"]
        or Decimal("0")
    )


def _clean_correction_amount(amount, *, cap: Decimal | None) -> Decimal:
    """مبلغُ التصحيح: موجبٌ، و**بسقفٍ** للإشعار الدائن وحده.

    والفاتورةُ التكميلية **بلا سقفِ الأصل**: سببُها نقصٌ قد يتجاوز الإجمالي
    (خدمةٌ نُسيت كلُّها)، وتقييدُها بإجمالي الأصل يمنع تصحيحَ نقصٍ أكبرَ منه.
    """
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        value = value.quantize(AMOUNT_QUANTUM)
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({"amount": "مبلغٌ غير صالح."}) from None
    if value <= 0:
        raise ValidationError({"amount": "مبلغُ التصحيح أكبرُ من صفر."})
    if cap is not None and value > cap:
        raise ValidationError({
            "amount": (
                "مبلغُ الإشعار الدائن يتجاوز ما بقي من الفاتورة "
                f"({cap:.2f})."
            ),
        })
    return value


def _issue_correction(invoice, *, actor, kind, amount, reason, day=None) -> FeeInvoice:
    """يُصدر فاتورةَ تصحيحٍ على نظام الأصل اللقطة ونسبته المؤرَّخة."""
    fees._assert_approver(invoice.tenant, actor)
    with transaction.atomic():
        # **القفلُ قبل فحص المبلغ**: السقفُ التراكميّ يُبنى على صفوفٍ قد تتغيّر،
        # وقراءتُه من لقطةٍ خارج القفل تُجيز تجاوزَ الأصل بإشعارين متزامنين.
        invoice = _locked(invoice)
        _assert_correctable(invoice)
        cap = _credit_note_cap(invoice) if kind == FEE_INVOICE_KIND_CREDIT_NOTE else None
        amount = _clean_correction_amount(amount, cap=cap)
        rate = invoice.tax_percent
        tax_total = amount - _net_of(amount, rate=rate)
        issued_at = _issued_at(day)
        year = _local_day(issued_at).year
        note = FeeInvoice.objects.create(
            tenant=invoice.tenant,
            client=invoice.client,
            #: **لا مسودّةَ لتصحيح**: مسودّةُ الشهر واحدة، والتصحيحُ مستندٌ على
            #: فاتورتها (`related_invoice`) لا فاتورةُ شهرٍ ثانية.
            source_draft=None,
            kind=kind,
            related_invoice=invoice,
            number=_next_number(invoice.tenant, kind=kind, year=year),
            title=invoice_title(invoice.tenant, invoice.tax_system, kind=kind),
            tax_system=invoice.tax_system,
            total=amount,
            tax_total=tax_total,
            tax_percent=rate,
            issued_at=issued_at,
            issued_by=actor if getattr(actor, "pk", None) else None,
            cancel_reason=(reason or "").strip()[:300],
        )
        # #284/ب: **الإشعارُ الدائنُ يُرحَّل** عكساً لقيد فاتورته.
        # #292: **والتكميليةُ كذلك — بقيد الفاتورة نفسِه** (`post_invoice_journal`):
        # مطالبةٌ إضافيةٌ صادرةٌ كالأصل في بنودها (مدينٌ ذمّةٌ بالإجمالي، دائنٌ
        # إيرادٌ بالصافي، دائنٌ ض.ق.م بالضريبة)، وكانت تبقى ورقةً مرقَّمةً بلا أثرٍ
        # محاسبيّ: «اللي عليه» يطلبها وذمّةُ الدفاتر لا تعرفها. والمرجعُ
        # `(office_fee_invoice, معرّفها)` فلا تكرار (`idempotent`).
        if kind == FEE_INVOICE_KIND_CREDIT_NOTE:
            office_journal.post_credit_note_journal(note, actor=actor)
        else:
            # #282fix/٢: **الضريبةُ لقطةُ الأصل لا مفتاحُ اليوم** — نسبةُ
            # التكميلية وضريبتُها من `tax_percent`/`tax_total` على الأصل، فإطفاءُ
            # «مشتغل مرخّص» بعد الإصدار لا يُسقِط سطرَ الضريبة فيخرج القيدُ غيرَ
            # متوازنٍ ويُرفَض المستندُ كلُّه.
            office_journal.post_invoice_journal(
                note, actor=actor, enforce_licence=False,
            )
        return note


def issue_credit_note(invoice, *, actor, amount, reason, day=None) -> FeeInvoice:
    """إشعارٌ دائنٌ على سلسلةٍ منفصلة — بسببٍ غيرِ فارغٍ وسقفٍ تراكميّ."""
    if not (reason or "").strip():
        raise ValidationError({"reason": "سببُ الإشعار الدائن مطلوب."})
    return _issue_correction(
        invoice,
        actor=actor,
        kind=FEE_INVOICE_KIND_CREDIT_NOTE,
        amount=amount,
        reason=reason,
        day=day,
    )


def issue_supplementary(invoice, *, actor, amount, reason="", day=None) -> FeeInvoice:
    """فاتورةٌ تكميليةٌ للنقص — على السلسلة الرئيسية، **وبلا سقفِ الأصل**."""
    return _issue_correction(
        invoice,
        actor=actor,
        kind=FEE_INVOICE_KIND_SUPPLEMENTARY,
        amount=amount,
        reason=reason,
        day=day,
    )


def credit_note_remaining(invoice) -> Decimal:
    """ما بقي قابلاً للإشعار الدائن — للعرض في الشاشة (قراءةٌ بلا قفل)."""
    return max(invoice.total - _issued_credit_total(invoice), Decimal("0"))


#: حدُّ «رقم الفاتورة الرسمية الخارجية» — من عمود النموذج (`EXTERNAL_NUMBER_MAX_LENGTH`)
#: ويقرؤه المُسلسِلُ من الموضع نفسه، فلا رقمان يفترقان.
def set_external_number(invoice, *, number) -> FeeInvoice:
    """يقيّد رقمَ الفاتورة الرسمية الخارجية على ورقتها (#282fix/٥).

    **حقلٌ واحدٌ يُكتب ولا تُمسّ ورقة**: الفاتورةُ لا تُعدَّل ولا تُمحى، والرقمُ
    مرجعٌ يُضاف بعد الإصدار لأن المكتبَ يُصدر ورقتَه الرسمية في نظامٍ آخر. والفارغُ
    يمحو رقماً أُدخل خطأً — الحقلُ اختياريّ على الصفّ أصلاً.

    والحدُّ يُفحص هنا أيضاً لا في المُسلسِل وحده: نداءٌ برمجيّ يمرّ من الخدمة
    (كحدود `payments` المعروضة)، فحدُّ العمود يبقى محروساً في الطرفين.
    """
    number = (number or "").strip()
    if len(number) > EXTERNAL_NUMBER_MAX_LENGTH:
        raise ValidationError({
            "external_number": (
                f"الرقم الخارجي أطول من {EXTERNAL_NUMBER_MAX_LENGTH} حرفاً."
            ),
        })
    with transaction.atomic():
        invoice = _locked(invoice)
        invoice.external_number = number
        invoice.save(update_fields=["external_number"])
    return invoice


# ── القراءة: الرؤيةُ والقناع ───────────────────────────────────────────────────
def visible_invoices(tenant, user):
    """فواتيرُ ما يراه العضو وحدها — والتفصيلُ والتصحيحُ يُقرآن من هنا أيضاً.

    ومسودّةُ زبونٍ لا يراه العضو **404** في الـview لا 403، كما في المسودّات.
    """
    return (
        FeeInvoice.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related(
            "client", "source_draft", "issued_by", "cancelled_by", "related_invoice",
        )
    )


def _client_payload(client) -> dict:
    return {"id": client.pk, "name": client.name}


def _user_payload(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "name": services.user_display_name(user)}


def _lines_payload(invoice) -> list[dict]:
    """سطورُ الورقة من بنود مسودّتها — لقطةُ التوليد لا حسابٌ جديد.

    والتصحيحُ (إشعارٌ دائنٌ أو تكميلية) لا مسودّةَ له: سطرُه واحدٌ بسببه ومبلغه —
    فالإشعارُ يحمل «كلَّ حقول الفاتورة مع قيمته وسببه» (م.4–م.12 من تعليمات
    25/2025) لا بنودَ الأصل نفسَها.
    """
    if invoice.source_draft_id is None:
        return [{
            "id": None,
            "label": invoice.cancel_reason or printed_title(invoice),
            "quantity": LINE_QUANTITY,
            "unit": unit_for(invoice.tax_system),
            "amount": invoice.net_total,
            "source": None,
            "source_label": "",
        }]
    return [
        {
            "id": line.pk,
            "label": line.label,
            "quantity": LINE_QUANTITY,
            "unit": unit_for(invoice.tax_system),
            "amount": line.amount,
            "source": line.source,
            "source_label": FEE_LINE_SOURCE_LABELS.get(line.source, ""),
        }
        for line in invoice.source_draft.lines.all()
    ]


def invoice_row(invoice, *, masked) -> dict:
    """سطرُ فاتورةٍ كما يخرج — والمبلغُ `None` لمن لا يراه، والشكلُ ثابتٌ دائماً."""
    data = {
        "id": invoice.pk,
        "number": invoice.number,
        "kind": invoice.kind,
        "kind_label": FEE_INVOICE_KIND_LABELS.get(invoice.kind, ""),
        "title": printed_title(invoice),
        "client": _client_payload(invoice.client),
        "source_draft": invoice.source_draft_id,
        "related_invoice": invoice.related_invoice_id,
        "tax_system": invoice.tax_system,
        "tax_percent": invoice.tax_percent,
        "total": invoice.total,
        "tax_total": invoice.tax_total,
        "external_number": invoice.external_number,
        "issued_at": invoice.issued_at.isoformat(),
        "issued_by": _user_payload(invoice.issued_by),
        "state": invoice.state,
        "is_tax_invoice": invoice.is_tax_invoice,
        "cancelled_at": (
            None if invoice.cancelled_at is None else invoice.cancelled_at.isoformat()
        ),
        "cancelled_by": _user_payload(invoice.cancelled_by),
        "cancel_reason": invoice.cancel_reason,
        "has_link": invoice_has_link(invoice),
    }
    return services.mask_amounts(data, INVOICE_AMOUNT_KEYS) if masked else data


def invoice_detail(invoice, *, masked) -> dict:
    """تفصيلُ فاتورة: صفُّها وبحورُها ورابطُها الحيّ إن وُجد.

    **والرابطُ يسقط مع القناع** (#282fix/١): ورقةُ `/s/` تُفتح بلا دخول وبكل
    مبالغها، فرابطٌ يُسلَّم لعضوٍ لا يملك «يرى المبالغ» يقرأ ما مُنع عنه.
    """
    data = invoice_row(invoice, masked=masked)
    lines = _lines_payload(invoice)
    data["lines"] = (
        [_masked_line(line) for line in lines] if masked else lines
    )
    data["net_total"] = None if masked else invoice.net_total
    data["url"] = "" if masked else (live_invoice_url(invoice) or "")
    data["credit_note_remaining"] = (
        None if masked else credit_note_remaining(invoice)
    )
    return data


def _masked_line(line) -> dict:
    """سطرٌ مقنَّع — المفتاحُ يبقى والمبلغُ يصير `None` كسائر صفوف الموديول."""
    return services.mask_amounts(line, services.FEE_AMOUNT_KEYS)


def invoices_payload(tenant, *, user, client=None, kind=None, state=None) -> list[dict]:
    """قائمةُ الفواتير — الفلاترُ تُطبَّق في الاستعلام لا في بايثون.

    `state` قيمتاه `issued`/`cancelled` وحدهما؛ وقيمةٌ غيرُهما تُهمَل (القائمةُ
    كاملةً) لأن الفلترةَ عرضٌ لا حارس: لا خطأَ في طلبِ قائمةٍ بفلترٍ مطبوعٍ خطأً.
    """
    masked = fees.amounts_masked(tenant, user)
    queryset = visible_invoices(tenant, user)
    if client is not None:
        queryset = queryset.filter(client_id=client)
    if kind in FEE_INVOICE_KIND_LABELS:
        queryset = queryset.filter(kind=kind)
    if state == "cancelled":
        queryset = queryset.filter(cancelled_at__isnull=False)
    elif state == "issued":
        queryset = queryset.filter(cancelled_at__isnull=True)
    return [
        invoice_row(invoice, masked=masked)
        for invoice in queryset.order_by("-issued_at", "-id")
    ]


# ── الرابطُ العامّ: ورقةٌ واحدةٌ لكل فاتورة ───────────────────────────────────
def invoice_has_link(invoice) -> bool:
    """هل لهذه الفاتورة رابطٌ حيٌّ الآن؟ — سؤالُ عرضٍ لا سؤالَ إرسال."""
    return live_invoice_url(invoice) is not None


def live_invoice_urls(tenant, invoice_ids) -> dict[int, str]:
    """روابطُ الأوراق **الحيّة القائمة** — قراءةٌ محضة، بلا إنشاء ولا كتابة.

    شرطُ «الحيّ» في موضعٍ واحد: غيرُ عامّ، وغيرُ مُبطَل، وغيرُ منتهٍ. يقرؤه
    `live_invoice_url` للورقة الواحدة، و`invoice_urls` قبل أن يُنشئ الناقص،
    وبطاقاتُ المسودّات في شاشة «المسودّات» — فنسخةٌ ثانية منه تفترق عن الأولى
    بأوّل تغييرٍ في سياسة انتهاء الرابط.
    """
    from docshare import services as docshare_services
    from docshare.models import DOC_FEE_INVOICE, DocumentShare

    wanted = {invoice_id for invoice_id in invoice_ids if invoice_id is not None}
    if not wanted:
        return {}
    shares = (
        DocumentShare.objects
        .filter(
            tenant=tenant,
            doc_type=DOC_FEE_INVOICE,
            doc_id__in=list(wanted),
            is_public=False,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at", "-id")
        .values_list("doc_id", "token")
    )
    urls: dict[int, str] = {}
    for doc_id, token in shares:
        urls.setdefault(doc_id, docshare_services.public_url_for_token(token))
    return urls


def live_invoice_url(invoice) -> str | None:
    """الرابطُ الحيّ القائم إن وُجد — **قراءةٌ فقط، لا إنشاءَ من مسار قراءة**."""
    return live_invoice_urls(invoice.tenant_id, [invoice.pk]).get(invoice.pk)


def invoice_urls(tenant, invoice_ids, *, user=None) -> dict[int, str]:
    """رابطُ ورقة الفاتورة لكلّ فاتورةٍ في المجموعة — نمطُ `payment_notice_urls`.

    الرابطُ يُنشَأ أوّلَ مرّةٍ **في مسار القراءة** («جاهز للإرسال») عن قصد: نصُّ
    الرسالة يجب أن يكون نهائياً قبل الإرسال، ورابطٌ يُخلَق بعده لا يكون في
    الورقة التي بيد الزبون. والتكرارُ آمن — الحيّ نفسه يُعاد (`dedupe`).
    ولا يُعدّ إنشاءُ الرابط إرسالاً: `invoice_was_sent` يقيس التذكيرَ الصادرَ
    أو المشاهدة، لا وجودَ الصفّ.

    **ومن لا يرى المبالغ لا رابطَ له ولا مشاركة** (#282fix/١): الورقةُ تُعرض على
    `/s/` بلا دخول وبالصافي والضريبة والإجمالي، فمشاركةٌ تُنشأ لعضوٍ مقنَّعٍ
    تُسلّمه ما مُنع عنه في الحمولات.
    """
    from docshare import services as docshare_services
    from docshare.models import DOC_FEE_INVOICE

    if fees.amounts_masked(tenant, user):
        return {}
    wanted = {invoice_id for invoice_id in invoice_ids if invoice_id is not None}
    if not wanted:
        return {}
    urls = live_invoice_urls(tenant, wanted)
    for invoice_id in sorted(wanted - set(urls)):
        try:
            share = docshare_services.create_share(
                tenant, DOC_FEE_INVOICE, invoice_id, user=user,
            )
        except docshare_services.ShareNotFound:
            # الفاتورةُ تغيّرت بين القراءتين: النصُّ يمضي بلا رابطٍ ولا يسقط الطلب.
            continue
        urls[invoice_id] = docshare_services.public_url(share)
    return urls


# ── بطاقةُ الورقة على صفّ المسودّة (شاشةُ «المسودّات») ───────────────────────
def draft_invoice_cards(tenant, drafts, *, masked) -> dict[int, dict]:
    """بطاقةُ الورقة **الحيّة** لكل مسودّة: رقمُها وتاريخُها ورابطُها — استعلامان.

    شاشةُ «المسودّات» تقرأ `fees/drafts/` وحدها، فالبطاقةُ هنا تمنعها من جلب
    قائمة الفواتير كلَّها لتصل إلى ثلاثة حقول. والقراءةُ **بلا إنشاء رابط**:
    شاشةُ قائمةٍ لا تُنشئ روابطَ مشاركةٍ لكل صفٍّ مرّت عليه.

    **و`masked` تُسقط الرابطَ لا البطاقة** (#282fix/١): رقمُ الورقة وتاريخُها بلا
    مبالغ، والرابطُ يفتح ورقةً كاملةَ المبالغ — فمن لا يرى المبالغ يقرأ بطاقةً
    بلا رابط (ولا تُقرأ روابطه أصلاً). **ولا افتراضَ لها**: قرارُ القناع يُمرَّر
    صريحاً (كما في `invoice_detail`)، فلا يُفتح بابٌ يُنسى فيه.
    """
    draft_ids = [draft.pk for draft in drafts if getattr(draft, "pk", None)]
    if not draft_ids:
        return {}
    live = list(
        FeeInvoice.objects
        .filter(
            tenant=tenant,
            source_draft_id__in=draft_ids,
            cancelled_at__isnull=True,
        )
        .only("id", "source_draft_id", "number", "issued_at")
        .order_by("id"),
    )
    urls = {} if masked else live_invoice_urls(
        tenant, [invoice.pk for invoice in live],
    )
    return {
        invoice.source_draft_id: {
            "id": invoice.pk,
            "number": invoice.number,
            "issued_at": invoice.issued_at.isoformat(),
            "url": urls.get(invoice.pk, ""),
        }
        for invoice in live
    }


def draft_invoice_card(tenant, draft, *, masked) -> dict | None:
    """بطاقةُ ورقةِ مسودّةٍ واحدة — للصفّ المفرد (ردُّ الاعتماد مثلاً)."""
    return draft_invoice_cards(tenant, [draft], masked=masked).get(draft.pk)


# ── الورقة: حقولُها بترتيبها ──────────────────────────────────────────────────
_ARABIC_ONES = (
    "", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة",
)
_ARABIC_TEENS = (
    "عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر",
    "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر",
)
_ARABIC_TENS = (
    "", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون",
    "تسعون",
)
_ARABIC_HUNDREDS = (
    "", "مئة", "مئتان", "ثلاثمئة", "أربعمئة", "خمسمئة", "ستمئة", "سبعمئة",
    "ثمانمئة", "تسعمئة",
)
#: مقاييسُ الألف والمليون: (مفرد، مثنّى، جمع، تمييز).
_ARABIC_SCALES = (
    ("ألف", "ألفان", "آلاف", "آلاف"),
    ("مليون", "مليونان", "ملايين", "ملايين"),
    ("مليار", "ملياران", "مليارات", "مليارات"),
)


def _words_under_thousand(number: int) -> str:
    """0..999 بالحروف — بلا واوٍ في الطرف، والوصلُ في `_join_arabic`."""
    parts = []
    hundreds, rest = divmod(number, 100)
    if hundreds:
        parts.append(_ARABIC_HUNDREDS[hundreds])
    if 10 < rest < 20:
        parts.append(_ARABIC_TEENS[rest - 10])
        rest = 0
    elif rest == 10:
        parts.append(_ARABIC_TEENS[0])
        rest = 0
    tens, ones = divmod(rest, 10)
    if ones:
        parts.append(_ARABIC_ONES[ones])
    if tens:
        parts.append(_ARABIC_TENS[tens])
    return _join_arabic(parts)


def _join_arabic(parts) -> str:
    return " و".join(part for part in parts if part)


def _scale_words(count: int, index: int) -> str:
    """مقياسٌ (ألف/مليون/مليار) بعددِه — مثنّىً وجمعاً ومفرداً بتمييزه."""
    if count == 0:
        return ""
    singular, dual, plural, _distinct = _ARABIC_SCALES[index]
    if count == 1:
        return singular
    if count == 2:
        return dual
    if 3 <= count <= 10:
        return f"{_words_under_thousand(count)} {plural}"
    return f"{_words_under_thousand(count)} {singular}"


def amount_in_words(amount) -> str:
    """**تفقيطُ مبلغٍ عربيًّا** — «قيمة الضريبة بالأرقام والحروف» (م4/1/6).

    دالّةٌ نقيّةٌ على المبلغ لا بياناتٌ ناقصة: العمودُ السادس في تعليمات 25/2025
    يطلب قيمةَ الضريبة بالأرقام **وبالحروف**، والورقةُ الرقميةُ تطبع الرقمَ وحده
    فتُقرأ ورقةً ناقصة. تُقرأ الأجزاءُ الصحيحةُ إلى مليار، والأغورةُ كسراً.
    """
    value = Decimal(amount or 0).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    whole = int(value)
    agorot = int((value - whole) * 100)
    parts = []
    remaining = whole
    groups = []
    while remaining:
        groups.append(remaining % 1000)
        remaining //= 1000
    if not groups:
        groups = [0]
    if len(groups) > len(_ARABIC_SCALES) + 1:
        # مبلغٌ فوق المليار لا يقع في أتعاب مكتب؛ الرقمُ يبقى، والحروفُ تُختصر.
        return f"{value:.2f}"
    for index in range(len(groups) - 1, -1, -1):
        count = groups[index]
        if index == 0:
            words = _words_under_thousand(count)
            if words:
                parts.append(words)
            continue
        scale = _scale_words(count, index - 1)
        if scale:
            parts.append(scale)
    if not parts:
        parts.append("صفر")
    text = _join_arabic(parts)
    if agorot:
        text = f"{text} و{_words_under_thousand(agorot)} أغورة"
    return f"-{text}" if negative and whole else text


def reminder_period(invoice) -> tuple[date, date]:
    """مفتاحُ بند الفاتورة في «جاهز للإرسال»: (يومُ الإصدار، يومُ الاستحقاق).

    **لا شهرَ المسودّة** (#282/أ٢): الشهرُ قد ينتج ورقتين (ملغاةً وسارية)،
    ومفتاحُ التذكير (يبدأ، ينتهي) لقطةُ الورقة نفسها.
    """
    issued_on = _local_day(invoice.issued_at)
    return issued_on, issued_on + timedelta(days=INVOICE_DUE_DAYS)


def document_period_text(invoice) -> str | None:
    """شهرُ مسودّة الورقة كما يُنطق في الرسالة — **لا شهرُ يوم الإصدار**.

    نصُّ النوع يقول «على حساب {period}»، والورقةُ تخصّ شهرَ مسودّتها: مسودّةُ
    آذار قد تُصدر في تشرين الثاني، وقراءةُ الفترة من `issued_at` تذكر شهراً لا
    تخصّه الورقة. والتصحيحُ يورث شهرَ أصله (`related_invoice`) لا شهرَ يومه،
    وورقةٌ بلا مسودّةٍ ولا أصل — لا لقطةَ شهرٍ لها — تبقى على تسمية فترة إصدارها.

    **ولا يمسّ المفتاح**: `reminder_period` يبقى (الإصدار، الاستحقاق) لكل ورقة.
    """
    draft = invoice.source_draft
    if draft is None and invoice.related_invoice_id is not None:
        related = invoice.related_invoice
        draft = None if related is None else related.source_draft
    if draft is None:
        return None
    start = date(draft.year, draft.month, 1)
    return deadlines.period_label(
        start, deadlines.month_start_after(start, 1) - timedelta(days=1),
    )


def sheet_lines(invoice) -> list[dict]:
    """سطورُ الورقة بأعمدة م4/1: النوعُ والكميةُ والوحدةُ والسعرُ ونسبةُ الضريبة."""
    unit = unit_for(invoice.tax_system)
    return [
        {
            "label": line["label"],
            "quantity": LINE_QUANTITY,
            "unit": unit,
            "unit_price": line["amount"],
            "tax_percent": invoice.tax_percent,
            "line_total": line["amount"],
        }
        for line in _lines_payload(invoice)
    ]


#: تسمياتٌ لكل نظام — **نصٌّ واحدٌ لكل مفهوم**، فيقرؤه القالبُ ولا يحمل حرفاً.
LABELS_PS: dict[str, str] = {
    "registration": "رقم المشتغل المرخّص",
    "trade_name": "الاسم التجاري",
    "address": "العنوان",
    "phone": "هاتف العمل",
    "number": "رقم الفاتورة",
    "issued_on": "تاريخ الإصدار",
    "client": "الزبون",
    "client_file": "رقم الملف الضريبي",
    "lines_head": "البيان",
    "quantity": "الكمية",
    "unit": "الوحدة",
    "unit_price": "سعر الوحدة",
    "tax_percent": "الضريبة %",
    "line_total": "الإجمالي",
    #: لا عنوانَ لكتلة المبالغ في فلسطين: «الإجمالي قبل الضريبة» هو العنصرُ
    #: الخامس نفسه، وعنوانٌ ثانٍ فوقه تكرارُ رقمٍ باسمين.
    "consideration": "",
    "net": "الإجمالي قبل الضريبة",
    "tax": "قيمة الضريبة",
    "tax_words": "قيمة الضريبة بالحروف",
    "gross": "الإجمالي شاملاً الضريبة",
    "signature": "توقيع المُصدِر",
    "original": "الأصل",
    "copy": "نسخة",
    "external_number": "رقم الفاتورة الرسمية",
    "kind_credit_note": FEE_INVOICE_CREDIT_TITLES["PS"],
    "kind_supplementary": "فاتورة تكميلية",
    "related": "الفاتورة الأصل",
    "cancelled": "ملغاة",
    "cancel_reason": "سبب الإلغاء",
}

LABELS_IL: dict[str, str] = {
    "registration": 'מספר עוסק',
    "trade_name": "שם העסק",
    "address": "כתובת",
    "phone": "טלפון",
    "number": "מספר סידורי",
    "issued_on": "תאריך הוצאה",
    "client": "שם המקבל",
    "client_file": "מספר תיק ניכויים",
    "lines_head": "תיאור הפעולה",
    "quantity": "כמות",
    "unit": "יחידה",
    "unit_price": "מחיר יחידה",
    "tax_percent": 'מע"מ %',
    "line_total": "סכום",
    #: العنصرُ السادس في `§9א` («התמורה») — عنوانٌ على كتلة المبالغ. وفي
    #: فلسطين لا عنوانَ زائداً: العنصرُ الخامس هو «الإجمالي قبل الضريبة» نفسه.
    "consideration": "התמורה",
    "net": 'סכום לפני מע"מ',
    "tax": 'מע"מ',
    "tax_words": 'מע"מ באותיות',
    "gross": 'סה"כ לתשלום',
    "signature": "חתימת המוציא",
    "original": "",
    "copy": "",
    "external_number": "מספר חשבונית חיצונית",
    "kind_credit_note": FEE_INVOICE_CREDIT_TITLES["IL"],
    "kind_supplementary": "חשבונית משלימה",
    "related": "חשבונית מקור",
    "cancelled": "מבוטלת",
    "cancel_reason": "סיבת הביטול",
}


def labels_for(tax_system: str) -> dict[str, str]:
    return LABELS_IL if tax_system == TAX_SYSTEM_IL else LABELS_PS


def sheet_context(invoice) -> dict:
    """سياقُ الورقة — **كلُّ ما يُطبع يُمرَّر صريحاً**، والقالبُ لا يحسب مالاً.

    والنظامُ والنسبةُ والعنوانُ **من الصفّ** لا من إعداداتٍ حيّة (#282/أ٢):
    ورقةٌ خرجت لا تتغيّر بتغيير نظام المكتب أو نسبته. والنسختان في فلسطين وحدها
    (م4/5: «نسختين على الأقل، الأصل ثم نسخة»)، وإسرائيل لا تشترط نسختين.
    """
    tax_system = invoice.tax_system
    labels = labels_for(tax_system)
    copies = (
        [labels["original"], labels["copy"]]
        if tax_system == TAX_SYSTEM_PS else [""]
    )
    return {
        "title": printed_title(invoice),
        "tax_system": tax_system,
        "not_tax_line": not_tax_line(tax_system),
        "labels": labels,
        "company": company_card(invoice.tenant),
        "client_name": invoice.client.name,
        "client_tax_file": invoice.client.tax_file_number or "",
        "number": invoice.number,
        "external_number": invoice.external_number,
        "date": _local_day(invoice.issued_at),
        "kind_label": (
            labels["kind_credit_note"]
            if invoice.kind == FEE_INVOICE_KIND_CREDIT_NOTE
            else labels["kind_supplementary"]
            if invoice.kind == FEE_INVOICE_KIND_SUPPLEMENTARY
            else printed_title(invoice)
        ),
        "related_number": (
            None if invoice.related_invoice_id is None
            else invoice.related_invoice.number
        ),
        "lines": sheet_lines(invoice),
        "net": invoice.net_total,
        "tax_total": invoice.tax_total,
        "tax_words": amount_in_words(invoice.tax_total),
        "total": invoice.total,
        "tax_percent": invoice.tax_percent,
        "show_tax": bool(invoice.tax_total),
        "copies": copies,
        "cancelled": invoice.is_cancelled,
        "cancel_reason": invoice.cancel_reason,
    }


def render_sheet(invoice) -> str:
    """ورقةُ الفاتورة HTML — يستدعيها نوعُ مستند `fee_invoice` في `docshare`."""
    from django.template.loader import render_to_string

    return render_to_string("docshare/fee_invoice.html", sheet_context(invoice))


# ── حمولةُ العقد العامّ ───────────────────────────────────────────────────────
def share_payload(invoice) -> dict:
    """حمولةُ `docshare` العامة — من `payload()` و`line_row()` وحدَهما.

    `show_lines=True` و`show_line_prices=True`: الفاتورةُ أسطرٌ وأسعارٌ — بخلاف
    سند القبض الذي يُخفي أعمدة السعر لأنها بلا معنى عليه.
    """
    from docshare.documents._contract import (
        TONE_DANGER,
        TONE_OK,
        VALUE_DATE,
        line_row,
        meta,
        payload,
        total as total_row,
    )

    labels = labels_for(invoice.tax_system)
    lines = [
        line_row(name=line["label"], unit=line["unit"], quantity=line["quantity"],
                 unit_price=line["unit_price"], tax_percent=line["tax_percent"],
                 line_total=line["line_total"])
        for line in sheet_lines(invoice)
    ]
    totals = [total_row(labels["net"], invoice.net_total)]
    if invoice.tax_total:
        totals.append(total_row(labels["tax"], invoice.tax_total))
    totals.append(total_row(labels["gross"], invoice.total, strong=True))
    return payload(
        kind="fee_invoice",
        title=printed_title(invoice),
        number=invoice.number,
        date=_local_day(invoice.issued_at),
        status_label=(
            labels["cancelled"] if invoice.is_cancelled
            else FEE_INVOICE_KIND_LABELS.get(invoice.kind, "")
        ),
        status_tone=TONE_DANGER if invoice.is_cancelled else TONE_OK,
        party_title="الزبون",
        party=invoice.client.name,
        currency=None,
        meta_rows=[
            meta(labels["issued_on"], _local_day(invoice.issued_at), VALUE_DATE),
            meta(labels["client_file"], invoice.client.tax_file_number),
        ],
        lines=lines,
        totals_rows=totals,
        grand_total=invoice.total,
        show_lines=True,
        show_line_prices=True,
    )


# ── «جاهز للإرسال»: رسالةُ الفاتورة ──────────────────────────────────────────
def _reminder_invoice(invoice, *, due) -> dict:
    """بندُ الفاتورة كما يخرج في الرسالة — مبالغُه نصوصٌ مصيغةٌ لا `Decimal`.

    والمبلغُ مكشوفٌ كما في نصّ الرسالة نفسه: الرسالةُ إلى الزبون عن مبلغٍ عليه،
    وقنعُه عن الموظّف كان يُرسل «—» إلى الزبون بدل مبلغه (قاعدةُ #281).
    **و`original_number` للأصل**: نصُّ الإشعار الدائن يسمّي الفاتورةَ التي يخصمها.
    **والعنوانُ بـ`printed_title`** (#282fix2/٢): هذا البندُ يدخل نصَّ رسالةٍ تصل
    الزبونَ، فعنوانٌ مخزَّنٌ محرَّمٌ لا يخرج منه كما خُزِّن.
    """
    return {
        "id": invoice.pk,
        "number": invoice.number,
        "title": printed_title(invoice),
        "kind": invoice.kind,
        "total": f"{invoice.total:.2f}",
        "tax_total": f"{invoice.tax_total:.2f}",
        "issued_on": _local_day(invoice.issued_at).isoformat(),
        "due_on": due.isoformat(),
        "reason": invoice.cancel_reason,
        "original_number": (
            "" if invoice.related_invoice_id is None else invoice.related_invoice.number
        ),
        "url": "",
    }


#: أنواعُ بنود الفواتير في «جاهز للإرسال»: الفاتورةُ والتكميليةُ **مطالبةٌ**
#: (`balance`)، والإشعارُ الدائنُ **مستندٌ يُسلَّم** لا مطالبة (`documents`) —
#: رسالةٌ تعطيه مبلغاً وتعرضه «عليه» تكذب عليه. ولا نوعَ تذكيرٍ خامس: النوعان
#: قائمان، والقنواتُ (الإذنُ والتنبيهاتُ والقوالب) تعرفهما أصلاً.
_INVOICE_REMINDER_TYPES: dict[str, str] = {
    FEE_INVOICE_KIND_INVOICE: REMINDER_BALANCE,
    FEE_INVOICE_KIND_SUPPLEMENTARY: REMINDER_BALANCE,
    FEE_INVOICE_KIND_CREDIT_NOTE: REMINDER_DOCUMENTS,
}


def invoice_reminder_type(invoice) -> str:
    """نوعُ بند الفاتورة: مطالبةٌ أو مستندٌ غيرُ مطالِب."""
    return _INVOICE_REMINDER_TYPES.get(invoice.kind, REMINDER_BALANCE)


def invoice_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """بندُ كلّ ورقةٍ صادرةٍ لم تُلغَ — **من يوم إصدارها** لا يوم استحقاقها.

    - الفاتورةُ والتكميليةُ: نوعُ `balance` («اللي عليه») بمبلغها الكامل.
    - الإشعارُ الدائنُ: نوعُ `documents` — **غيرُ مطالِب**، ومبلغُه نصيبُه.
    - والمفتاحُ **لكل ورقة**: `(issued_on, due_on)`، لا شهرَ المسودّة.
    - والاستحقاقُ `issued_on + 7` في `next_due`/`render_due`/`due_on`، والبندُ
      **ظاهرٌ من يوم الإصدار** (`due`) كي يُرسَل مع بقية رسائل ذلك اليوم بلا
      انتظار سبعة أيام.
    - ونوعُ التذكير يُقرأ من `reminder_types_enabled` كما في مولّدَي المواعيد.
    """
    if reminder_type is not None:
        if services._assert_reminder_type(reminder_type) not in _INVOICE_REMINDER_TYPES.values():
            return []
    client_ids = [client.pk for client in clients]
    if not client_ids:
        return []
    rows = (
        FeeInvoice.objects
        .filter(
            tenant=tenant,
            client_id__in=client_ids,
            kind__in=tuple(_INVOICE_REMINDER_TYPES),
            cancelled_at__isnull=True,
        )
        .select_related("client", "source_draft", "related_invoice")
        .order_by("issued_at", "id")
    )
    candidates = []
    for invoice in rows:
        item_type = invoice_reminder_type(invoice)
        if reminder_type is not None and item_type != reminder_type:
            continue
        resolved = settings_by_client.get(invoice.client_id, {})
        enabled = resolved.get(services.REMINDER_TYPES_ENABLED_KEY) or []
        if item_type not in enabled:
            continue
        issued_on, due_on = reminder_period(invoice)
        pairs = by_pair.get(
            (invoice.client_id, item_type, issued_on, due_on), [],
        )
        count = sum(
            1 for row in pairs if row["kind"] in services.REMINDER_COUNTED_KINDS
        )
        candidates.append(services.ReminderCandidate(
            client=invoice.client,
            reminder_type=item_type,
            period_start=issued_on,
            period_end=due_on,
            missing=(),
            missing_codes=(),
            count=count,
            maximum=INVOICE_REMINDER_MAX,
            interval_days=INVOICE_DUE_DAYS,
            next_due=due_on,
            contact=contacts.get((invoice.client_id, item_type)),
            tax_system=invoice.tax_system,
            due=day >= issued_on,
            exhausted=count >= INVOICE_REMINDER_MAX,
            postponed=(invoice.client_id, item_type) in postponed_pairs,
            render_due=due_on,
            period_text=document_period_text(invoice),
            amount=invoice.total,
            invoice=_reminder_invoice(invoice, due=due_on),
        ))
    return candidates


def attach_invoice_links(tenant, candidates, *, user=None):
    """يُركّب رابطَ الورقة على بنود الفواتير — **بعد الحواجز كلّها**.

    والرابطُ لمن يملك مشاركةَ النوع **والمبالغَ معاً**: يُنشَأ في مسار قراءة، فلا
    يجوز أن يمنح عضوَ قراءةٍ صفَّ مشاركةٍ حيّاً؛ ومن لا يرى المبالغ لا رابطَ له
    ولو ملك مفتاح الكتابة (#282fix/١) — ورقةُ `/s/` تُعرض بكل مبالغها. والحكمُ في
    `invoice_urls` وحدها (فلا نسختان تفترقان)، وهذه تعود بلا رابطٍ إن لم يصلها.
    """
    from dataclasses import replace

    if user is None or not user_has_perm(
        user, tenant, services.OFFICE_CLIENTS_WRITE_KEY,
    ):
        return candidates
    wanted = [
        candidate.invoice["id"]
        for candidate in candidates
        if candidate.invoice is not None and not candidate.invoice.get("url")
    ]
    if not wanted:
        return candidates
    urls = invoice_urls(tenant, wanted, user=user)
    if not urls:
        return candidates
    attached = list(candidates)
    for index, candidate in enumerate(attached):
        if candidate.invoice is None:
            continue
        url = urls.get(candidate.invoice["id"])
        if url:
            attached[index] = replace(
                candidate,
                invoice={**candidate.invoice, "url": url},
            )
    return attached


def invoice_item(invoice) -> dict | None:
    """بندُ الفاتورة في الصفحة — `None` لبندٍ ليس فاتورة (كأيّ نوعٍ آخر)."""
    return None if invoice is None else dict(invoice)


def strip_public_links(text: str) -> str:
    """يحذف من نصٍّ **كلَّ رابطٍ عامٍّ لـ`docshare`** — وسطرَ «الرابط:» الذي يحمله.

    لسجلّ التذكيرات (#282fix2/١): `ReminderLog.body` يحفظ نصَّ الرسالة كما أُرسل
    بروابطه، وورقةُ `/s/` تُفتح بلا دخولٍ وبكل المبالغ. فمن لا يملك
    `office.amounts.view` يقرأ النصَّ بلا توكِنٍ. والنمطُ الأساسُ العامُّ الحاليُّ
    (`public_url_for_token`) مع المَركبَين المعروفَين (`/s/` و`/api/share/`) على أيّ
    نطاق — فتغييرُ `DOCSHARE_PUBLIC_PATH` بعد الإرسال لا يُعيد روابطَ السجلّ القديم.
    والمبلغُ في النصّ لا يُمسّ (قاعدةُ #281: الرسالةُ إلى الزبون نفسه).

    وبناةُ الرسالة الثلاثةُ (الفاتورةُ هنا، وتقريرُ الدفتر، وإشعارُ الدفع) يكتبون
    الرابطَ سطراً مستقلّاً بالوسم `الرابط:` — فيُحذف السطرُ كلُّه، وما سواه يُحذف
    عنوانُه من موضعه.
    """
    from docshare import services as docshare_services

    url = (
        r"(?:https?://[^\s/]+)?"
        rf"(?:{re.escape(docshare_services.public_url_for_token(''))}|/s/|/api/share/)"
        r"[A-Za-z0-9_-]+/?"
    )
    line = rf"(?:\n|\A)[ \t]*(?:الرابط:[ \t]*)?{url}[ \t]*(?=\n|\Z)"
    return re.sub(url, "", re.sub(line, "", text))


def invoice_text(invoice) -> str:
    """نصُّ الورقة كما يدخل `body` الرسالة — بلا رمزٍ جديدٍ في القوالب.

    **ونصُّ الإشعار الدائن ليس نصَّ فاتورة** (#282/أ٢/١): «المبلغ … — الاستحقاق»
    مطالبةٌ، والإشعارُ يقول «لصالحك» ويسمّي **الفاتورةَ الأصل** التي يخصمها —
    نصٌّ بلا أصله يقرأ خصماً بلا مرجع.
    """
    if invoice is None:
        return ""
    if invoice["kind"] == FEE_INVOICE_KIND_CREDIT_NOTE:
        headline = f"{invoice['title']} {invoice['number']}"
        if invoice.get("original_number"):
            headline = f"{headline} — عن الفاتورة {invoice['original_number']}"
        parts = [headline]
        parts.append(f"المبلغ: {invoice['total']} — لصالحك")
        if invoice.get("reason"):
            parts.append(f"السبب: {invoice['reason']}")
    else:
        parts = [f"{invoice['title']} {invoice['number']}"]
        parts.append(
            f"المبلغ: {invoice['total']} — الاستحقاق: {invoice['due_on']}"
        )
    if invoice.get("url"):
        parts.append(f"الرابط: {invoice['url']}")
    return "\n".join(parts)
