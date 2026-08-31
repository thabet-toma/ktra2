from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductFamilyViewSet, ProductViewSet, ProductSerialViewSet,
    UnitOfMeasureViewSet, StockMovementViewSet, SupplierProductViewSet,
    WarehouseViewSet, WarehouseTransferViewSet, StocktakeViewSet,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'product-families', ProductFamilyViewSet, basename='product-families')
router.register(r'products', ProductViewSet)
router.register(r'serials', ProductSerialViewSet, basename='serials')
router.register(r'uom', UnitOfMeasureViewSet)
router.register(r'warehouses', WarehouseViewSet, basename='warehouses')
router.register(r'stock-movements', StockMovementViewSet, basename='stock-movements')
router.register(r'supplier-products', SupplierProductViewSet, basename='supplier-products')
router.register(r'warehouse-transfers', WarehouseTransferViewSet, basename='warehouse-transfers')
router.register(r'stocktakes', StocktakeViewSet, basename='stocktakes')

urlpatterns = [
    path('', include(router.urls)),
]
