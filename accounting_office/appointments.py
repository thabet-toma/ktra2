"""مواعيدُ الزبون وتذكيراتُها (#281) — الحجزُ والتأكيدُ والمولّدان.

**الموعدُ حجزُ موظّفٍ لا حجزُ زبون**: يُسجَّل من ملفّ الزبون ومن التقويم، ويُحمل
بتاريخه **ووقته** (`scheduled_at`)؛ فالفرقُ بين موعدَي العاشرة والثانية في اليوم
نفسه هو ما يجعل «مواعيد اليوم» قائمةً مرتَّبةً بوقتها لا عدّةً.

**ولا محرّكاً موازياً للتذكير** (د3): مولّدا «تذكير موعد» و«موعد رسمي قريب»
يُرجعان بنوداً بالنوع القائم (`services.ReminderCandidate`) فتمرّ في
`_reminder_candidates`/`ready_to_send_payload` نفسِهما — بالموافقة ويوم الراحة
والعطلة والتأجيل والحدّ الأقصى. والفرقُ الوحيدُ أنّ مؤقّتاتِهما تُقاس بـ
`Obligation.due_date` و`ClientAppointment.scheduled_at` لا بفترة أوراق.

**والنافذةُ لا العدّاد** (جولة التصليح الأولى): كلُّ مولّدٍ يفتح نافذةً من اليوم —
للموعد `slot_day - lead`، وللموعد الرسميّ موضعا `(7، 2)` — والبندُ مستحقٌّ إن لم
يكن في السجلّ **صفٌّ مؤقّتٌ يومُه داخل النافذة السارية**، والداخلُ بحدّيه: من بداية
النافذة إلى اليوم المحسوب (فصفٌّ بعد ذلك اليوم لم يكن قد وُجد حينها، و`ready-to-send`
يقبل يوماً صريحاً لعرض يومٍ مضى). والعدُّ وحده كان يُسقط
«شيل» (لا يُعدّ) فتعود التنحيةُ كلَّ يوم، ويُكرِّر الرسالةَ في اليوم نفسه (إزاحةٌ
أضيق بعد أوّل صفّ)، ويستهلك تأكيدُ الموعد نافذةَ تذكيره فيمنع «قبله بيوم».

**وموعدُ التقديم لا يُحسب من جديد**: «آخر موعد فعلي» هو
`extended_to or actual_deadline` — نفسُ `Obligation.due_date` التي يقرؤها التأخيرُ
الأحمرُ ونافذةُ «قريب هالأسبوع»؛ نسخةٌ ثانية هنا كانت ستختلف عنه عند أوّل تمديد.
**وبندٌ واحدٌ لكل (زبون، فترة)**: التزامان في الفترة الواحدة بندان بمفتاحٍ واحد
(تحذيرُ مفاتيحَ مكرَّرة في React، وعدّادٌ مشتركٌ يسقط «قبل ٢»)، فتُجمَّع التزاماتُ
الفترة في بندٍ واحد: أقربُ موعدٍ **لم يمضِ** بين التزاماتها **التي عليها شيء**
يفتح نافذته (فالمدفوعُ لا يُذكَّر بموعده، والماضي متأخّرٌ يخصّه الأحمرُ، ولا بندَ
لفترةٍ لم يبقَ فيها موعدٌ قادمٌ عليه شيء)، وناقصُها اتّحادٌ، ومبلغُها مجموعُ
المستحقّ عليها. **وبندٌ واحدٌ لكل (زبون، يوم)** في تذكير الموعد للسبب نفسه:
موعدان في اليوم نفسه يتشاركان المفتاح، فيُجمعان في بندٍ بوقتَيهما.

**والشرطُ الحاسم**: لا تذكيرَ بموعدٍ رسميٍّ إلّا إذا **على الزبون شيء** —
أوراقٌ ناقصةٌ أو مبلغٌ غيرُ مدفوع. ودالّةُ `client_owes` نقيّةٌ ومفردة، فيُثبت
اختبارُها الحالاتِ الأربع بلا قاعدة بيانات.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting_office import services
from accounting_office.models import (
    APPOINTMENT_KIND_CHOICES,
    APPOINTMENT_KIND_LABELS,
    APPOINTMENT_OPEN_STATUSES,
    APPOINTMENT_STATUS_CANCELLED,
    APPOINTMENT_STATUS_DONE,
    APPOINTMENT_STATUS_LABELS,
    APPOINTMENT_STATUS_SCHEDULED,
    OBLIGATION_BADGE_NEAR,
    OBLIGATION_DIRECTION_REFUND,
    OBLIGATION_STATUS_PENDING,
    REMINDER_APPOINTMENT,
    REMINDER_DEADLINE,
    ClientAppointment,
    Obligation,
)

#: مفتاحُ «تذكير الموعد قبل كم يوم» — إعدادُ مكتبٍ يُخصَّص للزبون (د2).
#: واسمُه من `services` لا حرفياً هنا: المفتاحُ يُقرأ في مسحة المحرّك هناك أيضاً،
#: فنسختان تفترقان عند أوّل إعادة تسمية.
APPOINTMENT_REMINDER_DAYS_KEY = services.APPOINTMENT_REMINDER_DAYS_KEY

#: موضعا تذكير «موعد رسمي قريب»: **سبعةُ أيامٍ ويومان** قبل آخر موعدٍ فعليّ.
#: كلُّ موضعٍ **نافذةٌ** تُفتح مرّةً: تُحسب من اليوم (`due - offset`) لا من عدّ
#: الصفوف، والبندُ يسكت متى وقع في السجلّ صفٌّ داخل نافذته السارية.
DEADLINE_REMINDER_OFFSETS: tuple[int, ...] = (7, 2)

#: أقصى عددِ تذكيراتٍ لموعدٍ واحد — تذكيرٌ واحدٌ يكفي، وما بعده إلحاح.
APPOINTMENT_REMINDER_MAX = 1


# ── هل على الزبون شيء؟ (د6) ─────────────────────────────────────────────────
def client_owes(*, status, missing=(), amount=None, client_paid=False, direction="") -> bool:
    """**هل يستحقّ هذا الالتزامُ تذكيراً بموعده الرسميّ؟** — دالّةٌ نقيّة.

    المنطقُ في ترتيبه: «انقدّم» و«مش لازم» يُسقطان السؤالَ كلَّه؛ وبعدهما أوراقٌ
    ناقصةٌ تكفي وحدها (نقصُ ورقةٍ عملٌ له موعد)، ثم مبلغٌ **على الزبون** لم
    يُعلَّم «الزبون دفع» — ومبلغٌ «إله» (مرتجع) ليس على الزبون فلا يُذكَّر به.
    """
    if status != OBLIGATION_STATUS_PENDING:
        return False
    if missing:
        return True
    if client_paid or direction == OBLIGATION_DIRECTION_REFUND:
        return False
    if amount is None:
        return False
    return amount > 0


# ── أدواتٌ داخليّة ───────────────────────────────────────────────────────────
def _day_start(day):
    """بدايةُ اليوم المحلّيّ لحظةً واعية — مفتاحُ قراءة `scheduled_at`."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def _clean_scheduled_at(value):
    """وقتٌ واعٍ من كائنٍ أو نصّ — و400 يسمّي الحقل، لا `TypeError` بـ500."""
    if isinstance(value, datetime.datetime):
        moment = value
    else:
        try:
            moment = datetime.datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            raise ValidationError({
                "scheduled_at": "وقتٌ غير صالح — الصيغة YYYY-MM-DDTHH:MM.",
            }) from None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return moment


def _client_or_raise(tenant, user, client_id):
    """زبونٌ يراه هذا العضو — وإلا `ReminderClientNotVisible` (404 في الـview).

    والرؤيةُ من `visible_clients` وحدها — النسخةُ الثانية من القاعدة تفترق عنها.
    """
    try:
        pk = int(client_id)
    except (TypeError, ValueError):
        raise ValidationError({"client_id": "معرّفُ زبونٍ غير صالح."}) from None
    client = services.visible_clients(tenant, user).filter(pk=pk).first()
    if client is None:
        raise services.ReminderClientNotVisible({"client_id": "الزبون غير موجود."})
    return client


def _assert_open(appointment):
    """ما صار أو أُلغي لا يُعاد تأكيدُه ولا يُزحزح وقته."""
    if appointment.status != APPOINTMENT_STATUS_SCHEDULED:
        raise ValidationError({
            "status": "الموعدُ ليس محجوزاً — لا تأكيدَ ولا تأجيلَ على ملغىً أو منتهٍ.",
        })
    return appointment


def _stamp(appointment, **fields):
    """كتابةُ حقولٍ مختارةٍ دفعةً واحدة — والصفُّ نفسه يبقى برقمه."""
    fields["updated_at"] = timezone.now()
    ClientAppointment.objects.filter(pk=appointment.pk).update(**fields)
    appointment.refresh_from_db()
    return appointment


def _within_window(rows, *, window_start, day):
    """الصفوفُ المؤقّتة الواقعة في النافذة السارية — **قاعدةٌ واحدة للمولّدَين**.

    الصفُّ بعد اليوم المحسوب لا يُحسب: `ready-to-send` يقبل يوماً صريحاً (لعرض
    يومٍ مضى)، وصفٌّ كُتب بعده لم يكن قد وُجد «حينها».
    """
    return [row for row in rows if window_start <= row["day"] <= day]


# ── السطر كما يُعرض ─────────────────────────────────────────────────────────
def appointment_row(appointment, *, day=None, tax_system=None) -> dict:
    """سطرُ موعدٍ واحد: نوعُه ووقتُه وحالتُه — والتسمياتُ من الخادم لا من الواجهة.

    **ونظامُ زبونه الضريبيُّ معه** (#281): رابطُ الواتساب يحتاج مفتاحَ دولة
    الأرضيِّ (`officeWhatsappLink`)، ولا يُخمَّن نظامٌ من مكانٍ آخر.
    """
    scheduled = timezone.localtime(appointment.scheduled_at)
    created_by = appointment.created_by
    return {
        "id": appointment.pk,
        "client": {"id": appointment.client_id, "name": appointment.client.name},
        "tax_system": tax_system,
        "kind": appointment.kind,
        "kind_label": APPOINTMENT_KIND_LABELS.get(appointment.kind, ""),
        "scheduled_at": scheduled.isoformat(),
        "day": scheduled.date().isoformat(),
        "time": scheduled.strftime("%H:%M"),
        "note": appointment.note,
        "status": appointment.status,
        "status_label": APPOINTMENT_STATUS_LABELS.get(appointment.status, ""),
        "confirmed_at": (
            None if appointment.confirmed_at is None
            else timezone.localtime(appointment.confirmed_at).isoformat()
        ),
        "cancelled_at": (
            None if appointment.cancelled_at is None
            else timezone.localtime(appointment.cancelled_at).isoformat()
        ),
        "created_by": (
            None if created_by is None
            else {"id": created_by.pk, "name": services.user_display_name(created_by)}
        ),
        "created_at": timezone.localtime(appointment.created_at).isoformat(),
    }


def _appointment_rows(queryset, *, day=None, tenant=None) -> list[dict]:
    """أسطرٌ ونظامُ كلّ زبونٍ **بمسحةٍ واحدة**: لا استعلامُ إعدادٍ لكل صفّ."""
    rows = list(queryset)
    systems: dict[int, object] = {}
    if tenant is not None and rows:
        systems = services.resolve_setting_for_clients(
            tenant, services.TAX_SYSTEM_KEY,
            list({row.client_id: row.client for row in rows}.values()),
        )
    return [
        appointment_row(row, day=day, tax_system=systems.get(row.client_id))
        for row in rows
    ]


def _row_with_system(tenant, appointment, *, day=None) -> dict:
    """سطرُ فعلٍ واحد — نظامُ زبونه يُقرأ له وحده (زبونٌ واحد لا مجموعة)."""
    return appointment_row(
        appointment,
        day=day,
        tax_system=services.resolve_setting(
            tenant, services.TAX_SYSTEM_KEY, client=appointment.client,
        ),
    )


def client_appointments_payload(client, *, day=None) -> dict:
    """تبويبُ «المواعيد» في ملفّ الزبون — مواعيدُه كلُّها بترتيب وقتها.

    **والأنواعُ تُقرأ هنا مرّةً** (`kind_choices`) فيعرض المنتقي تسمياتِ الخادم ولا
    يبني جدولَ تسمياتٍ ثانياً في الواجهة.
    """
    day = day or timezone.localdate()
    rows = (
        ClientAppointment.objects
        .filter(tenant_id=client.tenant_id, client=client)
        .select_related("client", "created_by")
    )
    return {
        "client": {"id": client.pk, "name": client.name},
        "day": day.isoformat(),
        "rows": _appointment_rows(rows, day=day, tenant=client.tenant),
        "kind_choices": kind_choices(),
    }


def kind_choices() -> list[dict]:
    """أنواعُ المواعيد بتسميات الخادم — مصدرٌ واحدٌ للمنتقي والشاشة."""
    return [
        {"value": value, "label": label} for value, label in APPOINTMENT_KIND_CHOICES
    ]


def appointment_queryset(tenant, user, *, client=None, open_only=True):
    """مواعيدُ ما يراه العضو — **الرؤيةُ من `visible_clients` وحدها**.

    والافتراضُ المحجوزُ وحده (`open_only`): ما صار أو أُلغي لا يزاحم يومَ المكتب،
    ويبقى في ملفّ الزبون بتاريخه (`client_appointments_payload`).
    """
    queryset = (
        ClientAppointment.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "created_by")
        .order_by("scheduled_at", "id")
    )
    if open_only:
        queryset = queryset.filter(status__in=APPOINTMENT_OPEN_STATUSES)
    return queryset if client is None else queryset.filter(client=client)


def appointments_for_day(tenant, user, day, *, client=None) -> list[dict]:
    """«مواعيد اليوم» — المحجوزُ وحده، مرتَّباً بوقته، وداخل رؤية العضو."""
    queryset = appointment_queryset(tenant, user, client=client).filter(
        scheduled_at__gte=_day_start(day),
        scheduled_at__lt=_day_start(day + datetime.timedelta(days=1)),
    )
    return _appointment_rows(queryset, day=day, tenant=tenant)


def calendar_appointments(
    tenant, user, *, start, end, client=None, member=None,
) -> list[dict]:
    """مواعيدُ مدى التقويم — تُعرض مع الالتزامات في اليوم نفسه لا في شاشةٍ ثانية.

    **وبالفلاتر نفسها**: مرشِّحُ الزبون والموظّف في التقويم يقصّان الاثنين معاً —
    عرضُ كل المواعيد تحت تقويمٍ مُرشَّحٍ بزبونٍ واحد يقرأ صفوفاً لغيره.
    """
    queryset = appointment_queryset(tenant, user, client=client)
    if member is not None:
        queryset = queryset.filter(client__responsible_id=member)
    queryset = queryset.filter(
        scheduled_at__gte=_day_start(start),
        scheduled_at__lt=_day_start(end + datetime.timedelta(days=1)),
    )
    return _appointment_rows(queryset, day=start, tenant=tenant)


def appointments_list(tenant, user, *, client=None) -> list[dict]:
    """كلُّ ما يراه العضو بلا مدى — حين لا يسأل الطلبُ عن يومٍ بعينه."""
    return _appointment_rows(appointment_queryset(tenant, user, client=client), tenant=tenant)


# ── الأفعال ─────────────────────────────────────────────────────────────────
@transaction.atomic
def create_appointment(
    tenant, *, user, client_id, kind, scheduled_at, note="",
) -> dict:
    """حجزُ موعدٍ لزبونٍ يراه العضو — بالحالة `scheduled` وبالتاريخ والوقت."""
    if kind not in APPOINTMENT_KIND_LABELS:
        raise ValidationError({"kind": f"نوعُ موعدٍ غير معروف: {kind}."})
    client = _client_or_raise(tenant, user, client_id)
    appointment = ClientAppointment.objects.create(
        tenant=tenant,
        client=client,
        kind=kind,
        scheduled_at=_clean_scheduled_at(scheduled_at),
        note=(note or "").strip(),
        created_by=user,
    )
    return _row_with_system(tenant, appointment)


@transaction.atomic
def reschedule_appointment(appointment, *, scheduled_at, actor, note=None) -> dict:
    """«أجّل» — الوقتُ يتحرّك والصفُّ يبقى: لا إلغاءَ وحجزٌ جديد بإثراءٍ مزدوج."""
    _assert_open(appointment)
    # `confirmed_at` يُمسح: الموعدُ صار وقتاً آخر فتأكيدُه القديمُ لم يعد تأكيداً
    # له، والتقويمُ يخفي زرَّ «ابعت تأكيد» متى وُجد — فبلا المسح لا يُعاد التأكيد.
    fields = {"scheduled_at": _clean_scheduled_at(scheduled_at), "confirmed_at": None}
    if note is not None:
        fields["note"] = (note or "").strip()
    return _row_with_system(appointment.tenant, _stamp(appointment, **fields))


@transaction.atomic
def cancel_appointment(appointment, *, actor) -> dict:
    """«ألغِ» — **حالةٌ لا حذف**: الصفُّ يبقى أثراً بوقت إلغائه."""
    if appointment.status == APPOINTMENT_STATUS_CANCELLED:
        raise ValidationError({"status": "الموعدُ ملغىً أصلاً."})
    return _row_with_system(appointment.tenant, _stamp(
        appointment,
        status=APPOINTMENT_STATUS_CANCELLED,
        cancelled_at=timezone.now(),
    ))


@transaction.atomic
def complete_appointment(appointment, *, actor) -> dict:
    """«صار» — الزيارةُ وقعت: الحالةُ تتحرّك والوقت المُسجَّل يبقى."""
    _assert_open(appointment)
    return _row_with_system(
        appointment.tenant, _stamp(appointment, status=APPOINTMENT_STATUS_DONE),
    )


def _appointment_render_values(tenant, appointment, client, *, language="") -> dict:
    """قيمُ رموز النصّ لموعد — `{due_date}` يومُ الموعد لا يومُ الحساب.

    و`{period}` و`{amount}` و`{missing_list}` **غائبةٌ** هنا: الموعدُ ليس فترةً ولا
    مبلغاً ولا ناقصاً — نصُّ الموعد المشحون لا يقرؤها، وملؤها بقيمةٍ مخترعةٍ يكذب
    على من يخصّص النصّ. وتُنطق **`REMINDER_ABSENT_TEXT` بلغة المستلِم** كما في
    `services._reminder_render_values`: عُرفٌ واحدٌ للغياب لا «فراغٌ هنا و«لا
    شيء» هناك».
    """
    scheduled = timezone.localtime(appointment.scheduled_at)
    absent = services.reminder_absent_text(language)
    return {
        "client_name": client.name,
        "period": absent,
        "due_date": scheduled.strftime("%d/%m/%Y"),
        "amount": absent,
        "missing_list": absent,
        "office_name": tenant.CompanyName,
    }


@transaction.atomic
def send_appointment_confirmation(
    tenant, appointment, *, actor, body=None,
) -> dict:
    """«ابعت تأكيد»: رسالةُ تذكيرٍ بالسجلّ القائم (د4) وختمُ وقت التأكيد.

    **ولا يُرسَل إلى غير أهلها**: الجهةُ المستلِمة تُحلّ بالقاعدة القائمة نفسها
    (`resolve_reminder_recipient`: التعيينُ ثم الرئيسية)، وغيابُ جهةٍ بهاتفٍ
    يُرفَض 400 برسالةٍ تدلّ على ما يُضاف — لا صفَّ `sent` إلى لا أحد.

    **ولا `day` هنا**: ما يُسجَّل هو يومُ الموعد نفسه، ووقتُ الختم ساعةُ الفعل —
    تمريرُ يومٍ ثانٍ كان يفتح بابَ صفٍّ بتاريخٍ غير الذي في نصّه.
    """
    _assert_open(appointment)
    client = appointment.client
    link = services.resolve_reminder_recipient(client, REMINDER_APPOINTMENT)
    contact = None if link is None else link.contact
    if contact is None or not (contact.phone or "").strip():
        raise ValidationError({
            "contact": (
                "الزبون بلا جهة اتصالٍ رئيسية بهاتف — أضف جهةً ورقماً قبل التأكيد."
            ),
        })
    if body is None:
        bodies = services.reminder_template_bodies(tenant, REMINDER_APPOINTMENT)
        body = services.render_reminder_body(
            bodies.get(contact.language, ""),
            _appointment_render_values(
                tenant, appointment, client, language=contact.language,
            ),
        )
    scheduled = timezone.localtime(appointment.scheduled_at)
    slot = scheduled.date()
    logs = services.mark_reminders_sent(
        tenant,
        user=actor,
        contact_id=contact.pk,
        body=body,
        items=[{
            "client_id": client.pk,
            "reminder_type": REMINDER_APPOINTMENT,
            "period_start": slot.isoformat(),
            "period_end": slot.isoformat(),
        }],
    )
    stamped = _stamp(appointment, confirmed_at=timezone.now())
    return {
        "appointment": _row_with_system(tenant, stamped),
        "log": services.reminder_log_row(logs[0]),
        "body": body,
        "phone": contact.phone,
    }


# ── مولّدُ «تذكير موعد» ──────────────────────────────────────────────────────
def appointment_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """بنودُ موعدٍ اقترب — **مولّدٌ ثانٍ** يمرّ في المحرّك القائم نفسه.

    الميعادُ = `scheduled_at - appointment_reminder_days`، ونافذتُه منه إلى يوم
    الموعد؛ والبندُ مستحقٌّ إن لم يكن في السجلّ صفٌّ مؤقّتٌ **داخل النافذة** —
    فيُسكت «شيل» و«تأكيد» و«انبعثت» حتّى اليوم نفسه، ولا يستهلك تأكيدٌ سابقٌ
    للنافذة تذكيرَ «قبله بيوم».
    """
    if reminder_type is not None and reminder_type != REMINDER_APPOINTMENT:
        return []
    live = [
        client for client in clients
        if REMINDER_APPOINTMENT in (
            settings_by_client[client.pk].get(services.REMINDER_TYPES_ENABLED_KEY) or []
        )
    ]
    if not live:
        return []
    leads = {
        client.pk: settings_by_client[client.pk].get(APPOINTMENT_REMINDER_DAYS_KEY) or 0
        for client in live
    }
    widest = max(leads.values())
    rows = list(
        ClientAppointment.objects
        .filter(
            tenant=tenant,
            client_id__in=list(leads),
            status__in=APPOINTMENT_OPEN_STATUSES,
            scheduled_at__gte=_day_start(day),
            scheduled_at__lt=_day_start(day + datetime.timedelta(days=widest + 1)),
        )
        .order_by("scheduled_at", "id")
        .values("pk", "client_id", "scheduled_at"),
    )
    by_client: dict[int, list] = {}
    for row in rows:
        by_client.setdefault(row["client_id"], []).append(row)
    clients_by_id = {client.pk: client for client in live}
    candidates = []
    for client_id, slots in by_client.items():
        client = clients_by_id[client_id]
        contact = contacts.get((client_id, REMINDER_APPOINTMENT))
        #: بندٌ واحدٌ لكل (زبون، يوم): مفتاحُ البند يومُ الموعد بطرفيه، فموعدان في
        #: يومٍ واحدٍ بندان بمفتاحٍ واحد (مفتاحُ React مكرَّر، وإرسالُ أحدهما يُسكت
        #: الآخر). فيُجمعان في بندٍ بوقتَيهما — وهو ما تُسكته رسالةٌ واحدة أصلاً.
        times_by_day: dict[datetime.date, list[str]] = {}
        for slot in slots:
            scheduled = timezone.localtime(slot["scheduled_at"])
            times_by_day.setdefault(scheduled.date(), []).append(f"{scheduled:%H:%M}")
        for slot_day, times in times_by_day.items():
            window_start = slot_day - datetime.timedelta(days=leads[client_id])
            count = len(_within_window(
                by_pair.get(
                    (client_id, REMINDER_APPOINTMENT, slot_day, slot_day), (),
                ),
                window_start=window_start,
                day=day,
            ))
            candidates.append(services.ReminderCandidate(
                client=client,
                reminder_type=REMINDER_APPOINTMENT,
                # المفتاحُ يومُ الموعد بطرفيه، وبندُ اليوم واحدٌ يحمل مواعيده كلَّها
                # (`times_by_day`) — فلا يتكرّر المفتاحُ بين بنود الحمولة.
                period_start=slot_day,
                period_end=slot_day,
                missing=(),
                missing_codes=(),
                count=count,
                maximum=APPOINTMENT_REMINDER_MAX,
                interval_days=leads[client_id],
                next_due=window_start,
                contact=contact,
                tax_system=settings_by_client[client_id].get(services.TAX_SYSTEM_KEY),
                # من فتح النافذة إلى يوم الموعد نفسه، ولا إرسالَ بعد أن مضى.
                due=(
                    window_start <= day <= slot_day
                    and count < APPOINTMENT_REMINDER_MAX
                ),
                exhausted=count >= APPOINTMENT_REMINDER_MAX,
                postponed=(client_id, REMINDER_APPOINTMENT) in postponed_pairs,
                badge=OBLIGATION_BADGE_NEAR,
                render_due=slot_day,
                period_text=f"{slot_day:%d/%m/%Y} {'، '.join(times)}",
            ))
    return candidates


# ── مولّدُ «موعد رسمي قريب» (د3) ────────────────────────────────────────────
def _deadline_window(day, due):
    """النافذةُ السارية اليوم من موضعَي `(7، 2)`: (موضعُها، بدايتها).

    والموضعُ يُقرأ من اليوم لا من عدد الصفوف: `(7)` ساريةٌ من `due - 7`، و`(2)`
    تفتح فوقها من `due - 2` فتلغيها (الأضيقُ هو الساري). وقبل أن تُفتح الأولى
    يُرجَع موضعُها هي — وبدايتُها بعد اليوم، فلا يستحقّ البند.
    """
    for index in range(len(DEADLINE_REMINDER_OFFSETS), 0, -1):
        start = due - datetime.timedelta(days=DEADLINE_REMINDER_OFFSETS[index - 1])
        if day >= start:
            return index, start
    return 1, due - datetime.timedelta(days=DEADLINE_REMINDER_OFFSETS[0])


def _period_unpaid_total(rows):
    """مجموعُ المستحقّ **على الزبون** في التزامات فترةٍ — `Decimal` أو `None`.

    المدفوعُ («الزبون دفع») والمرتجعُ («إلنا» لا «علينا») لا يدخلان المجموع،
    ومجموعُ صفرٍ يعني «لا مبلغَ في النصّ» لا «مبلغٌ صفر».
    """
    total = sum(
        (
            row["amount"] for row in rows
            if row["amount"] is not None
            and not row["client_paid"]
            and row["direction"] != OBLIGATION_DIRECTION_REFUND
        ),
        Decimal("0"),
    )
    return total if total > 0 else None


def deadline_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    missing_by_period, postponed_pairs, reminder_type=None,
) -> list:
    """بنودُ «موعد رسمي قريب» — **بندٌ واحدٌ لكل (زبون، فترة)**.

    المصدرُ `Obligation.due_date` وحدها (الممدَّدُ أو الفعليّ) — ولذلك يعبر
    التمديدُ الموضعَين معه بلا حسابٍ ثانٍ. والالتزامُ الذي لا شيءَ على الزبون فيه
    لا يفتح بنداً، و«انقدّم»/«مش لازم» يُسقطانه قبل السؤال أصلاً. والتزاماتُ
    الفترة الواحدة تُجمع: **أقربُ** موعدٍ لم يمضِ بين التزاماتها **التي عليها
    شيء** هو ما يفتح نافذتها (لا أبكرُ التزامٍ في الفترة: المدفوعُ والماضي لا
    يُسقطان تذكيرَ الموعد الحقيقيّ)، وإن لم يبقَ منها موعدٌ قادمٌ فلا بند. وأسماءُ
    الناقص اتّحادُها، والمبلغُ مجموعُ المستحقّ عليها.
    """
    if reminder_type is not None and reminder_type != REMINDER_DEADLINE:
        return []
    live = [
        client for client in clients
        if REMINDER_DEADLINE in (
            settings_by_client[client.pk].get(services.REMINDER_TYPES_ENABLED_KEY) or []
        )
    ]
    if not live:
        return []
    widest = max(DEADLINE_REMINDER_OFFSETS)
    rows = list(
        Obligation.objects
        .filter(
            tenant=tenant,
            client_id__in=[client.pk for client in live],
            status=OBLIGATION_STATUS_PENDING,
        )
        .values(
            "client_id", "period_start", "period_end", "actual_deadline",
            "extended_to", "amount", "client_paid", "direction",
        )
    )
    periods: dict[tuple[int, object, object], list] = {}
    for row in rows:
        periods.setdefault(
            (row["client_id"], row["period_start"], row["period_end"]), [],
        ).append(row)
    clients_by_id = {client.pk: client for client in live}
    maximum = len(DEADLINE_REMINDER_OFFSETS)
    candidates = []
    for (client_id, period_start, period_end), period_rows in periods.items():
        bucket = missing_by_period.get((client_id, period_start, period_end)) or {}
        missing = tuple(bucket.get("names") or ())
        owing = [
            row for row in period_rows
            if client_owes(
                status=OBLIGATION_STATUS_PENDING,
                missing=missing,
                amount=row["amount"],
                client_paid=row["client_paid"],
                direction=row["direction"],
            )
        ]
        if not owing:
            continue
        #: أقربُ موعدٍ **لم يمضِ بعدُ** بين التزامات الفترة **التي عليها شيء** وحدها:
        #: ما لا شيءَ عليه (مدفوعٌ أو مرتجعٌ) ليس موعداً يُذكَّر به، وما مضى موعدُه
        #: متأخّرٌ يخصّه التنبيهُ الأحمر. والأبكرُ منهما كان يجعل `day <= due` خطأً
        #: للفترة كلّها فيسقط «قبل ٧» و«قبل ٢» عن موعدها الحقيقيّ.
        upcoming = [
            moment for moment in (
                row["extended_to"] or row["actual_deadline"] for row in owing
            )
            if moment >= day
        ]
        if not upcoming:
            continue
        due = min(upcoming)
        if (due - day).days > widest:
            # أبعدُ من أوسع النوافذ — لا بندَ له اليومَ أصلاً (كلفةٌ لا نتيجة).
            continue
        window_index, window_start = _deadline_window(day, due)
        #: الصفوفُ المؤقّتة **داخل النافذة السارية** — وجودُ واحدٍ يُسكتها.
        observed = _within_window(
            by_pair.get(
                (client_id, REMINDER_DEADLINE, period_start, period_end), (),
            ),
            window_start=window_start,
            day=day,
        )
        candidates.append(services.ReminderCandidate(
            client=clients_by_id[client_id],
            reminder_type=REMINDER_DEADLINE,
            period_start=period_start,
            period_end=period_end,
            missing=missing,
            missing_codes=tuple(bucket.get("codes") or ()),
            # `step`/`max` من موضع النافذة لا من الصفوف: النافذةُ الثانية «٢ من ٢»
            # ولو لم يُرسل شيءٌ في الأولى.
            count=window_index - 1,
            maximum=maximum,
            interval_days=DEADLINE_REMINDER_OFFSETS[-1],
            next_due=window_start,
            contact=contacts.get((client_id, REMINDER_DEADLINE)),
            tax_system=settings_by_client[client_id].get(services.TAX_SYSTEM_KEY),
            # من فتح النافذة، و**إلى يوم الموعد نفسه** بنيةً: `due` من `upcoming` فلا
            # يكون إلّا `>= day` — بعده يصير متأخّراً، والتنبيهُ الأحمرُ يخصّه
            # (`obligation_late`) فلا ينبّه النصُّ تذكيراً بموعدٍ فات.
            # وصفٌّ في السجلّ داخل النافذة السارية يُسكتها حتّى تُفتح التالية.
            due=window_start <= day and not observed,
            # والسقفُ بنيويٌّ لا عدّاد: نافذتان لا ثالثَ بعدهما، وما بعد يوم
            # الموعد لا موعدَ قادمَ له فيسقط البندُ — فلا `exhausted` لهذا النوع أبداً.
            exhausted=False,
            postponed=(client_id, REMINDER_DEADLINE) in postponed_pairs,
            badge=OBLIGATION_BADGE_NEAR,
            render_due=due,
            amount=_period_unpaid_total(period_rows),
        ))
    return candidates
