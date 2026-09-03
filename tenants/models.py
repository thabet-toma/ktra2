import re

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# ── ST-1: معرّف المتجر العام (`Tenant.store_slug`) ─────────────────────────
#: الشكل المسموح — حروف لاتينية صغيرة وأرقام وشرطات، 3..40 محرفاً. الرابط
#: يُرسَل على واتساب ويظهر في نتائج البحث، فالمقروئية أهم من العتامة.
STORE_SLUG_RE = re.compile(r"^[a-z0-9-]{3,40}$")

#: كلمات محجوزة: لا يصير معرّف متجرٍ ما قد يلتبس بمسار من مسارات المنصة نفسها
#: (`/api/…`, `/store/…`) أو بصفحةٍ عامة قائمة. الحجز تطبيقي لا يعتمد على ترتيب
#: مطابقة المسارات — فإعادة ترتيب `core/urls.py` لاحقاً لا تفتح ثغرة.
RESERVED_STORE_SLUGS = frozenset({
    "api", "admin", "store", "app", "www", "static", "media", "assets",
    "login", "logout", "signup", "register", "settings", "dashboard",
    "about", "about-us", "gallery", "health", "docs", "support",
})


def validate_store_slug(value):
    """يتحقق من شكل معرّف المتجر ومن أنه ليس كلمة محجوزة.

    يُستعمل في موضعين: مُحقِّقاً على الحقل (فيحرس `full_clean` وdjango-admin)
    وفي نقطة الكتابة في `tenants/views.py` (`TenantViewSet.set_store_slug`) —
    قاعدةٌ واحدة في موضع واحد، لا نسختان تنزاحان.
    """
    text = (value or "").strip()
    if not STORE_SLUG_RE.match(text):
        raise ValidationError(
            "معرّف المتجر يقبل الحروف الإنجليزية الصغيرة والأرقام والشرطة فقط، "
            "وطوله بين 3 و40 محرفاً."
        )
    if text in RESERVED_STORE_SLUGS:
        raise ValidationError(f"«{text}» معرّف محجوز — اختر معرّفاً آخر.")


class Currency(models.Model):
    CurrencyID = models.AutoField(primary_key=True)
    Code = models.CharField(max_length=3)
    Name = models.CharField(max_length=50, null=True, blank=True)
    Symbol = models.CharField(max_length=5, null=True, blank=True)
    IsBaseCurrency = models.BooleanField(default=False)

    class Meta:
        db_table = 'currencies'
        managed = True

    def __str__(self):
        return f"{self.Code} - {self.Name}"

class Tenant(models.Model):
    SUBSCRIPTION_PLANS = [
        ('Trial', 'Trial'),
        ('Basic', 'Basic'),
        ('Pro', 'Pro'),
        ('Enterprise', 'Enterprise'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Suspended', 'Suspended'),
        ('Trial', 'Trial'),
    ]

    TenantID = models.AutoField(primary_key=True)
    CompanyName = models.CharField(max_length=150)
    SubscriptionPlan = models.CharField(max_length=50, choices=SUBSCRIPTION_PLANS)
    Status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Trial')
    # T-TRIAL: تاريخ انتهاء الاشتراك — **NULL = بلا انتهاء** (الخطط الدائمة)، فلا
    # حقل `is_expired` منفصل يمكن أن يناقض التاريخ. التاريخ **شامل**: آخر يوم
    # عملٍ هو اليوم المكتوب هنا، والقراءة-فقط تبدأ في اليوم التالي له.
    # حقلٌ على الشركة لا على الخطة: نفس الآلية تخدم تجربةً بأربعة عشر يوماً
    # واشتراكاً سنوياً مدفوعاً، فالانتهاء واحدٌ والخطة تحدّد الحدود لا العمر.
    subscription_ends_at = models.DateField(
        null=True, blank=True, db_column='SubscriptionEndsAt',
        help_text='آخر يوم يُسمح فيه بالكتابة — فارغ يعني اشتراكاً بلا تاريخ انتهاء',
    )
    CreatedAt = models.DateTimeField(auto_now_add=True)
    DomainName = models.CharField(max_length=100, unique=True, null=True, blank=True)
    # وحدة الاستيراد (الصفقات/الشحن/التخليص/الفاتورة الدولية) — يضبطها السوبر أدمن
    # فقط لكل شركة. الشركة غير المفعّلة لا يرى أعضاؤها قائمة الاستيراد ولا قسم
    # «تكاليف الاستيراد» في شجرة الحسابات.
    import_enabled = models.BooleanField(default=False, db_column='ImportEnabled')
    # شركة مشتركة للتجربة؛ تعيينها من لوحة السوبر أدمن يمنح الجميع عضوية staff.
    is_example = models.BooleanField(default=False, db_column='IsExample')
    # ST-1: معرّف المتجر العام — هو نفسه مفتاح التفعيل. **NULL = المتجر مقفل**،
    # فلا حقل `store_enabled` منفصل يمكن أن يتناقض معه، ولا backfill للشركات
    # القائمة: المتجر opt-in يختار المدير معرّفه عند أول فتح لشاشة «متجري».
    # ملاحظة MySQL: قيد unique لا يمنع تكرار NULL — نفس ما وثّقناه في TenantBook،
    # وهو المطلوب هنا بالضبط (كل الشركات مقفلة المتجر تتعايش).
    store_slug = models.CharField(
        max_length=40, unique=True, null=True, blank=True, db_column='StoreSlug',
        validators=[validate_store_slug],
        help_text='معرّف المتجر العام في الرابط /store/<slug> — فارغ يعني أن المتجر مقفل',
    )
    # ISSUE #50: قالب الشركة — يحدّد بذرة دليل الحسابات ودفاتر المستندات
    # المزروعة عند الإنشاء (`tenants/company_templates.py`). الافتراضي
    # `general` يعني بلا قناع وبلا تغيير سلوك (قرار 16): الشركات القائمة
    # بعد الهجرة تُصنَّف `general` ولا تتغيّر أي شجرة حسابات عندها.
    template = models.CharField(
        max_length=32, default='general', db_column='Template',
        help_text='مفتاح قالب الشركة — يحدّد بذرة الحسابات والدفاتر عند الإنشاء',
    )
    # ISSUE #52: الدفتر المُدار — علمٌ من جنس is_example/import_enabled/store_slug:
    # القيمة نفسها هي العلم، فلا حقل "مُدار؟" منفصل يمكن أن يتناقض معها. مكتب
    # محاسبة (Tenant آخر) يملك هذا الدفتر ويديره — **لا يُعَدّ في حصّة خطة أحد
    # كشركة** (my_companies يستثنيه)، ولا يظهر في مبدّل الشركات العادي، والحذف
    # ممنوعٌ أصلاً على كل الشركات (TenantViewSet.destroy). PROTECT: لا يُحذف
    # مكتبٌ يملك دفاتر مُدارة سهواً.
    managed_by = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='managed_books', db_column='ManagedByTenantID',
        help_text='مكتب المحاسبة المالك لهذا الدفتر المُدار — فارغ يعني شركة عادية',
    )

    class Meta:
        db_table = 'tenants'
        managed = True

    def __str__(self):
        return self.CompanyName


# ── N0-T1: TenantSettings (ثوابت المجموعة) ──────────────────────────────

class TenantSettings(models.Model):
    """ثوابت المجموعة — صفحة F11 في الأصيل."""
    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name='settings',
        db_column='TenantID',
    )

    # بيانات الشركة
    company_name_primary = models.CharField(max_length=200, null=True, blank=True, db_column='CompanyNamePrimary')
    company_name_sub = models.CharField(max_length=200, null=True, blank=True, db_column='CompanyNameSub')
    address = models.TextField(null=True, blank=True, db_column='Address')
    po_box = models.CharField(max_length=50, null=True, blank=True, db_column='POBox')
    phone = models.CharField(max_length=50, null=True, blank=True, db_column='Phone')
    fax = models.CharField(max_length=50, null=True, blank=True, db_column='Fax')
    email = models.EmailField(null=True, blank=True, db_column='Email')

    logo_url = models.CharField(max_length=500, null=True, blank=True, db_column='LogoUrl')

    # أرقام رسمية
    licensed_dealer_no = models.CharField(max_length=50, null=True, blank=True, db_column='LicensedDealerNo')
    income_tax_file_no = models.CharField(max_length=50, null=True, blank=True, db_column='IncomeTaxFileNo')

    # ضرائب وافتراضيات
    default_vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16.00, db_column='DefaultVatRate')
    default_source_discount_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, db_column='DefaultSourceDiscountRate')

    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True,
        db_column='CurrencyID', related_name='tenant_settings',
    )

    # فترة مالية
    fiscal_period_label = models.CharField(max_length=100, null=True, blank=True, db_column='FiscalPeriodLabel')
    fiscal_period_start = models.DateField(null=True, blank=True, db_column='FiscalPeriodStart')
    fiscal_period_end = models.DateField(null=True, blank=True, db_column='FiscalPeriodEnd')

    # يوم بداية الدورة الشهرية المتكررة لملخص لوحة الأعمال.
    dashboard_month_start_day = models.PositiveSmallIntegerField(
        default=1, db_column='DashboardMonthStartDay',
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="يوم بداية شهر ملخص الأعمال (1..31)",
    )

    # حسابات افتراضية
    default_freight_credit_account = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='DefaultFreightCreditAccountID',
        related_name='tenant_settings_freight',
    )

    # خيارات
    mixture_auto_fill_enabled = models.BooleanField(default=False, db_column='MixtureAutoFillEnabled')
    barcode_action = models.CharField(
        max_length=20, default='index', db_column='BarcodeAction',
        help_text="'index' = يفتح فهرس المنتجات, 'cashier' = يفتح فاتورة كاشير",
    )

    # تفضيل المظهر (حجم/نوع الخط) — يُحفَظ خادمياً لكل شركة فيثبت عبر الأجهزة
    # ولا يرجع للافتراضي عند إعادة فتح الموقع، ويُعزَل لكل شركة لا للمنصة كلها.
    font_scale = models.CharField(
        max_length=10, default='normal', db_column='FontScale',
        help_text="small | normal | large | xlarge",
    )
    font_family = models.CharField(
        max_length=20, default='default', db_column='FontFamily',
        help_text="default | tahoma | segoe | arial",
    )

    # مهلة الخمول قبل إنهاء الجلسة (بالدقائق) — يُحفَظ خادمياً لكل شركة فيثبت
    # عبر الأجهزة، ويُدخِله المستخدم من صفحة الإعدادات. مقيّد بنطاق معقول
    # (5 دقائق .. 24 ساعة) حماية من إدخال خاطئ يُبقي الجلسة أبداً أو يقطعها فوراً.
    idle_timeout_minutes = models.PositiveIntegerField(
        default=180, db_column='IdleTimeoutMinutes',
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text="مهلة إنهاء الجلسة عند الخمول بالدقائق (5..1440)",
    )

    # سند المصروف/الإيراد: أيُلزَم كاتبُه باختيار حسابٍ من الشجرة، أم يكفيه
    # أن يكتب اسم المصروف نصّاً فيُنشأ له حسابٌ تحت أبيه المعياري؟
    # الافتراضي `free` — هو السلوك القائم منذ issue #56، وتغييرُه افتراضاً كان
    # يكسر كل شركةٍ تكتب مصاريفها نصّاً اليوم. من يريد شجرةً مضبوطة لا تنبت
    # فيها حسابات جديدة مع كل سند يختار `linked`.
    VOUCHER_ACCOUNT_ENTRY_FREE = 'free'
    VOUCHER_ACCOUNT_ENTRY_LINKED = 'linked'
    VOUCHER_ACCOUNT_ENTRY_CHOICES = [
        (VOUCHER_ACCOUNT_ENTRY_FREE, 'نصّ حرّ — يُنشأ الحساب إن لم يوجد'),
        (VOUCHER_ACCOUNT_ENTRY_LINKED, 'حساب من الشجرة إلزاماً'),
    ]
    voucher_account_entry_mode = models.CharField(
        max_length=10, default=VOUCHER_ACCOUNT_ENTRY_FREE,
        choices=VOUCHER_ACCOUNT_ENTRY_CHOICES,
        db_column='VoucherAccountEntryMode',
        help_text='سندا المصروف والإيراد: نصّ حرّ يُنشئ حساباً، أم ربطٌ بحسابٍ قائم',
    )

    # T-HR: هل يُعلَن غياب الموظف في يومٍ لا وردية مُسنَدة له فيه؟
    # الافتراضي **لا**: شركةٌ فعّلت الحضور ولم تبنِ جداولها بعد كانت ستستيقظ
    # على موظفيها كلّهم «غائبين» بأثرٍ مالي في مسير الرواتب.
    hr_absence_requires_shift = models.BooleanField(
        default=True, db_column='HrAbsenceRequiresShift',
        help_text='لا يُحتسب غياب إلا في يومٍ للموظف فيه وردية مُسنَدة',
    )

    class Meta:
        db_table = 'tenant_settings'
        managed = True

    def __str__(self):
        return f"Settings — {self.tenant}"


# ── task11 M4: Branch (الفرع) ──────────────────────────────────────────

class Branch(models.Model):
    """فرع تابع لشركة أم.

    التعريف القاطع: الفرع يشارك الشركةَ الأمَّ شجرةَ الحسابات والمنتجات
    والشركاء، لكن فواتيره ومخزونه وتقاريره المالية مستقلة (بُعد branch
    على SalesInvoice / StockMovement / JournalHeader).
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='branches', db_column='TenantID')
    name = models.CharField(max_length=150, db_column='Name')
    code = models.CharField(
        max_length=20, db_column='Code',
        help_text='رمز قصير يدخل في بادئة ترقيم المستندات، مثل MAIN أو NAB')
    is_main = models.BooleanField(default=False, db_column='IsMain')
    is_active = models.BooleanField(default=True, db_column='IsActive')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'branches'
        managed = True
        unique_together = [['tenant', 'code']]

    def __str__(self):
        return f"{self.tenant.CompanyName} / {self.name}"


# ── task49: WhatsAppContact (ربط رقم واتساب بشركة للمساعد الذكي) ───────

class WhatsAppContact(models.Model):
    """رقم واتساب مصرَّح له بمحادثة المساعد الذكي، مربوط بشركة واحدة.

    هذا الربط هو حارس العزل الوحيد على مسار واتساب: أي رقم غير مُدرَج هنا
    (أو مُدرَج لكنه غير نشط) لا يحصل على أي رد من المساعد مهما كان محتوى
    رسالته — الأمان هنا خادمي بالكامل، لا يعتمد على النموذج أو على واتساب.
    """

    phone_number = models.CharField(
        max_length=20, unique=True, db_column='PhoneNumber',
        help_text='أرقام فقط بصيغة دولية بلا +، مثل 972501234567',
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='whatsapp_contacts',
        db_column='TenantID',
    )
    label = models.CharField(
        max_length=100, blank=True, default='', db_column='Label',
        help_text='اسم توضيحي اختياري (مثال: أشرف — مدير المبيعات)',
    )
    is_active = models.BooleanField(default=True, db_column='IsActive')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'whatsapp_contacts'
        managed = True

    def __str__(self):
        return f"{self.phone_number} → {self.tenant.CompanyName}"


# ── N0-T2: TenantBook (أرقام الدفاتر) ──────────────────────────────────

class TenantBook(models.Model):
    """دفتر أرقام لكل نوع مستند — 10 دفاتر افتراضية لكل نوع."""

    DOCUMENT_TYPES = [
        ('sales_invoice', 'فاتورة مبيعات'),
        ('purchase_invoice', 'فاتورة شراء'),
        ('sales_return', 'مرجع بيع'),
        ('purchase_return', 'مرجع شراء'),
        ('receipt_voucher', 'سند قبض'),
        ('payment_voucher', 'سند صرف'),
        ('expense_voucher', 'سند مصروف'),
        ('revenue_voucher', 'سند إيراد'),
        ('multi_receipt', 'إيصال قبض متعدد'),
        ('multi_payment', 'سند صرف متعدد'),
        ('credit_note', 'إشعار دائن'),
        ('debit_note', 'إشعار مدين'),
        ('quotation', 'عرض سعر'),
        ('journal_entry', 'قيد محاسبة'),
        ('deal', 'صفقة'),
        ('shipment', 'شحنة'),
        ('clearance', 'تخليص جمركي'),
        # ISSUE #112: طلبية (طلب عروض أسعار) تسبق عرض المورّد — مواصفة #108.
        ('purchase_rfq', 'طلبية شراء (طلب عروض)'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    # task11 M4: NULL = دفتر على مستوى الشركة (التوافق القديم)؛ قيمة = دفتر فرع
    # مستقل بتسلسله الخاص. ملاحظة MySQL: قيود unique لا تمنع تكرار NULL — التفرد
    # لصفوف NULL محمي تطبيقياً بقفل get_next_number.
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, null=True, blank=True,
        db_column='BranchID', related_name='books')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES, db_column='DocumentType')
    book_number = models.IntegerField(default=0, db_column='BookNumber')

    name = models.CharField(max_length=100, null=True, blank=True, db_column='Name')
    last_used_number = models.IntegerField(default=0, db_column='LastUsedNumber')
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'tenant_books'
        managed = True
        unique_together = [['tenant', 'branch', 'document_type', 'book_number']]

    @classmethod
    def get_next_number(
        cls, tenant_id: int, document_type: str,
        book_number: int = 0, branch_id: int | None = None,
    ) -> int:
        """P-H-11: يولد الرقم التالي مع select_for_update لضمان الذرية.

        يستخدم قفل الصف (row-level lock) لمنع سباق الرقم المتزامن بين
        المستخدمين. يخلق الدفتر تلقائياً إذا لم يكن موجوداً.
        task11 M4: branch_id يعزل تسلسل كل فرع عن الآخر.
        """
        from django.db import transaction
        with transaction.atomic():
            book = cls.objects.select_for_update().get_or_create(
                tenant_id=tenant_id,
                branch_id=branch_id,
                document_type=document_type,
                book_number=book_number,
                defaults={
                    'name': f'{document_type} [{book_number}]',
                    'last_used_number': 0,
                    'is_active': True,
                },
            )[0]
            if not book.is_active:
                from django.core.exceptions import ValidationError
                raise ValidationError(f"الدفتر {book_number} لنوع {document_type} غير نشط.")
            next_num = book.last_used_number + 1
            book.last_used_number = next_num
            book.save(update_fields=['last_used_number'])
            return next_num

    def __str__(self):
        return f"{self.tenant} — {self.document_type} [{self.book_number}]"


# ── ISSUE #54: تسليم الدفاتر (نمط Xero) ─────────────────────────────────
#
# طلبٌ ينشئه مكتبٌ على دفترٍ مُدارٍ يملكه (`Tenant.managed_by`)، ولا يتم شيء
# حتى يقبله العميل المدعوّ صراحةً. القبول وحده يُسقط `managed_by` — لا قيدٌ
# يُعاد ولا رقمٌ يتغيّر، عَلَمُ ملكيةٍ وحده. حصّة `office.managed_books` تتحرّر
# تلقائياً لأنها عدٌّ حيّ على `managed_by` (`core/plans.py`)، لا عدّاداً مخزَّناً.
class BookHandoverRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('accepted', 'مقبول'),
        ('expired', 'منتهي'),
        ('cancelled', 'ملغى'),
    ]

    book = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='handover_requests',
        db_column='BookTenantID',
        help_text='الدفتر المُدار محلّ التسليم',
    )
    # المكتب يُسجَّل صراحةً وقت الإنشاء بدل الاعتماد على `book.managed_by`
    # وقت القراءة — القبول يُسقط ذلك الحقل، فيضيع مصدر «مَن سلَّم لمَن» تاريخياً
    # لو اعتمدنا عليه وحده.
    office = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='sent_handover_requests',
        db_column='OfficeTenantID',
        help_text='مكتب المحاسبة المُرسِل — كما كان وقت إنشاء الطلب',
    )
    invited_user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='book_handover_requests',
        db_column='InvitedUserID',
        help_text='مستخدم العميل المدعوّ للقبول — هو وحده مَن يملك قبول هذا الطلب',
    )
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', db_column='CreatedByUserID',
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending', db_column='Status')
    expires_at = models.DateTimeField(db_column='ExpiresAt')
    accepted_at = models.DateTimeField(null=True, blank=True, db_column='AcceptedAt')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'tenant_book_handover_requests'
        managed = True
        indexes = [
            models.Index(fields=['book', 'status'], name='idx_bhr_book_status'),
        ]

    def __str__(self):
        return f"handover({self.book_id} → {self.invited_user_id}) [{self.status}]"


class UserCompanyMembership(models.Model):
    ROLE_CHOICES = [
        ('manager', 'مدير (Manager)'),
        ('accountant', 'محاسب (Accountant)'),
        ('legal_accountant', 'محاسب قانوني خارجي'),
        # T-PERM: دورا الموظف المتخصّص — لكلٍّ مصفوفة صلاحيات في core.access
        ('sales', 'موظف مبيعات (Sales)'),
        ('procurement', 'موظف مشتريات (Procurement)'),
        ('staff', 'موظف (Staff)'),
        # T-HR: صاحب حسابٍ للخدمة الذاتية وحدها — يبصم ويطلب ويرى قسيمته.
        # `ess` لا `employee`: الأخيرة محجوزة لدور التطبيق القديم (انظر
        # `core/access.py` عند `_ESS_EMPLOYEE` و`user_tenant_role`).
        ('ess', 'موظف خدمة ذاتية (ESS)'),
        ('viewer', 'مستعرض (Viewer)'),
    ]

    UI_MODE_CHOICES = [
        ('simple', 'الوضع السهل'),
        ('advanced', 'الواجهة المتقدمة'),
    ]

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='company_memberships', db_column='UserID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships', db_column='TenantID')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff', db_column='Role')
    is_default = models.BooleanField(default=False, db_column='IsDefault')
    # منح هذا العضو صلاحية وحدة الاستيراد — يضبطه مدير الشركة، وفعّال فقط ضمن
    # شركة مفعّل لديها الاستيراد. المدير يملكها ضمناً.
    can_access_import = models.BooleanField(default=False, db_column='CanAccessImport')
    # عضوية أنشأها تعيين «شركة المثال» وليست دعوة أصلية من مدير الشركة.
    is_example_access = models.BooleanField(default=False, db_column='IsExampleAccess')
    # وضع عرض الواجهة لهذا العضو في هذه الشركة — «سهل» يقلّم القائمة والنماذج
    # ولا يمسّ صلاحية ولا منطقاً محاسبياً. تفضيل شخصي لكل (مستخدم × شركة): نفس
    # الشخص قد يكون سهلاً في شركته ومتقدماً في شركة يحاسب لها. الافتراضي
    # «متقدم» كي لا تتبدّل تجربة عضو قائم صامتاً.
    ui_mode = models.CharField(
        max_length=10, choices=UI_MODE_CHOICES, default='advanced', db_column='UiMode')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'user_company_memberships'
        managed = True
        unique_together = [['user', 'tenant']]

    def __str__(self):
        return f"{self.user.username} - {self.tenant.CompanyName} ({self.role})"



class RolePermission(models.Model):
    """T-PERM: تجاوز صلاحية لدور داخل شركة بعينها.

    الافتراضات في `core.access.ROLE_DEFAULTS`؛ هذا الجدول يحمل الفروق فقط
    (منح صريح allowed=True أو منع صريح allowed=False) كما يضبطها مدير الشركة من
    شاشة الصلاحيات. غياب السطر = «كما هو الافتراضي» — فالاستعادة تعني الحذف.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='role_permissions',
        db_column='TenantID')
    role = models.CharField(
        max_length=20, choices=UserCompanyMembership.ROLE_CHOICES, db_column='Role')
    permission_key = models.CharField(max_length=64, db_column='PermissionKey')
    allowed = models.BooleanField(default=True, db_column='Allowed')
    updated_at = models.DateTimeField(auto_now=True, db_column='UpdatedAt')

    class Meta:
        db_table = 'tenant_role_permissions'
        managed = True
        unique_together = [['tenant', 'role', 'permission_key']]

    def __str__(self):
        state = 'منح' if self.allowed else 'منع'
        return f"{self.tenant_id}/{self.role}/{self.permission_key} = {state}"


class MemberPermission(models.Model):
    """T-PERM (المرحلة 2): تجاوز صلاحية لعضو بعينه فوق دوره.

    الترتيب: افتراضي الدور ← تجاوز الدور (RolePermission) ← هذا الجدول (الأعلى).
    مثال: موظف مبيعات واحد يُمنح «التراجع عن ترحيل فاتورة بيع» دون زملائه.
    حذف السطر = العودة لما يمليه الدور.
    """

    membership = models.ForeignKey(
        UserCompanyMembership, on_delete=models.CASCADE,
        related_name='permission_overrides', db_column='MembershipID')
    permission_key = models.CharField(max_length=64, db_column='PermissionKey')
    allowed = models.BooleanField(default=True, db_column='Allowed')
    updated_at = models.DateTimeField(auto_now=True, db_column='UpdatedAt')

    class Meta:
        db_table = 'member_permissions'
        managed = True
        unique_together = [['membership', 'permission_key']]

    def __str__(self):
        state = 'منح' if self.allowed else 'منع'
        return f"{self.membership_id}/{self.permission_key} = {state}"
