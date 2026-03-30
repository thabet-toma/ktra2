from django.db import models
from tenants.models import Tenant, Currency
from partners.models import Partner
from inventory.models import Product
from accounting.models import Account, JournalHeader
from django.contrib.auth.models import User
from core.base_models import SoftDeleteMixin, TimeStampMixin

class LogisticsDeal(SoftDeleteMixin, models.Model):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Shipped', 'Shipped'),
        ('Cleared', 'Cleared'),
        ('Closed', 'Closed'),
        ('Cancelled', 'Cancelled'),
    ]

    id = models.AutoField(primary_key=True, db_column='DealID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    ref_number = models.CharField(max_length=50, db_column='RefNumber')
    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, db_column='PartnerID')
    order_date = models.DateField(db_column='OrderDate')
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='TotalAmount')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open', db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column='CreatedBy_UserID')

    # Professional Logistics Fields
    pi_number = models.CharField(max_length=50, null=True, blank=True, db_column='pi_number')
    description = models.CharField(max_length=255, null=True, blank=True, db_column='description')
    shipping_method = models.CharField(max_length=50, default='Sea', db_column='shipping_method')
    incoterms = models.CharField(max_length=10, default='FOB', db_column='incoterms')
    payment_method = models.CharField(max_length=50, default='T/T', db_column='payment_method')
    production_days = models.IntegerField(default=0, db_column='production_days')
    delivery_days = models.IntegerField(default=0, db_column='delivery_days')
    total_cbm = models.DecimalField(max_digits=10, decimal_places=3, default=0.000, db_column='total_cbm')
    total_weight = models.DecimalField(max_digits=10, decimal_places=3, default=0.000, db_column='total_weight')
    certificates = models.CharField(max_length=255, null=True, blank=True, db_column='certificates')
    shipping_cost_estimate = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='shipping_cost_estimate')
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='discount_amount')
    fees_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, db_column='fees_percentage')
    is_shipping_included = models.BooleanField(default=False, db_column='is_shipping_included')
    alibaba_link = models.CharField(max_length=500, null=True, blank=True, db_column='alibaba_link')
    
    # Exact Mapping Fields from deal.ts
    price_offer_id = models.CharField(max_length=50, null=True, blank=True, db_column='price_offer_id')
    original_offer_number = models.CharField(max_length=50, null=True, blank=True, db_column='original_offer_number')
    factory_name = models.CharField(max_length=255, null=True, blank=True, db_column='factory_name')
    supplier_invoice_number = models.CharField(max_length=100, null=True, blank=True, db_column='supplier_invoice_number')
    installment_plan_enabled = models.BooleanField(default=False, db_column='installment_plan_enabled')
    current_installment_number = models.IntegerField(null=True, blank=True, db_column='current_installment_number')
    remaining_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='remaining_amount')
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='subtotal')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, db_column='tax_rate')
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='tax_amount')
    tax_type = models.CharField(max_length=20, choices=[('percentage', 'percentage'), ('amount', 'amount')], default='percentage', db_column='tax_type')
    warranty_duration = models.IntegerField(null=True, blank=True, db_column='warranty_duration')
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, db_column='total_weight_kg')
    shipment_notes = models.TextField(null=True, blank=True, db_column='shipment_notes')
    first_payment_date = models.DateField(null=True, blank=True, db_column='first_payment_date')
    payment_date = models.DateField(null=True, blank=True, db_column='payment_date')
    started_production_at = models.DateField(null=True, blank=True, db_column='started_production_at')

    # V2 Overhaul Fields
    payment_status = models.CharField(
        max_length=20, 
        choices=[('Unpaid', 'Unpaid'), ('Partially Paid', 'Partially Paid'), ('Fully Paid', 'Fully Paid')],
        default='Unpaid',
        db_column='PaymentStatus'
    )
    order_status = models.CharField(
        max_length=20,
        choices=[
            ('Open', 'Open'),
            ('Manufacturing', 'Manufacturing'),
            ('ReadyToShip', 'ReadyToShip'),
            ('Shipping', 'Shipping'),
            ('Clearance', 'Clearance'),
            ('Delivered', 'Delivered'),
            ('Closed', 'Closed')
        ],
        default='Open',
        db_column='OrderStatus'
    )
    currency_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1.0, db_column='CurrencyRate')

    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, db_column='JournalID')

    class Meta:
        db_table = 'logistics_deals'
        managed = True

    def __str__(self):
        return f"{self.ref_number} - {self.partner.name}"

class LogisticsPayment(SoftDeleteMixin, models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('ClaimUploaded', 'ClaimUploaded'),
        ('Paid', 'Paid'),
        ('Confirmed', 'Confirmed'),
    ]

    id = models.AutoField(primary_key=True, db_column='PaymentID')
    deal = models.ForeignKey(LogisticsDeal, on_delete=models.CASCADE, related_name='payments', db_column='DealID')
    payment_number = models.IntegerField(db_column='PaymentNumber', default=1)
    title = models.CharField(max_length=100, db_column='Title', default='Payment')
    due_date = models.DateField(null=True, blank=True, db_column='DueDate')
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, db_column='Percentage')
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='Amount')
    amount_local = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='Amount_Local')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_column='Status')
    claim_doc = models.CharField(max_length=255, null=True, blank=True, db_column='ClaimDoc')
    invoice_doc = models.CharField(max_length=255, null=True, blank=True, db_column='InvoiceDoc')
    transfer_date = models.DateField(null=True, blank=True, db_column='TransferDate')
    confirmation_date = models.DateField(null=True, blank=True, db_column='ConfirmationDate')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    # Exact Mapping Fields from deal.ts
    usd_to_ils = models.DecimalField(max_digits=18, decimal_places=6, default=3.5, db_column='usd_to_ils')
    transfer_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='transfer_cost')
    bank_swift_image = models.CharField(max_length=500, null=True, blank=True, db_column='bank_swift_image')
    supplier_confirmation_image = models.CharField(max_length=500, null=True, blank=True, db_column='supplier_confirmation_image')
    supplier_notes = models.TextField(null=True, blank=True, db_column='supplier_notes')
    confirmed_by_supplier = models.BooleanField(default=False, db_column='confirmed_by_supplier')

    # Accounting Integration
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True, db_column='JournalID')
    bank_account = models.ForeignKey('accounting.Account', on_delete=models.SET_NULL, null=True, blank=True, db_column='BankAccountID', related_name='payment_bank_entries')

    class Meta:
        db_table = 'logistics_payments'
        managed = True
    
    def __str__(self):
        return f"{self.title} - {self.deal.ref_number}"

class LogisticsDealItem(SoftDeleteMixin, models.Model):
    id = models.AutoField(primary_key=True, db_column='DealItemID')
    deal = models.ForeignKey(LogisticsDeal, on_delete=models.CASCADE, related_name='items', db_column='DealID')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='ProductID')
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column='Quantity')
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, db_column='UnitPrice')
    notes = models.CharField(max_length=255, null=True, blank=True, db_column='Notes')

    class Meta:
        db_table = 'logistics_deal_items'
        managed = True
    
    @property
    def total_price(self):
        return self.quantity * self.unit_price

class LogisticsShipment(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In-Transit', 'In-Transit'),
        ('Arrived', 'Arrived'),
        ('Clearing', 'Clearing'),
        ('Cleared', 'Cleared'),
    ]

    id = models.AutoField(primary_key=True, db_column='ShipmentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    shipment_number = models.CharField(max_length=50, db_column='ShipmentNumber', default='NEW')
    shipping_agent = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, db_column='ShippingAgentID', related_name='shipments_as_agent')
    bill_of_lading = models.CharField(max_length=100, null=True, blank=True, db_column='BillOfLading')
    container_number = models.CharField(max_length=100, null=True, blank=True, db_column='ContainerNumber')
    departure_date = models.DateField(null=True, blank=True, db_column='DepartureDate')
    arrival_date = models.DateField(null=True, blank=True, db_column='ArrivalDate')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    # Exact Mapping Fields from shipment.ts
    agent_shipment_number = models.CharField(max_length=100, null=True, blank=True, db_column='agent_shipment_number')
    israeli_side_name = models.CharField(max_length=255, null=True, blank=True, db_column='israeli_side_name')
    shipment_name = models.CharField(max_length=255, null=True, blank=True, db_column='shipment_name')
    pricing_method = models.CharField(max_length=50, choices=[('total', 'total'), ('unit', 'unit')], null=True, blank=True, db_column='pricing_method')
    unit_type = models.CharField(max_length=50, choices=[('cbm', 'cbm'), ('weight', 'weight'), ('container', 'container')], null=True, blank=True, db_column='unit_type')
    price_per_unit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='price_per_unit')
    total_shipping_cost_usd = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='total_shipping_cost_usd')
    total_volume = models.DecimalField(max_digits=10, decimal_places=3, default=0.000, db_column='total_volume')
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0.000, db_column='total_weight_kg')
    remaining_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, db_column='remaining_amount')
    installment_plan_enabled = models.BooleanField(default=False, db_column='installment_plan_enabled')
    shipping_type = models.CharField(max_length=20, choices=[('sea', 'sea'), ('air', 'air')], default='sea', db_column='shipping_type')
    ship_name = models.CharField(max_length=255, null=True, blank=True, db_column='ship_name')
    international_shipping_company = models.CharField(max_length=255, null=True, blank=True, db_column='international_shipping_company')
    bill_of_lading_file = models.CharField(max_length=500, null=True, blank=True, db_column='bill_of_lading_file')
    flight_number = models.CharField(max_length=100, null=True, blank=True, db_column='flight_number')
    airway_bill_number = models.CharField(max_length=100, null=True, blank=True, db_column='airway_bill_number')
    airway_bill_file = models.CharField(max_length=500, null=True, blank=True, db_column='airway_bill_file')
    from_term = models.CharField(max_length=100, null=True, blank=True, db_column='from_term')
    to_term = models.CharField(max_length=100, null=True, blank=True, db_column='to_term')
    imo_number = models.CharField(max_length=100, null=True, blank=True, db_column='imo_number')
    mmsi_number = models.CharField(max_length=100, null=True, blank=True, db_column='mmsi_number')
    tracking_link = models.CharField(max_length=500, null=True, blank=True, db_column='tracking_link')

    deals = models.ManyToManyField(LogisticsDeal, through='LogisticsShipmentDeal', related_name='shipments')

    class Meta:
        db_table = 'logistics_shipments'
        managed = True

    def __str__(self):
        return self.shipment_number

class LogisticsShipmentDeal(models.Model):
    id = models.AutoField(primary_key=True, db_column='LinkID')
    shipment = models.ForeignKey(LogisticsShipment, on_delete=models.CASCADE, db_column='ShipmentID')
    deal = models.ForeignKey(LogisticsDeal, on_delete=models.PROTECT, db_column='DealID')

    class Meta:
        db_table = 'logistics_shipment_deals'
        managed = True
        unique_together = [['shipment', 'deal']]

class LogisticsClearance(models.Model):
    STATUS_CHOICES = [
        ('Processing', 'Processing'),
        ('Cleared', 'Cleared'),
        ('Hold', 'Hold'),
    ]

    id = models.AutoField(primary_key=True, db_column='ClearanceID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    shipment = models.OneToOneField(LogisticsShipment, on_delete=models.CASCADE, db_column='ShipmentID', related_name='clearance')
    customs_broker = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, db_column='CustomsBrokerID', related_name='clearances_as_broker')
    declaration_number = models.CharField(max_length=100, null=True, blank=True, db_column='DeclarationNumber')
    clearance_date = models.DateField(null=True, blank=True, db_column='ClearanceDate')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Processing', db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    class Meta:
        db_table = 'logistics_clearance'
        managed = True

class LogisticsExpense(models.Model):
    RELATED_TYPE_CHOICES = [
        ('Deal', 'Deal'),
        ('Shipment', 'Shipment'),
        ('Clearance', 'Clearance'),
    ]

    id = models.AutoField(primary_key=True, db_column='ExpenseID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    related_type = models.CharField(max_length=20, choices=RELATED_TYPE_CHOICES, db_column='RelatedType')
    related_id = models.IntegerField(db_column='RelatedID')
    
    # Financial Integration
    expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, db_column='ExpenseAccountID', related_name='logistics_expenses')
    payable_account = models.ForeignKey(Account, on_delete=models.PROTECT, db_column='PayableAccountID', related_name='logistics_payables')
    
    description = models.CharField(max_length=255, db_column='Description')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, default=1, db_column='CurrencyID')
    invoice_number = models.CharField(max_length=100, null=True, blank=True, db_column='InvoiceNumber')
    invoice_date = models.DateField(null=True, blank=True, db_column='InvoiceDate')
    
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, db_column='JournalID')

    class Meta:
        db_table = 'logistics_expenses'
        managed = True
        indexes = [
            models.Index(fields=['related_type', 'related_id']),
        ]

# Automatically connect signals for the logistics app
import logistics.signals
