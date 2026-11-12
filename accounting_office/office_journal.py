"""القيدُ التلقائيُّ في دفاتر المكتب — الفواتيرُ والدفعاتُ والإشعارُ الدائن (#284).

**لماذا وحدةٌ مستقلّة:** `payments.py` يملك مالَ المكتب («اللي عليه» والتخصيصَ
والشطب)، و`fee_invoices.py` يملك المستندَ المرقَّم، والدفاترُ ملكُ `accounting`.
الجسرُ بينهما هنا وحده: كلُّ وحدةٍ تنادي دالّةً واحدةً بعد حفظ الصفّ، والـview لا
يعرف شيئاً عن القيود، والحسابُ يُحلّ من شجرة الشركة لا من قائمةٍ في الكود.

**وخمسةُ قيودٍ، لكلٍّ مرجعُه الخاصّ (idempotent على `(النوع، المعرّف)`):**

    فاتورةٌ:  مدينٌ الذمّمُ المدينة        ÷ دائنٌ الإيراد + دائنٌ ض.ق.م المخرجات
    إشعارٌ:   مدينٌ الإيراد + مدينٌ الضريبة ÷ دائنٌ الذمّمُ المدينة
    دفعةٌ:    مدينٌ حسابُ طريقة الدفع      ÷ دائنٌ الذمّمُ المدينة
    شطبٌ:     مدينٌ حسابُ الشطب            ÷ دائنٌ الذمّمُ المدينة
    إلغاءٌ:   عكسُ قيدِ المستندِ الملغى بالبنود نفسها معكوسةً (#292)

و**التكميليةُ تُرحَّل بقيد الفاتورة نفسِه** (`post_invoice_journal`) لا بقيدٍ منفصل
لها: هي مطالبةٌ صادرةٌ كالأصل في بنودها، وتفترق عنه في المرجع وحده.

**ووسمُ الطرف على سطر الذمّم وحده** — `accounting/services.py` (`post_journal`)
يرفض وسمَ طرفٍ على حسابٍ ليس ذمّته، لأن سطرَ صندوقٍ أو إيرادٍ موسومٍ بالطرف يُلغي
سطرَ ذمّته في كشف حسابه (رصيدٌ يقرأ صفراً وقيدٌ متوازن).

**والقيدُ الضريبيُّ شرطان لا واحد**: أن يكون المكتبُ «مشتغلاً مرخّصاً»
(`office_licensed_dealer`) وأن تكون ضريبةُ الورقة أكبرَ من صفر. والقيدان يتّفقان
لحظةَ الإصدار بطبيعتهما — `issue_for_draft` يُصفّر النسبةَ لمكتبٍ غير مرخّص
فتصير `tax_total` صفراً — والفحصُ الثاني حارسٌ على صفٍّ كُتب بغير هذا المسار.
**والشرطُ الأوّل لا يحكم إلا الإصدار**: الإشعارُ الدائنُ والفاتورةُ التكميليةُ
تقرآن اللقطةَ المثبتةَ على المستند (`enforce_licence=False`)، فإطفاءُ المفتاح
بعد الإصدار لا يُسقِط سطراً أثبته الأصلُ فتخرج قيودُها غيرَ متوازنة.

**والذرّيةُ فوق هذا كله:** الدوالُّ تُنادَى داخل `transaction.atomic` الذي فتحه
`payments` (الدفعة/الشطب) أو `fee_invoices` (الإصدار/الإشعار)، فـ`ValidationError`
من `post_journal` (فترةٌ مقفلة، حسابٌ معطَّل، توازن) تُرجع الصفَّ كلَّه — لا صفَّ
مالٍ ولا مستندَ مرقَّمٍ بلا قيده. ولا `try/except` هنا: الرسالةُ العربية تصل
المستخدم كما هي (هي تُترجم إلى 400 في `core/exception_handler.py`).

**و«اعتمد الكل» يُرحّل قيودَه أيضاً**: `issue_for_drafts` يُنشئ صفوفَ الفواتير
بـ`bulk_create` (قراءةُ المسودّات وبنودها ثابتةٌ لا تكبر بعددها)، ثم يُنادي
`post_invoice_journal` **مرّةً لكل صفّ** داخل المعاملة نفسها — الصافي والضريبةُ
من `total`/`tax_total` على الصفّ لا من بنود مسودّته. فهو نموُّ الكلفة الوحيدُ في
ذلك المسار، وثمنُ «لا فاتورةَ مرقَّمةً بلا قيدها»: القيدُ صفٌّ ماليٌّ لكل مستند،
ولا `post_journal` جماعيٌّ في المستودع.

**ولا استيرادَ من `accounting.models`** (عقد `importlinter`
`no-direct-accounting-models`): القراءةُ بالكود عبر `accounting.api.py`
(`get_account_by_code`، `posted_journal_ids_by_reference`)، والكتابةُ عبر
`accounting.services.py` (`post_journal`)، وإنشاءُ الشيك عبر واجهةٍ عامةٍ
أُضيفت لهذا الغرض (`accounting/api.py` — `ensure_incoming_cheque`).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting import api as accounting_api
from accounting import services as accounting_services
from accounting_office import services
from accounting_office import settings_registry
from accounting_office.models import FEE_INVOICE_KIND_CREDIT_NOTE, OfficeClient
from core.terminology import term as tenant_term

#: مفاتيحُ الإعدادات — **السجلّ هو مصدرها**، وهذه أسماءُ القراءة منها.
JOURNAL_ENABLED_KEY = "office_journal_enabled"
CASH_ACCOUNT_KEY = "office_journal_cash_account"
BANK_ACCOUNT_KEY = "office_journal_bank_account"
CHEQUE_ACCOUNT_KEY = "office_journal_cheque_account"
RECEIVABLE_ACCOUNT_KEY = "office_journal_receivable_account"
#: أوّلُ قارئٍ لحساب الإيراد: كان مسجَّلاً في السجلّ بلا مستهلك حتى #284/ب.
REVENUE_ACCOUNT_KEY = "office_journal_revenue_account"
WRITEOFF_ACCOUNT_KEY = "office_journal_writeoff_account"

#: حسابُ ض.ق.م المخرجات — **ثابتُ `accounting.services` القائم** لا نصٌّ جديد:
#: `REVENUE_VOUCHER_VAT_OUTPUT_CODE` هو ما يكتب عليه سندُ الإيراد وتقرؤه تقاريرُ
#: الضريبة، فنسخةٌ ثانية من «2104» تفترق عنه بأوّل تغيير. **ولا إعدادَ له**:
#: ليس مالاً يملكه المكتب مثل الصندوق والبنك، بل الالتزامُ الضريبيُّ الوحيد في
#: الشجرة، وكودٌ يكتبه المكتب غلطاً يُسقِط القيدَ في صمت.
TAX_OUTPUT_ACCOUNT_CODE = accounting_services.REVENUE_VOUCHER_VAT_OUTPUT_CODE
TAX_OUTPUT_ACCOUNT_LABEL = "ضريبة القيمة المضافة - مخرجات"

#: مراجعُ القيود — بها يُقرأ القيدُ المرحَّل وبهما يمنع `post_journal` التكرار.
REFERENCE_INVOICE = "office_fee_invoice"
REFERENCE_CREDIT_NOTE = "office_fee_credit_note"
REFERENCE_PAYMENT = "office_fee_payment"
REFERENCE_WRITEOFF = "office_fee_writeoff"
#: **عكسُ قيدِ مستندٍ أُلغي** — مرجعٌ ثالثٌ لمعرّف الورقة نفسِه، وإلا اصطدم
#: بالقيد الأصليّ في `idempotent` فلم يُرحَّل عكسٌ أصلاً (#292).
REFERENCE_INVOICE_CANCEL = "office_fee_invoice_cancel"


#: حسابُ المدين لكل طريقة دفع — «بطاقة» تُقبض في البنك لا في الصندوق، والشيكُ
#: الورقةُ في اليد لا نقداً (نفسُ تفريق `accounting/api.py` — `money_account_kind`).
#: **والطرقُ الأربعُ المعلَنة وحدها** (`cash`/`cheque`/`transfer`/`card`): مفتاحٌ
#: لطريقةٍ لا يمكن اختيارها يَعِد بما لا يقع، والمجهولةُ يردّها `_method_account_key`.
METHOD_ACCOUNT_KEYS: dict[str, str] = {
    "cash": CASH_ACCOUNT_KEY,
    "transfer": BANK_ACCOUNT_KEY,
    "card": BANK_ACCOUNT_KEY,
    "cheque": CHEQUE_ACCOUNT_KEY,
}

QUANTUM = Decimal("0.01")
ZERO = Decimal("0.00")

#: اسمُ حساب الديون المعدومة وأبوه — يُنشأ عند أوّل شطب (انظر
#: `ensure_writeoff_account`). والكودُ في السجلّ (`WRITEOFF_ACCOUNT_CODE`) لأنه
#: افتراضُ إعدادٍ يُعرَض للمكتب.
WRITEOFF_ACCOUNT_NAME = "ديون معدومة (Bad Debts)"
WRITEOFF_ACCOUNT_PARENT_CODE = "52"


def _money(value) -> Decimal:
    """تقريبٌ إلى خانتين — **نسخةٌ من `payments._money` لا استيرادٌ لها**.

    الوحدةُ يستوردها `payments` (نداءُ القيد)، فاستيرادُها منه دورةُ استيراد. ونسخةُ
    سطرٍ واحدٍ لا تُكرّر قاعدة: لو صار التقريبُ سياسةً (خاناتٌ أو عملة) انتقلت إلى
    `payments` أو إلى `core`.
    """
    return Decimal(str(value)).quantize(QUANTUM)


def _tenant_id(tenant) -> int:
    """معرّفُ الشركة من كائنها أو من رقمها — الدوالُّ تقبل الاثنين."""
    return getattr(tenant, "pk", tenant)


# ── البوّابة: هل يُرحَّل شيءٌ أصلاً؟ ──────────────────────────────────────────
def journaling_enabled(tenant) -> bool:
    """مفتاحُ المكتب — مطفأً لا قيدَ ولا شيك، والدفعةُ والشطبُ يُسجَّلان عاديًّا."""
    return bool(services.resolve_setting(tenant, JOURNAL_ENABLED_KEY))


# ── الطرف: قيدٌ واحد لكل زبون، ويُنشأ عند أوّل قيد ───────────────────────────
def partner_for(client):
    """طرفُ الزبون في الدفاتر — القائمَ أو يُنشأ ويُربط، **مرّةً واحدة**.

    **المفتاحُ `partner_id` على الزبون وحده** ولا مطابقةَ بالاسم: لا فرادةَ على
    `Partner.name` في القاعدة، ومطابقةُ الاسم تخلط «شركة النور» ب«شركة النور»
    أخرى فيصير رصيدُ إحداهما على الأخرى بلا خطأٍ يُرى.

    **والقفلُ على صفّ الزبون** لأن الربطَ كتابةُ سباقٍ حقيقية: نداءان متزامنان
    (دفعتان في اللحظة نفسها) كانا يُنشئان طرفين ويُربطان واحداً — فيبقى طرفٌ
    بهذا الاسم بلا زبونٍ يشير إليه. القفلُ يجعل الثاني يرى `partner_id` مكتوباً.
    """
    with transaction.atomic():
        locked = OfficeClient.objects.select_for_update().get(pk=client.pk)
        if locked.partner_id:
            client.partner_id = locked.partner_id
            return locked.partner
        partner = _create_partner(locked)
        locked.partner = partner
        locked.save(update_fields=["partner"])
        client.partner_id = partner.pk
        return partner


def _create_partner(client):
    """طرفٌ زبونٌ جديد باسم الزبون — والحسابُ المحاسبيّ يُنشأ له تلقائياً.

    `partners` يربط الطرفَ بحساب ذمّته في `post_save`
    (`accounting/api.py` — `sync_partner_accounting`)، فلا نكتب حساباً هنا.
    والاسمُ يُقصّ عند حدّ عمود الطرف (150) لأن اسمَ الزبون يُقبل حتى 200.
    """
    from partners.models import Partner

    return Partner.objects.create(
        tenant_id=client.tenant_id,
        name=client.name[:150],
        partner_type="Customer",
    )


# ── الحسابات: من شجرة الشركة بالكود، أو 400 يُسمّي المفتاح ────────────────────
def _account_by_code(tenant, code, *, key, label):
    """حسابٌ بكودٍ صريح — وفعّال، وإلا 400 بمفتاحه وكوده.

    الكودُ لا يُقبل على الثقة: كودٌ غائبٌ أو معطَّلٌ كان يُسقِط القيدَ عند
    `post_journal` برسالةٍ لا تقول أيَّ إعدادٍ يُصلَح، أو — أسوأ — يُرحّل إلى
    حسابٍ آخر مطابقٍ بالاسم. فالفحصُ هنا، والرسالةُ تسمّي المفتاحَ والكود.
    """
    account = accounting_api.get_account_by_code(tenant, str(code).strip())
    if account is None:
        raise ValidationError({
            key: (
                f"«{label}»: لا حسابَ بالكود «{code}» في شجرة حسابات "
                "المكتب."
            ),
        })
    if not account.is_active:
        raise ValidationError({
            key: (
                f"«{label}»: الحساب «{code} {account.name}» معطَّل — "
                "فعّله أو اختر كوداً آخر."
            ),
        })
    return account


def _account(tenant, key):
    """حسابُ الإعداد — كودُه في السجلّ، ويُحلّ بـ`_account_by_code`.

    والرسائلُ واحدةٌ للاثنين: مفتاحُ الإعداد وكودٌ ثابت (حسابُ الضريبة) يردّان
    بالشكل نفسه، فلا رسالتان تفترقان عند أوّل تعديل.
    """
    definition = settings_registry.get_definition(key)
    code = str(services.resolve_setting(tenant, key) or "").strip()
    if not code:
        raise ValidationError({
            key: (
                f"«{definition.label}» غير مضبوط — عيّن كودَ حسابٍ له في إعدادات "
                "المكتب قبل ترحيل القيد."
            ),
        })
    return _account_by_code(tenant, code, key=key, label=definition.label)


# ── الفاتورةُ الورقية: أوّلُ قارئٍ لحساب الإيراد ──────────────────────────────
def _licensed_dealer(tenant) -> bool:
    """«المكتب مشتغل مرخّص» — **قاعدةٌ واحدة** في `fee_invoices` لا نسخةً هنا.

    والاستيرادُ داخل الدالّة يفكّ دورةً حقيقيّة: `fee_invoices` يستورد هذه الوحدة
    في أعلاه (نداءُ القيد عند الإصدار)، فاستيرادُها في الأعلى يدير الدورةَ عند
    أوّل تحميل. والنداءُ يقع عند الترحيل وحده.
    """
    from accounting_office import fee_invoices

    return fee_invoices.office_is_licensed(tenant)


def _tax_account(tenant, tax_total, *, enforce_licence=True):
    """حسابُ ض.ق.م المخرجات أو `None` — **سطرٌ يُزاد أو يُغفل**.

    `None` في حالتين لا ثالثة: مكتبٌ غيرُ مشتغلٍ مرخّص، أو ضريبةٌ صفر. فالقيدُ
    يبقى متوازناً في الحالين، وورقةٌ بلا سطر ضريبةٍ لا يُخترع لها سطرٌ في الدفاتر.

    **و`enforce_licence=False` حيث تكون الضريبةُ لقطةَ مستندٍ صدر**: العكسُ
    والإشعارُ الدائنُ والتكميليةُ (#282fix/٢) — الضريبةُ هناك **مُثبتةٌ على مستندٍ
    صدر** (`tax_total`/`tax_percent` على الصفّ)، ومفتاحُ الترخيص قد يكون أُطفئ
    بعد الإصدار — وإسقاطُ سطرها يترك مدينَ الإيراد وحدَه في مقابل دائن الذمّة
    بالإجمالي فلا يتوازن القيدُ أصلاً. فالسطرُ يُكتب لأنّه كُتب، والترخيصُ يحكم
    الإصدارَ لا تصحيحَه.
    """
    if _money(tax_total) <= ZERO:
        return None
    if enforce_licence and not _licensed_dealer(tenant):
        return None
    return _account_by_code(
        tenant,
        TAX_OUTPUT_ACCOUNT_CODE,
        key=TAX_OUTPUT_ACCOUNT_CODE,
        label=TAX_OUTPUT_ACCOUNT_LABEL,
    )


def post_invoice_journal(invoice, *, actor, enforce_licence=True):
    """قيدُ الفاتورة: مدينٌ الذمّمُ المدينة بإجماليها، دائنٌ الإيرادُ والضريبة.

    **الإجماليُّ مدينٌ مرّةً واحدة**: الصافيُّ إلى `4102` والضريبةُ إلى `2104`،
    ومجموعُهما إجماليُ الورقة — فسطرُ الذمّة يقرأ ما يطلبه المكتبُ من الزبون
    بالضبط، وتقريرُ الضريبة يقرأ نصيبَه من القيد نفسه لا من حسابٍ موازٍ.

    والتاريخُ يومُ الإصدار لا يومُ الترحيل — وهما واحدٌ هنا لأن النداء داخل
    معاملة الإصدار، ولو تأخّر لغيره صار للورقة تاريخان يفترقان في الفترة.

    **و`enforce_licence=False` للفاتورة التكميلية وحدها** (#282fix/٢): مفتاحُ
    «المشتغل المرخّص» يحكم **الإصدار** — ورقمُ التكميلية يُنشأ في `_issue_correction`
    على لقطة الأصل ضريبةً ونسبةً، فقد يكون المفتاحُ أُطفئ بعدُ. وإسقاطُ سطرها
    يترك مدينَ الذمّة بالإجمالي في مقابل دائن الإيراد بالصافي وحده فلا يتوازن
    القيدُ أصلاً. فالسطرُ يُكتب لأنّ الأصل أثبته، والمفتاحُ لا يحكم تصحيحاً.

    تُعيد القيدَ (قائماً إن كان `idempotent`)، أو `None` حين يكون الترحيل مطفأً
    **أو إجماليُ الورقة صفراً**: `post_journal` يرفض قيداً صفريّاً
    («cannot be empty»)، وورقةُ صفرٍ لا أثرَ لها في الدفاتر — فلا تُسقِط الإصدارَ
    برسالةٍ لا يفهمها الموظّف ولا تخصّ ورقتَه.
    """
    tenant = invoice.tenant
    if not journaling_enabled(tenant):
        return None
    client = invoice.client
    total = _money(invoice.total)
    if total <= ZERO:
        return None
    partner = partner_for(client)
    receivable_account = _account(tenant, RECEIVABLE_ACCOUNT_KEY)
    revenue_account = _account(tenant, REVENUE_ACCOUNT_KEY)
    net = _money(invoice.net_total)
    tax_total = _money(invoice.tax_total)
    lines_data = [
        {
            "account": receivable_account.pk,
            "debit": total,
            "credit": ZERO,
            "partner": partner.pk,
            "description": f"ذمّة {client.name} — فاتورة {invoice.number}",
        },
        {
            "account": revenue_account.pk,
            "debit": ZERO,
            "credit": net,
            "partner": None,
            "description": f"إيراد أتعاب — فاتورة {invoice.number}",
        },
    ]
    tax_account = _tax_account(
        tenant, tax_total, enforce_licence=enforce_licence,
    )
    if tax_account is not None:
        lines_data.append({
            "account": tax_account.pk,
            "debit": ZERO,
            "credit": tax_total,
            "partner": None,
            "description": f"ضريبة مخرجات — فاتورة {invoice.number}",
        })
    return accounting_services.post_journal(
        tenant_id=_tenant_id(tenant),
        transaction_date=timezone.localdate(invoice.issued_at),
        reference_type=REFERENCE_INVOICE,
        reference_id=invoice.pk,
        # اسمُ المستند من معجم الشركة لا حرفياً (حارس `test_terminology_guard`):
        # قالبُ مكتب المحاسبة يسمّيها «أتعاب»، وغيره باسمه العامّ.
        description=(
            f"{tenant_term(tenant, 'doc.sales_invoice')} {invoice.number} — "
            f"{client.name}"
        ),
        lines_data=lines_data,
        user=actor,
        idempotent=True,
    )


def post_credit_note_journal(note, *, actor):
    """قيدُ الإشعار الدائن — **عكسُ قيد الفاتورة** بالأسطر نفسها معكوسةً.

    مدينٌ الإيرادُ بصافيه وض.ق.م المخرجات بنصيبها، دائنٌ الذمّمُ المدينة
    بإجمالي الإشعار بوسم الطرف: الإشعارُ يخصم من `4102` ومن `2104` بقدر ما
    أثبته الأصل، ويسقط عن الزبون ما لم يعد عليه.

    **والوسمُ على الذمّة وحدها**: سطرُ إيرادٍ موسومٌ بالطرف يُلغي سطرَ ذمّته في
    كشف حسابه، وهو ما يرفضه `post_journal` أصلاً.

    **وسطرُ ضريبتها يتبع لقطةَ الأصل لا المفتاح الحيّ** (#282fix/٢):
    `enforce_licence=False`، لأن مبلغَ الإشعار ونسبتَه من لقطة الأصل (انظر
    `fee_invoices._issue_correction`) — وإطفاءُ المفتاح بعد الإصدار كان يُسقط
    السطرَ فيخرج القيدُ غيرَ متوازن ويُرفَض الإشعارُ كلُّه.

    وتُندى عند إنشاء الإشعار داخل معاملة `fee_invoices._issue_correction`،
    فإشعارٌ لا يُرحّل لا يُنشأ.
    """
    tenant = note.tenant
    if not journaling_enabled(tenant):
        return None
    client = note.client
    partner = partner_for(client)
    receivable_account = _account(tenant, RECEIVABLE_ACCOUNT_KEY)
    revenue_account = _account(tenant, REVENUE_ACCOUNT_KEY)
    total = _money(note.total)
    net = _money(note.net_total)
    tax_total = _money(note.tax_total)
    lines_data = [
        {
            "account": revenue_account.pk,
            "debit": net,
            "credit": ZERO,
            "partner": None,
            "description": f"خصم إيراد — إشعار {note.number}",
        },
    ]
    tax_account = _tax_account(tenant, tax_total, enforce_licence=False)
    if tax_account is not None:
        lines_data.append({
            "account": tax_account.pk,
            "debit": tax_total,
            "credit": ZERO,
            "partner": None,
            "description": f"خصم ضريبة مخرجات — إشعار {note.number}",
        })
    lines_data.append({
        "account": receivable_account.pk,
        "debit": ZERO,
        "credit": total,
        "partner": partner.pk,
        "description": f"ذمّة {client.name} — إشعار دائن {note.number}",
    })
    return accounting_services.post_journal(
        tenant_id=_tenant_id(tenant),
        transaction_date=timezone.localdate(note.issued_at),
        reference_type=REFERENCE_CREDIT_NOTE,
        reference_id=note.pk,
        description=f"إشعار دائن {note.number} — {client.name}",
        lines_data=lines_data,
        user=actor,
        idempotent=True,
    )


# ── الإلغاء: عكسُ قيدِ المستند الصادر ────────────────────────────────────────
def _document_reference_type(document) -> str:
    """مرجعُ **قيد المستند نفسِه** — الإشعارُ الدائنُ على سلسلته، وغيرهما على الفواتير."""
    return (
        REFERENCE_CREDIT_NOTE
        if document.kind == FEE_INVOICE_KIND_CREDIT_NOTE
        else REFERENCE_INVOICE
    )


def post_invoice_reversal_journal(document, *, actor, day=None):
    """قيدُ عكسِ مستندٍ صادرٍ أُلغي: **بنودُه نفسُها معكوسةً** (#292).

    فاتورةٌ (أو تكميلية) أُلغيت ⇒ دائنٌ الذمّمُ المدينة بإجماليها بوسم الطرف،
    مدينٌ الإيرادُ بصافيه وض.ق.م المخرجات بنصيبها. وإشعارٌ دائنٌ أُلغي ⇒ عكسُ
    عكسِه: مدينٌ الذمّةُ، دائنٌ الإيرادُ والضريبة. فالذمّةُ تعود إلى ما كانت عليه
    قبل المستند بالضبط، ولا يبقى على الزبون أثرُ ورقةٍ أُلغيت.

    **والتاريخُ يومُ الإلغاء لا يومُ الإصدار**: العكسُ حركةٌ وقعت الآن، وإلحاقُه
    بفترةٍ قد تكون مقفلةً كان يرفض الإلغاءَ بلا سببٍ يفهمه الموظّف. و`day` تُمرَّر
    في الاختبار وحده.

    **ولا حذفَ ولا تعديلَ لقيد**: `post_journal` لا يعرف الحذف، وقيدُ الأصل يبقى
    مرحَّلاً بتاريخه — فالسجلُّ يقول «صدرت ثم أُلغيت» لا «لم تصدر».

    **ولا عكسَ بلا أصل:** مكتبٌ أطفأ الترحيلَ وقتَ الإصدار لا قيدَ لورقته، فعكسٌ
    يُكتب اليوم يُدائن ذمّاً لم تُدَن (رصيدٌ سالبٌ لا يُقرأ). والفحصُ بمرجع
    المستند في `accounting` لا بتخمين — والإعدادُ المطفأُ يُصان كما في الإصدار.

    تُعيد القيدَ (قائماً إن كان `idempotent`)، أو `None` حين يكون الترحيلُ مطفأً
    أو لا قيدَ أصليّاً. والنداءُ الثاني لا يقع أصلاً: `cancel_invoice` يرفض الملغاة.
    """
    tenant = document.tenant
    if not journaling_enabled(tenant):
        return None
    original = accounting_api.posted_journal_ids_by_reference(
        _tenant_id(tenant), _document_reference_type(document), [document.pk],
    )
    if not original:
        return None
    total = _money(document.total)
    if total <= ZERO:
        return None
    client = document.client
    partner = partner_for(client)
    receivable_account = _account(tenant, RECEIVABLE_ACCOUNT_KEY)
    revenue_account = _account(tenant, REVENUE_ACCOUNT_KEY)
    net = _money(document.net_total)
    tax_total = _money(document.tax_total)
    # الإشارةُ من نوع المستند: عكسُ الإشعار الدائن مدينٌ للذمّة، وعكسُ الفاتورة دائنٌ لها.
    credit_note = document.kind == FEE_INVOICE_KIND_CREDIT_NOTE
    label = "إشعار دائن" if credit_note else tenant_term(tenant, "doc.sales_invoice")
    lines_data = [
        {
            "account": receivable_account.pk,
            "debit": total if credit_note else ZERO,
            "credit": ZERO if credit_note else total,
            "partner": partner.pk,
            "description": f"عكس ذمّة {client.name} — إلغاء {label} {document.number}",
        },
        {
            "account": revenue_account.pk,
            "debit": ZERO if credit_note else net,
            "credit": net if credit_note else ZERO,
            "partner": None,
            "description": f"عكس إيراد — إلغاء {label} {document.number}",
        },
    ]
    tax_account = _tax_account(tenant, tax_total, enforce_licence=False)
    if tax_account is not None:
        lines_data.append({
            "account": tax_account.pk,
            "debit": ZERO if credit_note else tax_total,
            "credit": tax_total if credit_note else ZERO,
            "partner": None,
            "description": f"عكس ضريبة مخرجات — إلغاء {label} {document.number}",
        })
    return accounting_services.post_journal(
        tenant_id=_tenant_id(tenant),
        transaction_date=day or timezone.localdate(),
        reference_type=REFERENCE_INVOICE_CANCEL,
        reference_id=document.pk,
        description=f"إلغاء {label} {document.number} — {client.name}",
        lines_data=lines_data,
        user=actor,
        idempotent=True,
    )


# ── الدفعة ───────────────────────────────────────────────────────────────────
def post_payment_journal(payment, *, actor):
    """قيدُ الدفعة: مدينٌ حسابُ طريقة الدفع، دائنٌ الذمّمُ المدينة بوسم الطرف.

    `transaction_date` تاريخُ الدفع نفسه لا تاريخُ الإدخال: الدفعةُ عن شهرٍ
    سابقٍ تخصّ فترتَه، وإلا اختلفت الدفاترُ عن الإشعار الصادر للزبون.

    **والشيكُ يسبق القيد**: ورقةٌ بحالة «مسودّة» على رقم الإشعار نفسه، يُنشئها
    `accounting.api` بمفتاح (الشركة، الرقم) فلا تتكرر. ولو رُحِّل القيدُ ثم فشل
    إنشاءُ الورقة لبقيت الدفعةُ بقيدٍ بلا شيكٍ في المحفظة (أو العكس) — والذرّيةُ
    في `payments.create_payment` تُرجع الاثنين معاً.

    تُعيد القيدَ (قائماً إن كان `idempotent`)، أو `None` حين يكون الترحيل مطفأً.
    """
    tenant = payment.tenant
    if not journaling_enabled(tenant):
        return None
    client = payment.client
    partner = partner_for(client)
    amount = _money(payment.amount)
    debit_account = _account(tenant, _method_account_key(payment.method))
    receivable_account = _account(tenant, RECEIVABLE_ACCOUNT_KEY)
    description = f"قبض دفعة أتعاب {payment.receipt_number} من {client.name}"
    if payment.method == "cheque":
        accounting_api.ensure_incoming_cheque(
            tenant=tenant,
            cheque_number=payment.receipt_number,
            amount=amount,
            partner=partner,
            user=actor,
        )
    return accounting_services.post_journal(
        tenant_id=_tenant_id(tenant),
        transaction_date=payment.paid_at,
        reference_type=REFERENCE_PAYMENT,
        reference_id=payment.pk,
        description=description,
        lines_data=[
            {
                "account": debit_account.pk,
                "debit": amount,
                "credit": Decimal("0.00"),
                "partner": None,
                "description": f"قبض {payment.receipt_number}",
            },
            {
                "account": receivable_account.pk,
                "debit": Decimal("0.00"),
                "credit": amount,
                "partner": partner.pk,
                "description": f"ذمّة {client.name} — دفعة {payment.receipt_number}",
            },
        ],
        user=actor,
        idempotent=True,
    )


def _method_account_key(method) -> str:
    """مفتاحُ حساب طريقة الدفع — وطريقةٌ خارج القائمة خطأُ مناداةٍ لا صمت."""
    key = METHOD_ACCOUNT_KEYS.get(method)
    if key is None:
        raise ValidationError({"method": "طريقةُ دفعٍ بلا حسابِ دفعٍ معروف."})
    return key


# ── حسابُ الديون المعدومة: يُقرأ أو يُنشأ ────────────────────────────────────
def ensure_writeoff_account(tenant):
    """حسابُ مصروف الديون المعدومة — القائمَ أو يُنشأ تحت «52»، **مرّةً واحدة**.

    **لا بذرةَ تحمله**: لا `COA_DATA` ولا `ACCOUNTING_FIRM_COA` فيه حسابُ ديونٍ
    معدومة (تحقّقٌ مكتوب في `accounting_office/tests/test_office_journal.py`)،
    فافتراضُ كودٍ غيرِ موجودٍ كان يجعل الشطبَ يردّ 400 في **كل** مكتب — وهو بندٌ
    من التذكرة لا اختيارٌ للمكتب. فالحسابُ يُنشأ عند الحاجة بـ
    `accounting.api.ensure_account` (نمط «الحسابُ يُنشأ من الكود ويُثبَّت في
    الإعدادات»، نفسه في حسابات الشيكات).

    **ولا يُنشأ لكودٍ صريحٍ كتبه المكتب**: كودٌ مغايرٌ للافتراضيّ ولا حسابَ له
    يبقى خطأً يُرفَض 400 باسم المفتاح — إنشاءُ حسابٍ باسم «ديون معدومة» بكودٍ
    مكتوبٍ غلطاً يُخفي الغلطةَ بدل أن يقولها.

    و`ensure_account` بـ`get_or_create` على (الشركة، الكود)، فنداءٌ ثانٍ — أو
    شطبٌ ثانٍ — لا يُنشئ حساباً ثانياً.
    """
    code = str(services.resolve_setting(tenant, WRITEOFF_ACCOUNT_KEY) or "").strip()
    if not code:
        return None
    existing = accounting_api.get_account_by_code(tenant, code)
    if existing is not None:
        return existing
    if code != settings_registry.WRITEOFF_ACCOUNT_CODE:
        return None  # كودُ المكتب الغائب — يرفضه `_account` برسالته
    return accounting_api.ensure_account(
        tenant_id=_tenant_id(tenant),
        code=code,
        name=WRITEOFF_ACCOUNT_NAME,
        account_type="Expense",
        parent_code=WRITEOFF_ACCOUNT_PARENT_CODE,
    )


# ── الشطب ───────────────────────────────────────────────────────────────────
def post_writeoff_journal(write_off, *, actor):
    """قيدُ الشطب: مدينٌ حسابُ الديون المعدومة، دائنٌ الذمّمُ المدينة بوسم الطرف.

    والتاريخُ تاريخُ الشطب (`created_at` في **التاريخ المحلّي** لا UTC): شطبٌ في
    الواحدة صباحاً بتوقيت المكتب يخصّ يومَه لا أمسَ. و`timezone.localdate` هي
    القاعدةُ نفسُها التي تحوّل بها `after_sales/service_orders.py` (`_local_date`)
    — و`.date()` على لحظةٍ واعيةٍ بـUTC تنزلق يوماً في أوّل ساعتين محلّيّاً.

    والشطبُ لا يمسّ قيدَ الدفعة: دفعةٌ قُبضت ثم شُطب باقيها يبقيان قيدين —
    الأولُ مالٌ دخل، والثاني تنازلٌ عن دين. ودمجُهما يُخفي أثرَ القرار.
    """
    tenant = write_off.tenant
    if not journaling_enabled(tenant):
        return None
    draft = write_off.draft
    client = draft.client
    partner = partner_for(client)
    amount = _money(write_off.amount)
    # الحسابُ يُنشأ إن غاب **قبل** القيد: الشجرةُ المبذورة لا تحمل ديوناً معدومة،
    # وافتراضُ التسجيل يشير إلى كودٍ لا وجود له في شجرةٍ قياسية.
    ensure_writeoff_account(tenant)
    writeoff_account = _account(tenant, WRITEOFF_ACCOUNT_KEY)
    receivable_account = _account(tenant, RECEIVABLE_ACCOUNT_KEY)
    period = f"{draft.year}-{draft.month:02d}"
    return accounting_services.post_journal(
        tenant_id=_tenant_id(tenant),
        transaction_date=timezone.localdate(write_off.created_at),
        reference_type=REFERENCE_WRITEOFF,
        reference_id=write_off.pk,
        description=f"شطب متبقّي أتعاب {period} — {client.name}",
        lines_data=[
            {
                "account": writeoff_account.pk,
                "debit": amount,
                "credit": Decimal("0.00"),
                "partner": None,
                "description": f"شطب دين أتعاب {period} — {write_off.reason}",
            },
            {
                "account": receivable_account.pk,
                "debit": Decimal("0.00"),
                "credit": amount,
                "partner": partner.pk,
                "description": f"ذمّة {client.name} — شطب {period}",
            },
        ],
        user=actor,
        idempotent=True,
    )


# ── القراءة: هل لهذه الدفعة قيد؟ ────────────────────────────────────────────
def journal_entry_ids(tenant, payments) -> dict[int, int]:
    """{معرّفُ الدفعة: معرّفُ قيدها المرحَّل} — **استعلامٌ واحد** لصفوف القائمة.

    يقرؤها سطرُ الدفعة في `payments.payment_row` فيرى المستخدمُ أن القيد وقع.
    والدفعةُ الغائبةُ من القاموس (ترحيلٌ مطفأ، أو بياناتُ ما قبل #284) يعرضها
    `payment_row` كـ`None` صريح — الغيابُ الحقلَ لا يُقرأ في الواجهة. ولكل مرجعٍ
    قيدٌ واحدٌ بـ`idempotent`، ولو وُجد أكثرُ يُقرأ الأقدم (الترتيبُ في
    `posted_journal_ids_by_reference`).
    """
    ids = [row.pk for row in payments]
    if not ids:
        return {}
    found = accounting_api.posted_journal_ids_by_reference(
        _tenant_id(tenant), REFERENCE_PAYMENT, ids,
    )
    return {payment_id: journals[0] for payment_id, journals in found.items()}
