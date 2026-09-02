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
from datetime import timedelta
from typing import Callable

from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

from core.date_ranges import local_day_start

logger = logging.getLogger(__name__)

PERIOD_MONTH = "month"
PERIOD_TOTAL = "total"

PERIOD_LABELS = {
    PERIOD_MONTH: "شهرياً",
    PERIOD_TOTAL: "إجمالاً",
}

_CACHE_TTL_SECONDS = 300

# «قريب من الحدّ» = بلغ الاستهلاك أربعة أخماس الحدّ الفعّال. تحذيرٌ مبكّر يكفي
# لترقية خطة أو رفع حدّ قبل أن يُمنع المستخدم من إنشاء المستند التالي.
NEAR_LIMIT_RATIO = 0.8


@dataclass(frozen=True)
class LimitSpec:
    """تعريف حدّ واحد: مفتاحه، وصفه للمستخدم، ومن أين يُعدّ استهلاكه.

    لكل حدّ عدّادان متطابقا القاعدة: `count` لشركة واحدة، و`bulk` توأمه المجمَّع
    لعدّة شركات في استعلام واحد (`values('tenant_id').annotate(Count)`). لوحة
    المنصة تقرأ الثاني: العدّ الفردي في حلقة على الشركات هو مصدر انفجار
    الاستعلامات، لا الحلّ.
    """

    key: str
    label: str
    unit: str
    period: str
    count: Callable[[int, object], int]
    bulk: Callable[[object, object], dict]


def _month_start():
    """أول يوم في الشهر الحالي بتوقيت الخادم — بداية نافذة العدّ الشهري."""
    return timezone.localdate().replace(day=1)


def _grouped_count(queryset, tenant_ids) -> dict:
    """{tenant_id: عدد} في استعلام واحد — الشركة بلا صفوف تغيب عن القاموس.

    `order_by()` ليس تجميلاً: ترتيب `Meta` الافتراضي يدخل `GROUP BY` فيشظّي
    المجموعات ويعيد صفّاً لكل قيمة ترتيب بدل صفّ لكل شركة.
    """
    if tenant_ids is not None:
        queryset = queryset.filter(tenant_id__in=tenant_ids)
    return {
        row["tenant_id"]: row["n"]
        for row in queryset.values("tenant_id").order_by().annotate(n=Count("pk"))
    }


def _count_sales_invoices(tenant_id, since):
    from sales.models import SalesInvoice

    return SalesInvoice.objects.filter(
        tenant_id=tenant_id, created_at__gte=local_day_start(since),
    ).count()


def _bulk_sales_invoices(tenant_ids, since):
    from sales.models import SalesInvoice

    return _grouped_count(
        SalesInvoice.objects.filter(created_at__gte=local_day_start(since)), tenant_ids,
    )


def _count_purchase_invoices(tenant_id, since):
    from logistics.models import PurchaseInvoice

    return PurchaseInvoice.objects.filter(
        tenant_id=tenant_id, created_at__gte=local_day_start(since),
    ).count()


def _bulk_purchase_invoices(tenant_ids, since):
    from logistics.models import PurchaseInvoice

    return _grouped_count(
        PurchaseInvoice.objects.filter(created_at__gte=local_day_start(since)), tenant_ids,
    )


def _count_all_invoices(tenant_id, since):
    return (
        _count_sales_invoices(tenant_id, since)
        + _count_purchase_invoices(tenant_id, since)
    )


def _bulk_all_invoices(tenant_ids, since):
    merged = dict(_bulk_sales_invoices(tenant_ids, since))
    for tenant_id, count in _bulk_purchase_invoices(tenant_ids, since).items():
        merged[tenant_id] = merged.get(tenant_id, 0) + count
    return merged


def _count_warehouses(tenant_id, since):
    from inventory.models import Warehouse

    return Warehouse.objects.filter(tenant_id=tenant_id).count()


def _bulk_warehouses(tenant_ids, since):
    from inventory.models import Warehouse

    return _grouped_count(Warehouse.objects.all(), tenant_ids)


def _count_hr_employees(tenant_id, since):
    """الموظفون **النشطون** وحدهم — الموظف المعطَّل سجلٌّ تاريخي لا مقعدٌ مشغول.

    نظيرُ `company.members` وليس بديلَه: العضو حسابُ دخولٍ للنظام، والموظف
    ملفُّ رواتبٍ وحضور. أكثرُ الموظفين هنا بلا حساب دخول أصلاً.
    """
    from hr.models import Employee

    return Employee.objects.filter(tenant_id=tenant_id, is_active=True).count()


def _bulk_hr_employees(tenant_ids, since):
    from hr.models import Employee

    return _grouped_count(Employee.objects.filter(is_active=True), tenant_ids)


def _count_members(tenant_id, since):
    from tenants.models import UserCompanyMembership

    return UserCompanyMembership.objects.filter(tenant_id=tenant_id).count()


def _bulk_members(tenant_ids, since):
    from tenants.models import UserCompanyMembership

    return _grouped_count(UserCompanyMembership.objects.all(), tenant_ids)


def _count_branches(tenant_id, since):
    from tenants.models import Branch

    return Branch.objects.filter(tenant_id=tenant_id).count()


def _bulk_branches(tenant_ids, since):
    from tenants.models import Branch

    return _grouped_count(Branch.objects.all(), tenant_ids)


def _count_products(tenant_id, since):
    from inventory.models import Product

    return Product.objects.filter(tenant_id=tenant_id).count()


def _bulk_products(tenant_ids, since):
    from inventory.models import Product

    return _grouped_count(Product.objects.all(), tenant_ids)


def _count_partners(tenant_id, since):
    from partners.models import Partner

    return Partner.objects.filter(tenant_id=tenant_id).count()


def _bulk_partners(tenant_ids, since):
    from partners.models import Partner

    return _grouped_count(Partner.objects.all(), tenant_ids)


def _count_managed_books(tenant_id, since):
    """ISSUE #52: عدد الدفاتر المُدارة التي يملكها هذا المكتب (`Tenant.managed_by`)."""
    from tenants.models import Tenant

    return Tenant.objects.filter(managed_by_id=tenant_id).count()


def _bulk_managed_books(tenant_ids, since):
    """يجمع على `managed_by_id` لا `tenant_id` — لا حقل بهذا الاسم على Tenant."""
    from tenants.models import Tenant

    qs = Tenant.objects.filter(managed_by_id__isnull=False)
    if tenant_ids is not None:
        qs = qs.filter(managed_by_id__in=tenant_ids)
    return {
        row["managed_by_id"]: row["n"]
        for row in qs.values("managed_by_id").order_by().annotate(n=Count("pk"))
    }


LIMITS = {
    spec.key: spec
    for spec in (
        LimitSpec(
            key="sales.invoices",
            label="فواتير البيع",
            unit="فاتورة",
            period=PERIOD_MONTH,
            count=_count_sales_invoices,
            bulk=_bulk_sales_invoices,
        ),
        LimitSpec(
            key="purchase.invoices",
            label="فواتير الشراء",
            unit="فاتورة",
            period=PERIOD_MONTH,
            count=_count_purchase_invoices,
            bulk=_bulk_purchase_invoices,
        ),
        LimitSpec(
            key="documents.invoices",
            label="إجمالي الفواتير (بيع + شراء)",
            unit="فاتورة",
            period=PERIOD_MONTH,
            count=_count_all_invoices,
            bulk=_bulk_all_invoices,
        ),
        LimitSpec(
            key="inventory.warehouses",
            label="المستودعات",
            unit="مستودع",
            period=PERIOD_TOTAL,
            count=_count_warehouses,
            bulk=_bulk_warehouses,
        ),
        LimitSpec(
            key="hr.employees",
            label="الموظفون على كشف الرواتب",
            unit="موظف",
            period=PERIOD_TOTAL,
            count=_count_hr_employees,
            bulk=_bulk_hr_employees,
        ),
        LimitSpec(
            key="company.members",
            label="أعضاء الشركة",
            unit="عضو",
            period=PERIOD_TOTAL,
            count=_count_members,
            bulk=_bulk_members,
        ),
        LimitSpec(
            key="company.branches",
            label="الفروع",
            unit="فرع",
            period=PERIOD_TOTAL,
            count=_count_branches,
            bulk=_bulk_branches,
        ),
        LimitSpec(
            key="inventory.products",
            label="المنتجات",
            unit="منتج",
            period=PERIOD_TOTAL,
            count=_count_products,
            bulk=_bulk_products,
        ),
        LimitSpec(
            key="partners.records",
            label="العملاء والموردون",
            unit="طرف",
            period=PERIOD_TOTAL,
            count=_count_partners,
            bulk=_bulk_partners,
        ),
        LimitSpec(
            key="office.managed_books",
            label="الدفاتر المُدارة",
            unit="دفتر",
            period=PERIOD_TOTAL,
            count=_count_managed_books,
            bulk=_bulk_managed_books,
        ),
    )
}


# افتراضات الخطط — `None` = بلا حدّ. تُعدَّل هنا للمنصة كلها، ويُعدّلها
# السوبر أدمن لشركة بعينها من لوحة المنصة (TenantLimit) دون لمس هذا الجدول.
PLAN_DEFAULTS = {
    "Basic": {
        "sales.invoices": 200,
        "purchase.invoices": 100,
        "documents.invoices": 250,
        "inventory.warehouses": 1,
        "hr.employees": 10,
        "company.members": 3,
        "company.branches": 1,
        "inventory.products": 500,
        "partners.records": 200,
        "office.managed_books": 3,
    },
    "Pro": {
        "sales.invoices": 1500,
        "purchase.invoices": 750,
        "documents.invoices": 2000,
        "inventory.warehouses": 5,
        "hr.employees": 50,
        "company.members": 10,
        "company.branches": 3,
        "inventory.products": 5000,
        "partners.records": 2000,
        "office.managed_books": 25,
    },
    "Enterprise": {
        "sales.invoices": None,
        "purchase.invoices": None,
        "documents.invoices": None,
        "inventory.warehouses": None,
        "hr.employees": None,
        "company.members": None,
        "company.branches": None,
        "inventory.products": None,
        "partners.records": None,
        "office.managed_books": None,
    },
}

# T-TRIAL: التجربة تعرض المنتج بكامل قوّته — حدود Pro لأسبوعين. تجربةٌ مخنوقة
# بحدود الأساسية تُخفي نصف النظام عمّن جاء يقرّر، وهو ما تتفق عليه منتجات
# الاشتراك (Zoho/Odoo): القيد على **العمر** لا على المزايا. نسخةٌ لا إشارة،
# فرفع حدود Pro لاحقاً قرارٌ منفصل عن رفع سقف التجربة.
PLAN_DEFAULTS["Trial"] = dict(PLAN_DEFAULTS["Pro"])

# طول التجربة الافتراضي حين يحوّل السوبر أدمن شركةً إلى الخطة التجريبية بلا
# تاريخ — يمدّده يدوياً لأي شركة بتعديل التاريخ وحده.
TRIAL_PERIOD_DAYS = 14

# «قاربت على الانتهاء» = هذا العدد من الأيام أو أقل. نافذة التذكير الأخيرة قبل
# أن يصير الحساب للقراءة فقط، ويقرأها الشريط داخل التطبيق ولوحة المنصة معاً.
EXPIRY_WARNING_DAYS = 7


def _tenant_id(tenant):
    """يقبل كائن الشركة أو معرّفها — بعض الحُرّاس لا يملك إلا المعرّف."""
    if tenant is None:
        return None
    if isinstance(tenant, int):
        return tenant
    return getattr(tenant, "pk", None)


def _billing_tenant(tenant):
    """ISSUE #52: الدفتر المُدار ليس مشتركاً — مكتبه هو المشترك.

    الدفتر يُنشأ عبر `create_company` كأي شركة، فيبدأ تجريبياً بأربعة عشر يوماً.
    ولو بقي كذلك لصار مكتبٌ **مشترِكٌ ودافع** عاجزاً عن الكتابة في دفاتر عملائه
    بعد أسبوعين. فالخطة والانتهاء يُقرآن من المكتب المالك، ومصدر الحقيقة يبقى
    واحداً: لا نسخةَ تاريخٍ تُنسخ عند الإنشاء ثم تفترق عند التجديد.

    بلا كلفة على المسار الشائع: `managed_by_id` محمولٌ مع الشركة المحمَّلة،
    والاستعلام الإضافي لا يقع إلا على دفترٍ مُدار فعلاً.
    """
    office_id = getattr(tenant, "managed_by_id", None)
    if office_id is None:
        return tenant
    from tenants.models import Tenant

    office = (
        Tenant.objects.filter(pk=office_id)
        .only("SubscriptionPlan", "subscription_ends_at", "managed_by")
        .first()
    )
    return office if office is not None else tenant


def _plan_of(tenant):
    tenant = _billing_tenant(tenant)
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


def trial_end_date():
    """تاريخ انتهاء تجربةٍ تبدأ اليوم — بتوقيت الخادم لا بتوقيت المتصفّح."""
    return timezone.localdate() + timedelta(days=TRIAL_PERIOD_DAYS)


def subscription_expiry(tenant) -> dict:
    """حالة اشتراك الشركة زمنياً: {ends_at, days_left, expired, expiring_soon}.

    مصدر الحقيقة الواحد للانتهاء — يقرأه حارس الكتابة، وكرت الشركة في لوحة
    المنصة، والشريط داخل التطبيق؛ فلا تتكرّر قاعدة «متى انتهى» في ثلاثة أمكنة
    تتباعد لاحقاً بيومٍ أو بشرطِ `>=` مقابل `>`.

    التاريخ **شامل**: `days_left == 0` يعني «آخر يوم عمل اليوم» لا «انتهى»،
    والانتهاء يبدأ في اليوم التالي (`days_left < 0`). `ends_at = None` (الخطط
    الدائمة) يعطي `expired=False` و`days_left=None` — لا صفراً يُقرأ خطأً.

    يقبل كائن الشركة أو معرّفها؛ الكائن لا يكلّف استعلاماً (الحقل محمول معه)،
    والمعرّف وحده يكلّف استعلاماً واحداً بعمودٍ واحد.
    """
    tenant = _billing_tenant(tenant)
    ends_at = getattr(tenant, "subscription_ends_at", None)
    if ends_at is None and not hasattr(tenant, "subscription_ends_at"):
        from tenants.models import Tenant

        tenant_id = _tenant_id(tenant)
        row = (
            Tenant.objects.filter(pk=tenant_id).only("subscription_ends_at").first()
            if tenant_id is not None else None
        )
        ends_at = getattr(row, "subscription_ends_at", None)
    if ends_at is None:
        return {
            "ends_at": None,
            "days_left": None,
            "expired": False,
            "expiring_soon": False,
        }
    days_left = (ends_at - timezone.localdate()).days
    return {
        "ends_at": ends_at,
        "days_left": days_left,
        "expired": days_left < 0,
        "expiring_soon": 0 <= days_left <= EXPIRY_WARNING_DAYS,
    }


def subscription_expired(tenant) -> bool:
    """هل مضى تاريخ انتهاء اشتراك الشركة؟ — حارس الكتابة يسأل هذا وحده."""
    return subscription_expiry(tenant)["expired"]


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


def bulk_usage(keys=None, tenant_ids=None) -> dict:
    """{key: {tenant_id: استهلاك}} — استعلامٌ لكل مصدر عدّ، لا استعلام لكل شركة.

    توأم `current_usage` للوحة المنصة: قراءة صفٍّ لخمسين شركة عبر `current_usage`
    تعني خمسين ضرب عدد الحدود من الاستعلامات. النافذة الشهرية هي نفسها هنا
    (`created_at`)، والشركة بلا صفوف تغيب عن القاموس فاستهلاكها صفر.
    """
    selected = tuple(LIMITS) if keys is None else tuple(k for k in keys if k in LIMITS)
    month_start = _month_start()
    usage = {}
    for key in selected:
        spec = LIMITS[key]
        since = month_start if spec.period == PERIOD_MONTH else None
        usage[key] = spec.bulk(tenant_ids, since)
    return usage


def bulk_overrides(tenant_ids=None) -> dict:
    """{tenant_id: {key: max_value}} في استعلام واحد — بلا كاش ولا `_plan_of`.

    `tenant_overrides` مُخزَّن مؤقتاً لشركةٍ واحدة تُقرأ مراراً؛ اللوحة تقرأ كل
    الشركات مرةً واحدة، فالكاش هناك يصير خمسين قراءةً بلا فائدة. وجود المفتاح هو
    الإشارة: `max_value = None` تجاوزٌ صريح بمعنى **بلا حدّ**، لا «غير مضبوط».
    """
    from core.models import TenantLimit

    rows = TenantLimit.objects.all()
    if tenant_ids is not None:
        rows = rows.filter(tenant_id__in=tenant_ids)
    overrides: dict = {}
    for tenant_id, key, max_value in rows.values_list(
        "tenant_id", "limit_key", "max_value",
    ):
        overrides.setdefault(tenant_id, {})[key] = max_value
    return overrides


def near_limit_rows(plan: str, overrides: dict, usage: dict) -> list[dict]:
    """حدود هذه الشركة التي بلغ استهلاكها `NEAR_LIMIT_RATIO` — الأقربُ أولاً.

    دالة حسابٍ خالصة: تأخذ ما قرأه `bulk_usage`/`bulk_overrides` ولا تلمس قاعدة
    البيانات، فتصلح لخمسين شركة بلا استعلامٍ واحد. «بلا حدّ» (`None`) لا يقترب
    أبداً — لا نسبة له أصلاً.
    """
    rows = []
    for key, spec in LIMITS.items():
        limit = overrides[key] if key in overrides else plan_default(plan, key)
        if limit is None:
            continue
        used = usage.get(key, 0)
        if used >= limit * NEAR_LIMIT_RATIO:
            rows.append({
                "key": key,
                "label": spec.label,
                "usage": used,
                "limit": limit,
            })
    # الأقرب إلى حدّه أولاً كي يقرأ من يعرض الصفّ أسوأ حدٍّ من أول عنصر.
    # حدّ صفر مبلوغٌ بطبيعته — نسبته 1.0 لا قسمةٌ على صفر.
    rows.sort(
        key=lambda row: (row["usage"] / row["limit"]) if row["limit"] else 1.0,
        reverse=True,
    )
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
