from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerNoteViewSet, PartnerViewSet

router = DefaultRouter()
router.register(r'partners', PartnerViewSet)
router.register(r'customer-notes', CustomerNoteViewSet, basename='customer-note')

urlpatterns = [
    path('', include(router.urls)),
]
