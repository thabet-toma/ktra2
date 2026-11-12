"""نماذج مكتب المحاسبة — زبون المكتب وبطاقته وجهاته وإعداداته (#271).

**زبون المكتب سجلٌّ يملكه المكتب** — `tenant` FK على كل نموذج. ليس `Partner`، ولا
شركةً على المنصّة، ولا صفّاً من طبقة المكتب القديمة (`PracticeClient`): المواصفة
(#258) تُحرِّر التصميم منها، فلا حقلَ ربطٍ بأيٍّ منها هنا.

**ولا حذف للزبون:** الحالتان `active`/`ended` وحدهما، و«منتهي» يبقى ببطاقته
وجهاته وملاحظاته، و`ended_on` تاريخُ وقوعٍ لا يُعاد كتابته إلا بمسحٍ صريح عند
الإعادة. لا `DELETE` في الـAPI أصلاً.

قيودٌ في القاعدة لا في العُرف:
- بطاقةٌ ضريبية واحدة لكل زبون (`OneToOne`).
- جهةٌ رئيسية واحدة على الأكثر لكل زبون — **بعمودٍ مُولَّدٍ وفهرسةٍ غير مشروطة**،
  لا `UniqueConstraint(condition=…)`: MySQL لا تدعم الفهارس الجزئية وتتجاهل
  الشرط **بصمت**، فيخضرّ الاختبار على SQLite ويغيب القيد في الإنتاج
  (`core/tests/test_conditional_uniqueness.py`). العمود يساوي الزبون حين
  `is_primary` و`NULL` حين لا، وMySQL تسمح بتكرار `NULL`.
- مستلِمٌ واحد لكل (زبون، نوع تذكير).
"""
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from accounting_office import settings_registry
from core.terminology import OFFICE_FEE_INVOICE_LABEL
#: أنواعُ الأحداث (#277) — تُعرَّف في السجلّ لأن إعداد `enabled_event_kinds` يقرأ
#: مفاتيحها، والسجلَّ لا يستورد النماذج (دَّورة). وتُعاد تصديراً هنا فتُقرأ من
#: النماذج كسائر ثوابت الموديول (`as` نفسَه = تصديرٌ مقصود لا استيرادٌ عابر).
from accounting_office.settings_registry import (
    EVENT_KIND_CHOICES,
    EVENT_KIND_LABELS as EVENT_KIND_LABELS,
    EVENT_KIND_WITHHOLDING as EVENT_KIND_WITHHOLDING,
    #: #280: أنواعُ التذكير الأربعة — في السجلّ للسبب نفسه: إعدادا
    #: `reminder_types_enabled` و`reminder_default_consent_types` يقرآنها.
    REMINDER_APPOINTMENT as REMINDER_APPOINTMENT,
    REMINDER_BALANCE as REMINDER_BALANCE,
    REMINDER_DEADLINE as REMINDER_DEADLINE,
    REMINDER_DOCUMENTS as REMINDER_DOCUMENTS,
    REMINDER_TYPE_CHOICES as REMINDER_TYPE_CHOICES,
    REMINDER_TYPE_LABELS as REMINDER_TYPE_LABELS,
    REMINDER_TYPES as REMINDER_TYPES,
)
from tenants.models import Currency, Tenant, UserCompanyMembership


def is_tenant_member(tenant_id, user_id) -> bool:
    """هل هذا المستخدم عضوٌ في هذه الشركة؟ — **قاعدةٌ واحدة** يقرؤها الاثنان.

    يستهلكها حارسُ النموذج (`OfficeClient._assert_responsible_is_member`) وحارسُ
    الخدمة (`accounting_office/services.py` — `_assert_member_of_tenant`)، فيبقى
    معنى «عضو» واحداً. نسخةٌ ثانية من الشرط تفترق عن الأولى عند أوّل تعديل: حارسٌ
    يقبل مسؤولاً ويرفضه الآخر.
    """
    if not tenant_id or not user_id:
        return False
    return UserCompanyMembership.objects.filter(
        tenant_id=tenant_id, user_id=user_id,
    ).exists()

# ── البطاقة الضريبية: اختياراتٌ لكل نظام ضريبي ──────────────────────────────
#
# تسمياتٌ لا مواعيد ولا نسب، فثوابتُ الكود مقبولة هنا (المعجم #254). المصدر
# البحثان `research/acct-tax-ps` و`research/acct-tax-il`. والمفاتيح **مشتركةٌ**
# بين النظامين حيث كان المعنى واحداً (`individual` · `company` · `partnership` ·
# `nonprofit` · `exempt`)، ومختلفةٌ حيث اختلف التصنيف: «مشتغل مرخّص» في فلسطين
# ليس «עוסק מורשה» حرفاً — الأول `licensed` والثاني `authorized`، لأن تبديل
# النظام يجب أن يُفرّغ ما لا معنى له في النظام الجديد لا أن يُلبسه معنىً آخر.
TAX_CARD_CHOICES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "PS": {
        "entity_type": [
            ("individual", "فرد / مؤسسة فردية"),
            ("partnership", "شركة عادية (تضامن)"),
            ("company", "شركة مساهمة"),
            ("nonprofit", "جمعية / غير ربحية"),
        ],
        "vat_classification": [
            ("licensed", "مشتغل مرخّص"),
            ("exempt", "مشتغل معفى"),
            ("unregistered", "غير مسجّل"),
        ],
    },
    "IL": {
        "entity_type": [
            ("individual", "יחיד — فرد"),
            ("partnership", "שותפות — شراكة"),
            ("company", "חברה בע\"מ — شركة"),
            ("nonprofit", "מלכ\"ר — غير ربحية"),
        ],
        "vat_classification": [
            ("authorized", "עוסק מורשה — مشتغل مرخّص"),
            ("exempt", "עוסק פטור — مشتغل معفى"),
            ("nonprofit", 'מלכ"ר — مؤسسة غير ربحية'),
        ],
    },
}


def _union_choices(field: str) -> list[tuple[str, str]]:
    """اتّحادُ الاختيارات بمفاتيحها — لِـ`choices=` في النموذج (أوّل تسميةٍ تفوز)."""
    merged: dict[str, str] = {}
    for system in TAX_CARD_CHOICES.values():
        for value, label in system[field]:
            merged.setdefault(value, label)
    return list(merged.items())


ENTITY_TYPE_CHOICES = _union_choices("entity_type")
VAT_CLASSIFICATION_CHOICES = _union_choices("vat_classification")


def tax_card_choices(tax_system: str | None, field: str) -> list[tuple[str, str]]:
    """اختيارات البطاقة لنظامٍ بعينه — ونظامٌ غير مختار يعني الاتّحاد كاملاً."""
    system = TAX_CARD_CHOICES.get(tax_system or "")
    if system is None:
        return _union_choices(field)
    return list(system[field])


def _fill_tenant_from_client(instance) -> None:
    """شركةُ الصفّ تتبع زبونَه: تُملأ إن غابت، و**تُرفض** إن خالفت.

    كانت القاعدة تعليقاً: `if client_id and tenant_id is None: fill` — وهي تقبل
    شركةً مخالفة بصمت فتنتج صفّاً يقرؤه مكتبٌ لا يملكه. الآن الملءُ عند الغياب
    وحده، والمخالفةُ `ValueError` تصل 500 لأنها خطأُ برمجةٍ لا خطأُ مدخلات —
    مسارُ الـAPI يُحقّق الشركة قبل الوصول إلى هنا.
    """
    if not instance.client_id:
        return
    expected = instance.client.tenant_id
    if instance.tenant_id is None:
        instance.tenant_id = expected
    elif instance.tenant_id != expected:
        raise ValueError(
            "شركةُ الصفّ تخالف شركة الزبون — لا يُكتب سجلٌّ عابرٌ للمكاتب.",
        )


class OfficeClient(models.Model):
    """منشأةٌ بملف ضريبي واحد (محل، شركة) — سجلٌّ يملكه المكتب."""

    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "نشط"),
        (STATUS_ENDED, "منتهي"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_clients",
        verbose_name="المكتب",
    )
    name = models.CharField(max_length=200, verbose_name="الاسم")
    # #272: الموظف المسؤول — **مسؤولٌ واحد لكل زبون**، وكلُّ شغلةٍ ترثه.
    # `SET_NULL` لا `CASCADE`: خروجُ الموظف من الشركة لا يمحو زبائنها؛ يصيرون
    # بلا مسؤولٍ حتى يُسندوا، ويبقى تاريخهم. والتحويلُ فعلٌ مُسجَّل لا كتابةٌ صامتة.
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_clients_responsible",
        verbose_name="الموظف المسؤول",
    )
    # #284: طرفُ الزبون في دفاتر المكتب — **المفتاحُ الوحيد** لطرفٍ موجود، ولا
    # مطابقةَ بالاسم: لا فرادةَ على `Partner.name`، ومطابقةُ الاسم تخلط زبونين
    # متشابهين فيصير رصيدُ أحدهما على الآخر. `SET_NULL` لأن حذفَ الطرف لا يحذف
    # زبوناً (تاريخُ المكتب أطول من شجرة حسابات) — ويُنشأ طرفٌ جديد عند الحاجة.
    partner = models.ForeignKey(
        "partners.Partner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_clients",
        verbose_name="الطرف في الدفاتر",
    )
    tax_file_number = models.CharField(
        max_length=60, blank=True, default="", verbose_name="رقم الملف الضريبي",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE, verbose_name="الحالة",
    )
    ended_on = models.DateField(
        null=True, blank=True, verbose_name="تاريخ الإنهاء",
    )
    notes = models.TextField(blank=True, default="", verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "زبون مكتب"
        verbose_name_plural = "زبائن المكتب"
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="office_client_tenant_status"),
            # «زبائن هذا الموظف» هو استعلامُ كلِّ قائمةٍ لعضوٍ لا يرى زبائن غيره.
            models.Index(fields=["tenant", "responsible"], name="office_client_tenant_resp"),
        ]
        constraints = [
            # الحالة وتاريخها لا يفترقان: «منتهٍ» عليه تاريخ، و«نشط» بلا تاريخ.
            models.CheckConstraint(
                condition=(
                    models.Q(status="active", ended_on__isnull=True)
                    | models.Q(status="ended", ended_on__isnull=False)
                ),
                name="office_client_ended_on_matches_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # الحارسُ على **كتابة المسؤول** لا على كل حفظ: موظّفٌ يخرج من المكتب
        # (تُحذف عضويّته) يبقى `responsible` على زبائنه حتى يُسندوا — وحارسٌ على
        # كل حفظ كان يمنع إنهاء زبونٍ أو تعديل ملاحظاته بسبب عضويّةٍ قديمة.
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "responsible" in update_fields:
            self._assert_responsible_is_member()
        super().save(*args, **kwargs)

    def _assert_responsible_is_member(self) -> None:
        """المسؤولُ عضوٌ في شركة الزبون — حارسُ النموذج بعد حارس الخدمة.

        الخدمةُ تردّ 400 بالسبب، وهذا يغلق مسار `save()` **وحده**: مسؤولٌ من خارج
        الشركة يجعل «زبائني» صفوفاً لا يراها أحدٌ في المكتب ولا يراها هو.
        و`QuerySet.update()` لا يمرّ بالنموذج فلا يحرسه هذا — إصلاحٌ جماعيٌّ مباشر
        على الجدول مسؤوليةُ من يكتبه.
        """
        if not self.responsible_id or not self.tenant_id:
            return
        if not is_tenant_member(self.tenant_id, self.responsible_id):
            raise ValueError(
                "الموظف المسؤول ليس عضواً في شركة الزبون — لا يُسند زبونٌ لغير عضوه.",
            )


class TaxCard(models.Model):
    """البطاقة الضريبية: واحدةٌ لكل زبون، تُنشأ معه.

    **يوم الراحة وطريقة التقديم ليسا حقلين هنا**: هما إعدادان
    (`rest_days` و`filing_method`) يُخصَّصان للزبون فوق إعداد المكتب، وتعرضهما
    الشاشة كأيّ تخصيصٍ آخر. حقلٌ هنا كان سيصنع نسخةً ثانية من القيمة تفترق عن
    إعداد المكتب بصمت.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="office_tax_cards",
        verbose_name="المكتب",
    )
    client = models.OneToOneField(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="tax_card",
        verbose_name="الزبون",
    )
    entity_type = models.CharField(
        max_length=20, choices=ENTITY_TYPE_CHOICES, blank=True, default="",
        verbose_name="نوع الكيان",
    )
    vat_classification = models.CharField(
        max_length=20, choices=VAT_CLASSIFICATION_CHOICES, blank=True, default="",
        verbose_name="تصنيف ق.م",
    )
    annual_sales = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="المبيعات السنوية",
    )
    has_employees = models.BooleanField(default=False, verbose_name="له موظفون")
    #: #279/D7: التسميةُ المعروضة «عدد العاملين» — الحقلُ يبقى `employees_count`.
    employees_count = models.PositiveSmallIntegerField(
        default=0, verbose_name="عدد العاملين",
    )
    is_self_employed = models.BooleanField(
        default=False, verbose_name="עצמאי يدفع ביטוח לאומי",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "بطاقة ضريبية"
        verbose_name_plural = "البطاقات الضريبية"

    def __str__(self) -> str:
        return f"بطاقة {self.client_id}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


# ── الموافقة على التذكير (#280/D2) ──────────────────────────────────────────
#
# **الإذنُ يُسجَّل بكيفه لا بمفتاحٍ مفتوح**: المكتب يسأل «بتحب نذكّرك؟» فيُكتب
# الجوابُ وتاريخُه وطريقُه (حكيٌّ أو ورقٌ أو واتساب) — فحين يقول الزبون «أنا ما
# وافقت» يوجد سطرٌ يقول متى وكيف. وهذه قناةُ **الإذن** لا قناةُ الإرسال:
# `ReminderLog.channel` يقول كيف ذهبت الرسالة فعلاً.
CONSENT_CHANNEL_TALK = "talk"
CONSENT_CHANNEL_PAPER = "paper"
CONSENT_CHANNEL_WHATSAPP = "whatsapp"
CONSENT_CHANNEL_CHOICES: list[tuple[str, str]] = [
    (CONSENT_CHANNEL_TALK, "حكي"),
    (CONSENT_CHANNEL_PAPER, "ورق"),
    (CONSENT_CHANNEL_WHATSAPP, "واتساب"),
]
CONSENT_CHANNEL_LABELS: dict[str, str] = dict(CONSENT_CHANNEL_CHOICES)


def _default_consent_types() -> list[str]:
    """أنواعُ التذكير كلُّها افتراضاً — **نسخةٌ جديدة** لا قائمةً مشتركة تُعدَّل."""
    return list(REMINDER_TYPES)


class Contact(models.Model):
    """شخصٌ يحكي معه المكتب — يملكه المكتب، ويُربط بأكثر من زبون.

    **والتذكيرُ بإذنه (#280/D2)**: `reminders_consent` ما يقوله هو، و`consent_types`
    ما وافق عليه من الأنواع، و`consent_on` و`consent_channel` كيف ومتى أذن،
    و`consent_withdrawn_on`/`consent_withdrawn_by` متى ومَن سحب. **والسحبُ لا
    يمحو الإذن**: يبقى تاريخُ الإذن قارئاً بجانب تاريخ السحب، فالمكتب يعرف كم
    تذكيراً أُرسل قبل أن يتغيّر رأيُه. وجهةٌ بلا إذنٍ (أو نوعُها ليس في
    `consent_types`) لا تدخل قائمة «جاهز للإرسال» أبداً.
    """

    LANGUAGE_ARABIC = "ar"
    LANGUAGE_HEBREW = "he"
    LANGUAGE_CHOICES = [
        (LANGUAGE_ARABIC, "عربي"),
        (LANGUAGE_HEBREW, "عبري"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_contacts",
        verbose_name="المكتب",
    )
    name = models.CharField(max_length=200, verbose_name="الاسم")
    phone = models.CharField(max_length=40, blank=True, default="", verbose_name="الهاتف")
    language = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES, default=LANGUAGE_ARABIC, verbose_name="اللغة",
    )
    #: #280/D2: الموافقةُ على التذكير — الافتراضُ «نعم» لأن الجهةَ تُسجَّل في
    #: المكتب لهذا الغرض، والرفضُ فعلٌ صريح يُسجَّل بتاريخه.
    reminders_consent = models.BooleanField(
        default=True, verbose_name="موافق على التذكير",
    )
    consent_types = models.JSONField(
        default=_default_consent_types, verbose_name="الأنواع الموافق عليها",
    )
    consent_on = models.DateField(null=True, blank=True, verbose_name="تاريخ الموافقة")
    consent_channel = models.CharField(
        max_length=20,
        choices=CONSENT_CHANNEL_CHOICES,
        blank=True,
        default="",
        verbose_name="كيف أذن",
    )
    consent_withdrawn_on = models.DateField(
        null=True, blank=True, verbose_name="تاريخ سحب الموافقة",
    )
    consent_withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_consent_withdrawals",
        verbose_name="سحبها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "جهة اتصال"
        verbose_name_plural = "جهات الاتصال"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    def allows_reminder(self, reminder_type: str) -> bool:
        """هل يوافق هذا الشخص على هذا النوع؟ — السؤالُ الوحيد الذي تسأله القائمة."""
        return self.reminders_consent and reminder_type in (self.consent_types or ())


class ClientContact(models.Model):
    """ربطُ جهةٍ بزبون: رئيسية؟ — والجهة نفسها قد تكون لأكثر من زبون."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_contacts",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="contact_links",
        verbose_name="الزبون",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="client_links",
        verbose_name="جهة الاتصال",
    )
    is_primary = models.BooleanField(default=False, verbose_name="رئيسية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الربط")

    #: معرّف الزبون **حين تكون رئيسية** وإلا `NULL` — فتُفرَض «واحدةٌ لا غير»
    #: في MySQL فعلاً، لا بقيدٍ مشروطٍ تتجاهله.
    primary_client_key = models.GeneratedField(
        expression=models.Case(
            models.When(is_primary=True, then=models.F("client")),
            output_field=models.IntegerField(),
        ),
        output_field=models.IntegerField(),
        db_persist=True,
        verbose_name="مفتاح الجهة الرئيسية",
    )

    class Meta:
        verbose_name = "ربط جهة بزبون"
        verbose_name_plural = "روابط الجهات بالزبائن"
        ordering = ["-is_primary", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "contact"], name="uniq_client_contact",
            ),
            models.UniqueConstraint(
                fields=["primary_client_key"], name="uniq_primary_contact_per_client",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}←{self.contact_id}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        # رباطٌ بين زبون شخصٍ من مكتبٍ آخر يقطع «من نكلّم» بلا أن يقول شيئاً:
        # الرابطُ يُقرأ من مكتب الزبون، والشخصُ يُرسَل إليه من مكتبٍ غيره.
        if self.client_id and self.contact_id:
            if self.client.tenant_id != self.contact.tenant_id:
                raise ValueError(
                    "جهةُ الاتصال من مكتبٍ آخر — لا يُربط بها زبونُ هذا المكتب.",
                )
        super().save(*args, **kwargs)


class ClientReminderRecipient(models.Model):
    """مستلِمُ نوع تذكير لزبون — وغياب الصفّ يعني **الجهة الرئيسية**.

    والأنواعُ الأربعة **معرَّفةٌ أعلى الملفّ** (من `settings_registry`) لأن
    `Contact.consent_types` يقرأ قائمتَها قبل هذا النموذج؛ وهذه أسماءٌ مصدَّرةٌ
    هنا فلا يفترق تعريفا نوعٍ واحد.
    """

    REMINDER_DOCUMENTS = REMINDER_DOCUMENTS
    REMINDER_DEADLINE = REMINDER_DEADLINE
    REMINDER_BALANCE = REMINDER_BALANCE
    REMINDER_APPOINTMENT = REMINDER_APPOINTMENT
    REMINDER_TYPE_CHOICES = REMINDER_TYPE_CHOICES
    REMINDER_TYPES: tuple[str, ...] = REMINDER_TYPES

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_reminder_recipients",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="reminder_recipients",
        verbose_name="الزبون",
    )
    reminder_type = models.CharField(
        max_length=20, choices=REMINDER_TYPE_CHOICES, verbose_name="نوع التذكير",
    )
    client_contact = models.ForeignKey(
        ClientContact,
        on_delete=models.CASCADE,
        related_name="reminder_assignments",
        verbose_name="الجهة المستلِمة",
    )

    class Meta:
        verbose_name = "مستلِم تذكير"
        verbose_name_plural = "مستلِمو التذكيرات"
        constraints = [
            models.UniqueConstraint(
                fields=["client", "reminder_type"], name="uniq_client_reminder_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}:{self.reminder_type}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        # المستلِمُ لا يُعيَّن إلا رابطاً **لهذا الزبون**: رابطُ زبونٍ آخر يجعل
        # «من نكلّم» اسمَ شخصٍ لا علاقة له بالزبون المعنيّ.
        if self.client_id and self.client_contact_id:
            if self.client_contact.client_id != self.client_id:
                raise ValueError(
                    "المستلِمُ جهةٌ غير مربوطةٍ بهذا الزبون — لا يُعيَّن رابطُ زبونٍ آخر.",
                )
        super().save(*args, **kwargs)


# ── التذكيرات والرسائل (#280) ────────────────────────────────────────────────
#
# **نصٌّ واحدٌ يُرسَل، ومصدرُه اثنان**: افتراضيُّ المنصّة في الكود
# (`REMINDER_DEFAULT_TEXTS`) يُشحَن مع النظام، وبديلُ المكتب في
# `ReminderTemplate` يغلبه. والرمزُ الوحيد المعتمد ستة:
# `{client_name}` `{period}` `{due_date}` `{amount}` `{missing_list}` `{office_name}`
# — ونصٌّ يحمل غيرها يُرفَض عند الحفظ باسمه، لا يُقبل ثم يفشل عند الإرسال.
REMINDER_PLACEHOLDERS: tuple[str, ...] = (
    "client_name", "period", "due_date", "amount", "missing_list", "office_name",
)

#: النصوصُ المشحونة — لكل نوعٍ عربيٌّ وعبريٌّ (بحث #256 §5). **عربيٌّ وعبريٌّ
#: قالبان لا واحد**: النبرةُ الشاميّة البسيطة في الأول والعبريةُ القصيرة في الثاني.
REMINDER_DEFAULT_TEXTS: dict[str, dict[str, str]] = {
    REMINDER_DOCUMENTS: {
        "ar": (
            "أهلاً {client_name}،\n"
            "لما نجهّز {period} ناقصنا منك: {missing_list}.\n"
            "لو بتقدر تبعتلنا إياهم قبل {due_date} بنكون خلّصنا بأسرع وقت،\n"
            "وإذا في شي مش واضح خبرنا.\n"
            "شكراً — {office_name}"
        ),
        "he": (
            "שלום {client_name},\n"
            "כדי שנוכל להכין את {period} חסרים לנו: {missing_list}.\n"
            "נשמח לקבל אותם עד {due_date},\n"
            "ואם משהו לא ברור — דברו איתנו.\n"
            "תודה, {office_name}"
        ),
    },
    #: (ب) في البحث ينادي الموعدَ باسمه (`{deadline_name}`) — وهذا الرمزُ خارج
    #: الستّة المعتمدة، فالنصُّ المشحون يقول «موعد التقديم» — ومولّدُ النوع في
    #: `accounting_office/appointments.py` (#281).
    REMINDER_DEADLINE: {
        # **سطرٌ لكل قيمةٍ لا جملةٌ تبتلعها**: البندُ يظهر بمبلغٍ بلا أوراقٍ ناقصة
        # وبأوراقٍ بلا مبلغ، وجملةُ «بدنا نستلم منك {missing_list} قبل…» تُقرأ
        # «منك  قبل» بفراغٍ مزدوجٍ وكلمةٍ معلَّقة. والقيمةُ الغائبةُ تُنطق «ولا شي»
        # في `services._reminder_render_values` بلغة المستلِم.
        "ar": (
            "أهلاً {client_name}،\n"
            "بذكّرك إنّ موعد التقديم عن {period} هو {due_date}.\n"
            "أوراق ناقصة: {missing_list}\n"
            "مبلغ مستحقّ: {amount}\n"
            "إذا في عائق خبرنا من اليوم لنلحق.\n"
            "{office_name}"
        ),
        "he": (
            "שלום {client_name},\n"
            "תזכורת: המועד להגשה של {period} הוא {due_date}.\n"
            "מסמכים חסרים: {missing_list}\n"
            "יתרה לתשלום: {amount}\n"
            "אם יש משהו תקוע — דברו איתנו היום כדי שנספיק.\n"
            "{office_name}"
        ),
    },
    REMINDER_BALANCE: {
        "ar": (
            "أهلاً {client_name}،\n"
            "على حساب {period} عندك {amount} مستحقة،\n"
            "آخر موعد للسداد {due_date}.\n"
            "بنستلم كاش أو تحويل أو شيك، وإذا في استفسار خبرنا.\n"
            "شكراً — {office_name}"
        ),
        "he": (
            "שלום {client_name},\n"
            "יתרת החובה שלך עבור {period} היא {amount},\n"
            "המועד האחרון לתשלום: {due_date}.\n"
            "אפשר לשלם במזומן, בהעברה או בצ'ק. לכל שאלה — אנחנו כאן.\n"
            "תודה, {office_name}"
        ),
    },
    #: (د) تذكيرُ موعد: نصٌّ قصيرٌ محايدٌ بالنبرة نفسها — ومولّدُه
    #: `appointment_reminder_candidates` في `accounting_office/appointments.py` (#281).
    REMINDER_APPOINTMENT: {
        "ar": (
            "أهلاً {client_name}،\n"
            "بذكّرك بموعدك مع المكتب يوم {due_date}.\n"
            "إذا الموعد مش مناسب خبرنا من اليوم نغيّره.\n"
            "{office_name}"
        ),
        "he": (
            "שלום {client_name},\n"
            "תזכורת לפגישה במשרד ביום {due_date}.\n"
            "אם המועד לא מתאים — דברו איתנו ונשנה אותו.\n"
            "{office_name}"
        ),
    },
}

REMINDER_LANGUAGE_CHOICES: list[tuple[str, str]] = list(Contact.LANGUAGE_CHOICES)
REMINDER_LANGUAGES: tuple[str, ...] = tuple(key for key, _label in REMINDER_LANGUAGE_CHOICES)


#: **ما يُسجَّل في السجلّ** (#280/D4): أربعةُ أنواعٍ لا تُعدَّل ولا تُحذف.
#: `sent` و`manual` يعدّان في الإيقاع، و`dismissed` يُعيد المؤقّت ولا يُعدّ،
#: و`undo` صفٌّ جديدٌ يشير إلى ما يُبطله — فالتصحيحُ إضافةٌ لا محو.
REMINDER_KIND_SENT = "sent"
REMINDER_KIND_MANUAL = "manual"
REMINDER_KIND_DISMISSED = "dismissed"
REMINDER_KIND_UNDO = "undo"
REMINDER_KIND_CHOICES: list[tuple[str, str]] = [
    (REMINDER_KIND_SENT, "انبعتت"),
    (REMINDER_KIND_MANUAL, "كلّمناه"),
    (REMINDER_KIND_DISMISSED, "شيل لهذه المرة"),
    (REMINDER_KIND_UNDO, "ما انبعتت"),
]
REMINDER_KIND_LABELS: dict[str, str] = dict(REMINDER_KIND_CHOICES)
#: ما **يُعدّ** في الإيقاع — و`dismissed` و`undo` خارجَه عمداً.
REMINDER_COUNTED_KINDS: tuple[str, ...] = (REMINDER_KIND_SENT, REMINDER_KIND_MANUAL)
#: ما **يُعيد المؤقّت**: كلُّ صفٍّ صدر فعلاً (إرسالاً أو تنحيةً).
REMINDER_TIMER_KINDS: tuple[str, ...] = (
    REMINDER_KIND_SENT, REMINDER_KIND_MANUAL, REMINDER_KIND_DISMISSED,
)

REMINDER_CHANNEL_WHATSAPP = "whatsapp"
REMINDER_CHANNEL_PHONE = "phone"
REMINDER_CHANNEL_IN_PERSON = "in_person"
REMINDER_CHANNEL_CHOICES: list[tuple[str, str]] = [
    (REMINDER_CHANNEL_WHATSAPP, "واتساب"),
    (REMINDER_CHANNEL_PHONE, "تلفون"),
    (REMINDER_CHANNEL_IN_PERSON, "بالزيارة"),
]
REMINDER_CHANNEL_LABELS: dict[str, str] = dict(REMINDER_CHANNEL_CHOICES)
#: قناتا «كلّمناه» — الإرسالُ بالتطبيق ليس يدوياً، والواتسابُ ليس «كلّمناه».
REMINDER_MANUAL_CHANNELS: tuple[str, ...] = (
    REMINDER_CHANNEL_PHONE, REMINDER_CHANNEL_IN_PERSON,
)


class ReminderTemplate(models.Model):
    """بديلُ المكتب عن نصّ المنصّة — صفٌّ لكل (نوع، لغة)، وغيابُه يعني الافتراضي.

    **والحذفُ هو «ارجع للافتراضي»**: لا يُكتب الافتراضيُّ في الجدول مكان البديل،
    فتصحيحُ نصٍّ في الكود لا يصل مكتباً جمّده صفٌّه. وهذا منعُ النمط نفسه الذي
    تمنعه `reset_office_setting`.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_reminder_templates",
        verbose_name="المكتب",
    )
    reminder_type = models.CharField(
        max_length=20, choices=REMINDER_TYPE_CHOICES, verbose_name="نوع التذكير",
    )
    language = models.CharField(
        max_length=2, choices=REMINDER_LANGUAGE_CHOICES, verbose_name="اللغة",
    )
    body = models.TextField(verbose_name="النص")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_reminder_templates",
        verbose_name="عدّله",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "نص تذكير"
        verbose_name_plural = "نصوص التذكيرات"
        ordering = ["reminder_type", "language"]
        constraints = [
            # فرادةٌ **غير مشروطة**: بديلٌ واحد لكل نوعٍ ولغة في المكتب.
            models.UniqueConstraint(
                fields=["tenant", "reminder_type", "language"],
                name="uniq_reminder_template",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reminder_type}/{self.language}"


class ReminderLog(models.Model):
    """سجلُّ تذكيرٍ أُرسل أو نُحّي أو صُحِّح — **إلحاقيّ لا يُعدَّل ولا يُحذف**.

    **واللقطةُ فيه**: `recipient_name` و`recipient_phone` نسخةُ ما كان وقت
    الإرسال، فتغييرُ الهاتف بعدها لا يعيد كتابة التاريخ. و`body` نصُّ ما ذهب
    فعلاً — فما أُرسل يُقرأ بعد سنة كما أُرسل.

    **والتصحيحُ صفٌّ جديد** (`undo` يشير بـ`reverts` إلى ما يُبطله) لا محوٌ
    للصفّ: «ما انبعتت» خبرٌ يُضاف، والصفُّ الأصلِيُّ يبقى أثراً. والعدّ في
    الإيقاع يستثني المُبطَل — فالتصحيحُ يُنقص العدّاد ولا يشطب السطر.

    و`client` على `PROTECT` كسائر ما لا يُمحى تاريخُه: زبونٌ له سجلُّ تذكير لا
    يُحذف. و`contact` على `SET_NULL` لأن حذف الجهة لا يمحو ما أُرسل إليها —
    اللقطةُ تحفظ الاسم والهاتف.
    """

    KIND_SENT = REMINDER_KIND_SENT
    KIND_MANUAL = REMINDER_KIND_MANUAL
    KIND_DISMISSED = REMINDER_KIND_DISMISSED
    KIND_UNDO = REMINDER_KIND_UNDO
    CHANNEL_WHATSAPP = REMINDER_CHANNEL_WHATSAPP
    CHANNEL_PHONE = REMINDER_CHANNEL_PHONE
    CHANNEL_IN_PERSON = REMINDER_CHANNEL_IN_PERSON

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_reminder_logs",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="reminder_logs",
        verbose_name="الزبون",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reminder_logs",
        verbose_name="الجهة",
    )
    recipient_name = models.CharField(
        max_length=200, blank=True, default="", verbose_name="اسم المستلِم",
    )
    recipient_phone = models.CharField(
        max_length=40, blank=True, default="", verbose_name="هاتف المستلِم",
    )
    reminder_type = models.CharField(
        max_length=20, choices=REMINDER_TYPE_CHOICES, verbose_name="نوع التذكير",
    )
    kind = models.CharField(
        max_length=20, choices=REMINDER_KIND_CHOICES, verbose_name="نوع الصفّ",
    )
    channel = models.CharField(
        max_length=20,
        choices=REMINDER_CHANNEL_CHOICES,
        blank=True,
        default="",
        verbose_name="القناة",
    )
    #: نصُّ ما أُرسل — فارغٌ في التنحية والتصحيح.
    body = models.TextField(blank=True, default="", verbose_name="النص المرسل")
    #: بدايةُ الفترة ونهايتُها — فارغتان في نوعٍ لا فترةَ له (موعد، حساب).
    period_start = models.DateField(null=True, blank=True, verbose_name="بداية الفترة")
    period_end = models.DateField(null=True, blank=True, verbose_name="نهاية الفترة")
    #: تفصيلُ المرجع: أكوادُ بنود الأوراق التي كانت ناقصة وقت الإرسال.
    subject = models.JSONField(default=dict, blank=True, verbose_name="التفصيل")
    reason = models.TextField(blank=True, default="", verbose_name="السبب")
    reverts = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reverted_by",
        verbose_name="يبطل",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_reminder_logs",
        verbose_name="سجّله",
    )
    #: معرّفُ الدفعة: كلُّ صفوف نداءٍ واحدٍ تحمل القيمة نفسها، فيُعاد قراءتها بعد
    #: `bulk_create` — MySQL لا يُرجع المفاتيح منه (SQLite يُرجعها فيُخفي ذلك).
    batch = models.UUIDField(
        default=uuid4, editable=False, db_index=True, verbose_name="الدفعة",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "سجل تذكير"
        verbose_name_plural = "سجلات التذكيرات"
        ordering = ["-created_at", "-id"]
        indexes = [
            # القائمةُ والعدّ يقرآن بـ(الزبون، النوع، بداية الفترة) دائماً.
            models.Index(
                fields=["tenant", "client", "reminder_type", "period_start"],
                name="office_reminder_log_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.client_id}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class ReminderPostpone(models.Model):
    """«أجّل التذكير لتاريخ…» — والساري **أحدثُ صفٍّ** لكل (زبون، نوع).

    سجلٌّ لا حقل: التأجيلُ يُكتب صفّاً بتاريخه وسببه، و`until=None` صفٌّ يمسح
    التأجيل. فيُقرأ «إلى متى تؤجَّل هذه الزوجة؟» من آخر صفٍّ وحده، ويبقى تاريخُ
    التأجيلات كلِّها مكتوباً.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_reminder_postpones",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="reminder_postpones",
        verbose_name="الزبون",
    )
    reminder_type = models.CharField(
        max_length=20, choices=REMINDER_TYPE_CHOICES, verbose_name="نوع التذكير",
    )
    until = models.DateField(null=True, blank=True, verbose_name="حتى تاريخ")
    reason = models.CharField(
        max_length=300, blank=True, default="", verbose_name="السبب",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_reminder_postpones",
        verbose_name="أجّله",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "تأجيل تذكير"
        verbose_name_plural = "تأجيلات التذكيرات"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["tenant", "client", "reminder_type"],
                name="office_reminder_postpone_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}:{self.reminder_type}→{self.until}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class OfficeHoliday(models.Model):
    """عطلةٌ في يومٍ بعينه — **لا تقويمَ عطلٍ وطنيّ يُخترَع** (#280/D8).

    المكتبُ يعطّل يومَه بنفسه (عيدٌ وطنيّ أو عطلةُ المكتب)، والمحرّكُ لا يعرف
    مناسباتٍ في الكود. والتذكيرُ لا يُلغى بيوم العطلة: يُحسَب عند القراءة فيظهر
    في أوّل يومٍ مسموح بعده.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_holidays",
        verbose_name="المكتب",
    )
    date = models.DateField(verbose_name="اليوم")
    name = models.CharField(max_length=200, blank=True, default="", verbose_name="العطلة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عطلة مكتب"
        verbose_name_plural = "عطل المكتب"
        ordering = ["-date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "date"], name="uniq_office_holiday_day",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date}:{self.name}"


# ── المواعيد مع الزبون (#281) ────────────────────────────────────────────────
#
# **الموعدُ حجزُ موظّفٍ لا حجزُ زبون**: يُسجَّل من ملفّ الزبون ومن التقويم،
# ويُحمل بتاريخه **ووقته** — «زيارة الثلاثاء 10:30» لا «الثلاثاء»؛ فقياسُ
# «حلّ الموعد» بالساعة يفرّق موعدَي العاشرة والثانية في اليوم نفسه.
APPOINTMENT_KIND_VISIT = "visit"
APPOINTMENT_KIND_CALL = "call"
APPOINTMENT_KIND_SIGNATURE = "signature"
APPOINTMENT_KIND_PAPERS = "papers"
APPOINTMENT_KIND_CHOICES: list[tuple[str, str]] = [
    (APPOINTMENT_KIND_VISIT, "زيارة"),
    (APPOINTMENT_KIND_CALL, "مكالمة"),
    (APPOINTMENT_KIND_SIGNATURE, "توقيع"),
    (APPOINTMENT_KIND_PAPERS, "استلام أوراق"),
]
APPOINTMENT_KIND_LABELS: dict[str, str] = dict(APPOINTMENT_KIND_CHOICES)

#: **ولا حذف**: الإلغاءُ يكتب حالةً، والصفُّ يبقى أثراً — كسائر ما لا يُمحى هنا.
APPOINTMENT_STATUS_SCHEDULED = "scheduled"
APPOINTMENT_STATUS_DONE = "done"
APPOINTMENT_STATUS_CANCELLED = "cancelled"
APPOINTMENT_STATUS_CHOICES: list[tuple[str, str]] = [
    (APPOINTMENT_STATUS_SCHEDULED, "محجوز"),
    (APPOINTMENT_STATUS_DONE, "صار"),
    (APPOINTMENT_STATUS_CANCELLED, "ملغى"),
]
APPOINTMENT_STATUS_LABELS: dict[str, str] = dict(APPOINTMENT_STATUS_CHOICES)

#: الحالةُ الوحيدة التي تُذكَّر وتُؤكَّد: ما صار لا يُذكَّر، وما أُلغي لا يعود.
APPOINTMENT_OPEN_STATUSES: tuple[str, ...] = (APPOINTMENT_STATUS_SCHEDULED,)


class ClientAppointment(models.Model):
    """موعدٌ بين المكتب وزبونه: نوعُه ووقتُه وحالتُه — **بهوية المكتب والزبون**.

    **و`confirmed_at` وقتُ تسجيل التأكيد لا وقتُ إرسالٍ في الشبكة**: التأكيدُ
    يخرج رسالةَ تذكيرٍ بالسجلّ القائم (`ReminderLog` بنوع `appointment`، د4)،
    وهذا الحقلُ ختمُ الفعل عليه — فبُقّ «ابعت تأكيد» يعود صفراً بعد أن يُسجَّل.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_appointments",
        verbose_name="المكتب",
    )
    #: `PROTECT` لا `CASCADE`: تاريخُ موعدِ زبونٍ لا يُحذف بحذفِه — والحذفُ أصلاً
    #: ممنوعٌ هنا، والإلغاءُ يكتب حالة.
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="الزبون",
    )
    kind = models.CharField(
        max_length=20,
        choices=APPOINTMENT_KIND_CHOICES,
        default=APPOINTMENT_KIND_VISIT,
        verbose_name="نوع الموعد",
    )
    scheduled_at = models.DateTimeField(verbose_name="وقت الموعد")
    note = models.CharField(
        max_length=300, blank=True, default="", verbose_name="ملاحظة",
    )
    status = models.CharField(
        max_length=20,
        choices=APPOINTMENT_STATUS_CHOICES,
        default=APPOINTMENT_STATUS_SCHEDULED,
        verbose_name="الحالة",
    )
    confirmed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت التأكيد",
    )
    cancelled_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت الإلغاء",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_appointments",
        verbose_name="سجّله",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "موعد زبون"
        verbose_name_plural = "مواعيد الزبائن"
        ordering = ["scheduled_at", "id"]
        indexes = [
            # ملفُّ الزبون يقرأ مواعيده مرتَّبةً بوقتها دائماً.
            models.Index(
                fields=["tenant", "client", "scheduled_at"],
                name="office_appt_client_time",
            ),
            # «مواعيد اليوم» والتقويم يقرآن المكتب كلَّه بمدىً — لا زبوناً زبوناً.
            models.Index(
                fields=["tenant", "scheduled_at"], name="office_appt_tenant_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}@{self.scheduled_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class OfficeSettingValue(models.Model):
    """قيمة إعدادٍ على مستوى المكتب — `(tenant, key) → value`.

    **لا يُقرأ هذا الجدول خارج `accounting_office/services.py`**: المحلّل وحده
    يعرف ترتيب المستويات. يحرسه
    `accounting_office/tests/test_settings_guard.py`.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_setting_values",
        verbose_name="المكتب",
    )
    key = models.CharField(max_length=60, verbose_name="مفتاح الإعداد")
    value = models.JSONField(verbose_name="القيمة")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "قيمة إعداد مكتب"
        verbose_name_plural = "قيم إعدادات المكاتب"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uniq_office_setting"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.key}"


class ClientSettingOverride(models.Model):
    """تخصيص إعدادٍ لزبون — `(tenant, client, key) → value`.

    القيمة تغلب إعداد المكتب وتُغلب بتخصيص الشغلة، والترتيب كلّه في المحلّل.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_setting_overrides",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="setting_overrides",
        verbose_name="الزبون",
    )
    key = models.CharField(max_length=60, verbose_name="مفتاح الإعداد")
    value = models.JSONField(verbose_name="القيمة")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "تخصيص إعداد لزبون"
        verbose_name_plural = "تخصيصات إعدادات الزبائن"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client", "key"], name="uniq_client_setting_override",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}:{self.key}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


# ── الخدمات والباقات (#273) ──────────────────────────────────────────────────
#
# **الخدمةُ ما يقدّمه المكتب، وخدمةُ الزبون ما اشتراه زبونٌ بعينه** (المعجم #254):
# الأولى صفٌّ في كتالوج المكتب يُفعَّل ويُضاف ولا يُحذف بعد استعماله، والثانية صفٌّ
# مؤرَّخ `من ← إلى` لا يُحذف أصلاً — الإيقاف يكتب `ends_on` ويُبقي التاريخ.
#
# **والدوريةُ مؤرَّخة**: تغييرُها من نيسان لا يمسّ آذار، لأنّ `ClientServiceFrequency`
# يضيف صفّاً جديداً ولا يعدّل القديم. الدوريةُ في يومٍ ما = الصفُّ ذو أكبر
# `effective_from <= اليوم`، وتقرؤه دالّةٌ واحدة (`services.frequency_on`).

#: أكوادُ الخدمات الخمس الافتراضية — **عقودٌ ثابتة** يقرؤها الاقتراحُ وتذاكر
#: الالتزامات القادمة، فلا تتغيّر بتسميةٍ في الشاشة. والتسميةُ `name` تُعدَّل.
DEFAULT_SERVICES: tuple[tuple[str, str], ...] = (
    ("bookkeeping", "مسك دفاتر"),
    ("vat", "قيمة مضافة"),
    ("payroll", "رواتب"),
    ("annual_accounts", "ميزانية وتدقيق"),
    ("consulting", "استشارات ومعاملات"),
)

#: أكوادُ الاقتراح المعروفة — كلُّ كودٍ آخر (خدمةٌ أضافها المكتب) «عند الطلب».
SERVICE_CODE_BOOKKEEPING = "bookkeeping"
SERVICE_CODE_VAT = "vat"
SERVICE_CODE_PAYROLL = "payroll"
SERVICE_CODE_ANNUAL_ACCOUNTS = "annual_accounts"
SERVICE_CODE_CONSULTING = "consulting"

FREQUENCY_MONTHLY = "monthly"
FREQUENCY_BIMONTHLY = "bimonthly"
FREQUENCY_QUARTERLY = "quarterly"
FREQUENCY_ANNUAL = "annual"
FREQUENCY_ON_DEMAND = "on_demand"

CLIENT_SERVICE_FREQUENCY_CHOICES: list[tuple[str, str]] = [
    (FREQUENCY_MONTHLY, "شهري"),
    (FREQUENCY_BIMONTHLY, "كل شهرين"),
    (FREQUENCY_QUARTERLY, "ربع سنوي"),
    (FREQUENCY_ANNUAL, "سنوي"),
    (FREQUENCY_ON_DEMAND, "عند الطلب"),
]

FREQUENCY_KEYS: tuple[str, ...] = tuple(
    value for value, _label in CLIENT_SERVICE_FREQUENCY_CHOICES
)
FREQUENCY_LABELS: dict[str, str] = dict(CLIENT_SERVICE_FREQUENCY_CHOICES)

#: حالتا خدمة الزبون — نصّان من الخادم وحده، والواجهة ترسمهما كما وصلا.
CLIENT_SERVICE_STATUS_ACTIVE = "active"
CLIENT_SERVICE_STATUS_STOPPED = "stopped"
CLIENT_SERVICE_STATUS_LABELS: dict[str, str] = {
    CLIENT_SERVICE_STATUS_ACTIVE: "نشطة",
    CLIENT_SERVICE_STATUS_STOPPED: "موقوفة",
}

#: سقوفٌ ضريبية **مؤرَّخة** — بياناتُ منصّةٍ واحدةٌ لكل المكاتب، لا رقمٌ في الكود
#: ولا قيمةُ إعدادٍ لمكتب. سنةٌ بلا صفٍّ تأخذ آخر سقفٍ سابق وتقول «تقديري».
THRESHOLD_KIND_VAT_MONTHLY_REPORTING = "vat_monthly_reporting"
THRESHOLD_KIND_VAT_EXEMPT_DEALER = "vat_exempt_dealer"
#: #274: سقفُ التقرير المفصّل 874 — تجاوزُه يُلزم التقرير المفصّل، والرقمُ منشورٌ
#: في إشعار רשות המסים لا في الكود.
THRESHOLD_KIND_VAT_DETAILED_REPORTING = "vat_detailed_reporting"
THRESHOLD_KIND_CHOICES: list[tuple[str, str]] = [
    (THRESHOLD_KIND_VAT_MONTHLY_REPORTING, "سقف التقرير الدوري لق.م"),
    (THRESHOLD_KIND_VAT_EXEMPT_DEALER, "سقف עוסק פטור"),
    (THRESHOLD_KIND_VAT_DETAILED_REPORTING, "سقف التقرير المفصّل 874"),
]


def _tax_system_choices() -> list[tuple[str, str]]:
    """تسمياتُ النظام الضريبي من **سجلّ الإعدادات** وحده — لا نسخةً ثانية هنا."""
    definition = settings_registry.SETTINGS_REGISTRY["tax_system"]
    return [
        (value, definition.labels.get(value, value))
        for value in definition.choices
    ]


TAX_SYSTEM_CHOICES: list[tuple[str, str]] = _tax_system_choices()


def _fill_tenant_from_client_service(instance) -> None:
    """شركةُ صفّ الدورية تتبع خدمةَ زبونها — الملءُ عند الغياب والرفضُ عند المخالفة.

    `ClientServiceFrequency` لا زبونَ لها مباشرةً، فقاعدتُها كقاعدة النماذج الابنة
    الأخرى: تمتلئ من أبيها ولا تُكتب لشركةٍ مخالفة.
    """
    if not instance.client_service_id:
        return
    expected = instance.client_service.tenant_id
    if instance.tenant_id is None:
        instance.tenant_id = expected
    elif instance.tenant_id != expected:
        raise ValueError(
            "شركةُ صفّ الدورية تخالف شركة خدمة الزبون — لا يُكتب سجلٌّ عابرٌ للمكاتب.",
        )


class OfficeService(models.Model):
    """خدمةٌ في كتالوج المكتب — تسميةٌ وكودٌ وحالةُ تفعيلٍ وترتيب.

    **الكودُ عقدٌ لا تسمية**: الخمسةُ الافتراضية أكوادُها ثابتة (`DEFAULT_SERVICES`)
    لأنّ اقتراحَ الدورية وتذاكرَ الالتزامات تقرؤها، وتغييرُ اسمٍ في الشاشة لا يغيّر
    سلوكها. والخدمةُ التي يضيفها المكتب `is_builtin=False` بكودٍ مولَّد.

    **ولا حذفَ لخدمةٍ استُعملت**: `ClientService.service` على `PROTECT`، والـAPI لا
    يعرف `DELETE` هنا أصلاً — التعطيلُ (`is_active=False`) هو ما يُخفيها من الإضافة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_services",
        verbose_name="المكتب",
    )
    code = models.SlugField(max_length=60, verbose_name="الكود")
    name = models.CharField(max_length=120, verbose_name="الاسم")
    is_active = models.BooleanField(default=True, verbose_name="مفعّلة")
    is_builtin = models.BooleanField(default=False, verbose_name="من الافتراضي")
    position = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "خدمة مكتب"
        verbose_name_plural = "خدمات المكتب"
        ordering = ["position", "name", "id"]
        constraints = [
            # فرادةٌ **غير مشروطة** — الشرطُ في `UniqueConstraint` تتجاهله MySQL
            # بصمت فتمرّ الهجرة ويغيب القيد في الإنتاج.
            models.UniqueConstraint(
                fields=["tenant", "code"], name="uniq_office_service_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class ServicePackage(models.Model):
    """باقةٌ جاهزة: خدماتُ المكتب وسعرٌ مقترحٌ اختياري.

    **مبلغٌ من أوّله**: `suggested_price` مُسجَّلٌ في `AMOUNT_KEYS` ويمرّ بـ
    `mask_amounts`، وكتابتُه بلا `office.amounts.view` ⇒ 403. والباقةُ **قالب**:
    تطبيقُها ينسخ خدماتِ الزبون ولا يربطها بها.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_service_packages",
        verbose_name="المكتب",
    )
    name = models.CharField(max_length=200, verbose_name="الاسم")
    suggested_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="السعر المقترح",
    )
    services = models.ManyToManyField(
        OfficeService,
        blank=True,
        related_name="packages",
        verbose_name="الخدمات",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "باقة خدمات"
        verbose_name_plural = "باقات الخدمات"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name


class ClientService(models.Model):
    """خدمةٌ لزبونٍ بعينه: من–لتاريخ، ومن أيّ فترةٍ المكتب مسؤول.

    **لا حذف**: الإيقافُ يكتب `ends_on` ويُبقي الصفَّ في التاريخ — «رواتب من آذار»
    سؤالٌ له جوابٌ بعد أن تتوقّف الخدمة.

    **و`responsible_from` يُخزَّن فقط** (#273): أولُ يومٍ في الفترة التي يبدأ المكتب
    مسؤوليته منها. لا توليدَ التزاماتٍ ولا فترات هنا — تلك تذاكرُها.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_services",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="services",
        verbose_name="الزبون",
    )
    service = models.ForeignKey(
        # `PROTECT` لا `CASCADE`: حذفُ خدمةٍ من الكتالوج كان يمحو تاريخ كل زبونٍ
        # اشتراها. والتعطيلُ هو الطريق، والـAPI لا يعرف `DELETE` على الكتالوج.
        OfficeService,
        on_delete=models.PROTECT,
        related_name="client_services",
        verbose_name="الخدمة",
    )
    starts_on = models.DateField(verbose_name="تبدأ في")
    ends_on = models.DateField(null=True, blank=True, verbose_name="تنتهي في")
    responsible_from = models.DateField(verbose_name="المكتب مسؤول من فترة")
    #: «آخرُ فترةٍ علينا؟» (#275) — رفعُها عند الإيقاف تُسقط آخرَ فترةٍ في كلِّ
    #: سلسلةٍ من الالتزامات، وتمنع توليدَها في «حدّث المكتب». الافتراضُ «علينا».
    last_period_ours = models.BooleanField(
        default=True, verbose_name="آخر فترة علينا",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "خدمة زبون"
        verbose_name_plural = "خدمات الزبائن"
        ordering = ["starts_on", "id"]
        indexes = [
            models.Index(
                fields=["tenant", "client"], name="office_client_service_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}:{self.service_id}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)

    def status_on(self, day) -> str:
        """حالةُ الخدمة **في يومٍ ما**: موقوفةٌ ⇔ انتهت قبل ذلك اليوم.

        الإيقافُ بتاريخٍ مستقبليّ لا يجعلها موقوفةً اليوم: من كتب «تنتهي في 31/12»
        يعمل عليها حتى ذلك اليوم. ولذلك لا تُشتقّ الحالةُ من `ends_on is None` —
        ذلك كان يقول «موقوفة» فورَ الكتابة، ويسمح بفترةٍ متداخلة.
        """
        if self.ends_on is not None and self.ends_on < day:
            return CLIENT_SERVICE_STATUS_STOPPED
        return CLIENT_SERVICE_STATUS_ACTIVE


class ClientServiceFrequency(models.Model):
    """دوريةُ خدمة الزبون **بتاريخ سريان** — صفٌّ لكل تغيير، ولا تعديلَ لما قبله.

    فرادةُ `(client_service, effective_from)` تجعل «غيّرها من نيسان» كتابةً واحدةً في
    يومٍ واحد: الطلبُ المكرَّر يستبدل صفَّه المستقبليّ وحده، أو يُرفض إن كان ماضياً.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_service_frequencies",
        verbose_name="المكتب",
    )
    client_service = models.ForeignKey(
        ClientService,
        on_delete=models.CASCADE,
        related_name="frequencies",
        verbose_name="خدمة الزبون",
    )
    frequency = models.CharField(
        max_length=20,
        choices=CLIENT_SERVICE_FREQUENCY_CHOICES,
        verbose_name="الدورية",
    )
    effective_from = models.DateField(verbose_name="سارية من")
    #: القيمةُ المقترحة وقت الكتابة — للتمييز بين «قبلها الموظف» و«غيّرها».
    suggested = models.CharField(
        max_length=20,
        choices=CLIENT_SERVICE_FREQUENCY_CHOICES,
        blank=True,
        default="",
        verbose_name="المقترحة وقتها",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_service_frequencies",
        verbose_name="أنشأها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الكتابة")

    class Meta:
        verbose_name = "دورية خدمة زبون"
        verbose_name_plural = "دوريات خدمات الزبائن"
        ordering = ["effective_from", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client_service", "effective_from"],
                name="uniq_client_service_frequency_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_service_id}@{self.effective_from}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client_service(self)
        super().save(*args, **kwargs)


class TaxThreshold(models.Model):
    """سقفٌ ضريبيّ **مؤرَّخ** — بياناتُ منصّةٍ لا بياناتُ مكتب.

    **بلا `tenant` عمداً**: السقفُ واحدٌ لكل المكاتب كاللائحة القادمة في #274،
    ونسخةٌ لكل شركة تعني سقفين مختلفين لنفس السنة في منصّةٍ واحدة. ولذلك لا يمرّ
    `amount` بقناع المبالغ: ليس مبلغَ زبون، بل رقمٌ منشورٌ في `source_url`.
    """

    KIND_VAT_MONTHLY_REPORTING = THRESHOLD_KIND_VAT_MONTHLY_REPORTING
    KIND_VAT_EXEMPT_DEALER = THRESHOLD_KIND_VAT_EXEMPT_DEALER
    KIND_VAT_DETAILED_REPORTING = THRESHOLD_KIND_VAT_DETAILED_REPORTING

    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    kind = models.CharField(
        max_length=40, choices=THRESHOLD_KIND_CHOICES, verbose_name="نوع السقف",
    )
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="السقف",
    )
    #: المصدرُ الرسميّ المنشور — بلا رابطٍ يصير الرقم رأياً.
    source_url = models.URLField(max_length=300, verbose_name="المصدر")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإدخال")

    class Meta:
        verbose_name = "سقف ضريبي"
        verbose_name_plural = "السقوف الضريبية"
        ordering = ["tax_system", "kind", "year"]
        constraints = [
            models.UniqueConstraint(
                fields=["tax_system", "kind", "year"], name="uniq_tax_threshold",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tax_system}/{self.kind}/{self.year}"


# ── لائحة المواعيد (#274) ────────────────────────────────────────────────────
#
# **اللائحةُ بياناتُ منصّةٍ بلا `tenant`** — كـ`TaxThreshold`: الموعدُ واحدٌ لكل
# المكاتب، ونسخةٌ لكل شركة تعني موعدين مختلفين لنفس القانون في منصّةٍ واحدة.
#
# **والنسخُ مؤرَّخة**: سنةٌ تُنشر لها لائحةٌ جديدة تُضاف بـ`version` أعلى ولا
# تُعدَّل النسخةُ القائمة — والنسخةُ السارية هي أكبر `version`، والسنةُ بلا نسخةٍ
# تأخذ آخر سنةٍ سابقة وتُعلَن «تقديرية» (انظر `services.schedule_for`).
#
# **ولا تاريخَ قانونيّاً في الكود**: كلُّ يومٍ وكلُّ شهرٍ يُقرأ من صفٍّ هنا. يحرسه
# `accounting_office/tests/test_deadlines.py` بمسح `ast` على `deadlines.py`.
REST_DAY_POLICY_WARN = "warn"
REST_DAY_POLICY_POSTPONE_CLIENT = "postpone_client"
REST_DAY_POLICY_CHOICES: list[tuple[str, str]] = [
    (REST_DAY_POLICY_WARN, "تنبيه بلا زحزحة"),
    (REST_DAY_POLICY_POSTPONE_CLIENT, "تأجيل بعد يوم راحة الزبون"),
]

#: دورياتُ السطر — **أسماءٌ لعائلةٍ واحدة**: `monthly`/`quarterly`/`annual` هي قيمُ
#: `FREQUENCY_*` نفسها، فلا عائلتان لثوابتِ القيمة الواحدة تفترقان عند أول تعديل.
#: و`service` وحدها زيادةٌ هنا: «يتبع دورية خدمة الزبون».
CADENCE_SERVICE = "service"
CADENCE_MONTHLY = FREQUENCY_MONTHLY
CADENCE_QUARTERLY = FREQUENCY_QUARTERLY
CADENCE_ANNUAL = FREQUENCY_ANNUAL
#: #277: «كل شهرين» — دوريةٌ قائمة في `FREQUENCY_*`، أُضيفت هنا لأن التزامَ
#: المكتب يختارها. و`event` ليست دوريةَ توليدٍ: سطرُ الحدث يُولَّد من الحدث وحده.
CADENCE_BIMONTHLY = FREQUENCY_BIMONTHLY
CADENCE_EVENT = "event"
#: #279: «نصف سنوي» — **دوريةُ سطرٍ في اللائحة لا دوريةَ خدمة**: `טופס 126
#: חציוני` يستحق مرّتين في السنة (يناير–يونيو ثم السنة كلها) ولا يُنتظر من
#: الزبون أن يشترك في خدمةٍ نصف سنوية. فلا تُضاف إلى `FREQUENCY_*`.
CADENCE_SEMIANNUAL = "semiannual"
DEADLINE_CADENCE_CHOICES: list[tuple[str, str]] = [
    (CADENCE_SERVICE, "يتبع دورية خدمة الزبون"),
    (CADENCE_MONTHLY, "شهري"),
    (CADENCE_BIMONTHLY, "كل شهرين"),
    (CADENCE_QUARTERLY, "ربع سنوي"),
    (CADENCE_SEMIANNUAL, "نصف سنوي"),
    (CADENCE_ANNUAL, "سنوي"),
    (CADENCE_EVENT, "حدث — يُولَّد عند تسجيله لا دورياً"),
]

RULE_KIND_DAY_OF_NEXT_MONTH = "day_of_next_month"
RULE_KIND_END_OF_PERIOD = "end_of_period"
RULE_KIND_MONTH_DAY_NEXT_YEAR = "month_day_next_year"
#: #277: `legal_date = period_end + rule_day أيام` — قاعدةُ سطر الحدث: اقتطاعٌ
#: بتاريخ X يستحق خلال ثلاثين يوماً منه.
RULE_KIND_DAYS_AFTER_EVENT = "days_after_event"
RULE_KIND_CHOICES: list[tuple[str, str]] = [
    (RULE_KIND_DAY_OF_NEXT_MONTH, "يوم في الشهر التالي لنهاية الفترة"),
    (RULE_KIND_END_OF_PERIOD, "آخر يوم في الفترة"),
    (RULE_KIND_MONTH_DAY_NEXT_YEAR, "يوم في السنة التالية لنهاية الفترة"),
    (RULE_KIND_DAYS_AFTER_EVENT, "عدد أيام بعد الحدث"),
]
#: أنواعُ القاعدة التي يختارها المكتب لالتزامه الخاص (#277) — الثلاثةُ الدوريّة
#: وحدها: قاعدةُ «بعد الحدث» لا معنى لها في التزامٍ لا حدثَ له. والمصدرُ
#: `RULE_KIND_CHOICES` نفسه، فلا تسميتان لنوعٍ واحد.
OFFICE_CUSTOM_RULE_KIND_CHOICES: list[tuple[str, str]] = [
    (key, label) for key, label in RULE_KIND_CHOICES
    if key != RULE_KIND_DAYS_AFTER_EVENT
]
#: دورياتُ التزام المكتب (#277) — بلا `event`: التزامُ المكتب دوريٌّ يُولَّد،
#: والحدثُ يُسجَّل من ملفّ الزبون فيأخذ سطرَ اللائحة لا قاعدةَ مكتب. و«نصف سنوي»
#: (#279) دوريةُ **سطرٍ منشورٍ في المنصة** لا دوريةَ مكتبٍ يختارها — خارج القائمة.
OFFICE_CUSTOM_RULE_CADENCE_CHOICES: list[tuple[str, str]] = [
    (key, label) for key, label in DEADLINE_CADENCE_CHOICES
    if key not in (CADENCE_EVENT, CADENCE_SEMIANNUAL)
]

#: مفاتيح شروط السطر المسموحة — **وحدها**: مفتاحٌ آخر يرفعه `clean()`، فالشروطُ
#: تُقرأ من اللائحة ولا تُخترَع في الكود. و`annual_sales_above` قيمتُه اسمُ
#: `kind` في `TaxThreshold` (لا رقماً)، فيُقرأ السقفُ المنشور لا يُحفَر.
CONDITION_VAT_CLASSIFICATION_IN = "vat_classification_in"
CONDITION_ENTITY_TYPE_IN = "entity_type_in"
CONDITION_HAS_EMPLOYEES = "has_employees"
CONDITION_IS_SELF_EMPLOYED = "is_self_employed"
CONDITION_ANNUAL_SALES_ABOVE = "annual_sales_above"
CONDITION_KEYS: frozenset[str] = frozenset({
    CONDITION_VAT_CLASSIFICATION_IN,
    CONDITION_ENTITY_TYPE_IN,
    CONDITION_HAS_EMPLOYEES,
    CONDITION_IS_SELF_EMPLOYED,
    CONDITION_ANNUAL_SALES_ABOVE,
})

#: عددُ أشهر كلِّ دورية في التقويم — محاذاةُ الفترات تقرؤه
#: (`deadlines.periods_for` و`deadlines.service_periods`). **ليس هنا تاريخاً
#: قانونياً**: القانونُ في اللائحة، وعددُ الأشهر في الدورية نفسها. و`service`
#: صفرٌ لأنها تُقرأ من دورية خدمة الزبون المؤرَّخة. و`on_demand` صفرٌ لأنها لا
#: تولّد فترة.
#:
#: والمفاتيحُ من عائلة `FREQUENCY_*` وحدها (و`CADENCE_*` أسماءٌ لها) كي لا تحمل
#: القيمةَ الواحدة عائلتان.
CADENCE_SPAN_MONTHS: dict[str, int] = {
    CADENCE_SERVICE: 0,
    CADENCE_EVENT: 0,
    FREQUENCY_MONTHLY: 1,
    FREQUENCY_BIMONTHLY: 2,
    FREQUENCY_QUARTERLY: 3,
    # #279: نصفُ السنة — يناير–يونيو ثم يوليو–ديسمبر (حزمةٌ محاذاةٌ للتقويم).
    CADENCE_SEMIANNUAL: 6,
    FREQUENCY_ANNUAL: 12,
    FREQUENCY_ON_DEMAND: 0,
}


class DeadlineSchedule(models.Model):
    """نسخةُ لائحة المواعيد لسنةٍ ونظام — بمصدرها وتاريخ نشرها.

    **النسخةُ لا تُعدَّل**: تصحيحُ لائحةٍ منشورة يُضاف بـ`version` أعلى، فيبقى
    ما حُسب على القديمة قابلاً للتفسير.
    """

    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    version = models.PositiveSmallIntegerField(default=1, verbose_name="النسخة")
    #: الرابطُ الرسميّ المنشور — بلا مصدرٍ يصير الموعدُ رأياً.
    source_url = models.URLField(max_length=300, verbose_name="المصدر")
    published_on = models.DateField(verbose_name="تاريخ النشر")
    rest_day_policy = models.CharField(
        max_length=20,
        choices=REST_DAY_POLICY_CHOICES,
        default=REST_DAY_POLICY_WARN,
        verbose_name="سياسة يوم الراحة",
    )
    #: أيامُ إغلاق السلطة في هذا النظام — مفاتيحُ من
    #: `settings_registry.WEEKDAY_KEYS`. تُستعمل مع أيام راحة الزبون.
    authority_closed_days = models.JSONField(
        default=list, blank=True, verbose_name="أيام إغلاق السلطة",
    )
    note = models.TextField(blank=True, default="", verbose_name="ملاحظة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإدخال")

    class Meta:
        verbose_name = "نسخة لائحة مواعيد"
        verbose_name_plural = "نسخ لائحة المواعيد"
        ordering = ["tax_system", "-year", "-version"]
        constraints = [
            # فرادةٌ **غير مشروطة**: الشرطُ في `UniqueConstraint` تتجاهله MySQL
            # بصمت فتمرّ الهجرة ويغيب القيد في الإنتاج.
            models.UniqueConstraint(
                fields=["tax_system", "year", "version"],
                name="uniq_deadline_schedule_version",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tax_system}/{self.year}/v{self.version}"


class DeadlineRule(models.Model):
    """سطرُ التزامٍ في نسخة لائحة: قاعدتُه، والخدمةُ التي تولّده، وشروطُه.

    **القاعدةُ بيانات**: `rule_kind` و`rule_day`/`rule_month` تُقرأ ولا تُحفَر،
    و`period_overrides` تحمل تواريخَ النشرة المنشورة (تأجيلاتُ الأعياد) بمفتاح
    شهر **نهاية** الفترة — و`rest_day_only` تعني أنّ سببَ التأجيل يومُ الراحة
    الأسبوعيّ وحده، فتُعاد الحسبة لزبونٍ راحتُه غيرها.
    """

    schedule = models.ForeignKey(
        DeadlineSchedule,
        on_delete=models.CASCADE,
        related_name="rules",
        verbose_name="نسخة اللائحة",
    )
    code = models.SlugField(max_length=60, verbose_name="الكود")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    #: كودُ الخدمة التي يولّدها هذا السطر — من `DEFAULT_SERVICES` وحدها، فالخدمةُ
    #: عقدٌ ثابت لا تسميةُ شاشة.
    service_code = models.CharField(
        max_length=60, choices=DEFAULT_SERVICES, verbose_name="الخدمة المولِّدة",
    )
    cadence = models.CharField(
        max_length=20,
        choices=DEADLINE_CADENCE_CHOICES,
        default=CADENCE_SERVICE,
        verbose_name="الدورية",
    )
    rule_kind = models.CharField(
        max_length=30, choices=RULE_KIND_CHOICES, verbose_name="نوع القاعدة",
    )
    rule_day = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="يوم القاعدة",
    )
    rule_month = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="شهر القاعدة",
    )
    #: شروطُ التوليد على البطاقة — مفاتيحها في `CONDITION_KEYS` وحدها.
    conditions = models.JSONField(default=dict, blank=True, verbose_name="الشروط")
    #: False = «لا يُولَّد» (مثل الضمان الاجتماعي الفلسطيني الموقوف بقرار 4/2019).
    is_generated = models.BooleanField(default=True, verbose_name="يُولَّد")
    #: #277: نوعُ الحدث الذي يُولّد هذا السطر — من `EVENT_KIND_CHOICES`، وفارغٌ في
    #: كل سطرٍ دوريّ. وسطرُ الحدث `cadence="event"` ولا يُولَّد إلا من حدثٍ مسجَّل.
    event_kind = models.CharField(
        max_length=40, choices=EVENT_KIND_CHOICES, blank=True, default="",
        verbose_name="نوع الحدث",
    )
    #: أيامُ التقديم الإلكترونيّ فوق الموعد الرسميّ: **أربعةٌ في إسرائيل** (حتى
    #: 19 بدل 15 لتقرير الـמע"מ والسلفيات)، وصفرٌ حيث لا تمديدَ منشوراً.
    electronic_extension_days = models.PositiveSmallIntegerField(
        default=0, verbose_name="تمديد التقديم الإلكتروني",
    )
    #: تواريخُ النشرة المنشورة: `{"YYYY-MM": {"date": "YYYY-MM-DD", "rest_day_only": bool}}`.
    period_overrides = models.JSONField(
        default=dict, blank=True, verbose_name="تعديلات الفترات المنشورة",
    )
    #: قيمةٌ غير مؤكَّدة في البحث — تُعرض «راجع» ولا تُملأ بصمت.
    needs_review = models.BooleanField(default=False, verbose_name="راجع")
    source_url = models.URLField(max_length=300, verbose_name="المصدر")
    position = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")

    class Meta:
        verbose_name = "سطر لائحة مواعيد"
        verbose_name_plural = "أسطر لائحة المواعيد"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "code"], name="uniq_deadline_rule_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code}@{self.schedule_id}"

    def clean(self):
        """مفتاحُ شرطٍ غير معروف يُرفض — الشروطُ تُقرأ من اللائحة لا تُخترَع."""
        unknown = sorted(set(self.conditions or {}) - CONDITION_KEYS)
        if unknown:
            raise ValidationError({
                "conditions": f"شروط غير معروفة: {unknown}",
            })


# ── تعديل المكتب على اللائحة والالتزامات الخاصة والأحداث (#277) ─────────────
#
# **اللائحةُ بياناتُ منصّةٍ لا تُعدَّل** (قرار #274). وتعديلُ المكتب عليها **صفٌّ
# إلحاقيّ** في جدولٍ مِلكُ المكتب: الساري = أحدثُ صفٍّ لكل (مكتب، نظام، كود)،
# و«رجّع للمنصة» صفٌّ `cleared` لا حذف. فتاريخُ التعديل — مَن واتّى — لا يُمحى
# (قرار #255)، وتاريخُ المنصة يبقى مقروءاً في `based_on`.
OFFICE_RULE_OVERRIDE_FIELDS = (
    "rule_day", "rule_month", "electronic_extension_days",
)


class OfficeRuleOverride(models.Model):
    """تعديلُ المكتب على سطر لائحة — **سجلٌّ إلحاقيّ لا يُعدَّل ولا يُحذف**.

    القيمةُ `None` في أي حقلٍ تعني «كالمنصة»: المكتب يعدّل الأيام وحدها ولا
    يغيّر نوعَ القاعدة (`rule_kind` يبقى من `based_on`). والتعديلُ يسري على كل
    السنوات وكل زباين المكتب لهذا الكود — لا على فترةٍ بعينها.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_rule_overrides",
        verbose_name="المكتب",
    )
    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    rule_code = models.SlugField(max_length=60, verbose_name="كود السطر")
    rule_day = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="يوم القاعدة",
    )
    rule_month = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="شهر القاعدة",
    )
    electronic_extension_days = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="تمديد التقديم الإلكتروني",
    )
    #: صفُّ «رجّع لتاريخ المنصة»: هو أحدثُ صفٍّ ⇒ لا تعديلَ ساري.
    cleared = models.BooleanField(default=False, verbose_name="رجّع للمنصة")
    #: لقطةُ قيم المنصة وقت التعديل: `{rule_kind, rule_day, rule_month,
    #: electronic_extension_days, schedule_id}` — تُقارَن بنسخة المنصة الجديدة
    #: فتقول «المنصة غيّرت موعداً أنت معدّله» بلا أن تُقرأ نسخةٌ قديمة.
    based_on = models.JSONField(default=dict, blank=True, verbose_name="لقطة المنصة")
    note = models.CharField(max_length=300, blank=True, default="", verbose_name="ملاحظة")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_rule_overrides",
        verbose_name="عدّله",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "تعديل مكتب على سطر لائحة"
        verbose_name_plural = "تعديلات المكتب على اللائحة"
        # الأحدثُ أوّلاً: الساري هو أوّلُ صفٍّ يُقرأ لكل (نظام، كود).
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["tenant", "tax_system", "rule_code"],
                name="office_override_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tax_system}/{self.rule_code}"


class OfficeCustomRule(models.Model):
    """التزامٌ خاص بالمكتب: اسمٌ ودوريةٌ وقاعدةٌ وخدمةٌ — يُولّد كالرسميّ.

    **يُعطَّل ولا يُحذف**: التعطيلُ يوقف توليد الفترات الجديدة، وما وُلد يبقى
    بتاريخه (`Obligation.custom_rule` على `PROTECT`). وكوده المشتقّ
    `office-<pk>` هو `rule_code` في الالتزام، فيسري عليه كلُّ ما يسري على كودٍ
    رسميّ — الفرادةُ والبحثُ والفلترة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_custom_rules",
        verbose_name="المكتب",
    )
    name = models.CharField(max_length=200, verbose_name="الاسم")
    service = models.ForeignKey(
        OfficeService,
        on_delete=models.PROTECT,
        related_name="custom_rules",
        verbose_name="الخدمة",
    )
    cadence = models.CharField(
        max_length=20,
        choices=OFFICE_CUSTOM_RULE_CADENCE_CHOICES,
        default=CADENCE_MONTHLY,
        verbose_name="الدورية",
    )
    rule_kind = models.CharField(
        max_length=30,
        choices=OFFICE_CUSTOM_RULE_KIND_CHOICES,
        verbose_name="نوع القاعدة",
    )
    rule_day = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="يوم القاعدة",
    )
    rule_month = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="شهر القاعدة",
    )
    is_active = models.BooleanField(default=True, verbose_name="مفعَّل")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_custom_rules",
        verbose_name="أنشأه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "التزام خاص بالمكتب"
        verbose_name_plural = "التزامات المكتب الخاصة"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def code(self) -> str:
        """كودُ السطر المشتقّ — فريدٌ بين أسطر المنصة المكوَّدة بـ`ps_`/`il_`."""
        return f"office-{self.pk}"


class ClientEvent(models.Model):
    """«صار حدث»: اقتطاعٌ أو ما يُضاف صفّاً في `EVENT_KIND_CHOICES`.

    **لا يُعدَّل ولا يُحذف** (قرار #255: «التاريخ لا يُمحى»): الصفُّ خبرٌ عن يومٍ
    وقع، وتصحيحُه حدثٌ جديد. ولكل حدثٍ التزاماتُه من أسطر `cadence="event"` في
    لائحة نظام الزبون.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_events",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="events",
        verbose_name="الزبون",
    )
    kind = models.CharField(
        max_length=40, choices=EVENT_KIND_CHOICES, verbose_name="نوع الحدث",
    )
    occurred_on = models.DateField(verbose_name="تاريخ الحدث")
    note = models.CharField(max_length=300, blank=True, default="", verbose_name="ملاحظة")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_client_events",
        verbose_name="سجّله",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")

    class Meta:
        verbose_name = "حدث زبون"
        verbose_name_plural = "أحداث الزبائن"
        ordering = ["-occurred_on", "-id"]

    def __str__(self) -> str:
        return f"{self.kind}@{self.occurred_on}"


# ── الالتزامات والشغلات (#275) ───────────────────────────────────────────────
#
# **الالتزامُ سطرٌ محفوظ، وحالتُه المشتقّة تُحسب عند القراءة**: «قريب هالأسبوع»
# و«متأخّر» تُقرأ من `actual_deadline` واليوم المُمرَّر، فلا عمودَ لهما يتعفّن
# بين تشغيلين. **والمخزّنُ ثلاثُ حالاتٍ لا غير**: لسا ما انقدّم · انقدّم (نهائيٌّ
# لا يُتراجَع عنه) · مش لازم هالفترة.
#
# **والأصلُ «رسمي»** — «من المكتب» (#277) أصلٌ ثانٍ يُضاف صفّاً لا فرعاً في الكود.
OBLIGATION_ORIGIN_OFFICIAL = "official"
OBLIGATION_ORIGIN_OFFICE = "office"
#: #277:التزامٌ وُلد من «صار حدث» في ملفّ الزبون — لا من سطرٍ دوريّ.
OBLIGATION_ORIGIN_EVENT = "event"
OBLIGATION_ORIGIN_CHOICES: list[tuple[str, str]] = [
    (OBLIGATION_ORIGIN_OFFICIAL, "رسمي"),
    (OBLIGATION_ORIGIN_OFFICE, "من المكتب"),
    (OBLIGATION_ORIGIN_EVENT, "حدث"),
]
OBLIGATION_ORIGIN_LABELS: dict[str, str] = dict(OBLIGATION_ORIGIN_CHOICES)

OBLIGATION_STATUS_PENDING = "pending"
OBLIGATION_STATUS_SUBMITTED = "submitted"
OBLIGATION_STATUS_NOT_REQUIRED = "not_required"
OBLIGATION_STATUS_CHOICES: list[tuple[str, str]] = [
    (OBLIGATION_STATUS_PENDING, "لسا ما انقدّم"),
    (OBLIGATION_STATUS_SUBMITTED, "انقدّم"),
    (OBLIGATION_STATUS_NOT_REQUIRED, "مش لازم هالفترة"),
]
OBLIGATION_STATUS_LABELS: dict[str, str] = dict(OBLIGATION_STATUS_CHOICES)

OBLIGATION_DIRECTION_DUE = "due"
OBLIGATION_DIRECTION_REFUND = "refund"
OBLIGATION_DIRECTION_CHOICES: list[tuple[str, str]] = [
    (OBLIGATION_DIRECTION_DUE, "عليه"),
    (OBLIGATION_DIRECTION_REFUND, "إله"),
]
OBLIGATION_DIRECTION_LABELS: dict[str, str] = dict(OBLIGATION_DIRECTION_CHOICES)

#: الشارةُ المشتقّة — واحدةٌ بالأولوية `late` ثم `late_internal` ثم `near` (`services._badge_keys`).
OBLIGATION_BADGE_NEAR = "near"
OBLIGATION_BADGE_LATE = "late"
#: #276: الدرجةُ الداخليّة — شغلةُ الالتزام تجاوزت `internal_deadline` ولم يبلغ
#: الرسميُّ بعد. ومفتاحٌ ثالثٌ لمفتاحين قائمين لا عمودَ ولا حالة.
OBLIGATION_BADGE_LATE_INTERNAL = "late_internal"
#: #278: «ناقصه أوراق» — **شارةٌ إضافية** تُضاف فوق واحدة التأخير ولا تُزاحمها:
#: التأخيرُ سؤالٌ عن الموعد، وهذه عن الورق، وصفٌّ قد يستحقّ الاثنين معاً.
OBLIGATION_BADGE_MISSING_DOCS = "missing_docs"
OBLIGATION_BADGE_LABELS: dict[str, str] = {
    OBLIGATION_BADGE_NEAR: "قريب هالأسبوع",
    OBLIGATION_BADGE_LATE: "متأخّر رسمي",
    OBLIGATION_BADGE_LATE_INTERNAL: "متأخّر داخلي",
    OBLIGATION_BADGE_MISSING_DOCS: "ناقصه أوراق",
}


class PeriodTask(models.Model):
    """شغلةُ فترة: **خدمةُ زبون × فترة** — بموعدها الداخليّ ومسؤولها.

    `client_service` على `PROTECT` لا `CASCADE`: حذفُ خدمةِ زبونٍ كان يمحو تاريخ
    شغلاتها ومواعيدها، والخدمةُ لا تُحذف أصلاً (الإيقافُ يكتب `ends_on`).

    **و`assignee` فارغةٌ تعني الوراثة** لا «بلا مسؤول»: الشغلةُ ترث مسؤولَ الزبون
    (`effective_assignee`)، وتحويلُها لعضوٍ آخر فعلٌ مستقلٌّ بمفتاحه
    (`office.clients.assign`) — فالوراثةُ لا تحتاج كتابة، والتحويلُ يحتاج مفتاحاً.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_period_tasks",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="الزبون",
    )
    client_service = models.ForeignKey(
        ClientService,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="خدمة الزبون",
    )
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    #: **أبكرُ** موعدٍ داخليٍّ بين التزامات الشغلة: يُضبط عند الإنشاء ثم يُخفَّض
    #: إن انضمّ التزامٌ أبكر — فالموعدُ لا يتأخّر أبداً بعد أن رآه الموظف.
    internal_deadline = models.DateField(verbose_name="الموعد الداخلي الأبكر")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_period_tasks",
        verbose_name="المحوَّلة له",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "شغلة فترة"
        verbose_name_plural = "شغلات الفترات"
        # الأحدثُ أوّلاً: ملفُّ الزبون يعرض الشغلات من أحدثِ فترةٍ لآخرها.
        ordering = ["-period_end", "-id"]
        constraints = [
            # فرادةٌ **غير مشروطة** — الشرطُ في `UniqueConstraint` تتجاهله MySQL
            # بصمت فتمرّ الهجرة ويغيب القيد في الإنتاج.
            models.UniqueConstraint(
                fields=["client_service", "period_start", "period_end"],
                name="uniq_period_task_span",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "assignee"], name="office_task_tenant_assignee",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_service_id}@{self.period_start}"

    @property
    def effective_assignee(self):
        """المسؤولُ الفعليّ: المحوَّلُ إليه، وإلا مسؤولُ الزبون — قاعدةُ الوراثة."""
        return self.assignee or self.client.responsible


class Obligation(models.Model):
    """التزامٌ محفوظ: سطرُ لائحة × فترة، بتاريخه وحالته ومبلغه.

    **التواريخُ لقطةٌ وقت الحفظ** (`DeadlineResult` كما حُسب): تصحيحُ لائحةٍ لا
    يعيد كتابة ما رآه الموظف وأرسله — وإعادةُ حساب الصفوف تذكرةٌ أخرى (#277).
    **والمبلغُ مبلغ**: مُسجَّلٌ في `AMOUNT_KEYS` ويمرّ بالقناع، ويُقفل عند «انقدّم».
    """

    ORIGIN_OFFICIAL = OBLIGATION_ORIGIN_OFFICIAL
    ORIGIN_OFFICE = OBLIGATION_ORIGIN_OFFICE
    STATUS_PENDING = OBLIGATION_STATUS_PENDING
    STATUS_SUBMITTED = OBLIGATION_STATUS_SUBMITTED
    STATUS_NOT_REQUIRED = OBLIGATION_STATUS_NOT_REQUIRED
    DIRECTION_DUE = OBLIGATION_DIRECTION_DUE
    DIRECTION_REFUND = OBLIGATION_DIRECTION_REFUND

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_obligations",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="obligations",
        verbose_name="الزبون",
    )
    client_service = models.ForeignKey(
        ClientService,
        on_delete=models.PROTECT,
        related_name="obligations",
        verbose_name="خدمة الزبون",
    )
    task = models.ForeignKey(
        PeriodTask,
        on_delete=models.PROTECT,
        related_name="obligations",
        verbose_name="شغلة الفترة",
    )
    #: سطرُ اللائحة الأصليّ — `PROTECT`: الالتزامُ يُفسَّر بسنده ولا يبقى يتيماً.
    #: و`null` في التزامات المكتب (`custom_rule`) والحدث (`event`) — والقيدُ أدناه
    #: يضمن مصدراً واحداً بالضبط.
    rule = models.ForeignKey(
        DeadlineRule,
        on_delete=models.PROTECT,
        related_name="obligations",
        null=True,
        blank=True,
        verbose_name="سطر اللائحة",
    )
    #: #277: التزامٌ عرّفه المكتب لنفسه — يُولَّد كالرسميّ بكوده `office-<pk>`.
    custom_rule = models.ForeignKey(
        OfficeCustomRule,
        on_delete=models.PROTECT,
        related_name="obligations",
        null=True,
        blank=True,
        verbose_name="قاعدة المكتب",
    )
    #: #277: الحدثُ الذي وُلد منه الالتزام («صار حدث»).
    event = models.ForeignKey(
        ClientEvent,
        on_delete=models.PROTECT,
        related_name="obligations",
        null=True,
        blank=True,
        verbose_name="الحدث",
    )
    #: لقطةُ السطر وقت الحفظ: اللائحةُ المنشورة لا تُعدَّل، والاسمُ يبقى مقروءاً
    #: حتى لو صار كودُ السطر في نسخةٍ لاحقةٍ غيره.
    rule_code = models.SlugField(max_length=60, verbose_name="كود السطر")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    origin = models.CharField(
        max_length=20,
        choices=OBLIGATION_ORIGIN_CHOICES,
        default=OBLIGATION_ORIGIN_OFFICIAL,
        verbose_name="الأصل",
    )
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    legal_date = models.DateField(verbose_name="التاريخ بالقاعدة")
    official_date = models.DateField(verbose_name="الموعد الرسمي")
    actual_deadline = models.DateField(verbose_name="آخر موعد فعلي")
    internal_deadline = models.DateField(verbose_name="الموعد الداخلي")
    estimated = models.BooleanField(default=False, verbose_name="تقديري")
    postponed = models.BooleanField(default=False, verbose_name="مؤجَّل")
    warnings = models.JSONField(default=list, blank=True, verbose_name="تنبيهات")
    #: #277: موعدُ المنصة الرسميّ حين يختلف عن الموعد الساري بسبب تعديل المكتب —
    #: يُعرض «المنصة: …» بجانبه، وإلا `None` (لا نسخةَ ثانية من القيمة بلا سبب).
    platform_official_date = models.DateField(
        null=True, blank=True, verbose_name="موعد المنصة",
    )
    #: #277: التمديد — تاريخٌ وملاحظةٌ ومَن ومتى، و`due_date` تقرؤه وحده. والتاريخُ
    #: الرسميُّ (`actual_deadline`) لا يُكتب فوقه: التمديدُ قرارٌ زائدٌ يُلغى.
    extended_to = models.DateField(null=True, blank=True, verbose_name="ممدَّد حتى")
    extension_note = models.CharField(
        max_length=300, blank=True, default="", verbose_name="ملاحظة التمديد",
    )
    extended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_extended_obligations",
        verbose_name="مدّده",
    )
    extended_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التمديد")
    status = models.CharField(
        max_length=20,
        choices=OBLIGATION_STATUS_CHOICES,
        default=OBLIGATION_STATUS_PENDING,
        verbose_name="الحالة",
    )
    submitted_on = models.DateField(null=True, blank=True, verbose_name="تاريخ التقديم")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_submitted_obligations",
        verbose_name="قدّمها",
    )
    submission_number = models.CharField(
        max_length=60, blank=True, default="", verbose_name="رقم التقديم",
    )
    #: «هدول انقدّموا قبل ما يجي علينا» — أُغلقت بلا تاريخ تقديمٍ ولا موظفٍ قدّمها.
    prior_to_office = models.BooleanField(
        default=False, verbose_name="انقدّم قبل المكتب",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="المبلغ",
    )
    direction = models.CharField(
        max_length=10,
        choices=OBLIGATION_DIRECTION_CHOICES,
        blank=True,
        default="",
        verbose_name="الاتجاه",
    )
    client_paid = models.BooleanField(default=False, verbose_name="الزبون دفع")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "التزام"
        verbose_name_plural = "الالتزامات"
        ordering = ["actual_deadline", "internal_deadline", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client_service", "rule_code", "period_end"],
                name="uniq_obligation_period_rule",
            ),
            # #277: مصدرٌ واحدٌ بالضبط — سطرُ منصةٍ أو قاعدةُ مكتب. والشرطُ في
            # `CheckConstraint` لا `UniqueConstraint` (تلك تتجاهل شرطها في MySQL).
            models.CheckConstraint(
                condition=(
                    (Q(rule__isnull=False) & Q(custom_rule__isnull=True))
                    | (Q(rule__isnull=True) & Q(custom_rule__isnull=False))
                ),
                name="obligation_one_source",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"], name="office_oblig_tenant_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rule_code}@{self.period_end}"

    @property
    def due_date(self):
        """**الموعدُ الساري**: الممدَّد إن وُجد، وإلا الفعليّ.

        وهو وحده ما يقرؤه التأخيرُ الأحمرُ ونافذةُ «قريب هالأسبوع» وتنبيهُ
        `obligation_late` وترتيبُ «اليوم» — والموعدُ الداخليُّ (الأصفر) يبقى على
        `PeriodTask.internal_deadline`: الموعدُ الداخليُّ قرارُ المكتب الداخليّ،
        والتمديدُ للموعد الرسميّ.
        """
        return self.extended_to or self.actual_deadline


#: أسبابُ تغيّر تواريخ التزام — **سجلٌّ إلحاقيّ** لا يُعدَّل ولا يُحذف.
OBLIGATION_CHANGE_OFFICE_OVERRIDE = "office_override"
OBLIGATION_CHANGE_PLATFORM_UPDATE = "platform_update"
OBLIGATION_CHANGE_EXTENSION = "extension"
OBLIGATION_CHANGE_EXTENSION_CLEARED = "extension_cleared"
OBLIGATION_CHANGE_REASON_CHOICES: list[tuple[str, str]] = [
    (OBLIGATION_CHANGE_OFFICE_OVERRIDE, "تعديل المكتب على اللائحة"),
    (OBLIGATION_CHANGE_PLATFORM_UPDATE, "تحديث المنصة للائحة"),
    (OBLIGATION_CHANGE_EXTENSION, "تمديد"),
    (OBLIGATION_CHANGE_EXTENSION_CLEARED, "إلغاء تمديد"),
]
OBLIGATION_CHANGE_REASON_LABELS: dict[str, str] = dict(
    OBLIGATION_CHANGE_REASON_CHOICES,
)


class ObligationDateChange(models.Model):
    """تغيّرُ تواريخ التزامٍ محفوظ: قبلُ وبعدُ وسببه ومَن.

    **لا يُثبت شيءٌ بلا سبب** (قرار #255: «التاريخ لا يُمحى»): تصحيحُ لائحةٍ أو
    تعديلُ مكتبٍ أو تمديدٌ يترك أثراً يُقرأ. و`before`/`after` لقطتان JSON
    بالتواريخ الأربعة (والممدَّد حين يخصّه السبب)، و`changed_by` فارغٌ للتلقائي.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_obligation_date_changes",
        verbose_name="المكتب",
    )
    obligation = models.ForeignKey(
        Obligation,
        on_delete=models.CASCADE,
        related_name="date_changes",
        verbose_name="الالتزام",
    )
    reason = models.CharField(
        max_length=20,
        choices=OBLIGATION_CHANGE_REASON_CHOICES,
        verbose_name="السبب",
    )
    before = models.JSONField(default=dict, blank=True, verbose_name="قبل")
    after = models.JSONField(default=dict, blank=True, verbose_name="بعد")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_obligation_date_changes",
        verbose_name="غيّره",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التغيّر")

    class Meta:
        verbose_name = "تغيّر تاريخ التزام"
        verbose_name_plural = "تغيّرات تواريخ الالتزامات"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.obligation_id}:{self.reason}"


class OfficeRefreshRun(models.Model):
    """سجلُّ «حدّث المكتب ليوم X» — صفٌّ واحدٌ لكل (مكتب، يوم).

    الفرادةُ هي الضمانة: تشغيلُ اليوم نفسه مرّتين لا يكتب سطراً ثانياً، ولا تعيد
    `ensure_office_refreshed` العملَ على يومٍ رآه أحد. والعدّادُ المحفوظ هو ما
    أنشأه أوّلُ تشغيلٍ لذلك اليوم.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_refresh_runs",
        verbose_name="المكتب",
    )
    day = models.DateField(verbose_name="اليوم")
    ran_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت التشغيل")
    created_obligations = models.PositiveIntegerField(
        default=0, verbose_name="التزامات أُنشئت",
    )

    class Meta:
        verbose_name = "تشغيل تحديث مكتب"
        verbose_name_plural = "تشغيلات تحديث المكاتب"
        ordering = ["-day", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "day"], name="uniq_office_refresh_run_day",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}@{self.day}"


# ── التنبيهات الداخلية (#276) ───────────────────────────────────────────────
#
# **التنبيهُ لقطةٌ لا مرآة**: يُولَّد مرّةً واحدةً لكل (مستلِم، نوع، مرجع) داخل
# «حدّث المكتب»، ويُقرأ من الجرس بعد استبعاد المحسوم. فما انقدّم لا يختفي صفُّه
# (يبقى أثراً لِما نُبِّه عليه) لكنه لا يُعرض ولا يُعدّ.
#
# **والمفتاحُ يُصلح للتذاكر اللاحقة**: تصعيدُ التذكير وتغيّرُ اللائحة والمسودّةُ
# غير المعتمدة تُضاف **صفّاً في `OFFICE_ALERT_KIND_CHOICES`** لا فرعاً في الكود،
# و`ref_key` يُميّز الصفوف داخل النوع الواحد.
OFFICE_ALERT_KIND_TASK_LATE_INTERNAL = "task_late_internal"
OFFICE_ALERT_KIND_OBLIGATION_LATE = "obligation_late"
#: #277: تغيّرت تواريخُ التزامات المكتب بنسخة لائحةٍ جديدة (مرّةً لكل نسخة).
OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED = "schedule_dates_changed"
#: #277: المنصة غيّرت موعداً عدّله المكتب — «تُبقي تاريخك أم تأخذ الجديد؟».
OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED = "override_platform_changed"
#: #280: وصل التذكيرُ حدَّه وما زالت الأوراق ناقصة — للمسؤول أوّلاً.
OFFICE_ALERT_KIND_REMINDER_LIMIT = "reminder_limit_reached"
#: #280: ومضت أيامُ المهلة وما زالت ناقصة — يُصعَّد لصاحب المكتب.
OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER = "reminder_limit_reached_owner"
#: #282: مسودّةُ أتعابٍ مرّ عليها ثلاثةُ أيامٍ وما اعتُمدت — التنبيهُ لمن يعتمدها.
OFFICE_ALERT_KIND_FEE_DRAFT_PENDING = "fee_draft_pending"
#: نوعا التذكير — يُحكمان بشرطهما في القراءة (اكتمالُ الأوراق) لا بالحالة.
REMINDER_ALERT_KINDS: tuple[str, ...] = (
    OFFICE_ALERT_KIND_REMINDER_LIMIT,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
)
OFFICE_ALERT_KIND_CHOICES: list[tuple[str, str]] = [
    (OFFICE_ALERT_KIND_TASK_LATE_INTERNAL, "شغلة تجاوزت موعدها الداخلي"),
    (OFFICE_ALERT_KIND_OBLIGATION_LATE, "التزام تجاوز موعده الرسمي ولم يُقدَّم"),
    (OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED, "تغيّر موعد التزامات بنسخة لائحة جديدة"),
    (OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED, "المنصة غيّرت موعداً معدَّلاً من المكتب"),
    (OFFICE_ALERT_KIND_REMINDER_LIMIT, "وصل التذكير حدّه والأوراق ناقصة"),
    (
        OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
        "الأوراق ناقصة بعد حدّ التذكير — صار لصاحب المكتب",
    ),
    (OFFICE_ALERT_KIND_FEE_DRAFT_PENDING, "مسودّة أتعاب تنتظر الاعتماد"),
]
OFFICE_ALERT_KIND_LABELS: dict[str, str] = dict(OFFICE_ALERT_KIND_CHOICES)
#: شارةُ كل نوعٍ في الواجهة — **مفتاحُ صنفٍ لا لون**، يُرسَل في `alert_row` فيُلوَّن
#: الجرسُ بلا معرفة أنواعٍ فيه. نوعٌ لاحقٌ يُضاف صفّاً هنا ويأخذ محايداً حتى يُضاف.
OFFICE_ALERT_KIND_BADGES: dict[str, str] = {
    OFFICE_ALERT_KIND_TASK_LATE_INTERNAL: OBLIGATION_BADGE_LATE_INTERNAL,
    OFFICE_ALERT_KIND_OBLIGATION_LATE: OBLIGATION_BADGE_LATE,
    # نوعا اللائحة قرارُ مكتبٍ لا تأخيرُ موعد — أصفر محايدٌ بلا ادّعاء تأخير.
    OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED: OBLIGATION_BADGE_LATE_INTERNAL,
    OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED: OBLIGATION_BADGE_LATE_INTERNAL,
    # نوعا التذكير شأنُ أوراقٍ ناقصة — شارةُ «ناقصه أوراق» نفسها لا شارتان.
    OFFICE_ALERT_KIND_REMINDER_LIMIT: OBLIGATION_BADGE_MISSING_DOCS,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER: OBLIGATION_BADGE_MISSING_DOCS,
    # ومسودّةُ الأتعاب شأنُ اعتمادٍ ليس تأخيراً رسمياً — الأصفرُ المحايد نفسه.
    OFFICE_ALERT_KIND_FEE_DRAFT_PENDING: OBLIGATION_BADGE_LATE_INTERNAL,
}
#: **أين يُفتح التنبيه** — مفتاحٌ خادميّ يقرؤه `alert_row` فتبني الواجهةُ الوجهةَ
#: بلا معرفة أنواع. الافتراضُ ملفُّ الزبون، ونوعا اللائحة يفتحان شاشة الإعدادات
#: على مجموعة «الضريبة ولائحة المواعيد»، ونوعا التذكير تبويبَ «الأوراق» في الملفّ.
OFFICE_ALERT_OPENS_CLIENT = "client"
OFFICE_ALERT_OPENS_DEADLINE_RULES = "deadline_rules"
OFFICE_ALERT_OPENS_CLIENT_DOCUMENTS = "client_documents"
#: #282: تبويبُ «الأتعاب» في ملفّ الزبون — مسودّةُ الشهر التي تنتظر الاعتماد.
OFFICE_ALERT_OPENS_CLIENT_FEES = "client_fees"
OFFICE_ALERT_KIND_OPENS: dict[str, str] = {
    OFFICE_ALERT_KIND_TASK_LATE_INTERNAL: OFFICE_ALERT_OPENS_CLIENT,
    OFFICE_ALERT_KIND_OBLIGATION_LATE: OFFICE_ALERT_OPENS_CLIENT,
    OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED: OFFICE_ALERT_OPENS_DEADLINE_RULES,
    OFFICE_ALERT_KIND_OVERRIDE_PLATFORM_CHANGED: OFFICE_ALERT_OPENS_DEADLINE_RULES,
    OFFICE_ALERT_KIND_REMINDER_LIMIT: OFFICE_ALERT_OPENS_CLIENT_DOCUMENTS,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER: OFFICE_ALERT_OPENS_CLIENT_DOCUMENTS,
    OFFICE_ALERT_KIND_FEE_DRAFT_PENDING: OFFICE_ALERT_OPENS_CLIENT_FEES,
}
OFFICE_ALERT_DEFAULT_OPENS = OFFICE_ALERT_OPENS_CLIENT


class OfficeAlert(models.Model):
    """تنبيهٌ داخليٌّ لمستلِمٍ واحد: شغلةٌ تجاوزت موعدها الداخلي أو التزامٌ رسميّ.

    **الفرادةُ غير المشروطة** `(tenant, recipient, kind, ref_key)` هي «مرّةً واحدةً
    لكل مرجع»: تشغيلُ اليوم نفسه مرّتين لا يضيف صفّاً، ويومٌ لاحقٌ لا يُكرّر
    التنبيهَ نفسه — الشارةُ تبقى تقول الحال. والمرجعُ `"task:<id>"` أو
    `"obligation:<id>"` نصّاً، ليجمع الصفَّ الواحد مستلِمٌ ونوعٌ ومرجع.

    **ولا مبلغَ فيه**: `message` لقطةُ اسم الزبون واسم الالتزام/الفترة وقت التوليد،
    بلا أيّ رقم مال — فلا يمرّ بحارس المبالغ أصلاً.

    و`client`/`task`/`obligation` على `CASCADE` لأنها **مكانُ الفتح** لا سندُ
    التنبيه: ما حُذف منها لا تنبيهَ له، فلا معنى لبقاء صفٍّ يشير إلى العدم.
    """

    KIND_TASK_LATE_INTERNAL = OFFICE_ALERT_KIND_TASK_LATE_INTERNAL
    KIND_OBLIGATION_LATE = OFFICE_ALERT_KIND_OBLIGATION_LATE

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_alerts",
        verbose_name="المكتب",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="office_alerts",
        verbose_name="المستلِم",
    )
    kind = models.CharField(
        max_length=40,
        choices=OFFICE_ALERT_KIND_CHOICES,
        verbose_name="النوع",
    )
    #: مفتاحُ عدم التكرار: `"task:<id>"` أو `"obligation:<id>"`.
    ref_key = models.CharField(max_length=80, verbose_name="المفتاح")
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
        verbose_name="الزبون",
    )
    task = models.ForeignKey(
        PeriodTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
        verbose_name="شغلة الفترة",
    )
    obligation = models.ForeignKey(
        Obligation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
        verbose_name="الالتزام",
    )
    #: لقطةُ النصّ وقت التوليد — اسمُ الزبون والالتزام/الفترة، **بلا مبلغ**.
    message = models.TextField(verbose_name="النص")
    day = models.DateField(verbose_name="يوم التوليد")
    seen_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الشوفة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "تنبيه داخلي"
        verbose_name_plural = "التنبيهات الداخلية"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "recipient", "kind", "ref_key"],
                name="uniq_office_alert_ref",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "recipient", "seen_at"],
                name="office_alert_recipient_seen",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.ref_key}→{self.recipient_id}"


# ── قائمة الأوراق: الكتالوج والصفوف والملفات ومدد الحفظ (#278) ────────────────
#
# **ثلاثُ طبقاتٍ لا طبقة**: بنداتُ المنصّة (`PlatformDocumentItem`، بياناتُ منصّةٍ
# بلا `tenant` كـ`DeadlineSchedule`)، ثم قائمةُ المكتب (`OfficeDocumentItem`
# المضاف و`OfficeDocumentItemChoice` المُخرِج)، ثم **خيارُ الزبون**
# (`ClientDocumentItemChoice`) **الذي يغلب الجميع**: إدخالاً يفرض بنداً لا تنطبق
# شروطه، وإخراجاً يمحو بنداً انطبقت.
#
# **والبندُ يعرف خدماته**: `service_codes` أكوادٌ من `SERVICE_CODE_*`، وقائمةٌ
# فارغةٌ تعني «لكل زبون». وبندٌ واحدٌ بخدمتين («فواتير المشتريات» لمسك الدفاتر
# والقيمة المضافة) يُولَّد **مرّةً واحدة** — لا بندان لخدمةٍ واحدة.
#
# **والصفُّ لقطة**: `item_code` و`name` و`service_codes` تُنسخ عند التوليد، فتصحيحُ
# الكتالوج أو خياراتِه لا يعيد كتابة ما رآه الموظف.
DOCUMENT_STATUS_REQUIRED = "required"
DOCUMENT_STATUS_PARTIAL = "partial"
DOCUMENT_STATUS_RECEIVED = "received"
DOCUMENT_STATUS_NOT_NEEDED = "not_needed"
DOCUMENT_STATUS_CHOICES: list[tuple[str, str]] = [
    (DOCUMENT_STATUS_REQUIRED, "مطلوبة"),
    (DOCUMENT_STATUS_PARTIAL, "وصلت ناقصة"),
    (DOCUMENT_STATUS_RECEIVED, "وصلت"),
    (DOCUMENT_STATUS_NOT_NEEDED, "مش لازمة هالشهر"),
]
DOCUMENT_STATUS_LABELS: dict[str, str] = dict(DOCUMENT_STATUS_CHOICES)
#: تسميةُ الاستثناء تتبع دورية الصفّ: الشهرُ شهرُه والسنةُ سنتُها.
DOCUMENT_STATUS_NOT_NEEDED_ANNUAL_LABEL = "مش لازمة هالسنة"

DOCUMENT_CHANNEL_WHATSAPP = "whatsapp"
DOCUMENT_CHANNEL_PAPER = "paper"
DOCUMENT_CHANNEL_EMAIL = "email"
DOCUMENT_CHANNEL_CHOICES: list[tuple[str, str]] = [
    (DOCUMENT_CHANNEL_WHATSAPP, "واتساب"),
    (DOCUMENT_CHANNEL_PAPER, "ورق"),
    (DOCUMENT_CHANNEL_EMAIL, "إيميل"),
]
DOCUMENT_CHANNEL_LABELS: dict[str, str] = dict(DOCUMENT_CHANNEL_CHOICES)

#: دوريتان لا أكثر: الشهرُ والسنة. **أسماءٌ لعائلة `FREQUENCY_*`** نفسها، فلا
#: تحمل القيمةَ الواحدة عائلتان تفترقان عند أول تعديل.
DOCUMENT_CADENCE_MONTHLY = FREQUENCY_MONTHLY
DOCUMENT_CADENCE_ANNUAL = FREQUENCY_ANNUAL
DOCUMENT_CADENCE_CHOICES: list[tuple[str, str]] = [
    (DOCUMENT_CADENCE_MONTHLY, "شهري"),
    (DOCUMENT_CADENCE_ANNUAL, "سنوي"),
]
DOCUMENT_CADENCE_LABELS: dict[str, str] = dict(DOCUMENT_CADENCE_CHOICES)

#: أساسُ حساب مدة الحفظ — **بياناتُ منصّةٍ لكل نظام** (قرار #278/D5): فلسطين
#: خمسُ سنواتٍ من نهاية السنة (م79/1)، وإسرائيل سبعٌ من نهايتها أو ستٌّ من
#: التقديم **الأبعدُ منهما** (§25(ג))، وثلاثٌ من التقديم للمستندات غير الإلزامية
#: (§25(ד)). ولا حسابَ تاريخٍ آخر في v1 ولا حذفَ آليّ.
RETENTION_BASIS_YEAR_END = "year_end"
RETENTION_BASIS_LATER_OF_YEAR_END_OR_FILING = "later_of_year_end_or_filing"
RETENTION_BASIS_FILING = "filing"
RETENTION_BASIS_CHOICES: list[tuple[str, str]] = [
    (RETENTION_BASIS_YEAR_END, "من نهاية السنة"),
    (RETENTION_BASIS_LATER_OF_YEAR_END_OR_FILING, "الأبعد بين نهاية السنة والتقديم"),
    (RETENTION_BASIS_FILING, "من تاريخ التقديم"),
]
RETENTION_BASIS_LABELS: dict[str, str] = dict(RETENTION_BASIS_CHOICES)
#: حقولُ البطاقة التي يجوز أن تكون شرطاً على بند — وهي **وحدها**: مفتاحٌ آخر
#: لا معنى له في `card_conditions` فيُرفض في الخدمة.
DOCUMENT_CARD_CONDITION_FIELDS: frozenset[str] = frozenset({
    "entity_type", "vat_classification",
})

#: «صورة — الأصل عند الزبون»: وسمُ نسخة العمل التي يرفعها المكتب. الأصلُ يبقى
#: عند الزبون في النظامين، فلا ندّعي أرشيفاً قانونياً (بحث #260 §5.4).
DOCUMENT_FILE_COPY_TAG = "صورة — الأصل عند الزبون"


class PlatformDocumentItem(models.Model):
    """بندُ ورقةٍ في **لائحة المنصّة** — بياناتُ منصّةٍ لا بياناتُ مكتب.

    **بلا `tenant` عمداً** كـ`TaxThreshold` و`DeadlineSchedule`: القائمةُ المطلوبة
    في قانونٍ واحد، ونسخةٌ لكل مكتب تعني قوائمَ مختلفة لنفس الخدمة. وخياراتُ
    المكاتب والزبائن فوقها صفوفٌ في جداولهم، لا تعديلٌ على صفّ المنصّة.
    """

    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    code = models.SlugField(max_length=60, verbose_name="الكود")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    cadence = models.CharField(
        max_length=20, choices=DOCUMENT_CADENCE_CHOICES, verbose_name="الدورية",
    )
    #: أكوادُ الخدمات التي يلزمها البند — فارغةٌ = لكل زبون.
    service_codes = models.JSONField(
        default=list, blank=True, verbose_name="الخدمات",
    )
    #: شروطُ البطاقة: `{"entity_type": ["company"]}` — و`{}` لا شرط.
    card_conditions = models.JSONField(
        default=dict, blank=True, verbose_name="شروط البطاقة",
    )
    #: #279: الحالةُ التي يبدأ بها صفُّ الورقة المولَّد من هذا البند. بندُ المنصّة
    #: وحده يحملها — **وبندُ المكتب يبدأ «مطلوبة» دائماً**: ورقةٌ أضافها المكتب
    #: لقائمته لا تُولَد «مش لازمة» بلا قراره.
    default_status = models.CharField(
        max_length=20,
        choices=DOCUMENT_STATUS_CHOICES,
        default=DOCUMENT_STATUS_REQUIRED,
        verbose_name="الحالة الابتدائية",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="الترتيب")

    class Meta:
        verbose_name = "بند ورقة (منصة)"
        verbose_name_plural = "بنود الأوراق (منصة)"
        ordering = ["sort_order", "name", "id"]
        constraints = [
            # فرادةٌ **غير مشروطة** — الشرطُ في `UniqueConstraint` تتجاهله MySQL
            # بصمت فتمرّ الهجرة ويغيب القيد في الإنتاج.
            models.UniqueConstraint(
                fields=["tax_system", "code"], name="uniq_platform_doc_item_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tax_system}/{self.code}"


class OfficeDocumentItem(models.Model):
    """بندٌ أضافه المكتب للائحته — يُعطَّل ولا يُحذف بعد استعماله.

    كودُه المشتقّ `office_doc_<pk>` **مستقرٌّ** ويُخزَّن في الصفوف لقطةً، فيسري
    عليه كلُّ ما يسري على كودِ المنصّة: الفرادةُ والبحثُ والفلترة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_document_items",
        verbose_name="المكتب",
    )
    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    name = models.CharField(max_length=200, verbose_name="الاسم")
    cadence = models.CharField(
        max_length=20, choices=DOCUMENT_CADENCE_CHOICES, verbose_name="الدورية",
    )
    service_codes = models.JSONField(
        default=list, blank=True, verbose_name="الخدمات",
    )
    card_conditions = models.JSONField(
        default=dict, blank=True, verbose_name="شروط البطاقة",
    )
    is_active = models.BooleanField(default=True, verbose_name="مفعَّل")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_document_items",
        verbose_name="أنشأه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "بند ورقة (مكتب)"
        verbose_name_plural = "بنود الأوراق (مكتب)"
        ordering = ["name", "id"]
        indexes = [
            models.Index(
                fields=["tenant", "tax_system", "is_active"],
                name="office_doc_item_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def code(self) -> str:
        """كودُ البند المشتقّ — بادئتُه تميّزه عن أكواد المنصّة (`ps_`/`il_`)."""
        return f"office_doc_{self.pk}"


class OfficeDocumentItemChoice(models.Model):
    """خيارُ المكتب على بندِ المنصّة: **`included=False` يخرجه** من القالب.

    والغيابُ يعني «ضمن القائمة»: لا صفَّ لكل عضوٍ لكل بند، والخيارُ لا يُحذف
    بل يُقلب — فتاريخُ من أخرجه يبقى.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_document_item_choices",
        verbose_name="المكتب",
    )
    item_code = models.SlugField(max_length=60, verbose_name="كود البند")
    included = models.BooleanField(default=True, verbose_name="ضمن القائمة")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_document_item_choices",
        verbose_name="عدّله",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "خيار المكتب على بند ورقة"
        verbose_name_plural = "خيارات المكتب على بنود الأوراق"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "item_code"], name="uniq_office_doc_item_choice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_code}:{self.included}"


class ClientDocumentItemChoice(models.Model):
    """خيارُ الزبون على بند: **يغلب كلَّ ما فوقه** إدخالاً وإخراجاً.

    قائمةُ المنصّة تعرف ما يطلبه القانون، وقالبُ المكتب يعرف ما يشتغل عليه هذا
    المكتب — والزبونُ وحدَه يعرف أن هذه الورقة عنده ليست ورقاً (ساقيةٌ في درجِه،
    أو بنكٌ لا يُصدر كشفاً). فقرارُه فوق الاثنين بلا شرطٍ ثانٍ.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_document_choices",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="document_item_choices",
        verbose_name="الزبون",
    )
    item_code = models.SlugField(max_length=60, verbose_name="كود البند")
    included = models.BooleanField(default=True, verbose_name="ضمن القائمة")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_client_document_choices",
        verbose_name="عدّله",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "خيار بندٍ لزبون"
        verbose_name_plural = "خيارات بنود الزبائن"
        constraints = [
            models.UniqueConstraint(
                fields=["client", "item_code"], name="uniq_client_doc_item_choice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}/{self.item_code}:{self.included}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class DocumentChecklistItem(models.Model):
    """صفُّ ورقةٍ محفوظ: بندٌ × فترة، بحالته ومَن وكيف — **ولقطةُ اسمِه**.

    **التوليدُ لا يُعيد الكتابة**: `get_or_create` على
    `(client, item_code, period_start)`، فتشغيلُ اليوم نفسه مرّتين لا يكتب صفاً،
    والقائمُ يبقى بما رآه الموظف ولو تغيّر الكتالوج.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_document_rows",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="document_rows",
        verbose_name="الزبون",
    )
    item_code = models.SlugField(max_length=60, verbose_name="كود البند")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    #: لقطةُ خدمات البند — تُقرأ بها شارةُ «ناقصه أوراق» بلا ربطٍ بالكتالوج.
    service_codes = models.JSONField(
        default=list, blank=True, verbose_name="الخدمات",
    )
    cadence = models.CharField(
        max_length=20, choices=DOCUMENT_CADENCE_CHOICES, verbose_name="الدورية",
    )
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    status = models.CharField(
        max_length=20,
        choices=DOCUMENT_STATUS_CHOICES,
        default=DOCUMENT_STATUS_REQUIRED,
        verbose_name="الحالة",
    )
    received_on = models.DateField(null=True, blank=True, verbose_name="وصلت في")
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_received_documents",
        verbose_name="استلمها",
    )
    channel = models.CharField(
        max_length=20,
        choices=DOCUMENT_CHANNEL_CHOICES,
        blank=True,
        default="",
        verbose_name="كيف وصلت",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_updated_documents",
        verbose_name="عدّلها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        verbose_name = "ورقة زبون"
        verbose_name_plural = "أوراق الزبائن"
        ordering = ["period_start", "item_code", "id"]
        constraints = [
            # فرادةٌ **غير مشروطة**: صفٌّ واحد لكل بندٍ في فترة.
            models.UniqueConstraint(
                fields=["client", "item_code", "period_start"],
                name="uniq_document_row_period",
            ),
        ]
        indexes = [
            # شبكةُ الأشهر وشارةُ الالتزام تقرآن بثلاثة أعمدة: المكتب والزبون والفترة.
            models.Index(
                fields=["tenant", "client", "period_start"],
                name="office_docs_tenant_client",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_code}@{self.period_start}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class DocumentFile(models.Model):
    """ملفُّ ورقةٍ **اختياريّ** بحقول נספח ז السبعة — كيانٌ منفصلٌ عن الحالة.

    **الحالةُ والملفُّ لا يُستنتج أحدُهما من الآخر** (بحث #260 §5.4): ورقةٌ في درج
    المكتب «وصلت» بلا ملف، وملفٌّ واحدٌ قد يغطّي بندين. فرفعُ الملف أو حذفُه لا
    يمسّ `DocumentChecklistItem.status` أبداً.

    **و`file_url` لا يخرج في أيّ ردّ**: يُقدَّم بايتاتٍ من `stream_stored_asset`
    وحده، فيبقى رابطُ التخزين على الخادم.

    والحقولُ السبعة: مُعرِّفٌ فريد (`uid`)، ومَن أنشأ السجلّ (`created_by`)، ونوعُ
    المستند (`document_type`)، ورقمُ تسجيل المُصدر (`issuer_registration`)،
    وتاريخُ المستند (`document_date`)، ورقمُ المستند (`document_number`)، وتاريخُ
    الالتقاط (`captured_at`) — أوّلُ ثلاثةٍ تلقائية والباقي وصفٌ يكتبه الموظف.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_document_files",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="document_files",
        verbose_name="الزبون",
    )
    checklist_item = models.ForeignKey(
        DocumentChecklistItem,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="الورقة",
    )
    #: 「נספח ז」١: مُعرِّفٌ فريدٌ آليّ — يُقرأ في الأرشيف لا يُكتب.
    uid = models.UUIDField(
        default=uuid4, unique=True, editable=False, verbose_name="المعرّف الفريد",
    )
    #: 「נספח ז」٢: هويّةُ مَن أنشأ السجلّ.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_document_files",
        verbose_name="أنشأه",
    )
    #: 「נספח ז」٣: نوعُ المستند — افتراضُه اسمُ الورقة.
    document_type = models.CharField(max_length=200, verbose_name="نوع المستند")
    #: 「נספח ז」٤: رقمُ تسجيل المُصدر (עוסק).
    issuer_registration = models.CharField(
        max_length=60, blank=True, default="", verbose_name="رقم تسجيل المُصدر",
    )
    #: 「נספח ז」٥: تاريخُ المستند نفسه (لا تاريخُ رفعه).
    document_date = models.DateField(null=True, blank=True, verbose_name="تاريخ المستند")
    #: 「נספח ז」٦: رقمُ المستند.
    document_number = models.CharField(
        max_length=60, blank=True, default="", verbose_name="رقم المستند",
    )
    #: 「נספח ז」٧: تاريخُ الالتقاط — تلقائيٌّ عند الرفع.
    captured_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الالتقاط")
    #: **لا يخرج في أيّ ردّ** — التقديمُ بايتاتٍ من `stream_stored_asset`.
    file_url = models.URLField(max_length=500, verbose_name="رابط التخزين")
    file_name = models.CharField(max_length=255, blank=True, default="", verbose_name="اسم الملف")
    #: نسخةُ عملٍ لا أصلٌ موثَّق: تُوسم «صورة — الأصل عند الزبون».
    is_copy = models.BooleanField(default=True, verbose_name="صورة")

    class Meta:
        verbose_name = "ملف ورقة"
        verbose_name_plural = "ملفات الأوراق"
        ordering = ["-captured_at", "-id"]
        indexes = [
            models.Index(
                fields=["tenant", "client"], name="office_doc_file_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.uid}:{self.file_name}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class DocumentRetentionRule(models.Model):
    """مدةُ حفظٍ قانونية لنظامٍ ضريبيّ — **بياناتُ منصّةٍ لا ثابتاً في الكود**.

    الحفظُ إلزامُ الزبون لا المكتب، والمددُ مختلفة: خمسُ سنواتٍ فلسطينياً من
    نهاية السنة (م79/1)، وسبعٌ إسرائيلياً من النهاية أو ستٌّ من التقديم
    **الأبعدُ منهما** (§25(ג))، وثلاثٌ من التقديم للمستندات غير الإلزامية
    (§25(ד)). المصدرُ منشورٌ في `source_url`، وv1 يعرضها ولا يحسب تاريخاً.
    """

    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    code = models.SlugField(max_length=60, verbose_name="الكود")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    years = models.PositiveSmallIntegerField(verbose_name="السنوات")
    #: بديلٌ يُقارَن بالأساس الأبعد (إسرائيل: ٦ من التقديم مع ٧ من النهاية).
    alt_years = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="سنوات بديلة",
    )
    basis = models.CharField(
        max_length=40, choices=RETENTION_BASIS_CHOICES, verbose_name="أساس الحساب",
    )
    source_url = models.URLField(max_length=300, verbose_name="المصدر")

    class Meta:
        verbose_name = "مدة حفظ مستندات"
        verbose_name_plural = "مدد حفظ المستندات"
        ordering = ["tax_system", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tax_system", "code"], name="uniq_retention_rule_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tax_system}/{self.code}:{self.years}"


# ─────────────────────────────────────────────────────────────────────────────
# دفترُ الزبون (#286) — دفترُ عملٍ يملكه المكتب عن زبونه، **لا دفترَ الشركة**.
#
# القرارُ وسببه في `docs/decisions/client_books.md`: لا `post_journal` ولا
# `JournalHeader`/`JournalLine` في هذا القسم ولا في `client_books.py`، لأن
# `accounting` هو دفترُ الشركة المالكة للمستأجر (المكتبُ نفسه) — ودفترُ الزبون
# دفترُ منشأةٍ أخرى. ويحرس الاستثناءَ مسحُ `ast` في
# `accounting_office/tests/test_client_books.py` (لا تعليقٌ يُنسى).
#
# **ولا حذف**: التصحيحُ حركةٌ عكسية (`BookEntry.reverses`) والأصلُ يبقى. ولذلك
# `BookEntry.client_book` على `PROTECT`: دفترٌ فيه تاريخٌ لا يُطوى من تحت حركاته.
# ─────────────────────────────────────────────────────────────────────────────

BOOK_KIND_SIMPLE = "simple"
BOOK_KIND_DOUBLE = "double"
BOOK_KIND_CHOICES: list[tuple[str, str]] = [
    (BOOK_KIND_SIMPLE, "بسيط"),
    (BOOK_KIND_DOUBLE, "مزدوج"),
]
BOOK_KIND_LABELS: dict[str, str] = dict(BOOK_KIND_CHOICES)

#: أنواعُ الحساب — خمسةٌ على تصنيف القوائم المالية، لا شجرةَ أكوادٍ مخترَعة.
BOOK_ACCOUNT_TYPE_ASSET = "asset"
BOOK_ACCOUNT_TYPE_LIABILITY = "liability"
BOOK_ACCOUNT_TYPE_EQUITY = "equity"
BOOK_ACCOUNT_TYPE_REVENUE = "revenue"
BOOK_ACCOUNT_TYPE_EXPENSE = "expense"
BOOK_ACCOUNT_TYPE_CHOICES: list[tuple[str, str]] = [
    (BOOK_ACCOUNT_TYPE_ASSET, "أصول"),
    (BOOK_ACCOUNT_TYPE_LIABILITY, "خصوم"),
    (BOOK_ACCOUNT_TYPE_EQUITY, "حقوق ملكية"),
    (BOOK_ACCOUNT_TYPE_REVENUE, "إيرادات"),
    (BOOK_ACCOUNT_TYPE_EXPENSE, "مصاريف"),
]
BOOK_ACCOUNT_TYPE_LABELS: dict[str, str] = dict(BOOK_ACCOUNT_TYPE_CHOICES)

#: أنواعُ الحركة — الورقةُ التي جاءت منها، لا نوعُ الحساب. و`daily_report` هو
#: الإدخالُ اليوميّ/الشهريّ المباشر حين تكون طريقةُ الإدخال «إدخال الشهر».
BOOK_ENTRY_KIND_SALES_INVOICE = "sales_invoice"
BOOK_ENTRY_KIND_PURCHASE_INVOICE = "purchase_invoice"
BOOK_ENTRY_KIND_EXPENSE = "expense"
BOOK_ENTRY_KIND_BANK_MOVEMENT = "bank_movement"
BOOK_ENTRY_KIND_DAILY_REPORT = "daily_report"
BOOK_ENTRY_KIND_CHOICES: list[tuple[str, str]] = [
    (BOOK_ENTRY_KIND_SALES_INVOICE, "فاتورة بيع"),
    (BOOK_ENTRY_KIND_PURCHASE_INVOICE, "فاتورة شراء"),
    (BOOK_ENTRY_KIND_EXPENSE, "مصروف"),
    (BOOK_ENTRY_KIND_BANK_MOVEMENT, "حركة بنك"),
    (BOOK_ENTRY_KIND_DAILY_REPORT, "تقرير يومي"),
]
BOOK_ENTRY_KIND_LABELS: dict[str, str] = dict(BOOK_ENTRY_KIND_CHOICES)


def _fill_tenant_from_entry(instance) -> None:
    """شركةُ بند الحركة تتبع حركتها — والحركةُ تتبع زبونها.

    كـ`_fill_tenant_from_client_service`: النموذجُ الابنُ لا زبونَ له مباشرةً،
    فقاعدتُه كقاعدة بقية النماذج الابنة — تمتلئ من أبيها ولا تُكتب لشركةٍ مخالفة.
    """
    if not instance.entry_id:
        return
    expected = instance.entry.tenant_id
    if instance.tenant_id is None:
        instance.tenant_id = expected
    elif instance.tenant_id != expected:
        raise ValueError(
            "شركةُ بند الحركة تخالف شركة حركتها — لا يُكتب سجلٌّ عابرٌ للمكاتب.",
        )


class BookAccountTemplate(models.Model):
    """شجرةُ الحساب الافتراضية للمنصّة — **بلا `tenant` عمداً** كـ`TaxThreshold`.

    الأكوادُ واحدةٌ لكل المكاتب (والنسخةُ لكل شركة تعني كودين مختلفين للحساب
    نفسه). والمكتبُ يعدّل نسختَه في `OfficeBookAccount`، والزبونُ يأخذ نسخةً
    عند إنشاء دفتره — لا مرجعَ حيّ إلى هذا الصفّ.
    """

    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    book_kind = models.CharField(
        max_length=10, choices=BOOK_KIND_CHOICES, verbose_name="نوع الدفتر",
    )
    code = models.CharField(max_length=20, verbose_name="الكود")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    #: كودُ الأب لا مفتاحُه: الشجرةُ تُكتب نصّاً في اللائحة وتُقرأ كوداً في الواجهة.
    parent_code = models.CharField(
        max_length=20, blank=True, default="", verbose_name="كود الأب",
    )
    account_type = models.CharField(
        max_length=12, choices=BOOK_ACCOUNT_TYPE_CHOICES, verbose_name="نوع الحساب",
    )
    is_system = models.BooleanField(default=True, verbose_name="حساب نظام")

    class Meta:
        verbose_name = "قالب حساب دفتر"
        verbose_name_plural = "قوالب حسابات الدفاتر"
        ordering = ["tax_system", "book_kind", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tax_system", "book_kind", "code"],
                name="uniq_book_template_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tax_system}/{self.book_kind}/{self.code}"


class OfficeBookAccount(models.Model):
    """نسخةُ المكتب من الشجرة — تُنشأ حين يعدّل قالباً، وتُنسخ عنها دفاترُ زبائنه.

    **`is_edited`** تقول «هذا صفٌّ عدّله المكتب» لا «هذا صفٌّ من المنصّة» — فلا
    يُظنّ التعديلُ ضياعاً عند أول قراءة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_book_accounts",
        verbose_name="المكتب",
    )
    tax_system = models.CharField(
        max_length=2, choices=TAX_SYSTEM_CHOICES, verbose_name="النظام الضريبي",
    )
    book_kind = models.CharField(
        max_length=10, choices=BOOK_KIND_CHOICES, verbose_name="نوع الدفتر",
    )
    code = models.CharField(max_length=20, verbose_name="الكود")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    parent_code = models.CharField(
        max_length=20, blank=True, default="", verbose_name="كود الأب",
    )
    account_type = models.CharField(
        max_length=12, choices=BOOK_ACCOUNT_TYPE_CHOICES, verbose_name="نوع الحساب",
    )
    is_system = models.BooleanField(default=True, verbose_name="حساب نظام")
    is_edited = models.BooleanField(default=False, verbose_name="عدّله المكتب")

    class Meta:
        verbose_name = "حساب دفتر مكتب"
        verbose_name_plural = "حسابات دفاتر المكتب"
        ordering = ["tax_system", "book_kind", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "tax_system", "book_kind", "code"],
                name="uniq_office_book_account_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}/{self.tax_system}/{self.code}"


class ClientBook(models.Model):
    """دفترُ زبونٍ واحد: نوعُه وتاريخُ فتحه — **ولا يُحذف**.

    وجودُه مشتقٌّ من خدمة مسك الدفاتر لا من حقلٍ هنا، وإيقافُ الخدمة يجعله
    للقراءة وحدها. و`kind_changed_on` يسجّل تاريخَ الانتقال من البسيط إلى
    المزدوج — فحين يتغيّر النوع يبقى معروفاً **من أيّ يوم** صار مزدوجاً.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_books",
        verbose_name="المكتب",
    )
    client = models.OneToOneField(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="book",
        verbose_name="الزبون",
    )
    kind = models.CharField(
        max_length=10, choices=BOOK_KIND_CHOICES, verbose_name="نوع الدفتر",
    )
    opened_on = models.DateField(verbose_name="يبدأ في")
    kind_changed_on = models.DateField(
        null=True, blank=True, verbose_name="تغيّر نوعه في",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "دفتر زبون"
        verbose_name_plural = "دفاتر الزبائن"
        ordering = ["client_id"]

    def __str__(self) -> str:
        return f"{self.client_id}:{self.kind}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class ClientBookAccount(models.Model):
    """شجرةُ حساب الزبون — **نسخةٌ واحدة عند إنشاء الدفتر**، لا مرجعٌ حيّ.

    `parent` مفتاحٌ حقيقيّ هنا (لا `parent_code` كالقالب): الشجرةُ صارت ملك
    الزبون، والدورانُ فيها استعلامٌ لا مطابقةَ نصوص.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_book_accounts",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="book_accounts",
        verbose_name="الزبون",
    )
    code = models.CharField(max_length=20, verbose_name="الكود")
    name = models.CharField(max_length=200, verbose_name="الاسم")
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="الحساب الأب",
    )
    account_type = models.CharField(
        max_length=12, choices=BOOK_ACCOUNT_TYPE_CHOICES, verbose_name="نوع الحساب",
    )
    is_system = models.BooleanField(default=True, verbose_name="حساب نظام")
    #: التعطيلُ بدل الحذف: حسابٌ استُعمل في حركةٍ لا يُمحى، ويُخفى إن لم يعد.
    is_active = models.BooleanField(default=True, verbose_name="مفعّل")

    class Meta:
        verbose_name = "حساب دفتر زبون"
        verbose_name_plural = "حسابات دفاتر الزبائن"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "code"], name="uniq_client_book_account_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "client"], name="office_book_tree_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}/{self.code}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class ClientBookSequence(models.Model):
    """عدّادُ ترقيم حركات الدفتر — **أداةُ القفل والترقيم** (#286/د3).

    `(client, year) → last_number`، والزيادةُ داخل `transaction.atomic()` بعد
    `select_for_update` على هذا الصفّ. **لا `MAX(number)+1` ولا `count()+1`**:
    كلاهما يقرأ لقطةً قديمة تحت التزامن فيُكرّر رقماً أو يُحدث فجوة. والقيدُ
    `(client, year, number)` على `BookEntry` طبقةٌ ثانية تُساند القفل لا تُبدله.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_book_sequences",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="book_sequences",
        verbose_name="الزبون",
    )
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    last_number = models.PositiveIntegerField(default=0, verbose_name="آخر رقم")

    class Meta:
        verbose_name = "عدّاد دفتر زبون"
        verbose_name_plural = "عدّادات دفاتر الزبائن"
        ordering = ["client_id", "year"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "year"], name="uniq_client_book_sequence_year",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}/{self.year}:{self.last_number}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class BookEntry(models.Model):
    """حركةٌ في دفتر زبون: مرقَّمةٌ بلا فجوات، **ولا تُحذف ولا تُعدَّل**.

    `reverses` يقول «هذه الحركة تُبطل تلك»، و`reversed_by` (عكسيّ الروابط) يقول
    العكس. والتصحيحُ حركةٌ جديدة ببنودٍ معكوسة، فالأصلُ يبقى في التاريخ.
    و`reverses` **`OneToOneField`** لا `ForeignKey`: عكسٌ واحد على الأكثر لكل حركة
    فرادةً في القاعدة — طبقةٌ ثانية تُساند قفلَ الأصل في `reverse_entry`.

    **وأوراقُها في `BookEntryDocument` لا في عمود**: حركةُ الشهر تُدخل أوراقَه
    كلَّها، وعكسُها يجب أن يُعيدها إلى «للإدخال» — وربطٌ يُقرأ أصدقُ من عمودٍ
    يُكتب. والقاعدةُ «حركةٌ حيّةٌ واحدة على الأكثر لكل ورقة» في الخدمة تحت قفل.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_book_entries",
        verbose_name="المكتب",
    )
    client_book = models.ForeignKey(
        # `PROTECT` لا `CASCADE`: دفترٌ فيه تاريخٌ لا يُطوى من تحت حركاته (#286/د4).
        ClientBook,
        on_delete=models.PROTECT,
        related_name="entries",
        verbose_name="الدفتر",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.PROTECT,
        related_name="book_entries",
        verbose_name="الزبون",
    )
    #: سنةُ الترقيم — سنةُ `entry_date`، مخزَّنةٌ لأن الترقيم يبدأ من أول كل سنة.
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    number = models.PositiveIntegerField(verbose_name="الرقم")
    entry_date = models.DateField(verbose_name="تاريخ الحركة")
    kind = models.CharField(
        max_length=20, choices=BOOK_ENTRY_KIND_CHOICES, verbose_name="نوع الحركة",
    )
    memo = models.CharField(
        max_length=300, blank=True, default="", verbose_name="البيان",
    )
    reverses = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversed_by",
        verbose_name="تُبطل الحركة",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_book_entries",
        verbose_name="أنشأها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "حركة دفتر زبون"
        verbose_name_plural = "حركات دفاتر الزبائن"
        ordering = ["year", "number"]
        constraints = [
            # فرادةٌ **غير مشروطة**: الشرطُ في `UniqueConstraint` تتجاهله MySQL
            # بصمت فتمرّ الهجرة ويغيب القيد في الإنتاج.
            models.UniqueConstraint(
                fields=["client", "year", "number"], name="uniq_book_entry_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "client", "year"], name="client_book_entry_year",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}/{self.year}-{self.number}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class BookEntryLine(models.Model):
    """بندُ حركة: حسابٌ ومدينٌ أو دائن — وطرفٌ مقابلٌ نصّاً حين لا يكون حساباً.

    `side_party` اسمُ الطرف الآخر كما ورد في الورقة («شركة كذا») — لا يُصطنع له
    حسابٌ في شجرة الزبون، ولا يُترك المبلغ بلا قول مَن قابلَه.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_book_entry_lines",
        verbose_name="المكتب",
    )
    entry = models.ForeignKey(
        BookEntry,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="الحركة",
    )
    account = models.ForeignKey(
        ClientBookAccount,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name="الحساب",
    )
    debit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="مدين",
    )
    credit = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="دائن",
    )
    side_party = models.CharField(
        max_length=200, blank=True, default="", verbose_name="الطرف المقابل",
    )

    class Meta:
        verbose_name = "بند حركة دفتر"
        verbose_name_plural = "بنود حركات الدفاتر"
        ordering = ["entry_id", "id"]

    def __str__(self) -> str:
        return f"{self.entry_id}/{self.account_id}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_entry(self)
        super().save(*args, **kwargs)


class BookEntryDocument(models.Model):
    """ورقةٌ أُدخلت في حركة — **ربطٌ لا عمود** (#286).

    الحركةُ الواحدة قد تُدخل أوراقَ الشهر كاملة (طريقةُ «إدخال الشهر»)، فعمودٌ
    واحدٌ على الحركة يترك بقيةَ الشهر في «للإدخال» إلى الأبد. والربطُ **يُقرأ**:
    عكسُ الحركة يُعيد أوراقَها إلى «للإدخال» بلا كتابة حالةٍ واحدة (د9).

    وقاعدةُ «حركةٌ حيّةٌ واحدة على الأكثر لكل ورقة» ليست هنا — القاعدةُ في
    `client_books.create_entry` داخل `transaction.atomic()` وبقفلٍ على صفوف
    الأوراق، لأن الحارسَ الذي يقرأ ثم يكتب بلا قفلٍ يمرّ تحت التزامن.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_book_entry_documents",
        verbose_name="المكتب",
    )
    entry = models.ForeignKey(
        BookEntry,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="الحركة",
    )
    document = models.ForeignKey(
        # `PROTECT`: ورقةٌ دخلت في حركةٍ لا تُمحى من تحت رابطها.
        DocumentChecklistItem,
        on_delete=models.PROTECT,
        related_name="book_entry_links",
        verbose_name="الورقة",
    )

    class Meta:
        verbose_name = "ورقة حركة دفتر"
        verbose_name_plural = "أوراق حركات الدفاتر"
        ordering = ["entry_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "document"], name="uniq_entry_document",
            ),
        ]
        indexes = [
            # «هل هذه الورقة مُدخلة؟» سؤالُ «للإدخال» — بمفتاح المكتب والورقة.
            models.Index(
                fields=["tenant", "document"], name="client_book_entry_doc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entry_id}/{self.document_id}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_entry(self)
        super().save(*args, **kwargs)


# ── الأتعاب: الاشتراك والمسودّات والاعتماد (#282، الجزء أ١) ────────────────────
#
# **ثلاثةُ مصادرَ لسطر المسودّة لا واحد**: اشتراكٌ بسعرٍ مؤرَّخ، أو سعرُ خدمةٍ
# استحقّت فترتُها في الشهر، أو خدمةٌ إضافيةٌ نُفِّذت. والسطرُ يحمل مصدرَه صريحاً
# (`source`) لتشرحه الواجهةُ بلا تخمينٍ من الاسم.
#
# **ولا تُمحى مسودّة**: `draft → approved` أو `draft → cancelled` قبل الاعتماد،
# والمعتمدةُ سندُ فاتورةِ الأتعاب في أ٢. والحذفُ ليس فعلاً في النماذج كلّها.
#
# **والاشتراك بتاريخ سريانٍ لا بعمودِ سعرٍ واحد**: تغييرُ السعر **يضيف صفّاً** ولا
# يعدّل ما قبله، فتبقى مسودّةُ الشهر الماضي تقرأ سعرَها. وهي القاعدةُ نفسُها في
# `ClientServiceFrequency`، ولها الدالّةُ الواحدةُ في `accounting_office/fees.py`
# (`subscription_on`) — لا نسخةً ثانية من «أكبر `starts_on` لا يتجاوز الشهر».
#
# **وفاتورةُ الأتعاب ليست هنا**: `FeeDraft` مسودّةُ حسابٍ تُحسب وتُعتمد، والفاتورةُ
# مستندٌ يُرقَّم ويُطبع (أ٢) — لا يُدمجان في صفٍّ واحدٍ لأن أحدهما حسابٌ والآخر
# مستند.
FEE_CADENCE_MONTHLY = "monthly"
#: الدوريّةُ الوحيدةُ اليوم — الحقلُ موجودٌ لأن الاشتراك قد يكون ربعياً لاحقاً،
#: ودوريّةٌ تُخزَّن ولا يولّدها المولّدُ وعدٌ لا يُوفى. تُضاف صفّاً مع دعمها في
#: `fees._subscription_lines` لا قبله.
FEE_CADENCE_CHOICES: list[tuple[str, str]] = [
    (FEE_CADENCE_MONTHLY, "شهري"),
]
FEE_CADENCE_LABELS: dict[str, str] = dict(FEE_CADENCE_CHOICES)

FEE_DRAFT_STATUS_DRAFT = "draft"
FEE_DRAFT_STATUS_APPROVED = "approved"
FEE_DRAFT_STATUS_CANCELLED = "cancelled"
FEE_DRAFT_STATUS_CHOICES: list[tuple[str, str]] = [
    (FEE_DRAFT_STATUS_DRAFT, "مسودّة"),
    (FEE_DRAFT_STATUS_APPROVED, "معتمدة"),
    (FEE_DRAFT_STATUS_CANCELLED, "ملغاة"),
]
FEE_DRAFT_STATUS_LABELS: dict[str, str] = dict(FEE_DRAFT_STATUS_CHOICES)

FEE_LINE_SOURCE_SUBSCRIPTION = "subscription"
FEE_LINE_SOURCE_SERVICE = "service"
FEE_LINE_SOURCE_EXTRA = "extra"
FEE_LINE_SOURCE_CHOICES: list[tuple[str, str]] = [
    (FEE_LINE_SOURCE_SUBSCRIPTION, "اشتراك"),
    (FEE_LINE_SOURCE_SERVICE, "خدمة"),
    (FEE_LINE_SOURCE_EXTRA, "خدمة إضافية"),
]
FEE_LINE_SOURCE_LABELS: dict[str, str] = dict(FEE_LINE_SOURCE_CHOICES)

FEE_EXTRA_DESTINATION_NEXT_MONTH = "next_month"
FEE_EXTRA_DESTINATION_STANDALONE = "standalone"
FEE_EXTRA_DESTINATION_CHOICES: list[tuple[str, str]] = [
    (FEE_EXTRA_DESTINATION_NEXT_MONTH, "مسودّة الشهر القادم"),
    (FEE_EXTRA_DESTINATION_STANDALONE, "فاتورة لحالها"),
]
FEE_EXTRA_DESTINATION_LABELS: dict[str, str] = dict(FEE_EXTRA_DESTINATION_CHOICES)


def fee_draft_alert_ref(draft_id) -> str:
    """مفتاحُ تنبيه المسودّة الواحد — يقرؤه التوليدُ وقراءةُ الجرس معاً.

    نسخةٌ ثانية من الصيغة (`"fee_draft:<id>"`) في موضعٍ آخر تفترق عن الأولى عند
    أوّل تعديلٍ بصمت، فيتكرّر التنبيه أو لا يسقط باعتماد مسودّته.
    """
    return f"fee_draft:{draft_id}"


def assert_fee_amount(amount, *, field="amount") -> None:
    """مبلغُ الأتعاب: غيرُ سالبٍ وبخانتين عشريتين على الأكثر — والرسالةُ بالحقل.

    يُطبَّع قبل الفحص لأن `Decimal("300")` و`300` يصلان من مسارين (المسلسِل
    يمرّر `Decimal`، والنداءُ البرمجيّ قد يمرّر رقماً)، وقاعدةُ المال واحدة.
    """
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "مبلغٌ غير صالح."}) from None
    if not value.is_finite() or value < 0:
        raise ValidationError({field: "المبلغ لا يكون سالباً."})
    if value != value.quantize(Decimal("0.01")):
        raise ValidationError({field: "المبلغ بخانتين عشريتين على الأكثر."})


class FeeSubscription(models.Model):
    """اشتراكُ زبونٍ **بتاريخ سريانٍ**: صفٌّ لكل تغييرِ سعر، ولا تعديلَ لما قبله.

    «سعرُ شهرٍ ما» = الصفُّ ذو أكبر `starts_on` لا يتجاوز آخرَ الشهر (انظر
    `fees.subscription_on`). والفرادةُ على `(client, starts_on)` تجعل كتابةَ
    السعر نفسه بتاريخه مرّةً واحدة: الطلبُ المكرَّر **يُرفض 400** لا يضاعف الصفّ.

    **و`paused_from`/`paused_to` إيقافُ فوترةٍ مؤقّت**: الشهرُ الذي يبدأ داخل
    المدى لا مسودّةَ له. و`ended_on` إنهاءٌ نهائيّ — صفٌّ انتهى قبل الشهر لا
    يولّد شيئاً، وانتهاؤه في منتصفه يُنسب بعدد أيامه.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_subscriptions",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="fee_subscriptions",
        verbose_name="الزبون",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="office_fee_subscriptions",
        verbose_name="العملة",
    )
    cadence = models.CharField(
        max_length=20,
        choices=FEE_CADENCE_CHOICES,
        default=FEE_CADENCE_MONTHLY,
        verbose_name="الدورية",
    )
    starts_on = models.DateField(verbose_name="سارية من")
    paused_from = models.DateField(null=True, blank=True, verbose_name="إيقاف الفوترة من")
    paused_to = models.DateField(null=True, blank=True, verbose_name="إيقاف الفوترة إلى")
    ended_on = models.DateField(null=True, blank=True, verbose_name="تنتهي في")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإدخال")

    class Meta:
        verbose_name = "اشتراك أتعاب"
        verbose_name_plural = "اشتراكات الأتعاب"
        ordering = ["starts_on", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "starts_on"],
                name="uniq_fee_subscription_start",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="fee_subscription_amount_not_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(ended_on__isnull=True)
                    | models.Q(ended_on__gte=models.F("starts_on"))
                ),
                name="fee_subscription_ends_after_start",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(paused_from__isnull=True)
                    | models.Q(paused_to__isnull=True)
                    | models.Q(paused_to__gte=models.F("paused_from"))
                ),
                name="fee_subscription_pause_ordered",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "client"], name="office_fee_subs_tenant_client",
            ),
        ]
    def __str__(self) -> str:
        return f"{self.client_id}@{self.starts_on}={self.amount}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        assert_fee_amount(self.amount)
        super().save(*args, **kwargs)


class ClientServicePrice(models.Model):
    """سعرُ خدمةِ زبونٍ في طريقة «سعرٌ لكل خدمة» — صفٌّ لكل خدمةِ زبون.

    **مربوطٌ بـ`ClientService`** لا بالكتالوج: السعرُ يخصّ اتفاقَ هذا الزبون على
    هذه الخدمة، وكتالوجُ المكتب لا يعرف أسعارَ زبائنه. وفرادةُ `client_service`
    تجعل «سعرُ الخدمة» سؤالاً واحداً له جوابٌ واحد.

    **ولا تاريخَ سريانٍ هنا**: تغييرُ السعر يُحدَّث في هذا الصفّ، والمسودّاتُ
    السابقة لا تتغيّر لأن سطورها لقطةٌ محفوظة (والمدفوعُ لا يُعاد حسابه).
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_client_service_prices",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="service_prices",
        verbose_name="الزبون",
    )
    client_service = models.OneToOneField(
        ClientService,
        on_delete=models.CASCADE,
        related_name="price",
        verbose_name="خدمة الزبون",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="السعر")

    class Meta:
        verbose_name = "سعر خدمة زبون"
        verbose_name_plural = "أسعار خدمات الزبائن"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="client_service_price_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_service_id}={self.amount}"

    def save(self, *args, **kwargs):
        if self.client_service_id:
            self.client_id = self.client_service.client_id
        _fill_tenant_from_client(self)
        assert_fee_amount(self.amount)
        super().save(*args, **kwargs)


class FeeExtraService(models.Model):
    """خدمةٌ إضافيةٌ نُفِّذت للزبون بسعرها — **تُسجَّل عند التنفيذ لا عند الفوترة**.

    وتسير إلى **مسودّة الشهر القادم** (نُفِّذت في آذار ⇒ مسودّةُ نيسان)، أو إلى
    «فاتورة لحالها»: عملٌ كبيرٌ لا يُجمَع مع اشتراكٍ شهريّ (تأسيسُ شركةٍ مثلاً).

    **وحقلان مختلفان لا حقلٌ واحد**: `draft` **اختيارُ وجهة** (إلى مسودّةٍ أو
    فاتورةٍ لحالها)، و`billed_draft` **مفتاحُ الربط** بالمسودّة التي فوترتها.
    وبلا الربط كانت إضافةٌ تُسجَّل بعد توليد مسودّة شهرها تضيع بصمت: الشهرُ لقطةٌ
    لا تُعاد، والتوليدُ التالي يقرأ شهرَه وحده. فيُربط في المعاملة نفسها،
    والإلغاءُ يُعيده `None` فتلحق أوّلَ مسودّةٍ تالية.
    """

    DESTINATION_NEXT_MONTH = FEE_EXTRA_DESTINATION_NEXT_MONTH
    DESTINATION_STANDALONE = FEE_EXTRA_DESTINATION_STANDALONE

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_extras",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="fee_extras",
        verbose_name="الزبون",
    )
    service_name = models.CharField(max_length=200, verbose_name="الخدمة")
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    performed_on = models.DateField(verbose_name="نُفِّذت في")
    draft = models.CharField(
        max_length=20,
        choices=FEE_EXTRA_DESTINATION_CHOICES,
        default=FEE_EXTRA_DESTINATION_NEXT_MONTH,
        verbose_name="إلى",
    )
    #: المسودّةُ التي فوترت هذه الإضافة — `PROTECT` لأن المسودّةَ سندٌ لا يُمحى،
    #: و`None` = لم تُفوتر بعد (فتلتقطها أوّلُ مسودّةٍ تالية).
    billed_draft = models.ForeignKey(
        # نصّاً لا صنفاً: `FeeDraft` مُعرَّفٌ بعد هذا النموذج في الملفّ نفسه.
        "FeeDraft",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="billed_extras",
        verbose_name="المسودّة المفوتر فيها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإدخال")

    class Meta:
        verbose_name = "خدمة إضافية"
        verbose_name_plural = "الخدمات الإضافية"
        ordering = ["performed_on", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="fee_extra_amount_not_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "client", "performed_on"],
                name="office_fee_extra_client_month",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service_name}={self.amount}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        assert_fee_amount(self.amount)
        super().save(*args, **kwargs)


class FeeDraft(models.Model):
    """مسودّةُ أتعاب شهرٍ لزبون — **واحدةٌ لا أكثر** بفرادة `(client, year, month)`.

    الفرادةُ هي «مرّتان في اليوم نفسه = مسودّةٌ واحدة»: المولّدُ يعتمد على القاعدة
    لا على ذاكرةٍ في العملية. والمسودّةُ **لقطة**: سطورُها ومجموعُها يُحفظان عند
    التوليد، فلا يتغيّر مبلغُ شهرٍ مضى بتغيّر سعرٍ أو إضافةٍ لاحقة.

    **`total` = `subtotal` في الجزء أ١**: لا ضريبةَ على الأتعاب بعد (مستندُ أ٢ هو
    الذي يحمل حقولَه القانونية) — والحقلان موجودان ليقرأ المستندُ مصدرَهما الواحد
    ولا يُعاد حسابُ مجموعٍ في موضعٍ ثانٍ.

    و`approved_by`/`approved_at`/`approved_note` تُكتب عند الاعتماد مرّةً واحدة،
    و`draft → approved` تُقصي أيّ تغييرٍ لاحقٍ على السطور (`fees` لا تمسّه).
    """

    STATUS_DRAFT = FEE_DRAFT_STATUS_DRAFT
    STATUS_APPROVED = FEE_DRAFT_STATUS_APPROVED
    STATUS_CANCELLED = FEE_DRAFT_STATUS_CANCELLED

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_drafts",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="fee_drafts",
        verbose_name="الزبون",
    )
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    month = models.PositiveSmallIntegerField(verbose_name="الشهر")
    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="المجموع قبل الضريبة",
    )
    total = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="الإجمالي",
    )
    status = models.CharField(
        max_length=10,
        choices=FEE_DRAFT_STATUS_CHOICES,
        default=FEE_DRAFT_STATUS_DRAFT,
        verbose_name="الحالة",
    )
    generated_at = models.DateTimeField(
        default=timezone.now, verbose_name="وقت التوليد",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_fee_drafts_approved",
        verbose_name="اعتمدها",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الاعتماد")
    approved_note = models.CharField(
        max_length=300, blank=True, default="", verbose_name="ملاحظة الاعتماد",
    )

    class Meta:
        verbose_name = "مسودّة أتعاب"
        verbose_name_plural = "مسودّات الأتعاب"
        ordering = ["-year", "-month", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "year", "month"], name="uniq_fee_draft_month",
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name="fee_draft_month_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0) & models.Q(total__gte=0),
                name="fee_draft_amounts_not_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"], name="office_fee_draft_tenant_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}@{self.year}-{self.month:02d}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


class FeeDraftLine(models.Model):
    """سطرُ مسودّة: **مصدرُه مكتوبٌ لا مستنتَج**، ومبلغُه لقطةٌ لا حسابٌ مؤجَّل.

    المصادرُ ثلاثة: الاشتراك (`subscription`)، وسعرُ خدمةٍ استحقّت (`service`)،
    وخدمةٌ إضافية (`extra`). والنصُّ (`label`) اسمُ الخدمة أو وصفُ الاشتراك — بلا
    مبلغٍ فيه، فيُعرض لمن لا يرى المبالغ بلا تسريب.
    """

    SOURCE_SUBSCRIPTION = FEE_LINE_SOURCE_SUBSCRIPTION
    SOURCE_SERVICE = FEE_LINE_SOURCE_SERVICE
    SOURCE_EXTRA = FEE_LINE_SOURCE_EXTRA

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_draft_lines",
        verbose_name="المكتب",
    )
    draft = models.ForeignKey(
        FeeDraft,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="المسودّة",
    )
    label = models.CharField(max_length=200, verbose_name="البيان")
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    source = models.CharField(
        max_length=20, choices=FEE_LINE_SOURCE_CHOICES, verbose_name="المصدر",
    )

    class Meta:
        verbose_name = "بند مسودّة أتعاب"
        verbose_name_plural = "بنود مسودّات الأتعاب"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="fee_draft_line_amount_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.draft_id}:{self.source}"

    def save(self, *args, **kwargs):
        if self.draft_id:
            self.tenant_id = self.draft.tenant_id
        super().save(*args, **kwargs)


# ── فاتورةُ الأتعاب الورقية (#282، أ٢/١) ───────────────────────────────────────
#
# **المسودّةُ حسابٌ والفاتورةُ مستند**، فلا يُدمجان: `FeeDraft` تُحسب وتُعتمد
# (أ١)، و`FeeInvoice` تُرقَّم وتُطبع بعد الاعتماد، وتحمل حقولَها القانونية لقطةً.
# ولذلك `total` هنا **شاملٌ للضريبة** و`tax_total` نصيبُها منه — مصدران لا واحد،
# فالورقةُ تطبع «قبل الضريبة» و«الضريبة» و«شاملاً الضريبة» من عمودين لا من حسابٍ
# وقتَ العرض (فاتورةٌ تُقرأ بعملية حسابٍ تُقرأ خطأً بعد تغيير نسبة).
#
# **و`is_tax_invoice` ليس حقلاً**: «الفوترة الرسمية» مطفأةٌ ومقفلة، وخاصيّةٌ لا
# حقلُ إعداد — فلا مفتاحَ يفتحها ولا صفٌّ يحملها.
FEE_INVOICE_KIND_INVOICE = "invoice"
FEE_INVOICE_KIND_CREDIT_NOTE = "credit_note"
FEE_INVOICE_KIND_SUPPLEMENTARY = "supplementary"
FEE_INVOICE_KIND_CHOICES: list[tuple[str, str]] = [
    (FEE_INVOICE_KIND_INVOICE, OFFICE_FEE_INVOICE_LABEL),
    (FEE_INVOICE_KIND_CREDIT_NOTE, "إشعار دائن"),
    (FEE_INVOICE_KIND_SUPPLEMENTARY, "فاتورة تكميلية"),
]
FEE_INVOICE_KIND_LABELS: dict[str, str] = dict(FEE_INVOICE_KIND_CHOICES)

#: عنوانُ الورقة الافتراضيّ **بحسب نظام المُصدِر الضريبي** — يُخزَّن لحظةَ
#: الإصدار (أو يُقرأ من إعداد `fee_invoice_title`) فلا يغيّر تعديلُ العنوان
#: ورقةً خرجت. ولا «فاتورة ضريبية» ولا «חשבונית מס» فيه.
FEE_INVOICE_TITLE_PS = OFFICE_FEE_INVOICE_LABEL
FEE_INVOICE_TITLE_IL = "חשבון עסקה"
FEE_INVOICE_TITLES: dict[str, str] = {
    "PS": FEE_INVOICE_TITLE_PS,
    "IL": FEE_INVOICE_TITLE_IL,
}
#: عنوانُ ورقة الإشعار الدائن — **ليس عنوان الفاتورة** (#282/أ٢): ورقةٌ تحمل
#: عنوانَ الفاتورة على مبلغٍ دائنٍ تُقرأ مطالبةً، والعنوانُ يقول نوعَ المستند.
FEE_INVOICE_CREDIT_TITLE_PS = "إشعار دائن أتعاب"
FEE_INVOICE_CREDIT_TITLE_IL = "הודעת זיכוי"
FEE_INVOICE_CREDIT_TITLES: dict[str, str] = {
    "PS": FEE_INVOICE_CREDIT_TITLE_PS,
    "IL": FEE_INVOICE_CREDIT_TITLE_IL,
}

#: سطرُ النفي الثابت — **في كل صفحة، لا يُطفأ ولا يُحذف بإعداد**. ورقةٌ بلا نفيٍ
#: تدّعي الرسمية، والعقوبةُ عليها في القانون نفسه (م55/1 فلسطينياً: ضعفُ الضريبة).
FEE_INVOICE_NOT_TAX_LINE_PS = "ليست فاتورة ضريبية"
FEE_INVOICE_NOT_TAX_LINE_IL = "אינו חשבונית מס"
FEE_INVOICE_NOT_TAX_LINES: dict[str, str] = {
    "PS": FEE_INVOICE_NOT_TAX_LINE_PS,
    "IL": FEE_INVOICE_NOT_TAX_LINE_IL,
}

#: سلسلتان لا واحدة: الفاتورةُ (والتكميلية) على `أتعاب-{السنة}`، والإشعارُ الدائن
#: على `إشعار-أتعاب-{السنة}` — فإشعارٌ دائنٌ برقمٍ من سلسلة الفواتير يقرأ
#: فاتورةً ثانية في كشف الزبون.
FEE_INVOICE_SERIES_PREFIX = "أتعاب"
FEE_INVOICE_CREDIT_SERIES_PREFIX = "إشعار-أتعاب"
FEE_INVOICE_SERIES_MAX_LENGTH = 20
#: عرضُ العدّاد: خمسةُ أرقامٍ — `أتعاب-2026-00007`.
FEE_INVOICE_SEQUENCE_WIDTH = 5


def fee_invoice_series(year) -> str:
    """سلسلةُ الفاتورة والتكميلية لسنةٍ — البادئةُ تحمل السنة لا عموداً ثانياً."""
    return f"{FEE_INVOICE_SERIES_PREFIX}-{int(year)}"


def fee_invoice_credit_series(year) -> str:
    """سلسلةُ الإشعار الدائن لسنةٍ — منفصلةٌ عن سلسلة الفواتير عمداً."""
    return f"{FEE_INVOICE_CREDIT_SERIES_PREFIX}-{int(year)}"


def fee_invoice_number(series: str, number: int) -> str:
    """الصيغةُ النهائية `"{series}-{n:05d}"` — في موضعٍ واحد يقرؤه الحارسُ والاختبار."""
    return f"{series}-{int(number):0{FEE_INVOICE_SEQUENCE_WIDTH}d}"


class FeeInvoiceSequence(models.Model):
    """عدّادُ ترقيم فواتير المكتب — **أداةُ القفل والترقيم** لا عموداً محسوباً.

    `(tenant, year, series) → last_number`، والزيادةُ داخل `transaction.atomic()`
    بعد `select_for_update` على هذا الصفّ. **لا `MAX(number)+1` ولا `count()+1`**:
    كلاهما يقرأ لقطةً قديمة تحت التزامن فيُكرّر رقماً أو يُحدث فجوة — ورقمُ
    فاتورةٍ مكرَّر عطبٌ محاسبيّ لا خطأُ عرض. والقيدُ `(tenant, number)` على
    `FeeInvoice` طبقةٌ ثانية تُساند القفل لا تُبدله.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_invoice_sequences",
        verbose_name="المكتب",
    )
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    series = models.CharField(
        max_length=FEE_INVOICE_SERIES_MAX_LENGTH, verbose_name="السلسلة",
    )
    last_number = models.PositiveIntegerField(default=0, verbose_name="آخر رقم")

    class Meta:
        verbose_name = "عدّاد فواتير الأتعاب"
        verbose_name_plural = "عدّادات فواتير الأتعاب"
        ordering = ["tenant_id", "year", "series"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year", "series"],
                name="uniq_fee_invoice_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.series}:{self.last_number}"


class FeeInvoice(models.Model):
    """فاتورةُ أتعابٍ **مرقَّمةٌ لا تُمحى** — والتصحيحُ إشعارٌ دائن أو تكميلية.

    **وثلاثةُ أنواعٍ في صفٍّ واحد** (`kind`) لأن الحقولَ واحدة والحقولَ القانونيةَ
    واحدة: إشعارٌ دائنٌ يحمل كلَّ حقول الفاتورة مع قيمته وسببه (م.4–م.12 من
    تعليمات 25/2025)، والنسختان تختلفان في السلسلة والعلاقة لا في الشكل.

    **ولا حذف ولا تعديل**: `cancelled_at` وحدها تُكتب — وقبل إنشاء الرابط فقط،
    لأن ورقةً بيد الزبون لا يُقال لها «أُلغيت» بضغطةٍ في الخادم.
    """

    KIND_INVOICE = FEE_INVOICE_KIND_INVOICE
    KIND_CREDIT_NOTE = FEE_INVOICE_KIND_CREDIT_NOTE
    KIND_SUPPLEMENTARY = FEE_INVOICE_KIND_SUPPLEMENTARY

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_invoices",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        #: تاريخٌ لا يُمحى: فاتورةُ زبونٍ تبقى بعد إنهائه وبعد أيّ تصفيةِ سجلّ.
        on_delete=models.PROTECT,
        related_name="fee_invoices",
        verbose_name="الزبون",
    )
    #: **`source_draft` لا `draft`، وFK لا `OneToOne`** (#282/أ٢): الإلغاءُ
    #: يعيد المسودّةَ `approved → draft` فتُعتمد ثانيةً وتُصدر ورقةً جديدةً
    #: برقمٍ جديد — فمسودّةٌ واحدة قد تُنتج ورقتين في التاريخ (الملغاة والسارية).
    #: **ولا فرادة:** المفتاحُ أثرٌ تاريخيّ لا قيدُ «ورقةٌ واحدة لكل مسودّة»؛
    #: والقيدُ الحقيقيّ «لا فاتورتان حيّتان لمسودّةٍ واحدة» يُفرض في الخدمة
    #: تحت قفل صفّ المسودّة (`select_for_update` في الاعتماد)، لأن فرادةً
    #: مشروطةً (`cancelled_at IS NULL`) لا تدعمها MySQL وتُلغى بصمت.
    source_draft = models.ForeignKey(
        FeeDraft,
        on_delete=models.PROTECT,
        #: **فارغةٌ في التصحيح**: الإشعارُ الدائن والفاتورةُ التكميلية مستندان
        #: على فاتورةٍ (`related_invoice`) لا فاتورةُ شهرٍ ثانية.
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="المسودّة المصدر",
    )
    kind = models.CharField(
        max_length=20,
        choices=FEE_INVOICE_KIND_CHOICES,
        default=FEE_INVOICE_KIND_INVOICE,
        verbose_name="النوع",
    )
    #: الإشعارُ الدائن والفاتورةُ التكميلية يشيران إلى فاتورتهما — والأصلُ يبقى.
    related_invoice = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
        verbose_name="الفاتورة الأصل",
    )
    number = models.CharField(max_length=40, verbose_name="الرقم")
    #: عنوانُ الورقة كما طُبعت — نصُّ الإعداد افتراضُه، وهو لقطةٌ لا مرجعٌ حيّ.
    title = models.CharField(max_length=60, verbose_name="عنوان الورقة")
    #: **نظامُ الورقة لقطةً** (#282/أ٢): يُقرأ منه عند كل عرض، ولا يُقرأ نظامُ
    #: الزبون الحيّ — تغييرُ نظام المكتب بعد الإصدار لا يقلب ورقةً عربيةً عبرية.
    tax_system = models.CharField(
        max_length=2,
        choices=[("PS", "فلسطيني"), ("IL", "إسرائيلي")],
        default="PS",
        verbose_name="النظام الضريبي",
    )
    #: **شاملٌ للضريبة**: الإجماليُ الذي يدفعه الزبون.
    total = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="الإجمالي")
    #: نصيبُ الضريبة من `total` — صفرٌ حين المكتبُ ليس مشتغلاً مرخّصاً.
    tax_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="قيمة الضريبة",
    )
    #: **نسبةُ الضريبة لقطةً** (#282/أ٢): تُخزَّن عند الإصدار ولا تُشتقّ عند
    #: العرض، فتغييرُ نسبة الشركة لا يعيد كتابة ورقةٍ خرجت. **وهي ليست مبلغاً**
    #: فلا تدخل `AMOUNT_KEYS`؛ ومبلغُها `tax_total` مقنَّعٌ كسائر المبالغ.
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الضريبة",
    )
    #: رقمُ الفاتورة الرسمية الخارجية (فاتورةٌ ضريبية أصدرها المكتب) — اختياريّ،
    #: وغيابُه هو الحالُ الغالب: ورقتُنا ليست فاتورةً ضريبية.
    external_number = models.CharField(
        max_length=60, blank=True, default="", verbose_name="رقم الفاتورة الخارجية",
    )
    issued_at = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الإصدار")
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_fee_invoices_issued",
        verbose_name="أصدرها",
    )
    cancelled_at = models.DateTimeField(
        null=True, blank=True, verbose_name="وقت الإلغاء",
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_fee_invoices_cancelled",
        verbose_name="ألغاها",
    )
    cancel_reason = models.CharField(
        max_length=300, blank=True, default="", verbose_name="سبب الإلغاء",
    )

    class Meta:
        verbose_name = OFFICE_FEE_INVOICE_LABEL
        verbose_name_plural = "فواتير الأتعاب"
        ordering = ["-issued_at", "-id"]
        constraints = [
            #: رقمٌ واحدٌ لفاتورةٍ واحدة في المكتب — طبقةٌ ثانية تُساند القفل.
            models.UniqueConstraint(
                fields=["tenant", "number"], name="uniq_fee_invoice_number",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_total__gte=0) & models.Q(total__gte=0),
                name="fee_invoice_amounts_not_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "client"], name="office_fee_inv_tenant_client",
            ),
            models.Index(
                fields=["tenant", "kind"], name="office_fee_inv_tenant_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} ({self.kind})"

    @property
    def is_tax_invoice(self) -> bool:
        """**ثابتٌ `False` غيرُ قابلٍ للضبط** — خاصيّةٌ لا حقلُ إعداد.

        «الفوترة الرسمية» مطفأةٌ ومقفلةٌ في هذه المرحلة: ورقةٌ تدّعي أنها فاتورة
        ضريبية وهي ليست كذلك تورّط المكتبَ والزبون (م55/1 فلسطينياً: ضعفُ
        الضريبة، وفي إسرائيل: خصمُ مدخلاتٍ بلا رقم تخصيص). ولا مفتاحَ إعدادٍ
        يفتحها — الفتحُ قرارُ منتجٍ يمرّ بتذكرة، لا قيمةٌ في صفّ.
        """
        return False

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled_at is not None

    @property
    def state(self) -> str:
        return "cancelled" if self.is_cancelled else "issued"

    @property
    def net_total(self) -> Decimal:
        """ما قبل الضريبة — `total - tax_total`، ولا عمودَ ثالثاً يفترق عنهما."""
        return self.total - self.tax_total

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        super().save(*args, **kwargs)


# ── الدفعات و«اللي عليه» وكشف الحساب (#283، الجزء أ) ─────────────────────────
#
# **الدفعةُ سندُ قبضٍ رقيق، والقيمةُ الكاملةُ مشتقّة**: التخصيصُ (`FeePaymentAllocation`)
# والشطبُ (`FeeWriteOff`) صفوفٌ إلحاقيّةٌ تُقرأ، و«المتبقّي» و«الرصيدُ الدائن» لا
# عمودَ لهما — تُحسبان في `accounting_office/payments.py` (`client_due`) مرّةً واحدة.
# عمودٌ مخزَّنٌ ثانٍ كان سيختلف عن الصفوف عند أوّل شطبٍ أو تخصيص، ويُصلَح بالكذب.
#
# **ولا حذفَ ولا تعديل**: `FeePayment`/`FeePaymentAllocation`/`FeeWriteOff` تُنشأ
# ولا تُلمَس بعدها (لا `PUT` ولا `PATCH` ولا `DELETE`)، والقيدُ في القاعدة للشطب
# `> 0` وللتخصيص `> 0`، ورقمُ الإشعار فريدٌ لكل مكتب.
FEE_PAYMENT_METHOD_CASH = "cash"
FEE_PAYMENT_METHOD_CHEQUE = "cheque"
FEE_PAYMENT_METHOD_TRANSFER = "transfer"
FEE_PAYMENT_METHOD_CARD = "card"
FEE_PAYMENT_METHOD_CHOICES: list[tuple[str, str]] = [
    (FEE_PAYMENT_METHOD_CASH, "نقد"),
    (FEE_PAYMENT_METHOD_CHEQUE, "شيك"),
    (FEE_PAYMENT_METHOD_TRANSFER, "تحويل"),
    (FEE_PAYMENT_METHOD_CARD, "بطاقة"),
]
FEE_PAYMENT_METHOD_LABELS: dict[str, str] = dict(FEE_PAYMENT_METHOD_CHOICES)


def assert_positive_fee_amount(amount, *, field="amount") -> None:
    """مبلغُ دفعةٍ أو تخصيصٍ أو شطب: **أكبرُ من صفر** وبخانتين كسائر الموديول.

    و`assert_fee_amount` وحدها لا تكفي: هي تسمح بالصفر لأن مبلغَ مسودّةٍ قد
    يكون صفراً، والدفعةُ الصفريّةُ سطرٌ لا معنى له في الحساب.
    """
    assert_fee_amount(amount, field=field)
    if (amount if isinstance(amount, Decimal) else Decimal(str(amount))) <= 0:
        raise ValidationError({field: "المبلغ يجب أن يكون أكبر من صفر."})


class FeePayment(models.Model):
    """دفعةٌ من الزبون — سندُ قبضٍ لا يُعدَّل ولا يُحذف بعد إنشائه.

    **ولا حقلَ عملة**: كـ`FeeDraft` — الأتعابُ بعملة المكتب الواحدة، وإدخالُ
    دفعةٍ بعملةٍ أخرى تحويلٌ لا دفعة.

    **و`amount` مبلغُ السند، لا مبلغُ تخصيصه**: الجزءُ غيرُ المخصَّص **رصيدٌ
    دائن** يُحسب من الصفوف (`credit` في `payments.py`) ولا يُخزَّن هنا هدراً.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_payments",
        verbose_name="المكتب",
    )
    client = models.ForeignKey(
        OfficeClient,
        on_delete=models.CASCADE,
        related_name="fee_payments",
        verbose_name="الزبون",
    )
    method = models.CharField(
        max_length=20, choices=FEE_PAYMENT_METHOD_CHOICES, verbose_name="طريقة الدفع",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    paid_at = models.DateField(verbose_name="تاريخ الدفع")
    note = models.CharField(
        max_length=300, blank=True, default="", verbose_name="ملاحظة",
    )
    #: `{year}-{n:05d}` من العدّاد المقفول (`FeeReceiptSequence`) — فريدٌ للمكتب.
    receipt_number = models.CharField(max_length=30, verbose_name="رقم الإشعار")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_fee_payments_created",
        verbose_name="سجّلها",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإدخال")

    class Meta:
        verbose_name = "دفعة أتعاب"
        verbose_name_plural = "دفعات الأتعاب"
        ordering = ["-paid_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "receipt_number"], name="uniq_fee_payment_receipt",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="fee_payment_amount_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "client", "paid_at"],
                name="office_fee_payment_client",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.receipt_number}={self.amount}"

    def save(self, *args, **kwargs):
        _fill_tenant_from_client(self)
        assert_positive_fee_amount(self.amount)
        super().save(*args, **kwargs)


class FeeReceiptSequence(models.Model):
    """عدّادُ أرقام الإشعارات — **القفلُ والترقيم** كـ`ClientBookSequence`.

    `select_for_update` على الصفّ يُسلسل الكُتّاب داخل `transaction.atomic`،
    والرقمُ يُنسخ إلى `FeePayment.receipt_number`. **لا `MAX+1` ولا `count+1`**:
    كلاهما يقرأ لقطةً قديمة تحت التزامن فيكرّر رقماً أو يُحدث فجوة.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_receipt_sequences",
        verbose_name="المكتب",
    )
    year = models.PositiveSmallIntegerField(verbose_name="السنة")
    last_number = models.PositiveIntegerField(default=0, verbose_name="آخر رقم")

    class Meta:
        verbose_name = "عدّاد إشعارات الأتعاب"
        verbose_name_plural = "عدّادات إشعارات الأتعاب"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "year"], name="uniq_fee_receipt_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.year}={self.last_number}"


class FeePaymentAllocation(models.Model):
    """تخصيصُ جزءٍ من دفعةٍ على مسودّةٍ معتمدة — **صفٌّ لكل (دفعة، مسودّة)**.

    والفرادةُ على `(payment, draft)` تجعل تخصيصَين لنفس المسودّة من الدفعة نفسها
    مستحيلاً في القاعدة: التصحيحُ تخصيصٌ من دفعةٍ أخرى أو شطبٌ، لا صفٌّ ثانٍ في
    الدفعة نفسها يُقرأ معه مجموعاً مضاعفاً.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_payment_allocations",
        verbose_name="المكتب",
    )
    payment = models.ForeignKey(
        FeePayment,
        on_delete=models.CASCADE,
        related_name="allocations",
        verbose_name="الدفعة",
    )
    #: `PROTECT`: مسودّةٌ عليها دفعاتٌ لا تُمحى من تحت تخصيصاتها.
    draft = models.ForeignKey(
        FeeDraft,
        on_delete=models.PROTECT,
        related_name="allocations",
        verbose_name="المسودّة",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")

    class Meta:
        verbose_name = "تخصيص دفعة"
        verbose_name_plural = "تخصيصات الدفعات"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "draft"], name="uniq_fee_payment_allocation",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="fee_payment_allocation_amount_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "draft"], name="office_fee_allocation_draft",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.payment_id}->{self.draft_id}={self.amount}"

    def save(self, *args, **kwargs):
        if self.payment_id:
            self.tenant_id = self.payment.tenant_id
        assert_positive_fee_amount(self.amount)
        super().save(*args, **kwargs)


class FeeWriteOff(models.Model):
    """شطبُ جزءٍ من مسودّةٍ معتمدة — **سطرٌ إلحاقيّ** بسببٍ مكتوبٍ ومَن كتبه.

    الشطبُ يخفّض `remaining` ولا يمحو الفاتورةَ ولا الدفعة: «تنازلنا عن المتبقّي»
    قرارٌ يُقرأ في الكشف، لا تصحيحُ مجموعةٍ يُخفي أثرَه.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="office_fee_write_offs",
        verbose_name="المكتب",
    )
    draft = models.ForeignKey(
        FeeDraft,
        on_delete=models.PROTECT,
        related_name="write_offs",
        verbose_name="المسودّة",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ")
    #: إلزاميٌّ غيرُ فارغ — يفرضه `payments.write_off_fee_draft` لا القاعدة.
    reason = models.CharField(max_length=300, verbose_name="السبب")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="office_fee_write_offs",
        verbose_name="شطبه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الشطب")

    class Meta:
        verbose_name = "شطب مسودّة أتعاب"
        verbose_name_plural = "شطوب مسودّات الأتعاب"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="fee_write_off_amount_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "draft"], name="office_fee_writeoff_draft",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.draft_id}={self.amount}"

    def save(self, *args, **kwargs):
        if self.draft_id:
            self.tenant_id = self.draft.tenant_id
        assert_positive_fee_amount(self.amount)
        super().save(*args, **kwargs)
