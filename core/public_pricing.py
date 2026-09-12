"""نقطة الأسعار العامة — بلا مصادقة وبلا شركة.

**لماذا ملفٌّ مستقل:** نفس حجّة `store/views.py` و`docshare/views.py` — كل كود
`AllowAny` يعيش في مكانٍ واحدٍ يُقرأ كاملاً في جلسة، فلا يختبئ بابٌ مفتوحٌ بين
مئات الأسطر المصادَقة. النقطة الوحيدة هنا: خطط الأسعار وإضافة خدمة الإدخال،
بلا أي رقمٍ يخصّ شركةً بعينها — زائرٌ مجهولٌ يقرؤها قبل التسجيل.
"""
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.plans import DATA_ENTRY_ADDON, PLAN_CURRENCY, public_plan_rows


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_pricing_plans(request):
    """قائمة الخطط المعروضة بأسعارها وحدودها ووحداتها، وإضافة خدمة الإدخال.

    `authentication_classes = []` ليست زينة — وهي القاعدة التي تتبعها كلُّ
    نقطةٍ عامّةٍ في هذا المستودع (`store/views.py` · `docshare/views.py` ·
    `platform_ops/public_hiring/views.py`) لسببين:

    **الأوّل أنّ `AllowAny` وحدَها لا تفتح الباب.** المصادقةُ تسبق الصلاحيّة،
    ولائحةُ DRF الافتراضيّة هنا تبدأ بـ`DeviceTokenAuthentication`؛ فتوكنٌ
    قديمٌ باقٍ في `localStorage` يُرسَل مع كلّ طلبٍ من الواجهة يُرَدّ **401
    على صفحة أسعارٍ عامّة** — وهو أسوأُ من الخطأ: زائرٌ جاء يقرأ السعرَ فوجد
    «انتهت الجلسة».

    **والثاني أنّ التوكنَ لا يقدر أن يغيّر حرفاً في هذا الردّ**، فقراءتُه
    أصلاً بلا معنى. تركُها خاصيّةً بنيويّةً لا وعداً في مراجعة.
    """
    return Response({
        "currency": PLAN_CURRENCY,
        "plans": public_plan_rows(),
        # نسخةٌ لا الأصل: `DATA_ENTRY_ADDON` قاموسٌ على مستوى الوحدة يعيش طولَ
        # عمر العملية، وتسليمُه بالإشارة يجعل أيَّ تعديلٍ لاحقٍ عليه تعديلاً
        # دائماً في الذاكرة يراه كلُّ طلبٍ بعده.
        "data_entry_addon": dict(DATA_ENTRY_ADDON),
    })
