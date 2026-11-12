"""التزامُ المكتب نفسه «من المنصة» (#290/ج) — سجلٌّ مستقلّ عن التزامات الزبائن.

**لماذا سجلٌّ ثالثٌ لا صفٌّ في `Obligation`:** `Obligation` التزامُ **زبون** —
له `client` و`client_service` و`Obligation` قيومُه وفرادةُ `(client_service,
rule_code, period_end)`، وكلُّ عدّادٍ في الموديول يعُدّ صفوفَه على هذا الأساس.
مكتبٌ يُلتزَم عنه (بيانُ أسماء زبائنه للدائرة، م111) ليس زبوناً عند نفسه، وتمثيلُه
زبوناً كان يجعل قوائمَ الزبائن والأوراق والأتعاب و«للإدخال» تكذب بأثرٍ لا علاقة
له بالزبائن — وهذا ما منعته التذكرة صراحةً (قرارُ المالك: **سجلٌّ مستقلّ**).

**ولائحتُه في الكود** (`deadlines.OFFICE_SELF_DEADLINES`) لا صفوفُ منصّةٍ جديدة
ولا هجرةُ بيانات: بندٌ واحدٌ اليوم، وإضافةُ ثانٍ سطرٌ في تلك القائمة.

**والتوليدُ `get_or_create` على المفتاح الطبيعيّ** `(tenant, rule_code,
period_start)`، فتشغيلُ «حدّث المكتب» مرّتين في اليوم نفسه لا يكتب صفّاً —
القاعدةُ نفسها التي تجعل `refresh_office` idempotent.
"""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounting_office import deadlines
from accounting_office.models import (
    OFFICE_SELF_STATUS_LABELS,
    OFFICE_SELF_STATUS_NOT_REQUIRED,
    OFFICE_SELF_STATUS_PENDING,
    OFFICE_SELF_STATUS_SUBMITTED,
    OfficeSelfObligation,
)

#: مصدرُ الصفّ كما يُعرض: لائحةُ المنصّة لا إدخالُ المكتب.
SOURCE_PLATFORM = "platform"
SOURCE_LABELS: dict[str, str] = {SOURCE_PLATFORM: "المنصة"}

#: رسالةُ رفض الكتابة — واحدةٌ للثلاثة (تقديمٌ وإرجاعٌ وتعديل)، والسببُ فيها مسمّى.
WRITER_ONLY_MESSAGE = (
    "التزامُ المكتب نفسه يُكتب بالدور — صاحبُ المكتب أو مديرُه، لا بمفتاح "
    "الكتابة."
)

#: «قُدِّم» نهائيٌّ كالتزام الزبون، والرسالةُ تقول لماذا لا يُعاد.
ALREADY_SUBMITTED_MESSAGE = (
    "قُدِّم هذا البند بالفعل — التصحيحُ تصريحٌ جديدٌ للدائرة لا إعادةُ تقديمٍ هنا."
)

#: لا كتابة على بندٍ غادر «بالانتظار» — والحالتان الأخريان ممثَّلتان بلا رجوع.
NOT_PENDING_MESSAGE = "هذا البند لم يبقَ «بالانتظار» — لا فعلَ عليه الآن."


def _assert_writer(tenant, actor) -> None:
    """الكتابةُ لدورٍ في `ENTRY_APPROVER_ROLES` وحدها — **403 لا 400**.

    والمفتاحُ لا يكفي: المحاسبُ يملك `office.clients.write`، والمنعُ دورٌ لا
    صلاحية (نمط `client_books._assert_entry_writer` و`payments.can_write_off`).
    و`actor=None` نداءٌ داخليٌّ محض؛ الـviews تمرّر المستخدمَ دائماً.
    """
    # استيرادٌ كسول: `client_books` يستورد `services`، وهذه الوحدة يقرؤها
    # `services.refresh_office` — فالثوابتُ تُقرأ وقتَ الحاجة لا وقتَ الإقلاع.
    from accounting_office.client_books import ENTRY_APPROVER_ROLES
    from core.access import user_tenant_role

    if actor is None:
        return
    if user_tenant_role(actor, tenant) not in ENTRY_APPROVER_ROLES:
        raise PermissionDenied(WRITER_ONLY_MESSAGE)


def can_write_self_obligations(tenant, user) -> bool:
    """هل يملك هذا العضو كتابةَ التزام المكتب؟ — للواجهة، والحكمُ للخادم."""
    from accounting_office.client_books import ENTRY_APPROVER_ROLES
    from core.access import user_tenant_role

    return user_tenant_role(user, tenant) in ENTRY_APPROVER_ROLES


def _office_tax_system(tenant):
    """نظامُ المكتب الضريبيّ من محلّله الواحد — لا قراءةً خامّةً لجدول الإعدادات."""
    from accounting_office import services

    return services.resolve_setting(tenant, services.TAX_SYSTEM_KEY)


# ── التوليد (يُنادى من `services.refresh_office` وحده) ───────────────────────
def sync_self_obligations(tenant, *, day) -> int:
    """يولّد بنودَ لائحة المكتب المنطبقة على نظامه — ويُرجع **ما أنشأه هذا النداء**.

    **ولا يولّد لمكتبٍ بلا نظامٍ ضريبيّ بعد**: النظامُ يُختار في أول تشغيل،
    والتزامٌ قبل اختياره تخمينٌ — وقائمةُ البنود تصفيةٌ بنظامه.
    """
    tax_system = _office_tax_system(tenant)
    created = 0
    with transaction.atomic():
        for spec in deadlines.self_deadlines_for(tax_system):
            period_start, period_end, due_on = deadlines.self_deadline_period(
                spec, day,
            )
            _row, was_created = OfficeSelfObligation.objects.get_or_create(
                tenant=tenant,
                rule_code=spec.rule_code,
                period_start=period_start,
                defaults={
                    "name": spec.name,
                    "period_end": period_end,
                    "due_on": due_on,
                },
            )
            created += int(was_created)
    return created


# ── القراءة ──────────────────────────────────────────────────────────────────
def self_obligation_row(row, *, day=None) -> dict:
    """سطرُ البند كما يُعرض — و**المشتقُّ يُحسب هنا ولا يُخزَّن**.

    `days_left` فرقُ أيامٍ من اليوم إلى الموعد (سالبٌ بعد فواته)، و`is_late`
    بندٌ منتظرٌ فات موعدُه. والبندُ المقدَّم أو «غير مطلوب» لا «متأخّر» أبداً،
    ولو كان تاريخُه ماضياً — الحالةُ سبقت الموعد.
    """
    day = day or timezone.localdate()
    days_left = (row.due_on - day).days
    return {
        "id": row.pk,
        "rule_code": row.rule_code,
        "name": row.name,
        "source": SOURCE_PLATFORM,
        "source_label": SOURCE_LABELS[SOURCE_PLATFORM],
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "due_on": row.due_on.isoformat(),
        "days_left": days_left,
        "is_late": row.status == OFFICE_SELF_STATUS_PENDING and days_left < 0,
        "status": row.status,
        "status_label": OFFICE_SELF_STATUS_LABELS.get(row.status, row.status),
        "submitted_on": (
            row.submitted_on.isoformat() if row.submitted_on else None
        ),
        "note": row.note,
    }


def self_obligations_payload(tenant, *, user, day=None) -> dict:
    """حمولةُ القائمة: الصفوفُ الأقربَ موعداً أولاً، و`can_write` قرارُ الخادم.

    `can_write` يُرسَل في الحمولة فيُخفي الواجهةُ الأزرارَ لمن لا يملكها بدل
    زرٍّ يردّ 403 — والحكمُ يبقى هنا لا في الشاشة.
    """
    day = day or timezone.localdate()
    rows = [
        self_obligation_row(row, day=day)
        for row in OfficeSelfObligation.objects.filter(tenant=tenant).order_by(
            "due_on", "id",
        )
    ]
    can_write = can_write_self_obligations(tenant, user)
    for row in rows:
        row["can_write"] = can_write
    return {
        "rows": rows,
        "total": len(rows),
        "pending": sum(
            1 for row in rows if row["status"] == OFFICE_SELF_STATUS_PENDING
        ),
        "can_write": can_write,
    }


# ── الأفعال ──────────────────────────────────────────────────────────────────
def _clean_note(note) -> str:
    """الملاحظةُ نصٌّ قصير — تُطبَّع، وطولُها سقفُ العمود لا يقتطعها MySQL صامتاً."""
    text = (note or "").strip()
    limit = OfficeSelfObligation._meta.get_field("note").max_length
    if len(text) > limit:
        raise ValidationError({
            "note": f"الملاحظة أطول من {limit} محرفاً.",
        })
    return text


def _assert_pending(row) -> None:
    if row.status == OFFICE_SELF_STATUS_SUBMITTED:
        raise ValidationError({"status": ALREADY_SUBMITTED_MESSAGE})
    if row.status != OFFICE_SELF_STATUS_PENDING:
        raise ValidationError({"status": NOT_PENDING_MESSAGE})


def submit_self_obligation(row, *, actor, submitted_on=None, note="") -> OfficeSelfObligation:
    """«قُدِّم» — تاريخٌ اختياريّ (افتراضُه اليوم)، والملاحظةُ اختيارية.

    **نهائيٌّ كالالتزام** (`submit_obligation`): الثاني يُرفض 400 برسالته، لأن
    «قدّمتُه ثم قدّمتُه ثانيةً» ليس تصحيحاً بل تكرارُ إقرارٍ على جهةٍ واحدة.
    """
    _assert_writer(row.tenant, actor)
    with transaction.atomic():
        locked = (
            OfficeSelfObligation.objects.select_for_update().get(pk=row.pk)
        )
        _assert_pending(locked)
        locked.status = OFFICE_SELF_STATUS_SUBMITTED
        locked.submitted_on = submitted_on or timezone.localdate()
        locked.note = _clean_note(note)
        locked.save(update_fields=["status", "submitted_on", "note", "updated_at"])
    return locked


def dismiss_self_obligation(row, *, actor, note="") -> OfficeSelfObligation:
    """«غير مطلوب» — إسقاطُ بندٍ لا يُقدَّم هذه السنة، **بلا تاريخِ تقديم**.

    وليس حذفاً: الصفُّ يبقى فيُقرأ لماذا لم يُقدَّم، كما في `not_required` على
    التزام الزبون.
    """
    _assert_writer(row.tenant, actor)
    with transaction.atomic():
        locked = (
            OfficeSelfObligation.objects.select_for_update().get(pk=row.pk)
        )
        _assert_pending(locked)
        locked.status = OFFICE_SELF_STATUS_NOT_REQUIRED
        locked.submitted_on = None
        locked.note = _clean_note(note)
        locked.save(update_fields=["status", "submitted_on", "note", "updated_at"])
    return locked


# ── موعدُ المكتب نفسه، بتسميته المحلية ───────────────────────────────────────
def self_deadline_label(row) -> str:
    """تسميةُ فترة البند للإسناد في الشاشة — من `deadlines.period_label` وحدها."""
    return deadlines.period_label(row.period_start, row.period_end)
