"""مُسلسِلات مكتب المحاسبة — شكل الـAPI وحده، والحساب في الخدمات.

**لا قراءة إعداداتٍ هنا**: كل قيمةٍ فعليّة (نظام الزبون، إعداداته، بطاقته
بتسميات نظامه) تأتي من `accounting_office/services.py`. يحرس ذلك
`accounting_office/tests/test_settings_guard.py`.

**ومُسلسِلان للزبون لا واحد:** القائمة صفٌّ خفيف بلا بطاقة، وكلُّ صفوفها تقرأ
نظامها من `context["tax_systems"]` الذي يبنيه الـview باستعلامين — لا المحلّل
مرّتين لكل صف. والتفصيل وحده يحمل البطاقة كاملة.
"""
from rest_framework import serializers

from accounting_office import services
from accounting_office.models import ClientReminderRecipient, Contact, OfficeClient


class TaxCardWriteSerializer(serializers.Serializer):
    """حقول البطاقة القابلة للكتابة — والاختياراتُ تُتحقَّق على نظام الزبون."""

    entity_type = serializers.CharField(required=False, allow_blank=True, max_length=20)
    vat_classification = serializers.CharField(required=False, allow_blank=True, max_length=20)
    annual_sales = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, min_value=0,
    )
    has_employees = serializers.BooleanField(required=False)
    employees_count = serializers.IntegerField(
        required=False, min_value=0, max_value=32767,
    )
    is_self_employed = serializers.BooleanField(required=False)


class TaxCardField(serializers.Field):
    """حقلٌ واحدٌ يُقرأ منه شكل البطاقة ويُكتب به تعديلها مع الزبون."""

    def to_representation(self, value):
        if not value:
            return None
        client = getattr(value, "client", None)
        if client is None:
            return None
        return services.tax_card_payload(client)

    def to_internal_value(self, data):
        serializer = TaxCardWriteSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


def _resolved_tax_system(serializer, obj):
    """نظامُ الزبون مرّةً واحدة لكل كائن: من `context` إن وُجد، وإلا من المحلّل.

    `context["tax_systems"]` يبنيه `list` باستعلامين لكل القائمة؛ وحين يغيب
    (المسار المفرد) يُنادى المحلّل مرّةً ويُحفظ على الكائن كي لا يُنادى ثانيةً
    من `get_tax_system` ومن `get_tax_system_label` معاً.
    """
    prefetched = serializer.context.get("tax_systems")
    if prefetched is not None:
        return prefetched.get(obj.pk)
    if not hasattr(obj, "_resolved_tax_system"):
        obj._resolved_tax_system = services.resolve_setting(
            obj.tenant, services.TAX_SYSTEM_KEY, client=obj,
        )
    return obj._resolved_tax_system


class TaxSystemFieldsMixin(serializers.Serializer):
    """الحقلان المشتقّان من المحلّل — يُعرَّفان مرّةً ويورثهما المُسلسِلان.

    يرث `Serializer` لا `object`: درف لا يجمع الحقول المعلَنة من صنفٍ عاديّ
    (`_declared_fields` لا يوجد فيه)، فيُقرأ `tax_system` حقلَ نموذجٍ غير موجود.
    ولا يُنادَى وحده أبداً — خصائصُه (النظامُ وتسميتُه) تأتي من `context`/المحلّل.

    نسخةٌ في كل مُسلسِلٍ تعني موضعين يُنسى أحدهما عند أول تعديل — وقد كانا
    متطابقين حرفياً، وهو أسوأ أنواع الازدواج: يبدو سليماً حتى يختلف.
    """

    tax_system = serializers.SerializerMethodField()
    tax_system_label = serializers.SerializerMethodField()

    def get_tax_system(self, obj):
        return _resolved_tax_system(self, obj)

    def get_tax_system_label(self, obj):
        return services.tax_system_label(self.get_tax_system(obj))


class OfficeClientListSerializer(TaxSystemFieldsMixin, serializers.ModelSerializer):
    """صفُّ القائمة: بلا بطاقة، ونظامُه من الحساب الجماعيّ."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OfficeClient
        fields = [
            "id", "name", "tax_file_number", "status", "status_label",
            "ended_on", "notes", "tax_system", "tax_system_label",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class OfficeClientSerializer(TaxSystemFieldsMixin, serializers.ModelSerializer):
    """زبون المكتب — والنظامُ الضريبيّ الفعليّ يُقرأ من المحلّل لا من حقلٍ هنا."""

    tax_card = TaxCardField(required=False)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OfficeClient
        fields = [
            "id", "name", "tax_file_number", "status", "status_label",
            "ended_on", "notes", "tax_system", "tax_system_label",
            "tax_card", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "ended_on", "created_at", "updated_at"]


class ContactSerializer(serializers.ModelSerializer):
    language_label = serializers.CharField(source="get_language_display", read_only=True)

    class Meta:
        model = Contact
        fields = [
            "id", "name", "phone", "language", "language_label",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class ClientContactRowSerializer(serializers.Serializer):
    """سطرُ ربطٍ للعرض: الجهة كاملةً + هل هي رئيسية."""

    id = serializers.IntegerField()
    is_primary = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    contact = ContactSerializer()


class ClientContactLinkSerializer(serializers.Serializer):
    contact = serializers.IntegerField()
    is_primary = serializers.BooleanField(required=False, default=False)


class ReminderRecipientSerializer(serializers.Serializer):
    reminder_type = serializers.ChoiceField(
        choices=ClientReminderRecipient.REMINDER_TYPE_CHOICES,
    )
    contact = serializers.IntegerField(required=False, allow_null=True)


class SettingValueSerializer(serializers.Serializer):
    """قيمة إعدادٍ كما تصل — نوعُها ومُتحقِّقُها في السجلّ، لا هنا."""

    value = serializers.JSONField()
