"""واجهة العقود ومسير الرواتب (`hr_suite`).

**العقد يتحرّك بأفعالٍ لا بـ`PATCH` على حالته**: `activate` يحرس قاعدة «عقد
نشط واحد لكل موظف»، و`terminate` يُنهيه بتاريخ. حالةٌ تُكتب مباشرةً تتخطّى
الحارسين معاً وتترك موظفاً بعقدين نشطين — ورقمين للراتب.

**والمسير لا يخترع حساباً**: كل قسيمة فيه تمرّ بـ`compute_payslip` و
`post_payslip` نفسيهما اللذين تمرّ بهما القسيمة المفردة. ما يضيفه المسير هو
الوعاء والدفعة، لا طريقةً ثانية لاحتساب المال.
"""
import logging

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.activity import log_activity

from . import payroll
from .contracts import EXPIRY_WARNING_DAYS, expiring_contracts
from .models import Contract, Employee, PayrollRun, Payslip
from .serializers import ContractSerializer, PayrollRunSerializer, PayslipSerializer
from .suite import (
    PERM_CONTRACTS_MANAGE, PERM_CONTRACTS_VIEW, HrSuiteViewSetBase,
)

logger = logging.getLogger(__name__)

#: سقف الموظفين في مسير واحد — حلقةٌ أطول من هذا داخل طلب HTTP تُعلّقه.
MAX_RUN_EMPLOYEES = 500


class ContractViewSet(HrSuiteViewSetBase):
    """عقود الموظفين — مصدر أرقام الراتب حين تكون نشطة."""

    queryset = Contract.objects.select_related('employee').prefetch_related('components')
    serializer_class = ContractSerializer
    perm_read = PERM_CONTRACTS_VIEW
    perm_write = PERM_CONTRACTS_MANAGE

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        expiring = params.get('expiring')
        if str(expiring or '').isdigit():
            ids = [row.pk for row in expiring_contracts(
                self.tenant.pk, within_days=int(expiring))]
            qs = qs.filter(pk__in=ids)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=self.tenant, created_by=self.request.user)
        log_activity(
            action='create', entity_type='hr_contract', entity_id=serializer.instance.pk,
            entity_label=serializer.instance.employee.name,
            description='إنشاء عقد', request=self.request,
        )

    def perform_update(self, serializer):
        """العقد النشط يُعدَّل بحذر: تعديل أرقامه يغيّر رواتب قادمة.

        والقسائم المرحّلة محميّةٌ بلقطاتها — لا يُعاد كتابة تاريخٍ رُحِّل.
        """
        serializer.save()
        log_activity(
            action='update', entity_type='hr_contract', entity_id=serializer.instance.pk,
            entity_label=serializer.instance.employee.name,
            description='تعديل عقد', request=self.request,
        )

    def perform_destroy(self, instance):
        if instance.status == Contract.STATUS_ACTIVE:
            raise ValidationError(
                {'detail': 'لا يُحذف عقدٌ نشط — أنهِه أولاً ثم احذفه إن لزم.'})
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """يفعّل العقد — ولا يُترك للموظف عقدان نشطان.

        العقد السابق يصير «منتهياً» تلقائياً: تركُه نشطاً كان يجعل
        `effective_terms` تختار أحدهما بالترتيب وحده، فيتغيّر الراتب بترتيب
        صفوفٍ لا بقرار.
        """
        contract = self.get_object()
        if contract.status == Contract.STATUS_ACTIVE:
            raise ValidationError({'detail': 'العقد نشطٌ بالفعل.'})

        with transaction.atomic():
            superseded = list(
                Contract.objects
                .select_for_update()
                .filter(employee=contract.employee, status=Contract.STATUS_ACTIVE)
                .exclude(pk=contract.pk)
            )
            for previous in superseded:
                previous.status = Contract.STATUS_EXPIRED
                if previous.end_date is None or previous.end_date >= contract.start_date:
                    # ينتهي عشيّة بداية الجديد — لا يومَ يغطّيه عقدان.
                    from datetime import timedelta

                    previous.end_date = contract.start_date - timedelta(days=1)
                previous.save(update_fields=['status', 'end_date', 'updated_at'])
            contract.status = Contract.STATUS_ACTIVE
            contract.save(update_fields=['status', 'updated_at'])

        log_activity(
            action='update', entity_type='hr_contract', entity_id=contract.pk,
            entity_label=contract.employee.name,
            description='تفعيل عقد', request=request,
        )
        return Response({
            **self.get_serializer(contract).data,
            'superseded': [row.pk for row in superseded],
        })

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """ينهي عقداً نشطاً بتاريخ — والراتب بعده يعود لبطاقة الموظف."""
        contract = self.get_object()
        if contract.status != Contract.STATUS_ACTIVE:
            raise ValidationError({'detail': 'لا يُنهى إلا عقدٌ نشط.'})
        raw = request.data.get('end_date')
        from django.utils.dateparse import parse_date

        end_date = parse_date(str(raw)) if raw else timezone.localdate()
        if end_date is None:
            raise ValidationError({'end_date': 'تاريخ غير صالح.'})
        if end_date < contract.start_date:
            raise ValidationError({'end_date': 'تاريخ الإنهاء قبل بداية العقد.'})

        contract.status = Contract.STATUS_TERMINATED
        contract.end_date = end_date
        contract.notes = (str(request.data.get('notes') or contract.notes))[:2000]
        contract.save(update_fields=['status', 'end_date', 'notes', 'updated_at'])
        log_activity(
            action='update', entity_type='hr_contract', entity_id=contract.pk,
            entity_label=contract.employee.name,
            description='إنهاء عقد', request=request,
        )
        return Response(self.get_serializer(contract).data)

    @action(detail=False, methods=['get'])
    def alerts(self, request):
        """تنبيه انتهاء العقود — **محسوبٌ بلا مجدول**.

        لا cron في هذه المنصة، فالتنبيه سؤالٌ يُطرح عند فتح الشاشة لا رسالةٌ
        تُرسَل ليلاً. ثمنُه أن من لا يفتح التطبيق لا يُنبَّه — مقبولٌ مقابل
        ألّا نعلّق ميزةً على بنيةٍ غير موجودة.
        """
        within = request.query_params.get('within')
        within = int(within) if str(within or '').isdigit() else EXPIRY_WARNING_DAYS
        rows = expiring_contracts(self.tenant.pk, within_days=within)
        return Response({
            'within_days': within,
            'count': len(rows),
            'contracts': [
                {
                    'id': row.pk,
                    'employee': row.employee_id,
                    'employee_name': row.employee.name,
                    'end_date': row.end_date,
                    'days_to_expiry': row.days_to_expiry,
                }
                for row in rows
            ],
        })


class PayrollRunViewSet(HrSuiteViewSetBase):
    """مسير الرواتب — احتساب قسائم فترةٍ لمجموعة، ثم ترحيلها دفعةً."""

    queryset = PayrollRun.objects.select_related('branch', 'department')
    serializer_class = PayrollRunSerializer
    perm_read = 'hr.payroll.view'
    perm_write = 'hr.payroll.manage'
    action_perms = {
        'post_run': 'hr.payroll.post',
        'unpost_run': 'hr.payroll.post',
    }

    def get_queryset(self):
        return super().get_queryset().annotate(
            payslip_count=Count('payslips', distinct=True),
            total_net=Sum('payslips__net'),
        )

    def perform_create(self, serializer):
        serializer.save(tenant=self.tenant, created_by=self.request.user)

    def perform_destroy(self, instance):
        """المسير المرحَّل لا يُحذف — قسائمه في الدفاتر."""
        if instance.status == PayrollRun.STATUS_POSTED:
            raise ValidationError(
                {'detail': 'لا يُحذف مسيرٌ مرحَّل — ألغِ ترحيله أولاً.'})
        # القسائم المسودّة تُحرَّر من الوعاء ولا تُحذف معه.
        instance.payslips.update(run=None)
        super().perform_destroy(instance)

    def _scope_employees(self, run):
        qs = Employee.objects.filter(tenant=self.tenant, is_active=True)
        if run.branch_id:
            qs = qs.filter(branch_id=run.branch_id)
        if run.department_id:
            qs = qs.filter(department_id=run.department_id)
        return qs.order_by('name')[:MAX_RUN_EMPLOYEES]

    @action(detail=True, methods=['post'])
    def compute(self, request, pk=None):
        """يحتسب قسيمةً لكل موظف في نطاق المسير — ويعيد احتساب مسودّاته.

        القسيمة المرحّلة **لا تُمَسّ** ولو أُعيد الاحتساب: مجمَّدةٌ بقاعدة
        قائمة في المحرّك، وهذا الزرّ لا يستثنيها.

        وموظفٌ له قسيمةٌ للفترة نفسها خارج هذا المسير يُتخطّى مع سببه: القيد
        الفريد (موظف، فترة) كان سيردّ 500 بدل رسالةٍ تُقرأ.
        """
        run = self.get_object()
        if run.status == PayrollRun.STATUS_POSTED:
            raise ValidationError({'detail': 'المسير مرحَّل — لا يُعاد احتسابه.'})

        created, updated, skipped = 0, 0, []
        with transaction.atomic():
            for employee in self._scope_employees(run):
                existing = Payslip.objects.filter(
                    employee=employee,
                    period_start=run.period_start,
                    period_end=run.period_end,
                ).first()
                if existing is not None and existing.run_id not in (None, run.pk):
                    skipped.append({'employee': employee.pk, 'name': employee.name,
                                    'reason': 'له كشفٌ لهذه الفترة في مسيرٍ آخر.'})
                    continue
                if existing is not None and existing.status == Payslip.STATUS_POSTED:
                    skipped.append({'employee': employee.pk, 'name': employee.name,
                                    'reason': 'كشفه لهذه الفترة مرحَّل.'})
                    continue

                slip = existing or Payslip(
                    tenant=self.tenant, employee=employee,
                    period_start=run.period_start, period_end=run.period_end,
                )
                slip.run = run
                payroll.apply_computation(slip)
                slip.save()
                if existing is None:
                    created += 1
                else:
                    updated += 1

            run.status = PayrollRun.STATUS_COMPUTED
            run.save(update_fields=['status', 'updated_at'])

        return Response({'created': created, 'updated': updated, 'skipped': skipped})

    @action(detail=True, methods=['post'], url_path='post')
    def post_run(self, request, pk=None):
        """يرحّل كل مسودّات المسير — والفاشلة تُبلَّغ ولا تُسقط الباقي.

        ترحيلٌ يتوقّف عند أول قسيمةٍ صافيها صفر كان يترك المسير نصفه مرحَّلاً
        ونصفه لا، ولا يقول أين وقف.
        """
        run = self.get_object()
        posted, failed = 0, []
        for slip in run.payslips.filter(status=Payslip.STATUS_DRAFT).select_related('employee'):
            try:
                with transaction.atomic():
                    payroll.post_payslip(slip, user=request.user)
                posted += 1
            except ValidationError as exc:
                failed.append({'payslip': slip.pk, 'employee_name': slip.employee.name,
                               'reason': str(exc.detail)})

        if posted and not run.payslips.filter(status=Payslip.STATUS_DRAFT).exists():
            run.status = PayrollRun.STATUS_POSTED
            run.posted_at = timezone.now()
            run.save(update_fields=['status', 'posted_at', 'updated_at'])

        log_activity(
            action='post', entity_type='hr_payroll_run', entity_id=run.pk,
            entity_label=str(run), description=f'ترحيل مسير رواتب ({posted} كشفاً)',
            request=request,
        )
        run.refresh_from_db()
        return Response({'posted': posted, 'failed': failed,
                         'status': run.status})

    @action(detail=True, methods=['post'], url_path='unpost')
    def unpost_run(self, request, pk=None):
        """يلغي ترحيل قسائم المسير — والمصروف منها يمنع نفسه برسالته."""
        run = self.get_object()
        reverted, failed = 0, []
        for slip in run.payslips.filter(status=Payslip.STATUS_POSTED).select_related('employee'):
            try:
                with transaction.atomic():
                    payroll.unpost_payslip(slip, user=request.user)
                reverted += 1
            except ValidationError as exc:
                failed.append({'payslip': slip.pk, 'employee_name': slip.employee.name,
                               'reason': str(exc.detail)})

        if reverted and not run.payslips.filter(status=Payslip.STATUS_POSTED).exists():
            run.status = PayrollRun.STATUS_COMPUTED
            run.posted_at = None
            run.save(update_fields=['status', 'posted_at', 'updated_at'])

        log_activity(
            action='unpost', entity_type='hr_payroll_run', entity_id=run.pk,
            entity_label=str(run), description=f'إلغاء ترحيل مسير ({reverted} كشفاً)',
            request=request,
        )
        run.refresh_from_db()
        return Response({'reverted': reverted, 'failed': failed, 'status': run.status})

    @action(detail=True, methods=['get'])
    def payslips(self, request, pk=None):
        """قسائم المسير — تُقرأ بمُسلسِل القسيمة نفسه، لا بشكلٍ ثانٍ."""
        run = self.get_object()
        rows = run.payslips.select_related('employee').prefetch_related('payments')
        return Response(PayslipSerializer(rows, many=True).data)
