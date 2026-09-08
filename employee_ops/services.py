"""خدمات متابعة الموظفين."""
import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

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

from .models import EmployeeInvitation, EmployeeOpsSettings, EmployeeProfile

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
