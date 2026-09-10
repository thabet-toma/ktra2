"""مساراتُ الوحدة **الموجَّهةُ للزبون** — خارج `/api/platform/` عمداً (م٧).

`/api/platform/` سطحُ السوبر أدمن، وعقدُه مكتوبٌ في `core/urls.py` ويحرسه
`PlatformRouteGuardTest`: **لا نقطةَ تحته تُقرأ بغير سوبر أدمن**. ونقاطُ م٧ ثلاثٌ
لا ينطبق عليها ذلك: تبويبُ «من يمسك دفاتري» لصاحب الشركة، والتقييمُ اليوميّ له،
والرابطُ اليوميُّ العامُّ الذي يُفتح **بلا تسجيل دخولٍ أصلاً**.

فمكانُها سطحُ المستأجرين، تماماً كما فصلت `docshare` مساراتِها العامّة في
`urls_public.py` عن مساراتها المحروسة.
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import DailyRatingViewSet, PublicDailyRatingView, TenantAgentBooksViewSet

router = SimpleRouter()
router.register("daily-ratings", DailyRatingViewSet, basename="tenant-daily-ratings")
#: بادئةٌ خالية: `/api/my-agent/` نفسُه هو التبويب، و`suspend/` إجراؤه الوحيد.
router.register("", TenantAgentBooksViewSet, basename="tenant-my-agent")

urlpatterns = [
    path("ratings/public/<str:token>/", PublicDailyRatingView.as_view(), name="tenant-public-rating"),
    path("", include(router.urls)),
]
