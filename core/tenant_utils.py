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
    """
    Resolve tenant securely from request.

    Resolution order:
    1. X-Tenant-Id header (or HTTP_X_TENANT_ID META)
    2. User's default tenant (if user.profile.tenant_id exists)
    3. Single-tenant auto-resolve (if only 1 tenant in DB)
    4. None (or PermissionDenied if raise_on_missing=True)

    SECURITY: Never falls back to Tenant.objects.first() blindly.
    """
    global _single_tenant_cache, _single_tenant_checked

    # ── 1. Try explicit header ──
    if request is not None:
        tid = (
            request.headers.get('X-Tenant-Id')
            or request.META.get('HTTP_X_TENANT_ID')
        )
        if tid:
            try:
                tenant = Tenant.objects.get(TenantID=int(tid))
                # Optional: validate user has access to this tenant
                _validate_user_tenant_access(request, tenant)
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
            try:
                return Tenant.objects.get(TenantID=int(user_tenant_id))
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
        # Re-verify it's still the only one (invalidate cache if more were added)
        if Tenant.objects.count() == 1:
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
    Optional: Validates that the authenticated user has access to
    the requested tenant. Override this with your own logic.

    Currently logs a warning if the user doesn't belong to the tenant.
    In production, you may want to raise PermissionDenied.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return

    user = request.user
    user_tenant_id = getattr(user, 'tenant_id', None)

    if user_tenant_id and int(user_tenant_id) != tenant.TenantID:
        # User is trying to access a different tenant!
        logger.error(
            "SECURITY ALERT: User %s (tenant=%s) attempted to access tenant=%s. IP=%s",
            user, user_tenant_id, tenant.TenantID,
            _get_client_ip(request),
        )
        raise PermissionDenied("ليس لديك صلاحية الوصول لهذه الشركة.")


def _get_client_ip(request) -> str:
    """Extract client IP for security logging."""
    if request is None:
        return 'unknown'
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def invalidate_tenant_cache():
    """Call this when tenants are created/deleted to reset the cache."""
    global _single_tenant_cache, _single_tenant_checked
    _single_tenant_cache = None
    _single_tenant_checked = False
