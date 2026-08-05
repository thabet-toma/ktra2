from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission


class EngagementInactive(PermissionDenied):
    """ارتباط المحاسب بهذه الشركة ليس نشطاً — الواجهة تلتقط الرمز فتعيده للوحة."""

    code = "engagement_inactive"


LEGAL_ACCOUNTANT_FORBIDDEN = frozenset(
    {
        "admin.members.manage",
        "admin.permissions.manage",
        "admin.settings.manage",
        "tax.integration.manage",
        "inventory.doc.post",
        "inventory.doc.unpost",
        "inventory.item.manage",
        "import.*",
        "hr.*",
        "sales.invoice.delete",
        "purchase.invoice.delete",
    }
)


def is_legal_accountant_forbidden(permission_key: str) -> bool:
    return permission_key in LEGAL_ACCOUNTANT_FORBIDDEN or any(
        wildcard.endswith(".*") and permission_key.startswith(wildcard[:-1])
        for wildcard in LEGAL_ACCOUNTANT_FORBIDDEN
    )


class ForbiddenAccountantPermission(APIException):
    status_code = 422
    default_code = "forbidden_permission_key"
    default_detail = "لا يمكن منح هذه الصلاحية للمحاسب القانوني الخارجي."


def reject_forbidden_accountant_permission(role: str, permission_key: str) -> None:
    if role == "legal_accountant" and is_legal_accountant_forbidden(permission_key):
        raise ForbiddenAccountantPermission()


_RESTRICTED_ROUTE_PREFIXES = (
    "/api/inventory/",
    "/api/hr/",
    "/api/logistics/",
)


def is_restricted_accountant_route(path: str) -> bool:
    if path.startswith("/api/hr/auth/"):
        return False
    return path.startswith(_RESTRICTED_ROUTE_PREFIXES)


class LegalAccountantRoutePermission(BasePermission):
    message = "هذا المسار التشغيلي غير متاح للمحاسب القانوني الخارجي."

    def has_permission(self, request, view):
        if not is_restricted_accountant_route(request.path):
            return True
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return True

        from core.access import user_tenant_role
        from core.tenant_utils import get_tenant

        tenant = get_tenant(request)
        if tenant is not None:
            return user_tenant_role(user, tenant) != "legal_accountant"

        from tenants.models import UserCompanyMembership

        return not UserCompanyMembership.objects.filter(
            user=user,
            role="legal_accountant",
        ).exists()
