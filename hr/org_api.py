"""الهيكل التنظيمي — الأقسام والمسميات الوظيفية (`hr_suite`).

القسم والمسمّى ليسا زينةً في ملف الموظف: عليهما يُوجَّه اعتمادُ الطلبات
(`ApprovalRule`)، وبهما يُصفّى مسير الرواتب والتقارير. ولذلك الحذف محروس —
قسمٌ يحمل موظفين أو أقساماً تابعة يُعطَّل ولا يُمحى، وإلا انقطع أثرُ كل ما
وُجّه به سابقاً.
"""
import logging

from django.db.models import Count, Q
from rest_framework.exceptions import ValidationError

from core.activity import log_activity
from .models import Department, Employee, JobTitle
from .serializers import DepartmentSerializer, JobTitleSerializer
from .suite import PERM_ATTENDANCE_VIEW, PERM_ORG, HrSuiteViewSetBase

logger = logging.getLogger(__name__)


class OrgViewSetBase(HrSuiteViewSetBase):
    """القراءة لمن يرى شاشة الحضور، والتحرير لمن يملك الهيكل التنظيمي."""

    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_ORG

    def _filter_active(self, qs):
        active = self.request.query_params.get('active')
        if active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        elif active in ('0', 'false', 'False'):
            qs = qs.filter(is_active=False)
        search = str(self.request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class DepartmentViewSet(OrgViewSetBase):
    """الأقسام — شجرةٌ مسطّحة تُرسل بأبنائها، والواجهة تبنيها."""

    queryset = Department.objects.select_related('parent', 'branch', 'manager').all()
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            employees_count=Count('employees', filter=Q(employees__is_active=True), distinct=True),
        )
        return self._filter_active(qs)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(
            action='create', entity_type='hr_department',
            entity_id=serializer.instance.pk, entity_label=serializer.instance.name,
            description='إنشاء قسم', request=self.request,
        )

    def perform_update(self, serializer):
        serializer.save()
        log_activity(
            action='update', entity_type='hr_department',
            entity_id=serializer.instance.pk, entity_label=serializer.instance.name,
            description='تعديل قسم', request=self.request,
        )

    def perform_destroy(self, instance):
        """قسمٌ مشغول يُعطَّل ولا يُمحى — الحذف يقطع أثر ما وُجّه به."""
        if instance.employees.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف قسم يضمّ موظفين — عطّله بدل حذفه.'})
        if instance.children.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف قسم يتبعه أقسام — انقل أو احذف التابعة أولاً.'})
        label = instance.name
        pk = instance.pk
        instance.delete()
        log_activity(
            action='delete', entity_type='hr_department', entity_id=pk,
            entity_label=label, description='حذف قسم', request=self.request,
        )


class JobTitleViewSet(OrgViewSetBase):
    """المسميات الوظيفية — قائمة مسطّحة تُربط اختياراً بقسم."""

    queryset = JobTitle.objects.select_related('department').all()
    serializer_class = JobTitleSerializer

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            employees_count=Count('employees', filter=Q(employees__is_active=True), distinct=True),
        )
        params = self.request.query_params
        if str(params.get('department') or '').isdigit():
            qs = qs.filter(department_id=params['department'])
        return self._filter_active(qs)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        log_activity(
            action='create', entity_type='hr_job_title',
            entity_id=serializer.instance.pk, entity_label=serializer.instance.name,
            description='إنشاء مسمّى وظيفي', request=self.request,
        )

    def perform_update(self, serializer):
        serializer.save()
        log_activity(
            action='update', entity_type='hr_job_title',
            entity_id=serializer.instance.pk, entity_label=serializer.instance.name,
            description='تعديل مسمّى وظيفي', request=self.request,
        )

    def perform_destroy(self, instance):
        if Employee.objects.filter(job_title_ref=instance).exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف مسمّى مستعمل لموظفين — عطّله بدل حذفه.'})
        label = instance.name
        pk = instance.pk
        instance.delete()
        log_activity(
            action='delete', entity_type='hr_job_title', entity_id=pk,
            entity_label=label, description='حذف مسمّى وظيفي', request=self.request,
        )
