"""سيريالايزرات وحدة الأجهزة الحساسة — تحقق الحقول هو مصدر أخطاء 400."""
from rest_framework import serializers

from device_registry.models import DeviceAuditLog, SensitiveDevice, normalize_phone


def _user_name(user) -> str:
    if user is None:
        return "—"
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.username


class SensitiveDeviceSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    deleted_by_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_deleted = serializers.SerializerMethodField()

    class Meta:
        model = SensitiveDevice
        fields = [
            "id", "customer_name", "customer_phone", "model_name", "serial_number",
            "imei", "technical_notes", "photo_url", "status", "status_label",
            "created_by", "created_by_name", "created_at", "updated_at",
            "deleted_at", "deleted_by_name", "is_deleted",
        ]
        # الشركة والمُسجِّل والحذف تُحسم في الخادم — لا تُقبل من الجسم أبداً.
        read_only_fields = ["created_by", "created_at", "updated_at", "deleted_at"]

    def get_created_by_name(self, obj):
        return _user_name(obj.created_by)

    def get_deleted_by_name(self, obj):
        return _user_name(obj.deleted_by) if obj.deleted_by_id else ""

    def get_is_deleted(self, obj):
        return obj.deleted_at is not None

    def validate_customer_phone(self, value):
        """يُخزَّن الرقم مطبّعاً كي يعمل البحث برقم الهاتف على شكل واحد."""
        return normalize_phone(value)


class DeviceAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = DeviceAuditLog
        fields = [
            "id", "device", "action", "action_label", "actor", "actor_name",
            "details", "ip", "created_at",
        ]

    def get_actor_name(self, obj):
        return _user_name(obj.actor)
