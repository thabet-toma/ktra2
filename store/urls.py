"""مسارات المتجر العام — تحت `/api/store/` من `core/urls.py`.

المسارات ثابتة بحرفها لأن روابطها تُشارَك على واتساب وتظهر في نتائج البحث:
كسرُ رابطٍ هنا يكسر رابطاً في يد زبون، لا استدعاءً في شاشة نملكها.
"""
from django.urls import path

from store.views import StoreProductDetailView, StoreProductListView, StoreProfileView

urlpatterns = [
    # الأخصّ أولاً: `<slug>/products/` قبل `<slug>/`، وإلا ابتلع الأولُ الثاني.
    path("<slug:slug>/products/", StoreProductListView.as_view(), name="store-products"),
    path(
        "<slug:slug>/products/<int:pk>/",
        StoreProductDetailView.as_view(), name="store-product-detail",
    ),
    path("<slug:slug>/", StoreProfileView.as_view(), name="store-profile"),
]
