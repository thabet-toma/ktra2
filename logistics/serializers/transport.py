import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from accounting.models import Account
from sales.models import SupplierPayment, SupplierPaymentAllocation
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
    # وسم الشحنة الدولية التي تنقلها (مباشرةً أو عبر التخليص) — فارغ لإرساليةٍ حرّة.
    shipment_label = serializers.CharField(read_only=True)
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
    advance_balance = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    class Meta:
        model = LocalShipment
        fields = [
            'id',
            'shipment_number',
            'clearance', 'clearance_number',
            'shipment', 'shipment_number_source', 'shipment_label',
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
            'amount_paid', 'remaining_balance', 'advance_balance', 'payment_status', 'payments',
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

    def _settlement(self, obj) -> dict:
        """مرآة التخليص (`party_accruals.document_settlement`) بعملة الإرسالية."""
        from logistics.domain.party_accruals import document_settlement

        cache = self.__dict__.setdefault('_settlement_cache', {})
        if obj.pk not in cache:
            cache[obj.pk] = document_settlement(
                'local', obj, draft_due=obj.amount, draft_paid=self._paid_total(obj),
                rate=obj.exchange_rate,
            )
        return cache[obj.pk]

    def get_amount_paid(self, obj):
        return self._settlement(obj)['amount_paid']

    def get_remaining_balance(self, obj):
        return self._settlement(obj)['remaining_balance']

    def get_advance_balance(self, obj):
        return self._settlement(obj)['advance_balance']

    def get_payment_status(self, obj):
        return self._settlement(obj)['payment_status']

    def get_payments(self, obj):
        return LocalShipmentPaymentSerializer(obj.payments.all(), many=True).data

class LocalShipmentPaymentSerializer(serializers.ModelSerializer):
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True)
    shipment_label = serializers.CharField(source='local_shipment.shipment_label', read_only=True)
    currency_code = serializers.CharField(source='currency.Code', read_only=True)

    class Meta:
        model = LocalShipmentPayment
        fields = '__all__'
        read_only_fields = [
            'id', 'tenant', 'local_shipment', 'is_posted', 'journal',
            'created_at', 'created_by',
        ]
