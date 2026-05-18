from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from core.tenant_utils import get_tenant


class TenantQuerySetMixin:
    """Scopes get_queryset() to the current request's tenant.

    Returns queryset.none() when no tenant is resolvable so that data never
    leaks across companies.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if tenant:
            return qs.filter(tenant=tenant)
        return qs.none()


class TenantCreateMixin:
    """Injects the current request's tenant into perform_create().

    Raises a 400 ValidationError instead of silently falling back to
    tenant_id=1, so a missing tenant configuration fails loudly.
    """

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)


class BaseTenantViewSet(TenantQuerySetMixin, TenantCreateMixin, viewsets.ModelViewSet):
    """Convenience base combining tenant-scoped queryset and create."""
