"""نواةُ CRM كترا الخلفيّة — زبائنُ كترا المحتمَلون (محلّات) قبل أن يصيروا شركاتٍ
على المنصّة.

**كلُّ نماذج هذا الملفّ بلا `tenant` عمداً** — استثناءٌ موثَّقٌ ومحروسٌ
(`crm/tests/test_crm_isolation_guard.py`)، بنفس حجّة `JobPosting`/`PlatformMeeting`
في `platform_ops`: الزبونُ المحتمَل زبونُ **كترا** نفسِها لا زبونُ شركةٍ على
المنصّة، فلا معنى لعزله بشركة.

`assigned_to`/`suggested_by` تشيران إلى `platform_ops.PlatformEmployee`
بـ**مرجعٍ نصّيّ** (`"platform_ops.PlatformEmployee"`) — وهذا أسلوبُ جانغو المعتاد
في تعريف مفتاحٍ أجنبيٍّ عبر التطبيقات، نفسُ النمط الموثَّق في `ARCHITECTURE.md`
لمرجع `partners.Partner.managed_tenant` إلى
`accountant_portal.AccountantEngagement`. وهو **ليس** تحايلاً على حارس العزل:
`crm` عضوٌ معلَنٌ في `PLATFORM_CLUSTER_APPS`
(`platform_ops/tests/test_isolation_guard.py`)، فاستيرادُ `platform_ops` صريحٌ
ومسموحٌ في هذه الوحدة — والمفتاحُ الأجنبيُّ هنا يجعل الاعتمادَ قائماً في القاعدة
أصلاً، فحجبُه بسطرٍ كان سيجعله غيرَ معلَنٍ لا غيرَ موجود.
"""
from django.conf import settings
from django.db import models

from tenants.models import Tenant


class LeadImportBatch(models.Model):
    """دفعةُ استيراد عملاء محتمَلين من ملفٍّ واحد (مديرٌ وحده يرفعها)."""

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="رافع الملف",
    )
    file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="اسم الملف")
    total_rows = models.PositiveIntegerField(default=0, verbose_name="عدد الصفوف")
    created_count = models.PositiveIntegerField(default=0, verbose_name="عدد الصفوف المُنشأة")
    duplicate_count = models.PositiveIntegerField(default=0, verbose_name="عدد الصفوف المكرَّرة")
    invalid_count = models.PositiveIntegerField(default=0, verbose_name="عدد الصفوف غير الصالحة")
    duplicates = models.JSONField(
        default=list,
        blank=True,
        verbose_name="تفاصيل التكرار",
        help_text="عناصر {row, phone, existing_lead_id, existing_lead_name, assigned_to_name}.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "دفعة استيراد عملاء"
        verbose_name_plural = "دفعات استيراد العملاء"

    def __str__(self):
        return f"{self.file_name or 'دفعة'} ({self.created_count}/{self.total_rows})"


class Lead(models.Model):
    """زبونٌ محتمَل (محلّ) — بلا `tenant`: هو زبون كترا نفسها لا شركةٌ على المنصّة.

    مفتاحُ منع تكراره أرقامُ هواتفه في `LeadPhone` لا حقلٌ هنا.
    """

    class Status(models.TextChoices):
        NEW = "new", "جديد"
        CONTACTED = "contacted", "تم الاتصال"
        INTERESTED = "interested", "مهتم"
        FOLLOW_UP = "follow_up", "متابعة"
        CUSTOMER = "customer", "عميل"
        NOT_INTERESTED = "not_interested", "غير مهتم"
        NO_ANSWER = "no_answer", "لا يجيب"
        WRONG_NUMBER = "wrong_number", "رقم خاطئ"
        POSTPONED = "postponed", "مؤجل"
        CLOSED = "closed", "مغلق"

    class Source(models.TextChoices):
        ADMIN_UPLOAD = "admin_upload", "رفع المدير"
        EMPLOYEE_SUGGESTION = "employee_suggestion", "اقتراح موظف"
        PUBLIC_FORM = "public_form", "نموذج عام"
        REFERRAL = "referral", "إحالة"
        WHATSAPP = "whatsapp", "واتساب"
        WEB = "web", "الموقع"

    class Approval(models.TextChoices):
        APPROVED = "approved", "معتمد"
        PENDING = "pending", "بانتظار الاعتماد"
        REJECTED = "rejected", "مرفوض"

    store_name = models.CharField(max_length=200, verbose_name="اسم المحل")
    owner_name = models.CharField(max_length=150, blank=True, default="", verbose_name="صاحب المحل")
    city = models.CharField(max_length=100, blank=True, default="", verbose_name="المدينة")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="العنوان")
    activity = models.CharField(max_length=150, blank=True, default="", verbose_name="النشاط")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, verbose_name="الحالة",
    )
    assigned_to = models.ForeignKey(
        "platform_ops.PlatformEmployee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="crm_leads",
        verbose_name="الموظف المسند",
        help_text="`None` يعني أنّ العميل في المخزن المتاح لا أنّ لا أحد سُئل.",
    )
    assigned_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإسناد")
    next_follow_up_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="موعد المتابعة القادمة",
    )
    source = models.CharField(
        max_length=24, choices=Source.choices, default=Source.ADMIN_UPLOAD, verbose_name="المصدر",
    )
    approval_status = models.CharField(
        max_length=12, choices=Approval.choices, default=Approval.APPROVED, verbose_name="حالة الاعتماد",
    )
    suggested_by = models.ForeignKey(
        "platform_ops.PlatformEmployee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="crm_suggested_leads",
        verbose_name="مقترح العميل",
    )
    rejection_reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="سبب رفض الاقتراح",
    )
    converted_tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="الشركة الناتجة",
        help_text="يُملأ حين يصير هذا العميل المحتمَل شركةً فعليّة على المنصّة.",
    )
    import_batch = models.ForeignKey(
        LeadImportBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leads",
        verbose_name="دفعة الاستيراد",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="أنشأه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "زبون محتمَل"
        verbose_name_plural = "زبائن محتمَلون"
        indexes = [
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["approval_status"]),
        ]

    def __str__(self):
        return self.store_name

    def primary_phone(self):
        """الرقمُ الأساسيّ — يقرأ من `phones` المحمَّلة سلفاً (`prefetch_related`)
        ولا يفتح استعلاماً جديداً؛ استدعاؤها في حلقةٍ بلا `prefetch_related` يعيد
        فخّ N+1 الذي سُجِّل في هذا المستودع من قبل."""
        for phone in self.phones.all():
            if phone.kind == LeadPhone.Kind.PRIMARY:
                return phone
        return None


class LeadPhone(models.Model):
    """هاتفُ عميلٍ محتمَل — **مفتاحُ منع التكرار الوحيد في الوحدة**.

    قرارُ تصميمٍ مقصود: لا أعمدة هاتف على `Lead` نفسها؛ كلّ الأرقام في جدولٍ
    واحدٍ بفهرس فرادةٍ **واحد** (`e164`) — فلا يمكن لواتساب عميلٍ أن يكون هاتفَ
    عميلٍ آخر لأنّ القيد في القاعدة لا في الكود.
    """

    class Kind(models.TextChoices):
        PRIMARY = "primary", "أساسي"
        WHATSAPP = "whatsapp", "واتساب"
        SECONDARY = "secondary", "ثانوي"
        OWNER_MOBILE = "owner_mobile", "جوال المالك"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="phones", verbose_name="العميل")
    e164 = models.CharField(max_length=20, unique=True, db_index=True, verbose_name="الرقم المطبَّع")
    raw = models.CharField(max_length=32, verbose_name="كما كُتب")
    kind = models.CharField(max_length=16, choices=Kind.choices, verbose_name="النوع")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإضافة")

    class Meta:
        verbose_name = "هاتف عميل محتمَل"
        verbose_name_plural = "هواتف العملاء المحتمَلين"
        constraints = [
            # غيرُ مشروط عمداً: MySQL تتجاهل UniqueConstraint(condition=...) بصمت.
            models.UniqueConstraint(fields=["lead", "kind"], name="crm_leadphone_one_per_kind"),
        ]

    def __str__(self):
        return f"{self.e164} ({self.get_kind_display()})"


class LeadActivity(models.Model):
    """سجلُّ تواصلٍ مع عميلٍ محتمَل — **لا يُعدَّل ولا يُحذَف** (405 على PUT/PATCH/DELETE)."""

    class Kind(models.TextChoices):
        CALL = "call", "مكالمة"
        WHATSAPP = "whatsapp", "واتساب"
        VISIT = "visit", "زيارة"
        NOTE = "note", "ملاحظة"
        STATUS_CHANGE = "status_change", "تغيير حالة"
        ASSIGNMENT = "assignment", "إسناد"
        TRANSFER = "transfer", "تحويل"
        MATERIALS_SENT = "materials_sent", "إرسال مواد"

    lead = models.ForeignKey(
        Lead,
        on_delete=models.PROTECT,
        related_name="activities",
        verbose_name="العميل",
        help_text="PROTECT مقصود: عميلٌ له سجلّ تواصل لا يُحذف.",
    )
    employee = models.ForeignKey(
        "platform_ops.PlatformEmployee",
        null=True,
        on_delete=models.SET_NULL,
        related_name="crm_lead_activities",
        verbose_name="الموظف",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="الفاعل",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="النوع")
    body = models.TextField(blank=True, default="", verbose_name="ماذا حدث")
    outcome = models.CharField(max_length=120, blank=True, default="", verbose_name="النتيجة")
    materials = models.JSONField(default=list, blank=True, verbose_name="المواد المُرسَلة")
    status_before = models.CharField(max_length=20, blank=True, default="", verbose_name="الحالة قبل")
    status_after = models.CharField(max_length=20, blank=True, default="", verbose_name="الحالة بعد")
    next_follow_up_at = models.DateTimeField(null=True, blank=True, verbose_name="موعد المتابعة القادمة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ ووقت النشاط")

    class Meta:
        verbose_name = "نشاطُ تواصل"
        verbose_name_plural = "أنشطة التواصل"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["lead", "-created_at"])]

    def __str__(self):
        return f"{self.lead}: {self.get_kind_display()}"


class LeadTransfer(models.Model):
    """تحويلُ عميلٍ محتمَل من موظّفٍ إلى آخر — مباشرٌ أو بطلبٍ يبتّ فيه المدير."""

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار القرار"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    lead = models.ForeignKey(
        Lead, on_delete=models.PROTECT, related_name="transfers", verbose_name="العميل",
    )
    from_employee = models.ForeignKey(
        "platform_ops.PlatformEmployee",
        null=True,
        on_delete=models.SET_NULL,
        related_name="crm_transfers_out",
        verbose_name="من",
    )
    to_employee = models.ForeignKey(
        "platform_ops.PlatformEmployee",
        on_delete=models.PROTECT,
        related_name="crm_transfers_in",
        verbose_name="إلى",
    )
    reason = models.TextField(verbose_name="السبب")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="طالب التحويل",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="من بتّ",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ القرار")

    class Meta:
        verbose_name = "تحويل عميل"
        verbose_name_plural = "تحويلات العملاء"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lead}: {self.from_employee} → {self.to_employee} ({self.get_status_display()})"
