from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.tenant_utils import get_tenant
from inventory.models import Product
from store.models import (
    StoreBrand,
    StoreCategory,
    StoreCollection,
    StoreCollectionItem,
    StoreProduct,
    StoreProductImage,
    StoreSettings,
)


class TenantScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """مرجع لا يقبل إلا سجلات شركة الطلب.

    عزل الشركات يُفرض عند الكتابة كما يُفرض عند القراءة: تقييد `get_queryset`
    وحده يحجب سجلّ الغير عن القائمة، ولا يمنع ربطه بمعرّفه في جسم الطلب.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = get_tenant(self.context.get("request"))
        if tenant is None:
            return queryset.none()
        return queryset.filter(tenant=tenant)


class StoreProfileSerializer(serializers.Serializer):
    """بطاقة الشركة وإعدادات المظهر كما يراها زائر: مَن هي، وكيف يتواصل معها، وهوية المتجر."""

    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    logo_url = serializers.CharField(read_only=True, allow_null=True)
    phone = serializers.CharField(read_only=True, allow_null=True)
    address = serializers.CharField(read_only=True, allow_null=True)
    currency = serializers.CharField(read_only=True, allow_null=True)
    # إعدادات المظهر والهوية
    hero_title = serializers.CharField(read_only=True, allow_null=True)
    hero_subtitle = serializers.CharField(read_only=True, allow_null=True)
    announcement_bar = serializers.CharField(read_only=True, allow_null=True)
    show_announcement = serializers.BooleanField(read_only=True, default=True)
    theme_preset = serializers.CharField(read_only=True, default="default")
    primary_color = serializers.CharField(read_only=True, default="#2563eb")
    accent_color = serializers.CharField(read_only=True, default="#f59e0b")
    background_color = serializers.CharField(read_only=True, default="#f8fafc")
    background_image_url = serializers.CharField(read_only=True, allow_null=True)
    background_style = serializers.CharField(read_only=True, default="cover")
    banner_image_url = serializers.CharField(read_only=True, allow_null=True)
    instagram_url = serializers.CharField(read_only=True, allow_null=True)
    tiktok_url = serializers.CharField(read_only=True, allow_null=True)
    facebook_url = serializers.CharField(read_only=True, allow_null=True)
    snapchat_url = serializers.CharField(read_only=True, allow_null=True)
    whatsapp_number = serializers.CharField(read_only=True, allow_null=True)
    catalog_mode_default = serializers.CharField(read_only=True, default="grid")
    allow_cart = serializers.BooleanField(read_only=True, default=True)
    show_prices = serializers.BooleanField(read_only=True, default=True)


class StoreProductSerializer(serializers.Serializer):
    """المنتج كما يُنشر للعالم — مصدره `store.StoreProduct` المستقلّ منذ
    THA-166 م٢. العقد الأصليّ (أحد عشر حقلاً) **يبقى كما هو حرفياً** —
    الواجهة الحالية تقرؤه ولن تُعاد كتابتها قبل م٧ — وستٌّ إضافيةٌ محضة.
    """

    id = serializers.IntegerField(read_only=True)
    name_ar = serializers.CharField(read_only=True, allow_null=True)
    name_en = serializers.CharField(read_only=True, allow_null=True)
    brand = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    uom_name = serializers.CharField(source="unit", read_only=True, allow_null=True)
    price = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    description = serializers.CharField(read_only=True, allow_null=True)
    images = serializers.SerializerMethodField()
    cover_overlay = serializers.SerializerMethodField(read_only=True)

    # ── THA-166 م٢: إضافاتٌ محضة ────────────────────────────────────────
    slug = serializers.CharField(read_only=True)
    original_price = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    stock_state = serializers.CharField(read_only=True)
    brand_id = serializers.IntegerField(read_only=True, allow_null=True)

    #: `stock_state` (إعلانٌ من التاجر) ← `availability` (حالةٌ عامة) — و
    #: `limited` سقطت عمداً: كانت تُحسَب من رصيدٍ مخزنيّ لا وجود له هنا.
    _AVAILABILITY_BY_STOCK_STATE = {
        "in_stock": "available",
        "out_of_stock": "out",
        "preorder": "preorder",
    }

    def _prices_public(self):
        return self.context.get("prices_public", True)

    def _sorted_categories(self, obj):
        """فئات المنتج مرتّبةً — من ذاكرة `prefetch_related` بلا استعلامٍ إضافي."""
        return list(obj.categories.all())

    def get_brand(self, obj):
        return obj.brand.name if obj.brand_id else ""

    def get_category_name(self, obj):
        cats = self._sorted_categories(obj)
        return cats[0].name if cats else ""

    def get_categories(self, obj):
        return [
            {"id": c.id, "name": c.name, "slug": c.slug}
            for c in self._sorted_categories(obj)
        ]

    def get_availability(self, obj):
        return self._AVAILABILITY_BY_STOCK_STATE.get(obj.stock_state, "available")

    @staticmethod
    def _money(value):
        """يقرّب العرضَ إلى خانتين لا القيمةَ المخزَّنة — السعر الخام يبقى
        تامّاً في القاعدة، لكن دقّته الفعلية على SQLite/MySQL تتذبذب بحسب
        مسار الحساب (`effective_price` عبر `Case`/`Least` قد يفقد الصفر
        اللاحق). ونصٌّ صريح لا `Decimal` خام: `SerializerMethodField` لا يمرّ
        بـ`DecimalField.to_representation()` الذي يُخرج نصّاً دائماً، فيسقط
        على ترميز DRF العام لـ`Decimal` (رقمٌ لا نص حين `COERCE_DECIMAL_TO_STRING`
        غير مضبوطة) — وكل عملاء العقد (إعادة تسعير السلّة بـ`ids` مثلاً)
        يتوقّعون نصّاً ثابت الخانتين كبقية أسعار المنصة."""
        if value is None:
            return None
        return str(value.quantize(Decimal("0.01")))

    def get_price(self, obj):
        if not self._prices_public():
            return None
        return self._money(obj.effective_price)

    def _discount_pair(self, obj):
        """(السعر الأساس، السعر الفعليّ) — أو `(None, None)` حين لا يُعلَن
        السعر، فلا نلمس `obj.price` أصلاً حينها (مؤجَّلٌ عمداً عن القاعدة)."""
        if not self._prices_public():
            return None, None
        return obj.price, obj.effective_price

    def get_original_price(self, obj):
        """ما قبل الخصم — `null` صراحةً إلّا حين تكون هناك خصمٌ فعليّ حقاً
        (الحارس الأوّل: `original_price` أكبر من `price` فعلياً وإلّا فلا خصم)."""
        base, effective = self._discount_pair(obj)
        if base is None or effective is None or effective >= base:
            return None
        return self._money(base)

    def get_discount_percent(self, obj):
        """نسبةٌ صحيحةٌ للشارة فقط — التقريب هنا عرضٌ لا يمسّ `price` المخزَّن."""
        base, effective = self._discount_pair(obj)
        if base is None or effective is None or effective >= base:
            return None
        pct = (base - effective) / base * 100
        return int(pct.to_integral_value(rounding=ROUND_HALF_UP))

    def get_images(self, obj):
        """روابط صور المنتج — من خريطة مجهّزة باستعلام واحد للصفحة كلها."""
        return self.context.get("images", {}).get(obj.id, [])

    def get_cover_overlay(self, obj):
        """بيانات النص والشريط الإعلاني المخصص لصورة الغلاف إن وُجد."""
        return self.context.get("cover_overlays", {}).get(obj.id)


class StoreCollectionSerializer(serializers.Serializer):
    """المجموعة / الحملة الإعلانية كما يراها الزائر في القائمة العامة."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_null=True)
    banner_image_url = serializers.CharField(read_only=True, allow_null=True)
    badge_text = serializers.CharField(read_only=True, allow_null=True)
    featured_product_id = serializers.IntegerField(
        read_only=True, allow_null=True
    )
    items_count = serializers.IntegerField(read_only=True, default=0)


class StoreCollectionDetailSerializer(serializers.Serializer):
    """تفاصيل المجموعة / الحملة الإعلانية لصفحة الهبوط مع منتجها المميز."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_null=True)
    banner_image_url = serializers.CharField(read_only=True, allow_null=True)
    badge_text = serializers.CharField(read_only=True, allow_null=True)
    featured_product = serializers.SerializerMethodField()

    def get_featured_product(self, obj):
        """المنتج المميّز — يحلّه العرضُ عبر `published_products` ويضعه في السياق.

        قراءته من `obj.featured_product` مباشرةً تنشر منتجاً غير منشور أو منتج
        شركة أخرى، وتُسقط `price` و`availability` لغياب حقول الاستعلام.
        """
        featured = self.context.get("featured_product")
        if featured is None:
            return None
        return StoreProductSerializer(featured, context=self.context).data


# ── سيريالايزرات الإدارة والمصادقة (Store Admin) ──────────────────────────


class StoreSettingsAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = [
            "id", "hero_title", "hero_subtitle", "announcement_bar",
            "show_announcement", "theme_preset", "primary_color",
            "accent_color", "background_color", "background_image_url",
            "background_style", "banner_image_url", "instagram_url",
            "tiktok_url", "facebook_url", "snapchat_url", "whatsapp_number",
            "catalog_mode_default", "allow_cart", "show_prices",
        ]


def _django_error_detail(exc):
    """يحوّل رسائل `django.core.exceptions.ValidationError` إلى شكلٍ يقبله
    `rest_framework.exceptions.ValidationError` — قاموسٌ بالحقل حين تتوفّر
    الخريطة، وإلا قائمةٌ عامة."""
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    return {"non_field_errors": exc.messages}


class _ConvertsModelValidationErrors:
    """يحوّل `ValidationError` النموذج (من `Model.save()`) إلى `400` صريح.

    بلا هذا، حارسٌ يرمي من `save()` (مثل `StoreProduct._reject_non_positive_sale_price`
    أو `StoreCollection._reject_price_killing_discount`) يفجّر استثناءً غير
    معالَج فيردّ **500** في وجه المستخدم — نفس درسِ قيد `unique(tenant, sku)`
    الذي عولج سابقاً بتحقّقٍ صريح في `validate()`. هنا التحويل عامٌّ فلا
    يتكرّر لكل حارسٍ جديد بمنطقه الخاص.
    """

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_django_error_detail(exc))

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(_django_error_detail(exc))


class StoreProductImageAdminSerializer(serializers.ModelSerializer):
    store_product = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreProduct.objects.all()
    )

    class Meta:
        model = StoreProductImage
        fields = [
            "id", "store_product", "image_url", "sort_order", "is_cover",
            "caption", "overlay_text", "overlay_style", "overlay_color", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class StoreCollectionItemAdminSerializer(serializers.ModelSerializer):
    collection = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreCollection.objects.all()
    )
    store_product = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreProduct.objects.all()
    )
    store_product_name = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCollectionItem
        fields = [
            "id", "collection", "store_product", "store_product_name", "price",
            "image_url", "sort_order",
        ]
        read_only_fields = ["id"]

    def get_store_product_name(self, obj):
        return obj.store_product.name_ar if obj.store_product_id else None

    def get_price(self, obj):
        return obj.store_product.price if obj.store_product_id else None

    def get_image_url(self, obj):
        if not obj.store_product_id:
            return None
        image = obj.store_product.images.order_by("sort_order", "id").first()
        return image.image_url if image else None


class StoreCollectionAdminSerializer(_ConvertsModelValidationErrors, serializers.ModelSerializer):
    featured_product = TenantScopedPrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True
    )
    # THA-166 م٢ (تصحيح): المرساةُ الحيّة للعرض العام — `featured_product`
    # أعلاه بقي بلا حذفٍ ولا كتابةٍ فعلية جديدة إليه من هنا، فقط للتوافق.
    featured_store_product = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreProduct.objects.all(), required=False, allow_null=True
    )
    items_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = StoreCollection
        fields = [
            "id", "title", "slug", "description", "banner_image_url",
            "badge_text", "featured_product", "featured_store_product",
            "is_active", "sort_order", "starts_at", "ends_at",
            "discount_percent", "priority", "items_count", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class StoreBrandAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreBrand
        fields = ["id", "name", "sort_order", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class StoreCategoryAdminSerializer(_ConvertsModelValidationErrors, serializers.ModelSerializer):
    """إدارة فئات كتالوج المتجر — العمقُ محدودٌ بمستويين، والحارسُ
    (`StoreCategory._reject_third_level`) يعمل من `save()` فيرجع **400**
    هنا عبر `_ConvertsModelValidationErrors` لا `500`."""

    parent = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreCategory.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = StoreCategory
        fields = [
            "id", "name", "parent", "slug", "sort_order", "is_active",
            "image_url", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class StoreProductAdminSerializer(_ConvertsModelValidationErrors, serializers.ModelSerializer):
    """إدارة كتالوج المتجر المستقلّ (`StoreProduct`) مباشرة.

    THA-166 م٢ (تصحيح): لا تكتب على `inventory.Product` إطلاقاً — القراءةُ
    والكتابةُ ينتقلان معاً. `sale_price ≤ 0` يرفضه `StoreProduct.save()` عند
    الحفظ، ويعود **400** لا **500** عبر `_ConvertsModelValidationErrors`.
    """

    brand = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreBrand.objects.all(), required=False, allow_null=True,
    )
    categories = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreCategory.objects.all(), many=True, required=False,
    )
    images = serializers.SerializerMethodField(read_only=True)
    initial_images = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
        write_only=True,
    )

    class Meta:
        model = StoreProduct
        fields = [
            "id", "name_ar", "name_en", "slug", "brand", "categories", "unit",
            "price", "sale_price", "stock_state", "description", "is_active",
            "sort_order", "images", "initial_images", "imported_from_product_id",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "imported_from_product_id", "created_at"]
        extra_kwargs = {
            "name_ar": {"required": True},
        }

    def get_images(self, obj):
        return list(
            obj.images.order_by("sort_order", "id").values_list("image_url", flat=True)
        )

    def create(self, validated_data):
        initial_images = validated_data.pop("initial_images", [])
        tenant = validated_data.get("tenant")
        product = super().create(validated_data)
        for idx, img_url in enumerate(initial_images):
            if img_url and img_url.strip():
                StoreProductImage.objects.create(
                    tenant=tenant,
                    store_product=product,
                    image_url=img_url.strip(),
                    is_cover=(idx == 0),
                    sort_order=idx + 1,
                )
        return product

    def update(self, instance, validated_data):
        validated_data.pop("initial_images", None)
        return super().update(instance, validated_data)


