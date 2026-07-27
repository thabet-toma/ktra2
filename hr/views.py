import logging
from datetime import date as _date
from decimal import Decimal

from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Task, TaskSubmission, AttendanceRecord, PointsHistory, PersonalExpense
from .serializers import (
    TaskSerializer, TaskSubmissionSerializer, AttendanceRecordSerializer,
    PointsHistorySerializer, PersonalExpenseSerializer,
)
from core.mixins import BaseTenantViewSet
from core.tenant_utils import get_tenant

logger = logging.getLogger(__name__)


class TaskViewSet(BaseTenantViewSet):
    queryset = Task.objects.all().order_by('-created_at')
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant} if tenant else {}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
        serializer.save(**kwargs)

    @action(detail=True, methods=['post'])
    def add_submission(self, request, pk=None):
        task = self.get_object()
        data = request.data.copy()
        data['task'] = task.id
        if request.user.is_authenticated:
            data['user'] = request.user.id
            
        serializer = TaskSubmissionSerializer(data=data)
        if serializer.is_valid():
            serializer.save(task=task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AttendanceRecordViewSet(BaseTenantViewSet):
    queryset = AttendanceRecord.objects.all().order_by('-date')
    serializer_class = AttendanceRecordSerializer

class PointsHistoryViewSet(BaseTenantViewSet):
    queryset = PointsHistory.objects.all().order_by('-date')
    serializer_class = PointsHistorySerializer


def _month_bounds(month: str):
    """'YYYY-MM' → (أول الشهر، آخره)؛ None إن كانت الصيغة غير صالحة."""
    try:
        year, mon = month.split('-')
        first = _date(int(year), int(mon), 1)
    except (ValueError, AttributeError):
        return None
    last = _date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, last


class PersonalExpenseViewSet(viewsets.ModelViewSet):
    """مصاريف المستخدم الشخصية — معزولة عنه وحده، بلا أي أثر محاسبي.

    - **العزل**: كل استعلام يبدأ من `user=request.user`؛ لا رؤية ولا تعديل ولا
      حذف لمصاريف غيره، ومدير الشركة ليس استثناءً (لذا 404 لا 403).
    - **بلا TenantRolePermission**: هذه ليست دفاتر الشركة، فقيد «مستعرض قراءة
      فقط» لا محل له هنا — لكل مستخدم مصادَق عليه دفتره.
    - الفلاتر: `?month=YYYY-MM` أو `?from=&?to=` · `?category=` · `?is_paid=`.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PersonalExpenseSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PersonalExpense.objects.none()
        qs = PersonalExpense.objects.filter(user=user).order_by('-date', '-id')

        params = self.request.query_params
        month = params.get('month')
        if month:
            bounds = _month_bounds(month)
            if bounds:
                qs = qs.filter(date__gte=bounds[0], date__lt=bounds[1])
        if params.get('from'):
            qs = qs.filter(date__gte=params['from'])
        if params.get('to'):
            qs = qs.filter(date__lte=params['to'])
        if params.get('category'):
            qs = qs.filter(category=params['category'])
        is_paid = params.get('is_paid')
        if is_paid in ('true', 'false'):
            qs = qs.filter(is_paid=is_paid == 'true')
        return qs

    def perform_create(self, serializer):
        expense = serializer.save(user=self.request.user)
        # بلا عنوان ولا مبلغ — دفتر شخصي، السجل للتتبّع لا للمحتوى.
        logger.info('personal_expense.create id=%s user=%s', expense.id, self.request.user.pk)

    def perform_update(self, serializer):
        expense = serializer.save()
        logger.info('personal_expense.update id=%s user=%s', expense.id, self.request.user.pk)

    def perform_destroy(self, instance):
        expense_id = instance.id
        instance.delete()
        logger.info('personal_expense.delete id=%s user=%s', expense_id, self.request.user.pk)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """خلاصة الفترة المعروضة: الإجمالي، المدفوع، غير المدفوع، وتوزيع الفئات."""
        qs = self.filter_queryset(self.get_queryset())
        zero = Decimal('0.00')

        def money(value):
            return str((value or zero).quantize(Decimal('0.01')))

        paid = qs.filter(is_paid=True).aggregate(s=Sum('amount'))['s']
        unpaid = qs.filter(is_paid=False).aggregate(s=Sum('amount'))['s']
        labels = dict(PersonalExpense.CATEGORY_CHOICES)
        by_category = [
            {
                'category': row['category'],
                'label': labels.get(row['category'], row['category']),
                'total': money(row['total']),
            }
            for row in qs.values('category').annotate(total=Sum('amount')).order_by('-total')
        ]
        return Response({
            'count': qs.count(),
            'total': money((paid or zero) + (unpaid or zero)),
            'paid_total': money(paid),
            'unpaid_total': money(unpaid),
            'by_category': by_category,
        })
