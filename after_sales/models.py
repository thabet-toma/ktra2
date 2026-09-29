"""خدمة ما بعد البيع (THA-24) — بطاقات الكفالة وأوامر الصيانة.

المخطط كامل من الهجرة الأولى وإن لم يُستهلك منطق أمر الصيانة إلا في معلم لاحق:
جدولٌ يُهاجَر مرتين يكلّف أكثر مما يوفّره تأجيله.

قاعدتان تحكمان هذا الملف:

- **حالة الكفالة مشتقّة دائماً** من `end_date` مقابل اليوم — لا عمود حالة. قيمة
  مشتقّة تُخزَّن تتناقض مع مصدرها أول يوم يمرّ دون أن يمسّها أحد. والاستثناء
  المُعلَن الوحيد **واقعةُ الانتهاء** (`ended_on`/`end_reason`، #222): المرجع
  حدثٌ وقع في يومٍ بعينه، والتواريخ لا تستطيع أن تشتقّه — فنخزّن الواقعة
  وتاريخها، وتبقى الحالة محسوبةً منها في `status_on` وحدها.
- **لا فرادة شرطية** («بطاقة حيّة واحدة لكل وحدة»): MySQL لا تدعمها، واختبار
  SQLite يكذب عليها — الحصر في الكود (`after_sales.services`).
"""
from datetime import date

from django.core.validators import MaxValueValidator
from django.db import models

from tenants.models import Tenant
from django.utils import timezone

from .verify import new_verify_token


def add_months(start: date, months: int) -> date:
    """يضيف شهوراً تقويمية مع تثبيت اليوم على آخر الشهر حين يقصر.

    31 يناير + شهر = 28/29 فبراير. لا نستعمل `timedelta(days=30*n)`: كفالة سنة
    ليست 360 يوماً، والفرق يظهر على أول بطاقة تُفحص في نهاية مدّتها.
    """
    months = int(months or 0)
    total = (start.year * 12 + (start.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    import calendar

    return calendar.monthrange(year, month)[1]


class WarrantyCardQuerySet(models.QuerySet):
    """كل فلترة على `end_date` تمرّ من هنا — لا مقارنة حرّة في مكان آخر (#229).

    `active_on` و`expired_on` لا تُعدّان المنتهية بواقعة (`ended_on`) ولا
    الملغاة (`voided_at`، #236)؛ و`voided()` الملغاة غير المنتهية — الانتهاء
    يغلب الإلغاء إن اجتمعا، كما في `WarrantyCard.status_on`.
    """

    def active_on(self, today: date | None = None):
        today = today or timezone.localdate()
        return self.filter(
            ended_on__isnull=True, voided_at__isnull=True, end_date__gte=today,
        )

    def expired_on(self, today: date | None = None):
        today = today or timezone.localdate()
        return self.filter(
            ended_on__isnull=True, voided_at__isnull=True, end_date__lt=today,
        )

    def ended(self):
        return self.filter(ended_on__isnull=False)

    def voided(self):
        return self.filter(ended_on__isnull=True, voided_at__isnull=False)


class WarrantyCard(models.Model):
    """بطاقة كفالة — نسخة الكفالة الفعلية لوحدة واحدة عند الزبون.

    السياسة تعيش على `WarrantyPolicy` (صفٌّ مستقل بلا حقلَين على المنتج، #231)؛
    هذه هي النسخة المصروفة منها: تُنشأ آلياً عند ترحيل فاتورة البيع لكل وحدة متسلسلة استُهلكت
    (`source=auto_sale`)، أو يدوياً لما لا وحدة متسلسلة له (`source=manual`).

    `end_date` **مخزَّن وقابل للتعديل** — التمديد مجاملةً قرارُ تاجر لا حساب،
    وتخزينه يجعله واقعة مؤرَّخة لا نتيجة ضربٍ تتبدّل بتبدّل سياسة المنتج.

    و«الانتهاء» (#222) واقعةٌ مؤرَّخة أخرى لا عمود حالة: `ended_on` مع
    `end_reason` يقولان إن الشهادة لم تعد لهذا الزبون — أُرجع الجهاز، أو أُلغي
    ترحيل فاتورته، أو حُذفت مسودّتها، أو حلّت محلّها بطاقةُ مشترٍ ثانٍ. البطاقة
    **لا تُحذف أبداً** لأن هويّتها مرساةُ أوامر الصيانة ورمزِ التحقّق المطبوع.

    **البطاقة تحمل طبقتين مستقلتين (#232):** كفالة التاجر (`duration_months`/
    `end_date` أعلاه) وكفالة المصنع (`manufacturer_*` أسفله)، ولكلٍّ حالتها
    (`status_on`/`manufacturer_status_on`). طبقة المصنع مجمَّدةٌ عند الإنشاء —
    الجهة والمدة لا تُعدَّلان، والبداية وحدها قابلة للتعديل اليدوي فتُعيد
    احتساب النهاية من المدة المجمَّدة نفسها. مصدرها عند البيع (`method=serial`
    وحده): آخر بطاقة سابقة لهذه الوحدة نفسها (إعادة بيع)، وإلا سياسة البراند —
    `after_sales/services.py` (`_resolve_manufacturer_layer`).
    """

    SOURCE_AUTO_SALE = "auto_sale"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_AUTO_SALE, "تلقائية من فاتورة بيع"),
        (SOURCE_MANUAL, "يدوية"),
    ]

    #: أسباب انتهاء البطاقة. قائمةٌ مغلقة تُعَدّ في التقرير وتُقرأ في الشاشة —
    #: و«إلغاء كفالة التاجر» ليس منها (#218): ذاك يخصّ طبقةً واحدة من الكفالة،
    #: وهذا يُنهي الشهادة كلّها. إن اجتمعا غلب الانتهاء.
    END_RETURNED = "returned"
    END_INVOICE_UNPOSTED = "invoice_unposted"
    END_SALE_CANCELLED = "sale_cancelled"
    END_SUPERSEDED = "superseded"
    #: سحب البطاقة **اليدوية** الصادرة للزبون بدل حذفها (#238) — للبطاقة اليدوية وحدها.
    END_WITHDRAWN = "withdrawn"
    END_REASON_CHOICES = [
        (END_RETURNED, "أُرجع الجهاز"),
        (END_INVOICE_UNPOSTED, "أُلغي ترحيل الفاتورة"),
        (END_SALE_CANCELLED, "أُلغي البيع"),
        (END_SUPERSEDED, "حلّت محلّها بطاقة أحدث"),
        (END_WITHDRAWN, "سُحبت البطاقة"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_ENDED = "ended"
    STATUS_VOIDED = "voided"

    #: أسباب إلغاء كفالة التاجر ورفضها لهذا العطل (#236) — قائمةٌ واحدة للفعلين.
    VOID_PHYSICAL_DAMAGE = "physical_damage"
    VOID_LIQUID = "liquid"
    VOID_OPENED_OUTSIDE = "opened_outside"
    VOID_TAMPERED = "tampered"
    VOID_MISUSE = "misuse"
    VOID_OTHER = "other"
    VOID_REASON_CHOICES = [
        (VOID_PHYSICAL_DAMAGE, "ضرر مادي"),
        (VOID_LIQUID, "تعرّض لسوائل"),
        (VOID_OPENED_OUTSIDE, "فُتح خارج المركز"),
        (VOID_TAMPERED, "عبث بالأختام أو البرمجيات"),
        (VOID_MISUSE, "سوء استخدام"),
        (VOID_OTHER, "أخرى"),
    ]

    objects = WarrantyCardQuerySet.as_manager()

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="warranty_cards",
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_cards",
    )
    # جهازٌ لم نبعه (زبون خارجي) حالة أولى الدرجة لا استثناء — الاسم الحر يكفي.
    device_name = models.CharField(max_length=200, blank=True, default="")
    serial = models.CharField(max_length=100, blank=True, default="")
    product_serial = models.ForeignKey(
        "inventory.ProductSerial", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_cards",
        help_text="الوحدة المُرقَّمة التي تغطّيها البطاقة، إن كانت من بضاعتنا",
    )
    sales_invoice_line = models.ForeignKey(
        "sales.SalesInvoiceLine", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_cards",
        help_text="بند فاتورة البيع الذي وَلَّد البطاقة — يُفرَّغ إن حُذف البند من المسودّة",
    )
    # #222: المرساة الحقيقية. تعديلُ المسودّة يحذف البنود التي تُرسَل بلا `id`
    # (`sales/serializers.py` — `SalesInvoiceSerializer.update`) فيُفرَّغ البند
    # أعلاه بصمت؛ أما الفاتورة فتبقى، فعليها تُطابَق البطاقة عند إعادة الترحيل.
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_cards",
        help_text="فاتورة البيع التي وَلَّدت البطاقة — مرساة إحيائها عند إعادة الترحيل",
    )
    partner = models.ForeignKey(
        "partners.Partner", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_cards",
    )
    # لقطة الاسم والهاتف: الطرف قد يُحذف أو يتغيّر اسمه، والبطاقة وثيقة لحظتها.
    customer_name = models.CharField(max_length=150, blank=True, default="")
    customer_phone = models.CharField(max_length=32, blank=True, default="")

    start_date = models.DateField()
    duration_months = models.PositiveSmallIntegerField(default=0)
    end_date = models.DateField()

    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL,
    )

    # جانب المورد: نتتبّعه عرضاً وتأشيراً — موظف الكاونتر يرى أن القطعة ما زالت
    # بكفالة المورد فلا تتحمّل الشركة كلفةً يتحمّلها غيرها. لا مستند RMA هنا.
    supplier = models.ForeignKey(
        "partners.Partner", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplied_warranty_cards",
    )
    supplier_warranty_end_date = models.DateField(null=True, blank=True)

    # ── طبقة كفالة المصنع (#232) ─────────────────────────────────────────
    # مجمَّدةٌ عند الإنشاء (الجهة والمدة)، والبداية وحدها قابلة للتعديل
    # اليدوي لاحقاً — بعض المصنّعين يحسبون من تاريخ التفعيل لا البيع، وتعديلها
    # يعيد احتساب `manufacturer_end_date` من `manufacturer_duration_months`
    # المجمَّدة نفسها. الفارغ (`manufacturer_warrantor=None`) يعني «لا يوجد»
    # صراحةً، لا نقصاً في البيانات — سياسةٌ بلا جهة مصنع تنتج بطاقةً هكذا عمداً.
    manufacturer_warrantor = models.ForeignKey(
        "ManufacturerWarrantor", on_delete=models.PROTECT, null=True, blank=True,
        related_name="warranty_cards",
    )
    manufacturer_start_date = models.DateField(null=True, blank=True)
    manufacturer_duration_months = models.PositiveSmallIntegerField(default=0)
    manufacturer_end_date = models.DateField(null=True, blank=True)

    # ── بطاقة «كفالة على الفاتورة» (#234) ──────────────────────────────────
    # بلا رقم تسلسلي (`product_serial` فارغ): بطاقةٌ واحدة لكل (فاتورة، منتج)
    # بالكمية، لا لكل وحدة. صفرٌ على بطاقة وحدة مُرقَّمة — لا معنى له هناك.
    # التغطية `quantity − returned_quantity` **محسوبة لا مخزَّنة**
    # (`covered_quantity` أسفله)، والمرتجع الجزئي ينقص منها بحدثٍ جزئي
    # (`WarrantyCardEvent.quantity`) دون أن يُنهي البطاقة إلا حين تبلغ صفراً.
    # `PositiveIntegerField` لا `Small` (#234-review): كميةُ فاتورةٍ واحدة قد
    # تتجاوز 32767 (بضاعة بالجملة)، والحقل عددٌ صحيح دائماً — الترحيل يرفض
    # كسراً لمنتج `method=invoice` بدل أن يقصّه (`create_auto_warranty_cards`).
    quantity = models.PositiveIntegerField(default=0)
    returned_quantity = models.PositiveIntegerField(default=0)

    # ── واقعة الانتهاء (#222) ─────────────────────────────────────────────
    ended_on = models.DateField(
        null=True, blank=True,
        help_text="يوم انتهاء البطاقة كواقعة — لا بانقضاء مدّتها",
    )
    end_reason = models.CharField(
        max_length=20, choices=END_REASON_CHOICES, blank=True, default="",
    )
    end_return_line = models.ForeignKey(
        "sales.SalesInvoiceLine", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ended_warranty_cards",
        help_text="بند مرجع البيع الذي أنهى البطاقة — ومنه يُحييها إلغاءُ ترحيله",
    )

    # ── إلغاء كفالة التاجر (#236) ─────────────────────────────────────────
    # طبقة التاجر وحدها: كفالة المصنع لا تُمسّ. واقعةٌ مؤرَّخة لا عمود حالة —
    # `status_on` تشتقّ منها، والانتهاء (`ended_on`) يغلبها إن اجتمعا.
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="voided_warranty_cards",
    )
    void_reason = models.CharField(
        max_length=20, choices=VOID_REASON_CHOICES, blank=True, default="",
    )
    void_note = models.TextField(blank=True, default="")
    void_service_order = models.ForeignKey(
        "ServiceOrder", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="voided_warranty_cards",
        help_text="أمر الصيانة الذي أُلغيت الكفالة من داخله، إن وُجد",
    )

    # #237: رمز التحقق المطبوع بصيغة QR — 128 بت، يُولَّد عند الإدراج، **لا يُدوَّر أبداً**:
    # الإحياء والترحيل المتكرّر يحدّثان الصفّ نفسه بـ`update_fields` فلا يمسّانه، وأوراقٌ
    # مطبوعة على مكاتب الزبائن تعتمد عليه. ولا يخرج في أي serializer (الرابط وحده يخرج).
    verify_token = models.CharField(
        max_length=22, unique=True, editable=False, default=new_verify_token,
    )
    notes = models.TextField(blank=True, default="")
    # #231: الشروط المجمَّدة لحظة الإنشاء — من `WarrantyPolicy.terms_override`
    # وإلا `AfterSalesSettings.default_terms`. لا تتغيّر بتعديل السياسة لاحقاً؛
    # بطاقةٌ قديمة (قبل هذا المعلم) تبقى فارغة، والطباعة تطبع شروط الشركة
    # الحالية لها (#238 — غير مبنيّة هنا، الحقل يُخزَّن فقط).
    terms_text = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_warranty_cards",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "warranty_cards"
        indexes = [
            models.Index(fields=["tenant", "serial"], name="warranty_tenant_serial_idx"),
            models.Index(fields=["tenant", "end_date"], name="warranty_tenant_end_idx"),
        ]
        ordering = ["-end_date", "-id"]

    def __str__(self):
        return f"{self.serial or self.device_name or '—'} → {self.end_date}"

    # ── الحالة مشتقّة، لا مخزّنة ──────────────────────────────────────────
    def is_active_on(self, today: date | None = None) -> bool:
        """داخل المدّة **وغير منتهية بواقعة ولا ملغاة** — سؤالٌ واحد لا أسئلة."""
        if self.ended_on is not None or self.voided_at is not None:
            return False
        return self.end_date >= (today or timezone.localdate())

    def days_remaining(self, today: date | None = None) -> int:
        return (self.end_date - (today or timezone.localdate())).days

    def status_on(self, today: date | None = None) -> str:
        """`ended` ثم `voided` ثم `active`/`expired` — الواقعة تغلب التاريخ.

        بطاقةٌ أُنهيت بمرجعٍ قد تبقى مدّتها سارية شهوراً؛ الجواب «غير سارية»
        لا «سارية»، وإلا قال الاستقبال «مغطّى» عن جهازٍ في المخزن. و`voided`
        لطبقة التاجر وحدها (#236) — `manufacturer_status_on` لا تقرؤه.
        """
        if self.ended_on is not None:
            return self.STATUS_ENDED
        if self.voided_at is not None:
            return self.STATUS_VOIDED
        return (
            self.STATUS_ACTIVE if self.end_date >= (today or timezone.localdate())
            else self.STATUS_EXPIRED
        )

    def supplier_active_on(self, today: date | None = None) -> bool:
        if self.ended_on is not None:
            return False
        if self.supplier_warranty_end_date is None:
            return False
        return self.supplier_warranty_end_date >= (today or timezone.localdate())

    # ── طبقة المصنع: حالةٌ مستقلة عن طبقة التاجر (#232) ───────────────────
    def manufacturer_status_on(self, today: date | None = None) -> str | None:
        """`None` صراحةً حين لا جهة («لا يوجد») — ليست حالة رابعة، بل غيابُ طبقة.

        وإلا فالواقعة نفسها تغلب: بطاقةٌ أُنهيت (مرجع/إلغاء ترحيل/استبدال) لم
        تعد طبقتاها سارية معاً، ثم `active`/`expired` من `manufacturer_end_date`
        — بمعزلٍ تام عن حالة طبقة التاجر (`status_on`).
        """
        if self.manufacturer_warrantor_id is None:
            return None
        if self.ended_on is not None:
            return self.STATUS_ENDED
        today = today or timezone.localdate()
        return (
            self.STATUS_ACTIVE if self.manufacturer_end_date >= today
            else self.STATUS_EXPIRED
        )

    def manufacturer_days_remaining(self, today: date | None = None) -> int | None:
        if self.manufacturer_end_date is None:
            return None
        return (self.manufacturer_end_date - (today or timezone.localdate())).days

    @property
    def covered_quantity(self) -> int:
        """بطاقة الفاتورة: ما تبقّى مكفولاً — بحدٍّ أدنى صفر، لا يُخزَّن أبداً (#234)."""
        return max(0, self.quantity - self.returned_quantity)


class WarrantyCardEvent(models.Model):
    """سجل إلحاقي واحد لكل ما يحدث للبطاقة — لا تحديث ولا حذف (#229).

    `card` بـ`PROTECT`: بطاقةٌ لها حدثٌ واحد لا تُحذف، فهويّتها التي يتّكئ
    عليها هذا السجل نفسه تبقى مرساة. أنواع الحدث أوسع مما تكتبه هذه التذكرة —
    الإلغاء والإصدار والإحالة والاستبدال تذاكر لاحقة (#218، #217، #226…) تكتب
    فيها؛ هنا الشكل النهائي وحده، والتمديد اليدوي أول من يملأه.

    `reason_code` نصٌّ حرّ بلا `choices` على مستوى النموذج عمداً: التمديد
    يستعمل مفرداتٍ (`courtesy`/`shop_days`/`shop_days_reversed`) والإلغاء
    مفرداتٍ أخرى تماماً (`physical_damage`/`liquid`/…) — قائمةٌ واحدة تخلطهما،
    والتحقّق من المفردة الصحيحة شأن الخدمة التي تكتب هذا النوع من الحدث.
    """

    TYPE_VOID = "void"
    TYPE_UNVOID = "unvoid"
    TYPE_EXTEND = "extend"
    TYPE_ENDED = "ended"
    TYPE_REVIVED = "revived"
    TYPE_ISSUED = "issued"
    TYPE_REFERRED = "referred"
    TYPE_COVERAGE_REFUSED = "coverage_refused"
    TYPE_COVERAGE_RESTORED = "coverage_restored"
    TYPE_REPLACEMENT = "replacement"
    TYPE_CHOICES = [
        (TYPE_VOID, "إلغاء كفالة التاجر"),
        (TYPE_UNVOID, "تراجع عن الإلغاء"),
        (TYPE_EXTEND, "تمديد"),
        (TYPE_ENDED, "انتهاء"),
        (TYPE_REVIVED, "إحياء"),
        (TYPE_ISSUED, "إصدار (طباعة/مشاركة)"),
        (TYPE_REFERRED, "إحالة لمركز الوكيل"),
        (TYPE_COVERAGE_REFUSED, "رفض الكفالة لهذا العطل"),
        (TYPE_COVERAGE_RESTORED, "استعادة الكفالة لهذا العطل"),
        (TYPE_REPLACEMENT, "استبدال الجهاز"),
    ]

    #: مفردات `reason_code` للتمديد وحده — لا تُفرض بـ`choices` (انظر الشرح أعلاه).
    EXTEND_REASON_COURTESY = "courtesy"
    EXTEND_REASON_SHOP_DAYS = "shop_days"
    EXTEND_REASON_SHOP_DAYS_REVERSED = "shop_days_reversed"
    #: التقصير (#236) يُسجَّل بنوع `extend` نفسه ويتميّز بهذا الرمز، فتعرضه الواجهة
    #: «تقصير» لا «تمديد» ولا يحتاج نوعاً جديداً في الترحيل.
    EXTEND_REASON_SHORTEN = "shorten"

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="warranty_card_events",
    )
    card = models.ForeignKey(
        WarrantyCard, on_delete=models.PROTECT, related_name="events",
    )
    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    reason_code = models.CharField(max_length=30, blank=True, default="")
    text = models.TextField(blank=True, default="")
    service_order = models.ForeignKey(
        "ServiceOrder", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_card_events",
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="warranty_card_events",
    )
    # للتمديد بنوعيه (مجاملة/أيام صيانة) — واقعتا قبل/بعد في حدثٍ واحد.
    old_end_date = models.DateField(null=True, blank=True)
    new_end_date = models.DateField(null=True, blank=True)
    # كمية الحدث الجزئي — لمرتجع بطاقة الفاتورة. `PositiveIntegerField` لا
    # `Small` (#234-review): يطابق نوع `WarrantyCard.quantity` الذي يصفه.
    quantity = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "warranty_card_events"
        indexes = [
            models.Index(fields=["card", "created_at"], name="warrantyevent_card_new_idx"),
        ]
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.event_type}#{self.card_id}"


class ServiceOrder(models.Model):
    """أمر صيانة — الملف الذي يوثّق كل شيء من الشكوى حتى الحل.

    الحالة والنتيجة حقلان منفصلان: خلطهما يُنتج FSM بحالات نهاية متكاثرة
    («سُلّم غير مُصلَح»، «سُلّم مرفوض التقدير»…). المنطق كله في معلم لاحق —
    هنا المخطط وحده كي لا يُهاجَر الجدول مرتين.
    """

    STATUS_RECEIVED = "received"
    STATUS_IN_DIAGNOSIS = "in_diagnosis"
    STATUS_AWAITING_APPROVAL = "awaiting_approval"
    STATUS_IN_REPAIR = "in_repair"
    STATUS_READY = "ready"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_RECEIVED, "مُستلَم"),
        (STATUS_IN_DIAGNOSIS, "قيد التشخيص"),
        (STATUS_AWAITING_APPROVAL, "بانتظار الموافقة"),
        (STATUS_IN_REPAIR, "قيد الإصلاح"),
        (STATUS_READY, "جاهز للتسليم"),
        (STATUS_DELIVERED, "تم التسليم"),
        (STATUS_CANCELLED, "ملغى"),
    ]

    OUTCOME_REPAIRED = "repaired"
    OUTCOME_UNREPAIRED = "unrepaired"
    OUTCOME_REJECTED = "rejected_estimate"
    OUTCOME_NO_FAULT = "no_fault"
    OUTCOME_CHOICES = [
        (OUTCOME_REPAIRED, "تم الإصلاح"),
        (OUTCOME_UNREPAIRED, "تعذّر الإصلاح"),
        (OUTCOME_REJECTED, "رفض الزبون التقدير"),
        (OUTCOME_NO_FAULT, "لا عطل"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="service_orders",
    )
    order_number = models.CharField(max_length=30, blank=True, default="")
    order_date = models.DateField()

    partner = models.ForeignKey(
        "partners.Partner", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_orders",
    )
    customer_name = models.CharField(max_length=150, blank=True, default="")
    customer_phone = models.CharField(max_length=32, blank=True, default="")

    product = models.ForeignKey(
        "inventory.Product", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_orders",
    )
    serial = models.CharField(max_length=100, blank=True, default="")
    device_description = models.CharField(max_length=300, blank=True, default="")
    received_condition = models.TextField(blank=True, default="")
    accessories = models.CharField(max_length=300, blank=True, default="")

    complaint = models.TextField(blank=True, default="")
    diagnosis = models.TextField(blank=True, default="")
    resolution = models.TextField(blank=True, default="")

    technician = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_orders_assigned",
    )

    warranty_card = models.ForeignKey(
        WarrantyCard, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_orders",
    )
    warranty_covered = models.BooleanField(default=False)
    supplier_claim = models.BooleanField(default=False)
    supplier_claim_note = models.CharField(max_length=300, blank=True, default="")

    estimated_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_orders_approved",
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_RECEIVED,
    )
    outcome = models.CharField(
        max_length=20, choices=OUTCOME_CHOICES, blank=True, default="",
    )
    # لحظة ترحيل صرف القطع المغطاة — بوابة التسليم تقرأها، والتراجع يُفرِّغها.
    covered_posted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_orders",
    )
    billing_waived_reason = models.CharField(max_length=300, blank=True, default="")

    photos = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_service_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_orders"
        indexes = [
            models.Index(fields=["tenant", "status"], name="svcorder_tenant_status_idx"),
            models.Index(fields=["tenant", "serial"], name="svcorder_tenant_serial_idx"),
            models.Index(fields=["tenant", "-created_at"], name="svcorder_tenant_new_idx"),
            # فهرسٌ لا قيد فرادة: الفرادة الشرطية (تستثني الرقم الفارغ) تُهمَل
            # صامتةً على MySQL بينما تُنفَّذ على SQLite — قيدٌ يكذب عليه الاختبار
            # أسوأ من غيابه. تفرّد الرقم مضمون من مصدره (`next_document_number`
            # يسلسل بـ`select_for_update` على دفتر الشركة).
            models.Index(fields=["tenant", "order_number"], name="svcorder_tenant_num_idx"),
        ]
        ordering = ["-order_date", "-id"]

    def __str__(self):
        return f"أمر صيانة {self.order_number or self.pk}"


class ServiceOrderPart(models.Model):
    """قطعة غيار على أمر صيانة — تتجسّد في مستند **واحد بالضبط**.

    `billing` يحسم المسار: `billable` يمرّ في فاتورة بيع (مسار SALE المجرَّب)،
    و`covered` يُصرَف مصروفَ كفالة بلا إيراد. `materialized_at` هو القفل الذي
    يمنع البند من الظهور في المسارين معاً — الخصم المزدوج يُمنع بالبناء.
    """

    BILLING_BILLABLE = "billable"
    BILLING_COVERED = "covered"
    BILLING_CHOICES = [
        (BILLING_BILLABLE, "مفوترة على الزبون"),
        (BILLING_COVERED, "مغطاة بالكفالة"),
    ]

    order = models.ForeignKey(
        ServiceOrder, on_delete=models.CASCADE, related_name="parts",
    )
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.PROTECT, related_name="service_order_parts",
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=1)
    billing = models.CharField(
        max_length=20, choices=BILLING_CHOICES, default=BILLING_BILLABLE,
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    # الأرقام المختارة لقطعةٍ مغطاة مرقّمة — على نمط `sales.SalesInvoiceLine.serials`
    # (نيّةٌ تُترجَم إلى صفوف `inventory.ProductSerial` عند الترحيل، #223).
    serials = models.JSONField(default=list, blank=True)
    # كلفة FIFO الفعلية لحركة `SERVICE_ISSUE` — تُملأ عند `post_covered_parts`
    # وتُفرَّغ عند التراجع؛ تحتاجها تذكرة استبدال الجهاز (#245).
    issued_cost = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
    )
    sales_invoice_line = models.ForeignKey(
        "sales.SalesInvoiceLine", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_order_parts",
    )
    materialized_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_order_parts"
        ordering = ["id"]

    def __str__(self):
        return f"{self.product_id} × {self.quantity} ({self.billing})"


class ServiceOrderEvent(models.Model):
    """سجل إلحاقي لأمر الصيانة — «من الشكوى حتى الحل» مؤرَّخاً من الخادم.

    النص يبقى نصاً (لا مفاتيح مُرمَّزة وحدها) كي يعمل البحث عليه، وتاريخ الحدث
    من الخادم لا من العميل: ساعة الجهاز ليست مصدر حقيقة.
    """

    TYPE_STATUS = "status"
    TYPE_NOTE = "note"
    TYPE_PART = "part"
    TYPE_POSTING = "posting"
    TYPE_INVOICE = "invoice"
    TYPE_APPROVAL = "approval"
    TYPE_WARRANTY = "warranty"
    TYPE_CHOICES = [
        (TYPE_STATUS, "تغيير حالة"),
        (TYPE_NOTE, "ملاحظة"),
        (TYPE_PART, "قطع غيار"),
        (TYPE_POSTING, "ترحيل"),
        (TYPE_INVOICE, "فوترة"),
        (TYPE_APPROVAL, "موافقة"),
        (TYPE_WARRANTY, "كفالة"),
    ]

    order = models.ForeignKey(
        ServiceOrder, on_delete=models.CASCADE, related_name="events",
    )
    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_NOTE)
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    text = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_order_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_order_events"
        indexes = [
            models.Index(fields=["order", "created_at"], name="svcevent_order_new_idx"),
        ]
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.event_type}#{self.order_id}"


class ManufacturerWarrantor(models.Model):
    """جهة كفالة المصنع — الاسم فريد للشركة (#230).

    كل من يشير إليها لاحقاً (سياسة الكفالة #231، بند الشراء #235، طبقة المصنع
    على البطاقة #232) يفعل ذلك بـ`PROTECT` — لا حذف لجهة مرتبطة، أرشفة
    (`is_active=False`) بدلاً منه. العنوان والهاتف **يُقرآن حيّاً** في الطباعة
    وورقة الإحالة لاحقاً: ما يُجمَّد على البطاقة هو **مَن** يكفل لا **مكانه** —
    فجهةٌ تنقل مركزها بعد البيع تطبع عنوانها الحالي على ورقة الإحالة.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="manufacturer_warrantors",
    )
    name = models.CharField(max_length=150)
    service_center_address = models.CharField(max_length=300, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "manufacturer_warrantors"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="manufacturer_warrantor_tenant_name_uniq",
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class WarrantyPolicy(models.Model):
    """سياسة كفالة براند واحد — ما يقرأه ترحيل البيع ليقرّر مدد بطاقته (#231).

    صفٌّ واحدٌ لكل براند (`product` علاقةٌ فريدة — لا حالة، بل وعدٌ). المنتج
    بلا صفّ هنا لا كفالة له أصلاً: `create_auto_warranty_cards` لا تخترع
    مدّةً من مكانٍ آخر. تعديل السياسة لا يمسّ بطاقةً صُرفت — شروطها ومددها
    مجمَّدةٌ على البطاقة نفسها لحظة إنشائها.

    التحقّق (السيريالايزر هو من يفرضه، على نمط بقية الوحدة):
    - طبقة واحدة على الأقل (تاجر/مصنع/مورّد) أكبر من صفر.
    - `manufacturer_months` أكبر من صفر إذا وُجدت الجهة، وصفرٌ وجوباً إن غابت.
    - `method=serial` مرفوضةٌ لمنتج خدمة (`product.is_service`) — `invoice`
      مسموحةٌ له.
    """

    METHOD_SERIAL = "serial"
    METHOD_INVOICE = "invoice"
    METHOD_CHOICES = [
        (METHOD_SERIAL, "برقم تسلسلي"),
        (METHOD_INVOICE, "على الفاتورة"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="warranty_policies",
    )
    # علاقةٌ فريدة (لا FK متكرّر): صفٌّ واحدٌ لكل براند، على نمط
    # `inventory.ProductDemandForecast.product` — الحذف يتبع المنتج (CASCADE).
    product = models.OneToOneField(
        "inventory.Product", on_delete=models.CASCADE, related_name="warranty_policy",
    )
    method = models.CharField(
        max_length=10, choices=METHOD_CHOICES, default=METHOD_SERIAL,
    )
    dealer_months = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(600)],
        help_text="مدة كفالة التاجر بالأشهر",
    )
    # الفارغ = «لا يوجد» — جهة كفالة المصنع (#230)، PROTECT: لا حذف لجهةٍ
    # عليها سياسة، أرشفة بدلاً منه.
    manufacturer_warrantor = models.ForeignKey(
        ManufacturerWarrantor, on_delete=models.PROTECT, null=True, blank=True,
        related_name="warranty_policies",
    )
    manufacturer_months = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(600)],
        help_text="مدة كفالة المصنع بالأشهر — أكبر من صفر إن وُجدت الجهة، وإلا صفر",
    )
    supplier_months = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(600)],
        help_text="مدة كفالة المورّد (داخلية) بالأشهر",
    )
    terms_override = models.TextField(
        blank=True, default="",
        help_text="شروطٌ خاصة بهذا البراند — تحلّ محلّ شروط الشركة على بطاقاته",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "warranty_policies"
        ordering = ["product_id"]

    def __str__(self):
        return f"سياسة كفالة #{self.product_id}"


class AfterSalesSettings(models.Model):
    """إعدادات الوحدة لكل شركة — مثبِّت الحسابات والمنتجات الافتراضية.

    الحساب والمنتج يُنشآن من الكود ويُثبَّتان هنا (نمط حسابات الشيكات) بدل ردّ
    استفسارٍ على المستخدم عند أول ترحيل: من لا يعرف رقم الحساب لن يعرفه لأننا
    سألناه.
    """

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="after_sales_settings",
    )
    warranty_expense_account = models.ForeignKey(
        "accounting.Account", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="after_sales_warranty_expense_settings",
        help_text="حساب «مصاريف صيانة الكفالة» — مدين صرف القطع المغطاة",
    )
    default_labour_product = models.ForeignKey(
        "inventory.Product", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="after_sales_labour_settings",
        help_text="منتج خدمة «أجرة صيانة» الافتراضي في الفاتورة المولَّدة",
    )
    # ── شروط الشركة وإعدادات الصيانة (#230) ─────────────────────────────
    default_terms = models.TextField(
        blank=True, default="",
        help_text="شروط كفالة الشركة — تُنسخ إلى `terms_text` على كل بطاقة عند إنشائها",
    )
    extend_for_shop_days = models.BooleanField(
        default=True,
        help_text="تمديد كفالة التاجر تلقائياً بعدد أيام بقاء الجهاز المغطّى عندنا",
    )
    repair_warranty_days = models.PositiveSmallIntegerField(
        default=90,
        help_text="مدة كفالة الإصلاح بالأيام — صفرٌ يطفئها، وإلا فمن 1 إلى 730",
    )
    repair_terms = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "after_sales_settings"

    def __str__(self):
        return f"إعدادات ما بعد البيع — {self.tenant_id}"


class PurchaseLineWarranty(models.Model):
    """كفالة المصنع كما وُعدت عند الشراء — صفٌّ اختياريٌّ لكل سطر فاتورة شراء (#235).

    غياب الصفّ = «خذ من السياسة»؛ وجودُه بجهةٍ فارغة = «لا يوجد» صريحةً (يغلب
    السياسةَ التي لها جهة). تقرؤه `_resolve_manufacturer_layer` عند البيع في
    الخطوة الثانية (بعد بطاقةٍ سابقةٍ للوحدة، قبل السياسة). لا يُصنع إلا من شاشة
    فاتورة الشراء (عبر امتداد السطر في `core.hooks`)؛ فبنودُ التخليص والأمر
    والنسخة والمرتجع لا صفَّ لها. تصحيحه بعد الترحيل لا يمسّ بطاقةً صدرت.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="purchase_line_warranties",
    )
    purchase_item = models.OneToOneField(
        "logistics.PurchaseInvoiceItem", on_delete=models.CASCADE,
        related_name="line_warranty",
    )
    manufacturer_warrantor = models.ForeignKey(
        ManufacturerWarrantor, on_delete=models.PROTECT, null=True, blank=True,
        related_name="purchase_line_warranties",
    )
    manufacturer_months = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(600)],
        help_text="مدة كفالة المصنع بالأشهر — أكبر من صفر إن وُجدت الجهة، وإلا صفر",
    )
    # الفارغ = خذ مدة كفالة المورّد من السياسة.
    supplier_months = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(600)],
        help_text="مدة كفالة المورّد بالأشهر لهذا السطر — الفارغ يأخذ من السياسة",
    )
    updated_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="updated_purchase_line_warranties",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchase_line_warranties"

    def __str__(self):
        return f"كفالة سطر شراء #{self.purchase_item_id}"
