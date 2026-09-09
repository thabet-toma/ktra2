"""مستقبلات إشارات عمليات المنصة (platform_ops receivers)."""
from .models import Engagement, PlatformEmployee
from .services import record_agent_granted_membership


def handle_company_member_changed(sender, actor=None, membership=None, role_before="", role_after="", tenant=None, **kwargs):
    """التقاط إضافة أو تعديل دور عضو في شركة وتسجيله إذا كان الفاعل وكيل منصة نشطاً.

    القواعد:
    1. لا يسجل الإسناد الخاص بالوكيل نفسه (actor.pk == membership.user_id).
    2. يسجل فقط إذا كان الفاعل موظف منصة نشطاً ولديه ارتباط نشط مع نفس الشركة.
    3. إذا كان الفاعل مديراً عادياً للشركة وليس وكيل منصة، لا يسجل شيئاً.
    """
    if not actor or not getattr(actor, "is_authenticated", False) or not membership or not tenant:
        return

    # استبعاد إجراءات الوكيل على حسابه الشخصي
    if actor.pk == membership.user_id:
        return

    # التحقق من أن الفاعل موظف منصة نشط
    employee = PlatformEmployee.objects.filter(
        user=actor,
        status=PlatformEmployee.Status.ACTIVE,
    ).first()
    if not employee:
        return

    # التحقق من وجود ارتباط نشط لهذا الموظف مع هذه الشركة
    engagement = Engagement.objects.filter(
        employee=employee,
        tenant=tenant,
        status=Engagement.Status.ACTIVE,
    ).first()
    if not engagement:
        return

    record_agent_granted_membership(
        engagement=engagement,
        membership=membership,
        role_after=role_after,
        role_before=role_before,
    )
