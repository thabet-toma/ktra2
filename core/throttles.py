"""خوانق مشتركة — هويّةُ الخانق بين وكيلٍ مضبوطٍ ووكيلٍ مجهول.

`ClientIpScopedThrottle` يعمل بوضعين، ويقرّرهما `DRF_NUM_PROXIES` وحده:

- **مضبوط (الإنتاج: nginx مفرد ⇒ `DRF_NUM_PROXIES=1`)**: نفوّض الهويّة إلى
  `BaseThrottle.get_ident`، فيأخذ DRF العنوانَ رقم `NUM_PROXIES` من **آخر**
  `X-Forwarded-For`. العنوانُ الذي يضيفه الوكيل الأخير آخرُ القائمة، وما قبله
  يكتبه العميل، فاختيارُ الآخِر لا يُلفَّق — ويحصل كلّ عميلٍ على دلوٍ مستقلّ.
- **غير مضبوط (الافتراضي، بلا وكيلٍ أمام التطبيق)**: `REMOTE_ADDR` وحده. DRF
  حينها يتّخذ **كامل** `X-Forwarded-For` هويّةً، فترويسةٌ واحدةٌ يكتبها العميل
  تعطيه دلواً جديداً في كلّ طلب: **٥/ساعة تصير بلا حدّ**. و`REMOTE_ADDR` خلف
  وكيلٍ عكسيٍّ يصير عنوانَ الوكيل — دلوٌ واحدٌ للجميع، وهو تشدّدٌ آمن لا
  انفلاتٌ صامت.

**ولماذا انتقلت هنا (K3):** كانت في `employee_ops/throttles.py`، و`employee_ops`
**وحدةٌ معزولة** يحرس حارسُها ألّا يستوردها ملفٌّ خارجها — وسطحُ عدّ الجرد العامّ
في `docshare` يحتاج القاعدة نفسها. فالقاعدة المشتركة تسكن `core` (الطبقة
الأساسية التي يستوردها الجميع)، ويُعيد `employee_ops.throttles` و
`platform_ops.throttles` تصديرها فلا يتغيّر مستوردٌ قائم.
"""
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle


class ClientIpScopedThrottle(ScopedRateThrottle):
    """نطاقٌ مسمّىً بهويّةٍ لا يملك العميلُ أن يختارها بترويسة."""

    def get_ident(self, request):
        if api_settings.NUM_PROXIES is not None:
            # DRF يختار العنوان رقم NUM_PROXIES من آخر الترويسة — أي العنوان
            # الذي أضافه الوكيل الأخير، لا أوّل ما كتبه العميل.
            return super().get_ident(request)
        return request.META.get("REMOTE_ADDR")
