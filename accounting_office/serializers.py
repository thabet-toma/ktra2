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
from accounting_office.models import (
    CLIENT_SERVICE_FREQUENCY_CHOICES,
    ClientReminderRecipient,
    Contact,
    OBLIGATION_DIRECTION_CHOICES,
    OfficeClient,
    OfficeService,
)


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
    """حقلٌ واحدٌ يُقرأ منه شكل البطاقة ويُكتب به تعديلها مع الزبون.

    **والقناع يمرّ من هنا أيضاً**: التفصيلُ يحمل البطاقة داخله — فحقلُ مبلغٍ
    يُقرأ من `tax_card_payload` بلا مستخدمٍ كان يُظهر لكل عضوٍ ما لا يملكه.
    """

    def to_representation(self, value):
        if not value:
            return None
        client = getattr(value, "client", None)
        if client is None:
            return None
        request = self.context.get("request") if self.context else None
        return services.tax_card_payload(
            client, user=getattr(request, "user", None),
        )

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


class ResponsibleFieldsMixin(serializers.Serializer):
    """الموظف المسؤول — **للقراءة وحدها**: تحويلُه له نقطته (`clients/<pk>/assign/`).

    يظهر في القائمة وفي التفصيل لأنّه العمودُ الذي يعرف به العضو «زبوني أم لا».
    """

    responsible_id = serializers.IntegerField(read_only=True)
    responsible_name = serializers.SerializerMethodField()

    def get_responsible_name(self, obj):
        return services.user_display_name(obj.responsible)


class OfficeClientListSerializer(
    ResponsibleFieldsMixin, TaxSystemFieldsMixin, serializers.ModelSerializer,
):
    """صفُّ القائمة: بلا بطاقة، ونظامُه من الحساب الجماعيّ."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OfficeClient
        fields = [
            "id", "name", "tax_file_number", "status", "status_label",
            "ended_on", "notes", "tax_system", "tax_system_label",
            "responsible_id", "responsible_name",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class OfficeClientSerializer(
    ResponsibleFieldsMixin, TaxSystemFieldsMixin, serializers.ModelSerializer,
):
    """زبون المكتب — والنظامُ الضريبيّ الفعليّ يُقرأ من المحلّل لا من حقلٍ هنا."""

    tax_card = TaxCardField(required=False)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OfficeClient
        fields = [
            "id", "name", "tax_file_number", "status", "status_label",
            "ended_on", "notes", "tax_system", "tax_system_label",
            "tax_card", "responsible_id", "responsible_name",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "ended_on", "responsible_id", "responsible_name",
            "created_at", "updated_at",
        ]


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


# ── الخدمات والباقات وخدمات الزبون (#273) ────────────────────────────────────
class OfficeServiceSerializer(serializers.ModelSerializer):
    """سطرُ كتالوج — **`code` و`is_builtin` للقراءة وحدها**: الكودُ عقدُ الاقتراح."""

    class Meta:
        model = OfficeService
        fields = ["id", "code", "name", "is_active", "is_builtin", "position"]
        read_only_fields = ["id", "code", "is_builtin"]


class ServicePackageWriteSerializer(serializers.Serializer):
    """باقةٌ كما تصل — **`suggested_price` مبلغ** يُفحص بالقناع في الـview."""

    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    suggested_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True, min_value=0,
    )
    #: معرّفاتُ خدمات الكتالوج — تُتحقَّق شركتُها في الخدمة، لا في الاستعلام هنا.
    services = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False,
    )


class ClientServiceWriteSerializer(serializers.Serializer):
    """إضافةُ خدمةٍ لزبون — والدوريةُ تُترك فارغةً ليُقترح ويُؤكَّد."""

    service = serializers.IntegerField(min_value=1)
    starts_on = serializers.DateField(required=False)
    responsible_from = serializers.DateField(required=False)
    frequency = serializers.ChoiceField(
        choices=CLIENT_SERVICE_FREQUENCY_CHOICES, required=False, allow_null=True,
    )


class ClientServiceFrequencyWriteSerializer(serializers.Serializer):
    """تغييرُ الدورية **من تاريخ** — والتاريخُ المكرَّر يُستبدل أو يُرفض في الخدمة."""

    frequency = serializers.ChoiceField(choices=CLIENT_SERVICE_FREQUENCY_CHOICES)
    effective_from = serializers.DateField()


class ClientServiceStopSerializer(serializers.Serializer):
    """إيقافُ خدمةٍ بتاريخ — الصفُّ يبقى، و`ends_on` يُكتب.

    **و`last_period_ours`**: «آخرُ فترةٍ علينا» — رفعُها تُسقط آخرَ فترةٍ في كل
    سلسلةٍ (لا تُولَّد، ويُسكَت المنتظِرُ منها)، والافتراضُ «علينا».
    """

    ends_on = serializers.DateField()
    last_period_ours = serializers.BooleanField(required=False, default=True)


class ApplyPackageSerializer(serializers.Serializer):
    package = serializers.IntegerField(min_value=1)


# ── الالتزامات والشغلات (#275) ───────────────────────────────────────────────
class ObligationSubmitSerializer(serializers.Serializer):
    """«انقدّم»: تاريخٌ اختياريّ (افتراضُه اليوم) ورقمُ تقديمٍ اختياريّ."""

    submitted_on = serializers.DateField(required=False)
    number = serializers.CharField(required=False, allow_blank=True, max_length=60)


class ObligationAmountSerializer(serializers.Serializer):
    """مبلغُ الالتزام واتجاهه — **مبلغٌ مسجَّلٌ في `AMOUNT_KEYS`**، والـview يقنّعه.

    `amount` **مطلوب**: المسحُ بـ`null` صريحاً، وجسمٌ لا مفتاحَ فيه (`{}`) 400 —
    وإلا مرّ طلبٌ لا يقول شيئاً فحُسب «نجاحاً» بلا أثر.
    """

    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=True, allow_null=True, min_value=0,
    )
    direction = serializers.ChoiceField(
        choices=OBLIGATION_DIRECTION_CHOICES, required=False, allow_blank=True,
    )


class ObligationClientPaidSerializer(serializers.Serializer):
    """«الزبون دفع» — خبرٌ عن الزبون، يُكتب في كلّ الحالات."""

    paid = serializers.BooleanField()


class TaskAssignSerializer(serializers.Serializer):
    """تحويلُ شغلةٍ لعضوٍ آخر — `null` يُعيدها إلى وراثة مسؤول الزبون."""

    assignee = serializers.IntegerField(required=True, allow_null=True, min_value=1)


class ClosePriorSerializer(serializers.Serializer):
    """«هدول انقدّموا قبل ما يجي علينا» — التاريخُ افتراضُه اليوم."""

    before = serializers.DateField(required=False)


# ── تعديل المكتب على اللائحة، والتمديد، والتزامات المكتب، والأحداث (#277) ────
#
# **الحدودُ هنا شكلُ الطلب لا قيمتُه**: المدى (1..31، ومدى أيام سطر الحدث) والرسائل و«كالمنصة» تُقرأ في
# الخدمة وحدها، فنداءٌ برمجيّ لا يمرّ بالمسلسِل يأخذ الرفضَ نفسه.
class RuleOverrideSerializer(serializers.Serializer):
    """تعديلُ سطرٍ: النظامُ والكودُ مطلوبان، والقيمُ الفارغة تعني «كالمنصة»."""

    system = serializers.CharField(max_length=2)
    code = serializers.SlugField(max_length=60)
    # بلا حدودٍ عدديّة: `rule_day` لسطر الحدث مدىً بالأيام (حتى 180) لا يومَ شهر،
    # والخدمةُ تعرف نوعَ السطر فتحكم.
    rule_day = serializers.IntegerField(required=False, allow_null=True)
    rule_month = serializers.IntegerField(required=False, allow_null=True)
    electronic_extension_days = serializers.IntegerField(
        required=False, allow_null=True,
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class RuleCodeSerializer(serializers.Serializer):
    """«رجّع للمنصة» و«أُبقي تاريخي»: السطرُ وحده، بلا قيم."""

    system = serializers.CharField(max_length=2)
    code = serializers.SlugField(max_length=60)


class CustomRuleWriteSerializer(serializers.Serializer):
    """التزامٌ خاص بالمكتب — والخدمةُ تُحلّ من كتالوج الشركة في الخدمة."""

    name = serializers.CharField(max_length=200)
    service = serializers.IntegerField(min_value=1)
    cadence = serializers.CharField(max_length=20)
    rule_kind = serializers.CharField(max_length=30)
    rule_day = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=31,
    )
    rule_month = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=12,
    )
    is_active = serializers.BooleanField(required=False)


class CustomRuleUpdateSerializer(serializers.Serializer):
    """تعديلُ التزام مكتبٍ بحقولٍ كلُّها اختيارية — والغيابُ لا يمسّ."""

    name = serializers.CharField(required=False, max_length=200)
    service = serializers.IntegerField(required=False, min_value=1)
    cadence = serializers.CharField(required=False, max_length=20)
    rule_kind = serializers.CharField(required=False, max_length=30)
    rule_day = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=31,
    )
    rule_month = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=12,
    )
    is_active = serializers.BooleanField(required=False)


class ObligationExtensionSerializer(serializers.Serializer):
    """«مدّد»: تاريخُ التمديد وملاحظتُه — والرفضُ الدلاليّ في الخدمة."""

    until = serializers.DateField()
    note = serializers.CharField(max_length=300)


class ClientEventSerializer(serializers.Serializer):
    """«صار حدث»: النوعُ والتاريخُ وملاحظةٌ اختيارية — والفعّالُ يُفحص في الخدمة."""

    kind = serializers.CharField(max_length=40)
    occurred_on = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


# ── قائمة الأوراق (#278) ─────────────────────────────────────────────────────
#
# **الحدودُ هنا شكلُ الطلب لا قيمتُه**: أسماءُ الحالات والقنوات وقيمُها تُقرأ في
# الخدمة وحدها، فنداءٌ برمجيّ لا يمرّ بالمسلسِل يأخذ الرفضَ نفسه.
class DocumentStatusSerializer(serializers.Serializer):
    """`{status, channel?}` — والقناةُ تُلزم لمن وصلت في الخدمة لا هنا."""

    status = serializers.CharField(max_length=20)
    channel = serializers.CharField(required=False, allow_blank=True, max_length=20)


class DefaultTrueBooleanField(serializers.BooleanField):
    """مربّعُ اختيارٍ **غائبٌ** في multipart يعني «نعم» — كـ`is_copy`.

    DRF يقرأ غيابَ المفتاح في نموذج HTML كـ`False` (`default_empty_html`)، وهذا
    الصفُّ يقلبه إلى `True`: الملفُّ المرفوعُ صورةُ عملٍ إلا أن يقول الموظف غيرَ
    ذلك صريحاً. و`false` المرسَلة تُقرأ `False` كالمعتاد.
    """

    default_empty_html = True


class DocumentFileUploadSerializer(serializers.Serializer):
    """ملفُّ ورقةٍ **مع حقول נספח ז الوصفية** — والرفعُ multipart.

    `file` وحده إلزاميّ: نوعُ المستند افتراضُه اسمُ الورقة، ورقمُ المُصدر وتاريخُ
    المستند ورقمُه وصفٌ يكتبه الموظف إن عرفه. و`is_copy` افتراضُه «صورة».
    """

    file = serializers.FileField()
    document_type = serializers.CharField(
        required=False, allow_blank=True, max_length=200,
    )
    issuer_registration = serializers.CharField(
        required=False, allow_blank=True, max_length=60,
    )
    document_date = serializers.DateField(required=False, allow_null=True)
    document_number = serializers.CharField(
        required=False, allow_blank=True, max_length=60,
    )
    is_copy = DefaultTrueBooleanField(required=False)


class DocumentItemChoiceSerializer(serializers.Serializer):
    """خيارُ بند: «ضمن القائمة» أو لا — كودُ البند يُتحقَّق في الخدمة."""

    item_code = serializers.SlugField(max_length=60)
    included = serializers.BooleanField()


class OfficeDocumentItemWriteSerializer(serializers.Serializer):
    """بندٌ يضيفه المكتب: اسمٌ ودوريةٌ وخدماتٌ — وشروطُ البطاقة تبقى فارغة."""

    system = serializers.CharField(max_length=2)
    name = serializers.CharField(max_length=200)
    cadence = serializers.CharField(max_length=20)
    service_codes = serializers.ListField(
        child=serializers.CharField(max_length=60), required=False,
    )
    is_active = serializers.BooleanField(required=False)


class OfficeDocumentItemUpdateSerializer(serializers.Serializer):
    """تعديلُ بند مكتبٍ بحقولٍ كلُّها اختيارية — والغيابُ لا يمسّ."""

    name = serializers.CharField(required=False, max_length=200)
    cadence = serializers.CharField(required=False, max_length=20)
    service_codes = serializers.ListField(
        child=serializers.CharField(max_length=60), required=False,
    )
    is_active = serializers.BooleanField(required=False)
