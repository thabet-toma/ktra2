"""السطح العام — يُدرَج **مرتين** في `core/urls.py`: تحت `s/` وتحت `api/share/`.

nginx على الإنتاج يخدم الـSPA من القرص ويمرّر `/api/` وحده إلى جانغو، فمسار
`/s/<token>` القصير يحتاج سطر `location` جديداً هناك. حتى يُضاف، يعمل
`/api/share/<token>/` فوراً بلا لمس السيرفر — فلا ميزة معطَّلة بانتظار إعداد.
"""
from django.urls import path

from docshare.views import DocShareDecisionView, DocSharePublicView

urlpatterns = [
    path("<str:token>/decision/", DocShareDecisionView.as_view(), name="docshare-decision"),
    path("<str:token>/", DocSharePublicView.as_view(), name="docshare-public"),
    # وبلا شرطة مائلة أخيرة أيضاً: الرابط المنسوخ إلى واتساب أقصر وأنظف، ولا
    # نتّكل على تحويل `APPEND_SLASH` لأنه يحوّل POST إلى GET ويُفقِد جسم الطلب.
    path("<str:token>", DocSharePublicView.as_view(), name="docshare-public-bare"),
]
