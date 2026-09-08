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
    invitation_expiry_days = models.PositiveIntegerField(
        default=7,
        verbose_name="أجل رابط الدعوة بالأيام",
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


class EmployeeProfile(models.Model):
    """ملحقُ الموظف في هذه الوحدة — قائمةُ الموظفين تبقى `hr.Employee` وحدها.

    لا نُنشئ جدولَ موظفين ثانياً: الموديول يأخذ ملكيّة الشاشة لا الأعمدة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_profiles",
    )
    employee = models.OneToOneField(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="employee_ops_profile",
    )
    # manager معلومةٌ لا حارس — حاملُ employee_ops.manage يرى الجميع،
    # ولا تُفلتَر أيُّ استعلامٍ بهذا الحقل في أيّ مكان. تفصيلٌ في الهيكل يُقرأ ولا يُنفَّذ.
    manager = models.ForeignKey(
        "hr.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_ops_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ملحق موظف متابعة الموظفين"
        verbose_name_plural = "ملاحق موظفي متابعة الموظفين"

    def __str__(self):
        return f"ملحق {self.employee_id}"


class EmployeeInvitation(models.Model):
    """دعوة انضمام موظف لوحدة متابعة الموظفين."""

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_PENDING, "قيد الانتظار"),
        (STATUS_ACCEPTED, "مقبولة"),
        (STATUS_CANCELLED, "ملغاة"),
        (STATUS_EXPIRED, "منتهية الصلاحية"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_invitations",
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="employee_ops_invitations",
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "دعوة موظف"
        verbose_name_plural = "دعوات الموظفين"
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"دعوة {self.employee_id} ({self.status})"
