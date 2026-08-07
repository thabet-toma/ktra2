"""
إعدادات DRF المشتركة للواجهات التي يجب أن تكون مصادقاً عليها.
يُفضّل ربط كل ViewSet حساس (محاسبة، شركاء، …) بـ Token أو جلسة Django.
"""
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
