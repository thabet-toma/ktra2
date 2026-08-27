"""واجهة الطلبات والإجازات والسلف (`hr_suite`).

**من يرى ماذا** هو كل شيء هنا، فالطلب مستندٌ شخصيّ:

- صاحبُ الطلب يرى طلباتِه دائماً بـ`ess.self` — ولا يحتاج صلاحيةً إدارية
  ليقرأ ما كتبه بنفسه.
- `hr.requests.view` يفتح طلبات **الجميع** (شؤون الموظفين والمحاسب).
- `hr.requests.approve` يفتح صندوق الاعتماد ويسمح بالبتّ.

والحالة **لا تُكتب بـ`PATCH`** أبداً: أفعالٌ صريحة (`submit`/`approve`/
`reject`/`cancel`) تمرّ بآلة الحالات في `hr/requests.py` — حقلُ حالةٍ قابلٌ
للكتابة كان يعني تجاوز سلسلة الاعتماد كلها بطلبٍ واحد.
"""
import logging

from django.db import transaction
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core.access import user_has_perm
from core.activity import log_activity

from . import notify
from . import requests as flow
from .models import (
    Advance, ApprovalRule, ApprovalStep, Employee, EmployeeRequest, Holiday,
    LeaveBalanceAdjustment, LeaveType,
)
from .serializers import (
    AdvanceSerializer, ApprovalRuleSerializer, EmployeeRequestSerializer,
    HolidaySerializer, LeaveBalanceAdjustmentSerializer, LeaveTypeSerializer,
)
from .suite import (
    PERM_ATTENDANCE_VIEW, PERM_ESS, PERM_LEAVE, PERM_REQUESTS_APPROVE,
    PERM_REQUESTS_VIEW, PERM_SETTINGS, HrSuiteViewSetBase,
)

logger = logging.getLogger(__name__)


class LeaveTypeViewSet(HrSuiteViewSetBase):
    """أنواع الإجازات — ضبطُ الشركة لقواعد استحقاقها."""

    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_LEAVE

    def perform_destroy(self, instance):
        """نوعٌ استُعمل في طلبٍ أو تسوية يُعطَّل ولا يُمحى — `PROTECT` يمنعه بـ500."""
        if instance.requests.exists() or instance.adjustments.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف نوع إجازة استُعمل — عطّله بدل حذفه.'})
        super().perform_destroy(instance)


class HolidayViewSet(HrSuiteViewSetBase):
    """العطلات الرسمية — تُستثنى من حساب الحضور والغياب."""

    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_LEAVE

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get('year')
        if str(year or '').isdigit():
            qs = qs.filter(date__year=int(year))
        return qs


class LeaveBalanceAdjustmentViewSet(HrSuiteViewSetBase):
    """تسويات أرصدة الإجازات — السطر الوحيد الذي يُكتب بيدٍ في دفتر الأرصدة."""

    queryset = LeaveBalanceAdjustment.objects.select_related(
        'employee', 'leave_type').all()
    serializer_class = LeaveBalanceAdjustmentSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_LEAVE

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)
        serializer.instance.created_by = self.request.user
        serializer.instance.save(update_fields=['created_by'])

    @action(detail=False, methods=['get'], url_path='balances')
    def balances(self, request):
        """أرصدة الإجازات — لموظفٍ بعينه أو لكل الموظفين النشطين.

        محسوبةٌ من الدفتر في كل نداء (`hr/leave.py`): رصيدٌ مخزَّن يفترق عن
        دفتره عند أول تعديلٍ رجعيّ ولا يُكتشف فرقُه إلا حين يشتكي صاحبه.
        """
        from .leave import employee_balances

        employees = Employee.objects.filter(tenant=self.tenant, is_active=True)
        employee_id = request.query_params.get('employee')
        if str(employee_id or '').isdigit():
            employees = employees.filter(pk=employee_id)
        year = request.query_params.get('year')
        year = int(year) if str(year or '').isdigit() else None

        return Response([
            {
                'employee': employee.pk,
                'employee_name': employee.name,
                'employee_code': employee.code,
                'balances': [
                    {**row, 'accrued': str(row['accrued']), 'adjusted': str(row['adjusted']),
                     'taken': str(row['taken']), 'remaining': str(row['remaining'])}
                    for row in employee_balances(employee, year=year)
                ],
            }
            for employee in employees.order_by('name')
        ])


class ApprovalRuleViewSet(HrSuiteViewSetBase):
    """قواعد توجيه الاعتماد — ضبطٌ إداريّ، فخلف صلاحية الإعدادات."""

    queryset = ApprovalRule.objects.select_related(
        'department', 'branch', 'approver_user').all()
    serializer_class = ApprovalRuleSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_SETTINGS


class EmployeeRequestViewSet(HrSuiteViewSetBase):
    """طلبات الموظفين — تقديمها والبتّ فيها.

    القراءة أوسع مفاتيح الوحدة (`ess.self`) لأن كل موظف يرى **طلباته هو**؛
    والفلترة في `get_queryset` هي ما يمنع رؤية طلبات غيره.
    """

    queryset = EmployeeRequest.objects.select_related(
        'employee', 'leave_type').prefetch_related('steps__approver_user', 'steps__acted_by')
    serializer_class = EmployeeRequestSerializer
    perm_read = PERM_ESS
    perm_write = PERM_ESS
    action_perms = {
        'approve': PERM_REQUESTS_APPROVE,
        'reject': PERM_REQUESTS_APPROVE,
    }

    def _my_employee(self):
        return Employee.objects.filter(
            tenant=self.tenant, user=self.request.user, is_active=True).first()

    def _can_view_all(self) -> bool:
        return user_has_perm(self.request.user, self.tenant, PERM_REQUESTS_VIEW) \
            or user_has_perm(self.request.user, self.tenant, PERM_REQUESTS_APPROVE)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        if not self._can_view_all():
            # من لا يملك صلاحية إدارية يرى طلباته هو وحدها — وبلا ملفّ موظف
            # لا يرى شيئاً (لا خطأ: لا وجود لطلباته أصلاً).
            mine = self._my_employee()
            qs = qs.filter(employee=mine) if mine else qs.none()
        elif params.get('scope') == 'mine':
            mine = self._my_employee()
            qs = qs.filter(employee=mine) if mine else qs.none()
        elif params.get('scope') == 'inbox':
            # صندوق الاعتماد: ما ينتظر قرار **هذا** المستخدم الآن — خطوةٌ باسمه
            # أو خطوةٌ مفتوحة وهو يملك صلاحية الاعتماد.
            qs = qs.filter(status=EmployeeRequest.STATUS_PENDING)
            if not user_has_perm(self.request.user, self.tenant, PERM_REQUESTS_APPROVE):
                qs = qs.filter(steps__approver_user=self.request.user,
                               steps__status=ApprovalStep.STATUS_PENDING)
            qs = qs.distinct()

        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('kind'):
            qs = qs.filter(kind=params['kind'])
        if str(params.get('employee') or '').isdigit() and self._can_view_all():
            qs = qs.filter(employee_id=params['employee'])
        return qs

    def perform_create(self, serializer):
        """الطلب يُنسب لصاحبه لا لمن أرسل الطلب — إلا لمن يملك إدارة الطلبات.

        بلا هذا الحارس يقدّم موظفٌ إجازةً باسم زميله بتغيير رقمٍ في الحمولة.
        """
        employee = serializer.validated_data.get('employee')
        if not self._can_view_all():
            mine = self._my_employee()
            if mine is None:
                raise PermissionDenied('لا يوجد ملفّ موظف مرتبط بحسابك.')
            if employee is not None and employee.pk != mine.pk:
                raise PermissionDenied('لا يمكنك تقديم طلب باسم موظف آخر.')
            employee = mine
        serializer.save(
            tenant=self.tenant, employee=employee, created_by=self.request.user)

    def _guard_open(self, instance):
        if instance.status not in EmployeeRequest.OPEN_STATUSES:
            raise ValidationError({'detail': 'الطلب بُتّ فيه ولا يُعدَّل.'})
        if not self._can_view_all():
            mine = self._my_employee()
            if mine is None or instance.employee_id != mine.pk:
                raise PermissionDenied('هذا ليس طلبك.')
            if instance.status != EmployeeRequest.STATUS_DRAFT:
                raise ValidationError(
                    {'detail': 'الطلب قيد المراجعة — ألغِه ثم قدّم طلباً جديداً.'})

    def perform_update(self, serializer):
        self._guard_open(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        """المسودّة وحدها تُحذف — وما دخل المراجعة يُلغى ويبقى أثرُه."""
        if instance.status != EmployeeRequest.STATUS_DRAFT:
            raise ValidationError(
                {'detail': 'لا تُحذف إلا المسودّة — استعمل «إلغاء» لما دخل المراجعة.'})
        self._guard_open(instance)
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """يقدّم الطلب للاعتماد، ويُبلِغ موظفي المستوى الأول."""
        instance = self.get_object()
        self._guard_open(instance)
        with transaction.atomic():
            flow.submit(instance, user=request.user)
        notify.request_submitted(instance)
        log_activity(
            action='update', entity_type='hr_request', entity_id=instance.pk,
            entity_label=f'{instance.employee.name} — {instance.get_kind_display()}',
            description='تقديم طلب للاعتماد', request=request,
        )
        return Response(self.get_serializer(instance).data)

    def _act(self, request, *, approving: bool):
        instance = self.get_object()
        has_perm = user_has_perm(request.user, self.tenant, PERM_REQUESTS_APPROVE)
        if not flow.can_act(request.user, instance, has_perm=has_perm):
            raise PermissionDenied('هذا المستوى ليس بانتظار قرارك.')
        note = str(request.data.get('note') or '')
        with transaction.atomic():
            if approving:
                flow.approve(instance, user=request.user, note=note)
            else:
                flow.reject(instance, user=request.user, note=note)
        instance.refresh_from_db()
        if instance.status in (EmployeeRequest.STATUS_APPROVED, EmployeeRequest.STATUS_REJECTED):
            notify.request_decided(instance)
        else:
            # بقيت مستويات — يُبلَّغ من ينتظره القرار الآن.
            notify.request_submitted(instance)
        log_activity(
            action='update', entity_type='hr_request', entity_id=instance.pk,
            entity_label=f'{instance.employee.name} — {instance.get_kind_display()}',
            description='موافقة على طلب' if approving else 'رفض طلب', request=request,
        )
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._act(request, approving=True)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._act(request, approving=False)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """يلغي طلباً لم يُبتّ فيه — صاحبُه أو من يديره."""
        instance = self.get_object()
        if not self._can_view_all():
            mine = self._my_employee()
            if mine is None or instance.employee_id != mine.pk:
                raise PermissionDenied('هذا ليس طلبك.')
        with transaction.atomic():
            flow.cancel(instance, user=request.user)
        return Response(self.get_serializer(instance).data)


class AdvanceViewSet(HrSuiteViewSetBase):
    """السلف — تُنشأ باعتماد طلبها، وتُصرف بسند صرفٍ يحمل مرجعها.

    القراءة والكتابة كلتاهما خلف صلاحية **الترحيل** (`hr.payroll.post`): هذا
    دَينٌ على الموظف وأثرُه في راتبه، ومَن يقرؤه هو مَن يقرأ دفاتره.
    """

    queryset = Advance.objects.select_related('employee', 'request').all()
    serializer_class = AdvanceSerializer
    perm_read = 'hr.payroll.post'
    perm_write = 'hr.payroll.post'
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        return qs

    def create(self, request, *args, **kwargs):
        return Response(
            {'detail': 'السلفة تُنشأ باعتماد طلب سلفة — لا تُدخَل مباشرةً.'},
            status=405)

    @action(detail=True, methods=['post'])
    def disburse(self, request, pk=None):
        """يصرف السلفة بسند صرفٍ يحمل مرجعها — **بلا مسار مالٍ ثانٍ**.

        القيد هو قيد سند الصرف المعتاد بالضبط (مدين حساب الموظف / دائن
        الصندوق)، ويمرّ بـ`post_payroll_payment` كسائر الصرف. ولو أُنشئ هنا
        قيدٌ خاصٌّ بالسلف لصار للمال بابان في الوحدة الواحدة.
        """
        from .models import PayrollPayment
        from .payroll import post_payroll_payment

        advance = self.get_object()
        if advance.status != Advance.STATUS_OPEN:
            raise ValidationError({'detail': 'لا تُصرف إلا سلفةٌ قائمة.'})
        if advance.is_disbursed:
            raise ValidationError({'detail': 'هذه السلفة مصروفةٌ سلفاً.'})

        account_id = request.data.get('cash_account')
        with transaction.atomic():
            payment = PayrollPayment.objects.create(
                tenant=self.tenant,
                employee=advance.employee,
                advance=advance,
                date=request.data.get('date') or advance.date,
                amount=advance.total,
                cash_account_id=account_id if str(account_id or '').isdigit() else None,
                notes=f'صرف سلفة #{advance.pk}'[:200],
                created_by=request.user,
            )
            post_payroll_payment(payment, user=request.user)

        log_activity(
            action='payment', entity_type='hr_advance', entity_id=advance.pk,
            entity_label=advance.employee.name,
            description='صرف سلفة', request=request,
        )
        advance.refresh_from_db()
        return Response(self.get_serializer(advance).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """يلغي سلفةً لم تُصرَف — والمصروفة تُسدَّد ولا تُلغى."""
        advance = self.get_object()
        if advance.is_disbursed:
            raise ValidationError(
                {'detail': 'السلفة مصروفة — تُسدَّد بأقساطها ولا تُلغى.'})
        advance.status = Advance.STATUS_CANCELLED
        advance.remaining = 0
        advance.save(update_fields=['status', 'remaining', 'updated_at'])
        return Response(self.get_serializer(advance).data)
