"""واجهات برمجة تطبيقات عمليات المنصة (المرحلة الأولى).

**قراءةٌ فقط في هذه المرحلة.** تغييرُ الحالة في هذه الوحدة يمرّ بطبقة الخدمات
(`platform_ops/services.py`) لا بـ`ModelViewSet` عامّ: الإسنادُ وتفعيلُ الخدمة
لهما قواعدُ لا يعرفها المُسلسِل — بوّابةُ الاشتراك النشط، وفرادةُ الارتباط تحت
قفل، وسجلُّ النشاط. فنقاطُ الكتابة تُفتح في مرحلتها ومعها خدمتُها.

**ولا فلترَ شركةٍ هنا عن قصد.** قاعدةُ المستودع أنّ `get_queryset` بلا فلتر
شركة تسريبُ بيانات، وهي قاعدةُ مسارات المستأجرين. هذه مساراتُ منصّةٍ تحت
`/api/platform/` بلا `X-Tenant-Id` أصلاً، محروسةٌ بـ`IsPlatformOperationsManager`،
وغرضُها بالضبط أن يرى مديرُ العمليات كلَّ الشركات في جدولٍ واحد.
"""
from rest_framework import viewsets

from .models import Engagement, PlatformEmployee, ServiceSubscription, WorkOrder
from .permissions import IsPlatformOperationsManager, IsPlatformOperationsStaff
from .serializers import (
    PlatformEmployeeSerializer,
    ServiceSubscriptionSerializer,
    WorkOrderSerializer,
)


class PlatformEmployeeViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ موظفي عمليات المنصة — مدير العمليات فقط."""

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = PlatformEmployeeSerializer
    queryset = PlatformEmployee.objects.select_related("user").all().order_by("-created_at")


class ServiceSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ اشتراكات خدمة المتابعة — مدير العمليات فقط."""

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = ServiceSubscriptionSerializer
    queryset = ServiceSubscription.objects.select_related("tenant").all().order_by("-created_at")


class WorkOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ أوامر العمل — قراءة فقط لموظفي ومديري عمليات المنصة.

    **وهذه النقطةُ مفلترةٌ بخلاف أختَيها أعلاه، والفرقُ مقصود**: النقطتان السابقتان
    لمدير المنصّة وحدَه (`IsPlatformOperationsManager`) فيرى كلَّ شيءٍ بحكم موقعه.
    أمّا هنا فيدخل **موظّفُ المنصّة** أيضاً، وهو ليس مالكَ منصّةٍ بل موظّفُ تشغيل:
    فلو بقي `queryset` بلا فلترٍ لرأى أوامرَ **كلِّ الشركات** لا شركاتِه — وهو تسريبٌ
    عابرٌ للشركات داخل الوحدة نفسِها.

    والشركاتُ **تُشتقّ من الارتباطات النشطة** (`Engagement`) لا من الطلب: لا يقبل
    المسارُ قائمةَ شركاتٍ حرّةً، وإلّا صار البابُ الذي أُغلق.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]
    serializer_class = WorkOrderSerializer
    queryset = (
        WorkOrder.objects.select_related("tenant", "assignee__user", "created_by")
        .all()
        .order_by("-created_at")
    )

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # مديرُ المنصّة يرى كلَّ شيء — هو صاحبُ المنصّة لا موظّفٌ فيها.
        if IsPlatformOperationsManager().has_permission(self.request, self):
            return qs

        # وموظّفُ المنصّة يرى شركاتِ ارتباطاتِه النشطة وحدَها.
        engaged_tenant_ids = Engagement.objects.filter(
            employee__user=user,
            status=Engagement.Status.ACTIVE,
        ).values_list("tenant_id", flat=True)
        return qs.filter(tenant_id__in=engaged_tenant_ids)
