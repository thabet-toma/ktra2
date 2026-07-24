from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

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
    CreatedAt = models.DateTimeField(auto_now_add=True)
    DomainName = models.CharField(max_length=100, unique=True, null=True, blank=True)
    # وحدة الاستيراد (الصفقات/الشحن/التخليص/الفاتورة الدولية) — يضبطها السوبر أدمن
    # فقط لكل شركة. الشركة غير المفعّلة لا يرى أعضاؤها قائمة الاستيراد ولا قسم
    # «تكاليف الاستيراد» في شجرة الحسابات.
    import_enabled = models.BooleanField(default=False, db_column='ImportEnabled')

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
        help_text="'index' = يفتح فهرس الأصناف, 'cashier' = يفتح فاتورة كاشير",
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

    class Meta:
        db_table = 'tenant_settings'
        managed = True

    def __str__(self):
        return f"Settings — {self.tenant}"


# ── task11 M4: Branch (الفرع) ──────────────────────────────────────────

class Branch(models.Model):
    """فرع تابع لشركة أم.

    التعريف القاطع: الفرع يشارك الشركةَ الأمَّ شجرةَ الحسابات والأصناف
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
        ('multi_receipt', 'إيصال قبض متعدد'),
        ('multi_payment', 'سند صرف متعدد'),
        ('credit_note', 'إشعار دائن'),
        ('debit_note', 'إشعار مدين'),
        ('quotation', 'عرض سعر'),
        ('journal_entry', 'قيد محاسبة'),
        ('deal', 'صفقة'),
        ('shipment', 'شحنة'),
        ('clearance', 'تخليص جمركي'),
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


class UserCompanyMembership(models.Model):
    ROLE_CHOICES = [
        ('manager', 'مدير (Manager)'),
        ('accountant', 'محاسب (Accountant)'),
        ('staff', 'موظف (Staff)'),
        ('viewer', 'مستعرض (Viewer)'),
    ]

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='company_memberships', db_column='UserID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships', db_column='TenantID')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff', db_column='Role')
    is_default = models.BooleanField(default=False, db_column='IsDefault')
    # منح هذا العضو صلاحية وحدة الاستيراد — يضبطه مدير الشركة، وفعّال فقط ضمن
    # شركة مفعّل لديها الاستيراد. المدير يملكها ضمناً.
    can_access_import = models.BooleanField(default=False, db_column='CanAccessImport')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'user_company_memberships'
        managed = True
        unique_together = [['user', 'tenant']]

    def __str__(self):
        return f"{self.user.username} - {self.tenant.CompanyName} ({self.role})"

