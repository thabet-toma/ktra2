"""مسارات المتجر العام ولوحة الإدارة — تحت `/api/store/` من `core/urls.py`."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from store.views import (
    StoreCollectionAdminViewSet,
    StoreCollectionDetailView,
    StoreCollectionItemAdminViewSet,
    StoreCollectionListView,
    StoreProductAdminViewSet,
    StoreProductDetailView,
    StoreProductImageAdminViewSet,
    StoreProductListView,
    StoreProfileView,
    StoreSettingsAdminView,
)

router = SimpleRouter()
router.register(
    r"admin/products",
    StoreProductAdminViewSet,
    basename="store-admin-products",
)
router.register(
    r"admin/product-images",
    StoreProductImageAdminViewSet,
    basename="store-admin-product-images",
)
router.register(
    r"admin/collections",
    StoreCollectionAdminViewSet,
    basename="store-admin-collections",
)
router.register(
    r"admin/collection-items",
    StoreCollectionItemAdminViewSet,
    basename="store-admin-collection-items",
)

urlpatterns = [
    # نقاط إدارة المتجر المصادق عليها
    path("admin/settings/", StoreSettingsAdminView.as_view(), name="store-admin-settings"),
    path("", include(router.urls)),
    # النقاط العامة لزائر المتجر
    path("<slug:slug>/products/", StoreProductListView.as_view(), name="store-products"),
    path(
        "<slug:slug>/products/<int:pk>/",
        StoreProductDetailView.as_view(),
        name="store-product-detail",
    ),
    path(
        "<slug:slug>/collections/",
        StoreCollectionListView.as_view(),
        name="store-collections",
    ),
    path(
        "<slug:slug>/collections/<slug:collection_slug>/",
        StoreCollectionDetailView.as_view(),
        name="store-collection-detail",
    ),
    path("<slug:slug>/", StoreProfileView.as_view(), name="store-profile"),
]

