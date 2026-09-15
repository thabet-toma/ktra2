"""مسارُ صفحةِ الإعلان الوظيفيّ المُصيَّرةِ من الخادم (#214-أ).

ملفٌّ مستقلٌّ عن `urls.py` عمداً: ذاك سطحُ JSON للـSPA، وهذا صفحةُ HTML واحدةٌ
تُركَّب **مرّتين** في `core/urls.py` (`/j/` و`/api/careers/j/`) — وخلطُهما في
ملفٍّ واحدٍ يجعل تركيبَ أحدِهما يجرّ الآخرَ معه.
"""
from django.urls import path

from .views import PublicJobPageView

urlpatterns = [
    path("<str:token>/", PublicJobPageView.as_view(), name="careers-job-page"),
    # وبلا شرطةٍ مائلةٍ أخيرةً أيضاً — نفس حجّة `docshare/urls_public.py`:
    # الرابطُ المنسوخُ إلى فيسبوك أقصرُ وأنظف، ولا نتّكل على تحويل
    # `APPEND_SLASH` لأنّ بعضَ الزواحف لا تتبع التحويل وتقرأ الردَّ الفارغ.
    path("<str:token>", PublicJobPageView.as_view(), name="careers-job-page-bare"),
]
