"""دورة اعتماد طلبات الموظفين — التوجيه، وآلة الحالات، وأثر الاعتماد.

**آلة حالاتٍ واحدة لأربعة أنواع** (إجازة · سلفة · تسوية مصروف · طلب آخر) لأن
الدورة واحدة: تقديمٌ ثم مستويات ثم قرار. فصلُها نماذجَ كان يعني نسخ الآلة
وقواعد التوجيه أربع مرّات — وأربع نسخٍ من قاعدةٍ هي أربع فرصٍ لانزياحها.

    مسودّة ──تقديم──▶ قيد المراجعة ──موافقة كل المستويات──▶ موافق
        │                   │
        └──── إلغاء ────────┴──رفض أي مستوى──▶ مرفوض

**الرفض يقطع السلسلة فوراً**: مستوى ثانٍ يُسأل بعد رفض الأول عبثٌ يُربك من
يُسأل، ويفتح باب اعتمادٍ يناقض رفضاً قائماً.

وأثر الاعتماد بحسب النوع:
- **إجازة** → أيامها تنقلب في `AttendanceDay` إلى «إجازة» بدل «غياب».
- **سلفة** → تُنشأ `Advance` بأقساطها. **ولا مال يتحرّك بالاعتماد**: الصرف
  فعلٌ مستقل بسند صرفٍ لاحق، لأن من يعتمد ليس بالضرورة من يملك الصندوق.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models import ApprovalRule, ApprovalStep, Advance, EmployeeRequest

logger = logging.getLogger(__name__)

CENTS = Decimal('0.01')

#: سقف مستويات الاعتماد لطلب واحد — قواعدُ سيئة الضبط كانت تبني سلسلةً بلا نهاية.
MAX_LEVELS = 10


def money(value) -> Decimal:
    return (Decimal(value or 0)).quantize(CENTS, rounding=ROUND_HALF_UP)


def matching_rules(request_row) -> list:
    """قواعد الاعتماد التي تنطبق على هذا الطلب، مستوىً بمستوى.

    لكل مستوى تُختار **أخصّ** قاعدة: قاعدةٌ لقسم الموظف تسبق قاعدةً عامّة،
    وإلا احتاج كل قسمٍ إلى نسخةٍ من كل قاعدة عامّة.
    """
    employee = request_row.employee
    rules = (
        ApprovalRule.objects
        .filter(tenant_id=request_row.tenant_id, is_active=True)
        .select_related('approver_user')
        .order_by('level', 'id')
    )
    per_level = {}
    for rule in rules:
        if rule.kind and rule.kind != request_row.kind:
            continue
        if rule.department_id and rule.department_id != employee.department_id:
            continue
        if rule.branch_id and rule.branch_id != employee.branch_id:
            continue
        current = per_level.get(rule.level)
        if current is None or rule.specificity > current.specificity:
            per_level[rule.level] = rule
    return [per_level[level] for level in sorted(per_level)][:MAX_LEVELS]


def build_steps(request_row) -> list:
    """يبني مستويات الاعتماد كلّها لحظة التقديم.

    مقدَّماً لا خطوةً بخطوة: الطلب يجب أن يُظهر لصاحبه **أين وصل ومن بقي**،
    وسلسلةٌ تُبنى عند كل قرار لا تستطيع أن تقول ذلك.

    وبلا قواعد مضبوطة يُبنى مستوىً واحد مفتوح لأي حاملِ صلاحية اعتماد — شركةٌ
    لم تضبط قواعدها بعد يجب أن تستطيع تشغيل الطلبات، لا أن تجد طلباً معلّقاً
    بلا أحدٍ يستطيع البتّ فيه.
    """
    request_row.steps.all().delete()
    rules = matching_rules(request_row)
    if not rules:
        return [ApprovalStep.objects.create(request=request_row, level=1)]
    return [
        ApprovalStep.objects.create(
            request=request_row, level=index,
            approver_user=rule.approver_user,
        )
        for index, rule in enumerate(rules, start=1)
    ]


def current_step(request_row):
    """المستوى المنتظر الآن — أوّل خطوةٍ لم يُبتّ فيها."""
    return request_row.steps.filter(status=ApprovalStep.STATUS_PENDING).order_by('level').first()


def can_act(user, request_row, *, has_perm: bool) -> bool:
    """أيستطيع هذا المستخدم البتّ في المستوى الحالي؟

    خطوةٌ باسم مستخدمٍ بعينه لا يبتّ فيها غيره **حتى لو ملك الصلاحية**: تسميةُ
    المعتمِد قرارٌ تنظيمي، وتجاوزُه بالصلاحية يُفرغه من معناه. وخطوةٌ بلا اسم
    يبتّ فيها أي حاملٍ للصلاحية.
    """
    step = current_step(request_row)
    if step is None:
        return False
    if step.approver_user_id:
        return step.approver_user_id == getattr(user, 'pk', None)
    return has_perm


@transaction.atomic
def submit(request_row, *, user=None) -> EmployeeRequest:
    """يقدّم الطلب للاعتماد ويبني سلسلته."""
    from rest_framework.exceptions import ValidationError

    if request_row.status != EmployeeRequest.STATUS_DRAFT:
        raise ValidationError({'detail': 'لا يُقدَّم إلا الطلب المسودّة.'})
    build_steps(request_row)
    request_row.status = EmployeeRequest.STATUS_PENDING
    request_row.decided_at = None
    request_row.decision_note = ''
    request_row.save(update_fields=['status', 'decided_at', 'decision_note', 'updated_at'])
    return request_row


@transaction.atomic
def approve(request_row, *, user, note='') -> EmployeeRequest:
    """يوافق على المستوى الحالي — وحين يكتمل آخرها يصير الطلب معتمداً."""
    from rest_framework.exceptions import ValidationError

    if request_row.status != EmployeeRequest.STATUS_PENDING:
        raise ValidationError({'detail': 'لا يُعتمد إلا طلبٌ قيد المراجعة.'})
    step = current_step(request_row)
    if step is None:
        raise ValidationError({'detail': 'لا يوجد مستوى بانتظار القرار.'})

    step.status = ApprovalStep.STATUS_APPROVED
    step.acted_by = user
    step.acted_at = timezone.now()
    step.note = str(note or '')[:300]
    step.save(update_fields=['status', 'acted_by', 'acted_at', 'note'])

    if current_step(request_row) is not None:
        return request_row  # بقيت مستويات — الطلب ما زال قيد المراجعة.

    request_row.status = EmployeeRequest.STATUS_APPROVED
    request_row.decided_at = timezone.now()
    request_row.decision_note = str(note or '')[:300]
    request_row.save(update_fields=['status', 'decided_at', 'decision_note', 'updated_at'])
    apply_approval(request_row, user=user)
    return request_row


@transaction.atomic
def reject(request_row, *, user, note='') -> EmployeeRequest:
    """يرفض الطلب عند المستوى الحالي — والرفض يقطع السلسلة فوراً."""
    from rest_framework.exceptions import ValidationError

    if request_row.status != EmployeeRequest.STATUS_PENDING:
        raise ValidationError({'detail': 'لا يُرفض إلا طلبٌ قيد المراجعة.'})
    step = current_step(request_row)
    if step is None:
        raise ValidationError({'detail': 'لا يوجد مستوى بانتظار القرار.'})

    step.status = ApprovalStep.STATUS_REJECTED
    step.acted_by = user
    step.acted_at = timezone.now()
    step.note = str(note or '')[:300]
    step.save(update_fields=['status', 'acted_by', 'acted_at', 'note'])

    request_row.status = EmployeeRequest.STATUS_REJECTED
    request_row.decided_at = timezone.now()
    request_row.decision_note = str(note or '')[:300]
    request_row.save(update_fields=['status', 'decided_at', 'decision_note', 'updated_at'])
    return request_row


@transaction.atomic
def cancel(request_row, *, user=None) -> EmployeeRequest:
    """يلغي طلباً لم يُبتّ فيه بعد — والمعتمَد لا يُلغى بهذا الباب.

    إلغاء المعتمَد يفكّ أثراً وقع فعلاً (أيام إجازةٍ حُسبت، أو سلفةٌ أُنشئت)،
    وهو فعلٌ إداريّ آخر له بابه: تُلغى السلفة من شاشتها، وتُعدَّل الإجازة
    بتصحيح أيامها.
    """
    from rest_framework.exceptions import ValidationError

    if request_row.status not in EmployeeRequest.OPEN_STATUSES:
        raise ValidationError({'detail': 'لا يُلغى إلا طلبٌ لم يُبتّ فيه بعد.'})
    request_row.status = EmployeeRequest.STATUS_CANCELLED
    request_row.decided_at = timezone.now()
    request_row.save(update_fields=['status', 'decided_at', 'updated_at'])
    return request_row


def apply_approval(request_row, *, user=None) -> None:
    """أثر الاعتماد — يختلف بحسب نوع الطلب."""
    if request_row.kind == EmployeeRequest.KIND_LEAVE:
        _apply_leave(request_row)
    elif request_row.kind == EmployeeRequest.KIND_ADVANCE:
        _apply_advance(request_row, user=user)


def _apply_leave(request_row) -> None:
    """يعيد حساب أيام الإجازة فتنقلب من «غياب» إلى «إجازة».

    إعادة الحساب لا كتابةٌ مباشرة: `recompute_attendance_day` هي مصدر حكم
    اليوم الوحيد، وكتابةُ الحالة هنا كانت تفتح مصدرَ حقيقةٍ ثانياً.
    """
    from datetime import timedelta

    from . import attendance as engine
    from .models import ShiftAssignment

    if not request_row.date_from or not request_row.date_to:
        return
    employee = request_row.employee
    assignments = list(
        ShiftAssignment.objects
        .filter(employee=employee)
        .select_related('shift')
        .order_by('-start_date', '-id')
    )
    day = request_row.date_from
    guard = 0
    while day <= request_row.date_to and guard < 366:
        engine.recompute_attendance_day(employee, day, assignments=assignments)
        day += timedelta(days=1)
        guard += 1


def _apply_advance(request_row, *, user=None) -> None:
    """ينشئ السلفة بأقساطها — **ولا يصرف مالاً**.

    الصرف فعلٌ مستقل بسند صرفٍ لاحق: من يعتمد الطلب ليس بالضرورة من يملك
    الصندوق، ودمجُ القرارين كان يجعل موافقةً إداريةً تُخرج نقداً بلا سند.
    """
    if request_row.amount is None or Decimal(request_row.amount) <= 0:
        return
    if Advance.objects.filter(request=request_row).exists():
        return
    total = money(request_row.amount)
    count = max(1, int(request_row.installments or 1))
    Advance.objects.create(
        tenant_id=request_row.tenant_id,
        employee=request_row.employee,
        request=request_row,
        date=request_row.execution_date or timezone.localdate(),
        total=total,
        # القسط الأخير يبتلع فرق التقريب لأن `remaining` هو من يحكم التوقّف.
        monthly_installment=money(total / count),
        remaining=total,
        created_by=user,
    )
