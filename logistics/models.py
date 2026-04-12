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
    tax_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0.00, db_column='tax_rate')
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

    SHIPPING_WORKFLOW_CHOICES = [
        ('sw_mfg_start', 'Start manufacturing'),
        ('sw_wait_agent_ship', 'Mfg done wait ship to agent'),
        ('sw_wait_intl_ship', 'At agent wait international ship'),
        ('sw_wait_arrival', 'Wait shipment arrival'),
        ('sw_wait_clearance', 'Wait clearance'),
        ('sw_released', 'Released cleared'),
    ]
    shipping_workflow_status = models.CharField(
        max_length=32,
        choices=SHIPPING_WORKFLOW_CHOICES,
        null=True,
        blank=True,
        db_column='shipping_workflow_status',
    )

    class Meta:
        db_table = 'logistics_deals'
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'ref_number'],
                name='unique_tenant_deal_ref',
            ),
        ]

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
    deal = models.ForeignKey(
        LogisticsDeal,
        on_delete=models.CASCADE,
        related_name='payments',
        db_column='DealID',
        null=True,
        blank=True,
    )
    shipment = models.ForeignKey(
        'LogisticsShipment',
        on_delete=models.CASCADE,
        related_name='agent_payments',
        db_column='LinkedShipmentID',
        null=True,
        blank=True,
    )
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
    # معرف مستند الصندوق في Firestore — يُربَط بحساب GL عبر CashBoxLedgerAccount
    cash_box_external_id = models.CharField(max_length=128, null=True, blank=True, db_column='cash_box_external_id')

    class Meta:
        db_table = 'logistics_payments'
        managed = True

    def __str__(self):
        if self.deal_id:
            return f"{self.title} - {self.deal.ref_number}"
        if self.shipment_id:
            return f"{self.title} - شحنة {self.shipment.shipment_number}"
        return f"{self.title} - #{self.pk}"

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

class LogisticsShipment(SoftDeleteMixin, models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In-Transit', 'In-Transit'),
        ('Arrived', 'Arrived'),
        ('Clearing', 'Clearing'),
        ('Cleared', 'Cleared'),
    ]

    id = models.AutoField(primary_key=True, db_column='ShipmentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    shipment_number = models.CharField(max_length=50, db_column='ShipmentNumber', default='')
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
    # مراحل المسار التفصيلية (مثل الواجهة: agent_warehouse, at_sea, …) — عمود Status يبقى للحالة الخشنة
    shipment_route_status = models.CharField(
        max_length=64, null=True, blank=True, db_column='shipment_route_status'
    )
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

    def save(self, *args, **kwargs):
        if not self.shipment_number or self.shipment_number in ('', 'NEW'):
            last = (
                LogisticsShipment.objects
                .order_by('-id')
                .values_list('id', flat=True)
                .first()
            )
            next_id = (last or 0) + 1
            self.shipment_number = f"SH-{next_id:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.shipment_number

class LogisticsShipmentDeal(models.Model):
    id = models.AutoField(primary_key=True, db_column='LinkID')
    shipment = models.ForeignKey(LogisticsShipment, on_delete=models.CASCADE, db_column='ShipmentID')
    deal = models.ForeignKey(LogisticsDeal, on_delete=models.PROTECT, db_column='DealID')
    allocated_shipping_cost = models.DecimalField(
        max_digits=18, decimal_places=2, default=0.00,
        db_column='AllocatedShippingCostUSD',
        help_text='Share of international shipping (USD) allocated to this deal on the shipment',
    )
    extra_costs = models.DecimalField(
        max_digits=18, decimal_places=2, default=0.00,
        db_column='ExtraCostsUSD',
        help_text='Additional shipment-side costs allocated to this deal (USD)',
    )

    class Meta:
        db_table = 'logistics_shipment_deals'
        managed = True
        unique_together = [['shipment', 'deal']]

def default_clearance_cost_lines():
    """بنود تكلفة التخليص الافتراضية — قابلة للتعديل/الحذف من الواجهة."""
    return [
        {"label": "ضريبة القيمة المضافة", "amount": 0},
        {"label": "رسوم البيان الجمركي", "amount": 0},
        {"label": "محطة الشحن", "amount": 0},
        {"label": "معالجة التصاريح", "amount": 0},
        {"label": "عمولة المخلص", "amount": 0},
        {"label": 'نظام الجمارك «الجيل الجديد»', "amount": 0},
    ]


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
    cost_lines = models.JSONField(
        default=default_clearance_cost_lines,
        blank=True,
        db_column='cost_lines',
    )

    class Meta:
        db_table = 'logistics_clearance'
        managed = True


class LogisticsClearancePayment(models.Model):
    """دفعة تخليص: قيد مباشر بين حساب المخلّص وحساب الصندوق."""

    id = models.AutoField(primary_key=True, db_column='ClearancePaymentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    clearance = models.ForeignKey(
        LogisticsClearance,
        on_delete=models.CASCADE,
        related_name='payments',
        db_column='ClearanceID',
    )
    customs_broker = models.ForeignKey(
        Partner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clearance_payments',
        db_column='CustomsBrokerID',
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount')
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='CurrencyID_ClearancePay',
        related_name='clearance_payments',
        help_text='Payment amount currency; null = ILS (legacy)',
    )
    payment_date = models.DateField(null=True, blank=True, db_column='PaymentDate')
    cash_box_external_id = models.CharField(max_length=128, db_column='CashBoxExternalID')
    notes = models.TextField(null=True, blank=True, db_column='Notes')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, db_column='JournalID')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'logistics_clearance_payments'
        managed = True
        indexes = [
            models.Index(fields=['clearance', 'payment_date']),
            models.Index(fields=['tenant', 'cash_box_external_id']),
        ]

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

class PurchaseInvoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'مسودة'),
        ('incomplete', 'غير مكتملة'),
        ('completed', 'مكتملة'),
        ('deposit_paid', 'دفعة أولى'),
        ('partially_paid', 'مدفوعة جزئياً'),
        ('fully_paid', 'مدفوعة بالكامل'),
        ('archived', 'مؤرشفة'),
    ]

    id = models.AutoField(primary_key=True, db_column='PurchaseInvoiceID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    invoice_number = models.CharField(max_length=50, db_column='InvoiceNumber')
    invoice_name = models.CharField(max_length=255, null=True, blank=True, db_column='InvoiceName')
    invoice_date = models.DateField(null=True, blank=True, db_column='InvoiceDate')

    partner = models.ForeignKey(
        Partner, on_delete=models.PROTECT, db_column='PartnerID',
        related_name='purchase_invoices',
    )
    deal = models.ForeignKey(
        LogisticsDeal, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='DealID', related_name='purchase_invoices',
    )
    shipment = models.ForeignKey(
        LogisticsShipment, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='ShipmentID', related_name='purchase_invoices',
    )
    clearance = models.ForeignKey(
        LogisticsClearance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='ClearanceID',
        related_name='purchase_invoices',
    )

    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, default=1,
        db_column='CurrencyID',
    )
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1.0, db_column='ExchangeRate')

    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='Subtotal')
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='DiscountAmount')
    tax_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0, db_column='TaxRate')
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='TaxAmount')
    tax_type = models.CharField(
        max_length=20,
        choices=[('percentage', 'نسبة'), ('amount', 'مبلغ ثابت')],
        default='percentage', db_column='TaxType',
    )
    shipping_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='ShippingCost')
    shipping_included = models.BooleanField(default=False, db_column='ShippingIncluded')
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='GrandTotal')

    local_payments_json = models.JSONField(null=True, blank=True, db_column='LocalPaymentsJSON')
    conversion_metadata_json = models.JSONField(null=True, blank=True, db_column='ConversionMetadataJSON')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    supplier_invoice_number = models.CharField(max_length=100, null=True, blank=True, db_column='SupplierInvoiceNumber')
    factory_name = models.CharField(max_length=255, null=True, blank=True, db_column='FactoryName')

    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='purchase_invoices',
    )

    firestore_id = models.CharField(
        max_length=100, null=True, blank=True, db_column='FirestoreID',
        help_text='Legacy link to Firestore document id',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='UpdatedAt')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedBy_UserID',
    )

    class Meta:
        db_table = 'purchase_invoices'
        managed = True
        indexes = [
            models.Index(fields=['tenant', 'invoice_number']),
            models.Index(fields=['partner']),
            models.Index(fields=['deal']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.invoice_number} — {self.partner.name}"


class PurchaseInvoiceItem(models.Model):
    id = models.AutoField(primary_key=True, db_column='InvoiceItemID')
    invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.CASCADE,
        db_column='PurchaseInvoiceID', related_name='items',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, null=True, blank=True,
        db_column='ProductID', related_name='invoice_items',
    )
    name = models.CharField(max_length=255, db_column='Name')
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column='Quantity')
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, db_column='UnitPrice')
    total_price = models.DecimalField(max_digits=18, decimal_places=2, db_column='TotalPrice')
    notes = models.CharField(max_length=500, null=True, blank=True, db_column='Notes')
    hs_code = models.CharField(max_length=20, null=True, blank=True, db_column='HSCode')

    landed_unit_price_ils = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True,
        db_column='LandedUnitPriceILS',
    )
    landed_line_total_ils = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        db_column='LandedLineTotalILS',
    )

    class Meta:
        db_table = 'purchase_invoice_items'
        managed = True

    def __str__(self):
        return f"{self.name} x{self.quantity}"


# Automatically connect signals for the logistics app
import logistics.signals
