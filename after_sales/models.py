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

from django.db import models

from tenants.models import Tenant
from django.utils import timezone


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

    الثلاثة لا تستثني إلا المنتهية بواقعة (`ended_on`): بطاقةٌ ملغاة تبقى
    خارج نطاق هذا الملف — حقولها (`voided_at`…) لم تُضَف بعد (#236)، وتذكرة
    الإلغاء هي من تُضيف `voided()` حين تُبنى الحقول فعلاً.
    """

    def active_on(self, today: date | None = None):
        today = today or timezone.localdate()
        return self.filter(ended_on__isnull=True, end_date__gte=today)

    def expired_on(self, today: date | None = None):
        today = today or timezone.localdate()
        return self.filter(ended_on__isnull=True, end_date__lt=today)

    def ended(self):
        return self.filter(ended_on__isnull=False)


class WarrantyCard(models.Model):
    """بطاقة كفالة — نسخة الكفالة الفعلية لوحدة واحدة عند الزبون.

    السياسة تعيش على المنتج (`Product.warranty_months`)؛ هذه هي النسخة المصروفة
    منها: تُنشأ آلياً عند ترحيل فاتورة البيع لكل وحدة متسلسلة استُهلكت
    (`source=auto_sale`)، أو يدوياً لما لا وحدة متسلسلة له (`source=manual`).

    `end_date` **مخزَّن وقابل للتعديل** — التمديد مجاملةً قرارُ تاجر لا حساب،
    وتخزينه يجعله واقعة مؤرَّخة لا نتيجة ضربٍ تتبدّل بتبدّل سياسة المنتج.

    و«الانتهاء» (#222) واقعةٌ مؤرَّخة أخرى لا عمود حالة: `ended_on` مع
    `end_reason` يقولان إن الشهادة لم تعد لهذا الزبون — أُرجع الجهاز، أو أُلغي
    ترحيل فاتورته، أو حُذفت مسودّتها، أو حلّت محلّها بطاقةُ مشترٍ ثانٍ. البطاقة
    **لا تُحذف أبداً** لأن هويّتها مرساةُ أوامر الصيانة ورمزِ التحقّق المطبوع.
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
    END_REASON_CHOICES = [
        (END_RETURNED, "أُرجع الجهاز"),
        (END_INVOICE_UNPOSTED, "أُلغي ترحيل الفاتورة"),
        (END_SALE_CANCELLED, "أُلغي البيع"),
        (END_SUPERSEDED, "حلّت محلّها بطاقة أحدث"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_ENDED = "ended"

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

    notes = models.TextField(blank=True, default="")
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
        """داخل المدّة **وغير منتهية بواقعة** — سؤالٌ واحد لا سؤالان."""
        if self.ended_on is not None:
            return False
        return self.end_date >= (today or timezone.localdate())

    def days_remaining(self, today: date | None = None) -> int:
        return (self.end_date - (today or timezone.localdate())).days

    def status_on(self, today: date | None = None) -> str:
        """`ended` أولاً ثم `active`/`expired` — الواقعة تغلب التاريخ.

        بطاقةٌ أُنهيت بمرجعٍ قد تبقى مدّتها سارية شهوراً؛ الجواب «غير سارية»
        لا «سارية»، وإلا قال الاستقبال «مغطّى» عن جهازٍ في المخزن.
        """
        if self.ended_on is not None:
            return self.STATUS_ENDED
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
    # كمية الحدث الجزئي — لمرتجع بطاقة الفاتورة (`quantity`/`returned_quantity`
    # على البطاقة نفسها لم يُضافا بعد؛ هذا العمود ينتظرهما بلا استعمال اليوم).
    quantity = models.PositiveSmallIntegerField(null=True, blank=True)
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
    TYPE_CHOICES = [
        (TYPE_STATUS, "تغيير حالة"),
        (TYPE_NOTE, "ملاحظة"),
        (TYPE_PART, "قطع غيار"),
        (TYPE_POSTING, "ترحيل"),
        (TYPE_INVOICE, "فوترة"),
        (TYPE_APPROVAL, "موافقة"),
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
