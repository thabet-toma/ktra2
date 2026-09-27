"""سجلّ تدقيق المنصة — نقطة الكتابة الوحيدة إلى `PlatformAuditLog`.

كل فعلٍ إداريٍّ للسوبر أدمن وكل حدثٍ أمنيٍّ عابرٍ للشركات يمرّ من
`record_platform_event`. الكتابة **حاظرة** عمداً في الأفعال الإدارية: تُنادى
داخل معاملة الفعل نفسه، فإن فشل التسجيل فشل الفعل — فعلٌ إداريٌّ بلا أثر هو
بالضبط ما يُبنى هذا السجلّ لمنعه. الاستثناء `record_platform_event_safely`
لمسارات لا يجوز أن تسقط بسبب السجلّ (تسجيل الدخول).
"""
import logging

from core.activity import _client_ip
from core.logger_middleware import get_current_trace_id
from core.models import PlatformAuditLog

logger = logging.getLogger(__name__)

# الأحداث المعروفة وخطورتها الافتراضية. المفتاح هو ما يُفلتَر به في اللوحة،
# والتسمية ما يقرؤه المالك — مصدرٌ واحد للاثنين.
PLATFORM_EVENTS = {
    'SUPER_ADMIN_GRANTED': ('high', 'منح صلاحية سوبر أدمن'),
    'SUPER_ADMIN_REVOKED': ('high', 'سحب صلاحية سوبر أدمن'),
    'USER_ACTIVE_CHANGED': ('warning', 'إيقاف/تفعيل حساب مستخدم'),
    'COMPANY_CREATED': ('warning', 'إنشاء شركة لعميل'),
    'COMPANY_UPDATED': ('info', 'تعديل بيانات شركة'),
    'COMPANY_STATUS_CHANGED': ('warning', 'تغيير حالة شركة'),
    'COMPANY_PLAN_CHANGED': ('info', 'تغيير خطة شركة'),
    'MODULE_TOGGLED': ('info', 'تفعيل/تعطيل وحدة'),
    'LIMIT_CHANGED': ('info', 'تعديل حدّ من حدود الخطة'),
    'PLAN_PRICE_CHANGED': ('warning', 'تعديل سعر خطة'),
    'MEMBER_ADDED': ('warning', 'إضافة عضو إلى شركة'),
    'MEMBER_REMOVED': ('warning', 'إخراج عضو من شركة'),
    'MEMBER_UPDATED': ('warning', 'تعديل عضوية'),
    'ACCOUNTANT_VERIFIED': ('info', 'قرار توثيق محاسب'),
    'ACCOUNTANT_WORKSPACE_OPENED': ('info', 'فتح واجهة المحاسب'),
    'LOGIN_FAILED': ('warning', 'محاولة دخول فاشلة'),
    'SUPPORT_ACCESS_REQUESTED': ('info', 'طلب إذن دخول لشركة'),
    'SUPPORT_ACCESS_EMERGENCY': ('high', 'دخول طارئ لشركة بلا موافقة'),
    'SUPPORT_ACCESS_APPROVED': ('warning', 'موافقة شركة على دخول الدعم'),
    'SUPPORT_ACCESS_REJECTED': ('info', 'رفض شركة دخول الدعم'),
    'SUPPORT_ACCESS_REVOKED': ('info', 'سحب/إنهاء إذن دخول'),
    'SUPPORT_ACCESS_CANCELLED': ('info', 'إلغاء طلب دخول'),
    'SUPPORT_ACCESS_USED': ('high', 'بدء استعمال إذن دخول لشركة'),
}


def _label_user(user):
    if user is None or not getattr(user, 'pk', None):
        return ''
    full = f'{user.first_name} {user.last_name}'.strip()
    return (full or user.username or user.email or '')[:150]


def record_platform_event(
    action, *, request=None, actor=None, tenant=None, target_user=None,
    reason='', metadata=None, severity=None,
):
    """يكتب سطراً واحداً في سجلّ تدقيق المنصة ويعيده.

    `actor` افتراضه مستخدم الطلب. `severity` افتراضه ما في `PLATFORM_EVENTS`.
    حدثٌ غير معروف يُرفض — الكود الحرّ يصنع سجلّاً لا يُفلتَر.
    """
    if action not in PLATFORM_EVENTS:
        raise ValueError(f'حدث تدقيق غير معروف: {action}')
    default_severity, _label = PLATFORM_EVENTS[action]
    if actor is None and request is not None:
        user = getattr(request, 'user', None)
        actor = user if getattr(user, 'is_authenticated', False) else None
    return PlatformAuditLog.objects.create(
        action=action,
        severity=severity or default_severity,
        actor=actor,
        actor_label=_label_user(actor),
        tenant=tenant,
        tenant_label=(getattr(tenant, 'CompanyName', '') or '')[:200],
        target_user=target_user,
        target_label=_label_user(target_user),
        reason=(reason or '')[:4000],
        metadata=metadata or {},
        ip_address=_client_ip(request),
        trace_id=(getattr(request, 'trace_id', None) or get_current_trace_id() or '')[:64],
    )


def record_platform_event_safely(action, **kwargs):
    """نفس `record_platform_event` لكن لا يُسقط المسار المنادي أبداً."""
    try:
        return record_platform_event(action, **kwargs)
    except Exception:  # noqa: BLE001 — السجلّ لا يكسر تسجيل الدخول
        logger.exception('platform audit write failed action=%s', action)
        return None


def event_label(action):
    return PLATFORM_EVENTS.get(action, (None, action))[1]
