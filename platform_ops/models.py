"""نماذج عمليات المنصة (المرحلة الأولى: الأساس)."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import Tenant, UserCompanyMembership

#: أقصى أيام تجربة لخدمة الإدخال — حدّ أمان واحد تقرؤه النماذج والخدمات والمُسلسِلات.
MAX_SERVICE_TRIAL_DAYS = 30


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


class ServiceSubscriptionPolicy(models.Model):
    """نسخة مؤرخة من افتراضيات اشتراك خدمة المنصة.

    النسخة النشطة لا تُعدّل؛ تُنشأ نسخة مسودة جديدة ثم تُفعّل لتصبح مرجعاً
    تاريخياً. `billing_tenant` هو شركة المنصة المفوترة التي يجب أن ينتمي إليها
    عميل الفوترة وصنفا الفوترة عند إنشاء اشتراك جديد.

    `plan` نطاق النسخة: فارغ = عامة لكل الخطط، أو اسم خطة بعينها تغلب العامة.
    السريان تحدده نافذة `effective_from`/`effective_to` لا حقل الحالة وحده: نسخة
    `active` بتاريخ سريان لاحق «مجدولة»، ونسخة انتهت نافذتها «منتهية» حتى قبل أن
    يُحدَّث حقل حالتها في التفعيل التالي (`effective_state`).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        ACTIVE = "active", "نشطة"
        RETIRED = "retired", "منتهية"

    version = models.PositiveIntegerField(unique=True, verbose_name="رقم النسخة")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="الحالة",
    )
    plan = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="نطاق الخطة",
        help_text="فارغ = نسخة عامة لكل الخطط؛ اسم خطة = نسخة خاصة بها تغلب العامة.",
    )
    billing_tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="platform_subscription_policies",
        verbose_name="شركة فوترة المنصة",
    )
    monthly_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("300.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="الرسم الشهري الافتراضي",
    )
    included_quota = models.PositiveIntegerField(
        default=300,
        verbose_name="الحصة الافتراضية المشمولة",
    )
    trial_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MaxValueValidator(MAX_SERVICE_TRIAL_DAYS)],
        verbose_name="أيام التجربة الافتراضية",
    )
    overage_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="سعر العملية الزائدة الافتراضي",
    )
    fixed_fee_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="صنف الرسم الشهري",
        help_text="صنف خدمي في شركة فوترة المنصة؛ إلزامي لحظة التفعيل.",
    )
    overage_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="صنف العمليات الزائدة",
        help_text="صنف خدمي في شركة فوترة المنصة؛ إلزامي عند سعر تجاوز أكبر من صفر.",
    )
    activation_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="سبب التفعيل",
        help_text="إلزامي لحظة تفعيل المسودة؛ يبقى في الصف بعد التفعيل.",
    )
    effective_from = models.DateTimeField(null=True, blank=True, verbose_name="سريان النسخة من")
    effective_to = models.DateTimeField(null=True, blank=True, verbose_name="سريان النسخة إلى")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_platform_subscription_policies",
        verbose_name="أنشأها",
    )
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activated_platform_subscription_policies",
        verbose_name="فعّلها",
    )
    activated_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التفعيل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        ordering = ["-version"]
        verbose_name = "سياسة اشتراك خدمة المنصة"
        verbose_name_plural = "سياسات اشتراك خدمة المنصة"

    def __str__(self):
        return f"سياسة الاشتراك v{self.version} ({self.get_status_display()})"

    def effective_state(self, at=None) -> str:
        """draft / scheduled / current / retired — من نافذة السريان لا من حقل الحالة وحده."""
        if self.status == self.Status.DRAFT:
            return "draft"
        if self.status == self.Status.RETIRED:
            return "retired"
        moment = at or timezone.now()
        if self.effective_from and self.effective_from > moment:
            return "scheduled"
        if self.effective_to and self.effective_to <= moment:
            return "retired"
        return "current"


class ServiceSubscription(models.Model):
    """اشتراك الشركة في خدمة المتابعة والإدخال.

    صف الخدمة لكل شركة داخل الوحدة، وهو البوابة الوحيدة لإسناد موظف منصة للشركة.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "تجربة"
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
    trial_days = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(MAX_SERVICE_TRIAL_DAYS)],
        verbose_name="أيام التجربة الملتقطة",
    )
    trial_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="بداية التجربة",
    )
    trial_ends_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="نهاية التجربة",
    )
    billing_tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="platform_service_billing_subscriptions",
        verbose_name="شركة فوترة المنصة الملتقطة",
    )
    billing_customer = models.ForeignKey(
        "partners.Partner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_service_subscriptions",
        verbose_name="عميل الفوترة في شركة المنصة",
        help_text="سجل العميل التابع لشركة المنصة المفوترة الذي تصدر باسمه فواتير الخدمة",
    )
    subscription_policy_version = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="نسخة سياسة الاشتراك الملتقطة",
    )
    fixed_fee_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="صنف الرسم الشهري الملتقط",
        help_text="يُلتقط من السياسة لحظة بدء التجربة أو التفعيل؛ الفوترة الشهرية تقرؤه ما لم يُمرَّر تجاوز صريح.",
    )
    overage_product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="صنف العمليات الزائدة الملتقط",
    )
    pre_suspension_status = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="الحالة قبل التعليق",
        help_text="تحفظ لحظة التعليق كي يعيدها الاستئناف؛ لا تُقرأ إلا من خدمة الاستئناف.",
    )
    scheduled_cancellation_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإلغاء المجدول",
        help_text="نهاية الدورة أو التجربة الحالية؛ يُطبَّق تلقائياً بأمر الفوترة الشهري.",
    )
    cancellation_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="سبب الإلغاء",
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


class ServiceSubscriptionEvent(models.Model):
    """سجل تدقيق غير قابل للمحو لكل انتقال أو تعديل تجاري على اشتراك الخدمة.

    لا مسار تعديل أو حذف عليه عمداً — الصفّ يُكتب مرة واحدة داخل نفس معاملة
    الانتقال ولا يُعاد لمسه. `subscription` بحماية `PROTECT` كي لا يُحذف
    الاشتراك فيسقط تاريخه، و`actor` بـ`SET_NULL` لأن هوية الفاعل معلومة ثانوية
    لا تبرر منع حذف حساب مستخدم قديم. `details` حقل JSON بلا PII ولا أسرار.
    """

    class Action(models.TextChoices):
        TRIAL_STARTED = "trial_started", "بدء تجربة"
        ACTIVATED = "activated", "تفعيل مدفوع"
        TRIAL_CONVERTED = "trial_converted", "تحويل التجربة إلى مدفوع"
        SETTINGS_UPDATED = "settings_updated", "تعديل إعدادات تجارية"
        SUSPENDED = "suspended", "تعليق"
        RESUMED = "resumed", "استئناف"
        CANCELLATION_SCHEDULED = "cancellation_scheduled", "جدولة إلغاء"
        CANCELLATION_WITHDRAWN = "cancellation_withdrawn", "سحب جدولة الإلغاء"
        CANCELLED = "cancelled", "إلغاء"

    subscription = models.ForeignKey(
        ServiceSubscription,
        on_delete=models.PROTECT,
        related_name="events",
        verbose_name="اشتراك الخدمة",
    )
    action = models.CharField(max_length=30, choices=Action.choices, verbose_name="الإجراء")
    from_status = models.CharField(max_length=20, blank=True, default="", verbose_name="من حالة")
    to_status = models.CharField(max_length=20, blank=True, default="", verbose_name="إلى حالة")
    reason = models.CharField(max_length=500, blank=True, default="", verbose_name="السبب")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_subscription_events",
        verbose_name="الفاعل",
    )
    correlation_id = models.CharField(max_length=64, blank=True, default="", verbose_name="معرّف الارتباط")
    details = models.JSONField(default=dict, blank=True, verbose_name="تفاصيل بلا بيانات شخصية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "حدث اشتراك خدمة المنصة"
        verbose_name_plural = "أحداث اشتراك خدمة المنصة"
        indexes = [
            models.Index(fields=["subscription", "-created_at"]),
            models.Index(fields=["correlation_id"]),
        ]

    def __str__(self):
        return f"{self.subscription_id}: {self.get_action_display()}"


class ServiceSubscriptionPolicyEvent(models.Model):
    """سجل تدقيق غير قابل للمحو لكل كتابة على نسخ سياسة الاشتراك (§١١).

    على مستوى المنصة بلا `tenant` — كالسياسة نفسها. `policy` بـ`PROTECT` كي لا
    تُحذف نسخةٌ فيسقط تاريخها، و`details` تحمل قبل/بعد للتعديل بلا بيانات شخصية.
    """

    class Action(models.TextChoices):
        CREATED = "created", "إنشاء مسودة"
        UPDATED = "updated", "تعديل مسودة"
        CLONED = "cloned", "استنساخ مسودة"
        ACTIVATED = "activated", "تفعيل سياسة"
        RETIRED = "retired", "إنهاء سياسة"

    policy = models.ForeignKey(
        ServiceSubscriptionPolicy,
        on_delete=models.PROTECT,
        related_name="events",
        verbose_name="سياسة الاشتراك",
    )
    action = models.CharField(max_length=20, choices=Action.choices, verbose_name="الإجراء")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_subscription_policy_events",
        verbose_name="الفاعل",
    )
    correlation_id = models.CharField(max_length=64, blank=True, default="", verbose_name="معرّف الارتباط")
    details = models.JSONField(default=dict, blank=True, verbose_name="تفاصيل بلا بيانات شخصية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "حدث سياسة اشتراك خدمة المنصة"
        verbose_name_plural = "أحداث سياسات اشتراك خدمة المنصة"
        indexes = [
            models.Index(fields=["policy", "-created_at"]),
            models.Index(fields=["correlation_id"]),
        ]

    def __str__(self):
        return f"{self.policy_id}: {self.get_action_display()}"


class SubscriptionBillingRecord(models.Model):
    """سجل تدقيق وفوترة دورة اشتراك الخدمة الشهرية (المرحلة 8A).

    - يربط دورة فوترة اشتراك الخدمة بفاتورة المبيعات الصادرة في شركة المنصة.
    - يحفظ لقطة مجمدة من الكميات والأسعار والإجمالي وقت الفوترة.
    - يفرض عدم التكرار (idempotency) على مستوى قاعدة البيانات عبر قيد فريد
      على (subscription, period_start, period_end).
    - ليس دفتراً ثانياً ولا يُنشئ قيوداً محاسبية بنفسه، بل يربط الفاتورة الحقيقية.
    - يُشتق نطاق الشركة من اشتراك الخدمة (subscription.tenant) لشركة الزبون،
      ومن الفاتورة (invoice.tenant) لشركة المنصة المفوترة.
    """

    subscription = models.ForeignKey(
        ServiceSubscription,
        on_delete=models.CASCADE,
        related_name="billing_records",
        verbose_name="اشتراك الخدمة",
    )
    period_start = models.DateField(
        verbose_name="بداية دورة الفوترة",
    )
    period_end = models.DateField(
        verbose_name="نهاية دورة الفوترة",
    )
    invoice = models.ForeignKey(
        "sales.SalesInvoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subscription_billing_records",
        verbose_name="فاتورة المبيعات",
    )
    monthly_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="الرسم الشهري الثابت",
    )
    included_quota = models.PositiveIntegerField(
        default=0,
        verbose_name="العمليات المشمولة",
    )
    consumed_quota = models.PositiveIntegerField(
        default=0,
        verbose_name="العمليات المستهلكة",
    )
    overage_units = models.PositiveIntegerField(
        default=0,
        verbose_name="العمليات الزائدة",
    )
    overage_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="سعر العملية الزائدة",
    )
    overage_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="رسوم العمليات الزائدة",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="إجمالي الفاتورة",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
    )

    class Meta:
        verbose_name = "سجل فوترة اشتراك"
        verbose_name_plural = "سجلات فوترة الاشتراكات"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "period_start", "period_end"],
                name="platform_ops_sub_billing_sub_period_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.subscription} ({self.period_start} -> {self.period_end}) -> {self.total_amount}"


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
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت الإلغاء",
        help_text=(
            "طابعُ حدثٍ ثابت. ومعدّلُ إعادة العمل كان يُنسَب للشهر عبر `updated_at` وهو "
            "`auto_now`: لمسةٌ لاحقةٌ للصفّ تنقله بين الشهور فيتغيّر رقمُ شهرٍ التُقط."
        ),
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


class PolicyProfile(models.Model):
    """ملف سياسة أداء تخصص عمليات المنصة (المرحلة الخامسة: م٥).

    - صف لكل تخصص (PlatformEmployee.specialty) يحمل أوزان المحاور وأهدافها.
    - لا أوزان لكل موظف على حدة؛ السياسة على مستوى التخصص المنصي.
    - التعديل اللاحق لا يغير لقطات الأشهر السابقة الملتقطة في PerformanceSnapshot.
    - التخصص فريد على مستوى المنصة (unique=True).
    """

    specialty = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name="التخصص",
        help_text="تخصص موظفي المنصة المطبق عليه هذا الملف التعريفي",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="تسمية السياسة",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="الوصف",
    )
    weights = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="أوزان محاور التقييم",
        help_text=(
            "أوزان المحاور الرسمية الخمسة: kpi_results, quality, customer_rating, "
            "sla_compliance, attendance_regularity. المحور غير المنطبق يُسقط ويُعاد "
            "توزيع وزنه بالتناسب، فلا يلزم أن يجمع المكتوب هنا مئةً بالضبط."
        ),
    )
    targets = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="مستهدفات المقاييس",
        help_text="المستهدفات الرقمية للمقاييس (مثل مستهدف السعة، مستهدف المبيعات، إلخ)",
    )
    sla_hours_by_kind = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="ساعات الأجل حسب نوع أمر العمل",
        help_text="خريطة ساعات الأجل الافتراضية لكل نوع أمر عمل",
    )
    min_sample_size = models.PositiveIntegerField(
        default=5,
        verbose_name="الحد الأدنى لحجم العينة",
        help_text="الحد الأدنى لحجم العينة لتوليد درجة مركبة وترتيب رسمي",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط",
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
        verbose_name = "ملف سياسة الأداء"
        verbose_name_plural = "ملفات سياسات الأداء"

    def __str__(self):
        return f"سياسة {self.specialty} ({self.name or 'افتراضية'})"


class PerformanceSnapshot(models.Model):
    """لقطة أداء شهرية لموظف المنصة (المرحلة الخامسة: م٥).

    - لقطة شهرية مجمدة تُحفظ بالأوزان والمستهدفات السارية وقتها (policy_snapshot).
    - تعديل PolicyProfile لاحقاً لا يغير شهراً ملتقطاً.
    - التقاطها دالة خدمة idempotent: تشغيلها مرتين لنفس الموظف والشهر لا ينتج لقطتين ولا يضاعف أثراً.
    - فرادة غير مشروطة لكل (employee, period_year, period_month) تفرضها MySQL.
    """

    class Status(models.TextChoices):
        CALCULATED = "calculated", "محسوبة"
        INSUFFICIENT_DATA = "insufficient_data", "بيانات غير كافية"

    employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.CASCADE,
        related_name="performance_snapshots",
        verbose_name="موظف العمليات",
    )
    period_year = models.PositiveSmallIntegerField(
        verbose_name="سنة التقييم",
    )
    period_month = models.PositiveSmallIntegerField(
        verbose_name="شهر التقييم",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.CALCULATED,
        verbose_name="حالة اللقطة",
    )
    composite_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="الدرجة المركبة",
        help_text="الدرجة المركبة الرسمية من 100؛ تكون NULL إذا كانت البيانات غير كافية",
    )
    sample_size = models.PositiveIntegerField(
        default=0,
        verbose_name="حجم العينة الفعلي",
        help_text="عدد أوامر العمل المعتمدة الداخلة في التقييم",
    )
    policy_profile = models.ForeignKey(
        PolicyProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshots",
        verbose_name="ملف السياسة المعتمد",
    )
    policy_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="لقطة السياسة والأوزان",
        help_text="لقطة مجمدة من أوزان المحاور ومستهدفاتها السارية وقت الالتقاط",
    )
    metrics_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="بيانات المقاييس الستة ومقاماتها",
        help_text="تفاصيل المقاييس الستة مع البسط والمقام المعلن وحجم العينة",
    )
    axes_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="بيانات المحاور وتوزيع الأوزان",
        help_text="تفاصيل المحاور ودرجاتها وأوزانها بعد إعادة التوزيع",
    )
    rework_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="معدل إعادة العمل",
        help_text="نسبة أوامر العمل الملغاة كرقم تشخيصي منفصل لا يُخصم من الدرجة المركبة",
    )
    processed_sales_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="قيمة مبيعات عالجها",
        help_text="مجموع مبيعات أوامر العمل المعتمدة كمؤشر عرض لا استحقاق",
    )
    captured_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="وقت الالتقاط",
    )
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="ملتقط التقرير",
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
        verbose_name = "لقطة أداء موظف المنصة"
        verbose_name_plural = "لقطات أداء موظفي المنصة"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "period_year", "period_month"],
                name="platform_ops_perfsnapshot_employee_period_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["employee", "period_year", "period_month"]),
            models.Index(fields=["period_year", "period_month"]),
        ]

    def __str__(self):
        score_str = f"{self.composite_score}%" if self.composite_score is not None else self.get_status_display()
        return f"لقطة {self.employee} ({self.period_year}/{self.period_month}): {score_str}"


class PlatformNotification(models.Model):
    """إشعار منصي لموظف أو مدير عمليات المنصة (المرحلة السادسة: م٦).

    - الفلترة على الخادم حصراً: المستخدم لا يستقبل إلا إشعاراته.
    - أنواع مغلقة: تجاوز أجل (sla_breach)، تقييم منخفض (low_score)، تجاوز باقة (quota_exceeded).
    """

    class NotificationType(models.TextChoices):
        SLA_BREACH = "sla_breach", "تجاوز أجل"
        LOW_SCORE = "low_score", "تقييم منخفض"
        QUOTA_EXCEEDED = "quota_exceeded", "تجاوز باقة"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_notifications",
        verbose_name="المستلم",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="platform_notifications",
        verbose_name="الشركة",
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        verbose_name="نوع الإشعار",
    )
    title = models.CharField(
        max_length=255,
        verbose_name="العنوان",
    )
    message = models.TextField(
        verbose_name="نص الإشعار",
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="مقروء",
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="وقت القراءة",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="بيانات إضافية",
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
        verbose_name = "إشعار عمليات المنصة"
        verbose_name_plural = "إشعارات عمليات المنصة"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title} ({self.recipient})"


class PlatformActivityLog(models.Model):
    """سجل نشاط موظف المنصة عابراً كل الشركات في جدول واحد (القصة رقم ١٣ - م٦).

    - بنية خاصة بوحدة عمليات المنصة وليست توسيعاً لـ ActivityLog؛
      لأن ActivityLog لا يتسع لحدث بلا شركة وفهارسه تبدأ بـ tenant.
    - مفهرس زمنياً للقراءة العابرة للشركات: (employee, -created_at) و(-created_at).
    """

    class Action(models.TextChoices):
        WORK_ORDER_TRANSITION = "work_order_transition", "تغيير حالة أمر العمل"
        DELIVERABLE_SUBMIT = "deliverable_submit", "تقديم مُسلَّم"
        DELIVERABLE_REVIEW = "deliverable_review", "مراجعة مُسلَّم"
        COMMENT_ADDED = "comment_added", "إضافة تعليق"
        ENGAGEMENT_ASSIGNED = "engagement_assigned", "إسناد ارتباط"
        ENGAGEMENT_SUSPENDED = "engagement_suspended", "تعليق ارتباط"
        ENGAGEMENT_REVOKED = "engagement_revoked", "إلغاء ارتباط"
        SNAPSHOT_CAPTURED = "snapshot_captured", "التقاط لقطة أداء"
        OTHER = "other", "أخرى"

    employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.CASCADE,
        related_name="activity_logs",
        verbose_name="موظف العمليات",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_activity_logs",
        verbose_name="الشركة",
    )
    action = models.CharField(
        max_length=50,
        choices=Action.choices,
        verbose_name="نوع النشاط",
    )
    entity_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="نوع الكيان",
    )
    entity_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="معرف الكيان",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="وصف النشاط",
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="تفاصيل إضافية",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="تاريخ ووقت النشاط",
    )

    class Meta:
        verbose_name = "سجل نشاط عمليات المنصة"
        verbose_name_plural = "سجلات أنشطة عمليات المنصة"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        tenant_str = f" [{self.tenant}]" if self.tenant else " [منصة]"
        return f"{self.employee}: {self.get_action_display()}{tenant_str} - {self.description[:40]}"


class DailyRating(models.Model):
    """التقييم اليومي لأداء موظف المنصة في شركة معينة (المرحلة السابعة: م٧).

    المفتاح المنطقي الصارم: (tenant, employee, service_date).
    - service_date: حقل تاريخ صريح (DateField) لا مشتق من وقت، لتجنب مشاكل المناطق الزمنية على MySQL.
    - stars: من 1 إلى 5 نجوم.
    - edited_once: يسمح بالتعديل مرة واحدة فقط، والمحاولة الثانية تُرفض.
    - الفرادة غير مشروطة تفرضها قاعدة البيانات بقيد UniqueConstraint.
    """

    class Source(models.TextChoices):
        TOKEN = "token", "رابط يومي"
        IN_APP = "in_app", "داخل التطبيق"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="daily_ratings",
        verbose_name="الشركة",
    )
    employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.CASCADE,
        related_name="daily_ratings",
        verbose_name="موظف العمليات",
    )
    service_date = models.DateField(
        db_index=True,
        verbose_name="تاريخ الخدمة",
        help_text="حقل تاريخ صريح ليوم العمل المُقيَّم",
    )
    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="التقييم بالنجوم",
        help_text="من 1 إلى 5 نجوم",
    )
    note = models.TextField(
        blank=True,
        default="",
        verbose_name="ملاحظة التقييم",
    )
    edited_once = models.BooleanField(
        default=False,
        verbose_name="عُدّل مرة واحدة",
        help_text="يسمح بالتعديل مرة واحدة فقط وتُرفض المحاولة الثانية",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.IN_APP,
        verbose_name="مصدر التقييم",
    )
    rated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="المقيِّم",
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
        verbose_name = "تقييم يومي"
        verbose_name_plural = "تقييمات يومية"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee", "service_date"],
                name="platform_ops_dailyrating_tenant_employee_date_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "service_date"]),
            models.Index(fields=["employee", "service_date"]),
        ]

    def __str__(self):
        return f"{self.tenant} - {self.employee} ({self.service_date}): {self.stars}★"


class DailyRatingToken(models.Model):
    """الرابط اليومي المهشر للتقييم العام بلا تسجيل دخول (المرحلة السابعة: م٧).

    - الرمز الخام لا يُحفظ في القاعدة إطلاقاً، بل يُخزن مهشراً (SHA-256) كنمط docshare وIntegrationKey.
    - الرابط صالح لمدة 72 ساعة من لحظة التوليد.
    - انتهاء الصلاحية يُرد بحالة 410 Gone صريحة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="daily_rating_tokens",
        verbose_name="الشركة",
    )
    employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.CASCADE,
        related_name="daily_rating_tokens",
        verbose_name="موظف العمليات",
    )
    service_date = models.DateField(
        db_index=True,
        verbose_name="تاريخ الخدمة",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="مهشر الرمز",
        help_text="تجزئة SHA-256 للرمز الخام؛ الرمز الأصلي لا يُحفظ في القاعدة أبداً",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name="تاريخ الانتهاء",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإبطال",
    )
    rating = models.ForeignKey(
        DailyRating,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tokens",
        verbose_name="التقييم المرتبط",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
    )

    class Meta:
        verbose_name = "رمز التقييم اليومي"
        verbose_name_plural = "رموز التقييم اليومي"
        indexes = [
            models.Index(fields=["tenant", "service_date"]),
            models.Index(fields=["employee", "service_date"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Token for {self.tenant} - {self.employee} ({self.service_date})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_live(self) -> bool:
        return not self.is_revoked and not self.is_expired


# ==============================================================================
# المرحلة الثامنة (م٨-ب): بوّابة التوظيف المنصّيّة
# ==============================================================================


class PlatformRecruiter(models.Model):
    """مسؤول توظيف في المنصة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

    استثناء موثَّق من قاعدة وجود مفتاح الشركة (tenant FK)؛ فمسؤول التوظيف يتبع المنصة نفسها.
    يفتح صلاحيات التوظيف وحدها بلا بقية صلاحيات عمليات المنصة ولا IsPlatformAdmin.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_recruiter",
        verbose_name="المستخدم",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط",
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
        verbose_name = "مسؤول توظيف المنصة"
        verbose_name_plural = "مسؤولو توظيف المنصة"

    def __str__(self):
        return f"Recruiter: {self.user} ({'نشط' if self.is_active else 'معطل'})"


class JobPosting(models.Model):
    """إعلان وظيفة منصي (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

    استثناء موثَّق من قاعدة وجود مفتاح الشركة (tenant FK) بقرار #207؛
    الوظائف والمتقدمون يتبعون المنصة نفسها لا شركة زبون.
    الرابط العام مبني بمفتاح عشوائي غير قابل للتخمين (token_urlsafe).
    """

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "دوام كامل"
        PART_TIME = "part_time", "دوام جزئي"
        CONTRACT = "contract", "عقد"
        TEMPORARY = "temporary", "مؤقت"

    title = models.CharField(
        max_length=200,
        verbose_name="عنوان الوظيفة",
    )
    #: التخصّصُ المنصّيُّ الذي تُوظّف له — **لا عنوانُ الإعلان**.
    #: يُنسخ إلى `PlatformEmployee.specialty` عند قبول الدعوة، وعليه تُبنى مطابقةُ
    #: `PolicyProfile.specialty` في احتساب الأداء. ولذلك طولُه طولُ العمود الهدف
    #: (١٠٠) لا طولَ العنوان (٢٠٠): عنوانٌ حرٌّ في عمودٍ أقصرَ يُخطئ على MySQL
    #: ويُبتَر صامتاً على SQLite.
    specialty = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="التخصص المنصي",
        help_text="يجب أن يطابق تخصصاً في ملفات السياسة (PolicyProfile.specialty) ليُحتسب الأداء بسياسته",
    )
    description = models.TextField(
        verbose_name="وصف الوظيفة",
    )
    requirements = models.TextField(
        blank=True,
        default="",
        verbose_name="المتطلبات",
    )
    location = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="المكان",
    )
    employment_type = models.CharField(
        max_length=30,
        choices=EmploymentType.choices,
        blank=True,
        default="",
        verbose_name="نوع الدوام",
    )
    salary_range = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="نطاق الراتب",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="مفتاح الرابط العام",
    )
    is_open = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="مفتوحة للتقديم",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="تاريخ انتهاء الرابط",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإغلاق",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="مُنشئ الإعلان",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإنشاء",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاريخ التحديث",
    )

    class Meta:
        verbose_name = "إعلان وظيفة منصي"
        verbose_name_plural = "إعلانات الوظائف المنصية"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["is_open", "-created_at"]),
        ]

    def __str__(self):
        return self.title

    def is_live(self, now=None) -> bool:
        if not self.is_open:
            return False
        if self.expires_at is None:
            return True
        return self.expires_at > (now or timezone.now())


class JobApplicant(models.Model):
    """متقدم على وظيفة منصية (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

    استثناء موثَّق من قاعدة وجود مفتاح الشركة (tenant FK) بقرار #207.
    مُدخل المجهول محجور بحالة 'new' ولا يمس شيئاً آخر.
    رابط السيرة cv_url محمي بالكامل ولا يُطبع في أي مُسلسِل.
    """

    class Status(models.TextChoices):
        NEW = "new", "جديد"
        SCREENING = "screening", "فرز أولي"
        INTERVIEW = "interview", "مقابلة"
        OFFERED = "offered", "عرض عمل"
        HIRED = "hired", "مقبول"
        REJECTED = "rejected", "مرفوض"

    job = models.ForeignKey(
        JobPosting,
        on_delete=models.CASCADE,
        related_name="applicants",
        verbose_name="الوظيفة",
    )
    name = models.CharField(
        max_length=200,
        verbose_name="اسم المتقدم",
    )
    phone = models.CharField(
        max_length=40,
        verbose_name="رقم التواصل",
    )
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name="البريد الإلكتروني",
    )
    about = models.TextField(
        blank=True,
        default="",
        verbose_name="نبذة عن المتقدم",
    )
    cv_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="رابط السيرة",
    )
    cv_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="اسم ملف السيرة",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
        verbose_name="الحالة",
    )
    rating = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="التقييم",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="ملاحظات مسؤول التوظيف",
    )
    reference_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name="رقم المرجع",
    )
    hired_employee = models.ForeignKey(
        PlatformEmployee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="سجل موظف المنصة",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ التقديم",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاريخ التحديث",
    )

    class Meta:
        verbose_name = "متقدم على وظيفة منصية"
        verbose_name_plural = "المتقدمون على الوظائف المنصية"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["job", "status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.job.title} ({self.get_status_display()})"


class JobApplicantInvitation(models.Model):
    """دعوة قبول التوظيف المنصية المهشرة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

    - الرمز الخام لا يُحفظ في القاعدة إطلاقاً، بل يُخزن مهشراً (SHA-256) كنمط docshare وDailyRatingToken.
    - رابط الدعوة يقود إلى صفحة ويب لا نقطة API.
    - حساب المقبول (User + PlatformEmployee) يُنشأ عند قبول الدعوة لا قبلها.
    - الرابط المستهلك أو المنتهي يرد بـ 410 Gone صريحة.
    """

    applicant = models.ForeignKey(
        JobApplicant,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name="المتقدم",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="مهشر الرمز",
        help_text="تجزئة SHA-256 للرمز الخام؛ الرمز الأصلي لا يُحفظ في القاعدة أبداً",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name="تاريخ الانتهاء",
    )
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ القبول",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإبطال",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="مُرسل الدعوة",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاريخ الإنشاء",
    )

    class Meta:
        verbose_name = "دعوة توظيف منصية"
        verbose_name_plural = "دعوات التوظيف المنصية"

    def __str__(self):
        return f"Invitation for {self.applicant.name} ({self.applicant.job.title})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_consumed(self) -> bool:
        return self.is_accepted or self.is_revoked or self.is_expired

    @property
    def is_live(self) -> bool:
        return not self.is_consumed

