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















# المرحلة 3: مراجع عبر وحدات الحزمة (نفس الملف سابقاً) — لا-دوري.
from ._helpers import _quantize_decimal_10_3, _sync_shipment_agent_payments, _to_decimal
from .deals import LogisticsDealShipmentSummarySerializer, LogisticsPaymentSerializer, LogisticsShipmentDealAllocationSerializer

class LogisticsShipmentSerializer(serializers.ModelSerializer):
    shipment_number = serializers.CharField(required=False, allow_blank=True)
    agent_name = serializers.CharField(source='shipping_agent.name', read_only=True)
    deals = LogisticsDealShipmentSummarySerializer(many=True, read_only=True)
    shipment_deal_allocations = LogisticsShipmentDealAllocationSerializer(
        source="logisticsshipmentdeal_set", many=True, read_only=True
    )
    deal_allocations = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )
    # نموذج الشحنة يستخدم related_name=agent_payments (وليس payments)
    payments = LogisticsPaymentSerializer(
        many=True, required=False, source="agent_payments"
    )

    class Meta:
        model = LogisticsShipment
        fields = [f.name for f in LogisticsShipment._meta.concrete_fields] + [
            "agent_name",
            "deals",
            "shipment_deal_allocations",
            "deal_allocations",
            "payments",
        ]
        # حالة استحقاق الشحن يملكها مسارا post/unpost-freight-accrual وحدهما.
        # شاشة الشحنة تُرسل النموذج كاملاً عند «تخزين»، فلو بقيت قابلة للكتابة
        # لمسح أي حفظ لاحق قيدَ الاستحقاق من السجل بينما القيد باقٍ في اليومية.
        read_only_fields = [
            "id", "tenant",
            "freight_is_posted", "freight_journal", "freight_exchange_rate",
        ]

    def validate_shipment_number(self, value):
        value = str(value or '').strip()
        if self.instance is not None and not value:
            raise serializers.ValidationError('لا يمكن مسح رقم شحنة محفوظة.')
        return value

    def validate_total_volume(self, value):
        return _quantize_decimal_10_3(value)

    def validate_total_weight_kg(self, value):
        return _quantize_decimal_10_3(value)

    def _apply_deal_allocations(self, instance, rows):
        if not rows:
            return
        for row in rows:
            try:
                did = int(row.get("deal_id"))
            except (TypeError, ValueError):
                continue
            alloc = _to_decimal(row.get("allocated_shipping_cost", 0))
            extra = _to_decimal(row.get("extra_costs", 0))
            LogisticsShipmentDeal.objects.filter(shipment=instance, deal_id=did).update(
                allocated_shipping_cost=alloc,
                extra_costs=extra,
            )

    def create(self, validated_data):
        # الحقل اسمه payments لكن source="agent_payments" → المفتاح في validated_data هو agent_payments
        payments_data = validated_data.pop(
            "agent_payments", validated_data.pop("payments", None)
        )
        deal_alloc = validated_data.pop("deal_allocations", None)
        instance = LogisticsShipment.objects.create(**validated_data)
        if payments_data:
            _sync_shipment_agent_payments(instance, payments_data)
        if deal_alloc:
            self._apply_deal_allocations(instance, deal_alloc)
        return instance

    def update(self, instance, validated_data):
        payments_data = validated_data.pop(
            "agent_payments", validated_data.pop("payments", None)
        )
        deal_alloc = validated_data.pop("deal_allocations", None)
        instance = super().update(instance, validated_data)
        if payments_data is not None:
            _sync_shipment_agent_payments(instance, payments_data)
        if deal_alloc is not None:
            self._apply_deal_allocations(instance, deal_alloc)
        return instance

class LogisticsShipmentListSerializer(serializers.ModelSerializer):
    """Collection contract: shipment header plus scalar summaries only."""

    agent_name = serializers.CharField(source='shipping_agent.name', read_only=True)
    deals_count = serializers.IntegerField(read_only=True)
    payments_count = serializers.IntegerField(read_only=True)
    payments_total = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = LogisticsShipment
        fields = [field.name for field in LogisticsShipment._meta.concrete_fields] + [
            'agent_name', 'deals_count', 'payments_count', 'payments_total',
        ]
        read_only_fields = fields
