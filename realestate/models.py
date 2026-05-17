from django.db import models
from django.conf import settings
from tenants.models import Tenant
from core.base_models import TimeStampMixin


class Building(TimeStampMixin, models.Model):
    """عمارة أو مجمع — يحتوي عدادًا رئيسيًا للكهرباء ووحدات (شقق / مخازن)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="buildings",
        db_column="TenantID",
    )
    name = models.CharField(max_length=200, db_column="name")
    address = models.CharField(max_length=500, blank=True, default="", db_column="address")
    notes = models.TextField(blank=True, default="", db_column="notes")

    class Meta:
        db_table = "realestate_buildings"
        ordering = ["name"]

    def __str__(self):
        return self.name


class RentalUnit(TimeStampMixin, models.Model):
    UNIT_APARTMENT = "apartment"
    UNIT_WAREHOUSE = "warehouse"
    UNIT_TYPE_CHOICES = [
        (UNIT_APARTMENT, "شقة"),
        (UNIT_WAREHOUSE, "مخزن"),
    ]

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="units",
        db_column="building_id",
    )
    unit_type = models.CharField(
        max_length=20,
        choices=UNIT_TYPE_CHOICES,
        default=UNIT_APARTMENT,
        db_column="unit_type",
    )
    floor_number = models.SmallIntegerField(default=0, db_column="floor_number")
    code = models.CharField(
        max_length=80,
        db_column="code",
        help_text="رمز الوحدة مثل: 3أ، مخزن-1",
    )
    area_sqm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        db_column="area_sqm",
    )
    is_active = models.BooleanField(default=True, db_column="is_active")

    class Meta:
        db_table = "realestate_rental_units"
        ordering = ["building", "floor_number", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["building", "code"],
                name="realestate_unit_unique_code_per_building",
            ),
        ]

    def __str__(self):
        return f"{self.building.name} — {self.code}"


class Lease(TimeStampMixin, models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "ساري"),
        (STATUS_ENDED, "منتهي"),
    ]

    unit = models.ForeignKey(
        RentalUnit,
        on_delete=models.CASCADE,
        related_name="leases",
        db_column="unit_id",
    )
    renter_name = models.CharField(max_length=200, db_column="renter_name")
    renter_phone = models.CharField(max_length=40, blank=True, default="", db_column="renter_phone")
    monthly_rent = models.DecimalField(max_digits=14, decimal_places=2, db_column="monthly_rent")
    start_date = models.DateField(db_column="start_date")
    end_date = models.DateField(null=True, blank=True, db_column="end_date")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_column="status",
    )
    notes = models.TextField(blank=True, default="", db_column="notes")

    class Meta:
        db_table = "realestate_leases"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.renter_name} — {self.unit}"


class ElectricMeter(TimeStampMixin, models.Model):
    KIND_MAIN = "main"
    KIND_SUB = "sub"
    KIND_CHOICES = [
        (KIND_MAIN, "رئيسي"),
        (KIND_SUB, "فرعي"),
    ]

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="electric_meters",
        db_column="building_id",
    )
    meter_kind = models.CharField(
        max_length=10,
        choices=KIND_CHOICES,
        db_column="meter_kind",
    )
    rental_unit = models.ForeignKey(
        RentalUnit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="electric_meters",
        db_column="rental_unit_id",
        help_text="للعداد الفرعي فقط — يرتبط بشقة أو مخزن",
    )
    label = models.CharField(max_length=120, blank=True, default="", db_column="label")
    serial_number = models.CharField(max_length=80, blank=True, default="", db_column="serial_number")

    class Meta:
        db_table = "realestate_electric_meters"
        ordering = ["building", "meter_kind", "id"]

    def __str__(self):
        if self.meter_kind == self.KIND_MAIN:
            return f"رئيسي — {self.building.name}"
        ucode = getattr(self.rental_unit, "code", None) or str(self.rental_unit_id or "")
        return f"فرعي — {ucode} ({self.building.name})"


class MeterReading(TimeStampMixin, models.Model):
    meter = models.ForeignKey(
        ElectricMeter,
        on_delete=models.CASCADE,
        related_name="readings",
        db_column="meter_id",
    )
    reading_date = models.DateField(db_column="reading_date")
    kwh_value = models.DecimalField(max_digits=14, decimal_places=3, db_column="kwh_value")
    notes = models.CharField(max_length=500, blank=True, default="", db_column="notes")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meter_readings",
        db_column="recorded_by_id",
    )

    class Meta:
        db_table = "realestate_meter_readings"
        ordering = ["-reading_date", "-id"]

    def __str__(self):
        return f"{self.meter_id} @ {self.reading_date}: {self.kwh_value}"
