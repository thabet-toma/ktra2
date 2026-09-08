"""خدمات متابعة الموظفين (المرحلة الأولى: الأساس)."""
from .models import EmployeeOpsSettings

MODULE_KEY = "employee_ops"


def settings_for_read(tenant) -> EmployeeOpsSettings:
    """إعدادات الشركة للعرض — **بلا كتابة**.

    الشركة التي لم تضبط شيئاً تُعاد بصفٍّ غير محفوظ يحمل الافتراضيات. طلبُ `GET`
    الذي يكتب صفّاً عطلٌ لا تحسينٌ: يعطّل القراءة من نسخةٍ قرائية، ويترك أثراً
    لمن نظر ولم يغيّر شيئاً.
    """
    tenant_id = getattr(tenant, "pk", tenant)
    existing = EmployeeOpsSettings.objects.filter(tenant_id=tenant_id).first()
    return existing if existing is not None else EmployeeOpsSettings(tenant_id=tenant_id)


def get_or_create_settings(tenant) -> EmployeeOpsSettings:
    """إعدادات الشركة للكتابة — تُنشأ بالافتراضيات إن لم تكن.

    يقبل كائن الشركة أو معرّفها — كما يفعل `core.modules._tenant_id`.
    """
    tenant_id = getattr(tenant, "pk", tenant)
    settings_obj, _ = EmployeeOpsSettings.objects.get_or_create(tenant_id=tenant_id)
    return settings_obj
