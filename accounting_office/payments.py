"""الدفعات و«اللي عليه» وكشف الحساب (#283، الجزء أ — الخادم).

**المالُ هنا مشتقٌّ لا مخزَّن، والاتّجاهُ واحد:**

    charges(زبون)     = Σ إجماليِّ الفواتير والتكميليات الحيّة − Σ الإشعارات الدائنة
    remaining(ورقة)   = إجماليها − Σ allocations(مسودّتها) − Σ write_offs(مسودّتها)
                        − الإشعارات الدائنة عليها
    credit(زبون)      = Σ(payment.amount − Σ allocations(payment))
    due(زبون)         = charges − Σ allocations − Σ write_offs − credit   (قد يكون سالباً)

**والمبلغُ إجماليُ الورقة لا مجموعُ المسودّة** (#292): `FeeDraft.total` قبل الضريبة،
و`FeeInvoice.total = net + tax_total`، والدفاترُ تُدين الذمّةَ بالإجمالي
(`office_journal.post_invoice_journal`). فقراءةُ المسودّة كانت تُطالب الزبونَ بـ300
وذمّتُه 348، ودفعُ 348 يُنتج رصيداً دائناً وهميّاً 48. والمسودّةُ التي لم تُصدر
ليست مستحقّاً أصلاً، والملغاةُ لم تكن يوماً (`cancelled_at`).

`client_due` هي **الصيغةُ الوحيدة**: كلُّ سطحٍ يعرض «اللي عليه» — حمولةُ الزبون،
وحمولةُ المسودّة (بمعناها الخاصّ: `remaining` على تلك الفاتورة)، ونقطةُ الدفعات،
وكشفُ الحساب — يقرأ من هنا. نسخةٌ ثانية من المعادلة في موضعٍ آخر تفترق عن الأولى
بأوّل شطبٍ أو تخصيص، ولا يراها أحد. **و`due` سالبٌ** حين يكون للزبون رصيدٌ دائن،
ولا يُقصّ إلى صفر: الصفرُ يقول «لا شيء عليه» والسالِبُ يقول «له عندنا»، وكلاهما
معلومةٌ مختلفة. و`draft`/`cancelled` لا تدخلان الحساب أصلاً — لا مسودّةَ تُستحقّ
قبل الاعتماد، والملغاةُ لم تكن يوماً.

**التخصيصُ الأقدمُ أوّلَاً** (`year, month, id`): دفعةُ الزبون تُسقِط أقدمَ فاتورةٍ
قائمةٍ عليه — عُرفُ كشف الحساب في دفترة وOdoo وQuickBooks، وليس اختياراً
جمالياً: بغيرِه يتأخّر أقدمُ دينٍ أبداً ويصير تقادُمُ الديون بلا معنى. ويُغيّره
الموظف بتخصيصٍ صريحٍ (`allocations`) حين يعرف هو ما لا يعرفه الترتيب — والمجموعُ
لا يتجاوز الدفعة، والمسودّةُ معتمدةٌ وله وللمكتب نفسه.

**والزيادةُ رصيدٌ دائنٌ مشتقّ**: لا نموذجَ رصيدٍ منفصل ⇒ لا ازدواجَ ولا انحراف.
ويُستهلك **بتخصيصٍ جديد** لا بمعادلة: عند اعتماد فاتورةٍ جديدةٍ يمرّ (بعد
التزام معاملة الاعتماد) `apply_open_credit` على دفعات الزبون ذاتِ الرصيد فيخصّصه عليها — فيبقى الكشفُ
سجلَّ صفوفٍ يُقرأ، لا حساباً يُعاد في كل طلب.

**ولا حذفَ ولا تعديل**: الدفعةُ والتخصيصُ والشطبُ صفوفٌ إلحاقيّة، والتصحيحُ صفٌّ
جديد أو شطبٌ بسببٍ مكتوب. وشطبُ المسودّة **لصاحب المكتب وحده** (`manager` لا
`office_manager` ولا المحاسب) لأنه تنازلٌ عن مالٍ لا إدخالُ حركة.

**وكلُّ مبلغٍ يمرّ بالقناع** (`fees.amounts_masked` كما في `draft_row`): من لا يملك
«يرى المبالغ» يقرأ `None` في `amount`/`paid_amount`/`written_amount`/`remaining`/`due`/`credit`/
`tax_note` — بالمفاتيح نفسها لا بمفاتيح محذوفة، على نمط `services.mask_amounts`.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404
from django.utils import timezone

from accounting_office import deadlines, fees, office_journal, services, settings_registry
from accounting_office.models import (
    FEE_DRAFT_STATUS_APPROVED,
    FEE_INVOICE_KIND_CREDIT_NOTE,
    FEE_INVOICE_KIND_INVOICE,
    FEE_INVOICE_KIND_SUPPLEMENTARY,
    FEE_PAYMENT_METHOD_CHEQUE,
    FEE_PAYMENT_METHOD_CHOICES,
    FEE_PAYMENT_METHOD_LABELS,
    OBLIGATION_BADGE_PAYMENT_RECEIVED,
    OBLIGATION_DIRECTION_REFUND,
    OBLIGATION_STATUS_NOT_REQUIRED,
    REMINDER_COUNTED_KINDS,
    FeeDraft,
    FeeInvoice,
    FeePayment,
    FeePaymentAllocation,
    FeeReceiptSequence,
    FeeStatement,
    FeeWriteOff,
    Obligation,
    assert_positive_fee_amount,
)
from core.access import MANAGER_ROLE, user_tenant_role
from core.terminology import term as tenant_term

AMOUNT_QUANTUM = Decimal("0.01")
MONEY_EXPRESSION = DecimalField(max_digits=14, decimal_places=2)

#: ترتيبُ التخصيص الافتراضيّ: **الأقدمُ أوّلَاً** — سنةٌ ثم شهرٌ ثم معرّف.
DRAFT_AGING_ORDER: tuple[str, ...] = ("year", "month", "id")

#: حالةُ الفاتورة في الكشف — **مشتقّةٌ من `remaining`** لا عموداً في المسودّة.
INVOICE_STATE_PAID = "paid"
INVOICE_STATE_PARTIAL = "partial"
INVOICE_STATE_UNPAID = "unpaid"
INVOICE_STATE_CHOICES: list[tuple[str, str]] = [
    (INVOICE_STATE_PAID, "مدفوعة"),
    (INVOICE_STATE_PARTIAL, "مدفوعة جزئياً"),
    (INVOICE_STATE_UNPAID, "غير مدفوعة"),
]
INVOICE_STATE_LABELS: dict[str, str] = dict(INVOICE_STATE_CHOICES)

#: حدودُ صفحة الكشف — الترقيمُ في الاستعلام لا في بايثون.
LEDGER_PAGE_SIZE = 50
LEDGER_MAX_PAGE_SIZE = 200

#: ── المستندان (#283/ب) ──────────────────────────────────────────────────────
#: عنوانُ الورقة ورمزُها في `docshare` **من هنا**: القالبُ والحمولةُ والنوعُ
#: تقرأ الثلاثةَ من موضع واحد، فلا يفترق عنوانُ المستند عن عنوان نوعه.
RECEIPT_TITLE = "إشعار قبض"
STATEMENT_TITLE = "كشف حساب"
RECEIPT_DOC_TYPE = "fee_receipt"
STATEMENT_DOC_TYPE = "fee_statement"

#: أنواعُ الحركة في كشف الحساب الثلاثة — وترتيبُها عند تساوي التاريخ: الفاتورةُ
#: تُنشئ الدين قبل أن تُسدّده دفعةٌ في اليوم نفسه.
MOVEMENT_KIND_INVOICE = "invoice"
MOVEMENT_KIND_PAYMENT = "payment"
MOVEMENT_KIND_WRITE_OFF = "write_off"
MOVEMENT_KIND_LABELS: dict[str, str] = {
    MOVEMENT_KIND_INVOICE: "فاتورة",
    MOVEMENT_KIND_PAYMENT: "دفعة",
    MOVEMENT_KIND_WRITE_OFF: "شطب",
}
MOVEMENT_KIND_ORDER: dict[str, int] = {
    MOVEMENT_KIND_INVOICE: 0,
    MOVEMENT_KIND_PAYMENT: 1,
    MOVEMENT_KIND_WRITE_OFF: 2,
}


# ── القناع ──────────────────────────────────────────────────────────────────
def amounts_masked(tenant, user) -> bool:
    """قرارُ القناع **مرّةً واحدة** — نفسُ `fees.amounts_masked` لا نسخةً ثانية."""
    return fees.amounts_masked(tenant, user)


def _mask(data: dict, keys=None) -> dict:
    """قناعُ حمولة: المفاتيحُ تبقى بقيمة `None` — نمطُ `fees.py` حرفياً.

    والافتراضُ **كلُّ مفاتيح المبالغ** (`services.AMOUNT_KEYS`) كـ`fees.draft_row`:
    حمولةُ كشف الحساب تحمل `total` أيضاً، وقنعُ مفاتيح الدفعات وحدها يُظهره.
    """
    return services.mask_amounts(data, keys or services.AMOUNT_KEYS)


# ── المبالغ: تنظيفٌ وتقريب ──────────────────────────────────────────────────
def _money(value, *, field="amount") -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "مبلغٌ غير صالح."}) from None
    return amount.quantize(AMOUNT_QUANTUM)


def _clean_positive_amount(value, *, field="amount") -> Decimal:
    """مبلغُ دفعةٍ/تخصيصٍ/شطب: **أكبرُ من صفر** بخانتين — أو 400 برسالته.

    **يُفحص أوّلاً ثم يُقرَّب**: الحدُّ الموجبُ وعددُ الخانات وكونُه منتهياً في
    `models.assert_positive_fee_amount` (حارسُ الحفظ) على **القيمة كما وصلت**، ثم
    `_money` تُطبّعها `Decimal`. فالتقريبُ قبل الفحص كان يقبل `100.005` و`100.015`
    بصمتٍ ويُسقط `Infinity` في `InvalidOperation` (500) لنداءٍ برمجيّ لا يمرّ
    بالمُسلسِل — ولا نسخةَ ثالثة من «مبلغٌ موجبٌ بخانتين» تفترق بين الـAPI والـORM.
    """
    assert_positive_fee_amount(value, field=field)
    return _money(value, field=field)


def _iso_date(raw, field):
    """تاريخٌ اختياريّ من نصّ ISO — الفاسدُ 400 بالحقل لا 500."""
    value = (raw or "").strip() if isinstance(raw, str) else raw
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError({field: "تاريخٌ غير صالح — الصيغة YYYY-MM-DD."}) from None


# ── الصيغةُ الوحيدة: المدفوعُ والمتبقّي على مسودّة ───────────────────────────
def _relation_sum(model, relation: str):
    """مجموعُ علاقةٍ عكسيّةٍ كاستعلامٍ فرعيٍّ — **لا `SUM` على JOIN مزدوج**.

    جمعُ التخصيصات والشطوب في `annotate` واحدٍ بالـJOIN يضرب الصفوف في بعضها
    (تخصيصان × شطان = أربعة أسطر لمجموعها ضِعفُ الحقيقة)، والاستعلامان الفرعيان
    يُبقيان المجموعين مستقلَّين.
    """
    return Coalesce(
        Subquery(
            model.objects
            .filter(**{relation: OuterRef("pk")})
            .values(relation)
            .annotate(total=Sum("amount"))
            .values("total")
            # ترتيبُ النموذج الافتراضي يُضاف إلى `ORDER BY` في `GROUP BY` هذا —
            # وMySQL بـ`ONLY_FULL_GROUP_BY` ترفض العمودَ غيرَ المجموع (1055)،
            # وSQLite تمرّ فلا يكشفه اختبار.
            .order_by()[:1],
            output_field=MONEY_EXPRESSION,
        ),
        Value(Decimal("0.00")),
        output_field=MONEY_EXPRESSION,
    )


def _live_invoice_total():
    """إجماليُّ الورقة **الحيّة** لمسودّةٍ كاستعلامٍ فرعيٍّ — `NULL` إن لم تصدر.

    ولا يُقرأ `FeeDraft.total` مكانه: ذاك مجموعُ المسودّة **قبل الضريبة**، والورقةُ
    تُصدَر بالإجمالي (`net + tax_total`) والدفاترُ تُدين الذمّةَ به. فالفرقُ بينهما
    هو عيبُ «اللي عليه» نفسُه (#292).
    """
    return Subquery(
        FeeInvoice.objects
        .filter(source_draft=OuterRef("pk"), cancelled_at__isnull=True)
        .order_by("pk")
        .values("total")[:1],
        output_field=MONEY_EXPRESSION,
    )


def _credit_note_sum():
    """مجموعُ الإشعارات الدائنة **الحيّة** على مسودّة — استعلامٌ فرعيٌّ واحد.

    الإشعارُ يشير إلى فاتورته (`related_invoice`) لا إلى المسودّة، فيُقرأ عبرها.
    ويُخصَم من متبقّي الورقة كما يخصم من «اللي عليه»: بدونه يُطالَب الزبون بورقةٍ
    خُصم نصفُها بإشعار، ويُقبل شطبٌ بأكثر من الباقي فيصير المستحقُّ سالباً — وهو
    عيبُ #292 نفسُه في موضعٍ ثانٍ. والملغى لا يخصم (`cancelled_at`).
    """
    return Coalesce(
        Subquery(
            FeeInvoice.objects
            .filter(
                related_invoice__source_draft=OuterRef("pk"),
                kind=FEE_INVOICE_KIND_CREDIT_NOTE,
                cancelled_at__isnull=True,
            )
            .order_by()
            .values("related_invoice__source_draft")
            .annotate(total=Sum("total"))
            .values("total")[:1],
            output_field=MONEY_EXPRESSION,
        ),
        Value(Decimal("0.00")),
        output_field=MONEY_EXPRESSION,
    )


def with_invoice_totals(queryset):
    """يُلحق بكل مسودّة: `billed_total` و`paid_amount` و`written_amount` و`remaining` (≥ 0).

    **والمتبقّي من `billed_total`** — إجماليُّ ورقتها الصادرة الحيّة (شاملاً
    الضريبة)، أو مجموعُ المسودّة حين لم تصدر بعد (مسودّةٌ منتظرةٌ لم تصر دَيناً).
    فسقفُ التخصيص والشطب يقرأ ما على **الورقة**: سقفٌ صافٍ (300) على ورقةٍ
    بإجمالي 348 كان يترك 48 رصيداً دائناً وهميّاً عند دفع الإجمالي. وتُخصَم منه
    الإشعاراتُ الدائنة الحيّة على الورقة (`_credit_note_sum`) لأنها خُصمت من ذمّتها.
    """
    return queryset.annotate(
        billed_total=Coalesce(
            _live_invoice_total(), F("total"), output_field=MONEY_EXPRESSION,
        ),
        paid_amount=_relation_sum(FeePaymentAllocation, "draft"),
        written_amount=_relation_sum(FeeWriteOff, "draft"),
        credited_amount=_credit_note_sum(),
    ).annotate(
        remaining=Greatest(
            ExpressionWrapper(
                F("billed_total")
                - F("paid_amount")
                - F("written_amount")
                - F("credited_amount"),
                output_field=MONEY_EXPRESSION,
            ),
            Value(Decimal("0.00")),
            output_field=MONEY_EXPRESSION,
        ),
    )


def with_payment_credit(queryset):
    """يُلحق بكل دفعة: `allocated_amount` و`credit` (الجزءُ غيرُ المخصَّص)."""
    return queryset.annotate(
        allocated_amount=_relation_sum(FeePaymentAllocation, "payment"),
    ).annotate(
        credit=ExpressionWrapper(
            F("amount") - F("allocated_amount"), output_field=MONEY_EXPRESSION,
        ),
    )


def invoice_state(total, remaining) -> str:
    """حالةُ الفاتورة من متبقّيها — **ثلاثٌ ولا رابعة** (`paid|partial|unpaid`).

    والشطبُ يخفّض `remaining` كالدفعة: فاتورةٌ شُطب ما بقي عليها تُقرأ «مدفوعةً»
    لأن ما على الزبون منها صار صفراً — والكشفُ يُظهر الشطبَ: `written_amount`
    على صفّ الفاتورة، وصفُّه المستقلُّ في `write_offs`.
    """
    total = _money(total)
    remaining = _money(remaining)
    if remaining <= 0:
        return INVOICE_STATE_PAID
    if remaining < total:
        return INVOICE_STATE_PARTIAL
    return INVOICE_STATE_UNPAID


@dataclass(frozen=True)
class InvoiceSummary:
    """ملخّصُ فاتورةٍ واحد: ما دُفع عليها وما شُطب وما خُصم بإشعارٍ وبقي وحالتُه."""

    paid_amount: Decimal
    written_amount: Decimal
    credited_amount: Decimal
    remaining: Decimal
    state: str
    state_label: str


def _summary(*, paid_amount, written_amount, credited_amount, total, remaining) -> InvoiceSummary:
    """الملخّصُ من أرقامه — **موضعٌ واحد** للحالة وتسميتها، ووسائطُ مُسمّاةٌ فلا تُبدَّل."""
    state = invoice_state(total, remaining)
    return InvoiceSummary(
        paid_amount=_money(paid_amount),
        written_amount=_money(written_amount),
        credited_amount=_money(credited_amount),
        remaining=_money(remaining),
        state=state,
        state_label=INVOICE_STATE_LABELS.get(state, ""),
    )


def _summary_from_row(row) -> InvoiceSummary:
    return _summary(
        paid_amount=row.paid_amount,
        written_amount=row.written_amount,
        credited_amount=row.credited_amount,
        total=row.billed_total,
        remaining=row.remaining,
    )


def invoice_summaries(drafts) -> dict[int, InvoiceSummary]:
    """ملخّصاتُ مجموعة مسودّاتٍ باستعلامٍ واحد — لا استعلامان لكل مسودّة.

    والقراءةُ بالمعرّفات وحدها (`pk__in`): المنادي يمرّر صفوفاً خرجت من استعلامٍ
    مُقيَّدٍ بالمكتب والرؤية (`visible_drafts`/`visible_payments` أو مسودّةٍ
    مقفولة)، فليس هنا مصدرٌ ثانٍ للعزل.
    """
    drafts = list(drafts)
    if not drafts:
        return {}
    rows = with_invoice_totals(
        FeeDraft.objects.filter(pk__in=[draft.pk for draft in drafts if draft.pk]),
    )
    found = {row.pk: _summary_from_row(row) for row in rows}
    zero = Decimal("0.00")
    return {
        # مسودّةٌ لم تُقرأ (غيرُ محفوظة) لا تخصيصَ عليها ولا شطب: متبقّيها مبلغُها.
        draft.pk: found.get(
            draft.pk,
            _summary(
                paid_amount=zero,
                written_amount=zero,
                credited_amount=zero,
                total=draft.total,
                remaining=draft.total,
            ),
        )
        for draft in drafts
    }


def invoice_summary(draft) -> InvoiceSummary:
    """ملخّصُ مسودّةٍ واحدة — نفسُ المصدر، لا صيغةٌ ثانية."""
    return invoice_summaries([draft])[draft.pk]


# ── «اللي عليه»: الدالّةُ الوحيدة ────────────────────────────────────────────
@dataclass(frozen=True)
class ClientDue:
    """ما على الزبون — صيغةٌ واحدةٌ تُقرأ من كل سطح.

    `due` سالبٌ حين يكون `credit` أكبرَ من مجموع المتبقّي: الزبون دفع أكثر مما
    عليه، والسالِبُ هو ما له.
    """

    due: Decimal
    invoices_total: Decimal
    paid_total: Decimal
    credit: Decimal
    unpaid_count: int


def _credits_map(tenant, client_ids) -> dict[int, Decimal]:
    """رصيدُ كل زبون: مجموعُ (مبلغُ الدفعة − المخصَّص منها) — مشتقٌّ لا مخزَّن."""
    credits: dict[int, Decimal] = {}
    if not client_ids:
        return credits
    rows = (
        with_payment_credit(
            FeePayment.objects.filter(tenant=tenant, client_id__in=client_ids),
        )
        .values("client_id", "credit")
        .order_by()
    )
    for row in rows:
        credits[row["client_id"]] = credits.get(
            row["client_id"], Decimal("0.00"),
        ) + _money(row["credit"])
    return credits


def _client_ids(clients) -> list[int]:
    """معرّفاتُ زبائنَ بلا تكرار — كائنٌ أو معرّفٌ يُقبلان، والترتيبُ محفوظٌ."""
    seen: dict[int, None] = {}
    for client in clients:
        seen.setdefault(getattr(client, "pk", client), None)
    return list(seen)


def _settled_amounts(model, tenant, client_ids):
    """مجموعُ صفوفٍ ماليّةٍ على المسودّات — **استعلامٌ واحد** يُعيد خريطتين.

    `{مسودّة: مجموعها}` لسقف الورقة الواحدة، و`{زبون: مجموعُ مسودّاته}` للصيغة
    الكلّية. والتجميعُ على العمودين في `GROUP BY` واحد (لا استعلامان: واحدٌ لكل
    مسودّةٍ وآخرُ لكل زبون). و`order_by()` يُفرّغ ترتيبَ النموذج لأن MySQL مع
    `ONLY_FULL_GROUP_BY` ترفض العمودَ غيرَ المجموع، وSQLite تمرّ فلا تكشفه.
    """
    rows = (
        model.objects
        .filter(tenant=tenant, draft__client_id__in=client_ids)
        .values("draft_id", "draft__client_id")
        .annotate(total=Sum("amount"))
        .order_by()
    )
    by_draft: dict[int, Decimal] = {}
    by_client: dict[int, Decimal] = {}
    for row in rows:
        amount = _money(row["total"] or 0)
        by_draft[row["draft_id"]] = by_draft.get(row["draft_id"], Decimal("0.00")) + amount
        client_id = row["draft__client_id"]
        by_client[client_id] = by_client.get(client_id, Decimal("0.00")) + amount
    return by_draft, by_client


def client_due_map(tenant, clients) -> dict[int, ClientDue]:
    """«اللي عليه» لكل زبونٍ في المجموعة — أربعةُ استعلاماتٍ لا استعلاماتٍ لكل زبون.

    **المستحقُّ من الورقة الصادرة لا من مسودّتها** (#292): مجموعُ إجماليِّ
    الفواتير والتكميليات **الحيّة** ناقصَ الإشعارات الدائنة الحيّة (بإجماليها
    شاملاً الضريبة، كما قُيِّدت). والملغاةُ (`cancelled_at`) والمسودّةُ التي لم
    تُصدر لا تدخلان الحساب: لا مطالبةَ بورقةٍ لم تصدر.

    ثم يُخصَم ما غطّى الذمّةَ فعلاً — تخصيصاتُ الدفعات وشطوبُ المكتب — ويُخصَم
    الرصيدُ الدائن (المالُ المقبوض غيرُ المخصَّص). فالمعادلةُ هي معادلةُ الدفاتر:
    مدينُ الورقة ناقصَ دائنِ الدفع والعكسِ والشطب.

    و`unpaid_count` تعدّ الأوراقَ التي **بقي عليها شيء** من متبقّيها هي:
    إجماليُها − ما على مسودّتها من تخصيصٍ وشطب − ما خُصم منها بإشعارٍ دائن.
    """
    ids = _client_ids(clients)
    if not ids:
        return {}
    invoices = list(
        FeeInvoice.objects
        .filter(tenant=tenant, client_id__in=ids, cancelled_at__isnull=True)
        .values("id", "client_id", "kind", "total", "source_draft_id", "related_invoice_id")
        .order_by("id"),
    )
    paid_by_draft, paid_by_client = _settled_amounts(FeePaymentAllocation, tenant, ids)
    written_by_draft, written_by_client = _settled_amounts(FeeWriteOff, tenant, ids)
    credits = _credits_map(tenant, ids)

    # الإشعارُ الدائنُ يخصم من فاتورته (لسقفها التراكميّ ومن متبقّيها) — مرّتان:
    # الأولى تجمع الإشعارات على فواتيرها، والثانية تحسب المتبقّيَ لكل ورقة.
    notes_by_invoice: dict[int, Decimal] = {}
    for row in invoices:
        if row["kind"] != FEE_INVOICE_KIND_CREDIT_NOTE:
            continue
        key = row["related_invoice_id"]
        notes_by_invoice[key] = notes_by_invoice.get(key, Decimal("0.00")) + _money(row["total"])

    charges = {pk: Decimal("0.00") for pk in ids}
    unpaid = {pk: 0 for pk in ids}
    for row in invoices:
        client_id = row["client_id"]
        total = _money(row["total"])
        if row["kind"] == FEE_INVOICE_KIND_CREDIT_NOTE:
            charges[client_id] -= total
            continue
        charges[client_id] += total
        covered = (
            paid_by_draft.get(row["source_draft_id"], Decimal("0.00"))
            + written_by_draft.get(row["source_draft_id"], Decimal("0.00"))
            + notes_by_invoice.get(row["id"], Decimal("0.00"))
        )
        if total - covered > 0:
            unpaid[client_id] += 1

    result: dict[int, ClientDue] = {}
    for client_id in ids:
        credit = credits.get(client_id, Decimal("0.00"))
        result[client_id] = ClientDue(
            due=_money(
                charges[client_id]
                - paid_by_client.get(client_id, Decimal("0.00"))
                - written_by_client.get(client_id, Decimal("0.00"))
                - credit,
            ),
            invoices_total=_money(charges[client_id]),
            paid_total=_money(paid_by_client.get(client_id, Decimal("0.00"))),
            credit=_money(credit),
            unpaid_count=unpaid[client_id],
        )
    return result


def client_due(tenant, client) -> ClientDue:
    """**الدالّةُ الوحيدة** لـ«اللي عليه» — لا صيغةَ ثانيةً في أيّ موضع."""
    return client_due_map(tenant, [client])[client.pk]


def client_tax_notes_map(tenant, clients) -> dict[int, Decimal]:
    """سطرُ العلم الضريبيّ لكل زبون: مجموعُ الالتزامات **التي على الزبون**.

    الشرطُ ثلاثةٌ لا واحد — `client_paid=False`، و`direction != refund` (المرتجعُ
    «إلنا» لا «علينا»، وجمعُه يجعل زبوناً عليه 1,000 وله 5,000 يظهر 6,000)،
    و`status != not_required` («مش لازم» ليست مستحقّة). وهي القاعدةُ نفسُها في
    `appointments._period_unpaid_total` و`client_owes` — بثوابت النموذج لا بنصٍّ.

    **`Obligation` لا يحمل حقلاً خاصّاً بمبلغ ضريبة** — الموجودُ `amount` بقيمةٍ
    قد تكون فارغة. فالسطرُ مجموعُ ما وُجد منها، ولا حقلَ جديدٌ يُخترَع له.
    """
    ids = _client_ids(clients)
    if not ids:
        return {}
    rows = (
        Obligation.objects
        .filter(tenant=tenant, client_id__in=ids, client_paid=False)
        .exclude(direction=OBLIGATION_DIRECTION_REFUND)
        .exclude(status=OBLIGATION_STATUS_NOT_REQUIRED)
        .values("client_id")
        .annotate(total=Sum("amount"))
        # ترتيبُ النموذج الافتراضي يكسر `GROUP BY` في MySQL (`ONLY_FULL_GROUP_BY`).
        .order_by()
    )
    return {row["client_id"]: _money(row["total"] or 0) for row in rows}


def client_due_tax_note(tenant, client) -> Decimal:
    """سطرُ العلم الضريبيّ لزبونٍ واحد — **لا يدخل `due`** (علمٌ يُعرض تحته)."""
    return client_tax_notes_map(tenant, [client]).get(client.pk, Decimal("0.00"))


def client_dues_payload(tenant, clients, *, user, masked=None) -> dict[int, dict]:
    """حمولةُ «اللي عليه» لمجموعةٍ — القناعُ فيها واحدٌ يُحسب مرّة.

    و`masked` يُمرَّر من قائمةٍ حسبته أصلاً (`payments_payload`/`ledger_payload`)
    فلا يُسأل `can_see_amounts` مرّتين في الطلب نفسه.

    **وعلامةُ حجب التسليم (#283/ج) تُضاف مفتاحاً واحداً `delivery` ولا تُضاف حين
    يكون الإعدادُ مطفأً**: مطفأً هو سلوكُ اليوم حرفاً، فمفتاحٌ مخزَّنٌ بقيمةٍ فارغة
    كان يغيّر شكلَ الحمولة على كل مكتبٍ لم يُفعّله. والعلامةُ للزبون الذي **عليه
    رصيد** (وإلا فلا شيءَ يُحجب)، ومصدرُ الرقم `client_due` وحدها.
    """
    clients = list(clients)
    masked = amounts_masked(tenant, user) if masked is None else masked
    dues = client_due_map(tenant, clients)
    notes = client_tax_notes_map(tenant, clients)
    hold = bool(clients) and bool(
        services.resolve_setting(tenant, services.DELIVERY_HOLD_UNPAID_KEY),
    )
    payload: dict[int, dict] = {}
    for client in clients:
        due = dues.get(client.pk)
        if due is None:
            continue
        data = {
            "due": due.due,
            "invoices_total": due.invoices_total,
            "paid_total": due.paid_total,
            "credit": due.credit,
            "unpaid_count": due.unpaid_count,
            "tax_note": notes.get(client.pk, Decimal("0.00")),
        }
        if hold and due.due > 0:
            data["delivery"] = {"label": services.DELIVERY_HELD_LABEL}
        payload[client.pk] = (
            _mask(data, services.PAYMENT_AMOUNT_KEYS) if masked else data
        )
    return payload


def client_due_payload(tenant, client, *, user) -> dict:
    """حمولةُ «اللي عليه» لزبونٍ واحد — بما فيها سطرُ العلم الضريبيّ."""
    return client_dues_payload(tenant, [client], user=user)[client.pk]


# ── رقمُ الإشعار: عدّادٌ مقفول ───────────────────────────────────────────────
def next_receipt_number(tenant, *, year) -> str:
    """الرقمُ التالي `{year}-{n:05d}` من **عدّادٍ مقفول** لا من `MAX+1`.

    `select_for_update` على صفّ العدّاد يُسلسل الكُتّاب داخلَ معاملةٍ واحدة،
    والزيادةُ تُكتب فيها؛ والبديلان (`MAX`/`count`) يقرآن لقطةً قديمة تحت
    التزامن فيكرّران رقماً أو يُحدثان فجوة. ولا يُعاد رقمُ إشعارٍ قائم أبداً.

    **وأوّلُ دفعتين متزامنتين في السنة** (الصفُّ غيرُ موجودٍ فلا قفلَ عليه بعد):
    يتولّاه `get_or_create` نفسُه — يلتقط `IntegrityError` الإدراج ويُعيد `get()`
    على الـqueryset المقفول ذاتِه فيتبع الخاسرُ صفَّ الفائز. وفرادةُ
    `(tenant, receipt_number)` على `FeePayment` طبقةٌ ثانية لا بديل.
    """
    sequence, _created = FeeReceiptSequence.objects.select_for_update().get_or_create(
        tenant=tenant,
        year=year,
        defaults={"last_number": 0},
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    return f"{year}-{sequence.last_number:05d}"


# ── التخصيص ─────────────────────────────────────────────────────────────────
def _open_drafts(tenant, client_id):
    """مسودّاتُ الزبون المعتمدة التي بقي عليها شيء — **الأقدمُ أوّلَاً**.

    **والقفلُ بترتيب المعرّف** ثم القراءةُ بترتيب التقادُم: القفلُ يخصّ الصفوف لا
    ترتيبَ التخصيص، وكلُّ مسارٍ يقفل مسودّات الزبون بالـ`pk` (وهذا ومسارُ
    `_apply_explicit_allocations` معاً) فلا يقفل أحدُهما صفًّا ينتظره الآخر.
    """
    list(
        FeeDraft.objects.select_for_update().filter(
            tenant=tenant,
            client_id=client_id,
            status=FEE_DRAFT_STATUS_APPROVED,
        ).order_by("pk"),
    )  # قفلُ صفوف الزبون — بالـ`pk` لا بترتيب التقادُم
    return list(
        with_invoice_totals(
            FeeDraft.objects.filter(
                tenant=tenant,
                client_id=client_id,
                status=FEE_DRAFT_STATUS_APPROVED,
            ),
        )
        .filter(remaining__gt=0)
        .order_by(*DRAFT_AGING_ORDER)
    )


def _allocate(payment, draft, amount) -> FeePaymentAllocation:
    return FeePaymentAllocation.objects.create(
        tenant_id=payment.tenant_id, payment=payment, draft=draft, amount=amount,
    )


def _payment_free_amount(payment) -> Decimal:
    """ما بقي من الدفعة غيرَ مخصَّص — يُقرأ من الصفوف لا من لقطةٍ قديمة."""
    allocated = (
        FeePaymentAllocation.objects
        .filter(payment=payment)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return _money(Decimal(str(payment.amount)) - _money(allocated))


def _allocate_oldest(payment) -> int:
    """يخصّص المتاح من الدفعة على أقدم المسودّات — ويُرجع عددَ الصفوف المكتوبة.

    **يقفل صفَّ الدفعة أوّلاً**: اعتمادان متزامنان لزبونٍ له رصيدٌ كانا يقرآن
    المتاح نفسَه فيخصّصانه مرّتين، فيتجاوز مجموعُ التخصيصات مبلغَ الدفعة. والقفلُ
    قبل القراءة يجعل الثاني يرى ما كتبه الأوّل.
    """
    with transaction.atomic():
        locked = FeePayment.objects.select_for_update().get(pk=payment.pk)
        free = _payment_free_amount(locked)
        if free <= 0:
            return 0
        written = 0
        for draft in _open_drafts(locked.tenant_id, locked.client_id):
            if free <= 0:
                break
            amount = _money(min(draft.remaining, free))
            if amount <= 0:
                continue
            _allocate(locked, draft, amount)
            free = _money(free - amount)
            written += 1
        return written


def _apply_explicit_allocations(payment, allocations) -> int:
    """تخصيصُ الموظف الصريح — يُتحقَّق كاملاً قبل كتابة أول صفّ.

    الشروطُ: مبلغٌ موجب، والمسودّةُ **معتمدةٌ وله وللمكتب نفسه**، والتخصيصُ لا
    يتجاوز متبقّيها، والمجموعُ لا يتجاوز مبلغَ الدفعة.

    **والأقفالُ بترتيب المعرّف لا بترتيب الحمولة**: `apply_open_credit` يقفل
    مسودّات الزبون في مسارٍ آخر؛ ترتيبٌ مختلفٌ هنا يفتح بابَ جمودٍ (كلٌّ يقفل
    صفًّا ينتظره الآخر). فتُجمع المعرّفاتُ وتُقفل مرّةً واحدةً مرتَّبةً، ثم
    تُطبَّق المبالغ بترتيب الحمولة.
    """
    requested: list[tuple[int, Decimal]] = []
    seen: set[int] = set()
    intended = Decimal("0.00")
    for raw in allocations:
        draft_id = raw.get("draft")
        amount = _clean_positive_amount(raw.get("amount"), field="allocations")
        if draft_id in seen:
            raise ValidationError({"allocations": "مسودّةٌ مكرَّرةٌ في التخصيصات."})
        seen.add(draft_id)
        intended += amount
        requested.append((draft_id, amount))
    if intended > _money(payment.amount):
        raise ValidationError({
            "allocations": "مجموعُ التخصيصات يتجاوز مبلغَ الدفعة.",
        })
    # **قفلٌ في جملة، وقراءةٌ في جملةٍ ثانية** (نمطُ `_open_drafts`): `remaining`
    # استعلاماتٌ فرعيةٌ تأخذ لقطتَها عند أوّل تقييمٍ على `READ COMMITTED` — أي بعد
    # قفل الصفّ الأوّل وقبل انتظار الثاني — فشطبٌ متزامنٌ يُفلت منها ويخسر الرصيدُ
    # الدائنُ ما لم يُستحقّ. فالقراءةُ بعد أن صارت كلُّ الأقفال في اليد.
    scope = {
        "pk__in": sorted(seen),
        "tenant": payment.tenant_id,
        "client_id": payment.client_id,
        "status": FEE_DRAFT_STATUS_APPROVED,
    }
    list(FeeDraft.objects.select_for_update().filter(**scope).order_by("pk"))
    drafts = {
        draft.pk: draft
        for draft in with_invoice_totals(FeeDraft.objects.filter(**scope))
    }
    if len(drafts) != len(seen):
        # 400 لا 404: الرسالةُ واحدةٌ للمسودّة الغائبة ولمسودّةِ غيرِك، فلا
        # يقول الردُّ إنّ مسودّةً بهذا المعرّف موجودةٌ عند مكتبٍ آخر.
        raise ValidationError({"allocations": "مسودّةٌ غير موجودة أو غير معتمدة."})
    prepared: list[tuple[object, Decimal]] = []
    for draft_id, amount in requested:
        draft = drafts[draft_id]
        if amount > _money(draft.remaining):
            raise ValidationError({
                "allocations": "المبلغُ يتجاوز المتبقّي على المسودّة.",
            })
        prepared.append((draft, amount))
    for draft, amount in prepared:
        _allocate(payment, draft, amount)
    return len(prepared)


# ── الكتابة: دفعةٌ وطباعتها ─────────────────────────────────────────────────
def create_payment(
    tenant, client, *, amount, method, paid_at, note="", actor=None,
    allocations=None,
):
    """دفعةٌ جديدة: رقمُ إشعارٍ مقفول، ثم تخصيصُ الموظف أو الأقدمُ أوّلَاً.

    - **`allocations=None` (الحقلُ غائب أو `null`)** ⇒ يُخصَّص على أقدم المسودّات
      المعتمدة حتى ينفد المبلغ، وما بقي رصيدٌ دائن.
    - **`allocations=[]` (قائمةٌ فارغة)** ⇒ **لا تخصيصَ إطلاقاً**: دفعةٌ مقدَّمةٌ
      صريحةٌ تبقى رصيداً دائناً خالصاً ولو كانت للزبون فواتيرُ مفتوحة. ولو عادت
      إلى «الأقدم أولاً» لما أمكن تسجيلُ دفعةٍ مقدَّمةٍ أصلاً.
    - **ومع قائمةٍ غير فارغة** ⇒ هي المرجعُ وحدها، وما لم يُخصَّص منها رصيدٌ دائن.
    - **`paid_at` تاريخُ الرقم وسنته**: الإشعارُ يتبع سنةَ الدفع لا سنةَ الإدخال.
    """
    services.assert_client_of_tenant(tenant, client)
    amount = _clean_positive_amount(amount)
    if method not in dict(FEE_PAYMENT_METHOD_CHOICES):
        raise ValidationError({"method": "طريقةُ دفعٍ غير معروفة."})
    paid_at = _iso_date(paid_at, "paid_at")
    if paid_at is None:
        raise ValidationError({"paid_at": "تاريخُ الدفع مطلوب."})
    note = (note or "").strip()
    if len(note) > 300:
        raise ValidationError({"note": "الملاحظة أطول من 300 حرف."})
    actor = actor if getattr(actor, "pk", None) else None
    with transaction.atomic():
        payment = FeePayment.objects.create(
            tenant=tenant,
            client=client,
            method=method,
            amount=amount,
            paid_at=paid_at,
            note=note,
            receipt_number=next_receipt_number(tenant, year=paid_at.year),
            created_by=actor,
        )
        if allocations is None:
            _allocate_oldest(payment)
        elif allocations:
            _apply_explicit_allocations(payment, allocations)
        # #284: القيدُ في الدفاتر **داخل المعاملة نفسها** — فشلُه (فترةٌ مقفلة،
        # حسابٌ معطَّل، توازن) يُرجع الدفعةَ والتخصيصَ والرقمَ كلَّه. لا صفَّ مالٍ
        # بلا قيد: «دفعةٌ سُجّلت ولم تُرحَّل» عطلٌ لا يظهر في أيّ شاشة.
        office_journal.post_payment_journal(payment, actor=actor)
    return payment


def apply_open_credit(tenant, clients) -> int:
    """يستهلك أرصدةَ الزبائن الدائنة على مسودّاتهم القائمة بتخصيصاتٍ جديدة.

    يُنادى عند **اعتماد مسودّة** — لحظةَ صيرورة الفاتورة مستحقّة: رصيدٌ دائمٌ
    لا يُخصَّص يبقى «له عندنا» إلى الأبد، وتخصيصُه الآن يجعل الكشفَ صفوفاً
    تُقرأ. والقراءةُ تسبق الحلقة فحسابُ الأرصدة استعلامٌ واحدٌ ثابتُ الكلفة.

    **وتُنادى بعد التزام معاملة الاعتماد (`transaction.on_commit`) لا داخلها**:
    الاعتمادُ يقفل المسودّةَ `D`، فلو قفلنا هنا دفعةَ الزبون ثم مسودّاتِه لجاء
    ترتيبُ `D ← دفعة ← d1…` ومعه `create_payment` الذي يقفل `d1` قبل `D` —
    جمودٌ (1213). و`due = Σ remaining − credit` لا يتغيّر بتخصيص الرصيد، فتأخيرُه
    لا يغيّر ما يُقرأ، وفشلُه بعد الالتزام يؤخّر الاستهلاكَ إلى نداءٍ لاحقٍ فقط.
    """
    client_ids = _client_ids(clients)
    if not client_ids:
        return 0
    owed = list(
        with_payment_credit(
            FeePayment.objects.filter(tenant=tenant, client_id__in=client_ids),
        )
        .filter(credit__gt=0)
        .order_by("paid_at", "id"),
    )
    if not owed:
        return 0
    applied = 0
    with transaction.atomic():
        for payment in owed:
            applied += _allocate_oldest(payment)
    return applied


def can_write_off(tenant, user) -> bool:
    """شطبُ المتبقّي **لصاحب المكتب وحده** — لا مديرُ المكتب ولا المحاسب."""
    return user_tenant_role(user, tenant) == MANAGER_ROLE


def _assert_write_off_owner(tenant, actor) -> None:
    if not can_write_off(tenant, actor):
        raise PermissionDenied("شطبُ متبقّي الأتعاب لصاحب المكتب وحده.")


def write_off_fee_draft(draft, *, amount, reason, actor):
    """شطبُ جزءٍ من متبقّي مسودّةٍ معتمدة — **سطرٌ إلحاقيٌّ بسببٍ مكتوب**.

    لا يمسّ `FeeDraft.total` ولا `status` ولا ينشئ دفعة: «تنازلنا عن المتبقّي»
    قرارٌ يُقرأ في الكشف. والمبلغُ لا يتجاوز المتبقّي — شطبُ أكثرَ يمحو الباقي
    بصمتٍ ويُظهر رصيداً دائناً لم يدفعه أحد.
    """
    _assert_write_off_owner(draft.tenant, actor)
    amount = _clean_positive_amount(amount)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "سببُ الشطب مطلوب."})
    if len(reason) > 300:
        raise ValidationError({"reason": "السبب أطول من 300 حرف."})
    actor = actor if getattr(actor, "pk", None) else None
    with transaction.atomic():
        locked = FeeDraft.objects.select_for_update().get(pk=draft.pk)
        if locked.status != FEE_DRAFT_STATUS_APPROVED:
            raise ValidationError({
                "draft": "الشطبُ على مسودّةٍ معتمدةٍ وحدها — المسودّةُ ليست دَيناً بعد.",
            })
        remaining = invoice_summary(locked).remaining
        if amount > remaining:
            raise ValidationError({
                "amount": "المبلغُ يتجاوز المتبقّي على المسودّة.",
            })
        write_off = FeeWriteOff.objects.create(
            tenant_id=locked.tenant_id,
            draft=locked,
            amount=amount,
            reason=reason,
            created_by=actor,
        )
        # #284: قيدُ الشطب في المعاملة نفسها — لا شطبَ بلا قيد (والعكس).
        office_journal.post_writeoff_journal(write_off, actor=actor)
        return write_off


# ── القراءة: الرؤية والقناع ─────────────────────────────────────────────────
def visible_payments(tenant, user):
    """دفعاتُ زبائنَ يراها العضو — ودفعةُ غيره **404** لأنها ليست في المجموعة."""
    return (
        FeePayment.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "created_by")
        .prefetch_related("allocations__draft")
    )


def visible_approved_drafts(tenant, user):
    """المعتمدةُ وحدها: مسودّةٌ غيرُ معتمدةٍ ليست دَيناً يُكشف عليه."""
    return (
        FeeDraft.objects
        .filter(
            tenant=tenant,
            status=FEE_DRAFT_STATUS_APPROVED,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client")
    )


def _client_payload(client) -> dict:
    return {"id": client.pk, "name": client.name}


def _created_by_payload(user):
    if user is None:
        return None
    return {"id": user.pk, "name": services.user_display_name(user)}


def allocation_row(allocation, *, masked) -> dict:
    data = {
        "id": allocation.pk,
        "draft": {
            "id": allocation.draft_id,
            "year": allocation.draft.year,
            "month": allocation.draft.month,
        },
        "amount": allocation.amount,
    }
    return _mask(data) if masked else data


def payment_row(payment, *, masked, client_due=None, journal_entry=None) -> dict:
    """سطرُ دفعة — ومعه **رصيدُ الزبون الدائنُ وما عليه** من `client_due` وحدها.

    `client_due` هو **حمولةُ الزبون** (`client_dues_payload`) لا مبلغُ `due`: تُمرَّر
    مجمَّعةً حين تُقرأ قائمةٌ فلا استعلامان لكل صفّ، وتُحسب للصفّ المفرد حين تغيب.

    و`journal_entry` معرّفُ قيد الدفعة في الدفاتر (#284) — يُمرَّر مجمَّعاً
    (`office_journal.journal_entry_ids`) فلا استعلامَ لكل صفّ، و`None` تعني «بلا
    قيد» صراحةً: الترحيلُ مطفأ أو دفعةٌ سابقةٌ لهذا الحقل.
    """
    data = {
        "id": payment.pk,
        "client": _client_payload(payment.client),
        "method": payment.method,
        "method_label": FEE_PAYMENT_METHOD_LABELS.get(payment.method, ""),
        "amount": payment.amount,
        "paid_at": payment.paid_at.isoformat(),
        "note": payment.note,
        "receipt_number": payment.receipt_number,
        "created_by": _created_by_payload(payment.created_by),
        "created_at": payment.created_at.isoformat(),
        "allocations": [
            allocation_row(allocation, masked=masked)
            for allocation in payment.allocations.all()
        ],
        "due": None if client_due is None else client_due.get("due"),
        "credit": None if client_due is None else client_due.get("credit"),
        "journal_entry": journal_entry,
    }
    return _mask(data) if masked else data


def filter_payments(queryset, params):
    """فلاترُ قائمة الدفعات — **في الاستعلام** لا في بايثون."""
    client_id = params.get("client")
    if client_id not in (None, ""):
        queryset = queryset.filter(client_id=_int_or_error(client_id, "client"))
    method = (params.get("method") or "").strip()
    if method:
        if method not in dict(FEE_PAYMENT_METHOD_CHOICES):
            raise ValidationError({"method": "طريقةُ دفعٍ غير معروفة."})
        queryset = queryset.filter(method=method)
    date_from = _iso_date(params.get("date_from"), "date_from")
    if date_from is not None:
        queryset = queryset.filter(paid_at__gte=date_from)
    date_to = _iso_date(params.get("date_to"), "date_to")
    if date_to is not None:
        queryset = queryset.filter(paid_at__lte=date_to)
    return queryset.order_by("-paid_at", "-id")


def _int_or_error(value, field) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "معرّفٌ غير صالح."}) from None


def payments_payload(tenant, *, user, queryset=None) -> list[dict]:
    """قائمةُ دفعاتٍ بحمولةٍ واحدة: القناعُ والأرصدةُ والقيودُ تُحسب مرّةً لا لكل صفّ."""
    masked = amounts_masked(tenant, user)
    rows = list(queryset if queryset is not None else visible_payments(tenant, user))
    dues = client_dues_payload(
        tenant, [row.client for row in rows], user=user, masked=masked,
    )
    entries = office_journal.journal_entry_ids(tenant, rows)
    return [
        payment_row(
            row,
            masked=masked,
            client_due=dues.get(row.client_id),
            journal_entry=entries.get(row.pk),
        )
        for row in rows
    ]


def created_payment_row(tenant, payment, *, user) -> dict:
    """سطرُ دفعةٍ أُنشئت للتوّ — يُقرأ من مصدر الرؤية نفسه قبل الردّ."""
    row = visible_payments(tenant, user).get(pk=payment.pk)
    return payments_payload(tenant, user=user, queryset=[row])[0]


def write_off_row(write_off, *, masked) -> dict:
    data = {
        "id": write_off.pk,
        "draft": write_off.draft_id,
        "amount": write_off.amount,
        "reason": write_off.reason,
        "created_by": _created_by_payload(write_off.created_by),
        "created_at": write_off.created_at.isoformat(),
    }
    return _mask(data) if masked else data


# ── كشف الحساب: فاتورةٌ ودفعة ───────────────────────────────────────────────
def invoice_row(draft, *, summary, masked) -> dict:
    data = {
        "kind": "invoice",
        "id": draft.pk,
        "client": _client_payload(draft.client),
        "year": draft.year,
        "month": draft.month,
        "period_label": fees.draft_period_label(draft),
        # إجماليُّ الورقة الصادرة (بضريبتها) — لا مجموعُ المسودّة الصافي؛ وإلا
        # قرأ الصفُّ 300 ومتبقّيه 348 (#292).
        "total": draft.billed_total,
        "paid_amount": summary.paid_amount,
        # ما شُطب منها — يظهر هنا وفي صفوف `write_offs` معاً (#283): `remaining`
        # وحدها لا تقول لِمَ نقصت.
        "written_amount": summary.written_amount,
        # وما خُصم منها بإشعارٍ دائنٍ (#292): بدونه لا يُقرأ `remaining` من
        # `total − paid − written`.
        "credited_amount": summary.credited_amount,
        "remaining": summary.remaining,
        "state": summary.state,
        "state_label": summary.state_label,
    }
    return _mask(data) if masked else data


def _state_filter(state):
    """شرطُ الحالة **في SQL** على التعليق المشتقّ — لا تصفيةً في بايثون.

    `paid` = لا متبقّي، و`unpaid` = لم يُخصَّص منه شيء، و`partial` بينهما.
    **و`unpaid` يشترط متبقّياً موجباً**: مسودّةٌ إجماليُها صفر `0 = 0` فتُطابق
    «لم يُخصَّص منها شيء» و`paid` معاً، وهي مسدَّدةٌ بالمعنى (`remaining = 0`).
    """
    if state == INVOICE_STATE_PAID:
        return Q(remaining__lte=0)
    if state == INVOICE_STATE_PARTIAL:
        return Q(remaining__gt=0) & Q(remaining__lt=F("billed_total"))
    return Q(remaining=F("billed_total")) & Q(remaining__gt=0)


def _page(queryset, params) -> dict:
    """صفحةٌ من استعلامٍ: العدُّ والقصُّ في القاعدة — لا `len()` على قائمةٍ كاملة."""
    page = max(_positive_int(params.get("page"), field="page", default=1), 1)
    size = _positive_int(params.get("page_size"), field="page_size", default=LEDGER_PAGE_SIZE)
    size = min(max(size, 1), LEDGER_MAX_PAGE_SIZE)
    total = queryset.count()
    start = (page - 1) * size
    return {
        "count": total,
        "page": page,
        "page_size": size,
        "results": list(queryset[start:start + size]),
    }


def _positive_int(value, *, field, default) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "رقمٌ غير صالح."}) from None


def ledger_payload(tenant, *, user, params) -> dict:
    """كشفُ الحساب: **الفواتيرُ المعتمدةُ والدفعاتُ والشطوب** بفلترٍ وترقيمٍ في الاستعلام.

    الحمولةُ ثلاثُ مجموعاتٍ مفصولة (`invoices`/`payments`/`write_offs`) لأنها
    سجلّاتٌ مستقلّةٌ في المصدر: دمجُها في قائمةٍ واحدة يتطلّب `UNION` على أنواع
    تواريخَ مختلفة أو تصفيةً في بايثون — والأولى هشّةٌ عبر قواعد البيانات والثانية
    ممنوعةٌ صراحةً. فالشاشةُ تقرأ المجموعاتِ وتصفّها كما تشاء. والفلترةُ (زبون،
    بحثٌ بالاسم) والترقيمُ على الاستعلام في الثلاث، و`state` على الفواتير وحدها.
    **والشطبُ يُقرأ هنا** (تاريخٌ ومبلغٌ وسببٌ ومَن شطب والفاتورة) ويظهر مجموعُه
    على صفّ الفاتورة `written_amount` — فمن ينقص `remaining` عن `total − paid` يجد
    السببَ في الكشف لا في قاعدةِ البيانات.
    """
    masked = amounts_masked(tenant, user)
    client_filter = None
    client = None
    if params.get("client") not in (None, ""):
        client_filter = _int_or_error(params.get("client"), "client")
        # الزبونُ من مصدر الرؤية الواحد: زبونُ غيره **404** لا كشفٌ فارغ.
        client = services.visible_clients(tenant, user).filter(pk=client_filter).first()
        if client is None:
            raise Http404("الزبون غير موجود.")
    search = (params.get("q") or "").strip()
    state = (params.get("state") or "").strip()
    if state and state not in INVOICE_STATE_LABELS:
        raise ValidationError({"state": "حالةُ فاتورةٍ غير معروفة."})

    invoices = with_invoice_totals(visible_approved_drafts(tenant, user))
    if client_filter is not None:
        invoices = invoices.filter(client_id=client_filter)
    if search:
        invoices = invoices.filter(client__name__icontains=search)
    if state:
        invoices = invoices.filter(_state_filter(state))
    invoices = invoices.order_by(*DRAFT_AGING_ORDER)

    payments_qs = visible_payments(tenant, user)
    if client_filter is not None:
        payments_qs = payments_qs.filter(client_id=client_filter)
    if search:
        payments_qs = payments_qs.filter(client__name__icontains=search)
    payments_qs = payments_qs.order_by("-paid_at", "-id")

    # الشطوبُ من مصدر الرؤية نفسه: شطبُ زبونٍ لا يراه العضو لا يُقرأ.
    write_offs_qs = (
        FeeWriteOff.objects
        .filter(
            tenant=tenant,
            draft__client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("created_by")
    )
    if client_filter is not None:
        write_offs_qs = write_offs_qs.filter(draft__client_id=client_filter)
    if search:
        write_offs_qs = write_offs_qs.filter(draft__client__name__icontains=search)
    write_offs_qs = write_offs_qs.order_by("-created_at", "-id")

    invoice_page = _page(invoices, params)
    payment_page = _page(payments_qs, params)
    write_off_page = _page(write_offs_qs, params)

    invoice_page["results"] = [
        invoice_row(
            row,
            summary=_summary_from_row(row),
            masked=masked,
        )
        for row in invoice_page["results"]
    ]
    payment_dues = client_dues_payload(
        tenant,
        [row.client for row in payment_page["results"]],
        user=user,
        masked=masked,
    )
    payment_entries = office_journal.journal_entry_ids(
        tenant, payment_page["results"],
    )
    payment_page["results"] = [
        payment_row(
            row,
            masked=masked,
            client_due=payment_dues.get(row.client_id),
            journal_entry=payment_entries.get(row.pk),
        )
        for row in payment_page["results"]
    ]
    write_off_page["results"] = [
        write_off_row(row, masked=masked) for row in write_off_page["results"]
    ]
    return {
        "invoices": invoice_page,
        "payments": payment_page,
        "write_offs": write_off_page,
        # «اللي عليه» للزبون المفلتر — من الدالّة الواحدة، ومقيّدةً بالرؤية.
        "client_due": (
            None if client is None
            else client_dues_payload(
                tenant, [client], user=user, masked=masked,
            )[client.pk]
        ),
    }


# ── إشعارُ القبض (#283/ب) ────────────────────────────────────────────────────
def _text(value) -> str:
    """مبلغٌ كنصٍّ بخانتين — لا `Decimal` خاماً في حمولةٍ تصل الودجات.

    نفسُ حجّة `appointments.payment_notice_item`: قاموسٌ خامٌّ يمرّ مع DRF مائعاً
    (`float`)، وهذا مبلغُ زبونٍ على ورقةٍ يوقّعها.
    """
    return f"{_money(value):.2f}"


def _cheque_of(tenant, payment):
    """ورقةُ الشيك في الدفاتر — `None` لغير الشيك، وللدفعة التي رُحّلت بلا شيك.

    **`FeePayment` لا يحمل حقولَ شيك** (طريقةٌ ومبلغٌ وتاريخٌ وملاحظة فقط)،
    وورقةُ الشيك تُنشَأ عند ترحيل الدفعة (`office_journal.post_payment_journal`
    ← `accounting.api.ensure_incoming_cheque`) برقم الإشعار نفسِه مفتاحاً
    (الشركة، الرقم). فالشيكُ يُقرأ من دفاتره لا من حقلٍ يُضاف إلى نموذج الدفعة —
    ودفعةٌ في مكتبٍ أطفأ الترحيل لا شيكَ لها فلا سطرَ لها على الورقة.

    **والاستيرادُ كسولٌ في الدالّة**: `accounting` يجرّ خدماتِه، وهذه الوحدةُ
    تُستورد في إقلاع التطبيقات.
    """
    if payment.method != FEE_PAYMENT_METHOD_CHEQUE:
        return None
    from accounting import api as accounting_api

    return accounting_api.cheque_snapshot(
        tenant,
        number=payment.receipt_number,
        direction="Incoming",
    )


def receipt_payload(tenant, payment, *, masked: bool) -> dict:
    """ورقةُ إشعار القبض: **رقمُ الإشعار المخزَّن يُقرأ ولا يُولَّد**.

    الرقمُ يأتي من `FeePayment.receipt_number` وحده — حقلٌ كُتب مرّةً عند
    `create_payment` من العدّاد المقفول (`next_receipt_number`) ولا يُلمَس بعدها.
    فطباعةُ الإشعار مرّتين لا تُكلّف العدّادَ شيئاً، ولا يوجد في هذه الدالّة —
    ولا في القالب — أيُّ نداءٍ يستهلك رقماً. (الاختبارُ يفحص `FeeReceiptSequence`
    قبل الطباعة وبعدها.)

    و«اللي عليه» يُقرأ من `client_due` **الدالّة الواحدة** لا من حسابٍ ثانٍ هنا:
    متبقّي كلّ فاتورةٍ بعد تخصيصاتها وشطوبها ناقصَ رصيده الدائن.

    **والتخصيصاتُ تسمَّر بفترتها** (`fees.draft_period_label`) لا بمعرّف المسودّة:
    الورقةُ تخرج للزبون، و`#412` في ورقةٍ لا يقول له شيئاً.
    """
    due = client_due(tenant, payment.client)
    allocations = [
        {
            "draft": allocation.draft_id,
            "period_label": fees.draft_period_label(allocation.draft),
            "amount": None if masked else _text(allocation.amount),
        }
        for allocation in payment.allocations.select_related("draft").order_by("id")
    ]
    return {
        "title": RECEIPT_TITLE,
        "number": payment.receipt_number,
        "date": payment.paid_at.isoformat(),
        "client": _client_payload(payment.client),
        "amount": None if masked else _text(payment.amount),
        "method": payment.method,
        "method_label": FEE_PAYMENT_METHOD_LABELS.get(payment.method, ""),
        "cheque": _cheque_of(tenant, payment),
        "note": payment.note,
        "allocations": allocations,
        "due": None if masked else _text(due.due),
        "credit": None if masked else _text(due.credit),
        "office": {"name": tenant.CompanyName},
    }


# ── كشفُ الحساب (#283/ب) ────────────────────────────────────────────────────
def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _statement_movements(tenant, client, *, masked: bool) -> list[dict]:
    """حركاتُ الزبون الثلاث **مرتَّبةً زمنياً** مع صفّها الجاهز لكل مجموعة.

    المصدرُ هو مصدرُ `fees/ledger/` نفسه: `with_invoice_totals` للفواتير،
    و`invoice_row`/`payment_row`/`write_off_row` تبني الصفوف كما تبنيها نقطةُ
    الكشف — **لا حسابَ ثانياً هنا**. الجديدُ ترتيبٌ واحدٌ (تاريخ، نوع، معرّف)
    يجعل رصيداً جارياً ممكناً: ثلاثُ مجموعاتٍ مفصولةٌ لا رصيدَ بينها.

    وتاريخُ الحركة: تاريخُ الدفع للدفعة، ويومُ الشطب للشطب، و**أوّلُ شهر الفاتورة**
    للفاتورة (المسودّةُ شهرٌ لا يوم). والرتيبُ `year, month, id` كما في
    `DRAFT_AGING_ORDER`، ففاتورةُ آذار تسبق دفعةَ العاشر من نيسان دائماً.

    **والمبالغُ مُوقَّعة**: الفاتورةُ تزيد الدين (+) والدفعةُ والشطبُ ينقصانه (−)،
    فمجموعُها هو التغييرُ الصافي في «اللي عليه» — وهذا ما يثبته الاختبار.
    """
    movements: list[dict] = []
    drafts = (
        with_invoice_totals(
            FeeDraft.objects
            .filter(
                tenant=tenant,
                client=client,
                status=FEE_DRAFT_STATUS_APPROVED,
            )
            .select_related("client"),
        )
        .order_by(*DRAFT_AGING_ORDER)
    )
    for draft in drafts:
        movement_day = _month_start(draft.year, draft.month)
        movements.append({
            "kind": MOVEMENT_KIND_INVOICE,
            "kind_label": MOVEMENT_KIND_LABELS[MOVEMENT_KIND_INVOICE],
            "id": draft.pk,
            "date": movement_day,
            # اسمُ المستند من معجم الشركة لا حرفياً (حارس `test_terminology_guard`):
            # قالبُ مكتب المحاسبة يسمّيها «أتعاب»، وغيره باسمه العامّ.
            "label": (
                f"{tenant_term(tenant, 'doc.sales_invoice')} "
                f"{fees.draft_period_label(draft)}"
            ),
            "signed": _money(draft.billed_total),
            "group": invoice_row(
                draft, summary=_summary_from_row(draft), masked=masked,
            ),
        })
    payments = list(
        FeePayment.objects
        .filter(tenant=tenant, client=client)
        .select_related("client")
        .prefetch_related("allocations__draft")
        .order_by("paid_at", "id"),
    )
    # معرّفاتُ القيود في استعلامٍ واحد — `None` في `payment_row` تعني «بلا قيد»
    # صراحةً، فتمريرُها فارغةً كان يُنكر قيداً قائماً (#284).
    entries = office_journal.journal_entry_ids(tenant, payments)
    for payment in payments:
        movements.append({
            "kind": MOVEMENT_KIND_PAYMENT,
            "kind_label": MOVEMENT_KIND_LABELS[MOVEMENT_KIND_PAYMENT],
            "id": payment.pk,
            "date": payment.paid_at,
            "label": (
                f"دفعة {payment.receipt_number} — "
                f"{FEE_PAYMENT_METHOD_LABELS.get(payment.method, '')}"
            ),
            "signed": -_money(payment.amount),
            "group": payment_row(
                payment, masked=masked, journal_entry=entries.get(payment.pk),
            ),
        })
    for write_off in (
        FeeWriteOff.objects
        .filter(tenant=tenant, draft__client=client)
        .select_related("draft", "created_by")
        .order_by("created_at", "id")
    ):
        movements.append({
            "kind": MOVEMENT_KIND_WRITE_OFF,
            "kind_label": MOVEMENT_KIND_LABELS[MOVEMENT_KIND_WRITE_OFF],
            "id": write_off.pk,
            "date": timezone.localdate(write_off.created_at),
            "label": f"شطب — {write_off.reason}",
            "signed": -_money(write_off.amount),
            "group": write_off_row(write_off, masked=masked),
        })
    movements.sort(
        key=lambda row: (row["date"], MOVEMENT_KIND_ORDER[row["kind"]], row["id"]),
    )
    return movements


def statement_payload(
    tenant, client, *, period_from=None, period_to=None, masked: bool = False,
) -> dict:
    """كشفُ حساب الزبون لفترة: الحركاتُ والرصيدُ الجاري والرصيدُ الختامي.

    **الرصيدُ الجاري = الافتتاحيُّ + مجموع الحركات المعروضة**، والافتتاحيُّ صافي
    ما قبل `period_from`. فآخرُ صفٍّ يطابق `closing_balance` دائماً — كشفُ
    `client_books` (`book_reports`) نفسه في معناه.

    **و`due` هو «اللي عليه» الآن** من `client_due` — **الدالّة الوحيدة**، لا من
    الصفوف. ولهذا يُرسَل حقلٌ ثالثٌ مع الرصيدين: كشفٌ لفترةٍ سابقة رقمُه الختاميُّ
    رصيدُ نهايتها (لا رصيدَ اليوم)، والورقةُ تحتاج الاثنين صريحين. وحين تغطّي
    الفترةُ كلَّ الحركات حتى اليوم يتساوى الثلاثة — والاختبارُ يثبت ذلك، فهو
    برهانُ اتّساق الصيغتين لا صدفةُ تركيب أرقام.

    **والمجموعاتُ الثلاثُ** (`groups`) صفوفُ كشف الحساب القائمة نفسها
    (`invoice_row`/`payment_row`/`write_off_row`) مقصورةً على الفترة — يقرؤها
    القالبُ كما يشاء، ويُجمع كلُّ مجموعٍ من صفوفه (`totals`).
    """
    movements = _statement_movements(tenant, client, masked=masked)
    opening = Decimal("0.00")
    if period_from is not None:
        opening = sum(
            (row["signed"] for row in movements if row["date"] < period_from),
            Decimal("0.00"),
        )
    opening = _money(opening)

    running = opening
    rows: list[dict] = []
    shown: list[dict] = []
    for movement in movements:
        if period_from is not None and movement["date"] < period_from:
            continue
        if period_to is not None and movement["date"] > period_to:
            continue
        running = _money(running + movement["signed"])
        shown.append(movement)
        rows.append({
            "kind": movement["kind"],
            "kind_label": movement["kind_label"],
            "id": movement["id"],
            "date": movement["date"].isoformat(),
            "label": movement["label"],
            "amount": None if masked else _text(movement["signed"]),
            "balance": None if masked else _text(running),
        })

    totals = {kind: Decimal("0.00") for kind in MOVEMENT_KIND_LABELS}
    for movement in shown:
        totals[movement["kind"]] += abs(movement["signed"])
    due = client_due(tenant, client)
    groups = {
        "invoices": [row["group"] for row in shown if row["kind"] == MOVEMENT_KIND_INVOICE],
        "payments": [row["group"] for row in shown if row["kind"] == MOVEMENT_KIND_PAYMENT],
        "write_offs": [row["group"] for row in shown if row["kind"] == MOVEMENT_KIND_WRITE_OFF],
    }
    return {
        "title": STATEMENT_TITLE,
        "client": _client_payload(client),
        "from": None if period_from is None else period_from.isoformat(),
        "to": None if period_to is None else period_to.isoformat(),
        "opening_balance": None if masked else _text(opening),
        "closing_balance": None if masked else _text(running),
        "due": None if masked else _text(due.due),
        "credit": None if masked else _text(due.credit),
        "totals": {
            "invoices": None if masked else _text(totals[MOVEMENT_KIND_INVOICE]),
            "payments": None if masked else _text(totals[MOVEMENT_KIND_PAYMENT]),
            "write_offs": None if masked else _text(totals[MOVEMENT_KIND_WRITE_OFF]),
            "movements": None if masked else _text(running - opening),
        },
        "rows": rows,
        "groups": groups,
        "office": {"name": tenant.CompanyName},
    }


def create_fee_statement(tenant, client, *, period_from=None, period_to=None, actor=None):
    """صفُّ الكشف الذي يُعنوِن المستندَ — الفترةُ وحدها تُجمَّد، والأرقامُ تُقرأ.

    **الافتراضُ سنةُ اليوم حتى اليوم** حين لا تُمرَّر فترة: كشفٌ بلا طرفٍ آخر
    يفتح على «كلّ التاريخ» ويتضخّم مع كل دفعة، وسنةٌ كاملةٌ هي ما يطلبه المكتب
    عادةً. والفترةُ الصريحة تُحترم كما هي ولو كانت مفتوحةً من الماضي.
    """
    period_to = period_to or timezone.localdate()
    period_from = period_from or date(period_to.year, 1, 1)
    if period_from > period_to:
        raise ValidationError({"from": "بدايةُ الفترة بعد نهايتها."})
    return FeeStatement.objects.create(
        tenant=tenant,
        client=client,
        period_from=period_from,
        period_to=period_to,
        created_by=actor if getattr(actor, "pk", None) else None,
    )


def _share_payload(tenant, doc_type, doc_id, *, user, days=None) -> dict:
    """رابطٌ عامٌّ حيٌّ للمستند — بآلية `docshare` وحدها، بلا مسارٍ ثانٍ.

    **الاستيرادُ كسولٌ**: `docshare.services` يستورد سجلَّ الأنواع، ونوعُ
    الإشعار هناك يستورد هذه الوحدة — واستيرادٌ في الأعلى يدير دورةً حقيقيّة.
    """
    from docshare import services as docshare_services

    share = docshare_services.create_share(
        tenant,
        doc_type,
        doc_id,
        days=days or docshare_services.DEFAULT_EXPIRY_DAYS,
        user=user,
    )
    return {
        "url": docshare_services.public_url(share),
        "expires_at": share.expires_at.isoformat(),
    }


def share_payment_receipt(tenant, payment, *, user, days=None) -> dict:
    """`{url, expires_at}` لإشعار قبض دفعةٍ — الرابطُ على الورقة لا على الدفعة."""
    return _share_payload(tenant, RECEIPT_DOC_TYPE, payment.pk, user=user, days=days)


def share_client_statement(tenant, statement, *, user, days=None) -> dict:
    """`{url, expires_at}` لكشف حسابٍ أُنشئ صفُّه للتوّ."""
    return _share_payload(tenant, STATEMENT_DOC_TYPE, statement.pk, user=user, days=days)


def share_new_client_statement(
    tenant, client, *, period_from=None, period_to=None, user, days=None,
) -> dict:
    """صفُّ الكشف ورابطُه **في معاملةٍ واحدة** — لا صفَّ مستندٍ بلا رابط.

    والصفُّ يبقى بعد الرابط (المستندُ موجودٌ تاريخياً وإن أُبطل رابطه)، لكن
    فشلَ إنشاء الرابط (شركةٌ أطفأت ترخيص الوحدة مثلاً) لا يترك كشفاً لم يُصدر.
    """
    with transaction.atomic():
        statement = create_fee_statement(
            tenant, client,
            period_from=period_from,
            period_to=period_to,
            actor=user,
        )
        return share_client_statement(tenant, statement, user=user, days=days)


# ── اقتراحُ إشعار القبض في «جاهز للإرسال» (#283/ب) ──────────────────────────
#: نصُّ سطر التفصيل المرافق لبند الإشعار — **برقمه ومبلغه وباقيه**.
#:
#: وليس في `REMINDER_DEFAULT_TEXTS` لأنه لا يُكتب بقوالب المكتب: الرقمُ والمبلغُ
#: والباقي أرقامُ الخادم، والقوالبُ السابقةُ تحمل رموزاً عامّةً لا رقمَ مستند.
#: واللغتان منفصلتان كسائر نصوص الموديول (بحث #256 §5).
FEE_RECEIPT_DETAIL_TEXTS: dict[str, str] = {
    "ar": "رقم الإشعار: {numbers} — المبلغ: {amount} — الباقي عليك: {remaining}",
    "he": "מספר קבלה: {numbers} — סכום: {amount} — יתרה לתשלום: {remaining}",
}


def fee_receipt_detail(*, receipts, remaining, language="ar") -> str:
    """سطرُ البند: أرقامُ إشعارات اليوم ومجموعُ مبالغها وما بقي على الزبون.

    **ومفتاحُ البند تاريخُه**: `period_start = period_end = paid_at`. فدفعتان
    لزبونٍ في يومٍ واحد تُطوى في بندٍ واحد يذكر رقمَي الإشعار — ولا بندان
    بمفتاحٍ واحد. وهذا هو معنى «لا مفتاحَ مشترك» في تذكرة #283/ب: مفتاحُ البند
    في هذا النظام (زبون، نوع، طرفا الفترة) ولا يحمل معرّفَ دفعة، فبندان برقمٍ
    ليومٍ واحد يُعلَّم أحدهما فيُعلَّم الآخر — وهو بعينه ما مُنع.
    """
    numbers = "، ".join(receipt for receipt, _amount in receipts)
    total = sum((amount for _receipt, amount in receipts), Decimal("0.00"))
    template = FEE_RECEIPT_DETAIL_TEXTS.get(
        language, FEE_RECEIPT_DETAIL_TEXTS["ar"],
    )
    return template.format(
        numbers=numbers,
        amount=_text(total),
        remaining=_text(remaining),
    )


def fee_receipt_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """دفعاتُ اليوم التي لم يُعلَّم إشعارُها — بندٌ واحدٌ لكل زبونٍ في اليوم.

    **والحاجزُ سجلُّ التذكيرات نفسه** لا صفٌّ على الدفعة: بندٌ عُلِّم «انبعث»
    أو «كلّمناه» أو نُحّي يُقرأ من `by_pair` (المفتاحُ: زبون، نوع، طرفا الفترة)
    فيصير `count >= maximum` فتحجبه `ready_to_send_payload` بحواجزها نفسها.
    و`maximum = 1`: إشعارُ القبض يُقترح مرّةً واحدة، لا إيقاعَ تذكيرٍ متكرّر —
    «جاهز للإرسال» يذكّر بما يجب، والإيصالُ الذي حصل حصل.

    **ولا يقترح دفعةً أُرسل إشعارُها بطباعةٍ أو رابط**: تلك طُرُقٌ أخرى للمستند
    نفسه (`fees/payments/<pk>/print|share`)، والاقتراحُ عن **الإعلام** لا عن
    الطباعة. فمن طبعه ولم يرسله يبقى مقترحاً — وهو الصواب.
    """
    if reminder_type is not None and reminder_type != settings_registry.REMINDER_FEE_RECEIPT:
        return []
    client_ids = [client.pk for client in clients]
    if not client_ids:
        return []
    rows = list(
        FeePayment.objects
        .filter(tenant=tenant, client_id__in=client_ids, paid_at=day)
        .values("id", "client_id", "receipt_number", "amount")
        .order_by("id"),
    )
    if not rows:
        return []
    by_client: dict[int, list[dict]] = {}
    for row in rows:
        by_client.setdefault(row["client_id"], []).append(row)
    remaining_map = client_due_map(
        tenant, [client for client in clients if client.pk in by_client],
    )
    candidates = []
    for client in clients:
        receipts = by_client.get(client.pk)
        if not receipts:
            continue
        resolved = settings_by_client.get(client.pk, {})
        enabled = resolved.get(services.REMINDER_TYPES_ENABLED_KEY) or []
        if settings_registry.REMINDER_FEE_RECEIPT not in enabled:
            continue
        contact = contacts.get(
            (client.pk, settings_registry.REMINDER_FEE_RECEIPT),
        )
        pair = (
            client.pk, settings_registry.REMINDER_FEE_RECEIPT, day, day,
        )
        count = sum(
            1 for row in by_pair.get(pair, []) if row["kind"] in REMINDER_COUNTED_KINDS
        )
        due = remaining_map.get(client.pk)
        remaining = Decimal("0.00") if due is None else due.due
        receipts_by_number = [
            (row["receipt_number"], _money(row["amount"])) for row in receipts
        ]
        candidates.append(services.ReminderCandidate(
            client=client,
            reminder_type=settings_registry.REMINDER_FEE_RECEIPT,
            period_start=day,
            period_end=day,
            missing=(),
            missing_codes=(),
            count=count,
            maximum=1,
            interval_days=1,
            next_due=day,
            contact=contact,
            tax_system=resolved.get(services.TAX_SYSTEM_KEY),
            due=day >= day,
            exhausted=count >= 1,
            postponed=(client.pk, settings_registry.REMINDER_FEE_RECEIPT) in postponed_pairs,
            badge=OBLIGATION_BADGE_PAYMENT_RECEIVED,
            render_due=day,
            amount=sum((amount for _number, amount in receipts_by_number), Decimal("0.00")),
            detail=fee_receipt_detail(
                receipts=receipts_by_number,
                remaining=remaining,
                language=getattr(contact, "language", "") or "ar",
            ),
            receipt={
                "payment_ids": [row["id"] for row in receipts],
                "numbers": [number for number, _amount in receipts_by_number],
                "amount": _text(
                    sum((amount for _n, amount in receipts_by_number), Decimal("0.00")),
                ),
                "remaining": _text(remaining),
            },
        ))
    return candidates


# ── تذكيرُ «اللي عليه» بعد الاستحقاق (#283/ج) ────────────────────────────────
#
# **درجتان لا إيقاع**: بعد الاستحقاق ثلاثةَ أيامٍ ثم سبعة، وسقفُهما اثنتان.
# والاستحقاقُ **المخزَّن** لا يومُ فتح الشاشة: تاريخُ إصدار آخر فاتورةٍ صادرةٍ حيّةٍ
# (`issued_at`) + المهلة المعتمدة في الموديول (`fee_invoices.INVOICE_DUE_DAYS`).
# فالمفتاحُ `(الاستحقاق، الاستحقاق)` لا `(الإصدار، الاستحقاق)` الذي يحمله بندُ
# «فاتورةُ اليوم» (#282/أ٢) — خيطان لا يصطدم عدُّهما، ورسالتان في يومين مختلفين.
#
# **والمبلغُ من `client_due` وحدها**: `due` للباقي و`invoices_total` لـ«من» — لا
# صيغةَ ثانيةً تُحسب هنا. و`due <= 0` لا يولّد بنداً أصلاً، فالدفعُ الكاملُ يُسكِت
# الخيطَ بلا صفٍّ يُكتب، والجزئيُّ يُبقيه لأن الرصيدَ ما زال قائماً.
BALANCE_REMINDER_STEPS: tuple[int, ...] = (3, 7)
#: مهلةُ «شيل لهذه المرة»: تُعيد المؤقّتَ ولا تستهلك السقف — بفاصل الدرجتين
#: نفسه (نمطُ الأوراق: آخرُ صفٍّ مؤقّتٍ + الفاصل)، وإلا عاد البندُ غداً بلا سبب.
BALANCE_REMINDER_RESET_DAYS = BALANCE_REMINDER_STEPS[-1] - BALANCE_REMINDER_STEPS[0]

#: #283/ج: يومُ الكشف الشهريّ — أوّلُ كل شهر، ويُقاس بيومٍ يُمرَّر للدالّة.
MONTHLY_STATEMENT_DAY = 1

#: سطرُ «الباقي من الأصل» الملحَق بنصّ النوع — رقمُ الخادم لا قالبُ المكتب، فلا
#: رمزَ جديداً في `REMINDER_PLACEHOLDERS` (نمطُ `FEE_RECEIPT_DETAIL_TEXTS`).
FEE_BALANCE_DETAIL_TEXTS: dict[str, str] = {
    "ar": "عليك {due} من {total}",
    "he": "עליך {due} מתוך {total}",
}


def fee_balance_detail(*, due, total, language="ar") -> str:
    """«عليك 250.00 من 400.00» — الباقي والأصل كلاهما من `ClientDue` وحدها."""
    template = FEE_BALANCE_DETAIL_TEXTS.get(
        language, FEE_BALANCE_DETAIL_TEXTS["ar"],
    )
    return template.format(due=_text(due), total=_text(total))


def _month_bounds(day: date) -> tuple[date, date]:
    """أوّلُ شهر اليوم وآخرُه — بعبور السنة عبر `deadlines.month_start_after`."""
    start = date(day.year, day.month, 1)
    return start, deadlines.month_start_after(start, 1) - timedelta(days=1)


def _balance_due_anchor(tenant, client_ids) -> dict[int, tuple]:
    """آخرُ فاتورةٍ صادرةٍ حيّةٍ لكل زبون — كائنُها ويومُ استحقاقها المخزَّن.

    **ولا يحتاج «غيرُ مسدَّدة»**: الخيطُ واحدٌ للزبون، وآخرُ ورقةٍ خرجت هي التي
    يبدأ استحقاقُها عدَّه؛ وحسابُ المتبقّي لكل ورقةٍ صيغةٌ ثانية للرصيد ممنوعة.

    والإشعارُ الدائنُ خارجُ العدّ: ليس مطالبةً كالفاتورة والتكميلية، واستحقاقُه
    ليس استحقاقَ دَين. والملغاةُ مستبعدةٌ بـ`cancelled_at`.
    """
    from accounting_office import fee_invoices

    anchors: dict[int, tuple] = {}
    rows = (
        FeeInvoice.objects
        .filter(
            tenant=tenant,
            client_id__in=client_ids,
            cancelled_at__isnull=True,
            kind__in=(FEE_INVOICE_KIND_INVOICE, FEE_INVOICE_KIND_SUPPLEMENTARY),
        )
        .select_related("client", "source_draft", "related_invoice")
        .order_by("issued_at", "id")
    )
    for invoice in rows:
        due_on = timezone.localdate(invoice.issued_at) + timedelta(
            days=fee_invoices.INVOICE_DUE_DAYS,
        )
        # الأخيرةُ في الترتيب تغلب: `order_by` تصاعديّ فيُكتب كلٌّ فوق ما قبله.
        anchors[invoice.client_id] = (invoice, due_on)
    return anchors


def _enabled_balance_clients(clients, settings_by_client) -> list:
    """زبائنُ نوع «اللي عليه» المفعّل لهم — وإلا فلا بندَ ولا استعلامَ رصيد."""
    enabled = []
    for client in clients:
        resolved = settings_by_client.get(client.pk) or {}
        if settings_registry.REMINDER_BALANCE in (
            resolved.get(services.REMINDER_TYPES_ENABLED_KEY) or []
        ):
            enabled.append(client)
    return enabled


def balance_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """بندُ «اللي عليه» بعد الاستحقاق — **ميلادُه من السجلّ** لا من عدّادٍ مخزَّن.

    - أوّلُه بعد 3 أيام من الاستحقاق، وثانيه بعد 7، ولا ثالث.
    - والعدُّ من صفوف `by_pair` بـ`kind` في `REMINDER_COUNTED_KINDS`: إرسالٌ أو
      «كلّمناه» يرفع الدرجة، والتنحيةُ لا تُعدّ، والإبطالُ يُنقص عدَّه.
    - و«شيل لهذه المرة» تُعيد المؤقّتَ بفاصل الدرجتين ولا تستهلك السقف (نمطُ
      الأوراق) — فلا يعود البندُ غداً بلا سبب.
    - `render_due` تاريخُ الاستحقاق المخزَّن نفسه، فلا يُقرأ في الرسالة يومُ فتحها.
    - **وبلا فاتورةٍ صادرةٍ لا استحقاق**: لا تاريخَ مخزَّناً يُقاس عليه، ولم يُطالَب
      الزبون بورقةٍ بعد. فزبونٌ برصيدٍ بلا ورقة (مسودّةٌ معتمدةٌ لم تُصدر) لا بندَ له.
    """
    if reminder_type is not None and reminder_type != settings_registry.REMINDER_BALANCE:
        return []
    enabled = _enabled_balance_clients(clients, settings_by_client)
    if not enabled:
        return []
    due_map = client_due_map(tenant, enabled)
    anchors = _balance_due_anchor(tenant, [client.pk for client in enabled])
    maximum = len(BALANCE_REMINDER_STEPS)
    candidates = []
    for client in enabled:
        due = due_map.get(client.pk)
        if due is None or due.due <= 0:
            continue
        anchor = anchors.get(client.pk)
        if anchor is None:
            continue
        invoice, due_on = anchor
        pairs = by_pair.get(
            (client.pk, settings_registry.REMINDER_BALANCE, due_on, due_on), [],
        )
        count = sum(
            1 for row in pairs if row["kind"] in REMINDER_COUNTED_KINDS
        )
        step_days = BALANCE_REMINDER_STEPS[min(count, maximum - 1)]
        next_due = due_on + timedelta(days=step_days)
        last_day = max((row["day"] for row in pairs), default=None)
        if last_day is not None:
            # التنحيةُ تُعيد المؤقّتَ لا تُستهلك: آخرُ صفٍّ مؤقّتٍ + الفاصل،
            # والإرسالُ يزيد العدَّ فيُقدّم الدرجةَ كذلك (`max` يجمعهما).
            next_due = max(
                next_due, last_day + timedelta(days=BALANCE_REMINDER_RESET_DAYS),
            )
        contact = contacts.get((client.pk, settings_registry.REMINDER_BALANCE))
        candidates.append(services.ReminderCandidate(
            client=client,
            reminder_type=settings_registry.REMINDER_BALANCE,
            period_start=due_on,
            period_end=due_on,
            missing=(),
            missing_codes=(),
            count=count,
            maximum=maximum,
            interval_days=step_days,
            next_due=next_due,
            contact=contact,
            tax_system=(settings_by_client.get(client.pk) or {}).get(
                services.TAX_SYSTEM_KEY,
            ),
            due=day >= next_due,
            exhausted=count >= maximum,
            postponed=(
                (client.pk, settings_registry.REMINDER_BALANCE) in postponed_pairs
            ),
            render_due=due_on,
            period_text=_balance_period_text(invoice),
            amount=due.due,
            detail=fee_balance_detail(
                due=due.due,
                total=due.invoices_total,
                language=getattr(contact, "language", "") or "ar",
            ),
        ))
    return candidates


def _balance_period_text(invoice) -> str | None:
    """فترةُ الورقة التي يخصّها الاستحقاق — شهرُ مسودّتها لا شهرُ إصدارها."""
    from accounting_office import fee_invoices

    return fee_invoices.document_period_text(invoice)


# ── الكشفُ الشهريّ يوم 1 (#283/ج) ────────────────────────────────────────────
MONTHLY_STATEMENT_TEXTS: dict[str, str] = {
    "ar": (
        "كشفُ حسابك عن {period}: عليك {due} من {total}.\n"
        "فواتيرُ الشهر {invoices}، ودفعاتُه {payments}، والرصيدُ الختاميّ {closing}."
    ),
    "he": (
        "דוח החשבון שלך עבור {period}: עליך {due} מתוך {total}.\n"
        "חשבוניות החודש {invoices}, תשלומים {payments}, "
        "יתרת סוף החודש {closing}."
    ),
}


def statement_reminder_candidates(
    tenant, clients, *, day=None, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """كشفُ الشهر لهذا الزبون — **بندٌ واحدٌ لكل زبونٍ عليه رصيد، يوم 1 وحده**.

    واليومُ يُمرَّر (`day=None` افتراضُه اليوم) فتُقاس الحالةُ بتاريخٍ مُعطى.

    **والشكلُ كشفٌ موجودٌ لا نسخة**: الأرقامُ من `statement_payload` نفسها عند
    بناء الرسالة (`statement_reminder_payload`)، فيُقرأ ما تقرؤه الورقةُ المطبوعة.

    **ولا يتكرّر بعد الإرسال**: مفتاحُه (أوّلُ الشهر، آخرُه)، و`maximum = 1`،
    والعدُّ من السجلّ. وزبونٌ أُرسل له **أيُّ تذكيرٍ** في اليوم نفسه لا يأخذ كشفاً
    ثانياً — فالبندُ الواحدُ لكل زبونٍ في اليوم هو القاعدة (الدَّمجُ في
    `services._with_monthly_statements`، ومن دون قيدٍ هنا يخرج بندان أو يعود
    الكشفُ بنداً مستقلاً بعد إرسال البند الذي دُمج فيه).
    """
    day = day or timezone.localdate()
    if day.day != MONTHLY_STATEMENT_DAY:
        return []
    if reminder_type is not None and reminder_type != settings_registry.REMINDER_BALANCE:
        return []
    enabled = _enabled_balance_clients(clients, settings_by_client)
    if not enabled:
        return []
    due_map = client_due_map(tenant, enabled)
    period_start, period_end = _month_bounds(day)
    reminded_today = {
        key[0]
        for key, rows in by_pair.items()
        if any(
            row["day"] == day and row["kind"] in REMINDER_COUNTED_KINDS
            for row in rows
        )
    }
    candidates = []
    for client in enabled:
        due = due_map.get(client.pk)
        if due is None or due.due <= 0:
            continue
        if client.pk in reminded_today:
            continue
        pair = (client.pk, settings_registry.REMINDER_BALANCE, period_start, period_end)
        count = sum(
            1 for row in by_pair.get(pair, []) if row["kind"] in REMINDER_COUNTED_KINDS
        )
        candidates.append(services.ReminderCandidate(
            client=client,
            reminder_type=settings_registry.REMINDER_BALANCE,
            period_start=period_start,
            period_end=period_end,
            missing=(),
            missing_codes=(),
            count=count,
            maximum=1,
            interval_days=1,
            next_due=day,
            contact=contacts.get((client.pk, settings_registry.REMINDER_BALANCE)),
            tax_system=(settings_by_client.get(client.pk) or {}).get(
                services.TAX_SYSTEM_KEY,
            ),
            due=True,
            exhausted=count >= 1,
            postponed=(
                (client.pk, settings_registry.REMINDER_BALANCE) in postponed_pairs
            ),
            render_due=day,
            amount=due.due,
            # لقطةُ النافذة وحدها: الأرقامُ تُقرأ عند بناء الرسالة، فلا كلفةَ
            # كشفٍ لكل زبونٍ في مسحٍ لن يُرسَل منه شيء (الحواجزُ بعد الحساب).
            statement={
                "from": period_start.isoformat(),
                "to": period_end.isoformat(),
            },
        ))
    return candidates


def statement_reminder_payload(tenant, client, *, day) -> dict:
    """أرقامُ الكشف للرسالة — **من `statement_payload` وحدها** لا صيغةً ثانية.

    والنافذةُ شهرُ اليوم حتى اليوم: ما تحرّك هذا الشهر، والرصيدُ الختاميّ كما
    تقرؤه الورقة، و`due` هو «اللي عليه» الآن من الدالّة الواحدة.
    """
    period_from = date(day.year, day.month, 1)
    sheet = statement_payload(tenant, client, period_from=period_from, period_to=day)
    due = client_due(tenant, client)
    return {
        "from": period_from.isoformat(),
        "to": day.isoformat(),
        "period": deadlines.period_label(period_from, day),
        "due": sheet["due"],
        "total": _text(due.invoices_total),
        "invoices": sheet["totals"]["invoices"],
        "payments": sheet["totals"]["payments"],
        "closing": sheet["closing_balance"],
    }


def statement_reminder_text(statement, language="ar") -> str:
    """نصُّ سطر الكشف — القيمُ الغائبةُ تُنطق شرطةً لا فراغاً يُقرأ خطأً."""
    template = MONTHLY_STATEMENT_TEXTS.get(language, MONTHLY_STATEMENT_TEXTS["ar"])
    absent = "—"
    return template.format(
        period=statement.get("period") or absent,
        due=statement.get("due") or absent,
        total=statement.get("total") or absent,
        invoices=statement.get("invoices") or absent,
        payments=statement.get("payments") or absent,
        closing=statement.get("closing") or absent,
    )
