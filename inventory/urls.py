from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductViewSet, UnitOfMeasureViewSet,
    StockMovementViewSet, WarehouseViewSet,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'uom', UnitOfMeasureViewSet)
router.register(r'warehouses', WarehouseViewSet, basename='warehouses')
router.register(r'stock-movements', StockMovementViewSet, basename='stock-movements')

urlpatterns = [
    path('', include(router.urls)),
]
