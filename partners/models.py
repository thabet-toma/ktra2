from django.db import models
from tenants.models import Tenant, Currency

class PartnerGroup(models.Model):
    id = models.AutoField(primary_key=True, db_column='GroupID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    name = models.CharField(max_length=100, db_column='Name', default='Group')
    group_type = models.CharField(max_length=50, choices=[('Customer', 'Customer'), ('Supplier', 'Supplier')], db_column='Type', default='Customer')
    
    # Financial Links
    account_receivable = models.ForeignKey('accounting.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='ar_groups', db_column='AccountReceivableID')
    account_payable = models.ForeignKey('accounting.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='ap_groups', db_column='AccountPayableID')

    class Meta:
        db_table = 'partner_groups'
        managed = True

    def __str__(self):
        return self.name

class Partner(models.Model):
    PARTNER_TYPES = [
        ('Customer', 'Customer'),
        ('Supplier', 'Supplier'),
        ('FreightForwarder', 'FreightForwarder'),
        ('CustomsBroker', 'CustomsBroker'),
        ('LocalTransporter', 'LocalTransporter'),
        ('Carrier', 'Carrier'),
    ]

    # T-IMPOFFER: فصل المورد الدولي عن المحلي. ليس نوعاً ثالثاً في PARTNER_TYPES
    # عمداً — عشرات المواضع تفلتر partner_type='Supplier'، فتقسيم النوع نفسه
    # كان سيُسقِط الموردين الدوليين من كل تلك الشاشات.
    SUPPLIER_SCOPE_LOCAL = 'local'
    SUPPLIER_SCOPE_INTERNATIONAL = 'international'
    SUPPLIER_SCOPE_CHOICES = [
        (SUPPLIER_SCOPE_LOCAL, 'مورد محلي'),
        (SUPPLIER_SCOPE_INTERNATIONAL, 'مورد دولي (استيراد)'),
    ]

    id = models.AutoField(primary_key=True, db_column='PartnerID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='partners', db_column='TenantID', default=1)
    name = models.CharField(max_length=150, db_column='Name', default='New Partner')
    
    # New Group Link
    group = models.ForeignKey(PartnerGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='partners', db_column='GroupID')
    
    legal_name = models.CharField(max_length=255, blank=True, null=True, db_column='LegalName')
    
    # Address fields (detailed)
    street_address = models.CharField(max_length=255, blank=True, null=True, db_column='StreetAddress')
    city = models.CharField(max_length=100, blank=True, null=True, db_column='City')
    state_or_province = models.CharField(max_length=100, blank=True, null=True, db_column='StateOrProvince')
    postal_code = models.CharField(max_length=20, blank=True, null=True, db_column='PostalCode')
    country = models.CharField(max_length=50, blank=True, null=True, db_column='Country')
    
    partner_type = models.CharField(max_length=50, choices=PARTNER_TYPES, db_column='Type', default='Customer')
    # '' = غير مصنَّف: يظهر في قائمتي المورد المحلي والدولي كلتيهما حتى يُصنَّف،
    # فالتصنيف الجديد لا يُخفي مورداً قائماً عن الشاشة التي كان يظهر فيها.
    supplier_scope = models.CharField(
        max_length=20, choices=SUPPLIER_SCOPE_CHOICES, blank=True, default='',
        db_column='SupplierScope',
        help_text='نطاق المورد: محلي أو دولي (استيراد). فارغ = غير مصنَّف.',
    )
    tax_number = models.CharField(max_length=50, blank=True, null=True, db_column='TaxNumber')
    phone = models.CharField(max_length=20, blank=True, null=True, db_column='Phone')
    email = models.EmailField(max_length=100, blank=True, null=True, db_column='Email')
    
    # Financial Info
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True, db_column='CreditLimit')
    source_discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, db_column='SourceDiscountPercent',
        help_text="نسبة خصم مصدر افتراضية على مستوى العميل (0-100)",
    )
    source_discount_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column='SourceDiscountAmount',
        help_text="مبلغ خصم مصدر افتراضي على مستوى العميل",
    )
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='OpeningBalance')
    opening_balance_date = models.DateField(blank=True, null=True, db_column='OpeningBalanceDate')
    currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, blank=True, related_name='partners', db_column='CurrencyID')
    linked_account = models.ForeignKey('accounting.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='linked_partners', db_column='LinkedAccountID')
    image_path = models.CharField(max_length=512, blank=True, null=True, db_column='ImagePath')
    # ── N8-T8: Partner enrichment fields ────────────────────────
    default_cost_center = models.ForeignKey(
        'accounting.CostCenter', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='DefaultCostCenterID', related_name='partners_with_default',
        help_text='مركز التكلفة الافتراضي للشريك',
    )
    end_of_dealing_date = models.DateField(
        null=True, blank=True, db_column='EndOfDealingDate',
        help_text='تاريخ انتهاء التعامل — تحذير عند إضافة معاملات بعد هذا التاريخ',
    )
    assigned_price_tier = models.PositiveSmallIntegerField(
        null=True, blank=True, db_column='AssignedPriceTier',
        help_text='شريحة الأسعار المخصصة (1-5) — تُستخدم في فواتير المبيعات',
    )
    password_for_invoices = models.CharField(
        max_length=50, null=True, blank=True, db_column='PasswordForInvoices',
        help_text='كلمة مرور للفاتورة — يُتحقَّق منها عند إنشاء فاتورة',
    )
    # ── N9-T8: Row color ──
    row_color = models.CharField(
        max_length=7, null=True, blank=True, db_column='RowColor',
        help_text='لون HEX (مثل #ff0000) لتلوين صف الشريك في الجداول',
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'partners'
        managed = True

    def __str__(self):
        return self.name


class CustomerNote(models.Model):
    """ملاحظة/تذكير على بطاقة الزبون — نمط علاقات زبائن (CRM).

    remind_on (اختياري): عند حلول هذا اليوم (أو تجاوزه) يظهر تذكير في إشعارات
    الموقع لملاحظة غير منجزة. is_done: عند إنجازها يتوقف التذكير.

    priority: ملاحظة «عاجل» غير منجزة وحلّ موعدها (أو تأخّر) تُعرَض كتنبيه لكل
    مستخدم يفتح معاملة لهذا الطرف — عميلاً كان أو مورداً.
    """
    PRIORITY_URGENT = 'urgent'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_NORMAL = 'normal'
    PRIORITY_CHOICES = [
        (PRIORITY_URGENT, 'عاجل'),
        (PRIORITY_MEDIUM, 'متوسط'),
        (PRIORITY_NORMAL, 'عادي'),
    ]

    id = models.AutoField(primary_key=True, db_column='CustomerNoteID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='customer_notes', db_column='TenantID')
    partner = models.ForeignKey(
        Partner, on_delete=models.CASCADE, related_name='notes', db_column='PartnerID')
    title = models.CharField(max_length=200, db_column='Title')
    body = models.TextField(blank=True, default='', db_column='Body')
    remind_on = models.DateField(
        null=True, blank=True, db_column='RemindOn',
        help_text='يوم التذكير — يظهر في إشعارات الموقع عند حلوله')
    is_done = models.BooleanField(default=False, db_column='IsDone')
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL,
        db_column='Priority',
        help_text='أولوية الملاحظة — «عاجل» تُنبّه عند أي معاملة للطرف بعد حلول موعدها')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy_UserID', related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='UpdatedAt')

    class Meta:
        db_table = 'partner_customer_notes'
        managed = True
        indexes = [
            models.Index(fields=['tenant', 'partner', '-created_at'], name='pcn_tenant_partner_created'),
            models.Index(fields=['tenant', 'is_done', 'remind_on'], name='pcn_tenant_done_remind'),
            models.Index(fields=['tenant', 'partner', 'priority', 'is_done'], name='pcn_tenant_partner_prio'),
        ]

    def __str__(self):
        return f"{self.title} — {self.partner_id}"


class PartnerBankAccount(models.Model):
    id = models.AutoField(primary_key=True, db_column='PartnerBankAccountID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='bank_accounts', db_column='PartnerID', default=1)
    bank_name = models.CharField(max_length=100, db_column='BankName', default='Bank')
    account_number = models.CharField(max_length=50, db_column='AccountNumber', default='-')
    branch_name = models.CharField(max_length=100, blank=True, null=True, db_column='BranchName')
    iban = models.CharField(max_length=50, blank=True, null=True, db_column='IBAN')
    swift_code = models.CharField(max_length=20, blank=True, null=True, db_column='SwiftCode')
    bank_address = models.CharField(max_length=255, blank=True, null=True, db_column='BankAddress')
    beneficiary_name = models.CharField(max_length=150, blank=True, null=True, db_column='BeneficiaryName')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID', default=1)
    is_active = models.BooleanField(default=True, db_column='IsActive')
    is_default = models.BooleanField(default=False, db_column='IsDefault')

    class Meta:
        db_table = 'partner_bank_accounts'
        managed = True
        unique_together = [['tenant', 'partner', 'account_number']]

    def __str__(self):
        return f"{self.partner.name} - {self.bank_name} ({self.account_number})"

