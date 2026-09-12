"""محولات بيانات عمليات المنصة."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from inventory.models import Product
from partners.models import Partner
from tenants.models import Tenant

from .models import (
    MAX_SERVICE_TRIAL_DAYS,
    CompanyHealthCheck,
    CompanyHealthCheckItem,
    CustomerAcquisition,
    DailyRating,
    DailyRatingToken,
    Engagement,
    IntegrationKey,
    JobApplicant,
    JobApplicantInvitation,
    JobPosting,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
    PlatformOperationEvent,
    PlatformRecruiter,
    PolicyProfile,
    ServiceDocumentType,
    ServiceSubscription,
    ServiceSubscriptionEvent,
    ServiceSubscriptionPolicy,
    ServiceUnitCatalog,
    ServiceUnitCatalogEntry,
    ServiceUsageEvent,
    SubscriptionBillingRecord,
    WorkOrder,
    WorkOrderComment,
    WorkOrderDeliverable,
    WorkOrderDocumentLink,
)



class PlatformEmployeeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = PlatformEmployee
        fields = [
            "id",
            "user",
            "username",
            "email",
            "specialty",
            "capacity_target",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ServiceSubscriptionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    billing_customer_name = serializers.CharField(source="billing_customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_trial = serializers.SerializerMethodField()
    is_eligible = serializers.SerializerMethodField()
    active_engagements_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceSubscription
        fields = [
            "id",
            "tenant",
            "company_name",
            "billing_customer",
            "billing_customer_name",
            "status",
            "status_display",
            "plan",
            "monthly_fee",
            "included_quota",
            "overage_unit_price",
            "consumed_quota",
            "period_start",
            "period_end",
            "trial_started_at",
            "trial_ends_at",
            "is_trial",
            "is_eligible",
            "active_engagements_count",
            "pre_suspension_status",
            "scheduled_cancellation_date",
            "cancellation_reason",
            "subscription_policy_version",
            "fixed_fee_product",
            "overage_product",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_trial(self, obj):
        from .services import is_service_trial

        return is_service_trial(obj)

    def get_is_eligible(self, obj):
        from .services import is_service_subscription_eligible

        return is_service_subscription_eligible(obj)

    def get_active_engagements_count(self, obj):
        annotated_count = getattr(obj, "active_engagements_count", None)
        if annotated_count is not None:
            return annotated_count

        from .models import Engagement

        return Engagement.objects.filter(tenant_id=obj.tenant_id, status=Engagement.Status.ACTIVE).count()


class ServiceSubscriptionEventSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True, default="")

    class Meta:
        model = ServiceSubscriptionEvent
        fields = [
            "id",
            "action",
            "action_display",
            "from_status",
            "to_status",
            "reason",
            "actor",
            "actor_name",
            "correlation_id",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class StartServiceTrialSerializer(serializers.Serializer):
    """بدء تجربة لشركة لا صفّ اشتراك لها بعد — الشركة والخطة وحدهما."""

    tenant = serializers.IntegerField(min_value=1)
    plan = serializers.CharField(required=False, allow_blank=True, max_length=50)


class ActivatePaidSubscriptionSerializer(serializers.Serializer):
    """تفعيل مدفوع لصفّ اشتراك قائم — الشركة تأتي من الصفّ نفسه لا من الطلب."""

    billing_customer = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(), required=True, allow_null=False,
    )
    plan = serializers.CharField(required=False, max_length=50)


class ActivatePaidNewSubscriptionSerializer(ActivatePaidSubscriptionSerializer):
    """تفعيل مدفوع لشركة بلا صفّ اشتراك — تحقّقٌ واحد يحمل الشركة والعميل والخطة معاً."""

    tenant = serializers.IntegerField(min_value=1)


class ServiceSubscriptionSettingsSerializer(serializers.Serializer):
    plan = serializers.CharField(required=False, max_length=50)
    monthly_fee = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
    included_quota = serializers.IntegerField(required=False, min_value=0)
    overage_unit_price = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
    billing_customer = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(), required=False, allow_null=True
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class SubscriptionReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=500)


class ServiceSubscriptionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=500)
    immediate = serializers.BooleanField(required=False, default=False)


class SubscriptionPolicySerializer(serializers.ModelSerializer):
    billing_tenant_name = serializers.CharField(source="billing_tenant.CompanyName", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    fixed_fee_product_name = serializers.CharField(
        source="fixed_fee_product.name_ar", read_only=True, default=None, allow_null=True,
    )
    overage_product_name = serializers.CharField(
        source="overage_product.name_ar", read_only=True, default=None, allow_null=True,
    )
    effective_state = serializers.SerializerMethodField()

    class Meta:
        model = ServiceSubscriptionPolicy
        fields = [
            "id",
            "version",
            "status",
            "status_display",
            "effective_state",
            "plan",
            "billing_tenant",
            "billing_tenant_name",
            "monthly_fee",
            "included_quota",
            "trial_days",
            "overage_unit_price",
            "fixed_fee_product",
            "fixed_fee_product_name",
            "overage_product",
            "overage_product_name",
            "activation_reason",
            "effective_from",
            "effective_to",
            "created_by",
            "activated_by",
            "activated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_effective_state(self, obj):
        return obj.effective_state()


class SubscriptionPolicyDraftSerializer(serializers.Serializer):
    billing_tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all(), required=False)
    monthly_fee = serializers.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    included_quota = serializers.IntegerField(required=False, min_value=0)
    trial_days = serializers.IntegerField(required=False, min_value=0, max_value=MAX_SERVICE_TRIAL_DAYS)
    overage_unit_price = serializers.DecimalField(
        required=False, max_digits=12, decimal_places=2, min_value=Decimal("0.00"),
    )
    plan = serializers.CharField(required=False, allow_blank=True, max_length=50)
    fixed_fee_product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True,
    )
    overage_product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True,
    )


class ActivateSubscriptionPolicySerializer(serializers.Serializer):
    change_reason = serializers.CharField(required=True, allow_blank=False, max_length=500)
    effective_from = serializers.DateTimeField(required=False, allow_null=True)


class SubscriptionBillingRecordSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True, default="", allow_null=True)
    #: هويّةُ الشركة المفوتَرة — بدونها يعرض سجلُّ الفوترة أرقامَ اشتراكاتٍ لا يعرف
    #: قارئُها لمن هي. والـqueryset يجلب `subscription__tenant` مسبقاً فلا N+1.
    tenant_id = serializers.IntegerField(source="subscription.tenant_id", read_only=True)
    company_name = serializers.CharField(source="subscription.tenant.CompanyName", read_only=True)

    class Meta:
        model = SubscriptionBillingRecord
        fields = [
            "id",
            "subscription",
            "tenant_id",
            "company_name",
            "period_start",
            "period_end",
            "invoice",
            "invoice_number",
            "monthly_fee",
            "included_quota",
            "consumed_quota",
            "overage_units",
            "overage_unit_price",
            "overage_fee",
            "total_amount",
            "created_at",
        ]
        read_only_fields = fields


class WorkOrderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    # التسمياتُ المقروءة: الواجهةُ كانت تعرض `data_entry` و`waiting_customer` خامّةً
    # لأنّ الخادمَ لا يُعلن نصّاً لها، ولا يجوز أن تُترجمها الواجهةُ بجدولٍ ثانٍ يتباعد.
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    assignee_name = serializers.SerializerMethodField()
    effective_duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrder
        fields = [
            "id",
            "tenant",
            "company_name",
            "title",
            "description",
            "kind",
            "kind_display",
            "source",
            "source_display",
            "priority",
            "priority_display",
            "channel",
            "external_ref",
            "attachment_ids",
            "assignee",
            "assignee_name",
            "status",
            "status_display",
            "return_status",
            "waiting_seconds_total",
            "waiting_entered_at",
            "received_at",
            "approved_at",
            "closed_at",
            "policy_snapshot",
            "deadline_at",
            "effective_duration_seconds",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "kind_display",
            "source_display",
            "status_display",
            "priority_display",
            "channel",
            "external_ref",
            "attachment_ids",
            "status",
            "return_status",
            "waiting_seconds_total",
            "waiting_entered_at",
            "approved_at",
            "closed_at",
            "policy_snapshot",
            "deadline_at",
            "effective_duration_seconds",
            "created_at",
            "updated_at",
        ]

    def get_assignee_name(self, obj):
        if obj.assignee and obj.assignee.user:
            return getattr(obj.assignee.user, "username", str(obj.assignee))
        return None

    def get_effective_duration_seconds(self, obj):
        return obj.calculate_effective_duration_seconds()


class IntegrationKeySerializer(serializers.ModelSerializer):
    """عرضُ مفتاح القناة — **بلا رمزٍ ولا تجزئة**.

    `token_hash` نفسُه لا يُعرَض: هو المادّةُ التي تُقارَن بها المحاولات، وعرضُه
    يمنح المهاجمَ هدفاً يعمل عليه دون داعٍ. والرمزُ الخامُّ لا يُحفَظ أصلاً فلا
    سبيلَ لعرضه بعد لحظةِ التوليد.
    """

    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)

    class Meta:
        model = IntegrationKey
        fields = [
            "id",
            "tenant",
            "company_name",
            "channel",
            "status",
            "name",
            "revoked_at",
            "revocation_reason",
            "rotated_at",
            "last_used_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PolicyProfileSerializer(serializers.ModelSerializer):
    """محول بيانات ملف سياسة الأداء — قراءة للمدير وفريق العمليات."""

    class Meta:
        model = PolicyProfile
        fields = [
            "id",
            "specialty",
            "name",
            "description",
            "weights",
            "targets",
            "sla_hours_by_kind",
            "min_sample_size",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PerformanceSnapshotSerializer(serializers.ModelSerializer):
    """محول بيانات لقطة الأداء الشهرية — قراءة فقط."""

    employee_name = serializers.CharField(source="employee.user.username", read_only=True)
    specialty = serializers.CharField(
        source="employee.specialty", read_only=True, default=""
    )

    class Meta:
        model = PerformanceSnapshot
        fields = [
            "id",
            "employee",
            "employee_name",
            "specialty",
            "period_year",
            "period_month",
            "status",
            "composite_score",
            "sample_size",
            "policy_profile",
            "policy_snapshot",
            "metrics_data",
            "axes_data",
            "rework_rate",
            "processed_sales_value",
            "captured_at",
            "captured_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PlatformNotificationSerializer(serializers.ModelSerializer):
    """محول بيانات إشعارات عمليات المنصة (م٦)."""

    notification_type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )
    company_name = serializers.CharField(
        source="tenant.CompanyName", read_only=True, default=None
    )

    class Meta:
        model = PlatformNotification
        fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "is_read",
            "read_at",
            "tenant",
            "company_name",
            "data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "tenant",
            "company_name",
            "data",
            "created_at",
            "updated_at",
        ]


class PlatformActivityLogSerializer(serializers.ModelSerializer):
    """محول بيانات سجل أنشطة موظفي المنصة عبر الشركات (م٦)."""

    employee_name = serializers.CharField(
        source="employee.user.username", read_only=True
    )
    company_name = serializers.CharField(
        source="tenant.CompanyName", read_only=True, default=None
    )
    action_display = serializers.CharField(
        source="get_action_display", read_only=True
    )

    class Meta:
        model = PlatformActivityLog
        fields = [
            "id",
            "employee",
            "employee_name",
            "tenant",
            "company_name",
            "action",
            "action_display",
            "entity_type",
            "entity_id",
            "description",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class DailyRatingSerializer(serializers.ModelSerializer):
    """محول بيانات التقييم اليومي (م٧)."""

    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = DailyRating
        fields = [
            "id",
            "tenant",
            "company_name",
            "employee",
            "employee_name",
            "service_date",
            "stars",
            "note",
            "edited_once",
            "source",
            "rated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "company_name",
            "employee_name",
            "edited_once",
            "source",
            "rated_by",
            "created_at",
            "updated_at",
        ]

    def get_employee_name(self, obj) -> str:
        if obj.employee and obj.employee.user:
            return obj.employee.user.get_full_name() or obj.employee.user.username
        return ""


class DailyRatingCreateSerializer(serializers.Serializer):
    """بيانات إدخال التقييم اليومي من داخل التطبيق."""

    employee_id = serializers.IntegerField(required=True)
    service_date = serializers.DateField(required=True)
    stars = serializers.IntegerField(min_value=1, max_value=5, required=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class DailyRatingUpdateSerializer(serializers.Serializer):
    """تعديل التقييم اليومي لمرة واحدة.

    `stars` إلزاميّةٌ في `PUT` واختياريّةٌ في `PATCH` — والمُنشئُ يمرّر `partial`
    فيرفعُ الإلزامَ من تلقاء `Serializer`، فلا يُردّ تعديلُ الملاحظةِ وحدَها بـ400.
    """

    stars = serializers.IntegerField(min_value=1, max_value=5, required=True)
    note = serializers.CharField(required=False, allow_blank=True)


class GenerateRatingLinkSerializer(serializers.Serializer):
    """طلب توليد رابط التقييم اليومي المهشر."""

    employee_id = serializers.IntegerField(required=True)
    service_date = serializers.DateField(required=True)


#: سقفُ ملاحظةِ التقييم على السطح **العام** — حقلٌ بلا حدٍّ يصبّ في `TextField`
#: على نقطةٍ بلا مصادقة، والمواصفة تسمّي «الحجمَ والفحصَ بالبايتات» على الأسطح العامة.
PUBLIC_RATING_NOTE_MAX_LENGTH = 2000


class PublicRatingSubmitSerializer(serializers.Serializer):
    """إرسال التقييم من الرابط العام."""

    stars = serializers.IntegerField(min_value=1, max_value=5, required=True)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=PUBLIC_RATING_NOTE_MAX_LENGTH,
    )


class PlatformRecruiterSerializer(serializers.ModelSerializer):
    """محول بيانات مسؤول توظيف المنصة.

    **الإسنادُ باسم المستخدم أو بريده لا بمعرّفه** — بنمط ترقية السوبر أدمن
    (`core/platform_admin_api.py` (`platform_super_admins`)): السوبر أدمن يعرف
    زميلَه باسمه ولا يملك شاشةً تُريه معرّفاتِ المستخدمين. والإسنادُ **لا يُنشئ
    حساباً**: يرفع الدورَ على مستخدمٍ مسجَّلٍ قائم.
    """

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    full_name = serializers.SerializerMethodField()
    identifier = serializers.CharField(write_only=True, max_length=254)

    class Meta:
        model = PlatformRecruiter
        fields = [
            "id",
            "user",
            "username",
            "email",
            "full_name",
            "is_active",
            "identifier",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "is_active", "created_at", "updated_at"]

    def validate_identifier(self, value):
        identifier = (value or "").strip()
        if not identifier:
            raise serializers.ValidationError("اكتب اسم المستخدم أو بريده.")
        user = (
            get_user_model()
            .objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
            .first()
        )
        if user is None:
            raise serializers.ValidationError("لا يوجد مستخدم بهذا الاسم أو البريد.")
        return user

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username


class JobPostingSerializer(serializers.ModelSerializer):
    """عرض وإدارة إعلان الوظيفة لمسؤولي التوظيف والمديرين."""

    employment_type_display = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )
    is_live = serializers.SerializerMethodField()
    public_url = serializers.SerializerMethodField()
    applicants_count = serializers.SerializerMethodField()

    class Meta:
        model = JobPosting
        fields = [
            "id",
            "title",
            #: التخصّصُ المنصّيّ — يُنسَخ إلى الموظّف عند قبول الدعوة، فبلا إتاحته
            #: هنا لا يستطيع مسؤولُ التوظيف ضبطَه ويُوظَّف المقبولُ بلا تخصّص.
            "specialty",
            "description",
            "requirements",
            "location",
            "employment_type",
            "employment_type_display",
            "salary_range",
            "token",
            "is_open",
            "is_live",
            "expires_at",
            "closed_at",
            "public_url",
            "applicants_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "token", "is_open", "closed_at", "created_by", "created_at", "updated_at"]

    def get_is_live(self, obj) -> bool:
        return obj.is_live()

    def get_public_url(self, obj) -> str:
        from .services import job_public_url
        return job_public_url(obj.token)

    def get_applicants_count(self, obj) -> int:
        # `.count()` استعلامٌ لكلّ صفّ ويتجاهل `prefetch_related` المدفوعَ ثمنُه
        # في الـqueryset. `len()` على المخزَّن المسبق يقرأ الذاكرة، ويسقط على
        # `.count()` وحدَه حين لم يُطلَب الجلبُ المسبق (صفٌّ مفرد).
        cache = getattr(obj, "_prefetched_objects_cache", None)
        if cache is not None and "applicants" in cache:
            return len(cache["applicants"])
        return obj.applicants.count()


class JobApplicantSerializer(serializers.ModelSerializer):
    """عرض المتقدم لإدارة التوظيف — بلا cv_url بأي حال.

    قاعدة أمنية صارمة:
    - رابط السيرة الذاتية cv_url لا يُطبع في أي مُسلسِل إطلاقاً (داخلياً كان أم عاماً).
    - بدلاً من الرابط يُعرض فقط علم has_cv، والوصول للسيرة عبر نقطة تحميل مخصصة.
    """

    job_title = serializers.CharField(source="job.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    has_cv = serializers.SerializerMethodField()
    #: الانتقالاتُ المسموحةُ من الحالة الحاليّة — **من جدول الخادم الوحيد**
    #: (`APPLICANT_TRANSITIONS`) لا من نسخةٍ في الواجهة تتباعد عنه بصمت. و«مقبول»
    #: مستبعَدةٌ منها: تُبلَغ بقبول المتقدّم للدعوة لا بزرّ.
    next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = JobApplicant
        fields = [
            "id",
            "job",
            "job_title",
            "name",
            "phone",
            "email",
            "about",
            "status",
            "status_display",
            "rating",
            "notes",
            "reference_code",
            "has_cv",
            "cv_name",
            "hired_employee",
            "next_statuses",
            "created_at",
            "updated_at",
        ]
        #: `status` و`job` و`cv_name` **قراءةٌ فقط عمداً**: الحالةُ تتحرّك بـ
        #: `transition-status` وحدَها فتمرّ بجدول الانتقالات المعلَن وبحارس
        #: «حالةُ المقبول تُبلَغ بقبول الدعوة لا بكتابةٍ مباشرة». وبدون ذلك يصنع
        #: `PATCH {"status": "hired"}` مقبولاً بلا حسابٍ ولا `PlatformEmployee`
        #: ولا دعوةٍ مستهلَكة. و`job` نقلُ متقدّمٍ إلى إعلانٍ آخر — ليس تحريراً.
        #: و`cv_name` اسمُ ملفٍّ رفعه المتقدّم، لا حقلٌ إداريّ.
        read_only_fields = [
            "id",
            "job",
            "status",
            "cv_name",
            "reference_code",
            "has_cv",
            "hired_employee",
            "next_statuses",
            "created_at",
            "updated_at",
        ]

    def get_has_cv(self, obj) -> bool:
        return bool(obj.cv_url)

    def get_next_statuses(self, obj) -> list[dict]:
        from .services import APPLICANT_TRANSITIONS

        allowed = APPLICANT_TRANSITIONS.get(obj.status, set())
        return [
            {"value": value, "label": label}
            for value, label in JobApplicant.Status.choices
            if value in allowed and value != JobApplicant.Status.HIRED
        ]


class JobApplicantInvitationSerializer(serializers.ModelSerializer):
    """محول بيانات دعوة المرشح."""

    applicant_name = serializers.CharField(source="applicant.name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_accepted = serializers.BooleanField(read_only=True)
    is_consumed = serializers.BooleanField(read_only=True)
    class Meta:
        model = JobApplicantInvitation
        fields = [
            "id",
            "applicant",
            "applicant_name",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "is_expired",
            "is_accepted",
            "is_consumed",
            "created_at",
        ]
        read_only_fields = fields


# ==============================================================================
# التذكرة 210-B: فحص صحة الشركة، والإسناد والطاقة، واكتساب العميل
# ==============================================================================


class CompanyHealthCheckItemSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True, default="")

    class Meta:
        model = CompanyHealthCheckItem
        fields = [
            "id",
            "health_check",
            "code",
            "status",
            "status_display",
            "evidence_value",
            "evidence_note",
            "source",
            "source_display",
            "mandatory",
            "action",
            "owner",
            "owner_name",
            "due_date",
            "work_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "health_check", "code", "source", "mandatory", "work_order", "created_at", "updated_at",
        ]


class CompanyHealthCheckSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    complexity_display = serializers.CharField(source="get_complexity_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True, default="")
    approved_by_name = serializers.CharField(source="approved_by.get_full_name", read_only=True, default="")
    items = CompanyHealthCheckItemSerializer(many=True, read_only=True)

    class Meta:
        model = CompanyHealthCheck
        fields = [
            "id",
            "tenant",
            "company_name",
            "kind",
            "kind_display",
            "status",
            "status_display",
            "period",
            "complexity",
            "complexity_display",
            "notes",
            "created_by",
            "created_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "tenant", "status", "created_by", "approved_by", "approved_at", "items", "created_at", "updated_at",
        ]


class CreateHealthCheckDraftSerializer(serializers.Serializer):
    tenant = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=CompanyHealthCheck.Kind.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class UpdateHealthCheckSerializer(serializers.Serializer):
    complexity = serializers.ChoiceField(choices=CompanyHealthCheck.Complexity.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class UpdateHealthCheckItemSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CompanyHealthCheckItem.ItemStatus.choices, required=False)
    evidence_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    evidence_note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    action = serializers.CharField(required=False, allow_blank=True, max_length=500)
    owner = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), required=False, allow_null=True,
    )
    due_date = serializers.DateField(required=False, allow_null=True)


class EngagementSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.user.get_full_name", read_only=True)
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Engagement
        fields = [
            "id",
            "employee",
            "employee_name",
            "tenant",
            "company_name",
            "status",
            "status_display",
            "kind",
            "kind_display",
            "onboarding_expires_at",
            "assigned_by",
            "assigned_at",
            "suspended_at",
            "suspension_reason",
            "revoked_at",
            "revocation_reason",
            "ended_at",
            "end_reason",
            "predecessor",
            "capacity_override_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AssignEngagementSerializer(serializers.Serializer):
    tenant = serializers.IntegerField(min_value=1)
    employee = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=Engagement.Kind.choices, required=False)
    capacity_override_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class TransferEngagementSerializer(serializers.Serializer):
    to_employee = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=True, allow_blank=False, max_length=500)
    capacity_override_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class CustomerAcquisitionSerializer(serializers.ModelSerializer):
    acquired_by_name = serializers.CharField(source="acquired_by.user.get_full_name", read_only=True)

    class Meta:
        model = CustomerAcquisition
        fields = [
            "id",
            "tenant",
            "acquired_by",
            "acquired_by_name",
            "acquired_at",
            "note",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_by", "created_at", "updated_at"]


class SetCustomerAcquisitionSerializer(serializers.Serializer):
    tenant = serializers.IntegerField(min_value=1)
    acquired_by = serializers.IntegerField(min_value=1)
    acquired_at = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


# ==============================================================================
# التذكرة 210-C: كتالوج وحدات الخدمة، ربط المستندات، ودفتر الاستخدام
# ==============================================================================


class WorkOrderDocumentLinkSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source="get_document_type_display", read_only=True)
    complexity_display = serializers.CharField(source="get_complexity_display", read_only=True)
    line_count_source_display = serializers.CharField(source="get_line_count_source_display", read_only=True)

    class Meta:
        model = WorkOrderDocumentLink
        fields = [
            "id",
            "work_order",
            "deliverable",
            "document_type",
            "document_type_display",
            "document_id",
            "line_count",
            "line_count_source",
            "line_count_source_display",
            "recount_reason",
            "complexity",
            "complexity_display",
            "linked_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "work_order", "deliverable", "linked_by", "created_at", "updated_at",
            "line_count_source", "line_count_source_display", "recount_reason",
        ]


class LinkWorkOrderDocumentSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=ServiceDocumentType.choices)
    document_id = serializers.IntegerField(min_value=1)
    line_count = serializers.IntegerField(min_value=1, required=False, default=1)
    #: سببُ إعادة احتساب مستندٍ سبق احتسابُه — مديرُ العمليات وحدَه يمرّره (`WorkOrderViewSet.link_document`).
    recount_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    complexity = serializers.ChoiceField(
        choices=ServiceUnitCatalogEntry.Complexity.choices, required=False, allow_blank=True,
    )


class WorkOrderDeliverableSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    review_status_display = serializers.CharField(source="get_review_status_display", read_only=True)
    rejection_category_display = serializers.CharField(source="get_rejection_category_display", read_only=True)
    document_links = WorkOrderDocumentLinkSerializer(many=True, read_only=True)

    class Meta:
        model = WorkOrderDeliverable
        fields = [
            "id",
            "tenant",
            "work_order",
            "kind",
            "kind_display",
            "review_status",
            "review_status_display",
            "content",
            "payload",
            "file_url",
            "content_snapshot",
            "rejection_reason",
            "rejection_category",
            "rejection_category_display",
            "reviewed_by",
            "reviewed_at",
            "submitted_by",
            "document_links",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "tenant", "work_order", "review_status", "review_status_display", "content_snapshot",
            "rejection_reason", "rejection_category", "rejection_category_display",
            "reviewed_by", "reviewed_at", "submitted_by", "document_links", "created_at", "updated_at",
        ]


class SubmitWorkOrderDeliverableSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=WorkOrderDeliverable.Kind.choices, required=False)
    content = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.JSONField(required=False)
    file_url = serializers.CharField(required=False, allow_blank=True, max_length=500)
    document_link_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list,
    )


class ReviewWorkOrderDeliverableSerializer(serializers.Serializer):
    review_status = serializers.ChoiceField(choices=WorkOrderDeliverable.ReviewStatus.choices)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    rejection_category = serializers.ChoiceField(
        choices=WorkOrderDeliverable.RejectionCategory.choices, required=False, allow_blank=True,
    )

    def validate(self, attrs):
        if attrs.get("review_status") == WorkOrderDeliverable.ReviewStatus.REJECTED:
            if not attrs.get("rejection_reason", "").strip():
                raise serializers.ValidationError({"rejection_reason": ["سبب الرفض إلزامي عند الرفض."]})
            if not attrs.get("rejection_category"):
                raise serializers.ValidationError({"rejection_category": ["تصنيف سبب الرفض إلزامي عند الرفض."]})
        return attrs


class WorkOrderCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)
    visibility_display = serializers.CharField(source="get_visibility_display", read_only=True)

    class Meta:
        model = WorkOrderComment
        fields = [
            "id", "tenant", "work_order", "visibility", "visibility_display",
            "author", "author_name", "content", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "tenant", "work_order", "author", "author_name", "visibility_display", "created_at", "updated_at"]


class AddWorkOrderCommentSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False)
    visibility = serializers.ChoiceField(choices=WorkOrderComment.Visibility.choices)


class TransitionWorkOrderStatusSerializer(serializers.Serializer):
    target_status = serializers.ChoiceField(choices=WorkOrder.Status.choices)


class CreateWorkOrderSerializer(serializers.Serializer):
    tenant = serializers.IntegerField(min_value=1)
    title = serializers.CharField(allow_blank=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    kind = serializers.ChoiceField(choices=WorkOrder.Kind.choices, required=False)
    priority = serializers.ChoiceField(choices=WorkOrder.Priority.choices, required=False)
    assignee = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class AssignWorkOrderSerializer(serializers.Serializer):
    assignee = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class ChangeWorkOrderPrioritySerializer(serializers.Serializer):
    priority = serializers.ChoiceField(choices=WorkOrder.Priority.choices)


class ServiceUnitCatalogEntrySerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source="get_document_type_display", read_only=True)

    class Meta:
        model = ServiceUnitCatalogEntry
        fields = [
            "id", "catalog", "document_type", "document_type_display", "base_units", "per_line_weight",
            "complexity_low_add", "complexity_medium_add", "complexity_high_add", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "catalog", "document_type_display", "created_at", "updated_at"]


class ServiceUnitCatalogSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    effective_state = serializers.SerializerMethodField()
    entries = ServiceUnitCatalogEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ServiceUnitCatalog
        fields = [
            "id", "version", "status", "status_display", "effective_state", "activation_reason",
            "effective_from", "effective_to", "created_by", "activated_by", "activated_at", "entries",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "version", "status", "status_display", "effective_state", "activation_reason",
            "effective_from", "effective_to", "created_by", "activated_by", "activated_at", "entries",
            "created_at", "updated_at",
        ]

    def get_effective_state(self, obj):
        return obj.effective_state()


class CatalogEntryInputSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=ServiceDocumentType.choices)
    base_units = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=Decimal("0.00"))
    per_line_weight = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default=Decimal("0.00"))
    complexity_low_add = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=Decimal("0.00"))
    complexity_medium_add = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=Decimal("0.00"))
    complexity_high_add = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=Decimal("0.00"))


class UpdateServiceUnitCatalogEntriesSerializer(serializers.Serializer):
    entries = CatalogEntryInputSerializer(many=True)


class ActivateServiceUnitCatalogSerializer(serializers.Serializer):
    activation_reason = serializers.CharField(allow_blank=False, max_length=500)
    effective_from = serializers.DateTimeField(required=False, allow_null=True)


class ServiceUsageEventSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)
    #: الخادمُ هو من يسمّي مصدرَ العدد — شاشةُ الدفتر تعرضه ولا تترجمه بجدولٍ ثانٍ يتباعد.
    line_count_source_display = serializers.CharField(source="get_line_count_source_display", read_only=True)
    employee_name = serializers.CharField(source="employee.user.get_full_name", read_only=True, default="")
    company_name = serializers.CharField(source="tenant.CompanyName", read_only=True)

    class Meta:
        model = ServiceUsageEvent
        fields = [
            "id", "tenant", "company_name", "subscription", "work_order", "deliverable", "document_link",
            "event_type", "event_type_display", "source_type", "source_type_display", "source_id",
            "line_count_snapshot", "line_count_source", "line_count_source_display", "catalog_version", "units",
            "chargeable_to_customer", "creditable_to_employee",
            "employee", "employee_name", "approved_by", "approved_at", "period_start", "period_end",
            "idempotency_key", "reversed_event", "reason", "correlation_id", "created_at",
        ]
        read_only_fields = fields


class ReverseUsageEventSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, max_length=500)
