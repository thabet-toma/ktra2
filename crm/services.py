"""خدمات نواة الـCRM — كلُّ كتابةٍ تمرّ من هنا، لا من الـview مباشرةً.

ترتيب القفل: `Lead` → `LeadTransfer` (حين يلزم قفل الاثنين معاً، `Lead` أوّلاً).
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

# حدودُ اليوم المحلّيّ من الطبقة المشتركة — **لا `__date` أبداً**: جانغو يترجمها
# إلى `DATE(CONVERT_TZ(...))` وجداولُ `mysql.time_zone` فارغةٌ على خادمنا فتعيد
# `NULL` ⇒ صفرُ صفوفٍ بلا خطأٍ ولا أثرٍ في اللوج. الشرحُ كاملاً في الملفّ نفسِه.
from core.date_ranges import local_day_start

# عضويّةُ عنقود المنصّة معلَنةٌ في `platform_ops/tests/test_isolation_guard.py`
# (`PLATFORM_CLUSTER_APPS`)، فالاستيرادُ صريحٌ لا مُخبَّأٌ بـ`apps.get_model`:
# مفاتيحُ `Lead.assigned_to` الأجنبيّةُ تجعل الاعتمادَ قائماً في القاعدة أصلاً.
from platform_ops.models import PlatformEmployee

from .models import Lead, LeadActivity, LeadImportBatch, LeadPhone, LeadTransfer
from .phone import PhoneNormalizationError, normalize_phone


class CrmError(Exception):
    """خطأ عام في خدمات الـCRM."""

    def __init__(self, code: str, detail: str, status_code: int = 400):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class CrmValidationError(CrmError):
    """خطأ تحقّقٍ عادي (400)."""


class CrmConflictError(CrmError):
    """تعارضُ حالة (409) — سباقٌ أو محاولةٌ ثانية على قرارٍ سبق."""

    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


class LeadLockedError(CrmError):
    """العميلُ مُسنَدٌ لغير الفاعل (403) — الحارسُ الذي يمنع كتابة الزميل."""

    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=403)


class DuplicateLeadError(CrmError):
    """الرقمُ مسجَّلٌ سلفاً لعميلٍ آخر (409) — تُرفَع **قبل** الإنشاء وعند سباقٍ نادر."""

    def __init__(self, existing_lead: Lead, matched_e164: str):
        self.existing_lead = existing_lead
        self.matched_e164 = matched_e164
        assigned = existing_lead.assigned_to
        self.assigned_to = {"id": assigned.pk, "name": _employee_display_name(assigned)} if assigned else None
        super().__init__(
            "duplicate_lead_phone", "هذا الرقم مسجَّلٌ لدى عميلٍ آخر.", status_code=409,
        )


def _employee_display_name(employee) -> str:
    user = getattr(employee, "user", None)
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _normalize_phone_entries(phones: list[dict]) -> list[dict]:
    if not phones:
        raise CrmValidationError("phone_required", "رقمُ هاتفٍ واحدٌ على الأقلّ إلزاميّ.")
    normalized = []
    seen = set()
    for entry in phones:
        raw = entry.get("raw") or entry.get("phone") or ""
        kind = entry.get("kind") or LeadPhone.Kind.PRIMARY
        if kind not in LeadPhone.Kind.values:
            raise CrmValidationError("invalid_phone_kind", f"نوع هاتف غير معروف: {kind}")
        # الحدُّ في الخدمة أيضاً لا في المُسلسِل وحده: `create_lead` واجهةٌ عامّةٌ
        # تُنادى مباشرةً (`import_leads` وأدواتُ الإدارة)، و`raw` يُخزَّن كما كُتب
        # في عمودٍ محدودٍ — فاقتطاعُ MySQL الصامتُ يفسد «كما كتبه الزبون».
        raw_width = LeadPhone._meta.get_field("raw").max_length
        if len(raw) > raw_width:
            raise CrmValidationError(
                "phone_too_long", f"رقمُ الهاتف كما كُتب يتجاوز {raw_width} محرفاً.",
            )
        try:
            e164 = normalize_phone(raw)
        except PhoneNormalizationError as exc:
            raise CrmValidationError("invalid_phone", str(exc)) from exc
        if e164 in seen:
            raise CrmValidationError("duplicate_phone_in_request", "رقمان متطابقان في نفس الطلب.")
        seen.add(e164)
        normalized.append({"raw": raw, "kind": kind, "e164": e164})
    return normalized


def _find_existing_phone(e164_values):
    return (
        LeadPhone.objects.filter(e164__in=e164_values)
        .select_related("lead", "lead__assigned_to__user")
        .first()
    )


def create_lead(
    *,
    store_name: str,
    phones: list[dict],
    actor=None,
    source: str = Lead.Source.ADMIN_UPLOAD,
    approval_status: str = Lead.Approval.APPROVED,
    suggested_by=None,
    import_batch: LeadImportBatch | None = None,
    **fields,
) -> Lead:
    """إنشاءُ عميلٍ محتمَل — يكشف تكرار الهاتف **قبل** الإنشاء وتحت سباقٍ أيضاً.

    `phones`: قائمة `{"raw": "...", "kind": "primary"}`. عند التكرار تُرفَع
    `DuplicateLeadError` بلا إنشاء أيّ صفّ.
    """
    store_name = (store_name or "").strip()
    if not store_name:
        raise CrmValidationError("store_name_required", "اسم المحلّ إلزاميّ.")

    normalized = _normalize_phone_entries(phones)
    e164_values = [p["e164"] for p in normalized]

    existing = _find_existing_phone(e164_values)
    if existing:
        raise DuplicateLeadError(existing.lead, existing.e164)

    try:
        with transaction.atomic():
            lead = Lead.objects.create(
                store_name=store_name,
                source=source,
                approval_status=approval_status,
                suggested_by=suggested_by,
                import_batch=import_batch,
                created_by=actor,
                **fields,
            )
            LeadPhone.objects.bulk_create(
                LeadPhone(lead=lead, e164=p["e164"], raw=p["raw"], kind=p["kind"]) for p in normalized
            )
    except IntegrityError:
        # سباقٌ نادر: أُنشئ الرقم بين الفحص والكتابة تحت طلبٍ متزامن.
        existing = _find_existing_phone(e164_values)
        if existing:
            raise DuplicateLeadError(existing.lead, existing.e164) from None
        raise
    return lead


def lookup_lead_by_phone(raw: str, *, requesting_employee=None) -> dict:
    """«هل هذا الرقم مأخوذ؟» — تعمل على رقم زميلٍ أيضاً، بلا كشف سجلّ تواصله."""
    try:
        e164 = normalize_phone(raw)
    except PhoneNormalizationError as exc:
        raise CrmValidationError("invalid_phone", str(exc)) from exc

    phone = LeadPhone.objects.filter(e164=e164).select_related("lead", "lead__assigned_to__user").first()
    if not phone:
        return {"normalized": e164, "found": False, "lead": None, "locked_by": None,
                "can_claim": False, "is_mine": False}

    lead = phone.lead
    assigned = lead.assigned_to
    is_mine = bool(assigned and requesting_employee and assigned.pk == requesting_employee.pk)
    can_claim = assigned is None and lead.approval_status == Lead.Approval.APPROVED
    return {
        "normalized": e164,
        "found": True,
        "lead": {"id": lead.pk, "store_name": lead.store_name, "status": lead.status},
        "locked_by": {"id": assigned.pk, "name": _employee_display_name(assigned)} if assigned else None,
        "can_claim": can_claim,
        "is_mine": is_mine,
    }


@transaction.atomic
def claim_lead(*, lead: Lead, employee) -> Lead:
    """استلامُ عميلٍ من المخزن المتاح — يشترط `assigned_to is None` و`approved`."""
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if locked.approval_status != Lead.Approval.APPROVED:
        raise CrmValidationError("lead_not_approved", "هذا العميلُ بانتظار الاعتماد.")
    if locked.assigned_to_id is not None:
        raise CrmConflictError("lead_already_claimed", "هذا العميلُ مُسنَدٌ بالفعل.")
    locked.assigned_to = employee
    locked.assigned_at = timezone.now()
    locked.save(update_fields=["assigned_to", "assigned_at", "updated_at"])
    LeadActivity.objects.create(
        lead=locked, employee=employee, actor=getattr(employee, "user", None),
        kind=LeadActivity.Kind.ASSIGNMENT, body="استلامٌ من المخزن المتاح.",
    )
    return locked


@transaction.atomic
def release_lead(*, lead: Lead, actor, reason: str = "") -> Lead:
    """إعادةُ عميلٍ إلى المخزن المتاح — للمدير."""
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    previous = locked.assigned_to
    locked.assigned_to = None
    locked.assigned_at = None
    locked.save(update_fields=["assigned_to", "assigned_at", "updated_at"])
    LeadActivity.objects.create(
        lead=locked, employee=previous, actor=actor,
        kind=LeadActivity.Kind.ASSIGNMENT, body=reason or "إعادةٌ إلى المخزن المتاح.",
    )
    return locked


#: ذرّيّةٌ لأنّها تكتب صفّين: النشاطَ، وموعدَ المتابعة على `Lead`. و`ATOMIC_REQUESTS`
#: غيرُ مضبوطٍ في هذا المستودع، فبلا هذا المزخرِف يمكن أن يُعتمَد نشاطٌ يَعِد
#: بمتابعةٍ في تاريخٍ لا يحمله العميلُ نفسُه.
@transaction.atomic
def log_activity(
    *, lead: Lead, employee, kind: str, actor=None, is_manager: bool = False,
    body: str = "", outcome: str = "", materials=None, next_follow_up_at=None,
) -> LeadActivity:
    """تسجيلُ نشاط تواصل — يرفض إن لم يكن `employee` صاحبَ العميل ولا الفاعلُ مديراً."""
    if not is_manager and (employee is None or lead.assigned_to_id != employee.pk):
        raise LeadLockedError("lead_not_yours", "هذا العميلُ مُسنَدٌ لموظّفٍ آخر.")
    if kind not in LeadActivity.Kind.values:
        raise CrmValidationError("invalid_activity_kind", f"نوع نشاط غير معروف: {kind}")

    activity = LeadActivity.objects.create(
        lead=lead, employee=employee, actor=actor, kind=kind, body=body,
        outcome=outcome, materials=materials or [], next_follow_up_at=next_follow_up_at,
    )
    if next_follow_up_at is not None:
        Lead.objects.filter(pk=lead.pk).update(next_follow_up_at=next_follow_up_at)
    return activity


@transaction.atomic
def change_lead_status(
    *, lead: Lead, employee, status: str, actor=None, is_manager: bool = False, body: str = "",
) -> Lead:
    """تغييرُ حالة العميل — نفسُ حارس الملكية، ويكتب نشاط `status_change`."""
    if status not in Lead.Status.values:
        raise CrmValidationError("invalid_status", f"حالةٌ غير معروفة: {status}")
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if not is_manager and (employee is None or locked.assigned_to_id != employee.pk):
        raise LeadLockedError("lead_not_yours", "هذا العميلُ مُسنَدٌ لموظّفٍ آخر.")

    before = locked.status
    locked.status = status
    locked.save(update_fields=["status", "updated_at"])
    LeadActivity.objects.create(
        lead=locked, employee=employee, actor=actor, kind=LeadActivity.Kind.STATUS_CHANGE,
        body=body, status_before=before, status_after=status,
    )
    return locked


@transaction.atomic
def transfer_lead(
    *, lead: Lead, to_employee, reason: str, actor, actor_employee=None, is_manager: bool = False,
) -> LeadTransfer:
    """تحويلٌ مباشر — صاحبُ العميل أو المدير، فيُعاد الإسنادُ فوراً."""
    reason = (reason or "").strip()
    if not reason:
        raise CrmValidationError("reason_required", "سببُ التحويل إلزاميّ.")

    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if not is_manager and (actor_employee is None or locked.assigned_to_id != actor_employee.pk):
        raise LeadLockedError("lead_not_yours", "هذا العميلُ مُسنَدٌ لموظّفٍ آخر.")

    now = timezone.now()
    transfer = LeadTransfer.objects.create(
        lead=locked, from_employee=locked.assigned_to, to_employee=to_employee, reason=reason,
        requested_by=actor, decided_by=actor, status=LeadTransfer.Status.APPROVED, decided_at=now,
    )
    locked.assigned_to = to_employee
    locked.assigned_at = now
    locked.save(update_fields=["assigned_to", "assigned_at", "updated_at"])
    LeadActivity.objects.create(
        lead=locked, employee=to_employee, actor=actor, kind=LeadActivity.Kind.TRANSFER, body=reason,
    )
    return transfer


@transaction.atomic
def request_lead_transfer(*, lead: Lead, to_employee, reason: str, actor) -> LeadTransfer:
    """طلبُ تحويلٍ معلَّق — يبتّ فيه المديرُ أو صاحبُ العميل. طلبٌ واحدٌ معلَّق لكلّ عميل."""
    reason = (reason or "").strip()
    if not reason:
        raise CrmValidationError("reason_required", "سببُ التحويل إلزاميّ.")

    # **صاحبُ العميل لا يَطلُب، بل يُحوّل.** بلا هذا الحارس كان يستطيع فتحَ طلبٍ
    # على عميلِ نفسِه، فيُسجَّل `from_employee == to_employee`ـه هو، **ويسدُّ
    # بابَه**: أيُّ تحويلٍ لاحقٍ يُرفَض بـ`transfer_already_pending` حتى يبتَّ
    # أحدٌ في طلبٍ لا معنى له. وليس هذا احتمالاً نظريّاً: الواجهةُ كانت تعرف
    # «هل أنا صاحبُه؟» من دليل الزملاء، وذلك الدليلُ يستثني غيرَ `active`
    # فيُسقِط الموظّفَ من دليلِ نفسِه وهو في إجازة.
    actor_employee = getattr(actor, "platform_employee", None)
    if actor_employee is not None and lead.assigned_to_id == actor_employee.pk:
        raise CrmValidationError(
            "owner_transfers_directly",
            "أنت صاحبُ هذا العميل — حوِّله مباشرةً بلا طلب.",
        )

    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    already_pending = LeadTransfer.objects.select_for_update().filter(
        lead=locked, status=LeadTransfer.Status.PENDING,
    ).exists()
    if already_pending:
        raise CrmConflictError("transfer_already_pending", "يوجد طلبُ تحويلٍ معلَّقٌ لهذا العميل بالفعل.")

    return LeadTransfer.objects.create(
        lead=locked, from_employee=locked.assigned_to, to_employee=to_employee,
        reason=reason, requested_by=actor, status=LeadTransfer.Status.PENDING,
    )


@transaction.atomic
def decide_lead_transfer(*, transfer: LeadTransfer, approve: bool, actor, note: str = "") -> LeadTransfer:
    """البتُّ في طلب تحويل معلَّق — القبولُ يعيد الإسناد، والرفضُ يحفظ الملاحظة."""
    locked_transfer = LeadTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked_transfer.status != LeadTransfer.Status.PENDING:
        raise CrmValidationError("transfer_not_pending", "طلبُ التحويل ليس معلَّقاً.")

    now = timezone.now()
    if not approve:
        locked_transfer.status = LeadTransfer.Status.REJECTED
        locked_transfer.decided_by = actor
        locked_transfer.decided_at = now
        if note:
            locked_transfer.reason = f"{locked_transfer.reason}\n[رفض]: {note}"
        locked_transfer.save(update_fields=["status", "decided_by", "decided_at", "reason"])
        return locked_transfer

    locked_lead = Lead.objects.select_for_update().get(pk=locked_transfer.lead_id)
    locked_transfer.status = LeadTransfer.Status.APPROVED
    locked_transfer.decided_by = actor
    locked_transfer.decided_at = now
    locked_transfer.save(update_fields=["status", "decided_by", "decided_at"])

    locked_lead.assigned_to = locked_transfer.to_employee
    locked_lead.assigned_at = now
    locked_lead.save(update_fields=["assigned_to", "assigned_at", "updated_at"])
    LeadActivity.objects.create(
        lead=locked_lead, employee=locked_transfer.to_employee, actor=actor,
        kind=LeadActivity.Kind.TRANSFER, body=note or locked_transfer.reason,
    )
    return locked_transfer


def suggest_lead(*, store_name: str, phones: list[dict], employee, actor, **fields) -> Lead:
    """اقتراحُ عميلٍ من موظّف — `pending` ولا يظهر في المخزن حتى يعتمده المدير."""
    return create_lead(
        store_name=store_name, phones=phones, actor=actor,
        source=Lead.Source.EMPLOYEE_SUGGESTION, approval_status=Lead.Approval.PENDING,
        suggested_by=employee, **fields,
    )


@transaction.atomic
def approve_lead(*, lead: Lead, actor) -> Lead:
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if locked.approval_status != Lead.Approval.PENDING:
        raise CrmValidationError("not_pending", "هذا العميلُ ليس بانتظار الاعتماد.")
    locked.approval_status = Lead.Approval.APPROVED
    locked.save(update_fields=["approval_status", "updated_at"])
    return locked


@transaction.atomic
def reject_lead(*, lead: Lead, actor, reason: str) -> Lead:
    reason = (reason or "").strip()
    if not reason:
        raise CrmValidationError("reason_required", "سببُ الرفض إلزاميّ.")
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if locked.approval_status != Lead.Approval.PENDING:
        raise CrmValidationError("not_pending", "هذا العميلُ ليس بانتظار الاعتماد.")
    locked.approval_status = Lead.Approval.REJECTED
    locked.rejection_reason = reason
    locked.save(update_fields=["approval_status", "rejection_reason", "updated_at"])
    return locked


@transaction.atomic
def import_leads(*, rows: list[dict], uploaded_by, file_name: str = "") -> LeadImportBatch:
    """استيرادُ دفعةٍ — صفٌّ مكرَّرٌ لا يُنشأ ولا يُسقِط الدفعة؛ يُسجَّل في `duplicates`."""
    rows = list(rows)
    batch = LeadImportBatch.objects.create(uploaded_by=uploaded_by, file_name=file_name, total_rows=len(rows))

    duplicates = []
    created = 0
    invalid = 0
    for index, row in enumerate(rows, start=1):
        store_name = (row.get("store_name") or "").strip()
        raw_phone = row.get("phone") or ""
        if not store_name or not raw_phone:
            invalid += 1
            continue
        extra_fields = {
            key: row[key] for key in ("owner_name", "city", "address", "activity") if row.get(key)
        }
        try:
            create_lead(
                store_name=store_name,
                phones=[{"raw": raw_phone, "kind": LeadPhone.Kind.PRIMARY}],
                actor=uploaded_by,
                source=Lead.Source.ADMIN_UPLOAD,
                approval_status=Lead.Approval.APPROVED,
                import_batch=batch,
                **extra_fields,
            )
            created += 1
        except DuplicateLeadError as exc:
            duplicates.append({
                "row": index,
                "phone": exc.matched_e164,
                "existing_lead_id": exc.existing_lead.pk,
                "existing_lead_name": exc.existing_lead.store_name,
                "assigned_to_name": exc.assigned_to["name"] if exc.assigned_to else None,
            })
        except CrmValidationError:
            invalid += 1

    batch.created_count = created
    batch.duplicate_count = len(duplicates)
    batch.invalid_count = invalid
    batch.duplicates = duplicates
    batch.save(update_fields=["created_count", "duplicate_count", "invalid_count", "duplicates"])
    return batch


def follow_up_day_bounds() -> tuple:
    """حدُّ «اليوم» لمتابعات العملاء — **تعريفٌ واحدٌ لا ثلاثة**.

    الشاشةُ تكتب **تاريخاً** يختاره الموظّف وتُلحق به `T09:00:00` اعتباطاً، فوَحدةُ
    الصدق هنا يومٌ لا لحظة. وكان «متأخّر» يُقاس بـ`now` في ثلاثة مواضعَ مستقلّة
    (شارةُ البطاقة، وعدّادُ الموظّف، ومرشّحُ القائمة)، فينتج:

    - موعدٌ **لليوم** لا يظهر في «متابعاتي» صباحاً: الموظّفُ يفتح متابعاتِه في
      الثامنة فلا يرى عملَ يومِه، ثمّ يظهر في التاسعة وواحدةٍ **متأخّراً فوراً**؛
    - و`due` (`__lte=now`) و`overdue` (`__lt=now`) مجموعتان **متطابقتان عمليّاً**:
      ثلاثةُ أسماءٍ لسلوكَين.

    فالقاعدةُ: «مستحقّة» = اليومَ أو قبلَه · «متأخّرة» = يومٌ مضى · «قادمة» = بعد
    اليوم. ثلاثُ مجموعاتٍ متمايزةٍ فعلاً، و`overdue ⊂ due`.
    """
    today = timezone.localdate()
    return local_day_start(today), local_day_start(today + timedelta(days=1))


def employee_lead_stats(employee) -> dict:
    """مؤشّرات موظف واحد، ومنها عدّاد المتأخّر — استعلام مجمَّع واحد."""
    start_of_today, _ = follow_up_day_bounds()
    rows = (
        Lead.objects.filter(assigned_to=employee)
        .values("status")
        .annotate(
            n=Count("id"),
            overdue=Count("id", filter=Q(next_follow_up_at__lt=start_of_today)),
        )
    )
    counts = {row["status"]: row["n"] for row in rows}
    overdue = sum(row["overdue"] for row in rows)
    return {
        "assigned": sum(counts.values()),
        "contacted": counts.get(Lead.Status.CONTACTED, 0),
        "interested": counts.get(Lead.Status.INTERESTED, 0),
        "follow_up": counts.get(Lead.Status.FOLLOW_UP, 0),
        "customer": counts.get(Lead.Status.CUSTOMER, 0),
        "not_interested": counts.get(Lead.Status.NOT_INTERESTED, 0),
        "overdue": overdue,
    }


def manager_lead_overview() -> dict:
    """لكل موظف عداد حالاته والمتأخر، بعدد استعلامات ثابت بلا حلقة N+1."""
    start_of_today, _ = follow_up_day_bounds()
    rows = (
        Lead.objects.filter(assigned_to__isnull=False)
        .values("assigned_to_id", "status")
        .annotate(
            n=Count("id"),
            overdue=Count("id", filter=Q(next_follow_up_at__lt=start_of_today)),
        )
    )
    by_employee: dict[int, dict] = {}
    for row in rows:
        counts = by_employee.setdefault(row["assigned_to_id"], {"by_status": {}, "overdue": 0})
        counts["by_status"][row["status"]] = row["n"]
        counts["overdue"] += row["overdue"]

    employees = PlatformEmployee.objects.select_related("user").all()
    overview = []
    for employee in employees:
        counts = by_employee.get(employee.pk, {"by_status": {}, "overdue": 0})
        overview.append({
            "employee_id": employee.pk,
            "employee_name": _employee_display_name(employee),
            "total": sum(counts["by_status"].values()),
            "by_status": counts["by_status"],
            "overdue": counts["overdue"],
        })

    pool_size = Lead.objects.filter(assigned_to__isnull=True, approval_status=Lead.Approval.APPROVED).count()
    return {"employees": overview, "pool_size": pool_size}
