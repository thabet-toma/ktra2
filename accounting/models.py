from django.db import models
from tenants.models import Tenant, Currency
from core.base_models import SoftDeleteMixin, TimeStampMixin
from partners.models import Partner

class CostCenter(models.Model):
    id = models.AutoField(primary_key=True, db_column='CostCenterID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    name = models.CharField(max_length=150, db_column='Name')
    code = models.CharField(max_length=50, null=True, blank=True, db_column='Code')
    description = models.TextField(null=True, blank=True, db_column='Description')

    class Meta:
        db_table = 'cost_centers'
        managed = True
        unique_together = [['tenant', 'name']]

    def __str__(self):
        return self.name

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('Asset', 'Asset'),
        ('Liability', 'Liability'),
        ('Equity', 'Equity'),
        ('Revenue', 'Revenue'),
        ('Expense', 'Expense'),
    ]

    id = models.AutoField(primary_key=True, db_column='AccountID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    code = models.CharField(max_length=20, null=True, blank=True, db_column='Code')
    name = models.CharField(max_length=100, null=True, blank=True, db_column='Name')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, db_column='ParentID', related_name='children')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, null=True, blank=True, db_column='Type')
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'chartofaccounts'
        managed = True
        unique_together = [['tenant', 'code']]

    def __str__(self):
        return f"{self.code} - {self.name}"

class JournalHeader(models.Model):
    id = models.AutoField(primary_key=True, db_column='JournalID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    transaction_date = models.DateField(null=True, blank=True, db_column='TransactionDate')
    reference_type = models.CharField(max_length=50, null=True, blank=True, db_column='ReferenceType')
    reference_id = models.IntegerField(null=True, blank=True, db_column='ReferenceID')
    description = models.TextField(null=True, blank=True, db_column='Description')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')

    class Meta:
        db_table = 'journal_headers'
        managed = True

    def __str__(self):
        return f"Journal {self.id} - {self.transaction_date}"

class JournalLine(models.Model):
    id = models.AutoField(primary_key=True, db_column='JLineID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    journal = models.ForeignKey(JournalHeader, on_delete=models.CASCADE, db_column='JournalID', related_name='lines', default=1)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, db_column='AccountID', default=1)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='Debit')
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='Credit')
    
    # Updated to Strict Foreign Keys
    partner = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, blank=True, db_column='PartnerID')
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, db_column='CostCenterID')
    
    project_id = models.IntegerField(null=True, blank=True, db_column='ProjectID')

    class Meta:
        db_table = 'journal_lines'
        managed = True

class Cheque(models.Model):
    DIRECTION_CHOICES = [
        ('Incoming', 'Incoming'), # From Customer
        ('Outgoing', 'Outgoing'), # To Supplier
    ]
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Under_Collection', 'Under Collection'),
        ('Collected', 'Collected'),
        ('Bounced', 'Bounced'),
        ('Returned', 'Returned'),
    ]

    id = models.AutoField(primary_key=True, db_column='ChequeID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    cheque_number = models.CharField(max_length=50, db_column='ChequeNumber')
    bank_name = models.CharField(max_length=100, null=True, blank=True, db_column='BankName')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount', default=0.00)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, default=1, db_column='CurrencyID')
    due_date = models.DateField(db_column='DueDate', null=True, blank=True)
    issue_date = models.DateField(null=True, blank=True, db_column='IssueDate')
    payee_name = models.CharField(max_length=150, null=True, blank=True, db_column='PayeeName')
    partner = models.ForeignKey(Partner, on_delete=models.RESTRICT, null=True, blank=True, db_column='PartnerID')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Draft', db_column='Status')
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, db_column='Direction', default='Incoming')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, db_column='CreatedBy_UserID')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    class Meta:
        db_table = 'cheques'
        managed = True

    def __str__(self):
        return f"Cheque {self.cheque_number} - {self.amount}"




class AccountingAuditLog(models.Model):
    ACTIONS = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('POST', 'Post'),
    ]

    id = models.AutoField(primary_key=True, db_column='LogID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, db_column='UserID')
    action = models.CharField(max_length=20, choices=ACTIONS, db_column='Action')
    model_name = models.CharField(max_length=100, db_column='ModelName')
    object_id = models.IntegerField(db_column='ObjectID')
    change_details = models.TextField(db_column='ChangeDetails')
    timestamp = models.DateTimeField(auto_now_add=True, db_column='Timestamp')

    class Meta:
        db_table = 'accounting_audit_logs'
        managed = True

class FiscalPeriod(models.Model):
    id = models.AutoField(primary_key=True, db_column='PeriodID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    name = models.CharField(max_length=100, db_column='PeriodName')
    start_date = models.DateField(db_column='StartDate')
    end_date = models.DateField(db_column='EndDate')
    status = models.CharField(max_length=20, default='Open', db_column='Status')

    class Meta:
        db_table = 'fiscal_periods'
        managed = False

    def __str__(self):
        return f"{self.name} ({self.status})"
