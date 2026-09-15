"""مسارات بوّابة التوظيف العامة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة)."""
from django.urls import path

from .views import (
    PublicApplicantReplyView,
    PublicApplicantTrackRefreshView,
    PublicApplicantTrackView,
    PublicInvitationAcceptView,
    PublicInvitationDetailView,
    PublicJobApplyView,
    PublicJobDetailView,
)

urlpatterns = [
    path("jobs/<str:token>/", PublicJobDetailView.as_view(), name="careers-job-detail"),
    path("jobs/<str:token>/apply/", PublicJobApplyView.as_view(), name="careers-job-apply"),
    # ‏#215: المتابعةُ تحت رمز الوظيفة نفسِه — «نفس رابط التسجيل» بأمر المالك.
    path("jobs/<str:token>/track/", PublicApplicantTrackView.as_view(), name="careers-track"),
    path("track/refresh/", PublicApplicantTrackRefreshView.as_view(), name="careers-track-refresh"),
    path("track/reply/", PublicApplicantReplyView.as_view(), name="careers-track-reply"),
    path("invitations/<str:token>/", PublicInvitationDetailView.as_view(), name="careers-invitation-detail"),
    path("invitations/<str:token>/accept/", PublicInvitationAcceptView.as_view(), name="careers-invitation-accept"),
]
