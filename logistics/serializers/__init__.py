"""حزمة logistics.serializers — المرحلة 3: تفكيك serializers.py (2,466 سطراً)
حسب دومين رحلة الاستيراد (بنفس تقسيم views). صفر تغيير سلوك — الرسم لا-دوري
(shipments → deals الحافة الوحيدة عبر الوحدات). كل الأسماء العامة تُعاد
تصديرها فيبقى `from logistics.serializers import X` شغّالاً.
"""
# الترويسة (imports مثل CHEQUE_DUE_DATE_REQUIRED/PartnerSerializer) كانت
# مُعاد تصديرها من الملف الأصلي — _helpers يحملها فيستعيدها import *.
from ._helpers import *  # noqa: F401,F403
from ._helpers import (
    _deal_title_for_list_preview,
    _to_decimal,
    _quantize_decimal_10_3,
    _apply_lines_subtotal_and_grand_total,
    _coerce_logistics_payment_pk,
    _payments_total_exceeds_shipment,
    _sync_shipment_agent_payments,
)
from .procurement import (
    SupplierQuotationLineSerializer,
    SupplierQuotationSerializer,
    PurchaseRFQLineSerializer,
    PurchaseRFQRecipientSerializer,
    PurchaseRFQSerializer,
    PublicSupplierQuoteRequestLineSerializer,
    PublicSupplierQuoteRequestSerializer,
    PurchaseOrderLineSerializer,
    PurchaseOrderSerializer,
)
from .deals import (
    quotation_already_claimed_message,
    LogisticsPaymentSerializer,
    LogisticsDealItemSerializer,
    LogisticsDealSerializer,
    LogisticsDealListSerializer,
    LogisticsDealShipmentSummarySerializer,
    LogisticsShipmentDealAllocationSerializer,
)
from .clearance import (
    LogisticsClearanceLineSerializer,
    LogisticsClearanceSerializer,
    LogisticsClearancePaymentSerializer,
)
from .invoices import (
    PurchaseInvoiceItemSerializer,
    PurchaseInvoiceFeeSerializer,
    PurchaseInvoiceListSerializer,
    read_document_images,
    read_document_pdfs,
    PurchaseInvoiceSerializer,
)
from .transport import (
    LocalShipmentSerializer,
    LocalShipmentPaymentSerializer,
)
from .settings import (
    PurchaseSettingsSerializer,
)
from .goods_receipts import (
    GoodsReceiptLineSerializer,
    GoodsReceiptListSerializer,
    GoodsReceiptSerializer,
)
from .payments import (
    SupplierPaymentAllocationSerializer,
    _SupplierChequeInputSerializer,
    SupplierPaymentSerializer,
)
from .shipments import (
    LogisticsShipmentSerializer,
    LogisticsShipmentListSerializer,
)

__all__ = [
    "_deal_title_for_list_preview",
    "_to_decimal",
    "_quantize_decimal_10_3",
    "_apply_lines_subtotal_and_grand_total",
    "_coerce_logistics_payment_pk",
    "_payments_total_exceeds_shipment",
    "_sync_shipment_agent_payments",
    "SupplierQuotationLineSerializer",
    "SupplierQuotationSerializer",
    "PurchaseRFQLineSerializer",
    "PurchaseRFQRecipientSerializer",
    "PurchaseRFQSerializer",
    "PublicSupplierQuoteRequestLineSerializer",
    "PublicSupplierQuoteRequestSerializer",
    "PurchaseOrderLineSerializer",
    "PurchaseOrderSerializer",
    "LogisticsPaymentSerializer",
    "LogisticsDealItemSerializer",
    "LogisticsDealSerializer",
    "LogisticsDealListSerializer",
    "LogisticsDealShipmentSummarySerializer",
    "LogisticsShipmentDealAllocationSerializer",
    "LogisticsClearanceLineSerializer",
    "LogisticsClearanceSerializer",
    "LogisticsClearancePaymentSerializer",
    "PurchaseInvoiceItemSerializer",
    "PurchaseInvoiceFeeSerializer",
    "PurchaseInvoiceListSerializer",
    "read_document_images",
    "read_document_pdfs",
    "PurchaseInvoiceSerializer",
    "LocalShipmentSerializer",
    "LocalShipmentPaymentSerializer",
    "PurchaseSettingsSerializer",
    "GoodsReceiptLineSerializer",
    "GoodsReceiptListSerializer",
    "GoodsReceiptSerializer",
    "SupplierPaymentAllocationSerializer",
    "_SupplierChequeInputSerializer",
    "SupplierPaymentSerializer",
    "LogisticsShipmentSerializer",
    "LogisticsShipmentListSerializer",
]
