"""مسارات متابعة الموظفين.

SimpleRouter (لا DefaultRouter — الأخير يولّد فهرساً غير محروس بـ require_module).
الإعدادات موردٌ مفردٌ بمسارٍ صريح، والمسار العام لقبول الدعوة صريح كذلك.
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from employee_ops.views import (
    AcceptInvitationPublicView,
    EmployeeInvitationViewSet,
    EmployeeOpsSettingsViewSet,
    EmployeeViewSet,
    TaskSubmissionViewSet,
    TaskViewSet,
)

router = SimpleRouter()
router.register("employees", EmployeeViewSet, basename="employee-ops-employees")
router.register("invitations", EmployeeInvitationViewSet, basename="employee-ops-invitations")
router.register("tasks", TaskViewSet, basename="employee-ops-tasks")
router.register("submissions", TaskSubmissionViewSet, basename="employee-ops-submissions")

urlpatterns = [
    path(
        "invitations/accept/<str:token>/",
        AcceptInvitationPublicView.as_view(),
        name="employee-ops-invitation-accept",
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
