"""نماذج عمليات المنصة (المرحلة الأولى: الأساس)."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Tenant, UserCompanyMembership


class IntegrationKey(models.Model):
    """مفتاح قناة الاستقبال لعمليات المنصة (المرحلة الرابعة: م٤).

    صف لكل (شركة × قناة).
    - المفتاح يُخزَّن مهشَّراً فقط (SHA-256)؛ الرمز الخام يظهر مرة واحدة لحظة التوليد.
    - قابل للإبطال والتدوير مع طوابع الإبطال والتدوير.
    - فرادة غير مشروطة لكل (tenant, channel) تفرضها MySQL بقيد غير شرطي.
    """

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "واتساب"
        TELEGRAM = "telegram", "تيليجرام"
        EMAIL = "email", "بريد إلكتروني"
        API = "api", "واجهة برمجية (API)"
        WEBHOOK = "webhook", "ويب هوك"
        PORTAL = "portal", "بوابة"

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        REVOKED = "revoked", "مبطل"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="platform_integration_keys",
        verbose_name="الشركة",
    )
    channel = models.CharField(
        max_length=50,
        choices=Channel.choices,
        default=Channel.WHATSAPP,
        verbose_name="القناة",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="مهشر الرمز",
        help_text="تجزئة SHA-256 للرمز الخام؛ الرمز الأصلي لا يُحفظ في القاعدة أبداً",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="الحالة",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="تسمية المفتاح",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإبطال",
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="مُبطِل المفتاح",
    )
    revocation_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="سبب الإبطال",
    )
    rotated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ التدوير",
    )
    revocation_history = models.JSONField(
        default=list,
        blank=True,
        verbose_name="سجل الإبطالات السابقة",
        help_text=(
            "كل إبطال سابق لهذا الصف: متى وبأمر من ولماذا. الفرادة على (شركة، قناة) "
            "غير مشروطة فالصف واحد، ولولا هذا السجل لمحا إصدارُ مفتاحٍ جديد سببَ إبطال سابقه."
        ),
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ آخر استخدام",
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
        verbose_name = "مفتاح قناة الاستقبال"
        verbose_name_plural = "مفاتيح قنوات الاستقبال"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "channel"],
                name="platform_ops_integrationkey_tenant_channel_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["channel", "status"]),
        ]

    def __str__(self):
        return f"{self.tenant} - {self.get_channel_display()} ({self.get_status_display()})"


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


class WorkOrder(models.Model):
    """أمر عمل في مركز قيادة عمليات المنصة (المرحلة الثالثة: م٣).

    يمثل مهمة أو طلب عمل تنفذه المنصة لشركة الزبون (إدخال بيانات، مراجعة، مبيعات، إلخ).
    - كيان واحد محكوم بنوع (kind) ومصدر (source).
    - tenant FK إلزامي (شركة واحدة فقط لكل أمر عمل).
    - مسؤول واحد فقط (assignee FK إلى PlatformEmployee، يقبل NULL إذا كان في الطابور).
    - آلة حالات صارمة محكومة بطبقة الخدمات.
    - الأجل يُقاس من received_at إلى approved_at مع إيقاف العداد عند waiting_customer.
    - لقطة سياسة الأجل (policy_snapshot) تُحفظ على الصف عند الإنشاء لمنع تأثر الماضي بتعديل الإعدادات.
    """

    class Kind(models.TextChoices):
        DATA_ENTRY = "data_entry", "إدخال بيانات"
        REVIEW = "review", "مراجعة"
        SALES = "sales", "مبيعات"
        SERVICE = "service", "خدمة"
        INQUIRY = "inquiry", "استفسار"
        ADMIN_DIRECTIVE = "admin_directive", "توجيه إداري"

    class Source(models.TextChoices):
        CHANNEL = "channel", "قناة"
        STAFF = "staff", "موظف"
        ADMIN = "admin", "إدارة"

    class Status(models.TextChoices):
        RECEIVED = "received", "مستلم"
        SCREENING = "screening", "فرز وفحص"
        DATA_ENTRY = "data_entry", "إدخال بيانات"
        REVIEW = "review", "مراجعة"
        APPROVAL = "approval", "اعتماد"
        CLOSED = "closed", "مغلق"
        WAITING_CUSTOMER = "waiting_customer", "بانتظار العميل"
        CANCELLED = "cancelled", "ملغى"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="platform_work_orders",
        verbose_name="الشركة",
    )
    title = models.CharField(
        max_length=255,
        verbose_name="عنوان أمر العمل",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="الوصف",
    )
    kind = models.CharField(
        max_length=30,
        choices=Kind.choices,
        default=Kind.DATA_ENTRY,
        verbose_name="نوع أمر العمل",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.STAFF,
        verbose_name="المصدر",
    )
    assignee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_work_orders",
        verbose_name="المسؤول",
        help_text="مسؤول واحد فقط عن أمر العمل (يقبل فارغاً = في الطابور)",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.RECEIVED,
        verbose_name="الحالة",
    )
    return_status = models.CharField(
        max_length=30,
        choices=Status.choices,
        blank=True,
        default="",
        verbose_name="حالة العودة بعد الانتظار",
        help_text="الحالة التي كان عليها أمر العمل قبل دخوله في انتظار العميل",
    )
    waiting_entered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت دخول فترة الانتظار الحالية",
    )
    waiting_seconds_total = models.PositiveIntegerField(
        default=0,
        verbose_name="إجمالي ثواني الانتظار المتراكمة",
        help_text="مجموع فترات انتظار رد العميل المحسومة من حساب الأجل",
    )
    received_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="وقت الاستلام",
        help_text="نقطة بداية قياس الأجل (SLA)",
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت الاعتماد",
        help_text="نقطة نهاية قياس الأجل (SLA)",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت الإغلاق",
    )
    policy_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="لقطة سياسة الأجل",
        help_text="نسخة ثابتة من سياسة الأجل السارية وقت الإنشاء",
    )
    deadline_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="موعد الأجل النهائي",
    )
    channel = models.CharField(
        max_length=50,
        blank=True,
        default="",
        choices=IntegrationKey.Channel.choices,
        verbose_name="قناة الاستقبال",
    )
    external_ref = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="المرجع الخارجي",
        help_text="معرف فريد للرسالة/الطلب من القناة الخارجية لضمان idempotency",
    )
    integration_key = models.ForeignKey(
        IntegrationKey,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_orders",
        verbose_name="مفتاح التكامل",
    )
    intake_payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="حمولة الاستقبال الأصلية",
    )
    attachment_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name="معرفات المرفقات",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="أنشئ بواسطة",
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
        verbose_name = "أمر عمل"
        verbose_name_plural = "أوامر العمل"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "channel", "external_ref"],
                name="platform_ops_workorder_tenant_channel_extref_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "kind"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["channel", "external_ref"]),
        ]

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.title} ({self.get_status_display()})"

    def open_waiting_seconds(self, now=None) -> int:
        """ثواني فترةِ الانتظار **المفتوحة** الآن — صفرٌ إن لم يكن الأمرُ منتظِراً.

        مصدرٌ واحدٌ لهذا الحساب: كان مكرَّراً في ثلاثة مواضع، وحسابٌ مكرَّرٌ يعني
        أنّ تصحيحَ أحدِها لا يصحّح أخوَيه.
        """
        if self.approved_at or self.status != self.Status.WAITING_CUSTOMER:
            return 0
        if not self.waiting_entered_at:
            return 0
        cur_now = now or timezone.now()
        if cur_now <= self.waiting_entered_at:
            return 0
        return int((cur_now - self.waiting_entered_at).total_seconds())

    def calculate_effective_duration_seconds(self, now=None) -> int:
        """حساب الزمن الفعلي المحتسب من received_at إلى approved_at بعد خصم فترات الانتظار."""
        end_time = self.approved_at or (now or timezone.now())
        if not self.received_at or end_time < self.received_at:
            return 0
        total_seconds = (end_time - self.received_at).total_seconds()
        waiting = self.waiting_seconds_total + self.open_waiting_seconds(now=now)
        effective = total_seconds - waiting
        return max(0, int(effective))


class WorkOrderDeliverable(models.Model):
    """مُسلَّم أمر العمل.

    يمثل مخرجات أمر العمل المنجزة (ملاحظة، تقرير هيكلي، مرفق).
    - محتوى التسليم يُحفظ كلقطة غير قابلة للتعديل اللاحق.
    - يدعم دورة المراجعة والاعتماد أو الرفض مع سبب صريح.
    """

    class Kind(models.TextChoices):
        NOTE = "note", "ملاحظة"
        STRUCTURED_REPORT = "structured_report", "تقرير هيكلي"
        ATTACHMENT = "attachment", "مرفق"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "بانتظار المراجعة"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="platform_work_order_deliverables",
        verbose_name="الشركة",
    )
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="deliverables",
        verbose_name="أمر العمل",
    )
    kind = models.CharField(
        max_length=30,
        choices=Kind.choices,
        default=Kind.NOTE,
        verbose_name="نوع المُسلَّم",
    )
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        verbose_name="حالة المراجعة",
    )
    content = models.TextField(
        blank=True,
        default="",
        verbose_name="المحتوى النصي",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="البيانات الهيكلية",
    )
    file_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="رابط المرفق",
    )
    content_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="لقطة التسليم الثابتة",
        help_text="لقطة محتوى التسليم وقت التقديم لا تتغير بتحرير المصدر لاحقاً",
    )
    rejection_reason = models.TextField(
        blank=True,
        default="",
        verbose_name="سبب الرفض",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="المراجع",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ المراجعة",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="المُسلِّم",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ التسليم",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاريخ التحديث",
    )

    class Meta:
        verbose_name = "مُسلَّم أمر العمل"
        verbose_name_plural = "مُسلَّمات أوامر العمل"
        indexes = [
            models.Index(fields=["work_order", "review_status"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self):
        return f"{self.work_order}: {self.get_kind_display()} ({self.get_review_status_display()})"


class WorkOrderComment(models.Model):
    """تعليق أو استفسار على أمر العمل.

    - حقل visibility إلزامي على كل تعليق (internal أو client_visible).
    - التعليق الداخلي محجوب تماماً عن أي مسار موجه للزبون.
    """

    class Visibility(models.TextChoices):
        INTERNAL = "internal", "داخلي"
        CLIENT_VISIBLE = "client_visible", "مرئي للزبون"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="platform_work_order_comments",
        verbose_name="الشركة",
    )
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="أمر العمل",
    )
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        verbose_name="مستوى الظهور",
        help_text="إلزامي: داخلي لموظفي المنصة أو مرئي للزبون",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name="الكاتب",
    )
    content = models.TextField(
        verbose_name="نص التعليق",
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
        verbose_name = "تعليق أمر العمل"
        verbose_name_plural = "تعليقات أوامر العمل"
        indexes = [
            models.Index(fields=["work_order", "visibility", "created_at"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self):
        return f"{self.work_order} - {self.author} [{self.get_visibility_display()}]"
