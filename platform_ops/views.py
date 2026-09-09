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

from .models import PlatformEmployee, ServiceSubscription
from .permissions import IsPlatformOperationsManager
from .serializers import PlatformEmployeeSerializer, ServiceSubscriptionSerializer


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
