"""يُعيد تصدير الخانق المشترك من `core.throttles` (K3).

كان الصنف يعيش هنا، وانتقل إلى `core` لأن `employee_ops` وحدةٌ معزولة لا يجوز
أن يستوردها `docshare` — وسطحُ عدّ الجرد يحتاج القاعدة نفسها. إعادةُ التصدير
تُبقي كلّ مستوردٍ قائمٍ (`from .throttles import ClientIpScopedThrottle`) كما هو.
"""
from core.throttles import ClientIpScopedThrottle  # noqa: F401
