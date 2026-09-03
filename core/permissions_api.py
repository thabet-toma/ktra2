"""T-PERM — واجهة الصلاحيات.

    GET  /api/permissions/me/            صلاحياتي الفعلية (تغذّي إخفاء الأزرار)
    GET  /api/permissions/matrix/        الكتالوج + مصفوفة الأدوار (مدير فقط)
    PUT  /api/permissions/matrix/        حفظ تجاوزات الشركة (مدير فقط)
    POST /api/permissions/matrix/reset/  استعادة الافتراضي (حذف التجاوزات)

الحقيقة الوحيدة للمنطق في `core.access` — هذه الطبقة نقلٌ فقط.
"""
import logging

from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.access import (
    permission_catalog,
    permission_keys,
    require_perm,
    role_default_permissions,
    user_permissions,
    user_tenant_role,
    user_ui_mode,
    visible_role_labels,
)
from core.modules import MODULES, module_enabled
from core.tenant_utils import get_tenant
from core.terminology import terms_payload
from tenants.company_templates import DEFAULT_TEMPLATE

logger = logging.getLogger(__name__)


def _effective_matrix(tenant) -> dict:
    """مصفوفة {دور: {مفتاح: مسموح}} بعد تطبيق تجاوزات الشركة."""
    from tenants.models import RolePermission

    overrides: dict[tuple, bool] = {}
    if tenant is not None:
        for o in RolePermission.objects.filter(tenant=tenant).only(
            "role", "permission_key", "allowed"
        ):
            overrides[(o.role, o.permission_key)] = o.allowed

    matrix: dict[str, dict] = {}
    roles = tuple(role for role, _ in visible_role_labels(tenant))
    valid_keys = permission_keys(tenant)
    for role in roles:
        defaults = role_default_permissions(role, tenant)
        row = {}
        for key in valid_keys:
            if role == "manager":
                row[key] = True  # المدير لا يُجرَّد (يطابق core.access)
            else:
                row[key] = overrides.get((role, key), key in defaults)
        matrix[role] = row
    return matrix


def _matrix_payload(tenant) -> dict:
    roles = visible_role_labels(tenant)
    return {
        "roles": [{"key": r, "label": label} for r, label in roles],
        "permissions": permission_catalog(tenant),
        "defaults": {r: sorted(role_default_permissions(r, tenant)) for r, _ in roles},
        "matrix": _effective_matrix(tenant),
    }


@api_view(["GET"])
def my_permissions(request):
    """صلاحيات المستخدم الحالي في الشركة النشطة — للعرض فقط، الإنفاذ خادمي."""
    tenant = get_tenant(request)
    role = user_tenant_role(request.user, tenant)
    return Response({
        "role": role,
        "is_manager": role == "manager",
        "permissions": sorted(user_permissions(request.user, tenant)),
        # حقل واحد يخدم كل الوحدات — الواجهة تحرس شاشاتها به قبل أي import().
        "modules": {key: module_enabled(tenant, key) for key in MODULES},
        # ISSUE #51: القناع الحيّ — الواجهة تحرس شاشاتها به عبر
        # `TEMPLATE_HIDDEN_VIEWS` (`frontend_v2/utils/viewPermissions.ts`)،
        # والخادم يفرضه فعلياً على المسارات (`core.permissions.TemplateSurfacePermission`).
        "template": getattr(tenant, "template", DEFAULT_TEMPLATE),
        # THA-110: وضع العرض يركب هذه الحمولة نفسها (تُحمَّل عند الإقلاع) فلا
        # يكلّف طلباً شبكياً إضافياً. عرضٌ فقط — لا يحجب مساراً ولا يمنح صلاحية.
        "ui_mode": user_ui_mode(request.user, tenant),
        # ISSUE #82: المعجم — نقطة التسليم الوحيدة (القرار 8 في #46: لا آلية
        # ثالثة). قاموسٌ مسطّح بمفاتيح مصطلحات (`doc.*`، `line.*`)، والواجهة
        # تقرأه بـ`term(key)` بدل كتابة الاسم حرفياً في كل شاشة.
        "terms": terms_payload(tenant),
    })


@api_view(["GET"])
def permission_roles(request):
    """الأدوار المتاحة للشركة بعد إخفاء أدوار الوحدات غير المرخّصة."""
    tenant = get_tenant(request)
    return Response([
        {"key": role, "label": label}
        for role, label in visible_role_labels(tenant)
    ])


@api_view(["GET", "PUT", "PATCH"])
@transaction.atomic
def permissions_matrix(request):
    """قراءة/تحرير مصفوفة الصلاحيات لهذه الشركة — يتطلب admin.permissions.manage."""
    tenant = get_tenant(request)
    require_perm(request, "admin.permissions.manage", tenant=tenant)
    if request.method == "GET":
        return Response(_matrix_payload(tenant))

    from tenants.models import RolePermission, UserCompanyMembership

    if tenant is None:
        raise DRFValidationError({"detail": "لا يوجد شركة (tenant)."})
    changes = request.data.get("changes")
    if not isinstance(changes, list):
        raise DRFValidationError({"changes": "قائمة التغييرات مطلوبة."})

    valid_keys = permission_keys(tenant)
    valid_roles = {r for r, _ in UserCompanyMembership.ROLE_CHOICES}
    for ch in changes:
        role = str((ch or {}).get("role") or "").strip()
        key = str((ch or {}).get("permission_key") or "").strip()
        if role not in valid_roles:
            raise DRFValidationError({"role": f"دور غير صالح: {role}"})
        if key not in valid_keys:
            raise DRFValidationError({"permission_key": f"صلاحية غير معروفة: {key}"})
        if role == "manager":
            raise DRFValidationError(
                {"role": "لا يمكن تعديل صلاحيات المدير — مالك الشركة يملك كل شيء."}
            )
        from accountant_portal.permissions import reject_forbidden_accountant_permission

        if bool(ch.get("allowed")):
            reject_forbidden_accountant_permission(role, key)
        allowed = bool(ch.get("allowed"))
        default_allowed = key in role_default_permissions(role, tenant)
        if allowed == default_allowed:
            # العودة للافتراضي = حذف التجاوز (لا نُخزّن ما يساوي الافتراضي).
            RolePermission.objects.filter(
                tenant=tenant, role=role, permission_key=key).delete()
        else:
            RolePermission.objects.update_or_create(
                tenant=tenant, role=role, permission_key=key,
                defaults={"allowed": allowed},
            )
    logger.info(
        "permissions_matrix updated tenant=%s by_user=%s changes=%s",
        tenant.TenantID, getattr(request.user, "pk", None), len(changes),
    )
    return Response(_matrix_payload(tenant))


def _member_payload(membership) -> dict:
    """صورة العضو في شاشة الصلاحيات: دوره + تجاوزاته الفردية + صلاحياته الفعلية."""
    from tenants.models import MemberPermission

    overrides = {
        o.permission_key: o.allowed
        for o in MemberPermission.objects.filter(membership=membership)
        .only("permission_key", "allowed")
        if o.permission_key in permission_keys(membership.tenant)
    }
    user = membership.user
    effective = user_permissions(user, membership.tenant)
    return {
        "membership_id": membership.id,
        "user_id": membership.user_id,
        "name": (f"{user.first_name} {user.last_name}").strip() or user.username,
        "email": user.email or "",
        "role": membership.role,
        "overrides": overrides,
        "effective": sorted(effective),
        # T-PERMBOX: خانة «كل الصلاحيات» — مشتقّة لا مخزَّنة، فلا تكذب إن تغيّر
        # الكتالوج أو نُزعت صلاحية واحدة بعد المنح الشامل.
        "grant_all": permission_keys(membership.tenant) <= effective,
    }


@api_view(["GET"])
def permission_members(request):
    """أعضاء الشركة وصلاحياتهم الفعلية — لتبويب «حسب الموظف» (مدير فقط)."""
    tenant = get_tenant(request)
    require_perm(request, "admin.permissions.manage", tenant=tenant)
    from tenants.models import UserCompanyMembership

    rows = (
        UserCompanyMembership.objects.filter(tenant=tenant)
        .select_related("user", "tenant")
        .order_by("role", "id")
    )
    return Response([_member_payload(m) for m in rows])


@api_view(["PUT", "PATCH"])
@transaction.atomic
def member_permissions(request):
    """تجاوز فردي فوق الدور.

    body: {"membership_id": n, "changes": [{"permission_key": k, "allowed": true|false|null}]}
    `allowed=null` يحذف التجاوز فيعود العضو لما يمليه دوره.

    أو: {"membership_id": n, "grant_all": true|false} — منح شامل لهذا العضو
    (true) أو إعادته لما يمليه دوره بحذف كل تجاوزاته (false). وجود `grant_all`
    يحكم الطلب وحده، فلا يُخلط مع `changes` في نداء واحد.
    """
    tenant = get_tenant(request)
    require_perm(request, "admin.permissions.manage", tenant=tenant)
    from tenants.models import MemberPermission, UserCompanyMembership

    try:
        mid = int(request.data.get("membership_id"))
    except (TypeError, ValueError):
        raise DRFValidationError({"membership_id": "membership_id مطلوب."})
    membership = (
        UserCompanyMembership.objects.filter(id=mid, tenant=tenant)
        .select_related("user", "tenant").first()
    )
    if membership is None:
        raise DRFValidationError({"membership_id": "العضوية غير موجودة في هذه الشركة."})
    if membership.role == "manager":
        raise DRFValidationError(
            {"membership_id": "لا تُعدَّل صلاحيات المدير — مالك الشركة يملك كل شيء."}
        )

    valid_keys = permission_keys(tenant)
    grant_all = request.data.get("grant_all")
    if grant_all is not None:
        if grant_all:
            from accountant_portal.permissions import reject_forbidden_accountant_permission

            for key in valid_keys:
                reject_forbidden_accountant_permission(membership.role, key)
            # منحٌ صريح لكل مفتاح — لا اعتماد على دوره، فيبقى شاملاً ولو تبدّل.
            for key in sorted(valid_keys):
                MemberPermission.objects.update_or_create(
                    membership=membership, permission_key=key,
                    defaults={"allowed": True},
                )
        else:
            MemberPermission.objects.filter(membership=membership).delete()
        logger.info(
            "member_permissions grant_all=%s tenant=%s membership=%s by_user=%s",
            bool(grant_all), getattr(tenant, "TenantID", None), membership.id,
            getattr(request.user, "pk", None),
        )
        return Response(_member_payload(membership))

    changes = request.data.get("changes")
    if not isinstance(changes, list):
        raise DRFValidationError({"changes": "قائمة التغييرات مطلوبة."})
    for ch in changes:
        key = str((ch or {}).get("permission_key") or "").strip()
        if key not in valid_keys:
            raise DRFValidationError({"permission_key": f"صلاحية غير معروفة: {key}"})
        allowed = (ch or {}).get("allowed")
        if allowed:
            from accountant_portal.permissions import reject_forbidden_accountant_permission

            reject_forbidden_accountant_permission(membership.role, key)
        if allowed is None:
            MemberPermission.objects.filter(
                membership=membership, permission_key=key).delete()
        else:
            MemberPermission.objects.update_or_create(
                membership=membership, permission_key=key,
                defaults={"allowed": bool(allowed)},
            )
    logger.info(
        "member_permissions updated tenant=%s membership=%s by_user=%s changes=%s",
        getattr(tenant, "TenantID", None), membership.id,
        getattr(request.user, "pk", None), len(changes),
    )
    return Response(_member_payload(membership))


@api_view(["POST"])
def reset_permissions_matrix(request):
    """استعادة الافتراضي — حذف كل تجاوزات الشركة."""
    tenant = get_tenant(request)
    require_perm(request, "admin.permissions.manage", tenant=tenant)
    from tenants.models import RolePermission

    deleted, _ = RolePermission.objects.filter(tenant=tenant).delete()
    logger.info(
        "permissions_matrix reset tenant=%s by_user=%s removed=%s",
        getattr(tenant, "TenantID", None), getattr(request.user, "pk", None), deleted,
    )
    return Response(_matrix_payload(tenant))
