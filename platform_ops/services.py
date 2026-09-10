"""خدمات عمليات المنصة (المراحل الأولى والثانية والثالثة والرابعة: الأساس ودورة الارتباط وأوامر العمل وقناة الاستقبال).

ترتيب الأقفال الصارم لمنع التعارضات والـ Deadlocks على MySQL:
IntegrationKey -> ServiceSubscription -> PlatformEmployee -> Engagement -> WorkOrder
-> WorkOrderDeliverable -> UserCompanyMembership
ملاحظة: لا يُستعمل select_related مع select_for_update لتجنب قفل جداول غير مقصودة.
"""
import calendar
import copy
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.date_ranges import filter_local_date_range
from tenants.models import Tenant, UserCompanyMembership

from .models import (
    AgentGrantedMembership,
    Engagement,
    IntegrationKey,
    PerformanceSnapshot,
    PlatformEmployee,
    PolicyProfile,
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

    # معالجة الإلغاء
    elif target_status == WorkOrder.Status.CANCELLED:
        locked_wo.cancelled_at = current_time

    locked_wo.status = target_status
    locked_wo.save(
        update_fields=[
            "status",
            "return_status",
            "waiting_entered_at",
            "waiting_seconds_total",
            "approved_at",
            "closed_at",
            "cancelled_at",
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


# ==============================================================================
# المرحلة الخامسة (م٥): المقاييس الستة، ملفات السياسات، الدرجة المركبة، واللقطات الشهرية
# ==============================================================================

# المحاور الخمسة الرسمية للتقييم
AXIS_QUALITY = "quality"                    # محور الجودة (نسبة القبول من أول مراجعة)
AXIS_SLA_COMPLIANCE = "sla_compliance"      # محور الالتزام بالأجل
AXIS_PRODUCTIVITY = "productivity"          # محور الإنتاجية والـKPI
AXIS_SPEED_EFFICIENCY = "speed_efficiency"  # محور الكفاءة وسرعة الإنجاز
AXIS_SALES_VALUE = "sales_value"            # محور قيمة المبيعات المعالجة

ALL_PERFORMANCE_AXES = (
    AXIS_QUALITY,
    AXIS_SLA_COMPLIANCE,
    AXIS_PRODUCTIVITY,
    AXIS_SPEED_EFFICIENCY,
    AXIS_SALES_VALUE,
)

DEFAULT_AXIS_WEIGHTS: dict[str, Decimal] = {
    AXIS_QUALITY: Decimal("30.00"),
    AXIS_SLA_COMPLIANCE: Decimal("25.00"),
    AXIS_PRODUCTIVITY: Decimal("20.00"),
    AXIS_SPEED_EFFICIENCY: Decimal("15.00"),
    AXIS_SALES_VALUE: Decimal("10.00"),
}

# المقاييس الستة — قائمة مغلقة ولا سابع
METRIC_FIRST_TIME_APPROVAL = "first_time_approval_rate"  # نسبة القبول من أول مراجعة
METRIC_SLA_COMPLIANCE = "sla_compliance_rate"            # الالتزام بالأجل
METRIC_COMPLETED_WORK_VOLUME = "completed_work_volume"    # الإنتاجية المنجزة
METRIC_REWORK_RATE = "rework_rate"                        # معدل إعادة العمل (تشخيصي منفصل لا يخصم)
METRIC_PROCESSED_SALES_VALUE = "processed_sales_value"    # قيمة مبيعات عالجها (مؤشر عرض لا استحقاق)
METRIC_AVERAGE_HANDLING_TIME = "average_handling_time"    # متوسط سرعة الإنجاز

ALL_SIX_METRICS = (
    METRIC_FIRST_TIME_APPROVAL,
    METRIC_SLA_COMPLIANCE,
    METRIC_COMPLETED_WORK_VOLUME,
    METRIC_REWORK_RATE,
    METRIC_PROCESSED_SALES_VALUE,
    METRIC_AVERAGE_HANDLING_TIME,
)


def redistribute_axis_weights(
    raw_weights: dict[str, Decimal | float | int | str],
    applicable_axes: set[str],
) -> dict[str, Decimal]:
    """إعادة توزيع الأوزان على المحاور المنطبقة بالتناسب ليكون المجموع 100.00% بالضبط.

    القاعدة:
    - المحور غير المنطبق يُسقط ويعاد توزيع وزنه على الباقي.
    - المجموع يبقى 100% بالضبط دون أي كسور تقريب ضائعة؛ يُضاف فرق التقريب للمحور الأكبر وزناً.
    """
    # **محورٌ منطبقٌ غائبٌ عن أوزان السياسة يأخذ وزنَه الافتراضيَّ لا صفراً**: كان
    # `axis in raw_weights` يُسقطه من التوزيع فيبقى «منطبقاً» بوزنٍ صفريّ — المجموعُ
    # يبقى ١٠٠ فيمرّ الاختبارُ المفروض، والتفصيلُ يعرض محوراً منطبقاً لا يساهم بشيء.
    applicable = [axis for axis in ALL_PERFORMANCE_AXES if axis in applicable_axes]
    if not applicable:
        return {}

    def _weight_of(axis: str) -> Decimal:
        raw = raw_weights.get(axis, DEFAULT_AXIS_WEIGHTS.get(axis, Decimal("0.00")))
        try:
            return Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            return DEFAULT_AXIS_WEIGHTS.get(axis, Decimal("0.00"))

    weights_dec = {axis: _weight_of(axis) for axis in applicable}
    total_w = sum(weights_dec.values())

    if total_w <= Decimal("0.00"):
        n = Decimal(len(applicable))
        base = (Decimal("100.00") / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        res = {axis: base for axis in applicable}
        diff = Decimal("100.00") - sum(res.values())
        if diff:
            res[applicable[0]] += diff
        return res

    result: dict[str, Decimal] = {}
    for axis in applicable:
        w_norm = (weights_dec[axis] / total_w * Decimal("100.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        result[axis] = w_norm

    diff = Decimal("100.00") - sum(result.values())
    if diff != Decimal("0.00"):
        max_axis = max(result, key=lambda k: (result[k], k))
        result[max_axis] += diff

    return result


def resolve_policy_profile_for_employee(employee: PlatformEmployee) -> PolicyProfile | None:
    """استرجاع ملف السياسة النشط لتخصص موظف المنصة."""
    if not employee or not employee.specialty:
        return None
    return PolicyProfile.objects.filter(
        specialty=employee.specialty,
        is_active=True,
    ).first()


def get_default_policy_dict(specialty: str = "") -> dict:
    """الحصول على قاموس السياسة الافتراضية للمنصة عند غياب ملف مخصص."""
    return {
        "specialty": specialty,
        "name": "السياسة الافتراضية للمنصة",
        "weights": {k: float(v) for k, v in DEFAULT_AXIS_WEIGHTS.items()},
        "targets": {
            "capacity_target": 100,
            "sales_target": None,
            "quality_target_pct": 95,
            "sla_target_pct": 95,
        },
        "sla_hours_by_kind": copy.deepcopy(DEFAULT_WORK_ORDER_SLA_POLICY.get("sla_hours_by_kind", {})),
        "min_sample_size": 5,
        "default_sla_hours": 24,
    }


#: مفاتيحُ القيمة الماليّة المقبولةُ في تقرير المُسلَّم المنظَّم.
SALES_VALUE_PAYLOAD_KEYS = ("sales_value", "total_sales", "invoice_total", "deal_value", "amount")


def _extract_work_order_sales_value(work_order: WorkOrder) -> Decimal:
    """«قيمةُ مبيعاتٍ عالجها» — **من مُسلَّمٍ اعتُمد، لا من حمولة الزبون**.

    كانت الدالّةُ تقرأ `intake_payload` أوّلاً، وهو JSON يكتبه المرسِلُ عبر القناة.
    ومنذ م٤ صار `amount` **مسموحاً** في الحمولة عن قصد، لأنّ الفاتورةَ تحمله بطبيعتها
    وردُّها كان يُبطل القناة. فاجتماعُ القرارين يفتح ثغرةً حقيقيّة: **حاملُ مفتاح
    القناة يرفع درجةَ موظّفٍ بكتابة رقمٍ أكبر** — ومقياسُ أداءٍ يمليه الطرفُ المقيَّسُ
    لصالحه ليس مقياساً.

    والمصدرُ هنا مُسلَّماتُ الموظّف التي **راجعها غيرُه واعتمدها** (`approved`): رقمٌ
    كتبه موظّفُنا ووقّع عليه مراجعٌ ثانٍ. وهذا يوافق المواصفة: «مؤشّرُ عرضٍ لا استحقاق»،
    و«كلُّ عمليّةٍ تبقى داخل مبيعات الشركة ومحاسبتها» — لا في حمولةٍ خارجيّة.
    """
    total = Decimal("0.00")
    for deliv in work_order.deliverables.all():
        if deliv.review_status != WorkOrderDeliverable.ReviewStatus.APPROVED:
            continue
        payload = deliv.payload or {}
        if not isinstance(payload, dict):
            continue
        # قيمةٌ واحدةٌ لكلّ مُسلَّم (أوّلُ مفتاحٍ يحمل رقماً موجباً)، **ومجموعُها** عبر
        # المُسلَّمات — لا أوّلُ قيمةٍ ثمّ توقُّف، وإلا خالف الرقمُ اسمَه «مجموع».
        for key in SALES_VALUE_PAYLOAD_KEYS:
            val = payload.get(key)
            if val is None:
                continue
            try:
                dec = Decimal(str(val))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if dec > 0:
                total += dec
                break
    return total


def calculate_employee_performance(
    *,
    employee: PlatformEmployee,
    period_year: int | None = None,
    period_month: int | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    policy_dict: dict | None = None,
) -> dict:
    """حساب أداء موظف المنصة عبر المقاييس الستة والمحاور الخمسة والدرجة المركبة.

    القواعد الصارمة (م٥):
    1. الاستعلام العابر للشركات مشروع ومحصور بالشركات المشتقة من الارتباطات (Engagement) فقط.
    2. العرض والدخول لا يُعدّان عملاً إطلاقاً؛ الإنجاز يُحسب فقط لأوامر العمل المعتمدة (approved_at).
    3. الإنشاء لا يدخل الأداء إلا بعد الاعتماد (لا عند التسليم).
    4. الإلغاء (cancelled) لا يعاقب آلياً بل يظهر معدل إعادة عمل منفصلاً كمعيار تشخيصي.
    5. الجودة اسمها الصادق «نسبة القبول من أول مراجعة» وتُعرض بمقام معلن وحجم عينة.
    6. الرقم المالي اسمه «قيمة مبيعات عالجها» كمؤشر عرض لا استحقاق.
    7. العينة الناقصة (< min_sample_size) تُخرج الموظف من الترتيب وتُعيد حالة 'insufficient_data'
       مع composite_score=None صراحة وليس رقماً مضللاً.
    8. المحور غير المنطبق يُسقط ويُعاد توزيع وزنه بالتناسب مع بقاء المجموع 100% بالضبط.
    9. الفلترة الزمنية عبر core.date_ranges ولا وجود لـ __date إطلاقاً.
    """
    # 1. تحديد النطاق الزمني عبر date_from و date_to
    if period_year is not None and period_month is not None:
        start_date = datetime.date(period_year, period_month, 1)
        _, last_day = calendar.monthrange(period_year, period_month)
        end_date = datetime.date(period_year, period_month, last_day)
    else:
        start_date = date_from
        end_date = date_to

    # 2. الشركات تُشتق حصراً من الارتباطات (Engagement)
    #
    # **وبلا فلترِ حالة، عن قصد**: هذا قياسُ ماضٍ لا بوّابةُ وصول. عملٌ أنجزه الموظّفُ
    # في شركةٍ انتهى ارتباطُه بها اليومَ يبقى عملاً أنجزه، وإسقاطُه يُفقد الشهرَ الملتقَط
    # نصفَه. أمّا **الوصولُ** فمحروسٌ بالارتباط النشط وحدَه في `WorkOrderViewSet`.
    engaged_tenant_ids = list(
        Engagement.objects.filter(employee=employee).values_list("tenant_id", flat=True)
    )

    # أوامر العمل للموظف ضمن شركات ارتباطاته المشروعة فقط
    base_wo_qs = WorkOrder.objects.filter(
        assignee=employee,
        tenant_id__in=engaged_tenant_ids,
    )

    # أوامر العمل المعتمدة فعلياً (الإنشاء والتسليم غير المعتمد لا يدخلان في الأداء)
    approved_wo_qs = base_wo_qs.filter(
        status__in=[WorkOrder.Status.APPROVAL, WorkOrder.Status.CLOSED],
        approved_at__isnull=False,
    )
    if start_date or end_date:
        approved_wo_qs = filter_local_date_range(
            approved_wo_qs, "approved_at", date_from=start_date, date_to=end_date
        )

    # أوامر العمل الملغاة (لمعدل إعادة العمل المنفصل)
    # **بـ`cancelled_at` لا `updated_at`**: الثاني `auto_now`، فلمسةٌ لاحقةٌ لصفٍّ ملغىً
    # تنقله بين الشهور ويتغيّر معدّلُ إعادة العمل لشهرٍ التُقطت لقطتُه — واللقطةُ يُفترَض
    # أنّها مجمَّدة. وبه أيضاً يصير طرفا الكسر على ساعتَي **حدثٍ** لا ساعةِ حدثٍ وساعةِ تعديل.
    cancelled_wo_qs = base_wo_qs.filter(
        status=WorkOrder.Status.CANCELLED, cancelled_at__isnull=False
    )
    if start_date or end_date:
        cancelled_wo_qs = filter_local_date_range(
            cancelled_wo_qs, "cancelled_at", date_from=start_date, date_to=end_date
        )

    # `prefetch_related` لا `select_related`: المُسلَّماتُ علاقةٌ عكسيّةٌ متعدّدة،
    # وبدونها يُصدِر حسابُ القيمة الماليّة استعلاماً لكلّ أمرِ عمل.
    completed_orders = list(approved_wo_qs.prefetch_related("deliverables"))
    sample_size = len(completed_orders)
    cancelled_count = cancelled_wo_qs.count()
    total_processed = sample_size + cancelled_count

    # 3. إعداد السياسة والمستهدفات
    if policy_dict is None:
        p_profile = resolve_policy_profile_for_employee(employee)
        if p_profile:
            policy_dict = {
                "specialty": p_profile.specialty,
                "name": p_profile.name,
                "weights": p_profile.weights or {k: float(v) for k, v in DEFAULT_AXIS_WEIGHTS.items()},
                "targets": p_profile.targets or {},
                "sla_hours_by_kind": p_profile.sla_hours_by_kind or {},
                "min_sample_size": p_profile.min_sample_size,
            }
        else:
            policy_dict = get_default_policy_dict(employee.specialty)

    min_sample_size = int(policy_dict.get("min_sample_size", 5))
    raw_weights = policy_dict.get("weights") or {k: float(v) for k, v in DEFAULT_AXIS_WEIGHTS.items()}
    targets = policy_dict.get("targets") or {}

    # 4. حساب المقاييس الستة
    # مقياس 1: نسبة القبول من أول مراجعة (First-Time Approval Rate)
    # أمر العمل معتمد من أول مراجعة إذا لم يُرفض أي من مُسلَّماته
    order_ids = [wo.id for wo in completed_orders]
    rejected_order_ids = set(
        WorkOrderDeliverable.objects.filter(
            work_order_id__in=order_ids,
            review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
        ).values_list("work_order_id", flat=True)
    )
    first_time_approved_count = len([wo for wo in completed_orders if wo.id not in rejected_order_ids])
    if sample_size > 0:
        first_time_rate = (Decimal(first_time_approved_count) / Decimal(sample_size) * Decimal("100.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        first_time_rate = Decimal("0.00")

    metric_first_time = {
        "name": "نسبة القبول من أول مراجعة",
        "key": METRIC_FIRST_TIME_APPROVAL,
        "numerator": first_time_approved_count,
        "denominator": sample_size,
        "sample_size": sample_size,
        "rate": first_time_rate,
        "rate_pct": float(first_time_rate),
    }

    # مقياس 2: الالتزام بالأجل (SLA Compliance Rate)
    sla_met_count = 0
    total_effective_seconds = 0
    total_sla_target_seconds = 0
    for wo in completed_orders:
        sla_info = calculate_work_order_sla(work_order=wo)
        if not sla_info["is_overdue"]:
            sla_met_count += 1
        total_effective_seconds += sla_info["effective_duration_seconds"]
        total_sla_target_seconds += sla_info["target_seconds"]

    if sample_size > 0:
        sla_compliance_rate = (Decimal(sla_met_count) / Decimal(sample_size) * Decimal("100.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        sla_compliance_rate = Decimal("0.00")

    metric_sla = {
        "name": "الالتزام بالأجل",
        "key": METRIC_SLA_COMPLIANCE,
        "numerator": sla_met_count,
        "denominator": sample_size,
        "sample_size": sample_size,
        "rate": sla_compliance_rate,
        "rate_pct": float(sla_compliance_rate),
    }

    # مقياس 3: الإنتاجية المنجزة (Completed Work Volume)
    # مستهدف السعة من الموظف أو السياسة
    capacity_target_val = targets.get("capacity_target") or employee.capacity_target or Decimal("100.00")
    try:
        capacity_target_dec = Decimal(str(capacity_target_val))
    except Exception:
        capacity_target_dec = Decimal("100.00")

    if capacity_target_dec > Decimal("0.00"):
        volume_rate = min(
            Decimal("100.00"),
            (Decimal(sample_size) / capacity_target_dec * Decimal("100.00")),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        volume_rate = Decimal("100.00")

    metric_volume = {
        "name": "الإنتاجية المنجزة",
        "key": METRIC_COMPLETED_WORK_VOLUME,
        "numerator": sample_size,
        # المقامُ المعلَن هو القاسمُ نفسُه: `int()` كان يعرض ٢٠ ويقسم على ٢٠٫٥٠
        "denominator": float(capacity_target_dec),
        "sample_size": sample_size,
        "rate": volume_rate,
        "rate_pct": float(volume_rate),
    }

    # مقياس 4: معدل إعادة العمل (Rework Rate) — تشخيصي منفصل لا يُخصم من الدرجة
    if total_processed > 0:
        rework_rate = (Decimal(cancelled_count) / Decimal(total_processed) * Decimal("100.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        rework_rate = Decimal("0.00")

    metric_rework = {
        "name": "معدل إعادة العمل",
        "key": METRIC_REWORK_RATE,
        "numerator": cancelled_count,
        "denominator": total_processed,
        "sample_size": total_processed,
        "rate": rework_rate,
        "rate_pct": float(rework_rate),
        "is_diagnostic_only": True,
    }

    # مقياس 5: قيمة مبيعات عالجها (Processed Sales Value) — مؤشر عرض لا استحقاق
    total_sales_value = Decimal("0.00")
    sales_orders_count = 0
    for wo in completed_orders:
        s_val = _extract_work_order_sales_value(wo)
        if s_val > Decimal("0.00") or wo.kind == WorkOrder.Kind.SALES:
            sales_orders_count += 1
            total_sales_value += s_val

    sales_target_val = targets.get("sales_target")
    sales_target_dec = None
    if sales_target_val is not None:
        try:
            sales_target_dec = Decimal(str(sales_target_val))
        except Exception:
            sales_target_dec = None

    if sales_target_dec and sales_target_dec > Decimal("0.00"):
        sales_score = min(
            Decimal("100.00"),
            (total_sales_value / sales_target_dec * Decimal("100.00")),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        sales_score = Decimal("100.00") if total_sales_value > Decimal("0.00") else Decimal("0.00")

    metric_sales = {
        "name": "قيمة مبيعات عالجها",
        "key": METRIC_PROCESSED_SALES_VALUE,
        "numerator": float(total_sales_value),
        "denominator": float(sales_target_dec) if sales_target_dec else None,
        "sample_size": sales_orders_count,
        "total_value": total_sales_value,
        "is_display_only": True,
    }

    # مقياس 6: متوسط سرعة الإنجاز (Average Handling Time)
    if sample_size > 0:
        avg_handling_seconds = int(total_effective_seconds / sample_size)
    else:
        avg_handling_seconds = 0

    if total_sla_target_seconds > 0 and total_effective_seconds > 0:
        # الكفاءة: إذا كان الزمن الفعلي أقل من المستهدف فالكفاءة 100%
        speed_efficiency_score = min(
            Decimal("100.00"),
            (Decimal(total_sla_target_seconds) / Decimal(total_effective_seconds) * Decimal("100.00")),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif sample_size > 0:
        speed_efficiency_score = Decimal("100.00")
    else:
        speed_efficiency_score = Decimal("0.00")

    metric_speed = {
        "name": "متوسط سرعة الإنجاز",
        "key": METRIC_AVERAGE_HANDLING_TIME,
        "numerator": total_effective_seconds,
        "denominator": sample_size,
        "sample_size": sample_size,
        "average_seconds": avg_handling_seconds,
        "efficiency_score": speed_efficiency_score,
    }

    all_metrics = {
        METRIC_FIRST_TIME_APPROVAL: metric_first_time,
        METRIC_SLA_COMPLIANCE: metric_sla,
        METRIC_COMPLETED_WORK_VOLUME: metric_volume,
        METRIC_REWORK_RATE: metric_rework,
        METRIC_PROCESSED_SALES_VALUE: metric_sales,
        METRIC_AVERAGE_HANDLING_TIME: metric_speed,
    }

    # 5. تحديد المحاور المنطبقة وإعادة توزيع الأوزان
    # قاعدة: محور المبيعات يسقط إذا لم يكن للموظف مبيعات ولم يُحدد مستهدف مبيعات في السياسة
    applicable_axes: set[str] = set()
    axis_raw_scores: dict[str, Decimal] = {}

    # محور الجودة
    applicable_axes.add(AXIS_QUALITY)
    axis_raw_scores[AXIS_QUALITY] = first_time_rate

    # محور الالتزام بالأجل
    applicable_axes.add(AXIS_SLA_COMPLIANCE)
    axis_raw_scores[AXIS_SLA_COMPLIANCE] = sla_compliance_rate

    # محور الإنتاجية والـKPI
    applicable_axes.add(AXIS_PRODUCTIVITY)
    axis_raw_scores[AXIS_PRODUCTIVITY] = volume_rate

    # محور الكفاءة والسرعة
    applicable_axes.add(AXIS_SPEED_EFFICIENCY)
    axis_raw_scores[AXIS_SPEED_EFFICIENCY] = speed_efficiency_score

    # محور المبيعات
    # **السياسةُ تقرّر لا قائمةٌ مثبَّتةٌ في الكود**: تخصّصاتٌ محشورةٌ هنا تعني أنّ
    # إضافةَ تخصّصِ مبيعاتٍ جديدٍ تلزمها هجرةُ كود — بينما `PolicyProfile` وُجد ليحمل
    # هذا القرارَ لكلّ تخصّص. فالمحورُ ينطبق إن أعلنت السياسةُ له هدفاً أو وزناً موجباً،
    # أو إن كان للموظّف عملُ مبيعاتٍ فعليٌّ في الفترة.
    declared_sales_weight = Decimal(str(raw_weights.get(AXIS_SALES_VALUE, 0) or 0))
    has_sales_target = sales_target_dec is not None and sales_target_dec > Decimal("0.00")
    if has_sales_target or declared_sales_weight > Decimal("0.00") or sales_orders_count > 0:
        applicable_axes.add(AXIS_SALES_VALUE)
        axis_raw_scores[AXIS_SALES_VALUE] = sales_score

    # إذا كانت السياسة تحدد أوزاناً صفرية لمحور معين، يُسقط المحور
    for axis, w in raw_weights.items():
        try:
            declared = Decimal(str(w))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if declared <= Decimal("0.00") and axis in applicable_axes:
            applicable_axes.remove(axis)

    # إعادة توزيع الأوزان لضمان أن المجموع 100.00% بالضبط
    redistributed_weights = redistribute_axis_weights(raw_weights, applicable_axes)

    axes_breakdown = {}
    weighted_sum = Decimal("0.00")
    for axis in ALL_PERFORMANCE_AXES:
        is_app = axis in applicable_axes
        w = redistributed_weights.get(axis, Decimal("0.00"))
        sc = axis_raw_scores.get(axis, Decimal("0.00"))
        contrib = (w * sc / Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if is_app:
            weighted_sum += contrib
        axes_breakdown[axis] = {
            "applicable": is_app,
            "weight": w,
            "weight_pct": float(w),
            "score": sc,
            "score_pct": float(sc),
            "weighted_contribution": contrib,
        }

    # 6. فحص كفاية العينة وتحديد الحالة والدرجة المركبة
    if sample_size < min_sample_size:
        status = PerformanceSnapshot.Status.INSUFFICIENT_DATA
        composite_score = None
        status_message = "بيانات غير كافية"
    else:
        status = PerformanceSnapshot.Status.CALCULATED
        composite_score = min(Decimal("100.00"), max(Decimal("0.00"), weighted_sum)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        status_message = "محسوبة"

    return {
        "status": status,
        "status_message": status_message,
        "composite_score": composite_score,
        "sample_size": sample_size,
        "min_sample_size": min_sample_size,
        "rework_rate": rework_rate,
        "processed_sales_value": total_sales_value,
        "metrics": all_metrics,
        "axes": axes_breakdown,
        "weights_sum": sum(redistributed_weights.values()),
        "policy_used": policy_dict,
    }


def rank_employees_performance(
    *,
    employees: list[PlatformEmployee] | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> list[dict]:
    """ترتيب موظفي المنصة وفق أدائهم مع استبعاد العينات الناقصة من الترتيب الرقمي.

    القاعدة الصارمة:
    - العينة الناقصة (< min_sample_size) تُخرج الموظف من الترتيب (rank = None).
    - الموظفون الذين لديهم بيانات كافية يرتبون تصاعدياً برقم ترتيب رسمي (1, 2, 3...).
    """
    if employees is None:
        employees = list(
            PlatformEmployee.objects.select_related("user").filter(
                status=PlatformEmployee.Status.ACTIVE
            )
        )

    calculated_list = []
    insufficient_list = []

    for emp in employees:
        perf = calculate_employee_performance(
            employee=emp,
            period_year=period_year,
            period_month=period_month,
            date_from=date_from,
            date_to=date_to,
        )
        entry = {
            "employee_id": emp.id,
            "employee_name": str(emp.user),
            "specialty": emp.specialty,
            "performance": perf,
        }
        if perf["status"] == PerformanceSnapshot.Status.CALCULATED and perf["composite_score"] is not None:
            calculated_list.append(entry)
        else:
            entry["rank"] = None
            insufficient_list.append(entry)

    # ترتيب المحسوبين تنازلياً حسب الدرجة المركبة
    calculated_list.sort(key=lambda x: x["performance"]["composite_score"], reverse=True)
    for index, entry in enumerate(calculated_list, start=1):
        entry["rank"] = index

    return calculated_list + insufficient_list


def _make_json_safe(obj):
    """تحويل أي كائن Decimal أو كائنات غير قابلة للتسلسل إلى أنواع قياسية لـ JSON."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    return obj


@transaction.atomic
def capture_performance_snapshot(
    *,
    employee: PlatformEmployee,
    period_year: int,
    period_month: int,
    captured_by=None,
    force_refresh: bool = False,
) -> PerformanceSnapshot:
    """التقاط لقطة أداء شهرية لموظف منصة (عملية idempotent).

    ترتيب القفل الصارم: PlatformEmployee
    القواعد:
    1. القفل على PlatformEmployee لمنع إنشاء لقطتين متزامنتين لنفس الموظف والشهر.
    2. فرادة (employee, period_year, period_month) تضمن عدم وجود تكرار.
    3. إذا وُجدت لقطة سابقة ولم يُطلب force_refresh: تُعاد اللقطة السابقة كما هي (Idempotent).
    4. اللقطة تحفظ نسخة مجمدة من السياسة والأوزان السارية وقت الالتقاط (policy_snapshot).
       تعديل PolicyProfile لاحقاً لا يغير شهراً تم التقاطه.
    """
    emp_pk = getattr(employee, "pk", employee)
    # قفل موظف المنصة وفق ترتيب الأقفال المعلن
    locked_emp = PlatformEmployee.objects.select_for_update().get(pk=emp_pk)

    existing = PerformanceSnapshot.objects.filter(
        employee=locked_emp,
        period_year=period_year,
        period_month=period_month,
    ).first()

    if existing and not force_refresh:
        return existing

    # استخراج ملف السياسة النشط
    p_profile = resolve_policy_profile_for_employee(locked_emp)
    if p_profile:
        policy_dict = {
            "specialty": p_profile.specialty,
            "name": p_profile.name,
            "weights": p_profile.weights or {k: float(v) for k, v in DEFAULT_AXIS_WEIGHTS.items()},
            "targets": p_profile.targets or {},
            "sla_hours_by_kind": p_profile.sla_hours_by_kind or {},
            "min_sample_size": p_profile.min_sample_size,
        }
    else:
        policy_dict = get_default_policy_dict(locked_emp.specialty)

    # حساب الأداء للشهر المعني
    perf_result = calculate_employee_performance(
        employee=locked_emp,
        period_year=period_year,
        period_month=period_month,
        policy_dict=policy_dict,
    )

    now = timezone.now()
    if existing and force_refresh:
        existing.status = perf_result["status"]
        existing.composite_score = perf_result["composite_score"]
        existing.sample_size = perf_result["sample_size"]
        existing.policy_profile = p_profile
        existing.policy_snapshot = _make_json_safe(policy_dict)
        existing.metrics_data = _make_json_safe(perf_result["metrics"])
        existing.axes_data = _make_json_safe(perf_result["axes"])
        existing.rework_rate = perf_result["rework_rate"]
        existing.processed_sales_value = perf_result["processed_sales_value"]
        existing.captured_by = captured_by
        existing.captured_at = now
        existing.save()
        return existing

    snapshot = PerformanceSnapshot.objects.create(
        employee=locked_emp,
        period_year=period_year,
        period_month=period_month,
        status=perf_result["status"],
        composite_score=perf_result["composite_score"],
        sample_size=perf_result["sample_size"],
        policy_profile=p_profile,
        policy_snapshot=_make_json_safe(policy_dict),
        metrics_data=_make_json_safe(perf_result["metrics"]),
        axes_data=_make_json_safe(perf_result["axes"]),
        rework_rate=perf_result["rework_rate"],
        processed_sales_value=perf_result["processed_sales_value"],
        captured_by=captured_by,
        captured_at=now,
    )
    return snapshot

