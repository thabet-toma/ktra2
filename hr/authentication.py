"""
فئة المصادقة عبر جدول أجهزة الدخول (GitHub #168).
تحل محل DRF TokenAuthentication القياسية بنفس صيغة الترويسة:
`Authorization: Token <key>`
مع تحديث last_active_at فقط إذا مضى أكثر من 5 دقائق لتفادي الضغط على قاعدة البيانات.
"""
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication as DRFTokenAuthentication

#: نافذةُ تحديث «آخر نشاط» بالثواني. الكتابةُ مع كل طلبٍ تعني كتابةً في القاعدة
#: على **كل نداءٍ في النظام كلِّه** لأجل عمودٍ يُقرأ في شاشةٍ واحدة. والدقّةُ
#: المعروضة تصير «خلال خمس دقائق» — أدقُّ ممّا يحتاجه من يقرأ «نشِط قبل ساعتين».
LAST_ACTIVE_WINDOW_SECONDS = 300


def read_device_key(request) -> str:
    """المفتاحُ من ترويسة `Authorization: Token <مفتاح>` — أو نصٌّ فارغ."""
    return request.headers.get("Authorization", "").replace("Token ", "").strip()


def touch_last_active(device) -> None:
    """يُحدِّث «آخر نشاط» إن تجاوز عمرُه النافذة — وإلّا يسقط من المسار الحارّ.

    مصدرٌ واحدٌ للقاعدة: كانت النافذةُ مكتوبةً في موضعين، وقاعدةٌ في مكانين
    تتباعد بصمت (سابقةٌ في هذا المستودع: قاعدةُ احتساب رصيد المورّد).
    """
    from hr.models import UserDevice

    now = timezone.now()
    if device.last_active_at and (now - device.last_active_at).total_seconds() < LAST_ACTIVE_WINDOW_SECONDS:
        return
    UserDevice.objects.filter(pk=device.pk).update(last_active_at=now)
    device.last_active_at = now


def resolve_device(request):
    """جهازُ الدخول صاحبُ مفتاح هذا الطلب — أو `None`.

    **لا ارتدادَ إلى `authtoken_token`.** الهجرةُ الصامتة تترك الصفَّ القديم
    قائماً بنفس المفتاح إلى جانب صفِّ الجهاز — وهي حالُ كلِّ مستخدمٍ قائمٍ يوم
    النشر. فقبولُه هنا يجعله مفتاحاً هيكليّاً يُحيي جهازاً أُبطل: يخرج المستخدمُ
    فلا يخرج، ويُخرج جهازاً فيعود. جدولُ الأجهزة وحدَه مصدرُ الحقيقة.
    """
    from hr.models import UserDevice

    key = read_device_key(request)
    if not key:
        return None
    return UserDevice.objects.filter(key=key).select_related("user").first()


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

        touch_last_active(device)
        return (device.user, device)
