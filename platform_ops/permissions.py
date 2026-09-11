"""صلاحيات عمليات المنصة."""
from rest_framework.permissions import BasePermission

from core.platform_admin_api import IsPlatformAdmin

from .services import is_platform_employee


class IsPlatformOperationsManager(BasePermission):
    """مدير عمليات المنصة / السوبر أدمن — تحكم كامل في الموظفين والاشتراكات."""

    message = "هذه المساحة متاحة لمدير عمليات المنصة فقط."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return IsPlatformAdmin().has_permission(request, view)


class IsPlatformOperationsStaff(BasePermission):
    """موظف عمليات المنصة — يرى ويتابع أعماله المسندة إليه.

    قاعدة صارمة: موظف المنصة لا يُمنح IsPlatformAdmin؛ فهو موظف تشغيل لا مالك منصة.
    تتحقق الصلاحية بوجود صف PlatformEmployee بحالة نشطة دون اشتراط أن يكون سوبر أدمن.
    """

    message = "هذه المساحة متاحة لموظفي عمليات المنصة فقط."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return is_platform_employee(user)


class IsPlatformRecruiter(BasePermission):
    """صلاحيةُ مسؤول التوظيف المنصّيّ — **أو** السوبر أدمن.

    القاعدةُ في اتّجاهٍ واحد: الدورُ يفتح التوظيفَ وحدَه ولا يمنح شيئاً من بقيّة
    المنصّة — لا لوحةَ العمليات ولا أوامرَ العمل ولا الاشتراكاتِ ولا المفاتيح.
    والسوبر أدمن يمرّ هنا كما يمرّ في كلّ مكان، فالبوّابةُ عليه أوسعُ لا أضيق.
    يحرس الاتّجاهَ اختباران: `test_recruiter_permission_isolation_and_operations_block`
    و`PlatformRecruiterRouteScopeTest.test_a_platform_recruiter_reaches_the_hiring_routes_and_nothing_else`
    الذي يعدّ **كلّ** مسارات `/api/platform/` فلا تنفتح نقطةٌ جديدةٌ له سهواً.
    """

    message = "هذه المساحة متاحة لمسؤولي توظيف المنصة أو مديريها فقط."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        from .services import is_platform_recruiter
        return bool(IsPlatformAdmin().has_permission(request, view) or is_platform_recruiter(user))

