"""صلاحية وحدة الاستيراد — نموذج من مستويين.

السوبر أدمن (البريد في SUPER_ADMIN_EMAILS أو is_superuser) يقرر أي شركة تملك
الاستيراد عبر Tenant.import_enabled. مدير الشركة يقرر أي عضو داخلها يحصل على
الصلاحية عبر UserCompanyMembership.can_access_import.

الوصول الفعلي = سوبر أدمن، أو (الشركة مفعّلة وَ (المستخدم مدير أو ممنوح)).

الإنفاذ الموثوق على الخادم لكل شركة نشطة؛ أعلام الواجهة (canAccessImport) للعرض
فقط (إخفاء القائمة وقسم تكاليف الاستيراد).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# مالك المنصة — السوبر أدمن الافتراضي. يمكن توسيعه عبر settings.SUPER_ADMIN_EMAILS.
DEFAULT_SUPER_ADMIN_EMAILS = {"thapet64@gmail.com"}


def super_admin_emails() -> set:
    extra = getattr(settings, "SUPER_ADMIN_EMAILS", None) or []
    if isinstance(extra, str):
        extra = [extra]
    return {e.strip().lower() for e in (list(DEFAULT_SUPER_ADMIN_EMAILS) + list(extra)) if e}


def is_super_admin(user) -> bool:
    """سوبر أدمن المنصة: is_superuser أو بريده ضمن قائمة السوبر أدمن."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    email = (getattr(user, "email", "") or "").strip().lower()
    return bool(email) and email in super_admin_emails()


def user_can_access_import(user, tenant) -> bool:
    """الوصول الفعلي لوحدة الاستيراد ضمن شركة بعينها.

    تفعيل الشركة شرطٌ للجميع (حتى السوبر أدمن) — وحدة الاستيراد قدرة على مستوى
    الشركة؛ من لا شركةَ مفعّلةً له لا يرى الاستيراد. صلاحية السوبر أدمن هي
    «تفعيل» الشركة (عبر set-import-enabled) ثم يحصل على الوصول تلقائياً.
    """
    if tenant is None or not getattr(tenant, "import_enabled", False):
        return False
    if is_super_admin(user):
        return True
    from tenants.models import UserCompanyMembership

    m = (
        UserCompanyMembership.objects
        .filter(user=user, tenant=tenant)
        .only("role", "can_access_import")
        .first()
    )
    if m is None:
        return False
    if m.role == "manager":
        return True
    return bool(m.can_access_import)
