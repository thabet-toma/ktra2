import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import Sum
from rest_framework import serializers

from sales.models import SupplierPayment

from .text_utils import has_arabic as _has_arabic
from .text_utils import (
    is_english_payment_or_legal_boilerplate as _english_payment_boilerplate,
)


def _deal_title_for_list_preview(deal):
    """اسم الصفقة المختصر إن وُجد (T4-03)، وإلا وصف قصير/أول سطر عربي/رقم العرض/رقم الصفقة."""
    # T4-03: explicit short_name is authoritative — it exists precisely so
    # the user can override the description heuristic with a clean name.
    short = (getattr(deal, "short_name", None) or "").strip()
    if short:
        return short[:72]
    d = (getattr(deal, "description", None) or "").strip()
    notes = (getattr(deal, "notes", None) or "").strip()
    if d and _has_arabic(d):
        return d[:72]
    if notes:
        for line in notes.splitlines():
            line = line.strip()
            if line and _has_arabic(line):
                return line[:72]
    ref = (getattr(deal, "ref_number", None) or "").strip()
    offer = (getattr(deal, "original_offer_number", None) or "").strip()
    # بيانات قديمة خزّنت الاسم العربي في «رقم العرض» — يتقدم على الوصف الإنجليزي
    if offer and _has_arabic(offer) and not re.match(r"^d-\d+$", offer, re.I):
        return offer[:72]
    if d and not _english_payment_boilerplate(d):
        return d[:72]
    if offer and offer.lower() != ref.lower():
        if not re.match(r"^d-\d+$", offer, re.I):
            return offer[:72]
    return ref[:72] if ref else ""


def _to_decimal(x, default="0"):
    if x is None:
        return Decimal(default)
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _quantize_decimal_10_3(value) -> Decimal:
    """
    يطابق LogisticsShipment.total_volume / total_weight_kg (max_digits=10, decimal_places=3).
    يمنع رفض الطلب أو خطأ MySQL عند أرقام عشرية طويلة من الجمع أو JSON.
    """
    d = _to_decimal(value)
    d = d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    vmax = Decimal("9999999.999")
    if d > vmax:
        d = vmax
    if d < 0:
        d = Decimal("0")
    return d


def _apply_lines_subtotal_and_grand_total(instance, lines_subtotal):
    """يطابق DealForm.recalculateTotals (ج8): إجمالي الصفقة الدولية =
    بضاعة − خصم + شحن داخل الصين. **بلا ضريبة** — الضريبة تُدفع بالتخليص ولا
    تدخل إجمالي الصفقة ولا سقف دفعات المورد (قرار المالك Q2).
    """
    instance.subtotal = _to_decimal(lines_subtotal)
    discount = _to_decimal(getattr(instance, "discount_amount", None))
    shipping = (
        Decimal("0")
        if getattr(instance, "is_shipping_included", False)
        else _to_decimal(getattr(instance, "shipping_cost_estimate", None))
    )
    after_discount = instance.subtotal - discount
    if after_discount < 0:
        after_discount = Decimal("0")
    instance.tax_amount = Decimal("0")
    instance.total_amount = (after_discount + shipping).quantize(Decimal("0.01"))


def _coerce_logistics_payment_pk(pay_id_raw):
    """يقبل معرف SQL فقط؛ يتجاهل tmp- و p-0 وغيرها."""
    if pay_id_raw is None or pay_id_raw == "":
        return None
    try:
        return int(pay_id_raw)
    except (TypeError, ValueError):
        return None


def _payments_total_exceeds_shipment(payments_data, shipment_cost) -> bool:
    if not payments_data:
        return False
    try:
        total = float(shipment_cost or 0)
        s = sum(float(p.get("amount") or 0) for p in payments_data)
    except (TypeError, ValueError):
        return True
    eps = max(0.01, abs(total) * 1e-9)
    return s > total + eps


def _sync_shipment_agent_payments(shipment, payments_data):
    """مزامنة دفعات وكيل الشحن (بدون صفقة شراء).

    الدفع الزائد عن تكلفة الشحن مسموح: الفائض دفعة مقدمة لدى الوكيل (يصبح مديناً
    لنا وتُسوّى على شحنة لاحقة). كان الحظر يمنع واقعة محاسبية صحيحة.
    """
    cap = float(shipment.total_shipping_cost_usd or 0)
    if cap > 0 and _payments_total_exceeds_shipment(payments_data, cap):
        paid = sum(float(p.get("amount") or 0) for p in payments_data)
        logger.info(
            'shipment %s agent payments exceed freight → advance: paid=%s cap=%s',
            shipment.pk, paid, cap,
        )
    keep_payments = []
    matched_pks = set()

    for payment_data in payments_data:
        pay_pk = _coerce_logistics_payment_pk(payment_data.get("id"))
        pay_instance = None
        if pay_pk is not None:
            pay_instance = LogisticsPayment.objects.filter(
                id=pay_pk, shipment=shipment
            ).first()

        if pay_instance is None:
            pn = payment_data.get("payment_number")
            try:
                pn_int = int(pn) if pn is not None else None
            except (TypeError, ValueError):
                pn_int = None
            if pn_int is not None:
                candidates = (
                    LogisticsPayment.objects.filter(
                        shipment=shipment, payment_number=pn_int
                    )
                    .exclude(pk__in=matched_pks)
                    .order_by("id")
                )
                pay_instance = candidates.first()

        if pay_instance:
            matched_pks.add(pay_instance.pk)
            for attr, value in payment_data.items():
                if attr in ("id", "deal", "shipment"):
                    continue
                if not pay_instance.is_posted or attr == "notes":
                    setattr(pay_instance, attr, value)
            pay_instance.shipment = shipment
            pay_instance.deal = None
            pay_instance.save()
            keep_payments.append(pay_instance.id)
        else:
            create_data = {
                k: v
                for k, v in payment_data.items()
                if k not in ("id", "deal", "shipment")
            }
            pn_c = create_data.get("payment_number")
            if pn_c is not None:
                if LogisticsPayment.objects.filter(
                    shipment=shipment, payment_number=pn_c
                ).exists():
                    raise serializers.ValidationError(
                        {
                            "payments": (
                                f"يوجد بالفعل دفعة شحن بنفس رقم القسط ({pn_c}). "
                                "حدّث الصفحة (F5) وتجنّب حفظاً مكرراً."
                            )
                        }
                    )
            new_pay = LogisticsPayment.objects.create(
                shipment=shipment, deal=None, **create_data
            )
            logger.info(
                'shipment agent payment created shipment=%s payment=%s amount=%s',
                shipment.pk, new_pay.pk, new_pay.amount,
            )
            keep_payments.append(new_pay.id)

    shipment.agent_payments.filter(is_posted=False).exclude(
        id__in=keep_payments
    ).delete()


from .models import (
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
    LocalShipment,
    LocalShipmentPayment,
)

from partners.serializers import PartnerSerializer
from inventory.models import Product

logger = logging.getLogger(__name__)

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
    def _posted_paid_total(obj):
        return (
            obj.payments.filter(is_posted=True).aggregate(total=Sum('amount'))['total']
            or Decimal('0')
        ).quantize(Decimal('0.01'))

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
        out = []
        for row in value:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            if not label:
                continue
            try:
                amt = float(row.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amt = 0.0
            out.append({"label": label[:220], "amount": round(amt, 2)})
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


# ─── Purchase Invoice Serializers ──────────────────────────────────────────────

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
            'line_currency', 'line_exchange_rate', 'second_date', 'is_taxable', 'vat_percent',
            'discount_percent', 'discount_amount',
            'expense_account', 'expense_account_code', 'expense_account_name',
        ]
        read_only_fields = ['id', 'received_quantity']

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

    def get_deal_title(self, obj):
        return _deal_title_for_list_preview(obj.deal) if obj.deal_id else ''

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
            'amount_paid', 'remaining_balance', 'payment_status', 'payment_status_display',
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

    def get_quote_images(self, obj):
        return read_document_images(obj.tenant_id, 'purchase_invoices', obj.id)

    def get_quote_pdfs(self, obj):
        return read_document_pdfs(obj.tenant_id, 'purchase_invoices', obj.id)

    def _computed_amount_paid(self, obj) -> Decimal:
        """المدفوع = نقدي مرفق + دفعات صريحة؛ والفاتورة النقدية المرحَّلة مدفوعة بالكامل."""
        payable = self._payable_total(obj)
        paid = Decimal(str(obj.attached_cash_amount or 0))
        try:
            paid += sum((Decimal(str(p.amount or 0)) for p in obj.payments.all()), Decimal('0'))
        except Exception:
            pass
        if obj.payment_type == 'cash' and obj.is_posted:
            # تسوية الشراء النقدي (Section B) تُفرّغ ذمم المورد بالكامل
            paid = max(paid, payable)
        if payable and paid > payable:
            paid = payable
        return paid.quantize(Decimal('0.01'))

    @staticmethod
    def _fees_total(obj) -> Decimal:
        return sum(
            (Decimal(str(f.amount or 0)) for f in obj.fees.all()),
            Decimal('0'),
        ).quantize(Decimal('0.01'))

    def _payable_total(self, obj) -> Decimal:
        return (Decimal(str(obj.grand_total or 0)) + self._fees_total(obj)).quantize(Decimal('0.01'))

    def get_fees_total(self, obj):
        return str(self._fees_total(obj))

    def get_payable_total(self, obj):
        return str(self._payable_total(obj))

    def get_amount_paid(self, obj):
        return str(self._computed_amount_paid(obj))

    def get_remaining_balance(self, obj):
        return str((self._payable_total(obj) - self._computed_amount_paid(obj)).quantize(Decimal('0.01')))

    def get_payment_status(self, obj):
        grand = self._payable_total(obj)
        paid = self._computed_amount_paid(obj)
        if grand <= 0:
            return 'unpaid'
        if paid >= grand - Decimal('0.01'):
            return 'paid'
        if paid > 0:
            return 'partially_paid'
        return 'unpaid'

    def get_payment_status_display(self, obj):
        return {
            'paid': 'مدفوعة',
            'partially_paid': 'مدفوعة جزئياً',
            'unpaid': 'غير مدفوعة',
        }.get(self.get_payment_status(obj), 'غير مدفوعة')

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

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        fees_data = validated_data.pop('fees', None)
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


# ── P-H-3: SupplierPayment ──────────────────────────────────────────

class PurchaseSettingsSerializer(serializers.ModelSerializer):
    """FEAT-1: إعدادات الشراء (استراتيجية التسعير التلقائي)."""

    class Meta:
        model = PurchaseSettings
        fields = ['id', 'purchase_default_price_strategy', 'default_cash_account', 'updated_at']
        read_only_fields = ['id', 'updated_at']


class SupplierPaymentSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    currency_code = serializers.CharField(source='currency.Code', read_only=True, default=None)
    cash_account_name = serializers.CharField(
        source='cash_or_bank_account.name', read_only=True, default=None,
    )

    class Meta:
        model = SupplierPayment
        fields = [
            'id',
            'partner', 'partner_name',
            'payment_date',
            'amount',
            'currency', 'currency_code', 'exchange_rate',
            'cash_or_bank_account', 'cash_account_name',
            'is_posted', 'journal',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'is_posted', 'journal', 'created_at']

    def validate(self, attrs):
        try:
            if Decimal(str(attrs.get('amount', 0))) <= 0:
                raise serializers.ValidationError({'amount': 'المبلغ يجب أن يكون أكبر من صفر.'})
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError({'amount': 'قيمة غير صالحة.'})
        if not attrs.get('payment_date'):
            raise serializers.ValidationError({'payment_date': 'تاريخ الدفعة مطلوب.'})
        if not attrs.get('cash_or_bank_account'):
            raise serializers.ValidationError({'cash_or_bank_account': 'الصندوق/البنك مطلوب.'})
        return attrs
