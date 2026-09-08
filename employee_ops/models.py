"""نماذج متابعة الموظفين (المرحلة الأولى: الأساس).

إعدادات الوحدة لكل شركة — لا حقل يحمل default=1 للشركة أبداً.
"""
from django.db import models
from tenants.models import Tenant


class EmployeeOpsSettings(models.Model):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_settings",
    )
    points_full = models.PositiveIntegerField(
        default=10,
        verbose_name="نقاط القبول الكامل",
    )
    points_partial = models.PositiveIntegerField(
        default=5,
        verbose_name="نقاط القبول الجزئي",
    )
    points_attendance = models.PositiveIntegerField(
        default=1,
        verbose_name="نقاط الحضور",
    )
    attendance_daily_cap = models.PositiveIntegerField(
        default=5,
        verbose_name="سقف نقاط الحضور يومياً",
    )
    leaderboard_highlight_count = models.PositiveIntegerField(
        default=5,
        verbose_name="عدد المُبرَزين في لوحة الشرف",
    )
    rejected_retention_months = models.PositiveIntegerField(
        default=12,
        verbose_name="أشهر الاحتفاظ بالطلبات المرفوضة",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاريخ التحديث",
    )

    class Meta:
        verbose_name = "إعدادات متابعة الموظفين"
        verbose_name_plural = "إعدادات متابعة الموظفين"

    def __str__(self):
        return str(self.tenant)
