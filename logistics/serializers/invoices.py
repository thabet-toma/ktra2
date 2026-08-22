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

# مرآة POSTED_DOC_WARNING لحالة الاستلام: استبدال بنود فاتورة استُلمت بضاعتها
# يمسح كمياتها المستلَمة وأسطر إرساليتها بينما تبقى حركات المخزون.
RECEIVED_DOC_WARNING = (
    "استُلمت بضاعة هذه الفاتورة. ألغِ إرسالية الاستلام أولاً ثم عدّل البنود."
)

























# ─── Purchase Invoice Serializers ──────────────────────────────────────────────
















# ── P-H-3: SupplierPayment ──────────────────────────────────────────















# المرحلة 3: مراجع عبر وحدات الحزمة (نفس الملف سابقاً) — لا-دوري.
from ._helpers import _deal_title_for_list_preview

class PurchaseInvoiceItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    expense_account_code = serializers.CharField(source='expense_account.code', read_only=True)
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)

    class Meta:
        model = PurchaseInvoiceItem
        fields = [
            'id', 'product', 'product_name', 'name',
            'quantity', 'received_quantity', 'unit_price', 'total_price',
            'notes', 'hs_code',
            'landed_unit_price_ils', 'landed_line_total_ils',
            'seq', 'catalog_number', 'name_snapshot', 'description_line', 'unit', 'warehouse',
            'extra_qty', 'batch_number', 'serial_number', 'manufacture_number', 'expiry_date',
            'serials',
            'line_currency', 'line_exchange_rate', 'second_date', 'is_taxable', 'vat_percent',
            'discount_percent', 'discount_amount',
            'expense_account', 'expense_account_code', 'expense_account_name',
        ]
        read_only_fields = ['id', 'received_quantity']

    def validate_serials(self, value):
        from inventory.serials import normalize_serials
        return normalize_serials(value)

    def get_product_name(self, obj):
        if obj.product:
            from inventory.services import product_display_name
            return product_display_name(obj.product)
        return obj.name

class PurchaseInvoiceFeeSerializer(serializers.ModelSerializer):
    """رسم على فاتورة شراء — مدين بحساب مصروف (أو مُرسمل للمخزون)."""
    expense_account_code = serializers.CharField(source='expense_account.code', read_only=True)
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)
    expense_account_type = serializers.CharField(source='expense_account.account_type', read_only=True)

    class Meta:
        model = PurchaseInvoiceFee
        fields = [
            'id', 'description', 'amount',
            'calculation_type', 'calculation_value', 'percentage_basis',
            'expense_account', 'expense_account_code', 'expense_account_name', 'expense_account_type',
            'capitalize_to_inventory', 'is_taxable',
        ]
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('مبلغ الرسم يجب أن يكون ≥ 0.')
        return value

    def validate_calculation_value(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('قيمة الرسم أو النسبة يجب أن تكون ≥ 0.')
        return value

    def validate_expense_account(self, value):
        # نقبل Expense (الحالة العادية) أو Asset (مثال: المخزون عند الرسملة)
        if value.account_type not in ('Expense', 'Asset'):
            raise serializers.ValidationError(
                f'حساب الرسم يجب أن يكون Expense أو Asset، '
                f'لكن الحساب المختار من نوع {value.account_type}.'
            )
        return value

class PurchaseInvoiceListSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    deal_ref = serializers.CharField(source='deal.ref_number', read_only=True, default=None)
    currency_code = serializers.CharField(source='currency.Code', read_only=True, default=None)
    items_count = serializers.IntegerField(read_only=True)
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    receipt_status_display = serializers.CharField(source='get_receipt_status_display', read_only=True)
    shipment_number = serializers.CharField(source='shipment.shipment_number', read_only=True, default=None)
    shipment_name = serializers.CharField(source='shipment.shipment_name', read_only=True, default=None)
    # اسم الصفقة المحوَّلة — نفس مصدر قائمة الصفقات (بلا تكرار منطق الاشتقاق).
    deal_title = serializers.SerializerMethodField()
    fees_total = serializers.DecimalField(
        source='list_fees_total', max_digits=18, decimal_places=2, read_only=True,
    )
    payable_total = serializers.DecimalField(
        source='list_payable_total', max_digits=18, decimal_places=2, read_only=True,
    )
    amount_paid = serializers.DecimalField(
        source='list_amount_paid', max_digits=18, decimal_places=2, read_only=True,
    )
    remaining_balance = serializers.DecimalField(
        source='list_remaining_balance', max_digits=18, decimal_places=2, read_only=True,
    )
    payment_status = serializers.CharField(source='list_payment_status', read_only=True)
    payment_status_display = serializers.SerializerMethodField()
    supplier_balance = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True,
    )

    def get_deal_title(self, obj):
        return _deal_title_for_list_preview(obj.deal) if obj.deal_id else ''

    def get_payment_status_display(self, obj):
        return {
            'paid': 'مدفوعة بالكامل',
            'partially_paid': 'مدفوعة جزئياً',
            'unpaid': 'غير مدفوعة',
        }.get(obj.list_payment_status, 'غير مدفوعة')

    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'invoice_name', 'invoice_date',
            'invoice_type',
            'partner', 'partner_name',
            'deal', 'deal_ref', 'deal_title',
            'shipment', 'shipment_number', 'shipment_name', 'clearance',
            'currency', 'currency_code', 'exchange_rate',
            'subtotal', 'discount_amount', 'tax_rate', 'tax_amount',
            'grand_total', 'status', 'status_display',
            'fees_total', 'payable_total',
            'amount_paid', 'remaining_balance',
            'payment_status', 'payment_status_display', 'supplier_balance',
            'receipt_status', 'receipt_status_display',
            'is_posted', 'is_return', 'original_invoice', 'journal_id_display',
            'items_count',
            'created_at', 'updated_at',
        ]

def read_document_images(tenant_id, related_table, related_id):
    """W7c: روابط الصور المرفقة (غير PDF) من SystemAttachment لأي مستند. مصدر قراءة
    مشترك (DRY) لعرض المرفقات — يُستخدم لفاتورة الشراء (مرآة منطق صفقة get_quote_images)."""
    try:
        from core.models import SystemAttachment

        rows = SystemAttachment.objects.filter(
            tenant_id=tenant_id, related_table=related_table, related_id=related_id,
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

def read_document_pdfs(tenant_id, related_table, related_id):
    """W7c: ملفات PDF المرفقة ({name,url,size,type}) من SystemAttachment لأي مستند."""
    try:
        from core.models import SystemAttachment

        rows = SystemAttachment.objects.filter(
            tenant_id=tenant_id, related_table=related_table, related_id=related_id,
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

class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    items = PurchaseInvoiceItemSerializer(many=True, required=False)
    fees = PurchaseInvoiceFeeSerializer(many=True, required=False)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    deal_ref = serializers.CharField(source='deal.ref_number', read_only=True, default=None)
    currency_code = serializers.CharField(source='currency.Code', read_only=True, default=None)
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    receipt_status_display = serializers.CharField(source='get_receipt_status_display', read_only=True)
    is_local = serializers.SerializerMethodField()
    # T-PLINEAGE: المستند الذي وُلدت منه الفاتورة (عرض سعر أو طلبية) — الفاتورة
    # كانت صامتة عن أصلها، فلا سبيل للرجوع إلى العرض الذي سعّرها.
    source_document = serializers.SerializerMethodField()
    # W7a: رقم الفاتورة الأصلية — لعرض رابط «الفاتورة الأصلية #» في مستند المرجع.
    original_invoice_number = serializers.CharField(
        source='original_invoice.invoice_number', read_only=True, default=None,
    )
    # task16 C10: المبلغ المدفوع + المتبقي + حالة الدفع (مدفوعة/جزئياً/غير مدفوعة)
    amount_paid = serializers.SerializerMethodField()
    remaining_balance = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_status_display = serializers.SerializerMethodField()
    fees_total = serializers.SerializerMethodField()
    payable_total = serializers.SerializerMethodField()
    supplier_balance_current = serializers.DecimalField(
        source='supplier_balance', max_digits=18, decimal_places=2, read_only=True,
    )
    supplier_balance_before_invoice = serializers.SerializerMethodField()
    supplier_balance_after_invoice = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()
    cash_or_bank_account_name = serializers.CharField(
        source='cash_or_bank_account.name', read_only=True, default=None,
    )
    cash_or_bank_account_code = serializers.CharField(
        source='cash_or_bank_account.code', read_only=True, default=None,
    )
    # P-H-1: exposed for payment-voucher endpoint (read-only)
    cheques = serializers.SerializerMethodField()
    # W7c: مرفقات الفاتورة/المرجع (صور + PDF) من SystemAttachment — قراءة فقط،
    # الحفظ في PurchaseInvoiceViewSet._sync_attachments (نمط الموردين/المنتجات).
    quote_images = serializers.SerializerMethodField()
    quote_pdfs = serializers.SerializerMethodField()
    invoice_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    shipment_number = serializers.CharField(source='shipment.shipment_number', read_only=True, default=None)
    shipment_name = serializers.CharField(source='shipment.shipment_name', read_only=True, default=None)
    from tenants.models import Currency
    currency = serializers.SlugRelatedField(
        slug_field='Code',
        queryset=Currency.objects.all(),
        required=True
    )

    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'invoice_name', 'invoice_date',
            'invoice_type',
            'partner', 'partner_name',
            'deal', 'deal_ref',
            'shipment', 'shipment_number', 'shipment_name',
            'clearance',
            'currency', 'currency_code', 'exchange_rate',
            'subtotal', 'discount_amount',
            'tax_rate', 'tax_amount', 'tax_type',
            'shipping_cost', 'shipping_included',
            'grand_total',
            'payment_type',
            'cash_or_bank_account', 'cash_or_bank_account_name', 'cash_or_bank_account_code',
            'attached_cash_amount',
            # local_payments_json / conversion_metadata_json: dropped in P-D-8.
            # `to_representation` still emits the keys in the JSON payload from
            # the landed-cost live payload, but they are no longer model fields.
            # firestore_id: dropped in P-K-3 (migration 0042).
            'status', 'status_display', 'notes',
            'receipt_status', 'receipt_status_display', 'is_local',
            'source_document',
            'amount_paid', 'remaining_balance', 'payment_status', 'payment_status_display',
            'supplier_balance_current', 'supplier_balance_before_invoice',
            'supplier_balance_after_invoice', 'payment_details',
            'fees_total', 'payable_total',
            'supplier_invoice_number', 'factory_name',
            'is_posted', 'is_return', 'original_invoice', 'original_invoice_number',
            'journal', 'journal_id_display',
            'items', 'fees', 'cheques',
            'quote_images', 'quote_pdfs',
            'created_at', 'updated_at', 'created_by',
        ]
        read_only_fields = ['id', 'is_posted', 'is_return', 'original_invoice', 'journal', 'created_at', 'updated_at', 'receipt_status']

    def get_is_local(self, obj):
        """فاتورة محلية = غير مستوردة (بلا صفقة/شحنة/تخليص) — قابلة للاستلام للمخزن."""
        return not (obj.deal_id or obj.shipment_id or obj.clearance_id)

    def get_source_document(self, obj):
        """المستند الأب: طلبية شراء أو عرض سعر محوَّل مباشرةً — بالرقم والمعرّف.

        الطلبية المولودة من عرض تحمل جدّها في `origin_*`، فيصل المستخدم إلى
        العرض الذي بدأ السلسلة بنقرة واحدة بدل تتبّعه يدوياً.
        """
        order = getattr(obj, 'source_purchase_order', None)
        if order is not None:
            return {
                'kind': 'order',
                'id': order.id,
                'number': order.order_number,
                'origin_kind': 'quotation' if order.quotation_id else None,
                'origin_id': order.quotation_id,
                'origin_number': (
                    order.quotation.quotation_number if order.quotation_id else None
                ),
            }
        if obj.source_quotation_id:
            return {
                'kind': 'quotation',
                'id': obj.source_quotation_id,
                'number': obj.source_quotation.quotation_number,
                'origin_kind': None,
                'origin_id': None,
                'origin_number': None,
            }
        return None

    def get_quote_images(self, obj):
        return read_document_images(obj.tenant_id, 'purchase_invoices', obj.id)

    def get_quote_pdfs(self, obj):
        return read_document_pdfs(obj.tenant_id, 'purchase_invoices', obj.id)

    def _computed_amount_paid(self, obj) -> Decimal:
        return purchase_invoice_payment_summary(obj)['amount_paid']

    @staticmethod
    def _fees_total(obj) -> Decimal:
        return purchase_invoice_payment_summary(obj)['fees_total']

    def _payable_total(self, obj) -> Decimal:
        return purchase_invoice_payment_summary(obj)['payable_total']

    def get_fees_total(self, obj):
        return str(self._fees_total(obj))

    def get_payable_total(self, obj):
        return str(self._payable_total(obj))

    def get_amount_paid(self, obj):
        return str(self._computed_amount_paid(obj))

    def get_remaining_balance(self, obj):
        return str(purchase_invoice_payment_summary(obj)['remaining_balance'])

    def get_payment_status(self, obj):
        return purchase_invoice_payment_summary(obj)['payment_status']

    def get_payment_status_display(self, obj):
        return purchase_invoice_payment_summary(obj)['payment_status_display']

    def _balance_summary(self, obj):
        summary = purchase_invoice_payment_summary(obj)
        return document_partner_balance_summary(
            getattr(obj, 'supplier_balance', 0),
            summary['remaining_balance'],
            obj.exchange_rate,
            is_posted=obj.is_posted,
            direction=-1 if obj.is_return else 1,
        )

    def get_supplier_balance_before_invoice(self, obj):
        return str(self._balance_summary(obj)['balance_before'])

    def get_supplier_balance_after_invoice(self, obj):
        return str(self._balance_summary(obj)['balance_after'])

    def get_payment_details(self, obj):
        details = []
        for payment in obj.supplier_payments.all():
            details.append({
                'source': 'supplier_payment',
                'id': payment.id,
                'payment_date': payment.payment_date,
                'amount': str(payment.amount),
                'currency_code': payment.currency.Code,
                'exchange_rate': str(payment.exchange_rate),
                'cash_or_bank_account_name': payment.cash_or_bank_account.name,
                'is_posted': payment.is_posted,
                'journal': payment.journal_id,
                'notes': payment.notes or '',
            })
        for payment in obj.payments.all():
            details.append({
                'source': 'purchase_invoice_payment',
                'id': payment.id,
                'payment_date': payment.payment_date,
                'amount': str(payment.amount),
                'currency_code': payment.currency.Code,
                'exchange_rate': str(payment.exchange_rate),
                'cash_or_bank_account_name': payment.cash_or_bank_account.name,
                'is_posted': payment.is_posted,
                'journal': payment.journal_id,
                'notes': payment.notes or '',
            })
        return sorted(details, key=lambda row: (row['payment_date'], row['id']), reverse=True)

    def validate(self, attrs):
        payment_type = attrs.get('payment_type') or (
            self.instance.payment_type if self.instance else 'credit'
        )
        cash_acc = attrs.get(
            'cash_or_bank_account',
            self.instance.cash_or_bank_account if self.instance else None,
        )
        if payment_type == 'cash' and not cash_acc:
            raise serializers.ValidationError({
                'cash_or_bank_account': 'الدفع النقدي يتطلب اختيار حساب صندوق/بنك.'
            })
        # نمط «بدون» في إعدادات الشراء: لا تُخزَّن أرقام تسلسلية على البنود إطلاقاً.
        from core.tenant_utils import get_tenant
        from inventory.serials import purchase_serial_mode, strip_serials_when_off

        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and attrs.get('items'):
            strip_serials_when_off(
                attrs['items'], purchase_serial_mode(tenant.TenantID),
            )
        return attrs

    def get_cheques(self, obj):
        return [
            {
                'id': c.id,
                'cheque_number': c.cheque_number,
                'bank_name': c.bank_name,
                'amount': str(c.amount),
                'status': c.status,
                'direction': c.direction,
                'due_date': c.due_date.isoformat() if c.due_date else None,
                'issue_date': c.issue_date.isoformat() if c.issue_date else None,
                'payee_name': c.payee_name,
                'notes': c.notes,
            }
            for c in obj.cheques.all()
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(instance, 'is_posted', False):
            return data
        try:
            from logistics.landed_cost import (
                compute_live_purchase_invoice_read_payload,
                _json_friendly_value,
            )
        except Exception:
            return data
        live = compute_live_purchase_invoice_read_payload(instance)
        if not live:
            return data
        conv = live.get('conversion_metadata_json')
        if isinstance(conv, dict):
            data['conversion_metadata_json'] = _json_friendly_value(conv)
        for k in ('subtotal', 'shipping_cost'):
            if k in live and live[k] is not None:
                data[k] = _json_friendly_value(live[k])
        try:
            live_subtotal = Decimal(str(data.get('subtotal') or 0))
            live_shipping = Decimal(str(data.get('shipping_cost') or 0))
            transfer_commissions = Decimal('0')
            if isinstance(conv, dict):
                line_meta = conv.get('line_meta') if isinstance(conv.get('line_meta'), dict) else {}
                transfer_commissions = Decimal(str(
                    conv.get('deal_transfer_commissions_ils')
                    or line_meta.get('deal_transfer_commissions_ils')
                    or 0
                ))
            vat_base = max(
                Decimal('0'),
                live_subtotal - Decimal(str(instance.discount_amount or 0))
                + live_shipping + transfer_commissions,
            )
            if instance.tax_type == 'amount':
                live_tax = Decimal(str(instance.tax_amount or 0))
            else:
                live_tax = (vat_base * Decimal(str(instance.tax_rate or 0)) / Decimal('100')).quantize(
                    Decimal('0.01')
                )
            live_grand = (vat_base + live_tax).quantize(Decimal('0.01'))
            live_payable = (live_grand + self._fees_total(instance)).quantize(Decimal('0.01'))
            paid = min(Decimal(str(data.get('amount_paid') or 0)), live_payable)
            remaining = (live_payable - paid).quantize(Decimal('0.01'))
            payment_status = (
                'paid' if live_payable > 0 and paid >= live_payable - Decimal('0.01')
                else 'partially_paid' if paid > 0
                else 'unpaid'
            )
            data['tax_amount'] = _json_friendly_value(live_tax)
            data['grand_total'] = _json_friendly_value(live_grand)
            data['payable_total'] = str(live_payable)
            data['amount_paid'] = str(paid.quantize(Decimal('0.01')))
            data['remaining_balance'] = str(remaining)
            data['payment_status'] = payment_status
            data['payment_status_display'] = {
                'paid': 'مدفوعة',
                'partially_paid': 'مدفوعة جزئياً',
                'unpaid': 'غير مدفوعة',
            }[payment_status]
        except (ArithmeticError, TypeError, ValueError):
            logger.exception('Failed to reconcile live purchase invoice totals invoice=%s', instance.pk)
        live_lp = live.get('local_payments_json')
        stored_lp = data.get('local_payments_json')
        if isinstance(live_lp, dict):
            # live يعيد فقط ما يبنيه landed cost (رسوم تخليص مخصصة…) — لا يمسّ بنود الضرائب/الرسوم الإضافية
            # التي يحررها المستخدم؛ استبدال كامل كان يمحو taxesAndFeesLines بعد كل GET.
            base = dict(stored_lp) if isinstance(stored_lp, dict) else {}
            merged = {**base}
            for k, v in live_lp.items():
                if k in ('taxesAndFeesLines', 'taxes_and_fees_lines'):
                    continue
                merged[k] = v
            data['local_payments_json'] = _json_friendly_value(merged)
        if live.get('shipping_included') is not None:
            data['shipping_included'] = bool(live['shipping_included'])
        live_items = live.get('items') or []
        by_key = {}
        for row in live_items:
            key = (str(row.get('product') or ''), str(row.get('name') or '').strip())
            by_key[key] = row
        for it in data.get('items') or []:
            key = (str(it.get('product') or ''), str(it.get('name') or '').strip())
            row = by_key.get(key)
            if not row:
                continue
            if row.get('landed_unit_price_ils') is not None:
                it['landed_unit_price_ils'] = _json_friendly_value(row['landed_unit_price_ils'])
            if row.get('landed_line_total_ils') is not None:
                it['landed_line_total_ils'] = _json_friendly_value(row['landed_line_total_ils'])
        return data

    @staticmethod
    def _bind_import_expense_account(invoice, fee_data):
        """رسوم الفاتورة الدولية: اسم الرسم يحدّد حسابه تحت «53 مصاريف الاستيراد».

        الضمان هنا على الخادم لا في الواجهة: ربط الواجهة يحدث عند الخروج من خانة
        الاسم فقط، فلو رُحّلت الفاتورة قبل حفظ ذلك الربط بقي الرسم على الحساب
        الافتراضي (5307) وظهر الأستاذ العام للحساب الجديد فارغاً. نحصر إعادة الربط
        بالحساب الافتراضي/الفارغ حتى لا نلغي حساباً اختاره المستخدم عمداً.
        """
        if invoice.invoice_type != PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL:
            return fee_data
        description = str(fee_data.get('description') or '').strip()
        if not description:
            return fee_data
        current = fee_data.get('expense_account')
        current_code = str(getattr(current, 'code', '') or '')
        if current is not None and current_code != '5307':
            return fee_data
        from accounting.services import resolve_import_expense_account
        account, created = resolve_import_expense_account(invoice.tenant_id, description)
        if account is None:
            return fee_data
        if current is None or account.pk != getattr(current, 'pk', None):
            logger.info(
                'purchase invoice fee bound to import expense account invoice=%s '
                'fee=%s account=%s created=%s',
                invoice.pk, description, account.code, created,
            )
        fee_data['expense_account'] = account
        return fee_data

    @staticmethod
    def _normalize_fee_amount(invoice, fee_data):
        calculation_type = fee_data.get(
            'calculation_type', PurchaseInvoiceFee.CALCULATION_AMOUNT,
        )
        if 'calculation_value' in fee_data:
            calculation_value = Decimal(str(fee_data.get('calculation_value') or 0))
        else:
            calculation_value = Decimal(str(fee_data.get('amount') or 0))
        percentage_basis = fee_data.get(
            'percentage_basis', PurchaseInvoiceFee.BASIS_GOODS,
        )
        if calculation_type == PurchaseInvoiceFee.CALCULATION_PERCENTAGE:
            if percentage_basis == PurchaseInvoiceFee.BASIS_AFTER_MAIN_VAT:
                basis = Decimal(str(invoice.grand_total or 0))
            else:
                basis = max(
                    Decimal('0'),
                    Decimal(str(invoice.subtotal or 0))
                    - Decimal(str(invoice.discount_amount or 0))
                    + Decimal(str(invoice.shipping_cost or 0)),
                )
            amount = (basis * calculation_value / Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )
        else:
            calculation_type = PurchaseInvoiceFee.CALCULATION_AMOUNT
            percentage_basis = PurchaseInvoiceFee.BASIS_GOODS
            amount = calculation_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        fee_data['calculation_type'] = calculation_type
        fee_data['calculation_value'] = calculation_value
        fee_data['percentage_basis'] = percentage_basis
        fee_data['amount'] = amount
        return fee_data

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        fees_data = validated_data.pop('fees', [])
        invoice = PurchaseInvoice.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseInvoiceItem.objects.create(invoice=invoice, **item_data)
        for fee_data in fees_data:
            fee_data = self._normalize_fee_amount(invoice, fee_data)
            fee_data = self._bind_import_expense_account(invoice, fee_data)
            PurchaseInvoiceFee.objects.create(
                invoice=invoice, tenant=invoice.tenant, **fee_data,
            )
        if fees_data:
            logger.info('purchase invoice fees created invoice=%s count=%s', invoice.pk, len(fees_data))
        return invoice

    def _reject_edit_of_received_items(self, instance):
        """بنود فاتورة استُلمت بضاعتها لا تُستبدل — أُلغِ الإرسالية أولاً.

        استبدال البنود هنا حذفٌ وإعادة إنشاء: `received_quantity` يعود صفراً
        (حقل للقراءة فقط فلا يصل في الحمولة)، وأسطر الإرسالية تسقط بالـCASCADE
        (`GoodsReceiptLine.item`) — بينما حركات المخزون وقيدها تبقى. النتيجة
        مخزنٌ يحمل البضاعة وفاتورةٌ تقول لم يُستلَم شيء، وإرسالية بلا أسطر لا
        يقدر `void_goods_receipt` على عكسها.

        الحارس هنا لا في الـview: هذا موضع الحذف، فيغطّي كل مستدعٍ للـserializer.
        الفاتورة المرحّلة يمنعها حارسها في `perform_update`؛ وهذا يغطّي النافذة
        المتبقية — فاتورة غير مرحّلة استُلمت بلا قيد (قيمة صفرية).
        """
        received = [
            it for it in instance.items.all()
            if Decimal(str(it.received_quantity or 0)) > 0
        ]
        if not received:
            return
        logger.info(
            'purchase invoice item edit rejected — already received invoice=%s items=%s',
            instance.pk, len(received),
        )
        raise serializers.ValidationError({'detail': RECEIVED_DOC_WARNING})

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        fees_data = validated_data.pop('fees', None)
        if items_data is not None:
            self._reject_edit_of_received_items(instance)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseInvoiceItem.objects.create(invoice=instance, **item_data)

        if fees_data is not None:
            instance.fees.all().delete()
            for fee_data in fees_data:
                fee_data = self._normalize_fee_amount(instance, fee_data)
                fee_data = self._bind_import_expense_account(instance, fee_data)
                PurchaseInvoiceFee.objects.create(
                    invoice=instance, tenant=instance.tenant, **fee_data,
                )
            logger.info('purchase invoice fees replaced invoice=%s count=%s', instance.pk, len(fees_data))

        return instance
