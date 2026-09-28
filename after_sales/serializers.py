"""سيريالايزرات ما بعد البيع — التحقق هنا هو مصدر أخطاء 400 التي يقرأها المستخدم."""
from datetime import date

from rest_framework import serializers

from .models import (
    AfterSalesSettings,
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderEvent,
    ServiceOrderPart,
    WarrantyCard,
    WarrantyCardEvent,
    WarrantyPolicy,
    add_months,
)

#: سقف الشروط النصية (شروط الشركة وشروط الإصلاح) — الشهادة المطبوعة تبقى مقروءة (#230).
TERMS_MAX_LENGTH = 2000


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
    sales_invoice_number = serializers.SerializerMethodField()
    # #222: «منتهية بواقعة» حالةٌ أولى الدرجة على الشاشة — بطاقةٌ لجهازٍ أُرجع
    # لا يجوز أن تُعرض «سارية»، والسبب يُسمّى للموظف لا للزبون.
    ended = serializers.SerializerMethodField()
    end_reason_label = serializers.CharField(
        source="get_end_reason_display", read_only=True,
    )
    # #232: طبقة المصنع — `manufacturer_end_date` تُشتقّ دوماً من البداية
    # والمدة في `validate()`؛ ما يرسله العميل فيها يُتجاهَل ولا يُعتمَد.
    manufacturer_warrantor_name = serializers.SerializerMethodField()
    manufacturer_status = serializers.SerializerMethodField()
    manufacturer_days_remaining = serializers.SerializerMethodField()
    # #234: بطاقة «كفالة على الفاتورة» — `quantity`/`returned_quantity` من
    # الخادم وحده (ترحيل البيع والمرجع)، و`covered_quantity` محسوبةٌ لا
    # مخزَّنة أبداً. صفرٌ على بطاقة وحدة مُرقَّمة — لا معنى له هناك.
    covered_quantity = serializers.SerializerMethodField()

    class Meta:
        model = WarrantyCard
        fields = [
            "id", "product", "product_name", "device_name", "serial",
            "product_serial", "sales_invoice_line", "sales_invoice",
            "sales_invoice_number", "partner", "partner_name", "customer_name",
            "customer_phone", "start_date", "duration_months", "end_date",
            "source", "source_label", "supplier", "supplier_name",
            "supplier_warranty_end_date", "supplier_warranty_active", "notes",
            "manufacturer_warrantor", "manufacturer_warrantor_name",
            "manufacturer_start_date", "manufacturer_duration_months",
            "manufacturer_end_date", "manufacturer_status", "manufacturer_days_remaining",
            "quantity", "returned_quantity", "covered_quantity",
            "status", "days_remaining", "ended", "ended_on", "end_reason",
            "end_reason_label", "created_at", "updated_at",
        ]
        # المصدر والشركة والنسب من الخادم — بطاقة يدوية لا تدّعي أنها من ترحيل.
        # وواقعةُ الانتهاء من مسارها (ترحيل/مرجع/حذف) لا من PATCH. والكمية
        # (#234) من محرّك الكفالة وحده — لا يكتبها عميلٌ لا عبر إنشاء ولا تعديل.
        read_only_fields = [
            "source", "product_serial", "sales_invoice_line", "sales_invoice",
            "ended_on", "end_reason", "quantity", "returned_quantity",
            "created_at", "updated_at",
        ]

    def get_status(self, obj):
        return obj.status_on()

    def get_days_remaining(self, obj):
        return obj.days_remaining()

    def get_supplier_warranty_active(self, obj):
        return obj.supplier_active_on()

    def get_manufacturer_warrantor_name(self, obj):
        return obj.manufacturer_warrantor.name if obj.manufacturer_warrantor_id else ""

    def get_manufacturer_status(self, obj):
        return obj.manufacturer_status_on()

    def get_manufacturer_days_remaining(self, obj):
        return obj.manufacturer_days_remaining()

    def get_covered_quantity(self, obj):
        return obj.covered_quantity

    def get_product_name(self, obj):
        if not obj.product_id:
            return obj.device_name
        from inventory.services import product_display_name
        return product_display_name(obj.product)

    def get_partner_name(self, obj):
        return obj.partner.name if obj.partner_id else obj.customer_name

    def get_supplier_name(self, obj):
        return obj.supplier.name if obj.supplier_id else ""

    def get_ended(self, obj):
        return obj.ended_on is not None

    def get_sales_invoice_number(self, obj):
        # #222: من المرساة نفسها (`sales_invoice`) لا من البند — البند يُفرَّغ
        # حين تُعدَّل المسودّة فكان رقم الفاتورة يختفي عن بطاقةٍ لم تتغيّر.
        if obj.sales_invoice_id:
            return obj.sales_invoice.invoice_number
        line = obj.sales_invoice_line if obj.sales_invoice_line_id else None
        invoice = line.invoice if (line and line.invoice_id) else None
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

        # #232: طبقة المصنع — على نمط `WarrantyPolicy` نفسه: مدةٌ بلا جهة
        # مرفوضة، وجهةٌ بلا مدة أو بداية مرفوضة، والنهاية دائماً مشتقّة هنا لا
        # مُدخَلة (تعديل البداية على بطاقةٍ تلقائية يعيد احتسابها من المدة
        # المجمَّدة — `views.py` (`_AUTO_CARD_EDITABLE`) يفرض تجميد الباقي).
        warrantor = attrs.get(
            "manufacturer_warrantor", getattr(instance, "manufacturer_warrantor", None),
        )
        m_months = attrs.get(
            "manufacturer_duration_months",
            getattr(instance, "manufacturer_duration_months", 0) or 0,
        )
        m_start = attrs.get(
            "manufacturer_start_date", getattr(instance, "manufacturer_start_date", None),
        )
        if warrantor is None and m_months:
            raise serializers.ValidationError({
                "manufacturer_duration_months": "بلا جهة كفالة مصنع، مدتها يجب أن تكون صفراً.",
            })
        if warrantor is not None:
            if not m_months:
                raise serializers.ValidationError({
                    "manufacturer_duration_months": (
                        "اخترت جهة كفالة مصنع — حدّد مدتها بالأشهر، أو أزل الجهة."
                    ),
                })
            if m_start is None:
                raise serializers.ValidationError({
                    "manufacturer_start_date": "حدّد بداية كفالة المصنع.",
                })
            attrs["manufacturer_end_date"] = add_months(m_start, m_months)
        else:
            m_start = None
            attrs["manufacturer_end_date"] = None
        attrs["manufacturer_warrantor"] = warrantor
        attrs["manufacturer_duration_months"] = m_months
        attrs["manufacturer_start_date"] = m_start
        return attrs


class WarrantyCardEventSerializer(serializers.ModelSerializer):
    """سجل البطاقة — للقراءة فقط، إلحاقيّ لا يُكتب عبر هذا العقد (#229)."""

    event_type_label = serializers.CharField(
        source="get_event_type_display", read_only=True,
    )
    actor_name = serializers.SerializerMethodField()
    service_order_number = serializers.SerializerMethodField()

    class Meta:
        model = WarrantyCardEvent
        fields = [
            "id", "event_type", "event_type_label", "reason_code", "text",
            "service_order", "service_order_number", "actor", "actor_name",
            "old_end_date", "new_end_date", "quantity", "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        # الأقواس صريحة عمداً: بلا فاعل (`SET_NULL`، أو حدثٌ آليّ بلا مستخدم)
        # يجب أن يُقرأ «شرطٌ ثم بديل» لا أن يُقرأ بأولوية `or` فيلتبس على القارئ.
        return (obj.actor.get_full_name() or obj.actor.username) if obj.actor_id else ""

    def get_service_order_number(self, obj):
        return obj.service_order.order_number if obj.service_order_id else None


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
        """النهاية الجديدة — و**التمديد لا يقصّر** (#222 البند ٨).

        كان الرفض عند `end_date < start_date` وحده، فموظف المبيعات الذي يملك
        `aftersales.warranty.manage` (صلاحية عطاء) يقدر أن يسلب زبوناً شهوراً
        من كفالته باسم «تمديد». التقصير قرارٌ آخر بصلاحيةٍ أخرى ومسارٍ يوثّق
        سببه — لا خانة تاريخٍ في نافذة التمديد.
        """
        new_end = (
            self.validated_data["end_date"] if self.validated_data.get("end_date")
            else add_months(card.end_date, self.validated_data["months"])
        )
        if new_end <= card.end_date:
            raise serializers.ValidationError({
                "end_date": (
                    f"التمديد يُطيل الكفالة ولا يقصّرها — التاريخ الجديد "
                    f"({new_end}) ليس بعد نهايتها الحالية ({card.end_date})."
                )
            })
        return new_end


# ══════════════════════════════════════════════════════════════════════════
# جهات كفالة المصنع وإعدادات الوحدة (#230)
# ══════════════════════════════════════════════════════════════════════════

class ManufacturerWarrantorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManufacturerWarrantor
        fields = [
            "id", "name", "service_center_address", "phone", "notes",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("اسم جهة الكفالة مطلوب.")
        return value


class WarrantyPolicySerializer(serializers.ModelSerializer):
    """سياسة كفالة براند — التحقق هنا هو الجملة النهائية (#231).

    يُعاد استعمال هذا التحقّق حرفياً من `WarrantyPolicyViewSet.bulk`: كل صفٍّ
    يُطبَّق جماعياً يمرّ من نفس `is_valid()` — لا نسخة ثانية من القاعدة.
    """

    method_label = serializers.CharField(source="get_method_display", read_only=True)
    product_name = serializers.SerializerMethodField()
    manufacturer_warrantor_name = serializers.SerializerMethodField()
    last_purchase = serializers.SerializerMethodField()

    class Meta:
        model = WarrantyPolicy
        fields = [
            "id", "product", "product_name", "method", "method_label",
            "dealer_months",
            "manufacturer_warrantor", "manufacturer_warrantor_name",
            "manufacturer_months", "supplier_months", "terms_override",
            "last_purchase",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_last_purchase(self, obj):
        """آخر كفالة سطرٍ مرحَّل للمنتج (#235). الخريطة تُبنى مرةً للصفحة في
        `WarrantyPolicyViewSet.list`؛ وبدونها (تفصيل/حفظ) استعلامٌ واحد للصفّ."""
        lookup = self.context.get("last_purchase_map")
        if lookup is None:
            from .services import latest_purchase_line_warranties
            lookup = latest_purchase_line_warranties(obj.tenant_id, [obj.product_id])
        row = lookup.get(obj.product_id)
        if row is None:
            return None
        warrantor = row.manufacturer_warrantor
        return {
            "manufacturer_warrantor": row.manufacturer_warrantor_id,
            "manufacturer_warrantor_name": warrantor.name if warrantor else "",
            "manufacturer_months": row.manufacturer_months,
            "supplier_months": row.supplier_months,
            "invoice_date": row.invoice_date,
            "invoice_number": row.invoice_number,
        }

    def get_product_name(self, obj):
        if not obj.product_id:
            return ""
        from inventory.services import product_display_name
        return product_display_name(obj.product)

    def get_manufacturer_warrantor_name(self, obj):
        return obj.manufacturer_warrantor.name if obj.manufacturer_warrantor_id else ""

    def validate(self, attrs):
        instance = self.instance
        product = attrs.get("product", getattr(instance, "product", None))
        if product is None:
            raise serializers.ValidationError({"product": "حدّد المنتج (البراند)."})

        method = attrs.get(
            "method", getattr(instance, "method", WarrantyPolicy.METHOD_SERIAL),
        )
        if method == WarrantyPolicy.METHOD_SERIAL and product.is_service:
            raise serializers.ValidationError({
                "method": (
                    f"«{product.name_ar or product.name_en}» منتج خدمة — لا يُكفل "
                    "برقم تسلسلي، اختر «على الفاتورة»."
                ),
            })

        dealer = attrs.get("dealer_months", getattr(instance, "dealer_months", 0) or 0)
        warrantor = attrs.get(
            "manufacturer_warrantor", getattr(instance, "manufacturer_warrantor", None),
        )
        manufacturer = attrs.get(
            "manufacturer_months", getattr(instance, "manufacturer_months", 0) or 0,
        )

        if warrantor is None and manufacturer:
            raise serializers.ValidationError({
                "manufacturer_months": "بلا جهة كفالة مصنع، مدتها يجب أن تكون صفراً.",
            })
        if warrantor is not None and not manufacturer:
            raise serializers.ValidationError({
                "manufacturer_months": (
                    "اخترت جهة كفالة مصنع — حدّد مدتها بالأشهر، أو أزل الجهة."
                ),
            })

        # الطبقتان اللتان يراهما الزبون: التاجر والمصنع. كفالة المورّد داخلية
        # بيننا وبينه — وحدها كانت ستُصدر للزبون بطاقةً بصفر شهر، منتهيةً يوم بيعها.
        if not (dealer or manufacturer):
            raise serializers.ValidationError({
                "dealer_months": (
                    "حدّد مدة كفالة التاجر أو المصنع أكبر من صفر — كفالة المورّد "
                    "وحدها داخلية لا تُصدر للزبون بطاقة."
                ),
            })

        terms = attrs.get("terms_override", getattr(instance, "terms_override", "") or "")
        if len(terms) > TERMS_MAX_LENGTH:
            raise serializers.ValidationError({
                "terms_override": f"شروط البراند البديلة لا تتجاوز {TERMS_MAX_LENGTH} حرفاً.",
            })
        return attrs


class PurchaseLinePolicySerializer(serializers.ModelSerializer):
    """ما يحتاجه محرّر فاتورة الشراء من سياسة المنتج (#235) — بلا «آخر شراء»
    ولا الشروط: قراءةٌ خفيفة تُطلب دفعةً واحدة لكل منتجات الفاتورة."""

    class Meta:
        model = WarrantyPolicy
        fields = [
            "id", "product", "method",
            "manufacturer_warrantor", "manufacturer_months", "supplier_months",
        ]
        read_only_fields = fields


class WarrantyPolicyBulkSerializer(serializers.Serializer):
    """محدِّد التطبيق الجماعي — منتجٌ أبٌ **أو** تصنيف، لا كلاهما ولا بلا أحدهما."""

    family = serializers.IntegerField(required=False)
    category = serializers.IntegerField(required=False)
    method = serializers.ChoiceField(choices=WarrantyPolicy.METHOD_CHOICES)
    dealer_months = serializers.IntegerField(min_value=0, max_value=600, required=False, default=0)
    manufacturer_warrantor = serializers.IntegerField(required=False, allow_null=True)
    manufacturer_months = serializers.IntegerField(min_value=0, max_value=600, required=False, default=0)
    supplier_months = serializers.IntegerField(min_value=0, max_value=600, required=False, default=0)
    terms_override = serializers.CharField(required=False, allow_blank=True, max_length=TERMS_MAX_LENGTH)

    def validate(self, attrs):
        if bool(attrs.get("family")) == bool(attrs.get("category")):
            raise serializers.ValidationError({
                "detail": "حدّد منتجاً أباً واحداً أو تصنيفاً واحداً — لا كليهما ولا بلا أحدهما.",
            })
        return attrs


class AfterSalesSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AfterSalesSettings
        fields = [
            "default_terms", "extend_for_shop_days", "repair_warranty_days",
            "repair_terms", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_default_terms(self, value):
        if len(value) > TERMS_MAX_LENGTH:
            raise serializers.ValidationError(
                f"شروط الشركة لا تتجاوز {TERMS_MAX_LENGTH} حرفاً."
            )
        return value

    def validate_repair_terms(self, value):
        if len(value) > TERMS_MAX_LENGTH:
            raise serializers.ValidationError(
                f"شروط كفالة الإصلاح لا تتجاوز {TERMS_MAX_LENGTH} حرفاً."
            )
        return value

    def validate_repair_warranty_days(self, value):
        if value != 0 and not (1 <= value <= 730):
            raise serializers.ValidationError(
                "كفالة الإصلاح: صفرٌ يطفئها، أو مدةٌ من 1 إلى 730 يوماً."
            )
        return value


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
            "unit_price", "serials", "issued_cost", "notes", "sales_invoice_line",
            "materialized_at", "is_materialized", "created_at",
        ]
        # القفل من الخادم وحده: البند المُجسَّد واقعةٌ في الدفاتر لا حقلٌ يُرسَل.
        read_only_fields = [
            "sales_invoice_line", "materialized_at", "issued_cost", "created_at",
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

    def validate_billing(self, value):
        # `ModelSerializer` يفرض `choices` النموذج تلقائياً — هذا تصريحٌ صريح
        # يحمي المسار حتى لو تغيّر بناء الحقل، والفحص مذكورٌ صراحةً في العقد (#223).
        allowed = {choice for choice, _ in ServiceOrderPart.BILLING_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError(f"مسار فوترة غير معروف: {value}")
        return value

    def validate_serials(self, value):
        from inventory.serials import normalize_serials
        return normalize_serials(value)


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
