"""مصادقة مفاتيح قنوات الاستقبال لعمليات المنصة (المرحلة الرابعة م٤).

قواعد المصادقة:
1. المصادقة بالمفتاح حصراً (لا بجلسة ولا بتوكن مستخدم عادي).
2. استخراج الرمز الخام من ترويسة `X-Integration-Key` أو `Authorization: Api-Key <token>` / `Bearer <token>` — بمخطَّط صريح لا غير.
3. التحقق من التجزئة وحالة المفتاح (نشط / مبطل) عبر طبقة الخدمات.
4. المفتاح المبطل يُرفض فوراً برسالة صريحة.
"""
from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission

from .models import IntegrationKey
from .services import authenticate_integration_key


class IntegrationKeyAuthentication(BaseAuthentication):
    """صنف مصادقة خاص لنقطة الاستقبال بمفتاح القناة."""

    def authenticate_header(self, request):
        return 'ApiKey realm="api"'

    def authenticate(self, request):
        raw_token = request.META.get("HTTP_X_INTEGRATION_KEY")
        if not raw_token:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_header:
                parts = auth_header.split()
                # **بمخطَّطٍ صريحٍ فقط**: قَبولُ `Authorization: <قيمة>` عارياً يجعل أيَّ
                # ترويسةِ اعتمادٍ لأيّ نظامٍ آخر محاولةَ مصادقةٍ هنا — سطحٌ زائدٌ بلا حاجة.
                if len(parts) == 2 and parts[0].lower() in ("api-key", "apikey", "bearer"):
                    raw_token = parts[1]

        if not raw_token:
            return None

        key, reason = authenticate_integration_key(raw_token)
        if reason in ("invalid", "not_found", "missing"):
            raise exceptions.AuthenticationFailed("مفتاح القناة غير صالح.")
        if reason == "revoked":
            raise exceptions.AuthenticationFailed("مفتاح القناة مبطل وغير صالح للاستخدام.")
        if reason == "inactive":
            raise exceptions.AuthenticationFailed("مفتاح القناة غير نشط.")

        # **ولا يُوسَم `request.tenant` هنا**: كودُ الشركات في المستودع يثق بهذا الوسم،
        # ووسمُه من مفتاحِ قناةٍ خارجيّةٍ يجعل بابَ الاستقبال بابَ عزلٍ صامتاً. الشركةُ
        # تُقرأ من `request.auth.tenant` صراحةً حيث تلزم.
        return (AnonymousUser(), key)


class HasValidIntegrationKey(BasePermission):
    """حارس التحقق من وجود مفتاح قناة نشط ومصادق عليه."""

    message = "مفتاح القناة مطلوب وصالح للمصادقة."

    def has_permission(self, request, view):
        key = getattr(request, "auth", None)
        if not key or not isinstance(key, IntegrationKey):
            return False
        return key.status == IntegrationKey.Status.ACTIVE
