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
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
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
    short_name = models.CharField(max_length=120, blank=True, default='', db_column='short_name')
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

    book_number = models.PositiveIntegerField(
        default=0, db_column='BookNumber',
        help_text='رقم الدفتر. 0 = يدوي. >0 = مسلسل لكل دفتر مستقل.',
    )

    # P-F-3: Aseel header enrichment fields
    transaction_time = models.TimeField(null=True, blank=True, db_column='TransactionTime', help_text='ساعة الصفقة')
    second_date = models.DateField(null=True, blank=True, db_column='SecondDate', help_text='تاريخ ثاني للصفقة')
    licensed_dealer_no = models.CharField(max_length=100, blank=True, default='', db_column='LicensedDealerNo', help_text='رقم المشتغل المرخص للمورد')
    editable = models.BooleanField(default=True, db_column='Editable', help_text='قابل للتعديل')

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

    # ── State Machine: valid transitions for shipping_workflow_status ──
    VALID_TRANSITIONS = {
        None: ['sw_mfg_start'],
        'sw_mfg_start': ['sw_wait_agent_ship'],
        'sw_wait_agent_ship': ['sw_wait_intl_ship'],
        'sw_wait_intl_ship': ['sw_wait_arrival'],
        'sw_wait_arrival': ['sw_wait_clearance'],
        'sw_wait_clearance': ['sw_released'],
        'sw_released': [],  # terminal state
    }

    def _assert_valid_workflow_transition(self):
        """يرفض الانتقالات غير الصالحة لـ shipping_workflow_status.

        مفروض على مستوى save() (لا clean() فقط) لأن DRF لا يستدعي full_clean
        تلقائياً. التقدّم البرمجي للحالة في signals يستخدم .update() (bulk)
        فيتجاوز هذا الحارس عمداً — نفس نمط حارس القيد المرحّل (I4-02).
        """
        if not self.pk:
            return
        try:
            old = LogisticsDeal.objects.only('shipping_workflow_status').get(pk=self.pk)
        except LogisticsDeal.DoesNotExist:
            return
        old_st = old.shipping_workflow_status
        new_st = self.shipping_workflow_status
        if old_st != new_st:
            allowed = self.VALID_TRANSITIONS.get(old_st, [])
            if new_st not in allowed:
                from django.core.exceptions import ValidationError as DjangoVE
                raise DjangoVE(
                    f"انتقال غير صالح: '{old_st}' → '{new_st}'. "
                    f"المسموح: {allowed or 'لا انتقال (حالة نهائية)'}."
                )

    def clean(self):
        super().clean()
        self._assert_valid_workflow_transition()

    def save(self, *args, **kwargs):
        self._assert_valid_workflow_transition()
        self._sync_legacy_status_fields()
        super().save(*args, **kwargs)

    # ── P-F-4: Status field auto-sync (cache layer over shipping_workflow_status) ──
    #
    # The task6.md plan (P-F-4) suggested converting `status`, `order_status`,
    # `payment_status` to computed @property. A pure @property approach is
    # unsafe in this codebase because:
    #   1. Python's class body makes @property shadow the same-named Field,
    #      breaking Django ORM (`.filter(payment_status=...)`, `.update(...)`).
    #   2. `core/dashboard_api.py` issues 6+ filters/values on `status` and
    #      `payment_status`. `logistics.signals.recalculate_deal_payment_status`
    #      uses `.update(payment_status=...)`. The migrate-from-firebase command
    #      writes to `payment_status` directly. Frontend `SqlDealsPage` reads
    #      both fields from the API response.
    #
    # Safe equivalent: keep the columns as a denormalized cache, but force-sync
    # them from the canonical sources (`shipping_workflow_status` + payments
    # totals) on every save. The columns then function as a write-through cache
    # rather than independent state — same goal as @property (single source of
    # truth) without the breakage. P-F-5 (full column drop) remains optional
    # and deferred to task7 per task6.md's own statement.
    _STATUS_FROM_WORKFLOW = {
        None: 'Open',
        'sw_mfg_start': 'Open',
        'sw_wait_agent_ship': 'Shipped',
        'sw_wait_intl_ship': 'Shipped',
        'sw_wait_arrival': 'Shipped',
        'sw_wait_clearance': 'Cleared',
        'sw_released': 'Closed',
    }
    _ORDER_STATUS_FROM_WORKFLOW = {
        'sw_mfg_start': 'Manufacturing',
        'sw_wait_agent_ship': 'Shipping',
        'sw_wait_intl_ship': 'Shipping',
        'sw_wait_arrival': 'Shipping',
        'sw_wait_clearance': 'Clearance',
        'sw_released': 'Delivered',
    }

    def _sync_legacy_status_fields(self):
        """Force status/order_status/payment_status to reflect canonical state.
        Called from save(); also runnable as a one-shot via the migration."""
        sw = self.shipping_workflow_status
        derived_status = self._STATUS_FROM_WORKFLOW.get(sw)
        if derived_status is not None:
            self.status = derived_status
        derived_order = self._ORDER_STATUS_FROM_WORKFLOW.get(sw)
        if derived_order is not None:
            self.order_status = derived_order
        # payment_status from remaining_amount (no payment posting required —
        # `recalculate_deal_payment_status` keeps remaining_amount fresh).
        rem = self.remaining_amount if self.remaining_amount is not None else 0
        tot = self.total_amount if self.total_amount is not None else 0
        try:
            from decimal import Decimal
            rem_d = Decimal(str(rem))
            tot_d = Decimal(str(tot))
        except Exception:
            rem_d, tot_d = 0, 0
        if tot_d <= 0:
            self.payment_status = 'Unpaid'
        elif rem_d <= 0:
            self.payment_status = 'Fully Paid'
        elif rem_d < tot_d:
            self.payment_status = 'Partially Paid'
        else:
            self.payment_status = 'Unpaid'

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

    seq = models.PositiveSmallIntegerField(null=True, blank=True, db_column='Seq', help_text='مسلسل البند')
    catalog_number = models.CharField(max_length=100, blank=True, default='', db_column='CatalogNumber', help_text='رقم الكتالوج')
    name_snapshot = models.CharField(max_length=255, blank=True, default='', db_column='NameSnapshot', help_text='لقطة اسم المنتج وقت الإدخال')
    description_line = models.CharField(max_length=500, blank=True, default='', db_column='DescriptionLine', help_text='بيان السطر قابل للتعديل')
    unit = models.CharField(max_length=50, blank=True, default='', db_column='Unit', help_text='وحدة القياس (نص حر)')
    warehouse = models.CharField(max_length=100, blank=True, default='', db_column='Warehouse', help_text='المخزن')
    extra_qty = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, db_column='ExtraQty', help_text='الكمية الإضافية')
    batch_number = models.CharField(max_length=100, blank=True, default='', db_column='BatchNumber', help_text='رقم الدفعة')
    serial_number = models.CharField(max_length=100, blank=True, default='', db_column='SerialNumber', help_text='الرقم المسلسل')
    manufacture_number = models.CharField(max_length=100, blank=True, default='', db_column='ManufactureNumber', help_text='رقم التصنيع')
    expiry_date = models.DateField(null=True, blank=True, db_column='ExpiryDate', help_text='تاريخ انتهاء الصلاحية')
    line_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True, db_column='LineCurrencyID', help_text='عملة سعر البند')
    line_exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, db_column='LineExchangeRate', help_text='سعر صرف عملة البند')
    second_date = models.DateField(null=True, blank=True, db_column='SecondDate', help_text='تاريخ ثاني للبند')
    is_taxable = models.BooleanField(default=True, db_column='IsTaxable', help_text='يخضع للضريبة')
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column='VATPercent', help_text='نسبة الضريبة على البند')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column='DiscountPercent', help_text='نسبة الخصم على البند')
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='DiscountAmount', help_text='قيمة الخصم على البند')

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
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
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

    # ── M3-T2: Aseel «إرسالية» header fields (mirror sales-invoice M2-T1) ──
    # The Aseel program treats a shipment as an "إرسالية" (incoming) with the
    # same header chrome as invoices. These are independent of the existing
    # KTRA shipment workflow — they coexist as Aseel-side metadata.
    SHIPMENT_TYPE_INVOICE = "invoice"   # إرسالية تتحوّل لفاتورة شراء
    SHIPMENT_TYPE_TRANSPORT = "transport"  # إرسالية نقل فقط (لا تتحوّل لفاتورة)
    SHIPMENT_TYPE_CHOICES = [
        (SHIPMENT_TYPE_INVOICE, "إرسالية فاتورة"),
        (SHIPMENT_TYPE_TRANSPORT, "إرسالية نقل"),
    ]
    book_number = models.PositiveIntegerField(
        default=0, db_column='BookNumber',
        help_text='رقم الدفتر. 0 = يدوي. >0 = مسلسل لكل دفتر مستقل.',
    )
    second_date = models.DateField(
        null=True, blank=True, db_column='SecondDate',
        help_text='تاريخ ثاني لحركة الإرسالية',
    )
    licensed_dealer_no = models.CharField(
        max_length=100, blank=True, default='', db_column='LicensedDealerNo',
        help_text='رقم المشتغل المرخص للمورد/المستورد',
    )
    shipment_type = models.CharField(
        max_length=20, choices=SHIPMENT_TYPE_CHOICES,
        default=SHIPMENT_TYPE_INVOICE, db_column='ShipmentType',
        help_text='نوع الإرسالية (فاتورة → قابلة للتحويل لفاتورة شراء، أو نقل فقط)',
    )
    supplier_address = models.CharField(
        max_length=500, blank=True, default='', db_column='SupplierAddress',
        help_text='عنوان المورد/المستورد (نصّي حر، لا يتعارض مع شريك)',
    )

    # P-F-2: Aseel header enrichment fields
    transaction_time = models.TimeField(null=True, blank=True, db_column='TransactionTime', help_text='ساعة الإرسالية')
    transit_journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, db_column='TransitJournalID', related_name='transit_shipments', help_text='رقم القيد الناشئ من ترحيل الإرسالية')
    editable = models.BooleanField(default=True, db_column='Editable', help_text='قابل للتعديل')
    vat_statement = models.ForeignKey('sales.VatStatement', on_delete=models.SET_NULL, null=True, blank=True, db_column='VatStatementID', related_name='shipments', help_text='كشف الضريبة')
    journal_no_display = models.CharField(max_length=50, blank=True, default='', db_column='JournalNoDisplay', help_text='رقم القيد للعرض (read-only computed)')
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='Subtotal', help_text='المجموع بدون شحن')
    vat_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='VATTotal', help_text='مجموع الضريبة')
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='GrandTotal', help_text='إجمالي الإرسالية')

    deals = models.ManyToManyField(LogisticsDeal, through='LogisticsShipmentDeal', related_name='shipments')

    class Meta:
        db_table = 'logistics_shipments'
        managed = True

    # ── State Machine: valid transitions for status ──
    # القيم تطابق STATUS_CHOICES حرفياً (In-Transit بشرطة).
    # مفروضة على مستوى save() (وليس clean() فقط) لأن DRF لا يطبّق full_clean.
    VALID_STATUS_TRANSITIONS = {
        None:         ['Pending'],
        'Pending':    ['In-Transit'],
        'In-Transit': ['Arrived'],
        'Arrived':    ['Clearing'],
        'Clearing':   ['Cleared'],
        'Cleared':    [],  # terminal
    }

    def _assert_valid_status_transition(self):
        """يرفض الانتقالات غير الصالحة لحالة الشحنة.

        مفروض على مستوى save() (لا clean() فقط) لأن DRF لا يستدعي full_clean
        تلقائياً. التقدّم البرمجي عبر .update() (bulk) يتجاوزه عمداً.
        """
        if not self.pk:
            return
        try:
            old = LogisticsShipment.objects.only('status').get(pk=self.pk)
        except LogisticsShipment.DoesNotExist:
            return
        old_st = old.status
        new_st = self.status
        if old_st != new_st:
            allowed = self.VALID_STATUS_TRANSITIONS.get(old_st, [])
            if new_st not in allowed:
                from django.core.exceptions import ValidationError as DjangoVE
                raise DjangoVE(
                    f"انتقال غير صالح للشحنة: '{old_st}' → '{new_st}'. "
                    f"المسموح: {allowed or 'لا انتقال (حالة نهائية)'}."
                )

    def clean(self):
        super().clean()
        self._assert_valid_status_transition()

    def save(self, *args, **kwargs):
        self._assert_valid_status_transition()
        if self.shipment_number and self.shipment_number not in ('', 'NEW'):
            return super().save(*args, **kwargs)
        from django.db import transaction
        # القفل يجب أن يبقى مُمسَكاً حتى بعد INSERT، لذا super().save() داخل atomic.
        with transaction.atomic():
            last = (
                LogisticsShipment.objects
                .select_for_update()
                .filter(tenant_id=self.tenant_id)
                .order_by('-id')
                .values_list('id', flat=True)
                .first()
            )
            next_id = (last or 0) + 1
            self.shipment_number = f"SH-{next_id:04d}"
            return super().save(*args, **kwargs)

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
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    shipment = models.OneToOneField(LogisticsShipment, on_delete=models.CASCADE, db_column='ShipmentID', related_name='clearance')
    book_number = models.PositiveIntegerField(
        default=0, db_column='BookNumber',
        help_text='رقم الدفتر. 0 = يدوي. >0 = مسلسل لكل دفتر مستقل.',
    )
    customs_broker = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, db_column='CustomsBrokerID', related_name='clearances_as_broker')
    declaration_number = models.CharField(max_length=100, null=True, blank=True, db_column='DeclarationNumber')
    clearance_date = models.DateField(null=True, blank=True, db_column='ClearanceDate')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Processing', db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    transaction_time = models.TimeField(null=True, blank=True, db_column='TransactionTime', help_text='ساعة التخليص')
    second_date = models.DateField(null=True, blank=True, db_column='SecondDate', help_text='تاريخ ثاني')
    licensed_dealer_no = models.CharField(max_length=100, blank=True, default='', db_column='LicensedDealerNo', help_text='رقم المشتغل المرخص للمخلّص')
    settlement_invoice_number = models.CharField(max_length=100, blank=True, default='', db_column='SettlementInvoiceNumber', help_text='رقم فاتورة المقاصة')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True, db_column='CurrencyID', help_text='عملة البيان')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, db_column='ExchangeRate', help_text='سعر الصرف')
    vat_statement = models.ForeignKey('sales.VatStatement', on_delete=models.SET_NULL, null=True, blank=True, db_column='VatStatementID', help_text='كشف الضريبة')
    subtotal_no_vat = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='SubtotalNoVAT', help_text='المجموع بدون ضريبة')
    vat_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='VATTotal', help_text='مجموع الضريبة')
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='GrandTotal', help_text='مبلغ البيان الإجمالي')
    journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, db_column='JournalID', related_name='clearances', help_text='رقم القيد المباشر')
    editable = models.BooleanField(default=True, db_column='Editable', help_text='قابل للتعديل')

    class Meta:
        db_table = 'logistics_clearance'
        managed = True

    @property
    def cost_lines(self):
        """Backwards-compat shim: legacy callsites (landed_cost, views) read
        cost_lines as a list of {label, amount}. After P-D-1..P-D-4 the data
        lives in `LogisticsClearanceLine` rows; expose the same shape here so
        existing logic keeps working unchanged. Amount = debit - credit
        (matches the old JSON where -100 meant credit)."""
        try:
            return [
                {"label": line.description, "amount": float((line.debit or 0) - (line.credit or 0))}
                for line in self.lines.all()
            ]
        except Exception:
            return []


class LogisticsClearancePayment(models.Model):
    """دفعة تخليص: قيد مباشر بين حساب المخلّص وحساب الصندوق."""

    PAYMENT_PURPOSE_CHOICES = [
        ('clearance_fee', 'رسوم تخليص'),
        ('shipping', 'شحن'),
        ('broker_fee', 'عمولة مخلص'),
        ('customs', 'رسوم جمركية'),
        ('vat', 'ضريبة'),
        ('other', 'أخرى'),
    ]

    id = models.AutoField(primary_key=True, db_column='ClearancePaymentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
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
    payment_purpose = models.CharField(
        max_length=32, choices=PAYMENT_PURPOSE_CHOICES, default='other',
        db_column='PaymentPurpose',
        help_text='الغرض من الدفعة (رسوم تخليص، شحن، عمولة مخلص، ...)',
    )
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

class LogisticsClearanceLine(models.Model):
    LINE_TYPE_CHOICES = [
        ('vat', 'ضريبة القيمة المضافة'),
        ('declaration_fee', 'رسوم البيان الجمركي'),
        ('terminal', 'محطة الشحن'),
        ('permits', 'معالجة التصاريح'),
        ('broker_commission', 'عمولة المخلص'),
        ('customs_system', 'نظام الجمارك «الجيل الجديد»'),
        ('other', 'أخرى'),
    ]

    id = models.AutoField(primary_key=True, db_column='LineID')
    clearance = models.ForeignKey(LogisticsClearance, on_delete=models.CASCADE, related_name='lines', db_column='ClearanceID')
    seq = models.PositiveSmallIntegerField(db_column='Seq', help_text='ترتيب البند')
    line_type = models.CharField(max_length=32, choices=LINE_TYPE_CHOICES, default='other', db_column='LineType')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True, db_column='AccountID', help_text='الحساب المحاسبي')
    description = models.CharField(max_length=255, db_column='Description')
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='Debit')
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='Credit')
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_column='VATPercent')
    cost_center = models.ForeignKey('accounting.CostCenter', on_delete=models.SET_NULL, null=True, blank=True, db_column='CostCenterID')

    class Meta:
        db_table = 'logistics_clearance_lines'
        managed = True
        ordering = ['seq']


class LogisticsExpense(models.Model):
    RELATED_TYPE_CHOICES = [
        ('Deal', 'Deal'),
        ('Shipment', 'Shipment'),
        ('Clearance', 'Clearance'),
    ]

    id = models.AutoField(primary_key=True, db_column='ExpenseID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    related_type = models.CharField(max_length=20, choices=RELATED_TYPE_CHOICES, db_column='RelatedType')
    related_id = models.IntegerField(db_column='RelatedID')
    
    # Financial Integration
    expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, db_column='ExpenseAccountID', related_name='logistics_expenses')
    payable_account = models.ForeignKey(Account, on_delete=models.PROTECT, db_column='PayableAccountID', related_name='logistics_payables')
    
    description = models.CharField(max_length=255, db_column='Description')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID')
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


class LocalShipment(models.Model):
    """شحن محلي (ناقل داخلي) — المرحلة بين التخليص الجمركي وفاتورة المشتريات.

    يمثّل حركة البضاعة من مخزن التخليص إلى مستودع الشركة/وجهة العميل
    عبر ناقل محلي (شاحنة، نقل داخلي).

    الربط المحاسبي:
      - على الترحيل: Dr حساب الشحن المحلي (مصروف/أصل Landed)
                    Cr حساب الناقل (AP) أو الصندوق (لو نقدي)
      - إذا اخترنا capitalize_to_inventory=True → تُرسمل التكلفة على Landed Cost
    """

    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('in_transit', 'قيد النقل'),
        ('delivered', 'تم التسليم'),
        ('cancelled', 'ملغية'),
    ]

    PAYMENT_TYPE_CHOICES = [
        ('credit', 'آجل'),
        ('cash', 'نقدي'),
    ]

    id = models.AutoField(primary_key=True, db_column='LocalShipmentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')

    shipment_number = models.CharField(
        max_length=50, db_column='ShipmentNumber', default='',
        help_text='يولَّد تلقائياً LS-XXXX',
    )

    # ربط بالتخليص الجمركي أو الشحنة الدولية (اختياري)
    clearance = models.ForeignKey(
        LogisticsClearance,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='ClearanceID',
        related_name='local_shipments',
        help_text='التخليص الجمركي المصدر — اختياري إن كانت البضاعة خارج دورة الاستيراد',
    )
    shipment = models.ForeignKey(
        LogisticsShipment,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='InternationalShipmentID',
        related_name='local_shipments',
        help_text='الشحنة الدولية المرتبطة — يُملأ من التخليص تلقائياً',
    )

    # الناقل المحلي (Partner من نوع وكيل شحن أو مورّد خدمات)
    carrier = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        db_column='CarrierID',
        related_name='local_shipments',
        help_text='الناقل المحلي (شركة النقل أو السائق)',
    )
    driver_name = models.CharField(
        max_length=150, null=True, blank=True, db_column='DriverName',
        help_text='اسم السائق (اختياري)',
    )
    vehicle_number = models.CharField(
        max_length=50, null=True, blank=True, db_column='VehicleNumber',
        help_text='رقم المركبة / الشاحنة',
    )

    origin = models.CharField(
        max_length=255, null=True, blank=True, db_column='Origin',
        help_text='نقطة الانطلاق (مخزن التخليص، الميناء، ...)',
    )
    destination = models.CharField(
        max_length=255, null=True, blank=True, db_column='Destination',
        help_text='الوجهة (المستودع، عنوان العميل)',
    )

    pickup_date = models.DateField(null=True, blank=True, db_column='PickupDate')
    delivery_date = models.DateField(null=True, blank=True, db_column='DeliveryDate')

    # المبلغ المتفق عليه
    amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column='Amount',
        help_text='قيمة الشحن المتفق عليها',
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        db_column='CurrencyID',
        related_name='local_shipments',
    )
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1, db_column='ExchangeRate',
    )

    # طريقة الدفع والحسابات المحاسبية
    payment_type = models.CharField(
        max_length=10, choices=PAYMENT_TYPE_CHOICES, default='credit',
        db_column='PaymentType',
    )
    expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True, blank=True,
        db_column='ExpenseAccountID',
        related_name='local_shipment_expenses',
        help_text='حساب مصروف الشحن (مثلاً 5301 أو 5310 شحن محلي)',
    )
    cash_or_bank_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True, blank=True,
        db_column='CashOrBankAccountID',
        related_name='local_shipment_cash_payments',
        help_text='الصندوق أو البنك (في الدفع النقدي)',
    )

    capitalize_to_inventory = models.BooleanField(
        default=True, db_column='CapitalizeToInventory',
        help_text='إن True يُضاف لتكلفة Landed Cost بدل أن يُسجَّل كمصروف فترة',
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
        db_column='Status',
    )
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    # ربط محاسبي
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='local_shipments',
    )

    # ربط بفاتورة مشتريات (عند الاستيراد منها)
    purchase_invoice = models.ForeignKey(
        'PurchaseInvoice',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='PurchaseInvoiceID',
        related_name='local_shipments',
        help_text='الفاتورة التي نُقلت تكلفتها إليها (عند الاستيراد)',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='UpdatedAt')

    class Meta:
        db_table = 'logistics_local_shipments'
        managed = True
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['carrier']),
            models.Index(fields=['clearance']),
        ]

    def save(self, *args, **kwargs):
        if self.shipment_number and self.shipment_number not in ('', 'NEW'):
            return super().save(*args, **kwargs)
        from django.db import transaction
        # M2-08: ترقيم ذرّي per-tenant — القفل مُمسَك حتى بعد INSERT.
        with transaction.atomic():
            last = (
                LocalShipment.objects
                .select_for_update()
                .filter(tenant_id=self.tenant_id)
                .order_by('-id')
                .values_list('id', flat=True)
                .first()
            )
            next_id = (last or 0) + 1
            self.shipment_number = f"LS-{next_id:04d}"
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.shipment_number} — {self.carrier.name if self.carrier_id else '—'}"


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
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
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
        Currency, on_delete=models.PROTECT,
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

    converted_from_shipment = models.ForeignKey(
        'LogisticsShipment', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='ConvertedFromShipmentID', related_name='converted_invoices',
        help_text='الشحنة التي حوّلت إلى هذه الفاتورة',
    )
    converted_at = models.DateTimeField(null=True, blank=True, db_column='ConvertedAt')
    converted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='ConvertedBy_UserID', related_name='converted_purchase_invoices',
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_column='Status')
    notes = models.TextField(null=True, blank=True, db_column='Notes')

    supplier_invoice_number = models.CharField(max_length=100, null=True, blank=True, db_column='SupplierInvoiceNumber')
    factory_name = models.CharField(max_length=255, null=True, blank=True, db_column='FactoryName')

    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='purchase_invoices',
    )

    # نوع الدفع: credit → تُقيّد على ذمم المورد (AP)، cash → تُقيّد على صندوق/بنك
    PAYMENT_TYPE_CREDIT = 'credit'
    PAYMENT_TYPE_CASH = 'cash'
    PAYMENT_TYPE_CHOICES = [
        (PAYMENT_TYPE_CREDIT, 'آجل (ذمم مورد)'),
        (PAYMENT_TYPE_CASH, 'نقدي (صندوق/بنك)'),
    ]
    payment_type = models.CharField(
        max_length=10, choices=PAYMENT_TYPE_CHOICES, default=PAYMENT_TYPE_CREDIT,
        db_column='PaymentType',
        help_text='credit: دائنة على ذمم المورد | cash: يُخصم من صندوق/بنك مباشرة',
    )
    cash_or_bank_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        null=True, blank=True,
        db_column='CashBankAccountID',
        related_name='purchase_invoices_paid_from',
        help_text='حساب الصندوق/البنك — مطلوب عند payment_type=cash',
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

    seq = models.PositiveSmallIntegerField(null=True, blank=True, db_column='Seq')
    catalog_number = models.CharField(max_length=100, blank=True, default='', db_column='CatalogNumber')
    name_snapshot = models.CharField(max_length=255, blank=True, default='', db_column='NameSnapshot')
    description_line = models.CharField(max_length=500, blank=True, default='', db_column='DescriptionLine')
    unit = models.CharField(max_length=50, blank=True, default='', db_column='Unit')
    warehouse = models.CharField(max_length=100, blank=True, default='', db_column='Warehouse')
    extra_qty = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True, db_column='ExtraQty')
    batch_number = models.CharField(max_length=100, blank=True, default='', db_column='BatchNumber')
    serial_number = models.CharField(max_length=100, blank=True, default='', db_column='SerialNumber')
    manufacture_number = models.CharField(max_length=100, blank=True, default='', db_column='ManufactureNumber')
    expiry_date = models.DateField(null=True, blank=True, db_column='ExpiryDate')
    line_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True, db_column='LineCurrencyID')
    line_exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, db_column='LineExchangeRate')
    second_date = models.DateField(null=True, blank=True, db_column='SecondDate')
    is_taxable = models.BooleanField(default=True, db_column='IsTaxable')
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column='VATPercent')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, db_column='DiscountPercent')
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, db_column='DiscountAmount')

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


class PurchaseInvoicePayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'نقدي'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cheque', 'شيك'),
        ('credit', 'آجل'),
        ('other', 'أخرى'),
    ]

    id = models.AutoField(primary_key=True, db_column='PaymentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='payments', db_column='PurchaseInvoiceID')
    payment_date = models.DateField(db_column='PaymentDate')
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column='Amount')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, db_column='CurrencyID')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1, db_column='ExchangeRate')
    payment_method = models.CharField(max_length=32, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer', db_column='PaymentMethod')
    cash_or_bank_account = models.ForeignKey(Account, on_delete=models.PROTECT, db_column='CashBankAccountID', related_name='purchase_invoice_payments')
    reference_number = models.CharField(max_length=100, blank=True, default='', db_column='ReferenceNumber')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(JournalHeader, on_delete=models.SET_NULL, null=True, blank=True, db_column='JournalID')
    notes = models.TextField(blank=True, default='', db_column='Notes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='CreatedBy_UserID')

    class Meta:
        db_table = 'purchase_invoice_payments'
        managed = True
        ordering = ['-payment_date', '-id']


class PurchaseInvoiceFee(models.Model):
    """رسوم إضافية على فاتورة الشراء (شحن، تخليص، رسوم جمركية، تأمين، ...).

    كل رسم:
    - يُسجَّل مدين في حساب المصروف (account من نوع Expense أو Asset لـ Inventory/landed).
    - يُضاف دائن (مع صافي المخزون + VAT) في حساب المورد (Trade Payables) بحيث
      يبقى القيد متوازناً.
    - اختيارياً يمكن رسملته (capitalize_to_inventory=True) ليُضاف لتكلفة المخزون
      المستوردة بدل المصروف المباشر — تُستخدم لاحقاً في Landed Cost.
    """

    id = models.AutoField(primary_key=True, db_column='FeeID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.CASCADE,
        db_column='PurchaseInvoiceID', related_name='fees',
    )
    # الحساب المحاسبي المختار (مصروف عادة: 5301 شحن، 5302 تخليص، 5303 رسوم جمركية، ...)
    expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        db_column='ExpenseAccountID', related_name='purchase_invoice_fees',
        help_text='الحساب المدين للرسم — عادةً حساب مصروف (5xxx) أو جزء من تكلفة المخزون',
    )
    description = models.CharField(
        max_length=255, db_column='Description',
        help_text='وصف الرسم (مثال: رسوم جمركية، شحن دولي، تخليص)',
    )
    amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column='Amount',
    )
    capitalize_to_inventory = models.BooleanField(
        default=False, db_column='CapitalizeToInventory',
        help_text='إذا True يُرسمل على المخزون (landed cost) بدل تسجيله كمصروف في الفترة',
    )
    is_taxable = models.BooleanField(
        default=False, db_column='IsTaxable',
        help_text='إذا True يُحتسب ضريبة VAT على هذا الرسم ضمن فاتورة الشراء',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'purchase_invoice_fees'
        managed = True

    def __str__(self):
        return f"{self.description}: {self.amount}"


# Automatically connect signals for the logistics app
import logistics.signals
