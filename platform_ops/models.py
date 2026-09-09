"""نماذج عمليات المنصة (المرحلة الأولى: الأساس)."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenants.models import Tenant, UserCompanyMembership


class PlatformEmployee(models.Model):
    """موظف عمليات المنصة.

    هذا النموذج استثناء متعمَّد وموثَّق من قاعدة وجود مفتاح الشركة (tenant FK)؛
    فموظف عمليات المنصة ينتمي إلى المنصة نفسها وليس لأي شركة بعينها.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        ON_LEAVE = "on_leave", "في إجازة"
        OFFBOARDED = "offboarded", "خارج الخدمة"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_employee",
        verbose_name="المستخدم",
    )
    specialty = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="التخصص",
    )
    capacity_target = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="مستهدف السعة الموزون",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="الحالة",
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
        verbose_name = "موظف عمليات المنصة"
        verbose_name_plural = "موظفو عمليات المنصة"

    def __str__(self):
        return f"{self.user} ({self.get_status_display()})"


class ServiceSubscription(models.Model):
    """اشتراك الشركة في خدمة المتابعة والإدخال.

    صف الخدمة لكل شركة داخل الوحدة، وهو البوابة الوحيدة لإسناد موظف منصة للشركة.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        SUSPENDED = "suspended", "معلق"
        CANCELLED = "cancelled", "ملغى"

    # **صفٌّ واحدٌ لا صفّان**: المواصفة تقول «صفُّ الخدمة لكلّ شركة»، وهو نفسُه
    # بوّابةُ الإسناد وحاملُ الحدّ والعدّاد ودورة الفوترة. فاشتراكان لشركةٍ واحدة
    # يجعلان `included_quota`/`consumed_quota` غامضين وتقرأ الفوترةُ صفّاً عشوائياً.
    # والإلغاءُ يقلب `status` على الصفّ نفسِه؛ وتاريخُ الاشتراكات مكانُه الفواتير.
    # وهذه فرادةٌ **غيرُ مشروطة** فتفرضها MySQL فعلاً — بخلاف
    # `UniqueConstraint(condition=…)` التي تتجاهلها بصمت.
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="service_subscription",
        verbose_name="الشركة",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="حالة الاشتراك",
    )
    plan = models.CharField(
        max_length=50,
        default="standard",
        verbose_name="الباقة",
    )
    monthly_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="الرسم الشهري",
    )
    included_quota = models.PositiveIntegerField(
        default=0,
        verbose_name="العمليات المشمولة",
    )
    overage_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="سعر العملية الزائدة",
    )
    consumed_quota = models.PositiveIntegerField(
        default=0,
        verbose_name="العمليات المستهلكة",
    )
    period_start = models.DateField(
        null=True,
        blank=True,
        verbose_name="بداية الدورة",
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        verbose_name="نهاية الدورة",
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
        verbose_name = "اشتراك خدمة المتابعة"
        verbose_name_plural = "اشتراكات خدمة المتابعة"

    def __str__(self):
        return f"{self.tenant} - {self.plan} ({self.get_status_display()})"


class Engagement(models.Model):
    """ارتباط موظف عمليات المنصة بشركة زبون.

    يمثل إسناد موظف المنصة لإدارة دفاتر الشركة.
    حالاته: نشط (active) / معلق (suspended) / ملغى (revoked).
    لا يعتمد على قيد فرادة شرطي في قاعدة البيانات لأن MySQL تتجاهل
    UniqueConstraint(condition=...) بصمت، بل تُفرَض الفرادة
    في طبقة الخدمات تحت قفل select_for_update داخل معاملة ذرية.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        SUSPENDED = "suspended", "معلق"
        REVOKED = "revoked", "ملغى"

    employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.CASCADE,
        related_name="engagements",
        verbose_name="موظف العمليات",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="platform_engagements",
        verbose_name="الشركة",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="الحالة",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_platform_engagements",
        verbose_name="المُسنِد",
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإسناد",
    )
    created_membership = models.BooleanField(
        default=False,
        verbose_name="أنشأ العضوية",
        help_text="هل أنشأ هذا الارتباط عضوية المستخدم في الشركة أم كانت قائمة قبله؟",
    )
    managed_membership = models.ForeignKey(
        UserCompanyMembership,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managing_platform_engagements",
        verbose_name="العضوية المدارة",
    )
    previous_role = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="الدور السابق للعضوية المدارة",
    )
    suspended_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ التعليق",
    )
    suspension_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="سبب التعليق",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإلغاء",
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_platform_engagements",
        verbose_name="مُلغي الارتباط",
    )
    revocation_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="سبب الإلغاء",
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
        verbose_name = "ارتباط موظف المنصة"
        verbose_name_plural = "ارتباطات موظفي المنصة"
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"{self.employee} ↔ {self.tenant} ({self.get_status_display()})"


class AgentGrantedMembership(models.Model):
    """سجل العضويات الممنوحة أو المعدلة بواسطة وكيل منصة.

    يسجل كل عضوية أنشأها وكيل منصة أو عدل دورها داخل شركة الزبون، مع لقطة
    هوية ثابتة (identity_snapshot) تبقى ذات معنى حتى لو حُذفت العضوية لاحقاً.
    الحارس هنا هو التسجيل والمساءلة والشفافية لصاحب الشركة، لا الكنس التلقائي.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="agent_granted_memberships",
        verbose_name="الشركة",
    )
    acting_employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_memberships",
        verbose_name="موظف المنصة الفاعل",
    )
    engagement = models.ForeignKey(
        Engagement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_memberships",
        verbose_name="الارتباط الفاعل",
    )
    membership = models.ForeignKey(
        UserCompanyMembership,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_granted_records",
        verbose_name="العضوية",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_agent_granted_memberships",
        verbose_name="المستخدم المتأثر",
    )
    target_user_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="معرف المستخدم الأصلي",
        help_text="يبقى ثابتاً ومقروءاً حتى لو حُذف المستخدم أو العضوية",
    )
    identity_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="لقطة هوية المستخدم",
        help_text="لقطة ثابتة لبيانات المستخدم (الاسم، البريد، اسم المستخدم) وقت المنح",
    )
    role_before = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="الدور السابق",
    )
    role_after = models.CharField(
        max_length=50,
        verbose_name="الدور الجديد",
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
        verbose_name = "سجل عضوية ممنوحة من وكيل"
        verbose_name_plural = "سجلات العضويات الممنوحة من وكلاء"
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["acting_employee", "created_at"]),
        ]

    def __str__(self):
        username = self.identity_snapshot.get("username") or str(self.target_user_id or self.user_id)
        return f"{self.tenant}: {username} ({self.role_before or 'جديد'} → {self.role_after})"
