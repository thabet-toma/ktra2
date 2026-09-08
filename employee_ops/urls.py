"""مسارات متابعة الموظفين.

**لا راوتر في هذه المرحلة، وسبب ذلك مزدوج:**

1. `DefaultRouter` يولّد صفحة جذرٍ قابلة للتصفح **غير محروسة** بـ`require_module`،
   فتكشف وجود الوحدة لشركةٍ غير مرخّصة (نفس السبب مكتوب في `after_sales/urls.py`).
2. والإعدادات **موردٌ مفردٌ لكل شركة** لا مجموعة: راوترٌ من أيّ نوع يولّد لها
   مساراً تفصيلياً `settings/<pk>/` يقبل أيّ رقمٍ ثمّ يتجاهله ويعيد إعدادات
   الشركة الحالية — مسارٌ يكذب على من يقرأه.

الشركة تأتي من `require_module` في `initial()`، لا من المسار ولا من جسم الطلب.
"""
from django.urls import path

from employee_ops.views import EmployeeOpsSettingsViewSet

urlpatterns = [
    path(
        "settings/",
        EmployeeOpsSettingsViewSet.as_view(
            {"get": "list", "put": "update", "patch": "partial_update"}
        ),
        name="employee-ops-settings",
    ),
]
