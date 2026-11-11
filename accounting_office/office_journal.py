"""القيدُ التلقائيُّ في دفاتر المكتب — الدفعاتُ والشطب (#284، الجزء أ).

**لماذا وحدةٌ مستقلّة:** `payments.py` يملك مالَ المكتب («اللي عليه» والتخصيصَ
والشطب)، والدفاترُ ملكُ `accounting`. الجسرُ بينهما هنا وحده: `payments` ينادي
دالّةً واحدةً بعد إنشاء الصفّ، والـview لا يعرف شيئاً عن القيود، والحسابُ
يُحلّ من شجرة الشركة لا من قائمةٍ في الكود.

**والقيدان اثنان، لكلٍّ مرجعُه الخاصّ (idempotent على `(النوع، المعرّف)`):**

    دفعةٌ:  مدينٌ حسابُ طريقة الدفع  ÷  دائنٌ الذمّمُ المدينة  [وسمُ الطرف]
    شطبٌ:   مدينٌ حسابُ الشطب        ÷  دائنٌ الذمّمُ المدينة  [وسمُ الطرف]

**ووسمُ الطرف على سطر الذمّم وحده** — `accounting/services.py` (`post_journal`)
يرفض وسمَ طرفٍ على حسابٍ ليس ذمّته، لأن سطرَ صندوقٍ موسومٍ بالطرف يُلغي سطرَ
ذمّته في كشف حسابه (رصيدٌ يقرأ صفراً وقيدٌ متوازن).

**والذرّيةُ فوق هذا كله:** الدالّتان تُناديان داخل `transaction.atomic` الذي
فتحه `payments` حول إنشاء الصفّ، فـ`ValidationError` من `post_journal` (فترةٌ
مقفلة، حسابٌ معطَّل، توازن) تُرجع الدفعةَ أو الشطبَ كلَّه — لا صفَّ مالٍ بلا
قيد. ولا `try/except` هنا: الرسالةُ العربية تصل المستخدم كما هي (هي تُترجم إلى
400 في `core/exception_handler.py`).

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
from accounting_office.models import OfficeClient

#: مفاتيحُ الإعدادات — **السجلّ هو مصدرها**، وهذه أسماءُ القراءة منها.
#: ومفتاحُ الإيراد (`office_journal_revenue_account`) ليس هنا: يُسجَّل في السجلّ
#: للجزء الثاني، ولا يقرؤه شيءٌ في هذا الجزء فلا يُدَّعى أنّه يُقرأ.
JOURNAL_ENABLED_KEY = "office_journal_enabled"
CASH_ACCOUNT_KEY = "office_journal_cash_account"
BANK_ACCOUNT_KEY = "office_journal_bank_account"
CHEQUE_ACCOUNT_KEY = "office_journal_cheque_account"
RECEIVABLE_ACCOUNT_KEY = "office_journal_receivable_account"
WRITEOFF_ACCOUNT_KEY = "office_journal_writeoff_account"

#: مرجعا القيد — بهما يُقرأ القيدُ المرحَّل وبهما يمنع `post_journal` التكرار.
REFERENCE_PAYMENT = "office_fee_payment"
REFERENCE_WRITEOFF = "office_fee_writeoff"

#: حسابُ المدين لكل طريقة دفع — «بطاقة» تُقبض في البنك لا في الصندوق، والشيكُ
#: الورقةُ في اليد لا نقداً (نفسُ تفريق `accounting/api.py` — `money_account_kind`).
METHOD_ACCOUNT_KEYS: dict[str, str] = {
    "cash": CASH_ACCOUNT_KEY,
    "bank": BANK_ACCOUNT_KEY,
    "transfer": BANK_ACCOUNT_KEY,
    "card": BANK_ACCOUNT_KEY,
    "cheque": CHEQUE_ACCOUNT_KEY,
}

QUANTUM = Decimal("0.01")


def _money(value) -> Decimal:
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
def _account(tenant, key):
    """حسابُ الإعداد — كودُه في شجرة الشركة وفعّال، وإلا 400 باسم المفتاح.

    الكودُ لا يُقبل على الثقة: كودٌ غائبٌ أو معطَّلٌ كان يُسقِط القيدَ عند
    `post_journal` برسالةٍ لا تقول أيَّ إعدادٍ يُصلَح، أو — أسوأ — يُرحّل إلى
    حسابٍ آخر مطابقٍ بالاسم. فالفحصُ هنا، والرسالةُ تسمّي المفتاحَ والكود.
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
    account = accounting_api.get_account_by_code(tenant, code)
    if account is None:
        raise ValidationError({
            key: (
                f"«{definition.label}»: لا حسابَ بالكود «{code}» في شجرة حسابات "
                "المكتب."
            ),
        })
    if not account.is_active:
        raise ValidationError({
            key: (
                f"«{definition.label}»: الحساب «{code} {account.name}» معطَّل — "
                "فعّله أو اختر كوداً آخر."
            ),
        })
    return account


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
