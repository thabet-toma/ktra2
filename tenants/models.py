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

    class Meta:
        db_table = 'tenant_settings'
        managed = True

    def __str__(self):
        return f"Settings — {self.tenant}"


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
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES, db_column='DocumentType')
    book_number = models.IntegerField(default=0, db_column='BookNumber')

    name = models.CharField(max_length=100, null=True, blank=True, db_column='Name')
    last_used_number = models.IntegerField(default=0, db_column='LastUsedNumber')
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'tenant_books'
        managed = True
        unique_together = [['tenant', 'document_type', 'book_number']]

    def __str__(self):
        return f"{self.tenant} — {self.document_type} [{self.book_number}]"
