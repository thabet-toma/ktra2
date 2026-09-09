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
