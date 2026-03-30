from django.db import models
from tenants.models import Tenant

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
    is_serialized = models.BooleanField(default=False, db_column='IsSerialized')
    is_for_sale_online = models.BooleanField(default=False, db_column='IsForSaleOnline')
    online_price = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True, db_column='OnlinePrice')
    online_description = models.TextField(blank=True, null=True, db_column='OnlineDescription')

    class Meta:
        db_table = 'products'
        managed = True
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'sku'], name='idx_tenant_sku')
        ]

    def __str__(self):
        return self.name_ar or self.name_en or self.sku

