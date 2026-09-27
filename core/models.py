from django.db import models
from tenants.models import Tenant

class SystemAttachment(models.Model):
    id = models.AutoField(primary_key=True, db_column='AttachmentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    related_table = models.CharField(max_length=50, db_column='RelatedTable')
    related_id = models.IntegerField(db_column='RelatedID')
    file_type = models.CharField(max_length=50, db_column='FileType', null=True, blank=True)
    file_path = models.CharField(max_length=500, db_column='FilePath')
    uploaded_at = models.DateTimeField(auto_now_add=True, db_column='UploadedAt')

    class Meta:
        db_table = 'system_attachments'
        # كان `managed = False` — النموذج الوحيد كذلك في المشروع (P0-14).
        # الأثر لم يكن نظرياً: جانغو يسجّل `core.0001_initial` مطبَّقةً ولا يُصدِر
        # CREATE TABLE لنموذج غير مُدار، فأي قاعدة مبنيّة من الهجرات تنفجر
        # بـ(1146) عند أول لمسة للجدول — والإنتاج نجا لأن جدوله أُنشئ يدوياً
        # خارج جانغو. وأسوأ من ذلك: مُكتشِف الهجرات **يتجاهل حقول** النماذج غير
        # المُدارة، فحقل `tenant` أعلاه عاش خارج الهجرة تماماً.
        managed = True


class ActivityLog(models.Model):
    """سجل نشاط موحّد عبر الموقع: مَن فعل ماذا على أي مستند + أحداث الجلسة.

    طبقة Shared/Core واحدة تُغذّي: سجل نشاط كل مستند (فاتورة/صفقة) + الصفحة العامة
    للمدير. أحداث «العرض/الفتح» تُعلَّم is_view=True لتُستبعد من الجدول العام وتبقى
    ظاهرة في تفصيل المستخدم. تُكتب عبر core.activity.log_activity فقط (غير حاظرة).
    """

    ACTIONS = [
        ('create', 'إنشاء'),
        ('update', 'تعديل'),
        ('delete', 'حذف'),
        ('post', 'ترحيل'),
        ('unpost', 'إلغاء ترحيل'),
        ('duplicate', 'نسخ'),
        ('payment', 'دفعة'),
        ('view', 'عرض'),
        ('login', 'تسجيل دخول'),
        ('logout', 'تسجيل خروج'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    user = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, db_column='UserID')
    action = models.CharField(max_length=20, choices=ACTIONS)
    # يفصل أحداث العرض عن التعديلات — الجدول العام يفلتر is_view=False.
    is_view = models.BooleanField(default=False, db_index=True)
    entity_type = models.CharField(max_length=40)
    entity_id = models.IntegerField(null=True, blank=True)
    entity_label = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=64, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'activity_logs'
        managed = True
        indexes = [
            models.Index(fields=['tenant', '-timestamp'], name='act_tenant_ts_idx'),
            models.Index(fields=['tenant', 'user', '-timestamp'], name='act_tenant_user_ts_idx'),
            models.Index(fields=['tenant', 'entity_type', 'entity_id'], name='act_tenant_entity_idx'),
        ]

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id} by {self.user_id}"


class TenantModule(models.Model):
    """ترخيص وحدة اختيارية لشركة بعينها؛ غياب الصف يعني أن الوحدة معطّلة."""

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="module_licenses",
        db_column="TenantID",
    )
    module_key = models.CharField(max_length=40, db_column="ModuleKey")
    enabled = models.BooleanField(default=False, db_column="Enabled")
    enabled_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enabled_tenant_modules",
        db_column="EnabledBy_UserID",
    )
    enabled_at = models.DateTimeField(null=True, blank=True, db_column="EnabledAt")
    plan_note = models.CharField(
        max_length=120,
        blank=True,
        default="",
        db_column="PlanNote",
    )

    class Meta:
        db_table = "tenant_modules"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "module_key"],
                name="uniq_tenant_module",
            ),
        ]

    def __str__(self):
        return f"{self.tenant_id}:{self.module_key}={self.enabled}"


class TenantLimit(models.Model):
    """T-PLANLIMITS: تجاوز حدّ خطة لشركة بعينها.

    الافتراضات في `core.plans.PLAN_DEFAULTS`؛ هذا الجدول يحمل **الفروق فقط** كما
    يضبطها سوبر أدمن المنصة. غياب السطر = «كما تقول الخطة»، فالاستعادة حذف.
    `max_value = NULL` تجاوزٌ صريح بمعنى **بلا حدّ** — لا «غير مضبوط».
    """

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="plan_limits",
        db_column="TenantID",
    )
    limit_key = models.CharField(max_length=40, db_column="LimitKey")
    max_value = models.PositiveIntegerField(
        null=True, blank=True, db_column="MaxValue",
        help_text="NULL = بلا حدّ لهذه الشركة",
    )
    note = models.CharField(max_length=120, blank=True, default="", db_column="Note")
    updated_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_tenant_limits",
        db_column="UpdatedBy_UserID",
    )
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")

    class Meta:
        db_table = "tenant_limits"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "limit_key"],
                name="uniq_tenant_limit",
            ),
        ]

    def __str__(self):
        value = "بلا حدّ" if self.max_value is None else self.max_value
        return f"{self.tenant_id}:{self.limit_key}={value}"


class PlanPricing(models.Model):
    """T-PLANPRICE: تجاوز سعر خطةٍ عن افتراض `core.plans.PLAN_PRICING_DEFAULTS`.

    نفس نمط `TenantLimit` تماماً لكن على مستوى الخطة لا الشركة (كل مشتركي خطةٍ
    يدفعون سعراً واحداً): الافتراضات في الكود، وهذا الجدول يحمل **الفروق فقط**
    كما يضبطها سوبر أدمن المنصة. غياب السطر = «كما يقول الكود»، فحذفُه استعادةٌ
    للسعر الافتراضي الحالي — لا تصفير، ولا تجميد سعرٍ قديم حين يتغيّر الافتراض.
    """

    id = models.AutoField(primary_key=True)
    plan_key = models.CharField(max_length=40, db_column="PlanKey")
    monthly_price = models.DecimalField(
        max_digits=10, decimal_places=2, db_column="MonthlyPrice",
    )
    note = models.CharField(max_length=120, blank=True, default="", db_column="Note")
    updated_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_plan_pricing",
        db_column="UpdatedBy_UserID",
    )
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")

    class Meta:
        db_table = "plan_pricing"
        constraints = [
            models.UniqueConstraint(fields=["plan_key"], name="uniq_plan_pricing_key"),
        ]

    def __str__(self):
        return f"{self.plan_key}={self.monthly_price}"


class AssistantLesson(models.Model):
    """درس سلوكي عام يتعلّمه المساعد الذكي من تصحيح إنسان له أثناء محادثة.

    عمداً **بلا** حقل شركة (Tenant) — هذا الجدول لقواعد سلوك/SQL عامة تنطبق
    على كل الشركات (مثل «لا تفترض عمود X»)، وليس لحقائق أو أرقام خاصة بشركة
    معيّنة؛ البرومبت يوجّه النموذج صراحةً لعدم كتابة بيانات شركة هنا.

    `is_active=False` افتراضياً: يُلتقَط الدرس تلقائياً عند تصحيح واضح من
    مستخدم، لكن لا يُحقَن في تعليمات النموذج (lessons_text) إلا بعد مراجعة
    وتفعيل يدوي من /admin/ — يمنع درساً واحداً خاطئاً/مسيئاً من التأثير فوراً
    على كل محادثات كل الشركات.
    """

    id = models.AutoField(primary_key=True)
    text = models.CharField(max_length=500)
    is_active = models.BooleanField(default=False, db_index=True)
    # سياق تتبّع فقط (مفتاح الجلسة الذي وُلد منه الدرس) — ليس بيانات شركة.
    source = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assistant_lessons'
        managed = True
        ordering = ['-created_at']

    def __str__(self):
        return self.text[:80]


class DevelopmentNote(models.Model):
    """ملاحظة تطوير منصّية عالمية لا تتبع شركة بعينها."""

    STATUS_CHOICES = [
        ('todo', 'قيد الانتظار'),
        ('in_progress', 'قيد التنفيذ'),
        ('done', 'مكتملة'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'منخفضة'),
        ('medium', 'متوسطة'),
        ('high', 'عالية'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    # صور توضيحية للملاحظة — روابط مستضافة (Cloudinary عبر /api/media/upload/)
    # لا محتوى ثنائي في القاعدة؛ نفس نمط `SupplierQuotation.attachments`.
    images = models.JSONField(
        default=list, blank=True,
        help_text='[{url,caption}] صور توضيحية مرفوعة للملاحظة',
    )
    due_date = models.DateField(null=True, blank=True)
    # لحظة الإنجاز — تُختم عند دخول الحالة `done` وتُمحى عند الخروج منها.
    # ليست `updated_at` (كل حفظة تحرّكها) ولا تُشتقّ من الحالة وحدها: «متى
    # أُنجزت» سؤالٌ لا تجيبه حالةٌ حاضرة.
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_development_notes',
    )
    updated_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_development_notes',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'development_notes'
        ordering = ['created_at', 'id']

    def __str__(self):
        return self.title


class DevelopmentNoteComment(models.Model):
    """ردّ على ملاحظة تطوير — نقاشٌ مؤرَّخ بجانب الملاحظة لا داخل وصفها."""

    note = models.ForeignKey(
        DevelopmentNote, on_delete=models.CASCADE, related_name='comments',
    )
    body = models.TextField()
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='development_note_comments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'development_note_comments'
        ordering = ['created_at', 'id']

    def __str__(self):
        return self.body[:80]


class TenantAsset(models.Model):
    """سجلّ البايتات: صفٌّ لكل ملف مرفوع عبر نقطة الاختناق، بمالكه وحجمه.

    استهلاك التخزين لكل شركة لم يكن موجوداً في أي مكان: الرفع يذهب إلى Cloudinary
    ويُحفظ **الرابط** فقط، متناثراً في عشرات الأعمدة، بلا شركة وبلا حجم. وCloudinary
    نفسه لا يعطي حجم مجلّد إلا بسرد موارده وجمعها تحت سقف معدّل — فالقياس يُكتب هنا
    **لحظة الرفع** من ردّ Cloudinary ذاته (يحمل `bytes` و`public_id`) بلا نداء
    إضافي واحد، ويُقرأ لاحقاً بـ`SUM(bytes) GROUP BY tenant` — استعلامٌ واحد مفهرس.

    `tenant = NULL` ليست ثغرة بل حالة صريحة: أصول المنصة نفسها (صور ملاحظات
    التطوير) ومستندات مكتب المحاسبة لا تتبع شركةً بعينها، فتظهر في «غير منسوب»
    بدل أن تُحمَّل ظلماً على شركةٍ لا تراها ولا تملك حذفها.

    `public_id` فريد لأنه هوية الأصل عند Cloudinary: الحذف من التطبيق يمحو الصفّ
    به، وأي استرجاع أثري (backfill) يتعرّف على ما سُجّل من قبل فلا يزدوج.
    """

    SOURCES = [('upload', 'رفع'), ('backfill', 'استرجاع أثري')]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='assets',
        db_column='TenantID',
    )
    # 191 = سقف فهرس utf8mb4 في MySQL؛ المعرّفات الحقيقية ٤٠–٨٠ محرفاً.
    public_id = models.CharField(max_length=191, unique=True)
    bytes = models.BigIntegerField(default=0)
    resource_type = models.CharField(max_length=20, blank=True, default='')
    folder = models.CharField(max_length=200, blank=True, default='')
    source = models.CharField(max_length=20, choices=SOURCES, default='upload')
    uploaded_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_assets',
        db_column='UploadedBy_UserID',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenant_assets'
        managed = True
        indexes = [
            models.Index(fields=['tenant', '-created_at'], name='asset_tenant_created_idx'),
        ]

    def __str__(self):
        return f"{self.tenant_id or 'platform'}:{self.public_id} ({self.bytes}B)"


class ActivityLogPartner(models.Model):
    """يربط حدث النشاط الواحد بكل الجهات المتأثرة دون نسخ الحدث."""

    id = models.AutoField(primary_key=True)
    activity = models.ForeignKey(
        ActivityLog, on_delete=models.CASCADE, related_name="partner_links",
        db_column="ActivityLogID",
    )
    partner = models.ForeignKey(
        "partners.Partner", on_delete=models.CASCADE, related_name="activity_links",
        db_column="PartnerID",
    )

    class Meta:
        db_table = "activity_log_partners"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "partner"], name="uniq_activity_log_partner",
            ),
        ]


class PlatformAuditLogQuerySet(models.QuerySet):
    """سجلّ التدقيق append-only: لا `update()` ولا `delete()` جماعيّاً عبر الـORM."""

    def update(self, **kwargs):
        raise PermissionError('سجلّ تدقيق المنصة لا يُعدَّل.')

    def delete(self):
        raise PermissionError('سجلّ تدقيق المنصة لا يُحذَف.')


class PlatformAuditLog(models.Model):
    """سجلّ تدقيق المنصة — كل فعلٍ إداريّ للسوبر أدمن وكل حدثٍ أمنيّ عابر للشركات.

    يسدّ فجوة `ActivityLog`/`AccountingAuditLog` اللذين يلزمهما `tenant`: منح
    السوبر أدمن وسحبه، وأسعار الخطط، ومحاولات الدخول الفاشلة لا شركة لها،
    فكانت تُكتب في `logger.info` وحده وتضيع مع ملفّ اللوغ. **append-only**:
    الحفظ الثاني والحذف يرفعان خطأ. يُكتب عبر `core.platform_audit` فقط.
    الشركة والمستخدم المستهدف مع نسخةٍ نصّية من اسميهما، فالسطر يبقى مقروءاً
    ولو تغيّر الاسم لاحقاً.
    """

    SEVERITIES = [
        ('info', 'معلومة'),
        ('warning', 'تنبيه'),
        ('high', 'خطورة عالية'),
    ]

    id = models.BigAutoField(primary_key=True)
    action = models.CharField(max_length=40, db_index=True)
    severity = models.CharField(max_length=10, choices=SEVERITIES, default='info', db_index=True)
    actor = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='platform_audit_actions', db_column='ActorID')
    actor_label = models.CharField(max_length=150, blank=True, default='')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='platform_audit_events', db_column='TenantID')
    tenant_label = models.CharField(max_length=200, blank=True, default='')
    target_user = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='platform_audit_targets', db_column='TargetUserID')
    target_label = models.CharField(max_length=200, blank=True, default='')
    reason = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=64, null=True, blank=True)
    trace_id = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = PlatformAuditLogQuerySet.as_manager()

    class Meta:
        db_table = 'platform_audit_logs'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['tenant', '-created_at'], name='paudit_tenant_ts_idx'),
            models.Index(fields=['action', '-created_at'], name='paudit_action_ts_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise PermissionError('سجلّ تدقيق المنصة لا يُعدَّل.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('سجلّ تدقيق المنصة لا يُحذَف.')

    def __str__(self):
        return f'{self.action} [{self.severity}] {self.created_at:%Y-%m-%d %H:%M}'


class SupportAccessGrant(models.Model):
    """إذن دخول فريق كترا (سوبر أدمن) إلى شركةٍ ليس عضواً فيها — SA-2.

    الدورة: `pending` (طلبٌ بسببٍ مكتوب) ← `active` بموافقة مالك الشركة أو مديرها
    (قد تُقصِّر المدة أو تُخفِّض النطاق) | `rejected`. والإذن الساري ينتهي بمرور
    `expires_at` أو بسحبه (`revoked`، من الشركة أو بخروج صاحبه). الطلب المعلّق
    يسقط بعد مهلة (`core/support_access.py` — `PENDING_TTL`). **الدخول الطارئ**
    (`is_emergency`) يولد `active` بلا موافقة، بسببٍ إلزاميٍّ ومدةٍ قصيرة، وتُبلَّغ
    الشركة فوراً. الإذن شخصيّ: لـ`requested_by` وحده، لا لكل سوبر أدمن.
    الإنفاذ في `core/tenant_utils.py` (`_validate_user_tenant_access`).
    """

    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_REJECTED = 'rejected'
    STATUS_REVOKED = 'revoked'
    STATUS_CANCELLED = 'cancelled'
    STATUSES = [
        (STATUS_PENDING, 'بانتظار موافقة الشركة'),
        (STATUS_ACTIVE, 'ساري'),
        (STATUS_REJECTED, 'مرفوض'),
        (STATUS_REVOKED, 'مسحوب'),
        (STATUS_CANCELLED, 'ملغى'),
    ]
    SCOPE_READ_ONLY = 'read_only'
    SCOPE_FULL = 'full'
    SCOPES = [
        (SCOPE_READ_ONLY, 'قراءة فقط'),
        (SCOPE_FULL, 'كامل (قراءة وتعديل)'),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='support_access_grants',
        db_column='TenantID')
    requested_by = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT, related_name='support_access_requests')
    reason = models.TextField()
    requested_scope = models.CharField(max_length=10, choices=SCOPES, default=SCOPE_READ_ONLY)
    requested_hours = models.PositiveSmallIntegerField()
    is_emergency = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_PENDING, db_index=True)
    scope = models.CharField(max_length=10, choices=SCOPES, blank=True, default='')
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    decided_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='support_access_decisions')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default='')
    revoked_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='support_access_revocations')
    revoked_at = models.DateTimeField(null=True, blank=True)
    first_used_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'support_access_grants'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(
                fields=['tenant', 'requested_by', 'status'], name='sagrant_lookup_idx'),
        ]

    def __str__(self):
        return f'SupportAccessGrant#{self.pk} tenant={self.tenant_id} {self.status}'
