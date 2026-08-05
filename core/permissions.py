"""task11 R2-B — فرض أدوار العضوية على مستوى المنصة.

الأدوار (UserCompanyMembership.role) كانت موجودة منذ task10 لكنها لم تُفرض
في أي endpoint عمليات — «مستعرض» كان يستطيع ترحيل قيود وحذف مسودات وتعديل
إعدادات. هذه الطبقة تفرض الحد الأدنى الواضح:

    viewer  → قراءة فقط (GET/HEAD/OPTIONS)
    غيره    → حسب فحوصات كل endpoint (manager-only تبقى في مكانها)

تُطبَّق افتراضياً عبر ApiAuthAndUser وعبر DEFAULT_PERMISSION_CLASSES.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class TenantRolePermission(BasePermission):
    message = "صلاحيتك في هذه الشركة «مستعرض» — قراءة فقط."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            # المصادقة نفسها مسؤولية IsAuthenticated — لا نكررها هنا
            return True
        if user.is_superuser:
            return True

        from accountant_portal.permissions import is_restricted_accountant_route

        restricted_route = is_restricted_accountant_route(request.path)
        legal_office_bootstrap = (
            request.method == "POST"
            and request.path.rstrip("/") == "/api/tenants/companies"
        )
        if request.method in SAFE_METHODS and not restricted_route:
            return True

        from core.tenant_utils import get_tenant
        # get_tenant يرفع PermissionDenied لغير الأعضاء — يصل 403 من هناك
        tenant = get_tenant(request)
        from tenants.models import UserCompanyMembership

        if tenant is None:
            has_legal_membership = UserCompanyMembership.objects.filter(
                user=user,
                role="legal_accountant",
            ).exists()
            if has_legal_membership and (
                restricted_route
                or (
                    request.method not in SAFE_METHODS
                    and not request.path.startswith("/api/accountant/")
                    and not legal_office_bootstrap
                )
            ):
                self.message = "يلزم سياق شركة صالح للمحاسب القانوني الخارجي."
                return False
            return True  # بلا سياق شركة — فحوصات أخرى تتكفل

        cached_role = getattr(request, "_tenant_membership_role", None)
        if cached_role and cached_role[0] == tenant.pk:
            role = cached_role[1]
        else:
            membership = (
                UserCompanyMembership.objects
                .filter(user=user, tenant=tenant)
                .only("role")
                .first()
            )
            role = membership.role if membership is not None else None
        if role is None:
            return True  # superuser بلا عضوية أو سياق خاص — العضوية مفروضة في get_tenant
        if role == "legal_accountant" and restricted_route:
            self.message = "هذا المسار التشغيلي غير متاح للمحاسب القانوني الخارجي."
            return False
        if (
            role == "legal_accountant"
            and request.method not in SAFE_METHODS
            and not request.path.startswith("/api/accountant/")
            and not legal_office_bootstrap
        ):
            self.message = "الكتابة التشغيلية متاحة للمحاسب من بوابة المراجعة فقط."
            return False
        if request.method in SAFE_METHODS:
            return True
        return role != "viewer"
