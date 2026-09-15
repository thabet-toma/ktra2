"""مُسلسِلات بوّابة التوظيف العامة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

قاعدة صارمة:
- رابط السيرة الذاتية cv_url لا يُطبع في أي مُسلسِل إطلاقاً ولا يعود للمتقدم.
- لا تسريب لأي بيانات إدارية، ولا مسارات تخزين، ولا معلومات متقدمين آخرين.
"""
from rest_framework import serializers

from platform_ops.models import JobPosting


class PublicJobPostingSerializer(serializers.ModelSerializer):
    """عرض إعلان الوظيفة للمتقدمين — بلا أي بيانات داخلية."""

    #: التسميةُ من الخادم لا من جدولٍ في الصفحة العامّة يتباعد عن `choices`.
    employment_type_display = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )

    class Meta:
        model = JobPosting
        fields = [
            "id",
            "token",
            "title",
            "description",
            "requirements",
            "location",
            "employment_type",
            "employment_type_display",
            "salary_range",
            "created_at",
        ]
        read_only_fields = fields


class JobApplicationInputSerializer(serializers.Serializer):
    """استقبال طلب التقديم من المتقدم."""

    name = serializers.CharField(max_length=200, required=True, trim_whitespace=True)
    phone = serializers.CharField(max_length=40, required=True, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    about = serializers.CharField(required=False, allow_blank=True, default="")
    #: اسمُ الحقل جزءٌ من العقد العامّ فيُعلَن هنا لا في جسم الـview وحدَه.
    #: والفحصُ الأمنيُّ (الحجمُ والنوعُ بالبايتات) يجري في الـview بعد هذا، لأنّ
    #: `FileField` يفحص الوجودَ لا المحتوى.
    cv_file = serializers.FileField(required=False, allow_null=True)


class JobApplicationSuccessSerializer(serializers.Serializer):
    """ردُّ نجاح التقديم — مرجعٌ وحالةٌ واسمُ ملفٍّ، **ولا رابطَ سيرةٍ ولا معرّفاً داخليّاً**.

    الحالةُ تُعاد عمداً: مُدخَلُ المجهول يُحجَر بحالة «جديد» ولا يمسّ شيئاً، فليعرف
    المتقدّمُ أنّ طلبَه سُجّل بانتظار الفرز لا أنّه قُبل.
    """

    reference_code = serializers.CharField()
    status = serializers.CharField()
    job_title = serializers.CharField()
    cv_name = serializers.CharField(allow_blank=True)


class PublicInvitationDetailSerializer(serializers.Serializer):
    """تفاصيل الدعوة للمرشح — بلا بيانات حساسة.

    ‏#214-د: `note` و`contact_phone` يكتبهما المدير عند الإصدار. ولا شيءَ هنا
    من `JobApplicant.notes` — تلك ملاحظاتُ الفرز الداخليّةُ عن الشخص نفسِه.
    """

    job_title = serializers.CharField()
    applicant_name = serializers.CharField()
    email = serializers.EmailField()
    expires_at = serializers.DateTimeField()
    note = serializers.CharField(allow_blank=True)
    contact_phone = serializers.CharField(allow_blank=True)


class AcceptInvitationInputSerializer(serializers.Serializer):
    """استقبال كلمة المرور واسم المستخدم عند قبول الدعوة."""

    password = serializers.CharField(write_only=True, min_length=8, required=True)
    username = serializers.CharField(required=False, allow_blank=True, default="")


# ==============================================================================
# ‏#215: متابعةُ المتقدّم — مُسلسِلاتُ السطح العامّ
# ==============================================================================


class TrackingLookupInputSerializer(serializers.Serializer):
    """عاملا الدخول: رقمُ التتبّع ورقمُ الهاتف الذي قدّم به.

    **ولماذا عاملان لا واحد:** رابطُ الإعلان يُنشَر على فيسبوك عمداً (#214-أ)
    فرمزُ الوظيفة ليس سرّاً، ورقمُ التتبّع ثمانيةُ محارفَ تُجرَّب آليّاً — وخلفه
    اسمُ إنسانٍ ورقمُ هاتفه. الهاتفُ يعرفه صاحبُه غيباً ولا يعرفه غيرُه.
    """

    reference_code = serializers.CharField(max_length=64, trim_whitespace=True)
    phone = serializers.CharField(max_length=40, trim_whitespace=True)


class TrackingSessionInputSerializer(serializers.Serializer):
    """جلسةٌ موقَّعةٌ صدرت بعد إثبات العاملين."""

    session = serializers.CharField(max_length=2048, trim_whitespace=True)


class TrackingReplyInputSerializer(TrackingSessionInputSerializer):
    """ردُّ المتقدّم. السقفُ يطابق `services.APPLICANT_MESSAGE_MAX_LENGTH`."""

    body = serializers.CharField(max_length=4000, trim_whitespace=True)


class PublicApplicantUpdateSerializer(serializers.Serializer):
    """سطرٌ في دفتر المتقدّم — **ولا `is_public` ولا `author` ولا اسمُ كاتب**.

    ما يصل هنا منشورٌ أصلاً (المُرشِّحُ في الخدمة)، وإعادةُ العلَم تقول للقارئ
    إنّ ثمّة سطوراً لا يراها فتدعوه للسؤال عنها.
    """

    id = serializers.IntegerField(read_only=True)
    kind = serializers.CharField(read_only=True)
    author_kind = serializers.CharField(read_only=True)
    body = serializers.CharField(read_only=True)
    link = serializers.CharField(read_only=True, allow_blank=True)
    phone = serializers.CharField(read_only=True, allow_blank=True)
    created_at = serializers.DateTimeField(read_only=True)


class PublicApplicantMeetingSerializer(serializers.Serializer):
    """اجتماعٌ قادمٌ — **بلا حالة حضور**.

    «لم تحضر» تقديرٌ داخليٌّ يُكتب في دفتر الفرز، وعرضُه على صاحبه يفتح جدلاً
    لا تديره صفحةٌ عامّة. الموعدُ والمكانُ كلُّ ما يحتاجه ليحضر.
    """

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    start = serializers.DateTimeField(read_only=True)
    end = serializers.DateTimeField(read_only=True)
    location = serializers.CharField(read_only=True, allow_blank=True)


class PublicApplicantStateSerializer(serializers.Serializer):
    """حالةُ الطلب — **ولا اسم ولا هاتف ولا بريد ولا تقييم ولا `notes`**.

    كلُّها معروفةٌ لصاحب الطلب أصلاً، فإعادتُها لا تفيده وتجعل كلَّ اختراقٍ
    للرمز تسريبَ بياناتٍ شخصيّةٍ بدل تسريبِ حالةٍ وحدَها (OWASP API3).
    """

    reference_code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(read_only=True)
    can_reply = serializers.BooleanField(read_only=True)
