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
