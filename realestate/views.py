from django.db.models import Count, OuterRef, Subquery
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.tenant_utils import get_tenant

from .models import Building, RentalUnit, Lease, ElectricMeter, MeterReading
from .serializers import (
    BuildingSerializer,
    RentalUnitSerializer,
    LeaseSerializer,
    ElectricMeterSerializer,
    MeterReadingSerializer,
    MeterReadingListSerializer,
)


class TenantScopedViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def _tenant(self):
        return get_tenant(self.request)


class BuildingViewSet(TenantScopedViewSet):
    serializer_class = BuildingSerializer

    def get_queryset(self):
        tenant = self._tenant()
        qs = Building.objects.filter(tenant=tenant).annotate(units_count=Count("units", distinct=True))
        main_sub = (
            ElectricMeter.objects.filter(
                building_id=OuterRef("pk"),
                meter_kind=ElectricMeter.KIND_MAIN,
            )
            .order_by("id")
            .values("id")[:1]
        )
        return qs.annotate(main_meter_id=Subquery(main_sub))

    def perform_create(self, serializer):
        serializer.save(tenant=self._tenant())


class RentalUnitViewSet(TenantScopedViewSet):
    serializer_class = RentalUnitSerializer

    def get_queryset(self):
        tenant = self._tenant()
        qs = RentalUnit.objects.filter(building__tenant=tenant).select_related("building")
        bid = self.request.query_params.get("building")
        if bid:
            qs = qs.filter(building_id=bid)
        return qs.order_by("building", "floor_number", "code")


class LeaseViewSet(TenantScopedViewSet):
    serializer_class = LeaseSerializer

    def get_queryset(self):
        tenant = self._tenant()
        qs = Lease.objects.filter(unit__building__tenant=tenant).select_related("unit", "unit__building")
        bid = self.request.query_params.get("building")
        uid = self.request.query_params.get("unit")
        if bid:
            qs = qs.filter(unit__building_id=bid)
        if uid:
            qs = qs.filter(unit_id=uid)
        return qs


class ElectricMeterViewSet(TenantScopedViewSet):
    serializer_class = ElectricMeterSerializer

    def get_queryset(self):
        tenant = self._tenant()
        qs = ElectricMeter.objects.filter(building__tenant=tenant).select_related(
            "building", "rental_unit"
        )
        bid = self.request.query_params.get("building")
        if bid:
            qs = qs.filter(building_id=bid)
        return qs


class MeterReadingViewSet(TenantScopedViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return MeterReadingListSerializer
        return MeterReadingSerializer

    def get_queryset(self):
        tenant = self._tenant()
        qs = MeterReading.objects.filter(meter__building__tenant=tenant).select_related(
            "meter", "meter__rental_unit"
        )
        bid = self.request.query_params.get("building")
        mid = self.request.query_params.get("meter")
        if bid:
            qs = qs.filter(meter__building_id=bid)
        if mid:
            qs = qs.filter(meter_id=mid)
        return qs

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user if self.request.user.is_authenticated else None)


class RealestateSummaryViewSet(viewsets.ViewSet):
    """ملخص استهلاك: آخر قراءة للرئيسي ومجموع آخر قراءات الفرعية (للمقارنة التقريبية)."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def list(self, request):
        tenant = get_tenant(request)
        bid = request.query_params.get("building")
        if not bid:
            return Response({"detail": "أرسل معامل building"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            building = Building.objects.get(pk=bid, tenant=tenant)
        except Building.DoesNotExist:
            return Response({"detail": "العمارة غير موجودة"}, status=status.HTTP_404_NOT_FOUND)

        main = (
            ElectricMeter.objects.filter(building=building, meter_kind=ElectricMeter.KIND_MAIN)
            .order_by("id")
            .first()
        )
        subs = ElectricMeter.objects.filter(building=building, meter_kind=ElectricMeter.KIND_SUB).select_related(
            "rental_unit"
        )

        def latest_kwh(meter):
            if not meter:
                return None
            r = meter.readings.order_by("-reading_date", "-id").first()
            return float(r.kwh_value) if r else None

        main_latest = latest_kwh(main)
        sub_rows = []
        sub_sum_latest = 0.0
        for sm in subs:
            v = latest_kwh(sm)
            sub_rows.append(
                {
                    "meter_id": sm.id,
                    "unit_code": sm.rental_unit.code if sm.rental_unit else "",
                    "label": sm.label,
                    "latest_kwh": v,
                }
            )
            if v is not None:
                sub_sum_latest += v

        diff_hint = None
        if main_latest is not None:
            diff_hint = round(main_latest - sub_sum_latest, 3)

        return Response(
            {
                "building_id": building.id,
                "building_name": building.name,
                "main_meter_id": main.id if main else None,
                "main_latest_kwh": main_latest,
                "sub_meters": sub_rows,
                "sub_latest_kwh_sum": round(sub_sum_latest, 3) if sub_rows else None,
                "main_minus_sub_latest_hint": diff_hint,
                "note": "المقارنة بين مجموع «آخر قراءة» للفرعي والرئيسي تفيد كتلميح فقط؛ الفوترة تعتمد على الفرق بين دورتين.",
            }
        )
