"""واجهة الرواتب — الموظفون، ساعاتهم، غياباتهم، كشوفهم، وصرفها.

الحراسة على ثلاث درجات كما في بقية النظام:
- `BaseTenantViewSet` يعزل كل استعلام بالشركة النشطة،
- `hr.payroll.view` للقراءة و`hr.payroll.manage` للكتابة و`hr.payroll.post`
  للترحيل والصرف — الإنفاذ خادميّ، وأعلام الواجهة للعرض فقط،
- والمحاسب القانوني الخارجي محجوب عن مسارات الشركة التشغيلية كعادته.
"""
import logging
from datetime import date as _date

from django.db import transaction
from rest_framework import status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accountant_portal.permissions import LegalAccountantRoutePermission
from core.access import require_perm
from core.mixins import BaseTenantViewSet
from core.tenant_utils import get_tenant

from . import payroll
from .models import AttendanceAdjustment, Employee, Payslip, PayrollPayment, WorkLog
from .serializers import (
    AttendanceAdjustmentSerializer, EmployeeSerializer, PayrollPaymentSerializer,
    PayslipSerializer, WorkLogSerializer,
)
from .views import _month_bounds

logger = logging.getLogger(__name__)

PERM_VIEW = 'hr.payroll.view'
PERM_MANAGE = 'hr.payroll.manage'
PERM_POST = 'hr.payroll.post'

_READ_METHODS = ('GET', 'HEAD', 'OPTIONS')


class PayrollViewSetBase(BaseTenantViewSet):
    """أساس مشترك: مصادقة، عزل بالشركة، وصلاحية تتبع نوع الطلب."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, LegalAccountantRoutePermission]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_perm(request, PERM_VIEW if request.method in _READ_METHODS else PERM_MANAGE)

    def _tenant(self):
        tenant = get_tenant(self.request)
        if tenant is None:
            raise ValidationError({'tenant': 'لا يوجد شركة محددة لهذا الطلب.'})
        return tenant

    def _filter_by_employee_and_period(self, qs):
        """فلاتر مشتركة للسجلات اليومية: `?employee=` و`?month=` أو `?from=&to=`."""
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        month = params.get('month')
        if month:
            bounds = _month_bounds(month)
            if bounds:
                qs = qs.filter(date__gte=bounds[0], date__lt=bounds[1])
        if params.get('from'):
            qs = qs.filter(date__gte=params['from'])
        if params.get('to'):
            qs = qs.filter(date__lte=params['to'])
        return qs


class EmployeeViewSet(PayrollViewSetBase):
    """الموظفون — إنشاء الموظف يفتح له حسابه في الشجرة فوراً.

    بلا حساب لا يظهر الموظف تحت بند الرواتب، ولا يجد قيدُ الكشف طرفه الدائن.
    """
    queryset = Employee.objects.select_related('account').all()
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('pay_type') in (Employee.PAY_MONTHLY, Employee.PAY_HOURLY):
            qs = qs.filter(pay_type=params['pay_type'])
        active = params.get('is_active')
        if active in ('true', 'false'):
            qs = qs.filter(is_active=active == 'true')
        search = (params.get('search') or '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    def list(self, request, *args, **kwargs):
        """أرصدة الصفحة تُحسب دفعةً واحدة وتُمرَّر في سياق المُسلسِل."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        context = self.get_serializer_context()
        context['balances'] = payroll.employee_balances(self._tenant().pk, rows)
        data = self.get_serializer_class()(rows, many=True, context=context).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    def perform_create(self, serializer):
        tenant = self._tenant()
        # حدّ الخطة يُفحص قبل الإنشاء لا بعده — إنشاءٌ ثم رفضٌ يترك حساباً
        # في الشجرة بلا صاحب.
        from core.plans import enforce_limits

        enforce_limits(tenant, 'hr.employees')
        with transaction.atomic():
            code = (serializer.validated_data.get('code') or '').strip()
            employee = serializer.save(
                tenant=tenant, code=code or payroll.next_employee_code(tenant))
            payroll.ensure_employee_account(employee)
        logger.info('payroll.employee_created tenant=%s employee=%s pay_type=%s',
                    tenant.pk, employee.pk, employee.pay_type)

    def perform_update(self, serializer):
        employee = serializer.save()
        # الاسم في الشجرة يتبع اسم صاحبه (والحساب يُنشأ لموظفٍ قديمٍ بلا حساب).
        payroll.ensure_employee_account(employee)
        logger.info('payroll.employee_updated employee=%s', employee.pk)

    def perform_destroy(self, instance):
        """الموظف الذي دخل الدفاتر يُعطَّل ولا يُحذف — حذفه ييتّم قيوده."""
        if instance.payslips.exists() or instance.payroll_payments.exists():
            raise ValidationError(
                'لهذا الموظف كشوف أو سندات صرف — عطّله بدل حذفه كي لا تفقد سجلّه المحاسبي.'
            )
        employee_id = instance.pk
        instance.delete()
        logger.info('payroll.employee_deleted employee=%s', employee_id)

    @action(detail=True, methods=['post'], url_path='ess-access')
    def ess_access(self, request, pk=None):
        """يفتح للموظف حساب خدمة ذاتية — أو يربطه بحسابٍ قائم، أو يفصله.

        الفعل إداريّ لا مالي، وسطحُه هنا لأن مدخله كرت الموظف. وهو **خلف
        ترخيص الوحدة** رغم سُكناه في ViewSet قديمٍ مفتوح: بلا `hr_suite` لا
        وجود لخدمةٍ ذاتية أصلاً، فمنحُ صلاحيتها عبثٌ يُربك مصفوفة الأدوار.

        وكلمة المرور **لا تُولَّد ولا تُرسَل هنا**: الحساب يُنشأ بلا كلمة قابلة
        للاستعمال، والموظف يضبطها بمسار «نسيت كلمة المرور» المعتاد — كلمةُ مرور
        تعبر استجابةَ API تُكتب في سجلٍّ ما، وتبقى فيه.
        """
        from django.contrib.auth.models import User

        from core.modules import require_module
        from tenants.models import UserCompanyMembership

        from .suite import MODULE_KEY

        tenant = require_module(request, MODULE_KEY)
        require_perm(request, 'admin.members.manage', tenant=tenant)
        employee = self.get_object()

        if request.data.get('detach'):
            employee.user = None
            employee.save(update_fields=['user'])
            return Response(EmployeeSerializer(employee, context=self.get_serializer_context()).data)

        username = str(request.data.get('username') or '').strip()
        if not username:
            raise ValidationError({'username': 'اسم المستخدم مطلوب.'})

        with transaction.atomic():
            user = User.objects.filter(username__iexact=username).first()
            created = False
            if user is None:
                user = User.objects.create(username=username, first_name=employee.name[:150])
                user.set_unusable_password()
                user.save()
                created = True
            taken = Employee.objects.filter(tenant=tenant, user=user).exclude(pk=employee.pk)
            if taken.exists():
                raise ValidationError(
                    {'username': 'هذا المستخدم مرتبط بموظف آخر في هذه الشركة.'})
            UserCompanyMembership.objects.get_or_create(
                user=user, tenant=tenant, defaults={'role': 'ess'})
            employee.user = user
            employee.save(update_fields=['user'])

        logger.info('hr.ess_access employee=%s user=%s created=%s',
                    employee.pk, user.pk, created)
        payload = EmployeeSerializer(employee, context=self.get_serializer_context()).data
        payload['ess_user_created'] = created
        return Response(payload)

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """كشف حساب الموظف: كشوفه، صرفه، ورصيده الحالي."""
        employee = self.get_object()
        payslips = employee.payslips.all()[:200]
        payments = employee.payroll_payments.select_related('cash_account')[:200]
        return Response({
            'employee': EmployeeSerializer(employee).data,
            'payslips': PayslipSerializer(payslips, many=True).data,
            'payments': PayrollPaymentSerializer(payments, many=True).data,
            'balance': str(payroll.employee_balance(employee)),
        })


class WorkLogViewSet(PayrollViewSetBase):
    """ساعات العمل اليومية — سجلّ الموظف الجزئي."""
    queryset = WorkLog.objects.select_related('employee').all()
    serializer_class = WorkLogSerializer

    def get_queryset(self):
        return self._filter_by_employee_and_period(super().get_queryset())

    def perform_create(self, serializer):
        employee = serializer.validated_data['employee']
        log = serializer.save(tenant=self._tenant())
        logger.info('payroll.work_log_created employee=%s date=%s hours=%s',
                    employee.pk, log.date, log.hours)


class AttendanceAdjustmentViewSet(PayrollViewSetBase):
    """الغيابات والتأخيرات — سجلّ الموظف الدائم."""
    queryset = AttendanceAdjustment.objects.select_related('employee').all()
    serializer_class = AttendanceAdjustmentSerializer

    def get_queryset(self):
        qs = self._filter_by_employee_and_period(super().get_queryset())
        kind = self.request.query_params.get('kind')
        if kind in (AttendanceAdjustment.KIND_ABSENCE, AttendanceAdjustment.KIND_LATE):
            qs = qs.filter(kind=kind)
        return qs

    def perform_create(self, serializer):
        adjustment = serializer.save(tenant=self._tenant())
        logger.info('payroll.adjustment_created employee=%s kind=%s date=%s',
                    adjustment.employee_id, adjustment.kind, adjustment.date)


class PayslipViewSet(PayrollViewSetBase):
    """كشوف الرواتب — الاحتساب خادميّ دائماً، والترحيل بصلاحيته الخاصة."""
    queryset = Payslip.objects.select_related('employee').prefetch_related('payments').all()
    serializer_class = PayslipSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        if params.get('status') in (Payslip.STATUS_DRAFT, Payslip.STATUS_POSTED):
            qs = qs.filter(status=params['status'])
        month = params.get('month')
        if month:
            bounds = _month_bounds(month)
            if bounds:
                qs = qs.filter(period_start__gte=bounds[0], period_start__lt=bounds[1])
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            payslip = serializer.save(tenant=self._tenant())
            payroll.apply_computation(payslip)
            payslip.save()
        logger.info('payroll.payslip_created employee=%s period=%s..%s net=%s',
                    payslip.employee_id, payslip.period_start, payslip.period_end, payslip.net)

    def perform_update(self, serializer):
        if serializer.instance.status == Payslip.STATUS_POSTED:
            raise ValidationError('الكشف مرحّل — ألغِ ترحيله قبل تعديله.')
        with transaction.atomic():
            payslip = serializer.save()
            payroll.apply_computation(payslip)
            payslip.save()
        logger.info('payroll.payslip_updated payslip=%s net=%s', payslip.pk, payslip.net)

    def perform_destroy(self, instance):
        if instance.status == Payslip.STATUS_POSTED:
            raise ValidationError('الكشف مرحّل — ألغِ ترحيله قبل حذفه.')
        payslip_id = instance.pk
        instance.delete()
        logger.info('payroll.payslip_deleted payslip=%s', payslip_id)

    @action(detail=False, methods=['get'])
    def preview(self, request):
        """أرقام الفترة قبل حفظ الكشف — نفس دالة الاحتساب التي يستعملها الحفظ.

        `?employee=&period_start=&period_end=` (+`allowances`/`other_deductions`).
        """
        tenant = self._tenant()
        employee_id = request.query_params.get('employee')
        employee = Employee.objects.filter(tenant=tenant, pk=employee_id).first()
        if employee is None:
            raise ValidationError({'employee': 'الموظف غير موجود في هذه الشركة.'})
        try:
            start = _date.fromisoformat(request.query_params.get('period_start', ''))
            end = _date.fromisoformat(request.query_params.get('period_end', ''))
        except ValueError:
            raise ValidationError({'period_start': 'تاريخ الفترة غير صالح (YYYY-MM-DD).'})
        numbers = payroll.compute_payslip(
            employee, start, end,
            allowances=request.query_params.get('allowances') or 0,
            other_deductions=request.query_params.get('other_deductions') or 0,
        )
        return Response({key: str(value) for key, value in numbers.items()})

    @action(detail=True, methods=['post'])
    def post_slip(self, request, pk=None):
        require_perm(request, PERM_POST)
        payslip = payroll.post_payslip(self.get_object(), user=request.user)
        return Response(self.get_serializer(payslip).data)

    @action(detail=True, methods=['post'])
    def unpost(self, request, pk=None):
        require_perm(request, PERM_POST)
        payslip = self.get_object()
        payroll.unpost_payslip(payslip, user=request.user)
        payslip.refresh_from_db()
        return Response(self.get_serializer(payslip).data)


class PayrollPaymentViewSet(PayrollViewSetBase):
    """صرف الرواتب — يُرحَّل فور الحفظ كسندَي القبض والصرف، ويُلغى بحذفه."""
    queryset = PayrollPayment.objects.select_related('employee', 'cash_account').all()
    serializer_class = PayrollPaymentSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # الصرف يمسّ الدفاتر مباشرةً — صلاحية الترحيل لا الإدخال.
        if request.method not in _READ_METHODS:
            require_perm(request, PERM_POST)

    def get_queryset(self):
        return self._filter_by_employee_and_period(super().get_queryset())

    def perform_create(self, serializer):
        tenant = self._tenant()
        # الحفظ والترحيل صفقة واحدة: سندٌ محفوظٌ بلا قيد أسوأ من سندٍ لم يُحفظ.
        with transaction.atomic():
            payment = serializer.save(
                tenant=tenant,
                created_by=self.request.user if self.request.user.is_authenticated else None,
            )
            payroll.post_payroll_payment(payment, user=self.request.user)

    def perform_destroy(self, instance):
        payment_id = instance.pk
        with transaction.atomic():
            payroll.unpost_payroll_payment(instance, user=self.request.user)
            instance.delete()
        logger.info('payroll.payment_deleted payment=%s', payment_id)

    def update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'سند الصرف مرحّل — احذفه وأنشئ غيره بدل تعديله.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)
