"""محولات بيانات عمليات المنصة."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from .models import (
    DailyRating,
    DailyRatingToken,
    IntegrationKey,
    JobApplicant,
    JobApplicantInvitation,
    JobPosting,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
    PlatformRecruiter,
    PolicyProfile,
    ServiceSubscription,
    SubscriptionBillingRecord,
    WorkOrder,
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

    class Meta:
        model = ServiceSubscription
        fields = [
            "id",
            "tenant",
            "company_name",
            "billing_customer",
            "billing_customer_name",
            "status",
            "plan",
            "monthly_fee",
            "included_quota",
            "overage_unit_price",
            "consumed_quota",
            "period_start",
            "period_end",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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




