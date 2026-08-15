"""مكتب المحاسبة — خدمات سجلّ الممارسة (زبائن يدويون، برامج، مواعيد، مستندات).

**الجدار** (§الوحدة): كل صفّ هنا مملوك للمحاسب لا لشركة، فلا `tenant` في أي نموذج،
ولا يصل من هذه الوحدة طريق إلى `post_journal` ولا إلى `record_stock_movement`.
قراءة دفاتر زبون حقيقي تبقى حصراً على مسارات الارتباط النشط.

**العزل** كما في `services.py`: كل استعلام يبدأ بـ`accountant=`، وصفّ محاسبٍ آخر
يعود «غير موجود» (404) لا «ممنوع» (403) — كي لا يكشف الردُّ وجودَ الصف أصلاً.
"""
import logging
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    PracticeClient,
    PracticeDocument,
    PracticeProgram,
    PracticeSettings,
    PracticeTask,
)
from accountant_portal.services import (
    EngagementConflict,
    practice_overview,
    sanitize_log_value,
)


logger = logging.getLogger(__name__)

# «قريب» في لوحة المواعيد — أسبوع، وهو أفق المتابعة الذي يعمل به المكتب.
DUE_SOON_DAYS = 7

CLIENT_TEXT_FIELDS = (
    "contact_first",
    "contact_last",
    "phone",
    "mobile",
    "address",
    "sector",
    "tax_number",
    "notes",
)


def _profile(accountant):
    try:
        return accountant.accountant_profile
    except AccountantProfile.DoesNotExist as exc:
        raise EngagementConflict("accountant_profile_required", "يلزم ملف محاسب مهني.", 403) from exc


def _log(action, accountant, **details):
    """أثر تشغيلي فقط: لا `tenant` هنا ⇒ لا `ActivityLog` ولا تدقيق مالي."""
    logger.info(
        "accountant_practice %s user=%s %s",
        action,
        accountant.pk,
        " ".join(f"{key}={sanitize_log_value(value, 120)}" for key, value in details.items()),
    )


def _text(data, key, limit):
    return str(data.get(key) or "").strip()[:limit]


# ── إعدادات المكتب ───────────────────────────────────────────────────────────


def get_practice_settings(accountant):
    """إعدادات المكتب — تتجسّد عند أول قراءة، وغيابها لا يكسر شيئاً."""
    config, _ = PracticeSettings.objects.get_or_create(profile=_profile(accountant))
    return config


def practice_settings_payload(config):
    return {
        "default_program_due_days": config.default_program_due_days,
        "service_types": list(config.service_types or []),
    }


@transaction.atomic
def update_practice_settings(*, accountant, data):
    config = get_practice_settings(accountant)
    if "default_program_due_days" in data:
        try:
            days = int(data["default_program_due_days"])
        except (TypeError, ValueError) as exc:
            raise EngagementConflict("invalid_settings", "مهلة الاستحقاق يجب أن تكون رقماً.", 400) from exc
        if not 1 <= days <= 365:
            raise EngagementConflict("invalid_settings", "مهلة الاستحقاق بين يوم و365 يوماً.", 422)
        config.default_program_due_days = days
    if "service_types" in data:
        value = data["service_types"]
        if not isinstance(value, list):
            raise EngagementConflict("invalid_settings", "أنواع الخدمات يجب أن تكون قائمة.", 400)
        cleaned = [str(item).strip()[:120] for item in value]
        cleaned = list(dict.fromkeys(item for item in cleaned if item))
        if not cleaned:
            raise EngagementConflict("invalid_settings", "أبقِ نوع خدمة واحداً على الأقل.", 422)
        config.service_types = cleaned
    config.save()
    _log("settings_updated", accountant)
    return config


# ── الزبائن ──────────────────────────────────────────────────────────────────


def client_payload(client):
    return {
        "id": client.pk,
        "trade_name": client.trade_name,
        "contact_first": client.contact_first,
        "contact_last": client.contact_last,
        "phone": client.phone,
        "mobile": client.mobile,
        "email": client.email,
        "address": client.address,
        "sector": client.sector,
        "tax_number": client.tax_number,
        "status": client.status,
        "notes": client.notes,
        "engagement_id": client.engagement_id,
        # الشركة المرتبطة — وجودها يعني أن لهذا الزبون دفاتر على المنصة تُقرأ من
        # مسارات الارتباط، وهو ما تحتاجه الواجهة للتمييز بين نوعَي الزبائن.
        "tenant_id": client.engagement.tenant_id if client.engagement_id else None,
        "created_at": client.created_at,
    }


def get_practice_client(*, accountant, client_id):
    """زبون هذا المكتب أو «غير موجود» — صفّ مكتبٍ آخر لا يُفرَّق عن المعدوم."""
    client = (
        PracticeClient.objects.filter(accountant=accountant, pk=client_id)
        .select_related("engagement")
        .first()
    )
    if client is None:
        raise EngagementConflict("client_not_found", "الزبون غير موجود.", 404)
    return client


def list_practice_clients(*, accountant, status=None, search=None):
    queryset = PracticeClient.objects.filter(accountant=accountant).select_related("engagement")
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(trade_name__icontains=str(search)[:200])
    return list(queryset.order_by("trade_name", "id"))


def _resolve_engagement(*, accountant, engagement_id, exclude_client=None):
    """ربط الزبون بشركة على المنصة — وارتباط مكتبٍ آخر «غير موجود» (T2)."""
    if engagement_id in (None, ""):
        return None
    engagement = AccountantEngagement.objects.filter(
        pk=engagement_id, accountant=accountant,
    ).first()
    if engagement is None:
        raise EngagementConflict("engagement_not_found", "الارتباط غير موجود.", 404)
    duplicate = PracticeClient.objects.filter(accountant=accountant, engagement=engagement)
    if exclude_client is not None:
        duplicate = duplicate.exclude(pk=exclude_client.pk)
    if duplicate.exists():
        raise EngagementConflict("engagement_linked", "هذه الشركة مرتبطة بزبون آخر في مكتبك.")
    return engagement


def _apply_client_fields(client, data):
    if "trade_name" in data:
        trade_name = _text(data, "trade_name", 200)
        if not trade_name:
            raise EngagementConflict("invalid_client", "الاسم التجاري مطلوب.", 400)
        client.trade_name = trade_name
    for field in CLIENT_TEXT_FIELDS:
        if field in data:
            limit = PracticeClient._meta.get_field(field).max_length or 2000
            setattr(client, field, _text(data, field, limit))
    if "email" in data:
        email = _text(data, "email", 254)
        if email:
            try:
                validate_email(email)
            except DjangoValidationError as exc:
                raise EngagementConflict("invalid_email", "أدخل بريداً إلكترونياً صالحاً.", 400) from exc
        client.email = email


@transaction.atomic
def create_practice_client(*, accountant, data):
    _profile(accountant)
    if not _text(data, "trade_name", 200):
        raise EngagementConflict("invalid_client", "الاسم التجاري مطلوب.", 400)
    client = PracticeClient(accountant=accountant)
    _apply_client_fields(client, data)
    client.engagement = _resolve_engagement(
        accountant=accountant, engagement_id=data.get("engagement_id"),
    )
    try:
        client.save()
    except IntegrityError as exc:
        raise EngagementConflict("duplicate_client", "يوجد زبون بهذا الاسم التجاري في مكتبك.") from exc
    _log("client_created", accountant, client=client.pk, name=client.trade_name)
    return client


@transaction.atomic
def update_practice_client(*, accountant, client_id, data):
    client = get_practice_client(accountant=accountant, client_id=client_id)
    _apply_client_fields(client, data)
    if "engagement_id" in data:
        client.engagement = _resolve_engagement(
            accountant=accountant,
            engagement_id=data.get("engagement_id"),
            exclude_client=client,
        )
    try:
        client.save()
    except IntegrityError as exc:
        raise EngagementConflict("duplicate_client", "يوجد زبون بهذا الاسم التجاري في مكتبك.") from exc
    _log("client_updated", accountant, client=client.pk)
    return client


@transaction.atomic
def archive_practice_client(*, accountant, client_id):
    """الحذف أرشفة — ملف الزبون وبرامجه ومستنداته تاريخٌ مهني لا يُمحى."""
    client = get_practice_client(accountant=accountant, client_id=client_id)
    if client.status != "archived":
        client.status = "archived"
        client.save(update_fields=["status", "updated_at"])
        _log("client_archived", accountant, client=client.pk)
    return client


@transaction.atomic
def restore_practice_client(*, accountant, client_id):
    client = get_practice_client(accountant=accountant, client_id=client_id)
    if client.status != "active":
        client.status = "active"
        client.save(update_fields=["status", "updated_at"])
        _log("client_restored", accountant, client=client.pk)
    return client


# ── البرامج ──────────────────────────────────────────────────────────────────


def _is_overdue(due_date, status, today):
    return bool(due_date) and status != "done" and due_date < today


def program_payload(program, today=None):
    today = today or timezone.localdate()
    return {
        "id": program.pk,
        "client_id": program.client_id,
        "client_name": program.client.trade_name,
        "service_type": program.service_type,
        "frequency": program.frequency,
        "team_note": program.team_note,
        "due_date": program.due_date,
        "status": program.status,
        "notes": program.notes,
        # التأخر مشتقّ لا مخزَّن — حالة اليوم لا حالة آخر حفظ.
        "is_overdue": _is_overdue(program.due_date, program.status, today),
    }


def get_practice_program(*, accountant, program_id):
    program = (
        PracticeProgram.objects.filter(accountant=accountant, pk=program_id)
        .select_related("client")
        .first()
    )
    if program is None:
        raise EngagementConflict("program_not_found", "البرنامج غير موجود.", 404)
    return program


def list_practice_programs(*, accountant, client_id=None, status=None):
    queryset = PracticeProgram.objects.filter(accountant=accountant).select_related("client")
    if client_id:
        queryset = queryset.filter(client_id=client_id)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by("due_date", "id"))


def _validate_choice(value, choices, code, detail):
    if value not in dict(choices):
        raise EngagementConflict(code, detail, 422)
    return value


def _service_type(accountant, value):
    """نوع الخدمة من قائمة الإعدادات — كي لا يتشظّى النوع نفسه بأربع كتابات."""
    service_type = str(value or "").strip()[:120]
    if not service_type:
        raise EngagementConflict("invalid_program", "نوع الخدمة مطلوب.", 400)
    allowed = get_practice_settings(accountant).service_types or []
    if service_type not in allowed:
        raise EngagementConflict(
            "unknown_service_type",
            "نوع الخدمة غير معرَّف في إعدادات المكتب.",
            422,
        )
    return service_type


def _parse_due_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    due_date = parse_date(str(value))
    if due_date is None:
        raise EngagementConflict("invalid_due_date", "تاريخ الاستحقاق غير صالح.", 400)
    return due_date


@transaction.atomic
def create_practice_program(*, accountant, data, today=None):
    client = get_practice_client(accountant=accountant, client_id=data.get("client_id"))
    today = today or timezone.localdate()
    due_date = _parse_due_date(data.get("due_date"))
    if due_date is None:
        # غياب التاريخ ليس فراغاً: مهلة المكتب الافتراضية تملؤه فوراً.
        due_date = today + timedelta(days=get_practice_settings(accountant).default_program_due_days)
    program = PracticeProgram.objects.create(
        accountant=accountant,
        client=client,
        service_type=_service_type(accountant, data.get("service_type")),
        frequency=_validate_choice(
            str(data.get("frequency") or "monthly"),
            PracticeProgram.FREQUENCIES,
            "invalid_frequency",
            "دورية البرنامج غير صالحة.",
        ),
        team_note=_text(data, "team_note", 2000),
        due_date=due_date,
        status=_validate_choice(
            str(data.get("status") or "planned"),
            PracticeProgram.STATUSES,
            "invalid_status",
            "حالة البرنامج غير صالحة.",
        ),
        notes=_text(data, "notes", 2000),
    )
    _log("program_created", accountant, program=program.pk, client=client.pk)
    return program


@transaction.atomic
def update_practice_program(*, accountant, program_id, data):
    program = get_practice_program(accountant=accountant, program_id=program_id)
    if "client_id" in data:
        program.client = get_practice_client(accountant=accountant, client_id=data.get("client_id"))
    if "service_type" in data:
        program.service_type = _service_type(accountant, data.get("service_type"))
    if "frequency" in data:
        program.frequency = _validate_choice(
            str(data.get("frequency") or ""),
            PracticeProgram.FREQUENCIES,
            "invalid_frequency",
            "دورية البرنامج غير صالحة.",
        )
    if "status" in data:
        program.status = _validate_choice(
            str(data.get("status") or ""),
            PracticeProgram.STATUSES,
            "invalid_status",
            "حالة البرنامج غير صالحة.",
        )
    if "due_date" in data:
        program.due_date = _parse_due_date(data.get("due_date"))
    for field in ("team_note", "notes"):
        if field in data:
            setattr(program, field, _text(data, field, 2000))
    program.save()
    _log("program_updated", accountant, program=program.pk)
    return program


@transaction.atomic
def delete_practice_program(*, accountant, program_id):
    program = get_practice_program(accountant=accountant, program_id=program_id)
    program.delete()
    _log("program_deleted", accountant, program=program_id)


# ── المواعيد والاستحقاقات ────────────────────────────────────────────────────


def task_payload(task, today=None):
    today = today or timezone.localdate()
    due_date = timezone.localtime(task.due_at).date() if timezone.is_aware(task.due_at) else task.due_at.date()
    return {
        "id": task.pk,
        "client_id": task.client_id,
        "client_name": task.client.trade_name if task.client_id else "",
        "title": task.title,
        "due_at": task.due_at,
        "status": task.status,
        "kind": task.kind,
        "is_overdue": _is_overdue(due_date, task.status, today),
    }


def get_practice_task(*, accountant, task_id):
    task = (
        PracticeTask.objects.filter(accountant=accountant, pk=task_id)
        .select_related("client")
        .first()
    )
    if task is None:
        raise EngagementConflict("task_not_found", "الموعد غير موجود.", 404)
    return task


def list_practice_tasks(*, accountant, client_id=None, status=None):
    queryset = PracticeTask.objects.filter(accountant=accountant).select_related("client")
    if client_id:
        queryset = queryset.filter(client_id=client_id)
    if status:
        queryset = queryset.filter(status=status)
    return list(queryset.order_by("due_at", "id"))


def _parse_due_at(value):
    if value in (None, ""):
        raise EngagementConflict("invalid_due_at", "موعد التنفيذ مطلوب.", 400)
    if isinstance(value, datetime):
        due_at = value
    else:
        due_at = parse_datetime(str(value))
        if due_at is None:
            # تاريخ بلا ساعة موعدٌ صالح — أول اليوم.
            day = value if isinstance(value, date) else parse_date(str(value))
            if day is None:
                raise EngagementConflict("invalid_due_at", "موعد التنفيذ غير صالح.", 400)
            due_at = datetime(day.year, day.month, day.day)
    if timezone.is_naive(due_at):
        due_at = timezone.make_aware(due_at)
    return due_at


@transaction.atomic
def create_practice_task(*, accountant, data):
    _profile(accountant)
    client = None
    if data.get("client_id") not in (None, ""):
        client = get_practice_client(accountant=accountant, client_id=data.get("client_id"))
    title = _text(data, "title", 200)
    if not title:
        raise EngagementConflict("invalid_task", "عنوان الموعد مطلوب.", 400)
    task = PracticeTask.objects.create(
        accountant=accountant,
        client=client,
        title=title,
        due_at=_parse_due_at(data.get("due_at")),
        status=_validate_choice(
            str(data.get("status") or "open"),
            PracticeTask.STATUSES,
            "invalid_status",
            "حالة الموعد غير صالحة.",
        ),
        kind=_validate_choice(
            str(data.get("kind") or "appointment"),
            PracticeTask.KINDS,
            "invalid_kind",
            "نوع الموعد غير صالح.",
        ),
    )
    _log("task_created", accountant, task=task.pk)
    return task


@transaction.atomic
def update_practice_task(*, accountant, task_id, data):
    task = get_practice_task(accountant=accountant, task_id=task_id)
    if "client_id" in data:
        task.client = (
            get_practice_client(accountant=accountant, client_id=data["client_id"])
            if data["client_id"] not in (None, "")
            else None
        )
    if "title" in data:
        title = _text(data, "title", 200)
        if not title:
            raise EngagementConflict("invalid_task", "عنوان الموعد مطلوب.", 400)
        task.title = title
    if "due_at" in data:
        task.due_at = _parse_due_at(data.get("due_at"))
    if "status" in data:
        task.status = _validate_choice(
            str(data.get("status") or ""),
            PracticeTask.STATUSES,
            "invalid_status",
            "حالة الموعد غير صالحة.",
        )
    if "kind" in data:
        task.kind = _validate_choice(
            str(data.get("kind") or ""),
            PracticeTask.KINDS,
            "invalid_kind",
            "نوع الموعد غير صالح.",
        )
    task.save()
    _log("task_updated", accountant, task=task.pk)
    return task


@transaction.atomic
def delete_practice_task(*, accountant, task_id):
    task = get_practice_task(accountant=accountant, task_id=task_id)
    task.delete()
    _log("task_deleted", accountant, task=task_id)


# ── المستندات ────────────────────────────────────────────────────────────────


def document_payload(document):
    return {
        "id": document.pk,
        "client_id": document.client_id,
        "program_id": document.program_id,
        "name": document.name,
        "url": document.url,
        "uploaded_at": document.uploaded_at,
    }


def list_practice_documents(*, accountant, client_id=None, program_id=None):
    queryset = PracticeDocument.objects.filter(accountant=accountant)
    if client_id:
        queryset = queryset.filter(client_id=client_id)
    if program_id:
        queryset = queryset.filter(program_id=program_id)
    return list(queryset.order_by("-uploaded_at", "-id"))


@transaction.atomic
def create_practice_document(*, accountant, data):
    client = get_practice_client(accountant=accountant, client_id=data.get("client_id"))
    program = None
    if data.get("program_id") not in (None, ""):
        program = get_practice_program(accountant=accountant, program_id=data.get("program_id"))
        if program.client_id != client.pk:
            raise EngagementConflict("program_not_found", "البرنامج غير موجود.", 404)
    name = _text(data, "name", 200)
    url = _text(data, "url", 500)
    if not name or not url:
        raise EngagementConflict("invalid_document", "اسم المستند ورابطه مطلوبان.", 400)
    document = PracticeDocument.objects.create(
        accountant=accountant,
        client=client,
        program=program,
        name=name,
        url=url,
    )
    _log("document_added", accountant, document=document.pk, client=client.pk)
    return document


@transaction.atomic
def delete_practice_document(*, accountant, document_id):
    document = PracticeDocument.objects.filter(accountant=accountant, pk=document_id).first()
    if document is None:
        raise EngagementConflict("document_not_found", "المستند غير موجود.", 404)
    document.delete()
    _log("document_deleted", accountant, document=document_id)


# ── أجندة المكتب ─────────────────────────────────────────────────────────────


def practice_deadlines(*, accountant, today=None):
    """كل ما يستحق على المكتب في قائمة واحدة: برامج، مواعيد، ومواعيد تقديم.

    مواعيد التقديم مشتقّة من الشركات المرتبطة (`practice_overview`) لا مخزَّنة،
    فلا صفَّ يتقادم حين يعدّل الزبون إعداد مهلة التقديم عنده.
    """
    _profile(accountant)
    today = today or timezone.localdate()
    items = []

    for program in (
        PracticeProgram.objects.filter(accountant=accountant)
        .exclude(status="done")
        .select_related("client")
        .order_by("due_date", "id")
    ):
        if program.due_date is None:
            continue
        items.append({
            "kind": "program",
            "id": program.pk,
            "title": program.service_type,
            "client_id": program.client_id,
            "client_name": program.client.trade_name,
            "tenant_id": None,
            "due_date": program.due_date,
            "status": program.status,
        })

    for task in (
        PracticeTask.objects.filter(accountant=accountant, status="open")
        .select_related("client")
        .order_by("due_at", "id")
    ):
        due_at = timezone.localtime(task.due_at) if timezone.is_aware(task.due_at) else task.due_at
        items.append({
            "kind": task.kind,
            "id": task.pk,
            "title": task.title,
            "client_id": task.client_id,
            "client_name": task.client.trade_name if task.client_id else "",
            "tenant_id": None,
            "due_date": due_at.date(),
            "status": task.status,
        })

    for row in practice_overview(accountant=accountant, today=today)["clients"]:
        items.append({
            "kind": "filing",
            "id": None,
            "title": "تقديم إقرار ض.ق.م",
            "client_id": None,
            "client_name": row["company_name"],
            "tenant_id": row["tenant_id"],
            "due_date": parse_date(row["filing_due_date"]),
            "status": "planned",
        })

    for item in items:
        days_left = (item["due_date"] - today).days
        item["days_left"] = days_left
        item["is_overdue"] = days_left < 0
    items.sort(key=lambda item: (item["due_date"], item["kind"], item["id"] or 0))

    return {
        "today": today,
        "items": items,
        "totals": {
            "count": len(items),
            "overdue": sum(1 for item in items if item["is_overdue"]),
            "due_soon": sum(1 for item in items if 0 <= item["days_left"] <= DUE_SOON_DAYS),
        },
    }
