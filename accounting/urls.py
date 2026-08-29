from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AccountViewSet,
    BankAccountViewSet,
    BankBranchViewSet,
    BankReconciliationViewSet,
    BankViewSet,
    JournalViewSet,
    ChequeViewSet,
    CostCenterViewSet,
    GeneralLedgerView,
    TrialBalanceView,
    VatReportView,
    CashBoxLedgerViewSet,
    CashCountViewSet,
    CashTransferViewSet,
    OpeningBalanceViewSet,
    PurchaseReceiptViewSet,
    ExchangeRateViewSet,
    FiscalPeriodViewSet,
    TaxRateViewSet,
    CurrencyViewSet,
)

router = DefaultRouter()
router.register(r'accounts', AccountViewSet, basename='accounts')
router.register(r'journals', JournalViewSet)
router.register(r'cheques', ChequeViewSet)
router.register(r'cost-centers', CostCenterViewSet)
router.register(r'banks', BankViewSet, basename='banks')
router.register(r'bank-branches', BankBranchViewSet, basename='bank-branches')
router.register(r'bank-accounts', BankAccountViewSet, basename='bank-accounts')
router.register(r'bank-reconciliations', BankReconciliationViewSet, basename='bank-reconciliations')
router.register(r'general-ledger', GeneralLedgerView, basename='general-ledger')
router.register(r'trial-balance', TrialBalanceView, basename='trial-balance')
router.register(r'vat-report', VatReportView, basename='vat-report')
router.register(r'cash-box-accounts', CashBoxLedgerViewSet, basename='cash-box-accounts')
router.register(r'cash-transfers', CashTransferViewSet, basename='cash-transfers')
router.register(r'cash-counts', CashCountViewSet, basename='cash-counts')
router.register(r'purchase-receipts', PurchaseReceiptViewSet, basename='purchase-receipts')
router.register(r'exchange-rates', ExchangeRateViewSet, basename='exchange-rates')
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-periods')
router.register(r'opening-balance', OpeningBalanceViewSet, basename='opening-balance')
router.register(r'tax-rates', TaxRateViewSet, basename='tax-rates')
router.register(r'currencies', CurrencyViewSet, basename='currencies')

urlpatterns = [
    path('', include(router.urls)),
]

