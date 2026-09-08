"""مسارات متابعة الموظفين.

SimpleRouter (لا DefaultRouter — الأخير يولّد فهرساً غير محروس بـ require_module).
الإعدادات موردٌ مفردٌ بمسارٍ صريح، والمسار العام لقبول الدعوة صريح كذلك.
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from employee_ops.views import (
    AcceptInvitationPublicView,
    AttendanceCheckInView,
    EmployeeInvitationViewSet,
    EmployeeNoteViewSet,
    EmployeeOpsSettingsViewSet,
    EmployeeViewSet,
    LeaderboardView,
    PointViewSet,
    TaskSubmissionViewSet,
    TaskViewSet,
)

router = SimpleRouter()
router.register("employees", EmployeeViewSet, basename="employee-ops-employees")
router.register("invitations", EmployeeInvitationViewSet, basename="employee-ops-invitations")
router.register("notes", EmployeeNoteViewSet, basename="employee-ops-notes")
router.register("tasks", TaskViewSet, basename="employee-ops-tasks")
router.register("submissions", TaskSubmissionViewSet, basename="employee-ops-submissions")
router.register("points", PointViewSet, basename="employee-ops-points")

urlpatterns = [
    path(
        "invitations/accept/<str:token>/",
        AcceptInvitationPublicView.as_view(),
        name="employee-ops-invitation-accept",
    ),
    path(
        "attendance/check-in/",
        AttendanceCheckInView.as_view(),
        name="employee-ops-attendance-check-in",
    ),
    path(
        "leaderboard/",
        LeaderboardView.as_view(),
        name="employee-ops-leaderboard",
    ),
    path(
        "settings/",
        EmployeeOpsSettingsViewSet.as_view(
            {"get": "list", "put": "update", "patch": "partial_update"}
        ),
        name="employee-ops-settings",
    ),
    path("", include(router.urls)),
]
