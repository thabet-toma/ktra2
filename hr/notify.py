"""إشعارات الموارد البشرية — أول مسارِ إرسالٍ **خادميّ** في هذا المستودع.

جرسُ الإشعارات في الواجهة يقرأ مجموعة `notifications` في مرآة `bridge`
(`FirestoreMirrorDoc`)، وكان كلُّ ما يكتب فيها متصفّحاً: مُجدولاتٌ تعمل ما دام
أحدٌ فاتحاً التطبيق. وهذا لا يكفي هنا — الطلب يُقدَّم فيجب أن يصل مَن يعتمده
ولو كان تطبيقه مغلقاً، فالكتابة صارت من الخادم لحظةَ الحدث.

**ولا يُسقِط الإشعارُ الفعلَ الأصلي مهما فشل** (نفس عقد `core/activity.py`):
موافقةٌ نجحت ثم تعذّر إشعارها موافقةٌ نجحت. كل شيء داخل savepoint وكل استثناء
يُبتلع إلى السجلّ.

الوثيقة تُطابق `frontend_v2/types/notification.ts::AppNotification` حرفاً
بحرف — الواجهة تقرأها كما هي، وحقلٌ ناقصٌ هنا يعني بطاقةً فارغة هناك.
"""
from __future__ import annotations

import logging
import uuid

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: مجموعة الإشعارات في المرآة — ليست ضمن `bridge.views.GLOBAL_COLLECTIONS`
#: فهي معزولةٌ بالشركة، ويجب تمرير `tenant` عند الكتابة.
COLLECTION = 'notifications'

#: أنواعٌ تُضاف إلى الاتحاد في `frontend_v2/types/notification.ts` — نوعٌ
#: مجهولٌ هناك يسقط على أيقونة «عام» ولا يكسر شيئاً، لكنه يفقد تمييزه.
TYPE_REQUEST_SUBMITTED = 'hr_request_submitted'
TYPE_REQUEST_DECIDED = 'hr_request_decided'
TYPE_CONTRACT_EXPIRING = 'hr_contract_expiring'


def _write(tenant_id, *, user_id, title, message, kind, target_view='', target_path=''):
    """يكتب وثيقة إشعار واحدة. لا يرمي أبداً."""
    from bridge.models import FirestoreMirrorDoc

    try:
        with transaction.atomic():
            FirestoreMirrorDoc.objects.create(
                path=f'{COLLECTION}/{uuid.uuid4().hex}',
                tenant_id=tenant_id,
                data={
                    'userId': str(user_id),
                    'title': title,
                    'message': message,
                    'type': kind,
                    'targetView': target_view,
                    'targetPath': target_path,
                    'isRead': False,
                    'createdAt': timezone.now().isoformat(),
                },
            )
    except Exception:  # noqa: BLE001 — الإشعار لا يُسقط عمليةً نجحت
        logger.exception('hr.notify failed (user=%s kind=%s)', user_id, kind)


def _approver_user_ids(request_row) -> list:
    """مَن يُبلَّغ بالمستوى الحالي.

    خطوةٌ باسم مستخدمٍ بعينه تُبلَّغه وحده؛ وخطوةٌ مفتوحة تُبلّغ كل حاملي
    صلاحية الاعتماد في الشركة — وهم يُحسبون من مصفوفة الصلاحيات نفسها التي
    تحرس الفعل، فلا تنزاح قائمةُ المُبلَّغين عن قائمة القادرين.
    """
    from core.access import user_has_perm
    from tenants.models import UserCompanyMembership

    from .requests import current_step
    from .suite import PERM_REQUESTS_APPROVE

    step = current_step(request_row)
    if step is None:
        return []
    if step.approver_user_id:
        return [step.approver_user_id]

    tenant_id = request_row.tenant_id
    members = (
        UserCompanyMembership.objects
        .filter(tenant_id=tenant_id)
        .select_related('user')
    )
    return [
        membership.user_id
        for membership in members
        if user_has_perm(membership.user, tenant_id, PERM_REQUESTS_APPROVE)
    ]


def request_submitted(request_row) -> None:
    """طلبٌ قُدّم — يُبلَّغ به موظفو المستوى الحالي."""
    label = request_row.get_kind_display()
    for user_id in _approver_user_ids(request_row):
        _write(
            request_row.tenant_id,
            user_id=user_id,
            title=f'طلب {label} بانتظار اعتمادك',
            message=f'{request_row.employee.name} قدّم طلب {label}.',
            kind=TYPE_REQUEST_SUBMITTED,
            target_view='hr-requests',
            target_path='/hr/requests',
        )


def request_decided(request_row) -> None:
    """قرارٌ صدر — يُبلَّغ به صاحب الطلب إن كان له حساب.

    الموظف بلا حساب لا يُبلَّغ ولا يُسجَّل خطأ: ملفُّ موظفٍ بلا مستخدمٍ حالةٌ
    عادية في هذا النظام (من لا يبصم ولا يدخل النظام له ملفٌّ للرواتب فقط).
    """
    owner = request_row.employee.user_id
    if not owner:
        return
    decisions = {
        request_row.STATUS_APPROVED: ('تمت الموافقة على طلبك', 'وافقت الإدارة على'),
        request_row.STATUS_REJECTED: ('رُفض طلبك', 'رُفض'),
    }
    entry = decisions.get(request_row.status)
    if entry is None:
        return
    title, verb = entry
    _write(
        request_row.tenant_id,
        user_id=owner,
        title=title,
        message=f'{verb} طلب {request_row.get_kind_display()}.'
                + (f' — {request_row.decision_note}' if request_row.decision_note else ''),
        kind=TYPE_REQUEST_DECIDED,
        target_view='hr-requests',
        target_path='/hr/requests',
    )
