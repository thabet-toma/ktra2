"""مسارات عمليات المنصة."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter
from .views import (
    CompanyHealthCheckViewSet,
    CompanyHealthView,
    CustomerAcquisitionView,
    EngagementViewSet,
    IntegrationKeyViewSet,
    JobApplicantViewSet,
    JobPostingViewSet,
    PerformanceSnapshotViewSet,
    PlatformActivityLogViewSet,
    PlatformDashboardView,
    PlatformEmployeeViewSet,
    PlatformNotificationViewSet,
    PlatformRecruiterViewSet,
    PolicyProfileViewSet,
    ServiceSubscriptionViewSet,
    ServiceUnitCatalogViewSet,
    ServiceUsageEventViewSet,
    SubscriptionPolicyViewSet,
    SubscriptionBillingRecordViewSet,
    WorkOrderIntakeView,
    WorkOrderViewSet,
)

router = SimpleRouter()
router.register("employees", PlatformEmployeeViewSet, basename="platform-ops-employees")
router.register("subscriptions", ServiceSubscriptionViewSet, basename="platform-ops-subscriptions")
router.register("subscription-policies", SubscriptionPolicyViewSet, basename="platform-ops-subscription-policies")
router.register("billing-records", SubscriptionBillingRecordViewSet, basename="platform-ops-billing-records")
router.register("work-orders", WorkOrderViewSet, basename="platform-ops-work-orders")
router.register("integration-keys", IntegrationKeyViewSet, basename="platform-ops-integration-keys")
router.register("policy-profiles", PolicyProfileViewSet, basename="platform-ops-policy-profiles")
router.register("performance-snapshots", PerformanceSnapshotViewSet, basename="platform-ops-performance-snapshots")
router.register("notifications", PlatformNotificationViewSet, basename="platform-ops-notifications")
router.register("activity-logs", PlatformActivityLogViewSet, basename="platform-ops-activity-logs")
router.register("recruiters", PlatformRecruiterViewSet, basename="platform-ops-recruiters")
router.register("job-postings", JobPostingViewSet, basename="platform-ops-job-postings")
router.register("job-applicants", JobApplicantViewSet, basename="platform-ops-job-applicants")
router.register("health-checks", CompanyHealthCheckViewSet, basename="platform-ops-health-checks")
router.register("engagements", EngagementViewSet, basename="platform-ops-engagements")
router.register("service-unit-catalogs", ServiceUnitCatalogViewSet, basename="platform-ops-service-unit-catalogs")
router.register("usage-events", ServiceUsageEventViewSet, basename="platform-ops-usage-events")

urlpatterns = [
    path("companies/<int:tenant_id>/health/", CompanyHealthView.as_view(), name="platform-ops-company-health"),
    path("acquisition/", CustomerAcquisitionView.as_view(), name="platform-ops-acquisition"),
    path("intake/", WorkOrderIntakeView.as_view(), name="platform-ops-intake"),
    path("dashboard/", PlatformDashboardView.as_view(), name="platform-ops-dashboard"),
    path("", include(router.urls)),
]
