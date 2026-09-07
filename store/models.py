"""عدّاد مشاهدات المتجر — الجدول الوحيد الذي يكتبه مسارٌ مجهول في المنصة.

**لماذا جدول تجميع يومي لا عمود على `Product`:** صفّ المنتج يعيش في قلب الـERP
(المخزون والتسعير والفوترة تقرؤه وتقفله). كتابةُ زائرٍ مجهول عليه تعني قفل صفٍّ
ساخن مع كل فتحة صفحة، وتُدخِل مسارَ كتابة غيرَ مصادَقٍ عليه إلى جدولٍ تحرسه
قواعد المخزون. الفصل يجعل أسوأ حالةٍ للإساءة `UPDATE` واحداً على جدولٍ جانبي
لا يقرؤه أي مسار مالي.

**ولماذا يومي لا صفٌّ لكل مشاهدة:** الصفّ لكل مشاهدة ينمو بلا حدّ على أوسع
سطحٍ عام لدينا. التجميع اليومي هو الحبيبة التي يحتاجها فعلاً تقريرُ «الأكثر
مشاهدة» ومقارنةُ الأسعار لاحقاً (#60).
"""
from django.core.exceptions import ValidationError
from django.db import models

from inventory.models import Product
from store.slugs import build_unique_slug
from tenants.models import Tenant


class StoreProductView(models.Model):
    """عدّاد مشاهدات صفحة منتج واحد في يوم واحد.

    يُكتب من `store/views.py` (`StoreProductDetailView`) وحده، بـ`F('count') + 1`
    ذرّي — لا قراءة ثم كتابة، فمشاهدتان متزامنتان لا تبتلع إحداهما الأخرى.
    وصفحة القائمة **لا** تكتب شيئاً: مشاهدة المنتج فتحُ صفحته لا مرورُه في شبكة.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="store_product_views",
        db_column="TenantID")
    # THA-166 M2: نُقلت إلى `null=True` — منتجُ متجرٍ من الصفر لا صنفَ مخزونٍ
    # خلفه، فمشاهدةُ صفحته لا يمكن أن تكتب هنا. `store_product` أدناه هو
    # المرساة الحيّة لهذا الصفّ من الآن؛ هذا الحقل يبقى للصفوف القديمة فقط.
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="store_views",
        null=True, blank=True, db_column="ProductID")
    # THA-166 M1: يشير إلى منتج المتجر المستقلّ (`StoreProduct`) — أضيف بلا حذف
    # `product` القائم. null=True لأن كل صفٍّ قائمٍ يبقى بلا قيمة حتى تُنسَخ
    # الهجرةُ التوابع؛ قارئ هذا الحقل يأتي في مرحلةٍ لاحقة.
    store_product = models.ForeignKey(
        "StoreProduct", on_delete=models.CASCADE, related_name="views",
        null=True, blank=True, db_column="StoreProductID")
    view_date = models.DateField(db_column="ViewDate")
    count = models.PositiveIntegerField(default=0, db_column="Count")

    class Meta:
        db_table = "store_product_views"
        managed = True
        # القيد هو ما يجعل الـupsert ذرّياً: سباقُ إنشاءٍ متزامن يُخفق بـIntegrity
        # فيسقط إلى `UPDATE … F('count') + 1` بدل أن يخلق صفّاً ثانياً لليوم نفسه.
        unique_together = [
            ["tenant", "product", "view_date"],
            ["tenant", "store_product", "view_date"],
        ]

    def __str__(self):
        return f"{self.product_id} — {self.view_date}: {self.count}"


class StoreSettings(models.Model):
    """إعدادات ومظهر وهوية المتجر الإلكتروني للشركة."""

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="store_theme_settings",
        db_column="TenantID",
    )
    hero_title = models.CharField(
        max_length=200, blank=True, default="", db_column="HeroTitle"
    )
    hero_subtitle = models.TextField(
        blank=True, default="", db_column="HeroSubtitle"
    )
    announcement_bar = models.CharField(
        max_length=255, blank=True, default="", db_column="AnnouncementBar"
    )
    show_announcement = models.BooleanField(
        default=True, db_column="ShowAnnouncement"
    )
    theme_preset = models.CharField(
        max_length=50, default="default", db_column="ThemePreset"
    )
    primary_color = models.CharField(
        max_length=30, default="#2563eb", db_column="PrimaryColor"
    )
    accent_color = models.CharField(
        max_length=30, default="#f59e0b", db_column="AccentColor"
    )
    background_color = models.CharField(
        max_length=30, default="#f8fafc", db_column="BackgroundColor"
    )
    background_image_url = models.CharField(
        max_length=500, blank=True, null=True, db_column="BackgroundImageUrl"
    )
    background_style = models.CharField(
        max_length=50, default="cover", db_column="BackgroundStyle"
    )
    banner_image_url = models.CharField(
        max_length=500, blank=True, null=True, db_column="BannerImageUrl"
    )
    instagram_url = models.CharField(
        max_length=300, blank=True, null=True, db_column="InstagramUrl"
    )
    tiktok_url = models.CharField(
        max_length=300, blank=True, null=True, db_column="TiktokUrl"
    )
    facebook_url = models.CharField(
        max_length=300, blank=True, null=True, db_column="FacebookUrl"
    )
    snapchat_url = models.CharField(
        max_length=300, blank=True, null=True, db_column="SnapchatUrl"
    )
    whatsapp_number = models.CharField(
        max_length=50, blank=True, null=True, db_column="WhatsappNumber"
    )
    catalog_mode_default = models.CharField(
        max_length=30, default="grid", db_column="CatalogModeDefault"
    )
    allow_cart = models.BooleanField(
        default=True, db_column="AllowCart"
    )
    # `sale_price` حقلٌ تشغيلي تقرؤه الفوترة — وجودُه ليس إذناً بإعلانه.
    # متاجر الجملة تعرض كتالوجاً بلا أسعار وتترك السعر لمحادثة.
    # الافتراضي `True` كي لا يفقد متجرٌ قائم أسعاره بمجرّد الترقية.
    show_prices = models.BooleanField(
        default=True, db_column="ShowPrices"
    )
    # THA-166 م٤: عمر «الجديد» بالأيام لفلتر `is_new`. لا تعريف قياسيّ لهذه
    # الراية عند أيّ منصّة — قرارٌ لكل شركة: بائع سيّاراتٍ و«الجديد» عنده
    # ليسا نفس «الجديد» عند بقّال. ٣٠ افتراضاً كي لا يفقد متجرٌ قائم فلترته
    # بمجرّد الترقية.
    new_product_days = models.PositiveIntegerField(
        default=30, db_column="NewProductDays"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")

    class Meta:
        db_table = "store_settings"
        managed = True

    def __str__(self):
        return f"StoreSettings ({self.tenant_id})"


class StoreProductImage(models.Model):
    """صور مخصصة لمنتج المتجر تتيح رفع صور تسويقية مستقلة وترتيبها وتعيين الغلاف."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="store_product_images",
        db_column="TenantID",
    )
    # THA-166 M2: نُقلت إلى `null=True` — انظر التعليق المطابق على
    # `StoreProductView.product`.
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="store_custom_images",
        null=True,
        blank=True,
        db_column="ProductID",
    )
    # THA-166 M1: منتج المتجر المستقلّ — أضيف بلا حذف `product` القائم، انظر
    # التعليق المطابق على `StoreProductView`.
    store_product = models.ForeignKey(
        "StoreProduct",
        on_delete=models.CASCADE,
        related_name="images",
        null=True,
        blank=True,
        db_column="StoreProductID",
    )
    image_url = models.CharField(max_length=500, db_column="ImageUrl")
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")
    is_cover = models.BooleanField(default=False, db_column="IsCover")
    caption = models.CharField(
        max_length=200, blank=True, default="", db_column="Caption"
    )
    overlay_text = models.CharField(
        max_length=200, blank=True, default="", db_column="OverlayText"
    )
    overlay_style = models.CharField(
        max_length=50, default="diagonal_ribbon", db_column="OverlayStyle"
    )
    overlay_color = models.CharField(
        max_length=50, default="red_fire", db_column="OverlayColor"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "store_product_images"
        managed = True
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"StoreImage {self.id} for Product {self.product_id}"


class StoreCollection(models.Model):
    """مجموعات المنتجات وحملات الإعلانات الترويجية وصفحات الهبوط."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="store_collections",
        db_column="TenantID",
    )
    title = models.CharField(max_length=200, db_column="Title")
    slug = models.CharField(max_length=100, db_column="Slug")
    description = models.TextField(
        blank=True, default="", db_column="Description"
    )
    banner_image_url = models.CharField(
        max_length=500, blank=True, null=True, db_column="BannerImageUrl"
    )
    badge_text = models.CharField(
        max_length=100, blank=True, default="", db_column="BadgeText"
    )
    featured_product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="featured_store_collections",
        db_column="FeaturedProductID",
    )
    # THA-166 م٢: المرساةُ الحيّة منذ أن صارت القراءةُ العامة تقرأ `StoreProduct`
    # حصراً — `featured_product` أعلاه بقي بلا حذفٍ (فضاءُ معرّفاته `inventory.Product`
    # منفصلٌ تماماً عن هذا)، لكن العرضَ العامّ يقرأ هذا الحقلَ وحده الآن.
    featured_store_product = models.ForeignKey(
        "StoreProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="featured_in_collections",
        db_column="FeaturedStoreProductID",
    )
    is_active = models.BooleanField(default=True, db_column="IsActive")
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    # THA-166 M1: مجموعةٌ ذاتُ تواريخَ وخصمٍ تُسمّى «حملة» في الواجهة — الفرقُ
    # حالةٌ لا نوع، فلا نموذج `StoreCampaign` منفصل. `null` في الطرفين مقصود:
    # بلا بدايةٍ = ساريةٌ منذ الأزل، بلا نهايةٍ = بلا انتهاء.
    starts_at = models.DateTimeField(null=True, blank=True, db_column="StartsAt")
    ends_at = models.DateTimeField(null=True, blank=True, db_column="EndsAt")
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, db_column="DiscountPercent"
    )
    priority = models.IntegerField(default=0, db_column="Priority")

    class Meta:
        db_table = "store_collections"
        managed = True
        unique_together = [["tenant", "slug"]]
        ordering = ["sort_order", "id"]

    def _reject_price_killing_discount(self):
        """نسبةُ خصمٍ ≥ 100٪ تُنزل سعر كلّ عضوٍ في الحملة إلى صفرٍ أو دونه —
        مرفوضةٌ عند الحفظ بخطأ تحقّقٍ صريح لا قصّاً بصمتٍ (مواصفة #166 م٢)."""
        if self.discount_percent is not None and self.discount_percent >= 100:
            raise ValidationError(
                {"discount_percent": "نسبة خصم الحملة يجب أن تكون أقل من 100٪."}
            )

    def clean(self):
        self._reject_price_killing_discount()

    def save(self, *args, **kwargs):
        # الحارسُ هنا لا في `clean()` وحدها — نفس نمط `StoreCategory` و
        # `StoreProduct` أعلاه: `objects.create()` كان سيتجاوزه بصمت.
        self._reject_price_killing_discount()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.slug})"


class StoreCollectionItem(models.Model):
    """ربط المنتج بالمجموعة الإعلانية مع الترتيب."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="store_collection_items",
        db_column="TenantID",
    )
    collection = models.ForeignKey(
        StoreCollection,
        on_delete=models.CASCADE,
        related_name="items",
        db_column="CollectionID",
    )
    # THA-166 M2: نُقلت إلى `null=True` — انظر التعليق المطابق على
    # `StoreProductView.product`.
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="store_collection_memberships",
        null=True,
        blank=True,
        db_column="ProductID",
    )
    # THA-166 M1: منتج المتجر المستقلّ — أضيف بلا حذف `product` القائم، انظر
    # التعليق المطابق على `StoreProductView`.
    store_product = models.ForeignKey(
        "StoreProduct",
        on_delete=models.CASCADE,
        related_name="collection_items",
        null=True,
        blank=True,
        db_column="StoreProductID",
    )
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")

    class Meta:
        db_table = "store_collection_items"
        managed = True
        unique_together = [
            ["collection", "product"],
            ["collection", "store_product"],
        ]
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Collection {self.collection_id} -> Product {self.product_id}"


class StoreBrand(models.Model):
    """ماركةٌ جدولٌ لا نصٌّ حرّ — العدّاداتُ فوق نصٍّ حرٍّ تتشظّى («Samsung» و
    «samsung » و«سامسونج» ثلاثةُ صفوف)، وذاك عينُ «غير احترافيّ» (مواصفة #166)."""

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="store_brands",
        db_column="TenantID",
    )
    name = models.CharField(max_length=100, db_column="Name")
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")
    is_active = models.BooleanField(default=True, db_column="IsActive")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "store_brands"
        managed = True
        unique_together = [["tenant", "name"]]
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class StoreCategory(models.Model):
    """فئةٌ تسويقيةٌ بمستويين — شجرةٌ مستقلّةٌ عن `inventory.ProductCategory`
    المحاسبية (مواصفة #166).

    **العمقُ محدودٌ بالتحقّق لا بالبنية**: `parent` حقلٌ ذاتيٌّ حرٌّ، والتحقّقُ
    يرفض أن يكون للأب أبٌ (لا حفيد) **وأن يُسنَد أبٌ لفئةٍ لها أبناء** (الحالتان
    تنتجان ثلاثة مستويات — الأولى بأبٍ جديد، والثانية بإعادة تأبية فئةٍ وسيطة) —
    فرفعُ السقف لاحقاً يبقى تغييرَ سطرِ تحقّقٍ لا هجرةَ بنية.

    **الحارسُ موصولٌ بـ`clean()` و`save()` معاً**: `clean()` وحدَها لا تُستدعى
    تلقائياً من `save()` في جانغو، و`StoreCategory.objects.create()` كان
    سيتجاوز التحقّقَ كليّاً وبصمت بدون هذا الربط الصريح. `bulk_create` يبقى
    خارج المسار عمداً — الهجرةُ تستعمله ولا تمرّ بـ`save()`.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="store_categories",
        db_column="TenantID",
    )
    name = models.CharField(max_length=100, db_column="Name")
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="children", db_column="ParentID",
    )
    slug = models.CharField(max_length=140, db_column="Slug")
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")
    is_active = models.BooleanField(default=True, db_column="IsActive")
    image_url = models.CharField(max_length=500, blank=True, default="", db_column="ImageUrl")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "store_categories"
        managed = True
        unique_together = [["tenant", "slug"]]
        ordering = ["sort_order", "id"]

    def _reject_third_level(self):
        """يفحص طرفَي إسنادِ الأب معاً — لا طرفاً واحداً.

        الفحصُ الأصليّ كان ينظر إلى **أب الأب الجديد** وحدَه، فتُقبل إعادةُ
        تأبية فئةٍ لها أبناءٌ تحت جذرٍ آخر: النتيجةُ شجرةٌ فعليّةٌ من ثلاثة
        مستويات رغم أنّ كِلا الطرفين يبدو سليماً بمعزلٍ عن الآخر. **فإسناد
        أبٍ لفئةٍ لها أبناءٌ مرفوضٌ بنفس قوّة إسناد أبٍ له أب.**
        """
        if self.parent_id is None:
            return
        if self.pk is not None and self.parent_id == self.pk:
            raise ValidationError("لا يمكن أن تكون الفئة أباً لنفسها")
        if self.parent.parent_id is not None:
            raise ValidationError(
                "العمق الأقصى لشجرة فئات المتجر مستويان — لا يجوز أن يكون للأب أبٌ"
            )
        if self.pk is not None and self.children.exists():
            raise ValidationError(
                "لا يجوز إسنادُ أبٍ لفئةٍ لها أبناء — يجعلها ثلاثةَ مستويات"
            )

    def clean(self):
        self._reject_third_level()

    def save(self, *args, **kwargs):
        # العمقُ مفروضٌ **بالتحقّق لا بالبنية** (مواصفة #166) — فحارسٌ يعمل
        # فقط حين يُستدعى `full_clean()` يدويّاً حارسٌ اسميٌّ لا أكثر، لأنّ
        # جانغو لا ينادي `clean()` من `save()` تلقائياً. الفحصُ هنا يُطبَّق
        # على مسار الحفظ الفعليّ (`objects.create()` بما فيه)، لا على
        # `full_clean()` وحدَها. `bulk_create` يتجاوز `save()` عمداً ولا يُمسّ
        # بهذا (الهجرةُ تعتمد عليه).
        self._reject_third_level()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class StoreProduct(models.Model):
    """كتالوجُ المتجر المستقلّ — لا مخزونَ ولا محاسبةَ أبداً (قرار مالكٍ صريح،
    مواصفة #166). يُنشأ من شاشة المتجر أو يُنسَخ مرّةً واحدةً من
    `inventory.Product` بفعل «استيراد من الأصناف» ثمّ يتباعدان.

    `imported_from_product_id` رقمٌ مجرَّدٌ عمداً — لا `ForeignKey`: مفتاحٌ
    أجنبيٌّ هنا يُعيد بناء الاقتران الذي قطعه قرارُ المالك، ووظيفتُه الوحيدة
    تنبيهُ «هذا الصنف مستوردٌ من قبل» ومنعُ ازدواج الهجرة.
    """

    STOCK_IN_STOCK = "in_stock"
    STOCK_OUT_OF_STOCK = "out_of_stock"
    STOCK_PREORDER = "preorder"
    STOCK_STATE_CHOICES = [
        (STOCK_IN_STOCK, "متوفر"),
        (STOCK_OUT_OF_STOCK, "غير متوفر"),
        (STOCK_PREORDER, "طلب مسبق"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="store_products",
        db_column="TenantID",
    )
    name_ar = models.CharField(max_length=200, db_column="NameAr")
    name_en = models.CharField(max_length=200, blank=True, default="", db_column="NameEn")
    slug = models.CharField(max_length=220, db_column="Slug")
    brand = models.ForeignKey(
        StoreBrand, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="products", db_column="BrandID",
    )
    categories = models.ManyToManyField(
        StoreCategory, blank=True, related_name="products",
    )
    # «قطعة»، «كرتونة» — نصٌّ حرّ عمداً، لا FK إلى `inventory.UnitOfMeasure`.
    unit = models.CharField(max_length=50, blank=True, default="", db_column="Unit")
    # فارغٌ = «السعر عند الطلب» لهذا المنتج وحدَه.
    price = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, db_column="Price",
    )
    # مبلغٌ مطلقٌ لا نسبة — خصمُ المنتج المفرد.
    sale_price = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, db_column="SalePrice",
    )
    stock_state = models.CharField(
        max_length=20, choices=STOCK_STATE_CHOICES, default=STOCK_IN_STOCK,
        db_column="StockState",
    )
    description = models.TextField(blank=True, default="", db_column="Description")
    is_active = models.BooleanField(default=True, db_column="IsActive")
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")
    updated_at = models.DateTimeField(auto_now=True, db_column="UpdatedAt")
    imported_from_product_id = models.PositiveIntegerField(
        null=True, blank=True, db_index=True, db_column="ImportedFromProductID",
    )

    class Meta:
        db_table = "store_products"
        managed = True
        unique_together = [["tenant", "slug"]]
        ordering = ["sort_order", "id"]

    def _reject_non_positive_sale_price(self):
        """خصمٌ يُنزل السعرَ إلى صفرٍ أو دونه مرفوضٌ عند الحفظ — لا يُقصّ
        بصمتٍ إلى صفر (مواصفة #166 م٢). `sale_price` هنا **مبلغٌ مطلق** هو
        السعر بعد الخصم نفسه، فسعرٌ صفريٌّ أو سالبٌ في متجرٍ خطأُ إدخالٍ دائماً.
        """
        if self.sale_price is not None and self.sale_price <= 0:
            raise ValidationError(
                {"sale_price": "سعر العرض يجب أن يكون أكبر من صفر."}
            )

    def clean(self):
        self._reject_non_positive_sale_price()

    def save(self, *args, **kwargs):
        # الحارسُ هنا لا في `clean()` وحدها — جانغو لا ينادي `clean()` من
        # `save()` تلقائياً (نفس نمط `StoreCategory._reject_third_level`).
        self._reject_non_positive_sale_price()
        is_new = self._state.adding
        if not self.slug:
            self.slug = build_unique_slug(
                self.name_ar,
                lambda candidate: StoreProduct.objects.filter(
                    tenant_id=self.tenant_id, slug=candidate
                ).exclude(pk=self.pk).exists(),
            )
        old_price = None
        if not is_new:
            old_price = StoreProduct.objects.filter(pk=self.pk).values_list(
                "price", flat=True
            ).first()
        super().save(*args, **kwargs)
        # `to_python` طبيعياً: `self.price` قد يبقى النوعَ الخام المُسنَد
        # (نصّاً مثلاً) بعد `save()`، بينما `old_price` قادمٌ من القاعدة
        # Decimal دائماً — مقارنةٌ خاطئة بلا هذا التطبيع.
        new_price = self._meta.get_field("price").to_python(self.price)
        if is_new or old_price != new_price:
            StorePriceHistory.objects.create(
                tenant_id=self.tenant_id, store_product=self, price=new_price,
            )

    def __str__(self):
        return f"{self.name_ar} ({self.slug})"


class StorePriceHistory(models.Model):
    """سجلّ تغييرات سعر منتج المتجر — بيانٌ صامت، لا يظهر في أيّ عقدٍ عامّ ولا
    إداريّ في هذه المرحلة (مواصفة #166).

    **العلّة:** المادةُ 6a الأوروبية تُلزم بإعلان أدنى سعرٍ طُبِّق فعلاً خلال
    ٣٠ يوماً عند أيّ تخفيض، **وتاريخُ الأسعار لا يُسترجَع بأثرٍ رجعيّ** — أربعةُ
    أعمدةٍ اليومَ تساوي مستحيلاً بعد سنة، فالتسجيلُ يبدأ من أول يوم.

    **لماذا في `save()` لا بإشارة `post_save`:** القيمة القديمة يلزمها استعلامٌ
    *قبل* الحفظ الجديد لمقارنتها، وربطُ الكتابة بنقطة الحفظ الوحيدة لـ
    `StoreProduct` أبسط من إشارةٍ تعيش في ملفٍّ آخر وتُعيد نفس الاستعلام.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="store_price_history",
        db_column="TenantID",
    )
    store_product = models.ForeignKey(
        StoreProduct, on_delete=models.CASCADE, related_name="price_history",
        db_column="StoreProductID",
    )
    price = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, db_column="Price",
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_column="ChangedAt")

    class Meta:
        db_table = "store_price_history"
        managed = True
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.store_product_id} @ {self.changed_at}: {self.price}"

