"""مُسلسِلات نواة الـCRM — لا `fields = "__all__"` في أيّ مكان."""
from rest_framework import serializers

from .models import Lead, LeadActivity, LeadImportBatch, LeadPhone, LeadTransfer


def _employee_summary(employee):
    if employee is None:
        return None
    user = getattr(employee, "user", None)
    name = ((user.get_full_name() or user.username) if user else "")
    return {"id": employee.pk, "name": name}


class LeadPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadPhone
        fields = ["id", "e164", "raw", "kind", "created_at"]
        read_only_fields = fields


class LeadPhoneInputSerializer(serializers.Serializer):
    # 32 = عرضُ `LeadPhone.raw`. بلا هذا السقف يُخزَّن ما كتبه المستخدمُ كما هو
    # فتقتطعه MySQL بصمتٍ (أو ترفضه في الوضع الصارم)، ولا تكشفه SQLite في
    # الاختبارات لأنّها لا تفرض `max_length` إطلاقاً.
    # يحرس التطابقَ `crm/tests/test_input_widths_fit_columns.py`.
    raw = serializers.CharField(max_length=LeadPhone._meta.get_field("raw").max_length)
    kind = serializers.ChoiceField(choices=LeadPhone.Kind.choices)


class LeadSerializer(serializers.ModelSerializer):
    phones = LeadPhoneSerializer(many=True, read_only=True)
    assigned_to = serializers.SerializerMethodField()
    suggested_by = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id", "store_name", "owner_name", "city", "address", "activity",
            "status", "assigned_to", "assigned_at", "next_follow_up_at",
            "source", "approval_status", "suggested_by", "rejection_reason",
            "converted_tenant", "phones", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "assigned_to", "assigned_at", "approval_status", "suggested_by",
            "rejection_reason", "converted_tenant", "phones", "created_at", "updated_at",
        ]

    def get_assigned_to(self, obj):
        return _employee_summary(obj.assigned_to)

    def get_suggested_by(self, obj):
        return _employee_summary(obj.suggested_by)


class LeadCreateSerializer(serializers.Serializer):
    """إدخالُ إنشاء عميل — المدير يُنشئه معتمَداً، والموظّفُ يقترحه (`crm.views`)."""

    store_name = serializers.CharField(max_length=200)
    owner_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    activity = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phones = LeadPhoneInputSerializer(many=True)

    def validate_phones(self, value):
        if not value:
            raise serializers.ValidationError("رقمُ هاتفٍ واحدٌ على الأقلّ إلزاميّ.")
        return value


class LeadPatchSerializer(serializers.ModelSerializer):
    """تعديلُ حقول الوصف فقط — لا `assigned_to` ولا `status` ولا `approval_status` هنا."""

    class Meta:
        model = Lead
        fields = ["owner_name", "city", "address", "activity"]


class LeadActivitySerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()

    class Meta:
        model = LeadActivity
        fields = [
            "id", "lead", "employee", "kind", "body", "outcome", "materials",
            "status_before", "status_after", "next_follow_up_at", "created_at",
        ]
        read_only_fields = fields

    def get_employee(self, obj):
        return _employee_summary(obj.employee)


class LeadActivityCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=LeadActivity.Kind.choices)
    body = serializers.CharField(required=False, allow_blank=True, default="")
    outcome = serializers.CharField(required=False, allow_blank=True, default="")
    materials = serializers.ListField(required=False, default=list)
    next_follow_up_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class LeadStatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices)
    body = serializers.CharField(required=False, allow_blank=True, default="")


class LeadTransferSerializer(serializers.ModelSerializer):
    from_employee = serializers.SerializerMethodField()
    to_employee = serializers.SerializerMethodField()

    class Meta:
        model = LeadTransfer
        fields = ["id", "lead", "from_employee", "to_employee", "reason", "status", "created_at", "decided_at"]
        read_only_fields = fields

    def get_from_employee(self, obj):
        return _employee_summary(obj.from_employee)

    def get_to_employee(self, obj):
        return _employee_summary(obj.to_employee)


class LeadTransferCreateSerializer(serializers.Serializer):
    to_employee = serializers.IntegerField()
    reason = serializers.CharField()

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("سببُ التحويل إلزاميّ.")
        return value


class TransferDecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RejectLeadSerializer(serializers.Serializer):
    reason = serializers.CharField()

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("سببُ الرفض إلزاميّ.")
        return value


def _column_width(field_name: str, model=Lead) -> int:
    """عرضُ العمود من النموذج نفسِه لا رقماً مكتوباً بيدٍ ينزاح عنه."""
    return model._meta.get_field(field_name).max_length


class LeadImportRowSerializer(serializers.Serializer):
    """صفُّ استيرادٍ واحد — **كلُّ حقلٍ مسقوفٌ بعرض عموده**.

    هذا هو الطريقُ الذي تدخل منه بياناتُ ملفٍّ خارجيٍّ إلى القاعدة جملةً، فهو
    أوّلُ ما يُستغَلّ باسمٍ طويل: MySQL تقتطعه بصمتٍ (أو ترفض الدفعةَ كلَّها في
    الوضع الصارم)، وSQLite في الاختبارات لا تفرض `max_length` فلا تُظهر شيئاً.
    """

    store_name = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=_column_width("store_name"),
    )
    phone = serializers.CharField(
        required=False, allow_blank=True, default="",
        max_length=_column_width("raw", LeadPhone),
    )
    owner_name = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=_column_width("owner_name"),
    )
    city = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=_column_width("city"),
    )
    address = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=_column_width("address"),
    )
    activity = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=_column_width("activity"),
    )


#: سقفُ صفوفِ الدفعة الواحدة. الاستيرادُ كلُّه في معاملةٍ ذرّيّةٍ واحدة
#: (`import_leads`)، وكلُّ صفٍّ يُصدر عدّةَ استعلامات — فدفعةٌ بلا سقفٍ تُبقي
#: الأقفالَ مفتوحةً دقائقَ وتنتهي بمهلةٍ منقضية، لا برسالةٍ يفهمها الرافع.
#: والرقمُ سخيٌّ عمداً: ملفُّ أرقامٍ حقيقيٌّ أصغرُ منه بمراتب، وتقسيمُ ملفٍّ أكبرَ
#: عملٌ دقائقَ مقابل دفعةٍ تُرفَض في ثانية.
MAX_IMPORT_ROWS = 5000


class LeadImportRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)
    rows = LeadImportRowSerializer(
        many=True,
        max_length=MAX_IMPORT_ROWS,
        error_messages={
            "max_length": f"الدفعةُ الواحدةُ لا تتجاوز {MAX_IMPORT_ROWS} صفّاً — قسّم الملفَّ.",
        },
    )


class LeadImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadImportBatch
        fields = [
            "id", "file_name", "total_rows", "created_count", "duplicate_count",
            "invalid_count", "duplicates", "created_at",
        ]
        read_only_fields = fields
