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
from django.db import models

from tenants.models import Tenant

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
