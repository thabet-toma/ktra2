"""خدمات عمليات المنصة (المراحل الأولى والثانية والثالثة والرابعة: الأساس ودورة الارتباط وأوامر العمل وقناة الاستقبال).

ترتيب الأقفال الصارم لمنع التعارضات والـ Deadlocks على MySQL:
IntegrationKey -> ServiceSubscription -> PlatformEmployee -> Engagement -> WorkOrder
-> WorkOrderDeliverable -> UserCompanyMembership
ملاحظة: لا يُستعمل select_related مع select_for_update لتجنب قفل جداول غير مقصودة.
"""
import copy
import datetime
import hashlib
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from tenants.models import Tenant, UserCompanyMembership

from .models import (
    AgentGrantedMembership,
    Engagement,
    IntegrationKey,
    PlatformEmployee,
    ServiceSubscription,
    WorkOrder,
    WorkOrderComment,
    WorkOrderDeliverable,
)


class PlatformOpsError(Exception):
    """خطأ عام في خدمات عمليات المنصة."""

    def __init__(self, code: str, detail: str, status_code: int = 400):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class IntegrationKeyError(PlatformOpsError):
    """خطأ في عمليات مفاتيح قنوات الاستقبال."""

    pass


class IntegrationKeyConflict(IntegrationKeyError):
    """تعارض في مفتاح قناة الاستقبال (موجود مسبقاً أو غير متوافق)."""

    def __init__(self, code: str, detail: str, status_code: int = 409):
        super().__init__(code, detail, status_code=status_code)


class WorkOrderError(PlatformOpsError):
    """خطأ في عمليات أو أوامر العمل."""

    pass


class WorkOrderTransitionError(WorkOrderError):
    """خطأ في انتقال حالة أمر العمل غير المسموح به."""

    pass


class EngagementError(PlatformOpsError):
    """خطأ في شروط الإسناد أو التحقق من دورة حياة الارتباط."""

    pass


class EngagementConflict(EngagementError):
    """تعارض في حالة الارتباط أو تكرار ارتباط نشط لنفس الموظف والشركة."""

    def __init__(self, code: str, detail: str, status_code: int = 409):
        super().__init__(code, detail, status_code=status_code)


def is_service_active(tenant) -> bool:
    """هل خدمة المتابعة والإدخال نشطة لهذه الشركة؟

    تفعيل الخدمة هو البوابة الوحيدة لإسناد موظف منصة للشركة.
    """
    if tenant is None:
        return False
    tenant_id = getattr(tenant, "pk", tenant)
    return ServiceSubscription.objects.filter(
        tenant_id=tenant_id,
        status=ServiceSubscription.Status.ACTIVE,
    ).exists()


def is_platform_employee(user, active_only: bool = True) -> bool:
    """هل المستخدم موظف عمليات منصة؟

    الهوية صريحة بوجود صف في PlatformEmployee ولا تُستنتج من كونه سوبر أدمن
    أو له دور مدير في أي شركة.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    qs = PlatformEmployee.objects.filter(user=user)
    if active_only:
        qs = qs.filter(status=PlatformEmployee.Status.ACTIVE)
    return qs.exists()


def build_user_identity_snapshot(user) -> dict:
    """إنشاء لقطة هوية ثابتة ومستقرة للمستخدم.

    تبقى هذه اللقطة مقروءة ومفيدة في سجلات التدقيق حتى لو حُذفت العضوية أو المستخدم لاحقاً.
    """
    if not user:
        return {}
    full_name = ""
    if hasattr(user, "get_full_name"):
        try:
            full_name = user.get_full_name()
        except Exception:
            full_name = ""
    if not full_name:
        first = getattr(user, "first_name", "")
        last = getattr(user, "last_name", "")
        full_name = f"{first} {last}".strip()

    return {
        "user_id": user.pk,
        "username": getattr(user, "username", ""),
        "email": getattr(user, "email", ""),
        "full_name": full_name or getattr(user, "username", ""),
    }


@transaction.atomic
def record_agent_granted_membership(
    *,
    engagement: Engagement,
    membership: UserCompanyMembership,
    role_after: str,
    role_before: str = "",
) -> AgentGrantedMembership:
    """تسجيل منح أو تغيير دور عضوية بواسطة وكيل منصة مع لقطة هوية ثابتة.

    تُشتق الشركة والموظف الفاعل والمستخدم المتأثر مباشرة من (engagement + membership)
    تحت قفل لمنع أي تناقض بين المعاملات.

    ترتيب القفل: PlatformEmployee -> Engagement — كما يعلنه رأسُ الملفّ.
    ويُقرأ `employee_id` بلا قفلٍ أوّلاً ليُقفَل الموظفُ قبل الارتباط: لو قُفل
    الارتباطُ أوّلاً لصار هذا المسارُ يأخذ (Engagement ثمّ PlatformEmployee)
    بينما يأخذ `assign_platform_employee` عكسَهما — وهو تشابكٌ ABBA تكشفه
    MySQL بإسقاطِ إحدى المعاملتين. والقراءةُ بلا قفلٍ آمنة لأنّ `employee_id`
    لا يتغيّر بعد الإنشاء، والحالاتُ تُتحقَّق بعد اكتمال القفلين.
    """
    pre_eng = (
        Engagement.objects.filter(pk=engagement.pk).values("employee_id").first()
    )
    if not pre_eng:
        raise EngagementError("not_found", "الارتباط غير موجود.")

    # 1. قفل موظف المنصة
    employee = PlatformEmployee.objects.select_for_update().get(pk=pre_eng["employee_id"])
    if employee.status != PlatformEmployee.Status.ACTIVE:
        raise EngagementError("employee_not_active", "موظف المنصة ليس نشطاً.")

    # 2. قفل الارتباط
    locked_eng = Engagement.objects.select_for_update().get(pk=engagement.pk)
    if locked_eng.status != Engagement.Status.ACTIVE:
        raise EngagementError("engagement_not_active", "الارتباط ليس نشطاً.")
    if locked_eng.employee_id != employee.pk:
        raise EngagementError("employee_changed", "تغيّر موظفُ الارتباط أثناء القفل.")

    if membership.tenant_id != locked_eng.tenant_id:
        raise EngagementError("tenant_mismatch", "الشركة لا تطابق شركة الارتباط.")

    target_user = membership.user
    user_id = target_user.pk
    snapshot = build_user_identity_snapshot(target_user)

    return AgentGrantedMembership.objects.create(
        tenant_id=locked_eng.tenant_id,
        acting_employee=employee,
        engagement=locked_eng,
        membership=membership,
        user=target_user,
        target_user_id=user_id,
        identity_snapshot=snapshot,
        role_before=role_before or "",
        role_after=role_after,
    )


def _execute_suspend(locked_eng: Engagement, reason: str = "") -> Engagement:
    """تنفيذ التعليق على ارتباط مقفول مسبقاً دون إعادة طلب الأقفال."""
    locked_eng.status = Engagement.Status.SUSPENDED
    locked_eng.suspended_at = timezone.now()
    locked_eng.suspension_reason = str(reason)[:2000]

    if locked_eng.managed_membership_id:
        target_mem = (
            UserCompanyMembership.objects.select_for_update()
            .filter(pk=locked_eng.managed_membership_id)
            .first()
        )
        if target_mem:
            if locked_eng.created_membership:
                target_mem.delete()
            else:
                if locked_eng.previous_role:
                    target_mem.role = locked_eng.previous_role
                    target_mem.save(update_fields=["role"])
        locked_eng.managed_membership = None

    locked_eng.save(
        update_fields=[
            "status",
            "suspended_at",
            "suspension_reason",
            "managed_membership",
            "updated_at",
        ]
    )
    return locked_eng


def _execute_revoke(
    locked_eng: Engagement, revoked_by=None, reason: str = ""
) -> Engagement:
    """تنفيذ الإلغاء على ارتباط مقفول مسبقاً دون إعادة طلب الأقفال."""
    locked_eng.status = Engagement.Status.REVOKED
    locked_eng.revoked_at = timezone.now()
    locked_eng.revoked_by = revoked_by
    locked_eng.revocation_reason = str(reason)[:2000]

    if locked_eng.managed_membership_id:
        target_mem = (
            UserCompanyMembership.objects.select_for_update()
            .filter(pk=locked_eng.managed_membership_id)
            .first()
        )
        if target_mem:
            if locked_eng.created_membership:
                target_mem.delete()
            else:
                if locked_eng.previous_role:
                    target_mem.role = locked_eng.previous_role
                    target_mem.save(update_fields=["role"])
        locked_eng.managed_membership = None

    locked_eng.save(
        update_fields=[
            "status",
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "managed_membership",
            "updated_at",
        ]
    )
    return locked_eng


@transaction.atomic
def assign_platform_employee(
    *,
    employee: PlatformEmployee,
    tenant: Tenant,
    assigned_by=None,
) -> Engagement:
    """إسناد موظف منصة لشركة زبون.

    القواعد:
    1. ترتيب القفل: Subscription -> PlatformEmployee -> Engagement -> UserCompanyMembership.
    2. الإسناد مسموح فقط لاشتراك خدمة نشط ولموظف منصة نشط.
    3. فرادة الارتباط النشط تُفرض تحت قفل داخل معاملة ذرية.
    4. يوفر دور 'manager' للوكيل: إذا وُجدت عضوية قائمة بدور آخر، يُحفظ دورها السابق
       وتُرقى إلى 'manager'؛ أما إذا لم توجد، تُنشأ عضوية 'manager' جديدة ويسجل created_membership=True.
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    emp_pk = getattr(employee, "pk", employee)

    # 1. قفل والتحقق من اشتراك الخدمة
    subscription = (
        ServiceSubscription.objects.select_for_update()
        .filter(tenant=tenant_obj)
        .first()
    )
    if not subscription or subscription.status != ServiceSubscription.Status.ACTIVE:
        raise EngagementError(
            "subscription_not_active",
            "خدمة المتابعة والإدخال غير نشطة لهذه الشركة.",
        )

    # 2. قفل والتحقق من موظف المنصة
    locked_employee = (
        PlatformEmployee.objects.select_for_update()
        .get(pk=emp_pk)
    )
    if locked_employee.status != PlatformEmployee.Status.ACTIVE:
        raise EngagementError("employee_not_active", "موظف عمليات المنصة غير نشط.")

    # 3. قفل والتحقق من عدم وجود ارتباط نشط مسبق
    existing_active = (
        Engagement.objects.select_for_update()
        .filter(
            employee=locked_employee,
            tenant=tenant_obj,
            status=Engagement.Status.ACTIVE,
        )
        .first()
    )
    if existing_active:
        raise EngagementConflict(
            "already_active",
            "يوجد ارتباط نشط بالفعل لهذا الموظف مع هذه الشركة.",
        )

    # 4. قفل والتعامل مع عضوية الشركة
    existing_membership = (
        UserCompanyMembership.objects.select_for_update()
        .filter(user_id=locked_employee.user_id, tenant=tenant_obj)
        .first()
    )

    if existing_membership is None:
        membership = UserCompanyMembership.objects.create(
            user_id=locked_employee.user_id,
            tenant=tenant_obj,
            role="manager",
        )
        created_membership = True
        previous_role = ""
    else:
        membership = existing_membership
        created_membership = False
        previous_role = existing_membership.role
        if existing_membership.role != "manager":
            existing_membership.role = "manager"
            existing_membership.save(update_fields=["role"])

    engagement = Engagement.objects.create(
        employee=locked_employee,
        tenant=tenant_obj,
        status=Engagement.Status.ACTIVE,
        assigned_by=assigned_by,
        created_membership=created_membership,
        managed_membership=membership,
        previous_role=previous_role,
    )

    return engagement


@transaction.atomic
def suspend_engagement(
    *,
    engagement: Engagement,
    reason: str = "",
) -> Engagement:
    """تعليق ارتباط موظف المنصة مؤقتاً.

    ترتيب القفل: Subscription -> Engagement -> UserCompanyMembership
    يحذف فقط العضوية التي أنشأها هذا الارتباط (created_membership=True) عبر معرّفها الدقيق.
    إذا كانت العضوية مسبقة، يستعيد دورها السابق ولا يحذفها.
    """
    eng_pk = getattr(engagement, "pk", engagement)

    # 1. قفل الاشتراك
    pre_eng = Engagement.objects.filter(pk=eng_pk).values("tenant_id").first()
    if pre_eng:
        ServiceSubscription.objects.select_for_update().filter(
            tenant_id=pre_eng["tenant_id"]
        ).first()

    # 2. قفل الارتباط
    locked = Engagement.objects.select_for_update().get(pk=eng_pk)
    if locked.status == Engagement.Status.REVOKED:
        raise EngagementConflict("already_revoked", "الارتباط ملغى نهائياً ولا يمكن تعليقه.")
    if locked.status != Engagement.Status.ACTIVE:
        raise EngagementConflict("not_active", "الارتباط ليس نشطاً ليتم تعليقه.")

    return _execute_suspend(locked, reason=reason)


@transaction.atomic
def resume_engagement(
    *,
    engagement: Engagement,
) -> Engagement:
    """استئناف ارتباط معلق.

    ترتيب القفل: Subscription -> PlatformEmployee -> Engagement -> UserCompanyMembership
    يعيد حساب created_membership: يكون True فقط إذا أنشأ الاستئناف صفاً جديداً؛
    ويكون False إذا وجد صفاً قائماً للزبون ويرقيه لـ manager مع حفظ دوره السابق.
    """
    eng_pk = getattr(engagement, "pk", engagement)

    pre_eng = (
        Engagement.objects.filter(pk=eng_pk)
        .values("tenant_id", "employee_id")
        .first()
    )
    if not pre_eng:
        raise EngagementError("not_found", "الارتباط غير موجود.")

    # 1. قفل اشتراك الخدمة
    subscription = (
        ServiceSubscription.objects.select_for_update()
        .filter(tenant_id=pre_eng["tenant_id"])
        .first()
    )
    if not subscription or subscription.status != ServiceSubscription.Status.ACTIVE:
        raise EngagementError(
            "subscription_not_active",
            "خدمة المتابعة والإدخال غير نشطة لهذه الشركة.",
        )

    # 2. قفل موظف المنصة
    locked_employee = (
        PlatformEmployee.objects.select_for_update()
        .get(pk=pre_eng["employee_id"])
    )
    if locked_employee.status != PlatformEmployee.Status.ACTIVE:
        raise EngagementError("employee_not_active", "موظف عمليات المنصة غير نشط.")

    # 3. قفل الارتباط
    locked = Engagement.objects.select_for_update().get(pk=eng_pk)
    if locked.status == Engagement.Status.REVOKED:
        raise EngagementConflict("already_revoked", "الارتباط ملغى نهائياً ولا يمكن استئنافه.")
    if locked.status != Engagement.Status.SUSPENDED:
        raise EngagementConflict("not_suspended", "الارتباط ليس معلقاً ليتم استئنافه.")

    # 4. التأكد من عدم وجود ارتباط نشط آخر لنفس (الموظف، الشركة)
    existing_active = (
        Engagement.objects.select_for_update()
        .filter(
            employee_id=locked.employee_id,
            tenant_id=locked.tenant_id,
            status=Engagement.Status.ACTIVE,
        )
        .exclude(pk=locked.pk)
        .first()
    )
    if existing_active:
        raise EngagementConflict(
            "already_active",
            "يوجد ارتباط نشط بالفعل لهذا الموظف مع هذه الشركة.",
        )

    # 5. قفل والتعامل مع العضوية
    current_membership = (
        UserCompanyMembership.objects.select_for_update()
        .filter(user_id=locked_employee.user_id, tenant_id=locked.tenant_id)
        .first()
    )

    if current_membership is None:
        new_membership = UserCompanyMembership.objects.create(
            user_id=locked_employee.user_id,
            tenant_id=locked.tenant_id,
            role="manager",
        )
        locked.created_membership = True
        locked.previous_role = ""
        locked.managed_membership = new_membership
    else:
        locked.created_membership = False
        locked.previous_role = current_membership.role
        if current_membership.role != "manager":
            current_membership.role = "manager"
            current_membership.save(update_fields=["role"])
        locked.managed_membership = current_membership

    locked.status = Engagement.Status.ACTIVE
    locked.suspended_at = None
    locked.save(
        update_fields=[
            "status",
            "suspended_at",
            "created_membership",
            "previous_role",
            "managed_membership",
            "updated_at",
        ]
    )

    return locked


@transaction.atomic
def revoke_engagement(
    *,
    engagement: Engagement,
    revoked_by=None,
    reason: str = "",
) -> Engagement:
    """إلغاء ارتباط موظف المنصة نهائياً.

    ترتيب القفل: Subscription -> Engagement -> UserCompanyMembership
    يحذف فقط العضوية الدقيقة المدارة التي أنشأها الارتباط، ويستعيد الدور السابق للعضوية المسبقة دون حذفها.
    """
    eng_pk = getattr(engagement, "pk", engagement)

    # 1. قفل الاشتراك
    pre_eng = Engagement.objects.filter(pk=eng_pk).values("tenant_id").first()
    if pre_eng:
        ServiceSubscription.objects.select_for_update().filter(
            tenant_id=pre_eng["tenant_id"]
        ).first()

    # 2. قفل الارتباط
    locked = Engagement.objects.select_for_update().get(pk=eng_pk)
    if locked.status == Engagement.Status.REVOKED:
        raise EngagementConflict("already_revoked", "الارتباط ملغى سابقاً.")

    return _execute_revoke(locked, revoked_by=revoked_by, reason=reason)


@transaction.atomic
def deactivate_service_subscription(
    *,
    subscription,
    new_status: str = ServiceSubscription.Status.SUSPENDED,
    reason: str = "تعليق/إلغاء اشتراك الخدمة",
) -> ServiceSubscription:
    """إيقاف أو تعليق اشتراك خدمة المتابعة مع تعليق ارتباطاتها النشطة دون حذفها.

    ترتيب القفل: Subscription -> Engagements -> Memberships
    يستدعي _execute_suspend مباشرة على الارتباطات المقفولة لتجنب إعادة طلب الأقفال.
    """
    sub_obj = subscription
    if isinstance(subscription, Tenant):
        sub_obj = getattr(subscription, "service_subscription", None)
    elif hasattr(subscription, "pk") and not isinstance(subscription, ServiceSubscription):
        sub_obj = ServiceSubscription.objects.filter(tenant=subscription).first()

    if not sub_obj:
        raise EngagementError("no_subscription", "لا يوجد اشتراك خدمة لهذه الشركة.")

    if new_status not in (
        ServiceSubscription.Status.SUSPENDED,
        ServiceSubscription.Status.CANCELLED,
    ):
        raise ValueError(f"الحالة المستهدفة يجب أن تكون معلق أو ملغى: {new_status}")

    locked_sub = (
        ServiceSubscription.objects.select_for_update()
        .get(pk=sub_obj.pk)
    )
    locked_sub.status = new_status
    locked_sub.save(update_fields=["status", "updated_at"])

    # قفل وتعليق كافة الارتباطات النشطة لهذه الشركة
    active_engagements = (
        Engagement.objects.select_for_update()
        .filter(tenant_id=locked_sub.tenant_id, status=Engagement.Status.ACTIVE)
        .order_by("pk")
    )
    for eng in active_engagements:
        _execute_suspend(eng, reason=reason)

    return locked_sub


@transaction.atomic
def offboard_platform_employee(
    *,
    employee: PlatformEmployee,
    actor=None,
    reason: str = "إنهاء خدمة موظف المنصة (مغادرة)",
) -> PlatformEmployee:
    """إنهاء خدمة موظف المنصة (مغادرة) بعملية واحدة idempotent.

    ترتيب القفل: PlatformEmployee -> Engagements -> Memberships
    يتجنب إعادة كتابة status/updated_at إذا كان الموظف خارج الخدمة بالفعل،
    مع تنظيف وإلغاء أي ارتباطات غير ملغاة بشكل متسق عبر _execute_revoke.
    """
    emp_pk = getattr(employee, "pk", employee)
    locked_employee = (
        PlatformEmployee.objects.select_for_update()
        .get(pk=emp_pk)
    )

    # 1. تعيين حالة الموظف كخارج الخدمة فقط إذا لم تكن كذلك
    if locked_employee.status != PlatformEmployee.Status.OFFBOARDED:
        locked_employee.status = PlatformEmployee.Status.OFFBOARDED
        locked_employee.save(update_fields=["status", "updated_at"])

    # 2. قفل وإلغاء كافة الارتباطات غير الملغاة
    engagements = (
        Engagement.objects.select_for_update()
        .filter(employee_id=locked_employee.pk)
        .exclude(status=Engagement.Status.REVOKED)
        .order_by("pk")
    )
    for eng in engagements:
        _execute_revoke(
            eng,
            revoked_by=actor,
            reason=reason,
        )

    return locked_employee


# ==============================================================================
# المرحلة الثالثة (م٣): أوامر العمل ومحطاتها وأجلها وتسليمها وتعليقاتها
# ==============================================================================

DEFAULT_WORK_ORDER_SLA_POLICY = {
    "version": 1,
    "sla_hours_by_kind": {
        "data_entry": 24,
        "review": 12,
        "sales": 48,
        "service": 24,
        "inquiry": 4,
        "admin_directive": 8,
    },
    "default_sla_hours": 24,
}

#: خريطة الانتقالات الصريحة لآلة حالات أمر العمل (المحطة ← مجموعة المحطات التالية المسموحة)
WORK_ORDER_TRANSITIONS: dict[str, set[str]] = {
    WorkOrder.Status.RECEIVED: {
        WorkOrder.Status.SCREENING,
    },
    WorkOrder.Status.SCREENING: {
        WorkOrder.Status.DATA_ENTRY,
        WorkOrder.Status.WAITING_CUSTOMER,
    },
    WorkOrder.Status.DATA_ENTRY: {
        WorkOrder.Status.REVIEW,
        WorkOrder.Status.WAITING_CUSTOMER,
    },
    WorkOrder.Status.REVIEW: {
        WorkOrder.Status.APPROVAL,
        WorkOrder.Status.WAITING_CUSTOMER,
    },
    WorkOrder.Status.APPROVAL: {
        WorkOrder.Status.CLOSED,
        WorkOrder.Status.WAITING_CUSTOMER,
    },
    WorkOrder.Status.WAITING_CUSTOMER: {
        WorkOrder.Status.SCREENING,
        WorkOrder.Status.DATA_ENTRY,
        WorkOrder.Status.REVIEW,
        WorkOrder.Status.APPROVAL,
        WorkOrder.Status.CANCELLED,
    },
    WorkOrder.Status.CLOSED: set(),
    WorkOrder.Status.CANCELLED: set(),
}

#: الحالات التي يُسمح منها بالدخول في انتظار العميل
WAITING_CUSTOMER_ENTRY_STATUSES = frozenset({
    WorkOrder.Status.SCREENING,
    WorkOrder.Status.DATA_ENTRY,
    WorkOrder.Status.REVIEW,
    WorkOrder.Status.APPROVAL,
})


def resolve_policy_snapshot_for_work_order(kind: str, custom_policy: dict | None = None) -> dict:
    """استخراج لقطة سياسة الأجل السارية لأمر العمل وقت الإنشاء.

    في م٣: المصدر هو السياسة الافتراضية المعلنة في الوحدة.
    صُمِّم الحقل ليتكامل مع م٥ (PolicyProfile) لاحقاً بتمرير سياسة مخصصة دون حاجة لهجرة جديدة.
    """
    base = custom_policy or DEFAULT_WORK_ORDER_SLA_POLICY
    hours_map = base.get("sla_hours_by_kind", {})
    sla_hours = int(hours_map.get(kind, base.get("default_sla_hours", 24)))
    return {
        "version": base.get("version", 1),
        "source": "default_module_policy" if custom_policy is None else "custom_policy",
        "kind": kind,
        "sla_hours": sla_hours,
        "captured_at": timezone.now().isoformat(),
    }


@transaction.atomic
def create_work_order(
    *,
    tenant: Tenant,
    title: str,
    kind: str = WorkOrder.Kind.DATA_ENTRY,
    source: str = WorkOrder.Source.STAFF,
    description: str = "",
    assignee: PlatformEmployee | None = None,
    received_at=None,
    created_by=None,
    custom_policy: dict | None = None,
) -> WorkOrder:
    """إنشاء أمر عمل جديد مع حفظ لقطة سياسة الأجل فوراً على الصف.

    ترتيب القفل: PlatformEmployee (إن وُجد) -> WorkOrder
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    if not title or not title.strip():
        raise WorkOrderError("title_required", "عنوان أمر العمل إلزامي.")

    if kind not in WorkOrder.Kind.values:
        raise WorkOrderError("invalid_kind", f"نوع أمر العمل غير صالح: {kind}")

    if source not in WorkOrder.Source.values:
        raise WorkOrderError("invalid_source", f"مصدر أمر العمل غير صالح: {source}")

    locked_assignee = None
    if assignee:
        emp_pk = getattr(assignee, "pk", assignee)
        locked_assignee = PlatformEmployee.objects.select_for_update().get(pk=emp_pk)
        if locked_assignee.status != PlatformEmployee.Status.ACTIVE:
            raise WorkOrderError("assignee_not_active", "موظف المنصة المسؤول غير نشط.")

    rec_at = received_at or timezone.now()
    policy_snapshot = resolve_policy_snapshot_for_work_order(kind, custom_policy)
    sla_hours = policy_snapshot.get("sla_hours", 24)
    deadline_at = rec_at + datetime.timedelta(hours=sla_hours)

    return WorkOrder.objects.create(
        tenant=tenant_obj,
        title=title.strip(),
        description=description.strip() if description else "",
        kind=kind,
        source=source,
        assignee=locked_assignee,
        status=WorkOrder.Status.RECEIVED,
        received_at=rec_at,
        policy_snapshot=policy_snapshot,
        deadline_at=deadline_at,
        created_by=created_by,
    )


@transaction.atomic
def assign_work_order(
    *,
    work_order: WorkOrder,
    assignee: PlatformEmployee | None,
) -> WorkOrder:
    """إسناد أمر العمل لمسؤول واحد أو إعادته للطابور.

    ترتيب القفل الصارم: PlatformEmployee -> WorkOrder
    """
    wo_pk = getattr(work_order, "pk", work_order)

    locked_assignee = None
    if assignee is not None:
        emp_pk = getattr(assignee, "pk", assignee)
        # 1. قفل موظف المنصة
        locked_assignee = PlatformEmployee.objects.select_for_update().get(pk=emp_pk)
        if locked_assignee.status != PlatformEmployee.Status.ACTIVE:
            raise WorkOrderError("assignee_not_active", "موظف المنصة المسؤول غير نشط.")

    # 2. قفل أمر العمل
    locked_wo = WorkOrder.objects.select_for_update().get(pk=wo_pk)
    locked_wo.assignee = locked_assignee
    locked_wo.save(update_fields=["assignee", "updated_at"])
    return locked_wo


@transaction.atomic
def transition_work_order_status(
    *,
    work_order: WorkOrder,
    target_status: str,
    now=None,
) -> WorkOrder:
    """نقل حالة أمر العمل وفق آلة الحالات الصارمة.

    ترتيب القفل: WorkOrder
    القواعد:
    1. الانتقال مسموح فقط إذا كان target_status ضمن الحالات التالية لـ current_status.
    2. الدخول إلى waiting_customer يحفظ return_status وطابع waiting_entered_at.
    3. الخروج من waiting_customer:
       - إذا كان إلى cancelled: يجمع ثواني الانتظار ويصفر waiting_entered_at و return_status.
       - إذا كان إلى حالة تشغيل: يجب أن تكون مطابقة تماماً لـ return_status. يجمع ثواني الانتظار،
         ويمدد deadline_at بمقدار الانتظار، ويصفر waiting_entered_at و return_status.
    4. الانتقال إلى approval يسجل approved_at.
    5. الانتقال إلى closed يسجل closed_at.
    """
    wo_pk = getattr(work_order, "pk", work_order)
    current_time = now or timezone.now()

    # قفل أمر العمل
    locked_wo = WorkOrder.objects.select_for_update().get(pk=wo_pk)
    current_status = locked_wo.status

    allowed_next = WORK_ORDER_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_next:
        raise WorkOrderTransitionError(
            "invalid_transition",
            f"الانتقال من {current_status} إلى {target_status} غير مسموح به.",
            status_code=400,
        )

    # معالجة الدخول إلى انتظار العميل
    if target_status == WorkOrder.Status.WAITING_CUSTOMER:
        locked_wo.return_status = current_status
        locked_wo.waiting_entered_at = current_time

    # معالجة الخروج من انتظار العميل
    elif current_status == WorkOrder.Status.WAITING_CUSTOMER:
        elapsed = 0
        if locked_wo.waiting_entered_at:
            if current_time > locked_wo.waiting_entered_at:
                elapsed = int((current_time - locked_wo.waiting_entered_at).total_seconds())
        locked_wo.waiting_seconds_total += elapsed
        locked_wo.waiting_entered_at = None

        if target_status == WorkOrder.Status.CANCELLED:
            locked_wo.return_status = ""
        else:
            # استئناف العمل للحالة السابقة
            if target_status != locked_wo.return_status:
                raise WorkOrderTransitionError(
                    "invalid_return_status",
                    f"لا يمكن استئناف أمر العمل إلى {target_status}؛ حالة العودة المسجلة هي {locked_wo.return_status}.",
                    status_code=400,
                )
            if locked_wo.deadline_at and elapsed > 0:
                locked_wo.deadline_at += datetime.timedelta(seconds=elapsed)
            locked_wo.return_status = ""

    # معالجة الاعتماد
    if target_status == WorkOrder.Status.APPROVAL:
        locked_wo.approved_at = current_time

    # معالجة الإغلاق
    elif target_status == WorkOrder.Status.CLOSED:
        locked_wo.closed_at = current_time

    locked_wo.status = target_status
    locked_wo.save(
        update_fields=[
            "status",
            "return_status",
            "waiting_entered_at",
            "waiting_seconds_total",
            "approved_at",
            "closed_at",
            "deadline_at",
            "updated_at",
        ]
    )
    return locked_wo


@transaction.atomic
def submit_work_order_deliverable(
    *,
    work_order: WorkOrder,
    kind: str = WorkOrderDeliverable.Kind.NOTE,
    content: str = "",
    payload: dict | None = None,
    file_url: str = "",
    submitted_by=None,
) -> WorkOrderDeliverable:
    """تسليم مخرج لأمر العمل مع حفظ لقطة ثابتة غير قابلة للتعديل اللاحق."""
    if kind not in WorkOrderDeliverable.Kind.values:
        raise WorkOrderError("invalid_kind", f"نوع المُسلَّم غير صالح: {kind}")

    payload_copy = copy.deepcopy(payload) if payload else {}
    content_snapshot = {
        "kind": kind,
        "content": content or "",
        "payload": payload_copy,
        "file_url": file_url or "",
        "submitted_at": timezone.now().isoformat(),
        "submitted_by_id": getattr(submitted_by, "pk", None),
    }

    return WorkOrderDeliverable.objects.create(
        tenant=work_order.tenant,
        work_order=work_order,
        kind=kind,
        review_status=WorkOrderDeliverable.ReviewStatus.PENDING,
        content=content or "",
        payload=payload_copy,
        file_url=file_url or "",
        content_snapshot=content_snapshot,
        submitted_by=submitted_by,
    )


@transaction.atomic
def review_work_order_deliverable(
    *,
    deliverable: WorkOrderDeliverable,
    review_status: str,
    reviewed_by,
    rejection_reason: str = "",
) -> WorkOrderDeliverable:
    """مراجعة مُسلَّم أمر العمل (قبول أو رفض مع سبب صريح)."""
    if review_status not in (
        WorkOrderDeliverable.ReviewStatus.APPROVED,
        WorkOrderDeliverable.ReviewStatus.REJECTED,
    ):
        raise WorkOrderError(
            "invalid_review_status",
            f"حالة المراجعة يجب أن تكون مقبول أو مرفوض: {review_status}",
        )

    if review_status == WorkOrderDeliverable.ReviewStatus.REJECTED and not (rejection_reason and rejection_reason.strip()):
        raise WorkOrderError("rejection_reason_required", "سبب الرفض إلزامي عند رفض المُسلَّم.")

    deliv_pk = getattr(deliverable, "pk", deliverable)
    locked_deliv = WorkOrderDeliverable.objects.select_for_update().get(pk=deliv_pk)
    locked_deliv.review_status = review_status
    locked_deliv.reviewed_by = reviewed_by
    locked_deliv.reviewed_at = timezone.now()
    locked_deliv.rejection_reason = (rejection_reason or "").strip()
    locked_deliv.save(
        update_fields=[
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "updated_at",
        ]
    )
    return locked_deliv


@transaction.atomic
def add_work_order_comment(
    *,
    work_order: WorkOrder,
    author,
    content: str,
    visibility: str,
) -> WorkOrderComment:
    """إضافة تعليق أو استفسار على أمر العمل مع التحقق الصارم من حقل visibility."""
    if visibility not in (
        WorkOrderComment.Visibility.INTERNAL,
        WorkOrderComment.Visibility.CLIENT_VISIBLE,
    ):
        raise WorkOrderError(
            "visibility_required",
            f"مستوى الظهور (visibility) إلزامي ويجب أن يكون internal أو client_visible: {visibility}",
        )

    if not content or not content.strip():
        raise WorkOrderError("content_required", "نص التعليق إلزامي.")

    if not author:
        raise WorkOrderError("author_required", "كاتب التعليق إلزامي.")

    return WorkOrderComment.objects.create(
        tenant=work_order.tenant,
        work_order=work_order,
        author=author,
        content=content.strip(),
        visibility=visibility,
    )


def list_work_order_comments(
    *,
    work_order: WorkOrder,
    for_client: bool = False,
):
    """استرجاع تعليقات أمر العمل مع حجب التعليقات الداخلية عن الزبون."""
    qs = WorkOrderComment.objects.filter(work_order=work_order).order_by("created_at")
    if for_client:
        qs = qs.filter(visibility=WorkOrderComment.Visibility.CLIENT_VISIBLE)
    return qs


def calculate_work_order_sla(*, work_order: WorkOrder, now=None) -> dict:
    """حساب تفاصيل الأجل الفعلي وحالة تجاوزه (SLA) لأمر العمل."""
    cur_now = now or timezone.now()
    effective_seconds = work_order.calculate_effective_duration_seconds(now=cur_now)
    policy = work_order.policy_snapshot or {}
    sla_hours = policy.get("sla_hours", 24)
    target_seconds = sla_hours * 3600
    is_overdue = effective_seconds > target_seconds

    waiting_total = work_order.waiting_seconds_total
    current_waiting = work_order.open_waiting_seconds(now=cur_now)

    return {
        "received_at": work_order.received_at,
        "approved_at": work_order.approved_at,
        "waiting_seconds_total": waiting_total,
        "current_waiting_seconds": current_waiting,
        "effective_duration_seconds": effective_seconds,
        "sla_hours": sla_hours,
        "target_seconds": target_seconds,
        "is_overdue": is_overdue,
        "deadline_at": work_order.deadline_at,
    }


# ==============================================================================
# المرحلة الرابعة (م٤): مفاتيح القنوات وقناة الاستقبال وIdempotency واحتساب الفوترة
# ==============================================================================

def hash_integration_token(raw_token: str) -> str:
    """تجزئة الرمز الخام لمفتاح القناة باستخدام SHA-256."""
    if not raw_token or not isinstance(raw_token, str):
        return ""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


@transaction.atomic
def generate_integration_key(
    *,
    tenant: Tenant,
    channel: str = IntegrationKey.Channel.WHATSAPP,
    name: str = "",
    created_by=None,
) -> tuple[IntegrationKey, str]:
    """توليد مفتاح قناة جديد لشركة زبون.

    القواعد:
    1. صف لكل (شركة × قناة). إذا وُجد مفتاح مسبق لنفس القناة والشركة، يُرفع خطأ تعارض.
    2. المفتاح يُخزَّن مهشَّراً فقط (SHA-256)؛ الرمز الخام يظهر مرة واحدة فقط لحظة التوليد.
    3. الخدمة يجب أن تكون نشطة للشركة لتوليد المفتاح.
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)

    if channel not in IntegrationKey.Channel.values:
        raise IntegrationKeyError("invalid_channel", f"قناة الاستقبال غير صالحة: {channel}")

    if not is_service_active(tenant_obj):
        raise IntegrationKeyError(
            "subscription_not_active",
            "خدمة المتابعة والإدخال غير نشطة لهذه الشركة.",
            status_code=403,
        )

    # صفٌّ واحدٌ لكلّ (شركة، قناة) — والفرادةُ **غيرُ مشروطة** فتفرضها MySQL فعلاً،
    # بخلاف `UniqueConstraint(condition=…)` التي تتجاهلها بصمت. ولذلك لا يمكن أن
    # يتعايش صفٌّ مبطَلٌ وآخرُ نشطٌ للقناة نفسِها: **المفتاحُ المبطَل يُعاد إصدارُه على
    # صفِّه** بسرٍّ جديدٍ لا يُنشأ صفٌّ ثانٍ. ولولا ذلك لصارت قناةٌ أُبطل مفتاحُها
    # عاجزةً عن الحصول على مفتاحٍ جديدٍ إلى الأبد.
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_integration_token(raw_token)

    existing = (
        IntegrationKey.objects.select_for_update()
        .filter(tenant=tenant_obj, channel=channel)
        .first()
    )
    if existing:
        if existing.status == IntegrationKey.Status.ACTIVE:
            raise IntegrationKeyConflict(
                "already_exists",
                f"يوجد مفتاح تكامل نشط مسبق لقناة {channel} لهذه الشركة.",
            )

        # إعادةُ الإصدار على الصفّ نفسِه — وأثرُ الإبطال السابق يُحفَظ ولا يُمحى.
        existing.revocation_history = list(existing.revocation_history or []) + [
            {
                "revoked_at": existing.revoked_at.isoformat() if existing.revoked_at else None,
                "revoked_by_id": existing.revoked_by_id,
                "reason": existing.revocation_reason,
            }
        ]
        existing.token_hash = token_hash
        existing.status = IntegrationKey.Status.ACTIVE
        existing.rotated_at = timezone.now()
        existing.revoked_at = None
        existing.revoked_by = None
        existing.revocation_reason = ""
        if name:
            existing.name = name.strip()
        existing.save(
            update_fields=[
                "token_hash",
                "status",
                "rotated_at",
                "revoked_at",
                "revoked_by",
                "revocation_reason",
                "revocation_history",
                "name",
                "updated_at",
            ]
        )
        return existing, raw_token

    # **والقفلُ لا يُغني هنا**: `select_for_update` على صفٍّ غيرِ موجودٍ لا يقفل شيئاً،
    # فإصداران متزامنان لقناةٍ بكرٍ يمرّان معاً ويصطدمان عند الكتابة. القيدُ في القاعدة
    # هو الحارسُ الحقيقيّ، وواجبُ الخدمة أن تترجم اصطدامَه تعارضاً مفهوماً لا خطأَ ٥٠٠.
    try:
        with transaction.atomic():
            key = IntegrationKey.objects.create(
                tenant=tenant_obj,
                channel=channel,
                token_hash=token_hash,
                status=IntegrationKey.Status.ACTIVE,
                name=name.strip() if name else "",
            )
    except IntegrityError:
        raise IntegrationKeyConflict(
            "already_exists",
            f"يوجد مفتاح تكامل نشط مسبق لقناة {channel} لهذه الشركة.",
        )

    return key, raw_token


@transaction.atomic
def rotate_integration_key(
    *,
    key: IntegrationKey,
    rotated_by=None,
) -> tuple[IntegrationKey, str]:
    """تدوير مفتاح القناة: توليد رمز خام جديد وإبطال القديم فوراً.

    ترتيب القفل: IntegrationKey
    يقبل الجديد ويرفض القديم؛ الرمز الخام الجديد يظهر مرة واحدة فقط.
    """
    key_pk = getattr(key, "pk", key)
    locked_key = IntegrationKey.objects.select_for_update().get(pk=key_pk)

    # **المبطَلُ لا يُدوَّر**: التدويرُ كان يقلب الحالةَ إلى نشطٍ ويمسح `revoked_at`
    # و`revoked_by` و`revocation_reason` — فيُحيي مفتاحاً أُبطل لأنّه تسرّب **ويمحو
    # سببَ إبطاله**، وهو نقضٌ لما تَعِد به الدالّةُ المجاورة: «الصفُّ لا يُحذف لضمان
    # أثر المراجعة». وإعادةُ الإصدار بابُها `generate_integration_key` وهي تحفظ الأثر.
    if locked_key.status == IntegrationKey.Status.REVOKED:
        raise IntegrationKeyError(
            "key_revoked",
            "المفتاح مبطل ولا يُدوَّر — أصدِر مفتاحاً جديداً لهذه القناة.",
        )

    new_raw_token = secrets.token_urlsafe(32)
    new_hash = hash_integration_token(new_raw_token)

    locked_key.token_hash = new_hash
    locked_key.rotated_at = timezone.now()
    locked_key.save(
        update_fields=["token_hash", "rotated_at", "updated_at"]
    )

    return locked_key, new_raw_token


@transaction.atomic
def revoke_integration_key(
    *,
    key: IntegrationKey,
    revoked_by=None,
    reason: str = "",
) -> IntegrationKey:
    """إبطال مفتاح القناة نهائياً.

    ترتيب القفل: IntegrationKey
    الصف لا يُحذف لضمان أثر المراجعة والمساءلة.
    """
    key_pk = getattr(key, "pk", key)
    locked_key = IntegrationKey.objects.select_for_update().get(pk=key_pk)

    if locked_key.status == IntegrationKey.Status.REVOKED:
        raise IntegrationKeyError("already_revoked", "مفتاح التكامل مبطل مسبقاً.")

    locked_key.status = IntegrationKey.Status.REVOKED
    locked_key.revoked_at = timezone.now()
    locked_key.revoked_by = revoked_by
    locked_key.revocation_reason = (reason or "").strip()[:2000]
    locked_key.save(
        update_fields=[
            "status",
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "updated_at",
        ]
    )

    return locked_key


def authenticate_integration_key(raw_token: str) -> tuple[IntegrationKey | None, str]:
    """مصادقة الرمز الخام لمفتاح القناة والتحقق من حالته.

    يعيد (المفتاح, "ok") أو (None, سبب_الرفض).
    """
    if not raw_token or not isinstance(raw_token, str):
        return None, "missing"

    token_hash = hash_integration_token(raw_token)
    key = (
        IntegrationKey.objects.select_related("tenant")
        .filter(token_hash=token_hash)
        .first()
    )

    if not key:
        return None, "invalid"

    if key.status == IntegrationKey.Status.REVOKED:
        return None, "revoked"

    if key.status != IntegrationKey.Status.ACTIVE:
        return None, "inactive"

    return key, "ok"


@transaction.atomic
def receive_channel_work_order(
    *,
    key: IntegrationKey,
    title: str,
    external_ref: str,
    description: str = "",
    kind: str = WorkOrder.Kind.DATA_ENTRY,
    attachment_ids: list[int] | None = None,
    intake_payload: dict | None = None,
    custom_policy: dict | None = None,
) -> tuple[WorkOrder, bool]:
    """استقبال وقبول أمر عمل من قناة التكامل واحتساب العملية المفوترة تحت قفل.

    ترتيب القفل الصارم: ServiceSubscription -> WorkOrder
    القواعد:
    1. الشركة تُستنتج حصراً من المفتاح (key.tenant).
    2. فرادة (tenant, channel, external_ref) تمنع التكرار (idempotency):
       إعادة إرسال نفس المرجع الخارجي تُعيد أمر العمل نفسه دون إنشاء جديد،
       ودون احتساب عملية ثانية.
    3. احتساب العملية يزيد consumed_quota تحت قفل وفي نفس المعاملة الذرية
       فقط عند إنشاء أمر عمل جديد.
    """
    clean_ref = str(external_ref or "").strip()
    if not clean_ref:
        raise WorkOrderError("external_ref_required", "حقل المرجع الخارجي (external_ref) إلزامي.")

    clean_title = str(title or "").strip()
    if not clean_title:
        clean_title = f"طلب من قناة {key.get_channel_display()} ({clean_ref})"

    if kind not in WorkOrder.Kind.values:
        raise WorkOrderError("invalid_kind", f"نوع أمر العمل غير صالح: {kind}")

    # 1. قفل اشتراك الخدمة للتأكد من نشاطه وحماية عداد العمليات
    subscription = (
        ServiceSubscription.objects.select_for_update()
        .filter(tenant_id=key.tenant_id)
        .first()
    )
    if not subscription or subscription.status != ServiceSubscription.Status.ACTIVE:
        raise PlatformOpsError(
            "subscription_not_active",
            "خدمة المتابعة والإدخال غير نشطة لهذه الشركة.",
            status_code=403,
        )

    # 2. فحص idempotency تحت قفل الاشتراك لتجنب التكرار المتزامن
    existing_wo = WorkOrder.objects.filter(
        tenant_id=key.tenant_id,
        channel=key.channel,
        external_ref=clean_ref,
    ).first()

    if existing_wo:
        # إعادة نفس أمر العمل دون احتساب عملية ثانية
        return existing_wo, False

    # 3. احتساب العملية المفوترة بزيادة العداد تحت القفل
    subscription.consumed_quota += 1
    subscription.save(update_fields=["consumed_quota", "updated_at"])

    # 4. إنشاء أمر العمل الجديد
    rec_at = timezone.now()
    policy_snapshot = resolve_policy_snapshot_for_work_order(kind, custom_policy)
    sla_hours = policy_snapshot.get("sla_hours", 24)
    deadline_at = rec_at + datetime.timedelta(hours=sla_hours)

    work_order = WorkOrder.objects.create(
        tenant=key.tenant,
        title=clean_title,
        description=description.strip() if description else "",
        kind=kind,
        source=WorkOrder.Source.CHANNEL,
        channel=key.channel,
        external_ref=clean_ref,
        integration_key=key,
        status=WorkOrder.Status.RECEIVED,
        received_at=rec_at,
        policy_snapshot=policy_snapshot,
        deadline_at=deadline_at,
        intake_payload=intake_payload or {},
        attachment_ids=attachment_ids or [],
    )

    # تحديث وقت آخر استخدام للمفتاح
    key.last_used_at = rec_at
    key.save(update_fields=["last_used_at"])

    return work_order, True
