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
    """تفاصيل الدعوة للمرشح — بلا بيانات حساسة."""

    job_title = serializers.CharField()
    applicant_name = serializers.CharField()
    email = serializers.EmailField()
    expires_at = serializers.DateTimeField()


class AcceptInvitationInputSerializer(serializers.Serializer):
    """استقبال كلمة المرور واسم المستخدم عند قبول الدعوة."""

    password = serializers.CharField(write_only=True, min_length=8, required=True)
    username = serializers.CharField(required=False, allow_blank=True, default="")
