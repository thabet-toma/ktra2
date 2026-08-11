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















class SupplierPaymentAllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)

    class Meta:
        model = SupplierPaymentAllocation
        fields = ['id', 'invoice', 'invoice_number', 'amount',
                  'amount_in_invoice_currency', 'conversion_rate']
        read_only_fields = fields

class _SupplierChequeInputSerializer(serializers.Serializer):
    """شيك صادر داخل سند الصرف — مبلغه جزء من مبلغ السند لا إضافة عليه."""
    cheque_number = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    account_number = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    bank_branch = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    # T-CHQ3/ط: مرآة الجانب الوارد — لا شيك بلا موعد استحقاق (نفس الرسالة).
    due_date = serializers.DateField(
        error_messages={
            'null': CHEQUE_DUE_DATE_REQUIRED,
            'required': CHEQUE_DUE_DATE_REQUIRED,
            'invalid': CHEQUE_DUE_DATE_REQUIRED,
        },
    )
    issue_date = serializers.DateField(required=False, allow_null=True)
    payee_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')

class SupplierPaymentSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    # T-ONEPAY: شيكات السند (كتابة عند الإنشاء، قراءة من الشيكات المرتبطة).
    cheques = _SupplierChequeInputSerializer(many=True, required=False, write_only=True)
    attached_cheques = serializers.SerializerMethodField()

    def get_attached_cheques(self, obj) -> list:
        return [
            {
                'id': c.id, 'cheque_number': c.cheque_number,
                'bank_name': c.bank_name or '', 'amount': str(c.amount),
                'due_date': c.due_date, 'status': c.status,
            }
            for c in obj.cheques.all()
        ]
    currency_code = serializers.CharField(source='currency.Code', read_only=True, default=None)
    cash_account_name = serializers.CharField(
        source='cash_or_bank_account.name', read_only=True, default=None,
    )
    # T-DEFACC: اختياري في الإدخال — `validate` يملؤه من افتراضي الشركة.
    cash_or_bank_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True,
    )
    # T-ONACC: التوزيع على فواتير الشراء + المتبقّي «على الحساب» (مرآة سند القبض).
    allocations = SupplierPaymentAllocationSerializer(many=True, read_only=True)
    allocated_amount = serializers.SerializerMethodField()
    unallocated_amount = serializers.SerializerMethodField()

    def _allocated(self, obj) -> Decimal:
        return sum(
            (Decimal(str(a.amount)) for a in obj.allocations.all()), Decimal('0')
        )

    def get_allocated_amount(self, obj) -> str:
        return str(self._allocated(obj))

    def get_unallocated_amount(self, obj) -> str:
        return str(Decimal(str(obj.amount)) - self._allocated(obj))

    class Meta:
        model = SupplierPayment
        fields = [
            'id',
            'partner', 'partner_name',
            'purchase_invoice',
            'payment_date',
            'amount',
            'currency', 'currency_code', 'exchange_rate',
            'cash_or_bank_account', 'cash_account_name',
            'is_posted', 'journal',
            'notes',
            'cheques', 'attached_cheques',
            'allocations', 'allocated_amount', 'unallocated_amount',
            'created_at',
        ]
        read_only_fields = ['id', 'is_posted', 'journal', 'created_at',
                            'attached_cheques',
                            'allocations', 'allocated_amount', 'unallocated_amount']

    def validate(self, attrs):
        try:
            if Decimal(str(attrs.get('amount', 0))) <= 0:
                raise serializers.ValidationError({'amount': 'المبلغ يجب أن يكون أكبر من صفر.'})
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError({'amount': 'قيمة غير صالحة.'})
        if not attrs.get('payment_date'):
            raise serializers.ValidationError({'payment_date': 'تاريخ الدفعة مطلوب.'})
        # T-DEFACC: الصندوق يُملأ من افتراضي الشركة بدل رفض السند لفراغه.
        attrs = apply_default_cash_account(self, attrs)
        invoice = attrs.get(
            'purchase_invoice',
            self.instance.purchase_invoice if self.instance else None,
        )
        partner = attrs.get('partner', self.instance.partner if self.instance else None)
        if invoice:
            from core.tenant_utils import get_tenant
            request = self.context.get('request')
            tenant = get_tenant(request) if request else None
            if tenant and invoice.tenant_id != tenant.TenantID:
                raise serializers.ValidationError({
                    'purchase_invoice': 'فاتورة الشراء لا تتبع الشركة الحالية.',
                })
            if partner and invoice.partner_id != partner.id:
                raise serializers.ValidationError({
                    'purchase_invoice': 'فاتورة الشراء لا تتبع المورد المحدد.',
                })
        cheques_total = sum(
            (Decimal(str(c['amount'])) for c in attrs.get('cheques', [])), Decimal('0'),
        )
        if cheques_total > Decimal(str(attrs.get('amount', 0))):
            raise serializers.ValidationError({
                'cheques': 'مجموع الشيكات لا يجوز أن يتجاوز مبلغ السند.',
            })
        return attrs

    def create(self, validated_data):
        from accounting.models import Cheque

        cheques = validated_data.pop('cheques', [])
        payment = super().create(validated_data)
        for c in cheques:
            Cheque.objects.create(
                tenant=payment.tenant,
                supplier_payment=payment,
                partner=payment.partner,
                direction='Outgoing',
                status='Draft',  # يصير «برسم الدفع» عند ترحيل السند
                cheque_number=c['cheque_number'].strip(),
                amount=c['amount'],
                currency=payment.currency,
                bank_name=c.get('bank_name') or '',
                account_number=c.get('account_number') or '',
                bank_branch=c.get('bank_branch') or '',
                due_date=c.get('due_date') or None,
                issue_date=c.get('issue_date') or None,
                payee_name=c.get('payee_name') or '',
                notes=c.get('notes') or '',
            )
        return payment
