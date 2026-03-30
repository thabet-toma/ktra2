from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, JournalViewSet, ChequeViewSet, CostCenterViewSet, GeneralLedgerView, TrialBalanceView

router = DefaultRouter()
router.register(r'accounts', AccountViewSet)
router.register(r'journals', JournalViewSet)
router.register(r'cheques', ChequeViewSet)
router.register(r'cost-centers', CostCenterViewSet)
router.register(r'general-ledger', GeneralLedgerView, basename='general-ledger')
router.register(r'trial-balance', TrialBalanceView, basename='trial-balance')

urlpatterns = [
    path('', include(router.urls)),
]

