from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
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
    # M2-T3: cheques-receivable-undeposited (شيكات برسم التحصيل) account — used
    # when cheques are attached to invoices (Dr this account, Cr customer AR).
    default_cheques_under_collection_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultChequesUnderCollectionAccountID",
        related_name="sales_settings_cheques_uc",
        help_text="حساب شيكات برسم التحصيل (Asset). يستقبل الشيكات الواردة المرفقة بفواتير المبيعات.",
    )

    # M2-T4: dedicated source-discount (withholding) receivable account.
    # Source discount is NOT a COGS — it's an amount withheld by the customer
    # against future tax credit; sits as a receivable from the tax authority.
    default_source_discount_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="DefaultSourceDiscountAccountID",
        related_name="sales_settings_source_disc",
        help_text="حساب خصم المصدر (Asset/Receivable). يستلم مبلغ الضريبة المحجوزة من العميل عند الترحيل.",
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
    vat_input_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="VatInputAccountID",
        related_name="sales_settings_vat_input",
        help_text="حساب ضريبة المدخلات (VAT Input) المستخدم في فواتير الشراء — الربط الصريح يُغني عن البحث بالاسم",
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

    # N8-T11: unified invoice_kind — replaces separate models for each type
    INVOICE_KIND_SALE = 'sale'
    INVOICE_KIND_SALE_RETURN = 'sale_return'
    INVOICE_KIND_PURCHASE = 'purchase'
    INVOICE_KIND_PURCHASE_RETURN = 'purchase_return'
    INVOICE_KIND_CHOICES = [
        (INVOICE_KIND_SALE, 'فاتورة بيع'),
        (INVOICE_KIND_SALE_RETURN, 'مرجع بيع'),
        (INVOICE_KIND_PURCHASE, 'فاتورة شراء'),
        (INVOICE_KIND_PURCHASE_RETURN, 'مرجع شراء'),
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
    invoice_kind = models.CharField(
        max_length=20, choices=INVOICE_KIND_CHOICES,
        default=INVOICE_KIND_SALE, db_column="InvoiceKind",
        help_text='نوع الفاتورة: بيع / مرجع بيع / شراء / مرجع شراء',
    )
    original_invoice = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='OriginalInvoiceID', related_name='return_invoices',
        help_text='الفاتورة الأصلية (للمراجيع) — يربط مرجع البيع/الشراء بأصلها',
    )
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
    # M2-T3: linked financial instrument (سند مالي)
    financial_document_no = models.CharField(
        max_length=50, blank=True, default="", db_column="FinancialDocumentNo",
        help_text="رقم السند المالي المرفق بالفاتورة (إيصال قبض/صرف)",
    )
    stock_on_post = models.BooleanField(
        default=True,
        db_column="StockOnPost",
        help_text="إذا عطّل: لا يُخصم المخزون عند الترحيل بل عند تسليم أمر الإخراج",
    )

    book_number = models.PositiveIntegerField(
        default=0,
        db_column="BookNumber",
        help_text="رقم الدفتر. 0 = يدوي. >0 = مسلسل لكل دفتر مستقل.",
    )
    second_date = models.DateField(
        null=True, blank=True, db_column="SecondDate",
        help_text="تاريخ ثاني لحركة الفواتير (حقل اختياري)",
    )
    licensed_dealer_no = models.CharField(
        max_length=100, blank=True, default="", db_column="LicensedDealerNo",
        help_text="رقم المشتغل المرخص الخاص بالمورد أو العميل",
    )
    settlement_invoice_no = models.CharField(
        max_length=100, blank=True, default="", db_column="SettlementInvoiceNo",
        help_text="رقم فاتورة المقاصة",
    )
    prices_include_tax = models.BooleanField(
        default=False,
        db_column="PricesIncludeTax",
        help_text="إذا مفعّل: الأسعار المدخلة شاملة للضريبة (تجاوز إعدادات المبيعات)",
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, db_column="DiscountPercent",
        help_text="نسبة الخصم على مستوى الفاتورة (0-100)",
    )

    # M2-T3: Attached payment voucher (cash side; cheques attach via Cheque.sales_invoice FK).
    # When the operator records cash/cheques alongside the invoice, these fields
    # capture the cash portion. The integrated journal posts cash + cheques as
    # additional Dr lines, reducing the AR remainder.
    attached_cash_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        db_column="AttachedCashAmount",
        help_text="مبلغ نقدي مرفق مع الفاتورة (يُحسم من ذمم العميل ويُرحَّل ضمن نفس قيد الفاتورة)",
    )
    attached_cash_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True, blank=True,
        db_column="AttachedCashAccountID",
        related_name="sales_invoices_attached_cash",
        help_text="حساب الصندوق/البنك الذي استلم المبلغ النقدي المرفق",
    )

    # M2-T4: per-invoice OVERRIDE of source discount (نسبة/مبلغ خصم المصدر).
    # If null → falls back to customer's source_discount_percent/source_discount_amount.
    # Source discount is the withholding-tax slice the customer holds back (Aseel «خصم مصدر»);
    # it is NOT the regular discount (`discount_percent`/`invoice_discount`).
    source_discount_percent_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        db_column="SourceDiscountPercentOverride",
        help_text="نسبة خصم مصدر — تجاوز على مستوى الفاتورة (null = استخدم افتراضي العميل)",
    )
    source_discount_amount_override = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        db_column="SourceDiscountAmountOverride",
        help_text="مبلغ خصم مصدر — تجاوز على مستوى الفاتورة (null = احسب من النسبة أو افتراضي العميل)",
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

    unit = models.CharField(max_length=50, blank=True, default="", db_column="Unit")
    warehouse = models.CharField(max_length=100, blank=True, default="", db_column="Warehouse")
    catalog_no = models.CharField(max_length=100, blank=True, default="", db_column="CatalogNo")
    expiry_date = models.DateField(null=True, blank=True, db_column="ExpiryDate")
    extra_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, db_column="ExtraQuantity"
    )
    line_tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, db_column="LineTaxPercent",
        help_text="نسبة ضريبة مخصصة للسطر (تجاوز النسبة الافتراضية)",
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


class SupplierPayment(models.Model):
    """N8-T12: سند صرف للموردين — مرآة CustomerPayment لكن للموردين.

    الترحيل: Dr AP / Cr Cash (عكس CustomerPayment حيث Dr Cash / Cr AR).
    """
    id = models.AutoField(primary_key=True, db_column="SupplierPaymentID")
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column="TenantID", to_field="TenantID",
    )
    partner = models.ForeignKey(
        'partners.Partner', on_delete=models.PROTECT,
        db_column="PartnerID", related_name="supplier_payments",
    )
    payment_date = models.DateField(db_column="PaymentDate")
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column="Amount")
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, db_column="CurrencyID", to_field="CurrencyID",
    )
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1.0, db_column="ExchangeRate",
    )
    cash_or_bank_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        db_column="CashAccountID", related_name="supplier_payments_cash",
        help_text="الصندوق أو البنك (دائن)",
    )
    journal = models.ForeignKey(
        JournalHeader, on_delete=models.SET_NULL, null=True, blank=True,
        db_column="JournalID", related_name="supplier_payments",
    )
    is_posted = models.BooleanField(default=False, db_column="IsPosted")
    notes = models.TextField(null=True, blank=True, db_column="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "sales_module_supplier_payments"
        managed = True

    def __str__(self):
        return f"SupplierPayment #{self.id} — {self.partner_id} ({self.amount})"


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


class SalesQuotation(models.Model):
    """عرض أسعار للمبيعات — يحاكي دورة LogisticsDeal/Offer + نمط Odoo/Daftra."""

    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_ACCEPTED = "accepted"
    STATUS_CONVERTED = "converted"
    STATUS_EXPIRED = "expired"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "مسودة"),
        (STATUS_SENT, "أُرسل"),
        (STATUS_ACCEPTED, "مقبول"),
        (STATUS_CONVERTED, "محوّل"),
        (STATUS_EXPIRED, "منتهي الصلاحية"),
        (STATUS_REJECTED, "مرفوض"),
    ]

    id = models.AutoField(primary_key=True, db_column="SalesQuotationID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    quotation_number = models.CharField(max_length=50, db_column="QuotationNumber")
    customer = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        db_column="CustomerID",
        related_name="sales_quotations",
    )
    quotation_date = models.DateField(db_column="QuotationDate")
    valid_until = models.DateField(null=True, blank=True, db_column="ValidUntil")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_column="Status",
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        db_column="CurrencyID",
        to_field="CurrencyID",
    )
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=6, default=1.0, db_column="ExchangeRate",
    )
    subtotal = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="Subtotal",
    )
    discount_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="DiscountAmount",
    )
    tax_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="TaxAmount",
    )
    grand_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="GrandTotal",
    )
    notes = models.TextField(null=True, blank=True, db_column="Notes")
    invoice = models.ForeignKey(
        "SalesInvoice",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="InvoiceID",
        related_name="quotation_backref",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="CreatedBy_UserID",
    )

    class Meta:
        db_table = "sales_module_quotations"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "quotation_number"],
                name="uniq_sales_quotation_number_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "quotation_date"]),
            models.Index(fields=["customer"]),
        ]

    def __str__(self):
        return f"{self.quotation_number} — {self.customer_id}"

    def _assert_valid_workflow_transition(self, old, new):
        allowed = {
            self.STATUS_DRAFT: {self.STATUS_SENT, self.STATUS_EXPIRED},
            self.STATUS_SENT: {self.STATUS_ACCEPTED, self.STATUS_REJECTED, self.STATUS_EXPIRED},
            self.STATUS_ACCEPTED: {self.STATUS_CONVERTED, self.STATUS_EXPIRED},
            self.STATUS_CONVERTED: set(),
            self.STATUS_EXPIRED: set(),
            self.STATUS_REJECTED: set(),
        }
        if new not in allowed.get(old, set()):
            # DjangoValidationError → DRF returns a clean 400 (not a 500 like
            # bare ValueError would on the standard PATCH/update path).
            raise DjangoValidationError(
                f"انتقال حالة غير مسموح: {old} → {new}. الحالات المسموحة: {allowed.get(old, set())}"
            )

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old = SalesQuotation.objects.only("status").get(pk=self.pk)
                if old.status != self.status:
                    self._assert_valid_workflow_transition(old.status, self.status)
            except self.DoesNotExist:
                pass
        super().save(*args, **kwargs)


class SalesQuotationLine(models.Model):
    id = models.AutoField(primary_key=True, db_column="SalesQuotationLineID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
    )
    quotation = models.ForeignKey(
        SalesQuotation,
        on_delete=models.CASCADE,
        db_column="QuotationID",
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        db_column="ProductID",
        related_name="sales_quotation_lines",
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column="Quantity")
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, db_column="UnitPrice")
    line_discount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="LineDiscount",
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="TaxRateID",
        related_name="sales_quotation_lines",
    )
    line_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, db_column="LineTotal",
    )

    class Meta:
        db_table = "sales_module_quotation_lines"
        managed = True

    def __str__(self):
        return f"Line {self.id} quote={self.quotation_id}"


class CreditDebitNote(models.Model):
    """M4-T4 — إشعار مدين/دائن (Credit/Debit Note).

    يربط بحساب عميل وفاتورة اختيارياً، ويُنشئ قيداً محاسبياً متوازناً
    عبر `accounting.services.post_journal()` عند الترحيل.

    دلالات الإشارات (per `notices.txt` + standard accounting):
    - إشعار دائن (credit): العميل يحصل على رصيد لنا (تخفيض إيراد، خصم ذمم) →
      Dr إيرادات (نقص الإيراد)، Cr ذمم العميل (نقص الدائن).
    - إشعار مدين (debit): العميل مدين لنا بمبلغ إضافي → Dr ذمم العميل (زيادة)،
      Cr إيرادات (زيادة).

    Reference: docs/aseel_reference/notices.txt
    """

    TYPE_CREDIT = "credit"
    TYPE_DEBIT = "debit"
    TYPE_CHOICES = [(TYPE_CREDIT, "دائن"), (TYPE_DEBIT, "مدين")]

    STATUS_DRAFT = "draft"
    STATUS_POSTED = "posted"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "مسودة"),
        (STATUS_POSTED, "مرحّل"),
        (STATUS_CANCELLED, "ملغي"),
    ]

    id = models.AutoField(primary_key=True, db_column="CreditDebitNoteID")
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column="TenantID", to_field="TenantID",
    )
    note_number = models.CharField(max_length=50, db_column="NoteNumber")
    note_date = models.DateField(db_column="NoteDate")
    note_type = models.CharField(
        max_length=10, choices=TYPE_CHOICES, db_column="NoteType",
    )
    customer = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        db_column="CustomerID",
        related_name="credit_debit_notes",
    )
    related_invoice = models.ForeignKey(
        "SalesInvoice",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="RelatedInvoiceID",
        related_name="credit_debit_notes",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, db_column="Amount")
    reason = models.TextField(blank=True, default="", db_column="Reason")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_DRAFT, db_column="Status",
    )
    journal = models.ForeignKey(
        "accounting.JournalHeader",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="JournalID",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="CreatedBy_UserID",
    )

    class Meta:
        db_table = "sales_module_credit_debit_notes"
        managed = True
        unique_together = [("tenant", "note_number")]

    def __str__(self):
        return f"{self.note_number} ({self.note_type})"

