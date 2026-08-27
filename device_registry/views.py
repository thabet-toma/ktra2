"""API وحدة الأجهزة الحساسة (THA-45 M1).

كل نقطة هنا تفتح ببوابة الترخيص `require_module(...)` فترد **404 لا 403** على
شركةٍ غير مرخّصة: 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً. وكل استعلام
مقيّد بالشركة النشطة — لا افتراضي ولا سقوط على شركة أخرى.

نقطة كتابة التدقيق واحدة (`_audit`): تكتب الجدول المستقل دائماً، وتعكس أحداث
*التحرير* فقط إلى سجل النشاط المشترك. أحداث العرض/البحث تبقى في الجدول المستقل
وحده — حاجة أمنية خاصة بهذه الوحدة لا تُغرِق صفحة النشاط العامة.
"""
import logging

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.access import require_perm
from core.activity import _client_ip, build_activity_changes, log_activity
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module
from device_registry.models import DeviceAuditLog, SensitiveDevice, imei_is_valid
from device_registry.serializers import DeviceAuditLogSerializer, SensitiveDeviceSerializer

logger = logging.getLogger(__name__)

MODULE_KEY = "sensitive_devices"

PERM_VIEW = "devices.registry.view"
PERM_CREATE = "devices.registry.create"
PERM_EDIT = "devices.registry.edit"
PERM_DELETE = "devices.registry.delete"
PERM_AUDIT = "devices.audit.view"

_ACTION_PERMS = {
    "list": PERM_VIEW,
    "retrieve": PERM_VIEW,
    "check_imei": PERM_VIEW,
    "model_names": PERM_VIEW,
    "create": PERM_CREATE,
    "update": PERM_EDIT,
    "partial_update": PERM_EDIT,
    "destroy": PERM_DELETE,
    "restore": PERM_DELETE,
    "audit": PERM_AUDIT,
}

# حقول تُرصد في فرق التعديل، بتسمياتها العربية كما تُقرأ في سطر التدقيق.
_TRACKED_FIELDS = {
    "customer_name": "اسم الزبون",
    "customer_phone": "هاتف الزبون",
    "model_name": "الموديل",
    "serial_number": "الرقم التسلسلي",
    "imei": "IMEI",
    "technical_notes": "ملاحظات فنية",
    "photo_url": "صورة الجهاز",
    "status": "الحالة",
}

# أحداث التحرير وحدها تُعكس إلى `ActivityLog`، بمفردات أفعاله المعروفة — لا
# نخترع قيمة `action` جديدة في جدولٍ مشترك تقرأ الواجهة تسمياته من كتالوجه.
_MIRRORED_ACTIONS = {
    "register": ("create", "تسجيل جهاز حسّاس"),
    "update": ("update", "تعديل سجل جهاز حسّاس"),
    "status": ("update", "تغيير حالة جهاز حسّاس"),
    "delete": ("delete", "حذف سجل جهاز حسّاس"),
    "restore": ("update", "استرجاع سجل جهاز حسّاس محذوف"),
}


def _audit(request, tenant, action_key, *, device=None, details=None) -> None:
    """نقطة الكتابة الوحيدة للتدقيق. لا تُعطّل الطلب الأصلي مهما فشلت."""
    user = getattr(request, "user", None)
    actor = user if getattr(user, "is_authenticated", False) else None
    try:
        # savepoint: فشل الإدراج يتراجع وحده دون كسر معاملة المتصل.
        with transaction.atomic():
            DeviceAuditLog.objects.create(
                tenant=tenant,
                device=device,
                action=action_key,
                actor=actor,
                details=details or {},
                ip=_client_ip(request) or "",
            )
    except Exception:  # noqa: BLE001 — التدقيق لا يُسقط عمليةً نجحت
        logger.exception(
            "device audit failed (action=%s device=%s)", action_key, getattr(device, "pk", None),
        )

    mirrored = _MIRRORED_ACTIONS.get(action_key)
    if not mirrored:
        return
    mirrored_action, description = mirrored
    log_activity(
        action=mirrored_action,
        entity_type="sensitive_device",
        entity_id=getattr(device, "pk", None),
        # IMEI صار اختيارياً — السجل بلا IMEI يُعنون برقمه التسلسلي.
        entity_label=getattr(device, "imei", "") or getattr(device, "serial_number", "") or "",
        description=description,
        metadata=details or {},
        request=request,
        tenant=tenant,
        user=actor,
    )


def _duplicate_row(device) -> dict:
    return {
        "id": device.id,
        "created_at": device.created_at,
        "customer_name": device.customer_name,
        "status": device.status,
        "status_label": device.get_status_display(),
    }


class SensitiveDeviceViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = SensitiveDeviceSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # الترخيص أولاً: بلا ترخيص لا يُكشف حتى أن الصلاحية ناقصة.
        self.tenant = require_module(request, MODULE_KEY)
        required = _ACTION_PERMS.get(self.action)
        if required:
            require_perm(request, required, tenant=self.tenant)

    # ── الاستعلامات ────────────────────────────────────────────────────
    def _base_queryset(self):
        return (
            SensitiveDevice.all_objects
            .filter(tenant=self.tenant)
            .select_related("created_by", "deleted_by")
        )

    def _include_deleted(self) -> bool:
        requested = str(self.request.query_params.get("include_deleted", "")).lower()
        if requested not in ("1", "true", "yes"):
            return False
        require_perm(self.request, PERM_DELETE, tenant=self.tenant)
        return True

    def _filtered(self, queryset):
        params = self.request.query_params
        if not self._include_deleted():
            queryset = queryset.filter(deleted_at__isnull=True)

        term = (params.get("q") or "").strip()
        if term:
            queryset = queryset.filter(
                Q(imei__icontains=term)
                | Q(serial_number__icontains=term)
                | Q(customer_name__icontains=term)
                | Q(customer_phone__icontains=term)
            )

        status_filter = (params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        date_from = parse_date(params.get("date_from") or "")
        date_to = parse_date(params.get("date_to") or "")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_queryset(self):
        queryset = self._base_queryset()
        if self.action == "list":
            queryset = self._filtered(queryset)
        elif self.action not in ("restore", "audit"):
            # الاسترجاع وأثر التدقيق يريان المحذوف — وأثرُ سجلٍ حُذف هو أهمّ ما
            # يُقرأ. ما عداهما يعامل المحذوف كغير موجود.
            queryset = queryset.filter(deleted_at__isnull=True)
        return queryset.order_by("-created_at", "-id")

    def _duplicate_matches(self, imei, exclude_id=None):
        """التكرار داخل الشركة وعلى السجلات الحيّة فقط — فحصٌ عابر للشركات تسريب."""
        # IMEI اختياري: فراغ يطابق كل السجلات الفارغة — ليس تكراراً بل ضجيج.
        if not (imei or "").strip():
            return []
        queryset = SensitiveDevice.objects.filter(tenant=self.tenant, imei=imei)
        if exclude_id:
            queryset = queryset.exclude(pk=exclude_id)
        return [_duplicate_row(row) for row in queryset.order_by("-created_at")[:10]]

    # ── العمليات ──────────────────────────────────────────────────────
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        term = (request.query_params.get("q") or "").strip()
        if term:
            data = response.data
            count = data["count"] if isinstance(data, dict) and "count" in data else len(data)
            _audit(request, self.tenant, "search", details={
                "term": term,
                "filters": {
                    "status": request.query_params.get("status") or "",
                    "date_from": request.query_params.get("date_from") or "",
                    "date_to": request.query_params.get("date_to") or "",
                },
                "results": count,
            })
        return response

    def retrieve(self, request, *args, **kwargs):
        device = self.get_object()
        _audit(request, self.tenant, "view", device=device)
        return Response(self.get_serializer(device).data)

    def perform_create(self, serializer):
        # الشركة والمُسجِّل من سياق الطلب لا من جسمه — لا `tenant` قادم من العميل.
        self._created_device = serializer.save(
            tenant=self.tenant, created_by=self.request.user,
        )

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        device = self._created_device
        _audit(request, self.tenant, "register", device=device, details={
            "imei": device.imei,
            "serial_number": device.serial_number,
            "model_name": device.model_name,
        })
        # التكرار تنبيه لا منع: السجل حُفِظ، والواجهة تعرض السابق عليه.
        response.data["duplicate_of"] = self._duplicate_matches(
            device.imei, exclude_id=device.pk,
        )
        return response

    def update(self, request, *args, **kwargs):
        device = self.get_object()
        before = {field: getattr(device, field) for field in _TRACKED_FIELDS}
        response = super().update(request, *args, **kwargs)
        device.refresh_from_db()
        after = {field: getattr(device, field) for field in _TRACKED_FIELDS}

        changes = build_activity_changes(
            before=before, after=after, labels=_TRACKED_FIELDS,
        )
        if changes:
            _audit(request, self.tenant, "update", device=device, details={"changes": changes})
        if before["status"] != after["status"]:
            _audit(request, self.tenant, "status", device=device, details={
                "from": before["status"], "to": after["status"],
            })
        return response

    def destroy(self, request, *args, **kwargs):
        """حذف ناعم حصراً — لا مسار حذف نهائي في أي طبقة من هذه الوحدة."""
        device = self.get_object()
        device.deleted_at = timezone.now()
        device.deleted_by = request.user
        device.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
        _audit(request, self.tenant, "delete", device=device, details={"imei": device.imei})
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        device = self.get_object()
        if device.deleted_at is None:
            raise ValidationError({"detail": "هذا السجل غير محذوف."})
        device.deleted_at = None
        device.deleted_by = None
        device.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
        _audit(request, self.tenant, "restore", device=device)
        return Response(self.get_serializer(device).data)

    @action(detail=False, methods=["get"], url_path="check_imei")
    def check_imei(self, request):
        imei = (request.query_params.get("imei") or "").strip()
        valid = imei_is_valid(imei)
        matches = self._duplicate_matches(imei) if valid else []
        return Response({
            "valid": valid,
            "is_duplicate": bool(matches),
            "matches": matches,
        })

    @action(detail=False, methods=["get"], url_path="model_names")
    def model_names(self, request):
        """اقتراحات الموديلات من سجلات الشركة نفسها — بلا أي ربط بمنتجات المخزون."""
        names = (
            SensitiveDevice.objects
            .filter(tenant=self.tenant)
            .exclude(model_name="")
            .order_by("model_name")
            .values_list("model_name", flat=True)
            .distinct()
        )
        return Response(list(names))

    @action(detail=True, methods=["get"], url_path="audit")
    def audit(self, request, pk=None):
        device = self.get_object()
        rows = (
            DeviceAuditLog.objects
            .filter(tenant=self.tenant, device=device)
            .select_related("actor")
            .order_by("-created_at", "-id")
        )
        return Response(DeviceAuditLogSerializer(rows, many=True).data)
