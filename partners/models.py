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
    
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'partners'
        managed = True

    def __str__(self):
        return self.name


class PartnerBankAccount(models.Model):
    id = models.AutoField(primary_key=True, db_column='PartnerBankAccountID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name='bank_accounts', db_column='PartnerID', default=1)
    bank_name = models.CharField(max_length=100, db_column='BankName', default='Bank')
    account_number = models.CharField(max_length=50, db_column='AccountNumber', default='-')
    iban = models.CharField(max_length=50, blank=True, null=True, db_column='IBAN')
    swift_code = models.CharField(max_length=20, blank=True, null=True, db_column='SwiftCode')
    bank_address = models.CharField(max_length=255, blank=True, null=True, db_column='BankAddress')
    beneficiary_name = models.CharField(max_length=150, blank=True, null=True, db_column='BeneficiaryName')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID', default=1)
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'partner_bank_accounts'
        managed = True
        unique_together = [['tenant', 'partner', 'account_number']]

    def __str__(self):
        return f"{self.partner.name} - {self.bank_name} ({self.account_number})"

