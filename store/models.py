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
from django.db import models

from inventory.models import Product
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
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="store_views",
        db_column="ProductID")
    view_date = models.DateField(db_column="ViewDate")
    count = models.PositiveIntegerField(default=0, db_column="Count")

    class Meta:
        db_table = "store_product_views"
        managed = True
        # القيد هو ما يجعل الـupsert ذرّياً: سباقُ إنشاءٍ متزامن يُخفق بـIntegrity
        # فيسقط إلى `UPDATE … F('count') + 1` بدل أن يخلق صفّاً ثانياً لليوم نفسه.
        unique_together = [["tenant", "product", "view_date"]]

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
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="store_custom_images",
        db_column="ProductID",
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
    """مجموعات الأصناف وحملات الإعلانات الترويجية وصفحات الهبوط."""

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
    is_active = models.BooleanField(default=True, db_column="IsActive")
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "store_collections"
        managed = True
        unique_together = [["tenant", "slug"]]
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.slug})"


class StoreCollectionItem(models.Model):
    """ربط الصنف بالمجموعة الإعلانية مع الترتيب."""

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
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="store_collection_memberships",
        db_column="ProductID",
    )
    sort_order = models.PositiveIntegerField(default=0, db_column="SortOrder")

    class Meta:
        db_table = "store_collection_items"
        managed = True
        unique_together = [["collection", "product"]]
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Collection {self.collection_id} -> Product {self.product_id}"

