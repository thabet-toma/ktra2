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
        if request.method in SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            # المصادقة نفسها مسؤولية IsAuthenticated — لا نكررها هنا
            return True
        if user.is_superuser:
            return True

        from core.tenant_utils import get_tenant
        # get_tenant يرفع PermissionDenied لغير الأعضاء — يصل 403 من هناك
        tenant = get_tenant(request)
        if tenant is None:
            return True  # بلا سياق شركة — فحوصات أخرى تتكفل

        from tenants.models import UserCompanyMembership
        membership = (
            UserCompanyMembership.objects
            .filter(user=user, tenant=tenant)
            .only("role")
            .first()
        )
        if membership is None:
            return True  # superuser بلا عضوية أو سياق خاص — العضوية مفروضة في get_tenant
        return membership.role != "viewer"
