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
from ._helpers import _apply_lines_subtotal_and_grand_total, _to_decimal

class LogisticsPaymentSerializer(serializers.ModelSerializer):
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True)
    
    class Meta:
        model = LogisticsPayment
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'is_posted', 'journal']

class LogisticsDealItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name_ar', read_only=True)
    total_price = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    image_urls = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsDealItem
        fields = [
            'id', 'product', 'product_name', 'quantity', 'unit_price', 'total_price', 'notes',
            'image_urls',
            'seq', 'catalog_number', 'name_snapshot', 'description_line', 'unit', 'warehouse',
            'extra_qty', 'batch_number', 'serial_number', 'manufacture_number', 'expiry_date',
            'line_currency', 'line_exchange_rate', 'second_date', 'is_taxable', 'vat_percent',
            'discount_percent', 'discount_amount',
        ]

    def get_image_urls(self, obj):
        try:
            from core.models import SystemAttachment

            if not obj.product_id:
                return []
            flt = {'related_table': 'products', 'related_id': obj.product_id}
            deal = getattr(obj, 'deal', None)
            if deal is not None:
                flt['tenant_id'] = deal.tenant_id
            elif getattr(obj, 'product', None) is not None:
                flt['tenant_id'] = obj.product.tenant_id
            return list(
                SystemAttachment.objects.filter(**flt)
                .order_by('id')
                .values_list('file_path', flat=True)
            )
        except Exception:
            return []

class LogisticsDealSerializer(serializers.ModelSerializer):
    items = LogisticsDealItemSerializer(many=True)
    # ج8: الدفعات مورد مستقل (deals/{id}/payments/) — القراءة فقط هنا.
    # الكتابة المتداخلة كانت جذر «هذا المستند مرحَّل»: أي PATCH كامل للصفقة
    # يصطدم بحارس الترحيل بعد أول دفعة مرحّلة.
    payments = LogisticsPaymentSerializer(many=True, read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    partner_legal_name = serializers.CharField(
        source='partner.legal_name', read_only=True, allow_null=True, default=None
    )
    quote_images = serializers.SerializerMethodField()
    quote_pdfs = serializers.SerializerMethodField()
    # ج7: الصفقة تعرف شحنتها — لعرض خريطة مسار الشحنة ورابط «رحلة الاستيراد»
    # داخل شاشة الصفقة (خريطة موحّدة صفقة→فاتورة).
    linked_shipment = serializers.SerializerMethodField()
    # G-import: الصفقة «المحوّلة إلى فاتورة» يجب أن تشير لرقمها مباشرة (بدل نص حالة
    # بلا رابط) — انظر get_linked_invoice.
    linked_invoice = serializers.SerializerMethodField()
    posted_paid_amount = serializers.SerializerMethodField()
    amount_outstanding = serializers.SerializerMethodField()
    supplier_advance = serializers.SerializerMethodField()
    unposted_registered_amount = serializers.SerializerMethodField()
    payment_status_summary = serializers.SerializerMethodField()
    supplier_balance_current = serializers.DecimalField(
        source='supplier_balance', max_digits=18, decimal_places=2, read_only=True,
    )
    supplier_balance_before_deal_payments = serializers.SerializerMethodField()
    supplier_balance_after_deal_payments = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsDeal
        fields = '__all__'
        read_only_fields = ['id', 'tenant', 'created_by', 'is_posted', 'journal', 'total_amount']
        # الترقيم خادمي عند الغياب/التكرار (T12-B4) — perform_create يولّد D-####
        extra_kwargs = {'ref_number': {'required': False, 'allow_blank': True}}

    def get_linked_shipment(self, obj):
        try:
            # prefetch-aware: يستهلك prefetch الـviewset إن وُجد بدل استعلام لكل صف
            links = list(obj.logisticsshipmentdeal_set.all())
            if not links:
                return None
            link = max(links, key=lambda l: l.id)
            sh = link.shipment
            if not sh:
                return None
            return {
                'id': sh.id,
                'shipment_number': sh.shipment_number or '',
                'shipment_name': sh.shipment_name or '',
            }
        except Exception:
            return None

    def get_linked_invoice(self, obj):
        try:
            pi = obj.purchase_invoices.order_by('-id').first()
            if not pi:
                return None
            return {
                'id': pi.id,
                'invoice_number': pi.invoice_number or '',
            }
        except Exception:
            return None

    @staticmethod
    def _payments(obj):
        return list(obj.payments.all())

    @staticmethod
    def _posted_paid_total(obj):
        return sum(
            (Decimal(str(payment.amount or 0)) for payment in LogisticsDealSerializer._payments(obj) if payment.is_posted),
            Decimal('0'),
        ).quantize(Decimal('0.01'))

    def get_unposted_registered_amount(self, obj):
        return str(sum(
            (Decimal(str(payment.amount or 0)) for payment in self._payments(obj) if not payment.is_posted),
            Decimal('0'),
        ).quantize(Decimal('0.01')))

    def get_payment_status_summary(self, obj):
        return document_payment_summary(
            obj.total_amount, self._posted_paid_total(obj),
        )['payment_status']

    def _supplier_balance_summary(self, obj):
        from accounting.services import partner_posted_journal_effect

        cached = getattr(obj, '_deal_supplier_balance_summary', None)
        if cached is not None:
            return cached
        current = Decimal(str(getattr(obj, 'supplier_balance', 0) or 0))
        effect = partner_posted_journal_effect(
            obj.tenant_id,
            obj.partner_id,
            [payment.journal_id for payment in self._payments(obj) if payment.is_posted],
            supplier=True,
        )
        obj._deal_supplier_balance_summary = (current - effect, current)
        return obj._deal_supplier_balance_summary

    def get_supplier_balance_before_deal_payments(self, obj):
        return str(self._supplier_balance_summary(obj)[0])

    def get_supplier_balance_after_deal_payments(self, obj):
        return str(self._supplier_balance_summary(obj)[1])

    def get_posted_paid_amount(self, obj):
        return str(self._posted_paid_total(obj))

    def get_amount_outstanding(self, obj):
        return str(max(Decimal('0'), Decimal(str(obj.total_amount or 0)) - self._posted_paid_total(obj)))

    def get_supplier_advance(self, obj):
        return str(max(Decimal('0'), self._posted_paid_total(obj) - Decimal(str(obj.total_amount or 0))))

    def get_quote_images(self, obj):
        try:
            from core.models import SystemAttachment

            rows = SystemAttachment.objects.filter(
                tenant_id=obj.tenant_id,
                related_table='logistics_deals',
                related_id=obj.id,
            ).order_by('id')
            out = []
            for a in rows:
                ft = (a.file_type or '').lower()
                path = (a.file_path or '').lower()
                if 'pdf' in ft or path.endswith('.pdf'):
                    continue
                if a.file_path:
                    out.append(a.file_path)
            return out
        except Exception:
            return []

    def get_quote_pdfs(self, obj):
        try:
            from core.models import SystemAttachment

            rows = SystemAttachment.objects.filter(
                tenant_id=obj.tenant_id,
                related_table='logistics_deals',
                related_id=obj.id,
            ).order_by('id')
            out = []
            for a in rows:
                ft = (a.file_type or '').lower()
                path = (a.file_path or '').lower()
                is_pdf = 'pdf' in ft or path.endswith('.pdf')
                if not is_pdf or not a.file_path:
                    continue
                name = (a.file_type or 'quote.pdf')
                if 'quote pdf' in name.lower():
                    name = name.split(':', 1)[-1].strip() or 'quote.pdf'
                out.append({
                    'name': name[:255],
                    'url': a.file_path,
                    'size': 0,
                    'type': 'application/pdf',
                })
            return out
        except Exception:
            return []

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        deal = LogisticsDeal.objects.create(**validated_data)

        lines_subtotal = Decimal("0")
        for item_data in items_data:
            LogisticsDealItem.objects.create(deal=deal, **item_data)
            lines_subtotal += _to_decimal(item_data.get("quantity")) * _to_decimal(
                item_data.get("unit_price")
            )

        _apply_lines_subtotal_and_grand_total(deal, lines_subtotal)
        deal.save()
        return deal

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        # Update Deal fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            # Smart update for items
            keep_items = []
            lines_subtotal = Decimal("0")
            for item_data in items_data:
                item_id = item_data.get('id')
                if item_id:
                    # Update existing item
                    LogisticsDealItem.objects.filter(id=item_id, deal=instance).update(**item_data)
                    keep_items.append(item_id)
                    # Fetch for total calculation to ensure we have latest decimals
                    updated_item = LogisticsDealItem.objects.get(id=item_id)
                    lines_subtotal += updated_item.quantity * updated_item.unit_price
                else:
                    # Create new item
                    new_item = LogisticsDealItem.objects.create(deal=instance, **item_data)
                    keep_items.append(new_item.id)
                    lines_subtotal += new_item.quantity * new_item.unit_price

            # Delete items not in the list
            instance.items.exclude(id__in=keep_items).delete()

            _apply_lines_subtotal_and_grand_total(instance, lines_subtotal)
            instance.save()
        else:
            # تعديل «شحن داخل الصين» أو الخصم وحده (بلا items) كان يترك
            # total_amount قديماً محسوباً بلا الشحن، فتُقارَن الدفعات بأساس أصغر
            # منها: نسبة إنجاز > 100% و«رصيد لصالحك عند المورد» وهمي يساوي
            # الشحن بالضبط. الإجمالي مشتق دائماً فلا يمكن أن ينحرف.
            lines_subtotal = sum(
                (item.quantity * item.unit_price for item in instance.items.all()),
                Decimal("0"),
            )
            _apply_lines_subtotal_and_grand_total(instance, lines_subtotal)
            instance.save()

        return instance

class LogisticsDealListSerializer(serializers.ModelSerializer):
    """Light contract for collection screens; nested document rows stay on retrieve."""

    partner_name = serializers.CharField(source='partner.name', read_only=True)
    partner_legal_name = serializers.CharField(
        source='partner.legal_name', read_only=True, allow_null=True, default=None
    )
    linked_shipment = serializers.SerializerMethodField()
    # G-import: «تحولت إلى فاتورة» في قائمة الصفقات — رابط لرقم الفاتورة بجانب
    # الحالة. يجب أن يكون في serializer القائمة (لا التفصيل) وإلا لا يظهر شيء.
    linked_invoice = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsDeal
        fields = [
            'id', 'ref_number', 'partner', 'partner_name', 'partner_legal_name',
            'order_date', 'total_amount', 'currency', 'status', 'description',
            'short_name', 'pi_number', 'factory_name', 'original_offer_number',
            'supplier_invoice_number', 'installment_plan_enabled',
            'current_installment_number', 'remaining_amount', 'subtotal',
            'shipping_cost_estimate', 'discount_amount', 'is_shipping_included',
            'tax_rate', 'tax_amount', 'tax_type', 'shipping_method', 'payment_method',
            'production_days', 'delivery_days', 'total_cbm', 'total_weight',
            'total_weight_kg', 'certificates', 'shipping_workflow_status',
            'created_by', 'created_at', 'linked_shipment', 'linked_invoice',
        ]
        read_only_fields = fields

    def get_linked_shipment(self, obj):
        links = list(obj.logisticsshipmentdeal_set.all())
        if not links:
            return None
        shipment = max(links, key=lambda link: link.id).shipment
        return {
            'id': shipment.id,
            'shipment_number': shipment.shipment_number or '',
            'shipment_name': shipment.shipment_name or '',
        }

    def get_linked_invoice(self, obj):
        # prefetch-aware: يستهلك prefetch الـviewset (purchase_invoices) بلا استعلام لكل صف
        invoices = list(obj.purchase_invoices.all())
        if not invoices:
            return None
        pi = max(invoices, key=lambda inv: inv.id)
        return {'id': pi.id, 'invoice_number': pi.invoice_number or ''}

class LogisticsDealShipmentSummarySerializer(serializers.ModelSerializer):
    """The fields a shipment detail needs about a linked deal, without its document."""

    partner_name = serializers.CharField(source='partner.name', read_only=True)

    class Meta:
        model = LogisticsDeal
        fields = [
            'id', 'ref_number', 'original_offer_number', 'total_amount', 'total_cbm',
            'total_weight', 'total_weight_kg', 'description', 'notes', 'factory_name',
            'partner_name',
        ]
        read_only_fields = fields

class LogisticsShipmentDealAllocationSerializer(serializers.ModelSerializer):
    """أوزان تكلفة الشحن الدولي المحفوظة لكل صفقة على الشحنة."""

    deal_ref = serializers.CharField(source="deal.ref_number", read_only=True)
    deal_title = serializers.SerializerMethodField()
    # M2/UX: expose each deal's CBM/KG so the import wizard can show the measure per
    # deal and warn when it's missing (a 0 measure means freight can't be allocated).
    deal_total_cbm = serializers.DecimalField(
        source="deal.total_cbm", max_digits=10, decimal_places=3, read_only=True)
    deal_total_weight_kg = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsShipmentDeal
        fields = ["id", "deal", "deal_ref", "deal_title", "deal_total_cbm",
                  "deal_total_weight_kg", "allocated_shipping_cost", "extra_costs"]
        read_only_fields = ["id", "deal"]

    def get_deal_total_weight_kg(self, obj):
        w = obj.deal.total_weight_kg
        if w is None:
            w = obj.deal.total_weight
        return str(w) if w is not None else "0"

    def get_deal_title(self, obj):
        """عنوان عربي للعرض (نفس منطق اسم الفاتورة) — كانت شاشة الاستيراد تعرض «—»."""
        try:
            from logistics.landed_cost import invoice_title_from_deal
            return invoice_title_from_deal(obj.deal, max_len=120)
        except Exception:
            return None
