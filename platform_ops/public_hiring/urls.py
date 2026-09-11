"""مسارات بوّابة التوظيف العامة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة)."""
from django.urls import path

from .views import (
    PublicInvitationAcceptView,
    PublicInvitationDetailView,
    PublicJobApplyView,
    PublicJobDetailView,
)

urlpatterns = [
    path("jobs/<str:token>/", PublicJobDetailView.as_view(), name="careers-job-detail"),
    path("jobs/<str:token>/apply/", PublicJobApplyView.as_view(), name="careers-job-apply"),
    path("invitations/<str:token>/", PublicInvitationDetailView.as_view(), name="careers-invitation-detail"),
    path("invitations/<str:token>/accept/", PublicInvitationAcceptView.as_view(), name="careers-invitation-accept"),
]
