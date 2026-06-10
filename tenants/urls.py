"""N0-T4 — URLs for tenants app (GroupConstants F11 endpoints)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BranchViewSet, CurrencyViewSet, TenantBookViewSet, TenantSettingsViewSet, TenantViewSet

router = DefaultRouter()
router.register(r"settings", TenantSettingsViewSet, basename="tenant-settings")
router.register(r"books", TenantBookViewSet, basename="tenant-books")
router.register(r"currencies", CurrencyViewSet, basename="tenant-currencies")
router.register(r"companies", TenantViewSet, basename="tenant-companies")
router.register(r"branches", BranchViewSet, basename="tenant-branches")

urlpatterns = [
    path("", include(router.urls)),
]
