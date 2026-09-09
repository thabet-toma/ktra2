"""محولات بيانات عمليات المنصة."""
from rest_framework import serializers

from .models import IntegrationKey, PlatformEmployee, ServiceSubscription, WorkOrder


class PlatformEmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = PlatformEmployee
        fields = [
            "id",
            "user",
            "username",
            "email",
            "specialty",
            "capacity_target",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ServiceSubscriptionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)

    class Meta:
        model = ServiceSubscription
        fields = [
            "id",
            "tenant",
            "company_name",
            "status",
            "plan",
            "monthly_fee",
            "included_quota",
            "overage_unit_price",
            "consumed_quota",
            "period_start",
            "period_end",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WorkOrderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    assignee_name = serializers.SerializerMethodField()
    effective_duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrder
        fields = [
            "id",
            "tenant",
            "company_name",
            "title",
            "description",
            "kind",
            "source",
            "channel",
            "external_ref",
            "attachment_ids",
            "assignee",
            "assignee_name",
            "status",
            "return_status",
            "waiting_seconds_total",
            "waiting_entered_at",
            "received_at",
            "approved_at",
            "closed_at",
            "policy_snapshot",
            "deadline_at",
            "effective_duration_seconds",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "channel",
            "external_ref",
            "attachment_ids",
            "status",
            "return_status",
            "waiting_seconds_total",
            "waiting_entered_at",
            "approved_at",
            "closed_at",
            "policy_snapshot",
            "deadline_at",
            "effective_duration_seconds",
            "created_at",
            "updated_at",
        ]

    def get_assignee_name(self, obj):
        if obj.assignee and obj.assignee.user:
            return getattr(obj.assignee.user, "username", str(obj.assignee))
        return None

    def get_effective_duration_seconds(self, obj):
        return obj.calculate_effective_duration_seconds()


class IntegrationKeySerializer(serializers.ModelSerializer):
    """عرضُ مفتاح القناة — **بلا رمزٍ ولا تجزئة**.

    `token_hash` نفسُه لا يُعرَض: هو المادّةُ التي تُقارَن بها المحاولات، وعرضُه
    يمنح المهاجمَ هدفاً يعمل عليه دون داعٍ. والرمزُ الخامُّ لا يُحفَظ أصلاً فلا
    سبيلَ لعرضه بعد لحظةِ التوليد.
    """

    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)

    class Meta:
        model = IntegrationKey
        fields = [
            "id",
            "tenant",
            "company_name",
            "channel",
            "status",
            "name",
            "revoked_at",
            "revocation_reason",
            "rotated_at",
            "last_used_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
