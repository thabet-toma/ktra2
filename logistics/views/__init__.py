"""حزمة logistics.views — المرحلة 3: تفكيك ميكانيكي لـviews.py (4,994 سطراً)
حسب دومين رحلة الاستيراد. صفر تغيير سلوك — نقل كود حرفي، والأسماء العامة تُعاد
تصديرها هنا فيبقى `from logistics.views import X` شغّالاً كما كان.
"""
from .procurement import (
    SupplierQuotationViewSet,
    PurchaseRFQViewSet,
    PurchaseOrderViewSet,
)
from .deals import LogisticsDealViewSet, LogisticsPaymentViewSet
from .shipments import LogisticsShipmentViewSet
from .clearance import LogisticsClearanceViewSet
from .invoices import (
    PurchaseInvoiceViewSet,
    _purchase_item_snapshot,
    PURCHASE_ACTIVITY_FIELD_LABELS,
    PURCHASE_ACTIVITY_ITEM_LABELS,
)
from .payments import SupplierPaymentViewSet
from .transport import LocalShipmentViewSet
from .reports import (
    ImportJourneyViewSet,
    LandedCostReportViewSet,
    _build_landed_cost_summary,
)
from .goods_receipts import GoodsReceiptViewSet
from .purchase_settings import PurchaseSettingsViewSet

__all__ = [
    "SupplierQuotationViewSet", "PurchaseRFQViewSet", "PurchaseOrderViewSet",
    "LogisticsDealViewSet", "LogisticsPaymentViewSet",
    "LogisticsShipmentViewSet", "LogisticsClearanceViewSet",
    "PurchaseInvoiceViewSet", "SupplierPaymentViewSet",
    "LocalShipmentViewSet", "ImportJourneyViewSet",
    "LandedCostReportViewSet", "GoodsReceiptViewSet",
    "PurchaseSettingsViewSet",
    "_purchase_item_snapshot", "_build_landed_cost_summary",
    "PURCHASE_ACTIVITY_FIELD_LABELS", "PURCHASE_ACTIVITY_ITEM_LABELS",
]
