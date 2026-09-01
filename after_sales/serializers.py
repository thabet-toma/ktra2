"""سيريالايزرات ما بعد البيع — التحقق هنا هو مصدر أخطاء 400 التي يقرأها المستخدم."""
from datetime import date

from rest_framework import serializers

from .models import (
    ServiceOrder,
    ServiceOrderEvent,
    ServiceOrderPart,
    WarrantyCard,
    add_months,
)


class WarrantyCardSerializer(serializers.ModelSerializer):
    # النهاية تُشتقّ من البداية والمدة حين تُترك فارغة — إلزامها في الحقل يمنع
    # التحقق من الوصول إلى الاشتقاق أصلاً.
    end_date = serializers.DateField(required=False)
    status = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    supplier_warranty_active = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    partner_name = serializers.SerializerMethodField()
    supplier_name = serializers.SerializerMethodField()
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    sales_invoice = serializers.SerializerMethodField()
    sales_invoice_number = serializers.SerializerMethodField()

    class Meta:
        model = WarrantyCard
        fields = [
            "id", "product", "product_name", "device_name", "serial",
            "product_serial", "sales_invoice_line", "sales_invoice",
            "sales_invoice_number", "partner", "partner_name", "customer_name",
            "customer_phone", "start_date", "duration_months", "end_date",
            "source", "source_label", "supplier", "supplier_name",
            "supplier_warranty_end_date", "supplier_warranty_active", "notes",
            "status", "days_remaining", "created_at", "updated_at",
        ]
        # المصدر والشركة والنسب من الخادم — بطاقة يدوية لا تدّعي أنها من ترحيل.
        read_only_fields = [
            "source", "product_serial", "sales_invoice_line",
            "created_at", "updated_at",
        ]

    def get_status(self, obj):
        return obj.status_on()

    def get_days_remaining(self, obj):
        return obj.days_remaining()

    def get_supplier_warranty_active(self, obj):
        return obj.supplier_active_on()

    def get_product_name(self, obj):
        if not obj.product_id:
            return obj.device_name
        from inventory.services import product_display_name
        return product_display_name(obj.product)

    def get_partner_name(self, obj):
        return obj.partner.name if obj.partner_id else obj.customer_name

    def get_supplier_name(self, obj):
        return obj.supplier.name if obj.supplier_id else ""

    def _invoice(self, obj):
        line = obj.sales_invoice_line if obj.sales_invoice_line_id else None
        return line.invoice if (line and line.invoice_id) else None

    def get_sales_invoice(self, obj):
        invoice = self._invoice(obj)
        return invoice.pk if invoice else None

    def get_sales_invoice_number(self, obj):
        invoice = self._invoice(obj)
        return invoice.invoice_number if invoice else None

    # ── التحقق ────────────────────────────────────────────────────────────
    def validate(self, attrs):
        instance = self.instance
        serial = attrs.get("serial", getattr(instance, "serial", "") or "")
        device = attrs.get("device_name", getattr(instance, "device_name", "") or "")
        product = attrs.get("product", getattr(instance, "product", None))
        if not (serial.strip() or device.strip() or product):
            raise serializers.ValidationError(
                {"serial": "حدّد الرقم التسلسلي أو اسم الجهاز أو المنتج — البطاقة بلا هوية لا تُفحص."}
            )

        start = attrs.get("start_date", getattr(instance, "start_date", None))
        if start is None:
            raise serializers.ValidationError({"start_date": "تاريخ بدء الكفالة مطلوب."})

        months = attrs.get("duration_months", getattr(instance, "duration_months", 0) or 0)
        end = attrs.get("end_date", None)
        if end is None:
            end = getattr(instance, "end_date", None) if instance else None
            # بطاقة جديدة بمدّة ولا نهاية: النهاية تُشتقّ مرة واحدة عند الإنشاء
            # ثم تصير واقعة مخزَّنة قابلة للتمديد.
            if end is None:
                if not months:
                    raise serializers.ValidationError(
                        {"duration_months": "حدّد مدة الكفالة بالأشهر أو تاريخ انتهائها."}
                    )
                end = add_months(start, months)
        if end < start:
            raise serializers.ValidationError(
                {"end_date": "تاريخ انتهاء الكفالة قبل تاريخ بدئها."}
            )
        attrs["end_date"] = end
        attrs["duration_months"] = months

        supplier_end = attrs.get(
            "supplier_warranty_end_date",
            getattr(instance, "supplier_warranty_end_date", None),
        )
        if supplier_end is not None and supplier_end < start:
            raise serializers.ValidationError(
                {"supplier_warranty_end_date": "نهاية كفالة المورد قبل بدء الكفالة."}
            )
        return attrs


class WarrantyExtendSerializer(serializers.Serializer):
    """تمديد المجاملة: تاريخ صريح أو عدد أشهر يُضاف إلى النهاية الحالية."""

    end_date = serializers.DateField(required=False)
    months = serializers.IntegerField(required=False, min_value=1, max_value=600)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def validate(self, attrs):
        if not attrs.get("end_date") and not attrs.get("months"):
            raise serializers.ValidationError(
                {"months": "حدّد تاريخ النهاية الجديد أو عدد الأشهر المضافة."}
            )
        return attrs

    def resolved_end_date(self, card) -> date:
        if self.validated_data.get("end_date"):
            return self.validated_data["end_date"]
        return add_months(card.end_date, self.validated_data["months"])


# ══════════════════════════════════════════════════════════════════════════
# أمر الصيانة
# ══════════════════════════════════════════════════════════════════════════

class ServiceOrderPartSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    billing_label = serializers.CharField(source="get_billing_display", read_only=True)
    is_materialized = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrderPart
        fields = [
            "id", "product", "product_name", "quantity", "billing", "billing_label",
            "unit_price", "notes", "sales_invoice_line", "materialized_at",
            "is_materialized", "created_at",
        ]
        # القفل من الخادم وحده: البند المُجسَّد واقعةٌ في الدفاتر لا حقلٌ يُرسَل.
        read_only_fields = [
            "sales_invoice_line", "materialized_at", "created_at",
        ]

    def get_product_name(self, obj):
        if not obj.product_id:
            return ""
        from inventory.services import product_display_name
        return product_display_name(obj.product)

    def get_is_materialized(self, obj):
        return obj.materialized_at is not None

    def validate_quantity(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("كمية القطعة يجب أن تكون أكبر من صفر.")
        return value

    def validate_unit_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("سعر القطعة لا يكون سالباً.")
        return value


class ServiceOrderEventSerializer(serializers.ModelSerializer):
    event_type_label = serializers.CharField(
        source="get_event_type_display", read_only=True,
    )
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrderEvent
        fields = [
            "id", "event_type", "event_type_label", "from_status", "to_status",
            "text", "actor", "actor_name", "created_at",
        ]

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.username if obj.actor_id else ""


class ServiceOrderSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    partner_name = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    technician_name = serializers.SerializerMethodField()
    parts = ServiceOrderPartSerializer(many=True, read_only=True)
    events = serializers.SerializerMethodField()
    warranty_status = serializers.SerializerMethodField()
    sales_invoice_number = serializers.SerializerMethodField()
    delivery_blockers = serializers.SerializerMethodField()
    cancellation_blockers = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrder
        fields = [
            "id", "order_number", "order_date",
            "partner", "partner_name", "customer_name", "customer_phone",
            "product", "product_name", "serial", "device_description",
            "received_condition", "accessories",
            "complaint", "diagnosis", "resolution",
            "technician", "technician_name",
            "warranty_card", "warranty_covered", "warranty_status",
            "supplier_claim", "supplier_claim_note",
            "estimated_amount", "approved_at", "approved_by",
            "status", "status_label", "outcome", "outcome_label",
            "covered_posted_at", "delivered_at",
            "sales_invoice", "sales_invoice_number", "billing_waived_reason",
            "photos", "notes", "parts", "events",
            "delivery_blockers", "cancellation_blockers",
            "created_at", "updated_at",
        ]
        # الرقم والحالة والنتيجة ومراسي الترحيل كلها من الخادم: الحالة تنتقل
        # بنقطة `transition` المحروسة لا بـPATCH يتخطّى بواباتها.
        read_only_fields = [
            "order_number", "status", "outcome", "covered_posted_at",
            "delivered_at", "sales_invoice", "approved_at", "approved_by",
            "created_at", "updated_at",
        ]

    def get_partner_name(self, obj):
        return obj.partner.name if obj.partner_id else obj.customer_name

    def get_product_name(self, obj):
        if not obj.product_id:
            return obj.device_description
        from inventory.services import product_display_name
        return product_display_name(obj.product)

    def get_technician_name(self, obj):
        if not obj.technician_id:
            return ""
        return obj.technician.get_full_name() or obj.technician.username

    def get_events(self, obj):
        # التسلسل الزمني جزء من المستند نفسه («من الشكوى حتى الحل») لا نقطة ثانية.
        return ServiceOrderEventSerializer(obj.events.all(), many=True).data

    def get_warranty_status(self, obj):
        card = obj.warranty_card if obj.warranty_card_id else None
        if card is None:
            return None
        return {
            "id": card.pk,
            "end_date": card.end_date,
            "status": card.status_on(),
            "days_remaining": card.days_remaining(),
            "supplier_warranty_end_date": card.supplier_warranty_end_date,
            "supplier_warranty_active": card.supplier_active_on(),
        }

    def get_sales_invoice_number(self, obj):
        return obj.sales_invoice.invoice_number if obj.sales_invoice_id else None

    def get_delivery_blockers(self, obj):
        from .service_orders import delivery_blockers

        return delivery_blockers(obj)

    def get_cancellation_blockers(self, obj):
        from .service_orders import cancellation_blockers

        return cancellation_blockers(obj)

    def validate(self, attrs):
        instance = self.instance
        partner = attrs.get("partner", getattr(instance, "partner", None))
        name = attrs.get("customer_name", getattr(instance, "customer_name", "") or "")
        if not partner and not name.strip():
            raise serializers.ValidationError(
                {"customer_name": "حدّد الزبون من القائمة أو اكتب اسمه — الأمر بلا صاحب لا يُسلَّم."}
            )

        serial = attrs.get("serial", getattr(instance, "serial", "") or "")
        product = attrs.get("product", getattr(instance, "product", None))
        description = attrs.get(
            "device_description", getattr(instance, "device_description", "") or "",
        )
        if not (serial.strip() or product or description.strip()):
            raise serializers.ValidationError(
                {"serial": "حدّد الجهاز برقمه التسلسلي أو منتجه أو وصفه."}
            )

        estimated = attrs.get(
            "estimated_amount", getattr(instance, "estimated_amount", None),
        )
        if estimated is not None and estimated < 0:
            raise serializers.ValidationError(
                {"estimated_amount": "التقدير لا يكون سالباً."}
            )
        return attrs


class ServiceOrderListSerializer(serializers.ModelSerializer):
    """صفٌّ خفيف للقائمة — بلا بنود ولا أحداث ولا حسابات حرّاس لكل صف."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    outcome_label = serializers.CharField(source="get_outcome_display", read_only=True)
    partner_name = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrder
        fields = [
            "id", "order_number", "order_date", "partner", "partner_name",
            "customer_name", "customer_phone", "product", "product_name", "serial",
            "device_description", "complaint", "status", "status_label",
            "outcome", "outcome_label", "warranty_covered", "estimated_amount",
            "covered_posted_at", "sales_invoice", "delivered_at", "created_at",
        ]

    def get_partner_name(self, obj):
        return obj.partner.name if obj.partner_id else obj.customer_name

    def get_product_name(self, obj):
        if not obj.product_id:
            return obj.device_description
        from inventory.services import product_display_name
        return product_display_name(obj.product)


class ServiceOrderTransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(
        choices=[choice for choice, _ in ServiceOrder.STATUS_CHOICES],
    )
    outcome = serializers.ChoiceField(
        choices=[choice for choice, _ in ServiceOrder.OUTCOME_CHOICES],
        required=False, allow_blank=True,
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ServiceOrderNoteSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class GenerateServiceInvoiceSerializer(serializers.Serializer):
    labour_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, min_value=0,
    )
