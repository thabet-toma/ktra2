"""مُسلسِلات متابعة الموظفين (المرحلة الأولى: الأساس)."""
from rest_framework import serializers

from .models import EmployeeOpsSettings


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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_at", "updated_at"]
