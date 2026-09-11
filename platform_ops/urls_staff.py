"""سؤالُ المستخدم عن قدراته على المنصّة — خارج `/api/platform/` عمداً (#207 م٨-ب).

`/api/platform/` سطحُ السوبر أدمن وحارسُه يعدّ مساراتِه كلَّها، فلا مكانَ فيه
لنقطةٍ يسألها كلُّ مستخدمٍ مصادَقٍ عن نفسه. ومكانُها ليس `/api/my-agent/` أيضاً:
ذلك سطحُ صاحب الشركة، ومسؤولُ التوظيف قد لا تكون له شركة.
"""
from django.urls import path

from .views import PlatformStaffCapabilitiesView

urlpatterns = [
    path("me/", PlatformStaffCapabilitiesView.as_view(), name="platform-staff-me"),
]
