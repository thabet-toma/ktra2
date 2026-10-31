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
from django.conf import settings
from django.db import models

from accounting_office import settings_registry
from tenants.models import Tenant, UserCompanyMembership


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
    employees_count = models.PositiveSmallIntegerField(
        default=0, verbose_name="عدد الموظفين",
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


class Contact(models.Model):
    """شخصٌ يحكي معه المكتب — يملكه المكتب، ويُربط بأكثر من زبون."""

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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "جهة اتصال"
        verbose_name_plural = "جهات الاتصال"
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name


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
    """مستلِمُ نوع تذكير لزبون — وغياب الصفّ يعني **الجهة الرئيسية**."""

    REMINDER_DOCUMENTS = "documents"
    REMINDER_DEADLINE = "deadline"
    REMINDER_BALANCE = "balance"
    REMINDER_APPOINTMENT = "appointment"
    REMINDER_TYPE_CHOICES = [
        (REMINDER_DOCUMENTS, "أوراق ناقصة"),
        (REMINDER_DEADLINE, "موعد رسمي قريب"),
        (REMINDER_BALANCE, "اللي عليه"),
        (REMINDER_APPOINTMENT, "تذكير موعد"),
    ]
    REMINDER_TYPES: tuple[str, ...] = tuple(key for key, _label in REMINDER_TYPE_CHOICES)

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
THRESHOLD_KIND_CHOICES: list[tuple[str, str]] = [
    (THRESHOLD_KIND_VAT_MONTHLY_REPORTING, "سقف التقرير الدوري لق.م"),
    (THRESHOLD_KIND_VAT_EXEMPT_DEALER, "سقف עוסק פטור"),
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
