from django.db import models
from tenants.models import Tenant
from partners.models import Partner

class UnitOfMeasure(models.Model):
    id = models.AutoField(primary_key=True, db_column='UOMID')
    code = models.CharField(max_length=10, unique=True, db_column='Code')
    name_ar = models.CharField(max_length=50, db_column='Name_AR')
    name_en = models.CharField(max_length=50, db_column='Name_EN')
    is_active = models.BooleanField(default=True, db_column='IsActive')

    class Meta:
        db_table = 'units_of_measure'
        managed = True
        verbose_name_plural = 'Units of Measure'

    def __str__(self):
        return f"{self.name_ar} ({self.code})"

class ProductCategory(models.Model):
    id = models.AutoField(primary_key=True, db_column='CategoryID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    name = models.CharField(max_length=100, blank=True, null=True, db_column='Name')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children', db_column='ParentID')
    revenue_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='RevenueAccountID',
        related_name='product_categories_revenue',
    )
    cogs_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='CogsAccountID',
        related_name='product_categories_cogs',
    )
    inventory_account = models.ForeignKey(
        'accounting.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='InventoryAccountID',
        related_name='product_categories_inventory',
    )

    class Meta:
        db_table = 'product_categories'
        managed = True
        verbose_name_plural = 'Product Categories'

    def __str__(self):
        return self.name or f"Category {self.id}"

class Product(models.Model):
    id = models.AutoField(primary_key=True, db_column='ProductID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    sku = models.CharField(max_length=50, db_column='SKU')
    barcode = models.CharField(max_length=50, blank=True, null=True, db_column='Barcode')
    name_ar = models.CharField(max_length=200, blank=True, null=True, db_column='Name_AR')
    name_en = models.CharField(max_length=200, blank=True, null=True, db_column='Name_EN')
    # تجميع البراندات تحت «صنف فرعي» (المقاس/الموديل مثل 185/65/14): المنتجات بنفس
    # variant_group تظهر تحت عقدة أب واحدة في الشجرة/الجرد/الجدول، والبراند يميّز
    # الورقة (يظهر بين قوسين). إن تُرك variant_group فارغاً يُشتقّ group_key خادمياً
    # من الاسم (مقاس الإطار أو الاسم) — توافقاً مع البيانات القديمة.
    variant_group = models.CharField(max_length=120, blank=True, default='', db_column='VariantGroup')
    brand = models.CharField(max_length=100, blank=True, default='', db_column='Brand')
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, db_column='CategoryID', related_name='products')
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.SET_NULL, null=True, blank=True, db_column='UOMID', related_name='products')
    uom_legacy = models.CharField(max_length=20, blank=True, null=True, db_column='UOM') 
    weight_kg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True, db_column='Weight_KG')
    volume_cbm = models.DecimalField(max_digits=12, decimal_places=6, blank=True, null=True, db_column='Volume_CBM')
    hs_code = models.CharField(max_length=20, blank=True, null=True, db_column='HS_Code')
    min_stock_level = models.IntegerField(blank=True, null=True, db_column='MinStockLevel')
    allow_negative_stock = models.BooleanField(
        default=False,
        db_column='AllowNegativeStock',
        help_text='إن عُطّل، يُرفض الصرف إذا تجاوزت الكمية المتاحة (الافتراضي: مرفوض)',
    )
    is_serialized = models.BooleanField(default=False, db_column='IsSerialized')
    is_service = models.BooleanField(
        default=False,
        db_column='IsService',
        help_text='إذا مفعّل: يُعامل الصنف كخدمة — لا يُخصم من المخزون ويُرحّل لحساب مبيعات الخدمات',
    )
    is_for_sale_online = models.BooleanField(default=False, db_column='IsForSaleOnline')
    online_price = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True, db_column='OnlinePrice')
    online_description = models.TextField(blank=True, null=True, db_column='OnlineDescription')

    # task14 M2 (DEF-A5): فلتر الفترة + ترتيب «الأحدث أولاً» — القديم يأخذ تاريخ الترحيل
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    quantity_on_hand = models.DecimalField(
        max_digits=18, decimal_places=4, default=0, db_column='QuantityOnHand',
    )
    avg_cost = models.DecimalField(
        max_digits=18, decimal_places=4, default=0, db_column='AvgCost',
        help_text='Weighted average cost per unit (base currency)',
    )
    # كرت الصنف: «سعر البيع» بجانب «سعر التكلفة» — سعر البيع الافتراضي المعتمد
    # للصنف (بالعملة الأساسية). فارغ = لا سعر محفوظ، فتُظهر البطاقة آخر سعر بيع
    # فعلي بدلاً منه. لا أثر محاسبي — مرجع تسعير يقترحه المستند.
    sale_price = models.DecimalField(
        max_digits=18, decimal_places=4, blank=True, null=True, db_column='SalePrice',
        help_text='سعر البيع الافتراضي للوحدة (العملة الأساسية) — فارغ يعني الرجوع لآخر سعر بيع',
    )
    # ── N8-T10: Account overrides (6 FKs) ──────────────────────
    sale_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='SaleAccountOverrideID', related_name='products_sale_override',
        help_text='حساب البيع البديل — يتجاوز حساب البيع في ثوابت المجموعة',
    )
    sale_return_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='SaleReturnAccountOverrideID', related_name='products_sale_return_override',
        help_text='حساب مرجع البيع البديل',
    )
    purchase_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='PurchaseAccountOverrideID', related_name='products_purchase_override',
        help_text='حساب الشراء البديل',
    )
    purchase_return_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='PurchaseReturnAccountOverrideID', related_name='products_purchase_return_override',
        help_text='حساب مرجع الشراء البديل',
    )
    supplier_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='SupplierAccountOverrideID', related_name='products_supplier_override',
        help_text='حساب المورد البديل',
    )
    ending_inventory_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='EndingInventoryAccountOverrideID', related_name='products_ending_inventory_override',
        help_text='حساب بضاعة آخر المدة البديل',
    )

    class Meta:
        db_table = 'products'
        managed = True
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'sku'], name='idx_tenant_sku')
        ]

    def __str__(self):
        return self.name_ar or self.name_en or self.sku


class Warehouse(models.Model):
    """مستودع مستقل لكل شركة — وجهة استلام البضاعة وبُعد على حركات المخزون.

    منفصل عن «الفرع» (tenants.Branch): الفرع وحدة محاسبية مستقلة، بينما المستودع
    موقع تخزين فعلي يمكن أن يتعدد داخل الفرع الواحد. حركة المخزون تحمل البُعدين معاً.
    """
    id = models.AutoField(primary_key=True, db_column='WarehouseID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID', related_name='warehouses')
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='BranchID', related_name='warehouses',
        help_text='الفرع الذي يتبع له المستودع (اختياري)')
    name = models.CharField(max_length=150, db_column='Name')
    code = models.CharField(max_length=30, blank=True, default='', db_column='Code')
    location = models.CharField(max_length=255, blank=True, default='', db_column='Location')
    is_default = models.BooleanField(default=False, db_column='IsDefault')
    is_active = models.BooleanField(default=True, db_column='IsActive')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'warehouses'
        managed = True
        ordering = ['-is_default', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                condition=~models.Q(code=''),
                name='idx_tenant_warehouse_code',
            ),
        ]

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('IN', 'استلام بضاعة'),
        ('OUT', 'صرف / بيع'),
        ('ADJUST_IN', 'تسوية إضافة'),
        ('ADJUST_OUT', 'تسوية نقص'),
        ('RETURN_IN', 'مرتجع داخل'),
        ('RETURN_OUT', 'مرتجع خارج'),
    ]

    REFERENCE_TYPES = [
        ('SHIPMENT', 'شحنة'),
        ('DEAL', 'صفقة'),
        ('CLEARANCE', 'تخليص جمركي'),
        ('MANUAL', 'يدوي'),
        ('SALE', 'بيع'),
        ('STOCK_ISSUE', 'إذن صرف'),
        ('PURCHASE_INVOICE', 'فاتورة شراء'),
        ('WAREHOUSE_TRANSFER', 'تحويل مستودعي'),
        ('STOCKTAKE', 'جرد'),
        # مستندا الاستلام/التسليم المستقلان (بلا فاتورة مرتبطة بعد).
        ('GOODS_RECEIPT', 'سند استلام'),
        ('DELIVERY_NOTE', 'سند تسليم'),
    ]

    id = models.AutoField(primary_key=True, db_column='MovementID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
    # task11 M4: مخزون مستقل لكل فرع — NULL = حركة على مستوى الشركة/الفرع الرئيسي
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.PROTECT, null=True, blank=True,
        db_column='BranchID', related_name='stock_movements')
    # وجهة/مصدر البضاعة الفعلي — NULL = حركة قديمة قبل تفعيل المستودعات
    warehouse = models.ForeignKey(
        'Warehouse', on_delete=models.PROTECT, null=True, blank=True,
        db_column='WarehouseID', related_name='stock_movements',
        help_text='المستودع الذي وصلت إليه/خرجت منه البضاعة')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='ProductID', related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, db_column='MovementType')
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column='Quantity')
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='UnitCost')
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0, db_column='TotalCost')
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPES, default='MANUAL', db_column='ReferenceType')
    reference_id = models.IntegerField(null=True, blank=True, db_column='ReferenceID')
    partner = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, blank=True, db_column='PartnerID')
    movement_date = models.DateField(db_column='MovementDate')
    notes = models.CharField(max_length=500, null=True, blank=True, db_column='Notes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    quantity_before = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='QuantityBefore')
    quantity_after = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='QuantityAfter')
    avg_cost_before = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='AvgCostBefore')
    avg_cost_after = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='AvgCostAfter')

    # تقسيم المخزن: مصدر البضاعة محلي (فاتورة شراء عادية) أو دولي (مسار الاستيراد).
    IMPORT_REFERENCE_TYPES = ('SHIPMENT', 'DEAL', 'CLEARANCE')
    LOCAL_REFERENCE_TYPES = ('PURCHASE_INVOICE', 'GOODS_RECEIPT')

    class Meta:
        db_table = 'stock_movements'
        managed = True
        ordering = ['-movement_date', '-id']

    def __str__(self):
        return f"{self.get_movement_type_display()} | {self.product} | {self.quantity}"

    @property
    def origin(self) -> str:
        """مصدر الحركة: international (استيراد) / local (شراء محلي) / other."""
        if self.reference_type in self.IMPORT_REFERENCE_TYPES:
            return 'international'
        if self.reference_type in self.LOCAL_REFERENCE_TYPES:
            return 'local'
        return 'other'


class ProductPriceTier(models.Model):
    """N8-T9: 5 أسعار بيع + 5 أسعار شراء لكل صنف."""
    TIER_TYPE_SALE = 'sale'
    TIER_TYPE_PURCHASE = 'purchase'
    TIER_TYPE_CHOICES = [
        (TIER_TYPE_SALE, 'بيع'),
        (TIER_TYPE_PURCHASE, 'شراء'),
    ]

    id = models.AutoField(primary_key=True, db_column='PriceTierID')
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='ProductID',
        related_name='price_tiers',
    )
    tier_type = models.CharField(
        max_length=10, choices=TIER_TYPE_CHOICES, db_column='TierType',
    )
    tier_number = models.PositiveSmallIntegerField(db_column='TierNumber')
    price = models.DecimalField(max_digits=18, decimal_places=4, db_column='Price')
    currency = models.ForeignKey(
        'tenants.Currency', on_delete=models.PROTECT, db_column='CurrencyID',
    )
    tax_inclusive = models.BooleanField(default=False, db_column='TaxInclusive')

    class Meta:
        db_table = 'product_price_tiers'
        managed = True
        unique_together = [['product', 'tier_type', 'tier_number']]

    def __str__(self):
        return f"{self.product} — {self.tier_type} #{self.tier_number}: {self.price}"



# ════════════════════════════════════════════════════════════════════
# Phase 7 (T-I1/T-I2): مستندات المخزون — تحويل بين المستودعات + جرد
# ════════════════════════════════════════════════════════════════════


class WarehouseTransfer(models.Model):
    """T-I1: مستند تحويل بضاعة بين مستودعين.

    الترحيل = حركتا مخزون (صرف من المصدر + استلام في الوجهة) بالتكلفة المتوسطة،
    فلا يتغيّر إجمالي المخزون أو متوسط التكلفة على مستوى الشركة — تنتقل البضاعة
    بين المستودعين فقط. لا قيد محاسبي (لا أثر على قيمة المخزون).
    """
    id = models.AutoField(primary_key=True, db_column='TransferID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', related_name='warehouse_transfers')
    transfer_number = models.CharField(max_length=30, blank=True, default='', db_column='TransferNumber')
    transfer_date = models.DateField(db_column='TransferDate')
    source_warehouse = models.ForeignKey(
        'Warehouse', on_delete=models.PROTECT, db_column='SourceWarehouseID',
        related_name='transfers_out')
    dest_warehouse = models.ForeignKey(
        'Warehouse', on_delete=models.PROTECT, db_column='DestWarehouseID',
        related_name='transfers_in')
    notes = models.CharField(max_length=500, blank=True, default='', db_column='Notes')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'warehouse_transfers'
        managed = True
        ordering = ['-transfer_date', '-id']

    def __str__(self):
        return f"تحويل {self.transfer_number or self.id}: {self.source_warehouse} → {self.dest_warehouse}"


class WarehouseTransferLine(models.Model):
    id = models.AutoField(primary_key=True, db_column='TransferLineID')
    transfer = models.ForeignKey(WarehouseTransfer, on_delete=models.CASCADE, db_column='TransferID', related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='ProductID')
    quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column='Quantity')

    class Meta:
        db_table = 'warehouse_transfer_lines'
        managed = True

    def __str__(self):
        return f"{self.product} × {self.quantity}"


class Stocktake(models.Model):
    """T-I2: مستند جرد فعلي. الترحيل يسوّي رصيد كل صنف ليطابق الكمية المعدودة
    (حركات ADJUST_IN/ADJUST_OUT) ويُنشئ قيد فرق الجرد (المخزون مقابل تكلفة
    البضاعة المباعة — المعالجة المعتادة لفرو قات الجرد)."""
    id = models.AutoField(primary_key=True, db_column='StocktakeID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', related_name='stocktakes')
    stocktake_number = models.CharField(max_length=30, blank=True, default='', db_column='StocktakeNumber')
    stocktake_date = models.DateField(db_column='StocktakeDate')
    warehouse = models.ForeignKey(
        'Warehouse', on_delete=models.PROTECT, null=True, blank=True,
        db_column='WarehouseID', related_name='stocktakes',
        help_text='المستودع المجرود (وسم على الحركات) — الرصيد على مستوى الشركة')
    notes = models.CharField(max_length=500, blank=True, default='', db_column='Notes')
    is_posted = models.BooleanField(default=False, db_column='IsPosted')
    journal = models.ForeignKey(
        'accounting.JournalHeader', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='JournalID', related_name='stocktakes')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'stocktakes'
        managed = True
        ordering = ['-stocktake_date', '-id']

    def __str__(self):
        return f"جرد {self.stocktake_number or self.id}"


class StocktakeLine(models.Model):
    id = models.AutoField(primary_key=True, db_column='StocktakeLineID')
    stocktake = models.ForeignKey(Stocktake, on_delete=models.CASCADE, db_column='StocktakeID', related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, db_column='ProductID')
    counted_quantity = models.DecimalField(max_digits=18, decimal_places=4, db_column='CountedQuantity')
    # لقطة رصيد النظام لحظة الترحيل (للتدقيق) + الفرق المُرحَّل.
    system_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='SystemQuantity')
    variance = models.DecimalField(max_digits=18, decimal_places=4, default=0, db_column='Variance')

    class Meta:
        db_table = 'stocktake_lines'
        managed = True

    def __str__(self):
        return f"{self.product}: عُدّ {self.counted_quantity}"
