"""خدمات متابعة الموظفين."""
import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from core.access import FIELD_STAFF_ROLE
from core.activity import log_activity
from core.modules import module_enabled
from core.plans import (
    current_usage,
    enforce_limits,
    limit_exceeded_message,
    limit_value,
)
from hr.models import Employee
from tenants.models import UserCompanyMembership

from .models import (
    EmployeeInvitation,
    EmployeeOpsSettings,
    EmployeeProfile,
    Task,
    TaskAssignment,
    TaskSubmission,
    TaskSubmissionAttachment,
    TaskSubmissionItem,
)

MODULE_KEY = "employee_ops"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _log_activity(*, tenant, actor, action, entity_type, entity_id, entity_label="", description="", metadata=None):
    """يمرّ عبر `core.activity.log_activity` لا بالكتابة المباشرة.

    عقدُ `core.models.ActivityLog` صريح: «تُكتب عبر `core.activity.log_activity`
    فقط (**غير حاظرة**)». والكتابةُ المباشرة داخل `transaction.atomic` تجعل فشلَ
    **تسجيلٍ** يُسقط إنشاءَ الموظف — أثرٌ جانبيٌّ لا يريده أحد.
    """
    log_activity(
        tenant=tenant,
        user=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=str(entity_label)[:200],
        description=str(description),
        metadata=metadata or {"module": MODULE_KEY},
    )


def settings_for_read(tenant) -> EmployeeOpsSettings:
    """إعدادات الشركة للعرض — **بلا كتابة**.

    الشركة التي لم تضبط شيئاً تُعاد بصفٍّ غير محفوظ يحمل الافتراضيات. طلبُ `GET`
    الذي يكتب صفّاً عطلٌ لا تحسينٌ: يعطّل القراءة من نسخةٍ قرائية، ويترك أثراً
    لمن نظر ولم يغيّر شيئاً.
    """
    tenant_id = getattr(tenant, "pk", tenant)
    existing = EmployeeOpsSettings.objects.filter(tenant_id=tenant_id).first()
    return existing if existing is not None else EmployeeOpsSettings(tenant_id=tenant_id)


def get_or_create_settings(tenant) -> EmployeeOpsSettings:
    """إعدادات الشركة للكتابة — تُنشأ بالافتراضيات إن لم تكن.

    يقبل كائن الشركة أو معرّفها — كما يفعل `core.modules._tenant_id`.
    """
    tenant_id = getattr(tenant, "pk", tenant)
    settings_obj, _ = EmployeeOpsSettings.objects.get_or_create(tenant_id=tenant_id)
    return settings_obj


def next_employee_code(tenant) -> str:
    """رقم الموظف التالي — تسلسل بسيط لكل شركة (نسخة خاصة بالوحدة).

    لا نستورده من hr.payroll لأن ذلك الملف يستورد accounting في رأسه،
    فاستيراده يجعل عطلاً في المحاسبة عطلاً في إنشاء الموظف هنا.
    """
    used = set(
        Employee.objects.filter(tenant=tenant).values_list("code", flat=True)
    )
    numbers = [int(code) for code in used if str(code).isdigit()]
    candidate = (max(numbers) + 1) if numbers else 1
    while str(candidate) in used:
        candidate += 1
    return str(candidate)


def _invitation_expiry(tenant):
    """أجلُ الدعوة من إعدادات الشركة. الحدُّ الأدنى يومٌ واحد يفرضه المُسلسِل."""
    return timezone.now() + timedelta(days=settings_for_read(tenant).invitation_expiry_days)


def _issue_token(invitation_fields: dict) -> tuple[EmployeeInvitation, str]:
    """يُنشئ الدعوة برمزٍ عشوائيّ ويعيد الرمز **الخام مرّةً واحدة**.

    الرمزُ لا يُخزَّن — يُخزَّن تهشيرُه وحده، فلا يُسترجَع بعد هذا الردّ.
    """
    raw_token = secrets.token_urlsafe(32)
    invitation = EmployeeInvitation.objects.create(
        token_hash=_token_hash(raw_token),
        status=EmployeeInvitation.STATUS_PENDING,
        **invitation_fields,
    )
    return invitation, raw_token


@transaction.atomic
def create_employee_with_invitation(
    *,
    tenant,
    actor,
    name: str,
    phone: str = "",
    job_title: str = "",
    manager=None,
) -> tuple[Employee, EmployeeProfile, EmployeeInvitation, str]:
    """إنشاء موظف جديد مع ملفه ودعوته في معاملة واحدة.

    الحساب وعضويّة المستخدم لا يُنشآن هنا — الحساب غير المقبول يبقى مقعداً مشغولاً بشبح.
    """
    enforce_limits(tenant, "hr.employees", "employee_ops.seats")

    manager_obj = None
    if manager is not None:
        if isinstance(manager, Employee):
            manager_obj = manager
        else:
            manager_obj = Employee.objects.filter(tenant=tenant, pk=manager).first()
            if manager_obj is None:
                raise ValidationError({"manager": "المدير المحدد غير موجود في هذه الشركة."})

    code = next_employee_code(tenant)
    employee = Employee.objects.create(
        tenant=tenant,
        name=name.strip(),
        phone=(phone or "").strip(),
        job_title=(job_title or "").strip(),
        code=code,
        is_active=True,
    )
    profile = EmployeeProfile.objects.create(
        tenant=tenant,
        employee=employee,
        manager=manager_obj,
    )
    invitation, raw_token = _issue_token({
        "tenant": tenant,
        "employee": employee,
        "expires_at": _invitation_expiry(tenant),
        "created_by": actor if (actor and actor.is_authenticated) else None,
    })

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="create",
        entity_type="employee",
        entity_id=employee.pk,
        entity_label=employee.name,
        description="إنشاء موظف جديد",
    )
    _log_activity(
        tenant=tenant,
        actor=actor,
        action="create",
        entity_type="employee_invitation",
        entity_id=invitation.pk,
        entity_label=employee.name,
        description="إنشاء دعوة انضمام لموظف",
    )

    return employee, profile, invitation, raw_token


@transaction.atomic
def invite_employee(*, employee: Employee, actor) -> tuple[EmployeeInvitation, str]:
    """إرسال دعوة لموظف قائم في الرواتب بلا حساب.

    يرفض إن كان للموظف user وله عضويّةٌ نشطة في الشركة،
    ويرفض إن كانت له دعوةٌ معلّقة سارية.
    """
    tenant = employee.tenant
    if employee.user_id:
        has_membership = UserCompanyMembership.objects.filter(
            tenant=tenant, user=employee.user
        ).exists()
        if has_membership:
            raise ValidationError("الموظف يملك حساباً وعضوية نشطة في الشركة بالفعل.")

    active_pending = EmployeeInvitation.objects.filter(
        tenant=tenant,
        employee=employee,
        status=EmployeeInvitation.STATUS_PENDING,
        expires_at__gt=timezone.now(),
    ).exists()
    if active_pending:
        raise ValidationError("توجد دعوة معلقة سارية للموظف بالفعل.")

    enforce_limits(tenant, "employee_ops.seats")

    invitation, raw_token = _issue_token({
        "tenant": tenant,
        "employee": employee,
        "expires_at": _invitation_expiry(tenant),
        "created_by": actor if (actor and actor.is_authenticated) else None,
    })

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="create",
        entity_type="employee_invitation",
        entity_id=invitation.pk,
        entity_label=employee.name,
        description="إرسال دعوة لموظف قائم",
    )

    return invitation, raw_token


@transaction.atomic
def resend_invitation(invitation: EmployeeInvitation, actor) -> tuple[EmployeeInvitation, str]:
    """إعادة إرسال دعوة — رمز جديد وأجل جديد، والحالة تبقى pending."""
    if invitation.status == EmployeeInvitation.STATUS_ACCEPTED:
        raise ValidationError("لا يمكن إعادة إرسال دعوة مقبولة.")
    # «تُلغى بضغطة» تعني ما تقوله: الملغاةُ لا تُحيا. ومن أراد دعوةً بعد الإلغاء
    # يرسل واحدةً جديدةً من سجلّ الموظف — فيبقى الإلغاء قراراً لا حالةً مؤقّتة.
    if invitation.status == EmployeeInvitation.STATUS_CANCELLED:
        raise ValidationError("الدعوة ملغاة — أرسل دعوةً جديدة من سجلّ الموظف.")

    tenant = invitation.tenant
    # دعوةٌ معلّقةٌ سارية **تشغل مقعدها أصلاً**، فإعادةُ إرسالها لا تستهلك مقعداً
    # ثانياً ولا يجوز أن تُمنع بالحدّ. أمّا المنتهيةُ أو الملغاة فقد حرّرت مقعدها،
    # وإحياؤها استهلاكٌ جديد يُفحص.
    if invitation.status != EmployeeInvitation.STATUS_PENDING or invitation.expires_at <= timezone.now():
        enforce_limits(tenant, "employee_ops.seats")

    raw_token = secrets.token_urlsafe(32)
    invitation.token_hash = _token_hash(raw_token)
    invitation.status = EmployeeInvitation.STATUS_PENDING
    invitation.expires_at = _invitation_expiry(tenant)
    invitation.save(update_fields=["token_hash", "status", "expires_at"])

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="update",
        entity_type="employee_invitation",
        entity_id=invitation.pk,
        entity_label=invitation.employee.name,
        description="إعادة إرسال دعوة انضمام",
    )

    return invitation, raw_token


@transaction.atomic
def cancel_invitation(invitation: EmployeeInvitation, actor) -> EmployeeInvitation:
    """إلغاء دعوة معلقة."""
    if invitation.status == EmployeeInvitation.STATUS_ACCEPTED:
        raise ValidationError("لا يمكن إلغاء دعوة مقبولة.")

    invitation.status = EmployeeInvitation.STATUS_CANCELLED
    invitation.save(update_fields=["status"])

    _log_activity(
        tenant=invitation.tenant,
        actor=actor,
        action="update",
        entity_type="employee_invitation",
        entity_id=invitation.pk,
        entity_label=invitation.employee.name,
        description="إلغاء دعوة انضمام",
    )

    return invitation


class InvitationExpired(APIException):
    status_code = 410
    default_detail = "انتهت صلاحية الدعوة."
    default_code = "invitation_expired"


INVALID_OR_CANCELLED_INVITATION_MSG = "رابط الدعوة غير صالح أو أُلغي."


def load_pending_invitation(token: str) -> EmployeeInvitation:
    """تحلّ الرمز إلى دعوةٍ صالحةٍ للقبول، أو ترفع الخطأ المناسب.

    **مصدرٌ واحدٌ لسلسلة التحقّق** — كانت مكرّرةً بين العرض العامّ والخدمة، وأيُّ
    فرقٍ بينهما يعني رمزاً تقبله شاشةٌ وترفضه أخرى.

    - رمزٌ لا وجود له أو أُلغي أو استُعمل ⇒ **رسالةٌ واحدة** لا تفرّق بينها،
      فلا يعرف من يجرّب أنّه أصاب دعوةً حقيقيّة.
    - رمزٌ انتهى أجلُه ⇒ تُعلَّم `expired` (كتابةٌ **خارج** أيّ معاملةٍ ستتراجع) ثمّ 410.
    - وحدةٌ سُحب ترخيصُها بعد الإرسال ⇒ 404 برسالةٍ لا تكشف الشركة.
    """
    invitation = (
        EmployeeInvitation.objects.select_related("tenant", "employee")
        .filter(token_hash=_token_hash(str(token)))
        .first()
    )
    if invitation is None or invitation.status != EmployeeInvitation.STATUS_PENDING:
        raise ValidationError(INVALID_OR_CANCELLED_INVITATION_MSG)

    if invitation.expires_at and invitation.expires_at <= timezone.now():
        invitation.status = EmployeeInvitation.STATUS_EXPIRED
        invitation.save(update_fields=["status"])
        raise InvitationExpired()

    if not module_enabled(invitation.tenant, MODULE_KEY):
        raise NotFound("الشركة غير موجودة أو غير مرخصة.")

    return invitation


def accept_invitation(
    *,
    token: str,
    username: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> tuple[User, UserCompanyMembership]:
    """قبول دعوة الانضمام: حسابٌ جديد للمدعوّ الأوّل، **واستعادةُ عضويّةٍ للعائد**.

    الموظفُ الذي سبق أن غادر يحتفظ بحسابه وسجلّه (التعطيل حذف عضويّته وحدها)،
    فدعوتُه الثانية تُعيده إلى شركته بنفس الحساب — و`username`/`password`
    يُتجاهلان حينئذٍ لأنّ حسابه قائم.
    """
    invitation = load_pending_invitation(token)
    tenant = invitation.tenant

    # الفحصُ أعلاه بلا قفل، والقفلُ هنا: القراءةُ الأولى تُعلّم الدعوةَ المنتهية
    # وتُثبّت ذلك **خارج** المعاملة (رفعُ الاستثناء داخلها كان سيتراجع عن التعليم
    # فتبقى `pending` إلى الأبد). وما دون الانتهاء يُعاد فحصُه تحت القفل كي لا
    # يسبق مدعوّان أحدهما الآخر إلى آخر مقعد.
    with transaction.atomic():
        inv = (
            EmployeeInvitation.objects.select_for_update()
            .select_related("tenant", "employee")
            .filter(pk=invitation.pk)
            .first()
        )
        if inv is None or inv.status != EmployeeInvitation.STATUS_PENDING:
            raise ValidationError(INVALID_OR_CANCELLED_INVITATION_MSG)
        if inv.expires_at and inv.expires_at <= timezone.now():
            # سباقٌ نادر: انتهت بين القراءتين. لا نكتب هنا — الكتابةُ ستتراجع مع
            # الاستثناء؛ والمحاولةُ التالية تُعلّمها في الفحص غير المقفول أعلاه.
            raise InvitationExpired()

        # المقعدُ الذي تشغله هذه الدعوةُ المعلّقة يبقى محسوباً بعد القبول (يتحوّل
        # من دعوةٍ إلى عضويّة)، فالسؤال هنا: هل تجاوز الاستهلاكُ الحدَّ أصلاً —
        # كأن يكون الحدُّ خُفِّض بين الإرسال والقبول.
        limit = limit_value(tenant, "employee_ops.seats")
        if limit is not None and current_usage(tenant, "employee_ops.seats") > limit:
            msg = limit_exceeded_message(tenant, "employee_ops.seats", limit)
            raise ValidationError({"plan_limit": msg, "limit_key": "employee_ops.seats"})

        employee = inv.employee

        if employee.user_id:
            # **العائد إلى الشركة** — «العودةُ دعوةٌ جديدة على السجلّ نفسه فيتّصل
            # تاريخه» (المواصفة §٤). التعطيلُ حذف عضويّتَه وأبقى حسابَه وسجلَّه،
            # فالقبولُ هنا **يستعيد العضويّة** ولا يُنشئ حساباً ثانياً. إنشاءُ
            # حسابٍ جديدٍ كان يترك `hr.Employee.user` مشيراً إلى حسابٍ ميّت
            # والعضويّةَ على حسابٍ ثالث — فينقطع التاريخ الذي وُعد باتّصاله.
            user = employee.user
            membership, _ = UserCompanyMembership.objects.get_or_create(
                user=user, tenant=tenant, defaults={"role": FIELD_STAFF_ROLE},
            )
        else:
            username = (username or "").strip()
            if not username:
                raise ValidationError({"username": "اسم المستخدم مطلوب."})
            user = User(
                username=username,
                first_name=first_name.strip() if first_name else "",
                last_name=last_name.strip() if last_name else "",
            )
            # نقطةٌ عامّةٌ تُنشئ حساب دخول: قواعدُ كلمة المرور في
            # `AUTH_PASSWORD_VALIDATORS` لا تُطبَّق من `set_password` وحدها —
            # تُستدعى صراحةً كما في `hr/auth_api.py`. بدونها يُقبل «1» كلمةَ
            # مرورٍ لحسابٍ حقيقيّ في شركةٍ حقيقيّة.
            validate_password(password, user=user)
            user.set_password(password)
            try:
                # الفرادةُ من القاعدة لا من فحصٍ سابقٍ للحفظ: `exists()` ثمّ
                # `save()` يترك نافذةً يسبق فيها طلبٌ آخر فيصير 500 بدل 400.
                with transaction.atomic():
                    user.save()
            except IntegrityError as exc:
                raise ValidationError(
                    {"username": "اسم المستخدم مستعمل بالفعل."}
                ) from exc

            membership = UserCompanyMembership.objects.create(
                user=user, tenant=tenant, role=FIELD_STAFF_ROLE,
            )
            employee.user = user
            employee.save(update_fields=["user", "updated_at"])

        inv.status = EmployeeInvitation.STATUS_ACCEPTED
        inv.accepted_at = timezone.now()
        inv.accepted_user = user
        inv.save(update_fields=["status", "accepted_at", "accepted_user"])

        _log_activity(
            tenant=tenant,
            actor=user,
            action="update",
            entity_type="employee_invitation",
            entity_id=inv.pk,
            entity_label=employee.name,
            description="قبول دعوة الانضمام وإنشاء الحساب",
        )

    return user, membership


@transaction.atomic
def deactivate_employee(*, employee: Employee, actor) -> Employee:
    """تعطيل موظف: المغادرة تعطيلٌ لا حذف.

    employee.is_active = False، وتُحذف عضويّة المستخدم إن كان دورها field_staff وحده
    (فيتحرر المقعد)، وتُلغى الدعوات المعلقة.
    سجل الموظف وتاريخه يبقيان كما هما.
    """
    employee.is_active = False
    employee.save(update_fields=["is_active", "updated_at"])

    tenant = employee.tenant
    if employee.user_id:
        UserCompanyMembership.objects.filter(
            tenant=tenant,
            user=employee.user,
            role=FIELD_STAFF_ROLE,
        ).delete()

    EmployeeInvitation.objects.filter(
        tenant=tenant,
        employee=employee,
        status=EmployeeInvitation.STATUS_PENDING,
    ).update(status=EmployeeInvitation.STATUS_CANCELLED)

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="update",
        entity_type="employee",
        entity_id=employee.pk,
        entity_label=employee.name,
        description="تعطيل موظف",
    )

    return employee


@transaction.atomic
def reactivate_employee(*, employee: Employee, actor) -> Employee:
    """إعادة تفعيل موظف معطل."""
    tenant = employee.tenant
    enforce_limits(tenant, "hr.employees")
    employee.is_active = True
    employee.save(update_fields=["is_active", "updated_at"])

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="update",
        entity_type="employee",
        entity_id=employee.pk,
        entity_label=employee.name,
        description="إعادة تفعيل موظف",
    )

    return employee


def _recompute_task_status(task: Task) -> Task:
    """حالةُ المهمّة العامّة مشتقّةٌ من إسناداتها عند كلّ مراجعة:

    - كلُّ الإسنادات completed ⇒ COMPLETED وcompleted_at يُضبط.
    - وإلا إن بقي تسليمٌ ينتظر (decision="pending") ⇒ WAITING_FOR_REVIEW.
    - وإلا ⇒ IN_PROGRESS.
    """
    assignments = list(task.assignments.all())
    if not assignments:
        # مهمّةٌ بلا مُسنَدٍ إليها لم تبدأ بعد — «قيد التنفيذ» تكذب على قارئها.
        task.status = Task.STATUS_NEW
        task.completed_at = None
    elif all(a.status == TaskAssignment.STATUS_COMPLETED for a in assignments):
        task.status = Task.STATUS_COMPLETED
        if not task.completed_at:
            task.completed_at = timezone.now()
    elif all(a.status == TaskAssignment.STATUS_REJECTED for a in assignments):
        # كلُّ من أُسندت إليه رُفض عملُه ⇒ المهمّة مرفوضة. بدون هذا الفرع كانت
        # `REJECTED` حالةً معلَنةً لا يبلغها شيء، والمهمّةُ المرفوضةُ بالكامل
        # تُعرض «قيد التنفيذ» — والإعادةُ بعد الرفض تُخرجها منها تلقائياً.
        task.status = Task.STATUS_REJECTED
        task.completed_at = None
    elif task.submissions.filter(decision=TaskSubmission.DECISION_PENDING).exists():
        task.status = Task.STATUS_WAITING_FOR_REVIEW
        task.completed_at = None
    else:
        task.status = Task.STATUS_IN_PROGRESS
        task.completed_at = None
    task.save(update_fields=["status", "completed_at", "updated_at"])
    return task


@transaction.atomic
def create_task(
    *,
    tenant,
    actor,
    title: str,
    description: str = "",
    priority: str = "MEDIUM",
    due_date=None,
    category: str = "",
    tags=None,
    target_price=None,
    allowed_sites=None,
    extra=None,
    assignee_ids=None,
) -> Task:
    """إنشاء مهمة جديدة مع إسناداتها لموظفي هذه الشركة حصراً."""
    employees = []
    if assignee_ids:
        unique_ids = list(dict.fromkeys(assignee_ids))
        employees = list(Employee.objects.filter(tenant=tenant, id__in=unique_ids))
        if len(employees) != len(unique_ids):
            raise ValidationError({"assignee_ids": "أحد الموظفين المحددين غير موجود في هذه الشركة."})

    task = Task.objects.create(
        tenant=tenant,
        title=title.strip(),
        description=(description or "").strip(),
        priority=priority,
        status=Task.STATUS_NEW,
        due_date=due_date,
        category=(category or "").strip(),
        tags=tags or [],
        target_price=target_price,
        allowed_sites=allowed_sites or [],
        created_by=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        extra=extra or {},
    )

    for emp in employees:
        TaskAssignment.objects.create(
            tenant=tenant,
            task=task,
            employee=emp,
            status=TaskAssignment.STATUS_NOT_STARTED,
        )

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="create",
        entity_type="task",
        entity_id=task.pk,
        entity_label=task.title,
        description="إنشاء مهمة جديدة",
    )

    return task


@transaction.atomic
def update_task(*, task: Task, actor, **kwargs) -> Task:
    """تعديل مهمة ومزامنة إسناداتها إن لزم."""
    tenant = task.tenant
    assignee_ids = kwargs.pop("assignee_ids", None)
    if assignee_ids is not None:
        unique_ids = list(dict.fromkeys(assignee_ids))
        employees = list(Employee.objects.filter(tenant=tenant, id__in=unique_ids))
        if len(employees) != len(unique_ids):
            raise ValidationError({"assignee_ids": "أحد الموظفين المحددين غير موجود في هذه الشركة."})

        existing = {a.employee_id: a for a in task.assignments.all()}
        new_ids = set(unique_ids)
        # نزعُ مُسنَدٍ **سلّم فعلاً** يحذف صفَّ حالته ويترك تسليماتِه معلّقةً على
        # مهمّةٍ لم يعد مُسنَداً إليها — عملٌ أُنجز ولا يظهر لأحد. من انتهى دورُه
        # وقد سلّم يُراجَع لا يُنزع.
        submitters = set(
            TaskSubmission.objects.filter(task=task).values_list("employee_id", flat=True)
        )
        blocked = sorted(submitters - new_ids)
        if blocked:
            raise ValidationError(
                {"assignee_ids": "لا يمكن نزعُ موظفٍ سلّم على هذه المهمّة — راجع تسليمَه أوّلاً."}
            )
        for emp_id, a in existing.items():
            if emp_id not in new_ids:
                a.delete()
        for emp in employees:
            if emp.id not in existing:
                TaskAssignment.objects.create(
                    tenant=tenant,
                    task=task,
                    employee=emp,
                    status=TaskAssignment.STATUS_NOT_STARTED,
                )

    update_fields = ["updated_at"]
    for field in (
        "title",
        "description",
        "priority",
        "due_date",
        "category",
        "tags",
        "target_price",
        "allowed_sites",
        "extra",
    ):
        if field in kwargs:
            val = kwargs[field]
            if isinstance(val, str):
                val = val.strip()
            setattr(task, field, val)
            update_fields.append(field)

    if len(update_fields) > 1:
        task.save(update_fields=update_fields)

    if assignee_ids is not None:
        # الحالةُ تصف الإسنادات، فتبديلُها يوجب إعادةَ اشتقاقها — وإلا بقيت مهمّةٌ
        # نُزع آخرُ غيرِ المكتملين منها «قيد التنفيذ» إلى الأبد.
        task.refresh_from_db()
        _recompute_task_status(task)

    _log_activity(
        tenant=tenant,
        actor=actor,
        action="update",
        entity_type="task",
        entity_id=task.pk,
        entity_label=task.title,
        description="تعديل مهمة",
    )

    return task


@transaction.atomic
def delete_task(*, task: Task, actor) -> None:
    """حذف مهمة وتسجيل النشاط."""
    tenant = task.tenant
    # مهمّةٌ سُلِّم عليها تحمل عملَ موظفٍ ومراجعةَ مديرٍ — وحذفُها يمحوهما معاً
    # (وسيمحو معهما مصدرَ النقاط في المرحلة التالية). تُحذف المهمّةُ الفارغةُ وحدها.
    if TaskSubmission.objects.filter(task=task).exists():
        raise ValidationError("لا تُحذف مهمّةٌ لها تسليمات — فيها عملُ موظفٍ ومراجعتُه.")
    task_id = task.pk
    task_title = task.title
    task.delete()
    _log_activity(
        tenant=tenant,
        actor=actor,
        action="delete",
        entity_type="task",
        entity_id=task_id,
        entity_label=task_title,
        description="حذف مهمة",
    )


@transaction.atomic
def start_task_timer(*, task: Task, employee: Employee) -> TaskAssignment:
    """بدء مؤقت العمل للموظف على المهمة — متكرر بلا أثر مضاعف (idempotent)."""
    assignment = TaskAssignment.objects.filter(
        tenant=task.tenant, task=task, employee=employee
    ).first()
    if not assignment:
        raise PermissionDenied("المهمة غير مسندة إلى هذا الموظف.")

    # المكتملُ والمُسلَّمُ كلاهما مغلق: تسليمٌ ينتظر في طابور المدير يعود
    # «قيد التنفيذ» بضغطةٍ واحدة — وهو الكذبُ نفسُه الذي بُني الحارس ضدّه.
    if assignment.status in (
        TaskAssignment.STATUS_COMPLETED,
        TaskAssignment.STATUS_SUBMITTED,
    ):
        raise ValidationError("لا يُشغَّل المؤقّت على تسليمٍ ينتظر المراجعة أو عملٍ قُبِل.")

    update_fields = ["status", "updated_at"]
    assignment.status = TaskAssignment.STATUS_IN_PROGRESS
    if not assignment.started_at:
        assignment.started_at = timezone.now()
        update_fields.append("started_at")
    if assignment.work_started_at is None:
        assignment.work_started_at = timezone.now()
        update_fields.append("work_started_at")
    assignment.save(update_fields=update_fields)

    _recompute_task_status(task)

    return assignment


@transaction.atomic
def stop_task_timer(*, task: Task, employee: Employee) -> TaskAssignment:
    """إيقاف مؤقت العمل وإضافة الفارق إلى إجمالي ثواني العمل."""
    assignment = TaskAssignment.objects.filter(
        tenant=task.tenant, task=task, employee=employee
    ).first()
    if not assignment:
        raise PermissionDenied("المهمة غير مسندة إلى هذا الموظف.")

    if assignment.work_started_at is not None:
        elapsed = int((timezone.now() - assignment.work_started_at).total_seconds())
        if elapsed > 0:
            assignment.total_work_seconds += elapsed
        assignment.work_started_at = None
        assignment.save(update_fields=["total_work_seconds", "work_started_at", "updated_at"])

    return assignment


@transaction.atomic
def submit_task(
    *,
    task: Task,
    employee: Employee,
    actor,
    body: str = "",
    items: list = None,
    attachments: list = None,
) -> TaskSubmission:
    """تسليم مهمة من موظف مسند إليه: يرفع حالة الإسناد إلى submitted والمهمة إلى WAITING_FOR_REVIEW."""
    assignment = TaskAssignment.objects.filter(
        tenant=task.tenant, task=task, employee=employee
    ).first()
    if not assignment:
        raise PermissionDenied("المهمة غير مسندة إلى هذا الموظف.")

    # إعادةُ التسليم بعد **الرفض** مسموحة وهي المقصودة؛ أمّا بعد القبول فلا —
    # تسليمٌ ثانٍ على عملٍ قُبِل يعيد المهمّة للطابور ويكرّر نقاطه لاحقاً.
    if assignment.status == TaskAssignment.STATUS_COMPLETED:
        raise ValidationError("هذه المهمّة قُبلت منك بالفعل — لا تُسلَّم مرّةً أخرى.")
    # ولا تسليمَ ثانٍ ينتظر بجانب أوّلَ ينتظر: طابورٌ فيه تسليمان لعملٍ واحدٍ
    # يجعل المدير يراجع ما استُبدل.
    if TaskSubmission.objects.filter(
        tenant=task.tenant,
        task=task,
        employee=employee,
        decision=TaskSubmission.DECISION_PENDING,
    ).exists():
        raise ValidationError("لك تسليمٌ على هذه المهمّة ينتظر المراجعة.")

    submission = TaskSubmission.objects.create(
        tenant=task.tenant,
        task=task,
        employee=employee,
        body=(body or "").strip(),
        decision=TaskSubmission.DECISION_PENDING,
    )

    for pos, it in enumerate(items or []):
        TaskSubmissionItem.objects.create(
            tenant=task.tenant,
            submission=submission,
            product_link=(it.get("product_link") or "").strip(),
            product_price=it.get("product_price"),
            notes=(it.get("notes") or "").strip(),
            attachment_url=(it.get("attachment_url") or "").strip(),
            attachment_name=(it.get("attachment_name") or "").strip(),
            images=it.get("images") or [],
            position=it.get("position", pos),
            extra=it.get("extra") or {},
        )

    for pos, att in enumerate(attachments or []):
        TaskSubmissionAttachment.objects.create(
            tenant=task.tenant,
            submission=submission,
            url=att["url"].strip(),
            name=(att.get("name") or "").strip(),
            position=att.get("position", pos),
        )

    assignment.status = TaskAssignment.STATUS_SUBMITTED
    assignment.save(update_fields=["status", "updated_at"])

    # **الاشتقاق هو الكاتب الوحيد لحالة المهمّة.** كتابةُ `WAITING_FOR_REVIEW`
    # باليد هنا كانت تترك `completed_at` كما هو، فيصير صفٌّ «بانتظار المراجعة»
    # يحمل تاريخَ اكتمال — رقمٌ يكذب على كلّ من يقرؤه.
    _recompute_task_status(task)

    _log_activity(
        tenant=task.tenant,
        actor=actor,
        action="create",
        entity_type="task_submission",
        entity_id=submission.pk,
        entity_label=f"تسليم مهمة: {task.title}",
        description="تسليم مهمة للمراجعة",
    )

    return submission


@transaction.atomic
def review_submission(
    *,
    submission: TaskSubmission,
    actor,
    decision: str,
    reviewer_notes: str = "",
) -> TaskSubmission:
    """مراجعة تسليم مهمة: اعتماد كامل أو جزئي (completed) أو رفض (rejected يلزم سبب)."""
    if decision not in (
        TaskSubmission.DECISION_APPROVED_FULL,
        TaskSubmission.DECISION_APPROVED_PARTIAL,
        TaskSubmission.DECISION_REJECTED,
    ):
        raise ValidationError({"decision": "قرار المراجعة غير صالح."})

    # **التسليمُ يُراجَع مرّةً واحدة.** بدون هذا الحارس يستطيع المدير قلبَ قراره
    # على نفس التسليم مراراً — ومحرّكُ النقاط (مرحلةٌ تالية) يمنح على كلّ قرار،
    # فتُمنح النقطةُ مرّتين لعملٍ واحد. وإلغاءُ القبول له مسارُه: قيدٌ مضادّ.
    if submission.decision != TaskSubmission.DECISION_PENDING:
        raise ValidationError(
            {"decision": "هذا التسليم روجع سابقاً — لا يُراجَع مرّتين."}
        )

    notes = (reviewer_notes or "").strip()
    if decision == TaskSubmission.DECISION_REJECTED and not notes:
        raise ValidationError({"reviewer_notes": "سبب الرفض مطلوب عند رفض التسليم."})

    submission.decision = decision
    submission.reviewer = actor if (actor and getattr(actor, "is_authenticated", False)) else None
    submission.reviewed_at = timezone.now()
    submission.reviewer_notes = notes
    submission.save(update_fields=["decision", "reviewer", "reviewed_at", "reviewer_notes", "updated_at"])

    assignment = TaskAssignment.objects.filter(
        tenant=submission.tenant, task=submission.task, employee=submission.employee
    ).first()
    if assignment:
        if decision in (
            TaskSubmission.DECISION_APPROVED_FULL,
            TaskSubmission.DECISION_APPROVED_PARTIAL,
        ):
            assignment.status = TaskAssignment.STATUS_COMPLETED
            if not assignment.completed_at:
                assignment.completed_at = timezone.now()
            assignment.save(update_fields=["status", "completed_at", "updated_at"])
        elif decision == TaskSubmission.DECISION_REJECTED:
            assignment.status = TaskAssignment.STATUS_REJECTED
            assignment.save(update_fields=["status", "updated_at"])

    _recompute_task_status(submission.task)

    _log_activity(
        tenant=submission.tenant,
        actor=actor,
        action="update",
        entity_type="task_submission",
        entity_id=submission.pk,
        entity_label=f"مراجعة تسليم: {submission.task.title}",
        description=f"قرار المراجعة: {decision}",
    )

    return submission

