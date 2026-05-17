from django.conf import settings
from django.db import models

from accounting.models import Account, JournalHeader, TaxRate
from inventory.models import Product
from partners.models import Partner
from tenants.models import Currency, Tenant


class SalesSettings(models.Model):
    """إعدادات مركزية لفواتير المبيعات لكل شركة (Tenant).

    تُقلّل الإدخال اليدوي في الفواتير عبر تعريف قيم افتراضية قابلة للتعديل.
    """

    PAYMENT_CASH = "cash"
    PAYMENT_CREDIT = "credit"
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, "نقدي"),
        (PAYMENT_CREDIT, "آجل"),
    ]

    id = models.AutoField(primary_key=True, db_column="SalesSettingsID")
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
        related_name="sales_settings",
    )

    default_customer = models.ForeignKey(
        Partner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultCustomerID",
        related_name="default_for_sales_settings",
        help_text="العميل الافتراضي للفواتير (الزبون العام)",
    )
    default_currency = models.ForeignKey(
        Currency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultCurrencyID",
        to_field="CurrencyID",
        related_name="default_sales_settings",
    )

    default_revenue_account_product = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultRevenueAccountProductID",
        related_name="sales_settings_rev_product",
        help_text="حساب إيراد افتراضي لبيع البضائع (المنتجات)",
    )
    default_revenue_account_service = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultRevenueAccountServiceID",
        related_name="sales_settings_rev_service",
        help_text="حساب إيراد افتراضي للخدمات",
    )
    default_cash_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultCashAccountID",
        related_name="sales_settings_cash",
        help_text="حساب الصندوق الافتراضي للفواتير النقدية",
    )
    default_inventory_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultInventoryAccountID",
        related_name="sales_settings_inventory",
        help_text="حساب مخزون افتراضي (إن لم تُحدَّد فئة المنتج حساب مخزون)",
    )
    default_cogs_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultCogsAccountID",
        related_name="sales_settings_cogs",
        help_text="حساب تكلفة مبيعات افتراضي",
    )
    default_ar_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultArAccountID",
        related_name="sales_settings_ar",
        help_text="حساب ذمم افتراضي للعملاء الآجلين",
    )

    default_payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_CREDIT,
        db_column="DefaultPaymentType",
    )
    stock_on_post_default = models.BooleanField(
        default=True,
        db_column="StockOnPostDefault",
        help_text="خصم المخزون الافتراضي عند الترحيل",
    )

    default_vat_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultVatRateID",
        related_name="sales_settings_vat",
        help_text="نسبة ضريبة القيمة المضافة الافتراضية",
    )
    prices_include_tax = models.BooleanField(
        default=False,
        db_column="PricesIncludeTax",
        help_text="إذا كان مفعّلاً، تُعامل الأسعار المدخلة كشاملة للضريبة",
    )

    auto_post_invoices = models.BooleanField(
        default=False,
        db_column="AutoPostInvoices",
        help_text="ترحيل تلقائي للفواتير بعد الحفظ",
    )
    show_journal_preview = models.BooleanField(
        default=True,
        db_column="ShowJournalPreview",
        help_text="إظهار معاينة القيد المحاسبي قبل الترحيل",
    )

    default_shipping_origin = models.CharField(
        max_length=200, blank=True, default="", db_column="DefaultShippingOrigin"
    )
    default_shipping_destination = models.CharField(
        max_length=200, blank=True, default="", db_column="DefaultShippingDestination"
    )

    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")

    class Meta:
        db_table = "sales_module_settings"
        managed = True

    def __str__(self):
        return f"SalesSettings(tenant={self.tenant_id})"


class SalesInvoice(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_POSTED = "posted"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "مسودة"),
        (STATUS_POSTED, "مرحّلة"),
        (STATUS_CANCELLED, "ملغاة"),
    ]

    INVOICE_CASH = "cash"
    INVOICE_CREDIT = "credit"
    INVOICE_TYPE_CHOICES = [
        (INVOICE_CASH, "نقدي"),
        (INVOICE_CREDIT, "آجل"),
    ]

    id = models.AutoField(primary_key=True, db_column="SalesInvoiceID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    invoice_number = models.CharField(max_length=50, db_column="InvoiceNumber")
    customer = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        db_column="CustomerID",
        related_name="sales_invoices",
    )
    invoice_date = models.DateField(db_column="InvoiceDate")
    due_date = models.DateField(null=True, blank=True, db_column="DueDate")
    invoice_type = models.CharField(
        max_length=20,
        choices=INVOICE_TYPE_CHOICES,
        default=INVOICE_CREDIT,
        db_column="InvoiceType",
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        db_column="CurrencyID",
        to_field="CurrencyID",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=1.0,
        db_column="ExchangeRate",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_column="Status",
    )

    subtotal_excl_tax = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="SubtotalExclTax"
    )
    invoice_discount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="InvoiceDiscount"
    )
    tax_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="TaxAmount"
    )
    grand_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="GrandTotal"
    )
    amount_paid = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="AmountPaid"
    )

    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="RevenueAccountID",
        related_name="sales_invoices_revenue",
    )
    cash_or_bank_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="CashOrBankAccountID",
        related_name="sales_invoices_cash",
        help_text="حساب الصندوق أو البنك لفواتير النقدي",
    )
    accounts_receivable_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="AccountsReceivableAccountID",
        related_name="sales_invoices_ar",
    )

    journal = models.ForeignKey(
        JournalHeader,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="JournalID",
        related_name="sales_invoices",
    )
    stock_on_post = models.BooleanField(
        default=True,
        db_column="StockOnPost",
        help_text="إذا عطّل: لا يُخصم المخزون عند الترحيل بل عند تسليم أمر الإخراج",
    )

    notes = models.TextField(null=True, blank=True, db_column="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="CreatedBy_UserID",
    )

    class Meta:
        db_table = "sales_module_invoices"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "invoice_number"],
                name="uniq_sales_invoice_number_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "invoice_date"]),
            models.Index(fields=["customer"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} — {self.customer_id}"


class SalesInvoiceLine(models.Model):
    id = models.AutoField(primary_key=True, db_column="SalesInvoiceLineID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.CASCADE,
        db_column="InvoiceID",
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        db_column="ProductID",
        related_name="sales_invoice_lines",
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column="Quantity")
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, db_column="UnitPrice")
    line_discount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="LineDiscount"
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="TaxRateID",
        related_name="sales_invoice_lines",
    )
    line_total_excl_tax = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="LineTotalExclTax"
    )
    line_tax_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="LineTaxAmount"
    )

    class Meta:
        db_table = "sales_module_invoice_lines"
        managed = True

    def __str__(self):
        return f"Line {self.id} inv={self.invoice_id}"


class DeliveryOrder(models.Model):
    STATUS_PENDING = "pending"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "قيد التنفيذ"),
        (STATUS_DELIVERED, "تم التسليم"),
        (STATUS_CANCELLED, "ملغي"),
    ]

    id = models.AutoField(primary_key=True, db_column="DeliveryOrderID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.CASCADE,
        db_column="InvoiceID",
        related_name="delivery_orders",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_column="Status"
    )
    notes = models.CharField(max_length=500, blank=True, default="", db_column="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    delivered_at = models.DateTimeField(null=True, blank=True, db_column="DeliveredAt")

    class Meta:
        db_table = "sales_module_delivery_orders"
        managed = True


class CustomerPayment(models.Model):
    id = models.AutoField(primary_key=True, db_column="CustomerPaymentID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    partner = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        db_column="PartnerID",
        related_name="customer_payments",
    )
    payment_date = models.DateField(db_column="PaymentDate")
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column="Amount")
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        db_column="CurrencyID",
        to_field="CurrencyID",
    )
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1.0, db_column="ExchangeRate"
    )
    cash_or_bank_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        db_column="DebitAccountID",
        related_name="customer_payments_debit",
        help_text="الصندوق أو البنك (مدين)",
    )
    journal = models.ForeignKey(
        JournalHeader,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="JournalID",
        related_name="customer_payments",
    )
    is_posted = models.BooleanField(default=False, db_column="IsPosted")
    notes = models.CharField(max_length=500, blank=True, default="", db_column="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "sales_module_customer_payments"
        managed = True


class PaymentAllocation(models.Model):
    id = models.AutoField(primary_key=True, db_column="PaymentAllocationID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    payment = models.ForeignKey(
        CustomerPayment,
        on_delete=models.CASCADE,
        db_column="PaymentID",
        related_name="allocations",
    )
    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.CASCADE,
        db_column="InvoiceID",
        related_name="payment_allocations",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column="Amount")
    amount_in_invoice_currency = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        db_column="AmountInInvoiceCurrency",
        help_text="المبلغ محوّلاً لعملة الفاتورة. إذا كانت عملة الدفعة = عملة الفاتورة يساوي amount.",
    )
    conversion_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        db_column="ConversionRate",
        help_text="سعر الصرف المستخدم لتحويل مبلغ الدفعة لعملة الفاتورة",
    )

    class Meta:
        db_table = "sales_module_payment_allocations"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "invoice"],
                name="uniq_payment_invoice_allocation",
            ),
        ]

