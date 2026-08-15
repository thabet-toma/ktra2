"""T-PERM — محرّك الصلاحيات: مصدر حقيقة واحد للمن-يقدر-يفعل-ماذا.

قبل هذه الطبقة كان الإنفاذ مبعثراً: «مستعرض قراءة فقط» (core.permissions) +
فحوص `user_is_admin` متفرّقة + صلاحية الاستيراد (core.import_access) + شروط
`role === 'manager'` في الواجهة. لا مكان واحد يجيب: «مَن يتراجع عن الترحيل؟»

النموذج (كما في الأنظمة الاحترافية):
    كتالوج صلاحيات مُسمّاة  →  مصفوفة افتراضية لكل دور  →  تجاوزات لكل شركة

- `PERMISSIONS`: الكتالوج (مفتاح + تسمية عربية + مجموعة) — تغذّي شاشة الصلاحيات.
- `ROLE_DEFAULTS`: ما يملكه كل دور افتراضياً («*» = كل شيء، للمدير).
- `tenants.RolePermission`: تجاوز لكل (شركة، دور، مفتاح) — منح أو منع صريح،
  يُحرّره مدير الشركة من الشاشة. المدير لا يُجرَّد من صلاحياته بتجاوز (لئلا
  يقفل نفسه خارج نظامه).

الإنفاذ على **الخادم** عبر `require_perm` / `@requires_perm`؛ أعلام الواجهة
(`/api/permissions/me`) للعرض فقط — إخفاء زر لا يحمي endpoint.
"""
from __future__ import annotations

import logging
from functools import wraps

from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# الكتالوج — كل صلاحية تُذكر مرة واحدة هنا، والواجهة تقرأها كما هي.
# ──────────────────────────────────────────────────────────────────────────
GROUP_SALES = "المبيعات"
GROUP_PURCHASE = "المشتريات"
GROUP_INVENTORY = "المخزون"
GROUP_ACCOUNTING = "المحاسبة"
GROUP_IMPORT = "الاستيراد"
GROUP_HR = "شؤون الموظفين"
GROUP_ADMIN = "الإدارة والإعدادات"
GROUP_TAX = "الضريبة والمراجعة"
GROUP_DEVICES = "الأجهزة الحساسة"
GROUP_AFTERSALES = "خدمة ما بعد البيع"

PERMISSIONS: list[dict] = [
    # المبيعات
    {"key": "sales.invoice.view", "label": "عرض فواتير البيع", "group": GROUP_SALES},
    {"key": "sales.invoice.create", "label": "إنشاء فاتورة بيع", "group": GROUP_SALES},
    {"key": "sales.invoice.edit", "label": "تعديل فاتورة بيع", "group": GROUP_SALES},
    {"key": "sales.invoice.delete", "label": "حذف فاتورة بيع", "group": GROUP_SALES},
    {"key": "sales.invoice.post", "label": "ترحيل فاتورة بيع", "group": GROUP_SALES},
    {"key": "sales.invoice.unpost", "label": "التراجع عن ترحيل فاتورة بيع", "group": GROUP_SALES},
    {"key": "sales.payment.create", "label": "إنشاء سند قبض", "group": GROUP_SALES},
    {"key": "sales.payment.post", "label": "ترحيل سند قبض", "group": GROUP_SALES},
    {"key": "sales.payment.unpost", "label": "التراجع عن ترحيل سند قبض", "group": GROUP_SALES},
    {"key": "sales.quotation.manage", "label": "عروض الأسعار والطلبيات", "group": GROUP_SALES},
    {"key": "sales.customer.view", "label": "عرض العملاء", "group": GROUP_SALES},
    {"key": "sales.customer.manage", "label": "إدارة العملاء", "group": GROUP_SALES},
    {"key": "sales.settings.manage", "label": "إعدادات المبيعات", "group": GROUP_SALES},
    # المشتريات
    {"key": "purchase.invoice.view", "label": "عرض فواتير الشراء", "group": GROUP_PURCHASE},
    {"key": "purchase.invoice.create", "label": "إنشاء فاتورة شراء", "group": GROUP_PURCHASE},
    {"key": "purchase.invoice.edit", "label": "تعديل فاتورة شراء", "group": GROUP_PURCHASE},
    {"key": "purchase.invoice.delete", "label": "حذف فاتورة شراء", "group": GROUP_PURCHASE},
    {"key": "purchase.invoice.post", "label": "ترحيل فاتورة شراء", "group": GROUP_PURCHASE},
    {"key": "purchase.invoice.unpost", "label": "التراجع عن ترحيل فاتورة شراء", "group": GROUP_PURCHASE},
    {"key": "purchase.payment.create", "label": "إنشاء سند صرف", "group": GROUP_PURCHASE},
    {"key": "purchase.payment.post", "label": "ترحيل سند صرف", "group": GROUP_PURCHASE},
    {"key": "purchase.payment.unpost", "label": "التراجع عن ترحيل سند صرف", "group": GROUP_PURCHASE},
    {"key": "purchase.supplier.view", "label": "عرض الموردين", "group": GROUP_PURCHASE},
    {"key": "purchase.supplier.manage", "label": "إدارة الموردين", "group": GROUP_PURCHASE},
    {"key": "purchase.settings.manage", "label": "إعدادات المشتريات", "group": GROUP_PURCHASE},
    # المخزون
    {"key": "inventory.item.view", "label": "عرض الأصناف والمخزون", "group": GROUP_INVENTORY},
    {"key": "inventory.item.manage", "label": "إدارة الأصناف والفئات", "group": GROUP_INVENTORY},
    {"key": "inventory.cost.view", "label": "عرض التكاليف وهوامش الربح", "group": GROUP_INVENTORY},
    {"key": "inventory.doc.post", "label": "ترحيل مستندات المخزون (تحويل/جرد/تسوية)", "group": GROUP_INVENTORY},
    {"key": "inventory.doc.unpost", "label": "التراجع عن ترحيل مستندات المخزون", "group": GROUP_INVENTORY},
    # المحاسبة
    {"key": "accounting.journal.view", "label": "عرض القيود والتقارير المحاسبية", "group": GROUP_ACCOUNTING},
    {"key": "accounting.journal.create", "label": "إنشاء قيد يدوي", "group": GROUP_ACCOUNTING},
    {"key": "accounting.journal.post", "label": "ترحيل قيد", "group": GROUP_ACCOUNTING},
    {"key": "accounting.journal.unpost", "label": "التراجع عن ترحيل قيد", "group": GROUP_ACCOUNTING},
    {"key": "accounting.account.manage", "label": "إدارة شجرة الحسابات", "group": GROUP_ACCOUNTING},
    {"key": "accounting.period.manage", "label": "الفترات المالية والإغلاق السنوي", "group": GROUP_ACCOUNTING},
    {"key": "accounting.report.view", "label": "التقارير المالية", "group": GROUP_ACCOUNTING},
    {"key": "finance.cashbox.manage", "label": "صناديق الكاش (تمويل/تحويل/إيداع)", "group": GROUP_ACCOUNTING},
    # الاستيراد (يبقى مشروطاً بتفعيل الوحدة للشركة — core.import_access)
    {"key": "import.deal.manage", "label": "إدارة صفقات الاستيراد", "group": GROUP_IMPORT},
    {"key": "import.shipment.manage", "label": "إدارة الشحنات والتخليص", "group": GROUP_IMPORT},
    {"key": "import.doc.unpost", "label": "التراجع عن ترحيل مستندات الاستيراد", "group": GROUP_IMPORT},
    # شؤون الموظفين (تقود قائمة «إدارة الموظفين» في الشريط الجانبي)
    {"key": "hr.employees.manage", "label": "قائمة المستخدمين وملاحظات الموظفين", "group": GROUP_HR},
    {"key": "hr.attendance.view", "label": "شاشة الحضور والغياب", "group": GROUP_HR},
    {"key": "hr.points.manage", "label": "إدارة النقاط", "group": GROUP_HR},
    {"key": "hr.tasks.manage", "label": "إدارة المهام (لا مهامي)", "group": GROUP_HR},
    # الرواتب — قراءة، وإدارة (موظفون/ساعات/غيابات/كشوف)، وترحيل وصرف.
    {"key": "hr.payroll.view", "label": "عرض الرواتب وكشوفها", "group": GROUP_HR},
    {"key": "hr.payroll.manage", "label": "إدارة الموظفين والساعات وكشوف الرواتب", "group": GROUP_HR},
    {"key": "hr.payroll.post", "label": "ترحيل كشوف الرواتب وصرفها", "group": GROUP_HR},
    # الإدارة
    {"key": "admin.members.manage", "label": "إدارة أعضاء الشركة وأدوارهم", "group": GROUP_ADMIN},
    {"key": "admin.permissions.manage", "label": "إدارة الصلاحيات", "group": GROUP_ADMIN},
    {"key": "admin.settings.manage", "label": "إعدادات الشركة العامة", "group": GROUP_ADMIN},
    {"key": "admin.activity.view", "label": "سجل نشاط المستخدمين", "group": GROUP_ADMIN},
    # ST-3: المتجر العام — فتحه وإقفاله واختيار رابطه وتحديد ما يُعرض فيه.
    # مفتاح مستقل عن «إعدادات الشركة العامة» عمداً: مَن يضبط العنوان والشعار لا
    # يفتح بذلك واجهةً تعرض أسعار الشركة لكل زائر بلا جلسة. المدير يملكه ضمناً
    # («*») ويمنحه لمن يدير المتجر من شاشة الصلاحيات القائمة.
    {"key": "store.manage", "label": "إدارة المتجر العام", "group": GROUP_ADMIN},
    # بوابة المحاسب القانوني — لا تظهر إلا للشركات المرخّصة للوحدة.
    {"key": "tax.period.view", "label": "عرض فترات المراجعة الضريبية", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.period.prepare", "label": "تجهيز الفترة وتشغيل قائمة الجاهزية", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.period.approve", "label": "اعتماد الفترة الضريبية", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.period.reopen", "label": "إعادة فتح فترة معتمدة", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.filing.submit", "label": "تسجيل تقديم الإقرار", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.clearance.issue", "label": "إصدار فاتورة مقاصة", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.assignment.request", "label": "طلب رقم تخصيص إسرائيلي", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "tax.integration.manage", "label": "إدارة تفويض التكامل الضريبي", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "review.query.create", "label": "إنشاء طلب توضيح", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "review.query.respond", "label": "الرد على طلب توضيح", "group": GROUP_TAX, "module": "accountant_portal"},
    {"key": "finance.export.package", "label": "تصدير حزمة المراجعة", "group": GROUP_TAX, "module": "accountant_portal"},
    # تسجيل وتتبع الأجهزة الحساسة — لا تظهر إلا للشركات المرخّصة للوحدة.
    {"key": "devices.registry.view", "label": "عرض سجل الأجهزة الحساسة", "group": GROUP_DEVICES, "module": "sensitive_devices"},
    {"key": "devices.registry.create", "label": "تسجيل جهاز حسّاس", "group": GROUP_DEVICES, "module": "sensitive_devices"},
    {"key": "devices.registry.edit", "label": "تعديل سجل جهاز حسّاس", "group": GROUP_DEVICES, "module": "sensitive_devices"},
    {"key": "devices.registry.delete", "label": "حذف واسترجاع سجل جهاز حسّاس", "group": GROUP_DEVICES, "module": "sensitive_devices"},
    {"key": "devices.audit.view", "label": "عرض سجل تدقيق الأجهزة", "group": GROUP_DEVICES, "module": "sensitive_devices"},
    # خدمة ما بعد البيع — لا تظهر إلا للشركات المرخّصة للوحدة.
    {"key": "aftersales.warranty.view", "label": "عرض بطاقات الكفالة", "group": GROUP_AFTERSALES, "module": "after_sales"},
    {"key": "aftersales.warranty.manage", "label": "إنشاء بطاقة كفالة وتمديدها", "group": GROUP_AFTERSALES, "module": "after_sales"},
    {"key": "aftersales.order.view", "label": "عرض أوامر الصيانة", "group": GROUP_AFTERSALES, "module": "after_sales"},
    {"key": "aftersales.order.create", "label": "استقبال جهاز وفتح أمر صيانة", "group": GROUP_AFTERSALES, "module": "after_sales"},
    {"key": "aftersales.order.edit", "label": "تعديل أمر صيانة ونقل حالته", "group": GROUP_AFTERSALES, "module": "after_sales"},
    {"key": "aftersales.order.post", "label": "ترحيل قطع الكفالة وتوليد فاتورة الصيانة", "group": GROUP_AFTERSALES, "module": "after_sales"},
    {"key": "aftersales.order.unpost", "label": "التراجع عن ترحيل قطع الكفالة", "group": GROUP_AFTERSALES, "module": "after_sales"},
]

# القراءة المجرّدة — ما يملكه «المستعرض» ويرثه كل دور أعلى منه.
_VIEW_ONLY = {
    "sales.invoice.view",
    "sales.customer.view",
    "purchase.invoice.view",
    "purchase.supplier.view",
    "inventory.item.view",
}

# قراءة الدفاتر والتقارير المالية ليست قراءةً تشغيلية — المحاسب والمدير فقط
# افتراضياً (تُمنح لغيرهما بنقرة من شاشة الصلاحيات).
_ACCOUNTING_VIEW = {
    "accounting.journal.view",
    "accounting.report.view",
}

# قراءة ما بعد البيع: «موظف فصاعداً» — المستعرض وحده خارجها. تُذكر صراحةً في كل
# دور لأن الأدوار تبني على `_VIEW_ONLY` لا على `_STAFF`، فلا وراثة بينها.
_AFTERSALES_READ = {
    "aftersales.warranty.view",
    "aftersales.order.view",
}

_SALES_EMPLOYEE = _VIEW_ONLY | _AFTERSALES_READ | {
    "hr.attendance.view",
    "sales.invoice.create",
    "sales.invoice.edit",
    "sales.invoice.post",
    "sales.payment.create",
    "sales.payment.post",
    "sales.quotation.manage",
    "sales.customer.manage",
    # الكفالة وأمر الصيانة عملُ واجهة الزبون — البيع يفتحه ويحرّكه، والمال فيه
    # (ترحيل القطع المغطاة والفوترة) للمحاسب وحده.
    "aftersales.warranty.manage",
    "aftersales.order.create",
    "aftersales.order.edit",
}

_PROCUREMENT_EMPLOYEE = _VIEW_ONLY | _AFTERSALES_READ | {
    "hr.attendance.view",
    "purchase.invoice.create",
    "purchase.invoice.edit",
    "purchase.invoice.post",
    "purchase.payment.create",
    "purchase.payment.post",
    "purchase.supplier.manage",
    "inventory.item.manage",
    "inventory.cost.view",
    "inventory.doc.post",
    "import.deal.manage",
    "import.shipment.manage",
}

_ACCOUNTANT = _VIEW_ONLY | _ACCOUNTING_VIEW | _AFTERSALES_READ | {
    "hr.attendance.view",
    "sales.invoice.post",
    "sales.invoice.unpost",
    "sales.payment.create",
    "sales.payment.post",
    "sales.payment.unpost",
    "purchase.invoice.post",
    "purchase.invoice.unpost",
    "purchase.payment.create",
    "purchase.payment.post",
    "purchase.payment.unpost",
    "inventory.cost.view",
    "inventory.doc.post",
    "inventory.doc.unpost",
    "accounting.journal.create",
    "accounting.journal.post",
    "accounting.journal.unpost",
    "accounting.account.manage",
    "accounting.period.manage",
    "finance.cashbox.manage",
    "import.doc.unpost",
    # الرواتب مصروفٌ يمسّ الدفاتر — المحاسب صاحبها كسائر المستندات المالية.
    "hr.payroll.view",
    "hr.payroll.manage",
    "hr.payroll.post",
    # صرف قطع الكفالة قيدٌ في الدفاتر، وفاتورة الصيانة إيراد — كلاهما للمحاسب.
    "aftersales.warranty.manage",
    "aftersales.order.post",
    "aftersales.order.unpost",
}

_LEGAL_ACCOUNTANT = {
    "sales.invoice.view",
    "purchase.invoice.view",
    "sales.customer.view",
    "purchase.supplier.view",
    "accounting.journal.view",
    "accounting.report.view",
    "tax.period.view",
    "tax.period.prepare",
    "review.query.create",
    "finance.export.package",
}

# موظف عام (الدور الافتراضي للعضو الجديد): إدخال بيانات بلا ترحيل ولا حذف.
_STAFF = _VIEW_ONLY | _AFTERSALES_READ | {
    "hr.attendance.view",
    "sales.invoice.create",
    "sales.invoice.edit",
    "purchase.invoice.create",
    "purchase.invoice.edit",
    # استقبال الجهاز عند الكاونتر عملُ موظف — التعديل والحذف والتدقيق للمدير.
    "devices.registry.view",
    "devices.registry.create",
    # استقبال جهاز للصيانة عملُ كاونتر كذلك — بلا تعديل ولا ترحيل.
    "aftersales.order.create",
}

ROLE_DEFAULTS: dict[str, object] = {
    "manager": "*",
    "accountant": _ACCOUNTANT,
    "legal_accountant": _LEGAL_ACCOUNTANT,
    "sales": _SALES_EMPLOYEE,
    "procurement": _PROCUREMENT_EMPLOYEE,
    "staff": _STAFF,
    "viewer": _VIEW_ONLY,
}

# الأدوار المعروضة في شاشة الصلاحيات (المدير أولاً) وتسمياتها العربية.
ROLE_LABELS = (
    ("manager", "مدير"),
    ("accountant", "محاسب"),
    ("legal_accountant", "محاسب قانوني خارجي"),
    ("sales", "موظف مبيعات"),
    ("procurement", "موظف مشتريات"),
    ("staff", "موظف"),
    ("viewer", "مستعرض"),
)
ROLE_ORDER = tuple(r for r, _ in ROLE_LABELS)
ROLE_MODULES = {"legal_accountant": "accountant_portal"}


def permission_catalog(tenant=None) -> tuple[dict, ...]:
    """الكتالوج المرئي؛ تمرير شركة يزيل مفاتيح الوحدات غير المرخّصة."""
    if tenant is None:
        return tuple(PERMISSIONS)

    from core.modules import module_enabled

    return tuple(
        entry
        for entry in PERMISSIONS
        if not entry.get("module") or module_enabled(tenant, entry["module"])
    )


def permission_keys(tenant=None) -> frozenset:
    """كل مفاتيح الكتالوج المرئية للشركة، أو الكتالوج الكامل دون شركة."""
    return frozenset(p["key"] for p in permission_catalog(tenant))


def visible_role_labels(tenant=None) -> tuple[tuple[str, str], ...]:
    if tenant is None:
        return ROLE_LABELS

    from core.modules import module_enabled

    return tuple(
        (role, label)
        for role, label in ROLE_LABELS
        if role not in ROLE_MODULES or module_enabled(tenant, ROLE_MODULES[role])
    )


def role_default_permissions(role: str, tenant=None) -> frozenset:
    """صلاحيات الدور الافتراضية قبل تجاوزات الشركة."""
    granted = ROLE_DEFAULTS.get(role, _VIEW_ONLY)
    if granted == "*":
        return permission_keys(tenant)
    return frozenset(granted) & permission_keys(tenant)


def user_ui_mode(user, tenant) -> str:
    """THA-110: وضع عرض الواجهة لهذا المستخدم في هذه الشركة.

    تفضيل عرض لا صلاحية — يقلّم القائمة والنماذج ولا يحجب مساراً. غياب العضوية
    (سوبر أدمن، أو بلا سياق شركة) يعني «لا وضع محفوظاً» فيسقط على «متقدم»:
    الافتراضي هو التجربة الكاملة، والتبسيط اختيارٌ صريح.
    """
    from tenants.models import UserCompanyMembership

    default_mode = UserCompanyMembership._meta.get_field("ui_mode").default
    if tenant is None or user is None or not getattr(user, "is_authenticated", False):
        return default_mode

    membership = (
        UserCompanyMembership.objects
        .filter(user=user, tenant_id=getattr(tenant, "TenantID", tenant))
        .only("ui_mode")
        .first()
    )
    return membership.ui_mode if membership is not None else default_mode


def user_tenant_role(user, tenant) -> str:
    """دور المستخدم الفعلي داخل الشركة.

    العضوية هي المرجع؛ وإن غابت (تركيبات قديمة قبل نظام الشركات) نسقط على دور
    التطبيق من `core.user_roles` كي لا يفقد مالكٌ منفردٌ صلاحياته فجأة.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return "viewer"
    if getattr(user, "is_superuser", False):
        return "manager"

    if tenant is not None:
        from tenants.models import UserCompanyMembership

        tenant_id = getattr(tenant, "TenantID", tenant)
        membership = (
            UserCompanyMembership.objects
            .filter(user=user, tenant_id=tenant_id)
            .only("role")
            .first()
        )
        if membership is not None:
            # 'employee' القديم لم يكن ضمن أدوار العضوية — يُعامل موظفاً عامّاً.
            return "staff" if membership.role == "employee" else membership.role

    from core.user_roles import django_user_app_role

    legacy = django_user_app_role(user)
    if legacy in ROLE_DEFAULTS:
        return legacy
    return "manager" if legacy == "manager" else "staff"


def _apply(granted: set, overrides, valid: frozenset) -> None:
    """يطبّق تجاوزات (منح/منع) على مجموعة الصلاحيات، متجاهلاً المفاتيح المجهولة."""
    for o in overrides:
        if o.permission_key not in valid:
            continue
        if o.allowed:
            granted.add(o.permission_key)
        else:
            granted.discard(o.permission_key)


def user_permissions(user, tenant) -> frozenset:
    """الصلاحيات الفعلية = افتراضي الدور ← تجاوز الدور ← تجاوز العضو (الأعلى)."""
    role = user_tenant_role(user, tenant)
    granted = set(role_default_permissions(role, tenant))
    if role == "manager":
        # المدير مالك الشركة — لا يُقفل خارج نظامه بتجاوز، دوريّاً كان أو فردياً.
        return frozenset(granted)

    if tenant is not None:
        from tenants.models import MemberPermission, RolePermission

        tenant_id = getattr(tenant, "TenantID", tenant)
        valid = permission_keys(tenant)
        _apply(
            granted,
            RolePermission.objects.filter(tenant_id=tenant_id, role=role)
            .only("permission_key", "allowed"),
            valid,
        )
        _apply(
            granted,
            MemberPermission.objects.filter(
                membership__tenant_id=tenant_id, membership__user=user,
            ).only("permission_key", "allowed"),
            valid,
        )
    if role == "legal_accountant":
        from accountant_portal.permissions import is_legal_accountant_forbidden

        granted = {key for key in granted if not is_legal_accountant_forbidden(key)}
    return frozenset(granted)


def user_has_perm(user, tenant, key: str) -> bool:
    return key in user_permissions(user, tenant)


def require_perm(request, key: str, *, tenant=None) -> None:
    """يرفع 403 عربية إن لم يملك صاحب الطلب الصلاحية. يسجّل كل رفض."""
    if tenant is None:
        from core.tenant_utils import get_tenant

        tenant = get_tenant(request)
    user = getattr(request, "user", None)
    if user_has_perm(user, tenant, key):
        return
    role = user_tenant_role(user, tenant)
    logger.info(
        "perm_denied user=%s role=%s tenant=%s key=%s path=%s",
        getattr(user, "pk", None), role, getattr(tenant, "TenantID", tenant),
        key, getattr(request, "path", "?"),
    )
    label = next((p["label"] for p in PERMISSIONS if p["key"] == key), key)
    raise PermissionDenied(f"صلاحية «{label}» غير ممنوحة لدورك ({role}).")


def requires_perm(key: str):
    """مزيّن لإجراءات DRF: يفرض الصلاحية قبل تنفيذ الإجراء."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            require_perm(request, key)
            return func(self, request, *args, **kwargs)

        return wrapper

    return decorator
