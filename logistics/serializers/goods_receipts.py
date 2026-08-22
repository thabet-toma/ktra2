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

from logistics.services import (
    purchase_invoice_payment_summary,
    purchase_invoice_receipt_summary,
    purchase_item_receipt_quantities,
)
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















class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    """بند إرسالية شراء — المفوتر والمستلَم تراكمياً والباقي، لسياق المراجعة."""

    product_name = serializers.SerializerMethodField(read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True, default=None)
    ordered_quantity = serializers.SerializerMethodField()
    received_total = serializers.SerializerMethodField()
    remaining_quantity = serializers.SerializerMethodField()
    warehouse_name = serializers.CharField(
        source='warehouse.name', read_only=True, default=None,
    )

    class Meta:
        model = GoodsReceiptLine
        fields = [
            'id', 'item', 'item_name', 'product', 'product_name',
            'ordered_quantity', 'received_total', 'remaining_quantity',
            'quantity', 'unit_price', 'warehouse', 'warehouse_name',
        ]
        read_only_fields = fields

    def get_product_name(self, obj):
        return str(obj.product) if obj.product_id else None

    def get_ordered_quantity(self, obj):
        # السند المستقل بلا بند فاتورة ⇒ المفوتر = المستلَم نفسه (لا باقي).
        return str(obj.item.quantity if obj.item_id else obj.quantity)

    def get_received_total(self, obj):
        return str(obj.item.received_quantity if obj.item_id else obj.quantity)

    def get_remaining_quantity(self, obj):
        if not obj.item_id:
            return '0'
        return str(purchase_item_receipt_quantities(obj.item)[2])

class GoodsReceiptListSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source='invoice.invoice_number', read_only=True, default=None,
    )
    partner_name = serializers.SerializerMethodField()
    is_standalone = serializers.BooleanField(read_only=True)
    doc_label = serializers.SerializerMethodField()
    lines_count = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    total_remaining = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = [
            'id', 'receipt_number', 'receipt_date', 'invoice', 'invoice_number',
            'partner', 'partner_name', 'supplier_ref', 'is_standalone', 'doc_label',
            'auto_created', 'journal', 'notes',
            'lines_count', 'total_quantity', 'total_remaining', 'created_at',
        ]
        read_only_fields = fields

    def _labels(self, obj):
        cached = getattr(self, '_label_cache', None)
        if cached is None:
            from logistics.services import get_or_create_purchase_settings
            ps = get_or_create_purchase_settings(obj.tenant_id)
            cached = (ps.receipt_doc_label, ps.standalone_receipt_label)
            self._label_cache = cached
        return cached

    def get_doc_label(self, obj):
        linked, standalone = self._labels(obj)
        return standalone if obj.invoice_id is None else linked

    def get_partner_name(self, obj):
        if obj.partner_id:
            return obj.partner.name
        return obj.invoice.partner.name if obj.invoice_id else ''

    def get_lines_count(self, obj):
        return obj.lines.count()

    def get_total_quantity(self, obj):
        return str(sum((line.quantity for line in obj.lines.all()), Decimal('0')))

    def get_total_remaining(self, obj):
        """الباقي على الفاتورة المرتبطة بعد هذه الإرسالية (0 للسند المستقل)."""
        if obj.invoice_id is None:
            return '0'
        return str(purchase_invoice_receipt_summary(obj.invoice)['remaining'])

class GoodsReceiptSerializer(GoodsReceiptListSerializer):
    lines = GoodsReceiptLineSerializer(many=True, read_only=True)

    class Meta(GoodsReceiptListSerializer.Meta):
        fields = GoodsReceiptListSerializer.Meta.fields + ['lines']
        read_only_fields = fields
