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















class LocalShipmentSerializer(serializers.ModelSerializer):
    """شحن محلي — بين التخليص الجمركي وفاتورة المشتريات."""

    carrier_name = serializers.CharField(source='carrier.name', read_only=True)
    clearance_number = serializers.CharField(
        source='clearance.declaration_number', read_only=True,
    )
    shipment_number_source = serializers.CharField(
        source='shipment.shipment_number', read_only=True,
    )
    expense_account_code = serializers.CharField(
        source='expense_account.code', read_only=True, allow_null=True,
    )
    expense_account_name = serializers.CharField(
        source='expense_account.name', read_only=True, allow_null=True,
    )
    currency_code = serializers.CharField(
        source='currency.Code', read_only=True, allow_null=True,
    )
    purchase_invoice_number = serializers.CharField(
        source='purchase_invoice.invoice_number', read_only=True, allow_null=True,
    )
    amount_paid = serializers.SerializerMethodField()
    remaining_balance = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    class Meta:
        model = LocalShipment
        fields = [
            'id',
            'shipment_number',
            'clearance', 'clearance_number',
            'shipment', 'shipment_number_source',
            'carrier', 'carrier_name',
            'driver_name', 'vehicle_number',
            'origin', 'destination',
            'pickup_date', 'delivery_date',
            'amount',
            'currency', 'currency_code', 'exchange_rate',
            'payment_type',
            'expense_account', 'expense_account_code', 'expense_account_name',
            'cash_or_bank_account',
            'capitalize_to_inventory',
            'status',
            'notes',
            'is_posted', 'journal',
            'purchase_invoice', 'purchase_invoice_number',
            'amount_paid', 'remaining_balance', 'payment_status', 'payments',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'shipment_number', 'is_posted', 'journal',
            'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        amount = attrs.get('amount', getattr(instance, 'amount', 0))
        try:
            if Decimal(str(amount or 0)) <= 0:
                raise serializers.ValidationError({
                    'amount': 'المبلغ يجب أن يكون أكبر من صفر.',
                })
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError({'amount': 'قيمة غير صالحة.'})
        return attrs

    @staticmethod
    def _paid_total(obj):
        return sum(
            (Decimal(str(p.amount or 0)) for p in obj.payments.all() if p.is_posted),
            Decimal('0'),
        ).quantize(Decimal('0.01'))

    def get_amount_paid(self, obj):
        return str(self._paid_total(obj))

    def get_remaining_balance(self, obj):
        return str(max(Decimal('0'), Decimal(str(obj.amount or 0)) - self._paid_total(obj)))

    def get_payment_status(self, obj):
        amount = Decimal(str(obj.amount or 0))
        paid = self._paid_total(obj)
        if amount > 0 and paid >= amount - Decimal('0.01'):
            return 'paid'
        if paid > 0:
            return 'partially_paid'
        return 'unpaid'

    def get_payments(self, obj):
        return LocalShipmentPaymentSerializer(obj.payments.all(), many=True).data

class LocalShipmentPaymentSerializer(serializers.ModelSerializer):
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True)
    currency_code = serializers.CharField(source='currency.Code', read_only=True)

    class Meta:
        model = LocalShipmentPayment
        fields = '__all__'
        read_only_fields = [
            'id', 'tenant', 'local_shipment', 'is_posted', 'journal',
            'created_at', 'created_by',
        ]
