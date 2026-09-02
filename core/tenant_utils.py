"""
Centralized tenant resolution for all API views.

Security: NEVER falls back to a random tenant. Each request MUST
explicitly provide X-Tenant-Id. If missing or invalid, the function
returns None (or raises) so the calling view can decide.

For single-tenant deployments, use the AUTO_SINGLE_TENANT setting
to automatically resolve when only one tenant exists in the DB.
"""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied

from tenants.models import Tenant

logger = logging.getLogger(__name__)

# Cache for single-tenant mode optimization (process-level)
_single_tenant_cache: Tenant | None = None
_single_tenant_checked: bool = False


def get_tenant(request=None, *, raise_on_missing: bool = False):
    global _single_tenant_cache, _single_tenant_checked

    if request is None:
        from core.logger_middleware import get_current_request
        request = get_current_request()

    # ── 1. Try explicit header ──
    if request is not None:
        tid = (
            request.headers.get('X-Tenant-Id')
            or request.META.get('HTTP_X_TENANT_ID')
        )
        if tid:
            cached_tenant = getattr(request, '_resolved_tenant', None)
            if (
                cached_tenant is not None
                and str(getattr(cached_tenant, 'TenantID', '')) == str(tid)
            ):
                return cached_tenant
            try:
                tenant = Tenant.objects.get(TenantID=int(tid))
                # Optional: validate user has access to this tenant
                _validate_user_tenant_access(request, tenant)
                request._resolved_tenant = tenant
                return tenant
            except Tenant.DoesNotExist:
                logger.warning(
                    "SECURITY: Invalid X-Tenant-Id=%s from user=%s IP=%s",
                    tid,
                    getattr(request, 'user', 'anonymous'),
                    _get_client_ip(request),
                )
                if raise_on_missing:
                    raise PermissionDenied(
                        f"الشركة (Tenant) المحددة غير موجودة: {tid}"
                    )
                return None
            except (ValueError, TypeError):
                logger.warning(
                    "SECURITY: Malformed X-Tenant-Id=%s from user=%s",
                    tid, getattr(request, 'user', 'anonymous'),
                )
                if raise_on_missing:
                    raise PermissionDenied("X-Tenant-Id غير صالح.")
                return None

    # ── 2. Try user's default tenant ──
    if request is not None and hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user
        # Check if user has a tenant_id attribute (via profile or direct field)
        user_tenant_id = getattr(user, 'tenant_id', None)
        if user_tenant_id:
            # P2-2 (SCALABILITY_AUDIT §1.5): مسار الترويسة أعلاه يحفظ النتيجة على
            # الطلب (`_resolved_tenant`) فلا يتكرّر استعلامه، أما هذا المسار فكان
            # يعيد `Tenant.objects.get` من الصفر عند **كل** استدعاء لـget_tenant —
            # والطلب الواحد يستدعيها مرات (viewset + serializer + services).
            cached_tenant = getattr(request, '_resolved_tenant', None)
            if (
                cached_tenant is not None
                and str(getattr(cached_tenant, 'TenantID', '')) == str(user_tenant_id)
            ):
                return cached_tenant
            try:
                tenant = Tenant.objects.get(TenantID=int(user_tenant_id))
                _validate_user_tenant_access(request, tenant)
                request._resolved_tenant = tenant
                return tenant
            except (Tenant.DoesNotExist, ValueError, TypeError):
                pass

    # ── 3. Single-tenant auto-resolve ──
    # If there's exactly ONE tenant in the entire DB, use it automatically.
    # This preserves backward compatibility for single-tenant deployments.
    if not _single_tenant_checked:
        count = Tenant.objects.count()
        if count == 1:
            _single_tenant_cache = Tenant.objects.first()
        _single_tenant_checked = True

    if _single_tenant_cache is not None:
        # Re-verify it's still the only one (invalidate cache if more were added).
        # P2-2 (SCALABILITY_AUDIT §1.5): هذا العدّ كان يُنفَّذ على **كل** طلب في
        # النشر أحادي الشركة (الحالة الشائعة) — استعلام كامل على جدول الشركات
        # لمجرد تأكيد ما لا يتغيّر إلا عند إنشاء شركة. الآن يُعاد التحقق مرة لكل
        # طلب لا مرة لكل استدعاء، وإنشاء الشركة الثانية يبطل الكاش في الطلب التالي.
        recheck_done = getattr(request, '_single_tenant_rechecked', False) if request is not None else False
        if recheck_done or Tenant.objects.count() == 1:
            if request is not None:
                request._single_tenant_rechecked = True
                _validate_user_tenant_access(request, _single_tenant_cache)
            return _single_tenant_cache
        else:
            # Multiple tenants now exist — disable auto-resolve
            _single_tenant_cache = None

    # ── 4. No tenant resolved ──
    logger.warning(
        "SECURITY: No tenant resolved for request. user=%s path=%s",
        getattr(request, 'user', 'anonymous') if request else 'no-request',
        request.path if request else 'N/A',
    )
    if raise_on_missing:
        raise PermissionDenied(
            "لم يتم تحديد الشركة. أرسل X-Tenant-Id في الهيدر."
        )
    return None


def _validate_user_tenant_access(request, tenant: Tenant) -> None:
    """
    Validates that the authenticated user has access to the requested tenant
    using the UserCompanyMembership model. Superusers bypass this check.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return

    user = request.user
    if user.is_superuser:
        return

    from tenants.models import UserCompanyMembership
    membership = (
        UserCompanyMembership.objects
        .filter(user=user, tenant=tenant)
        .only('role')
        .first()
    )
    if membership is None:
        # ISSUE #52 (قرار 7): مدير المكتب يصل كل دفاتر مكتبه المُدارة بلا صفّ
        # عضويةٍ لكل دفتر — وإلا صار الدفتر ظاهراً في `TenantViewSet` (الذي
        # يمنحه الرؤية) وممنوعاً هنا، فيرى المدير دفتراً لا يستطيع فتحه.
        # موظفٌ غير مُسنَد لا يمرّ: الشرط `role="manager"` على المكتب نفسه.
        office_id = getattr(tenant, 'managed_by_id', None)
        if office_id is not None and UserCompanyMembership.objects.filter(
            user=user, tenant_id=office_id, role='manager',
        ).exists():
            return
        logger.error(
            "SECURITY ALERT: User %s attempted to access unauthorized tenant=%s. IP=%s",
            user, tenant.TenantID,
            _get_client_ip(request),
        )
        raise PermissionDenied("ليس لديك صلاحية الوصول لهذه الشركة.")

    if membership.role == 'legal_accountant':
        from accountant_portal.models import AccountantEngagement
        from accountant_portal.permissions import EngagementInactive
        from core.modules import module_enabled

        has_active_engagement = module_enabled(
            tenant,
            'accountant_portal',
        ) and AccountantEngagement.objects.filter(
            accountant=user,
            tenant=tenant,
            status='active',
        ).exists()
        if not has_active_engagement:
            logger.info(
                "inactive_accountant_engagement user=%s tenant=%s",
                user.pk,
                tenant.TenantID,
            )
            raise EngagementInactive("ارتباط المحاسب بهذه الشركة غير نشط.")

    request._tenant_membership_role = (tenant.pk, membership.role)

    # شركة أوقفتها إدارة المنصة — الإيقاف حالة نافذة لا وسماً في اللوحة.
    # السوبر أدمن يبقى قادراً على الدخول ليصلح/يعيد التفعيل.
    if (tenant.Status or '').strip().lower() == 'suspended':
        from core.import_access import is_super_admin
        if not is_super_admin(user):
            logger.warning(
                "tenant %s is suspended — access denied for user=%s", tenant.TenantID, user)
            raise PermissionDenied(
                "هذه الشركة موقوفة من إدارة المنصة. تواصل مع الدعم لإعادة تفعيلها."
            )


def _get_client_ip(request) -> str:
    """Extract client IP for security logging."""
    if request is None:
        return 'unknown'
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def get_branch(request, tenant=None):
    """task11 M4 — يحل الفرع النشط من X-Branch-Id.

    يرجع None إذا لم يُرسل الهيدر أو كانت قيمته 0/فارغة (= كل الفروع /
    مستوى الشركة). يرفض PermissionDenied إذا كان الفرع تابعاً لشركة أخرى.
    """
    if request is None:
        return None
    bid = request.headers.get('X-Branch-Id') or request.META.get('HTTP_X_BRANCH_ID')
    if not bid or str(bid).strip() in ('0', 'all', 'null'):
        return None
    try:
        bid_int = int(bid)
    except (ValueError, TypeError):
        logger.warning("SECURITY: Malformed X-Branch-Id=%s", bid)
        return None

    from tenants.models import Branch
    branch = Branch.objects.filter(pk=bid_int).select_related('tenant').first()
    if branch is None:
        logger.warning("X-Branch-Id=%s not found", bid_int)
        return None

    if tenant is None:
        tenant = get_tenant(request)
    if tenant is not None and branch.tenant_id != tenant.pk:
        logger.error(
            "SECURITY ALERT: branch %s belongs to tenant %s, not active tenant %s (user=%s)",
            branch.pk, branch.tenant_id, tenant.pk, getattr(request, 'user', '?'),
        )
        raise PermissionDenied("الفرع المحدد لا يتبع الشركة النشطة.")
    return branch


def invalidate_tenant_cache():
    """Call this when tenants are created/deleted to reset the cache."""
    global _single_tenant_cache, _single_tenant_checked
    _single_tenant_cache = None
    _single_tenant_checked = False
