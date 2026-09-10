"""خدمات عمليات المنصة (المراحل الأولى والثانية والثالثة والرابعة والخامسة والسادسة والسابعة).

ترتيب الأقفال الصارم لمنع التعارضات والـ Deadlocks على MySQL:
IntegrationKey -> ServiceSubscription -> PlatformEmployee -> Engagement -> WorkOrder
-> WorkOrderDeliverable -> UserCompanyMembership -> DailyRating
ملاحظة: لا يُستعمل select_related مع select_for_update لتجنب قفل جداول غير مقصودة.
"""
import calendar
import copy
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import secrets

from django.db import IntegrityError, models, transaction
from django.db.models import Avg, Max
from django.utils import timezone

from core.date_ranges import filter_local_date_range
from core.activity import describe_activity_changes
from core.models import ActivityLog
from core.terminology import term
from hr.models import UserDevice
from tenants.models import Tenant, UserCompanyMembership

from .models import (
    AgentGrantedMembership,
    DailyRating,
    DailyRatingToken,
    Engagement,
    IntegrationKey,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
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


class DailyRatingError(PlatformOpsError):
    """خطأ في التقييم اليومي."""

    pass


class DailyRatingConflict(DailyRatingError):
    """تعارض في التقييم اليومي (مثل محاولة تعديل ثانية)."""

    def __init__(self, code: str, detail: str, status_code: int = 400):
        super().__init__(code, detail, status_code=status_code)


class RatingTokenNotFound(PlatformOpsError):
    """الرمز غير موجود أو غير صالح => 404 (طابق سابقة docshare)."""

    def __init__(self, detail: str = "الرابط غير صالح أو غير موجود."):
        super().__init__("token_not_found", detail, status_code=404)


class RatingTokenGone(PlatformOpsError):
    """الرمز انتهت صلاحيته أو أُبطل => 410 (طابق سابقة docshare)."""

    def __init__(self, detail: str = "انتهت صلاحية هذا الرابط."):
        super().__init__("token_expired", detail, status_code=410)


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

    breached_deadline = False

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
        breached_deadline = bool(
            locked_wo.deadline_at and current_time > locked_wo.deadline_at
        )

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

    if locked_wo.assignee:
        log_platform_activity(
            employee=locked_wo.assignee,
            tenant=locked_wo.tenant,
            action=PlatformActivityLog.Action.WORK_ORDER_TRANSITION,
            entity_type="work_order",
            entity_id=locked_wo.pk,
            description=f"تغيير حالة أمر العمل '{locked_wo.title}' إلى {locked_wo.get_status_display()}",
            details={"from_status": current_status, "to_status": target_status},
            created_at=current_time,
        )

    # **إشعارُ «تجاوزُ أجل» عند الاعتماد**: هذه اللحظةُ التي يُحسَم فيها الأجلُ
    # نهائيّاً (الأجلُ من `received_at` إلى `approved_at`)، فيُطلَق مرّةً واحدةً
    # لا في كلّ قراءةٍ للوحة.
    if breached_deadline:
        notify_sla_breach(work_order=locked_wo)

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

    deliv = WorkOrderDeliverable.objects.create(
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

    if submitted_by:
        emp = getattr(submitted_by, "platform_employee", None)
        if not emp:
            emp = PlatformEmployee.objects.filter(user=submitted_by).first()
        if emp:
            log_platform_activity(
                employee=emp,
                tenant=work_order.tenant,
                action=PlatformActivityLog.Action.DELIVERABLE_SUBMIT,
                entity_type="deliverable",
                entity_id=deliv.pk,
                description=f"تسليم مُسلَّم لأمر العمل '{work_order.title}'",
                details={"work_order_id": work_order.pk, "kind": kind},
            )

    return deliv


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

    if reviewed_by:
        emp = getattr(reviewed_by, "platform_employee", None)
        if not emp:
            emp = PlatformEmployee.objects.filter(user=reviewed_by).first()
        if emp:
            log_platform_activity(
                employee=emp,
                tenant=locked_deliv.tenant,
                action=PlatformActivityLog.Action.DELIVERABLE_REVIEW,
                entity_type="deliverable",
                entity_id=locked_deliv.pk,
                description=f"مراجعة مُسلَّم لأمر العمل: {locked_deliv.get_review_status_display()}",
                details={"work_order_id": locked_deliv.work_order_id, "review_status": review_status},
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

    comment = WorkOrderComment.objects.create(
        tenant=work_order.tenant,
        work_order=work_order,
        author=author,
        content=content.strip(),
        visibility=visibility,
    )

    if author:
        emp = getattr(author, "platform_employee", None)
        if not emp:
            emp = PlatformEmployee.objects.filter(user=author).first()
        if emp:
            log_platform_activity(
                employee=emp,
                tenant=work_order.tenant,
                action=PlatformActivityLog.Action.COMMENT_ADDED,
                entity_type="comment",
                entity_id=comment.pk,
                description=f"إضافة تعليق [{visibility}] على أمر العمل '{work_order.title}'",
                details={"work_order_id": work_order.pk, "visibility": visibility},
            )

    return comment


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
    # `<=` لا `<`: لحظةَ العبور يكون المستهلَكُ **مساوياً** للحدّ قبل الزيادة
    # (٢ من ٢)، فشرطُ `<` يُفوّت العبورَ نفسَه فلا يُطلَق الإشعارُ أبداً.
    was_within_quota = (
        subscription.included_quota > 0
        and subscription.consumed_quota <= subscription.included_quota
    )
    subscription.consumed_quota += 1
    subscription.save(update_fields=["consumed_quota", "updated_at"])

    # **وهنا يُولَد إشعارُ «تجاوزُ باقة»**: صندوقُ الإشعارات كان بلا مُنتِجٍ واحدٍ في
    # الكود — دالّةُ الإنشاء لا يستدعيها إلا الاختبار، فالصندوقُ فارغٌ أبداً في
    # الإنتاج. وهذه هي اللحظةُ الوحيدةُ التي يُعرَف فيها التجاوزُ يقيناً: عبورُ
    # الحدّ، مرّةً واحدةً، لا في كلّ طلبٍ بعده.
    if was_within_quota and subscription.consumed_quota > subscription.included_quota:
        notify_quota_exceeded(subscription=subscription)

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

    log_platform_activity(
        employee=locked_emp,
        tenant=None,
        action=PlatformActivityLog.Action.SNAPSHOT_CAPTURED,
        entity_type="performance_snapshot",
        entity_id=snapshot.pk,
        description=f"التقاط لقطة أداء لشهر {period_year}/{period_month}",
        details={
            "period_year": period_year,
            "period_month": period_month,
            "status": snapshot.status,
            "composite_score": str(snapshot.composite_score) if snapshot.composite_score is not None else None,
        },
        created_at=now,
    )

    return snapshot


# ==============================================================================
# خدمات المرحلة السادسة (م٦): الإشعارات، النشاط العابر، اللوحة وشريط التدخل
# ==============================================================================

ANOMALY_CRITICAL_DELAY = "critical_delay"
ANOMALY_OVERLOADED = "overloaded"
ANOMALY_ABSENT_WITH_WORK = "absent_with_work"
ANOMALY_LOW_SCORE = "low_score"


def log_platform_activity(
    *,
    employee: PlatformEmployee,
    action: str,
    description: str = "",
    tenant: Tenant | None = None,
    entity_type: str = "",
    entity_id: str | int = "",
    details: dict | None = None,
    created_at: datetime.datetime | None = None,
) -> PlatformActivityLog:
    """تسجيل نشاط موظف المنصة عابراً كل الشركات في جدول واحد (القصة رقم ١٣ - م٦).

    - بنية خاصة بوحدة عمليات المنصة وليست توسيعاً لـ ActivityLog؛
      لأن ActivityLog لا يتسع لحدث بلا شركة وفهارسه تبدأ بـ tenant.
    - مفهرس زمنياً للقراءة العابرة للشركات: (employee, -created_at) و(-created_at).
    """
    if details is None:
        details = {}
    return PlatformActivityLog.objects.create(
        employee=employee,
        tenant=tenant,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else "",
        description=description,
        details=details,
        created_at=created_at or timezone.now(),
    )


def create_platform_notification(
    *,
    recipient,
    notification_type: str,
    title: str,
    message: str = "",
    tenant: Tenant | None = None,
    data: dict | None = None,
) -> PlatformNotification:
    """إنشاء إشعار منصي لموظف أو مدير عمليات المنصة (م٦).

    - الفلترة على الخادم حصراً: المستخدم لا يستقبل إلا إشعاراته.
    - أنواع مغلقة: sla_breach, low_score, quota_exceeded.
    """
    if data is None:
        data = {}
    return PlatformNotification.objects.create(
        recipient=recipient,
        tenant=tenant,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
    )


def _platform_operations_managers():
    """مديرو المنصّة — مستقبِلو إشعارات ما يخصّ المنصّةَ كلَّها."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(is_superuser=True, is_active=True)


def notify_quota_exceeded(*, subscription: ServiceSubscription) -> int:
    """إشعارُ تجاوزِ الباقة لمديري المنصّة — مرّةً عند العبور لا في كلّ عمليّة."""
    created = 0
    for manager in _platform_operations_managers():
        create_platform_notification(
            recipient=manager,
            notification_type=PlatformNotification.NotificationType.QUOTA_EXCEEDED,
            title=f"تجاوزت {subscription.tenant.CompanyName} باقتها",
            message=(
                f"المستهلَك {subscription.consumed_quota} من {subscription.included_quota} "
                "عمليّةً مشمولة."
            ),
            tenant=subscription.tenant,
            data={
                "subscription_id": subscription.pk,
                "consumed_quota": subscription.consumed_quota,
                "included_quota": subscription.included_quota,
            },
        )
        created += 1
    return created


def notify_sla_breach(*, work_order: WorkOrder) -> int:
    """إشعارُ تجاوزِ الأجل — للمسؤول عن الأمر ولمديري المنصّة."""
    recipients = []
    if work_order.assignee_id:
        assignee_user = (
            PlatformEmployee.objects.select_related("user")
            .filter(pk=work_order.assignee_id)
            .first()
        )
        if assignee_user and assignee_user.user:
            recipients.append(assignee_user.user)
    recipients.extend(_platform_operations_managers())

    seen = set()
    created = 0
    for user in recipients:
        if user.pk in seen:
            continue
        seen.add(user.pk)
        create_platform_notification(
            recipient=user,
            notification_type=PlatformNotification.NotificationType.SLA_BREACH,
            title=f"تجاوزَ الأجلَ: {work_order.title}",
            message=(
                f"اعتُمد أمرُ العمل بعد أجله لدى {work_order.tenant.CompanyName}."
            ),
            tenant=work_order.tenant,
            data={"work_order_id": work_order.pk, "deadline_at": work_order.deadline_at.isoformat()
                  if work_order.deadline_at else None},
        )
        created += 1
    return created


def get_employee_last_active(target) -> datetime.datetime | None:
    """قراءة طابع آخر ظهور (last_active_at) للمستخدم من hr.models.UserDevice.

    - لا نبضة جديدة: UserDevice.last_active_at يُكتب أصلاً على كل طلب مصادق بنافذة 5 دقائق.
    - طابع وقت حقيقي وليس مصباحاً أخضر.
    """
    if not target:
        return None
    user = getattr(target, "user", target)
    return (
        UserDevice.objects.filter(user=user)
        .order_by("-last_active_at")
        .values_list("last_active_at", flat=True)
        .first()
    )


def is_recently_active(target, now=None, threshold_minutes: int = 15) -> bool:
    """فحص عتبة النشاط (15 دقيقة).

    يقبل target كـ datetime أو PlatformEmployee أو User.
    إذا كان آخر ظهور خلال 15 دقيقة = نشط مؤخراً.
    أكثر من 15 دقيقة = غير نشط.
    """
    if target is None:
        return False
    if isinstance(target, datetime.datetime):
        last_active_at = target
    elif hasattr(target, "user"):
        last_active_at = get_employee_last_active(target.user)
    elif hasattr(target, "pk"):
        last_active_at = get_employee_last_active(target)
    else:
        last_active_at = target

    if not last_active_at:
        return False
    current_time = now or timezone.now()
    if last_active_at > current_time:
        return True
    return (current_time - last_active_at).total_seconds() <= threshold_minutes * 60


def detect_platform_anomalies(
    *,
    employee: PlatformEmployee | None = None,
    last_active_by_user: dict | None = None,
    tenant_ids: list[int] | None = None,
    now=None,
) -> list[dict]:
    """كشف الشذوذ في مركز قيادة العمليات (أربعة أنواع لا أكثر — م٦).

    1. تأخر حرج (critical_delay): أمر عمل تجاوز الأجل النهائي (deadline_at < now) وهو قيد التشغيل.
    2. حمل زائد (overloaded): حجم العمل النشط يتجاوز مستهدف السعة الموزون (capacity_target).
    3. موظف غائب وعليه عمل (absent_with_work): آخر ظهور > 15 دقيقة ولديه أوامر عمل معلقة.
    4. درجة هابطة (low_score): الدرجة المركبة أقل من 70%.

    الترتيب: الأسوأ أولاً.
    """
    current_time = now or timezone.now()
    anomalies = []

    # 1. الموظفون المفحوصون
    emp_qs = PlatformEmployee.objects.select_related("user").filter(
        status=PlatformEmployee.Status.ACTIVE
    )
    if employee:
        emp_qs = emp_qs.filter(pk=employee.pk)

    active_employees = list(emp_qs)

    # 2. فحص أوامر العمل المتأخرة (تأخر حرج)
    wo_qs = WorkOrder.objects.select_related("tenant", "assignee__user").filter(
        status__in=[
            WorkOrder.Status.RECEIVED,
            WorkOrder.Status.SCREENING,
            WorkOrder.Status.DATA_ENTRY,
            WorkOrder.Status.REVIEW,
        ],
        deadline_at__isnull=False,
        deadline_at__lt=current_time,
    )
    if employee:
        wo_qs = wo_qs.filter(assignee=employee)
    if tenant_ids is not None:
        wo_qs = wo_qs.filter(tenant_id__in=tenant_ids)

    for wo in wo_qs:
        delay_seconds = int((current_time - wo.deadline_at).total_seconds())
        delay_hours = round(delay_seconds / 3600, 1)
        anomalies.append({
            "type": ANOMALY_CRITICAL_DELAY,
            "anomaly_type": ANOMALY_CRITICAL_DELAY,
            "type_display": "تأخر حرج",
            "severity": "critical",
            "severity_weight": 100,
            "sort_metric": delay_seconds,
            "employee_id": wo.assignee_id,
            "employee_name": wo.assignee.user.username if wo.assignee and wo.assignee.user else "غير مسند",
            "tenant_id": wo.tenant_id,
            "tenant_name": wo.tenant.CompanyName if wo.tenant else "",
            "work_order_id": wo.pk,
            "work_order_title": wo.title,
            "message": f"أمر العمل '{wo.title}' متأخر عن موعده بـ {delay_hours} ساعة",
            "created_at": wo.deadline_at.isoformat(),
        })

    # 3. فحص الموظفين
    for emp in active_employees:
        emp_work_orders = WorkOrder.objects.filter(
            assignee=emp,
            status__in=[
                WorkOrder.Status.RECEIVED,
                WorkOrder.Status.SCREENING,
                WorkOrder.Status.DATA_ENTRY,
                WorkOrder.Status.REVIEW,
                WorkOrder.Status.WAITING_CUSTOMER,
            ],
        )
        if tenant_ids is not None:
            emp_work_orders = emp_work_orders.filter(tenant_id__in=tenant_ids)

        active_count = emp_work_orders.count()

        # أ) حمل زائد: موزون بهدف سعة التخصص
        if emp.capacity_target and emp.capacity_target > Decimal("0.00"):
            if Decimal(active_count) > emp.capacity_target:
                overload_diff = float(Decimal(active_count) - emp.capacity_target)
                anomalies.append({
                    "type": ANOMALY_OVERLOADED,
                    "anomaly_type": ANOMALY_OVERLOADED,
                    "type_display": "حمل زائد",
                    "severity": "high",
                    "severity_weight": 80,
                    "sort_metric": overload_diff,
                    "employee_id": emp.pk,
                    "employee_name": emp.user.username if emp.user else "",
                    "tenant_id": None,
                    "tenant_name": None,
                    "work_order_id": None,
                    "work_order_title": None,
                    "message": f"الموظف يحمل {active_count} أمر عمل وتجاوز سعته المستهدفة ({emp.capacity_target})",
                    "created_at": current_time.isoformat(),
                })

        # ب) موظف غائب وعليه عمل (عتبة 15 دقيقة)
        # الخريطةُ المحسوبةُ مرّةً واحدةً تُمرَّر من اللوحة؛ وبلاها يُستعلَم لموظّفٍ واحد.
        if last_active_by_user is not None:
            last_active = last_active_by_user.get(emp.user_id)
        else:
            last_active = get_employee_last_active(emp.user)
        active_recently = is_recently_active(last_active, now=current_time, threshold_minutes=15)
        if not active_recently and active_count > 0:
            if last_active:
                absent_minutes = int((current_time - last_active).total_seconds() / 60)
                absent_text = f"غائب منذ {absent_minutes} دقيقة"
            else:
                absent_minutes = 999999
                absent_text = "لم يسجل دخولاً بعد"

            anomalies.append({
                "type": ANOMALY_ABSENT_WITH_WORK,
                "anomaly_type": ANOMALY_ABSENT_WITH_WORK,
                "type_display": "موظف غائب وعليه عمل",
                "severity": "high",
                "severity_weight": 85,
                "sort_metric": absent_minutes,
                "employee_id": emp.pk,
                "employee_name": emp.user.username if emp.user else "",
                "tenant_id": None,
                "tenant_name": None,
                "work_order_id": None,
                "work_order_title": None,
                "message": f"الموظف {absent_text} ولديه {active_count} أمر عمل معلق",
                "created_at": current_time.isoformat(),
            })

        # ج) درجة هابطة (أداء أقل من 70%)
        perf = calculate_employee_performance(employee=emp)
        score = perf.get("composite_score")
        if score is None:
            latest_snapshot = (
                PerformanceSnapshot.objects.filter(employee=emp)
                .order_by("-period_year", "-period_month")
                .first()
            )
            if latest_snapshot and latest_snapshot.composite_score is not None:
                score = latest_snapshot.composite_score

        if score is not None and score < Decimal("70.00"):
            score_deficit = float(Decimal("70.00") - score)
            anomalies.append({
                "type": ANOMALY_LOW_SCORE,
                "anomaly_type": ANOMALY_LOW_SCORE,
                "type_display": "درجة هابطة",
                "severity": "medium" if score >= Decimal("50.00") else "high",
                "severity_weight": 60 if score >= Decimal("50.00") else 75,
                "sort_metric": score_deficit,
                "employee_id": emp.pk,
                "employee_name": emp.user.username if emp.user else "",
                "tenant_id": None,
                "tenant_name": None,
                "work_order_id": None,
                "work_order_title": None,
                "message": f"درجة الأداء المركبة هبطت إلى {score}% (الحد المستهدف 70%)",
                "created_at": current_time.isoformat(),
            })

    # ترتيب الأسوأ أولاً: severity_weight تنازلياً ثم sort_metric تنازلياً
    anomalies.sort(key=lambda a: (a["severity_weight"], a["sort_metric"]), reverse=True)
    return anomalies


def get_platform_dashboard_summary(*, user, now=None) -> dict:
    """توليد ملخص اللوحة التفاعلية لمركز قيادة العمليات (م٦).

    القواعد:
    - الوحدة الموظف لا الشركة (المبدل موظف/شركة متاح).
    - الترتيب الأسوأ أولاً.
    - شريط التدخل: شذوذ فقط (أربعة أنواع لا أكثر).
    - عزل الشركات: موظف المنصة يرى شركات ارتباطاته النشطة فقط، والمدير يرى الكل.
    - استخراج آخر ظهور من hr.models.UserDevice (طابع وقت، لا مصباح، عتبة 15 دقيقة).
    - لا نقاط لموظفي المنصة.
    """
    from .permissions import IsPlatformOperationsManager

    current_time = now or timezone.now()
    is_manager = IsPlatformOperationsManager().has_permission(
        type("DummyRequest", (), {"user": user})(), None
    ) if hasattr(user, "is_authenticated") and user.is_authenticated else False

    # تحديد نطاق الموظفين والشركات
    if is_manager:
        emp_qs = PlatformEmployee.objects.select_related("user").filter(
            status=PlatformEmployee.Status.ACTIVE
        )
        engaged_tenant_ids = None
    else:
        emp_qs = PlatformEmployee.objects.select_related("user").filter(
            user=user,
            status=PlatformEmployee.Status.ACTIVE,
        )
        engaged_tenant_ids = list(
            Engagement.objects.filter(
                employee__user=user,
                status=Engagement.Status.ACTIVE,
            ).values_list("tenant_id", flat=True)
        )

    active_employees = list(emp_qs)

    # **آخرُ ظهورٍ للجميع باستعلامٍ واحد**: `get_employee_last_active` تُصدِر استعلاماً
    # لكلّ موظّف، وهذه شاشةٌ تُفتَح على عشرات البطاقات. والدرسُ مسجَّلٌ في هذا المستودع
    # (٣٥٠١ استعلامٍ صارت ٣): الدمجُ في SQL لا في بايثون.
    last_active_by_user = dict(
        UserDevice.objects.filter(user_id__in=[e.user_id for e in active_employees])
        .values_list("user_id")
        .annotate(latest=Max("last_active_at"))
    )

    # 1. بطاقات الموظفين
    employee_cards = []
    for emp in active_employees:
        wo_qs = WorkOrder.objects.filter(
            assignee=emp,
            status__in=[
                WorkOrder.Status.RECEIVED,
                WorkOrder.Status.SCREENING,
                WorkOrder.Status.DATA_ENTRY,
                WorkOrder.Status.REVIEW,
                WorkOrder.Status.APPROVAL,
                WorkOrder.Status.WAITING_CUSTOMER,
            ],
        )
        if engaged_tenant_ids is not None:
            wo_qs = wo_qs.filter(tenant_id__in=engaged_tenant_ids)

        active_count = wo_qs.count()
        overdue_count = wo_qs.filter(
            deadline_at__isnull=False,
            deadline_at__lt=current_time,
        ).exclude(status__in=[WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED, WorkOrder.Status.APPROVAL]).count()

        perf = calculate_employee_performance(employee=emp)
        last_active = last_active_by_user.get(emp.user_id)
        active_recently = is_recently_active(last_active, now=current_time, threshold_minutes=15)

        emp_anomalies = detect_platform_anomalies(
            employee=emp,
            tenant_ids=engaged_tenant_ids,
            now=current_time,
            last_active_by_user=last_active_by_user,
        )

        engagements = Engagement.objects.filter(
            employee=emp,
            status=Engagement.Status.ACTIVE,
        ).select_related("tenant")
        if engaged_tenant_ids is not None:
            engagements = engagements.filter(tenant_id__in=engaged_tenant_ids)

        companies_list = [
            {"id": eng.tenant_id, "name": eng.tenant.CompanyName}
            for eng in engagements
        ]

        score_val = perf.get("composite_score")
        # **«بيانات غير كافية» ليست مئةً**: كان الغيابُ يُترجَم `100.0` في مفتاح
        # الترتيب، فيبدو موظّفٌ لا بياناتِ له **كاملَ الدرجة** ويُدفَع إلى ذيل
        # «الأسوأ أوّلاً» حيث لا يراه أحد — وهو عكسُ ما تقوله المواصفة: العيّنةُ
        # الناقصةُ **تُخرجه من الترتيب** لا تضعه على قمّته. فيُفصَل المرتَّبون عن
        # غيرِ المرتَّبين بدل تلفيقِ رقمٍ لهم.
        has_score = score_val is not None
        numeric_score = float(score_val) if has_score else 0.0

        employee_cards.append({
            "id": emp.pk,
            "user_id": emp.user_id,
            "name": emp.user.get_full_name() or emp.user.username,
            "username": emp.user.username,
            "email": emp.user.email,
            "specialty": emp.specialty,
            "capacity_target": float(emp.capacity_target),
            "status": emp.status,
            "active_work_orders_count": active_count,
            "overdue_work_orders_count": overdue_count,
            "last_active_at": last_active.isoformat() if last_active else None,
            "is_recently_active": active_recently,
            "is_active_now": active_recently,
            "performance": {
                "status": perf.get("status"),
                "status_message": perf.get("status_message"),
                "composite_score": float(score_val) if score_val is not None else None,
                "sample_size": perf.get("sample_size", 0),
                "min_sample_size": perf.get("min_sample_size", 5),
                "rework_rate": float(perf.get("rework_rate", 0)),
                "processed_sales_value": float(perf.get("processed_sales_value", 0)),
            },
            "anomalies_count": len(emp_anomalies),
            "anomalies": emp_anomalies,
            "engaged_tenants_count": len(companies_list),
            "companies": companies_list,
            "is_ranked": has_score,
            "_sort_key": (
                -len(emp_anomalies),
                -overdue_count,
                # المرتَّبون أوّلاً (الأسوأُ درجةً قبل الأفضل)، ثمّ غيرُ المرتَّبين
                # مجموعين في ذيلٍ واحدٍ بلا رقمٍ ملفَّق.
                0 if has_score else 1,
                numeric_score,
            ),
        })

    # ترتيب الموظفين: الأسوأ أولاً
    employee_cards.sort(key=lambda c: c["_sort_key"])
    for c in employee_cards:
        c.pop("_sort_key", None)

    # 2. بطاقات الشركات (لمبدل العرض)
    if is_manager:
        tenant_qs = Tenant.objects.all()
    else:
        tenant_qs = Tenant.objects.filter(pk__in=engaged_tenant_ids or [])

    company_cards = []
    subscriptions = {
        sub.tenant_id: sub
        for sub in ServiceSubscription.objects.filter(tenant__in=tenant_qs)
    }
    active_engagements = {
        eng.tenant_id: eng
        for eng in Engagement.objects.filter(
            tenant__in=tenant_qs,
            status=Engagement.Status.ACTIVE,
        ).select_related("employee__user")
    }

    for t in tenant_qs:
        t_active_wo = WorkOrder.objects.filter(
            tenant=t,
            status__in=[
                WorkOrder.Status.RECEIVED,
                WorkOrder.Status.SCREENING,
                WorkOrder.Status.DATA_ENTRY,
                WorkOrder.Status.REVIEW,
                WorkOrder.Status.APPROVAL,
                WorkOrder.Status.WAITING_CUSTOMER,
            ],
        )
        t_active_count = t_active_wo.count()
        t_overdue_count = t_active_wo.filter(
            deadline_at__isnull=False,
            deadline_at__lt=current_time,
        ).exclude(status__in=[WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED, WorkOrder.Status.APPROVAL]).count()

        sub = subscriptions.get(t.pk)
        eng = active_engagements.get(t.pk)

        assigned_emp = None
        if eng and eng.employee and eng.employee.user:
            assigned_emp = {
                "id": eng.employee_id,
                "name": eng.employee.user.get_full_name() or eng.employee.user.username,
                "specialty": eng.employee.specialty,
            }

        company_cards.append({
            "id": t.pk,
            "name": t.CompanyName,
            "subscription_status": sub.status if sub else "unknown",
            "subscription_plan": sub.plan if sub else "",
            "active_work_orders_count": t_active_count,
            "overdue_work_orders_count": t_overdue_count,
            "assigned_employee": assigned_emp,
            "_sort_key": (-t_overdue_count, -t_active_count),
        })

    company_cards.sort(key=lambda c: c["_sort_key"])
    for c in company_cards:
        c.pop("_sort_key", None)

    # 3. شريط التدخل: جميع الشذوذ
    all_anomalies = detect_platform_anomalies(
        tenant_ids=engaged_tenant_ids,
        now=current_time,
        last_active_by_user=last_active_by_user,
    )

    return {
        "view_unit": "employee",
        "employees": employee_cards,
        "companies": company_cards,
        "anomalies": all_anomalies,
        "total_anomalies_count": len(all_anomalies),
        "generated_at": current_time.isoformat(),
    }


# ==============================================================================
# المرحلة السابعة (م٧): التقييم اليومي وتبويب «من يمسك دفاتري» ودرجتا الصحة
# ==============================================================================

#: عمرُ الرابط اليوميّ — رقمُ المواصفة نفسُه، ومصدرٌ واحدٌ يستطيع اختبارٌ قياسَه.
RATING_TOKEN_LIFETIME = datetime.timedelta(hours=72)

#: حدُّ العيّنة الأدنى قبل أن تخصم التقييماتُ من «صحّة الخدمة» (§١٠).
RATING_HEALTH_MIN_SAMPLE = 5

#: سقفُ صفوفِ سجلّ نشاطِ الوكيل في تبويب «من يمسك دفاتري» — تحرٍّ لا تفريغُ جدول.
MY_BOOKS_ACTIVITY_PAGE_CAP = 100


def has_employee_worked_on_date(tenant, employee, service_date: datetime.date) -> bool:
    """التحقق من أن موظف المنصة عمل فعلياً في الشركة في هذا اليوم.

    شرط حاسم: لا يُنشأ تقييم ليوم لم يعمل فيه الموظف فعلياً في تلك الشركة
    (أوامر عمل تحركت ذلك اليوم)، وليس مجرد وجود ارتباط.
    تُفحص حركات أوامر العمل ومُسلَّماتها وسجل النشاط الزمني المحلي الآمن (دون __date).
    """
    tenant_id = getattr(tenant, "pk", tenant)
    employee_id = getattr(employee, "pk", employee)

    # 1. نشاط مسجل في PlatformActivityLog لهذا الموظف والشركة في تاريخ الخدمة
    act_qs = PlatformActivityLog.objects.filter(
        employee_id=employee_id,
        tenant_id=tenant_id,
        action__in=[
            PlatformActivityLog.Action.WORK_ORDER_TRANSITION,
            PlatformActivityLog.Action.DELIVERABLE_SUBMIT,
            PlatformActivityLog.Action.DELIVERABLE_REVIEW,
            PlatformActivityLog.Action.COMMENT_ADDED,
        ],
    )
    if filter_local_date_range(act_qs, "created_at", date_from=service_date, date_to=service_date).exists():
        return True

    # 2. حركات أوامر عمل مباشرة في هذا اليوم
    #
    # **`received_at` و`cancelled_at` ليسا عملاً**: الأوّلُ يُختم لحظةَ إرسالِ
    # **الزبون** عبر القناة (م٤)، فرفعُه مستنداً يصنع «يومَ عملٍ» لموظّفٍ لم يلمس
    # شيئاً ثمّ يُطلب منه تقييمُه. والثاني إلغاءٌ قد لا يكون من الموظف أصلاً.
    wo_qs = WorkOrder.objects.filter(assignee_id=employee_id, tenant_id=tenant_id)
    for field in ("approved_at", "closed_at", "waiting_entered_at"):
        if filter_local_date_range(wo_qs, field, date_from=service_date, date_to=service_date).exists():
            return True

    # 3. تسليم أو مراجعة مُسلَّم في هذا اليوم
    deliv_qs = WorkOrderDeliverable.objects.filter(
        tenant_id=tenant_id,
        work_order__assignee_id=employee_id,
    )
    if filter_local_date_range(deliv_qs, "created_at", date_from=service_date, date_to=service_date).exists():
        return True
    if filter_local_date_range(deliv_qs, "reviewed_at", date_from=service_date, date_to=service_date).exists():
        return True

    return False


@transaction.atomic
def generate_daily_rating_token(
    *,
    tenant: Tenant,
    employee: PlatformEmployee,
    service_date: datetime.date,
) -> tuple[DailyRatingToken, str]:
    """توليد رابط يومي مهشر صالح 72 ساعة لتقييم يوم عمل.

    - يتحقق من العمل الفعلي في هذا اليوم؛ ويرفض إذا لم يعمل.
    - الرمز الخام لا يُحفظ في القاعدة إطلاقاً، بل يُخزن مهشراً (SHA-256).
    - يعيد (كائن الرمز في القاعدة، الرمز الخام للرابط).
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    emp_obj = employee if isinstance(employee, PlatformEmployee) else PlatformEmployee.objects.get(pk=employee)

    if not has_employee_worked_on_date(tenant_obj, emp_obj, service_date):
        raise DailyRatingError(
            "no_work_on_date",
            "لا يمكن إنشاء تقييم ليوم لم يعمل فيه الموظف في هذه الشركة.",
            status_code=400,
        )

    now = timezone.now()

    # **إبطالُ ما سبق لليوم نفسِه**: رابطان حيّان لنفس (شركة، موظف، يوم) يعني
    # نافذتَي كتابةٍ على شهادةٍ واحدة. وهذا هو الكاتبُ الوحيدُ لـ`revoked_at`،
    # فالحقلُ الذي لا يكتبه أحدٌ وعدٌ في توثيقٍ لا سلوكٌ في كود.
    DailyRatingToken.objects.filter(
        tenant=tenant_obj,
        employee=emp_obj,
        service_date=service_date,
        revoked_at__isnull=True,
        expires_at__gt=now,
    ).update(revoked_at=now)

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = now + RATING_TOKEN_LIFETIME

    token_obj = DailyRatingToken.objects.create(
        tenant=tenant_obj,
        employee=emp_obj,
        service_date=service_date,
        token_hash=token_hash,
        expires_at=expires_at,
        # ربطُ تقييمِ اليومِ القائم إن وُجد — كي لا يبدأ الرابطُ من فراغٍ ويعده تعديلاً.
        rating=DailyRating.objects.filter(
            tenant=tenant_obj, employee=emp_obj, service_date=service_date,
        ).first(),
    )
    return token_obj, raw_token


def resolve_daily_rating_token(raw_token: str) -> DailyRatingToken:
    """حل الرمز الخام والتحقق من صلاحيته.

    يرفع RatingTokenNotFound (404) إذا لم يوجد، أو RatingTokenGone (410) إذا انتهت صلاحيته.
    طابق سابقة المستودع في docshare.
    """
    token_hash = hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()
    token_obj = (
        DailyRatingToken.objects.select_related("tenant", "employee__user", "rating")
        .filter(token_hash=token_hash)
        .first()
    )
    if not token_obj:
        raise RatingTokenNotFound("الرابط غير صالح أو غير موجود.")

    if not token_obj.is_live:
        raise RatingTokenGone("انتهت صلاحية هذا الرابط.")

    return token_obj


@transaction.atomic
def submit_daily_rating(
    *,
    tenant: Tenant,
    employee: PlatformEmployee,
    service_date: datetime.date,
    stars: int,
    note: str = "",
    source: str = DailyRating.Source.IN_APP,
    user=None,
    token_obj: DailyRatingToken | None = None,
) -> DailyRating:
    """إنشاء أو تعديل التقييم اليومي وفق القواعد الصارمة.

    ترتيب القفل: DailyRating
    - النجوم 1..5 إلزامية.
    - التحقق من العمل الفعلي في هذا اليوم (يرفض إذا لم يكن هناك عمل).
    - التعديل مسموح مرة واحدة فقط (edited_once) والمحاولة الثانية تُرفض فوراً.
    - فرادة (tenant, employee, service_date) غير مشروطة.
    """
    if stars < 1 or stars > 5:
        raise DailyRatingError("invalid_stars", "التقييم يجب أن يكون بين 1 و 5 نجوم.", status_code=400)

    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    emp_obj = employee if isinstance(employee, PlatformEmployee) else PlatformEmployee.objects.get(pk=employee)

    # 1. التحقق من العمل الفعلي في ذلك اليوم
    if not has_employee_worked_on_date(tenant_obj, emp_obj, service_date):
        raise DailyRatingError(
            "no_work_on_date",
            "لا يمكن إنشاء تقييم ليوم لم يعمل فيه الموظف في هذه الشركة.",
            status_code=400,
        )

    # 2. قفل التقييم الحالي إن وُجد لمنع سباق التعديل
    existing = (
        DailyRating.objects.select_for_update()
        .filter(tenant=tenant_obj, employee=emp_obj, service_date=service_date)
        .first()
    )

    clean_note = note.strip() if note else ""

    if existing:
        # التعديل مسموح مرة واحدة فقط
        if existing.edited_once:
            raise DailyRatingConflict(
                "already_edited",
                "تم تعديل هذا التقييم مسبقاً ولا يمكن تعديله مرة ثانية.",
                status_code=400,
            )
        existing.stars = stars
        existing.note = clean_note
        existing.edited_once = True
        existing.save(update_fields=["stars", "note", "edited_once", "updated_at"])

        if token_obj and not token_obj.rating_id:
            token_obj.rating = existing
            token_obj.save(update_fields=["rating"])

        return existing

    # إنشاء تقييم جديد.
    #
    # **والقفلُ لا يُغني هنا**: `select_for_update` على صفٍّ غيرِ موجودٍ لا يقفل
    # شيئاً، فإرسالان متزامنان لنفس اليوم يمرّان معاً ويصطدمان بالقيد. القيدُ في
    # القاعدة هو الحارس، وواجبُ الخدمة ترجمةُ اصطدامه — كما في `generate_integration_key`.
    try:
        with transaction.atomic():
            rating = DailyRating.objects.create(
                tenant=tenant_obj,
                employee=emp_obj,
                service_date=service_date,
                stars=stars,
                note=clean_note,
                source=source,
                rated_by=user if getattr(user, "is_authenticated", False) else None,
                edited_once=False,
            )
    except IntegrityError:
        raise DailyRatingConflict(
            "already_rated",
            "سُجّل تقييمٌ لهذا اليوم لتوّه؛ أعد المحاولة لتعديله.",
            status_code=409,
        )
    if token_obj:
        token_obj.rating = rating
        token_obj.save(update_fields=["rating"])

    return rating


@transaction.atomic
def update_daily_rating(
    *,
    rating_id: int,
    stars: int,
    note: str = "",
) -> DailyRating:
    """تعديل تقييم قائم لمرة واحدة فقط."""
    if stars < 1 or stars > 5:
        raise DailyRatingError("invalid_stars", "التقييم يجب أن يكون بين 1 و 5 نجوم.", status_code=400)

    locked = DailyRating.objects.select_for_update().filter(pk=rating_id).first()
    if not locked:
        raise DailyRatingError("not_found", "التقييم غير موجود.", status_code=404)

    if locked.edited_once:
        raise DailyRatingConflict(
            "already_edited",
            "تم تعديل هذا التقييم مسبقاً ولا يمكن تعديله مرة ثانية.",
            status_code=400,
        )

    locked.stars = stars
    locked.note = note.strip() if note else ""
    locked.edited_once = True
    locked.save(update_fields=["stars", "note", "edited_once", "updated_at"])
    return locked


def calculate_employee_ratings_summary(
    *,
    employee: PlatformEmployee,
    tenant: Tenant | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    min_sample_size: int = 5,
) -> dict:
    """حساب ملخص تقييمات الموظف مع اشتراط حد أدنى للعينة لدخول الأداء."""
    emp_id = getattr(employee, "pk", employee)
    qs = DailyRating.objects.filter(employee_id=emp_id)
    if tenant:
        t_id = getattr(tenant, "pk", tenant)
        qs = qs.filter(tenant_id=t_id)
    if date_from:
        qs = qs.filter(service_date__gte=date_from)
    if date_to:
        qs = qs.filter(service_date__lte=date_to)

    sample_size = qs.count()
    if sample_size < min_sample_size:
        return {
            "status": "insufficient_data",
            "average_stars": None,
            "sample_size": sample_size,
            "min_sample_size": min_sample_size,
        }

    avg_stars = qs.aggregate(Avg("stars"))["stars__avg"] or 0.0
    return {
        "status": "sufficient_data",
        "average_stars": round(float(avg_stars), 2),
        "sample_size": sample_size,
        "min_sample_size": min_sample_size,
    }


#: أسماءُ الكيانات التي **لا** مفتاحَ لها في معجم الشركة — تُكتب هنا وحدَها.
#: وما له مفتاحٌ (`doc.sales_invoice` مثلاً) يُقرأ من `term()` لا من هنا: قوالبُ
#: الشركات تسمّيه أسماءً مختلفة، وكتابتُه حرفياً تُري الزبونَ معجمَ شركةٍ غيرِه.
STATIC_ENTITY_LABELS = {
    "sales_quotation": "عرض سعر",
    "sales_order": "طلبية مبيعات",
    "purchase_invoice": "فاتورة مشتريات",
    "purchase_order": "أمر شراء",
    "local_purchase_invoice": "فاتورة شراء محلية",
    "customer_payment": "سند قبض",
    "supplier_payment": "سند صرف",
    "payment": "سند مالي",
    "journal_entry": "قيد محاسبي",
    "journal_header": "قيد محاسبي",
    "work_order": "أمر عمل",
    "deliverable": "مُسلَّم عمل",
    "partner": "طرف تعامل",
    "customer": "عميل",
    "supplier": "مورد",
    "product": "منتج",
    "document_share": "رابط مشاركة",
    "membership": "عضوية",
    "user": "مستخدم",
}


def _entity_label_for(tenant, entity_type: str) -> str:
    """اسمُ نوعِ المستند بمعجمِ هذه الشركة، وإلا فالثابتُ، وإلا «مستند»."""
    key = f"doc.{entity_type}"
    resolved = term(tenant, key)
    if resolved != key:  # `term` تُعيد المفتاحَ نفسَه حين لا تعرفه
        return resolved
    return STATIC_ENTITY_LABELS.get(entity_type, "مستند")


def _human_readable_activity_description(log: ActivityLog, tenant=None) -> str:
    """صياغة وصف النشاط بلغة عربية مفهومة دون JSON ولا أسماء جداول، وإظهار التغيير المالي من ماذا إلى ماذا."""
    actions_map = {
        "create": "إنشاء",
        "update": "تعديل",
        "delete": "حذف",
        "post": "ترحيل",
        "unpost": "إلغاء ترحيل",
        "duplicate": "نسخ",
        "payment": "تسجيل دفعة",
    }

    entity_name = _entity_label_for(tenant if tenant is not None else log.tenant, log.entity_type)
    action_name = actions_map.get(log.action, log.action)
    label = f" {log.entity_label}" if log.entity_label else ""

    meta = log.metadata if isinstance(log.metadata, dict) else {}

    # فحص التغيير المالي من ماذا إلى ماذا.
    #
    # **الواصفُ واصفُ المستودع لا نسخةٌ عنه**: المنتِجون الحقيقيّون (`sales/views.py`
    # وغيرُها) يكتبون `build_activity_changes(...) + build_line_changes(...)`، وبنودُ
    # الأسطر منها `{"kind": "line_changed", "changes": [...]}` — وهناك يسكن المال.
    # وقراءةُ `old`/`new` من المستوى الأعلى وحدَه كانت تُسقطها كلَّها بصمت.
    financial_change_str = ""
    changes = meta.get("changes") or meta.get("diff") or []
    if isinstance(changes, list) and changes:
        try:
            described = describe_activity_changes(
                [c for c in changes if isinstance(c, dict) and c.get("label")]
            )
        except (KeyError, TypeError):
            described = ""
        if described:
            financial_change_str = f" ({described})"

    # حالة 2: مفاتيح مالية مباشرة في metadata
    if not financial_change_str:
        for old_k, new_k, lbl in (
            ("old_total", "new_total", "الإجمالي"),
            ("old_amount", "new_amount", "المبلغ"),
            ("from_amount", "to_amount", "المبلغ"),
            ("old_price", "new_price", "السعر"),
            ("amount_before", "amount_after", "المبلغ"),
            ("before", "after", "القيمة"),
        ):
            if old_k in meta and new_k in meta:
                financial_change_str = f" (تغيير {lbl} من {meta[old_k]} إلى {meta[new_k]})"
                break

    if financial_change_str:
        return f"{action_name} {entity_name}{label}:{financial_change_str}"

    if log.description and not any(k in log.description for k in ("{", "}", '":', "table")):
        return log.description

    return f"{action_name} {entity_name}{label}".strip()


def get_my_books_tab_data(tenant: Tenant) -> dict:
    """بيانات تبويب «من يمسك دفاتري» لصاحب الشركة.

    القواعد الصارمة:
    1. المصدر الوحيد لمعرفة الوكيل هو صف Engagement النشط — لا قراءة لجدول العضويات.
    2. يقال للزبون صراحةً إن الوكيل يعمل بصلاحية مدير بلا تلطيف.
    3. نشاط الوكيل داخل هذه الشركة وحدها — لا يرى شيئاً من شركات أخرى.
    4. العرض والدخول مستبعدان من السجل (view و login).
    5. التغيير المالي يظهر «من ماذا إلى ماذا».
    6. بلغة مفهومة: لا JSON ولا أسماء جداول.
    7. قائمة AgentGrantedMembership (من أضافه الوكيل أو عدل دوره).
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)

    # 1. استخراج الوكيل النشط حصراً من Engagement
    active_engagement = (
        Engagement.objects.filter(tenant=tenant_obj, status=Engagement.Status.ACTIVE)
        .select_related("employee__user")
        .first()
    )

    agent_info = None
    agent_user_ids = []
    if active_engagement:
        emp = active_engagement.employee
        user = emp.user
        agent_user_ids.append(user.pk)
        agent_info = {
            "id": emp.pk,
            "user_id": user.pk,
            "name": user.get_full_name() or user.username,
            "username": user.username,
            "specialty": emp.specialty,
            "assigned_at": active_engagement.assigned_at.isoformat(),
            "role_title": "مدير النظام والعمليات",
            "authority_notice": "يعمل وكيل المنصة بصلاحية مدير كاملة على حساب الشركة لإدارة الدفاتر المحاسبية والعمليات التشغيلية.",
            "engagement_id": active_engagement.pk,
            "engagement_status": active_engagement.status,
        }

    # إذا لم يكن هناك ارتباط نشط، نجمع موظفي المنصة الذين ارتبطوا سابقاً بهذه الشركة لعرض سجلهم التاريخي
    all_past_emp_user_ids = list(
        PlatformEmployee.objects.filter(engagements__tenant=tenant_obj)
        .values_list("user_id", flat=True)
        .distinct()
    )
    for uid in all_past_emp_user_ids:
        if uid not in agent_user_ids:
            agent_user_ids.append(uid)

    # 2. سجل العضويات الممنوحة أو المعدلة بواسطة وكيل داخل هذه الشركة
    granted_qs = (
        AgentGrantedMembership.objects.filter(tenant=tenant_obj)
        .select_related("acting_employee__user", "user")
        .order_by("-created_at")
    )
    granted_memberships = []
    for record in granted_qs:
        snap = record.identity_snapshot or {}
        target_name = snap.get("full_name") or snap.get("username") or ""
        if not target_name and record.user:
            target_name = record.user.get_full_name() or record.user.username

        roles_ar = {
            "manager": "مدير",
            "accountant": "محاسب",
            "cashier": "أمين صندوق",
            "sales": "مسؤول مبيعات",
            "purchases": "مسؤول مشتريات",
            "inventory": "أمين مخزن",
            "viewer": "مشاهد",
            "": "عضو جديد",
        }
        role_before_display = roles_ar.get(record.role_before, record.role_before or "عضو جديد")
        role_after_display = roles_ar.get(record.role_after, record.role_after)

        granted_memberships.append({
            "id": record.pk,
            "target_user_name": target_name,
            "role_before": record.role_before,
            "role_before_display": role_before_display,
            "role_after": record.role_after,
            "role_after_display": role_after_display,
            "created_at": record.created_at.isoformat(),
            "acting_employee_name": (
                record.acting_employee.user.get_full_name() or record.acting_employee.user.username
                if record.acting_employee and record.acting_employee.user
                else "وكيل المنصة"
            ),
        })

    # 3. سجل نشاط الوكيل داخل هذه الشركة وحدها (مستبعد منه view و login)
    activity_base_qs = (
        ActivityLog.objects.filter(
            tenant=tenant_obj,
            user_id__in=agent_user_ids,
        )
        .exclude(action__in=["view", "login", "logout"])
        .exclude(is_view=True)
    )
    total_activities_count = activity_base_qs.count()
    # `select_related("user")` لا زينة: الحلقةُ أدناه تقرأ `log.user` لكلّ صفّ،
    # فبدونها مئةُ صفٍّ = مئةُ استعلامٍ إضافيّ.
    activity_qs = activity_base_qs.select_related("user").order_by("-timestamp")[:MY_BOOKS_ACTIVITY_PAGE_CAP]

    activity_items = []
    for log in activity_qs:
        desc = _human_readable_activity_description(log, tenant_obj)
        activity_items.append({
            "id": log.pk,
            "timestamp": log.timestamp.isoformat(),
            "action": log.action,
            "entity_type": log.entity_type,
            "description": desc,
            "actor_name": log.user.get_full_name() or log.user.username if log.user else "الوكيل",
        })

    return {
        "agent": agent_info,
        "granted_memberships": granted_memberships,
        "activity_log": activity_items,
        # العددُ الكلّيُّ من القاعدة لا `len` بعد القصّ — وإلا جمد على السقف وكذب.
        "total_activities_count": total_activities_count,
        "returned_activities_count": len(activity_items),
        "activity_page_cap": MY_BOOKS_ACTIVITY_PAGE_CAP,
        "can_suspend": bool(active_engagement),
    }


def calculate_two_health_scores(tenant: Tenant) -> dict:
    """احتساب درجتي الصحة المنفصلتين للشركة (المرحلة السابعة: م٧).

    القواعد الصارمة:
    1. «صحة الخدمة» = تقصيرنا (تجاوز أجل، إعادة عمل، مُسلَّمات مرفوضة، تقييمات منخفضة).
    2. «تعاون الزبون» = تقصيره (أعمال بانتظار العميل، ردود متأخرة، استفسارات معلقة).
    3. الخلط ممنوع: لا تدمج الدرجتين ولا تحسب متوسطاً.
    4. استهلاك الباقة وحالة الاشتراك خارج الصحة تماماً.
    5. أعلى 3 أسباب بقوالب ثابتة مسماة الجهة دون أي نموذج لغة.
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    now = timezone.now()

    # --------------------------------------------------------------------------
    # 1. صحة الخدمة (تقصير المنصة والوكيل)
    # --------------------------------------------------------------------------
    service_deductions = 0
    service_reasons = []

    # أ. أوامر عمل تجاوزت الأجل المحدد من طرفنا
    sla_breaches_count = (
        WorkOrder.objects.filter(tenant=tenant_obj)
        .filter(
            (models.Q(approved_at__gt=models.F("deadline_at")) & models.Q(deadline_at__isnull=False))
            | (models.Q(approved_at__isnull=True) & models.Q(deadline_at__lt=now) & models.Q(deadline_at__isnull=False))
        )
        .exclude(status__in=[WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED, WorkOrder.Status.WAITING_CUSTOMER])
        .count()
    )
    if sla_breaches_count > 0:
        deduction = sla_breaches_count * 15
        service_deductions += deduction
        service_reasons.append({
            "deduction": deduction,
            "text": f"علينا: {sla_breaches_count} أعمالٍ تجاوزت الأجل",
        })

    # ب. أوامر عمل ملغاة — **رقمٌ تشخيصيٌّ لا خصم**.
    #
    # المواصفة (§٨) تحسمها: «الإلغاءُ يظهر معدَّلَ إعادةِ عملٍ منفصلاً **لا عقوبةً
    # آليّة**، لأنّ سببَ الإلغاء قد لا يكون من الموظف» — وقد التزمت بها م٥ في
    # الدرجة المركّبة، فإعادتُها هنا تحت اسمٍ آخرَ خرقٌ لها بالباب الخلفيّ.
    cancelled_count = WorkOrder.objects.filter(
        tenant=tenant_obj, status=WorkOrder.Status.CANCELLED
    ).count()

    # ج. مُسلَّمات رُفضت في المراجعة
    rejected_deliv_count = WorkOrderDeliverable.objects.filter(
        tenant=tenant_obj,
        review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
    ).count()
    if rejected_deliv_count > 0:
        deduction = rejected_deliv_count * 10
        service_deductions += deduction
        service_reasons.append({
            "deduction": deduction,
            "text": f"علينا: {rejected_deliv_count} مُسلَّماتٍ رُفضت في المراجعة",
        })

    # د. تقييمات يومية منخفضة (نجمتان أو أقل) — **بعد حدٍّ أدنى للعيّنة**.
    #
    # المواصفة (§١٠): «تقييمٌ منفردٌ لا يُستعمل لعقوبةٍ ولا قرارٍ وظيفيّ — يدخل
    # الأداءَ بعد حدٍّ أدنى من العيّنة». فنقرةٌ واحدةٌ بنجمتين كانت تُنزل صحّةَ
    # الخدمة عشرَ درجاتٍ فوراً، وهي بالضبط ما نهت عنه.
    ratings_qs = DailyRating.objects.filter(tenant=tenant_obj)
    ratings_sample = ratings_qs.count()
    low_ratings_count = ratings_qs.filter(stars__lte=2).count()
    if ratings_sample >= RATING_HEALTH_MIN_SAMPLE and low_ratings_count > 0:
        deduction = low_ratings_count * 10
        service_deductions += deduction
        service_reasons.append({
            "deduction": deduction,
            "text": f"علينا: {low_ratings_count} تقييماتٍ يوميةٍ منخفضة",
        })

    service_health_score = max(0, 100 - service_deductions)
    service_reasons.sort(key=lambda r: r["deduction"], reverse=True)
    top_service_reasons = [r["text"] for r in service_reasons[:3]]

    # --------------------------------------------------------------------------
    # 2. تعاون الزبون (تقصير وتأخيرات الزبون)
    # --------------------------------------------------------------------------
    customer_deductions = 0
    customer_reasons = []

    # أ. أوامر عمل متوقفة بانتظار العميل حالياً
    waiting_customer_count = WorkOrder.objects.filter(
        tenant=tenant_obj, status=WorkOrder.Status.WAITING_CUSTOMER
    ).count()
    if waiting_customer_count > 0:
        deduction = waiting_customer_count * 15
        customer_deductions += deduction
        customer_reasons.append({
            "deduction": deduction,
            "text": f"بانتظار الزبون: {waiting_customer_count} أعمالٍ بانتظار الرد",
        })

    # ب. أوامر عمل تراكم فيها انتظار الزبون لأكثر من 48 ساعة
    long_waiting_count = WorkOrder.objects.filter(
        tenant=tenant_obj,
        waiting_seconds_total__gte=48 * 3600,
    ).count()
    if long_waiting_count > 0:
        deduction = long_waiting_count * 10
        customer_deductions += deduction
        customer_reasons.append({
            "deduction": deduction,
            "text": f"بانتظار الزبون: {long_waiting_count} أعمالٍ تأخّر ردّه عليها أكثر من ٤٨ ساعة",
        })

    # ج. استفسارات مرئية للزبون معلقة في أوامر عمل بانتظار العميل
    pending_comments_count = WorkOrderComment.objects.filter(
        tenant=tenant_obj,
        visibility=WorkOrderComment.Visibility.CLIENT_VISIBLE,
        work_order__status=WorkOrder.Status.WAITING_CUSTOMER,
    ).count()
    if pending_comments_count > 0:
        deduction = pending_comments_count * 5
        customer_deductions += deduction
        customer_reasons.append({
            "deduction": deduction,
            "text": f"بانتظار الزبون: {pending_comments_count} استفساراتٍ معلّقة",
        })

    customer_cooperation_score = max(0, 100 - customer_deductions)
    customer_reasons.sort(key=lambda r: r["deduction"], reverse=True)
    top_customer_reasons = [r["text"] for r in customer_reasons[:3]]

    return {
        # رقمٌ تشخيصيٌّ يُعرَض ولا يُخصَم — قرارُ المواصفة §٨.
        "rework_diagnostic": {
            "cancelled_work_orders": cancelled_count,
            "counts_against_score": False,
        },
        "ratings_sample": {
            "size": ratings_sample,
            "min_sample_size": RATING_HEALTH_MIN_SAMPLE,
            "counts_against_score": ratings_sample >= RATING_HEALTH_MIN_SAMPLE,
        },
        "service_health": {
            "score": service_health_score,
            "status": "excellent" if service_health_score >= 90 else "good" if service_health_score >= 70 else "needs_attention",
            "top_reasons": top_service_reasons,
        },
        "customer_cooperation": {
            "score": customer_cooperation_score,
            "status": "excellent" if customer_cooperation_score >= 90 else "good" if customer_cooperation_score >= 70 else "needs_attention",
            "top_reasons": top_customer_reasons,
        },
    }


