from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LogisticsDealViewSet, LogisticsShipmentViewSet,
    LogisticsClearanceViewSet, LogisticsExpenseViewSet,
    LogisticsPaymentViewSet
)

router = DefaultRouter()
router.register(r'deals', LogisticsDealViewSet)
router.register(r'shipments', LogisticsShipmentViewSet)
router.register(r'clearances', LogisticsClearanceViewSet)
router.register(r'expenses', LogisticsExpenseViewSet)
router.register(r'payments', LogisticsPaymentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
