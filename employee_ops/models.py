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

    #: الحالتان اللتان تُعرضان على الموظف؛ وما عداهما (`cancelled`/`expired`)
    #: يُقرأ **«لا دعوة»**. القاعدةُ هنا وحدها: كانت مكرّرةً في ثلاثة مواضع
    #: (استعلامُ القائمة · قراءةُ المفرد · كرتُ الموظف) — وقاعدةُ احتسابٍ في
    #: مواضعَ يجب أن تتفق هي فخٌّ معروفٌ في هذا المستودع.
    VISIBLE_STATUSES = ("pending", "accepted")

    class Meta:
        verbose_name = "دعوة موظف"
        verbose_name_plural = "دعوات الموظفين"
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"دعوة {self.employee_id} ({self.status})"


class Task(models.Model):
    """مهمة متابعة الموظفين — متعددة الإسناد وحالتها مشتقة من إسناداتها."""

    PRIORITY_LOW = "LOW"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_URGENT = "URGENT"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "منخفضة"),
        (PRIORITY_MEDIUM, "متوسطة"),
        (PRIORITY_HIGH, "مرتفعة"),
        (PRIORITY_URGENT, "عاجلة"),
    ]

    STATUS_NEW = "NEW"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_NEW, "جديدة"),
        (STATUS_ACCEPTED, "مقبولة"),
        (STATUS_IN_PROGRESS, "قيد التنفيذ"),
        (STATUS_WAITING_FOR_REVIEW, "بانتظار المراجعة"),
        (STATUS_COMPLETED, "مكتملة"),
        (STATUS_REJECTED, "مرفوضة"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_tasks",
    )
    title = models.CharField(max_length=255, verbose_name="عنوان المهمة")
    description = models.TextField(blank=True, default="", verbose_name="الوصف")
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        verbose_name="الأولوية",
    )
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        verbose_name="الحالة",
    )
    due_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الاستحقاق")
    category = models.CharField(max_length=100, blank=True, default="", verbose_name="التصنيف")
    tags = models.JSONField(default=list, blank=True, verbose_name="الوسوم")
    target_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="السعر المستهدف",
    )
    allowed_sites = models.JSONField(default=list, blank=True, verbose_name="المواقع المسموحة")
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="أنشئ بواسطة",
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاكتمال")
    extra = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    # فرادةٌ **لكلّ شركة** لا عالميّة: قيدٌ عالميٌّ على جدولٍ مُنطاقٍ بالشركة
    # يجعل استيراد شركةٍ يفشل بسبب صفٍّ في شركةٍ أخرى — تسريبُ وجودٍ في رسالة
    # خطأ. و`NULL` لا يتصادم في MySQL فالصفوفُ غير المهاجَرة بلا قيد.
    source_path = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default=None,
        verbose_name="مسار المصدر",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "مهمة"
        verbose_name_plural = "مهام متابعة الموظفين"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_path"], name="employee_ops_task_source_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "due_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class TaskAssignment(models.Model):
    """إسناد مهمة لموظف — لكل موظف حالته ومؤقته المستقل."""

    STATUS_NOT_STARTED = "not_started"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_SUBMITTED = "submitted"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, "لم تبدأ"),
        (STATUS_IN_PROGRESS, "قيد التنفيذ"),
        (STATUS_SUBMITTED, "تم التسليم"),
        (STATUS_COMPLETED, "مكتملة"),
        (STATUS_REJECTED, "مرفوضة"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_task_assignments",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="employee_ops_assignments",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NOT_STARTED,
        verbose_name="حالة الإسناد",
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ البدء")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الانتهاء")
    work_started_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت بدء جلسة العمل")
    total_work_seconds = models.PositiveIntegerField(default=0, verbose_name="إجمالي ثواني العمل")
    extra = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "إسناد مهمة"
        verbose_name_plural = "إسنادات المهام"
        constraints = [
            models.UniqueConstraint(fields=["task", "employee"], name="employee_ops_task_employee_unique"),
        ]
        indexes = [
            models.Index(fields=["tenant", "employee", "status"]),
        ]

    def __str__(self):
        return f"إسناد {self.task_id} -> موظف {self.employee_id} ({self.status})"


class TaskSubmission(models.Model):
    """تسليم المهمة من موظف مسند إليه."""

    DECISION_PENDING = "pending"
    DECISION_APPROVED_FULL = "approved_full"
    DECISION_APPROVED_PARTIAL = "approved_partial"
    DECISION_REJECTED = "rejected"

    DECISION_CHOICES = [
        (DECISION_PENDING, "قيد الانتظار"),
        (DECISION_APPROVED_FULL, "قبول كامل"),
        (DECISION_APPROVED_PARTIAL, "قبول جزئي"),
        (DECISION_REJECTED, "مرفوض"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_submissions",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="employee_ops_submissions",
    )
    body = models.TextField(blank=True, default="", verbose_name="نص التسليم")
    decision = models.CharField(
        max_length=20,
        choices=DECISION_CHOICES,
        default=DECISION_PENDING,
        verbose_name="قرار المراجعة",
    )
    reviewer = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="المراجع",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ المراجعة")
    reviewer_notes = models.TextField(blank=True, default="", verbose_name="ملاحظات المراجع")
    extra = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    # فرادةٌ **لكلّ شركة** لا عالميّة: قيدٌ عالميٌّ على جدولٍ مُنطاقٍ بالشركة
    # يجعل استيراد شركةٍ يفشل بسبب صفٍّ في شركةٍ أخرى — تسريبُ وجودٍ في رسالة
    # خطأ. و`NULL` لا يتصادم في MySQL فالصفوفُ غير المهاجَرة بلا قيد.
    source_path = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default=None,
        verbose_name="مسار المصدر",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "تسليم مهمة"
        verbose_name_plural = "تسليمات المهام"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_path"],
                name="employee_ops_submission_source_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "decision"]),
            models.Index(fields=["tenant", "employee"]),
        ]

    def __str__(self):
        return f"تسليم مهمة {self.task_id} من {self.employee_id} ({self.decision})"


class TaskSubmissionItem(models.Model):
    """بند بحث عن منتج في تسليم المهمة — اختياري."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_submission_items",
    )
    submission = models.ForeignKey(
        TaskSubmission,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product_link = models.TextField(blank=True, default="", verbose_name="رابط المنتج")
    product_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="سعر المنتج",
    )
    notes = models.TextField(blank=True, default="", verbose_name="ملاحظات")
    attachment_url = models.TextField(blank=True, default="", verbose_name="رابط المرفق")
    attachment_name = models.CharField(max_length=255, blank=True, default="", verbose_name="اسم المرفق")
    images = models.JSONField(default=list, blank=True, verbose_name="روابط الصور")
    position = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    extra = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "بند تسليم مهمة"
        verbose_name_plural = "بنود تسليمات المهام"
        ordering = ["position", "id"]

    def __str__(self):
        return f"بند {self.id} لتسليم {self.submission_id}"


class TaskSubmissionAttachment(models.Model):
    """مرفق تسليم المهمة (صورة، ملف)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_submission_attachments",
    )
    submission = models.ForeignKey(
        TaskSubmission,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    url = models.TextField(verbose_name="رابط المرفق")
    name = models.CharField(max_length=255, blank=True, default="", verbose_name="اسم المرفق")
    position = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "مرفق تسليم مهمة"
        verbose_name_plural = "مرفقات تسليمات المهام"
        ordering = ["position", "id"]

    def __str__(self):
        return f"مرفق {self.name or self.url} لتسليم {self.submission_id}"


class PointEntry(models.Model):
    """سجل نقاط الموظف — سجلٌّ يُضاف إليه لا صفٌّ يوميٌّ يُدهَس.

    يقبل السالب (للقيد المضاد عند الإلغاء أو التصحيح اليدوي).
    ملاحظة: هذا ليس حضورَ الدوام: `hr` فيه حضورٌ حقيقيّ بمفتاح `ess.self`.
    لا تلمسه ولا تخلط بينهما.
    """

    SOURCE_TASK_FULL = "task_full"
    SOURCE_TASK_PARTIAL = "task_partial"
    SOURCE_ATTENDANCE = "attendance"
    SOURCE_MANUAL = "manual"
    SOURCE_REVERSAL = "reversal"

    SOURCE_CHOICES = [
        (SOURCE_TASK_FULL, "مهمة كاملة"),
        (SOURCE_TASK_PARTIAL, "مهمة جزئية"),
        (SOURCE_ATTENDANCE, "حضور"),
        (SOURCE_MANUAL, "يدوي"),
        (SOURCE_REVERSAL, "إلغاء"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_points",
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="employee_ops_points",
    )
    points = models.IntegerField(verbose_name="النقاط")
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        verbose_name="المصدر",
    )
    awarded_on = models.DateField(verbose_name="تاريخ الاستحقاق")
    submission = models.ForeignKey(
        "TaskSubmission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="point_entries",
        verbose_name="التسليم المرتبط",
    )
    reverses = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversed_by",
        verbose_name="القيد المُلغى",
    )
    reason = models.TextField(blank=True, default="", verbose_name="السبب")
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="أنشئ بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    source_path = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default=None,
        verbose_name="مسار المصدر",
    )

    class Meta:
        verbose_name = "قيد نقاط"
        verbose_name_plural = "قيود النقاط"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_path"],
                name="employee_ops_point_source_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "awarded_on", "employee"]),
        ]

    def __str__(self):
        return f"نقاط {self.employee_id}: {self.points} ({self.source})"



class EmployeeNote(models.Model):
    """ملاحظةُ مديرٍ على موظف — **بكاتبٍ وتاريخٍ ونصّ**، وتتعدّد على الموظف الواحد.

    اليوم «ملاحظات الموظفين» حقلُ نصٍّ واحدٌ على سجلّ المستخدم يُدهَس بكلّ حفظ، بلا
    كاتبٍ ولا تاريخ — فملاحظةُ مديرٍ عن موظفٍ لا تصلح دليلاً على شيء. وحقلُ
    `hr.Employee.notes` القديم **لا يُلمس هنا**: قراءتُه مرّةً واحدةً وظيفةُ الهجرة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="employee_ops_notes",
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="employee_ops_notes",
    )
    body = models.TextField(verbose_name="نص الملاحظة")
    # الكاتبُ قد يُحذف حسابُه وتبقى ملاحظتُه — نصُّها دليلٌ ولو غاب قائلُه.
    author = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="الكاتب",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")
    source_path = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default=None,
        verbose_name="مسار المصدر",
    )

    class Meta:
        verbose_name = "ملاحظة على موظف"
        verbose_name_plural = "ملاحظات الموظفين"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_path"],
                name="employee_ops_note_source_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "employee", "-created_at"]),
        ]

    def __str__(self):
        return f"ملاحظة على {self.employee_id}"
