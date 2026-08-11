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
from ._helpers import _deal_title_for_list_preview

class LogisticsClearanceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogisticsClearanceLine
        fields = '__all__'
        read_only_fields = ['id']

class LogisticsClearanceSerializer(serializers.ModelSerializer):
    broker_name = serializers.CharField(source="customs_broker.name", read_only=True)
    shipment_number = serializers.CharField(
        source="shipment.shipment_number", read_only=True
    )
    shipment_name = serializers.CharField(
        source="shipment.shipment_name", read_only=True, allow_null=True
    )
    deals_count = serializers.SerializerMethodField()
    deals_preview = serializers.SerializerMethodField()
    local_shipments = serializers.SerializerMethodField()
    lines = LogisticsClearanceLineSerializer(many=True, read_only=True)
    # cost_lines: legacy JSON write shape (frontend still posts it). WRITE-ONLY now —
    # the model `cost_lines` shim (D2) was removed; the read shape is rebuilt from the
    # serialized `lines` in to_representation, so nothing reads a model property.
    cost_lines = serializers.JSONField(required=False, write_only=True)
    amount_paid = serializers.SerializerMethodField()
    remaining_balance = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsClearance
        fields = "__all__"
        read_only_fields = ["id", "tenant"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Rebuild the legacy {label, amount} list from the line rows (amount =
        # debit − credit) so existing frontend read paths keep working post-D2.
        rows = data.get("lines") or []
        data["cost_lines"] = [
            {
                "label": (r.get("description") or ""),
                "amount": float((r.get("debit") or 0)) - float((r.get("credit") or 0)),
                "type": r.get("line_type") or "other",
            }
            for r in rows
        ]
        return data

    @staticmethod
    def _cost_total(instance):
        return sum(
            (
                max(Decimal('0'), Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0)))
                for line in instance.lines.all()
                if line.description != 'دفعة الشحن (الناقل)'
            ),
            Decimal('0'),
        ).quantize(Decimal('0.01'))

    @staticmethod
    def _paid_total(instance):
        return sum(
            (
                Decimal(str(payment.amount or 0))
                for payment in instance.payments.all()
                if payment.is_posted and payment.payment_purpose != 'shipping'
            ),
            Decimal('0'),
        ).quantize(Decimal('0.01'))

    def get_amount_paid(self, instance):
        return str(self._paid_total(instance))

    def get_remaining_balance(self, instance):
        return str(max(Decimal('0'), self._cost_total(instance) - self._paid_total(instance)))

    def get_payment_status(self, instance):
        total = self._cost_total(instance)
        paid = self._paid_total(instance)
        if total > 0 and paid >= total - Decimal('0.01'):
            return 'paid'
        if paid > 0:
            return 'partially_paid'
        return 'unpaid'

    def get_local_shipments(self, obj):
        try:
            rows = obj.local_shipments.all()
            return [
                {
                    "id": r.id,
                    "shipment_number": r.shipment_number,
                    "amount": str(r.amount),
                    "status": r.status,
                    "is_posted": r.is_posted,
                    "currency": r.currency_id,
                }
                for r in rows
            ]
        except Exception:
            return []

    def get_deals_count(self, obj):
        try:
            sh = obj.shipment
            if sh is None:
                return 0
            cache = getattr(sh, "_prefetched_objects_cache", None)
            if cache and "deals" in cache:
                return len(cache["deals"])
            return sh.deals.count()
        except Exception:
            return 0

    def get_deals_preview(self, obj):
        """عناوين قصيرة من حقل description (عربي) أو رقم الصفقة — لقوائم الاستيراد."""
        try:
            sh = obj.shipment
            if sh is None:
                return None
            deals = list(sh.deals.all()[:5])
            parts = []
            for d in deals:
                t = _deal_title_for_list_preview(d)
                if t:
                    parts.append(t)
            if not parts:
                return None
            tail = " …" if len(deals) >= 5 else ""
            return " · ".join(parts[:4]) + tail
        except Exception:
            return None

    @staticmethod
    def _default_cost_lines():
        return [
            {"label": "ضريبة القيمة المضافة", "amount": 0},
            {"label": "رسوم البيان الجمركي", "amount": 0},
            {"label": "محطة الشحن", "amount": 0},
            {"label": "معالجة التصاريح", "amount": 0},
            {"label": "عمولة المخلص", "amount": 0},
            {"label": 'نظام الجمارك «الجيل الجديد»', "amount": 0},
        ]

    def validate_cost_lines(self, value):
        if value is None:
            return self._default_cost_lines()
        if not isinstance(value, list):
            raise serializers.ValidationError("cost_lines يجب أن تكون قائمة")
        valid_types = {c[0] for c in LogisticsClearanceLine.LINE_TYPE_CHOICES}
        out = []
        for row in value:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            line_type = str(row.get("type") or "").strip()
            if line_type not in valid_types:
                line_type = ""
            try:
                amt = float(row.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amt = 0.0
            # بند بلا بيان ولا نوع صريح ولا مبلغ = صف فارغ فعلاً — لا معنى لحفظه.
            # لكن بند اختير له نوع أو له مبلغ لا يُسقَط لمجرد أن «البيان» بقي فارغاً.
            if not label and not line_type and amt == 0:
                continue
            out.append({"label": label[:220], "amount": round(amt, 2), "type": line_type})
        return out if out else self._default_cost_lines()

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.method == "POST":
            sh = attrs.get("shipment")
            if sh is not None and LogisticsClearance.objects.filter(shipment=sh).exists():
                raise serializers.ValidationError(
                    {"shipment": "يوجد بالفعل تخليص جمركي لهذه الشحنة."}
                )
        return attrs

    LABEL_TO_LINE_TYPE = {
        'ضريبة القيمة المضافة': 'vat',
        'رسوم البيان الجمركي': 'declaration_fee',
        'محطة الشحن': 'terminal',
        'معالجة التصاريح': 'permits',
        'عمولة المخلص': 'broker_commission',
        'نظام الجمارك «الجيل الجديد»': 'customs_system',
    }

    def _sync_lines_from_cost_lines(self, instance, cost_lines):
        valid_types = {c[0] for c in LogisticsClearanceLine.LINE_TYPE_CHOICES}
        instance.lines.all().delete()
        for idx, item in enumerate(cost_lines):
            label = str(item.get('label', '') or '')
            amount_raw = item.get('amount', 0)
            try:
                amount = float(amount_raw) if amount_raw else 0
            except (ValueError, TypeError):
                amount = 0
            debit = abs(amount) if amount > 0 else 0
            credit = abs(amount) if amount < 0 else 0
            # النوع الصريح الوارد من الواجهة (اختيار المستخدم) له الأولوية؛ التخمين من
            # البيان (LABEL_TO_LINE_TYPE) للتوافق مع طلبات قديمة لا ترسل نوعاً.
            line_type = str(item.get('type') or '').strip()
            if line_type not in valid_types:
                line_type = self.LABEL_TO_LINE_TYPE.get(label, 'other')
            instance.lines.create(
                seq=idx + 1,
                line_type=line_type,
                description=label,
                debit=debit,
                credit=credit,
            )

    def create(self, validated_data):
        cost_lines = validated_data.pop('cost_lines', None) or self._default_cost_lines()
        instance = super().create(validated_data)
        self._sync_lines_from_cost_lines(instance, cost_lines)
        return instance

    def update(self, instance, validated_data):
        cost_lines = validated_data.pop('cost_lines', None)
        instance = super().update(instance, validated_data)
        if cost_lines is not None:
            self._sync_lines_from_cost_lines(instance, cost_lines)
        return instance

class LogisticsClearancePaymentSerializer(serializers.ModelSerializer):
    broker_name = serializers.CharField(source="customs_broker.name", read_only=True)
    journal_id_display = serializers.IntegerField(source="journal.id", read_only=True)
    currency_code = serializers.CharField(
        source="currency.Code", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = LogisticsClearancePayment
        fields = "__all__"
        read_only_fields = [
            "id",
            "tenant",
            "customs_broker",
            "is_posted",
            "journal",
            "created_at",
        ]
