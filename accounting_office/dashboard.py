"""لوحة صاحب المكتب (#289) — «كم على المكتب، ومن متأخّر، وما ينتظرني».

**اللوحةُ للمالك وحده، والباقي يُقرأ من مواضعه القائمة:**

- **«اللي عليه» من الدالّة الواحدة** (`payments.client_due_map`): لا صيغةَ مبلغٍ
  ثانيةً هنا. `due_total` مجموعُ `due` لكل زبونٍ يراه العضو — و`due` سالبٌ حين
  يكون للزبون رصيدٌ دائن، فيُجمَع كما هو: مكتبٌ له عند زبونٍ 500 وعليه لآخر
  1,000 «عليه» 500 لا 1,500.
- **التأخيرُ من `services.badge_keys`** — نفسُ الشارة التي تراها شاشةُ «اليوم»:
  الأحمرُ التزامٌ تجاوز موعده الساريّ، والأصفرُ شغلةٌ تجاوزت موعدها الداخليّ.
  فلا صيغةُ تأخيرٍ ثانيةٌ تفترق عن الأولى عند أوّل تمديد.
- **الانتظارُ من مواضعه**: مسودّاتُ الأتعاب من `fees.pending_drafts`، والتصعيدُ
  وتغيّرُ اللائحة من `services.visible_alerts` — أي من الجرس نفسه: ما رآه صاحبُ
  المكتب في جرسه هو ما يُعدّ هنا، لا نسخةٌ ثانيةٌ من شرط «محسوم».

**والاحمرارُ عتبتان من السجلّ لا ثابتٌ في الواجهة** (`dashboard_late_share_percent`
و`dashboard_late_ratio`): الصفُّ يحمرّ حين تبلغ نسبةُ المتأخّر من زبائن الموظف
عتبتَها، **أو** حين يبلغ متأخّرُه عتبةَ مضاعفِ متوسط المكتب. الاجتماعُ بـ«أو»
مقصود: النسبةُ وحدها تظلم مكتباً كبيراً، والمضاعفُ وحده يظلم صغيراً.

**ومكتبُ شخصٍ واحدٍ لا جدولَ فيه** (`single_person`): الجدولُ لمن يوزّع، ومن
يعمل وحده يعرف زبائنه — والواجهةُ تقرأ العلمَ ولا تخمّن من عدد الصفوف.

**والكلفةُ ثابتة**: مجموعاتُ الزبائن استعلامٌ واحد، و«اللي عليه» استعلامان
(`client_due_map`)، والالتزاماتُ المنتظِرة استعلامٌ واحدٌ بـ`select_related`
(كما تفعل «اليوم»)، والأوراقُ استعلامان (`document_progress`)، والتنبيهاتُ
استعلامٌ لكل مجموعة — ولا استعلامَ داخل حلقة.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.utils import timezone

from accounting_office import fees, payments, services, settings_registry
from accounting_office.models import (
    OBLIGATION_BADGE_LATE,
    OBLIGATION_STATUS_PENDING,
    OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED,
    OFFICE_ALERT_KIND_REMINDER_LIMIT,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
    OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
    Obligation,
)
from core.access import MANAGER_ROLE, office_role_keys, user_tenant_role
from tenants.models import UserCompanyMembership

#: مفتاحا العتبة — يُقرآن من السجلّ في كل نداء، فلا قيمةَ مكتوبةً في اللوحة.
LATE_SHARE_PERCENT_KEY = "dashboard_late_share_percent"
LATE_RATIO_KEY = "dashboard_late_ratio"
#: «مكتبُ شخصٍ واحد» — القيمةُ التي يختارها المكتب في أوّل تشغيل (لا عددُ صفوف).
OFFICE_SIZE_KEY = "office_size"
OFFICE_SIZE_SOLO = "solo"

#: خانتان لمتوسط المكتب في الحمولة — رقمُ عرضٍ لا مبلغ، فلا يمرّ بالقناع.
AVERAGE_QUANTUM = Decimal("0.01")

#: مجموعاتُ «بانتظارك» — المفتاحُ يقول للواجهة ماذا تفعل، والتسميةُ من الخادم.
WAITING_FEE_DRAFTS = "fee_drafts"
WAITING_REMINDER_ESCALATIONS = "reminder_escalations"
WAITING_SCHEDULE_CHANGES = "schedule_changes"

#: الفعلُ الذي تربطه الواجهة بالمفتاح: اعتمادُ الكلّ، أو فتحُ شاشة.
ACTION_APPROVE_ALL = "approve_all"
ACTION_OPEN_READY_TO_SEND = "open_ready_to_send"
ACTION_OPEN_DEADLINE_RULES = "open_deadline_rules"

#: أنواعُ التنبيه التي تدخل كلَّ مجموعة — **من ثوابت النموذج** لا بنصٍّ مكرَّر.
REMINDER_ESCALATION_KINDS: tuple[str, ...] = (
    OFFICE_ALERT_KIND_REMINDER_LIMIT,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
)
SCHEDULE_CHANGE_KINDS: tuple[str, ...] = (
    OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
    OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED,
)

WAITING_LABELS: dict[str, str] = {
    WAITING_FEE_DRAFTS: "مسودّات أتعاب تنتظر الاعتماد",
    WAITING_REMINDER_ESCALATIONS: "تصعيدات تذكير — الأوراق ناقصة",
    WAITING_SCHEDULE_CHANGES: "تنبيهات تغيّر لائحة المواعيد",
}
WAITING_ACTIONS: dict[str, str] = {
    WAITING_FEE_DRAFTS: ACTION_APPROVE_ALL,
    WAITING_REMINDER_ESCALATIONS: ACTION_OPEN_READY_TO_SEND,
    WAITING_SCHEDULE_CHANGES: ACTION_OPEN_DEADLINE_RULES,
}


# ── الدور: صاحبُ المكتب وحده ────────────────────────────────────────────────
def can_read_dashboard(tenant, user) -> bool:
    """هل يقرأ هذا العضو اللوحة؟ صاحبُ المكتب — لا مديرُ المكتب ولا المحاسب."""
    return user_tenant_role(user, tenant) == MANAGER_ROLE


def assert_dashboard_owner(tenant, actor) -> None:
    """**403 برسالته** لا 404: العضوُ يعمل في المكتب ويعرف اللوحة، وليس له دورها."""
    if not can_read_dashboard(tenant, actor):
        raise PermissionDenied("لوحةُ المكتب لصاحب المكتب وحده.")


# ── الأرقام الكبيرة ─────────────────────────────────────────────────────────
def _clients_snapshot(tenant, user):
    """زباينُ العضو المرئيّون ومعرّفاتُ مسؤوليهم — استعلامٌ واحدٌ بلا كائنات.

    ولا تُقرأ كائناتُ `OfficeClient` كاملةً: اللوحةُ تحتاج المعرّفَ والمسؤولَ
    وحدهما، و`client_due_map` تقبل معرّفات.
    """
    return list(
        services.visible_clients(tenant, user)
        .values("pk", "responsible_id")
        .order_by(),
    )


def _due_total(tenant, clients):
    """Σ «اللي عليه» من الدالّة الواحدة — ومعه مَن عليه مالٌ زبوناً زبوناً.

    `due` سالبٌ حين يكون للزبون رصيدٌ دائن، ولا يُقصّ إلى صفر: الصفرُ يقول «لا
    شيء عليه» والسالِبُ يقول «له عندنا» — والمجموعُ فرقُهما.
    """
    dues = payments.client_due_map(tenant, [row["pk"] for row in clients])
    total = sum((due.due for due in dues.values()), Decimal("0.00"))
    owing = {client_id for client_id, due in dues.items() if due.due > 0}
    return total, owing


def _late_snapshot(tenant, *, day):
    """الالتزاماتُ المنتظِرةُ وشاراتُها — استعلامٌ واحدٌ ثم حسابٌ في الذاكرة.

    **والشارةُ من `services._badge_keys`** لا من شرطٍ مكتوبٍ هنا: التمديدُ
    والتأخيرُ الداخليُّ يُقرآن من موضعٍ واحدٍ تراه «اليوم» أيضاً — والنداءُ
    الخاصُّ عبر الوحدات مقصودٌ كنمط `fee_invoices` مع `fees._assert_approver`:
    نسخةٌ ثانية من القاعدة تفترق عن الأولى بصمت.
    """
    pending = list(
        Obligation.objects
        .filter(tenant=tenant, status=OBLIGATION_STATUS_PENDING)
        .select_related("client", "task"),
    )
    tagged = [(row, services._badge_keys(row, day, task=row.task)) for row in pending]
    late_rows = [(row, keys) for row, keys in tagged if OBLIGATION_BADGE_LATE in keys]
    # الشغلةُ متأخّرةٌ داخلياً بموعدها هي — لا بشارة الالتزام فوقها: شغلةٌ صار
    # التزامُها أحمرَ تُعدّ مرّتين في `late_total` (التزاماً وشغلةً) كما في التوليد.
    late_tasks = {row.task_id for row, _keys in tagged if row.task.internal_deadline < day}
    return pending, tagged, late_rows, late_tasks


def _owner_id(obligation):
    """المسؤولُ الفعليُّ للصفّ — `effective_assignee` نفسُه: الشغلةُ ثم الزبون."""
    return obligation.task.assignee_id or obligation.client.responsible_id


def _missing_docs_by_owner(pending, progress) -> dict[int, int]:
    """عددُ التزامات كلِّ مسؤولٍ التي ينقصها ورقة — من `document_progress` وحدها."""
    counts: dict[int, int] = {}
    for obligation in pending:
        if not (progress.get(obligation.pk) or {}).get("missing"):
            continue
        owner_id = _owner_id(obligation)
        if owner_id is None:
            continue
        counts[owner_id] = counts.get(owner_id, 0) + 1
    return counts


def _office_members(tenant):
    """أعضاءُ المكتب النشطون بدور مكتب — **الأدوارُ مشتقّةٌ في `core.access`**."""
    return list(
        UserCompanyMembership.objects
        .filter(
            tenant=tenant,
            role__in=office_role_keys(),
            user__is_active=True,
        )
        .select_related("user")
        .order_by("id"),
    )


def _thresholds(tenant) -> tuple[int, Decimal]:
    """العتبتان من السجلّ — لا قيمةَ مكتوبةً هنا ولا في الواجهة."""
    share = services.resolve_setting(tenant, LATE_SHARE_PERCENT_KEY)
    ratio = services.resolve_setting(tenant, LATE_RATIO_KEY)
    share = settings_registry.SETTINGS_REGISTRY[LATE_SHARE_PERCENT_KEY].default \
        if share is None else share
    ratio = settings_registry.SETTINGS_REGISTRY[LATE_RATIO_KEY].default \
        if ratio is None else ratio
    return int(share), Decimal(str(ratio))


def _is_red(*, late, clients, average, share_percent, ratio) -> bool:
    """يحمرّ الصفُّ بتجاوز **إحدى** العتبتين — ونسبةٌ أو مضاعفٌ لا مجموع.

    و`late == 0` لا يُحمرّ أبداً ولو كانت العتبةُ صفراً: صفٌّ بلا تأخيرٍ أحمرُ
    يجعل اللونَ بلا معنى.
    """
    if late <= 0:
        return False
    if clients and Decimal(late) * 100 >= Decimal(share_percent) * Decimal(clients):
        return True
    return Decimal(late) >= ratio * average


# ── «بانتظارك» ──────────────────────────────────────────────────────────────
def _alert_counts(tenant, user, *, day) -> dict[str, int]:
    """تنبيهاتُ العضو غيرُ المقروءة بعددها لكل نوع — من الجرس نفسه لا نسخةٍ منه."""
    return dict(
        services.visible_alerts(tenant, user, day=day)
        .filter(seen_at__isnull=True)
        .values("kind")
        .annotate(total=Count("pk"))
        .values_list("kind", "total")
        .order_by(),
    )


def _waiting_group(kind, count) -> dict:
    return {
        "kind": kind,
        "label": WAITING_LABELS[kind],
        "count": count,
        "action": WAITING_ACTIONS[kind],
    }


def _waiting(tenant, user, *, day) -> dict:
    """ما ينتظر صاحبَ المكتب فعلاً — وبعددٍ لكل مجموعةٍ وأفعالُها معها.

    **مسودّاتُ الأتعاب تُعدّ على المكتب** لا على الزبائن المرئيّين: الاعتمادُ
    «اعتمد الكل» على كل منتظرة، فالعددُ الصحيحُ هو عددُها.
    """
    counts = _alert_counts(tenant, user, day=day)
    groups = [
        _waiting_group(WAITING_FEE_DRAFTS, fees.pending_drafts(tenant).count()),
        _waiting_group(
            WAITING_REMINDER_ESCALATIONS,
            sum(counts.get(kind, 0) for kind in REMINDER_ESCALATION_KINDS),
        ),
        _waiting_group(
            WAITING_SCHEDULE_CHANGES,
            sum(counts.get(kind, 0) for kind in SCHEDULE_CHANGE_KINDS),
        ),
    ]
    return {
        "total": sum(group["count"] for group in groups),
        # المجموعةُ الفارغة لا تُعرض — «بانتظارك» لا يقول صفراً ثلاث مرّات.
        "groups": [group for group in groups if group["count"]],
    }


# ── الحمولة ─────────────────────────────────────────────────────────────────
def dashboard_payload(tenant, *, user, day: date | None = None) -> dict:
    """حمولةُ اللوحة: رقمان كبيران، وجدولُ الموظفين، وما ينتظر صاحبَ المكتب.

    **`masked` يُحسب مرّةً** (`can_see_amounts`) ويُمرَّر: لا يُسأل القناعُ لكل
    حقل. والمقنَّعُ يبقى **بمفتاحه** بقيمة `None` — الواجهةُ ترسم «—» ولا تخمّن.
    """
    day = day or timezone.localdate()
    masked = not services.can_see_amounts(tenant, user)

    clients = _clients_snapshot(tenant, user)
    due_total, owing_ids = _due_total(tenant, clients)
    pending, tagged, late_rows, late_tasks = _late_snapshot(tenant, day=day)
    progress = services.document_progress(tenant, pending)
    missing_by_owner = _missing_docs_by_owner(pending, progress)

    clients_by_owner: dict[int, int] = {}
    owing_by_owner: dict[int, int] = {}
    for row in clients:
        owner_id = row["responsible_id"]
        if owner_id is None:
            continue
        clients_by_owner[owner_id] = clients_by_owner.get(owner_id, 0) + 1
        if row["pk"] in owing_ids:
            owing_by_owner[owner_id] = owing_by_owner.get(owner_id, 0) + 1
    late_by_owner: dict[int, int] = {}
    for obligation, _keys in late_rows:
        owner_id = _owner_id(obligation)
        if owner_id is None:
            continue
        late_by_owner[owner_id] = late_by_owner.get(owner_id, 0) + 1

    share_percent, ratio = _thresholds(tenant)
    # **الجدولُ لمن له زبائن**: صفٌّ بصفر زبائنَ لا يوزّع شيئاً، وإدخالُه في
    # المتوسط يخفض العتبةَ بلا سببٍ حقيقيّ.
    staff_users = [
        membership.user for membership in _office_members(tenant)
        if membership.user_id in clients_by_owner
    ]
    staff_users.sort(key=services.user_display_name)
    average = (
        Decimal(sum(late_by_owner.get(row.pk, 0) for row in staff_users))
        / Decimal(len(staff_users))
        if staff_users else Decimal("0.00")
    )
    staff = []
    for member in staff_users:
        late = late_by_owner.get(member.pk, 0)
        staff.append({
            "id": member.pk,
            "name": services.user_display_name(member),
            "clients": clients_by_owner.get(member.pk, 0),
            "late": late,
            "missing_docs": missing_by_owner.get(member.pk, 0),
            "overdue_clients": owing_by_owner.get(member.pk, 0),
            "red": _is_red(
                late=late,
                clients=clients_by_owner.get(member.pk, 0),
                average=average,
                share_percent=share_percent,
                ratio=ratio,
            ),
        })

    payload = {
        "day": day.isoformat(),
        "due_total": due_total,
        "late_total": len(late_rows) + len(late_tasks),
        "staff": staff,
        "waiting": _waiting(tenant, user, day=day),
        # الواجهةُ تقرأ العلمَ ولا تستنتج من عدد الصفوف.
        "single_person": (
            services.resolve_setting(tenant, OFFICE_SIZE_KEY) == OFFICE_SIZE_SOLO
        ),
        "thresholds": {
            "late_share_percent": share_percent,
            "late_ratio": str(ratio),
            "office_average_late": str(average.quantize(AVERAGE_QUANTUM)),
        },
    }
    return services.mask_amounts(payload, ("due_total",)) if masked else payload
