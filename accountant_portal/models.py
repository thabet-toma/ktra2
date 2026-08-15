from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from tenants.models import Tenant


def default_export_formats():
    return ["csv", "pdf"]


def default_service_types():
    """خدمات المكتب الافتراضية — قائمة قابلة للتعديل من إعدادات المكتب."""
    return ["ض.ق.م شهرية", "ضريبة دخل سنوية", "مراجعة سنوية", "رواتب"]


class AccountantProfile(models.Model):
    PROFESSIONAL_TYPES = [
        ("lawyer", "محامٍ"),
        ("licensed_auditor", "مدقق حسابات مرخص"),
        ("accountant", "محاسب"),
        ("finance_diploma", "دبلوم مالية"),
        ("ex_tax_officer", "موظف ضريبة سابق"),
    ]
    VERIFICATION_STATUSES = [
        ("unverified", "غير موثق"),
        ("pending_review", "بانتظار المراجعة"),
        ("verified", "موثق"),
        ("rejected", "مرفوض"),
        ("barred", "ممنوع"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accountant_profile",
    )
    account_type = models.CharField(max_length=30, default="legal_accountant")
    professional_type = models.CharField(max_length=30, choices=PROFESSIONAL_TYPES)
    license_number = models.CharField(max_length=60, blank=True, default="")
    license_authority = models.CharField(max_length=120, blank=True, default="")
    tax_registration_number = models.CharField(max_length=50)
    business_address = models.TextField()
    phone = models.CharField(max_length=30, blank=True, default="")
    email_verified_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUSES,
        default="unverified",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_accountant_profiles",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    barred_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_profiles"
        constraints = [
            models.UniqueConstraint(
                fields=["tax_registration_number"],
                name="uniq_acct_profile_tax_reg",
            ),
        ]


class AccountantEngagement(models.Model):
    STATUSES = [
        ("pending", "قيد الانتظار"),
        ("active", "نشط"),
        ("suspended", "معلق"),
        ("revoked", "ملغى"),
        ("declined", "مرفوض"),
        ("expired", "منتهي"),
    ]
    INITIATORS = [
        ("accountant", "المحاسب"),
        ("company", "الشركة"),
    ]

    accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="accountant_engagements",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="accountant_engagements",
    )
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")
    initiated_by = models.CharField(max_length=10, choices=INITIATORS)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_accountant_engagements",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_accountant_engagements",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_accountant_engagements",
    )
    revocation_reason = models.TextField(blank=True, default="")
    invitation_token_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
    )
    invitation_expires_at = models.DateTimeField(null=True, blank=True)
    invitation_used_at = models.DateTimeField(null=True, blank=True)
    approved_scope_snapshot = models.JSONField(default=list)
    engagement_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_engagements"
        constraints = [
            models.UniqueConstraint(
                fields=["accountant", "tenant"],
                name="uniq_acct_engagement_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="acct_eng_tenant_status"),
            models.Index(fields=["accountant", "status"], name="acct_eng_user_status"),
        ]


class PortalSettings(models.Model):
    TAX_JURISDICTIONS = [("PS", "فلسطين"), ("PS_IL_DUAL", "فلسطين وإسرائيل")]
    CLEARANCE_MODES = [("manual", "يدوي"), ("api_reserved", "API محجوز")]
    GRANT_PROFILES = [
        ("review_only", "مراجعة فقط"),
        ("review_and_prepare", "مراجعة وتجهيز"),
        ("full_accounting", "محاسبة كاملة"),
    ]
    TAX_PERIOD_TYPES = [("monthly", "شهري"), ("custom", "مخصص")]

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="accountant_portal_settings",
    )
    tax_jurisdiction = models.CharField(
        max_length=10,
        choices=TAX_JURISDICTIONS,
        default="PS",
    )
    strict_invoice_field_validation = models.BooleanField(default=False)
    clearance_mode = models.CharField(
        max_length=20,
        choices=CLEARANCE_MODES,
        default="manual",
    )
    is_israeli_registered_dealer = models.BooleanField(default=False)
    require_reauth_for_sensitive = models.BooleanField(default=True)
    reauth_window_minutes = models.PositiveSmallIntegerField(default=15)
    engagement_retention_years = models.PositiveSmallIntegerField(default=5)
    # ق8 — التكاليف غير ممنوحة افتراضاً، لكن للشركة أن تمنحها لارتباط بعينه
    # ما لم تُقفل المنح كلياً بجعل هذا الإعداد False.
    allow_grant_cost_view = models.BooleanField(default=True)
    invitation_expiry_days = models.PositiveSmallIntegerField(
        default=14,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
    max_active_engagements = models.PositiveIntegerField(default=0)
    lock_blocks_posting = models.BooleanField(default=True)
    default_grant_profile = models.CharField(
        max_length=24,
        choices=GRANT_PROFILES,
        default="review_only",
    )
    tax_period_type = models.CharField(
        max_length=10,
        choices=TAX_PERIOD_TYPES,
        default="monthly",
    )
    filing_due_days = models.PositiveSmallIntegerField(default=15)
    input_vat_window_months = models.PositiveSmallIntegerField(default=6)
    allow_accountant_reopen = models.BooleanField(default=False)
    export_formats = models.JSONField(default=default_export_formats)
    notify_company_on_accountant_action = models.BooleanField(default=True)

    class Meta:
        db_table = "acct_portal_settings"


class TaxPeriodReview(models.Model):
    """مراجعة فترة ضريبية. «OPEN» ليست حالة مخزَّنة — هي غياب الصف."""

    STATUSES = [
        ("in_review", "قيد المراجعة"),
        ("needs_company_action", "بانتظار الشركة"),
        ("ready", "جاهزة"),
        ("approved", "معتمدة"),
        ("submitted", "مقدَّمة"),
        ("locked", "مقفلة"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="tax_period_reviews",
    )
    vat_statement = models.OneToOneField(
        "sales.VatStatement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="period_review",
    )
    period_from = models.DateField()
    period_to = models.DateField()
    status = models.CharField(max_length=24, choices=STATUSES, default="in_review")
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_tax_period_reviews",
    )
    prepared_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_tax_period_reviews",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_tax_period_reviews",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submission_reference = models.CharField(max_length=120, blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    reopen_count = models.PositiveSmallIntegerField(default=0)
    last_reopen_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_period_reviews"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "period_from", "period_to"],
                name="uniq_acct_period_window",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="acct_period_tenant_status"),
        ]


class ReviewQuery(models.Model):
    """طلب توضيح مرتبط بمستند — بديل المحادثة العامة (§16)."""

    SEVERITIES = [("blocker", "مانع"), ("warning", "تحذير"), ("info", "معلومة")]
    STATUSES = [
        ("open", "مفتوح"),
        ("answered", "مُجاب"),
        ("resolved", "مُغلق"),
        ("withdrawn", "مسحوب"),
    ]
    ENTITY_TYPES = [
        ("sales_invoice", "فاتورة بيع"),
        ("purchase_invoice", "فاتورة شراء"),
        ("journal", "قيد محاسبي"),
        ("customer_payment", "سند قبض"),
        ("supplier_payment", "سند صرف"),
        ("partner", "طرف"),
        ("period", "فترة ضريبية"),
        ("other", "أخرى"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="accountant_review_queries",
    )
    engagement = models.ForeignKey(
        AccountantEngagement,
        on_delete=models.CASCADE,
        related_name="review_queries",
    )
    period_review = models.ForeignKey(
        TaxPeriodReview,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queries",
    )
    entity_type = models.CharField(max_length=40, choices=ENTITY_TYPES, default="other")
    entity_id = models.IntegerField(null=True, blank=True)
    entity_label = models.CharField(max_length=200, blank=True, default="")
    title = models.CharField(max_length=200)
    body = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITIES, default="warning")
    status = models.CharField(max_length=12, choices=STATUSES, default="open")
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="raised_review_queries",
    )
    raised_at = models.DateTimeField(auto_now_add=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answered_review_queries",
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    answer_body = models.TextField(blank=True, default="")
    attachment_url = models.CharField(max_length=500, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_review_queries"
        indexes = [
            models.Index(fields=["tenant", "status", "severity"], name="acct_q_tenant_status"),
            models.Index(fields=["tenant", "entity_type", "entity_id"], name="acct_q_tenant_entity"),
        ]


# ── مكتب المحاسبة: سجلّ الممارسة المهنية ─────────────────────────────────────
#
# **الجدار:** الزبون الخارجي **سجلّ ممارسة لا دفترَ حسابات**. لا نموذج من نماذج
# هذا القسم يحمل `tenant`، ولا يصل منه طريق إلى `post_journal` ولا إلى
# `record_stock_movement`. قراءة دفاتر زبون حقيقي تبقى حصراً على مسارات
# الارتباط النشط (`AccountantEngagement`) — وهذا وحده ما يمنع زبوناً خارجياً من
# التسرّب إلى دفاتر شركة فعلية. الملكية هنا للمحاسب: كل استعلام يبدأ بـ
# `accountant=`.


class PracticeClient(models.Model):
    """زبون مكتب المحاسبة — يُدخله المحاسب يدوياً، بشركة على المنصة أو بدونها."""

    STATUSES = [("active", "نشط"), ("archived", "مؤرشف")]

    accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="practice_clients",
    )
    trade_name = models.CharField(max_length=200)
    contact_first = models.CharField(max_length=100, blank=True, default="")
    contact_last = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    mobile = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    sector = models.CharField(max_length=120, blank=True, default="")
    tax_number = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUSES, default="active")
    notes = models.TextField(blank=True, default="")
    # الربط بشركة على المنصة **اختياري**: وجوده يعني أن لهذا الزبون دفاتر تُقرأ
    # من مسارات الارتباط، وغيابه هو الحالة الشائعة «زبون من برا».
    engagement = models.ForeignKey(
        AccountantEngagement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_clients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_practice_clients"
        constraints = [
            models.UniqueConstraint(
                fields=["accountant", "trade_name"],
                name="uniq_practice_client_name",
            ),
        ]
        indexes = [
            models.Index(fields=["accountant", "status"], name="acct_pc_user_status"),
        ]


class PracticeProgram(models.Model):
    """برنامج خدمة متكرر لزبون — «التأخر» مشتقّ من التاريخ لا حالةً مخزَّنة."""

    FREQUENCIES = [("annual", "سنوي"), ("monthly", "شهري"), ("once", "مرة واحدة")]
    STATUSES = [
        ("planned", "مخطط"),
        ("in_progress", "قيد التنفيذ"),
        ("done", "منجز"),
    ]

    accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="practice_programs",
    )
    client = models.ForeignKey(
        PracticeClient,
        on_delete=models.CASCADE,
        related_name="programs",
    )
    service_type = models.CharField(max_length=120)
    frequency = models.CharField(max_length=10, choices=FREQUENCIES, default="monthly")
    team_note = models.TextField(blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="planned")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_practice_programs"
        indexes = [
            models.Index(fields=["accountant", "status"], name="acct_pp_user_status"),
            models.Index(fields=["accountant", "due_date"], name="acct_pp_user_due"),
        ]


class PracticeTask(models.Model):
    """موعد أو استحقاق في أجندة المكتب — بزبون أو بلا زبون."""

    STATUSES = [("open", "مفتوح"), ("done", "منجز")]
    KINDS = [("appointment", "موعد"), ("deadline", "استحقاق")]

    accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="practice_tasks",
    )
    client = models.ForeignKey(
        PracticeClient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=200)
    due_at = models.DateTimeField()
    status = models.CharField(max_length=6, choices=STATUSES, default="open")
    kind = models.CharField(max_length=12, choices=KINDS, default="appointment")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "acct_portal_practice_tasks"
        indexes = [
            models.Index(fields=["accountant", "status", "due_at"], name="acct_pt_user_due"),
        ]


class PracticeDocument(models.Model):
    """مستند في ملف الزبون — رابط مخزَّن، والرفع نفسه من مسار المكتب."""

    accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="practice_documents",
    )
    client = models.ForeignKey(
        PracticeClient,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    program = models.ForeignKey(
        PracticeProgram,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    name = models.CharField(max_length=200)
    url = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "acct_portal_practice_documents"
        indexes = [
            models.Index(fields=["accountant", "client"], name="acct_pd_user_client"),
        ]


class PracticeSettings(models.Model):
    """إعدادات المكتب — الصفّ كسول، وغيابه يعني الافتراضات كاملةً."""

    profile = models.OneToOneField(
        AccountantProfile,
        on_delete=models.CASCADE,
        related_name="practice_settings",
    )
    default_program_due_days = models.PositiveSmallIntegerField(default=15)
    service_types = models.JSONField(default=default_service_types)

    class Meta:
        db_table = "acct_portal_practice_settings"
