"""مُسلسِلات متابعة الموظفين (المرحلة الأولى: الأساس)."""
from rest_framework import serializers

from .models import (
    EmployeeInvitation,
    EmployeeNote,
    EmployeeOpsSettings,
    EmployeeProfile,
    PointEntry,
    Task,
    TaskAssignment,
    TaskSubmission,
    TaskSubmissionAttachment,
    TaskSubmissionItem,
)


class EmployeeOpsSettingsSerializer(serializers.ModelSerializer):
    """إعدادات الوحدة لكل شركة.

    الحقول مذكورة صراحةً — `fields = "__all__"` ممنوع في هذا المستودع (فخٌّ عضّه
    سابقاً في سند الشيك: حقلٌ يُضاف للنموذج يصير قابلاً للكتابة من الشبكة بصمت).

    ولا تحقّق يدويّ على السالب هنا: الحقول `PositiveIntegerField`، فيشتقّ DRF
    منها `min_value=0` ويردّ 400 قبل أن يصل الرقم إلى أيّ `validate_*`. تحقّقٌ
    لا يستطيع السقوط ليس تحقّقاً.
    """

    class Meta:
        model = EmployeeOpsSettings
        fields = [
            "id",
            "tenant",
            "points_full",
            "points_partial",
            "points_attendance",
            "attendance_daily_cap",
            "leaderboard_highlight_count",
            "rejected_retention_months",
            "invitation_expiry_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_at", "updated_at"]
        # أجلٌ بصفرِ أيّامٍ دعوةٌ ميّتةٌ لحظةَ إنشائها — يُمنع هنا لا يُبتلع في الخدمة.
        extra_kwargs = {"invitation_expiry_days": {"min_value": 1}}


class EmployeeListSerializer(serializers.Serializer):
    """عرض موظفي الشركة في وحدة متابعة الموظفين."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    job_title = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    has_account = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    invitation_status = serializers.SerializerMethodField()

    def get_has_account(self, obj) -> bool:
        return bool(obj.user_id)

    def _get_profile(self, obj):
        # علاقةٌ عكسيّةٌ واحدٌ-لواحد ترفع `RelatedObjectDoesNotExist` لا تُعيد None،
        # والاستثناءُ محدَّدٌ لا عارٍ: `except Exception` هنا كان يبتلع أخطاء قاعدةٍ حقيقيّة.
        try:
            return obj.employee_ops_profile
        except EmployeeProfile.DoesNotExist:
            return None

    def get_manager(self, obj):
        profile = self._get_profile(obj)
        return profile.manager_id if profile else None

    def get_manager_name(self, obj):
        profile = self._get_profile(obj)
        if profile and profile.manager_id:
            return profile.manager.name if profile.manager else None
        return None

    def get_invitation_status(self, obj) -> str:
        annotated = getattr(obj, "annotated_invitation_status", None)
        if annotated in ("pending", "accepted"):
            return annotated
        return "none"


class EmployeeCreateSerializer(serializers.Serializer):
    """إنشاء موظف مع دعوة."""

    name = serializers.CharField(max_length=150, required=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    manager = serializers.IntegerField(required=False, allow_null=True, default=None)


class EmployeeUpdateSerializer(serializers.Serializer):
    """تعديل موظف — الاسم والهاتف والمسمّى والمدير المباشر فقط."""

    name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=100, required=False, allow_blank=True)
    manager = serializers.IntegerField(required=False, allow_null=True)


class EmployeeInvitationSerializer(serializers.ModelSerializer):
    """بيانات دعوة الموظف (الرمز الخام لا يُخزن ولا يُعرض هنا)."""

    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = EmployeeInvitation
        fields = [
            "id",
            "tenant",
            "employee",
            "employee_name",
            "status",
            "expires_at",
            "created_by",
            "created_at",
            "accepted_at",
            "accepted_user",
        ]
        read_only_fields = fields


class AcceptInvitationSerializer(serializers.Serializer):
    """مدخلات قبول الدعوة وإنشاء الحساب."""

    # اختياريّان: الموظف **العائد** يملك حسابه، فقبولُه استعادةُ عضويّةٍ لا إنشاءُ حساب.
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    password = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


class TaskAssignmentSerializer(serializers.ModelSerializer):
    """إسناد المهمة لموظف مع تفاصيل حالته ومؤقته."""

    employee_name = serializers.CharField(source="employee.name", read_only=True)
    employee_code = serializers.CharField(source="employee.code", read_only=True)

    class Meta:
        model = TaskAssignment
        fields = [
            "id",
            "tenant",
            "task",
            "employee",
            "employee_name",
            "employee_code",
            "status",
            "started_at",
            "completed_at",
            "work_started_at",
            "total_work_seconds",
            "extra",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TaskSubmissionAttachmentSerializer(serializers.ModelSerializer):
    """مرفق تسليم المهمة."""

    class Meta:
        model = TaskSubmissionAttachment
        fields = [
            "id",
            "url",
            "name",
            "position",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TaskSubmissionItemSerializer(serializers.ModelSerializer):
    """بند بحث عن منتج في تسليم المهمة."""

    class Meta:
        model = TaskSubmissionItem
        fields = [
            "id",
            "product_link",
            "product_price",
            "notes",
            "attachment_url",
            "attachment_name",
            "images",
            "position",
            "extra",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TaskSubmissionSerializer(serializers.ModelSerializer):
    """عرض تسليم المهمة مع بنوده ومرفقاته وتفاصيل المراجعة."""

    employee_name = serializers.CharField(source="employee.name", read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    items = TaskSubmissionItemSerializer(many=True, read_only=True)
    attachments = TaskSubmissionAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TaskSubmission
        fields = [
            "id",
            "tenant",
            "task",
            "employee",
            "employee_name",
            "body",
            "decision",
            "reviewer",
            "reviewer_name",
            "reviewed_at",
            "reviewer_notes",
            "items",
            "attachments",
            "extra",
            "source_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_reviewer_name(self, obj):
        if not obj.reviewer_id:
            return None
        return obj.reviewer.get_full_name() or obj.reviewer.username


class TaskSerializer(serializers.ModelSerializer):
    """عرض المهمة مع إسناداتها وحالة إسناد المستخدم الحالي."""

    created_by_name = serializers.SerializerMethodField()
    assignments = TaskAssignmentSerializer(many=True, read_only=True)
    my_assignment = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id",
            "tenant",
            "title",
            "description",
            "priority",
            "status",
            "due_date",
            "category",
            "tags",
            "target_price",
            "allowed_sites",
            "created_by",
            "created_by_name",
            "completed_at",
            "extra",
            "source_path",
            "assignments",
            "my_assignment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "created_by",
            "created_by_name",
            "completed_at",
            "assignments",
            "my_assignment",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by_id:
            return None
        return obj.created_by.get_full_name() or obj.created_by.username

    def get_my_assignment(self, obj):
        employee_id = self.context.get("employee_id")
        if not employee_id:
            return None
        for a in obj.assignments.all():
            if a.employee_id == employee_id:
                return TaskAssignmentSerializer(a).data
        return None


#: أقصى ما يُقبل في تسليمٍ واحد. السقفُ على المرفقات وحده كان يُلتفّ عليه:
#: البنودُ بلا عدد، وكلُّ بندٍ يحمل مرفقاً وقائمةَ صورٍ بلا حدّ — فتسليمٌ بمئة
#: صورةٍ يمرّ من باب «المرفقات ٥».
MAX_SUBMISSION_ATTACHMENTS = 5
MAX_SUBMISSION_ITEMS = 50
MAX_ITEM_IMAGES = 5

_PRIORITY_VALUES = frozenset(value for value, _ in Task.PRIORITY_CHOICES)


def _normalize_priority(value):
    """الحيُّ يكتبها صغيرةً (`low`) والنموذجُ كبيرةً — الترجمةُ هنا مرّةً واحدة."""
    val = str(value).upper()
    if val in _PRIORITY_VALUES:
        return val
    raise serializers.ValidationError("أولوية غير صالحة.")


def _validate_media_url(value):
    """رابطٌ لا نصٌّ حرّ: مرفقٌ بمحتوىً غير رابطٍ يكسر كلّ شاشةٍ تعرضه."""
    val = (value or "").strip()
    if not val:
        raise serializers.ValidationError("رابط المرفق مطلوب.")
    if not (val.startswith("http://") or val.startswith("https://") or val.startswith("/")):
        raise serializers.ValidationError("رابط المرفق غير صالح.")
    return val


class TaskCreateSerializer(serializers.Serializer):
    """إنشاء مهمة جديدة مع إسناداتها."""

    title = serializers.CharField(max_length=255, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.CharField(required=False, default="MEDIUM")
    due_date = serializers.DateField(required=False, allow_null=True, default=None)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    target_price = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True, default=None
    )
    allowed_sites = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    assignee_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)

    def validate_priority(self, value):
        return _normalize_priority(value)


class TaskUpdateSerializer(serializers.Serializer):
    """تعديل مهمة."""

    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.CharField(required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    target_price = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True
    )
    allowed_sites = serializers.ListField(child=serializers.CharField(), required=False)
    assignee_ids = serializers.ListField(child=serializers.IntegerField(), required=False)

    def validate_priority(self, value):
        return _normalize_priority(value)


class TaskSubmissionItemInputSerializer(serializers.Serializer):
    """مدخل بند في تسليم المهمة."""

    product_link = serializers.CharField(required=False, allow_blank=True, default="")
    product_price = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True, default=None
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    attachment_url = serializers.CharField(required=False, allow_blank=True, default="")
    attachment_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    images = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    position = serializers.IntegerField(required=False, default=0)

    def validate_images(self, value):
        if value and len(value) > MAX_ITEM_IMAGES:
            raise serializers.ValidationError(
                f"الحد الأقصى للصور في البند الواحد هو {MAX_ITEM_IMAGES} صور."
            )
        return value


class TaskSubmissionAttachmentInputSerializer(serializers.Serializer):
    """مدخل مرفق في تسليم المهمة."""

    url = serializers.CharField(required=True, validators=[_validate_media_url])
    name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    position = serializers.IntegerField(required=False, default=0)


class TaskSubmissionCreateSerializer(serializers.Serializer):
    """مدخلات تسليم المهمة (حتى 5 مرفقات)."""

    body = serializers.CharField(required=False, allow_blank=True, default="")
    items = serializers.ListField(child=TaskSubmissionItemInputSerializer(), required=False, default=list)
    attachments = serializers.ListField(
        child=TaskSubmissionAttachmentInputSerializer(), required=False, default=list
    )

    def validate_attachments(self, value):
        if value and len(value) > MAX_SUBMISSION_ATTACHMENTS:
            raise serializers.ValidationError(
                f"الحد الأقصى للمرفقات هو {MAX_SUBMISSION_ATTACHMENTS} مرفقات فقط."
            )
        return value

    def validate_items(self, value):
        if value and len(value) > MAX_SUBMISSION_ITEMS:
            raise serializers.ValidationError(
                f"الحد الأقصى لبنود التسليم هو {MAX_SUBMISSION_ITEMS} بنداً."
            )
        return value


class TaskSubmissionReviewSerializer(serializers.Serializer):
    """مدخلات مراجعة تسليم المهمة."""

    # القراراتُ الثلاثة من النموذج لا نصوصاً مكرّرة — و`pending` ليست قراراً.
    decision = serializers.ChoiceField(
        choices=[
            TaskSubmission.DECISION_APPROVED_FULL,
            TaskSubmission.DECISION_APPROVED_PARTIAL,
            TaskSubmission.DECISION_REJECTED,
        ],
        required=True,
    )
    reviewer_notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        decision = attrs.get("decision")
        notes = (attrs.get("reviewer_notes") or "").strip()
        if decision == "rejected" and not notes:
            raise serializers.ValidationError({
                "reviewer_notes": "سبب الرفض مطلوب عند رفض التسليم."
            })
        attrs["reviewer_notes"] = notes
        return attrs


class UnreviewSubmissionSerializer(serializers.Serializer):
    """مدخلات إلغاء مراجعة تسليم المهمة — يلزم سبب مكتوب."""

    reason = serializers.CharField(required=True, allow_blank=False)

    def validate_reason(self, value):
        val = (value or "").strip()
        if not val:
            raise serializers.ValidationError("سبب إلغاء المراجعة مطلوب.")
        return val


class PointEntrySerializer(serializers.ModelSerializer):
    """عرض قيد النقاط."""

    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = PointEntry
        fields = [
            "id",
            "employee",
            "employee_name",
            "points",
            "source",
            "awarded_on",
            "submission",
            "reverses",
            "reason",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class ManualPointEntrySerializer(serializers.Serializer):
    """مدخلات إضافة أو خصم النقاط يدوياً."""

    employee = serializers.IntegerField(required=True)
    points = serializers.IntegerField(required=True)
    # لا `awarded_on`: النقاطُ اليدويّة بتاريخ اليوم — انظر `record_manual_points`.
    reason = serializers.CharField(required=True, allow_blank=False)

    def validate_reason(self, value):
        val = (value or "").strip()
        if not val:
            raise serializers.ValidationError("سبب منح أو خصم النقاط مطلوب.")
        return val


class EmployeeNoteSerializer(serializers.ModelSerializer):
    """عرضُ الملاحظة — الكاتبُ للقراءة فقط: يُحلّ من الجلسة لا من الجسم."""

    author_name = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeNote
        fields = [
            "id",
            "employee",
            "body",
            "author",
            "author_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_author_name(self, obj):
        if not obj.author_id:
            return None
        return obj.author.get_full_name() or obj.author.username


class EmployeeNoteInputSerializer(serializers.Serializer):
    """مدخلاتُ كتابة ملاحظة — النصُّ وحده، و`employee` عند الإنشاء.

    **لا حقلَ كاتبٍ هنا**: تمريرُه من العميل يعني ملاحظةً منسوبةً لغير قائلها.
    """

    employee = serializers.IntegerField(required=False)
    body = serializers.CharField(required=True, allow_blank=False)

    def validate_body(self, value):
        val = (value or "").strip()
        if not val:
            raise serializers.ValidationError("نصّ الملاحظة مطلوب.")
        return val


class ActivityRangeSerializer(serializers.Serializer):
    """مدى تبويب النشاط.

    `core.date_ranges.filter_local_date_range` تتوقّع كائنَ **تاريخ** لا نصّاً؛
    تمريرُ النصّ خاماً كان يرمي `TypeError` ⇒ **٥٠٠ على مُدخَلٍ من المستخدم**.
    والتحقّقُ هنا يجعله ٤٠٠ برسالةٍ مفهومة.
    """

    date_from = serializers.DateField(required=False, allow_null=True, default=None)
    date_to = serializers.DateField(required=False, allow_null=True, default=None)
