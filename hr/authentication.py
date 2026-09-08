"""
فئة المصادقة عبر جدول أجهزة الدخول (GitHub #168).
تحل محل DRF TokenAuthentication القياسية بنفس صيغة الترويسة:
`Authorization: Token <key>`
مع تحديث last_active_at فقط إذا مضى أكثر من 5 دقائق لتفادي الضغط على قاعدة البيانات.
"""
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication as DRFTokenAuthentication


class DeviceTokenAuthentication(DRFTokenAuthentication):
    """
    مصادقة باستخدام مفتاح جهاز الدخول UserDevice.
    الكلمة المفتاحية في ترويسة الطلب تبقى "Token" مطابقة تماماً للعقد السابق.
    """
    keyword = 'Token'

    def get_model(self):
        from hr.models import UserDevice
        return UserDevice

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            device = model.objects.select_related('user').get(key=key)
        except model.DoesNotExist:
            # ISSUE #168: **لا ارتدادَ إلى `authtoken_token`.** الهجرةُ الصامتة
            # تترك الصفَّ القديم قائماً بنفس المفتاح إلى جانب صفِّ الجهاز — وهي
            # حالُ كلِّ مستخدمٍ قائمٍ يوم النشر. فارتدادٌ إليه هنا يجعل ذلك الصفَّ
            # مفتاحاً هيكليّاً يُحيي جهازاً أُبطل: يخرج المستخدمُ فلا يخرج. جدولُ
            # الأجهزة وحدَه مصدرُ الحقيقة، والصفوفُ القديمة بياناتٌ خاملة.
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not device.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        # 8. صيانة الأداء: تحديث last_active_at فقط إذا كان القيمة أقدم من 5 دقائق (300 ثانية)
        now = timezone.now()
        if not device.last_active_at or (now - device.last_active_at).total_seconds() >= 300:
            model.objects.filter(pk=device.pk).update(last_active_at=now)
            device.last_active_at = now

        return (device.user, device)


# الاسم المستعار للتوافق مع المواضع التي تستورد TokenAuthentication صراحةً
TokenAuthentication = DeviceTokenAuthentication
