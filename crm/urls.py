"""مسارات نواة الـCRM تحت `/api/platform/crm/`."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import LeadTransferViewSet, LeadViewSet, ManagerLeadOverviewView, MyLeadStatsView

router = SimpleRouter()
router.register("leads", LeadViewSet, basename="crm-leads")
router.register("transfer-requests", LeadTransferViewSet, basename="crm-transfer-requests")

urlpatterns = [
    path("stats/me/", MyLeadStatsView.as_view(), name="crm-stats-me"),
    path("stats/overview/", ManagerLeadOverviewView.as_view(), name="crm-stats-overview"),
    path("", include(router.urls)),
]
