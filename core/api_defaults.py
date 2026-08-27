"""
إعدادات DRF المشتركة للواجهات التي يجب أن تكون مصادقاً عليها.
يُفضّل ربط كل ViewSet حساس (محاسبة، شركاء، …) بـ Token أو جلسة Django.
"""
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import TenantRolePermission

# جلسة + توكن: الواجهة v2 ترسل Header Token؛ لوحة الإدارة / أدوات نفس الأصل قد تستخدم الجلسة.
# task11 R2-B: TenantRolePermission — دور «مستعرض» قراءة فقط.
ApiAuthAndUser = {
    "authentication_classes": [TokenAuthentication, SessionAuthentication],
    "permission_classes": [IsAuthenticated, TenantRolePermission],
}

# رسالة موحّدة تُعرض عند محاولة تعديل/حذف مستند مرحَّل قبل التراجع عن الترحيل.
# تُستهلك في فواتير المبيعات/الشراء والصفقات والشحنات والتخليص والنقل.
POSTED_DOC_WARNING = (
    "هذا المستند مرحَّل. يجب التراجع عن الترحيل قبل تعديله أو حذفه."
)


class TenantScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """P1-8 (المرحلة 5): حقل pk يقبل كائنات الشركة الحالية فقط عند الكتابة.

    `PrimaryKeyRelatedField(queryset=X.objects.all())` كان يقبل pk من أي شركة —
    `get_queryset` في الـviewset يحمي القراءة فقط، والكتابة تمرّ من الحقل
    مباشرةً. هذا المنتج يعيد تقييد الـqueryset بشركة الطلب وقت الحلّ، فيصير
    الـpk الأجنبي «غير موجود» (نفس رسالة DRF القياسية — لا يكشف وجود الكائن).

    الشركة تُحلّ من request في context (المسار الإنتاجي)، أو من
    context={"tenant": ...} للاستخدام البرمجي. غيابهما = queryset فارغ
    (fail-closed). `tenant_field` يسمّي حقل الشركة في الموديل الهدف
    (الافتراضي "tenant").
    """

    def __init__(self, *args, tenant_field: str = "tenant", **kwargs):
        self._tenant_field = tenant_field
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        from core.tenant_utils import get_tenant

        qs = super().get_queryset()
        if qs is None:  # read_only — لا حلّ للكتابة أصلاً
            return qs
        request = self.context.get("request")
        tenant = (
            get_tenant(request) if request is not None
            else self.context.get("tenant")
        )
        if tenant is None:
            return qs.none()
        return qs.filter(**{self._tenant_field: tenant})


class PagePartnerBalanceMixin:
    """رصيد الطرف في القوائم يُجلب لصفحةٍ محمَّلة، لا كاستعلام فرعي لكل صف.

    الاستعلام الفرعي المرتبط (`annotate_partner_posted_balance`) يحمل GROUP BY
    فتبني MySQL جدولاً مؤقتاً لكل صف — 15–20 ثانية على قائمة فواتير حقيقية.
    الـmixin يجعل `list` يجلب الصفحة أولاً ثم يعلّق الأرصدة باستعلام تجميعي
    واحد. مسار المستند المفتوح (`retrieve`) يبقى على الـannotate: صفٌّ واحد.

    الاستهلاك: `partner_balance_spec = ("customer_id", False, "customer_balance")`
    (اسم حقل الطرف · هل هو مورد · اسم السمة التي يقرؤها السيريالايزر).
    """

    partner_balance_spec: tuple[str, bool, str] | None = None

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page) if page is not None else list(queryset)
        spec = self.partner_balance_spec
        if spec:
            from accounting.services import attach_partner_posted_balance

            attach_partner_posted_balance(
                rows, spec[0], supplier=spec[1], attr=spec[2],
            )
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
