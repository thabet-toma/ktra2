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

    quantity_on_hand = models.DecimalField(
        max_digits=18, decimal_places=4, default=0, db_column='QuantityOnHand',
    )
    avg_cost = models.DecimalField(
        max_digits=18, decimal_places=4, default=0, db_column='AvgCost',
        help_text='Weighted average cost per unit (base currency)',
    )

    class Meta:
        db_table = 'products'
        managed = True
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'sku'], name='idx_tenant_sku')
        ]

    def __str__(self):
        return self.name_ar or self.name_en or self.sku


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
    ]

    id = models.AutoField(primary_key=True, db_column='MovementID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID', default=1)
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

    class Meta:
        db_table = 'stock_movements'
        managed = True
        ordering = ['-movement_date', '-id']

    def __str__(self):
        return f"{self.get_movement_type_display()} | {self.product} | {self.quantity}"

