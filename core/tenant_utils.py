"""
Centralized tenant resolution for all API views.
Checks X-Tenant-Id header first, falls back to first tenant.
"""
from tenants.models import Tenant


def get_tenant(request=None):
    """
    Resolve tenant from request header or fall back to first tenant.
    Safe for single-tenant deployments; ready for multi-tenant.
    """
    if request is not None:
        tid = (
            request.headers.get('X-Tenant-Id')
            or request.META.get('HTTP_X_TENANT_ID')
        )
        if tid:
            try:
                return Tenant.objects.get(TenantID=int(tid))
            except (Tenant.DoesNotExist, ValueError, TypeError):
                pass
    return Tenant.objects.first()
