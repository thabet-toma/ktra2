from rest_framework import serializers

from .models import Building, RentalUnit, Lease, ElectricMeter, MeterReading


class MeterReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeterReading
        fields = ["id", "meter", "reading_date", "kwh_value", "notes", "recorded_by", "created_at"]
        read_only_fields = ["id", "recorded_by", "created_at"]


class ElectricMeterSerializer(serializers.ModelSerializer):
    rental_unit_code = serializers.CharField(source="rental_unit.code", read_only=True)

    class Meta:
        model = ElectricMeter
        fields = [
            "id",
            "building",
            "meter_kind",
            "rental_unit",
            "rental_unit_code",
            "label",
            "serial_number",
            "created_at",
        ]
        read_only_fields = ["id", "rental_unit_code", "created_at"]

    def validate(self, attrs):
        building = attrs.get("building") or getattr(self.instance, "building", None)
        kind = attrs.get("meter_kind") or (self.instance.meter_kind if self.instance else None)
        unit = attrs.get("rental_unit")
        if self.instance:
            unit = attrs.get("rental_unit", self.instance.rental_unit)

        if kind == ElectricMeter.KIND_MAIN:
            if unit is not None:
                raise serializers.ValidationError(
                    {"rental_unit": "العداد الرئيسي لا يرتبط بوحدة؛ يخص العمارة بالكامل."}
                )
            qs = ElectricMeter.objects.filter(
                building=building,
                meter_kind=ElectricMeter.KIND_MAIN,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"meter_kind": "يوجد بالفعل عداد رئيسي لهذه العمارة."}
                )
        elif kind == ElectricMeter.KIND_SUB:
            if unit is None:
                raise serializers.ValidationError(
                    {"rental_unit": "العداد الفرعي يجب أن يرتبط بشقة أو مخزن."}
                )
            if unit.building_id != building.id:
                raise serializers.ValidationError(
                    {"rental_unit": "الوحدة لا تنتمي لنفس العمارة."}
                )
        return attrs


class LeaseSerializer(serializers.ModelSerializer):
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    building_name = serializers.CharField(source="unit.building.name", read_only=True)

    class Meta:
        model = Lease
        fields = [
            "id",
            "unit",
            "unit_code",
            "building_name",
            "renter_name",
            "renter_phone",
            "monthly_rent",
            "start_date",
            "end_date",
            "status",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "unit_code", "building_name", "created_at"]


class RentalUnitSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source="building.name", read_only=True)

    class Meta:
        model = RentalUnit
        fields = [
            "id",
            "building",
            "building_name",
            "unit_type",
            "floor_number",
            "code",
            "area_sqm",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "building_name", "created_at"]


class BuildingSerializer(serializers.ModelSerializer):
    units_count = serializers.IntegerField(read_only=True)
    main_meter_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Building
        fields = ["id", "tenant", "name", "address", "notes", "units_count", "main_meter_id", "created_at"]
        read_only_fields = ["id", "tenant", "units_count", "main_meter_id", "created_at"]


class MeterReadingListSerializer(serializers.ModelSerializer):
    """قراءة مع اسم العداد للقوائم."""

    meter_label = serializers.SerializerMethodField()

    class Meta:
        model = MeterReading
        fields = ["id", "meter", "meter_label", "reading_date", "kwh_value", "notes", "created_at"]

    def get_meter_label(self, obj):
        m = obj.meter
        if m.meter_kind == ElectricMeter.KIND_MAIN:
            return "عداد رئيسي"
        code = getattr(m.rental_unit, "code", "") or ""
        return f"فرعي — {code}"
