"""خدمات عمليات المنصة (المراحل الأولى والثانية والثالثة والرابعة والخامسة والسادسة والسابعة والثامنة، والتذاكر 210-B و210-C و210-D).

ترتيب الأقفال الصارم لمنع التعارضات والـ Deadlocks على MySQL:
Tenant -> ServiceSubscriptionPolicy -> ServiceUnitCatalog -> PerformanceEvaluationPolicy
-> EmployeeCompensationPolicy -> IntegrationKey -> ServiceSubscription -> CompanyHealthCheck
-> CompanyHealthCheckItem -> CustomerAcquisition -> PlatformEmployee -> Engagement -> WorkOrder
-> WorkOrderDeliverable -> WorkOrderDocumentLink -> ServiceUsageEvent -> MonthlyCompensationClose
-> EmployeeSalaryLine -> AcquisitionCommissionLine -> UserCompanyMembership -> DailyRating -> JobPosting -> JobApplicantInvitation -> JobApplicant
ملاحظة: لا يُستعمل select_related مع select_for_update لتجنب قفل جداول غير مقصودة.
"""
import calendar
import copy
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import logging
import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.db.models import Avg, Max, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from core.date_ranges import day_bounds, filter_local_date_range
from core.activity import describe_activity_changes
from core.models import ActivityLog
from core.terminology import term
from hr.models import AttendanceDay, UserDevice
from tenants.models import Currency, Tenant, UserCompanyMembership

from .models import (
    MAX_ONBOARDING_DAYS,
    MAX_SERVICE_TRIAL_DAYS,
    AcquisitionCommissionLine,
    AgentGrantedMembership,
    CompanyHealthCheck,
    CompanyHealthCheckItem,
    CustomerAcquisition,
    DailyRating,
    DailyRatingToken,
    Engagement,
    EmployeeCompensationPolicy,
    EmployeeCompensationPolicyEvent,
    EmployeeSalaryLine,
    IntegrationKey,
    JobApplicant,
    JobApplicantInvitation,
    JobPosting,
    MonthlyCompensationClose,
    PerformanceEvaluationPolicy,
    PerformanceEvaluationPolicyEvent,
    PerformanceReviewRequest,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
    PlatformOperationEvent,
    PlatformRecruiter,
    PolicyProfile,
    ServiceDocumentType,
    ServiceSubscriptionEvent,
    ServiceSubscriptionPolicyEvent,
    ServiceSubscriptionPolicy,
    ServiceSubscription,
    ServiceUnitCatalog,
    ServiceUnitCatalogEntry,
    ServiceUnitCatalogEvent,
    ServiceUsageEvent,
    SubscriptionBillingRecord,
    WalletLineStatus,
    WorkOrder,
    WorkOrderComment,
    WorkOrderDeliverable,
    WorkOrderDocumentLink,
    LineCountSource,
)

logger = logging.getLogger(__name__)

_UNSET = object()
DEFAULT_SERVICE_PLAN = "standard"



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


class BillingError(PlatformOpsError):
    """خطأ عام في عمليات فوترة اشتراكات المنصة (المرحلة 8A)."""

    pass


class BillingConfigurationError(BillingError):
    """خطأ في إعدادات الفوترة (عميل الفوترة أو الأصناف الخدمية أو العملة)."""

    pass


class SubscriptionManagementError(PlatformOpsError):
    """خطأ في تفعيل أو إعداد اشتراك خدمة المنصة."""


class SubscriptionManagementConflict(SubscriptionManagementError):
    """تعارض في انتقال أو إنشاء اشتراك خدمة."""

    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


class PerformanceEvaluationPolicyError(PlatformOpsError):
    """خطأ في إدارة نسخ سياسة تقييم الأداء (210-D)."""


class PerformanceEvaluationPolicyConflict(PerformanceEvaluationPolicyError):
    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


class EmployeeCompensationPolicyError(PlatformOpsError):
    """خطأ في إدارة نسخ سياسة تعويض الموظف (210-D)."""


class EmployeeCompensationPolicyConflict(EmployeeCompensationPolicyError):
    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


class WalletError(PlatformOpsError):
    """خطأ في محفظة الموظف أو عمولة الاكتساب (210-D)."""


class WalletConflict(WalletError):
    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


class MonthCloseBlockedError(PlatformOpsError):
    """إغلاق الشهر محجوبٌ بتسليماتٍ لا تزال بانتظار المراجعة (§٥، §٧)."""

    def __init__(self, code: str, detail: str, blockers: list[int] | None = None):
        super().__init__(code, detail, status_code=409)
        self.blockers = blockers or []


def _validate_subscription_decimal(value, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise SubscriptionManagementError(field_name, f"قيمة {field_name} غير صالحة.")
    if not result.is_finite() or result < Decimal("0.00"):
        raise SubscriptionManagementError(field_name, f"قيمة {field_name} يجب أن تكون صفراً أو أكبر.")
    return result.quantize(Decimal("0.01"))


def _validate_included_quota(value) -> int:
    # `bool` فرعٌ من `int` في بايثون — `True` ليست حصّة.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SubscriptionManagementError(
            "included_quota",
            "الحصة المشمولة يجب أن تكون عدداً صحيحاً غير سالب.",
        )
    return value


def _log_subscription_event(
    subscription: ServiceSubscription,
    *,
    action: str,
    from_status: str = "",
    to_status: str = "",
    reason: str = "",
    actor=None,
    correlation_id: str = "",
    details: dict | None = None,
):
    """يكتب حدث تدقيق واحد داخل معاملة الانتقال الحالية — لا مسار تعديل أو حذف له لاحقاً."""
    return ServiceSubscriptionEvent.objects.create(
        subscription=subscription,
        action=action,
        from_status=from_status or "",
        to_status=to_status or "",
        reason=str(reason or "")[:500],
        actor=actor if getattr(actor, "pk", None) else None,
        correlation_id=str(correlation_id or "")[:64],
        details=details or {},
    )


def _normalize_plan(plan) -> str:
    return str(plan or "").strip()[:50]


def get_active_subscription_policy(at: datetime.datetime | None = None, plan: str = ""):
    """يعيد نسخة السياسة السارية لخطة في لحظة محددة، دون تخمين افتراضي.

    النسخة الخاصة بالخطة تغلب العامة (`plan` فارغ)، والسريان من نافذة
    `effective_from`/`effective_to` — فالنسخة المجدولة لتاريخ لاحق لا تسري قبله.
    """
    moment = at or timezone.now()
    in_effect = (
        ServiceSubscriptionPolicy.objects
        .filter(status=ServiceSubscriptionPolicy.Status.ACTIVE, effective_from__lte=moment)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=moment))
    )
    plan = _normalize_plan(plan)
    if plan:
        specific = in_effect.filter(plan=plan).order_by("-version").first()
        if specific is not None:
            return specific
    return in_effect.filter(plan="").order_by("-version").first()


def _resolve_billing_product(value, field_name: str):
    """يقبل صنفاً أو معرّفه أو لا شيء؛ المعرّف غير الموجود خطأ نطاق 400 لا 500."""
    from inventory.models import Product

    if value is None or value == "":
        return None
    if isinstance(value, Product):
        return value
    product = Product.objects.filter(pk=value).first()
    if product is None:
        raise SubscriptionManagementError(f"{field_name}_not_found", "صنف الفوترة المحدد غير موجود.")
    return product


def _validate_policy_billing_products(
    *, billing_tenant_id, fixed_fee_product, overage_product, overage_unit_price, require_complete: bool,
):
    """صنفا الفوترة خدميان ويتبعان شركة فوترة المنصة نفسها — القاعدة التي يفرضها `billing_preflight` لاحقاً.

    `require_complete` لحظة التفعيل: صنف الرسم إلزامي، وصنف التجاوز إلزامي متى كان سعر التجاوز أكبر من صفر،
    كي لا تُنشأ اشتراكات لا يمكن فوترتها.
    """
    for field_name, product in (("fixed_fee_product", fixed_fee_product), ("overage_product", overage_product)):
        if product is None:
            continue
        if product.tenant_id != billing_tenant_id:
            raise SubscriptionManagementError(
                f"{field_name}_cross_tenant", "صنف الفوترة يجب أن يتبع شركة فوترة المنصة المحددة في السياسة.",
            )
        if not getattr(product, "is_service", False):
            raise SubscriptionManagementError(f"{field_name}_not_service", "صنف الفوترة يجب أن يكون صنفاً خدمياً.")
    if require_complete and fixed_fee_product is None:
        raise SubscriptionManagementError("fixed_fee_product_required", "حدّد صنف الرسم الشهري قبل تفعيل السياسة.")
    if require_complete and overage_unit_price > Decimal("0.00") and overage_product is None:
        raise SubscriptionManagementError(
            "overage_product_required", "حدّد صنف العمليات الزائدة لسياسة سعر تجاوزها أكبر من صفر.",
        )


def search_policy_billing_products(*, policy, query: str = "", limit: int = 20):
    """أصناف خدمية في شركة فوترة السياسة وحدها — لا معامل شركة من الطالب."""
    from inventory.models import Product

    billing_tenant_id = ServiceSubscriptionPolicy.objects.filter(
        pk=getattr(policy, "pk", policy),
    ).values_list("billing_tenant_id", flat=True).first()
    if billing_tenant_id is None:
        return Product.objects.none()
    qs = Product.objects.filter(tenant_id=billing_tenant_id, is_service=True)
    query = str(query or "").strip()
    if query:
        qs = qs.filter(Q(sku__icontains=query) | Q(name_ar__icontains=query))
    return qs.order_by("sku")[:limit]


def _resolve_billing_tenant(billing_tenant):
    if billing_tenant is None:
        raise SubscriptionManagementError(
            "billing_tenant_required",
            "شركة فوترة المنصة مطلوبة قبل تفعيل سياسة الاشتراك.",
        )
    if isinstance(billing_tenant, Tenant):
        return billing_tenant
    try:
        return Tenant.objects.get(pk=billing_tenant)
    except (Tenant.DoesNotExist, ValueError, TypeError):
        raise SubscriptionManagementError(
            "billing_tenant_not_found",
            "شركة فوترة المنصة غير موجودة.",
        )


def _validate_subscription_policy_values(
    *, monthly_fee, included_quota, trial_days, billing_tenant, overage_unit_price=Decimal("0.00"),
):
    billing_tenant = _resolve_billing_tenant(billing_tenant)
    monthly_fee = _validate_subscription_decimal(monthly_fee, "monthly_fee")
    overage_unit_price = _validate_subscription_decimal(overage_unit_price, "overage_unit_price")
    included_quota = _validate_included_quota(included_quota)
    try:
        trial_days = int(trial_days)
    except (TypeError, ValueError):
        raise SubscriptionManagementError("trial_days", "مدة التجربة يجب أن تكون عدداً صحيحاً.")
    if not 0 <= trial_days <= MAX_SERVICE_TRIAL_DAYS:
        raise SubscriptionManagementError(
            "trial_days",
            f"مدة التجربة يجب أن تكون بين 0 و{MAX_SERVICE_TRIAL_DAYS} يوماً.",
        )
    return monthly_fee, included_quota, trial_days, billing_tenant, overage_unit_price


def _policy_event_details(policy):
    return {
        "plan": policy.plan,
        "fixed_fee_product_id": policy.fixed_fee_product_id,
        "overage_product_id": policy.overage_product_id,
        "billing_tenant_id": policy.billing_tenant_id,
        "monthly_fee": str(policy.monthly_fee),
        "included_quota": policy.included_quota,
        "trial_days": policy.trial_days,
        "overage_unit_price": str(policy.overage_unit_price),
    }


def _log_subscription_policy_event(policy, *, action, actor=None, correlation_id="", details=None):
    """حدثُ تدقيقٍ للسياسة داخل معاملة الكتابة نفسها — لا مسار تعديل أو حذف له."""
    return ServiceSubscriptionPolicyEvent.objects.create(
        policy=policy,
        action=action,
        actor=actor if getattr(actor, "pk", None) else None,
        correlation_id=str(correlation_id or "")[:64],
        details=details or {},
    )


def create_subscription_policy_draft(
    *,
    actor=None,
    billing_tenant,
    monthly_fee=_UNSET,
    included_quota=_UNSET,
    trial_days=_UNSET,
    overage_unit_price=_UNSET,
    plan: str = "",
    fixed_fee_product=None,
    overage_product=None,
    correlation_id: str = "",
    cloned_from=None,
):
    """ينشئ نسخة مسودة مؤرخة من افتراضيات الاشتراك.

    الحقول الغائبة تأخذ افتراضيات النموذج — الواجهة لا تحمل أرقام الـpilot.
    `cloned_from` يجعل حدث التدقيق `cloned` بمصدره بدل `created`.

    لا `select_for_update` لحساب رقم النسخة: قفلُ مدى فارغ على MySQL يأخذ
    gap lock فتتشابك معاملتان تُدرجان معاً (1213، لا IntegrityError). القيدُ
    الفريد على `version` هو الحارس: المعاملة الثانية تنتظر ثم تُرفض بتكرار
    المفتاح ← 409 «أعد المحاولة».
    """
    if monthly_fee is _UNSET:
        monthly_fee = ServiceSubscriptionPolicy._meta.get_field("monthly_fee").default
    if included_quota is _UNSET:
        included_quota = ServiceSubscriptionPolicy._meta.get_field("included_quota").default
    if trial_days is _UNSET:
        trial_days = ServiceSubscriptionPolicy._meta.get_field("trial_days").default
    if overage_unit_price is _UNSET:
        overage_unit_price = ServiceSubscriptionPolicy._meta.get_field("overage_unit_price").default
    monthly_fee, included_quota, trial_days, billing_tenant, overage_unit_price = (
        _validate_subscription_policy_values(
            monthly_fee=monthly_fee,
            included_quota=included_quota,
            trial_days=trial_days,
            billing_tenant=billing_tenant,
            overage_unit_price=overage_unit_price,
        )
    )
    fixed_fee_product = _resolve_billing_product(fixed_fee_product, "fixed_fee_product")
    overage_product = _resolve_billing_product(overage_product, "overage_product")
    _validate_policy_billing_products(
        billing_tenant_id=billing_tenant.pk,
        fixed_fee_product=fixed_fee_product,
        overage_product=overage_product,
        overage_unit_price=overage_unit_price,
        require_complete=False,
    )
    with transaction.atomic():
        last_version = ServiceSubscriptionPolicy.objects.aggregate(Max("version"))["version__max"] or 0
        try:
            # نقطةُ حفظٍ حول الإدراج كي لا تبقى المعاملةُ الخارجية معطوبةً بعد IntegrityError.
            with transaction.atomic():
                policy = ServiceSubscriptionPolicy.objects.create(
                    version=last_version + 1,
                    status=ServiceSubscriptionPolicy.Status.DRAFT,
                    plan=_normalize_plan(plan),
                    billing_tenant=billing_tenant,
                    fixed_fee_product=fixed_fee_product,
                    overage_product=overage_product,
                    monthly_fee=monthly_fee,
                    included_quota=included_quota,
                    trial_days=trial_days,
                    overage_unit_price=overage_unit_price,
                    created_by=actor if getattr(actor, "pk", None) else None,
                )
        except IntegrityError:
            raise SubscriptionManagementConflict(
                "subscription_policy_version_conflict",
                "تعذر إنشاء نسخة سياسة جديدة؛ أعد المحاولة.",
            )
        details = {"after": _policy_event_details(policy)}
        if cloned_from is not None:
            details["source_policy_id"] = cloned_from.pk
        _log_subscription_policy_event(
            policy,
            action=(
                ServiceSubscriptionPolicyEvent.Action.CLONED
                if cloned_from is not None
                else ServiceSubscriptionPolicyEvent.Action.CREATED
            ),
            actor=actor,
            correlation_id=correlation_id,
            details=details,
        )
    logger.info(
        "platform.subscription_policy_draft_created policy=%s version=%s actor=%s",
        policy.pk,
        policy.version,
        getattr(actor, "pk", None),
    )
    return policy


def clone_subscription_policy_to_draft(*, policy, actor=None, correlation_id: str = ""):
    """ينسخ نسخة نشطة أو منتهية إلى مسودة جديدة قابلة للتعديل — النسخ الأخرى لا تُعدَّل أبداً."""
    source = ServiceSubscriptionPolicy.objects.get(pk=getattr(policy, "pk", policy))
    return create_subscription_policy_draft(
        actor=actor,
        billing_tenant=source.billing_tenant_id,
        monthly_fee=source.monthly_fee,
        included_quota=source.included_quota,
        trial_days=source.trial_days,
        overage_unit_price=source.overage_unit_price,
        plan=source.plan,
        fixed_fee_product=source.fixed_fee_product_id,
        overage_product=source.overage_product_id,
        correlation_id=correlation_id,
        cloned_from=source,
    )


@transaction.atomic
def update_subscription_policy_draft(*, policy, actor=None, correlation_id: str = "", **changes):
    """يعدّل المسودة فقط؛ النسخ النشطة والمنتهية غير قابلة للتغيير."""
    allowed = {
        "billing_tenant", "monthly_fee", "included_quota", "trial_days", "overage_unit_price",
        "plan", "fixed_fee_product", "overage_product",
    }
    if set(changes) - allowed:
        raise SubscriptionManagementError("unsupported_field", "يوجد حقل سياسة غير مسموح بتعديله.")
    locked = ServiceSubscriptionPolicy.objects.select_for_update().get(pk=getattr(policy, "pk", policy))
    if locked.status != ServiceSubscriptionPolicy.Status.DRAFT:
        raise SubscriptionManagementConflict("subscription_policy_immutable", "لا يمكن تعديل سياسة مفعلة أو منتهية.")
    monthly_fee, included_quota, trial_days, billing_tenant, overage_unit_price = (
        _validate_subscription_policy_values(
            monthly_fee=changes.get("monthly_fee", locked.monthly_fee),
            included_quota=changes.get("included_quota", locked.included_quota),
            trial_days=changes.get("trial_days", locked.trial_days),
            billing_tenant=changes.get("billing_tenant", locked.billing_tenant),
            overage_unit_price=changes.get("overage_unit_price", locked.overage_unit_price),
        )
    )
    fixed_fee_product = _resolve_billing_product(
        changes.get("fixed_fee_product", locked.fixed_fee_product_id), "fixed_fee_product",
    )
    overage_product = _resolve_billing_product(
        changes.get("overage_product", locked.overage_product_id), "overage_product",
    )
    _validate_policy_billing_products(
        billing_tenant_id=billing_tenant.pk,
        fixed_fee_product=fixed_fee_product,
        overage_product=overage_product,
        overage_unit_price=overage_unit_price,
        require_complete=False,
    )
    before = _policy_event_details(locked)
    locked.monthly_fee = monthly_fee
    locked.included_quota = included_quota
    locked.trial_days = trial_days
    locked.billing_tenant = billing_tenant
    locked.overage_unit_price = overage_unit_price
    locked.plan = _normalize_plan(changes.get("plan", locked.plan))
    locked.fixed_fee_product = fixed_fee_product
    locked.overage_product = overage_product
    locked.save(update_fields=[
        "monthly_fee", "included_quota", "trial_days", "billing_tenant", "overage_unit_price",
        "plan", "fixed_fee_product", "overage_product", "updated_at",
    ])
    _log_subscription_policy_event(
        locked, action=ServiceSubscriptionPolicyEvent.Action.UPDATED, actor=actor,
        correlation_id=correlation_id,
        details={"before": before, "after": _policy_event_details(locked)},
    )
    logger.info(
        "platform.subscription_policy_draft_updated policy=%s version=%s fields=%s actor=%s",
        locked.pk,
        locked.version,
        ",".join(sorted(changes)),
        getattr(actor, "pk", None),
    )
    return locked


def preview_subscription_policy(*, policy) -> dict:
    """يعيد أثر المسودة: النسخة النشطة الحالية، فروق الحقول، وتصريحاً بعدم مس القائم.

    لا يغيّر حالة السياسة ولا أي اشتراك — قراءة صرفة.
    """
    draft = ServiceSubscriptionPolicy.objects.select_related("billing_tenant").get(
        pk=getattr(policy, "pk", policy)
    )
    # تُقارن المسودة بالنسخة السارية لنطاقها (الخاصة بخطتها وإلا العامة).
    active = get_active_subscription_policy(plan=draft.plan)
    compared_fields = (
        "plan", "billing_tenant_id", "monthly_fee", "included_quota", "trial_days", "overage_unit_price",
        "fixed_fee_product_id", "overage_product_id",
    )
    diff = {}
    for field in compared_fields:
        draft_value = getattr(draft, field)
        active_value = getattr(active, field) if active else None
        if draft_value != active_value:
            money = field in {"monthly_fee", "overage_unit_price"}
            diff[field] = {
                "active": str(active_value) if money and active_value is not None else active_value,
                "draft": str(draft_value) if money and draft_value is not None else draft_value,
            }
    return {
        "draft": draft,
        "active": active,
        "diff": diff,
        "note": "معاينة فقط: لا يتغيّر أي اشتراك قائم؛ الأثر يسري على التفعيلات الجديدة من تاريخ سريان النسخة.",
    }


@transaction.atomic
def activate_subscription_policy(
    *, policy, actor=None, change_reason: str = "", correlation_id: str = "", effective_from=None,
):
    """يفعّل مسودة بسبب إلزامي وتاريخ سريان (الآن افتراضياً، أو لاحقاً فتصير «مجدولة»).

    منع التداخل لكل نطاق (`plan`) تحت قفل صريح على كل صفوف السياسة — لا بقيد
    شرطي تتجاهله MySQL: نسخة النطاق السارية أو المجدولة تُغلق نافذتها عند تاريخ
    سريان الجديدة، وتُرفض الجديدة إن سبق تاريخُها نسخةً مجدولة لنفس النطاق.
    النسخ التي انقضت نافذتها تُعلَّم `retired` هنا، و`effective_state` يعكس
    الحقيقة بين تفعيلين. التفعيل يلزمه صنفا الفوترة الصالحان.
    """
    change_reason = str(change_reason or "").strip()
    if not change_reason:
        raise SubscriptionManagementError("change_reason_required", "سبب التفعيل مطلوب.")
    locked_policies = list(ServiceSubscriptionPolicy.objects.select_for_update().order_by("pk"))
    locked = next((row for row in locked_policies if row.pk == getattr(policy, "pk", policy)), None)
    if locked is None:
        raise SubscriptionManagementError("subscription_policy_not_found", "سياسة الاشتراك غير موجودة.")
    if locked.status != ServiceSubscriptionPolicy.Status.DRAFT:
        raise SubscriptionManagementConflict("subscription_policy_not_draft", "لا يمكن تفعيل هذه السياسة مرة أخرى.")

    now = timezone.now()
    starts_at = effective_from or now
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    # هامش دقيقة لفرق الساعة بين المتصفح والخادم؛ ما قبله ماضٍ مرفوض.
    if starts_at < now - datetime.timedelta(minutes=1):
        raise SubscriptionManagementError("effective_from_in_past", "تاريخ السريان لا يكون في الماضي.")
    starts_at = max(starts_at, now)

    _validate_policy_billing_products(
        billing_tenant_id=locked.billing_tenant_id,
        fixed_fee_product=locked.fixed_fee_product,
        overage_product=locked.overage_product,
        overage_unit_price=locked.overage_unit_price,
        require_complete=True,
    )

    same_scope = [
        row for row in locked_policies
        if row.pk != locked.pk and row.status == ServiceSubscriptionPolicy.Status.ACTIVE and row.plan == locked.plan
    ]
    later = [row for row in same_scope if row.effective_from and row.effective_from >= starts_at]
    if later:
        raise SubscriptionManagementConflict(
            "subscription_policy_overlap",
            f"النسخة v{later[0].version} لنفس النطاق تسري من تاريخ لاحق أو مساوٍ؛ اختر تاريخ سريان بعده.",
        )
    superseded = []
    for previous in same_scope:
        if previous.effective_to is None or previous.effective_to > starts_at:
            previous.effective_to = starts_at
            previous.save(update_fields=["effective_to", "updated_at"])
            superseded.append(previous.pk)

    locked.status = ServiceSubscriptionPolicy.Status.ACTIVE
    locked.effective_from = starts_at
    locked.effective_to = None
    locked.activated_at = now
    locked.activated_by = actor if getattr(actor, "pk", None) else None
    locked.activation_reason = change_reason
    locked.save(update_fields=[
        "status", "effective_from", "effective_to",
        "activated_at", "activated_by", "activation_reason", "updated_at",
    ])
    _log_subscription_policy_event(
        locked, action=ServiceSubscriptionPolicyEvent.Action.ACTIVATED, actor=actor,
        correlation_id=correlation_id,
        details={
            "reason": change_reason,
            "effective_from": starts_at.isoformat(),
            "superseded_policy_ids": superseded,
            "after": _policy_event_details(locked),
        },
    )

    for row in locked_policies:
        if (
            row.pk != locked.pk
            and row.status == ServiceSubscriptionPolicy.Status.ACTIVE
            and row.effective_to is not None
            and row.effective_to <= now
        ):
            row.status = ServiceSubscriptionPolicy.Status.RETIRED
            row.save(update_fields=["status", "updated_at"])
            _log_subscription_policy_event(
                row, action=ServiceSubscriptionPolicyEvent.Action.RETIRED, actor=actor,
                correlation_id=correlation_id,
                details={"reason": change_reason, "effective_to": row.effective_to.isoformat()},
            )
    logger.info(
        "platform.subscription_policy_activated policy=%s version=%s plan=%s effective_from=%s actor=%s",
        locked.pk,
        locked.version,
        locked.plan,
        starts_at.isoformat(),
        getattr(actor, "pk", None),
    )
    return locked


def validate_billing_customer_for_subscription(*, customer, tenant_id: int | None, billing_tenant_id: int | None):
    """يحصر عميل الفوترة في شركة المنصة الملتقطة للسياسة."""
    if customer is None:
        return None
    if billing_tenant_id is None:
        raise BillingConfigurationError(
            "platform_billing_tenant_unconfigured",
            "لم تُضبط شركة فوترة المنصة في سياسة الاشتراك الفعالة.",
            status_code=400,
        )
    if getattr(customer, "tenant_id", None) == tenant_id:
        raise BillingConfigurationError(
            "billing_customer_same_tenant",
            "عميل الفوترة يجب أن يتبع شركة المنصة المفوترة المنفصلة عن الشركة المشتركة.",
            status_code=400,
        )
    if getattr(customer, "tenant_id", None) != billing_tenant_id:
        raise BillingConfigurationError(
            "billing_customer_wrong_platform_tenant",
            "عميل الفوترة لا يتبع شركة فوترة المنصة المحددة في سياسة الاشتراك.",
            status_code=400,
        )
    return customer


def search_platform_billing_customers(*, query: str = "", subscription=None, plan: str = "", limit: int = 20):
    """يبحث عن عملاء الفوترة داخل شركة الفوترة التي سيتحقّق منها الحفظ نفسه.

    لا معامل شركة من الطالب — الشركة مشتقة خادمياً: `billing_tenant` الملتقط على
    الاشتراك إن مُرِّر (تعديل عميله أو تحويل تجربته)، وإلا — أو لصفٍّ قديم بلا لقطة —
    شركة فوترة **نسخة السياسة السارية لنفس نطاق الخطة**. و`plan` هنا ليس زينة: الحفظ
    يتحقّق بسياسة الخطة المطلوبة، فبحثٌ بلا خطة كان يعرض عملاء شركةٍ أخرى ثم يرفضهم
    الحفظُ بـ`billing_customer_wrong_platform_tenant`. وخطةُ الاشتراك المُمرَّر تُستعمل
    حين لا لقطة عليه. بلا شركة فوترة معروفة تعود قائمة فارغة بدل تخمين شركة.
    """
    from partners.models import Partner

    billing_tenant_id = None
    plan = str(plan or "")
    if subscription is not None:
        subscription_id = getattr(subscription, "pk", subscription)
        snapshot = ServiceSubscription.objects.filter(pk=subscription_id).values("billing_tenant_id", "plan").first()
        if snapshot:
            billing_tenant_id = snapshot["billing_tenant_id"]
            plan = plan or snapshot["plan"] or ""
    if billing_tenant_id is None:
        active_policy = get_active_subscription_policy(plan=plan)
        billing_tenant_id = active_policy.billing_tenant_id if active_policy else None
    if billing_tenant_id is None:
        return Partner.objects.none()
    qs = Partner.objects.filter(tenant_id=billing_tenant_id, partner_type="Customer")
    query = str(query or "").strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    return qs.order_by("name")[:limit]


def is_service_subscription_eligible(subscription, at: datetime.datetime | None = None) -> bool:
    """محور الأهلية الوحيد: نشط دوماً مؤهَّل، وتجربة لم تنتهِ بعد مؤهَّلة أيضاً."""
    if not subscription:
        return False
    if subscription.status == ServiceSubscription.Status.ACTIVE:
        return True
    if subscription.status == ServiceSubscription.Status.TRIAL:
        moment = at or timezone.now()
        return bool(subscription.trial_ends_at and moment < subscription.trial_ends_at)
    return False


def eligible_service_tenant_ids(at: datetime.datetime | None = None):
    """معرّفات الشركات المؤهلة للخدمة باستعلام SQL واحد."""
    moment = at or timezone.now()
    return ServiceSubscription.objects.filter(
        Q(status=ServiceSubscription.Status.ACTIVE)
        | Q(status=ServiceSubscription.Status.TRIAL, trial_ends_at__gt=moment)
    ).values_list("tenant_id", flat=True)


def is_service_active(tenant, at: datetime.datetime | None = None) -> bool:
    """هل خدمة المتابعة والإدخال نشطة (فعلياً نشطة أو داخل نافذة تجربة) لهذه الشركة؟

    تفعيل الخدمة هو البوابة الوحيدة لإسناد موظف منصة للشركة، ولدخولها أوامر
    العمل والصحة والاستخدام والتقييم ومركز القيادة.
    """
    if tenant is None:
        return False
    tenant_id = getattr(tenant, "pk", tenant)
    subscription = ServiceSubscription.objects.filter(tenant_id=tenant_id).first()
    return is_service_subscription_eligible(subscription, at=at)


def is_service_trial(subscription, at: datetime.datetime | None = None) -> bool:
    """هل الاشتراك في حالة تجربة لم تنتهِ بعد؟"""
    return bool(subscription and subscription.status == ServiceSubscription.Status.TRIAL and is_service_subscription_eligible(subscription, at))


def _default_scheduled_cancellation_date(subscription) -> datetime.date:
    """نهاية الدورة الحالية أو التجربة — بلا prorating في الـpilot (قرار §1)."""
    in_trial = subscription.status == ServiceSubscription.Status.TRIAL or (
        subscription.status == ServiceSubscription.Status.SUSPENDED
        and subscription.pre_suspension_status == ServiceSubscription.Status.TRIAL
    )
    if in_trial and subscription.trial_ends_at:
        return timezone.localtime(subscription.trial_ends_at).date()
    if subscription.period_start and timezone.localdate() < subscription.period_start:
        return subscription.period_start - datetime.timedelta(days=1)
    if subscription.period_end:
        return subscription.period_end
    return timezone.localdate()


@transaction.atomic
def start_service_trial(
    *, tenant, plan: str | None = None, actor=None, correlation_id: str = "",
) -> ServiceSubscription:
    """يبدأ تجربة مجانية لشركة بلا أي صف اشتراك سابق — تجربة واحدة مدى حياة الشركة."""
    # قفلُ صفّ الشركة الموجود أولاً يُسلسل التفعيل: قفلُ صفّ اشتراكٍ غير موجود على MySQL
    # يأخذ gap lock فتتشابك معاملتان تُدرجان معاً (1213) بدل أن تنتظر إحداهما الأخرى.
    try:
        tenant_obj = Tenant.objects.select_for_update().get(pk=getattr(tenant, "pk", tenant))
    except Tenant.DoesNotExist:
        raise SubscriptionManagementError("tenant_not_found", "الشركة غير موجودة.")
    existing = ServiceSubscription.objects.select_for_update().filter(tenant_id=tenant_obj.pk).first()
    if existing:
        code = "trial_already_used" if existing.trial_started_at else "subscription_already_exists"
        raise SubscriptionManagementConflict(code, "لا يمكن بدء تجربة جديدة لهذه الشركة.")

    plan_name = _normalize_plan(plan) or DEFAULT_SERVICE_PLAN
    active_policy = get_active_subscription_policy(plan=plan_name)
    if active_policy is None:
        raise SubscriptionManagementError("subscription_policy_missing", "فعّل سياسة اشتراك قبل بدء تجربة.")
    if not active_policy.trial_days:
        raise SubscriptionManagementError("trial_not_configured", "السياسة الفعالة لا تمنح أيام تجربة.")
    _require_active_service_unit_catalog()

    now = timezone.now()
    try:
        subscription = ServiceSubscription.objects.create(
            tenant=tenant_obj,
            status=ServiceSubscription.Status.TRIAL,
            plan=plan_name,
            fixed_fee_product_id=active_policy.fixed_fee_product_id,
            overage_product_id=active_policy.overage_product_id,
            monthly_fee=active_policy.monthly_fee,
            included_quota=active_policy.included_quota,
            overage_unit_price=active_policy.overage_unit_price,
            trial_days=active_policy.trial_days,
            trial_started_at=now,
            trial_ends_at=now + datetime.timedelta(days=active_policy.trial_days),
            billing_tenant=active_policy.billing_tenant,
            subscription_policy_version=active_policy.version,
        )
    except IntegrityError:
        raise SubscriptionManagementConflict(
            "subscription_activation_conflict",
            "يوجد تفعيل متزامن لهذه الشركة؛ أعد تحميل الاشتراك.",
        )
    _log_subscription_event(
        subscription,
        action=ServiceSubscriptionEvent.Action.TRIAL_STARTED,
        from_status="",
        to_status=ServiceSubscription.Status.TRIAL,
        actor=actor,
        correlation_id=correlation_id,
        details={"trial_days": active_policy.trial_days},
    )
    return subscription


@transaction.atomic
def activate_paid_subscription(
    *, tenant, billing_customer=None, plan: str | None = None, actor=None, correlation_id: str = "",
) -> ServiceSubscription:
    """يفعّل اشتراكاً مدفوعاً من لا شيء أو من تجربة أو من ملغى — لا يمنح تجربة ثانية أبداً.

    يخدم هذا المسار كلاً من «تفعيل مدفوع مباشر» و«تحويل التجربة إلى مدفوع»:
    الفارق بينهما حالة المصدر وحدها، والانتقال والسجل نفسهما. تحويل التجربة
    **يبقي لقطة أسعارها** كما التُقطت لحظة بدئها، بينما التفعيل من لا شيء أو
    من اشتراكٍ ملغىً يلتقط نسخة السياسة الفعّالة الآن (§٣: الأسعار القديمة
    المجمَّدة على صفٍّ ملغىً لا تصحّ لإحيائه). وكل دخولٍ إلى `active` هنا يضبط
    دورة فوترة أولى جديدة تبدأ أول الشهر الميلادي التالي بلا استثناء
    (`_first_billing_period_after_activation`) — لا فوترة جزئية لبقيّة شهر
    التفعيل نفسه.
    """
    # قفلُ صفّ الشركة الموجود أولاً يُسلسل التفعيل: قفلُ صفّ اشتراكٍ غير موجود على MySQL
    # يأخذ gap lock فتتشابك معاملتان تُدرجان معاً (1213) بدل أن تنتظر إحداهما الأخرى.
    try:
        tenant_obj = Tenant.objects.select_for_update().get(pk=getattr(tenant, "pk", tenant))
    except Tenant.DoesNotExist:
        raise SubscriptionManagementError("tenant_not_found", "الشركة غير موجودة.")
    locked = ServiceSubscription.objects.select_for_update().filter(tenant_id=tenant_obj.pk).first()
    if locked and locked.status == ServiceSubscription.Status.ACTIVE:
        raise SubscriptionManagementConflict("subscription_already_active", "اشتراك الشركة نشط بالفعل.")
    if locked and locked.status == ServiceSubscription.Status.SUSPENDED:
        raise SubscriptionManagementConflict("subscription_suspended", "استأنف الاشتراك المعلق أولاً.")

    previous_status = locked.status if locked else ""
    is_trial_conversion = previous_status == ServiceSubscription.Status.TRIAL
    cleared_scheduled_cancellation_date = locked.scheduled_cancellation_date if locked else None
    # إعادة التفعيل من "لا شيء" أو من "ملغى" تلتقط سياسة اليوم؛ تحويل التجربة وحده يُبقي لقطتها.
    needs_fresh_snapshot = not is_trial_conversion
    requested_plan = _normalize_plan(plan)
    if is_trial_conversion and requested_plan and requested_plan != locked.plan:
        raise SubscriptionManagementError(
            "plan_fixed_by_trial",
            "تحويل التجربة يُبقي خطتها وأسعارها الملتقطة؛ لتغيير الخطة ألغِ التجربة ثم فعّل اشتراكاً جديداً.",
        )
    plan_name = (
        locked.plan if is_trial_conversion
        else requested_plan or (locked.plan if locked else "") or DEFAULT_SERVICE_PLAN
    )

    active_policy = get_active_subscription_policy(plan=plan_name) if needs_fresh_snapshot else None
    if needs_fresh_snapshot and active_policy is None:
        raise SubscriptionManagementError(
            "subscription_policy_missing", "فعّل سياسة اشتراك قبل إنشاء اشتراك خدمة جديد.",
        )
    _require_active_service_unit_catalog()

    billing_tenant_id = active_policy.billing_tenant_id if needs_fresh_snapshot else locked.billing_tenant_id
    if billing_customer is None:
        raise BillingConfigurationError("billing_customer_required", "عميل الفوترة مطلوب للتفعيل المدفوع.", status_code=400)
    validate_billing_customer_for_subscription(
        customer=billing_customer, tenant_id=tenant_obj.pk, billing_tenant_id=billing_tenant_id,
    )

    period_start, period_end = _first_billing_period_after_activation(timezone.localdate())

    locked_existed = locked is not None
    if locked is None:
        try:
            locked = ServiceSubscription.objects.create(
                tenant=tenant_obj,
                status=ServiceSubscription.Status.ACTIVE,
                plan=plan_name,
                monthly_fee=active_policy.monthly_fee,
                included_quota=active_policy.included_quota,
                overage_unit_price=active_policy.overage_unit_price,
                billing_customer=billing_customer,
                billing_tenant=active_policy.billing_tenant,
                subscription_policy_version=active_policy.version,
                fixed_fee_product_id=active_policy.fixed_fee_product_id,
                overage_product_id=active_policy.overage_product_id,
                period_start=period_start,
                period_end=period_end,
            )
        except IntegrityError:
            raise SubscriptionManagementConflict(
                "subscription_activation_conflict",
                "يوجد تفعيل متزامن لهذه الشركة؛ أعد تحميل الاشتراك.",
            )
    else:
        previous_terms = {
            "plan": locked.plan,
            "monthly_fee": str(locked.monthly_fee),
            "included_quota": locked.included_quota,
            "overage_unit_price": str(locked.overage_unit_price),
            "billing_tenant_id": locked.billing_tenant_id,
            "billing_customer_id": locked.billing_customer_id,
            "subscription_policy_version": locked.subscription_policy_version,
        }
        locked.status = ServiceSubscription.Status.ACTIVE
        locked.scheduled_cancellation_date = None
        locked.cancellation_reason = ""
        locked.pre_suspension_status = ""
        locked.consumed_quota = 0
        locked.period_start = period_start
        locked.period_end = period_end
        update_fields = [
            "status", "scheduled_cancellation_date", "cancellation_reason", "pre_suspension_status",
            "consumed_quota", "period_start", "period_end", "updated_at",
        ]
        locked.billing_customer = billing_customer
        locked.plan = plan_name
        update_fields += ["billing_customer", "plan"]
        if needs_fresh_snapshot:
            locked.monthly_fee = active_policy.monthly_fee
            locked.included_quota = active_policy.included_quota
            locked.overage_unit_price = active_policy.overage_unit_price
            locked.billing_tenant = active_policy.billing_tenant
            locked.subscription_policy_version = active_policy.version
            locked.fixed_fee_product_id = active_policy.fixed_fee_product_id
            locked.overage_product_id = active_policy.overage_product_id
            update_fields += [
                "monthly_fee", "included_quota", "overage_unit_price",
                "billing_tenant", "subscription_policy_version", "fixed_fee_product", "overage_product",
            ]
        locked.save(update_fields=update_fields)

    action = (
        ServiceSubscriptionEvent.Action.TRIAL_CONVERTED
        if is_trial_conversion
        else ServiceSubscriptionEvent.Action.ACTIVATED
    )
    _log_subscription_event(
        locked,
        action=action,
        from_status=previous_status,
        to_status=ServiceSubscription.Status.ACTIVE,
        actor=actor,
        correlation_id=correlation_id,
        details={
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            **({"cleared_scheduled_cancellation_date": cleared_scheduled_cancellation_date.isoformat()}
               if is_trial_conversion and cleared_scheduled_cancellation_date else {}),
            # إعادة تفعيل صفٍّ ملغى تستبدل شروطه التجارية — الشروط السابقة تبقى هنا لا تُمحى.
            **({"previous_terms": previous_terms} if locked_existed and needs_fresh_snapshot else {}),
        },
    )
    return locked


@transaction.atomic
def suspend_service_subscription(
    *, subscription, reason: str, actor=None, correlation_id: str = "",
) -> ServiceSubscription:
    """يعلّق تجربة أو اشتراكاً نشطاً فوراً — يوقف عملاً جديداً ويحفظ الدورة والتاريخ."""
    reason = str(reason or "").strip()
    if not reason:
        raise SubscriptionManagementError("reason_required", "سبب التعليق مطلوب.")
    return deactivate_service_subscription(
        subscription=subscription,
        new_status=ServiceSubscription.Status.SUSPENDED,
        reason=reason,
        actor=actor,
        correlation_id=correlation_id,
    )


@transaction.atomic
def resume_service_subscription(*, subscription, actor=None, correlation_id: str = "") -> ServiceSubscription:
    """يعيد اشتراكاً معلقاً إلى حالته السابقة الصالحة ويستأنف ما علّقه ذلك التعليق — لا يحيي ملغى.

    الاستئناف مقصور على الارتباطات التي سجّلها حدث التعليق الأخير
    (`suspended_engagement_ids`): ما علّقه مديرٌ يدوياً قبل تعليق الاشتراك يبقى معلَّقاً.
    وفشلُ ارتباطٍ بعينه (موظف خرج من الخدمة مثلاً) لا يُسقط الاستئناف — يُسجَّل في الحدث.
    """
    locked = ServiceSubscription.objects.select_for_update().get(pk=getattr(subscription, "pk", subscription))
    if locked.status != ServiceSubscription.Status.SUSPENDED:
        raise SubscriptionManagementConflict("subscription_not_suspended", "الاشتراك ليس معلقاً.")
    target_status = locked.pre_suspension_status or ServiceSubscription.Status.ACTIVE
    locked.status = target_status
    locked.pre_suspension_status = ""
    locked.save(update_fields=["status", "pre_suspension_status", "updated_at"])

    last_suspension = (
        ServiceSubscriptionEvent.objects.filter(
            subscription=locked, action=ServiceSubscriptionEvent.Action.SUSPENDED,
        )
        .order_by("-pk")
        .first()
    )
    to_resume = list((last_suspension.details or {}).get("suspended_engagement_ids", []) if last_suspension else [])
    resumed_engagement_ids, failed_engagements = [], []
    for engagement_id in to_resume:
        try:
            resume_engagement(engagement=engagement_id, actor=actor, correlation_id=correlation_id)
            resumed_engagement_ids.append(engagement_id)
        except PlatformOpsError as exc:
            failed_engagements.append({"engagement": engagement_id, "code": exc.code})

    _log_subscription_event(
        locked,
        action=ServiceSubscriptionEvent.Action.RESUMED,
        from_status=ServiceSubscription.Status.SUSPENDED,
        to_status=target_status,
        actor=actor,
        correlation_id=correlation_id,
        details={
            "resumed_engagement_ids": resumed_engagement_ids,
            "failed_engagements": failed_engagements,
        },
    )
    return locked


@transaction.atomic
def schedule_service_subscription_cancellation(
    *, subscription, reason: str, actor=None, correlation_id: str = "", immediate: bool = False,
) -> ServiceSubscription:
    """يجدول الإلغاء لنهاية الدورة/التجربة افتراضياً، أو يلغي فوراً إن طُلب صراحةً."""
    reason = str(reason or "").strip()
    if not reason:
        raise SubscriptionManagementError("reason_required", "سبب الإلغاء مطلوب.")
    locked = ServiceSubscription.objects.select_for_update().get(pk=getattr(subscription, "pk", subscription))
    if locked.status == ServiceSubscription.Status.CANCELLED:
        raise SubscriptionManagementConflict("subscription_already_cancelled", "الاشتراك ملغى بالفعل.")

    if immediate:
        return deactivate_service_subscription(
            subscription=locked,
            new_status=ServiceSubscription.Status.CANCELLED,
            reason=reason,
            actor=actor,
            correlation_id=correlation_id,
        )

    scheduled_for = _default_scheduled_cancellation_date(locked)
    locked.scheduled_cancellation_date = scheduled_for
    locked.cancellation_reason = reason
    locked.save(update_fields=["scheduled_cancellation_date", "cancellation_reason", "updated_at"])
    _log_subscription_event(
        locked,
        action=ServiceSubscriptionEvent.Action.CANCELLATION_SCHEDULED,
        from_status=locked.status,
        to_status=locked.status,
        reason=reason,
        actor=actor,
        correlation_id=correlation_id,
        details={"scheduled_cancellation_date": scheduled_for.isoformat()},
    )
    return locked


@transaction.atomic
def withdraw_scheduled_service_cancellation(
    *, subscription, actor=None, correlation_id: str = "",
) -> ServiceSubscription:
    """يسحب إلغاءً مجدولاً لم يُطبَّق بعد."""
    locked = ServiceSubscription.objects.select_for_update().get(pk=getattr(subscription, "pk", subscription))
    if not locked.scheduled_cancellation_date:
        raise SubscriptionManagementError("no_scheduled_cancellation", "لا يوجد إلغاء مجدول لسحبه.")
    locked.scheduled_cancellation_date = None
    locked.cancellation_reason = ""
    locked.save(update_fields=["scheduled_cancellation_date", "cancellation_reason", "updated_at"])
    _log_subscription_event(
        locked,
        action=ServiceSubscriptionEvent.Action.CANCELLATION_WITHDRAWN,
        from_status=locked.status,
        to_status=locked.status,
        actor=actor,
        correlation_id=correlation_id,
    )
    return locked


def apply_due_subscription_cancellations(now: datetime.datetime | None = None) -> dict:
    """يطبّق كل إلغاء مجدول حان أجله — idempotent، ولا يُستدعى من مسار dry-run.

    `scheduled_cancellation_date` هو **آخر يوم خدمةٍ يشمله**، فيُطبَّق الإلغاء
    بعد انقضائه فعلاً (`< اليوم` لا `<=`) — وإلا سقطت الخدمة قبل نهاية اليوم
    الذي لا يزال العميل يملك حقاً فيه. يُستدعى هذا **بعد** تمرير الفوترة الشهرية
    لا قبله: تجميدُ الاشتراك أولاً كان يُسقط فاتورة آخر شهرٍ مستحقّ بالكامل رغم
    أن المواصفة §١ تنصّ على بقاء الخدمة حتى نهاية الدورة بلا استرداد جزئي.

    **ولا يُلغى اشتراك نشط قبل فوترة دورته الأخيرة**: الفوترة الناجحة تنقل
    `period_start` إلى الشهر التالي، فإن بقي `period_start <= scheduled_cancellation_date`
    فالدورة التي تضم آخر يوم خدمة لم تُفوتر بعد (تشغيل محصور بـ`--tenant`/`--subscription`،
    أو خطأ إعداد، أو دورة خاطئة) — يُؤجَّل الإلغاء إلى تشغيل لاحق بدل أن يُسقط فاتورتها
    للأبد (`billing_preflight` لا يفوتر إلا `active`). المعلّق والتجربة لا يُفوتران أصلاً.

    كل صف يُقفل ويُعاد فحصه في معاملته، وخطأ النطاق (`PlatformOpsError`) في صف واحد يُسجَّل
    في `failed` ولا يوقف بقية الدفعة.
    """
    moment = now or timezone.now()
    today = timezone.localtime(moment).date() if timezone.is_aware(moment) else moment.date()
    candidates = ServiceSubscription.objects.filter(
        scheduled_cancellation_date__isnull=False,
        scheduled_cancellation_date__lt=today,
    ).exclude(status=ServiceSubscription.Status.CANCELLED)

    applied_ids = []
    awaiting_final_billing_ids = []
    failed = []
    for sub in candidates:
        try:
            with transaction.atomic():
                locked = ServiceSubscription.objects.select_for_update().get(pk=sub.pk)
                if locked.status == ServiceSubscription.Status.CANCELLED:
                    continue
                if not locked.scheduled_cancellation_date or locked.scheduled_cancellation_date >= today:
                    continue
                if (
                    locked.status == ServiceSubscription.Status.ACTIVE
                    and locked.period_start
                    and locked.period_start <= locked.scheduled_cancellation_date
                ):
                    awaiting_final_billing_ids.append(locked.pk)
                    continue
                reason = locked.cancellation_reason or "تطبيق إلغاء مجدول تلقائياً عند نهاية الدورة"
                deactivate_service_subscription(
                    subscription=locked,
                    new_status=ServiceSubscription.Status.CANCELLED,
                    reason=reason,
                    actor=None,
                    correlation_id=f"auto-cancel-{locked.pk}",
                )
                applied_ids.append(locked.pk)
        except PlatformOpsError as exc:
            # خطأ نطاق في صفّ واحد (مثل تعارض حالة) لا يوقف بقية الدفعة ولا يُسقط الأمر بعد فوترةٍ اعتُمدت.
            failed.append({"subscription_id": sub.pk, "code": exc.code})
            logger.warning(
                "platform.subscription_auto_cancel_failed subscription=%s code=%s", sub.pk, exc.code,
            )
    return {
        "applied_count": len(applied_ids),
        "applied_subscription_ids": applied_ids,
        "awaiting_final_billing_subscription_ids": awaiting_final_billing_ids,
        "failed": failed,
    }


@transaction.atomic
def update_subscription_commercial_settings(
    *, subscription, actor=None, correlation_id: str = "", reason: str = "", **changes,
) -> ServiceSubscription:
    """يحدّث شروط اشتراك بعينه (تفاوض خاص) بسبب إلزامي دون تغيير حالته.

    تعديل الأسعار هنا استثناء لهذا الصف لا تعديلٌ للسياسة: `subscription_policy_version`
    يبقى مصدر اللقطة الأصلية، والانحراف عنها وسببه في حدث `settings_updated`.
    الاشتراك الملغى لا تُعدَّل شروطه — إعادة تفعيله تلتقط السياسة السارية.
    """
    subscription_id = getattr(subscription, "pk", subscription)
    locked = ServiceSubscription.objects.select_for_update().get(pk=subscription_id)
    allowed = {"plan", "monthly_fee", "included_quota", "overage_unit_price", "billing_customer"}
    unknown = set(changes) - allowed
    if unknown:
        raise SubscriptionManagementError("unsupported_field", "يوجد حقل تجاري غير مسموح بتعديله.")
    if not changes:
        return locked
    if locked.status == ServiceSubscription.Status.CANCELLED:
        raise SubscriptionManagementConflict(
            "subscription_cancelled", "لا تُعدَّل شروط اشتراك ملغى؛ أعد تفعيله باشتراك مدفوع جديد.",
        )
    if "billing_customer" in changes:
        if changes["billing_customer"] is None and locked.status != ServiceSubscription.Status.TRIAL:
            # اشتراكٌ مدفوع بلا عميل فوترة لا يُفوتَر أبداً — لا يُسمح بتفريغه.
            raise SubscriptionManagementError("billing_customer_required", "عميل الفوترة مطلوب للاشتراك المدفوع.")
        # سياسةُ نطاق الخطة نفسِها لا العامّة — وإلا تحقّقنا بشركةِ فوترةٍ غير التي يبحث فيها المنتقي.
        billing_tenant_id = locked.billing_tenant_id or getattr(
            get_active_subscription_policy(plan=locked.plan), "billing_tenant_id", None,
        )
        validate_billing_customer_for_subscription(
            customer=changes["billing_customer"],
            tenant_id=locked.tenant_id,
            billing_tenant_id=billing_tenant_id,
        )
    if "plan" in changes:
        changes["plan"] = str(changes["plan"] or "").strip()
        if not changes["plan"]:
            raise SubscriptionManagementError("plan", "اسم الباقة مطلوب.")
    if "monthly_fee" in changes:
        changes["monthly_fee"] = _validate_subscription_decimal(changes["monthly_fee"], "monthly_fee")
    if "overage_unit_price" in changes:
        changes["overage_unit_price"] = _validate_subscription_decimal(changes["overage_unit_price"], "overage_unit_price")
    if "included_quota" in changes:
        changes["included_quota"] = _validate_included_quota(changes["included_quota"])
    def audit_value(field, value):
        # JSONField لا يشفّر Decimal؛ نمثل المال نصاً دقيقاً لا float.
        return str(value) if field in {"monthly_fee", "overage_unit_price"} and value is not None else value

    def stored_value(field):
        return getattr(locked, f"{field}_id" if field == "billing_customer" else field)

    def incoming_value(field):
        value = changes[field]
        return getattr(value, "pk", value) if field == "billing_customer" else value

    # حقلٌ أُرسل بقيمته الحالية ليس تعديلاً: لا يدخل الحفظ ولا حدث التدقيق.
    changes = {field: value for field, value in changes.items() if incoming_value(field) != stored_value(field)}
    if not changes:
        return locked
    reason = str(reason or "").strip()
    if not reason:
        raise SubscriptionManagementError("reason_required", "سبب تعديل شروط الاشتراك مطلوب.")

    before = {field: audit_value(field, stored_value(field)) for field in changes}
    for field, value in changes.items():
        setattr(locked, field, value)
    locked.save(update_fields=[*changes.keys(), "updated_at"])
    _log_subscription_event(
        locked,
        action=ServiceSubscriptionEvent.Action.SETTINGS_UPDATED,
        from_status=locked.status,
        to_status=locked.status,
        reason=reason,
        actor=actor,
        correlation_id=correlation_id,
        details={
            "changes": {
                field: {
                    "before": before[field],
                    "after": audit_value(
                        field,
                        getattr(locked, f"{field}_id" if field == "billing_customer" else field),
                    ),
                }
                for field in sorted(changes)
            },
        },
    )
    logger.info(
        "platform.subscription_settings_updated subscription=%s tenant=%s fields=%s actor=%s",
        locked.pk,
        locked.tenant_id,
        ",".join(sorted(changes)),
        getattr(actor, "pk", None),
    )
    return locked


class BillingPeriodError(BillingError):
    """خطأ في دورة الفوترة (طلب دورة غير مطابقة لدورة الاشتراك أو اشتراك غير نشط)."""

    pass


class RatingTokenNotFound(PlatformOpsError):
    """الرمز غير موجود أو غير صالح => 404 (طابق سابقة docshare)."""

    def __init__(self, detail: str = "الرابط غير صالح أو غير موجود."):
        super().__init__("token_not_found", detail, status_code=404)


class RatingTokenGone(PlatformOpsError):
    """الرمز انتهت صلاحيته أو أُبطل => 410 (طابق سابقة docshare)."""

    def __init__(self, detail: str = "انتهت صلاحية هذا الرابط."):
        super().__init__("token_expired", detail, status_code=410)


class JobGone(Exception):
    """انتهت فترة التقديم على الوظيفة أو أُغلقت (410)."""


class InvitationGone(Exception):
    """رابط الدعوة مستهلك أو منتهي الصلاحية (410)."""



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
    locked_eng: Engagement, revoked_by=None, reason: str = "", end_reason: str | None = None,
) -> Engagement:
    """تنفيذ الإلغاء على ارتباط مقفول مسبقاً دون إعادة طلب الأقفال.

    `ended_at`/`end_reason` (210-B) طابعُ نهاية الارتباط العامّ — يُكتب في كل مسار
    إلغاءٍ مهما كان مصدره (مباشر، نقل، مغادرة موظف، أو تعليق اشتراك)، بينما
    `revoked_at`/`revocation_reason` يبقيان الحقل التاريخي المحدَّد.
    """
    now = timezone.now()
    locked_eng.status = Engagement.Status.REVOKED
    locked_eng.revoked_at = now
    locked_eng.revoked_by = revoked_by
    locked_eng.revocation_reason = str(reason)[:2000]
    locked_eng.ended_at = now
    locked_eng.end_reason = str(end_reason if end_reason is not None else reason)[:500]

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
            "ended_at",
            "end_reason",
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
    kind: str = Engagement.Kind.STANDARD,
    capacity_override_reason: str = "",
    correlation_id: str = "",
) -> Engagement:
    """إسناد موظف منصة لشركة زبون.

    القواعد:
    1. ترتيب القفل: Subscription -> PlatformEmployee -> Engagement -> UserCompanyMembership.
    2. الإسناد مسموح فقط لاشتراك خدمة نشط ولموظف منصة نشط.
    3. فرادة الارتباط النشط تُفرض تحت قفل داخل معاملة ذرية.
    4. يوفر دور 'manager' للوكيل: إذا وُجدت عضوية قائمة بدور آخر، يُحفظ دورها السابق
       وتُرقى إلى 'manager'؛ أما إذا لم توجد، تُنشأ عضوية 'manager' جديدة ويسجل created_membership=True.
    5. (210-B) بلا فحصٍ تأسيسي معتمد يُرفض الإسناد العادي — استثناءً لـ`kind=onboarding`
       الموسوم والمؤرَّخ بحدٍّ أقصى `MAX_ONBOARDING_DAYS`. والطاقة المتوقّعة بعد الإسناد
       (حِملُ الموظف الحالي + وحدات حِمل هذه الشركة) تُرفض إن تجاوزت `capacity_target`
       بلا `capacity_override_reason`.
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    emp_pk = getattr(employee, "pk", employee)

    # 1. قفل والتحقق من اشتراك الخدمة
    subscription = (
        ServiceSubscription.objects.select_for_update()
        .filter(tenant=tenant_obj)
        .first()
    )
    if not is_service_subscription_eligible(subscription):
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

    kind = kind or Engagement.Kind.STANDARD
    if kind not in Engagement.Kind.values:
        raise EngagementError("invalid_kind", f"نوع الارتباط غير صالح: {kind}")

    onboarding_expires_at = None
    if kind == Engagement.Kind.ONBOARDING:
        onboarding_expires_at = timezone.now() + datetime.timedelta(days=MAX_ONBOARDING_DAYS)
    elif latest_approved_baseline(tenant_obj) is None:
        raise EngagementError(
            "baseline_required",
            "يلزم فحص صحة تأسيسي معتمد قبل الإسناد التشغيلي؛ استخدم إسناد onboarding مؤقتاً بدلاً منه.",
        )

    capacity_override_reason = str(capacity_override_reason or "").strip()
    projected_load = Decimal(employee_capacity_snapshot(locked_employee)["load"]) + Decimal(_tenant_load_units(tenant_obj))
    if _would_exceed_capacity(locked_employee.capacity_target, projected_load) and not capacity_override_reason:
        raise EngagementConflict(
            "capacity_exceeded",
            "إسناد هذه الشركة يتجاوز الطاقة المستهدفة للموظف؛ أضف سبب تجاوز للمتابعة.",
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
        kind=kind,
        onboarding_expires_at=onboarding_expires_at,
        capacity_override_reason=capacity_override_reason,
        created_membership=created_membership,
        managed_membership=membership,
        previous_role=previous_role,
    )
    _log_operation_event(
        tenant_obj,
        domain=PlatformOperationEvent.Domain.ENGAGEMENT,
        action=PlatformOperationEvent.Action.ASSIGNED,
        subject_id=engagement.pk,
        actor=assigned_by,
        correlation_id=correlation_id,
        details={"employee_id": locked_employee.pk, "kind": kind},
    )

    return engagement


@transaction.atomic
def suspend_engagement(
    *,
    engagement: Engagement,
    reason: str = "",
    actor=None,
    correlation_id: str = "",
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

    result = _execute_suspend(locked, reason=reason)
    _log_operation_event(
        result.tenant_id,
        domain=PlatformOperationEvent.Domain.ENGAGEMENT,
        action=PlatformOperationEvent.Action.SUSPENDED,
        subject_id=result.pk,
        actor=actor,
        correlation_id=correlation_id,
        reason=reason,
    )
    return result


@transaction.atomic
def resume_engagement(
    *,
    engagement: Engagement,
    actor=None,
    correlation_id: str = "",
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
    if not is_service_subscription_eligible(subscription):
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
    _log_operation_event(
        locked.tenant_id,
        domain=PlatformOperationEvent.Domain.ENGAGEMENT,
        action=PlatformOperationEvent.Action.RESUMED,
        subject_id=locked.pk,
        actor=actor,
        correlation_id=correlation_id,
    )

    return locked


@transaction.atomic
def revoke_engagement(
    *,
    engagement: Engagement,
    revoked_by=None,
    reason: str = "",
    correlation_id: str = "",
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

    result = _execute_revoke(locked, revoked_by=revoked_by, reason=reason)
    _log_operation_event(
        result.tenant_id,
        domain=PlatformOperationEvent.Domain.ENGAGEMENT,
        action=PlatformOperationEvent.Action.REVOKED,
        subject_id=result.pk,
        actor=revoked_by,
        correlation_id=correlation_id,
        reason=reason,
    )
    return result


@transaction.atomic
def deactivate_service_subscription(
    *,
    subscription,
    new_status: str = ServiceSubscription.Status.SUSPENDED,
    reason: str = "تعليق/إلغاء اشتراك الخدمة",
    actor=None,
    correlation_id: str = "",
) -> ServiceSubscription:
    """إيقاف أو تعليق اشتراك خدمة المتابعة مع تعليق ارتباطاتها النشطة دون حذفها.

    ترتيب القفل: Subscription -> Engagements -> Memberships
    يستدعي _execute_suspend مباشرة على الارتباطات المقفولة لتجنب إعادة طلب الأقفال.
    المسار المنخفض المشترك بين تعليق مباشر وإلغاء فوري (مجدولاً كان أو مباشراً)؛
    الجدولة لنهاية الدورة تمر بـ`schedule_service_subscription_cancellation` لا هنا.
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
    previous_status = locked_sub.status
    if new_status == ServiceSubscription.Status.CANCELLED and previous_status == ServiceSubscription.Status.CANCELLED:
        raise SubscriptionManagementConflict("subscription_already_cancelled", "الاشتراك ملغى بالفعل.")
    if new_status == ServiceSubscription.Status.SUSPENDED and previous_status not in (
        ServiceSubscription.Status.TRIAL, ServiceSubscription.Status.ACTIVE,
    ):
        raise SubscriptionManagementConflict("subscription_not_suspendable", "لا يمكن تعليق اشتراك بهذه الحالة.")

    update_fields = ["status", "updated_at"]
    if new_status == ServiceSubscription.Status.SUSPENDED:
        locked_sub.pre_suspension_status = previous_status
        update_fields.append("pre_suspension_status")
    if new_status == ServiceSubscription.Status.CANCELLED:
        locked_sub.scheduled_cancellation_date = None
        locked_sub.cancellation_reason = reason
        update_fields.extend(["scheduled_cancellation_date", "cancellation_reason"])
    locked_sub.status = new_status
    locked_sub.save(update_fields=update_fields)

    # قفل وتعليق كافة الارتباطات النشطة لهذه الشركة
    active_engagements = (
        Engagement.objects.select_for_update()
        .filter(tenant_id=locked_sub.tenant_id, status=Engagement.Status.ACTIVE)
        .order_by("pk")
    )
    # المعرّفات تُحفظ في الحدث كي يستأنف `resume_service_subscription` ما علّقه التعليق
    # وحده — لا كلَّ ارتباطٍ معلَّق، فالمعلَّق يدوياً قبله يبقى معلَّقاً.
    suspended_engagement_ids = []
    for eng in active_engagements:
        _execute_suspend(eng, reason=reason)
        suspended_engagement_ids.append(eng.pk)
        # التعليقُ عبر الاشتراك يكتب حدثَ الارتباط نفسه الذي يكتبه `suspend_engagement`:
        # سجلُّ 210-B الموحّد لا يعرف مَن علّق الارتباط إن سكت هذا المسار.
        _log_operation_event(
            locked_sub.tenant_id,
            domain=PlatformOperationEvent.Domain.ENGAGEMENT,
            action=PlatformOperationEvent.Action.SUSPENDED,
            subject_id=eng.pk,
            actor=actor,
            correlation_id=correlation_id,
            reason=reason,
            details={"source": "subscription_deactivation", "subscription_id": locked_sub.pk},
        )

    _log_subscription_event(
        locked_sub,
        action=(
            ServiceSubscriptionEvent.Action.SUSPENDED
            if new_status == ServiceSubscription.Status.SUSPENDED
            else ServiceSubscriptionEvent.Action.CANCELLED
        ),
        from_status=previous_status,
        to_status=new_status,
        reason=reason,
        actor=actor,
        correlation_id=correlation_id,
        details={"suspended_engagement_ids": suspended_engagement_ids},
    )
    logger.info(
        "platform.subscription_status_changed subscription=%s tenant=%s from_status=%s to_status=%s actor=%s",
        locked_sub.pk,
        locked_sub.tenant_id,
        previous_status,
        new_status,
        getattr(actor, "pk", None),
    )

    return locked_sub


@transaction.atomic
def offboard_platform_employee(
    *,
    employee: PlatformEmployee,
    actor=None,
    reason: str = "إنهاء خدمة موظف المنصة (مغادرة)",
    correlation_id: str = "",
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
        # كالتعليق عبر الاشتراك: الإلغاءُ عبر المغادرة يكتب حدثَ `revoke_engagement` نفسه،
        # وإلا اختفت شركاتٌ من خدمة موظفٍ بلا أثرٍ في السجل الموحّد.
        _log_operation_event(
            eng.tenant_id,
            domain=PlatformOperationEvent.Domain.ENGAGEMENT,
            action=PlatformOperationEvent.Action.REVOKED,
            subject_id=eng.pk,
            actor=actor,
            correlation_id=correlation_id,
            reason=reason,
            details={"source": "employee_offboarding", "employee_id": locked_employee.pk},
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
    priority: str = WorkOrder.Priority.NORMAL,
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

    if priority not in WorkOrder.Priority.values:
        raise WorkOrderError("invalid_priority", f"أولوية أمر العمل غير صالحة: {priority}")

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
        priority=priority,
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
    document_link_ids: list[int] | None = None,
) -> WorkOrderDeliverable:
    """تسليم مخرج لأمر العمل مع حفظ لقطة ثابتة غير قابلة للتعديل اللاحق.

    `document_link_ids` (٢١٠-ج، القصة ٣٦): روابطُ مستنداتٍ **موجودةٌ سلفاً**
    (`link_work_order_document`) تُعاد تعليقُها على هذا المُسلَّم. إعادةُ تسليمٍ
    بعد رفضٍ بسبب خطأ الموظف تُعيد **نفس** معرّفات الروابط لا روابطَ جديدة، فيبقى
    مفتاح idempotency لدفتر الاستخدام واحداً ولا يُحتسب المصدر مرتين؛ ربطٌ جديدٌ
    (بمعرّف مستندٍ آخر) هو ما يمثّل طلباً جديداً قابلاً للاحتساب من جديد.
    """
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

    if document_link_ids:
        locked_links = list(
            WorkOrderDocumentLink.objects.select_for_update().filter(
                pk__in=document_link_ids, work_order_id=work_order.pk,
            )
        )
        found_ids = {link.pk for link in locked_links}
        missing = [lid for lid in document_link_ids if lid not in found_ids]
        if missing:
            raise WorkOrderDocumentLinkError(
                "document_link_not_found", f"روابط مستندات غير موجودة لهذا الأمر: {missing}",
            )
        WorkOrderDocumentLink.objects.filter(pk__in=found_ids).update(deliverable=deliv)

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
    rejection_category: str = "",
) -> WorkOrderDeliverable:
    """مراجعة مُسلَّم أمر العمل (قبول أو رفض مع سبب صريح).

    `rejection_category` (٢١٠-ج، القصة ١٤) اختياريٌّ هنا على مستوى الخدمة كي لا
    ينكسر مسارٌ قديم كان يرفض بسببٍ نصّيٍّ وحده؛ نقطةُ الكتابة الجديدة في الواجهة
    (`WorkOrderViewSet.review_deliverable`) هي التي تفرضه إلزامياً عند الرفض.
    """
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

    if rejection_category and rejection_category not in WorkOrderDeliverable.RejectionCategory.values:
        raise WorkOrderError("invalid_rejection_category", f"تصنيف سبب الرفض غير صالح: {rejection_category}")

    deliv_pk = getattr(deliverable, "pk", deliverable)
    locked_deliv = WorkOrderDeliverable.objects.select_for_update().get(pk=deliv_pk)
    locked_deliv.review_status = review_status
    locked_deliv.reviewed_by = reviewed_by
    locked_deliv.reviewed_at = timezone.now()
    locked_deliv.rejection_reason = (rejection_reason or "").strip()
    locked_deliv.rejection_category = rejection_category if review_status == WorkOrderDeliverable.ReviewStatus.REJECTED else ""
    locked_deliv.save(
        update_fields=[
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "rejection_category",
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
    if not is_service_subscription_eligible(subscription):
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

# محاور التقييم الرسمية الخمسة حرفياً وفق #207 §8 و#203
AXIS_KPI_RESULTS = "kpi_results"                  # محور نتائج الأداء والـKPI (الإنتاجية المنجزة) - 30%
AXIS_QUALITY = "quality"                          # محور الجودة (نسبة القبول من أول مراجعة) - 25%
AXIS_CUSTOMER_RATING = "customer_rating"          # محور تقييم الزبون (المرحلة السابعة §١٠) - 20%
AXIS_SLA_COMPLIANCE = "sla_compliance"            # محور الالتزام بالأجل - 15%
AXIS_ATTENDANCE_REGULARITY = "attendance_regularity"  # محور الحضور والانضباط الفعلي - 10%

# توافق رجعي مع التسميات السابقة
AXIS_PRODUCTIVITY = AXIS_KPI_RESULTS
AXIS_ATTENDANCE = AXIS_ATTENDANCE_REGULARITY

# المقاييس التشخيصية القديمة تبقى كثوابت لمن يستوردها ولكن ليست محاور رسمية
AXIS_SPEED_EFFICIENCY = "speed_efficiency"
AXIS_SALES_VALUE = "sales_value"

ALL_PERFORMANCE_AXES = (
    AXIS_KPI_RESULTS,
    AXIS_QUALITY,
    AXIS_CUSTOMER_RATING,
    AXIS_SLA_COMPLIANCE,
    AXIS_ATTENDANCE_REGULARITY,
)

DEFAULT_AXIS_WEIGHTS: dict[str, Decimal] = {
    AXIS_KPI_RESULTS: Decimal("30.00"),
    AXIS_QUALITY: Decimal("25.00"),
    AXIS_CUSTOMER_RATING: Decimal("20.00"),
    AXIS_SLA_COMPLIANCE: Decimal("15.00"),
    AXIS_ATTENDANCE_REGULARITY: Decimal("10.00"),
}

# المقاييس الستة — قائمة مغلقة لأوامر العمل ومُسلَّماتها (والتقييم محورٌ لا مقياس أمر عمل)
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

# ==============================================================================
# محاور سياسة تقييم الـpilot (210-D، §٥) — أربعة محاور مستقلة عن #207 عمداً.
#
# **لا تُخلط بـALL_PERFORMANCE_AXES/DEFAULT_AXIS_WEIGHTS أعلاه**: تلك محاور
# #207 الخمسة القديمة وتبقى دون تعديل (§١٣: لا يُعاد بناء لقطاتها ولا يتغيّر
# معناها بأثر رجعي). هذه سياسةٌ جديدة تُقاس بصيغٍ مختلفة تماماً (دفتر الاستخدام
# وتصنيف الرفض بدل عدّ أوامر العمل المعتمدة)، فسُمّيت محاورها بأسماء مختلفة
# عمداً («quality_accuracy» لا «quality») كي لا يظن قارئ policy_snapshot/axes_data
# أنّ رقماً من نظامٍ يقارَن مباشرة برقمٍ من الآخر.
# ==============================================================================
PILOT_AXIS_TASK_COMPLETION = "task_completion"      # إنجاز العمل المقبول - 40%
PILOT_AXIS_QUALITY = "quality_accuracy"             # الدقة والجودة - 30%
PILOT_AXIS_SLA = "sla_adherence"                    # الالتزام بالـSLA - 20%
PILOT_AXIS_SATISFACTION = "customer_satisfaction"   # رضا العملاء - 10%

ALL_PILOT_PERFORMANCE_AXES = (
    PILOT_AXIS_TASK_COMPLETION,
    PILOT_AXIS_QUALITY,
    PILOT_AXIS_SLA,
    PILOT_AXIS_SATISFACTION,
)

DEFAULT_PILOT_AXIS_WEIGHTS: dict[str, Decimal] = {
    PILOT_AXIS_TASK_COMPLETION: Decimal("40.00"),
    PILOT_AXIS_QUALITY: Decimal("30.00"),
    PILOT_AXIS_SLA: Decimal("20.00"),
    PILOT_AXIS_SATISFACTION: Decimal("10.00"),
}


def redistribute_axis_weights(
    raw_weights: dict[str, Decimal | float | int | str],
    applicable_axes: set[str],
    all_axes: tuple[str, ...] = ALL_PERFORMANCE_AXES,
    default_weights: dict[str, Decimal] | None = None,
) -> dict[str, Decimal]:
    """إعادة توزيع الأوزان على المحاور المنطبقة بالتناسب ليكون المجموع 100.00% بالضبط.

    القاعدة:
    - المحور غير المنطبق يُسقط ويعاد توزيع وزنه على الباقي.
    - المجموع يبقى 100% بالضبط دون أي كسور تقريب ضائعة؛ يُضاف فرق التقريب للمحور الأكبر وزناً.

    `all_axes`/`default_weights` توسيعٌ (210-D) يسمح بإعادة استعمال المنطق نفسه
    لعوالم محاورَ أخرى (محاور الـpilot الأربعة) بلا تكرار الخوارزمية — الاستدعاء
    القديم بلا هذين المعطيين يعمل بالضبط كما كان (محاور #207 الخمسة).
    """
    default_weights = default_weights if default_weights is not None else DEFAULT_AXIS_WEIGHTS
    # **محورٌ منطبقٌ غائبٌ عن أوزان السياسة يأخذ وزنَه الافتراضيَّ لا صفراً**: كان
    # `axis in raw_weights` يُسقطه من التوزيع فيبقى «منطبقاً» بوزنٍ صفريّ — المجموعُ
    # يبقى ١٠٠ فيمرّ الاختبارُ المفروض، والتفصيلُ يعرض محوراً منطبقاً لا يساهم بشيء.
    applicable = [axis for axis in all_axes if axis in applicable_axes]
    if not applicable:
        return {}

    def _weight_of(axis: str) -> Decimal:
        raw = raw_weights.get(axis)
        if raw is None:
            if axis == AXIS_KPI_RESULTS:
                raw = raw_weights.get("productivity")
            elif axis == AXIS_ATTENDANCE_REGULARITY:
                raw = raw_weights.get("attendance")
        if raw is None:
            raw = default_weights.get(axis, Decimal("0.00"))
        try:
            return Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            return default_weights.get(axis, Decimal("0.00"))

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

    # 5. تحديد المحاور المنطبقة وإعادة توزيع الأوزان (المحاور الخمسة الرسمية وفق #207 §8 و#203)
    applicable_axes: set[str] = set()
    axis_raw_scores: dict[str, Decimal] = {}

    # 1) محور نتائج الأداء والـKPI (الإنتاجية المنجزة) - 30%
    applicable_axes.add(AXIS_KPI_RESULTS)
    axis_raw_scores[AXIS_KPI_RESULTS] = volume_rate

    # 2) محور الجودة (نسبة القبول من أول مراجعة) - 25%
    applicable_axes.add(AXIS_QUALITY)
    axis_raw_scores[AXIS_QUALITY] = first_time_rate

    # 3) محور الالتزام بالأجل - 15%
    applicable_axes.add(AXIS_SLA_COMPLIANCE)
    axis_raw_scores[AXIS_SLA_COMPLIANCE] = sla_compliance_rate

    # 4) محور الحضور والانضباط الفعلي - 10%
    # ينطبق من صفوف الحضور الفعلية (hr.AttendanceDay) للموظف ضمن شركات ارتباطاته وفترته.
    # الحالات المجدولة: حاضر (present)، متأخر (late)، غائب (absent).
    # الدرجة = حاضر / (حاضر + متأخر + غائب) * 100، محصورة بين 0 و100.
    # إن لم توجد أيام حضور مجدولة، يُسقط المحور ويُعاد توزيع وزنه (10%) بالتناسب.
    attendance_base_qs = AttendanceDay.objects.filter(
        employee__user=employee.user,
        tenant_id__in=engaged_tenant_ids,
    )
    if start_date:
        attendance_base_qs = attendance_base_qs.filter(date__gte=start_date)
    if end_date:
        attendance_base_qs = attendance_base_qs.filter(date__lte=end_date)

    scheduled_qs = attendance_base_qs.filter(
        status__in=[
            AttendanceDay.STATUS_PRESENT,
            AttendanceDay.STATUS_LATE,
            AttendanceDay.STATUS_ABSENT,
        ]
    )
    att_agg = scheduled_qs.aggregate(
        scheduled_count=models.Count("id"),
        present_count=models.Count("id", filter=models.Q(status=AttendanceDay.STATUS_PRESENT)),
    )
    scheduled_count = att_agg["scheduled_count"] or 0
    present_count = att_agg["present_count"] or 0
    if scheduled_count > 0:
        attendance_score = min(
            Decimal("100.00"),
            max(
                Decimal("0.00"),
                (Decimal(present_count) / Decimal(scheduled_count) * Decimal("100.00")),
            ),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        applicable_axes.add(AXIS_ATTENDANCE_REGULARITY)
        axis_raw_scores[AXIS_ATTENDANCE_REGULARITY] = attendance_score

    # 5) محور تقييم الزبون (المرحلة السابعة §١٠) - 20%
    # ينطبق فقط إن كانت عينة تقييمات الموظف في الفترة >= min_sample_size (من PolicyProfile)
    # ودونها يُسقط ويُعاد توزيع وزنه بالتناسب مع بقية المحاور.
    ratings_base_qs = DailyRating.objects.filter(
        employee=employee,
        tenant_id__in=engaged_tenant_ids,
    )
    if start_date:
        ratings_base_qs = ratings_base_qs.filter(service_date__gte=start_date)
    if end_date:
        ratings_base_qs = ratings_base_qs.filter(service_date__lte=end_date)
    ratings_sample_size = ratings_base_qs.count()
    if ratings_sample_size >= min_sample_size:
        avg_stars = ratings_base_qs.aggregate(Avg("stars"))["stars__avg"] or 0.0
        rating_score = (
            (Decimal(str(avg_stars)) / Decimal("5.00")) * Decimal("100.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        applicable_axes.add(AXIS_CUSTOMER_RATING)
        axis_raw_scores[AXIS_CUSTOMER_RATING] = rating_score

    # إذا كانت السياسة تحدد أوزاناً صفرية لمحور معين، يُسقط المحور
    for axis in list(applicable_axes):
        w = raw_weights.get(axis)
        if w is None and axis == AXIS_KPI_RESULTS:
            w = raw_weights.get("productivity")
        elif w is None and axis == AXIS_ATTENDANCE_REGULARITY:
            w = raw_weights.get("attendance")
        if w is not None:
            try:
                declared = Decimal(str(w))
                if declared <= Decimal("0.00"):
                    applicable_axes.remove(axis)
            except (InvalidOperation, TypeError, ValueError):
                pass

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
# التذكرة 210-D (تابع): سياسة تقييم الـpilot — إدارة النسخ (§٥، §٨، §١١)
# ==============================================================================


def _validate_pilot_weights(weights) -> dict[str, Decimal]:
    """يتحقق أن أوزان المحاور الأربعة أرقامٌ غير سالبة ومجموعها 100.00% بالضبط.

    فحصُ المجموع هنا **لحظة الكتابة** (مسودة/تفعيل) — منفصلٌ عن إعادة التوزيع
    وقت الحساب الشهري (`redistribute_axis_weights`) التي تُسقط محوراً غير منطبق
    وتعيد توزيع وزنه؛ فحصنا هنا يضمن أن ما يكتبه السوبر أدمن نفسه صحيحٌ ابتداءً.
    """
    weights = weights or {}
    validated: dict[str, Decimal] = {}
    total = Decimal("0.00")
    for axis in ALL_PILOT_PERFORMANCE_AXES:
        raw = weights.get(axis, DEFAULT_PILOT_AXIS_WEIGHTS[axis])
        try:
            dec = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            raise PerformanceEvaluationPolicyError("invalid_weight", f"وزن غير صالح للمحور {axis}.")
        if not dec.is_finite() or dec < Decimal("0.00"):
            raise PerformanceEvaluationPolicyError("invalid_weight", f"وزن المحور {axis} لا يكون سالباً.")
        validated[axis] = dec
        total += dec
    if total != Decimal("100.00"):
        raise PerformanceEvaluationPolicyError(
            "weights_must_total_100",
            f"مجموع أوزان المحاور يجب أن يساوي 100% بالضبط (الحالي {total}).",
        )
    return validated


def _evaluation_policy_event_details(policy: PerformanceEvaluationPolicy) -> dict:
    return {
        "specialty": policy.specialty,
        "weights": policy.weights,
        "min_sample_size": policy.min_sample_size,
        "review_grace_period_hours": policy.review_grace_period_hours,
    }


def _log_evaluation_policy_event(policy, *, action, actor=None, correlation_id="", details=None):
    return PerformanceEvaluationPolicyEvent.objects.create(
        policy=policy,
        action=action,
        actor=actor if getattr(actor, "pk", None) else None,
        correlation_id=str(correlation_id or "")[:64],
        details=details or {},
    )


def get_active_performance_evaluation_policy(specialty: str = "", at: datetime.datetime | None = None):
    """نسخة سياسة تقييم الـpilot السارية لتخصص، بنفس اصطلاح `get_active_subscription_policy`."""
    moment = at or timezone.now()
    in_effect = (
        PerformanceEvaluationPolicy.objects
        .filter(status=PerformanceEvaluationPolicy.Status.ACTIVE, effective_from__lte=moment)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=moment))
    )
    specialty = str(specialty or "").strip()[:100]
    if specialty:
        specific = in_effect.filter(specialty=specialty).order_by("-version").first()
        if specific is not None:
            return specific
    return in_effect.filter(specialty="").order_by("-version").first()


def get_default_pilot_policy_dict(specialty: str = "") -> dict:
    """قاموس سياسة الـpilot الافتراضي (جدول القيم الافتراضية) حين لا توجد نسخة منشورة بعد."""
    return {
        "specialty": specialty,
        "weights": {k: float(v) for k, v in DEFAULT_PILOT_AXIS_WEIGHTS.items()},
        "min_sample_size": 5,
        "review_grace_period_hours": 48,
    }


def create_performance_evaluation_policy_draft(
    *,
    actor=None,
    specialty: str = "",
    weights=None,
    min_sample_size=_UNSET,
    review_grace_period_hours=_UNSET,
    correlation_id: str = "",
    cloned_from=None,
) -> PerformanceEvaluationPolicy:
    """ينشئ نسخة مسودة مؤرخة من سياسة تقييم الـpilot — لا `select_for_update`
    لحساب رقم النسخة، كنمط `create_service_unit_catalog_draft` بالضبط.
    """
    validated_weights = _validate_pilot_weights(
        weights if weights is not None else {k: float(v) for k, v in DEFAULT_PILOT_AXIS_WEIGHTS.items()}
    )
    if min_sample_size is _UNSET:
        min_sample_size = PerformanceEvaluationPolicy._meta.get_field("min_sample_size").default
    if review_grace_period_hours is _UNSET:
        review_grace_period_hours = PerformanceEvaluationPolicy._meta.get_field("review_grace_period_hours").default
    try:
        min_sample_size = int(min_sample_size)
        review_grace_period_hours = int(review_grace_period_hours)
    except (TypeError, ValueError):
        raise PerformanceEvaluationPolicyError("invalid_integer", "حد العينة ومهلة المراجعة أعداد صحيحة.")
    if min_sample_size < 1 or review_grace_period_hours < 0:
        raise PerformanceEvaluationPolicyError("invalid_integer", "حد العينة ومهلة المراجعة يجب أن تكونا صالحتين.")

    last_version = PerformanceEvaluationPolicy.objects.aggregate(Max("version"))["version__max"] or 0
    try:
        with transaction.atomic():
            policy = PerformanceEvaluationPolicy.objects.create(
                version=last_version + 1,
                status=PerformanceEvaluationPolicy.Status.DRAFT,
                specialty=str(specialty or "").strip()[:100],
                weights={k: str(v) for k, v in validated_weights.items()},
                min_sample_size=min_sample_size,
                review_grace_period_hours=review_grace_period_hours,
                created_by=actor if getattr(actor, "pk", None) else None,
            )
    except IntegrityError:
        raise PerformanceEvaluationPolicyConflict(
            "policy_version_conflict", "تعذر إنشاء نسخة سياسة تقييم جديدة؛ أعد المحاولة.",
        )
    details = {"after": _evaluation_policy_event_details(policy)}
    if cloned_from is not None:
        details["source_policy_id"] = cloned_from.pk
    _log_evaluation_policy_event(
        policy,
        action=(
            PerformanceEvaluationPolicyEvent.Action.CLONED if cloned_from is not None
            else PerformanceEvaluationPolicyEvent.Action.CREATED
        ),
        actor=actor, correlation_id=correlation_id, details=details,
    )
    return policy


def clone_performance_evaluation_policy_to_draft(*, policy, actor=None, correlation_id: str = ""):
    """ينسخ نسخة نشطة أو منتهية إلى مسودة جديدة — النسخ الأخرى لا تُعدَّل أبداً."""
    source = PerformanceEvaluationPolicy.objects.get(pk=getattr(policy, "pk", policy))
    return create_performance_evaluation_policy_draft(
        actor=actor,
        specialty=source.specialty,
        weights=source.weights,
        min_sample_size=source.min_sample_size,
        review_grace_period_hours=source.review_grace_period_hours,
        correlation_id=correlation_id,
        cloned_from=source,
    )


@transaction.atomic
def update_performance_evaluation_policy_draft(*, policy, actor=None, correlation_id: str = "", **changes):
    """يعدّل المسودة فقط؛ النسخ النشطة والمنتهية غير قابلة للتغيير."""
    allowed = {"specialty", "weights", "min_sample_size", "review_grace_period_hours"}
    if set(changes) - allowed:
        raise PerformanceEvaluationPolicyError("unsupported_field", "يوجد حقل سياسة غير مسموح بتعديله.")
    locked = PerformanceEvaluationPolicy.objects.select_for_update().get(pk=getattr(policy, "pk", policy))
    if locked.status != PerformanceEvaluationPolicy.Status.DRAFT:
        raise PerformanceEvaluationPolicyConflict("policy_immutable", "لا يمكن تعديل سياسة مفعلة أو منتهية.")

    before = _evaluation_policy_event_details(locked)
    validated_weights = _validate_pilot_weights(changes.get("weights", locked.weights))
    try:
        min_sample_size = int(changes.get("min_sample_size", locked.min_sample_size))
        review_grace_period_hours = int(changes.get("review_grace_period_hours", locked.review_grace_period_hours))
    except (TypeError, ValueError):
        raise PerformanceEvaluationPolicyError("invalid_integer", "حد العينة ومهلة المراجعة أعداد صحيحة.")
    if min_sample_size < 1 or review_grace_period_hours < 0:
        raise PerformanceEvaluationPolicyError("invalid_integer", "حد العينة ومهلة المراجعة يجب أن تكونا صالحتين.")

    locked.specialty = str(changes.get("specialty", locked.specialty) or "").strip()[:100]
    locked.weights = {k: str(v) for k, v in validated_weights.items()}
    locked.min_sample_size = min_sample_size
    locked.review_grace_period_hours = review_grace_period_hours
    locked.save(update_fields=["specialty", "weights", "min_sample_size", "review_grace_period_hours", "updated_at"])
    _log_evaluation_policy_event(
        locked, action=PerformanceEvaluationPolicyEvent.Action.UPDATED, actor=actor, correlation_id=correlation_id,
        details={"before": before, "after": _evaluation_policy_event_details(locked)},
    )
    return locked


def preview_performance_evaluation_policy(*, policy) -> dict:
    """يعيد أثر المسودة: النسخة النشطة الحالية وفروق الحقول — قراءة صرفة."""
    draft = PerformanceEvaluationPolicy.objects.get(pk=getattr(policy, "pk", policy))
    active = get_active_performance_evaluation_policy(specialty=draft.specialty)
    compared_fields = ("specialty", "weights", "min_sample_size", "review_grace_period_hours")
    diff = {}
    for field in compared_fields:
        draft_value = getattr(draft, field)
        active_value = getattr(active, field) if active else None
        if draft_value != active_value:
            diff[field] = {"active": active_value, "draft": draft_value}
    return {
        "draft": draft,
        "active": active,
        "diff": diff,
        "note": "معاينة فقط: لا تتغيّر أي لقطةٍ محسوبة سابقاً؛ الأثر يسري على الفترات القادمة فقط.",
    }


@transaction.atomic
def activate_performance_evaluation_policy(
    *, policy, actor=None, activation_reason: str = "", correlation_id: str = "", effective_from=None,
) -> PerformanceEvaluationPolicy:
    """يفعّل مسودة سياسة تقييم بسبب إلزامي — على نمط `activate_service_unit_catalog` بالضبط.

    منعُ تداخل الإصدارات لكل نطاق (`specialty`) تحت قفل صريح، ورفضُ مجموع أوزانٍ
    لا يساوي 100% (`_validate_pilot_weights` أعلاه، مُطبَّقٌ مسبقاً في الكتابة).
    """
    activation_reason = str(activation_reason or "").strip()
    if not activation_reason:
        raise PerformanceEvaluationPolicyError("activation_reason_required", "سبب التفعيل مطلوب.")
    locked_policies = list(PerformanceEvaluationPolicy.objects.select_for_update().order_by("pk"))
    locked = next((row for row in locked_policies if row.pk == getattr(policy, "pk", policy)), None)
    if locked is None:
        raise PerformanceEvaluationPolicyError("policy_not_found", "سياسة التقييم غير موجودة.")
    if locked.status != PerformanceEvaluationPolicy.Status.DRAFT:
        raise PerformanceEvaluationPolicyConflict("policy_not_draft", "لا يمكن تفعيل هذه السياسة مرة أخرى.")
    _validate_pilot_weights({k: Decimal(str(v)) for k, v in (locked.weights or {}).items()})

    now = timezone.now()
    starts_at = effective_from or now
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    if starts_at < now - datetime.timedelta(minutes=1):
        raise PerformanceEvaluationPolicyError("effective_from_in_past", "تاريخ السريان لا يكون في الماضي.")
    starts_at = max(starts_at, now)

    same_scope = [
        row for row in locked_policies
        if row.pk != locked.pk and row.status == PerformanceEvaluationPolicy.Status.ACTIVE
        and row.specialty == locked.specialty
    ]
    later = [row for row in same_scope if row.effective_from and row.effective_from >= starts_at]
    if later:
        raise PerformanceEvaluationPolicyConflict(
            "policy_overlap",
            f"النسخة v{later[0].version} لنفس النطاق تسري من تاريخ لاحق أو مساوٍ؛ اختر تاريخ سريان بعده.",
        )
    superseded = []
    for previous in same_scope:
        if previous.effective_to is None or previous.effective_to > starts_at:
            previous.effective_to = starts_at
            previous.save(update_fields=["effective_to", "updated_at"])
            superseded.append(previous.pk)

    locked.status = PerformanceEvaluationPolicy.Status.ACTIVE
    locked.effective_from = starts_at
    locked.effective_to = None
    locked.activated_at = now
    locked.activated_by = actor if getattr(actor, "pk", None) else None
    locked.activation_reason = activation_reason
    locked.save(update_fields=[
        "status", "effective_from", "effective_to", "activated_at", "activated_by", "activation_reason", "updated_at",
    ])
    _log_evaluation_policy_event(
        locked, action=PerformanceEvaluationPolicyEvent.Action.ACTIVATED, actor=actor, correlation_id=correlation_id,
        details={"reason": activation_reason, "effective_from": starts_at.isoformat(), "superseded_policy_ids": superseded},
    )
    for row in locked_policies:
        if (
            row.pk != locked.pk and row.status == PerformanceEvaluationPolicy.Status.ACTIVE
            and row.effective_to is not None and row.effective_to <= now
        ):
            row.status = PerformanceEvaluationPolicy.Status.RETIRED
            row.save(update_fields=["status", "updated_at"])
            _log_evaluation_policy_event(
                row, action=PerformanceEvaluationPolicyEvent.Action.RETIRED, actor=actor, correlation_id=correlation_id,
                details={"reason": activation_reason, "effective_to": row.effective_to.isoformat()},
            )
    return locked


# ==============================================================================
# التذكرة 210-D (تابع): سياسة تعويض الموظف — إدارة النسخ (§٧، §٨، §١١)
# ==============================================================================


def _resolve_compensation_employee(employee):
    if employee is None:
        return None
    emp_pk = getattr(employee, "pk", employee)
    resolved = PlatformEmployee.objects.filter(pk=emp_pk).first()
    if resolved is None:
        raise EmployeeCompensationPolicyError("employee_not_found", "موظف المنصة غير موجود.")
    return resolved


def _validate_compensation_decimal(value, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise EmployeeCompensationPolicyError(field_name, f"قيمة {field_name} غير صالحة.")
    if not result.is_finite() or result < Decimal("0.00"):
        raise EmployeeCompensationPolicyError(field_name, f"قيمة {field_name} يجب أن تكون صفراً أو أكبر.")
    return result.quantize(Decimal("0.01"))


def _compensation_policy_event_details(policy: EmployeeCompensationPolicy) -> dict:
    return {
        "employee_id": policy.employee_id,
        "base_salary": str(policy.base_salary),
        "daily_hours": str(policy.daily_hours),
        "weekly_days": policy.weekly_days,
        "acquisition_commission_amount": str(policy.acquisition_commission_amount),
        "acquisition_commission_months": policy.acquisition_commission_months,
        "accrual_day_of_month": policy.accrual_day_of_month,
    }


def _log_compensation_policy_event(policy, *, action, actor=None, correlation_id="", details=None):
    return EmployeeCompensationPolicyEvent.objects.create(
        policy=policy,
        action=action,
        actor=actor if getattr(actor, "pk", None) else None,
        correlation_id=str(correlation_id or "")[:64],
        details=details or {},
    )


def get_active_employee_compensation_policy(employee=None, at: datetime.datetime | None = None):
    """نسخة سياسة التعويض السارية لموظفٍ بعينه، وإلا العامة — لا تخمين افتراضي."""
    moment = at or timezone.now()
    in_effect = (
        EmployeeCompensationPolicy.objects
        .filter(status=EmployeeCompensationPolicy.Status.ACTIVE, effective_from__lte=moment)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=moment))
    )
    emp_id = getattr(employee, "pk", employee)
    if emp_id:
        specific = in_effect.filter(employee_id=emp_id).order_by("-version").first()
        if specific is not None:
            return specific
    return in_effect.filter(employee__isnull=True).order_by("-version").first()


def get_default_compensation_policy_dict() -> dict:
    """افتراضيّات الـpilot (جدول القيم الافتراضية) حين لا توجد نسخة منشورة بعد.

    **القيمُ تُقرأ من تعريف الحقول لا تُكتب هنا ثانيةً:** كانت مكتوبةً حرفيّاً
    (500/3/6/100/3/1) وهي نفسُها defaults الحقول في `EmployeeCompensationPolicy`،
    فصار للراتب والعمولة **مصدرا حقيقةٍ اثنان**: تعديلُ default الحقل وحدَه يُبقي
    هذا المسارَ — مسارَ «لا سياسة منشورة بعد»، وهو مسارُ الـpilot كلِّه قبل أوّل
    نشر — يدفع الرقمَ القديمَ بصمت، ولا اختبارٌ يكشفه لأنّ كلا الرقمين متساويان
    اليوم. والنمطُ الصحيح مستعملٌ سلفاً في `create_employee_compensation_policy_draft`.
    """
    field = EmployeeCompensationPolicy._meta.get_field
    return {
        "base_salary": Decimal(str(field("base_salary").default)),
        "daily_hours": Decimal(str(field("daily_hours").default)),
        "weekly_days": field("weekly_days").default,
        "acquisition_commission_amount": Decimal(str(field("acquisition_commission_amount").default)),
        "acquisition_commission_months": field("acquisition_commission_months").default,
        "accrual_day_of_month": field("accrual_day_of_month").default,
    }


def create_employee_compensation_policy_draft(
    *,
    actor=None,
    employee=None,
    base_salary=_UNSET,
    daily_hours=_UNSET,
    weekly_days=_UNSET,
    acquisition_commission_amount=_UNSET,
    acquisition_commission_months=_UNSET,
    accrual_day_of_month=_UNSET,
    correlation_id: str = "",
    cloned_from=None,
) -> EmployeeCompensationPolicy:
    """ينشئ نسخة مسودة مؤرخة من سياسة تعويض — لا `select_for_update` لحساب رقم النسخة."""
    resolved_employee = _resolve_compensation_employee(employee)
    field = EmployeeCompensationPolicy._meta.get_field
    if base_salary is _UNSET:
        base_salary = field("base_salary").default
    if daily_hours is _UNSET:
        daily_hours = field("daily_hours").default
    if weekly_days is _UNSET:
        weekly_days = field("weekly_days").default
    if acquisition_commission_amount is _UNSET:
        acquisition_commission_amount = field("acquisition_commission_amount").default
    if acquisition_commission_months is _UNSET:
        acquisition_commission_months = field("acquisition_commission_months").default
    if accrual_day_of_month is _UNSET:
        accrual_day_of_month = field("accrual_day_of_month").default

    base_salary = _validate_compensation_decimal(base_salary, "base_salary")
    daily_hours = _validate_compensation_decimal(daily_hours, "daily_hours")
    acquisition_commission_amount = _validate_compensation_decimal(
        acquisition_commission_amount, "acquisition_commission_amount",
    )
    try:
        weekly_days = int(weekly_days)
        acquisition_commission_months = int(acquisition_commission_months)
        accrual_day_of_month = int(accrual_day_of_month)
    except (TypeError, ValueError):
        raise EmployeeCompensationPolicyError("invalid_integer", "الحقول العددية يجب أن تكون أعداداً صحيحة.")
    if not 1 <= weekly_days <= 7:
        raise EmployeeCompensationPolicyError("weekly_days", "أيام الدوام الأسبوعية بين 1 و7.")
    if acquisition_commission_months < 1:
        raise EmployeeCompensationPolicyError("acquisition_commission_months", "مدة العمولة شهر واحد على الأقل.")
    if not 1 <= accrual_day_of_month <= 28:
        raise EmployeeCompensationPolicyError("accrual_day_of_month", "يوم الاستحقاق بين 1 و28.")

    last_version = EmployeeCompensationPolicy.objects.aggregate(Max("version"))["version__max"] or 0
    try:
        with transaction.atomic():
            policy = EmployeeCompensationPolicy.objects.create(
                version=last_version + 1,
                status=EmployeeCompensationPolicy.Status.DRAFT,
                employee=resolved_employee,
                base_salary=base_salary,
                daily_hours=daily_hours,
                weekly_days=weekly_days,
                acquisition_commission_amount=acquisition_commission_amount,
                acquisition_commission_months=acquisition_commission_months,
                accrual_day_of_month=accrual_day_of_month,
                created_by=actor if getattr(actor, "pk", None) else None,
            )
    except IntegrityError:
        raise EmployeeCompensationPolicyConflict(
            "policy_version_conflict", "تعذر إنشاء نسخة سياسة تعويض جديدة؛ أعد المحاولة.",
        )
    details = {"after": _compensation_policy_event_details(policy)}
    if cloned_from is not None:
        details["source_policy_id"] = cloned_from.pk
    _log_compensation_policy_event(
        policy,
        action=(
            EmployeeCompensationPolicyEvent.Action.CLONED if cloned_from is not None
            else EmployeeCompensationPolicyEvent.Action.CREATED
        ),
        actor=actor, correlation_id=correlation_id, details=details,
    )
    return policy


def clone_employee_compensation_policy_to_draft(*, policy, actor=None, correlation_id: str = ""):
    source = EmployeeCompensationPolicy.objects.get(pk=getattr(policy, "pk", policy))
    return create_employee_compensation_policy_draft(
        actor=actor,
        employee=source.employee_id,
        base_salary=source.base_salary,
        daily_hours=source.daily_hours,
        weekly_days=source.weekly_days,
        acquisition_commission_amount=source.acquisition_commission_amount,
        acquisition_commission_months=source.acquisition_commission_months,
        accrual_day_of_month=source.accrual_day_of_month,
        correlation_id=correlation_id,
        cloned_from=source,
    )


@transaction.atomic
def update_employee_compensation_policy_draft(*, policy, actor=None, correlation_id: str = "", **changes):
    allowed = {
        "employee", "base_salary", "daily_hours", "weekly_days",
        "acquisition_commission_amount", "acquisition_commission_months", "accrual_day_of_month",
    }
    if set(changes) - allowed:
        raise EmployeeCompensationPolicyError("unsupported_field", "يوجد حقل سياسة غير مسموح بتعديله.")
    locked = EmployeeCompensationPolicy.objects.select_for_update().get(pk=getattr(policy, "pk", policy))
    if locked.status != EmployeeCompensationPolicy.Status.DRAFT:
        raise EmployeeCompensationPolicyConflict("policy_immutable", "لا يمكن تعديل سياسة مفعلة أو منتهية.")

    before = _compensation_policy_event_details(locked)
    employee = (
        _resolve_compensation_employee(changes["employee"]) if "employee" in changes else locked.employee
    )
    base_salary = _validate_compensation_decimal(changes.get("base_salary", locked.base_salary), "base_salary")
    daily_hours = _validate_compensation_decimal(changes.get("daily_hours", locked.daily_hours), "daily_hours")
    acquisition_commission_amount = _validate_compensation_decimal(
        changes.get("acquisition_commission_amount", locked.acquisition_commission_amount),
        "acquisition_commission_amount",
    )
    try:
        weekly_days = int(changes.get("weekly_days", locked.weekly_days))
        acquisition_commission_months = int(
            changes.get("acquisition_commission_months", locked.acquisition_commission_months)
        )
        accrual_day_of_month = int(changes.get("accrual_day_of_month", locked.accrual_day_of_month))
    except (TypeError, ValueError):
        raise EmployeeCompensationPolicyError("invalid_integer", "الحقول العددية يجب أن تكون أعداداً صحيحة.")
    if not 1 <= weekly_days <= 7:
        raise EmployeeCompensationPolicyError("weekly_days", "أيام الدوام الأسبوعية بين 1 و7.")
    if acquisition_commission_months < 1:
        raise EmployeeCompensationPolicyError("acquisition_commission_months", "مدة العمولة شهر واحد على الأقل.")
    if not 1 <= accrual_day_of_month <= 28:
        raise EmployeeCompensationPolicyError("accrual_day_of_month", "يوم الاستحقاق بين 1 و28.")

    locked.employee = employee
    locked.base_salary = base_salary
    locked.daily_hours = daily_hours
    locked.weekly_days = weekly_days
    locked.acquisition_commission_amount = acquisition_commission_amount
    locked.acquisition_commission_months = acquisition_commission_months
    locked.accrual_day_of_month = accrual_day_of_month
    locked.save(update_fields=[
        "employee", "base_salary", "daily_hours", "weekly_days", "acquisition_commission_amount",
        "acquisition_commission_months", "accrual_day_of_month", "updated_at",
    ])
    _log_compensation_policy_event(
        locked, action=EmployeeCompensationPolicyEvent.Action.UPDATED, actor=actor, correlation_id=correlation_id,
        details={"before": before, "after": _compensation_policy_event_details(locked)},
    )
    return locked


def preview_employee_compensation_policy(*, policy) -> dict:
    draft = EmployeeCompensationPolicy.objects.get(pk=getattr(policy, "pk", policy))
    active = get_active_employee_compensation_policy(employee=draft.employee_id)
    compared_fields = (
        "employee_id", "base_salary", "daily_hours", "weekly_days",
        "acquisition_commission_amount", "acquisition_commission_months", "accrual_day_of_month",
    )
    diff = {}
    for field in compared_fields:
        draft_value = getattr(draft, field)
        active_value = getattr(active, field) if active else None
        if draft_value != active_value:
            money = field in {"base_salary", "daily_hours", "acquisition_commission_amount"}
            diff[field] = {
                "active": str(active_value) if money and active_value is not None else active_value,
                "draft": str(draft_value) if money and draft_value is not None else draft_value,
            }
    return {
        "draft": draft,
        "active": active,
        "diff": diff,
        "note": "معاينة فقط: لا يتغيّر أيُّ سطرِ محفظةٍ مُنشأٍ سابقاً؛ الأثر يسري على الأشهر القادمة فقط.",
    }


@transaction.atomic
def activate_employee_compensation_policy(
    *, policy, actor=None, activation_reason: str = "", correlation_id: str = "", effective_from=None,
) -> EmployeeCompensationPolicy:
    """يفعّل مسودة سياسة تعويض بسبب إلزامي — نطاق التداخل هنا هو الموظف المستهدَف
    (`employee_id`، لا `specialty`)."""
    activation_reason = str(activation_reason or "").strip()
    if not activation_reason:
        raise EmployeeCompensationPolicyError("activation_reason_required", "سبب التفعيل مطلوب.")
    locked_policies = list(EmployeeCompensationPolicy.objects.select_for_update().order_by("pk"))
    locked = next((row for row in locked_policies if row.pk == getattr(policy, "pk", policy)), None)
    if locked is None:
        raise EmployeeCompensationPolicyError("policy_not_found", "سياسة التعويض غير موجودة.")
    if locked.status != EmployeeCompensationPolicy.Status.DRAFT:
        raise EmployeeCompensationPolicyConflict("policy_not_draft", "لا يمكن تفعيل هذه السياسة مرة أخرى.")

    now = timezone.now()
    starts_at = effective_from or now
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    if starts_at < now - datetime.timedelta(minutes=1):
        raise EmployeeCompensationPolicyError("effective_from_in_past", "تاريخ السريان لا يكون في الماضي.")
    starts_at = max(starts_at, now)

    same_scope = [
        row for row in locked_policies
        if row.pk != locked.pk and row.status == EmployeeCompensationPolicy.Status.ACTIVE
        and row.employee_id == locked.employee_id
    ]
    later = [row for row in same_scope if row.effective_from and row.effective_from >= starts_at]
    if later:
        raise EmployeeCompensationPolicyConflict(
            "policy_overlap",
            f"النسخة v{later[0].version} لنفس النطاق تسري من تاريخ لاحق أو مساوٍ؛ اختر تاريخ سريان بعده.",
        )
    superseded = []
    for previous in same_scope:
        if previous.effective_to is None or previous.effective_to > starts_at:
            previous.effective_to = starts_at
            previous.save(update_fields=["effective_to", "updated_at"])
            superseded.append(previous.pk)

    locked.status = EmployeeCompensationPolicy.Status.ACTIVE
    locked.effective_from = starts_at
    locked.effective_to = None
    locked.activated_at = now
    locked.activated_by = actor if getattr(actor, "pk", None) else None
    locked.activation_reason = activation_reason
    locked.save(update_fields=[
        "status", "effective_from", "effective_to", "activated_at", "activated_by", "activation_reason", "updated_at",
    ])
    _log_compensation_policy_event(
        locked, action=EmployeeCompensationPolicyEvent.Action.ACTIVATED, actor=actor, correlation_id=correlation_id,
        details={"reason": activation_reason, "effective_from": starts_at.isoformat(), "superseded_policy_ids": superseded},
    )
    for row in locked_policies:
        if (
            row.pk != locked.pk and row.status == EmployeeCompensationPolicy.Status.ACTIVE
            and row.effective_to is not None and row.effective_to <= now
        ):
            row.status = EmployeeCompensationPolicy.Status.RETIRED
            row.save(update_fields=["status", "updated_at"])
            _log_compensation_policy_event(
                row, action=EmployeeCompensationPolicyEvent.Action.RETIRED, actor=actor, correlation_id=correlation_id,
                details={"reason": activation_reason, "effective_to": row.effective_to.isoformat()},
            )
    return locked


# ==============================================================================
# التذكرة 210-D (تابع): محاور تقييم الـpilot الأربعة — الحساب (§٥)
# ==============================================================================


def calculate_employee_pilot_performance(
    *,
    employee: PlatformEmployee,
    period_year: int,
    period_month: int,
    policy_dict: dict | None = None,
) -> dict:
    """حساب أداء موظف الإدخال عبر محاور الـpilot الأربعة (40/30/20/10) — §٥.

    **توسيعٌ للمحرّك القائم لا محرّكٌ ثانٍ**: يُعاد استعمال `redistribute_axis_weights`
    (بعد تعميمها بـ`all_axes`) و`PerformanceSnapshot` و`calculate_work_order_sla`
    نفسها؛ الجديد هنا حصراً هو مصادر البسط/المقام (دفتر الاستخدام وتصنيف الرفض
    من 210-C) التي لا وجود لها في محرك #207 القديم إطلاقاً.

    استبعاداتٌ مُنفَّذة من §٥: `onboarding` (`Engagement.kind`)، انتظار العميل
    (عبر `WorkOrder.Status.WAITING_CUSTOMER` واستبعاد ثواني الانتظار من SLA)،
    والعمل الذي نُقل قبل الاستحقاق (بقراءة `assignee` **الحالي** فقط — عملٌ
    نُقل لموظفٍ آخر لم يعد يظهر أصلاً ضمن أعمال هذا الموظف).
    **استبعاد وقت الإجازة المعتمدة TODO — سؤال مفتوح غير منفَّذ (§٦ من التذكرة):
    لا رابط بين PlatformEmployee وموظف hr المرتبط بشركة.**
    """
    start_date = datetime.date(period_year, period_month, 1)
    _, last_day = calendar.monthrange(period_year, period_month)
    end_date = datetime.date(period_year, period_month, last_day)

    if policy_dict is None:
        p_policy = get_active_performance_evaluation_policy(specialty=employee.specialty)
        policy_dict = _pilot_policy_dict(p_policy, employee.specialty)

    min_sample_size = int(policy_dict.get("min_sample_size", 5))
    raw_weights = policy_dict.get("weights") or {k: float(v) for k, v in DEFAULT_PILOT_AXIS_WEIGHTS.items()}

    # الشركات المؤهَّلة: ارتباطاتٌ standard فقط — onboarding مستبعد (§٥).
    standard_tenant_ids = list(
        Engagement.objects.filter(
            employee=employee, kind=Engagement.Kind.STANDARD,
        ).values_list("tenant_id", flat=True)
    )

    # ── المحور ١: إنجاز العمل المقبول (40%) ──────────────────────────────
    # **البسطُ محصورٌ بشركات المقام نفسِها**: توحيدُ الوحدة لا يكفي إن اختلف المجتمع —
    # مقامٌ محصورٌ بارتباطات `standard` وبسطٌ يجمع كلَّ وحدات الموظّف يُدخل وحداتِ
    # `onboarding` (المستبعدَ صراحةً في §٥) في البسط بلا نظيرٍ في المقام، فترتفع
    # النسبةُ فوق المئة بلا عملٍ إضافيٍّ حقيقيّ.
    usage_qs = ServiceUsageEvent.objects.filter(
        employee=employee, creditable_to_employee=True, tenant_id__in=standard_tenant_ids,
    )
    usage_qs = filter_local_date_range(usage_qs, "approved_at", date_from=start_date, date_to=end_date)
    approved_creditable_units = Decimal("0.00")
    for row in usage_qs.values("event_type").annotate(units_sum=Sum("units")):
        amount = row["units_sum"] or Decimal("0.00")
        if row["event_type"] == ServiceUsageEvent.EventType.USAGE:
            approved_creditable_units += amount
        else:
            approved_creditable_units -= amount

    assigned_qs = WorkOrder.objects.filter(
        assignee=employee, tenant_id__in=standard_tenant_ids,
    ).exclude(status=WorkOrder.Status.WAITING_CUSTOMER)
    assigned_qs = filter_local_date_range(assigned_qs, "received_at", date_from=start_date, date_to=end_date)

    # **المقامُ بالوحدات لا بعددِ الأوامر**: البسطُ مجموعُ `units` من دفتر الاستخدام،
    # فمقامٌ بعددِ الصفوف يقيس جنساً آخر — أمرُ عملٍ واحدٌ بعشرِ وحداتٍ يُنتج 1000%
    # تُقصُّ بصمتٍ إلى 100 فتبدو طاقةً مكتملة، وأمرٌ بنصفِ وحدةٍ أُنجز كاملاً يُنتج 50%.
    # والصيغةُ هنا **هي عينُها** التي يحتسب بها الدفترُ البسط
    # (`ServiceUnitCatalogEntry.units_for`) لا صيغةٌ ثانيةٌ تُشتق، وإلّا عاد عيبُ
    # مصدرَي الحقيقة. وروابطُ المستندات تُنشأ «تمهيداً للتسليم» و`deliverable` فيها
    # يُملأ لحظةَ التسليم — فهي نطاقُ العملِ المُسند لا أثرُ المُنجَز، ولذلك يبقى
    # عملٌ أُسند ولم يُسلَّم حاضراً في المقام كما يقتضي المحور.
    assigned_wo_ids = list(assigned_qs.values_list("pk", flat=True))
    catalog = get_active_service_unit_catalog()
    entries_by_type = (
        {entry.document_type: entry for entry in catalog.entries.all()} if catalog is not None else {}
    )
    assigned_eligible_units = Decimal("0.00")
    uncatalogued_links = 0
    if assigned_wo_ids:
        for link in WorkOrderDocumentLink.objects.filter(work_order_id__in=assigned_wo_ids).only(
            "document_type", "line_count", "complexity",
        ):
            entry = entries_by_type.get(link.document_type)
            if entry is None:
                # لا يُطرح صامتاً: بندٌ بلا نظيرٍ في الكتالوج يصغّر المقامَ فيرفع الدرجة،
                # فيُعدُّ ويُعرض مع النتيجة ليُقرأ النقصُ بدل أن يُجمَّل.
                uncatalogued_links += 1
                continue
            assigned_eligible_units += entry.units_for(link.line_count, link.complexity)

    capacity_target = employee.capacity_target or Decimal("0.00")
    if capacity_target > Decimal("0.00"):
        eligible_target_units = min(capacity_target, assigned_eligible_units)
    else:
        # capacity_target == 0 يعني «لم تُضبط بعد» لا «طاقة صفر» (قرار 210-B).
        eligible_target_units = assigned_eligible_units

    completion_numerator = float(max(Decimal("0.00"), approved_creditable_units))
    completion_denominator = float(eligible_target_units)
    completion_score = None
    completion_raw_percent = None
    if eligible_target_units > Decimal("0.00"):
        # الفائضُ فوق المئة يُعرض ولا يُطوى: الدرجةُ تبقى مقصوصةً عند 100 لأنّ المركَّبَ
        # الموزونَ لا يقبل أكثر، لكنّ القصَّ وحدَه يخفي طاقةً فائضةً حقيقيّة — والفرقُ
        # بين «أنجز المُسندَ إليه» و«أنجز ضعفَه» قرارُ إدارةٍ لا تفصيلُ حساب.
        completion_raw_percent = (
            approved_creditable_units / eligible_target_units * Decimal("100.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        completion_score = min(Decimal("100.00"), max(Decimal("0.00"), completion_raw_percent))

    # ── المحور ٢: الدقة والجودة (30%) ────────────────────────────────────
    reviewed_qs = WorkOrderDeliverable.objects.filter(
        work_order__assignee=employee,
        work_order__tenant_id__in=standard_tenant_ids,
        review_status__in=[
            WorkOrderDeliverable.ReviewStatus.APPROVED,
            WorkOrderDeliverable.ReviewStatus.REJECTED,
        ],
    ).exclude(
        review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
        rejection_category__in=[
            WorkOrderDeliverable.RejectionCategory.CUSTOMER_NEW_INFO,
            WorkOrderDeliverable.RejectionCategory.OTHER,
        ],
    )
    reviewed_qs = filter_local_date_range(reviewed_qs, "reviewed_at", date_from=start_date, date_to=end_date)
    # **الاسمُ يقول ما يَعِدّ**: هذان عددا **مُسلَّمات** مُراجَعة لا وحداتِ خدمة؛ وتسميتُهما
    # `_units` هي بعينها المزلقُ الذي أنتج خلطَ المحور الأوّل (بسطٌ بالوحدات ومقامٌ
    # بالصفوف)، فلا تُترك لتضلّ القارئَ التالي. ودلالةُ «المراجعة الأولى» في §٥ مسألةٌ
    # مفتوحةٌ مرفوعةٌ للمالك: إعادةُ عملٍ رُفض ثم اعتُمد تُقرأ الآن 50% لا سقوطاً في
    # المرّة الأولى — تغييرُها تغييرُ مقياسٍ لا إصلاحُ خطأ.
    first_reviewed_deliverables = reviewed_qs.count()
    first_pass_approved_deliverables = reviewed_qs.filter(
        review_status=WorkOrderDeliverable.ReviewStatus.APPROVED
    ).count()
    quality_score = None
    if first_reviewed_deliverables > 0:
        quality_score = (
            Decimal(first_pass_approved_deliverables) / Decimal(first_reviewed_deliverables) * Decimal("100.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ── المحور ٣: الالتزام بالـSLA (20%) — لا إعادة كتابة لحساب الأجل ────
    accepted_qs = WorkOrderDeliverable.objects.filter(
        work_order__assignee=employee,
        work_order__tenant_id__in=standard_tenant_ids,
        review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
    ).select_related("work_order")
    accepted_qs = filter_local_date_range(accepted_qs, "reviewed_at", date_from=start_date, date_to=end_date)
    accepted_list = list(accepted_qs)
    eligible_accepted_deliverables = len(accepted_list)
    on_time_count = 0
    for deliv in accepted_list:
        sla_info = calculate_work_order_sla(work_order=deliv.work_order)
        if not sla_info["is_overdue"]:
            on_time_count += 1
    sla_score = None
    if eligible_accepted_deliverables > 0:
        sla_score = (
            Decimal(on_time_count) / Decimal(eligible_accepted_deliverables) * Decimal("100.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ── المحور ٤: رضا العملاء (10%) — نفس مصدر محور #207 بالضبط ─────────
    # `service_date` عمود `DateField` صريح — لا `filter_local_date_range` هنا
    # (تلك للحقول الزمنية `DateTimeField` وحدها)، بلا `__date` بحال.
    ratings_qs = DailyRating.objects.filter(
        employee=employee, tenant_id__in=standard_tenant_ids,
        service_date__gte=start_date, service_date__lte=end_date,
    )
    ratings_sample_size = ratings_qs.count()
    satisfaction_score = None
    if ratings_sample_size >= min_sample_size:
        avg_stars = ratings_qs.aggregate(Avg("stars"))["stars__avg"] or 0.0
        satisfaction_score = (
            (Decimal(str(avg_stars)) / Decimal("5.00")) * Decimal("100.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    axis_raw_scores: dict[str, Decimal] = {}
    applicable_axes: set[str] = set()
    axis_details: dict[str, dict] = {
        PILOT_AXIS_TASK_COMPLETION: {
            "numerator": completion_numerator,
            "denominator": completion_denominator,
            "exclusions": ["onboarding", "waiting_customer", "transferred_before_due"],
            # الدرجةُ مقصوصةٌ عند 100 والنسبةُ الخامُ كما هي — يُقرأ منها الفائضُ فوق الطاقة.
            "raw_percent": float(completion_raw_percent) if completion_raw_percent is not None else None,
            # روابطُ مستنداتٍ لا بندَ لها في الكتالوج النشط: مقامٌ ناقصٌ يرفع الدرجةَ بغير حقّ.
            "uncatalogued_document_links": uncatalogued_links,
        },
        PILOT_AXIS_QUALITY: {
            "numerator": first_pass_approved_deliverables,
            "denominator": first_reviewed_deliverables,
            "exclusions": ["customer_new_info", "other"],
        },
        PILOT_AXIS_SLA: {
            "numerator": on_time_count,
            "denominator": eligible_accepted_deliverables,
            "exclusions": ["waiting_customer"],
        },
        PILOT_AXIS_SATISFACTION: {
            "numerator": float(ratings_qs.aggregate(Sum("stars"))["stars__sum"] or 0),
            "denominator": 5 * ratings_sample_size,
            "exclusions": [],
            "sample_size": ratings_sample_size,
            "min_sample_size": min_sample_size,
        },
    }
    if completion_score is not None:
        applicable_axes.add(PILOT_AXIS_TASK_COMPLETION)
        axis_raw_scores[PILOT_AXIS_TASK_COMPLETION] = completion_score
    if quality_score is not None:
        applicable_axes.add(PILOT_AXIS_QUALITY)
        axis_raw_scores[PILOT_AXIS_QUALITY] = quality_score
    if sla_score is not None:
        applicable_axes.add(PILOT_AXIS_SLA)
        axis_raw_scores[PILOT_AXIS_SLA] = sla_score
    if satisfaction_score is not None:
        applicable_axes.add(PILOT_AXIS_SATISFACTION)
        axis_raw_scores[PILOT_AXIS_SATISFACTION] = satisfaction_score

    redistributed_weights = redistribute_axis_weights(
        raw_weights, applicable_axes, all_axes=ALL_PILOT_PERFORMANCE_AXES, default_weights=DEFAULT_PILOT_AXIS_WEIGHTS,
    )

    axes_breakdown = {}
    weighted_sum = Decimal("0.00")
    for axis in ALL_PILOT_PERFORMANCE_AXES:
        is_app = axis in applicable_axes
        w = redistributed_weights.get(axis, Decimal("0.00"))
        sc = axis_raw_scores.get(axis, Decimal("0.00"))
        contrib = (w * sc / Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if is_app:
            weighted_sum += contrib
        # §٥ تطلب عرضَ «الوزن الأصلي والفعلي» معاً: الفعليُّ وحدَه يُخفي أنّ محوراً غيرَ
        # منطبقٍ أُسقط وأُعيد توزيعُ وزنه، فيقرأ الموظّفُ وزناً لم تضعه السياسةُ قطّ
        # ولا يعرف أنّ محوراً غاب. (هذه حلقةُ الـpilot وحدَها — لمحرّك #207 حلقتُه.)
        original_w = Decimal(str(raw_weights.get(axis, 0) or 0))
        axes_breakdown[axis] = {
            "applicable": is_app,
            "weight": w,
            "weight_pct": float(w),
            "weight_original": original_w,
            "weight_original_pct": float(original_w),
            "score": sc,
            "score_pct": float(sc),
            "weighted_contribution": contrib,
            **axis_details[axis],
        }

    # حجم العينة الإجمالي: مقام محور الجودة، أشمل مقياسٍ لـ«هل عمل مراجَع هذا الشهر».
    sample_size = first_reviewed_deliverables
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
        "axes": axes_breakdown,
        "weights_sum": sum(redistributed_weights.values()) if redistributed_weights else Decimal("0.00"),
        "policy_used": policy_dict,
    }


def _pilot_policy_dict(policy: PerformanceEvaluationPolicy | None, specialty: str = "") -> dict:
    if policy is None:
        return get_default_pilot_policy_dict(specialty)
    return {
        "policy_id": policy.pk,
        "version": policy.version,
        "specialty": policy.specialty,
        "weights": policy.weights or {k: float(v) for k, v in DEFAULT_PILOT_AXIS_WEIGHTS.items()},
        "min_sample_size": policy.min_sample_size,
        "review_grace_period_hours": policy.review_grace_period_hours,
    }


@transaction.atomic
def capture_pilot_performance_snapshot(
    *,
    employee: PlatformEmployee,
    period_year: int,
    period_month: int,
    evaluation_policy: PerformanceEvaluationPolicy | None = None,
    captured_by=None,
    force_refresh: bool = False,
    policy_dict: dict | None = None,
) -> PerformanceSnapshot:
    """التقاط لقطة شهرية بمحاور الـpilot الأربعة — idempotent، بنفس اصطلاح
    `capture_performance_snapshot` (#207) واستعمال نفس نموذج `PerformanceSnapshot`.

    **لقطة مجمَّدة لا تتغيّر بتعديل السياسة لاحقاً**: `policy_snapshot` يحمل
    نسخةً ثابتةً من الأوزان وقت الالتقاط، و`evaluation_policy` يحمل فقط مرجع
    أيّ نسخة استُعملت — تعديل تلك النسخة لاحقاً (ممنوعٌ أصلاً، تُستنسخ لا تُعدَّل)
    لا يمسّ هذا الصفّ بحال.

    و`policy_dict` (210-F) يُمرَّر حين تُعاد لقطةٌ قائمةٌ فتُحسب على **سياستها
    المجمَّدة** لا على السارية اليوم: بدونه كانت `force_refresh` تقرأ السياسةَ
    النشطةَ لحظتَها فتُعيد تسعيرَ شهرٍ قديمٍ بأوزانٍ نُشرت بعده — وهو بعينه
    «لا أثر رجعي» الذي بُني عليه تجميدُ اللقطة.
    """
    emp_pk = getattr(employee, "pk", employee)
    locked_emp = PlatformEmployee.objects.select_for_update().get(pk=emp_pk)

    existing = PerformanceSnapshot.objects.filter(
        employee=locked_emp, period_year=period_year, period_month=period_month,
    ).first()
    if existing and not force_refresh:
        return existing

    if policy_dict is None:
        if evaluation_policy is None:
            evaluation_policy = get_active_performance_evaluation_policy(specialty=locked_emp.specialty)
        policy_dict = _pilot_policy_dict(evaluation_policy, locked_emp.specialty)

    perf_result = calculate_employee_pilot_performance(
        employee=locked_emp, period_year=period_year, period_month=period_month, policy_dict=policy_dict,
    )

    now = timezone.now()
    if existing and force_refresh:
        existing.status = perf_result["status"]
        existing.composite_score = perf_result["composite_score"]
        existing.sample_size = perf_result["sample_size"]
        existing.policy_profile = None
        existing.evaluation_policy = evaluation_policy
        existing.policy_snapshot = _make_json_safe(policy_dict)
        existing.metrics_data = {}
        existing.axes_data = _make_json_safe(perf_result["axes"])
        existing.rework_rate = Decimal("0.00")
        existing.processed_sales_value = Decimal("0.00")
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
        policy_profile=None,
        evaluation_policy=evaluation_policy,
        policy_snapshot=_make_json_safe(policy_dict),
        metrics_data={},
        axes_data=_make_json_safe(perf_result["axes"]),
        rework_rate=Decimal("0.00"),
        processed_sales_value=Decimal("0.00"),
        captured_by=captured_by,
        captured_at=now,
    )
    log_platform_activity(
        employee=locked_emp,
        tenant=None,
        action=PlatformActivityLog.Action.SNAPSHOT_CAPTURED,
        entity_type="performance_snapshot",
        entity_id=snapshot.pk,
        description=f"التقاط لقطة أداء (pilot) لشهر {period_year}/{period_month}",
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
# التذكرة 210-D (تابع): المحفظة، عمولة الاكتساب، وإغلاق الشهر (§٧)
# ==============================================================================


def _wallet_idempotency_key(kind: str, *parts) -> str:
    return "platform_ops:wallet:" + kind + ":" + ":".join(str(p) for p in parts)


def _resolve_employee_compensation(employee) -> EmployeeCompensationPolicy | dict:
    return get_active_employee_compensation_policy(employee=employee) or get_default_compensation_policy_dict()


def _compensation_field(comp, field_name):
    if isinstance(comp, EmployeeCompensationPolicy):
        return getattr(comp, field_name)
    return comp[field_name]


def _create_salary_line_for_employee(
    *, employee: PlatformEmployee, period_year: int, period_month: int, monthly_close: MonthlyCompensationClose,
) -> EmployeeSalaryLine | None:
    """سطر راتبٍ واحدٌ لموظفٍ في شهرٍ واحد — `None` إن كان موجوداً بالفعل (idempotent)."""
    comp = _resolve_employee_compensation(employee)
    idempotency_key = _wallet_idempotency_key("salary", employee.pk, period_year, period_month)
    try:
        with transaction.atomic():
            return EmployeeSalaryLine.objects.create(
                employee=employee,
                period_year=period_year,
                period_month=period_month,
                sequence=0,
                amount=_compensation_field(comp, "base_salary"),
                status=WalletLineStatus.ELIGIBLE,
                compensation_policy=comp if isinstance(comp, EmployeeCompensationPolicy) else None,
                monthly_close=monthly_close,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        return None


def _subscription_paid_for_period(subscription: ServiceSubscription, period_start, period_end) -> bool:
    """هل سُجِّل دفعُ اشتراك الشهر فعلاً؟ — «مفوتَر» ليس «مدفوع» (§٧).

    يبحث عن سجلّ فوترة تتقاطع دورته مع الشهر التقويمي المطلوب، وفاتورته
    مدفوعةٌ بالكامل. غيابُ السجلّ أو غيابُ الفاتورة (باقة صفرية) أو نقصُ الدفع
    كلّها «غير مدفوع» — لا يُعتبر وجود `SubscriptionBillingRecord` وحده دليلَ دفع.

    **تُفحَص كلُّ السجلّات المتقاطعة لا أحدثُها وحدَه:** كان `.order_by(
    "-period_start").first()` يقرأ سجلّاً واحداً، فشهرٌ فُوتر على سجلَّين
    (دورةٌ مقسومةٌ، أو إعادةُ فوترةٍ تصحيحيّةٌ تُنشئ سجلّاً أحدثَ بفاتورةٍ أخرى)
    يُقرأ «غير مدفوع» ولو كان مدفوعاً بالكامل — والسطرُ يبقى `PENDING` حتى يتدخّل
    مديرٌ يدويّاً. فيكفي **أيُّ** سجلٍّ متقاطعٍ بفاتورةٍ مسدَّدةٍ بالكامل.
    """
    records = (
        SubscriptionBillingRecord.objects
        .filter(subscription=subscription, period_start__lte=period_end, period_end__gte=period_start)
        .select_related("invoice")
    )
    for record in records:
        if record.invoice_id is None:
            continue
        invoice = record.invoice
        if invoice.amount_paid >= invoice.grand_total:
            return True
    return False


def _create_commission_line_for_acquisition(
    *,
    acquisition: CustomerAcquisition,
    period_year: int,
    period_month: int,
    period_start: datetime.date,
    period_end: datetime.date,
    monthly_close: MonthlyCompensationClose,
) -> AcquisitionCommissionLine | None:
    """سطر عمولة اكتسابٍ واحدٌ لعميلٍ في شهرٍ واحد — أو لا شيء إن لم يستحق (§٧).

    ثلاثة شروط: (أ) انتهت التجربة (ب) دفعُ اشتراك الشهر فعلاً (ج) الخدمة نشطة
    حتى نهاية الفترة. (أ) و(ج) يحدّدان **هل يُنشأ سطرٌ أصلاً** (ويستهلكان أحد
    الأشهر الثلاثة)، و(ب) يحدّد فقط **حالة** السطر (`eligible`/`pending`) لا
    وجوده. بعد `acquisition_commission_months` سطوراً لا يُنشأ سطرٌ جديدٌ إطلاقاً.
    """
    subscription = getattr(acquisition.tenant, "service_subscription", None)
    if subscription is None:
        return None
    # **«انتهت تجربة العميل» لا تعني «كانت له تجربة»**: `activate_paid_subscription`
    # لا تضبط `trial_ends_at` إطلاقاً، فعميلٌ فُعِّل مدفوعاً مباشرةً يبقى الحقلُ فيه
    # فارغاً — ورفضُ العمولة حينها يحرم جالبَه منها **إلى الأبد** عن أفضل أنواع
    # العملاء. ولا فراغَ في الحراسة: الشرط (ب) يطلب دفعاً مسجَّلاً والشرط (ج) خدمةً
    # نشطة، فاشتراكٌ لم تبدأ تجربتُه بعد يسقط بـ(ج) لا بهذا السطر.
    if subscription.trial_ends_at and subscription.trial_ends_at.date() > period_end:
        return None
    # **`TRIAL` ليست «خدمةً نشطةً حتى نهاية الفترة»:** الشرط (ج) نشاطٌ فعليّ،
    # والشرط (أ) انتهاءُ التجربة — فقبولُ `TRIAL` هنا يناقض (أ) نفسَه: صفٌّ
    # بقيت حالتُه `trial` بعد انقضاء `trial_ends_at` حالةٌ بائتةٌ لا اشتراكٌ
    # مدفوع، وعدُّها يمنح عمولةً عن شهرٍ لم تُفعَّل فيه الخدمة أصلاً.
    if subscription.status != ServiceSubscription.Status.ACTIVE:
        return None

    comp = _resolve_employee_compensation(acquisition.acquired_by)
    max_months = _compensation_field(comp, "acquisition_commission_months")
    # **السطرُ المعكوس لا يستهلك شهراً من الثلاثة:** العكسُ يعني أنّ العمولةَ لم
    # تُستحق أصلاً (اشتراكٌ أُلغي، اكتسابٌ خاطئ)، فعدُّه ضمن `existing_count`
    # يحرم الموظّفَ شهراً استحقّه ولم يُقبض. والحالةُ `REVERSED` وحدَها تُستثنى:
    # `PENDING` يستهلك سلفاً لأنّه استحقاقٌ قائمٌ ينتظر إثباتَ الدفع لا استحقاقاً مُلغى.
    existing_count = (
        AcquisitionCommissionLine.objects
        .filter(acquisition=acquisition, sequence=0)
        .exclude(status=WalletLineStatus.REVERSED)
        .count()
    )
    if existing_count >= max_months:
        return None

    paid = _subscription_paid_for_period(subscription, period_start, period_end)
    idempotency_key = _wallet_idempotency_key("commission", acquisition.pk, period_year, period_month)
    try:
        with transaction.atomic():
            return AcquisitionCommissionLine.objects.create(
                acquisition=acquisition,
                employee=acquisition.acquired_by,
                period_year=period_year,
                period_month=period_month,
                sequence=0,
                commission_month_index=existing_count + 1,
                amount=_compensation_field(comp, "acquisition_commission_amount"),
                status=WalletLineStatus.ELIGIBLE if paid else WalletLineStatus.PENDING,
                pending_reason="" if paid else "الدفع غير مسجل",
                compensation_policy=comp if isinstance(comp, EmployeeCompensationPolicy) else None,
                monthly_close=monthly_close,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        return None


def preview_compensation_month_close(*, period_year: int, period_month: int) -> dict:
    """معاينةٌ بلا كتابة: هل الشهر مُغلَقٌ سلفاً؟ وما التسليمات المعلَّقة التي تمنع الإغلاق؟"""
    existing = MonthlyCompensationClose.objects.filter(period_year=period_year, period_month=period_month).first()
    _, last_day = calendar.monthrange(period_year, period_month)
    period_start = datetime.date(period_year, period_month, 1)
    period_end = datetime.date(period_year, period_month, last_day)
    blockers = list(
        filter_local_date_range(
            WorkOrderDeliverable.objects.filter(review_status=WorkOrderDeliverable.ReviewStatus.PENDING),
            "created_at", date_from=period_start, date_to=period_end,
        ).values_list("id", flat=True)
    )
    active_perf_policy = get_active_performance_evaluation_policy()
    return {
        "already_closed": existing is not None,
        "close": existing,
        "blockers": blockers,
        "eligible_employees": PlatformEmployee.objects.filter(status=PlatformEmployee.Status.ACTIVE).count(),
        "performance_policy": active_perf_policy,
        "review_grace_period_hours": (
            active_perf_policy.review_grace_period_hours if active_perf_policy
            else get_default_pilot_policy_dict()["review_grace_period_hours"]
        ),
    }


@transaction.atomic
def close_compensation_month(
    *, period_year: int, period_month: int, actor=None, correlation_id: str = "",
) -> tuple[MonthlyCompensationClose, bool]:
    """يُغلق مستحقّات شهرٍ واحدٍ لكلّ الموظفين دفعةً واحدة — idempotent (§٥، §٧).

    الحارسُ فرادةُ `MonthlyCompensationClose` على الفترة: استدعاءٌ ثانٍ لنفس
    الشهر يجد الصفَّ القائم ويعود به **دون تنفيذ الحلقة مرّة أخرى** فلا يتكرّر
    أيُّ سطرٍ مالي — لا حتى عند تسابقٍ (يُمسَك بـ`IntegrityError`). التسليماتُ
    المعلَّقةُ المُقدَّمةُ ضمن الشهر تمنع الإغلاق صراحةً بدل أن تُغلَق بصمت.
    """
    existing = MonthlyCompensationClose.objects.filter(period_year=period_year, period_month=period_month).first()
    if existing is not None:
        return existing, False

    _, last_day = calendar.monthrange(period_year, period_month)
    period_start = datetime.date(period_year, period_month, 1)
    period_end = datetime.date(period_year, period_month, last_day)

    blockers = list(
        filter_local_date_range(
            WorkOrderDeliverable.objects.filter(review_status=WorkOrderDeliverable.ReviewStatus.PENDING),
            "created_at", date_from=period_start, date_to=period_end,
        ).values_list("id", flat=True)
    )
    if blockers:
        raise MonthCloseBlockedError(
            "pending_deliverables",
            f"يوجد {len(blockers)} تسليماً بانتظار المراجعة قُدِّم خلال هذا الشهر؛ راجعها قبل الإغلاق.",
            blockers=blockers,
        )

    perf_policy = get_active_performance_evaluation_policy()
    # **ترتيبُ الأقفال يُحترم هنا يدويّاً لأنّ الحارسَ الساكن لا يراه:**
    # `capture_pilot_performance_snapshot` تقفل `PlatformEmployee` (رتبة ١٠) وهي
    # تُنادى بعد إنشاء صفّ `MonthlyCompensationClose` (رتبة ١٥) — أي قفلٌ أدنى بعد
    # أعلى، نقضٌ للعقد المعلَن في رأس الملف. و`LockOrderSourceGuardTest` يفحص كلَّ
    # دالّةٍ **على حدة** بتحليلٍ ساكن، فقفلٌ داخل دالّةٍ مُناداةٍ لا يظهر له أصلاً
    # ولا يكسر البوّابة — فالحفاظُ عليه واجبٌ بالقراءة لا بالاختبار. تُقفل صفوفُ
    # الموظفين أوّلاً بترتيب `pk` ثابتٍ (يمنع تشابكَ ABBA بين إغلاقَين متزامنَين)
    # ثمّ يُنشأ صفُّ الإغلاق.
    locked_employees = list(
        PlatformEmployee.objects
        .select_for_update()
        .filter(status=PlatformEmployee.Status.ACTIVE)
        .order_by("pk")
    )
    try:
        with transaction.atomic():
            close = MonthlyCompensationClose.objects.create(
                period_year=period_year,
                period_month=period_month,
                performance_policy=perf_policy,
                closed_by=actor if getattr(actor, "pk", None) else None,
                correlation_id=str(correlation_id or "")[:64],
            )
    except IntegrityError:
        return MonthlyCompensationClose.objects.get(period_year=period_year, period_month=period_month), False

    employees_processed = 0
    snapshots = 0
    salary_lines = 0
    commission_lines = 0
    for employee in locked_employees:
        employees_processed += 1
        capture_pilot_performance_snapshot(
            employee=employee, period_year=period_year, period_month=period_month,
            evaluation_policy=perf_policy, captured_by=actor,
        )
        snapshots += 1
        if _create_salary_line_for_employee(
            employee=employee, period_year=period_year, period_month=period_month, monthly_close=close,
        ) is not None:
            salary_lines += 1

    for acquisition in CustomerAcquisition.objects.select_related("tenant", "acquired_by"):
        if _create_commission_line_for_acquisition(
            acquisition=acquisition, period_year=period_year, period_month=period_month,
            period_start=period_start, period_end=period_end, monthly_close=close,
        ) is not None:
            commission_lines += 1

    close.employees_processed = employees_processed
    close.snapshots_captured = snapshots
    close.salary_lines_created = salary_lines
    close.commission_lines_created = commission_lines
    close.save(update_fields=[
        "employees_processed", "snapshots_captured", "salary_lines_created", "commission_lines_created",
    ])
    return close, True


def _wallet_line_model(kind: str):
    if kind == "salary":
        return EmployeeSalaryLine
    if kind == "commission":
        return AcquisitionCommissionLine
    raise WalletError("invalid_kind", "نوع سطر المحفظة غير معروف.")


_WALLET_ALLOWED_TRANSITIONS = {
    WalletLineStatus.PENDING: {WalletLineStatus.ELIGIBLE},
    WalletLineStatus.ELIGIBLE: {WalletLineStatus.APPROVED},
    WalletLineStatus.APPROVED: {WalletLineStatus.PAYABLE},
    WalletLineStatus.PAYABLE: {WalletLineStatus.PAID},
}


@transaction.atomic
def transition_wallet_line(*, kind: str, line, to_status: str, actor=None) -> EmployeeSalaryLine | AcquisitionCommissionLine:
    """ينقل سطر محفظةٍ (راتب أو عمولة) عبر `PENDING → ELIGIBLE → APPROVED → PAYABLE → PAID`.

    **لا حذف لسطرٍ ماليٍّ أبداً** — لا مسار حذف في هذا الـmodule أصلاً.
    """
    model = _wallet_line_model(kind)
    locked = model.objects.select_for_update().get(pk=getattr(line, "pk", line))
    allowed_targets = _WALLET_ALLOWED_TRANSITIONS.get(locked.status, set())
    if to_status not in allowed_targets:
        raise WalletConflict(
            "invalid_transition", f"لا يمكن الانتقال من {locked.status} إلى {to_status}.",
        )
    locked.status = to_status
    if to_status == WalletLineStatus.APPROVED:
        locked.approved_by = actor if getattr(actor, "pk", None) else None
        locked.approved_at = timezone.now()
        locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    else:
        locked.save(update_fields=["status", "updated_at"])
    return locked


@transaction.atomic
def reverse_wallet_line(*, kind: str, line, reason: str, actor=None) -> EmployeeSalaryLine | AcquisitionCommissionLine:
    """يعكس سطر محفظةٍ — الحالة تصبح `REVERSED`؛ لا حذف ولا كتابة فوق الأصل."""
    reason = str(reason or "").strip()
    if not reason:
        raise WalletError("reversal_reason_required", "سبب العكس مطلوب.")
    model = _wallet_line_model(kind)
    locked = model.objects.select_for_update().get(pk=getattr(line, "pk", line))
    if locked.status == WalletLineStatus.REVERSED:
        raise WalletConflict("already_reversed", "هذا السطر معكوسٌ بالفعل.")
    if locked.status == WalletLineStatus.PAID:
        raise WalletConflict("cannot_reverse_paid", "لا يمكن عكس سطرٍ مصروفٍ بالفعل؛ استعمل سطر تسوية.")
    locked.status = WalletLineStatus.REVERSED
    locked.reason = reason[:500]
    locked.save(update_fields=["status", "reason", "updated_at"])
    # **عكسُ سطرٍ ماليٍّ لا يمرّ بلا أثرٍ يسمّي فاعلَه**: الصفُّ يحمل السببَ ولا يحمل
    # مَن عكس ولا متى، فيُلغى مبلغٌ مستحقٌّ لموظّفٍ بلا سجلٍّ يُراجَع. والسجلُّ
    # يُعلَّق على موظّف السطر لأنّ `PlatformActivityLog` بنيةٌ موظَّفيّة لا عمودَ
    # فاعلٍ فيها، فيُثبَّت الفاعلُ في `details` صراحةً لا ضمناً.
    log_platform_activity(
        employee=locked.employee,
        action=PlatformActivityLog.Action.OTHER,
        description=f"عكسُ سطر محفظة ({kind}) — {reason[:200]}",
        entity_type=f"wallet_line:{kind}",
        entity_id=locked.pk,
        details={
            "operation": "reverse_wallet_line",
            "actor_user_id": getattr(actor, "pk", None),
            "period_year": locked.period_year,
            "period_month": locked.period_month,
            "amount": str(locked.amount),
        },
    )
    return locked


@transaction.atomic
def adjust_wallet_line(
    *, kind: str, line, amount: Decimal, reason: str, actor=None,
) -> EmployeeSalaryLine | AcquisitionCommissionLine:
    """يُنشئ سطر تسويةٍ ظاهراً مرتبطاً بالأصل — **لا تعديل على الأصل ولا حذف** (§٧).

    التصحيحُ بعد الإغلاق سطرٌ جديدٌ بتسلسلٍ أعلى؛ الأصل يبقى كما التقطه الإغلاق.
    """
    reason = str(reason or "").strip()
    if not reason:
        raise WalletError("adjustment_reason_required", "سبب التسوية مطلوب.")
    model = _wallet_line_model(kind)
    original = model.objects.select_for_update().get(pk=getattr(line, "pk", line))
    next_sequence = (
        model.objects.filter(
            **({"employee_id": original.employee_id} if kind == "salary" else {"acquisition_id": original.acquisition_id}),
            period_year=original.period_year,
            period_month=original.period_month,
        ).aggregate(Max("sequence"))["sequence__max"] or 0
    ) + 1
    idempotency_key = _wallet_idempotency_key(
        "adjustment", kind, original.pk, next_sequence,
    )
    # **سطرُ التسوية يُولد `PENDING` غيرَ معتمَدٍ ولا يعتمد نفسَه:** كان يُولد
    # `ELIGIBLE` وقد خُتم بـ`approved_by`/`approved_at` لحظةَ إنشائه، فمن يملك
    # «تسوية» يمنح نفسَه مبلغاً معتمَداً بقفزةٍ فوق `PENDING → ELIGIBLE →
    # APPROVED` — وهي السلسلةُ التي تفرضها التذكرة على كلّ سطرٍ مالي. والاعتمادُ
    # يبقى فعلاً منفصلاً عبر `transition_wallet_line` بفاعلٍ ووقتٍ مسجَّلَين.
    common_kwargs = dict(
        period_year=original.period_year,
        period_month=original.period_month,
        sequence=next_sequence,
        amount=amount,
        status=WalletLineStatus.PENDING,
        compensation_policy=original.compensation_policy,
        monthly_close=original.monthly_close,
        adjustment_of=original,
        reason=reason[:500],
        idempotency_key=idempotency_key,
    )
    if kind == "salary":
        created = EmployeeSalaryLine.objects.create(employee=original.employee, **common_kwargs)
    else:
        created = AcquisitionCommissionLine.objects.create(
            acquisition=original.acquisition,
            employee=original.employee,
            commission_month_index=original.commission_month_index,
            **common_kwargs,
        )
    # التسويةُ تُدخل مبلغاً جديداً على اسم الموظّف، فيلزمها الأثرُ نفسُه الذي يلزم
    # العكس: مَن أدخله ومتى وعلى أيّ سطرٍ أصليّ — وإلا بقي المبلغُ بلا نسبةٍ لفاعل.
    log_platform_activity(
        employee=created.employee,
        action=PlatformActivityLog.Action.OTHER,
        description=f"سطرُ تسوية محفظة ({kind}) — {reason[:200]}",
        entity_type=f"wallet_line:{kind}",
        entity_id=created.pk,
        details={
            "operation": "adjust_wallet_line",
            "actor_user_id": getattr(actor, "pk", None),
            "adjustment_of_id": original.pk,
            "sequence": next_sequence,
            "amount": str(amount),
        },
    )
    return created


def get_employee_wallet_summary(*, employee: PlatformEmployee, period_year: int, period_month: int) -> dict:
    """محفظة الموظف لشهرٍ واحد: مؤكَّد/معلَّق/متوقَّع مع فتح مصدر كلّ سطر (§٧، §٨)."""
    salary_lines = list(
        EmployeeSalaryLine.objects.filter(
            employee=employee, period_year=period_year, period_month=period_month,
        ).order_by("sequence")
    )
    commission_lines = list(
        AcquisitionCommissionLine.objects.filter(
            employee=employee, period_year=period_year, period_month=period_month,
        ).select_related("acquisition__tenant").order_by("sequence")
    )
    confirmed_statuses = {WalletLineStatus.ELIGIBLE, WalletLineStatus.APPROVED, WalletLineStatus.PAYABLE, WalletLineStatus.PAID}

    def _bucket(lines):
        confirmed = sum((line.amount for line in lines if line.status in confirmed_statuses), Decimal("0.00"))
        pending = sum((line.amount for line in lines if line.status == WalletLineStatus.PENDING), Decimal("0.00"))
        return confirmed, pending

    salary_confirmed, salary_pending = _bucket(salary_lines)
    commission_confirmed, commission_pending = _bucket(commission_lines)

    return {
        "employee_id": employee.pk,
        "period_year": period_year,
        "period_month": period_month,
        "salary_lines": salary_lines,
        "commission_lines": commission_lines,
        "totals": {
            "confirmed": salary_confirmed + commission_confirmed,
            "pending": salary_pending + commission_pending,
            # §٧ تطلب ثلاثةَ أرقامٍ لا اثنين: «مؤكد، معلق، متوقع». والمتوقَّعُ حصيلةُ
            # الشهر **لو تحقّق كلُّ شرطٍ ناقص** — مشتقٌّ لا مُخترَع، و`REVERSED`
            # خارجَه كما هو خارجُ الآخرَين: سطرٌ عُكس ليس مبلغاً يُنتظَر.
            "expected": salary_confirmed + commission_confirmed + salary_pending + commission_pending,
        },
    }


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

    # نطاق مركز القيادة لا يدخل إلا الشركات المؤهلة، باستعلام SQL واحد.
    eligible_tenant_ids = eligible_service_tenant_ids(current_time)

    # تحديد نطاق الموظفين والشركات
    if is_manager:
        emp_qs = PlatformEmployee.objects.select_related("user").filter(
            status=PlatformEmployee.Status.ACTIVE
        )
        engaged_tenant_ids = eligible_tenant_ids
    else:
        emp_qs = PlatformEmployee.objects.select_related("user").filter(
            user=user,
            status=PlatformEmployee.Status.ACTIVE,
        )
        engaged_tenant_ids = list(
            Engagement.objects.filter(
                employee__user=user,
                status=Engagement.Status.ACTIVE,
                tenant_id__in=eligible_tenant_ids,
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
    tenant_qs = Tenant.objects.filter(pk__in=engaged_tenant_ids)

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


def rating_public_url(raw_token: str) -> str:
    """رابطُ صفحةِ التقييم المُسلَّم لصاحب الشركة — من إعدادٍ صريحٍ لا من ترويسة الطلب.

    نمطُ `docshare.services.public_url` حرفياً: `request.build_absolute_uri` يبني من
    ترويسة `Host` التي يرسلها العميل، وهذا رابطٌ يُلصَق في واتساب ويعيش ثلاثة أيّام.

    والوجهةُ **صفحةُ الواجهة** (`/rate/<token>`) لا نقطةُ الـAPI: من يفتح الرابط زبونٌ
    يريد نجماتٍ ينقرها، لا JSON.
    """
    base = str(getattr(settings, "PLATFORM_RATING_PUBLIC_BASE_URL", "")).rstrip("/")
    path = str(getattr(settings, "PLATFORM_RATING_PUBLIC_PATH", "/rate")).rstrip("/")
    return f"{base}{path}/{raw_token}"


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


def decide_rating_update(
    *,
    existing: DailyRating,
    new_stars: int,
    new_note: str,
) -> tuple[bool, bool]:
    """تقرير ما إذا كان التحديث تغييراً، وهل يستهلك حق التعديل الواحد (edited_once).

    القواعد الحرفية (المرحلة السابعة §١٠):
    1. إرسالٌ لا يغيّر شيئاً (نفس النجمات ونفس الملاحظة) ⇒ ليس تغييراً ولا يستهلك التعديل
       (حتى لو كان edited_once=True مسبقاً، فالنقرة المكررة أو إعادة الإرسال لا تسقط بـ 400).
    2. إن كان تغييراً وسبق تعديله (edited_once=True) ⇒ يرفع DailyRatingConflict('already_edited').
    3. إلحاق ملاحظة بتقييم ملاحظته فارغة والنجمات نفسها ⇒ تغيير، ولكن لا يستهلك التعديل (تبقى edited_once=False).
    4. تغيير النجمات، أو تغيير ملاحظة غير فارغة ⇒ تغيير يستهلك التعديل (تصبح edited_once=True).

    يعيد: (is_changed: bool, consume_edit: bool)
    """
    clean_existing_note = (existing.note or "").strip()
    clean_new_note = (new_note or "").strip()

    stars_match = (new_stars == existing.stars)
    notes_match = (clean_new_note == clean_existing_note)

    if stars_match and notes_match:
        return False, False

    if existing.edited_once:
        raise DailyRatingConflict(
            "already_edited",
            "تم تعديل هذا التقييم مسبقاً ولا يمكن تعديله مرة ثانية.",
            status_code=400,
        )

    if stars_match and not clean_existing_note and clean_new_note:
        return True, False

    return True, True


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
        is_changed, consume_edit = decide_rating_update(
            existing=existing,
            new_stars=stars,
            new_note=clean_note,
        )
        if is_changed:
            existing.stars = stars
            existing.note = clean_note
            if consume_edit:
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
    """تعديل تقييم قائم لمرة واحدة فقط وفق قاعدة decide_rating_update الموحدة."""
    if stars < 1 or stars > 5:
        raise DailyRatingError("invalid_stars", "التقييم يجب أن يكون بين 1 و 5 نجوم.", status_code=400)

    locked = DailyRating.objects.select_for_update().filter(pk=rating_id).first()
    if not locked:
        raise DailyRatingError("not_found", "التقييم غير موجود.", status_code=404)

    clean_note = note.strip() if note else ""
    is_changed, consume_edit = decide_rating_update(
        existing=locked,
        new_stars=stars,
        new_note=clean_note,
    )
    if is_changed:
        locked.stars = stars
        locked.note = clean_note
        if consume_edit:
            locked.edited_once = True
        locked.save(update_fields=["stars", "note", "edited_once", "updated_at"])
    return locked


def calculate_employee_ratings_summary(
    *,
    employee: PlatformEmployee,
    tenant: Tenant | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    min_sample_size: int | None = None,
) -> dict:
    """حساب ملخص تقييمات الموظف مع اشتراط حد أدنى للعينة لدخول الأداء."""
    if min_sample_size is None:
        policy = resolve_policy_profile_for_employee(employee)
        min_sample_size = policy.min_sample_size if policy else 5
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

    # 1. استخراج الوكلاء النشطين حصراً من Engagement
    #
    # **جمعٌ لا مفرد**: فرادةُ الارتباط على (موظف، شركة) لا على الشركة وحدَها
    # (`assign_platform_employee`)، فشركةٌ يعمل عليها وكيلان حالةٌ مشروعة. وكان
    # التبويبُ يعرض `first()` وحدَه — فيرى صاحبُ الشركة اسماً واحداً بينما اثنان
    # يملكان صلاحيةَ مديرٍ على دفاتره؛ وهذا نقيضُ ما وُجد التبويبُ له (قصة ٤٩).
    active_engagements = list(
        Engagement.objects.filter(tenant=tenant_obj, status=Engagement.Status.ACTIVE)
        .select_related("employee__user")
        .order_by("pk")
    )

    today = timezone.localdate()
    agents = []
    agent_user_ids = []
    for engagement in active_engagements:
        emp = engagement.employee
        user = emp.user
        if user.pk not in agent_user_ids:
            agent_user_ids.append(user.pk)
        # تقييمُ اليوم لهذا الوكيل — **يُرسَل مع التبويب لا تُترَك الواجهةُ تخمّنه**.
        # بدونه تفتح الشاشةُ بنجماتٍ فارغةٍ لصاحب شركةٍ قيّم صباحاً من الرابط، فتظنّ
        # نقرتُه التاليةَ إنشاءً وهي **تعديلٌ يستهلك حقَّه الوحيد** بلا أن يُقال له.
        row = DailyRating.objects.filter(
            tenant=tenant_obj, employee_id=emp.pk, service_date=today,
        ).first()
        agents.append({
            "id": emp.pk,
            "user_id": user.pk,
            "name": user.get_full_name() or user.username,
            "username": user.username,
            "specialty": emp.specialty,
            "assigned_at": engagement.assigned_at.isoformat(),
            "role_title": "مدير النظام والعمليات",
            "authority_notice": "يعمل وكيل المنصة بصلاحية مدير كاملة على حساب الشركة لإدارة الدفاتر المحاسبية والعمليات التشغيلية.",
            "engagement_id": engagement.pk,
            "engagement_status": engagement.status,
            # قصّة ٦٠: «لا يُطلَب منّي تقييمُ يومٍ لم يعمل فيه أحد» — **لا يُطلَب**،
            # لا «يُطلَب ثمّ يُرفَض بـ400». فالشاشةُ تعرف قبل أن تسأل.
            "worked_today": has_employee_worked_on_date(tenant_obj, emp, today),
            "today_rating": {
                "id": row.pk,
                "service_date": row.service_date.isoformat(),
                "stars": row.stars,
                "note": row.note,
                "edited_once": row.edited_once,
            } if row else None,
        })

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
        "agents": agents,
        # **اليومُ من الخادم لا من المتصفّح**: الواجهةُ كانت ترسل تاريخَ جهاز الزبون،
        # فمن يفتحها من خارج المنطقة — أو قبل منتصف الليل بقليل — يُنشئ تقييماً ليومٍ
        # غيرِ الذي عُرض عليه، فينقسم حقُّ التعديل الواحد على صفَّين. والتوقيت
        # `Asia/Hebron` من الإعدادات (`timezone.localdate`).
        "service_date": today.isoformat(),
        "granted_memberships": granted_memberships,
        "activity_log": activity_items,
        # العددُ الكلّيُّ من القاعدة لا `len` بعد القصّ — وإلا جمد على السقف وكذب.
        "total_activities_count": total_activities_count,
        "returned_activities_count": len(activity_items),
        "activity_page_cap": MY_BOOKS_ACTIVITY_PAGE_CAP,
        "can_suspend": bool(active_engagements),
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
    service_breakdown = []

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
        text = f"علينا: {sla_breaches_count} أعمالٍ تجاوزت الأجل"
        service_reasons.append({
            "deduction": deduction,
            "text": text,
        })
        service_breakdown.append({
            "reason_key": "sla_breaches",
            "label": text,
            "count": sla_breaches_count,
            "deduction": deduction,
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
        text = f"علينا: {rejected_deliv_count} مُسلَّماتٍ رُفضت في المراجعة"
        service_reasons.append({
            "deduction": deduction,
            "text": text,
        })
        service_breakdown.append({
            "reason_key": "rejected_deliverables",
            "label": text,
            "count": rejected_deliv_count,
            "deduction": deduction,
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
        text = f"علينا: {low_ratings_count} تقييماتٍ يوميةٍ منخفضة"
        service_reasons.append({
            "deduction": deduction,
            "text": text,
        })
        service_breakdown.append({
            "reason_key": "low_ratings",
            "label": text,
            "count": low_ratings_count,
            "deduction": deduction,
        })

    service_health_score = max(0, 100 - service_deductions)
    service_reasons.sort(key=lambda r: r["deduction"], reverse=True)
    service_breakdown.sort(key=lambda r: (r["deduction"], r["count"]), reverse=True)
    top_service_reasons = [r["text"] for r in service_reasons[:3]]

    # --------------------------------------------------------------------------
    # 2. تعاون الزبون (تقصير وتأخيرات الزبون)
    # --------------------------------------------------------------------------
    customer_deductions = 0
    customer_reasons = []
    customer_breakdown = []

    # أ. أوامر عمل متوقفة بانتظار العميل حالياً
    waiting_customer_count = WorkOrder.objects.filter(
        tenant=tenant_obj, status=WorkOrder.Status.WAITING_CUSTOMER
    ).count()
    if waiting_customer_count > 0:
        deduction = waiting_customer_count * 15
        customer_deductions += deduction
        text = f"بانتظار الزبون: {waiting_customer_count} أعمالٍ بانتظار الرد"
        customer_reasons.append({
            "deduction": deduction,
            "text": text,
        })
        customer_breakdown.append({
            "reason_key": "waiting_customer",
            "label": text,
            "count": waiting_customer_count,
            "deduction": deduction,
        })

    # ب. أوامر عمل تراكم فيها انتظار الزبون لأكثر من 48 ساعة
    long_waiting_count = WorkOrder.objects.filter(
        tenant=tenant_obj,
        waiting_seconds_total__gte=48 * 3600,
    ).count()
    if long_waiting_count > 0:
        deduction = long_waiting_count * 10
        customer_deductions += deduction
        text = f"بانتظار الزبون: {long_waiting_count} أعمالٍ تأخّر ردّه عليها أكثر من ٤٨ ساعة"
        customer_reasons.append({
            "deduction": deduction,
            "text": text,
        })
        customer_breakdown.append({
            "reason_key": "long_waiting",
            "label": text,
            "count": long_waiting_count,
            "deduction": deduction,
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
        text = f"بانتظار الزبون: {pending_comments_count} استفساراتٍ معلّقة"
        customer_reasons.append({
            "deduction": deduction,
            "text": text,
        })
        customer_breakdown.append({
            "reason_key": "pending_comments",
            "label": text,
            "count": pending_comments_count,
            "deduction": deduction,
        })

    customer_cooperation_score = max(0, 100 - customer_deductions)
    customer_reasons.sort(key=lambda r: r["deduction"], reverse=True)
    customer_breakdown.sort(key=lambda r: (r["deduction"], r["count"]), reverse=True)
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
            "breakdown": service_breakdown,
        },
        "customer_cooperation": {
            "score": customer_cooperation_score,
            "status": "excellent" if customer_cooperation_score >= 90 else "good" if customer_cooperation_score >= 70 else "needs_attention",
            "top_reasons": top_customer_reasons,
            "breakdown": customer_breakdown,
        },
    }


# ==============================================================================
# المرحلة 8A: فوترة اشتراكات الخدمة الشهرية (Issue #207 Stage 8A)
# ==============================================================================


def calculate_subscription_billing(
    subscription: ServiceSubscription,
) -> dict:
    """حساب مستحقات الفوترة لاشتراك الخدمة وفق المعادلة المعتمدة:

    Monthly charge = monthly_fee + max(consumed_quota - included_quota, 0) * overage_unit_price
    """
    monthly_fee = Decimal(str(subscription.monthly_fee or 0)).quantize(Decimal("0.01"))
    included_quota = int(subscription.included_quota or 0)
    consumed_quota = int(subscription.consumed_quota or 0)
    overage_unit_price = Decimal(str(subscription.overage_unit_price or 0)).quantize(Decimal("0.01"))

    overage_units = max(consumed_quota - included_quota, 0)
    overage_fee = (Decimal(overage_units) * overage_unit_price).quantize(Decimal("0.01"))
    total_amount = (monthly_fee + overage_fee).quantize(Decimal("0.01"))

    return {
        "monthly_fee": monthly_fee,
        "included_quota": included_quota,
        "consumed_quota": consumed_quota,
        "overage_units": overage_units,
        "overage_unit_price": overage_unit_price,
        "overage_fee": overage_fee,
        "total_amount": total_amount,
    }


def get_tenant_quota_usage(tenant) -> dict:
    """استهلاكُ الشركة من باقتها واقترابُها من الحدّ — **للزبون نفسِه**.

    القصّة ٦٢: «أريد أن أرى استهلاكي من الباقة واقترابي من الحدّ، حتى لا تفاجئني
    الفاتورة». فالأرقامُ المعروضةُ هي أرقامُ الفوترة نفسُها (`calculate_subscription_billing`)
    لا حسبةٌ ثانيةٌ تتباعد عنها.

    شركةٌ بلا اشتراكٍ تُعيد `has_subscription=False` بدل أن تسقط — الشاشةُ تعرض
    حالةً لا خطأً.
    """
    subscription = ServiceSubscription.objects.filter(tenant=tenant).first()
    if subscription is None:
        return {"has_subscription": False}

    calc = calculate_subscription_billing(subscription)
    included = calc["included_quota"]
    consumed = calc["consumed_quota"]
    remaining = max(included - consumed, 0)
    # نسبةُ الاستهلاك بلا قسمةٍ على صفر: باقةٌ بلا حدٍّ تعني أنّ كلّ عمليّةٍ زائدة.
    usage_percent = round((consumed / included) * 100, 2) if included > 0 else None

    # المبالغُ نصوصٌ عشريّةٌ مقرَّبة ("290.00") كما تُسلسلها حقولُ `DecimalField` في
    # بقيّة الوحدة — لا أعدادٌ عائمةٌ يُقرّبها المتصفّحُ على هواه.
    return {
        "has_subscription": True,
        "status": subscription.status,
        "status_display": subscription.get_status_display(),
        "plan": subscription.plan,
        "period_start": subscription.period_start,
        "period_end": subscription.period_end,
        "monthly_fee": str(calc["monthly_fee"]),
        "included_quota": included,
        "consumed_quota": consumed,
        "remaining_quota": remaining,
        "usage_percent": usage_percent,
        "overage_units": calc["overage_units"],
        "overage_unit_price": str(calc["overage_unit_price"]),
        "overage_fee": str(calc["overage_fee"]),
        "projected_total": str(calc["total_amount"]),
    }


def _calendar_month_bounds(day: datetime.date) -> tuple[datetime.date, datetime.date]:
    """أول وآخر يوم في الشهر الميلادي المحتوي على `day` — حاسبة الشهر الوحيدة.

    تستعملها الفوترة لتقديم الدورة بعد كل تحصيل، والتفعيل المدفوع لضبط أول
    دورة فوترة قبل أي تحصيل — بدل حاسبتين قد تختلفان لاحقاً.
    """
    _, last_day = calendar.monthrange(day.year, day.month)
    return datetime.date(day.year, day.month, 1), datetime.date(day.year, day.month, last_day)


def _first_day_of_next_month(day: datetime.date) -> datetime.date:
    if day.month == 12:
        return datetime.date(day.year + 1, 1, 1)
    return datetime.date(day.year, day.month + 1, 1)


def _first_billing_period_after_activation(activation_day: datetime.date) -> tuple[datetime.date, datetime.date]:
    """دورة الفوترة الأولى لاشتراك مدفوع: الشهر الميلادي التالي لشهر التفعيل كاملاً.

    قرارٌ صريحٌ للـpilot بلا prorating (§١): بقيّة شهر التفعيل لا تُفوتَر، وأول
    دورةٍ حقيقيّة تبدأ في اليوم الأول من الشهر التالي — فشركةٌ فُعِّلت في ٣٠ من
    الشهر لا تُحاسَب على شهرٍ كامل لم تستهلكه.
    """
    return _calendar_month_bounds(_first_day_of_next_month(activation_day))


def resolve_subscription_billing_products(
    subscription, *, fixed_fee_product_id: int | None = None, overage_product_id: int | None = None,
) -> tuple[int | None, int | None]:
    """أصناف فوترة الاشتراك: تجاوز صريح من الأمر، ثم لقطة الاشتراك من سياسته، ثم إعدادات الخادم للصفوف القديمة."""
    fixed = (
        fixed_fee_product_id
        or subscription.fixed_fee_product_id
        or getattr(settings, "PLATFORM_OPS_BILLING_FIXED_FEE_PRODUCT_ID", None)
    )
    overage = (
        overage_product_id
        or subscription.overage_product_id
        or getattr(settings, "PLATFORM_OPS_BILLING_OVERAGE_PRODUCT_ID", None)
    )
    return fixed, overage


def resolve_billing_period_bounds(period_str: str) -> tuple[datetime.date, datetime.date]:
    """تحليل نص الفترة بصيغة YYYY-MM واستخراج تاريخ البداية والنهاية الميلاديين بأمان."""
    raw = str(period_str or "").strip()
    import re
    m = re.match(r"^(\d{4})-(\d{2})$", raw)
    if not m:
        raise BillingPeriodError(
            "invalid_period_format",
            f"صيغة الفترة «{period_str}» غير صالحة؛ يجب أن تكون YYYY-MM (مثال: 2026-08).",
            status_code=400,
        )
    year, month = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12):
        raise BillingPeriodError(
            "invalid_period_month",
            f"الشهر {month} غير صالح؛ يجب أن يكون بين 1 و 12.",
            status_code=400,
        )
    _, last_day = calendar.monthrange(year, month)
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)


def billing_preflight(
    *,
    subscription: ServiceSubscription,
    period_start: datetime.date,
    period_end: datetime.date,
    fixed_fee_product_id: int | None = None,
    overage_product_id: int | None = None,
    check_already_billed: bool = True,
    raise_exception: bool = False,
) -> BillingError | None:
    """فحص مسبق موحد لصلاحية فوترة اشتراك خدمة لدورة معينة.

    يتحقق من:
    1. حالة الاشتراك نشطة.
    2. عدم الفوترة مسبقاً لنفس الدورة (إن طُلبت).
    3. مطابقة دورة الاشتراك للدورة المطلوبة.
    4. ربط الاشتراك بعميل فوترة.
    5. أن عميل الفوترة لا يتبع نفس شركة الاشتراك (أ٥).
    6. وجود صنف الرسم الثابت وأنه خدمي ويتبع شركة المنصة.
    7. إذا وُجد استهلاك زائد، التحقق من تحديد صنف العمليات الزائدة ووجوده وأنه خدمي ويتبع شركة المنصة.
    """
    from inventory.models import Product

    if subscription.status == ServiceSubscription.Status.TRIAL:
        err = BillingPeriodError(
            "subscription_in_trial",
            f"اشتراك الشركة «{subscription.tenant}» في فترة تجربة ولا يجوز فوترته.",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    if subscription.status != ServiceSubscription.Status.ACTIVE:
        err = BillingPeriodError(
            "subscription_inactive",
            f"اشتراك الشركة «{subscription.tenant}» غير نشط ({subscription.get_status_display()}).",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    if check_already_billed:
        if SubscriptionBillingRecord.objects.filter(
            subscription=subscription,
            period_start=period_start,
            period_end=period_end,
        ).exists():
            err = BillingPeriodError(
                "already_billed",
                f"تمت فوترة اشتراك الشركة «{subscription.tenant}» للدورة ({period_start} إلى {period_end}) مسبقاً.",
                status_code=400,
            )
            if raise_exception:
                raise err
            return err

    if subscription.period_start and subscription.period_start > period_end:
        err = BillingPeriodError(
            "subscription_not_yet_billable",
            f"دورة اشتراك الشركة «{subscription.tenant}» تبدأ في {subscription.period_start}، "
            f"بعد نهاية الدورة المطلوبة ({period_end}) — لم تحن دورته الأولى بعد.",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    if subscription.period_start and subscription.period_end:
        if (
            subscription.period_start != period_start
            or subscription.period_end != period_end
        ):
            err = BillingPeriodError(
                "period_mismatch",
                f"دورة الاشتراك الحالية ({subscription.period_start} إلى {subscription.period_end}) "
                f"لا تطابق دورة الفوترة المطلوبة ({period_start} إلى {period_end}).",
                status_code=400,
            )
            if raise_exception:
                raise err
            return err

    if not subscription.billing_customer_id:
        err = BillingConfigurationError(
            "missing_billing_customer",
            f"الاشتراك للشركة «{subscription.tenant}» غير مربوط بعميل فوترة في شركة المنصة.",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    customer = subscription.billing_customer
    if customer.tenant_id == subscription.tenant_id:
        err = BillingPeriodError(
            "billing_customer_same_tenant",
            f"عميل الفوترة يتبع نفس شركة الاشتراك ({subscription.tenant_id})؛ يجب أن يكون في شركة المنصة.",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    platform_tenant = customer.tenant

    if not fixed_fee_product_id:
        err = BillingConfigurationError(
            "missing_fixed_fee_product",
            "يجب تحديد معرّف صنف الرسم الثابت (fixed_fee_product_id).",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    fixed_product = Product.objects.filter(pk=fixed_fee_product_id).first()
    if not fixed_product:
        err = BillingConfigurationError(
            "fixed_fee_product_not_found",
            f"صنف الرسم الثابت برقم {fixed_fee_product_id} غير موجود.",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    if fixed_product.tenant_id != platform_tenant.TenantID:
        err = BillingConfigurationError(
            "fixed_fee_product_cross_tenant",
            f"صنف الرسم الثابت يتبع شركة أخرى ({fixed_product.tenant_id}) غير شركة المنصة المفوترة ({platform_tenant.TenantID}).",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    if not getattr(fixed_product, "is_service", False):
        err = BillingConfigurationError(
            "fixed_fee_product_not_service",
            f"صنف الرسم الثابت «{fixed_product.sku}» ليس صنفاً خدمياً (is_service=True).",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    calc = calculate_subscription_billing(subscription)
    if calc["overage_units"] > 0 and not overage_product_id:
        err = BillingConfigurationError(
            "missing_overage_product",
            f"توجد عمليات زائدة ({calc['overage_units']}) ولكن لم يُحدد صنف للعمليات الزائدة.",
            status_code=400,
        )
        if raise_exception:
            raise err
        return err

    if overage_product_id:
        overage_product = Product.objects.filter(pk=overage_product_id).first()
        if not overage_product:
            err = BillingConfigurationError(
                "overage_product_not_found",
                f"صنف العمليات الزائدة برقم {overage_product_id} غير موجود.",
                status_code=400,
            )
            if raise_exception:
                raise err
            return err

        if overage_product.tenant_id != platform_tenant.TenantID:
            err = BillingConfigurationError(
                "overage_product_cross_tenant",
                f"صنف العمليات الزائدة يتبع شركة أخرى ({overage_product.tenant_id}) غير شركة المنصة المفوترة ({platform_tenant.TenantID}).",
                status_code=400,
            )
            if raise_exception:
                raise err
            return err

        if not getattr(overage_product, "is_service", False):
            err = BillingConfigurationError(
                "overage_product_not_service",
                f"صنف العمليات الزائدة «{overage_product.sku}» ليس صنفاً خدمياً (is_service=True).",
                status_code=400,
            )
            if raise_exception:
                raise err
            return err

    return None


@transaction.atomic
def bill_subscription_for_period(
    *,
    subscription_id: int,
    period_start: datetime.date,
    period_end: datetime.date,
    fixed_fee_product_id: int | None = None,
    overage_product_id: int | None = None,
    currency_id: int | None = None,
    user=None,
) -> tuple[SubscriptionBillingRecord, bool]:
    """إصدار فاتورة بيعٍ حقيقيّة لاشتراك خدمة المتابعة والإدخال عن دورة محددة وترحيلها.

    الضمانات الصارمة:
    1. الذرية التامة (transaction.atomic): نجاح كل شيء أو لا شيء.
    2. عدم التكرار (Idempotency): التحقق من وجود SubscriptionBillingRecord لنفس الدورة،
       والقيد الفريد في قاعدة البيانات يحمي من التسابق (race condition).
    3. عزل الشركات: لا تخمين لشركة المنصة، بل تُستنتج حصراً من billing_customer.tenant.
       تُرفض الأصناف التابعة لشركة أخرى أو غير الخدمية قبل أي تعديل.
    4. ترحيل حقيقي: عبر SalesInvoiceSerializer ثم post_sales_invoice الذي يمر عبر post_journal.
       لا كتابة مباشرة لقيود المحاسبة إطلاقاً.
    5. إعادة ضبط العداد والدورة: فقط بعد نجاح الترحيل، يُعاد consumed_quota إلى 0
       وتتقدّم الدورة إلى الشهر التالي.
    """
    from inventory.models import Product
    from sales.models import SalesInvoice, SalesSettings
    from sales.serializers import SalesInvoiceSerializer
    from sales.services import post_sales_invoice

    # 1. قفل صف الاشتراك بدون select_related
    try:
        subscription = ServiceSubscription.objects.select_for_update().get(pk=subscription_id)
    except ServiceSubscription.DoesNotExist:
        raise BillingConfigurationError(
            "subscription_not_found",
            f"اشتراك الخدمة برقم {subscription_id} غير موجود.",
            status_code=404,
        )

    # الأصناف: تجاوز صريح، وإلا لقطة الاشتراك من سياسته، وإلا إعدادات الخادم للصفوف القديمة.
    fixed_fee_product_id, overage_product_id = resolve_subscription_billing_products(
        subscription, fixed_fee_product_id=fixed_fee_product_id, overage_product_id=overage_product_id,
    )

    # 2. فحص idempotency السريع
    existing_record = (
        SubscriptionBillingRecord.objects.select_related("invoice")
        .filter(
            subscription=subscription,
            period_start=period_start,
            period_end=period_end,
        )
        .first()
    )
    if existing_record:
        return existing_record, False

    # 3. الفحص الشامل الموحد
    billing_preflight(
        subscription=subscription,
        period_start=period_start,
        period_end=period_end,
        fixed_fee_product_id=fixed_fee_product_id,
        overage_product_id=overage_product_id,
        check_already_billed=False,
        raise_exception=True,
    )

    customer = subscription.billing_customer
    platform_tenant = customer.tenant
    fixed_product = Product.objects.filter(pk=fixed_fee_product_id).first()
    overage_product = Product.objects.filter(pk=overage_product_id).first() if overage_product_id else None

    calc = calculate_subscription_billing(subscription)

    # أ٤: إذا كان المبلغ الإجمالي صفراً أو دون الحد وبلا رسم ثابت:
    # إنشاء سجل فوترة بدون فاتورة، وتقديم الدورة، وتصفير العداد ضمن المعاملة الذرية
    if calc["total_amount"] <= 0:
        try:
            with transaction.atomic():
                billing_record = SubscriptionBillingRecord.objects.create(
                    subscription=subscription,
                    period_start=period_start,
                    period_end=period_end,
                    invoice=None,
                    monthly_fee=calc["monthly_fee"],
                    included_quota=calc["included_quota"],
                    consumed_quota=calc["consumed_quota"],
                    overage_units=calc["overage_units"],
                    overage_unit_price=calc["overage_unit_price"],
                    overage_fee=calc["overage_fee"],
                    total_amount=Decimal("0.00"),
                )
        except IntegrityError:
            raise BillingPeriodError(
                "billing_record_conflict",
                f"دورة الفوترة ({period_start} إلى {period_end}) لهذا الاشتراك فُوترت "
                f"في معاملةٍ متزامنة؛ أُلغيت الفاتورة المكرّرة ولم تُعتمد.",
                status_code=409,
            )

        next_start, next_end = _calendar_month_bounds(period_end + datetime.timedelta(days=1))

        subscription.consumed_quota = 0
        subscription.period_start = next_start
        subscription.period_end = next_end
        subscription.save(
            update_fields=["consumed_quota", "period_start", "period_end", "updated_at"]
        )

        return billing_record, True

    # 7. حل العملة
    curr = None
    if currency_id:
        curr = Currency.objects.filter(pk=currency_id).first()
    if not curr:
        ss = SalesSettings.objects.filter(tenant=platform_tenant).first()
        if ss and ss.default_currency:
            curr = ss.default_currency
    if not curr:
        curr = Currency.objects.filter(IsBaseCurrency=True).first() or Currency.objects.first()
    if not curr:
        raise BillingConfigurationError(
            "missing_currency",
            "لم يتم العثور على عملة صالحة لإصدار الفاتورة.",
            status_code=400,
        )

    # 8. بناء سطور الفاتورة
    lines_data = []
    # سطر الرسم الشهري الثابت
    if calc["monthly_fee"] > 0 or calc["overage_units"] == 0:
        lines_data.append({
            "product": fixed_product.pk,
            "quantity": Decimal("1.00"),
            "unit_price": calc["monthly_fee"],
            "customer_note": f"اشتراك خدمة المتابعة والإدخال - باقة {subscription.plan} ({period_start} إلى {period_end})",
        })

    # سطر العمليات الزائدة (يُحذف تماماً إن كانت 0)
    if calc["overage_units"] > 0 and overage_product:
        lines_data.append({
            "product": overage_product.pk,
            "quantity": Decimal(str(calc["overage_units"])),
            "unit_price": calc["overage_unit_price"],
            "customer_note": f"عمليات إضافية زائدة عن الباقة ({calc['overage_units']} عملية × {calc['overage_unit_price']})",
        })

    # 9. إنشاء الفاتورة عبر SalesInvoiceSerializer
    invoice_payload = {
        "invoice_kind": SalesInvoice.INVOICE_KIND_SALE,
        "invoice_type": SalesInvoice.INVOICE_CREDIT,
        "customer": customer.pk,
        "currency": curr.pk,
        "invoice_date": period_end,
        "due_date": period_end,
        "stock_on_post": False,
        "notes": f"فاتورة خدمة المتابعة والإدخال لشركة «{subscription.tenant}» عن الفترة {period_start} إلى {period_end}",
        "lines": lines_data,
    }

    serializer = SalesInvoiceSerializer(data=invoice_payload)
    serializer.is_valid(raise_exception=True)
    invoice = serializer.save(tenant=platform_tenant)

    # 10. ترحيل الفاتورة محاسبياً عبر الخدمة المعتمدة
    posted_invoice = post_sales_invoice(invoice, user=user)

    # 11. تسجيل سجل التدقيق والفوترة (مع حماية DB UniqueConstraint)
    #
    # الحارسُ الأوّلُ لعدم التكرار هو القفلُ على صفّ الاشتراك في الخطوة ١: معاملتان
    # متزامنتان تصطفّان، فترى الثانيةُ سجلَّ الأولى في الخطوة ٢ وتعود بلا فاتورة.
    # والقيدُ الفريدُ في القاعدة هو الحارسُ الأخير. فإن سقط الأخيرُ رغم الأوّل فهذا
    # **ليس موضعَ تعافٍ صامت**: الفاتورةُ رُحّلت للتوّ في هذه المعاملة نفسِها، فالعودةُ
    # بـ«السجلّ القائم» تعني اعتمادَ المعاملة وتركَ فاتورةٍ مرحَّلةٍ في الدفاتر لا
    # يذكرها أيُّ سجلِّ فوترة — أي فاتورةٌ مكرَّرةٌ صامتةٌ على الزبون. ولذلك نرفع
    # الخطأ فترتدّ المعاملةُ كاملةً بالفاتورة وقيدِها.
    #
    # و`transaction.atomic` الداخليّةُ نقطةُ حفظ: بدونها يترك خطأُ القاعدة المعاملةَ
    # الخارجيّةَ في حالةٍ معطوبةٍ فيرتدّ أيُّ استعلامٍ لاحقٍ بـ`TransactionManagementError`
    # بدل الخطأ الحقيقيّ.
    try:
        with transaction.atomic():
            billing_record = SubscriptionBillingRecord.objects.create(
                subscription=subscription,
                period_start=period_start,
                period_end=period_end,
                invoice=posted_invoice,
                monthly_fee=calc["monthly_fee"],
                included_quota=calc["included_quota"],
                consumed_quota=calc["consumed_quota"],
                overage_units=calc["overage_units"],
                overage_unit_price=calc["overage_unit_price"],
                overage_fee=calc["overage_fee"],
                total_amount=calc["total_amount"],
            )
    except IntegrityError:
        raise BillingPeriodError(
            "billing_record_conflict",
            f"دورة الفوترة ({period_start} إلى {period_end}) لهذا الاشتراك فُوترت "
            f"في معاملةٍ متزامنة؛ أُلغيت الفاتورة المكرّرة ولم تُعتمد.",
            status_code=409,
        )

    # 12. تدوير دورة الاشتراك وتصفير العداد بأمان
    next_start, next_end = _calendar_month_bounds(period_end + datetime.timedelta(days=1))

    subscription.consumed_quota = 0
    subscription.period_start = next_start
    subscription.period_end = next_end
    subscription.save(
        update_fields=["consumed_quota", "period_start", "period_end", "updated_at"]
    )

    return billing_record, True


def bill_subscriptions_for_period(
    *,
    period_start: datetime.date,
    period_end: datetime.date,
    fixed_fee_product_id: int | None = None,
    overage_product_id: int | None = None,
    currency_id: int | None = None,
    subscription_id: int | None = None,
    tenant_id: int | None = None,
    user=None,
) -> dict:
    """تشغيل الفوترة لمجموعة الاشتراكات المستحقة للدورة المحددة.

    - تفلتر الاشتراكات النشطة فقط.
    - تقبل التصفية باشتراك بعينه أو شركة بعينها.
    - تتجاهل الاشتراكات غير المستحقة أو التي فُوّترت مسبقاً دون إيقاف باقي الدفعة.
    """
    qs = ServiceSubscription.objects.all()
    if subscription_id:
        qs = qs.filter(pk=subscription_id)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    billed = []
    already_billed = []
    skipped = []
    errors = []

    candidates = list(qs.order_by("id"))
    for sub in candidates:
        # فحص مسبق للاشتراكات غير المحددة صراحة
        is_targeted = bool(subscription_id or tenant_id)

        if sub.status != ServiceSubscription.Status.ACTIVE:
            if is_targeted:
                errors.append({
                    "subscription_id": sub.id,
                    "tenant_id": sub.tenant_id,
                    "error": f"الاشتراك غير نشط ({sub.get_status_display()})",
                })
            else:
                skipped.append({
                    "subscription_id": sub.id,
                    "tenant_id": sub.tenant_id,
                    "reason": f"غير نشط ({sub.get_status_display()})",
                })
            continue

        # فحص الدورة إن كان مسجلاً
        if sub.period_start and sub.period_end:
            if sub.period_start != period_start or sub.period_end != period_end:
                # تحقق مما إذا كان قد فُوّتر لهذه الدورة مسبقاً
                existing = (
                    SubscriptionBillingRecord.objects.select_related("invoice")
                    .filter(
                        subscription=sub,
                        period_start=period_start,
                        period_end=period_end,
                    )
                    .first()
                )
                if existing:
                    already_billed.append({
                        "subscription_id": sub.id,
                        "tenant_id": sub.tenant_id,
                        "invoice_id": existing.invoice_id,
                        "invoice_number": existing.invoice.invoice_number if existing.invoice else "",
                        "total_amount": str(existing.total_amount),
                    })
                    continue
                if is_targeted:
                    errors.append({
                        "subscription_id": sub.id,
                        "tenant_id": sub.tenant_id,
                        "error": (
                            f"دورة الاشتراك ({sub.period_start} إلى {sub.period_end}) "
                            f"لا تطابق دورة الفوترة ({period_start} إلى {period_end})"
                        ),
                    })
                else:
                    skipped.append({
                        "subscription_id": sub.id,
                        "tenant_id": sub.tenant_id,
                        "reason": f"دورة الاشتراك ({sub.period_start} إلى {sub.period_end}) لا تطابق الدورة المطلوبة",
                    })
                continue

        # محاولة الفوترة
        try:
            record, created = bill_subscription_for_period(
                subscription_id=sub.id,
                period_start=period_start,
                period_end=period_end,
                fixed_fee_product_id=fixed_fee_product_id,
                overage_product_id=overage_product_id,
                currency_id=currency_id,
                user=user,
            )
            item = {
                "subscription_id": sub.id,
                "tenant_id": sub.tenant_id,
                "invoice_id": record.invoice_id,
                "invoice_number": record.invoice.invoice_number if record.invoice else "",
                "total_amount": str(record.total_amount),
            }
            if created:
                billed.append(item)
            else:
                already_billed.append(item)
        except Exception as exc:
            errors.append({
                "subscription_id": sub.id,
                "tenant_id": sub.tenant_id,
                "error": str(exc),
            })

    return {
        "period_start": str(period_start),
        "period_end": str(period_end),
        "candidates_count": len(candidates),
        "billed_count": len(billed),
        "already_billed_count": len(already_billed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "billed": billed,
        "already_billed": already_billed,
        "skipped": skipped,
        "errors": errors,
    }


# ==============================================================================
# المرحلة الثامنة (م٨-ب): بوّابة التوظيف المنصّيّة
# ==============================================================================

#: انتقالات آلة حالات المتقدم المعلنة والصريحة
APPLICANT_TRANSITIONS: dict[str, set[str]] = {
    JobApplicant.Status.NEW: {
        JobApplicant.Status.SCREENING,
        JobApplicant.Status.REJECTED,
    },
    JobApplicant.Status.SCREENING: {
        JobApplicant.Status.INTERVIEW,
        JobApplicant.Status.REJECTED,
    },
    JobApplicant.Status.INTERVIEW: {
        JobApplicant.Status.OFFERED,
        JobApplicant.Status.REJECTED,
    },
    JobApplicant.Status.OFFERED: {
        JobApplicant.Status.HIRED,
        JobApplicant.Status.REJECTED,
    },
    JobApplicant.Status.HIRED: set(),
    JobApplicant.Status.REJECTED: {
        JobApplicant.Status.SCREENING,
    },
}


def is_platform_recruiter(user) -> bool:
    """هل المستخدم مسؤول توظيف في المنصة؟"""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return PlatformRecruiter.objects.filter(user=user, is_active=True).exists()


def create_platform_recruiter(user: User) -> PlatformRecruiter:
    """تعيين مستخدم كمسؤول توظيف للمنصة."""
    recruiter, _ = PlatformRecruiter.objects.get_or_create(user=user, defaults={"is_active": True})
    if not recruiter.is_active:
        recruiter.is_active = True
        recruiter.save(update_fields=["is_active", "updated_at"])
    return recruiter


def revoke_platform_recruiter(user: User) -> None:
    """إلغاء صلاحية مسؤول توظيف المنصة."""
    PlatformRecruiter.objects.filter(user=user).update(is_active=False)


def create_job_posting(
    *,
    title: str,
    description: str,
    created_by=None,
    specialty: str = "",
    requirements: str = "",
    location: str = "",
    employment_type: str = "",
    salary_range: str = "",
    expires_at=None,
) -> JobPosting:
    """إنشاء إعلان وظيفة منصي مع توليد مفتاح عشوائي غير قابل للتخمين.

    **نقطةُ الكتابة الوحيدة** لإعلان الوظيفة: توليدُ المفتاح هنا لا في الـview،
    فلا تتباعد نسختان من التوليد ولا يبقى سلوكٌ يُختبَر عبر HTTP وحدَه.
    """
    if not title or not title.strip():
        raise ValidationError({"title": "عنوان الوظيفة إلزامي."})
    if not description or not description.strip():
        raise ValidationError({"description": "وصف الوظيفة إلزامي."})

    token = secrets.token_urlsafe(32)
    return JobPosting.objects.create(
        title=title.strip(),
        specialty=(specialty or "").strip()[:100],
        description=description.strip(),
        requirements=(requirements or "").strip(),
        location=(location or "").strip(),
        employment_type=employment_type or "",
        salary_range=(salary_range or "").strip(),
        token=token,
        is_open=True,
        expires_at=expires_at,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
    )


def close_job_posting(*, job: JobPosting) -> JobPosting:
    """إغلاق التقديم على الوظيفة يدوياً."""
    if job.is_open:
        job.is_open = False
        job.closed_at = timezone.now()
        job.save(update_fields=["is_open", "closed_at", "updated_at"])
    return job


def reopen_job_posting(*, job: JobPosting) -> JobPosting:
    """إعادة فتح التقديم على الوظيفة."""
    if not job.is_open:
        job.is_open = True
        job.closed_at = None
        job.save(update_fields=["is_open", "closed_at", "updated_at"])
    return job


def regenerate_job_posting_token(*, job: JobPosting) -> JobPosting:
    """إبطال الرابط العام السابق وتوليد رابط جديد فوراً."""
    job.token = secrets.token_urlsafe(32)
    job.save(update_fields=["token", "updated_at"])
    return job


def job_is_live(job: JobPosting, *, now=None) -> bool:
    """هل الوظيفةُ مفتوحةٌ وصالحةٌ للتقديم — **بتفويضٍ للنموذج لا بنسخةٍ عنه**.

    القاعدةُ تسكن `JobPosting.is_live` لأنّ المُسلسِلَ والقوالبَ تسألها هناك؛
    ونسخةٌ ثانيةٌ هنا تتباعد بصمت. ويبقى المُغلِّفُ لأنّه يقبل `now` للاختبار.
    """
    return job.is_live(now=now)


def resolve_public_job(token: str) -> JobPosting:
    """جلب الوظيفة خلف المفتاح العام أو إطلاق استثناء بحسب حالتها."""
    job = JobPosting.objects.filter(token=token).first()
    if job is None:
        raise NotFound("لا توجد وظيفة خلف هذا الرابط.")
    if not job_is_live(job):
        raise JobGone("انتهت فترة التقديم على هذه الوظيفة أو تم إغلاقها.")
    return job


def job_public_url(token: str) -> str:
    """بناء الرابط العام لصفحة عرض الوظيفة (صفحة ويب لا نقطة API)."""
    base = str(getattr(settings, "PLATFORM_JOB_PUBLIC_BASE_URL", "")).rstrip("/")
    path = str(getattr(settings, "PLATFORM_JOB_PUBLIC_PATH", "/careers/job")).rstrip("/")
    return f"{base}{path}/{token}"


def invitation_public_url(raw_token: str) -> str:
    """بناء الرابط العام لصفحة قبول الدعوة (صفحة ويب لا نقطة API)."""
    base = str(getattr(settings, "PLATFORM_HIRING_INVITATION_BASE_URL", "")).rstrip("/")
    path = str(getattr(settings, "PLATFORM_HIRING_INVITATION_PATH", "/careers/invite")).rstrip("/")
    return f"{base}{path}/{raw_token}"


@transaction.atomic
def submit_application(
    *,
    job: JobPosting,
    name: str,
    phone: str,
    email: str = "",
    about: str = "",
    cv_url: str = "",
    cv_name: str = "",
) -> JobApplicant:
    """تقديم طلب توظيف على وظيفة منصية بحالة 'new' محجورة."""
    if not job_is_live(job):
        raise JobGone("انتهت فترة التقديم على هذه الوظيفة.")

    clean_name = (name or "").strip()
    clean_phone = (phone or "").strip()
    if not clean_name:
        raise ValidationError({"name": "اسم المتقدم إلزامي."})
    if not clean_phone:
        raise ValidationError({"phone": "رقم التواصل إلزامي."})

    for _ in range(5):
        try:
            with transaction.atomic():
                return JobApplicant.objects.create(
                    job=job,
                    name=clean_name,
                    phone=clean_phone,
                    email=(email or "").strip(),
                    about=(about or "").strip(),
                    cv_url=(cv_url or "").strip(),
                    cv_name=(cv_name or "").strip(),
                    status=JobApplicant.Status.NEW,
                    reference_code=secrets.token_hex(4).upper(),
                )
        except IntegrityError:
            continue
    raise ValidationError({"detail": "تعذّر تسجيل الطلب، حاول مرة أخرى."})


@transaction.atomic
def transition_applicant_status(
    *,
    applicant: JobApplicant,
    target_status: str,
    actor=None,
) -> JobApplicant:
    """تحريك المتقدم بين مراحل الفرز المعلنة في آلة الحالات.

    ترتيب القفل الصارم:
    JobApplicantInvitation -> JobApplicant.
    ملاحظة: لا select_related مع select_for_update.
    """
    if target_status == JobApplicant.Status.HIRED:
        raise ValidationError(
            {"status": "حالة «مقبول» تُبلَغ بقبول المتقدّم للدعوة وإنشاء حسابه."}
        )

    # 1. قفل الدعوات النشطة أولاً بحسب ترتيب القفل المعلَن
    active_invitations = list(
        JobApplicantInvitation.objects.select_for_update().filter(
            applicant_id=applicant.pk,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
    )

    # 2. قفل المتقدم والتحقق من الانتقال المسموح
    locked_applicant = JobApplicant.objects.select_for_update().get(pk=applicant.pk)

    allowed = APPLICANT_TRANSITIONS.get(locked_applicant.status, set())
    if target_status not in allowed:
        raise ValidationError(
            {"status": f"الانتقال من {locked_applicant.status} إلى {target_status} غير مسموح به."}
        )

    # إبطال أي دعوات نشطة إذا خرج المتقدم من حالة العرض
    if locked_applicant.status == JobApplicant.Status.OFFERED and target_status != JobApplicant.Status.OFFERED:
        now = timezone.now()
        for inv in active_invitations:
            inv.revoked_at = now
            inv.save(update_fields=["revoked_at"])

    locked_applicant.status = target_status
    locked_applicant.save(update_fields=["status", "updated_at"])
    applicant.status = locked_applicant.status
    applicant.updated_at = locked_applicant.updated_at
    return locked_applicant


def rate_applicant(
    *,
    applicant: JobApplicant,
    rating=None,
    notes=None,
) -> JobApplicant:
    """تقييم المتقدم وتسجيل ملاحظات مسؤول التوظيف."""
    fields = ["updated_at"]
    if rating is not None:
        try:
            r = int(rating)
        except (ValueError, TypeError):
            raise ValidationError({"rating": "التقييم يجب أن يكون عدداً صحيحاً."})
        if not 0 <= r <= 5:
            raise ValidationError({"rating": "التقييم من صفر إلى 5 نجوم."})
        applicant.rating = r
        fields.append("rating")
    if notes is not None:
        applicant.notes = str(notes)
        fields.append("notes")
    applicant.save(update_fields=fields)
    return applicant


@transaction.atomic
def create_applicant_invitation(
    *,
    applicant: JobApplicant,
    created_by=None,
    expires_in_hours: int = 72,
) -> tuple[JobApplicantInvitation, str]:
    """إصدار دعوة قبول التوظيف للمرشح مع توليد رمز مهشر (SHA-256) وإبطال الدعوات السابقة.

    ترتيب القفل الصارم:
    `JobApplicantInvitation -> JobApplicant`.
    ملاحظة: لا يُستعمل select_related مع select_for_update.
    """
    if not isinstance(expires_in_hours, int) or not (1 <= expires_in_hours <= 168):
        raise ValidationError({"expires_in_hours": "مدة صلاحية الدعوة يجب أن تكون بين 1 و168 ساعة."})

    now = timezone.now()

    # 1. قفل الدعوات السابقة غير المستهلكة وإبطالها
    # بترتيب الأقفال الصارم المعلَن: JobApplicantInvitation -> JobApplicant
    active_invitations = list(
        JobApplicantInvitation.objects.select_for_update()
        .filter(
            applicant_id=applicant.pk,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
    )
    for prev_inv in active_invitations:
        prev_inv.revoked_at = now
        prev_inv.save(update_fields=["revoked_at"])

    # 2. قفل المتقدم والتحقق من حالته
    locked_applicant = (
        JobApplicant.objects.select_for_update()
        .get(pk=applicant.pk)
    )

    if locked_applicant.hired_employee_id is not None:
        raise ValidationError({"status": "تم توظيف هذا المتقدم مسبقاً ولا يمكن إصدار دعوة له."})

    if locked_applicant.status != JobApplicant.Status.OFFERED:
        raise ValidationError({"status": "لا يمكن إصدار دعوة إلا لمتقدم في حالة عرض عمل (offered)."})

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = now + datetime.timedelta(hours=expires_in_hours)

    invitation = JobApplicantInvitation.objects.create(
        applicant=locked_applicant,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
    )

    return invitation, raw_token


def resolve_public_invitation(token: str) -> JobApplicantInvitation:
    """التحقق من رابط الدعوة وإعادته أو إطلاق استثناء 404 أو 410."""
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    inv = JobApplicantInvitation.objects.select_related("applicant__job").filter(
        token_hash=token_hash
    ).first()

    if inv is None:
        raise NotFound("رمز الدعوة غير موجود.")

    if inv.is_consumed:
        raise InvitationGone("انتهت صلاحية رابط الدعوة أو تم استخدامه مسبقاً.")

    return inv


@transaction.atomic
def accept_applicant_invitation(
    *,
    token: str,
    password: str,
    username: str = "",
) -> tuple[User, PlatformEmployee, JobApplicant]:
    """قبول دعوة المرشح وإنشاء حسابه وموظف المنصة ومتابعة حالته.

    ترتيب القفل الصارم: JobApplicantInvitation -> JobApplicant
    ملاحظة: لا select_related مع select_for_update.
    """
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()

    # 1. قفل الدعوة
    locked_inv = (
        JobApplicantInvitation.objects.select_for_update()
        .filter(token_hash=token_hash)
        .first()
    )
    if locked_inv is None:
        raise NotFound("رمز الدعوة غير موجود.")

    if locked_inv.is_consumed:
        raise InvitationGone("انتهت صلاحية رابط الدعوة أو تم استخدامه مسبقاً.")

    # 2. قفل المتقدم
    locked_applicant = (
        JobApplicant.objects.select_for_update()
        .get(pk=locked_inv.applicant_id)
    )
    if locked_applicant.status == JobApplicant.Status.HIRED:
        raise InvitationGone("تم قبول هذا الطلب مسبقاً.")
    if locked_applicant.status != JobApplicant.Status.OFFERED:
        raise InvitationGone("طلب التوظيف ليس في حالة عرض عمل.")

    # 3. التحقق من كلمة المرور واسم المستخدم
    chosen_username = (username or "").strip()
    if not chosen_username:
        if locked_applicant.email and not User.objects.filter(username=locked_applicant.email).exists():
            chosen_username = locked_applicant.email
        else:
            base_user = (locked_applicant.email.split("@")[0] if locked_applicant.email else "staff").replace(".", "_")
            chosen_username = f"{base_user}_{secrets.token_hex(3)}"

    if User.objects.filter(username=chosen_username).exists():
        raise ValidationError({"username": "اسم المستخدم موجود بالفعل."})

    if not password:
        raise ValidationError({"password": "كلمة المرور مطلوبة."})

    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    user_for_validation = User(username=chosen_username, email=locked_applicant.email)
    try:
        validate_password(password, user=user_for_validation)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)})

    # 4. إنشاء المستخدم داخل نقطة ذرية لحماية المعاملة من فشل سباق اسم المستخدم
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=chosen_username,
                email=locked_applicant.email,
                password=password,
            )
    except IntegrityError:
        raise ValidationError({"username": "اسم المستخدم موجود بالفعل."})

    # 5. إنشاء موظف المنصة
    #
    # **التخصّصُ من حقل الوظيفة لا من عنوانها**: العنوانُ نصٌّ حرٌّ بطول ٢٠٠ محرف
    # والعمودُ الهدفُ ١٠٠، فكتابتُه فيه تُخطئ على MySQL وتُبتَر صامتاً على SQLite.
    # وأهمُّ منه أنّ `PolicyProfile` يُطابَق بالتخصّص: عنوانٌ حرٌّ لا يطابق شيئاً
    # فيُحتسب أداءُ الموظّف الجديد بسياسةٍ افتراضيّةٍ بلا أن يلاحظ أحد.
    job = locked_applicant.job
    specialty = ((job.specialty if job else "") or "").strip()[:100]
    employee = PlatformEmployee.objects.create(
        user=user,
        specialty=specialty,
        status=PlatformEmployee.Status.ACTIVE,
    )

    # 6. تحديث المتقدم
    locked_applicant.status = JobApplicant.Status.HIRED
    locked_applicant.hired_employee = employee
    locked_applicant.save(update_fields=["status", "hired_employee", "updated_at"])

    # 7. استهلاك الدعوة
    locked_inv.accepted_at = timezone.now()
    locked_inv.save(update_fields=["accepted_at"])

    return user, employee, locked_applicant


# ==============================================================================
# التذكرة 210-B: فحص صحة الدفاتر والتشغيل، والإسناد والطاقة، واكتساب العميل
# ==============================================================================


class HealthCheckError(PlatformOpsError):
    """خطأ في عمليات فحص صحة الشركة."""


class HealthCheckConflict(HealthCheckError):
    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


class AcquisitionError(PlatformOpsError):
    """خطأ في تسجيل اكتساب العميل."""


class AcquisitionConflict(AcquisitionError):
    def __init__(self, code: str, detail: str):
        super().__init__(code, detail, status_code=409)


#: كتالوج بنود فحص صحة الشركة — ثابتٌ في الكود لا إدخالاً حرّاً (§٦، §١١).
#: `auto=True` تعني أن `_compute_auto_health_evidence` تملأ دليله عند الإنشاء/التحديث،
#: وغير الآلي يبدأ `FOLLOW_UP` بلا دليل حتى يُدخله السوبر أدمن يدوياً.
HEALTH_CHECK_ITEM_CATALOG: dict[str, dict] = {
    "opening_balance_completeness": {"label": "اكتمال القيد الافتتاحي", "mandatory": True, "auto": False},
    "unposted_sales_documents": {"label": "مستندات مبيعات غير مرحَّلة", "mandatory": True, "auto": True},
    "bank_reconciliation": {"label": "مطابقة الحسابات البنكية", "mandatory": True, "auto": False},
    "receivables_aging": {"label": "تقادم ذمم العملاء", "mandatory": False, "auto": True},
    "fiscal_periods": {"label": "ضبط الفترات المالية", "mandatory": True, "auto": False},
    "inventory_provisional_layers": {"label": "طبقات تكلفة مخزون مؤقتة", "mandatory": False, "auto": True},
    "review_errors": {"label": "أخطاء مراجعة سابقة", "mandatory": False, "auto": False},
}

#: وحدات حِمل الشركة حسب تعقيد أحدث فحصٍ تأسيسي معتمد لها — ثابتٌ واحد موثَّق (§٦).
#: شركة onboarding أو بلا فحصٍ تأسيسي بعد تُحتسب بوسط `medium` حتى يُعتمد فحصها.
CAPACITY_LOAD_UNITS: dict[str, int] = {
    CompanyHealthCheck.Complexity.LOW: 1,
    CompanyHealthCheck.Complexity.MEDIUM: 2,
    CompanyHealthCheck.Complexity.HIGH: 3,
}
DEFAULT_CAPACITY_LOAD_UNITS = CAPACITY_LOAD_UNITS[CompanyHealthCheck.Complexity.MEDIUM]


def _log_operation_event(
    tenant,
    *,
    domain: str,
    action: str,
    subject_id: int,
    actor=None,
    correlation_id: str = "",
    reason: str = "",
    details: dict | None = None,
):
    """حدثُ تدقيقٍ واحد غير قابل للمحو لعمليات الإسناد/الصحة/الاكتساب — نمط `_log_subscription_event`."""
    return PlatformOperationEvent.objects.create(
        tenant_id=getattr(tenant, "pk", tenant),
        domain=domain,
        action=action,
        subject_id=subject_id,
        reason=str(reason or "")[:500],
        actor=actor if getattr(actor, "pk", None) else None,
        correlation_id=str(correlation_id or "")[:64],
        details=details or {},
    )


def _compute_auto_health_evidence(tenant_obj: Tenant) -> dict[str, dict]:
    """يحسب أدلة البنود الآلية فقط — قراءةٌ صرفة بلا أي كتابة.

    كل بندٍ لا يمكن قياسُه بأمانٍ هنا (افتتاحية قد تُنشئ صفاً بصمت، مطابقة بنكية،
    فترات مالية، أخطاء مراجعة تلزمها بيانات بوابة المحاسب) يبقى **يدوياً** عمداً —
    القرار المسجَّل في تقرير التسليم لا تخميناً.
    """
    from sales.models import SalesInvoice

    evidence: dict[str, dict] = {}

    unposted_count = (
        SalesInvoice.objects.filter(tenant=tenant_obj)
        .exclude(status=SalesInvoice.STATUS_POSTED)
        .count()
    )
    evidence["unposted_sales_documents"] = {
        "evidence_value": Decimal(unposted_count),
        "evidence_note": f"{unposted_count} {term(tenant_obj, 'doc.sales_invoice')} غير مرحَّلة",
        "status": (
            CompanyHealthCheckItem.ItemStatus.HEALTHY if unposted_count == 0
            else CompanyHealthCheckItem.ItemStatus.RISK if unposted_count > 10
            else CompanyHealthCheckItem.ItemStatus.FOLLOW_UP
        ),
    }

    today = timezone.localdate()
    overdue_count = (
        SalesInvoice.objects.filter(tenant=tenant_obj, status=SalesInvoice.STATUS_POSTED)
        .filter(Q(due_date__lt=today) | Q(due_date__isnull=True, invoice_date__lt=today))
        .exclude(amount_paid__gte=models.F("grand_total"))
        .count()
    )
    evidence["receivables_aging"] = {
        "evidence_value": Decimal(overdue_count),
        "evidence_note": f"{overdue_count} فاتورة متأخرة السداد",
        "status": (
            CompanyHealthCheckItem.ItemStatus.HEALTHY if overdue_count == 0
            else CompanyHealthCheckItem.ItemStatus.RISK if overdue_count > 5
            else CompanyHealthCheckItem.ItemStatus.FOLLOW_UP
        ),
    }

    from inventory.fifo import pending_provisional_layers

    layers_count = len(pending_provisional_layers(tenant_id=tenant_obj.pk))
    evidence["inventory_provisional_layers"] = {
        "evidence_value": Decimal(layers_count),
        "evidence_note": f"{layers_count} طبقة تكلفة مؤقتة معلَّقة",
        "status": (
            CompanyHealthCheckItem.ItemStatus.HEALTHY if layers_count == 0
            else CompanyHealthCheckItem.ItemStatus.RISK if layers_count > 20
            else CompanyHealthCheckItem.ItemStatus.FOLLOW_UP
        ),
    }
    return evidence


@transaction.atomic
def create_health_check_draft(
    *,
    tenant,
    kind: str = CompanyHealthCheck.Kind.BASELINE,
    period=None,
    notes: str = "",
    actor=None,
) -> CompanyHealthCheck:
    """ينشئ فحص صحة مسودة لشركةٍ مؤهَّلة للخدمة وحدها — يملأ البنود الآلية فوراً.

    فحصٌ جديدٌ صفٌّ جديدٌ دوماً (لا تعديل على صفّ سابق) — التاريخ يبقى كاملاً.
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.filter(pk=tenant).first()
    if tenant_obj is None:
        raise HealthCheckError("tenant_not_found", "الشركة غير موجودة.")
    if tenant_obj.pk not in set(eligible_service_tenant_ids()):
        raise HealthCheckError(
            "subscription_not_eligible", "خدمة المتابعة والإدخال غير مؤهَّلة لهذه الشركة.",
        )
    if kind not in CompanyHealthCheck.Kind.values:
        raise HealthCheckError("invalid_kind", f"نوع الفحص غير صالح: {kind}")

    check_period = period or timezone.localdate()
    if kind == CompanyHealthCheck.Kind.MONTHLY:
        check_period = check_period.replace(day=1)

    check = CompanyHealthCheck.objects.create(
        tenant=tenant_obj,
        kind=kind,
        status=CompanyHealthCheck.Status.DRAFT,
        period=check_period,
        notes=str(notes or ""),
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    auto_evidence = _compute_auto_health_evidence(tenant_obj)
    for code, meta in HEALTH_CHECK_ITEM_CATALOG.items():
        signal = auto_evidence.get(code) if meta["auto"] else None
        CompanyHealthCheckItem.objects.create(
            health_check=check,
            code=code,
            status=signal["status"] if signal else CompanyHealthCheckItem.ItemStatus.FOLLOW_UP,
            evidence_value=signal["evidence_value"] if signal else None,
            evidence_note=signal["evidence_note"] if signal else "",
            source=CompanyHealthCheckItem.Source.AUTO if meta["auto"] else CompanyHealthCheckItem.Source.MANUAL,
            mandatory=meta["mandatory"],
        )
    return check


ALLOWED_HEALTH_CHECK_UPDATE_FIELDS = frozenset({"complexity", "notes", "period"})


@transaction.atomic
def update_health_check(*, check, **changes) -> CompanyHealthCheck:
    """يعدّل حقول الفحص نفسه (التعقيد والملاحظات) على مسودة — التعقيد إلزامي قبل الاعتماد."""
    unknown = set(changes) - ALLOWED_HEALTH_CHECK_UPDATE_FIELDS
    if unknown:
        raise HealthCheckError("unsupported_field", f"حقل غير مسموح بتعديله: {', '.join(sorted(unknown))}")
    if changes.get("complexity") and changes["complexity"] not in CompanyHealthCheck.Complexity.values:
        raise HealthCheckError("invalid_complexity", f"تعقيد غير صالح: {changes['complexity']}")

    check_pk = getattr(check, "pk", check)
    locked_check = CompanyHealthCheck.objects.select_for_update().get(pk=check_pk)
    if locked_check.status != CompanyHealthCheck.Status.DRAFT:
        raise HealthCheckConflict("health_check_immutable", "لا يمكن تعديل فحصٍ معتمد.")
    for field, value in changes.items():
        setattr(locked_check, field, value)
    locked_check.save(update_fields=[*changes.keys(), "updated_at"])
    return locked_check


@transaction.atomic
def refresh_health_check_auto_items(*, check) -> CompanyHealthCheck:
    """يعيد حساب البنود الآلية فقط على مسودة — لا يمسّ البنود اليدوية ولا يعمل على فحصٍ معتمد."""
    check_pk = getattr(check, "pk", check)
    locked_check = CompanyHealthCheck.objects.select_for_update().get(pk=check_pk)
    if locked_check.status != CompanyHealthCheck.Status.DRAFT:
        raise HealthCheckConflict("health_check_immutable", "لا يمكن تحديث بنود فحصٍ معتمد.")
    tenant_obj = Tenant.objects.get(pk=locked_check.tenant_id)
    auto_evidence = _compute_auto_health_evidence(tenant_obj)
    now = timezone.now()
    for code, signal in auto_evidence.items():
        CompanyHealthCheckItem.objects.filter(health_check=locked_check, code=code).update(
            status=signal["status"],
            evidence_value=signal["evidence_value"],
            evidence_note=signal["evidence_note"],
            updated_at=now,
        )
    return locked_check


ALLOWED_HEALTH_ITEM_UPDATE_FIELDS = frozenset({
    "status", "evidence_value", "evidence_note", "action", "owner", "due_date",
})


@transaction.atomic
def update_health_check_item(*, item, **changes) -> CompanyHealthCheckItem:
    """يعدّل بنداً واحداً على مسودة — الفحص المعتمد غير قابل للتعديل."""
    unknown = set(changes) - ALLOWED_HEALTH_ITEM_UPDATE_FIELDS
    if unknown:
        raise HealthCheckError("unsupported_field", f"حقل غير مسموح بتعديله: {', '.join(sorted(unknown))}")
    if "status" in changes and changes["status"] not in CompanyHealthCheckItem.ItemStatus.values:
        raise HealthCheckError("invalid_item_status", f"حالة بند غير صالحة: {changes['status']}")

    item_pk = getattr(item, "pk", item)
    locked_item = CompanyHealthCheckItem.objects.select_for_update().get(pk=item_pk)
    check_status = (
        CompanyHealthCheck.objects.filter(pk=locked_item.health_check_id).values_list("status", flat=True).first()
    )
    if check_status != CompanyHealthCheck.Status.DRAFT:
        raise HealthCheckConflict("health_check_immutable", "لا يمكن تعديل بندٍ في فحصٍ معتمد.")

    for field, value in changes.items():
        setattr(locked_item, field, value)
    locked_item.save(update_fields=[*changes.keys(), "updated_at"])
    return locked_item


def latest_approved_baseline(tenant) -> CompanyHealthCheck | None:
    """أحدث فحصٍ تأسيسيٍّ معتمد لشركة — «الأساس الحالي» في كل مكانٍ يُستعمل فيه."""
    tenant_id = getattr(tenant, "pk", tenant)
    return (
        CompanyHealthCheck.objects.filter(
            tenant_id=tenant_id,
            kind=CompanyHealthCheck.Kind.BASELINE,
            status=CompanyHealthCheck.Status.APPROVED,
        )
        .order_by("-approved_at")
        .first()
    )


@transaction.atomic
def approve_health_check(*, check, actor=None, correlation_id: str = "") -> CompanyHealthCheck:
    """يعتمد فحصاً — ذرّيّ ومقفول، ويرفض بوضوح نقص الدليل أو التعقيد قبل الاعتماد."""
    check_pk = getattr(check, "pk", check)
    locked_check = CompanyHealthCheck.objects.select_for_update().get(pk=check_pk)
    if locked_check.status == CompanyHealthCheck.Status.APPROVED:
        raise HealthCheckConflict("already_approved", "الفحص معتمد بالفعل.")
    if not locked_check.complexity:
        raise HealthCheckError("complexity_required", "قدّر تعقيد الشركة قبل اعتماد الفحص.")

    missing = list(
        locked_check.items.filter(mandatory=True, evidence_value__isnull=True)
        .filter(Q(evidence_note__isnull=True) | Q(evidence_note=""))
        .values_list("code", flat=True)
    )
    if missing:
        raise HealthCheckError(
            "evidence_missing", f"بنود إلزامية بلا دليل رقمي أو ملاحظة: {', '.join(missing)}",
        )

    locked_check.status = CompanyHealthCheck.Status.APPROVED
    locked_check.approved_by = actor if getattr(actor, "pk", None) else None
    locked_check.approved_at = timezone.now()
    locked_check.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _log_operation_event(
        locked_check.tenant_id,
        domain=PlatformOperationEvent.Domain.HEALTH_CHECK,
        action=PlatformOperationEvent.Action.HEALTH_CHECK_APPROVED,
        subject_id=locked_check.pk,
        actor=actor,
        correlation_id=correlation_id,
        details={"kind": locked_check.kind, "complexity": locked_check.complexity},
    )
    return locked_check


#: رمزُ البند ← نوعُ أمر العمل الأنسب لمعالجته — تقريبٌ معقول لا حسمٌ نهائي (خارج 210-B تدقيقه).
_HEALTH_ITEM_WORK_ORDER_KIND = {
    "opening_balance_completeness": WorkOrder.Kind.DATA_ENTRY,
    "unposted_sales_documents": WorkOrder.Kind.DATA_ENTRY,
    "bank_reconciliation": WorkOrder.Kind.REVIEW,
    "receivables_aging": WorkOrder.Kind.REVIEW,
    "fiscal_periods": WorkOrder.Kind.ADMIN_DIRECTIVE,
    "inventory_provisional_layers": WorkOrder.Kind.REVIEW,
    "review_errors": WorkOrder.Kind.REVIEW,
}


@transaction.atomic
def convert_health_check_item_to_work_order(*, item, actor=None, correlation_id: str = "") -> WorkOrder:
    """يحوّل بند FOLLOW_UP/RISK إلى أمر عمل ويربطه — تكرار الاستدعاء idempotent يعيد نفس الأمر."""
    item_pk = getattr(item, "pk", item)
    locked_item = CompanyHealthCheckItem.objects.select_for_update().get(pk=item_pk)
    if locked_item.work_order_id:
        return locked_item.work_order
    if locked_item.status not in (CompanyHealthCheckItem.ItemStatus.FOLLOW_UP, CompanyHealthCheckItem.ItemStatus.RISK):
        raise HealthCheckError("item_not_convertible", "لا يجوز تحويل بندٍ سليم أو غير منطبق إلى أمر عمل.")

    check = CompanyHealthCheck.objects.select_related("tenant").get(pk=locked_item.health_check_id)
    label = HEALTH_CHECK_ITEM_CATALOG.get(locked_item.code, {}).get("label", locked_item.code)
    work_order = create_work_order(
        tenant=check.tenant,
        title=f"معالجة بند صحة: {label}",
        kind=_HEALTH_ITEM_WORK_ORDER_KIND.get(locked_item.code, WorkOrder.Kind.ADMIN_DIRECTIVE),
        source=WorkOrder.Source.ADMIN,
        description=locked_item.evidence_note or locked_item.action or "",
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    locked_item.work_order = work_order
    locked_item.save(update_fields=["work_order", "updated_at"])
    _log_operation_event(
        check.tenant_id,
        domain=PlatformOperationEvent.Domain.HEALTH_CHECK,
        action=PlatformOperationEvent.Action.HEALTH_CHECK_ITEM_CONVERTED,
        subject_id=locked_item.pk,
        actor=actor,
        correlation_id=correlation_id,
        details={"code": locked_item.code, "work_order_id": work_order.pk},
    )
    return work_order


def compare_health_baseline(*, tenant) -> dict:
    """يقارن آخر فحصين تأسيسيين معتمدين بنداً بنداً — قراءةٌ صرفة لا تُنسَب لأي موظف (§٦)."""
    tenant_id = getattr(tenant, "pk", tenant)
    approved = list(
        CompanyHealthCheck.objects.filter(
            tenant_id=tenant_id,
            kind=CompanyHealthCheck.Kind.BASELINE,
            status=CompanyHealthCheck.Status.APPROVED,
        )
        .order_by("-approved_at")[:2]
    )
    if not approved:
        return {"baseline": None, "current": None, "changes": []}

    current = approved[0]
    baseline = approved[1] if len(approved) > 1 else None
    current_items = {row.code: row for row in current.items.all()}
    baseline_items = {row.code: row for row in baseline.items.all()} if baseline else {}

    changes = []
    for code, row in current_items.items():
        previous = baseline_items.get(code)
        previous_status = previous.status if previous else None
        if previous_status != row.status:
            changes.append({"code": code, "from_status": previous_status, "to_status": row.status})
    return {"baseline": baseline, "current": current, "changes": changes}


def _tenant_load_units_map(tenant_ids) -> dict[int, int]:
    """وحدات حِمل عدّة شركات باستعلامٍ واحد — الصيغةُ الجمعيّة لـ`_tenant_load_units` (§٦).

    شاشةُ الإسناد تقيس كلّ موظفٍ على كلّ شركات ارتباطاته النشطة، فحسابُ الوحدات
    شركةً شركةً يعني استعلاماً لكلّ ارتباطٍ لكلّ موظف. هنا استعلامٌ واحدٌ للجميع.
    """
    ids = {getattr(tenant_id, "pk", tenant_id) for tenant_id in tenant_ids}
    if not ids:
        return {}
    complexity_by_tenant: dict[int, str] = {}
    rows = (
        CompanyHealthCheck.objects.filter(
            tenant_id__in=ids,
            kind=CompanyHealthCheck.Kind.BASELINE,
            status=CompanyHealthCheck.Status.APPROVED,
        )
        .order_by("tenant_id", "-approved_at")
        .values_list("tenant_id", "complexity")
    )
    for tenant_id, complexity in rows:
        # الترتيبُ يضع أحدثَ معتمدٍ أولاً، فأوّلُ صفٍّ لكلّ شركة هو أساسُها الحالي.
        complexity_by_tenant.setdefault(tenant_id, complexity)
    return {
        tenant_id: CAPACITY_LOAD_UNITS.get(
            complexity_by_tenant.get(tenant_id) or "", DEFAULT_CAPACITY_LOAD_UNITS,
        )
        for tenant_id in ids
    }


def _tenant_load_units(tenant) -> int:
    """وحدات حِمل شركة من تعقيد أحدث فحصٍ تأسيسي معتمد لها — وسطٌ إن لم يوجد بعد (§٦)."""
    tenant_id = getattr(tenant, "pk", tenant)
    return _tenant_load_units_map([tenant_id])[tenant_id]


def _would_exceed_capacity(capacity_target, projected_load) -> bool:
    """هل يتجاوز الحِملُ المتوقَّع طاقةَ الموظف المستهدفة؟

    `capacity_target` صفراً يعني «لم تُضبط بعد» لا «طاقته صفر» — وهو **افتراضُ
    النموذج** ولا واجهةَ كتابةٍ تضبطه (`PlatformEmployeeViewSet` للقراءة فقط)،
    وهو معناه نفسُه في حجم العيّنة (`_axis_*`) وفي كشف الحمل الزائد بشريط التدخّل.
    بغير هذا يُرفض كلُّ إسنادٍ لكلّ موظفٍ حقيقيٍّ برمز `capacity_exceeded` ويُطلب
    سببُ تجاوزٍ في كلّ مرة — والاختبارات وحدها تنجو لأنها تضبط الطاقة صراحةً.
    """
    target = Decimal(capacity_target or 0)
    if target <= 0:
        return False
    return Decimal(projected_load) > target


def employee_capacity_snapshot(employee, *, load_units_by_tenant: dict[int, int] | None = None) -> dict:
    """حِمل موظف المنصة الحالي وباقي طاقته — مجموع وحدات حِمل شركات ارتباطاته النشطة.

    `load_units_by_tenant` خريطةٌ محسوبةٌ مسبقاً تمرّرها القوائم كي لا يتكرّر استعلامُ
    وحدات الحِمل لكلّ موظف.
    """
    employee_id = getattr(employee, "pk", employee)
    active_tenant_ids = list(
        Engagement.objects.filter(employee_id=employee_id, status=Engagement.Status.ACTIVE)
        .values_list("tenant_id", flat=True)
    )
    load_units = (
        load_units_by_tenant if load_units_by_tenant is not None else _tenant_load_units_map(active_tenant_ids)
    )
    load = sum(load_units.get(tenant_id, DEFAULT_CAPACITY_LOAD_UNITS) for tenant_id in active_tenant_ids)
    capacity_target = (
        PlatformEmployee.objects.filter(pk=employee_id).values_list("capacity_target", flat=True).first()
        or Decimal("0.00")
    )
    return {
        "load": load,
        "capacity_target": capacity_target,
        "remaining": Decimal(capacity_target) - Decimal(load),
        "active_engagements_count": len(active_tenant_ids),
    }


def list_assignment_candidates(*, tenant) -> list[dict]:
    """موظفو المنصة النشطون مع حِملهم الحالي وأثر إسناد هذه الشركة عليهم — لشاشة الإسناد.

    عددُ الاستعلامات ثابتٌ (موظفون، ارتباطاتهم، وحدات حِمل شركاتهم) مهما كثر الطرفان.
    """
    tenant_obj = tenant if isinstance(tenant, Tenant) else Tenant.objects.get(pk=tenant)
    employees = list(
        PlatformEmployee.objects.filter(status=PlatformEmployee.Status.ACTIVE).select_related("user")
    )
    engagement_rows = list(
        Engagement.objects.filter(
            employee_id__in=[employee.pk for employee in employees],
            status=Engagement.Status.ACTIVE,
        ).values_list("employee_id", "tenant_id")
    )
    load_units = _tenant_load_units_map({tenant_id for _, tenant_id in engagement_rows} | {tenant_obj.pk})
    tenant_load = load_units[tenant_obj.pk]

    tenants_by_employee: dict[int, list[int]] = {}
    for employee_id, tenant_id in engagement_rows:
        tenants_by_employee.setdefault(employee_id, []).append(tenant_id)

    candidates = []
    for employee in employees:
        served_tenant_ids = tenants_by_employee.get(employee.pk, [])
        load = sum(
            load_units.get(tenant_id, DEFAULT_CAPACITY_LOAD_UNITS) for tenant_id in served_tenant_ids
        )
        capacity_target = employee.capacity_target or Decimal("0.00")
        projected_load = load + tenant_load
        candidates.append({
            "employee": employee,
            "load": load,
            "capacity_target": capacity_target,
            "remaining": Decimal(capacity_target) - Decimal(load),
            "active_engagements_count": len(served_tenant_ids),
            "projected_load_if_assigned": projected_load,
            "would_exceed_capacity": _would_exceed_capacity(capacity_target, projected_load),
        })
    return candidates


@transaction.atomic
def transfer_engagement(
    *,
    engagement,
    to_employee,
    reason: str,
    actor=None,
    correlation_id: str = "",
    capacity_override_reason: str = "",
) -> Engagement:
    """ينقل شركة من ارتباطٍ قائم إلى موظفٍ آخر بمعاملة واحدة — يُغلق القديم عبر مسار
    الإلغاء الرسمي (قواعد العضوية نفسها) وينشئ جديداً بـ`predecessor`. لا يمسّ الاكتساب.

    ترتيب القفل: Subscription -> PlatformEmployee -> Engagement -> UserCompanyMembership
    (نفس ترتيب `assign_platform_employee`).
    """
    reason = str(reason or "").strip()
    if not reason:
        raise EngagementError("reason_required", "سبب النقل مطلوب.")

    eng_pk = getattr(engagement, "pk", engagement)
    pre_eng = Engagement.objects.filter(pk=eng_pk).values("tenant_id", "kind").first()
    if not pre_eng:
        raise EngagementError("not_found", "الارتباط غير موجود.")

    subscription = ServiceSubscription.objects.select_for_update().filter(tenant_id=pre_eng["tenant_id"]).first()
    if not is_service_subscription_eligible(subscription):
        raise EngagementError("subscription_not_active", "خدمة المتابعة والإدخال غير نشطة لهذه الشركة.")

    emp_pk = getattr(to_employee, "pk", to_employee)
    locked_employee = PlatformEmployee.objects.select_for_update().get(pk=emp_pk)
    if locked_employee.status != PlatformEmployee.Status.ACTIVE:
        raise EngagementError("employee_not_active", "موظف عمليات المنصة غير نشط.")

    locked_old = Engagement.objects.select_for_update().get(pk=eng_pk)
    if locked_old.status == Engagement.Status.REVOKED:
        raise EngagementConflict("already_revoked", "الارتباط ملغى نهائياً ولا يمكن نقله.")
    # المعلَّقُ لا يُنقل: النقلُ كان يُخرج ارتباطاً نشطاً من معلَّقٍ بصمت، فيعود
    # الموظفُ الجديد يخدم شركةً عُلّقت خدمتُها عمداً.
    if locked_old.status != Engagement.Status.ACTIVE:
        raise EngagementConflict("not_active", "الارتباط معلَّق؛ استأنفه أو ألغه بدل نقله.")
    if locked_old.employee_id == locked_employee.pk:
        raise EngagementError("same_employee", "الموظف المستهدف هو نفسه الحالي.")

    tenant_obj = Tenant.objects.get(pk=pre_eng["tenant_id"])
    capacity_override_reason = str(capacity_override_reason or "").strip()
    projected_load = Decimal(employee_capacity_snapshot(locked_employee)["load"]) + Decimal(_tenant_load_units(tenant_obj))
    if _would_exceed_capacity(locked_employee.capacity_target, projected_load) and not capacity_override_reason:
        raise EngagementConflict(
            "capacity_exceeded",
            "نقل هذه الشركة يتجاوز الطاقة المستهدفة للموظف الجديد؛ أضف سبب تجاوز للمتابعة.",
        )

    _execute_revoke(locked_old, revoked_by=actor, reason=reason, end_reason=f"نُقل: {reason}")

    existing_membership = (
        UserCompanyMembership.objects.select_for_update()
        .filter(user_id=locked_employee.user_id, tenant=tenant_obj)
        .first()
    )
    if existing_membership is None:
        membership = UserCompanyMembership.objects.create(user_id=locked_employee.user_id, tenant=tenant_obj, role="manager")
        created_membership, previous_role = True, ""
    else:
        membership = existing_membership
        created_membership = False
        previous_role = existing_membership.role
        if existing_membership.role != "manager":
            existing_membership.role = "manager"
            existing_membership.save(update_fields=["role"])

    # مهلةُ التهيئة لا تُستأنف بالنقل — النقلُ تغييرُ موظفٍ لا استثناءٌ جديدٌ من شرط
    # الأساس المعتمد؛ استئنافُها كان يجعل «لا إسناد بلا أساس» قابلاً للتجاوز بلا نهاية.
    onboarding_expires_at = (
        locked_old.onboarding_expires_at if pre_eng["kind"] == Engagement.Kind.ONBOARDING else None
    )
    new_engagement = Engagement.objects.create(
        employee=locked_employee,
        tenant=tenant_obj,
        status=Engagement.Status.ACTIVE,
        assigned_by=actor,
        kind=pre_eng["kind"],
        onboarding_expires_at=onboarding_expires_at,
        created_membership=created_membership,
        managed_membership=membership,
        previous_role=previous_role,
        predecessor_id=locked_old.pk,
        capacity_override_reason=capacity_override_reason,
    )
    _log_operation_event(
        tenant_obj,
        domain=PlatformOperationEvent.Domain.ENGAGEMENT,
        action=PlatformOperationEvent.Action.TRANSFERRED,
        subject_id=new_engagement.pk,
        actor=actor,
        correlation_id=correlation_id,
        reason=reason,
        details={
            "from_engagement_id": locked_old.pk,
            "from_employee_id": locked_old.employee_id,
            "to_employee_id": locked_employee.pk,
        },
    )
    return new_engagement


def get_customer_acquisition(tenant) -> CustomerAcquisition | None:
    tenant_id = getattr(tenant, "pk", tenant)
    return CustomerAcquisition.objects.select_related("acquired_by__user").filter(tenant_id=tenant_id).first()


@transaction.atomic
def set_customer_acquisition(
    *,
    tenant,
    acquired_by,
    acquired_at=None,
    note: str = "",
    actor=None,
    correlation_id: str = "",
) -> CustomerAcquisition:
    """يسجّل أو يعدّل من جلب الشركة كزبون — صفٌّ واحدٌ لكل شركة، مستقلٌّ عن من يخدمها الآن."""
    tenant_obj = Tenant.objects.select_for_update().get(pk=getattr(tenant, "pk", tenant))
    emp_pk = getattr(acquired_by, "pk", acquired_by)
    employee = PlatformEmployee.objects.filter(pk=emp_pk).first()
    if employee is None:
        raise AcquisitionError("employee_not_found", "موظف العمليات غير موجود.")

    acquired_at = acquired_at or timezone.localdate()
    note = str(note or "")[:500]
    existing = CustomerAcquisition.objects.filter(tenant_id=tenant_obj.pk).first()
    if existing is None:
        try:
            with transaction.atomic():
                record = CustomerAcquisition.objects.create(
                    tenant=tenant_obj,
                    acquired_by=employee,
                    acquired_at=acquired_at,
                    note=note,
                    created_by=actor if getattr(actor, "pk", None) else None,
                )
        except IntegrityError:
            raise AcquisitionConflict("acquisition_conflict", "يوجد سجلّ اكتساب لهذه الشركة بالفعل؛ أعد التحميل.")
        change_kind = "created"
    else:
        record = CustomerAcquisition.objects.select_for_update().get(pk=existing.pk)
        record.acquired_by = employee
        record.acquired_at = acquired_at
        record.note = note
        record.save(update_fields=["acquired_by", "acquired_at", "note", "updated_at"])
        change_kind = "updated"

    _log_operation_event(
        tenant_obj,
        domain=PlatformOperationEvent.Domain.ACQUISITION,
        action=PlatformOperationEvent.Action.ACQUISITION_SET,
        subject_id=record.pk,
        actor=actor,
        correlation_id=correlation_id,
        details={"acquired_by": employee.pk, "acquired_at": acquired_at.isoformat(), "change": change_kind},
    )
    return record


# ==============================================================================
# التذكرة 210-C: كتالوج وحدات الخدمة، ربط المستندات، ودفتر الاستخدام
# ==============================================================================


class ServiceUnitCatalogError(PlatformOpsError):
    """خطأ في كتالوج وحدات الخدمة."""


class ServiceUnitCatalogConflict(ServiceUnitCatalogError):
    def __init__(self, code: str, detail: str, status_code: int = 409):
        super().__init__(code, detail, status_code=status_code)


class WorkOrderDocumentLinkError(WorkOrderError):
    """خطأ في ربط مستند بأمر عمل."""


class UsageLedgerError(PlatformOpsError):
    """خطأ في توليد أو عكس حدث استخدام دفتر الوحدات."""


def _catalog_event_details(catalog: ServiceUnitCatalog) -> dict:
    return {
        "status": catalog.status,
        "effective_from": catalog.effective_from.isoformat() if catalog.effective_from else None,
        "entries": [
            {
                "document_type": row["document_type"],
                "base_units": str(row["base_units"]),
                "per_line_weight": str(row["per_line_weight"]),
                "complexity_low_add": str(row["complexity_low_add"]),
                "complexity_medium_add": str(row["complexity_medium_add"]),
                "complexity_high_add": str(row["complexity_high_add"]),
            }
            for row in catalog.entries.values(
                "document_type", "base_units", "per_line_weight",
                "complexity_low_add", "complexity_medium_add", "complexity_high_add",
            ).order_by("document_type")
        ],
    }


def _log_catalog_event(catalog, *, action, actor=None, correlation_id="", details=None):
    """حدثُ تدقيقٍ للكتالوج داخل معاملة الكتابة نفسها — لا مسار تعديل أو حذف له."""
    return ServiceUnitCatalogEvent.objects.create(
        catalog=catalog,
        action=action,
        actor=actor if getattr(actor, "pk", None) else None,
        correlation_id=str(correlation_id or "")[:64],
        details=details or {},
    )


def get_active_service_unit_catalog(at=None) -> ServiceUnitCatalog | None:
    """نسخةُ الكتالوج الساريةُ الآن — عبر `effective_state` لا `status` وحده."""
    moment = at or timezone.now()
    for candidate in ServiceUnitCatalog.objects.filter(status=ServiceUnitCatalog.Status.ACTIVE).order_by("-version"):
        if candidate.effective_state(moment) == "current":
            return candidate
    return None


def _require_active_service_unit_catalog() -> ServiceUnitCatalog:
    """**لا تُفعَّل خطةٌ بلا كتالوج وحداتٍ صالح** (القصة ١٨).

    البوّابةُ هنا لا عند الاعتماد: كتالوجٌ غائبٌ يُكتشَف لحظةَ اعتماد أوّل مُسلَّم
    يعني أنّ الخدمةَ فُعِّلت وأُسند موظّفٌ وأُنجز عملٌ كامل ثم تبيّن أنّ احتسابَه
    غيرُ معرَّف — وهو عينُ ما تمنعه القصة. فيُرفض التفعيل نفسُه.
    """
    catalog = get_active_service_unit_catalog()
    if catalog is None:
        raise SubscriptionManagementError(
            "service_unit_catalog_required",
            "انشر كتالوج وحدات خدمةٍ ساريًا قبل تفعيل الخدمة؛ لا يبدأ احتسابٌ غيرُ محدَّد.",
        )
    return catalog


def _observe_document_line_count(*, tenant_id: int, document_type: str, document_id: int) -> int | None:
    """يرصد عددَ بنود المستند من مصدره الرسميّ، ويتحقّق أنّه يخصّ الشركة نفسَها.

    يعيد `None` حين يكون النوعُ غيرَ قابلٍ للرصد من هنا — أي أنّ app صاحبَ المستند
    خارجَ القائمة البيضاء لحارس العزل (`accounting` و`logistics` و`import_file`)؛
    فالعددُ يبقى تصريحاً موسوماً `declared` بدل أن نمدّ يدَنا إلى جداول غيرنا أو
    نلتفّ على الحارس بـ`apps.get_model`. وما دام `sales` في القائمة، فلا عذرَ
    لتصديق رقمٍ مكتوبٍ عن فاتورةِ بيعٍ نستطيع عدَّها.

    ويرفع خطأً إن كان المستندُ غيرَ موجودٍ أو لشركةٍ أخرى: لا FK هنا فلا نزاهةَ
    مرجعيّةً تحرسه، ورقمُ مستندٍ من شركةٍ أخرى يُفوتِر هذه الشركةَ بعمل تلك.
    """
    if document_type != ServiceDocumentType.SALES_INVOICE:
        return None
    from sales.models import SalesInvoice

    invoice = SalesInvoice.objects.filter(pk=document_id).only("id", "tenant_id").first()
    if invoice is None:
        raise WorkOrderDocumentLinkError("document_not_found", "المستند غير موجود.")
    if invoice.tenant_id != tenant_id:
        raise WorkOrderDocumentLinkError(
            "document_tenant_mismatch", "المستند يخصّ شركةً أخرى؛ لا يُربط بأمر عملِ هذه الشركة.",
        )
    return invoice.lines.count()


def _ledger_chargeable_total(subscription: ServiceSubscription, *, exclude_event_id: int | None = None) -> Decimal:
    """صافي وحدات الدفتر المحتسَبة على العميل **لدورة الاشتراك الجارية** (استخدامٌ ناقص عكس).

    **الحصرُ بالدورة ليس تفصيلاً:** `consumed_quota` يُصفَّر كلَّ دورةٍ عند التدوير
    (`bill_subscription_for_period`)، فمجموعٌ لكلّ الزمن يجعل الكسورَ تتراكم عبر
    الدورات فتُبتلع أحداثٌ جديدة — مجموعٌ تاريخيٌّ 10.50 وحدثٌ بنصف وحدة يُنتج
    `تقريب(11.00) − تقريب(10.50) = 0` فلا يستهلك الحدثُ شيئاً أبداً. والحصرُ نفسُه
    يمنع أن يخصم عكسُ حدثٍ من دورةٍ **فُوترت سلفاً** من عدّاد الدورة الجارية
    (§٢٧٠: لا إعادة حسابٍ رجعيّة) — حدثُ العكس يحمل دورةَ أصله لا الدورةَ الجارية.
    """
    qs = ServiceUsageEvent.objects.filter(
        subscription_id=subscription.pk,
        chargeable_to_customer=True,
        period_start=subscription.period_start,
        period_end=subscription.period_end,
    )
    if exclude_event_id is not None:
        qs = qs.exclude(pk=exclude_event_id)
    total = Decimal("0.00")
    for row in qs.values("event_type").annotate(units_sum=Sum("units")):
        amount = row["units_sum"] or Decimal("0.00")
        if row["event_type"] == ServiceUsageEvent.EventType.USAGE:
            total += amount
        else:
            total -= amount
    return total


@transaction.atomic
def create_service_unit_catalog_draft(*, actor=None, correlation_id: str = "", cloned_from=None) -> ServiceUnitCatalog:
    """ينشئ نسخة مسودة جديدة من كتالوج وحدات الخدمة — بلا بنود بعد.

    لا `select_for_update` لحساب رقم النسخة، كنمط `create_subscription_policy_draft`:
    قفلُ مدى فارغ على MySQL يأخذ gap lock فتتشابك معاملتان تُدرجان معاً. القيدُ
    الفريد على `version` هو الحارس.
    """
    last_version = ServiceUnitCatalog.objects.aggregate(Max("version"))["version__max"] or 0
    try:
        with transaction.atomic():
            catalog = ServiceUnitCatalog.objects.create(
                version=last_version + 1,
                status=ServiceUnitCatalog.Status.DRAFT,
                created_by=actor if getattr(actor, "pk", None) else None,
            )
    except IntegrityError:
        raise ServiceUnitCatalogConflict("catalog_version_conflict", "تعذر إنشاء نسخة كتالوج جديدة؛ أعد المحاولة.")
    details = {"after": _catalog_event_details(catalog)}
    if cloned_from is not None:
        details["source_catalog_id"] = cloned_from.pk
    _log_catalog_event(
        catalog,
        action=(
            ServiceUnitCatalogEvent.Action.CLONED if cloned_from is not None
            else ServiceUnitCatalogEvent.Action.CREATED
        ),
        actor=actor,
        correlation_id=correlation_id,
        details=details,
    )
    return catalog


def clone_service_unit_catalog_to_draft(*, catalog, actor=None, correlation_id: str = "") -> ServiceUnitCatalog:
    """ينسخ نسخة نشطة أو منتهية (وبنودها) إلى مسودة جديدة قابلة للتعديل."""
    source = ServiceUnitCatalog.objects.prefetch_related("entries").get(pk=getattr(catalog, "pk", catalog))
    draft = create_service_unit_catalog_draft(actor=actor, correlation_id=correlation_id, cloned_from=source)
    for entry in source.entries.all():
        ServiceUnitCatalogEntry.objects.create(
            catalog=draft,
            document_type=entry.document_type,
            base_units=entry.base_units,
            per_line_weight=entry.per_line_weight,
            complexity_low_add=entry.complexity_low_add,
            complexity_medium_add=entry.complexity_medium_add,
            complexity_high_add=entry.complexity_high_add,
        )
    return draft


def _validate_catalog_entry_decimal(value, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError):
        raise ServiceUnitCatalogError(field_name, f"قيمة {field_name} غير صالحة.")
    if not result.is_finite() or result < Decimal("0.00"):
        raise ServiceUnitCatalogError(field_name, f"قيمة {field_name} يجب أن تكون صفراً أو أكبر.")
    return result


@transaction.atomic
def update_service_unit_catalog_entries(
    *, catalog, entries: list[dict], actor=None, correlation_id: str = "",
) -> ServiceUnitCatalog:
    """يستبدل بنود مسودة الكتالوج دفعة واحدة — النسخة النشطة أو المنتهية غير قابلة للتعديل.

    `entries`: قائمة قواميس {document_type, base_units, per_line_weight,
    complexity_low_add, complexity_medium_add, complexity_high_add}. أساسُ الوحدة
    ووزنُ السطر وإضافات التعقيد من هذه الواجهة المخصّصة لا مدفونةً في الكود (القصة ١٧).
    """
    locked = ServiceUnitCatalog.objects.select_for_update().get(pk=getattr(catalog, "pk", catalog))
    if locked.status != ServiceUnitCatalog.Status.DRAFT:
        raise ServiceUnitCatalogConflict("catalog_immutable", "لا يمكن تعديل كتالوج مفعّل أو منتهٍ.")

    before = _catalog_event_details(locked)
    seen_types = set()
    validated = []
    for row in entries or []:
        doc_type = row.get("document_type")
        if doc_type not in ServiceDocumentType.values:
            raise ServiceUnitCatalogError("invalid_document_type", f"نوع مستند غير صالح: {doc_type}")
        if doc_type in seen_types:
            raise ServiceUnitCatalogError("duplicate_document_type", f"نوع المستند مكرر في الكتالوج: {doc_type}")
        seen_types.add(doc_type)
        validated.append({
            "document_type": doc_type,
            "base_units": _validate_catalog_entry_decimal(row.get("base_units"), "base_units").quantize(Decimal("0.01")),
            "per_line_weight": _validate_catalog_entry_decimal(
                row.get("per_line_weight"), "per_line_weight"
            ).quantize(Decimal("0.0001")),
            "complexity_low_add": _validate_catalog_entry_decimal(
                row.get("complexity_low_add"), "complexity_low_add"
            ).quantize(Decimal("0.01")),
            "complexity_medium_add": _validate_catalog_entry_decimal(
                row.get("complexity_medium_add"), "complexity_medium_add"
            ).quantize(Decimal("0.01")),
            "complexity_high_add": _validate_catalog_entry_decimal(
                row.get("complexity_high_add"), "complexity_high_add"
            ).quantize(Decimal("0.01")),
        })

    locked.entries.all().delete()
    for row in validated:
        ServiceUnitCatalogEntry.objects.create(catalog=locked, **row)

    _log_catalog_event(
        locked, action=ServiceUnitCatalogEvent.Action.UPDATED, actor=actor, correlation_id=correlation_id,
        details={"before": before, "after": _catalog_event_details(locked)},
    )
    return locked


@transaction.atomic
def activate_service_unit_catalog(
    *, catalog, actor=None, activation_reason: str = "", correlation_id: str = "", effective_from=None,
) -> ServiceUnitCatalog:
    """يفعّل مسودة كتالوج بسبب إلزامي وبنودٍ غير فارغة (القصة ١٨).

    يمنع تفعيل كتالوج بلا بنود صراحةً — لا يبدأ احتساب غير محدد. على نمط
    `activate_subscription_policy`: منعُ التداخل تحت قفل صريح على كل الصفوف
    لا بقيد شرطي تتجاهله MySQL، وتغيير النسخة يسري على الفترات القادمة فقط.
    """
    activation_reason = str(activation_reason or "").strip()
    if not activation_reason:
        raise ServiceUnitCatalogError("activation_reason_required", "سبب التفعيل مطلوب.")

    locked_catalogs = list(ServiceUnitCatalog.objects.select_for_update().order_by("pk"))
    locked = next((row for row in locked_catalogs if row.pk == getattr(catalog, "pk", catalog)), None)
    if locked is None:
        raise ServiceUnitCatalogError("catalog_not_found", "كتالوج وحدات الخدمة غير موجود.")
    if locked.status != ServiceUnitCatalog.Status.DRAFT:
        raise ServiceUnitCatalogConflict("catalog_not_draft", "لا يمكن تفعيل هذا الكتالوج مرة أخرى.")
    if not locked.entries.exists():
        raise ServiceUnitCatalogError("catalog_empty", "لا يمكن تفعيل كتالوج بلا بنود.")

    now = timezone.now()
    starts_at = effective_from or now
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    if starts_at < now - datetime.timedelta(minutes=1):
        raise ServiceUnitCatalogError("effective_from_in_past", "تاريخ السريان لا يكون في الماضي.")
    starts_at = max(starts_at, now)

    active_rows = [
        row for row in locked_catalogs
        if row.pk != locked.pk and row.status == ServiceUnitCatalog.Status.ACTIVE
    ]
    later = [row for row in active_rows if row.effective_from and row.effective_from >= starts_at]
    if later:
        raise ServiceUnitCatalogConflict(
            "catalog_overlap",
            f"النسخة v{later[0].version} تسري من تاريخ لاحق أو مساوٍ؛ اختر تاريخ سريان بعده.",
        )
    superseded = []
    for previous in active_rows:
        if previous.effective_to is None or previous.effective_to > starts_at:
            previous.effective_to = starts_at
            previous.save(update_fields=["effective_to", "updated_at"])
            superseded.append(previous.pk)

    locked.status = ServiceUnitCatalog.Status.ACTIVE
    locked.effective_from = starts_at
    locked.effective_to = None
    locked.activated_at = now
    locked.activated_by = actor if getattr(actor, "pk", None) else None
    locked.activation_reason = activation_reason
    locked.save(update_fields=[
        "status", "effective_from", "effective_to", "activated_at", "activated_by", "activation_reason", "updated_at",
    ])
    _log_catalog_event(
        locked, action=ServiceUnitCatalogEvent.Action.ACTIVATED, actor=actor, correlation_id=correlation_id,
        details={
            "reason": activation_reason,
            "effective_from": starts_at.isoformat(),
            "superseded_catalog_ids": superseded,
        },
    )
    for row in locked_catalogs:
        if (
            row.pk != locked.pk
            and row.status == ServiceUnitCatalog.Status.ACTIVE
            and row.effective_to is not None
            and row.effective_to <= now
        ):
            row.status = ServiceUnitCatalog.Status.RETIRED
            row.save(update_fields=["status", "updated_at"])
            _log_catalog_event(
                row, action=ServiceUnitCatalogEvent.Action.RETIRED, actor=actor, correlation_id=correlation_id,
                details={"reason": activation_reason, "effective_to": row.effective_to.isoformat()},
            )
    return locked


@transaction.atomic
def link_work_order_document(
    *,
    work_order: WorkOrder,
    document_type: str,
    document_id,
    line_count: int = 1,
    complexity: str = "",
    linked_by=None,
    recount_reason: str = "",
) -> WorkOrderDocumentLink:
    """ربطُ مستندٍ مُدخَل بأمر عمل تمهيداً لتسليمه (القصة ٣٦).

    **لا يغيّر قواعد المستند نفسه ولا يلتفّ على مساره المحاسبي أو المخزوني
    الرسمي** — مرجعٌ للاحتساب فقط، بلا FK لتنوّع نماذج المستندات الممكنة.
    """
    if document_type not in ServiceDocumentType.values:
        raise WorkOrderDocumentLinkError("invalid_document_type", f"نوع مستند غير صالح: {document_type}")
    try:
        doc_id = int(document_id)
    except (TypeError, ValueError):
        raise WorkOrderDocumentLinkError("invalid_document_id", "معرّف المستند غير صالح.")
    if doc_id <= 0:
        raise WorkOrderDocumentLinkError("invalid_document_id", "معرّف المستند غير صالح.")
    try:
        count = int(line_count)
    except (TypeError, ValueError):
        raise WorkOrderDocumentLinkError("invalid_line_count", "عدد البنود غير صالح.")
    if count <= 0:
        raise WorkOrderDocumentLinkError("invalid_line_count", "عدد البنود يجب أن يكون أكبر من صفر.")
    if complexity and complexity not in ServiceUnitCatalogEntry.Complexity.values:
        raise WorkOrderDocumentLinkError("invalid_complexity", f"قيمة تعقيد غير صالحة: {complexity}")

    wo = WorkOrder.objects.select_related("tenant").get(pk=getattr(work_order, "pk", work_order))

    # **لقطةٌ تُرصد لا تُصدَّق**: العددُ المُصرَّح به يحدّد إنجازَ الموظّف نفسِه وفاتورةَ
    # العميل معاً، فما أمكن رصدُه من المستند يغلب ما كُتب في الطلب.
    observed = _observe_document_line_count(
        tenant_id=wo.tenant_id, document_type=document_type, document_id=doc_id,
    )
    if observed is None:
        line_count_source = LineCountSource.DECLARED
    else:
        line_count_source = LineCountSource.OBSERVED
        count = observed

    # **إعادةُ الاحتساب طلبٌ جديدٌ يعتمده المدير** (المواصفة §٤): منعُ الاحتساب
    # المضاعف كان يقوم على اصطلاحِ «أعِد استخدام الرابط» وحدَه، فرابطٌ ثانٍ على
    # المستند نفسِه يُفوتِره مرّةً أخرى ويمنح الموظّفَ إنجازاً ثانياً بلا أيّ حارس.
    recount_reason = str(recount_reason or "").strip()
    # **المصدرُ لا الطلب**: §١٦٧ تقول «المصدر الواحد لا يُحتسب مرتين حتى مع إعادة
    # الطلب» — فالحصرُ بأمر العمل كان يترك البابَ مفتوحاً على مصراعيه: نفسُ الفاتورة
    # تُربط بأمر عملٍ **ثانٍ** فتُفوتَر مرّةً أخرى ويُمنح الموظّفُ إنجازاً ثانياً بلا
    # سببٍ ولا اعتمادِ مدير. والعزلُ بالشركة لا بالمنصّة: فاتورةُ شركةٍ لا تُقاس بأرقام غيرها.
    # وحدثٌ **عُكس** لم يبقَ محتسَباً، فالمستندُ يُربط من جديدٍ بلا سببٍ مكتوب.
    already_charged = ServiceUsageEvent.objects.filter(
        tenant_id=wo.tenant_id,
        source_type=document_type,
        source_id=doc_id,
        event_type=ServiceUsageEvent.EventType.USAGE,
        reversals__isnull=True,
    ).exists()
    if already_charged and not recount_reason:
        raise WorkOrderDocumentLinkError(
            "document_already_charged",
            "هذا المستند احتُسب سلفاً لأمر العمل؛ إعادةُ احتسابه طلبٌ جديدٌ يعتمده مديرُ العمليات بسببٍ مكتوب.",
            status_code=409,
        )

    link = WorkOrderDocumentLink.objects.create(
        tenant=wo.tenant,
        work_order=wo,
        document_type=document_type,
        document_id=doc_id,
        line_count=count,
        line_count_source=line_count_source,
        recount_reason=recount_reason[:500],
        complexity=complexity,
        linked_by=linked_by if getattr(linked_by, "pk", None) else None,
    )

    if linked_by:
        emp = getattr(linked_by, "platform_employee", None)
        if not emp:
            emp = PlatformEmployee.objects.filter(user=linked_by).first()
        if emp:
            log_platform_activity(
                employee=emp,
                tenant=wo.tenant,
                action=PlatformActivityLog.Action.DOCUMENT_LINKED,
                entity_type="work_order_document_link",
                entity_id=link.pk,
                description=f"ربط مستند ({link.get_document_type_display()} #{doc_id}) بأمر العمل '{wo.title}'",
                details={"work_order_id": wo.pk, "document_type": document_type, "document_id": doc_id},
            )

    return link


def _classify_usage_flags(work_order: WorkOrder) -> tuple[bool, bool]:
    """علما الاحتساب (القصة ١٦): هل يستهلك حصة العميل؟ هل يمنح إنجاز الموظف؟

    مستندٌ وصل عبر قناةٍ (source=channel، أي أنشأه العميل بنفسه) يستهلك حصةَ
    العميل دوماً — الاستهلاكُ عن معالجة عمله لا عن هويّة كاتبه — لكنه **لا يمنح
    الموظفَ إنجازاً** إلا إذا كان أمر العمل مراجعةً (kind=review) بوزنٍ مستقل.
    """
    customer_originated = work_order.source == WorkOrder.Source.CHANNEL
    chargeable_to_customer = True
    creditable_to_employee = (not customer_originated) or work_order.kind == WorkOrder.Kind.REVIEW
    return chargeable_to_customer, creditable_to_employee


def _apply_usage_event_to_quota(subscription: ServiceSubscription, *, event: ServiceUsageEvent):
    """يحدّث `consumed_quota` من **مجموع الدفتر** لا بتقريب كلّ حدثٍ على حدة.

    تقريبُ كلّ حدثٍ وحدَه إلى عددٍ صحيح كان يبتلع الكسورَ بلا أثر: كتالوجٌ وزنُه
    `0.05` للسطر على فاتورةِ ثلاثةِ بنودٍ يُنتج `0.15` وحدة ⇒ تُقرَّب إلى صفر،
    فيُنجَز العملُ ولا يُستهلَك شيءٌ من الحصّة مهما تكرّر. فيُحسب الفرقُ بين تقريب
    المجموع قبل الحدث وبعده: تتراكم الكسورُ وتظهر عند عبورها الوحدةَ الكاملة.

    والعكسُ يُطرح تلقائياً لأنّه حدثُ `reversal` داخل المجموع نفسِه — لا حسابَ
    منفصلاً له فلا يختلّ التماثل. والقفلُ محرَزٌ سلفاً في المعاملة نفسِها.
    """
    if not event.chargeable_to_customer:
        return
    locked_sub = ServiceSubscription.objects.select_for_update().get(pk=subscription.pk)
    before = _ledger_chargeable_total(locked_sub, exclude_event_id=event.pk)
    after = _ledger_chargeable_total(locked_sub)
    delta = int(after.to_integral_value(rounding=ROUND_HALF_UP)) - int(
        before.to_integral_value(rounding=ROUND_HALF_UP)
    )
    if delta == 0:
        return
    locked_sub.consumed_quota = max(0, locked_sub.consumed_quota + delta)
    locked_sub.save(update_fields=["consumed_quota", "updated_at"])


@transaction.atomic
def generate_usage_events_for_deliverable(
    *, deliverable: WorkOrderDeliverable, reviewed_by, correlation_id: str = "",
) -> list[ServiceUsageEvent]:
    """يولّد أحداث دفتر الاستخدام من روابط مستندات مُسلَّمٍ **مُعتمَد** (القصص ١٦-١٩، ٥٦، ٥٨).

    لا وحدات قبل اعتماد السوبر أدمن: هذه الدالّة تُستدعى فقط بعد اعتماد المُسلَّم
    (انظر `approve_work_order_deliverable_with_usage`). مفتاحُ idempotency مبنيٌّ
    على معرّف رابط المستند نفسِه لا على المُسلَّم أو الطلب: رابطٌ واحدٌ ينتج حدثاً
    واحداً مهما تكرّرت المراجعة أو انقطعت الشبكة — وهو ما يمنع الاحتساب المضاعف
    عند إعادة العمل بسبب خطأ الموظف (الرابطُ نفسُه يُعاد استخدامه لا يُعاد إنشاؤه).

    ترتيب القفل: ServiceSubscription — لا تُقفَل روابطُ المستندات ولا الكتالوج هنا.
    """
    wo = deliverable.work_order
    subscription = ServiceSubscription.objects.select_for_update().filter(tenant_id=wo.tenant_id).first()
    if subscription is None or not is_service_subscription_eligible(subscription):
        raise UsageLedgerError(
            "subscription_not_active", "خدمة المتابعة والإدخال غير نشطة لهذه الشركة.", status_code=403,
        )

    links = list(deliverable.document_links.all())
    if not links:
        return []

    catalog = get_active_service_unit_catalog()
    if catalog is None:
        raise UsageLedgerError(
            "service_unit_catalog_required",
            "لا يوجد كتالوج وحدات خدمة نشط؛ لا يبدأ احتساب الوحدات بلا كتالوج صالح.",
        )
    entries_by_type = {entry.document_type: entry for entry in catalog.entries.all()}

    chargeable_to_customer, creditable_to_employee = _classify_usage_flags(wo)
    now = timezone.now()
    created_events: list[ServiceUsageEvent] = []

    for link in links:
        entry = entries_by_type.get(link.document_type)
        if entry is None:
            raise UsageLedgerError(
                "catalog_entry_missing_for_document_type",
                f"لا بند في الكتالوج النشط لنوع المستند: {link.document_type}",
            )
        idempotency_key = f"platform_ops:usage:doclink:{link.pk}"
        existing = ServiceUsageEvent.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            created_events.append(existing)
            continue

        units = entry.units_for(link.line_count, link.complexity)
        try:
            with transaction.atomic():
                event = ServiceUsageEvent.objects.create(
                    tenant=wo.tenant,
                    subscription=subscription,
                    work_order=wo,
                    deliverable=deliverable,
                    document_link=link,
                    event_type=ServiceUsageEvent.EventType.USAGE,
                    source_type=link.document_type,
                    source_id=link.document_id,
                    line_count_snapshot=link.line_count,
                    # مصدرُ العدد يُثبَّت على الحدث كما يُثبَّت العددُ نفسُه: مَن يراجع
                    # اعتراضاً على الوحدات لاحقاً يحتاج أن يعرف هل رُصد أم صُرِّح به.
                    line_count_source=link.line_count_source,
                    catalog_version=catalog.version,
                    units=units,
                    chargeable_to_customer=chargeable_to_customer,
                    creditable_to_employee=creditable_to_employee,
                    employee=wo.assignee,
                    approved_by=reviewed_by if getattr(reviewed_by, "pk", None) else None,
                    approved_at=now,
                    period_start=subscription.period_start,
                    period_end=subscription.period_end,
                    idempotency_key=idempotency_key,
                    correlation_id=str(correlation_id or "")[:64],
                )
        except IntegrityError:
            # تسابقٌ نادر على نفس مفتاح idempotency: الفائزُ الآخر أنشأ الصفّ، فنقرؤه بدل تكراره.
            created_events.append(ServiceUsageEvent.objects.get(idempotency_key=idempotency_key))
            continue

        _apply_usage_event_to_quota(subscription, event=event)
        created_events.append(event)

    return created_events


@transaction.atomic
def approve_work_order_deliverable_with_usage(
    *, deliverable: WorkOrderDeliverable, reviewed_by, correlation_id: str = "",
) -> tuple[WorkOrderDeliverable, list[ServiceUsageEvent]]:
    """يعتمد مُسلَّماً ويولّد أحداث دفتر استخدامه في معاملة ذرّية واحدة.

    ترتيب القفل: ServiceSubscription -> WorkOrderDeliverable. الاشتراكُ يُقفَل
    هنا **أولاً** كي لا يخالف تركيبُ `review_work_order_deliverable` (يقفل
    WorkOrderDeliverable وحده) مع `generate_usage_events_for_deliverable` (يقفل
    ServiceSubscription وحده) الترتيبَ المعلَن — كلُّ دالّةٍ على حدةٍ تقفل نموذجاً
    واحداً فسلامتُها الذاتيةُ لا تكفي عند التركيب.
    """
    deliv_pk = getattr(deliverable, "pk", deliverable)
    preliminary = WorkOrderDeliverable.objects.select_related("work_order").get(pk=deliv_pk)
    ServiceSubscription.objects.select_for_update().filter(tenant_id=preliminary.work_order.tenant_id).first()

    updated = review_work_order_deliverable(
        deliverable=preliminary,
        review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
        reviewed_by=reviewed_by,
    )
    events = generate_usage_events_for_deliverable(
        deliverable=updated, reviewed_by=reviewed_by, correlation_id=correlation_id,
    )
    return updated, events


@transaction.atomic
def reverse_usage_event(
    *, usage_event: ServiceUsageEvent, reason: str, actor=None, correlation_id: str = "",
) -> ServiceUsageEvent:
    """يعكس حدث استخدامٍ سابقاً — لا حذف ولا أرقام سالبة مجهولة (القصص ١٩، ٥٨).

    ترتيب القفل: ServiceSubscription -> ServiceUsageEvent.
    """
    reason = str(reason or "").strip()
    if not reason:
        raise UsageLedgerError("reversal_reason_required", "سبب العكس مطلوب.")

    ue_pk = getattr(usage_event, "pk", usage_event)
    preliminary = ServiceUsageEvent.objects.get(pk=ue_pk)
    subscription = ServiceSubscription.objects.select_for_update().get(pk=preliminary.subscription_id)
    locked = ServiceUsageEvent.objects.select_for_update().get(pk=ue_pk)

    if locked.event_type != ServiceUsageEvent.EventType.USAGE:
        raise UsageLedgerError("not_reversible", "لا يمكن عكس حدثٍ ليس من نوع استخدام.")
    if ServiceUsageEvent.objects.filter(reversed_event_id=locked.pk).exists():
        raise UsageLedgerError("already_reversed", "هذا الحدث معكوسٌ بالفعل.")

    idempotency_key = f"platform_ops:usage:reversal:{locked.pk}"
    reversal = ServiceUsageEvent.objects.create(
        tenant=locked.tenant,
        subscription=subscription,
        work_order_id=locked.work_order_id,
        deliverable_id=locked.deliverable_id,
        document_link_id=locked.document_link_id,
        event_type=ServiceUsageEvent.EventType.REVERSAL,
        source_type=locked.source_type,
        source_id=locked.source_id,
        line_count_snapshot=locked.line_count_snapshot,
        # مصدرُ العدد ينتقل مع العكس: دفترٌ يعكس حدثاً مرصوداً ويسجّله «مُصرَّحاً به»
        # يكذب على من يراجع اعتراضاً على الوحدات.
        line_count_source=locked.line_count_source,
        catalog_version=locked.catalog_version,
        units=locked.units,
        chargeable_to_customer=locked.chargeable_to_customer,
        creditable_to_employee=locked.creditable_to_employee,
        employee=locked.employee,
        approved_by=actor if getattr(actor, "pk", None) else None,
        approved_at=timezone.now(),
        period_start=locked.period_start,
        period_end=locked.period_end,
        idempotency_key=idempotency_key,
        reversed_event=locked,
        reason=reason[:500],
        correlation_id=str(correlation_id or "")[:64],
    )
    _apply_usage_event_to_quota(subscription, event=reversal)
    return reversal


@transaction.atomic
def change_work_order_priority(*, work_order: WorkOrder, priority: str, changed_by=None) -> WorkOrder:
    """تعديل أولوية أمر عمل — لترتيب طابور الموظف (القصة ٣٤)."""
    if priority not in WorkOrder.Priority.values:
        raise WorkOrderError("invalid_priority", f"أولوية أمر العمل غير صالحة: {priority}")
    locked = WorkOrder.objects.select_for_update().get(pk=getattr(work_order, "pk", work_order))
    previous_priority = locked.priority
    locked.priority = priority
    locked.save(update_fields=["priority", "updated_at"])

    if changed_by:
        emp = getattr(changed_by, "platform_employee", None)
        if not emp:
            emp = PlatformEmployee.objects.filter(user=changed_by).first()
        if emp:
            log_platform_activity(
                employee=emp,
                tenant=locked.tenant,
                action=PlatformActivityLog.Action.WORK_ORDER_PRIORITY_CHANGED,
                entity_type="work_order",
                entity_id=locked.pk,
                description=f"تغيير أولوية أمر العمل '{locked.title}' إلى {locked.get_priority_display()}",
                details={"from_priority": previous_priority, "to_priority": priority},
            )

    return locked


#: ترتيبُ الأولويّة للطابور الموحَّد — الأعلى قيمةً أولاً، ثم الأجل الأقرب.
WORK_ORDER_PRIORITY_RANK: dict[str, int] = {
    WorkOrder.Priority.URGENT: 3,
    WorkOrder.Priority.HIGH: 2,
    WorkOrder.Priority.NORMAL: 1,
    WorkOrder.Priority.LOW: 0,
}


# ==============================================================================
# ربحيّةُ العميل ومطابقةُ الخطة — Customer Profitability / Plan Fit (§٩)
# ==============================================================================

PROFITABILITY_PROFITABLE = "profitable"
PROFITABILITY_WATCH = "watch"
PROFITABILITY_REPRICE = "reprice_or_upgrade"
PROFITABILITY_LOSING = "losing"

PROFITABILITY_LABELS = {
    PROFITABILITY_PROFITABLE: "مربح",
    PROFITABILITY_WATCH: "يحتاج مراقبة",
    PROFITABILITY_REPRICE: "يحتاج إعادة تسعير أو ترقية",
    PROFITABILITY_LOSING: "خاسر",
}

#: عتباتُ الهامش كنسبةٍ من الإيراد — قواعدُ deterministic قابلةٌ للضبط كما تطلب §٩.
PROFITABILITY_MARGIN_HEALTHY = Decimal("0.35")
PROFITABILITY_MARGIN_WATCH = Decimal("0.15")

#: اقتراحاتُ مطابقة الخطة الخمسةُ بنصّ §٩ — رموزٌ ثابتةٌ تقرؤها الواجهة.
PLAN_FIT_UPGRADE = "upgrade_plan"
PLAN_FIT_EXTRA_UNITS = "buy_extra_units"
PLAN_FIT_ADJUST_SLA = "adjust_sla"
PLAN_FIT_REQUEST_DATA = "request_customer_data"
PLAN_FIT_HEALTH_PLAN = "health_remediation_plan"

PLAN_FIT_LABELS = {
    PLAN_FIT_UPGRADE: "ترقية الخطة",
    PLAN_FIT_EXTRA_UNITS: "شراء وحدات إضافية",
    PLAN_FIT_ADJUST_SLA: "تعديل الـSLA",
    PLAN_FIT_REQUEST_DATA: "طلب بيانات من العميل",
    PLAN_FIT_HEALTH_PLAN: "خطة علاج للصحة",
}

#: «استهلاكٌ مرتفعٌ **متكرّر**» (§٩) — شهرٌ واحدٌ حدثٌ، وشهران نمط.
PLAN_FIT_REPEAT_MONTHS = 2


def classify_profitability(*, revenue: Decimal, total_cost: Decimal) -> str:
    """تصنيفُ الربحيّة بقاعدةٍ واحدةٍ لا باجتهادٍ في كلّ موضع.

    الخسارةُ أوّلاً مهما كان الإيراد؛ ثمّ الهامشُ **نسبةً لا مبلغاً** — فشركةٌ تدفع
    ٣٠٠ وتكلّف ٢٥٠ ليست كأخرى تدفع ٣٠٠٠ وتكلّف ٢٩٥٠ وإن تساوى الفرقُ عددياً.
    وإيرادٌ صفريٌّ بتكلفةٍ موجبةٍ خاسرٌ لا «مراقب»: القسمةُ على صفرٍ لا تُموِّه حقيقة.
    """
    margin = revenue - total_cost
    if margin < 0:
        return PROFITABILITY_LOSING
    if revenue <= 0:
        return PROFITABILITY_PROFITABLE if total_cost <= 0 else PROFITABILITY_LOSING
    ratio = margin / revenue
    if ratio >= PROFITABILITY_MARGIN_HEALTHY:
        return PROFITABILITY_PROFITABLE
    if ratio >= PROFITABILITY_MARGIN_WATCH:
        return PROFITABILITY_WATCH
    return PROFITABILITY_REPRICE


def _monthly_base_salary_for(employee_id: int, at: datetime.datetime | None = None) -> Decimal:
    """الراتبُ الأساسيُّ الشهريُّ من سياسة التعويض السارية — الخاصّةُ بالموظّف أوّلاً.

    ولا قاعدةَ اختيارٍ ثانيةً هنا: `get_active_employee_compensation_policy` هي
    مَن يُرجّح الخاصّةَ على العامّة ويحترم نافذةَ السريان، و`get_default_...` هي
    مَن يقرأ الافتراضيّاتِ من تعريف الحقول. كلاهما من 210-D، ونسخُ منطقِهما هنا
    كان سيُنشئ مصدرَ حقيقةٍ ثالثاً للراتب.
    """
    policy = get_active_employee_compensation_policy(employee_id, at=at)
    if policy is not None:
        return Decimal(str(policy.base_salary))
    return Decimal(str(get_default_compensation_policy_dict()["base_salary"]))


def _chargeable_units_in_month(tenant_ids, year: int, month: int) -> dict:
    """وحداتُ العميل المحسوبةُ عليه في شهرٍ محلّيّ — بلا `__year`/`__month`.

    `approved_at` عمودُ وقتٍ لا تاريخ، ومقارنتُه بسنةٍ أو شهرٍ تمرّ في MySQL عبر
    `CONVERT_TZ`، وجداولُ المناطق الزمنيّة فارغةٌ هنا فتعود **صفرَ صفوف** بصمت.
    فالمدى المحلّيُّ الصريح عبر `core.date_ranges` هو الطريقُ الوحيد.
    """
    _, last_day = calendar.monthrange(year, month)
    qs = ServiceUsageEvent.objects.filter(tenant_id__in=tenant_ids, chargeable_to_customer=True)
    qs = filter_local_date_range(
        qs, "approved_at",
        date_from=datetime.date(year, month, 1),
        date_to=datetime.date(year, month, last_day),
    )
    totals: dict = {}
    for tenant_id, event_type, units in qs.values_list("tenant_id", "event_type", "units"):
        amount = Decimal(str(units or 0))
        sign = 1 if event_type == ServiceUsageEvent.EventType.USAGE else -1
        totals[tenant_id] = totals.get(tenant_id, Decimal("0")) + sign * amount
    return totals


def build_plan_fit_suggestions(*, subscription, consumed_units, previous_consumed_units, health) -> list[dict]:
    """اقتراحاتُ مطابقة الخطة — قواعدُ deterministic لا تنفّذ نفسَها (§٩).

    خمسُ قواعدَ بنصّ المواصفة، ولكلٍّ دليلُها في الصفّ نفسِه: «كل رقم قابل للفتح
    إلى مصادره». والترقيةُ تنفصل عن شراء الوحدات بالتكرار لا بالمقدار — تجاوزٌ
    في شهرٍ يُشترى، وتجاوزٌ في شهرين يُرقّى.

    **ولا فعلَ هنا ولا سعرَ يتغيّر**: «الاقتراح لا ينفذ نفسه ولا يغير سعراً أو
    اشتراكاً دون تأكيد السوبر أدمن» — فهذه الدالّةُ قراءةٌ محضة، ونقطةُ الـAPI
    التي تحملها `GET` وحدَها.
    """
    suggestions: list[dict] = []
    included = Decimal(str(subscription.included_quota or 0))

    if included > 0 and consumed_units >= included and previous_consumed_units >= included:
        suggestions.append({
            "code": PLAN_FIT_UPGRADE,
            "label": PLAN_FIT_LABELS[PLAN_FIT_UPGRADE],
            "reason": f"استهلاكٌ بلغ الحصّة في {PLAN_FIT_REPEAT_MONTHS} شهرين متتاليين.",
            "evidence": {
                "included_quota": float(included),
                "consumed_units": float(consumed_units),
                "previous_consumed_units": float(previous_consumed_units),
            },
        })
    elif included > 0 and consumed_units > included:
        suggestions.append({
            "code": PLAN_FIT_EXTRA_UNITS,
            "label": PLAN_FIT_LABELS[PLAN_FIT_EXTRA_UNITS],
            "reason": "تجاوزٌ في هذا الشهر وحدَه — وحداتٌ إضافيّةٌ أرخصُ من ترقيةٍ مبكّرة.",
            "evidence": {
                "included_quota": float(included),
                "consumed_units": float(consumed_units),
                "overage_units": float(consumed_units - included),
            },
        })

    service_rows = {row["reason_key"]: row for row in (health or {}).get("service_health", {}).get("breakdown", [])}
    customer_rows = {row["reason_key"]: row for row in (health or {}).get("customer_cooperation", {}).get("breakdown", [])}

    sla_row = service_rows.get("sla_breaches")
    if sla_row and sla_row.get("count"):
        suggestions.append({
            "code": PLAN_FIT_ADJUST_SLA,
            "label": PLAN_FIT_LABELS[PLAN_FIT_ADJUST_SLA],
            "reason": "أعمالٌ تجاوزت الأجل المتّفَق عليه — الأجلُ نفسُه قد يكون غيرَ واقعيّ.",
            "evidence": {"sla_breaches": sla_row.get("count")},
        })

    waiting = sum(int(customer_rows.get(key, {}).get("count") or 0) for key in ("waiting_customer", "long_waiting", "pending_comments"))
    if waiting:
        suggestions.append({
            "code": PLAN_FIT_REQUEST_DATA,
            "label": PLAN_FIT_LABELS[PLAN_FIT_REQUEST_DATA],
            "reason": "أعمالٌ متوقّفةٌ بانتظار العميل — البياناتُ الناقصةُ هي العُنق.",
            "evidence": {key: int(customer_rows.get(key, {}).get("count") or 0) for key in ("waiting_customer", "long_waiting", "pending_comments")},
        })

    service_score = (health or {}).get("service_health", {}).get("score")
    if service_score is not None and service_score < 70:
        suggestions.append({
            "code": PLAN_FIT_HEALTH_PLAN,
            "label": PLAN_FIT_LABELS[PLAN_FIT_HEALTH_PLAN],
            "reason": "صحّةُ الخدمة دون الحدّ المقبول — خطّةُ علاجٍ قبل أيّ قرارِ تسعير.",
            "evidence": {"service_health_score": service_score},
        })
    return suggestions


def compute_customer_profitability(
    *, period_year: int, period_month: int, allocated_expenses_per_tenant=None, with_suggestions: bool = True,
) -> list[dict]:
    """ربحيّةُ كلّ شركةِ خدمةٍ لشهرٍ واحد (§٩) — مؤشّرٌ تشغيليٌّ **منفصلٌ** عن صحّة
    الشركة وعن تقييم الموظّف.

    **الإيراد**: رسمُ الاشتراك الشهريُّ زائدَ الوحداتِ فوق الحصّة بسعر التجاوز،
    مقروءاً من `ServiceSubscription` نفسِه لا من تقدير.

    **التكلفةُ البشريّة**: «تقديريّةٌ مبنيّةٌ على الوحدات المعتمدة وتكلفة الوحدة/الوقت»
    بنصّ §٩، ومصدرُها `EmployeeCompensationPolicy` الذي أنشأته 210-D: راتبُ الموظّف
    الشهريُّ مقسوماً على **كلّ** ما أنتجه من وحداتٍ ذلك الشهر يعطي تكلفةَ الوحدة،
    ثمّ تُضرب في وحدات هذه الشركة منه. موظّفٌ أنتج مئةَ وحدةٍ براتب ٥٠٠ تكلفةُ
    وحدته ٥، وشركةٌ استهلكت عشرين منه تكلّف ١٠٠.

    **وموظّفٌ بصفر وحداتٍ لا يُوزَّع راتبُه على أحد**: لا قسمةَ على صفر، ولا تكلفةَ
    تُلصَق بشركةٍ لم تستهلك منه شيئاً.

    **والنفقاتُ المخصَّصة مُدخَلٌ لا مُشتَقّ**: لا مصدرَ لها في المستودع، فتُمرَّر
    صراحةً وتكون صفراً حين لا تُمرَّر — رقمٌ مُختلَقٌ هنا كان سيُنتج تصنيفاً يبدو
    دقيقاً وهو تخمين.

    **وسياسةُ الراتب تُقرأ بلحظةٍ داخل الشهر المحسوب** لا بلحظة العرض: حسابُ آذار
    بعد ترقيةِ راتبٍ في نيسان يجب أن يبقى كما كان، وإلا تغيّر تاريخٌ مُغلَق.
    """
    extra = Decimal(str(allocated_expenses_per_tenant or "0"))
    eligible = list(eligible_service_tenant_ids())
    if not eligible:
        return []

    subs = {
        sub.tenant_id: sub
        for sub in ServiceSubscription.objects.filter(tenant_id__in=eligible).select_related("tenant")
    }
    if not subs:
        return []

    _, last_day = calendar.monthrange(period_year, period_month)
    start_date = datetime.date(period_year, period_month, 1)
    end_date = datetime.date(period_year, period_month, last_day)
    _, period_end_moment = day_bounds(start_date, end_date)
    period_moment = period_end_moment - datetime.timedelta(seconds=1)

    # وحداتُ الشهر المعتمدة، مفصولةً: ما يستهلك حصّةَ العميل (للإيراد) وما يدخل
    # إنجازَ الموظّف (للتكلفة) — عَلَمان مستقلّان في `ServiceUsageEvent` عمداً.
    events = filter_local_date_range(
        ServiceUsageEvent.objects.filter(tenant_id__in=eligible),
        "approved_at", date_from=start_date, date_to=end_date,
    ).values_list(
        "tenant_id", "employee_id", "units", "chargeable_to_customer", "creditable_to_employee", "event_type",
    )

    chargeable_units: dict = {}
    employee_total_units: dict = {}
    tenant_employee_units: dict = {}
    for tenant_id, employee_id, units, chargeable, creditable, event_type in events:
        # **العكسُ يطرح لا يضيف**: `REVERSAL` يخزّن وحداتِه موجبةً كالأصل تماماً
        # (`reverse_service_usage_event` ينسخ `units` كما هي)، فجمعُها بلا إشارةٍ
        # كان يُظهر شركةً عُكست وحداتُها وقد استهلكت ضِعفَها، ويشحن عليها تجاوزاً
        # لم يقع. والإشارةُ هنا هي نفسُها إشارةُ `_net_units_for_...` في الدفتر.
        amount = Decimal(str(units or 0)) * (1 if event_type == ServiceUsageEvent.EventType.USAGE else -1)
        if chargeable:
            chargeable_units[tenant_id] = chargeable_units.get(tenant_id, Decimal("0")) + amount
        if creditable and employee_id:
            employee_total_units[employee_id] = employee_total_units.get(employee_id, Decimal("0")) + amount
            key = (tenant_id, employee_id)
            tenant_employee_units[key] = tenant_employee_units.get(key, Decimal("0")) + amount

    salaries = {
        employee_id: _monthly_base_salary_for(employee_id, at=period_moment)
        for employee_id in employee_total_units
    }

    previous_units: dict = {}
    if with_suggestions:
        prev_year, prev_month = (period_year - 1, 12) if period_month == 1 else (period_year, period_month - 1)
        previous_units = _chargeable_units_in_month(list(subs), prev_year, prev_month)

    rows = []
    for tenant_id, sub in subs.items():
        included = Decimal(str(sub.included_quota or 0))
        consumed = chargeable_units.get(tenant_id, Decimal("0"))
        overage_units = max(consumed - included, Decimal("0"))
        revenue = Decimal(str(sub.monthly_fee or 0)) + overage_units * Decimal(str(sub.overage_unit_price or 0))

        human_cost = Decimal("0.00")
        contributors = []
        for (row_tenant, employee_id), units in tenant_employee_units.items():
            if row_tenant != tenant_id:
                continue
            produced = employee_total_units.get(employee_id, Decimal("0"))
            if produced <= 0:
                continue
            unit_cost = salaries.get(employee_id, Decimal("0")) / produced
            share = (unit_cost * units).quantize(Decimal("0.01"))
            human_cost += share
            contributors.append({
                "employee_id": employee_id,
                "units": float(units),
                "unit_cost": float(unit_cost.quantize(Decimal("0.01"))),
                "cost": float(share),
            })

        total_cost = human_cost + extra
        margin = revenue - total_cost
        state = classify_profitability(revenue=revenue, total_cost=total_cost)
        suggestions = []
        if with_suggestions:
            suggestions = build_plan_fit_suggestions(
                subscription=sub,
                consumed_units=consumed,
                previous_consumed_units=previous_units.get(tenant_id, Decimal("0")),
                health=calculate_two_health_scores(sub.tenant),
            )
        rows.append({
            "tenant_id": tenant_id,
            "company_name": sub.tenant.CompanyName,
            "period_year": period_year,
            "period_month": period_month,
            "revenue": float(revenue.quantize(Decimal("0.01"))),
            "monthly_fee": float(Decimal(str(sub.monthly_fee or 0))),
            "included_quota": float(included),
            "chargeable_units": float(consumed),
            "overage_units": float(overage_units),
            "human_cost": float(human_cost.quantize(Decimal("0.01"))),
            "allocated_expenses": float(extra),
            "total_cost": float(total_cost.quantize(Decimal("0.01"))),
            "margin": float(margin.quantize(Decimal("0.01"))),
            "margin_pct": float((margin / revenue * 100).quantize(Decimal("0.01"))) if revenue > 0 else None,
            "state": state,
            "state_label": PROFITABILITY_LABELS[state],
            # «كل رقم قابل للفتح إلى مصادره» (§٩) — مساهمةُ كلّ موظّفٍ ووحداتُه.
            "contributors": sorted(contributors, key=lambda row: -row["cost"]),
            "suggestions": suggestions,
        })
    rows.sort(key=lambda row: row["margin"])
    return rows


# ==============================================================================
# KTRA Champions (§١٠) — لوحةٌ إيجابيّةٌ شهريّةٌ بستّ فئات
# ==============================================================================

CHAMPION_CATEGORY_QUALITY = "quality"
CHAMPION_CATEGORY_SLA = "sla"
CHAMPION_CATEGORY_SATISFACTION = "satisfaction"
CHAMPION_CATEGORY_COMPLETION = "approved_completion"
CHAMPION_CATEGORY_ACQUISITION = "paid_acquisition"
CHAMPION_CATEGORY_IMPROVEMENT = "documented_improvement"

CHAMPION_CATEGORY_LABELS = {
    CHAMPION_CATEGORY_QUALITY: "الجودة",
    CHAMPION_CATEGORY_SLA: "الالتزام بالـSLA",
    CHAMPION_CATEGORY_SATISFACTION: "رضا العملاء",
    CHAMPION_CATEGORY_COMPLETION: "الإنجاز المعتمد",
    CHAMPION_CATEGORY_ACQUISITION: "الاكتساب المدفوع",
    CHAMPION_CATEGORY_IMPROVEMENT: "التحسّن الموثّق",
}

# أربعُ فئاتٍ تقابل محاورَ الـpilot مباشرةً — **لا الدرجةَ المركّبة**، فـ§١٠ تمنع
# «استخدام الدرجة المركبة وحدها»، وفئةٌ لكلّ محورٍ تُظهر أين برع كلُّ واحدٍ بعينه.
CHAMPION_AXIS_CATEGORIES = {
    CHAMPION_CATEGORY_QUALITY: PILOT_AXIS_QUALITY,
    CHAMPION_CATEGORY_SLA: PILOT_AXIS_SLA,
    CHAMPION_CATEGORY_SATISFACTION: PILOT_AXIS_SATISFACTION,
    CHAMPION_CATEGORY_COMPLETION: PILOT_AXIS_TASK_COMPLETION,
}

#: حدُّ التحسّن الذي يُعدّ «موثّقاً» — نقاطٌ مئويّةٌ على الدرجة المركّبة بين شهرين.
CHAMPION_IMPROVEMENT_MIN_DELTA = Decimal("5.00")

#: كم اسماً يُعرض لكلّ فئة. **قِمّةٌ فقط**: §١٠ تمنع «ترتيب الأسوأ»، وقائمةٌ كاملةٌ
#: مرتَّبةٌ تنتج ترتيبَ الأسوأ ضمناً مهما سُمّيت.
CHAMPION_TOP_N = 3


def build_champions_board(*, period_year: int, period_month: int, top_n: int = CHAMPION_TOP_N) -> dict:
    """لوحةُ Champions لشهرٍ واحد (§١٠).

    **ما لا يظهر فيها، بنصّ المواصفة**: «لا رواتب، لا قيم عمولات، لا أسماء عملاء،
    لا ترتيب للأسوأ، ولا دخول لمن لا يملك حد العينة». فالاكتسابُ يُعَدّ **عدداً**
    لا مبلغاً، ولا اسمَ شركةٍ في أيّ دليل، ولا تُعاد إلا القمّةُ لكلّ فئة.

    و«التحسّن الموثّق» — الفئةُ السادسة التي لا تعرّفها المواصفة — يُقرأ هنا **فرقَ
    الدرجة المركّبة بين هذا الشهر والذي قبله** بما لا يقلّ عن
    `CHAMPION_IMPROVEMENT_MIN_DELTA` نقطة. والدليلُ هو الرقمان نفساهما، ولقطتاهما
    المجمَّدتان قائمتان — فهو «موثّق» بالمعنى الحرفيّ لا بتقديرٍ بشريّ. وهذا
    اجتهادٌ مُعلَنٌ لا نصٌّ منقول: إن أراد المالكُ تعريفاً آخر فمكانُه هنا وحدَه.
    """
    employees = list(
        PlatformEmployee.objects.filter(status=PlatformEmployee.Status.ACTIVE).select_related("user")
    )
    if not employees:
        return {"period_year": period_year, "period_month": period_month, "categories": []}

    prev_year, prev_month = (period_year, period_month - 1) if period_month > 1 else (period_year - 1, 12)

    # حسابٌ حيٌّ لكلّ موظّف: اللقطةُ المجمَّدة تحفظ الدرجةَ المركّبة وحجمَ العينة
    # ولا تحفظ المحاورَ مفصَّلةً، والفئاتُ محاورُ لا مركَّب. عددُ موظّفي الـpilot
    # صغيرٌ بحكم المرحلة، وإن كبر فمكانُ العلاج لقطةٌ تحفظ المحاور لا كاشٌ هنا.
    per_employee: dict[int, dict] = {}
    for employee in employees:
        try:
            per_employee[employee.pk] = calculate_employee_pilot_performance(
                employee=employee, period_year=period_year, period_month=period_month,
            )
        except Exception:  # noqa: BLE001 — موظّفٌ بلا بياناتٍ لا يُسقط اللوحةَ لبقيّة الفريق
            continue

    names = {e.pk: e.user.username for e in employees}
    categories: list[dict] = []

    for category, axis in CHAMPION_AXIS_CATEGORIES.items():
        entries = []
        for employee_pk, result in per_employee.items():
            # **حدُّ العينة شرطُ دخول**: لا مركزَ لمن لا دليلَ كافٍ عليه.
            if result.get("status") != PerformanceSnapshot.Status.CALCULATED:
                continue
            detail = (result.get("axes") or {}).get(axis)
            if not detail or not detail.get("applicable"):
                continue
            score = Decimal(str(detail.get("score_pct") or 0))
            entries.append({
                "employee_id": employee_pk,
                "employee_name": names.get(employee_pk, ""),
                "value": float(score),
                "evidence": (
                    f"{detail.get('numerator')} من {detail.get('denominator')} "
                    f"خلال {period_year}/{period_month}"
                ),
            })
        entries.sort(key=lambda row: -row["value"])
        categories.append({
            "category": category,
            "category_label": CHAMPION_CATEGORY_LABELS[category],
            "unit": "%",
            "entries": entries[:top_n],
        })

    # الاكتسابُ المدفوع: **عدداً لا مبلغاً**، وبلا اسم شركة.
    paid_counts: dict[int, int] = {}
    for row in AcquisitionCommissionLine.objects.filter(
        period_year=period_year,
        period_month=period_month,
        status__in=[WalletLineStatus.APPROVED, WalletLineStatus.PAYABLE, WalletLineStatus.PAID],
    ).values_list("employee_id", flat=True):
        paid_counts[row] = paid_counts.get(row, 0) + 1
    acquisition_entries = [
        {
            "employee_id": pk,
            "employee_name": names.get(pk, ""),
            "value": float(count),
            "evidence": f"{count} عميلاً باستحقاقٍ مؤكَّدٍ في {period_year}/{period_month}",
        }
        for pk, count in paid_counts.items()
        if pk in names
    ]
    acquisition_entries.sort(key=lambda row: -row["value"])
    categories.append({
        "category": CHAMPION_CATEGORY_ACQUISITION,
        "category_label": CHAMPION_CATEGORY_LABELS[CHAMPION_CATEGORY_ACQUISITION],
        "unit": "عميل",
        "entries": acquisition_entries[:top_n],
    })

    # التحسّنُ الموثّق: فرقُ الدرجة المركّبة عن الشهر السابق.
    previous = {
        row.employee_id: row.composite_score
        for row in PerformanceSnapshot.objects.filter(
            period_year=prev_year, period_month=prev_month, status=PerformanceSnapshot.Status.CALCULATED,
        )
        if row.composite_score is not None
    }
    improvement_entries = []
    for employee_pk, result in per_employee.items():
        if result.get("status") != PerformanceSnapshot.Status.CALCULATED:
            continue
        current = result.get("composite_score")
        before = previous.get(employee_pk)
        if current is None or before is None:
            continue
        delta = Decimal(str(current)) - Decimal(str(before))
        if delta < CHAMPION_IMPROVEMENT_MIN_DELTA:
            continue
        improvement_entries.append({
            "employee_id": employee_pk,
            "employee_name": names.get(employee_pk, ""),
            "value": float(delta),
            "evidence": (
                f"من {before}% في {prev_year}/{prev_month} إلى {current}% في {period_year}/{period_month}"
            ),
        })
    improvement_entries.sort(key=lambda row: -row["value"])
    categories.append({
        "category": CHAMPION_CATEGORY_IMPROVEMENT,
        "category_label": CHAMPION_CATEGORY_LABELS[CHAMPION_CATEGORY_IMPROVEMENT],
        "unit": "نقطة",
        "entries": improvement_entries[:top_n],
    })

    return {"period_year": period_year, "period_month": period_month, "categories": categories}


def request_performance_review(*, employee, period_year: int, period_month: int, axis: str = "", reason: str):
    """اعتراضُ الموظّف على نتيجةِ شهرٍ بسببٍ مكتوب (القصة ٤٤).

    **السببُ إلزاميّ**: «طلب مراجعة نتيجة **مع سبب**» — وطلبٌ بلا سببٍ لا يُصحّح
    خطأَ بياناتٍ ولا تصنيفاً، بل يفتح صفّاً لا يعرف المديرُ ماذا يفعل به.

    **وطلبٌ مفتوحٌ واحدٌ لكلّ (موظّف، فترة، محور)**: الحارسُ في الخدمة لا في قيدٍ
    شرطيّ — MySQL تتجاهل القيودَ الشرطيّة بصمت، وقد سبق أن كلّف ذلك هذا المستودعَ
    قيداً ظنَّه قائماً. والطلبُ المردودُ لا يمنع طلباً جديداً: الردُّ قد يكشف بياناتٍ
    جديدة.
    """
    reason = str(reason or "").strip()
    if not reason:
        raise PlatformOpsError("reason_required", "سبب طلب المراجعة مطلوب.")
    axis = str(axis or "").strip()
    with transaction.atomic():
        existing = (
            PerformanceReviewRequest.objects.select_for_update()
            .filter(
                employee=employee,
                period_year=period_year,
                period_month=period_month,
                axis=axis,
                status=PerformanceReviewRequest.Status.OPEN,
            )
            .first()
        )
        if existing is not None:
            raise PlatformOpsError(
                "review_request_already_open",
                "لديك طلبُ مراجعةٍ مفتوحٌ لهذه الفترة بالفعل.",
            )
        created = PerformanceReviewRequest.objects.create(
            employee=employee,
            period_year=period_year,
            period_month=period_month,
            axis=axis,
            reason=reason,
        )
    log_platform_activity(
        employee=employee,
        action=PlatformActivityLog.Action.OTHER,
        description=f"طلبُ مراجعة نتيجة {period_year}/{period_month} — {reason[:200]}",
        entity_type="performance_review_request",
        entity_id=created.pk,
        details={"operation": "request_performance_review", "axis": axis},
    )
    return created


def resolve_performance_review(*, review_request, accepted: bool, resolution_note: str, actor=None):
    """ردُّ مدير العمليات على اعتراض: قبولٌ مع تصحيحٍ عند المصدر، أو رفضٌ مُعلَّل.

    **ولا يمسّ هذا الفعلُ الدرجةَ إطلاقاً.** القبولُ يعني أنّ المديرَ سيصحّح بيانةً
    أو تصنيفَ ردٍّ عند مصدره ثمّ تُعاد اللقطة — فلو رفع هذا الفعلُ الدرجةَ مباشرةً
    لصار طلبُ المراجعة باباً خلفيّاً يلتفّ على الحساب من الأعمال.
    """
    note = str(resolution_note or "").strip()
    if not note:
        raise PlatformOpsError("resolution_note_required", "ردُّ المدير مطلوب.")
    with transaction.atomic():
        locked = PerformanceReviewRequest.objects.select_for_update().get(pk=review_request.pk)
        if locked.status != PerformanceReviewRequest.Status.OPEN:
            raise PlatformOpsError("review_request_not_open", "هذا الطلبُ مردودٌ عليه سلفاً.")
        locked.status = (
            PerformanceReviewRequest.Status.ACCEPTED if accepted else PerformanceReviewRequest.Status.REJECTED
        )
        locked.resolution_note = note
        locked.resolved_by = actor
        locked.resolved_at = timezone.now()
        locked.save(update_fields=["status", "resolution_note", "resolved_by", "resolved_at", "updated_at"])
    log_platform_activity(
        employee=locked.employee,
        action=PlatformActivityLog.Action.OTHER,
        description=f"ردٌّ على اعتراض {locked.period_year}/{locked.period_month}: {locked.get_status_display()}",
        entity_type="performance_review_request",
        entity_id=locked.pk,
        details={
            "operation": "resolve_performance_review",
            "actor_user_id": getattr(actor, "pk", None),
            "accepted": bool(accepted),
        },
    )
    return locked


def recapture_performance_after_accepted_review(*, review_request, actor=None) -> PerformanceSnapshot:
    """إعادةُ التقاط لقطةِ شهرٍ بعد قبولِ اعتراضٍ عليه (القصة ٤٤، تتمّة 210-F).

    **هذه هي الخطوةُ التي كان وعدُها معلَّقاً في الهواء.** `resolve_performance_review`
    لا تمسّ الدرجةَ عمداً — «القبولُ يعني تصحيحاً عند المصدر ثمّ تُعاد اللقطة» —
    لكنّ «تُعاد اللقطة» لم يكن لها مسارٌ واحدٌ في النظام: `force_refresh` موجودةٌ
    في `capture_pilot_performance_snapshot` ولا تستدعيها إلا دالّةُ الإغلاق، والإغلاقُ
    نفسُه idempotent فلا يُعيد الحساب. فكان قبولُ الاعتراض فعلاً بلا أثرٍ إلى الأبد.

    **والصلاحيةُ مقيَّدةٌ بالمبرِّر لا بالرتبة وحدَها**: لا تُعاد لقطةٌ إلا ولها
    اعتراضٌ **مقبولٌ** على الشهر نفسِه. فإعادةُ الالتقاط ليست زرّاً يرفع درجةً
    متى شاء المدير، بل أثرُ قرارٍ مكتوبٍ مُعلَّلٍ مسجَّلٍ في `PerformanceReviewRequest`.

    **ولا تُمسّ المحفظة.** أسطرُ الشهر قد تكون `PAID`، وتصحيحُها بابُه الظاهرُ
    `adjust_wallet_line` الذي يُنشئ سطرَ تسويةٍ يُرى — لا كتابةٌ فوق سطرٍ مدفوع.
    فتعديلُ الدرجةِ هنا يُعيد الرقمَ ويترك المالَ لمساره المُدقَّق.
    """
    with transaction.atomic():
        locked = PerformanceReviewRequest.objects.select_for_update().get(pk=review_request.pk)
        if locked.status != PerformanceReviewRequest.Status.ACCEPTED:
            raise PlatformOpsError(
                "review_request_not_accepted",
                "لا تُعاد اللقطة إلا بعد قبول الاعتراض — القبولُ هو مبرّرُ إعادة الحساب.",
            )
        employee = locked.employee
        # **السياسةُ تبقى سياسةَ الشهر لا سياسةَ اليوم.** بلا تمرير النسخة المجمَّدة
        # كانت `force_refresh` تُعيد قراءةَ السياسة النشطة لحظتَها، فاعتراضٌ يُقبَل
        # اليوم يُعيد تسعيرَ آذار بأوزانٍ نُشرت في نيسان ويمحو نسخةَ آذار المجمَّدة —
        # وتجميدُ اللقطة إنّما بُني ليمنع هذا بالضبط (210-D: «لا أثر رجعي»).
        # التصحيحُ يمسّ **البيانات** لا المقياس.
        frozen = PerformanceSnapshot.objects.filter(
            employee=employee, period_year=locked.period_year, period_month=locked.period_month,
        ).first()
        before = frozen.composite_score if frozen is not None else None
        snapshot = capture_pilot_performance_snapshot(
            employee=employee,
            period_year=locked.period_year,
            period_month=locked.period_month,
            evaluation_policy=frozen.evaluation_policy if frozen is not None else None,
            policy_dict=dict(frozen.policy_snapshot) if frozen is not None and frozen.policy_snapshot else None,
            captured_by=actor,
            force_refresh=True,
        )

    log_platform_activity(
        employee=employee,
        action=PlatformActivityLog.Action.OTHER,
        description=(
            f"إعادةُ التقاط لقطة {locked.period_year}/{locked.period_month} بعد قبول اعتراض"
        ),
        entity_type="performance_snapshot",
        entity_id=snapshot.pk,
        details={
            "operation": "recapture_performance_after_accepted_review",
            "actor_user_id": getattr(actor, "pk", None),
            "review_request_id": locked.pk,
            # الرقمان معاً: تغييرُ درجةٍ بلا «قبلُ وبعدُ» في السجلّ لا يُراجَع.
            "composite_before": str(before) if before is not None else None,
            "composite_after": str(snapshot.composite_score) if snapshot.composite_score is not None else None,
        },
    )
    return snapshot


def list_employee_engaged_companies(user) -> list[dict]:
    """شركاتُ ارتباطات الموظّف النشطة، ولكلٍّ حصّتُها وبنودُ الصحّة المُسنَدةُ إليه.

    القصّتان ٣٩ و٤٠: «أريد رؤية بنود صحة الشركة **المطلوب مني** علاجها» و«أريد رؤية
    وحدات الشركة المستخدمة والمتبقية **لكي لا أعد العميل بخدمة تتجاوز خطته**».

    **الشركاتُ تُشتقّ من الارتباطات لا من الطلب** — كسائر مسارات الوحدة: لا يقبل
    المسارُ معرّفَ شركةٍ، فلا يُفتح البابُ الذي أُغلق. والبنودُ تُضيَّق على
    `owner=user` وعلى الحالتين اللتين تطلبان عملاً (`follow_up`/`risk`): بندٌ سليمٌ
    أو لا ينطبق ليس «مطلوباً منه علاجُه»، وبندُ زميلٍ ليس شغلَه.

    ومصدرُ البنود **أحدثُ فحصٍ معتمد** لكلّ شركة: المسودّةُ قد تُعدَّل أو تُلغى،
    فعرضُها يُحمّل الموظّفَ عملاً لم يُعتمد بعد.
    """
    eligible = list(eligible_service_tenant_ids())
    engagements = (
        Engagement.objects.filter(
            employee__user=user, status=Engagement.Status.ACTIVE, tenant_id__in=eligible,
        )
        .select_related("tenant")
        .order_by("tenant__CompanyName")
    )
    tenant_ids = [e.tenant_id for e in engagements]
    if not tenant_ids:
        return []

    subs = {
        sub.tenant_id: sub
        for sub in ServiceSubscription.objects.filter(tenant_id__in=tenant_ids)
    }

    # أحدثُ فحصٍ معتمدٍ لكلّ شركة — صفٌّ واحدٌ لكلّ شركةٍ لا كلُّ تاريخها.
    latest_check_id: dict[int, int] = {}
    for row in (
        CompanyHealthCheck.objects.filter(
            tenant_id__in=tenant_ids, status=CompanyHealthCheck.Status.APPROVED,
        )
        .order_by("tenant_id", "-approved_at", "-pk")
        .values_list("tenant_id", "pk", named=False)
    ):
        latest_check_id.setdefault(row[0], row[1])

    items_by_tenant: dict[int, list[dict]] = {}
    if latest_check_id:
        actionable = [
            CompanyHealthCheckItem.ItemStatus.FOLLOW_UP,
            CompanyHealthCheckItem.ItemStatus.RISK,
        ]
        for item in (
            CompanyHealthCheckItem.objects.filter(
                health_check_id__in=list(latest_check_id.values()),
                owner=user,
                status__in=actionable,
            )
            .select_related("health_check")
            .order_by("due_date", "pk")
        ):
            items_by_tenant.setdefault(item.health_check.tenant_id, []).append({
                "id": item.pk,
                "code": item.code,
                "status": item.status,
                "status_display": item.get_status_display(),
                "mandatory": item.mandatory,
                "action": item.action,
                "evidence_note": item.evidence_note,
                "due_date": item.due_date,
                "work_order_id": item.work_order_id,
            })

    rows = []
    for engagement in engagements:
        sub = subs.get(engagement.tenant_id)
        included = int(getattr(sub, "included_quota", 0) or 0)
        consumed = int(getattr(sub, "consumed_quota", 0) or 0)
        rows.append({
            "tenant_id": engagement.tenant_id,
            "company_name": engagement.tenant.CompanyName,
            "subscription_status": getattr(sub, "status", "") or "",
            "included_quota": included,
            "consumed_quota": consumed,
            # **لا سالب**: التجاوزُ يُقرأ من `over_quota` لا من رصيدٍ بالسالب، وإلا
            # قرأ الموظّفُ «-٧ متبقّية» وهي ليست كميّةً متبقّيةً بل زيادةً مستهلَكة.
            "remaining_quota": max(included - consumed, 0),
            "over_quota": max(consumed - included, 0),
            "health_items": items_by_tenant.get(engagement.tenant_id, []),
        })
    return rows


def list_employee_work_order_queue(user):
    """طابورٌ موحَّدٌ للموظف عبر شركاته، مرتَّبٌ بالأولوية ثم الأجل (القصة ٣٤).

    الشركاتُ تُشتقّ من ارتباطاته النشطة والمؤهَّلة للخدمة وحدها — لا معامل شركةٍ
    من الطلب. الأوامرُ المغلقة أو الملغاة لا تدخل الطابور.
    """
    engaged_tenant_ids = Engagement.objects.filter(
        employee__user=user, status=Engagement.Status.ACTIVE, tenant_id__in=eligible_service_tenant_ids(),
    ).values_list("tenant_id", flat=True)
    qs = (
        WorkOrder.objects.select_related("tenant", "assignee__user")
        .filter(assignee__user=user, tenant_id__in=engaged_tenant_ids)
        .exclude(status__in=[WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED])
    )
    rows = list(qs)
    rows.sort(
        key=lambda wo: (
            -WORK_ORDER_PRIORITY_RANK.get(wo.priority, 0),
            wo.deadline_at or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc),
        )
    )
    return rows
