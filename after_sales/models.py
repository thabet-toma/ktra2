"""خدمة ما بعد البيع (THA-24) — بطاقات الكفالة وأوامر الصيانة.

المخطط كامل من الهجرة الأولى وإن لم يُستهلك منطق أمر الصيانة إلا في معلم لاحق:
جدولٌ يُهاجَر مرتين يكلّف أكثر مما يوفّره تأجيله.

قاعدتان تحكمان هذا الملف:

- **حالة الكفالة مشتقّة دائماً** من `end_date` مقابل اليوم — لا عمود حالة. قيمة
  مشتقّة تُخزَّن تتناقض مع مصدرها أول يوم يمرّ دون أن يمسّها أحد.
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


class WarrantyCard(models.Model):
    """بطاقة كفالة — نسخة الكفالة الفعلية لوحدة واحدة عند الزبون.

    السياسة تعيش على الصنف (`Product.warranty_months`)؛ هذه هي النسخة المصروفة
    منها: تُنشأ آلياً عند ترحيل فاتورة البيع لكل وحدة متسلسلة استُهلكت
    (`source=auto_sale`)، أو يدوياً لما لا وحدة متسلسلة له (`source=manual`).

    `end_date` **مخزَّن وقابل للتعديل** — التمديد مجاملةً قرارُ تاجر لا حساب،
    وتخزينه يجعله واقعة مؤرَّخة لا نتيجة ضربٍ تتبدّل بتبدّل سياسة الصنف.
    """

    SOURCE_AUTO_SALE = "auto_sale"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_AUTO_SALE, "تلقائية من فاتورة بيع"),
        (SOURCE_MANUAL, "يدوية"),
    ]

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
        help_text="بند فاتورة البيع الذي وَلَّد البطاقة — مرساة حذفها عند إلغاء الترحيل",
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
        return self.end_date >= (today or timezone.localdate())

    def days_remaining(self, today: date | None = None) -> int:
        return (self.end_date - (today or timezone.localdate())).days

    def status_on(self, today: date | None = None) -> str:
        return "active" if self.is_active_on(today) else "expired"

    def supplier_active_on(self, today: date | None = None) -> bool:
        if self.supplier_warranty_end_date is None:
            return False
        return self.supplier_warranty_end_date >= (today or timezone.localdate())


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


class AfterSalesSettings(models.Model):
    """إعدادات الوحدة لكل شركة — مثبِّت الحسابات والأصناف الافتراضية.

    الحساب والصنف يُنشآن من الكود ويُثبَّتان هنا (نمط حسابات الشيكات) بدل ردّ
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
        help_text="صنف خدمة «أجرة صيانة» الافتراضي في الفاتورة المولَّدة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "after_sales_settings"

    def __str__(self):
        return f"إعدادات ما بعد البيع — {self.tenant_id}"
