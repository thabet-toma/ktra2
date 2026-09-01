import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from accounting.models import Account
from sales.models import SupplierPayment, SupplierPaymentAllocation
from sales.serializers import CHEQUE_DUE_DATE_REQUIRED
from core.payments import (
    apply_default_cash_account,
    document_partner_balance_summary,
    document_payment_summary,
)
from core.tenant_utils import get_tenant

from logistics.services import purchase_invoice_payment_summary
from logistics.text_utils import has_arabic as _has_arabic
from logistics.text_utils import (
    is_english_payment_or_legal_boilerplate as _english_payment_boilerplate,
)
















from logistics.models import (
    SupplierQuotation,
    SupplierQuotationLine,
    PurchaseOrder,
    PurchaseOrderLine,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsShipmentDeal,
    LogisticsPayment,
    LogisticsClearancePayment,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseInvoiceFee,
    PurchaseSettings,
    GoodsReceipt,
    GoodsReceiptLine,
    LocalShipment,
    LocalShipmentPayment,
)

from partners.serializers import PartnerSerializer
from inventory.models import Product

logger = logging.getLogger("logistics.serializers")

























# ─── Purchase Invoice Serializers ──────────────────────────────────────────────
















# ── P-H-3: SupplierPayment ──────────────────────────────────────────















class PurchaseSettingsSerializer(serializers.ModelSerializer):
    """FEAT-1: إعدادات الشراء (استراتيجية التسعير التلقائي).

    #34: المقابض السبعة (ط11 على خريطة T-REORDER) — كانت الثلاثة القائمة
    (`default_lead_time_days`/`review_period_days`) مضبوطةً بقيمة دائمة في
    قاعدة البيانات بلا شاشةٍ تعدّلها، والخمسة الجديدة (`forecast_*`) كانت
    ثوابت وحدة في `core/replenishment.py`. كلاهما مُعرَّضٌ هنا الآن.
    `replenishment_window_days` (نافذة معدّل الصرف اليومي) ليست من السبعة —
    خارج نطاق هذه التذكرة عمداً (ط11 يفرّقها عن `forecast_history_weeks`
    مفهوماً لا تعرّضاً).
    """

    class Meta:
        model = PurchaseSettings
        fields = ['id', 'purchase_default_price_strategy', 'default_cash_account',
                  'receive_on_post', 'receipt_doc_label', 'standalone_receipt_label',
                  'allow_standalone_receipt', 'allow_edit_receipt',
                  'serial_entry_mode',
                  'default_lead_time_days', 'review_period_days',
                  'forecast_alpha', 'forecast_beta', 'forecast_history_weeks',
                  'forecast_trend_cap_ratio', 'forecast_safety_factor',
                  'updated_at']
        read_only_fields = ['id', 'updated_at']
