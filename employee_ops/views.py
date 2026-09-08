"""API متابعة الموظفين — إعدادات الوحدة (المرحلة الأولى: الأساس).

ترتيب البوابتين مقصود ومُلزِم: `require_module` **قبل** `require_perm`،
فترد الشركة غير المرخّصة **404 لا 403** — 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً.
والشركة تأتي من الحارس نفسه، لا من جسم الطلب.
"""
from django.http import Http404
from rest_framework import viewsets
from rest_framework.response import Response

from core.access import require_perm
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module

from .serializers import EmployeeOpsSettingsSerializer
from .services import MODULE_KEY, get_or_create_settings, settings_for_read

PERM_MANAGE = "employee_ops.manage"

# الأفعال المتاحة وحدها — والمسار يربطها صراحةً في `urls.py`. مفتاحٌ لفعلٍ
# غير مربوطٍ هنا يعني حارساً لبابٍ لا وجود له.
#
# **والقراءة للمدير كذلك لا للموظف**: هذه أرقامُ ضبطٍ للشركة (قيم النقاط وسقفها
# ومدّة الاحتفاظ)، وقصّة المواصفة رقم ٢٩ تجعل ضبطها للمدير. ما يحتاجه الموظف من
# أرقامٍ يأتيه مع شاشته لا من هنا.
_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "update": PERM_MANAGE,
    "partial_update": PERM_MANAGE,
}


class EmployeeOpsSettingsViewSet(viewsets.ViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        # **فشلٌ مغلق لا مفتوح**: فعلٌ بلا مفتاحٍ في الجدول يُردّ، ولا يمرّ بلا
        # حارس. النمط الشائع في المستودع (`.get` ثمّ `if required`) يترك أيّ
        # `@action` تُضاف لاحقاً بلا صلاحية بصمت — وهذه وحدةٌ سببُ وجودها ألّا
        # تُسرّب شيئاً.
        required = _ACTION_PERMS.get(self.action)
        if required is None:
            raise Http404
        require_perm(request, required, tenant=self.tenant)

    def list(self, request):
        serializer = EmployeeOpsSettingsSerializer(settings_for_read(self.tenant))
        return Response(serializer.data)

    def update(self, request):
        return self._save(request, partial=False)

    def partial_update(self, request):
        return self._save(request, partial=True)

    def _save(self, request, *, partial: bool):
        settings_obj = get_or_create_settings(self.tenant)
        serializer = EmployeeOpsSettingsSerializer(
            settings_obj, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
