from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BuildingViewSet,
    RentalUnitViewSet,
    LeaseViewSet,
    ElectricMeterViewSet,
    MeterReadingViewSet,
    RealestateSummaryViewSet,
)

router = DefaultRouter()
router.register(r"buildings", BuildingViewSet, basename="realestate-building")
router.register(r"units", RentalUnitViewSet, basename="realestate-unit")
router.register(r"leases", LeaseViewSet, basename="realestate-lease")
router.register(r"meters", ElectricMeterViewSet, basename="realestate-meter")
router.register(r"readings", MeterReadingViewSet, basename="realestate-reading")

urlpatterns = [
    path("", include(router.urls)),
    path("summary/", RealestateSummaryViewSet.as_view({"get": "list"}), name="realestate-summary"),
]
