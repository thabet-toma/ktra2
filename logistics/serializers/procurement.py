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
    PurchaseRFQ,
    PurchaseRFQLine,
    PurchaseRFQRecipient,
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















class SupplierQuotationLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name_ar', read_only=True)

    class Meta:
        model = SupplierQuotationLine
        fields = [
            'id', 'product', 'product_name', 'seq', 'name_snapshot',
            'description_line', 'quantity', 'unit_price', 'line_total',
        ]
        read_only_fields = ['id', 'product_name', 'line_total']
        # T-DRAFTPARTY: بند بلا منتج مسجَّل مسموح — اسمه النصّي يكفي داخل العرض.
        extra_kwargs = {
            'product': {'required': False, 'allow_null': True},
        }

class SupplierQuotationSerializer(serializers.ModelSerializer):
    lines = SupplierQuotationLineSerializer(many=True)
    # T-DRAFTPARTY: اسم الطرف المعروض = المورد المسجَّل أو الاسم المبدئي.
    supplier_name = serializers.SerializerMethodField()
    is_draft_supplier = serializers.SerializerMethodField()
    currency_code = serializers.CharField(source='currency.Code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    converted_deal = serializers.SerializerMethodField()
    # T-PLINEAGE: المستند الناتج عن التحويل بالاسم والمعرّف — «محوَّل» بلا وجهة
    # لا يقود إلى شيء، والواجهة تحتاج المعرّف لفتحه بنقرة.
    converted_order = serializers.SerializerMethodField()
    converted_invoice = serializers.SerializerMethodField()

    class Meta:
        model = SupplierQuotation
        fields = [
            'id', 'quotation_number', 'scope', 'supplier', 'supplier_name',
            'supplier_draft_name', 'is_draft_supplier',
            'quotation_date', 'valid_until', 'status', 'status_display',
            'scope_display', 'currency', 'exchange_rate', 'subtotal',
            'currency_code',
            'discount_amount', 'tax_rate', 'tax_amount', 'grand_total',
            'shipping_cost_estimate', 'is_shipping_included', 'incoterms',
            'shipping_method', 'payment_method', 'production_days',
            'delivery_days', 'total_cbm', 'total_weight_kg',
            'order_name', 'order_description', 'notes',
            'alibaba_link', 'supplier_contact', 'decision_reason', 'attachments',
            'notes_log',
            'lines', 'converted_deal', 'converted_order', 'converted_invoice',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'subtotal', 'tax_amount', 'grand_total', 'converted_deal',
            'converted_order', 'converted_invoice', 'is_draft_supplier',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'quotation_number': {'required': False, 'allow_blank': True},
            'supplier': {'required': False, 'allow_null': True},
            'supplier_draft_name': {'required': False, 'allow_blank': True},
        }

    def get_supplier_name(self, obj):
        if obj.supplier_id:
            return obj.supplier.name
        return obj.supplier_draft_name

    def get_is_draft_supplier(self, obj):
        return not obj.supplier_id and bool(obj.supplier_draft_name)

    def get_converted_deal(self, obj):
        try:
            deal = obj.import_deal
        except LogisticsDeal.DoesNotExist:
            return None
        return {'id': deal.id, 'ref_number': deal.ref_number, 'stage': deal.stage}

    def get_converted_order(self, obj):
        # ISSUE #112: local_order صار FK عكسياً (manager) بعد رفع OneToOne.
        order = obj.local_order.first()
        if order is None:
            return None
        return {'id': order.id, 'order_number': order.order_number, 'status': order.status}

    def get_converted_invoice(self, obj):
        """الفاتورة الناتجة — مباشرةً من العرض أو عبر الطلبية التي وُلدت منه."""
        invoice = obj.local_invoice.first()
        if invoice is None:
            order = obj.local_order.first()
            invoice = order.invoice if order else None
        if invoice is None:
            return None
        return {
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'status': invoice.status,
        }

    def _stamp_notes_log(self, notes_log, instance):
        """T-OFFERSTATE: ختم تاريخ كل ملاحظة **في الخادم**.

        ساعة المتصفح ليست مصدراً موثوقاً لتاريخ ملاحظة تُقرأ بعد أشهر. الملاحظة
        التي وصلت بتاريخ سابق تحتفظ به (إعادة حفظ النموذج لا تُعيد تأريخ القديم)،
        والجديدة تُختم بوقت الخادم وباسم كاتبها.
        """
        if not isinstance(notes_log, list):
            raise serializers.ValidationError({
                'notes_log': 'الملاحظات يجب أن تكون قائمة.',
            })
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        author = (
            user.get_username()
            if user is not None and getattr(user, 'is_authenticated', False)
            else ''
        )
        now = timezone.now().isoformat()
        known_dates = {
            str(entry.get('at') or '')
            for entry in (getattr(instance, 'notes_log', None) or [])
            if isinstance(entry, dict)
        }
        stamped = []
        for entry in notes_log:
            if not isinstance(entry, dict):
                raise serializers.ValidationError({
                    'notes_log': 'كل ملاحظة يجب أن تكون كائناً يحمل نصاً.',
                })
            text = str(entry.get('text') or '').strip()
            if not text:
                raise serializers.ValidationError({
                    'notes_log': 'الملاحظة الفارغة لا تُحفظ.',
                })
            at = str(entry.get('at') or '')
            keep_original = at in known_dates and at != ''
            stamped.append({
                'text': text,
                'at': at if keep_original else now,
                'by': str(entry.get('by') or '') if keep_original else author,
            })
        return stamped

    def validate(self, attrs):
        tenant = get_tenant(self.context.get('request'))
        if tenant is None:
            raise serializers.ValidationError({'tenant': 'لا يوجد شركة محددة لهذا الطلب.'})

        instance = self.instance
        if instance and instance.status == SupplierQuotation.STATUS_CONVERTED:
            raise serializers.ValidationError('عرض السعر المحوّل لا يمكن تعديله.')

        supplier = attrs.get('supplier', getattr(instance, 'supplier', None))
        if supplier and supplier.tenant_id != tenant.pk:
            raise serializers.ValidationError({'supplier': 'المورد لا يتبع الشركة الحالية.'})
        if supplier and supplier.partner_type != 'Supplier':
            raise serializers.ValidationError({'supplier': 'الشريك المحدد ليس مورداً.'})

        # T-DRAFTPARTY: مورد مسجَّل **أو** اسم مبدئي — لا عرضَ بلا طرف، ولا اسمَ
        # مبدئياً معلّقاً بجانب مورد مسجَّل (فأيّهما الطرف حينها؟).
        draft_name = str(attrs.get(
            'supplier_draft_name', getattr(instance, 'supplier_draft_name', ''),
        ) or '').strip()
        if supplier is None and not draft_name:
            raise serializers.ValidationError({
                'supplier': 'اختر مورداً مسجَّلاً أو اكتب اسم مورد مبدئي.',
            })
        if supplier is not None:
            draft_name = ''
        if 'supplier_draft_name' in attrs or supplier is not None:
            attrs['supplier_draft_name'] = draft_name

        scope = attrs.get('scope', getattr(instance, 'scope', SupplierQuotation.SCOPE_LOCAL))
        tax_rate = attrs.get('tax_rate', getattr(instance, 'tax_rate', Decimal('0')))
        if scope == SupplierQuotation.SCOPE_IMPORT and Decimal(str(tax_rate or 0)) != 0:
            raise serializers.ValidationError({
                'tax_rate': 'عرض الاستيراد لا يتضمن الضريبة؛ تُسجل الضريبة عند التخليص.',
            })

        status_value = attrs.get('status', getattr(instance, 'status', SupplierQuotation.STATUS_DRAFT))
        if status_value == SupplierQuotation.STATUS_CONVERTED:
            raise serializers.ValidationError({
                'status': 'حالة converted تُعيّن فقط بواسطة عملية التحويل.',
            })

        # T-IMPOFFER: «غير ملائم» يلزمه سبب — في نطاق **الاستيراد** وحده، حيث
        # القرار مطلبٌ صريح للمالك. عرض الشراء المحلي يبقى كما كان (سبب اختياري)
        # فلا يتغيّر سلوك شاشة قائمة لم يُطلب تغييرها.
        # T-OFFERSTATE: و«بانتظار معلومات» يلزمها **بانتظار ماذا** — حالة انتظار
        # بلا مُنتظَر لا تقول شيئاً لمن يفتح القائمة بعد أسبوع.
        # وأي حالة أخرى تمحو التفصيل القديم كي لا يبقى عرضٌ مقبول حاملاً سبب رفض.
        reason = attrs.get(
            'decision_reason', getattr(instance, 'decision_reason', ''),
        )
        if status_value in (
            SupplierQuotation.STATUS_REJECTED, SupplierQuotation.STATUS_PENDING_INFO,
        ):
            if scope == SupplierQuotation.SCOPE_IMPORT and not str(reason or '').strip():
                raise serializers.ValidationError({
                    'decision_reason': (
                        'اذكر سبب اعتبار العرض غير ملائم.'
                        if status_value == SupplierQuotation.STATUS_REJECTED
                        else 'اذكر ما يُنتظَر وصوله من المورد.'
                    ),
                })
        elif str(reason or '').strip():
            attrs['decision_reason'] = ''

        notes_log = attrs.get('notes_log')
        if notes_log is not None:
            attrs['notes_log'] = self._stamp_notes_log(notes_log, instance)

        attachments = attrs.get('attachments')
        if attachments is not None:
            if not isinstance(attachments, list):
                raise serializers.ValidationError({
                    'attachments': 'المرفقات يجب أن تكون قائمة ملفات.',
                })
            for entry in attachments:
                if not isinstance(entry, dict) or not str(entry.get('url') or '').strip():
                    raise serializers.ValidationError({
                        'attachments': 'كل مرفق يجب أن يحمل رابط ملف (url).',
                    })

        quotation_date = attrs.get(
            'quotation_date', getattr(instance, 'quotation_date', None),
        )
        valid_until = attrs.get('valid_until', getattr(instance, 'valid_until', None))
        if quotation_date and valid_until and valid_until < quotation_date:
            raise serializers.ValidationError({
                'valid_until': 'تاريخ الصلاحية يجب ألا يسبق تاريخ العرض.',
            })

        lines = attrs.get('lines')
        if instance is None and not lines:
            raise serializers.ValidationError({'lines': 'يجب إضافة منتج واحد على الأقل.'})
        if lines is not None:
            seen_seq = set()
            for index, line in enumerate(lines, start=1):
                product = line.get('product')
                if product is not None and product.tenant_id != tenant.pk:
                    raise serializers.ValidationError({
                        'lines': f'المنتج في السطر {index} لا يتبع الشركة الحالية.',
                    })
                # T-DRAFTPARTY: السطر بلا منتج مسجّل يلزمه اسم نصّي يبقى داخل العرض.
                if product is None and not str(line.get('name_snapshot') or '').strip():
                    raise serializers.ValidationError({
                        'lines': f'اكتب اسم المنتج في السطر {index} أو اختره من المنتجات.',
                    })
                seq = line.get('seq', index)
                if seq in seen_seq:
                    raise serializers.ValidationError({
                        'lines': f'رقم ترتيب السطر {seq} مكرر.',
                    })
                seen_seq.add(seq)

        discount = Decimal(str(attrs.get(
            'discount_amount', getattr(instance, 'discount_amount', 0),
        ) or 0))
        shipping = Decimal(str(attrs.get(
            'shipping_cost_estimate',
            getattr(instance, 'shipping_cost_estimate', 0),
        ) or 0))
        if discount < 0:
            raise serializers.ValidationError({'discount_amount': 'الخصم لا يمكن أن يكون سالباً.'})
        if shipping < 0:
            raise serializers.ValidationError({
                'shipping_cost_estimate': 'تكلفة الشحن لا يمكن أن تكون سالبة.',
            })
        return attrs

    @staticmethod
    def _line_values(quotation, line, index):
        product = line.get('product')
        quantity = Decimal(str(line['quantity']))
        unit_price = Decimal(str(line['unit_price']))
        return {
            **line,
            'tenant': quotation.tenant,
            'quotation': quotation,
            'product': product,
            'seq': line.get('seq') or index,
            'name_snapshot': line.get('name_snapshot')
            or getattr(product, 'name_ar', '')
            or getattr(product, 'name_en', ''),
            'line_total': (quantity * unit_price).quantize(Decimal('0.01')),
        }

    @staticmethod
    def _recalculate(quotation):
        subtotal = sum(
            (line.line_total for line in quotation.lines.all()),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        discount = Decimal(str(quotation.discount_amount or 0))
        if discount > subtotal:
            raise serializers.ValidationError({
                'discount_amount': 'الخصم لا يمكن أن يتجاوز مجموع البنود.',
            })
        taxable = subtotal - discount
        tax_amount = (
            taxable * Decimal(str(quotation.tax_rate or 0)) / Decimal('100')
        ).quantize(Decimal('0.01'))
        shipping = (
            Decimal('0')
            if quotation.is_shipping_included
            else Decimal(str(quotation.shipping_cost_estimate or 0))
        )
        quotation.subtotal = subtotal
        quotation.tax_amount = tax_amount
        quotation.grand_total = (taxable + tax_amount + shipping).quantize(Decimal('0.01'))
        quotation.save(update_fields=['subtotal', 'tax_amount', 'grand_total', 'updated_at'])

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines')
        quotation = SupplierQuotation.objects.create(**validated_data)
        SupplierQuotationLine.objects.bulk_create([
            SupplierQuotationLine(**self._line_values(quotation, line, index))
            for index, line in enumerate(lines, start=1)
        ])
        self._recalculate(quotation)
        return quotation

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        instance = super().update(instance, validated_data)
        if lines is not None:
            instance.lines.all().delete()
            SupplierQuotationLine.objects.bulk_create([
                SupplierQuotationLine(**self._line_values(instance, line, index))
                for index, line in enumerate(lines, start=1)
            ])
        self._recalculate(instance)
        return instance


# ── ISSUE #112 — الطلبية (طلب عروض): الأبّ الذي يسبق `SupplierQuotation` ───

class PurchaseRFQLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name_ar', read_only=True)

    class Meta:
        model = PurchaseRFQLine
        fields = [
            'id', 'product', 'product_name', 'seq', 'name_snapshot',
            'specs', 'quantity', 'unit_of_measure', 'estimated_price',
        ]
        read_only_fields = ['id', 'product_name']
        # نفس نمط SupplierQuotationLine: بند بلا منتج مسجَّل مسموح — اسمه
        # النصّي يكفي داخل الطلبية.
        extra_kwargs = {
            'product': {'required': False, 'allow_null': True},
        }


class PurchaseRFQRecipientSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    quotation_number = serializers.CharField(
        source='quotation.quotation_number', read_only=True, default=None,
    )

    class Meta:
        model = PurchaseRFQRecipient
        fields = [
            'id', 'supplier', 'supplier_name', 'share', 'quotation',
            'quotation_number', 'sent_at', 'replied_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'supplier_name', 'share', 'quotation', 'quotation_number',
            'sent_at', 'replied_at', 'created_at',
        ]


class PurchaseRFQSerializer(serializers.ModelSerializer):
    lines = PurchaseRFQLineSerializer(many=True)
    recipients = PurchaseRFQRecipientSerializer(many=True, read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # ISSUE #112 §٧: «وردت عروض» تُعدّ ولا تُكتب — عدّادان مشتقّان من الردود،
    # لا حقلٌ مخزَّن.
    recipients_count = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRFQ
        fields = [
            'id', 'rfq_number', 'scope', 'scope_display', 'rfq_date',
            'status', 'status_display', 'reply_deadline', 'notes',
            'lines', 'recipients', 'recipients_count', 'replies_count',
            'created_at', 'updated_at',
        ]
        # rfq_number/status: لا يُكتبان مباشرةً — يُخصَّصان عبر أفعال دورة الحياة
        # (`send`/`cancel`/`award`) لا عبر PATCH عام. رقم الطلبية يُخصَّص عند
        # أوّل إرسال لا عند الإنشاء (لا تُحرق مسودّةٌ مهجورة رقماً).
        read_only_fields = [
            'id', 'rfq_number', 'status', 'status_display', 'scope_display',
            'recipients', 'recipients_count', 'replies_count',
            'created_at', 'updated_at',
        ]

    def get_recipients_count(self, obj):
        return len(obj.recipients.all())

    def get_replies_count(self, obj):
        return len([r for r in obj.recipients.all() if r.replied_at])

    def validate(self, attrs):
        tenant = get_tenant(self.context.get('request'))
        if tenant is None:
            raise serializers.ValidationError({'tenant': 'لا يوجد شركة محددة لهذا الطلب.'})

        instance = self.instance
        # ISSUE #112 §٧: البنود تُقفل عند **أوّل إرسال** لا عند الترسية —
        # تعديل كمية بعد ورود عروض يجعل المقارنة كذباً صامتاً. المسموح بعد
        # الإرسال: الملاحظات والمهلة وحدهما (إضافة مستقبِل والإلغاء أفعالٌ
        # مستقلّة لا تمرّ من هنا). من أراد تعديل البنود: نسخة جديدة.
        if instance is not None and instance.status != PurchaseRFQ.STATUS_DRAFT:
            allowed_fields = {'notes', 'reply_deadline'}
            offending = sorted(set(attrs.keys()) - allowed_fields)
            if offending:
                raise serializers.ValidationError(
                    'الطلبية بعد الإرسال: التعديل يقتصر على الملاحظات والمهلة'
                    f' — الحقول التالية ممنوعة: {", ".join(offending)}.'
                )

        lines = attrs.get('lines')
        if instance is None and not lines:
            raise serializers.ValidationError({'lines': 'يجب إضافة بند واحد على الأقل.'})
        if lines is not None:
            seen_seq = set()
            for index, line in enumerate(lines, start=1):
                product = line.get('product')
                if product is not None and product.tenant_id != tenant.pk:
                    raise serializers.ValidationError({
                        'lines': f'المنتج في السطر {index} لا يتبع الشركة الحالية.',
                    })
                if product is None and not str(line.get('name_snapshot') or '').strip():
                    raise serializers.ValidationError({
                        'lines': f'اكتب اسم المنتج في السطر {index} أو اختره من المنتجات.',
                    })
                seq = line.get('seq', index)
                if seq in seen_seq:
                    raise serializers.ValidationError({
                        'lines': f'رقم ترتيب السطر {seq} مكرر.',
                    })
                seen_seq.add(seq)
        return attrs

    @staticmethod
    def _line_values(rfq, line, index):
        product = line.get('product')
        return {
            **line,
            'tenant': rfq.tenant,
            'rfq': rfq,
            'product': product,
            'seq': line.get('seq') or index,
            'name_snapshot': line.get('name_snapshot')
            or getattr(product, 'name_ar', '')
            or getattr(product, 'name_en', ''),
        }

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines')
        rfq = PurchaseRFQ.objects.create(**validated_data)
        PurchaseRFQLine.objects.bulk_create([
            PurchaseRFQLine(**self._line_values(rfq, line, index))
            for index, line in enumerate(lines, start=1)
        ])
        return rfq

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        instance = super().update(instance, validated_data)
        if lines is not None:
            instance.lines.all().delete()
            PurchaseRFQLine.objects.bulk_create([
                PurchaseRFQLine(**self._line_values(instance, line, index))
                for index, line in enumerate(lines, start=1)
            ])
        return instance


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name_ar', read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            'id', 'product', 'product_name', 'seq', 'name_snapshot',
            'description_line', 'quantity', 'unit_price', 'line_total',
        ]
        read_only_fields = ['id', 'product_name', 'line_total']

class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    currency_code = serializers.CharField(source='currency.Code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    quotation_number = serializers.CharField(
        source='quotation.quotation_number', read_only=True, default=None,
    )
    invoice_number = serializers.CharField(
        source='invoice.invoice_number', read_only=True, default=None,
    )
    # T-RECVIS: الطلبية كانت تنتهي عند «محوّلة إلى فاتورة» فتصير طريقاً مسدوداً —
    # ورحلة البضاعة تكمل على الفاتورة (طلبيةٌ واحدة ← فاتورةٌ واحدة ← إرساليات
    # متعددة). فتحمل الطلبية الآن تقدّم استلام فاتورتها، من **نفس** دالّة
    # `purchase_invoice_receipt_summary` التي تغذّي الفاتورة وتقرير البواقي.
    invoice_receipt_status_display = serializers.SerializerMethodField()
    invoice_receipt_progress = serializers.SerializerMethodField()

    def get_invoice_receipt_status_display(self, obj):
        return obj.invoice.get_receipt_status_display() if obj.invoice_id else None

    def get_invoice_receipt_progress(self, obj):
        if not obj.invoice_id:
            return None
        from logistics.services import purchase_invoice_receipt_summary

        s = purchase_invoice_receipt_summary(obj.invoice)
        if not s['lines_total']:
            return None
        return {
            'ordered': str(s['ordered']),
            'received': str(s['received']),
            'remaining': str(s['remaining']),
            'lines_total': s['lines_total'],
            'lines_remaining': s['lines_remaining'],
        }

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'order_number', 'supplier', 'supplier_name',
            'quotation', 'quotation_number', 'invoice', 'invoice_number',
            'invoice_receipt_status_display', 'invoice_receipt_progress',
            'order_date', 'expected_delivery_date', 'status', 'status_display',
            'currency', 'currency_code', 'exchange_rate', 'subtotal',
            'discount_amount', 'tax_rate', 'tax_amount', 'grand_total',
            'shipping_cost', 'is_shipping_included', 'shipping_method',
            'payment_method', 'delivery_days', 'notes', 'cancel_reason',
            'lines', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'invoice', 'subtotal', 'tax_amount', 'grand_total',
            'cancel_reason', 'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'order_number': {'required': False, 'allow_blank': True},
        }

    def validate(self, attrs):
        tenant = get_tenant(self.context.get('request'))
        if tenant is None:
            raise serializers.ValidationError({'tenant': 'لا يوجد شركة محددة لهذا الطلب.'})

        instance = self.instance
        if instance and instance.status != PurchaseOrder.STATUS_DRAFT:
            raise serializers.ValidationError('لا يمكن تعديل طلبية ليست مسودة.')

        supplier = attrs.get('supplier', getattr(instance, 'supplier', None))
        if supplier and supplier.tenant_id != tenant.pk:
            raise serializers.ValidationError({'supplier': 'المورد لا يتبع الشركة الحالية.'})
        if supplier and supplier.partner_type != 'Supplier':
            raise serializers.ValidationError({'supplier': 'الشريك المحدد ليس مورداً.'})

        quotation = attrs.get('quotation', getattr(instance, 'quotation', None))
        if quotation:
            if quotation.tenant_id != tenant.pk or quotation.scope != SupplierQuotation.SCOPE_LOCAL:
                raise serializers.ValidationError({
                    'quotation': 'عرض السعر لا يتبع مشتريات الشركة المحلية.',
                })
            if supplier and quotation.supplier_id != supplier.pk:
                raise serializers.ValidationError({
                    'quotation': 'مورد الطلبية لا يطابق مورد عرض السعر.',
                })

        order_date = attrs.get('order_date', getattr(instance, 'order_date', None))
        expected = attrs.get(
            'expected_delivery_date',
            getattr(instance, 'expected_delivery_date', None),
        )
        if order_date and expected and expected < order_date:
            raise serializers.ValidationError({
                'expected_delivery_date': 'تاريخ التسليم يجب ألا يسبق تاريخ الطلبية.',
            })

        lines = attrs.get('lines')
        if instance is None and not lines:
            raise serializers.ValidationError({'lines': 'يجب إضافة منتج واحد على الأقل.'})
        if lines is not None:
            seen_seq = set()
            for index, line in enumerate(lines, start=1):
                product = line['product']
                if product.tenant_id != tenant.pk:
                    raise serializers.ValidationError({
                        'lines': f'المنتج في السطر {index} لا يتبع الشركة الحالية.',
                    })
                seq = line.get('seq', index)
                if seq in seen_seq:
                    raise serializers.ValidationError({
                        'lines': f'رقم ترتيب السطر {seq} مكرر.',
                    })
                seen_seq.add(seq)

        discount = Decimal(str(attrs.get(
            'discount_amount', getattr(instance, 'discount_amount', 0),
        ) or 0))
        shipping = Decimal(str(attrs.get(
            'shipping_cost', getattr(instance, 'shipping_cost', 0),
        ) or 0))
        if discount < 0:
            raise serializers.ValidationError({'discount_amount': 'الخصم لا يمكن أن يكون سالباً.'})
        if shipping < 0:
            raise serializers.ValidationError({'shipping_cost': 'تكلفة الشحن لا يمكن أن تكون سالبة.'})
        return attrs

    @staticmethod
    def _line_values(order, line, index):
        product = line['product']
        quantity = Decimal(str(line['quantity']))
        unit_price = Decimal(str(line['unit_price']))
        return {
            **line,
            'tenant': order.tenant,
            'order': order,
            'seq': line.get('seq') or index,
            'name_snapshot': line.get('name_snapshot')
            or getattr(product, 'name_ar', '')
            or getattr(product, 'name_en', ''),
            'line_total': (quantity * unit_price).quantize(Decimal('0.01')),
        }

    @staticmethod
    def _recalculate(order):
        subtotal = sum(
            (line.line_total for line in order.lines.all()),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        discount = Decimal(str(order.discount_amount or 0))
        if discount > subtotal:
            raise serializers.ValidationError({
                'discount_amount': 'الخصم لا يمكن أن يتجاوز مجموع البنود.',
            })
        taxable = subtotal - discount
        tax_amount = (
            taxable * Decimal(str(order.tax_rate or 0)) / Decimal('100')
        ).quantize(Decimal('0.01'))
        shipping = (
            Decimal('0')
            if order.is_shipping_included
            else Decimal(str(order.shipping_cost or 0))
        )
        order.subtotal = subtotal
        order.tax_amount = tax_amount
        order.grand_total = (taxable + tax_amount + shipping).quantize(Decimal('0.01'))
        order.save(update_fields=['subtotal', 'tax_amount', 'grand_total', 'updated_at'])

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines')
        order = PurchaseOrder.objects.create(**validated_data)
        PurchaseOrderLine.objects.bulk_create([
            PurchaseOrderLine(**self._line_values(order, line, index))
            for index, line in enumerate(lines, start=1)
        ])
        self._recalculate(order)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        instance = super().update(instance, validated_data)
        if lines is not None:
            instance.lines.all().delete()
            PurchaseOrderLine.objects.bulk_create([
                PurchaseOrderLine(**self._line_values(instance, line, index))
                for index, line in enumerate(lines, start=1)
            ])
        self._recalculate(instance)
        return instance
