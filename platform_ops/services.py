"""خدمات عمليات المنصة (المرحلتان الأولى والثانية: الأساس ودورة الارتباط).

ترتيب الأقفال الصارم لمنع التعارضات والـ Deadlocks على MySQL:
ServiceSubscription -> PlatformEmployee -> Engagement -> UserCompanyMembership
ملاحظة: لا يُستعمل select_related مع select_for_update لتجنب قفل جداول غير مقصودة.
"""
from django.db import transaction
from django.utils import timezone

from tenants.models import Tenant, UserCompanyMembership

from .models import (
    AgentGrantedMembership,
    Engagement,
    PlatformEmployee,
    ServiceSubscription,
)


class PlatformOpsError(Exception):
    """خطأ عام في خدمات عمليات المنصة."""

    def __init__(self, code: str, detail: str, status_code: int = 400):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


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
