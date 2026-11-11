"""الدفعات و«اللي عليه» وكشف الحساب (#283، الجزء أ — الخادم).

**المالُ هنا مشتقٌّ لا مخزَّن، والاتّجاهُ واحد:**

    remaining(مسودّة) = total − Σ allocations − Σ write_offs   (لا تسقط تحت الصفر)
    credit(زبون)      = Σ(payment.amount − Σ allocations(payment))
    due(زبون)         = Σ remaining(المعتمدة) − credit            (قد يكون سالباً)

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
from datetime import date
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

from accounting_office import fees, services
from accounting_office.models import (
    FEE_DRAFT_STATUS_APPROVED,
    FEE_PAYMENT_METHOD_CHOICES,
    FEE_PAYMENT_METHOD_LABELS,
    OBLIGATION_DIRECTION_REFUND,
    OBLIGATION_STATUS_NOT_REQUIRED,
    FeeDraft,
    FeePayment,
    FeePaymentAllocation,
    FeeReceiptSequence,
    FeeWriteOff,
    Obligation,
    assert_positive_fee_amount,
)
from core.access import MANAGER_ROLE, user_tenant_role

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


def with_invoice_totals(queryset):
    """يُلحق بكل مسودّة: `paid_amount` و`written_amount` و`remaining` (≥ 0)."""
    return queryset.annotate(
        paid_amount=_relation_sum(FeePaymentAllocation, "draft"),
        written_amount=_relation_sum(FeeWriteOff, "draft"),
    ).annotate(
        remaining=Greatest(
            ExpressionWrapper(
                F("total") - F("paid_amount") - F("written_amount"),
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
    """ملخّصُ فاتورةٍ واحد: ما دُفع عليها وما شُطب وما بقي وحالتُه."""

    paid_amount: Decimal
    written_amount: Decimal
    remaining: Decimal
    state: str
    state_label: str


def _summary(*, paid_amount, written_amount, total, remaining) -> InvoiceSummary:
    """الملخّصُ من أربعة أرقام — **موضعٌ واحد** للحالة وتسميتها، ووسائطُ مُسمّاةٌ فلا يُبدَّل ترتيبها."""
    state = invoice_state(total, remaining)
    return InvoiceSummary(
        paid_amount=_money(paid_amount),
        written_amount=_money(written_amount),
        remaining=_money(remaining),
        state=state,
        state_label=INVOICE_STATE_LABELS.get(state, ""),
    )


def _summary_from_row(row) -> InvoiceSummary:
    return _summary(
        paid_amount=row.paid_amount,
        written_amount=row.written_amount,
        total=row.total,
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


def client_due_map(tenant, clients) -> dict[int, ClientDue]:
    """«اللي عليه» لكل زبونٍ في المجموعة — استعلامان لا استعلامان لكل زبون.

    والدالّةُ تُجمع **`Σ remaining` نصّاً** لا `invoices_total − المغطّى`: هما
    متساويان اليوم لأن `remaining` مقصوصةٌ عند الصفر بأمرٍ مؤجَّلٍ مسجَّل، أيُّ
    تعديلٍ عليه يفتَرق عن الصيغة المكتوبة. و`paid_total` هو **المدفوع فعلاً**
    (تخصيصاتُ دفعاتٍ لا شطوبِ مكتب)، و`due` لا يُعاد بناؤه منه بعد شطب.
    """
    ids = _client_ids(clients)
    if not ids:
        return {}
    totals = {pk: [Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), 0] for pk in ids}
    rows = (
        with_invoice_totals(
            FeeDraft.objects.filter(
                tenant=tenant,
                client_id__in=ids,
                status=FEE_DRAFT_STATUS_APPROVED,
            ),
        )
        .values("client_id", "total", "paid_amount", "remaining")
        .order_by()
    )
    for row in rows:
        bucket = totals[row["client_id"]]
        remaining = _money(row["remaining"])
        bucket[0] += _money(row["total"])
        bucket[1] += _money(row["paid_amount"])
        bucket[2] += remaining
        if remaining > 0:
            bucket[3] += 1
    credits = _credits_map(tenant, ids)
    result: dict[int, ClientDue] = {}
    for client_id, (invoices_total, paid_total, remaining_total, unpaid_count) in totals.items():
        credit = credits.get(client_id, Decimal("0.00"))
        result[client_id] = ClientDue(
            due=_money(_money(remaining_total) - credit),
            invoices_total=_money(invoices_total),
            paid_total=_money(paid_total),
            credit=_money(credit),
            unpaid_count=unpaid_count,
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
    """
    clients = list(clients)
    masked = amounts_masked(tenant, user) if masked is None else masked
    dues = client_due_map(tenant, clients)
    notes = client_tax_notes_map(tenant, clients)
    payload: dict[int, dict] = {}
    for client_id, due in dues.items():
        data = {
            "due": due.due,
            "invoices_total": due.invoices_total,
            "paid_total": due.paid_total,
            "credit": due.credit,
            "unpaid_count": due.unpaid_count,
            "tax_note": notes.get(client_id, Decimal("0.00")),
        }
        payload[client_id] = (
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
        return FeeWriteOff.objects.create(
            tenant_id=locked.tenant_id,
            draft=locked,
            amount=amount,
            reason=reason,
            created_by=actor,
        )


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


def payment_row(payment, *, masked, client_due=None) -> dict:
    """سطرُ دفعة — ومعه **رصيدُ الزبون الدائنُ وما عليه** من `client_due` وحدها.

    `client_due` هو **حمولةُ الزبون** (`client_dues_payload`) لا مبلغُ `due`: تُمرَّر
    مجمَّعةً حين تُقرأ قائمةٌ فلا استعلامان لكل صفّ، وتُحسب للصفّ المفرد حين تغيب.
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
    """قائمةُ دفعاتٍ بحمولةٍ واحدة: القناعُ والأرصدةُ تُحسب مرّةً لا لكل صفّ."""
    masked = amounts_masked(tenant, user)
    rows = list(queryset if queryset is not None else visible_payments(tenant, user))
    dues = client_dues_payload(
        tenant, [row.client for row in rows], user=user, masked=masked,
    )
    return [
        payment_row(row, masked=masked, client_due=dues.get(row.client_id))
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
        "total": draft.total,
        "paid_amount": summary.paid_amount,
        # ما شُطب منها — يظهر هنا وفي صفوف `write_offs` معاً (#283): `remaining`
        # وحدها لا تقول لِمَ نقصت.
        "written_amount": summary.written_amount,
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
        return Q(remaining__gt=0) & Q(remaining__lt=F("total"))
    return Q(remaining=F("total")) & Q(remaining__gt=0)


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
    payment_page["results"] = [
        payment_row(
            row, masked=masked, client_due=payment_dues.get(row.client_id),
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
