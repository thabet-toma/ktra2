import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework import serializers

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
    if d and not _english_payment_boilerplate(d):
        return d[:72]
    ref = (getattr(deal, "ref_number", None) or "").strip()
    offer = (getattr(deal, "original_offer_number", None) or "").strip()
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
    """
    يطابق frontend DealForm.recalculateTotals: مجمّع البنود → خصم → شحن (إن لم يُضمّن) → ضريبة → total_amount.
    بدون هذا، كان total_amount يُستبدل بمجموع البنود فقط فيُرفض الحفظ إن وُجدت دفعات مبنية على الإجمالي الكامل.
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
    taxable_base = after_discount + shipping
    tax_type = str(getattr(instance, "tax_type", None) or "percentage").lower()
    if tax_type == "amount":
        tax_amt = _to_decimal(getattr(instance, "tax_amount", None))
    else:
        rate = _to_decimal(getattr(instance, "tax_rate", None))
        tax_amt = (taxable_base * rate / Decimal("100")).quantize(Decimal("0.01"))
        instance.tax_amount = tax_amt
    instance.total_amount = (taxable_base + tax_amt).quantize(Decimal("0.01"))


def _payments_total_exceeds_deal(payments_data, deal_total) -> bool:
    if not payments_data:
        return False
    try:
        total = _to_decimal(deal_total)
        s = sum((_to_decimal(p.get("amount") or 0) for p in payments_data), Decimal("0"))
    except (TypeError, ValueError):
        return True
    eps = Decimal("0.01")
    return s > total + eps


def _coerce_logistics_payment_pk(pay_id_raw):
    """يقبل معرف SQL فقط؛ يتجاهل tmp- و p-0 وغيرها."""
    if pay_id_raw is None or pay_id_raw == "":
        return None
    try:
        return int(pay_id_raw)
    except (TypeError, ValueError):
        return None


def _payment_amounts_unchanged_for_deal(deal_instance, payments_data) -> bool:
    """
    نفس الدفعات (لم يُعدّل المستخدم المبالغ) — يُسمح بالحفظ رغم أن إجمالي الصفقة أصبح أقل من مجموع الدفعات
    (تعديل لوجستي فقط، أو بيانات قديمة). يدعم: معرّفات SQL، أو طلب بلا id رقمي (واجهة مؤقتة) عبر مقارنة مجموعة المبالغ.
    """
    if not payments_data:
        try:
            return not deal_instance.payments.exists()
        except Exception:
            return False
    try:
        existing_list = list(deal_instance.payments.all())
    except Exception:
        return False
    if len(existing_list) != len(payments_data):
        return False

    def amount_key(x):
        try:
            return round(float(x or 0) * 100)
        except (TypeError, ValueError):
            return 0

    existing_by_id = {p.id: float(p.amount or 0) for p in existing_list}
    all_ids_valid = True
    for row in payments_data:
        pid = _coerce_logistics_payment_pk(row.get("id"))
        if pid is None:
            all_ids_valid = False
            break
        if pid not in existing_by_id:
            all_ids_valid = False
            break
        try:
            new_amt = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            return False
        if abs(existing_by_id[pid] - new_amt) > 0.05:
            return False
    if all_ids_valid:
        return True

    from collections import Counter

    c_exist = Counter(amount_key(p.amount) for p in existing_list)
    c_pay = Counter(amount_key(row.get("amount")) for row in payments_data)
    return c_exist == c_pay


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


def _payment_amounts_unchanged_for_shipment(shipment_instance, payments_data) -> bool:
    if not payments_data:
        try:
            return not shipment_instance.agent_payments.exists()
        except Exception:
            return False
    try:
        existing_list = list(shipment_instance.agent_payments.all())
    except Exception:
        return False
    if len(existing_list) != len(payments_data):
        return False

    def amount_key(x):
        try:
            return round(float(x or 0) * 100)
        except (TypeError, ValueError):
            return 0

    existing_by_id = {p.id: float(p.amount or 0) for p in existing_list}
    all_ids_valid = True
    for row in payments_data:
        pid = _coerce_logistics_payment_pk(row.get("id"))
        if pid is None:
            all_ids_valid = False
            break
        if pid not in existing_by_id:
            all_ids_valid = False
            break
        try:
            new_amt = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            return False
        if abs(existing_by_id[pid] - new_amt) > 0.05:
            return False
    if all_ids_valid:
        return True

    from collections import Counter

    c_exist = Counter(amount_key(p.amount) for p in existing_list)
    c_pay = Counter(amount_key(row.get("amount")) for row in payments_data)
    return c_exist == c_pay


def _sync_shipment_agent_payments(shipment, payments_data):
    """مزامنة دفعات وكيل الشحن (بدون صفقة شراء) مع حد إجمالي total_shipping_cost_usd."""
    cap = float(shipment.total_shipping_cost_usd or 0)
    if _payments_total_exceeds_shipment(payments_data, cap):
        if not _payment_amounts_unchanged_for_shipment(shipment, payments_data):
            raise serializers.ValidationError(
                {
                    "payments": "مجموع دفعات الشحن يتجاوز تكلفة الشحن الأساسية. خفّض المبلغ أو راجع الإجمالي."
                }
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
    LogisticsExpense,
    LogisticsShipmentDeal,
    LogisticsPayment,
    LogisticsClearancePayment,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseInvoiceFee,
    LocalShipment
)
from partners.serializers import PartnerSerializer
from inventory.models import Product

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
    payments = LogisticsPaymentSerializer(many=True, required=False)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    partner_legal_name = serializers.CharField(
        source='partner.legal_name', read_only=True, allow_null=True, default=None
    )
    quote_images = serializers.SerializerMethodField()
    quote_pdfs = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsDeal
        fields = '__all__'
        read_only_fields = ['id', 'tenant', 'created_by', 'is_posted', 'journal', 'total_amount']

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
        payments_data = validated_data.pop('payments', [])
        deal = LogisticsDeal.objects.create(**validated_data)

        lines_subtotal = Decimal("0")
        for item_data in items_data:
            LogisticsDealItem.objects.create(deal=deal, **item_data)
            lines_subtotal += _to_decimal(item_data.get("quantity")) * _to_decimal(
                item_data.get("unit_price")
            )

        _apply_lines_subtotal_and_grand_total(deal, lines_subtotal)
        deal.save()

        if _payments_total_exceeds_deal(payments_data, float(deal.total_amount or 0)):
            raise serializers.ValidationError(
                {
                    "payments": "مجموع الدفعات يتجاوز قيمة الصفقة (مجموع البنود). احذف دفعة زائدة أو خفّض المبالغ."
                }
            )

        for payment_data in payments_data:
            LogisticsPayment.objects.create(
                deal=deal, shipment=None, **payment_data
            )

        return deal

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        payments_data = validated_data.pop('payments', None)
        
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
            
        if payments_data is not None:
            deal_total = float(instance.total_amount or 0)
            if _payments_total_exceeds_deal(payments_data, deal_total):
                if not _payment_amounts_unchanged_for_deal(instance, payments_data):
                    raise serializers.ValidationError(
                        {
                            "payments": "مجموع الدفعات يتجاوز قيمة الصفقة. احذف دفعة زائدة أو خفّض المبالغ."
                        }
                    )

            keep_payments = []
            matched_pks = set()

            for payment_data in payments_data:
                pay_pk = _coerce_logistics_payment_pk(payment_data.get("id"))
                pay_instance = None

                # 1) مطابقة بمعرّف SQL صريح
                if pay_pk is not None:
                    pay_instance = LogisticsPayment.objects.filter(
                        id=pay_pk, deal=instance
                    ).first()

                # 2) مطابقة بـ payment_number فقط (بغض النظر عن is_posted أو amount)
                if pay_instance is None:
                    pn = payment_data.get("payment_number")
                    try:
                        pn_int = int(pn) if pn is not None else None
                    except (TypeError, ValueError):
                        pn_int = None
                    if pn_int is not None:
                        candidates = (
                            LogisticsPayment.objects.filter(
                                deal=instance, payment_number=pn_int
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
                    pay_instance.deal = instance
                    pay_instance.shipment = None
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
                            deal=instance, payment_number=pn_c
                        ).exists():
                            raise serializers.ValidationError(
                                {
                                    "payments": (
                                        f"يوجد بالفعل دفعة بنفس رقم القسط ({pn_c}). "
                                        "حدّث الصفحة (F5) وتجنّب حفظاً مكرراً."
                                    )
                                }
                            )
                    new_pay = LogisticsPayment.objects.create(
                        deal=instance, shipment=None, **create_data
                    )
                    keep_payments.append(new_pay.id)

            instance.payments.filter(is_posted=False).exclude(
                id__in=keep_payments
            ).delete()

        return instance

class LogisticsShipmentDealAllocationSerializer(serializers.ModelSerializer):
    """أوزان تكلفة الشحن الدولي المحفوظة لكل صفقة على الشحنة."""

    class Meta:
        model = LogisticsShipmentDeal
        fields = ["id", "deal", "allocated_shipping_cost", "extra_costs"]
        read_only_fields = ["id", "deal"]


class LogisticsShipmentSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source='shipping_agent.name', read_only=True)
    deals = LogisticsDealSerializer(many=True, read_only=True)
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
        read_only_fields = ["id", "tenant"]

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
    # cost_lines: legacy JSON-shape kept for backwards-compat (write+read).
    # On read it pulls from the @property on the model (which derives from
    # `lines` rows). On write it triggers `_sync_lines_from_cost_lines`.
    cost_lines = serializers.JSONField(required=False)

    class Meta:
        model = LogisticsClearance
        fields = "__all__"
        read_only_fields = ["id", "tenant"]

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

class LogisticsExpenseSerializer(serializers.ModelSerializer):
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)
    payable_account_name = serializers.CharField(source='payable_account.name', read_only=True)

    class Meta:
        model = LogisticsExpense
        fields = '__all__'
        read_only_fields = ['id', 'tenant', 'is_posted', 'journal']


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

    class Meta:
        model = PurchaseInvoiceItem
        fields = [
            'id', 'product', 'product_name', 'name',
            'quantity', 'unit_price', 'total_price',
            'notes', 'hs_code',
            'landed_unit_price_ils', 'landed_line_total_ils',
            'seq', 'catalog_number', 'name_snapshot', 'description_line', 'unit', 'warehouse',
            'extra_qty', 'batch_number', 'serial_number', 'manufacture_number', 'expiry_date',
            'line_currency', 'line_exchange_rate', 'second_date', 'is_taxable', 'vat_percent',
            'discount_percent', 'discount_amount',
        ]
        read_only_fields = ['id']

    def get_product_name(self, obj):
        if obj.product:
            return obj.product.name_ar or obj.product.name_en or obj.product.sku
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
            'expense_account', 'expense_account_code', 'expense_account_name', 'expense_account_type',
            'capitalize_to_inventory', 'is_taxable',
        ]
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('مبلغ الرسم يجب أن يكون ≥ 0.')
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
    items_count = serializers.SerializerMethodField()
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'invoice_name', 'invoice_date',
            'partner', 'partner_name',
            'deal', 'deal_ref',
            'shipment', 'clearance',
            'currency', 'currency_code', 'exchange_rate',
            'subtotal', 'discount_amount', 'tax_rate', 'tax_amount',
            'grand_total', 'status', 'status_display',
            'is_posted', 'journal_id_display',
            'items_count',
            'created_at', 'updated_at',
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    items = PurchaseInvoiceItemSerializer(many=True, required=False)
    fees = PurchaseInvoiceFeeSerializer(many=True, required=False)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    deal_ref = serializers.CharField(source='deal.ref_number', read_only=True, default=None)
    currency_code = serializers.CharField(source='currency.Code', read_only=True, default=None)
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    cash_or_bank_account_name = serializers.CharField(
        source='cash_or_bank_account.name', read_only=True, default=None,
    )
    cash_or_bank_account_code = serializers.CharField(
        source='cash_or_bank_account.code', read_only=True, default=None,
    )

    class Meta:
        model = PurchaseInvoice
        fields = [
            'id', 'invoice_number', 'invoice_name', 'invoice_date',
            'partner', 'partner_name',
            'deal', 'deal_ref',
            'shipment',
            'clearance',
            'currency', 'currency_code', 'exchange_rate',
            'subtotal', 'discount_amount',
            'tax_rate', 'tax_amount', 'tax_type',
            'shipping_cost', 'shipping_included',
            'grand_total',
            'payment_type',
            'cash_or_bank_account', 'cash_or_bank_account_name', 'cash_or_bank_account_code',
            'local_payments_json', 'conversion_metadata_json',
            'status', 'status_display', 'notes',
            'supplier_invoice_number', 'factory_name',
            'is_posted', 'journal', 'journal_id_display',
            'firestore_id',
            'items', 'fees',
            'created_at', 'updated_at', 'created_by',
        ]
        read_only_fields = ['id', 'is_posted', 'journal', 'created_at', 'updated_at']

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
        # لا نستبدل خصم/ضريبة/إجمالي الفاتورة من «live» — live يبنيها من صفقة الشحن (deal.tax_*)
        # وقد تختلف عن ض.ق.م الفاتورة المحفوظة؛ الاستبدال كان يصفّر الضريبة بعد التحديث رغم بقاء tax_rate.
        for k in ('subtotal', 'shipping_cost'):
            if k in live and live[k] is not None:
                data[k] = _json_friendly_value(live[k])
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

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        fees_data = validated_data.pop('fees', [])
        invoice = PurchaseInvoice.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseInvoiceItem.objects.create(invoice=invoice, **item_data)
        for fee_data in fees_data:
            PurchaseInvoiceFee.objects.create(
                invoice=invoice, tenant=invoice.tenant, **fee_data,
            )
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
                PurchaseInvoiceFee.objects.create(
                    invoice=instance, tenant=instance.tenant, **fee_data,
                )

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
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'shipment_number', 'is_posted', 'journal',
            'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        payment_type = attrs.get(
            'payment_type', getattr(instance, 'payment_type', 'credit'),
        )
        cash_acc = attrs.get(
            'cash_or_bank_account', getattr(instance, 'cash_or_bank_account', None),
        )
        if payment_type == 'cash' and not cash_acc:
            raise serializers.ValidationError({
                'cash_or_bank_account': 'الصندوق/البنك مطلوب في الدفع النقدي.',
            })
        amount = attrs.get('amount', getattr(instance, 'amount', 0))
        try:
            if Decimal(str(amount or 0)) <= 0:
                raise serializers.ValidationError({
                    'amount': 'المبلغ يجب أن يكون أكبر من صفر.',
                })
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError({'amount': 'قيمة غير صالحة.'})
        return attrs
