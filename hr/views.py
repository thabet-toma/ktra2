import logging
from datetime import date as _date
from decimal import Decimal

from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import (
    Task, TaskSubmission, AttendanceRecord, PointsHistory, PersonalExpense,
    PersonalExpenseCategory, PersonalExpenseSheet,
)
from .serializers import (
    TaskSerializer, TaskSubmissionSerializer, AttendanceRecordSerializer,
    PointsHistorySerializer, PersonalExpenseSerializer,
    PersonalExpenseCategorySerializer, PersonalExpenseSheetSerializer,
)
from core.mixins import BaseTenantViewSet
from core.tenant_utils import get_tenant
from accountant_portal.permissions import LegalAccountantRoutePermission

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


class PersonalExpenseOwnedViewSet(viewsets.ModelViewSet):
    """أساس مشترك لبيانات الدفتر الشخصي: مصادقة، عزل بالمستخدم، ومالك من الطلب."""
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, LegalAccountantRoutePermission]
    model = None

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return self.model.objects.none()
        return self.model.objects.filter(user=user)

    def perform_create(self, serializer):
        return serializer.save(user=self.request.user)


class PersonalExpenseSheetViewSet(PersonalExpenseOwnedViewSet):
    """أوراق المصاريف — تبويبات بأسلوب إكسل، لكل مستخدم أوراقه وحده."""
    serializer_class = PersonalExpenseSheetSerializer
    model = PersonalExpenseSheet

    def list(self, request, *args, **kwargs):
        # لا دفتر بلا ورقة: أول زيارة تزرع «الورقة 1» لصاحب الطلب.
        PersonalExpenseSheet.ensure_default(request.user)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        last = self.get_queryset().order_by('-position').first()
        sheet = serializer.save(
            user=self.request.user,
            position=(last.position + 1) if last else 0,
        )
        logger.info('personal_expense_sheet.create id=%s user=%s', sheet.id, self.request.user.pk)

    def perform_update(self, serializer):
        sheet = serializer.save()
        logger.info('personal_expense_sheet.update id=%s user=%s', sheet.id, self.request.user.pk)

    def destroy(self, request, *args, **kwargs):
        sheet = self.get_object()
        if self.get_queryset().count() <= 1:
            return Response(
                {'detail': 'لا يمكن حذف الورقة الوحيدة — أعد تسميتها بدلاً من حذفها.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sheet_id = sheet.id
        sheet.delete()  # يحذف مصاريف الورقة معها (CASCADE)
        logger.info('personal_expense_sheet.delete id=%s user=%s', sheet_id, request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PersonalExpenseCategoryViewSet(PersonalExpenseOwnedViewSet):
    """كتالوج فئات المستخدم — إضافة وإعادة تسمية؛ المفتاح خادمي لا يُعدَّل."""
    serializer_class = PersonalExpenseCategorySerializer
    model = PersonalExpenseCategory

    def list(self, request, *args, **kwargs):
        PersonalExpenseCategory.ensure_defaults(request.user)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        PersonalExpenseCategory.ensure_defaults(self.request.user)
        last = self.get_queryset().order_by('-position').first()
        category = serializer.save(
            user=self.request.user,
            key=PersonalExpenseCategory.next_key(self.request.user),
            position=(last.position + 1) if last else 0,
        )
        logger.info('personal_expense_category.create id=%s user=%s', category.id, self.request.user.pk)

    def perform_update(self, serializer):
        category = serializer.save()
        logger.info('personal_expense_category.update id=%s user=%s', category.id, self.request.user.pk)

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        in_use = PersonalExpense.objects.filter(user=request.user, category=category.key).exists()
        if in_use:
            return Response(
                {'detail': 'الفئة مستعملة في مصاريف مسجّلة — انقل مصاريفها أولاً.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        category_id = category.id
        category.delete()
        logger.info('personal_expense_category.delete id=%s user=%s', category_id, request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PersonalExpenseViewSet(viewsets.ModelViewSet):
    """مصاريف المستخدم الشخصية — معزولة عنه وحده، بلا أي أثر محاسبي.

    - **العزل**: كل استعلام يبدأ من `user=request.user`؛ لا رؤية ولا تعديل ولا
      حذف لمصاريف غيره، ومدير الشركة ليس استثناءً (لذا 404 لا 403).
    - **بلا TenantRolePermission**: هذه ليست دفاتر الشركة، فقيد «مستعرض قراءة
      فقط» لا محل له هنا — لكل مستخدم مصادَق عليه دفتره.
    - الفلاتر: `?sheet=` · `?month=YYYY-MM` أو `?from=&?to=` · `?category=` · `?is_paid=`.
    """
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, LegalAccountantRoutePermission]
    serializer_class = PersonalExpenseSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PersonalExpense.objects.none()
        qs = PersonalExpense.objects.filter(user=user).order_by('-date', '-id')

        params = self.request.query_params
        if str(params.get('sheet') or '').isdigit():
            qs = qs.filter(sheet_id=params['sheet'])
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
        # مصروف بلا ورقة يسكن الورقة الأولى — لا صفوف يتيمة خارج التبويبات.
        sheet = serializer.validated_data.get('sheet') or PersonalExpenseSheet.ensure_default(self.request.user)
        expense = serializer.save(user=self.request.user, sheet=sheet)
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
        labels = PersonalExpenseCategory.label_map(request.user.pk)
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
