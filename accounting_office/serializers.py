"""مُسلسِلات مكتب المحاسبة — شكل الـAPI وحده، والحساب في الخدمات.

**لا قراءة إعداداتٍ هنا**: كل قيمةٍ فعليّة (نظام الزبون، إعداداته، بطاقته
بتسميات نظامه) تأتي من `accounting_office/services.py`. يحرس ذلك
`accounting_office/tests/test_settings_guard.py`.

**ومُسلسِلان للزبون لا واحد:** القائمة صفٌّ خفيف بلا بطاقة، وكلُّ صفوفها تقرأ
نظامها من `context["tax_systems"]` الذي يبنيه الـview باستعلامين — لا المحلّل
مرّتين لكل صف. والتفصيل وحده يحمل البطاقة كاملة.
"""
from rest_framework import serializers

from accounting_office import payments, services
from accounting_office.models import (
    APPOINTMENT_KIND_CHOICES,
    BOOK_ACCOUNT_TYPE_CHOICES,
    BOOK_ENTRY_KIND_CHOICES,
    BOOK_KIND_CHOICES,
    CLIENT_SERVICE_FREQUENCY_CHOICES,
    CONSENT_CHANNEL_LABELS,
    FEE_CADENCE_CHOICES,
    FEE_EXTRA_DESTINATION_CHOICES,
    FEE_PAYMENT_METHOD_CHOICES,
    ClientReminderRecipient,
    Contact,
    OBLIGATION_DIRECTION_CHOICES,
    OfficeClient,
    OfficeService,
    REMINDER_CHANNEL_CHOICES,
    REMINDER_CHANNEL_WHATSAPP,
    REMINDER_MANUAL_CHANNELS,
    REMINDER_TYPE_CHOICES,
)
from accounting_office.payments import INVOICE_STATE_CHOICES


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


class ClientDueFieldsMixin(serializers.Serializer):
    """«اللي عليه» وسطرُ العلم الضريبيّ على صفّ الزبون — من `payments` وحدها (#283).

    الحمولةُ المجمَّعة (`client_dues`) تُمرَّر في `context` من القائمة فتُقرأ
    الصفحةُ كلُّها باستعلامين لا استعلامين لكل صفّ؛ وحين تغيب (التفصيل وإنشاء
    زبونٍ واحد) تُحسب للصفّ المفرد. والقناعُ داخل `client_due_payload` نفسه.
    **وسطرُ العلم تحت `due` لا داخله**: يقرؤه من يعرض «عليه 500 [ضريبة 200]».
    """

    due = serializers.SerializerMethodField()
    tax_note = serializers.SerializerMethodField()

    def _payload(self, obj):
        dues = self.context.get("client_dues")
        if dues is not None:
            return dues.get(obj.pk, {})
        # ذاكرةُ الحمولة لكائنٍ واحد: الحقلان يقرآنها معاً فلا تُحسب مرّتين.
        cache = getattr(self, "_client_due_cache", None)
        if cache is None:
            cache = self._client_due_cache = {}
        if obj.pk not in cache:
            tenant = self.context.get("tenant") or obj.tenant
            request = self.context.get("request")
            user = getattr(request, "user", None)
            cache[obj.pk] = payments.client_due_payload(tenant, obj, user=user)
        return cache[obj.pk]

    def get_due(self, obj):
        return self._payload(obj).get("due")

    def get_tax_note(self, obj):
        return self._payload(obj).get("tax_note")


class OfficeClientListSerializer(
    ClientDueFieldsMixin,
    ResponsibleFieldsMixin, TaxSystemFieldsMixin, serializers.ModelSerializer,
):
    """صفُّ القائمة: بلا بطاقة، ونظامُه من الحساب الجماعيّ، و`due`/`tax_note` من الدالّة الواحدة."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OfficeClient
        fields = [
            "id", "name", "tax_file_number", "status", "status_label",
            "ended_on", "notes", "tax_system", "tax_system_label",
            "responsible_id", "responsible_name", "due", "tax_note",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class OfficeClientSerializer(
    ClientDueFieldsMixin,
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
            "tax_card", "responsible_id", "responsible_name", "due", "tax_note",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "ended_on", "responsible_id", "responsible_name",
            "created_at", "updated_at",
        ]


class ContactSerializer(serializers.ModelSerializer):
    language_label = serializers.CharField(source="get_language_display", read_only=True)
    consent_channel_label = serializers.SerializerMethodField()
    # `{id, name}` لا رقمُ المفتاح — الشكلُ نفسُه في `services.contact_consent_payload`
    # وتقرؤه الواجهةُ (`consent_withdrawn_by.name`). والـviews تُحمِّله بـ`select_related`.
    consent_withdrawn_by = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = [
            "id", "name", "phone", "language", "language_label",
            # #280/D2: الإذنُ يُقرأ مع الجهة، ويُكتب بفعله وحده (`consent/`)
            # فيمرّ بحارس الخدمة — كتابتُه هنا كانت تُسقط `consent_on`.
            "reminders_consent", "consent_types",
            "consent_on", "consent_channel", "consent_channel_label",
            "consent_withdrawn_on", "consent_withdrawn_by",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "reminders_consent", "consent_types", "consent_on", "consent_channel",
            "consent_withdrawn_on", "created_at", "updated_at",
        ]

    def get_consent_channel_label(self, contact) -> str:
        return CONSENT_CHANNEL_LABELS.get(contact.consent_channel, "")

    def get_consent_withdrawn_by(self, contact):
        if contact.consent_withdrawn_by_id is None:
            return None
        return {
            "id": contact.consent_withdrawn_by_id,
            "name": services.user_display_name(contact.consent_withdrawn_by),
        }


class ContactConsentSerializer(serializers.Serializer):
    """`{consent, types?, channel?}` — الأنواعُ والقناةُ يُتحقَّقان في الخدمة."""

    consent = serializers.BooleanField()
    types = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True,
    )
    channel = serializers.CharField(required=False, allow_blank=True, max_length=20)


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


# ── التذكيرات والرسائل (#280) ────────────────────────────────────────────────
class ReminderTemplateWriteSerializer(serializers.Serializer):
    """نصُّ بديلٍ لمكتب — الرموزُ يُتحقَّق منها في الخدمة (وهي التي تعرف المعتمد)."""

    body = serializers.CharField()


#: قنواتُ الأفعال كما تُعلَن في الـAPI — `sent` واتسابٍ وحدها، و`manual` تلفونٌ أو
#: زيارة. قناةٌ تُقبل في الشكل ثم تُرفض في الخدمة عيبُ إعلانٍ لا تحقّق.
_SENT_CHANNEL_CHOICES = [
    (channel, label)
    for channel, label in REMINDER_CHANNEL_CHOICES
    if channel == REMINDER_CHANNEL_WHATSAPP
]
_MANUAL_CHANNEL_CHOICES = [
    (channel, label)
    for channel, label in REMINDER_CHANNEL_CHOICES
    if channel in REMINDER_MANUAL_CHANNELS
]


class ReadyToSendItemSerializer(serializers.Serializer):
    """بندٌ في رسالةٍ: مَن، وأيّ نوع، وأيّ فترة — **بطرفَيها**.

    و`period_end` مطلوبةٌ لأن مفتاحَ العدّ `(period_start, period_end)`: القائمةُ
    السنوية تبدأ في 1 يناير كالشهرية، وبدون النهاية تُخلط أوراقُ السنة بالشهر.
    ورسالةُ «جاهز للإرسال» تحمل المفتاحين، فلا تخمينَ في الشاشة.
    """

    client_id = serializers.IntegerField(min_value=1)
    reminder_type = serializers.ChoiceField(choices=REMINDER_TYPE_CHOICES)
    period_start = serializers.DateField()
    period_end = serializers.DateField()


class ReadyToSendPayloadSerializer(serializers.Serializer):
    """قائمةُ «جاهز للإرسال» كما يخرجها `ready_to_send_payload` — **قراءةٌ وحدها**.

    شكلُ المورد المعلَن لجمعِه (GET وحده): فلا يُعلن الـ`OPTIONS` حمولةَ كتابةٍ
    لا تقبلها النقطة، وللأفعال الأربعة سيريالايزراتُها.
    """

    day = serializers.DateField(read_only=True)
    merge_daily = serializers.BooleanField(read_only=True)
    reminder_type = serializers.CharField(read_only=True, allow_null=True)
    messages = serializers.ListField(child=serializers.DictField(), read_only=True)
    placeholders = serializers.ListField(child=serializers.CharField(), read_only=True)


class ReadyToSendSentSerializer(serializers.Serializer):
    """«انبعثت»: جهةٌ ونصٌّ وبنودٌ — وصفٌّ لكل بندٍ بالنصّ نفسه.

    و`channel` قناةٌ واحدةٌ (`whatsapp`)، وفراغُه يعنيها: «انبعثت» إرسالٌ
    بالتطبيق، والتلفونُ والزيارة «كلّمناه» لا «انبعثت».
    """

    contact_id = serializers.IntegerField(min_value=1)
    body = serializers.CharField(allow_blank=True, required=False)
    channel = serializers.ChoiceField(
        choices=_SENT_CHANNEL_CHOICES, required=False, allow_blank=True,
    )
    items = ReadyToSendItemSerializer(many=True)


class ReadyToSendManualSerializer(serializers.Serializer):
    """«كلّمناه»: نفسُ البنود بقناةٍ يدوية — تلفونٌ أو زيارة."""

    contact_id = serializers.IntegerField(min_value=1)
    body = serializers.CharField(allow_blank=True, required=False)
    channel = serializers.ChoiceField(choices=_MANUAL_CHANNEL_CHOICES)
    items = ReadyToSendItemSerializer(many=True)


class ReadyToSendDismissSerializer(serializers.Serializer):
    """«شيل لهذه المرة»: بلا جهةٍ ولا نصّ — المستلِمُ يُحلّ في الخدمة."""

    items = ReadyToSendItemSerializer(many=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class ReminderPostponeWriteSerializer(serializers.Serializer):
    """«أجّل التذكير لتاريخ…» — و`until=null` صفٌّ يمسح التأجيل."""

    client_id = serializers.IntegerField(min_value=1)
    reminder_type = serializers.ChoiceField(choices=REMINDER_TYPE_CHOICES)
    until = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class ReminderLogSerializer(serializers.Serializer):
    """سطرُ السجلّ كما يخرجه `reminder_log_row` — **قراءةٌ وحدها**.

    هذا شكلُ نقطة السجلّ المعلَن، فلا يُعلن الـ`OPTIONS` حمولةَ كتابةٍ لا تقبلها
    النقطة: الصفُّ لا يُنشأ ولا يُعدَّل ولا يُحذف من الـAPI، والتصحيحُ فعلُ
    `undo` وحده. وكلُّ حقلٍ هنا `read_only` — بطاقةُ السجلّ لا تُكتب.
    """

    id = serializers.IntegerField(read_only=True)
    client = serializers.DictField(read_only=True)
    contact_id = serializers.IntegerField(read_only=True, allow_null=True)
    recipient_name = serializers.CharField(read_only=True)
    recipient_phone = serializers.CharField(read_only=True)
    reminder_type = serializers.CharField(read_only=True)
    reminder_type_label = serializers.CharField(read_only=True)
    kind = serializers.CharField(read_only=True)
    kind_label = serializers.CharField(read_only=True)
    channel = serializers.CharField(read_only=True)
    channel_label = serializers.CharField(read_only=True)
    body = serializers.CharField(read_only=True)
    period_start = serializers.CharField(read_only=True, allow_null=True)
    period_end = serializers.CharField(read_only=True, allow_null=True)
    period_label = serializers.CharField(read_only=True)
    subject = serializers.DictField(read_only=True)
    reason = serializers.CharField(read_only=True)
    reverts_id = serializers.IntegerField(read_only=True, allow_null=True)
    created_by = serializers.DictField(read_only=True, allow_null=True)
    created_at = serializers.CharField(read_only=True)


class OfficeHolidayWriteSerializer(serializers.Serializer):
    """عطلةُ مكتبٍ بيومها واسمها — والتكرارُ يرفضه القيدُ في القاعدة."""

    date = serializers.DateField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=200)

class ClientAppointmentWriteSerializer(serializers.Serializer):
    """حجزُ موعدٍ من ملفّ الزبون أو من التقويم (#281) — **بتاريخه ووقته**.

    و`kind` اختيارٌ من الأربعة كما يعرّفها النموذج لا نصٌّ حرّ، و`note` اختياريّة.
    ولا يُمرَّر `status`: الموعدُ يُحجز، والحالةُ تُكتب بأفعالها وحدها.
    """

    client_id = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(
        choices=[value for value, _label in APPOINTMENT_KIND_CHOICES],
    )
    scheduled_at = serializers.DateTimeField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class ClientAppointmentRescheduleSerializer(serializers.Serializer):
    """«أجّل»: وقتٌ جديد وملاحظةٌ اختياريّة — والصفُّ يبقى برقمه."""

    scheduled_at = serializers.DateTimeField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class ClientAppointmentConfirmSerializer(serializers.Serializer):
    """«ابعت تأكيد»: نصٌّ اختياريّ يغلِب نصَّ القالب — وما عداه يُبنى في الخدمة.

    والقناةُ ثابتةٌ هنا (واتساب) كسائر «انبعثت»، فلا حقلَ لها.
    """

    body = serializers.CharField(required=False, allow_blank=True)


class ClientBookWriteSerializer(serializers.Serializer):
    """إنشاءُ دفترِ زبون: الزبونُ ونوعُه — وتاريخُ الفتح اختياريٌّ (اليوم افتراضاً).

    **ولا حقلَ لطريقة الإدخال هنا**: تلك إعدادٌ يقرؤه المحلّل ويُخصَّص لكل زبون
    (`book_entry_method`)، لا عموداً في الدفتر يفترق عنه.
    """

    client_id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=[value for value, _label in BOOK_KIND_CHOICES])
    opened_on = serializers.DateField(required=False, allow_null=True)


class ClientBookKindWriteSerializer(serializers.Serializer):
    """تغييرُ نوع الدفتر — والقاعدةُ (د7) في الخدمة لا هنا."""

    kind = serializers.ChoiceField(choices=[value for value, _label in BOOK_KIND_CHOICES])


class BookAccountWriteSerializer(serializers.Serializer):
    """حسابٌ يضيفه المكتب لشجرة زبون — `is_system` يبقى `False` لكل ما يُضاف.

    و`account_type` اختيارٌ هنا لا نصٌّ حرّ: نوعٌ مخترَع يُردّ 400 بالشكل قبل أن
    يصل الخدمة، والقائمةُ من النماذج لا نسخةً ثانية.
    """

    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=200)
    parent_code = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=20,
    )
    account_type = serializers.ChoiceField(
        choices=[value for value, _label in BOOK_ACCOUNT_TYPE_CHOICES],
    )


class BookEntryLineWriteSerializer(serializers.Serializer):
    """بندٌ في حركة: الحسابُ بكوده، ومدينٌ أو دائن — لا الاثنان (الخدمةُ تفحص)."""

    account_code = serializers.CharField(max_length=20)
    debit = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True,
    )
    credit = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True,
    )
    side_party = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=200,
    )


class BookEntryWriteSerializer(serializers.Serializer):
    """حركةُ دفترٍ جديدة: تاريخُها ونوعُها وبنودُها، **وأوراقُها الواردة**.

    `documents` قائمةُ أوراقٍ لا ورقةً واحدة: طريقةُ «إدخال الشهر» تُدخل أوراقَ
    الشهر في حركةٍ واحدة، والربطُ يُقرأ لينتقل العكسُ بها إلى «للإدخال».
    """

    entry_date = serializers.DateField()
    kind = serializers.ChoiceField(
        choices=[value for value, _label in BOOK_ENTRY_KIND_CHOICES],
    )
    memo = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=300,
    )
    # الحدُّ يحرس `IN (…)` المقفول في الخدمة لا الاستعمال: أوراقُ شهرِ زبونٍ واحد
    # عشراتٌ لا مئات، وطلبٌ بآلاف المعرّفات يُرفض هنا 400 قبل أن يقفل صفّاً.
    documents = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
        max_length=100,
    )
    lines = BookEntryLineWriteSerializer(many=True)


class BookEntryReverseSerializer(serializers.Serializer):
    """حركةٌ عكسية: بيانٌ اختياريّ، وتاريخٌ يعود للأصل إن غاب."""

    memo = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=300,
    )
    entry_date = serializers.DateField(required=False, allow_null=True)


# ── الأتعاب: الاشتراك والمسودّات والاعتماد (#282) ────────────────────────────
#
# **المالُ هنا شكلُ الطلب لا حسابُه**: الحدودُ المعروضة (غيرُ سالبٍ، خانتان
# عشريتان) يُعيد `accounting_office/fees.py` فحصَها فتصِل الرفضُ نفسُه لنداءٍ
# برمجيٍّ لا يمرّ بالمسلسِل. و`amount` مسجَّلٌ في `AMOUNT_KEYS` كسائر مبالغ
# الموديول، فالقناعُ وحارسُ الكتابة يقرآن الثابتَ نفسه.
class FeeSubscriptionWriteSerializer(serializers.Serializer):
    """اشتراكٌ جديد **بتاريخ سريانه** — والتاريخُ المكرَّر يُرفض في الخدمة."""

    client = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    starts_on = serializers.DateField()
    cadence = serializers.ChoiceField(choices=FEE_CADENCE_CHOICES, required=False)
    currency = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    #: الإيقافُ يُكتب مستقبلاً أو يُترك فارغاً؛ والخدمةُ تفحص ترتيبَ طرفيه.
    paused_from = serializers.DateField(required=False, allow_null=True)
    paused_to = serializers.DateField(required=False, allow_null=True)
    ended_on = serializers.DateField(required=False, allow_null=True)


class FeeExtraServiceWriteSerializer(serializers.Serializer):
    """خدمةٌ إضافيةٌ نُفِّذت — ووجهتُها «مسودّة الشهر القادم» افتراضاً."""

    client = serializers.IntegerField(min_value=1)
    service_name = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    performed_on = serializers.DateField()
    draft = serializers.ChoiceField(
        choices=FEE_EXTRA_DESTINATION_CHOICES, required=False,
    )


class FeeServicePriceWriteSerializer(serializers.Serializer):
    """سعرُ خدمةِ زبونٍ: الخدمةُ بمعرّفها أو بالخدمة والزبون، والمبلغُ مبلَغ.

    **بديلان لا ثلاثة حقولٍ مطلوبة**: `client_service` معرّفُ صفّ خدمة الزبون
    (وهو ما تعرضه شاشةُ أ٢ بعد اختيار الزبون)، و`service` + `client` يُغنيان عنه
    في نداءٍ واحد. وأحدُ البديلين مطلوبٌ وإلا فالعنوان ناقص.
    """

    client_service = serializers.IntegerField(required=False, min_value=1)
    service = serializers.IntegerField(required=False, min_value=1)
    client = serializers.IntegerField(required=False, min_value=1)
    #: المبلغُ مبلغ: في `AMOUNT_KEYS`، والقناعُ والكتابةُ كسائر أسعار الموديول.
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)

    def validate(self, attrs):
        if attrs.get("client_service") is not None:
            return attrs
        if attrs.get("service") is not None and attrs.get("client") is not None:
            return attrs
        raise serializers.ValidationError({
            "client_service": "حدّد خدمةَ الزبون: بمعرّفها أو بالخدمة والزبون معاً.",
        })


class FeeDraftApproveSerializer(serializers.Serializer):
    """ملاحظةُ الاعتماد اختيارية — والمَن اعتمد ومتى يكتبهما الخادم."""

    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class FeeDraftRowSerializer(serializers.Serializer):
    """شكلُ مسودّةٍ كما تخرج — **قراءةٌ وحدها**، ومبالغُها تُقنَّع في الخدمة.

    يُعلَن لتقرأ `OPTIONS` شكلَ المورد بدل حمولةِ كتابةٍ لا تقبلها النقطة: لا
    `POST` على الجمع (التوليدُ في «حدّث المكتب») ولا تعديلَ ولا حذف.
    """

    id = serializers.IntegerField(read_only=True)
    client = serializers.DictField(read_only=True)
    year = serializers.IntegerField(read_only=True)
    month = serializers.IntegerField(read_only=True)
    period_label = serializers.CharField(read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
    )
    total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
    )
    #: #283: ما دُفع على المسودّة وما بقي منها — يُقنَّعان كسائر مبالغ الموديول.
    paid_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
    )
    remaining = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
    )
    state = serializers.CharField(read_only=True)
    state_label = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    status_label = serializers.CharField(read_only=True)
    generated_at = serializers.CharField(read_only=True)
    approved_by = serializers.DictField(read_only=True, allow_null=True)
    approved_at = serializers.CharField(read_only=True, allow_null=True)
    approved_note = serializers.CharField(read_only=True)
    lines = serializers.ListField(child=serializers.DictField(), read_only=True)


# ── فاتورة الأتعاب (#282، أ٢/١) ──────────────────────────────────────────────
#
# **الحقولُ الكتابيةُ ثلاثةٌ لا أكثر**: سببُ الإلغاء، ومبلغُ التصحيح وسببُه،
# ومبلغُ التكميلية وسببُها. ولا مُسلسِلَ إنشاءٍ: الفاتورةُ تُصدَر بالاعتماد وحده
# (`fees.approve_fee_draft`)، و`POST` على الجمع 405.
class FeeInvoiceCancelSerializer(serializers.Serializer):
    """سببُ الإلغاء اختياريّ — والتاريخُ ومَن ألغى يكتبهما الخادم."""

    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=300,
    )


class FeeInvoiceCreditNoteSerializer(serializers.Serializer):
    """إشعارٌ دائن: مبلغٌ موجبٌ ≤ إجمالي الفاتورة، وسببٌ **إلزاميّ**.

    و«إشعارٌ بلا سبب» ورقةٌ لا تقول شيئاً: النقصُ يُفسَّر أو يُرفض، والنفيُ
    وحده ليس بياناً محاسبياً (م.12 من تعليمات 25/2025).
    """

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    reason = serializers.CharField(allow_blank=False, max_length=300)


class FeeInvoiceSupplementarySerializer(serializers.Serializer):
    """فاتورةٌ تكميليةٌ للنقص: مبلغٌ موجبٌ وسببٌ اختياريّ."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=300,
    )


class FeeInvoiceRowSerializer(serializers.Serializer):
    """شكلُ فاتورةٍ كما تخرج — **قراءةٌ وحدها**، ومبالغُها تُقنَّع في الخدمة.

    `tax_total` مسجَّلٌ في `FEE_AMOUNT_KEYS` كـ`total`: من لا يرى المبالغ يقرأ
    `null` في الاثنين وفي كل سطرٍ تحتهما.
    """

    id = serializers.IntegerField(read_only=True)
    number = serializers.CharField(read_only=True)
    kind = serializers.CharField(read_only=True)
    kind_label = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    client = serializers.DictField(read_only=True)
    #: **`source_draft` لا `draft`** (#282/أ٢): المفتاحُ أثرٌ تاريخيّ لا قيدُ
    #: «ورقةٌ واحدة لكل مسودّة» — الإلغاءُ يعيد المسودّةَ فتُصدر ورقةً جديدة.
    source_draft = serializers.IntegerField(read_only=True, allow_null=True)
    related_invoice = serializers.IntegerField(read_only=True, allow_null=True)
    tax_system = serializers.CharField(read_only=True)
    total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
    )
    tax_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True,
    )
    external_number = serializers.CharField(read_only=True)
    issued_at = serializers.CharField(read_only=True)
    issued_by = serializers.DictField(read_only=True, allow_null=True)
    state = serializers.CharField(read_only=True)
    is_tax_invoice = serializers.BooleanField(read_only=True)
    cancelled_at = serializers.CharField(read_only=True, allow_null=True)
    cancelled_by = serializers.DictField(read_only=True, allow_null=True)
    cancel_reason = serializers.CharField(read_only=True)
    has_link = serializers.BooleanField(read_only=True)
    lines = serializers.ListField(child=serializers.DictField(), read_only=True)


# ── الدفعات و«اللي عليه» وكشف الحساب (#283) ──────────────────────────────────
#
# **الدفعةُ تُنشأ ولا تُعدَّل**: لا `PUT`/`PATCH`/`DELETE` في الـviewset، والشطبُ
# فعلٌ على المسودّة لا على الدفعة. والحدودُ المعروضة (أكبرُ من صفر) يُعيد
# `accounting_office/payments.py` فحصَها فيصل الرفضُ نفسُه لنداءٍ برمجيّ.
class FeePaymentAllocationWriteSerializer(serializers.Serializer):
    """تخصيصُ جزءٍ من الدفعة على مسودّةٍ معتمدة — الصريحُ يُلغي «الأقدم أولاً»."""

    draft = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class FeePaymentWriteSerializer(serializers.Serializer):
    """دفعةٌ جديدة — غيابُ `allocations` أو `null` ⇒ «الأقدم أولاً»، و`[]` ⇒ لا تخصيص.

    **والفرقُ مقصود**: `[]` تُسجّل دفعةً مقدَّمةً تبقى رصيداً دائناً خالصاً ولو
    كانت للزبون فواتيرُ مفتوحة، و`null` تكليفٌ للخادم بترتيب التخصيص.
    """

    client = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=FEE_PAYMENT_METHOD_CHOICES)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    paid_at = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)
    allocations = FeePaymentAllocationWriteSerializer(
        many=True, required=False, allow_null=True,
    )


class FeeWriteOffWriteSerializer(serializers.Serializer):
    """شطبُ متبقّي مسودّةٍ — **بسببٍ مكتوبٍ إلزاميّ**، ومبالغُه تُقنَّع في الخدمة."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    reason = serializers.CharField(max_length=300)


class FeeLedgerQuerySerializer(serializers.Serializer):
    """فلاترُ كشف الحساب — تُعلَن لـ`OPTIONS`؛ والقراءةُ تُصفّي في الاستعلام."""

    client = serializers.IntegerField(required=False, min_value=1)
    state = serializers.ChoiceField(choices=INVOICE_STATE_CHOICES, required=False)
    q = serializers.CharField(required=False, allow_blank=True)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1)


# ── المستندان (#283/ب): رابطُ إشعار القبض ورابطُ كشف الحساب ──────────────────
class FeeDocumentShareSerializer(serializers.Serializer):
    """مشاركةُ إشعار قبض — المدةُ اختياريّة، والغائبُ يأخذ الافتراض في `docshare`.

    **والرقمُ لا يُرسَل في الجسم**: الرابطُ لعنوان المستند لا لمحتواه، ومدّةٌ
    خارج المدد المعروضة يضبطها `docshare.create_share` إلى الافتراضية.
    """

    days = serializers.IntegerField(required=False, min_value=1, max_value=90)


class FeeStatementShareSerializer(serializers.Serializer):
    """مشاركةُ كشف حساب: الزبونُ إلزاميٌّ، والفترةُ اختياريّة (سنةُ اليوم افتراضاً)."""

    client = serializers.IntegerField(min_value=1)
    period_from = serializers.DateField(required=False)
    period_to = serializers.DateField(required=False)
