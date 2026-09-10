"""محولات بيانات عمليات المنصة."""
from rest_framework import serializers

from .models import (
    DailyRating,
    DailyRatingToken,
    IntegrationKey,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
    PolicyProfile,
    ServiceSubscription,
    WorkOrder,
)


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
    # التسمياتُ المقروءة: الواجهةُ كانت تعرض `data_entry` و`waiting_customer` خامّةً
    # لأنّ الخادمَ لا يُعلن نصّاً لها، ولا يجوز أن تُترجمها الواجهةُ بجدولٍ ثانٍ يتباعد.
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
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
            "kind_display",
            "source",
            "source_display",
            "channel",
            "external_ref",
            "attachment_ids",
            "assignee",
            "assignee_name",
            "status",
            "status_display",
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
            "kind_display",
            "source_display",
            "status_display",
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


class PolicyProfileSerializer(serializers.ModelSerializer):
    """محول بيانات ملف سياسة الأداء — قراءة للمدير وفريق العمليات."""

    class Meta:
        model = PolicyProfile
        fields = [
            "id",
            "specialty",
            "name",
            "description",
            "weights",
            "targets",
            "sla_hours_by_kind",
            "min_sample_size",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PerformanceSnapshotSerializer(serializers.ModelSerializer):
    """محول بيانات لقطة الأداء الشهرية — قراءة فقط."""

    specialty = serializers.CharField(
        source="employee.specialty", read_only=True, default=""
    )
    employee_name = serializers.CharField(source="employee.user.username", read_only=True)
    specialty = serializers.CharField(source="employee.specialty", read_only=True)

    class Meta:
        model = PerformanceSnapshot
        fields = [
            "id",
            "employee",
            "employee_name",
            "specialty",
            "specialty",
            "period_year",
            "period_month",
            "status",
            "composite_score",
            "sample_size",
            "policy_profile",
            "policy_snapshot",
            "metrics_data",
            "axes_data",
            "rework_rate",
            "processed_sales_value",
            "captured_at",
            "captured_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PlatformNotificationSerializer(serializers.ModelSerializer):
    """محول بيانات إشعارات عمليات المنصة (م٦)."""

    notification_type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )
    company_name = serializers.CharField(
        source="tenant.CompanyName", read_only=True, default=None
    )

    class Meta:
        model = PlatformNotification
        fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "is_read",
            "read_at",
            "tenant",
            "company_name",
            "data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "tenant",
            "company_name",
            "data",
            "created_at",
            "updated_at",
        ]


class PlatformActivityLogSerializer(serializers.ModelSerializer):
    """محول بيانات سجل أنشطة موظفي المنصة عبر الشركات (م٦)."""

    employee_name = serializers.CharField(
        source="employee.user.username", read_only=True
    )
    company_name = serializers.CharField(
        source="tenant.CompanyName", read_only=True, default=None
    )
    action_display = serializers.CharField(
        source="get_action_display", read_only=True
    )

    class Meta:
        model = PlatformActivityLog
        fields = [
            "id",
            "employee",
            "employee_name",
            "tenant",
            "company_name",
            "action",
            "action_display",
            "entity_type",
            "entity_id",
            "description",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class DailyRatingSerializer(serializers.ModelSerializer):
    """محول بيانات التقييم اليومي (م٧)."""

    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = DailyRating
        fields = [
            "id",
            "tenant",
            "company_name",
            "employee",
            "employee_name",
            "service_date",
            "stars",
            "note",
            "edited_once",
            "source",
            "rated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "company_name",
            "employee_name",
            "edited_once",
            "source",
            "rated_by",
            "created_at",
            "updated_at",
        ]

    def get_employee_name(self, obj) -> str:
        if obj.employee and obj.employee.user:
            return obj.employee.user.get_full_name() or obj.employee.user.username
        return ""


class DailyRatingCreateSerializer(serializers.Serializer):
    """بيانات إدخال التقييم اليومي من داخل التطبيق."""

    employee_id = serializers.IntegerField(required=True)
    service_date = serializers.DateField(required=True)
    stars = serializers.IntegerField(min_value=1, max_value=5, required=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class DailyRatingUpdateSerializer(serializers.Serializer):
    """تعديل التقييم اليومي لمرة واحدة.

    `stars` إلزاميّةٌ في `PUT` واختياريّةٌ في `PATCH` — والمُنشئُ يمرّر `partial`
    فيرفعُ الإلزامَ من تلقاء `Serializer`، فلا يُردّ تعديلُ الملاحظةِ وحدَها بـ400.
    """

    stars = serializers.IntegerField(min_value=1, max_value=5, required=True)
    note = serializers.CharField(required=False, allow_blank=True)


class GenerateRatingLinkSerializer(serializers.Serializer):
    """طلب توليد رابط التقييم اليومي المهشر."""

    employee_id = serializers.IntegerField(required=True)
    service_date = serializers.DateField(required=True)


#: سقفُ ملاحظةِ التقييم على السطح **العام** — حقلٌ بلا حدٍّ يصبّ في `TextField`
#: على نقطةٍ بلا مصادقة، والمواصفة تسمّي «الحجمَ والفحصَ بالبايتات» على الأسطح العامة.
PUBLIC_RATING_NOTE_MAX_LENGTH = 2000


class PublicRatingSubmitSerializer(serializers.Serializer):
    """إرسال التقييم من الرابط العام."""

    stars = serializers.IntegerField(min_value=1, max_value=5, required=True)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=PUBLIC_RATING_NOTE_MAX_LENGTH,
    )


