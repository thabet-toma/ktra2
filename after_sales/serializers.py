"""سيريالايزرات بطاقة الكفالة — التحقق هنا هو مصدر أخطاء 400 التي يقرأها المستخدم."""
from datetime import date

from rest_framework import serializers

from .models import WarrantyCard, add_months


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
        return str(obj.product) if obj.product_id else obj.device_name

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
                {"serial": "حدّد الرقم التسلسلي أو اسم الجهاز أو الصنف — البطاقة بلا هوية لا تُفحص."}
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
