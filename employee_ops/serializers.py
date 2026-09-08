"""مُسلسِلات متابعة الموظفين (المرحلة الأولى: الأساس)."""
from rest_framework import serializers

from .models import EmployeeInvitation, EmployeeOpsSettings, EmployeeProfile


class EmployeeOpsSettingsSerializer(serializers.ModelSerializer):
    """إعدادات الوحدة لكل شركة.

    الحقول مذكورة صراحةً — `fields = "__all__"` ممنوع في هذا المستودع (فخٌّ عضّه
    سابقاً في سند الشيك: حقلٌ يُضاف للنموذج يصير قابلاً للكتابة من الشبكة بصمت).

    ولا تحقّق يدويّ على السالب هنا: الحقول `PositiveIntegerField`، فيشتقّ DRF
    منها `min_value=0` ويردّ 400 قبل أن يصل الرقم إلى أيّ `validate_*`. تحقّقٌ
    لا يستطيع السقوط ليس تحقّقاً.
    """

    class Meta:
        model = EmployeeOpsSettings
        fields = [
            "id",
            "tenant",
            "points_full",
            "points_partial",
            "points_attendance",
            "attendance_daily_cap",
            "leaderboard_highlight_count",
            "rejected_retention_months",
            "invitation_expiry_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_at", "updated_at"]
        # أجلٌ بصفرِ أيّامٍ دعوةٌ ميّتةٌ لحظةَ إنشائها — يُمنع هنا لا يُبتلع في الخدمة.
        extra_kwargs = {"invitation_expiry_days": {"min_value": 1}}


class EmployeeListSerializer(serializers.Serializer):
    """عرض موظفي الشركة في وحدة متابعة الموظفين."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    job_title = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    has_account = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    invitation_status = serializers.SerializerMethodField()

    def get_has_account(self, obj) -> bool:
        return bool(obj.user_id)

    def _get_profile(self, obj):
        # علاقةٌ عكسيّةٌ واحدٌ-لواحد ترفع `RelatedObjectDoesNotExist` لا تُعيد None،
        # والاستثناءُ محدَّدٌ لا عارٍ: `except Exception` هنا كان يبتلع أخطاء قاعدةٍ حقيقيّة.
        try:
            return obj.employee_ops_profile
        except EmployeeProfile.DoesNotExist:
            return None

    def get_manager(self, obj):
        profile = self._get_profile(obj)
        return profile.manager_id if profile else None

    def get_manager_name(self, obj):
        profile = self._get_profile(obj)
        if profile and profile.manager_id:
            return profile.manager.name if profile.manager else None
        return None

    def get_invitation_status(self, obj) -> str:
        annotated = getattr(obj, "annotated_invitation_status", None)
        if annotated in ("pending", "accepted"):
            return annotated
        return "none"


class EmployeeCreateSerializer(serializers.Serializer):
    """إنشاء موظف مع دعوة."""

    name = serializers.CharField(max_length=150, required=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    manager = serializers.IntegerField(required=False, allow_null=True, default=None)


class EmployeeUpdateSerializer(serializers.Serializer):
    """تعديل موظف — الاسم والهاتف والمسمّى والمدير المباشر فقط."""

    name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True)
    manager = serializers.IntegerField(required=False, allow_null=True)


class EmployeeInvitationSerializer(serializers.ModelSerializer):
    """بيانات دعوة الموظف (الرمز الخام لا يُخزن ولا يُعرض هنا)."""

    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = EmployeeInvitation
        fields = [
            "id",
            "tenant",
            "employee",
            "employee_name",
            "status",
            "expires_at",
            "created_by",
            "created_at",
            "accepted_at",
            "accepted_user",
        ]
        read_only_fields = fields


class AcceptInvitationSerializer(serializers.Serializer):
    """مدخلات قبول الدعوة وإنشاء الحساب."""

    # اختياريّان: الموظف **العائد** يملك حسابه، فقبولُه استعادةُ عضويّةٍ لا إنشاءُ حساب.
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    password = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
