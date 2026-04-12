from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AccountViewSet,
    JournalViewSet,
    ChequeViewSet,
    CostCenterViewSet,
    GeneralLedgerView,
    TrialBalanceView,
    CashBoxLedgerViewSet,
    PurchaseReceiptViewSet,
    ExchangeRateViewSet,
    FiscalPeriodViewSet,
    TaxRateViewSet,
    CurrencyViewSet,
)

router = DefaultRouter()
router.register(r'accounts', AccountViewSet)
router.register(r'journals', JournalViewSet)
router.register(r'cheques', ChequeViewSet)
router.register(r'cost-centers', CostCenterViewSet)
router.register(r'general-ledger', GeneralLedgerView, basename='general-ledger')
router.register(r'trial-balance', TrialBalanceView, basename='trial-balance')
router.register(r'cash-box-accounts', CashBoxLedgerViewSet, basename='cash-box-accounts')
router.register(r'purchase-receipts', PurchaseReceiptViewSet, basename='purchase-receipts')
router.register(r'exchange-rates', ExchangeRateViewSet, basename='exchange-rates')
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-periods')
router.register(r'tax-rates', TaxRateViewSet, basename='tax-rates')
router.register(r'currencies', CurrencyViewSet, basename='currencies')

urlpatterns = [
    path('', include(router.urls)),
]

