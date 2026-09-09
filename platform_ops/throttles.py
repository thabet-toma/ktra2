"""خوانق عمليات المنصة (المرحلة الرابعة: م٤)."""
from rest_framework.throttling import SimpleRateThrottle

from .models import IntegrationKey


class IntegrationKeyThrottle(SimpleRateThrottle):
    """خانقُ الاستقبال — الهويّةُ **مفتاحُ القناة** لا عنوانُ الشبكة.

    الربطُ بالمفتاح مقصود: عنوانُ IP لقناةٍ خارجيّةٍ مشتركٌ بين زبائنَ كثيرين
    (بوّابةُ واتساب واحدةٌ لكلّ الشركات)، فخانقٌ عليه يعاقب الجميعَ بذنب واحد.
    والنطاقُ مسجَّلٌ في `DEFAULT_THROTTLE_RATES` كأخواته فيُضبَط من البيئة.

    ولا احتياطيَّ بعنوان الشبكة هنا: `HasValidIntegrationKey` تسبق الخانقَ في
    دورة DRF، فلا يصل إليه طلبٌ بلا مفتاحٍ نشطٍ أصلاً — واحتياطيٌّ لا يُبلَغ
    يوهم بحمايةٍ لا توجد.
    """

    scope = "platform_ops_intake"

    def get_cache_key(self, request, view):
        key = getattr(request, "auth", None)
        if not isinstance(key, IntegrationKey) or not key.pk:
            return None  # لا خنقَ لما لا هويّةَ له — والحارسُ ردّه قبلنا أصلاً
        return self.cache_format % {"scope": self.scope, "ident": f"key_{key.pk}"}
