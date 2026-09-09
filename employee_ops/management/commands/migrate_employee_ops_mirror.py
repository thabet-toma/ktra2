# -*- coding: utf-8 -*-
"""أمر هجرة بيانات متابعة الموظفين من مرآة bridge (المواصفة #186 — المرحلة ٧).

ينقل الوثائق من `bridge.FirestoreMirrorDoc` إلى نماذج `employee_ops`:
  - tasks/<id> -> Task + TaskAssignment + TaskSubmission + TaskSubmissionItem
  - pointsHistory/<userId>/days/<YYYY-MM-DD> -> PointEntry (لكل فئة غير صفرية)
  - users/<userId> -> EmployeeNote (الملاحظة الأولى بكاتب None)

القواعد الحديدية:
  1. عزل تام: لا استيراد مباشر لـ bridge (عبر apps.get_model).
  2. نسب محكم: لا default=1، ولا تخمين. ما لا يُحسم يُترك مع بيان السبب.
  3. أمان إعادة التشغيل: idempotency عبر (tenant, source_path) دون تعديل المرآة.
  4. --dry-run إلزامي ولا يكتب أي صف في قاعدة البيانات.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
import logging

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from hr.models import Employee
from tenants.models import UserCompanyMembership

from employee_ops.models import (
    EmployeeNote,
    PointEntry,
    Task,
    TaskAssignment,
    TaskSubmission,
    TaskSubmissionAttachment,
    TaskSubmissionItem,
)
from employee_ops.serializers import normalize_priority

logger = logging.getLogger(__name__)

KNOWN_TASK_KEYS = {
    "title", "description", "priority", "status",
    "due_date", "dueDate", "category", "tags",
    "target_price", "targetPrice", "allowed_sites", "allowedSites",
    "created_by", "createdBy", "completed_at", "completedAt",
    "assignedTo", "userStatuses", "submissions", "createdAt", "updatedAt",
    "id", "taskId",
}

KNOWN_ASSIGNMENT_KEYS = {
    "status", "startedAt", "started_at", "completedAt", "completed_at",
    "workStartedAt", "work_started_at", "totalWorkTime", "total_work_seconds",
}

KNOWN_SUBMISSION_KEYS = {
    "id", "taskId", "task_id", "userId", "user_id", "createdAt", "created_at",
    "updatedAt", "updated_at", "status", "decision", "reviewerNotes", "reviewer_notes",
    "reviewedAt", "reviewed_at", "reviewedBy", "reviewed_by", "body", "items", "attachments",
}

KNOWN_ITEM_KEYS = {
    "id", "productLink", "product_link", "productPrice", "product_price",
    "notes", "attachmentUrl", "attachment_url", "attachmentName", "attachment_name",
    "images", "position",
}

POINTS_CATEGORY_MAP = [
    ("activityPoints", "activity", PointEntry.SOURCE_MANUAL, "نقاط نشاط مهاجرة"),
    ("taskPoints", "task", PointEntry.SOURCE_TASK_FULL, "نقاط مهام مهاجرة"),
    ("attendancePoints", "attendance", PointEntry.SOURCE_ATTENDANCE, "نقاط حضور مهاجرة"),
]

VALID_TASK_STATUSES = {
    Task.STATUS_NEW,
    Task.STATUS_ACCEPTED,
    Task.STATUS_IN_PROGRESS,
    Task.STATUS_WAITING_FOR_REVIEW,
    Task.STATUS_COMPLETED,
    Task.STATUS_REJECTED,
}

VALID_ASSIGNMENT_STATUSES = {
    TaskAssignment.STATUS_NOT_STARTED,
    TaskAssignment.STATUS_IN_PROGRESS,
    TaskAssignment.STATUS_SUBMITTED,
    TaskAssignment.STATUS_COMPLETED,
    TaskAssignment.STATUS_REJECTED,
}


def _parse_user_id(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_int(val, default: int = 0) -> int:
    """عددٌ صحيحٌ من قيمةٍ لم نكتبها نحن — `"12.5"` وقاموسٌ وnull كلُّها واردة."""
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _parse_date(val) -> datetime.date | None:
    if not val:
        return None
    if isinstance(val, datetime.date):
        return val
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        if "T" in val or " " in val:
            val = val.replace("Z", "").split("T")[0].split(" ")[0]
        try:
            return datetime.date.fromisoformat(val[:10])
        except Exception:
            return None
    return None


def _parse_datetime(val) -> datetime.datetime | None:
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val if timezone.is_aware(val) else timezone.make_aware(val)
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        try:
            dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if timezone.is_aware(dt) else timezone.make_aware(dt)
        except Exception:
            pass
        try:
            d = datetime.date.fromisoformat(val[:10])
            return timezone.make_aware(datetime.datetime.combine(d, datetime.time.min))
        except Exception:
            return None
    return None


def _parse_decimal(val) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


#: كلُّ مُطبِّعٍ يُعيد `(القيمة، أحُمِلت على الافتراضيّ؟)`.
#: **هجرةٌ تُعيد تفسير قيمةٍ بصمت أسوأُ من هجرةٍ تسقط**: القيمةُ الأصليّةُ تختفي
#: (الحقولُ المعروفةُ لا تدخل `extra`)، فيقرأ المالكُ لاحقاً «جديدة» ولا يعرف
#: أنّها كانت شيئاً آخر. فالأصلُ يُحفظ في `extra` والعددُ يظهر في التقرير.
def _normalize_task_priority(val) -> tuple[str, bool]:
    if not val:
        return Task.PRIORITY_MEDIUM, False
    try:
        return normalize_priority(val), False
    except Exception:
        upper = str(val).strip().upper()
        if upper in ("LOW", "MEDIUM", "HIGH", "URGENT"):
            return upper, False
        return Task.PRIORITY_MEDIUM, True


def _normalize_task_status(val) -> tuple[str, bool]:
    if not val:
        return Task.STATUS_NEW, False
    upper = str(val).strip().upper()
    if upper in VALID_TASK_STATUSES:
        return upper, False
    return Task.STATUS_NEW, True


def _normalize_submission_decision(val) -> tuple[str, bool]:
    if not val:
        return TaskSubmission.DECISION_PENDING, False
    lower = str(val).strip().lower()
    if lower == "approved":
        # الدرجةُ الواحدةُ الحيّة تصير «قبولاً كاملاً»: المديرُ وافق ولم يكن
        # أمامه درجتان، وإنزالُه إلى «جزئيّ» يحرمه نقاطاً لم يخسرها.
        return TaskSubmission.DECISION_APPROVED_FULL, False
    if lower in (
        TaskSubmission.DECISION_PENDING,
        TaskSubmission.DECISION_APPROVED_FULL,
        TaskSubmission.DECISION_APPROVED_PARTIAL,
        TaskSubmission.DECISION_REJECTED,
    ):
        return lower, False
    return TaskSubmission.DECISION_PENDING, True


def _normalize_assignment_status(val) -> tuple[str, bool]:
    if not val:
        return TaskAssignment.STATUS_NOT_STARTED, False
    lower = str(val).strip().lower()
    if lower in VALID_ASSIGNMENT_STATUSES:
        return lower, False
    return TaskAssignment.STATUS_NOT_STARTED, True


def _resolve_tenant_id(doc, data) -> tuple[int | None, str | None]:
    """يحل شركة الوثيقة وفق قاعدة bridge/migrations/0005:

    1. doc.tenant_id إن كان مضبوطاً.
    2. وإلا يستخرج معرّف المستخدم من المسار أو الحمولة.
    3. ثم يحل عضويته: عضوية واحدة فقط = شركته.
    4. عدا ذلك: لا نسب ويبقى السبب (no_tenant_on_doc / user_not_found / multiple_memberships).
    """
    if doc.tenant_id is not None:
        return doc.tenant_id, None

    path = doc.path or ""
    owner_raw = None
    if path.startswith("pointsHistory/"):
        parts = path.split("/")
        owner_raw = parts[1] if len(parts) > 1 else None
    elif path.startswith("users/"):
        parts = path.split("/")
        owner_raw = parts[1] if len(parts) > 1 else None
    elif path.startswith("tasks/"):
        # المالكُ من `createdBy`/`userId` وحدهما. الاستنادُ إلى `assignedTo`
        # تخمينٌ: المُسنَدُ إليه ليس مالكَ الوثيقة، وموظفٌ يعمل لشركتين يقلب
        # النسبَ كلَّه. وما لا يُحسم يُترك — لا يُقارَب.
        owner_raw = data.get("createdBy") or data.get("userId")

    if owner_raw is None:
        return None, "no_tenant_on_doc"

    owner_id = _parse_user_id(owner_raw)
    if owner_id is None:
        return None, "user_not_found"

    memberships = list(
        UserCompanyMembership.objects.filter(user_id=owner_id).values_list(
            "tenant_id", "created_at"
        )
    )
    if not memberships:
        return None, "user_not_found"
    if len(memberships) > 1:
        return None, "multiple_memberships"

    tenant_id, joined_at = memberships[0]

    # **عضويّةٌ واحدةٌ اليومَ ليست دليلاً على الملكيّةِ وقتَ كتابة الوثيقة.** من
    # ترك الشركةَ «أ» وصار عضواً في «ب» وحدها يجرّ مهامَّ «أ» وتسليماتِها إلى
    # دفاتر «ب» بصمت، ويُعدّ ذلك نجاحاً في التقرير. فإن سبقت الوثيقةُ العضويّةَ
    # فالنسبُ غيرُ محسوم — وما لا يُحسم يُترك.
    written_at = _parse_datetime(
        data.get("createdAt") or data.get("created_at")
    ) or doc.created_at
    if joined_at and written_at and written_at < joined_at:
        return None, "membership_postdates_doc"

    return tenant_id, None


class Command(BaseCommand):
    help = "أمر هجرة بيانات متابعة الموظفين من مرآة bridge إلى جداول employee_ops."

    #: عدّاداتُ آخرِ تشغيل — يقرؤها المستدعي بعد `call_command(Command(), ...)`.
    stats: dict | None = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="حساب وطباعة التقرير دون كتابة أي صف في قاعدة البيانات.",
        )
        parser.add_argument(
            "--tenant",
            type=int,
            default=None,
            help="معرف الشركة لتشغيل الهجرة لها وحدها (اختياري).",
        )

    def handle(self, *args, **opts):
        dry_run = opts.get("dry_run", False)
        tenant_filter = opts.get("tenant")

        stats = {
            "tasks_migrated": 0,
            "tasks_already_migrated": 0,
            "assignments_migrated": 0,
            "assignments_already_migrated": 0,
            "submissions_migrated": 0,
            "submissions_already_migrated": 0,
            "submission_items_migrated": 0,
            "submission_attachments_migrated": 0,
            "points_migrated": 0,
            "points_already_migrated": 0,
            "notes_migrated": 0,
            "notes_already_migrated": 0,
            # الأسبابُ منفصلةٌ لأنّ التقريرَ هو ما يقرّر عليه المالك: سببٌ
            # يُحشر في خانةِ سببٍ آخر يجعل الرقمَ كذبةً مرتّبة.
            "unresolved": {
                "no_tenant_on_doc": 0,
                "user_not_found": 0,
                "multiple_memberships": 0,
                "employee_not_found": 0,
                "bad_date": 0,
                "membership_postdates_doc": 0,
            },
            # قيمٌ لم نفهمها فحُمِلت على الافتراضيّ — والأصلُ محفوظٌ في `extra`.
            "coerced": {
                "task_status": 0,
                "task_priority": 0,
                "assignment_status": 0,
                "submission_decision": 0,
            },
        }

        with transaction.atomic():
            self._execute_migration(dry_run, tenant_filter, stats)
            if dry_run:
                transaction.set_rollback(True)

        stats["migrated"] = {
            "tasks": stats["tasks_migrated"],
            "assignments": stats["assignments_migrated"],
            "submissions": stats["submissions_migrated"],
            "submission_items": stats["submission_items_migrated"],
            "submission_attachments": stats["submission_attachments_migrated"],
            "points": stats["points_migrated"],
            "notes": stats["notes_migrated"],
        }
        stats["skipped"] = {
            "tasks": stats["tasks_already_migrated"],
            "assignments": stats["assignments_already_migrated"],
            "submissions": stats["submissions_already_migrated"],
            "points": stats["points_already_migrated"],
            "notes": stats["notes_already_migrated"],
        }
        stats["unresolved_reasons"] = stats["unresolved"]
        stats["unresolved_count"] = sum(stats["unresolved"].values())

        # التقريرُ يُطبع، والعدّاداتُ تُترك على المثيل. وكان هنا صنفٌ يرث `str`
        # ويتظاهر بأنّه `dict` ليُرضي `BaseCommand.execute` — يعمل، لكنّه فخٌّ
        # لمن يقرأ بعدنا. و`call_command` يقبل **مثيلَ** أمرٍ، فالاختبارُ يقرأ
        # `cmd.stats` بعد التشغيل بلا حيلة.
        self.stats = stats
        self.stdout.write(
            self._format_report(stats, dry_run=dry_run, tenant_filter=tenant_filter)
        )
        return None

    def _execute_migration(self, dry_run: bool, tenant_filter: int | None, stats: dict):
        FirestoreMirrorDoc = apps.get_model("bridge", "FirestoreMirrorDoc")
        qs = FirestoreMirrorDoc.objects.filter(
            Q(path__startswith="tasks/")
            | Q(path__startswith="pointsHistory/")
            | Q(path__startswith="users/")
        ).order_by("path")

        if tenant_filter is not None:
            qs = qs.filter(Q(tenant_id=tenant_filter) | Q(tenant__isnull=True))

        for doc in qs.iterator(chunk_size=500):
            path = doc.path or ""
            if path.startswith("tasks/"):
                self._migrate_task(doc, dry_run, tenant_filter, stats)
            elif path.startswith("pointsHistory/"):
                self._migrate_daily_points(doc, dry_run, tenant_filter, stats)
            elif path.startswith("users/"):
                self._migrate_user_note(doc, dry_run, tenant_filter, stats)

    def _migrate_user_note(self, doc, dry_run: bool, tenant_filter: int | None, stats: dict):
        data = doc.data or {}
        tenant_id, unresolved = _resolve_tenant_id(doc, data)
        if unresolved:
            stats["unresolved"][unresolved] += 1
            return
        if tenant_filter is not None and tenant_id != tenant_filter:
            return

        parts = doc.path.split("/")
        user_raw = parts[1] if len(parts) > 1 else data.get("id") or data.get("userId")
        user_id = _parse_user_id(user_raw)
        if user_id is None:
            stats["unresolved"]["user_not_found"] += 1
            return

        employee = Employee.objects.filter(tenant_id=tenant_id, user_id=user_id).first()
        if employee is None:
            stats["unresolved"]["employee_not_found"] += 1
            return

        note_text = data.get("notes")
        if not note_text or not str(note_text).strip():
            return

        source_path = doc.path
        if EmployeeNote.objects.filter(tenant_id=tenant_id, source_path=source_path).exists():
            stats["notes_already_migrated"] += 1
            return

        if not dry_run:
            EmployeeNote.objects.create(
                tenant_id=tenant_id,
                employee=employee,
                body=str(note_text),
                author=None,
                source_path=source_path,
            )
        stats["notes_migrated"] += 1

    def _migrate_daily_points(self, doc, dry_run: bool, tenant_filter: int | None, stats: dict):
        data = doc.data or {}
        tenant_id, unresolved = _resolve_tenant_id(doc, data)
        if unresolved:
            stats["unresolved"][unresolved] += 1
            return
        if tenant_filter is not None and tenant_id != tenant_filter:
            return

        parts = doc.path.split("/")
        user_raw = parts[1] if len(parts) > 1 else data.get("userId")
        user_id = _parse_user_id(user_raw)
        if user_id is None:
            stats["unresolved"]["user_not_found"] += 1
            return

        employee = Employee.objects.filter(tenant_id=tenant_id, user_id=user_id).first()
        if employee is None:
            stats["unresolved"]["employee_not_found"] += 1
            return

        date_raw = parts[3] if len(parts) > 3 else data.get("date")
        awarded_on = _parse_date(date_raw)
        if not awarded_on:
            # تاريخٌ لا يُقرأ ليس «وثيقةً بلا شركة» — والخلطُ يخفي عطباً حقيقيّاً
            # في بيانات المصدر خلف رقمٍ يبدو مألوفاً.
            stats["unresolved"]["bad_date"] += 1
            return

        for field_name, suffix, source_choice, default_reason in POINTS_CATEGORY_MAP:
            points_val = data.get(field_name)
            if points_val is None:
                continue
            try:
                points_int = int(points_val)
            except (TypeError, ValueError):
                continue

            if points_int == 0:
                continue

            category_source_path = f"{doc.path}#{suffix}"
            if PointEntry.objects.filter(tenant_id=tenant_id, source_path=category_source_path).exists():
                stats["points_already_migrated"] += 1
                continue

            if not dry_run:
                PointEntry.objects.create(
                    tenant_id=tenant_id,
                    employee=employee,
                    points=points_int,
                    source=source_choice,
                    awarded_on=awarded_on,
                    submission=None,
                    reverses=None,
                    reason=default_reason,
                    created_by=None,
                    source_path=category_source_path,
                )
            stats["points_migrated"] += 1

    def _migrate_task(self, doc, dry_run: bool, tenant_filter: int | None, stats: dict):
        data = doc.data or {}
        tenant_id, unresolved = _resolve_tenant_id(doc, data)
        if unresolved:
            stats["unresolved"][unresolved] += 1
            return
        if tenant_filter is not None and tenant_id != tenant_filter:
            return

        source_path = doc.path
        task = Task.objects.filter(tenant_id=tenant_id, source_path=source_path).first()

        if task:
            stats["tasks_already_migrated"] += 1
        else:
            title = (str(data.get("title") or "")).strip() or f"مهمة {doc.path.split('/')[-1]}"
            description = str(data.get("description") or "")
            priority, priority_coerced = _normalize_task_priority(data.get("priority"))
            status, status_coerced = _normalize_task_status(data.get("status"))
            if priority_coerced:
                stats["coerced"]["task_priority"] += 1
            if status_coerced:
                stats["coerced"]["task_status"] += 1
            due_date = _parse_date(data.get("dueDate") or data.get("due_date"))
            category = str(data.get("category") or "")
            tags = data.get("tags") if isinstance(data.get("tags"), list) else []
            target_price = _parse_decimal(data.get("targetPrice") or data.get("target_price"))
            allowed_sites = data.get("allowedSites") or data.get("allowed_sites") or []
            if not isinstance(allowed_sites, list):
                allowed_sites = []
            completed_at = _parse_datetime(data.get("completedAt") or data.get("completed_at"))

            creator_user = None
            creator_id = _parse_user_id(data.get("createdBy") or data.get("created_by"))
            if creator_id:
                creator_user = User.objects.filter(pk=creator_id).first()

            task_extra = {k: v for k, v in data.items() if k not in KNOWN_TASK_KEYS}
            # الأصلُ يُحفظ حين لم نفهمه — «لا يضيع شيء» تشمل ما أسأنا قراءته.
            if status_coerced:
                task_extra["_source_status"] = data.get("status")
            if priority_coerced:
                task_extra["_source_priority"] = data.get("priority")

            if not dry_run:
                task = Task.objects.create(
                    tenant_id=tenant_id,
                    title=title[:255],
                    description=description,
                    priority=priority,
                    status=status,
                    due_date=due_date,
                    category=category[:100],
                    tags=tags,
                    target_price=target_price,
                    allowed_sites=allowed_sites,
                    created_by=creator_user,
                    completed_at=completed_at,
                    extra=task_extra,
                    source_path=source_path,
                )
                created_at = _parse_datetime(data.get("createdAt") or data.get("created_at"))
                updated_at = _parse_datetime(data.get("updatedAt") or data.get("updated_at"))
                update_fields = []
                if created_at:
                    task.created_at = created_at
                    update_fields.append("created_at")
                if updated_at:
                    task.updated_at = updated_at
                    update_fields.append("updated_at")
                if update_fields:
                    Task.objects.filter(pk=task.pk).update(
                        **{f: getattr(task, f) for f in update_fields}
                    )

            stats["tasks_migrated"] += 1

        # إسنادات المهمة
        assigned_to_raw = data.get("assignedTo") or []
        user_statuses = data.get("userStatuses") or {}
        all_assignee_raw = set()
        if isinstance(assigned_to_raw, list):
            all_assignee_raw.update(assigned_to_raw)
        if isinstance(user_statuses, dict):
            all_assignee_raw.update(user_statuses.keys())

        for raw_uid in all_assignee_raw:
            uid = _parse_user_id(raw_uid)
            if uid is None:
                stats["unresolved"]["user_not_found"] += 1
                continue
            employee = Employee.objects.filter(tenant_id=tenant_id, user_id=uid).first()
            if employee is None:
                stats["unresolved"]["employee_not_found"] += 1
                continue

            u_status = user_statuses.get(str(raw_uid)) or user_statuses.get(raw_uid) or {}
            if not isinstance(u_status, dict):
                u_status = {}

            # الشركةُ في الفلتر صراحةً — دفاعٌ في العمق: `TaskAssignment` تحمل
            # `tenant` بذاتها، وسطرٌ يُنسخ إلى موضعٍ بلا مهمّةٍ مقيَّدة يتسرّب.
            if task and TaskAssignment.objects.filter(
                tenant_id=tenant_id, task=task, employee=employee
            ).exists():
                stats["assignments_already_migrated"] += 1
                continue

            a_status, a_coerced = _normalize_assignment_status(u_status.get("status"))
            if a_coerced:
                stats["coerced"]["assignment_status"] += 1
            started_at = _parse_datetime(u_status.get("startedAt") or u_status.get("started_at"))
            completed_at_a = _parse_datetime(u_status.get("completedAt") or u_status.get("completed_at"))
            work_started_at = _parse_datetime(u_status.get("workStartedAt") or u_status.get("work_started_at"))
            # `int()` عارياً كان يرمي على `"12.5"` أو على قاموس — وكلُّ الهجرة
            # في معاملةٍ واحدة، فصفٌّ واحدٌ فاسدٌ يُلغي الباقيَ كلَّه. وهجرةٌ
            # تسقط على قيمةٍ في بياناتٍ لم نكتبها نحن ليست «إعادةَ تشغيلٍ آمنة».
            total_work = _parse_int(
                u_status.get("totalWorkTime") or u_status.get("total_work_seconds")
            )
            extra_a = {k: v for k, v in u_status.items() if k not in KNOWN_ASSIGNMENT_KEYS}
            if a_coerced:
                extra_a["_source_status"] = u_status.get("status")

            if not dry_run and task and task.pk:
                TaskAssignment.objects.create(
                    tenant_id=tenant_id,
                    task=task,
                    employee=employee,
                    status=a_status,
                    started_at=started_at,
                    completed_at=completed_at_a,
                    work_started_at=work_started_at,
                    total_work_seconds=total_work,
                    extra=extra_a,
                )
            stats["assignments_migrated"] += 1

        # تسليمات المهمة
        submissions_raw = data.get("submissions") or []
        if isinstance(submissions_raw, list):
            for idx, sub in enumerate(submissions_raw):
                if not isinstance(sub, dict):
                    continue
                sub_uid = _parse_user_id(sub.get("userId") or sub.get("user_id"))
                if sub_uid is None:
                    stats["unresolved"]["user_not_found"] += 1
                    continue
                sub_employee = Employee.objects.filter(tenant_id=tenant_id, user_id=sub_uid).first()
                if sub_employee is None:
                    stats["unresolved"]["employee_not_found"] += 1
                    continue

                sub_id = sub.get("id") or str(idx)
                sub_source_path = f"{doc.path}#submission-{sub_id}"

                if TaskSubmission.objects.filter(tenant_id=tenant_id, source_path=sub_source_path).exists():
                    stats["submissions_already_migrated"] += 1
                    continue

                decision, d_coerced = _normalize_submission_decision(
                    sub.get("status") or sub.get("decision")
                )
                if d_coerced:
                    stats["coerced"]["submission_decision"] += 1
                body = sub.get("body") or ""
                reviewer_user = None
                rev_uid = _parse_user_id(sub.get("reviewedBy") or sub.get("reviewed_by"))
                if rev_uid:
                    reviewer_user = User.objects.filter(pk=rev_uid).first()
                reviewed_at = _parse_datetime(sub.get("reviewedAt") or sub.get("reviewed_at"))
                reviewer_notes = sub.get("reviewerNotes") or sub.get("reviewer_notes") or ""
                extra_sub = {k: v for k, v in sub.items() if k not in KNOWN_SUBMISSION_KEYS}
                if d_coerced:
                    extra_sub["_source_status"] = sub.get("status") or sub.get("decision")

                new_sub = None
                if not dry_run and task and task.pk:
                    new_sub = TaskSubmission.objects.create(
                        tenant_id=tenant_id,
                        task=task,
                        employee=sub_employee,
                        body=body,
                        decision=decision,
                        reviewer=reviewer_user,
                        reviewed_at=reviewed_at,
                        reviewer_notes=reviewer_notes,
                        extra=extra_sub,
                        source_path=sub_source_path,
                    )
                    created_at_s = _parse_datetime(sub.get("createdAt") or sub.get("created_at"))
                    updated_at_s = _parse_datetime(sub.get("updatedAt") or sub.get("updated_at"))
                    update_fields_s = []
                    if created_at_s:
                        new_sub.created_at = created_at_s
                        update_fields_s.append("created_at")
                    if updated_at_s:
                        new_sub.updated_at = updated_at_s
                        update_fields_s.append("updated_at")
                    if update_fields_s:
                        TaskSubmission.objects.filter(pk=new_sub.pk).update(
                            **{f: getattr(new_sub, f) for f in update_fields_s}
                        )

                stats["submissions_migrated"] += 1

                # بنود التسليم
                items_raw = sub.get("items") or []
                if isinstance(items_raw, list):
                    for item_idx, item in enumerate(items_raw):
                        if not isinstance(item, dict):
                            continue
                        p_link = item.get("productLink") or item.get("product_link") or ""
                        p_price = _parse_decimal(item.get("productPrice") or item.get("product_price"))
                        notes = item.get("notes") or ""
                        att_url = item.get("attachmentUrl") or item.get("attachment_url") or ""
                        att_name = item.get("attachmentName") or item.get("attachment_name") or ""
                        images = item.get("images") if isinstance(item.get("images"), list) else []
                        pos = _parse_int(item.get("position"), item_idx)
                        extra_item = {k: v for k, v in item.items() if k not in KNOWN_ITEM_KEYS}

                        if not dry_run and new_sub and new_sub.pk:
                            TaskSubmissionItem.objects.create(
                                tenant_id=tenant_id,
                                submission=new_sub,
                                product_link=p_link,
                                product_price=p_price,
                                notes=notes,
                                attachment_url=att_url,
                                attachment_name=att_name,
                                images=images,
                                position=pos,
                                extra=extra_item,
                            )
                        stats["submission_items_migrated"] += 1

                # مرفقات التسليم
                attachments_raw = sub.get("attachments") or []
                if isinstance(attachments_raw, list):
                    for att_idx, att in enumerate(attachments_raw):
                        if not isinstance(att, dict):
                            continue
                        att_u = att.get("url") or ""
                        att_n = att.get("name") or ""
                        att_p = _parse_int(att.get("position"), att_idx)
                        if not dry_run and new_sub and new_sub.pk and att_u:
                            TaskSubmissionAttachment.objects.create(
                                tenant_id=tenant_id,
                                submission=new_sub,
                                url=att_u,
                                name=att_n,
                                position=att_p,
                            )
                        if att_u:
                            stats["submission_attachments_migrated"] += 1

    def _format_report(self, stats: dict, *, dry_run: bool, tenant_filter: int | None) -> str:
        lines = [
            "\nتقرير هجرة بيانات متابعة الموظفين من مرآة bridge:",
        ]
        if dry_run:
            lines.append("  [وضع المعاينة --dry-run: لم تُكتب أي بيانات في قاعدة البيانات]")
        if tenant_filter:
            lines.append(f"  نطاق الشركة: #{tenant_filter}")

        lines.extend([
            "\n1. المهام والإسنادات والتسليمات:",
            f"   - المهام: {stats['tasks_migrated']} هاجرت، {stats['tasks_already_migrated']} تم تخطيها (مهاجرة سلفاً)",
            f"   - الإسنادات: {stats['assignments_migrated']} هاجرت، {stats['assignments_already_migrated']} تم تخطيها",
            f"   - التسليمات: {stats['submissions_migrated']} هاجرت، {stats['submissions_already_migrated']} تم تخطيها",
            f"   - بنود التسليم: {stats['submission_items_migrated']} هاجرت",
            f"   - مرفقات التسليم: {stats['submission_attachments_migrated']} هاجرت",
            "\n2. نقاط الموظفين (PointEntry):",
            f"   - قيود النقاط: {stats['points_migrated']} هاجرت، {stats['points_already_migrated']} تم تخطيها (مهاجرة سلفاً)",
            "\n3. ملاحظات الموظفين (EmployeeNote):",
            f"   - الملاحظات: {stats['notes_migrated']} هاجرت، {stats['notes_already_migrated']} تم تخطيها (مهاجرة سلفاً)",
            "\n4. ما لم يُنسب (غير محسوم):",
        ])
        for reason, count in stats["unresolved"].items():
            lines.append(f"   - {reason}: {count}")

        lines.append("\n5. قيمٌ لم تُفهم فحُمِلت على الافتراضيّ (الأصل محفوظ في extra):")
        for field, count in stats["coerced"].items():
            lines.append(f"   - {field}: {count}")

        total_migrated = (
            stats["tasks_migrated"]
            + stats["assignments_migrated"]
            + stats["submissions_migrated"]
            + stats["submission_items_migrated"]
            + stats["submission_attachments_migrated"]
            + stats["points_migrated"]
            + stats["notes_migrated"]
        )
        lines.append(f"\nإجمالي السجلات المعالجة للهجرة بنجاح: {total_migrated}.")
        return "\n".join(lines)
