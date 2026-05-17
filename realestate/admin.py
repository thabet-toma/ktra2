from django.contrib import admin

from .models import Building, RentalUnit, Lease, ElectricMeter, MeterReading


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "tenant", "address")
    list_filter = ("tenant",)


@admin.register(RentalUnit)
class RentalUnitAdmin(admin.ModelAdmin):
    list_display = ("id", "building", "code", "unit_type", "floor_number", "is_active")
    list_filter = ("unit_type", "building")


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("id", "unit", "renter_name", "monthly_rent", "start_date", "status")
    list_filter = ("status",)


@admin.register(ElectricMeter)
class ElectricMeterAdmin(admin.ModelAdmin):
    list_display = ("id", "building", "meter_kind", "rental_unit", "label")
    list_filter = ("meter_kind",)


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("id", "meter", "reading_date", "kwh_value")
    list_filter = ("reading_date",)
