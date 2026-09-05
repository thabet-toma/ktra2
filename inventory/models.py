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

class ProductFamily(models.Model):
    """«المنتج» — الأب فوق البراند (#17/#20، الشكل أ: `Product` الحالي صار البراند).

    **يُمنع من حمل أي رقم**: لا رصيد، ولا تكلفة، ولا مفتاح أجنبي من حركةٍ أو
    بند مستند. كل مجموعٍ على مستوى المنتج (الرصيد الكلي، التكلفة المرجَّحة…)
    يُشتقّ عند القراءة من برانداته (`Product.family`) — تخزينُ رقمٍ هنا هو
    بالضبط العطب الذي بُني هذا النموذج ليمنعه.

    الحقول هنا هي التي حسمها #9 «على المنتج»: الاسم، التصنيف، الوحدة، حدّا
    التجديد، طبيعة الصنف، والحسابات الستّة. فيزيائياً **نفس هذه الأعمدة تبقى
    موجودة أيضاً على صفّ البراند** (`Product`) — قاعدة التعايش الانتقالية تقرأ
    منها إن لم يكن للبراند أبٌ بعد؛ راجع `inventory.services.resolve_family_field`.
    """
    id = models.AutoField(primary_key=True, db_column='ProductFamilyID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='product_families',
    )
    name_ar = models.CharField(max_length=200, blank=True, null=True, db_column='Name_AR')
    name_en = models.CharField(max_length=200, blank=True, null=True, db_column='Name_EN')
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CategoryID', related_name='product_families',
    )
    uom = models.ForeignKey(
        UnitOfMeasure, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='UOMID', related_name='product_families',
    )
    min_stock_level = models.IntegerField(blank=True, null=True, db_column='MinStockLevel')
    max_stock_level = models.IntegerField(blank=True, null=True, db_column='MaxStockLevel')
    is_serialized = models.BooleanField(default=False, db_column='IsSerialized')
    is_service = models.BooleanField(default=False, db_column='IsService')
    allow_negative_stock = models.BooleanField(default=False, db_column='AllowNegativeStock')
    sale_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='SaleAccountOverrideID', related_name='product_families_sale_override',
    )
    sale_return_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='SaleReturnAccountOverrideID', related_name='product_families_sale_return_override',
    )
    purchase_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='PurchaseAccountOverrideID', related_name='product_families_purchase_override',
    )
    purchase_return_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='PurchaseReturnAccountOverrideID', related_name='product_families_purchase_return_override',
    )
    supplier_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='SupplierAccountOverrideID', related_name='product_families_supplier_override',
    )
    ending_inventory_account_override = models.ForeignKey(
        'accounting.Account', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='EndingInventoryAccountOverrideID', related_name='product_families_ending_inventory_override',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'product_families'
        managed = True
        verbose_name_plural = 'Product Families'

    def __str__(self):
        return self.name_ar or self.name_en or f"Family {self.id}"


class Product(models.Model):
    id = models.AutoField(primary_key=True, db_column='ProductID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    sku = models.CharField(max_length=50, db_column='SKU')
    barcode = models.CharField(max_length=50, blank=True, null=True, db_column='Barcode')
    name_ar = models.CharField(max_length=200, blank=True, null=True, db_column='Name_AR')
    name_en = models.CharField(max_length=200, blank=True, null=True, db_column='Name_EN')
    # تجميع البراندات تحت «منتج فرعي» (المقاس/الموديل مثل 185/65/14): المنتجات بنفس
    # variant_group تظهر تحت عقدة أب واحدة في الشجرة/الجرد/الجدول، والبراند يميّز
    # الورقة (يظهر بين قوسين). إن تُرك variant_group فارغاً يُشتقّ group_key خادمياً
    # من الاسم (مقاس الإطار أو الاسم) — توافقاً مع البيانات القديمة.
    variant_group = models.CharField(max_length=120, blank=True, default='', db_column='VariantGroup')
    brand = models.CharField(max_length=100, blank=True, default='', db_column='Brand')
    # #20: «المنتج» فوق «البراند» (الشكل أ) — قابلٌ للفراغ عمداً: الانتقال متدرّج
    # بلا يوم توقّف، وصفوف ما قبل هذه الهجرة تبقى بلا أبٍ (قاعدة التعايش تقرأ
    # حينها من صفّ البراند نفسه). لا تُجعل NOT NULL ولا تُبنَ عليها فرادةٌ شرطية.
    family = models.ForeignKey(
        'ProductFamily', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='ProductFamilyID', related_name='brands',
    )
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, db_column='CategoryID', related_name='products')
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.SET_NULL, null=True, blank=True, db_column='UOMID', related_name='products')
    uom_legacy = models.CharField(max_length=20, blank=True, null=True, db_column='UOM')
    # T-ITEMS M5: وحدتان إضافيتان بمعامل تحويلٍ إلى الوحدة الرئيسية (كرتونة = 12
    # قطعة). كانت الحقول الخمسة معروضةً في كرت المنتج ولا تُحفظ إطلاقاً — لا
    # وجود لها في النموذج ولا في العقد؛ يكتبها المستخدم ويقرأ «تم الحفظ».
    # الوحدات المتعدّدة قياسيّةٌ في Odoo وZoho والأصيل، فوُصلت بدل أن تُحذف.
    uom2 = models.ForeignKey(
        UnitOfMeasure, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='UOM2ID', related_name='products_as_uom2',
    )
    uom2_factor = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True, db_column='UOM2Factor',
        help_text='كم وحدةً رئيسية في الوحدة الثانية (كرتونة = 12 قطعة ⇒ 12)',
    )
    uom3 = models.ForeignKey(
        UnitOfMeasure, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='UOM3ID', related_name='products_as_uom3',
    )
    uom3_factor = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True, db_column='UOM3Factor',
        help_text='كم وحدةً رئيسية في الوحدة الثالثة',
    )
    # T-ITEMS M5: وصفٌ داخلي للمنتج — منفصلٌ عن `online_description` الذي يخصّ
    # المتجر ويراه العالم. Odoo وZoho يفصلان بينهما للسبب نفسه.
    description = models.TextField(blank=True, null=True, db_column='Description')
    # T-ITEMS M5: موقع التخزين (الرفّ/الممر) — نصّ حرّ لا كيان: لا حركة مخزون
    # عليه ولا رصيد، وهو ما تفعله دفترة وQuickBooks (bin) على كرت المنتج.
    storage_location = models.CharField(
        max_length=100, blank=True, null=True, db_column='StorageLocation',
        help_text='موقع المنتج في المستودع (رفّ/ممر) — نصّ إرشادي بلا أثر مخزني',
    )
    weight_kg = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True, db_column='Weight_KG')
    volume_cbm = models.DecimalField(max_digits=12, decimal_places=6, blank=True, null=True, db_column='Volume_CBM')
    hs_code = models.CharField(max_length=20, blank=True, null=True, db_column='HS_Code')
    # T-REORDER: الحدّان هما ثنائي إعادة الطلب (نمط min/max): الأدنى **هو** نقطة
    # الطلب — بلوغه يعني «اطلب»، والأقصى هو المستوى الذي يُطلَب حتى بلوغه. لا
    # ثالثَ بينهما عمداً: «حدّ إعادة طلب» منفصلٌ عن الأدنى يخلق سؤال «أيّهما
    # يحكم؟» بلا أن يضيف قراراً. فارغٌ = بلا حدّ يدوي، ويحلّ محلّه الحدّ المقترَح
    # المحسوب من المبيعات (`inventory/replenishment.py`).
    min_stock_level = models.IntegerField(blank=True, null=True, db_column='MinStockLevel')
    max_stock_level = models.IntegerField(blank=True, null=True, db_column='MaxStockLevel')
    # #33: مفتاح لكل صنف — أيّ مسارٍ يحكم اقتراح التجديد. `manual` (الافتراضي
    # على الكتالوج كلّه بالهجرة) هو المسار الحالي حرفياً؛ `auto` يقرأ
    # `ProductDemandForecast` (هولت) بدل معدّل الصرف/الذروة. حقلٌ على المنتج
    # لا إعدادٌ للشركة — المالك يريد التحويل صنفاً صنفاً على راحته
    # (`core/replenishment.py` — القرار ط6 في خريطة #31).
    REORDER_MODE_MANUAL = 'manual'
    REORDER_MODE_AUTO = 'auto'
    REORDER_MODE_CHOICES = [
        (REORDER_MODE_MANUAL, 'يدوي'),
        (REORDER_MODE_AUTO, 'تلقائي'),
    ]
    reorder_mode = models.CharField(
        max_length=10, choices=REORDER_MODE_CHOICES, default=REORDER_MODE_MANUAL,
        db_column='ReorderMode',
    )
    allow_negative_stock = models.BooleanField(
        default=False,
        db_column='AllowNegativeStock',
        help_text='إن عُطّل، يُرفض الصرف إذا تجاوزت الكمية المتاحة (الافتراضي: مرفوض)',
    )
    is_serialized = models.BooleanField(default=False, db_column='IsSerialized')
    # THA-24: سياسة الكفالة على المنتج — لا حالة. النسخة الفعلية لكل وحدة مباعة
    # تعيش في `after_sales.WarrantyCard`، وتغيير السياسة لا يمسّ بطاقة صُرفت.
    # فارغ أو صفر = لا كفالة، فلا تُنشأ بطاقة تلقائية عند ترحيل البيع.
    warranty_months = models.PositiveSmallIntegerField(
        null=True, blank=True, db_column='WarrantyMonths',
        help_text='مدة كفالة الزبون بالأشهر (فارغ = بلا كفالة)',
    )
    supplier_warranty_months = models.PositiveSmallIntegerField(
        null=True, blank=True, db_column='SupplierWarrantyMonths',
        help_text='مدة كفالة المورد لنا بالأشهر — تُحسب من تاريخ فاتورة الشراء',
    )
    is_service = models.BooleanField(
        default=False,
        db_column='IsService',
        help_text='إذا مفعّل: يُعامل المنتج كخدمة — لا يُخصم من المخزون ويُرحّل لحساب مبيعات الخدمات',
    )
    is_for_sale_online = models.BooleanField(default=False, db_column='IsForSaleOnline')
    is_store_only = models.BooleanField(
        default=False,
        db_column='IsStoreOnly',
        help_text='منتج خاص بالمتجر الإلكتروني فقط — لا يظهر في شاشة المنتجات المخزنية أو محددات فواتير البيع',
    )
    allow_preorder = models.BooleanField(
        default=False,
        db_column='AllowPreorder',
        help_text='إتاحة بيع المنتج كطلب مسبق / عند الطلب حتى لو كان الرصيد صفراً',
    )
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
    # كرت المنتج: «سعر البيع» بجانب «سعر التكلفة» — سعر البيع الافتراضي المعتمد
    # للمنتج (بالعملة الأساسية). فارغ = لا سعر محفوظ، فتُظهر البطاقة آخر سعر بيع
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


class ProductMerge(models.Model):
    """سجلّ ضمٍّ قابل للتراجع (#24) — «سلّة محذوفات» على نمط `accounting.VoidedJournal`.

    الضمّ لا ينقل رصيداً ولا تكلفة ولا يُنشئ حركة مخزون أو قيداً: هو إعادة
    ربط `Product.family` فقط (+تطبيع الاسم، +البراند إن مرَّره المستخدم).
    `snapshot` يحفظ الحالة **قبل** الضمّ لكل براند مُضموم (family_id/brand/
    name_ar/name_en) — نصّاً لا FK، لأن الأب القديم قد يبقى يتيماً بلا
    براندات، فحذفه لاحقاً (إن حدث) لا يجوز أن يكسر التراجع. `target_family`
    وحده FK حقيقي لأنه لا يُحذف أبداً: هو أبٌ حيّ ببراندٍ واحد على الأقل.
    """
    id = models.AutoField(primary_key=True, db_column='ProductMergeID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='product_merges',
    )
    target_family = models.ForeignKey(
        ProductFamily, on_delete=models.CASCADE, db_column='TargetFamilyID',
        related_name='merges',
    )
    snapshot = models.JSONField(
        db_column='Snapshot',
        help_text='لكل براند مُضموم: {product_id, family_id, brand, name_ar, name_en} قبل الضمّ',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='CreatedByUserID', related_name='product_merges',
    )
    undone_at = models.DateTimeField(null=True, blank=True, db_column='UndoneAt')

    class Meta:
        db_table = 'product_merges'
        managed = True

    def __str__(self):
        return f"ProductMerge #{self.id} → family {self.target_family_id}"


class ProductDemandForecast(models.Model):
    """رقما الصنف الحيّان من هولت — البيع الأسبوعي الحالي والاتجاه (#32).

    يكتبها حصراً `python manage.py recompute_demand_forecast`
    (`core/replenishment.py` — `holt_forecast`/`weekly_demand_series`)، ولا
    شيء يقرأها بعد في هذه التذكرة. صفٌّ واحد لكل منتج — `product` علاقةٌ
    فريدة (`OneToOneField`) لا FK متكرّر، لأن إعادة الحساب تُحدِّث نفس الصفّ
    ولا تراكم سجلّاً تاريخياً.
    """

    id = models.AutoField(primary_key=True, db_column='ProductDemandForecastID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='product_demand_forecasts',
    )
    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, db_column='ProductID',
        related_name='demand_forecast',
    )
    # ست خانات عشرية لا أربع كبقية حقول الكميات: الاستقراء (β=0.15) ينتج
    # كسوراً تحتاج دقّةً أعلى، وأربعٌ كانت تقرّب 0.256875 إلى 0.2569 صامتةً.
    level = models.DecimalField(max_digits=18, decimal_places=6, db_column='Level')
    trend = models.DecimalField(max_digits=18, decimal_places=6, db_column='Trend')
    weeks_observed = models.PositiveSmallIntegerField(db_column='WeeksObserved')
    mad = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True, db_column='MAD',
    )
    last_week_start = models.DateField(db_column='LastWeekStart')
    computed_at = models.DateTimeField(auto_now=True, db_column='ComputedAt')

    class Meta:
        db_table = 'product_demand_forecasts'
        managed = True

    def __str__(self):
        return f"DemandForecast product={self.product_id} level={self.level} trend={self.trend}"


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
        # THA-24: صرف قطع غيار مغطاة بالكفالة — نوعٌ مستقل عن STOCK_ISSUE عمداً:
        # خريطة تكلفة المبيعات تفلتر SALE/STOCK_ISSUE وحدهما، فمصروف الكفالة لا
        # يدخل تكلفة المبيع (مصروف تشغيلي لا COGS) ولا يتقاطع فضاء معرّفاته معها.
        ('SERVICE_ISSUE', 'صرف قطع كفالة'),
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
        # المرحلة 5 / P0-10 (SCALABILITY_AUDIT §3): أضخم جدول في المشروع كان
        # بلا أي فهرس — كل استعلام حركة = full scan. كل فهرس أدناه مربوط
        # باستعلام قائم، والعمود القائد tenant دائماً (كل قراءة مُنطاقة).
        indexes = [
            # كشف حركات منتج/إعادة حساب رصيده: inventory/services.py:901،
            # inventory/views.py:401.
            models.Index(fields=['tenant', 'product', 'movement_date'],
                         name='idx_sm_tenant_prod_date'),
            # قائمة الحركات وتقرير الحركات — نفس ترتيب Meta.ordering:
            # inventory/views.py:733، core/reports.py (تقرير حركات المخزون).
            models.Index(fields=['tenant', '-movement_date', '-id'],
                         name='idx_sm_tenant_date_id'),
            # التتبّع العكسي للمستند المصدر (ترحيل/إلغاء ترحيل، تشخيص):
            # inventory/services.py:312,385,476 · logistics/views المشتريات.
            models.Index(fields=['tenant', 'reference_type', 'reference_id'],
                         name='idx_sm_tenant_ref'),
            # تقييم المخزون لكل مستودع: core/reports (تقرير أرصدة المستودعات).
            models.Index(fields=['tenant', 'warehouse', 'product'],
                         name='idx_sm_tenant_wh_prod'),
        ]

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
    """N8-T9: 5 أسعار بيع + 5 أسعار شراء لكل منتج."""
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


class SupplierProduct(models.Model):
    """رقم المنتج عند المورّد — جدول ربط (شركة × مورّد × رقم).

    مطابقة فواتير المورّد تجري برقم كتالوجه (מק"ט)، وهو ليس رقمنا. حقلٌ واحد
    على `Product` كان سيكذب أوّل مرّة يأتي فيها المنتج من مورّدَين — والإطارات
    هي هذه الحالة بالضبط. ولذلك استقرّ Odoo (`product.supplierinfo.product_code`)
    وNetSuite (`itemvendor.vendorCode`) على جدول ربطٍ لا حقل، كلٌّ منهما استقلالاً.

    **بياناتٌ رئيسية لا مستند.** لقطةُ رقم المورّد على سطر الفاتورة تبقى في
    `PurchaseInvoiceItem.catalog_number`: البيانات الرئيسية تتغيّر، والمستند
    المرحّل يجب ألّا يتغيّر معها.

    **الفرادة على (شركة، مورّد، رقم) لا على (شركة، مورّد، منتج)** عمداً: للمورّد
    الواحد قد يكون أكثر من رقم للمنتج نفسه (ترقيم قديم وجديد)، وهذا مقبول
    ومفيد. الممنوع عكسُه — رقمٌ واحدٌ عند مورّدٍ واحد يشير إلى منتجين، فتصير
    المطابقة تخميناً.

    محايدٌ مالياً بالكامل: لا قيد ولا حركة مخزون ولا سعر.
    """

    id = models.AutoField(primary_key=True, db_column='SupplierProductID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='supplier_products',
    )
    supplier = models.ForeignKey(
        Partner, on_delete=models.CASCADE, db_column='SupplierID',
        related_name='product_codes',
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='ProductID',
        related_name='supplier_codes',
    )
    supplier_sku = models.CharField(
        max_length=100, db_column='SupplierSKU',
        help_text='رقم المنتج في كتالوج المورّد (مثال: 3068.82)',
    )
    supplier_name = models.CharField(
        max_length=255, blank=True, default='', db_column='SupplierName',
        help_text='اسم المنتج كما يسمّيه المورّد (اختياري — يساعد على المطابقة)',
    )
    notes = models.CharField(
        max_length=255, blank=True, default='', db_column='Notes',
    )
    # #34/ط9: الحدّ الأدنى للطلبية — خاصّية العلاقة (مورّد، صنف) لا الصنف: المورّد
    # الصيني يفرض خمسين والمحلّي يبيع بالقطعة، للصنف نفسه. `null` = لا حدّ مرصود.
    min_order_qty = models.DecimalField(
        max_digits=18, decimal_places=3, null=True, blank=True, db_column='MinOrderQty',
        help_text='أقلّ كمية يقبلها هذا المورّد لهذا الصنف في الطلبية الواحدة',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='UpdatedAt')

    class Meta:
        db_table = 'supplier_products'
        managed = True
        ordering = ['supplier_id', 'supplier_sku']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'supplier', 'supplier_sku'],
                name='uniq_supplier_sku_per_supplier',
            ),
        ]
        indexes = [
            # المطابقة العكسية: «هذا الرقم — أيّ منتجٍ هو؟» عبر موردي الشركة.
            models.Index(fields=['tenant', 'supplier_sku'], name='idx_tenant_supplier_sku'),
            models.Index(fields=['tenant', 'product'], name='idx_tenant_supplier_prod'),
        ]

    def __str__(self):
        return f'{self.supplier_sku} @ {self.supplier_id} -> {self.product_id}'


class ProductSerial(models.Model):
    """وحدة واحدة مُرقَّمة من منتج يتتبّع أرقامه التسلسلية (`Product.is_serialized`).

    سجلّ الوحدة الفعلية لا نيّةَ المستخدم: تُنشأ حين تدخل البضاعة المخزن باستلام
    الشراء، وتُوسم «مُباع» حين تُرحَّل فاتورة بيعها — فيُجاب سؤال «أي وحدة ذهبت
    لأي زبون» من الجانبين. الأرقام المدخلة على بند المستند تبقى على البند نفسه
    (`serials`) كنيّةٍ تُتَرجَم إلى صفوف هنا عند الاستلام/الترحيل، تماماً كما
    تُترجَم الكمية إلى `StockMovement`.

    الروابط قابلة للإفراغ: تعديل مستند غير مرحّل يحذف بنوده ويعيد إنشاءها، ووحدةٌ
    موجودة في المخزن فعلاً لا تُمحى لأن ورقتها تغيّرت.
    """

    STATUS_IN_STOCK = 'in_stock'
    STATUS_SOLD = 'sold'
    STATUS_CHOICES = [
        (STATUS_IN_STOCK, 'في المخزن'),
        (STATUS_SOLD, 'مُباع'),
    ]

    id = models.AutoField(primary_key=True, db_column='ProductSerialID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='ProductID',
        related_name='serials',
    )
    serial = models.CharField(max_length=100, db_column='Serial')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_STOCK,
        db_column='Status',
    )
    purchase_item = models.ForeignKey(
        'logistics.PurchaseInvoiceItem', on_delete=models.SET_NULL,
        null=True, blank=True, db_column='PurchaseInvoiceItemID',
        # `serial_units` لا `serials`: البند يحمل حقلاً بهذا الاسم للأرقام المُعلَنة
        # (نيّة)، وهذه هي الوحدات الفعلية (حالة) — الاسمان يجب أن يتفرّقا.
        related_name='serial_units',
        help_text='بند فاتورة الشراء الذي أدخل هذه الوحدة للمخزن',
    )
    sales_line = models.ForeignKey(
        'sales.SalesInvoiceLine', on_delete=models.SET_NULL,
        null=True, blank=True, db_column='SalesInvoiceLineID',
        related_name='serial_units',
        help_text='بند فاتورة البيع الذي استهلك هذه الوحدة',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column='CreatedAt')

    class Meta:
        db_table = 'product_serials'
        managed = True
        unique_together = [['tenant', 'product', 'serial']]
        indexes = [
            models.Index(
                fields=['tenant', 'product', 'status'],
                name='prodserial_tenant_prod_stat',
            ),
            # T-SCAN: المسح يبحث بالرقم وحده (لا يعرف منتجه — هذا سؤاله أصلاً)،
            # والفريد `(tenant, product, serial)` لا يخدمه لأن `product` في
            # وسطه. بلا هذا الفهرس كل مسحة تمسح كل وحدات الشركة.
            models.Index(
                fields=['tenant', 'serial'],
                name='prodserial_tenant_serial',
            ),
        ]

    def __str__(self):
        return f"{self.serial} ({self.get_status_display()})"


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
    """T-I2: مستند جرد فعلي. الترحيل يسوّي رصيد كل منتج ليطابق الكمية المعدودة
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


# ════════════════════════════════════════════════════════════════════
# مواصفة #137 — المرحلة 1: طبقات FIFO للمخزون (`inventory/fifo.py`)
# ════════════════════════════════════════════════════════════════════


class StockLayer(models.Model):
    """طبقة كلفة واردة — نظير `CashBoxFxLot` (`accounting/fx_fifo.py`) لكن للمخزون.

    كل حركة واردة (استلام شراء، تسوية إضافة، مرتجع) تُنشئ طبقة بسعرها الفعلي
    وقت الورود. الصرف اللاحق يستهلك الطبقات بترتيب الورود (الأقدم أولاً) بدل
    أن تُحسب الكلفة بمتوسطٍ متحرّك — فيُعرف بالضبط أيّ وارِدٍ باعت أيّ حركةُ صرف،
    وبأيّ سعرٍ، بدل رقمٍ واحدٍ مُذاب على كل الوحدات.

    **الطبقة على مستوى (الشركة، المنتج) لا على مستوى المستودع** — قرارٌ محسوم
    عمداً لا سهواً: `Product.quantity_on_hand` رقمٌ واحدٌ على مستوى الشركة
    (لا رصيد لكل مستودع على المنتج نفسه)، فتقسيم طبقات الكلفة حسب المستودع كان
    يُنتج طبقات «مقفلة» في مستودعٍ لا يمكن أن يستهلكها صرفٌ من مستودعٍ آخر رغم
    أن رصيد الشركة الواحد يسمح بذلك فعلياً. لذلك `warehouse` هنا حقل **أثرٍ**
    (أيّ مستودعٍ استقبل هذه الدفعة، للتتبّع والتقارير) لا حقل تقسيمٍ يدخل في
    منطق الاستهلاك — الاستهلاك (`inventory.fifo.consume`) يفلتر بـ(tenant,
    product) فقط ويتجاهل `warehouse` تماماً.
    """

    id = models.AutoField(primary_key=True, db_column='StockLayerID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='stock_layers',
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, db_column='ProductID',
        related_name='stock_layers',
    )
    warehouse = models.ForeignKey(
        'Warehouse', on_delete=models.PROTECT, null=True, blank=True,
        db_column='WarehouseID', related_name='stock_layers',
        help_text=(
            'المستودع الذي وصلت إليه هذه الدفعة — للأثر والتتبّع فقط، لا للتقسيم: '
            'الطبقة على مستوى الشركة والمنتج معاً (نظير Product.quantity_on_hand '
            'الذي هو رقمٌ واحدٌ على مستوى الشركة)، والاستهلاك لا يُقيَّد بمستودعٍ بعينه.'
        ),
    )
    layer_date = models.DateField(
        db_column='LayerDate', help_text='تاريخ ورود البضاعة (من حركة المخزون المصدر)',
    )
    original_qty = models.DecimalField(
        max_digits=18, decimal_places=4, db_column='OriginalQty',
        help_text='الكمية الأصلية وقت إنشاء الطبقة',
    )
    remaining_qty = models.DecimalField(
        max_digits=18, decimal_places=4, db_column='RemainingQty',
        help_text='المتبقّي غير المُستهلَك بعد (يُستهلَك FIFO)',
    )
    unit_cost = models.DecimalField(
        max_digits=18, decimal_places=4, db_column='UnitCost',
        help_text='كلفة الوحدة الفعلية لهذه الطبقة',
    )
    source_movement = models.ForeignKey(
        StockMovement, on_delete=models.CASCADE, null=True, blank=True,
        db_column='SourceMovementID', related_name='produced_layers',
        help_text='حركة المخزون الواردة التي أنشأت هذه الطبقة — فارغ للطبقات '
                  'الافتتاحية التي ينتجها أمر إعادة بناء الرصيد (مرحلة لاحقة)',
    )
    is_provisional = models.BooleanField(
        default=False, db_column='IsProvisional',
        help_text='طبقة مؤقّتة نتجت عن بيعٍ على مخزون سالب — تُستعمل في مرحلة لاحقة',
    )
    # مواصفة #137/تذكرة #136: الكمية من هذه الطبقة المؤقّتة التي وصلتها بضاعةٌ
    # حقيقيّةٌ وسُوّيت كلفتها — جزئياً أو كلياً (`inventory.fifo.reconcile_provisional`).
    # المعلَّق المتبقي لطبقةٍ = original_qty - reconciled_qty. صفرٌ دائماً على
    # الطبقات غير المؤقّتة (is_provisional=False).
    reconciled_qty = models.DecimalField(
        max_digits=18, decimal_places=4, default=0, db_column='ReconciledQty',
        help_text=(
            'الكمية من هذه الطبقة المؤقّتة التي سُوّيت كلفتها ببضاعةٍ حقيقيّةٍ وصلت لاحقاً '
            '(تسويةٌ جزئية مسموحة). المعلَّق = original_qty - reconciled_qty.'
        ),
    )

    class Meta:
        db_table = 'stock_layers'
        managed = True
        ordering = ['layer_date', 'id']  # ترتيب FIFO — مطابق لـ CashBoxFxLot
        indexes = [
            # استعلام الطبقات المفتوحة لمنتجٍ في شركة: inventory/fifo.py (consume،
            # open_layers_value، open_layers_quantity).
            models.Index(
                fields=['tenant', 'product', 'remaining_qty'],
                name='idx_stocklayer_tenant_prod_rem',
            ),
        ]

    def __str__(self):
        return f"Layer {self.id}: {self.remaining_qty}/{self.original_qty} @ {self.unit_cost}"


class StockLayerConsumption(models.Model):
    """سجلّ استهلاك: أيّ طبقةٍ أكل منها أيّ صرفٍ وكم — نظير تسجيل `consume_fifo`
    (`accounting/fx_fifo.py`) لكن كسجلٍّ صريح لا تعديلٍ مباشر على الطبقة وحدها.

    هذا الجدول هو ما يجعل الرَّدّ (`inventory.fifo.restore`) دقيقاً بالضبط: حين
    يُلغى ترحيل حركة الصرف، القراءة من هذه الصفوف تعرف أيّ طبقةٍ بعينها أُخذ
    منها وبأيّ كمية، فتُعاد الكمية إلى *نفس* الطبقة في *نفس* موقعها في رتل
    FIFO — لا طبقة جديدة تُنشأ في آخر الرتل بكمية الإرجاع، وهو ما كان سيُغيّر
    ترتيب الاستهلاك اللاحق. بدون سجلٍّ منفصل لا يوجد مصدر حقيقة لـ«من أين
    أُخذ» بعد أن تتغيّر `remaining_qty` على الطبقة نفسها.
    """

    id = models.AutoField(primary_key=True, db_column='StockLayerConsumptionID')
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_column='TenantID',
        related_name='stock_layer_consumptions',
    )
    movement = models.ForeignKey(
        StockMovement, on_delete=models.CASCADE, db_column='MovementID',
        related_name='layer_consumptions',
    )
    layer = models.ForeignKey(
        StockLayer, on_delete=models.CASCADE, db_column='StockLayerID',
        related_name='consumptions',
    )
    quantity = models.DecimalField(
        max_digits=18, decimal_places=4, db_column='Quantity',
        help_text='الكمية المأخوذة من هذه الطبقة لهذه الحركة',
    )
    unit_cost = models.DecimalField(
        max_digits=18, decimal_places=4, db_column='UnitCost',
        help_text='كلفة وحدة الطبقة لحظة الاستهلاك — لقطة لا مرجعاً متحرّكاً',
    )

    class Meta:
        db_table = 'stock_layer_consumptions'
        managed = True
        ordering = ['id']
        indexes = [
            # كل استهلاكات حركةٍ بعينها — restore() تقرأها بمفتاح الحركة.
            models.Index(fields=['tenant', 'movement'], name='idx_slc_tenant_movement'),
        ]

    def __str__(self):
        return f"Consumption {self.id}: layer={self.layer_id} qty={self.quantity}"
