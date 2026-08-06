"""T-PLANLIMITS: حدود خطة الاشتراك لكل شركة.

مصدر الحقيقة الواحد لثلاثة أسئلة: **ما الحدّ** (افتراضي الخطة أو تجاوز الشركة)،
**كم استُهلك** (عدّ حقيقي من الجداول لا عدّاد مخزَّن يتفاوت)، و**هل يُسمح بواحد
إضافي** (حارس واحد تستدعيه كل نقطة إنشاء).

نفس نمط `core.access.ROLE_DEFAULTS` و`tenants.RolePermission`: الافتراضات هنا في
الكود، والجدول (`core.TenantLimit`) يحمل **الفروق فقط** — فحذف سطر التجاوز يعني
العودة لافتراضي الخطة، لا صفراً.

الحدّ `None` = بلا حدّ. العدّ الشهري يعتمد `created_at` لا تاريخ المستند: تاريخ
المستند يكتبه المستخدم، فحدٌّ مبنيّ عليه يُتجاوَز بتغيير تاريخ الفاتورة.
"""
import logging
from dataclasses import dataclass
from typing import Callable

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

PERIOD_MONTH = "month"
PERIOD_TOTAL = "total"

PERIOD_LABELS = {
    PERIOD_MONTH: "شهرياً",
    PERIOD_TOTAL: "إجمالاً",
}

_CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class LimitSpec:
    """تعريف حدّ واحد: مفتاحه، وصفه للمستخدم، ومن أين يُعدّ استهلاكه."""

    key: str
    label: str
    unit: str
    period: str
    count: Callable[[int, object], int]


def _month_start():
    """أول يوم في الشهر الحالي بتوقيت الخادم — بداية نافذة العدّ الشهري."""
    return timezone.localdate().replace(day=1)


def _count_sales_invoices(tenant_id, since):
    from sales.models import SalesInvoice

    return SalesInvoice.objects.filter(
        tenant_id=tenant_id, created_at__date__gte=since,
    ).count()


def _count_purchase_invoices(tenant_id, since):
    from logistics.models import PurchaseInvoice

    return PurchaseInvoice.objects.filter(
        tenant_id=tenant_id, created_at__date__gte=since,
    ).count()


def _count_all_invoices(tenant_id, since):
    return (
        _count_sales_invoices(tenant_id, since)
        + _count_purchase_invoices(tenant_id, since)
    )


def _count_warehouses(tenant_id, since):
    from inventory.models import Warehouse

    return Warehouse.objects.filter(tenant_id=tenant_id).count()


def _count_members(tenant_id, since):
    from tenants.models import UserCompanyMembership

    return UserCompanyMembership.objects.filter(tenant_id=tenant_id).count()


def _count_branches(tenant_id, since):
    from tenants.models import Branch

    return Branch.objects.filter(tenant_id=tenant_id).count()


def _count_products(tenant_id, since):
    from inventory.models import Product

    return Product.objects.filter(tenant_id=tenant_id).count()


def _count_partners(tenant_id, since):
    from partners.models import Partner

    return Partner.objects.filter(tenant_id=tenant_id).count()


LIMITS = {
    spec.key: spec
    for spec in (
        LimitSpec(
            key="sales.invoices",
            label="فواتير البيع",
            unit="فاتورة",
            period=PERIOD_MONTH,
            count=_count_sales_invoices,
        ),
        LimitSpec(
            key="purchase.invoices",
            label="فواتير الشراء",
            unit="فاتورة",
            period=PERIOD_MONTH,
            count=_count_purchase_invoices,
        ),
        LimitSpec(
            key="documents.invoices",
            label="إجمالي الفواتير (بيع + شراء)",
            unit="فاتورة",
            period=PERIOD_MONTH,
            count=_count_all_invoices,
        ),
        LimitSpec(
            key="inventory.warehouses",
            label="المستودعات",
            unit="مستودع",
            period=PERIOD_TOTAL,
            count=_count_warehouses,
        ),
        LimitSpec(
            key="company.members",
            label="أعضاء الشركة",
            unit="عضو",
            period=PERIOD_TOTAL,
            count=_count_members,
        ),
        LimitSpec(
            key="company.branches",
            label="الفروع",
            unit="فرع",
            period=PERIOD_TOTAL,
            count=_count_branches,
        ),
        LimitSpec(
            key="inventory.products",
            label="الأصناف",
            unit="صنف",
            period=PERIOD_TOTAL,
            count=_count_products,
        ),
        LimitSpec(
            key="partners.records",
            label="العملاء والموردون",
            unit="طرف",
            period=PERIOD_TOTAL,
            count=_count_partners,
        ),
    )
}


# افتراضات الخطط الثلاث — `None` = بلا حدّ. تُعدَّل هنا للمنصة كلها، ويُعدّلها
# السوبر أدمن لشركة بعينها من لوحة المنصة (TenantLimit) دون لمس هذا الجدول.
PLAN_DEFAULTS = {
    "Basic": {
        "sales.invoices": 200,
        "purchase.invoices": 100,
        "documents.invoices": 250,
        "inventory.warehouses": 1,
        "company.members": 3,
        "company.branches": 1,
        "inventory.products": 500,
        "partners.records": 200,
    },
    "Pro": {
        "sales.invoices": 1500,
        "purchase.invoices": 750,
        "documents.invoices": 2000,
        "inventory.warehouses": 5,
        "company.members": 10,
        "company.branches": 3,
        "inventory.products": 5000,
        "partners.records": 2000,
    },
    "Enterprise": {
        "sales.invoices": None,
        "purchase.invoices": None,
        "documents.invoices": None,
        "inventory.warehouses": None,
        "company.members": None,
        "company.branches": None,
        "inventory.products": None,
        "partners.records": None,
    },
}


def _tenant_id(tenant):
    """يقبل كائن الشركة أو معرّفها — بعض الحُرّاس لا يملك إلا المعرّف."""
    if tenant is None:
        return None
    if isinstance(tenant, int):
        return tenant
    return getattr(tenant, "pk", None)


def _plan_of(tenant):
    plan = getattr(tenant, "SubscriptionPlan", None)
    if plan is None:
        from tenants.models import Tenant

        tenant_id = _tenant_id(tenant)
        row = Tenant.objects.filter(pk=tenant_id).only("SubscriptionPlan").first()
        plan = getattr(row, "SubscriptionPlan", None)
    return plan if plan in PLAN_DEFAULTS else "Basic"


def plan_default(plan: str, key: str):
    """حدّ الخطة لهذا المفتاح — الخطة المجهولة تُعامَل كالأساسية لا كبلا حدّ."""
    return PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS["Basic"]).get(key)


def _cache_key(tenant_id):
    return f"plan_limits:{tenant_id}"


def tenant_overrides(tenant) -> dict:
    """تجاوزات الشركة {key: max_value|None} — استعلام واحد مُخزَّن مؤقتاً."""
    from core.models import TenantLimit

    tenant_id = _tenant_id(tenant)
    if tenant_id is None:
        return {}
    cached = cache.get(_cache_key(tenant_id))
    if cached is None:
        cached = {
            row.limit_key: row.max_value
            for row in TenantLimit.objects.filter(tenant_id=tenant_id)
        }
        cache.set(_cache_key(tenant_id), cached, timeout=_CACHE_TTL_SECONDS)
    return cached


def invalidate_limit_cache(tenant_id) -> None:
    cache.delete(_cache_key(_tenant_id(tenant_id)))


def limit_value(tenant, key: str):
    """الحدّ الفعّال: تجاوز الشركة إن وُجد، وإلا افتراضي خطتها. None = بلا حدّ."""
    if key not in LIMITS:
        return None
    overrides = tenant_overrides(tenant)
    if key in overrides:
        return overrides[key]
    return plan_default(_plan_of(tenant), key)


def current_usage(tenant, key: str) -> int:
    """الاستهلاك الحالي — عدّ حقيقي من الجداول ضمن نافذة الحدّ."""
    spec = LIMITS.get(key)
    tenant_id = _tenant_id(tenant)
    if spec is None or tenant_id is None:
        return 0
    since = _month_start() if spec.period == PERIOD_MONTH else None
    return spec.count(tenant_id, since)


def limit_rows(tenant) -> list[dict]:
    """صف لكل حدّ: الافتراضي، التجاوز، الفعّال، والاستهلاك — للوحة المنصة."""
    plan = _plan_of(tenant)
    overrides = tenant_overrides(tenant)
    rows = []
    for key, spec in LIMITS.items():
        default = plan_default(plan, key)
        has_override = key in overrides
        effective = overrides[key] if has_override else default
        rows.append({
            "key": key,
            "label": spec.label,
            "unit": spec.unit,
            "period": spec.period,
            "period_label": PERIOD_LABELS[spec.period],
            "plan_default": default,
            "override": overrides.get(key) if has_override else None,
            "has_override": has_override,
            "effective": effective,
            "usage": current_usage(tenant, key),
        })
    return rows


def limit_exceeded_message(tenant, key: str, limit: int) -> str:
    spec = LIMITS[key]
    return (
        f"بلغت شركتك حدّ خطة «{_plan_of(tenant)}» من {spec.label}: "
        f"{limit} {spec.unit} {PERIOD_LABELS[spec.period]}. "
        "ارفع الحدّ من لوحة المنصة أو رقِّ الخطة."
    )


def check_limit(tenant, key: str, *, additional: int = 1):
    """يعيد رسالة المنع إن كان إنشاء `additional` سيتجاوز الحدّ، وإلا None."""
    limit = limit_value(tenant, key)
    if limit is None:
        return None
    usage = current_usage(tenant, key)
    if usage + additional <= limit:
        return None
    logger.info(
        "plan limit blocked tenant=%s key=%s usage=%s limit=%s",
        _tenant_id(tenant), key, usage, limit,
    )
    return limit_exceeded_message(tenant, key, limit)


def enforce_limits(tenant, *keys: str) -> None:
    """حارس نقاط الإنشاء — يرفع 400 عربية عند أول حدّ مُستنفَد.

    يُستدعى قبل الحفظ لا بعده: رفض بعد الإنشاء يترك صفاً محسوباً ضمن الحدّ.
    """
    from rest_framework.exceptions import ValidationError

    if tenant is None:
        return
    for key in keys:
        message = check_limit(tenant, key)
        if message:
            raise ValidationError({"plan_limit": message, "limit_key": key})
