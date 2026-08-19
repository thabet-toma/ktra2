from rest_framework import serializers

from core.tenant_utils import get_tenant
from inventory.models import Product, ProductCategory
from store.models import (
    StoreCollection,
    StoreCollectionItem,
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
    """المنتج كما يُنشر للعالم — عشرة حقول صريحة، كلٌّ منها قرار."""

    id = serializers.IntegerField(read_only=True)
    name_ar = serializers.CharField(read_only=True, allow_null=True)
    name_en = serializers.CharField(read_only=True, allow_null=True)
    brand = serializers.CharField(read_only=True, allow_null=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True, allow_null=True
    )
    uom_name = serializers.CharField(
        source="uom.name_ar", read_only=True, allow_null=True
    )
    price = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True, allow_null=True
    )
    availability = serializers.CharField(read_only=True)
    description = serializers.CharField(
        source="online_description", read_only=True, allow_null=True
    )
    images = serializers.SerializerMethodField()
    cover_overlay = serializers.SerializerMethodField(read_only=True)

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

        قراءته من `obj.featured_product` مباشرةً تنشر صنفاً غير منشور أو صنف
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


class StoreProductImageAdminSerializer(serializers.ModelSerializer):
    product = TenantScopedPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = StoreProductImage
        fields = [
            "id", "product", "image_url", "sort_order", "is_cover",
            "caption", "overlay_text", "overlay_style", "overlay_color", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class StoreCollectionItemAdminSerializer(serializers.ModelSerializer):
    collection = TenantScopedPrimaryKeyRelatedField(
        queryset=StoreCollection.objects.all()
    )
    product = TenantScopedPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name_ar", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    price = serializers.DecimalField(
        source="product.online_price", max_digits=18, decimal_places=2, read_only=True, allow_null=True
    )
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = StoreCollectionItem
        fields = [
            "id", "collection", "product", "product_name", "sku", "price", "image_url", "sort_order",
        ]
        read_only_fields = ["id"]

    def get_image_url(self, obj):
        if not obj.product_id:
            return None
        custom = obj.product.store_custom_images.first()
        if custom:
            return custom.image_url
        from core.models import SystemAttachment
        att = SystemAttachment.objects.filter(
            tenant_id=obj.tenant_id,
            related_table="products",
            related_id=obj.product_id,
            file_type__in=["Product Image", "Image"],
        ).first()
        return att.file_path if att else None


class StoreCollectionAdminSerializer(serializers.ModelSerializer):
    featured_product = TenantScopedPrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True
    )
    items_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = StoreCollection
        fields = [
            "id", "title", "slug", "description", "banner_image_url",
            "badge_text", "featured_product", "is_active", "sort_order",
            "items_count", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


#: ما تملك لوحة المتجر تعديله على صنفٍ **مخزني**. `store.manage` صلاحية
#: تسويقية: تنشر الصنف وتسحبه وتصف واجهته، ولا تُعيد تعريفه. `sale_price`
#: و`sku` و`name_ar` تقرؤها الفوترة والتقارير، وتغييرها من هنا يجعل مسؤول
#: تسويق يصيب سعر البيع المعتمَد بلا أن يدري. صنف المتجر الخالص
#: (`is_store_only`) ملكُ اللوحة كاملاً فلا يخضع لهذا الحصر.
STORE_EDITABLE_ON_INVENTORY = frozenset({
    "is_for_sale_online", "allow_preorder", "online_price", "online_description",
})


class StoreProductAdminSerializer(serializers.ModelSerializer):
    """إدارة وإنشاء منتجات المتجر الإلكتروني مباشرة."""

    category = TenantScopedPrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(), required=False, allow_null=True
    )
    category_name = serializers.CharField(
        source="category.name", read_only=True, allow_null=True
    )
    images = serializers.SerializerMethodField(read_only=True)
    initial_images = serializers.ListField(
        child=serializers.CharField(max_length=500),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name_ar",
            "name_en",
            "brand",
            "is_for_sale_online",
            "is_store_only",
            "allow_preorder",
            "online_price",
            "sale_price",
            "online_description",
            "category",
            "category_name",
            "images",
            "initial_images",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "sku": {"required": False, "allow_blank": True},
            "name_ar": {"required": True},
        }

    def get_images(self, obj):
        custom = list(obj.store_custom_images.values_list("image_url", flat=True))
        if custom:
            return custom
        from core.models import SystemAttachment

        return list(
            SystemAttachment.objects.filter(
                tenant_id=obj.tenant_id,
                related_table="products",
                related_id=obj.id,
                file_type__in=["Product Image", "Image"],
            ).values_list("file_path", flat=True)
        )

    def validate(self, attrs):
        """الصنف المخزني: حقول المتجر وحدها. والرمز المُدخل: فريد داخل الشركة."""
        instance = self.instance
        if instance is not None and not instance.is_store_only:
            refused = sorted(set(attrs) - STORE_EDITABLE_ON_INVENTORY)
            if refused:
                raise serializers.ValidationError({
                    field: (
                        "هذا صنف مخزني — لا يُعدَّل هذا الحقل من لوحة المتجر. "
                        "عدّله من شاشة الأصناف بصلاحيتها."
                    )
                    for field in refused
                })

        sku = (attrs.get("sku") or "").strip()
        if sku:
            # عند الإنشاء لا يكون `tenant` في `attrs` بعد — يحقنه العرض عند
            # `save()` — فيُقرأ من سياق الطلب وإلا مرّ التحقّق على لا شيء.
            tenant = (
                attrs.get("tenant")
                or getattr(instance, "tenant", None)
                or get_tenant(self.context.get("request"))
            )
            clash = Product.objects.filter(tenant=tenant, sku=sku)
            if instance is not None:
                clash = clash.exclude(pk=instance.pk)
            if clash.exists():
                # القيد `unique(tenant, sku)` كان يفجّر IntegrityError أي 500 في
                # وجه المستخدم — وهو خطأ إدخالٍ لا انهيار خادم.
                raise serializers.ValidationError(
                    {"sku": "رقم الصنف مستخدم مسبقاً لهذه الشركة."}
                )
        return attrs

    @staticmethod
    def _next_store_sku(tenant):
        """رمزٌ تسلسلي عبر عدّاد المنصة نفسه — لا عشوائيٌّ يتصادم.

        `TenantBook.get_next_number` هو الآلية الذرّية (`select_for_update`)
        التي تُرقّم بها كل مستندات المنصة. التخطّي المحدود يعالج رقماً حجزه
        المستخدم يدوياً بنفس الصيغة.
        """
        from tenants.models import TenantBook

        for _ in range(20):
            number = TenantBook.get_next_number(tenant.pk, "store_product", 0)
            candidate = f"ST-{number:06d}"
            if not Product.objects.filter(tenant=tenant, sku=candidate).exists():
                return candidate
        raise serializers.ValidationError(
            {"sku": "تعذّر توليد رقم صنف — أدخله يدوياً."}
        )

    def create(self, validated_data):
        initial_images = validated_data.pop("initial_images", [])
        tenant = validated_data.get("tenant")

        if not (validated_data.get("sku") or "").strip():
            validated_data["sku"] = self._next_store_sku(tenant)

        validated_data.setdefault("is_store_only", True)
        validated_data.setdefault("is_for_sale_online", True)
        # `allow_preorder` لا يُفرض: «طلب مسبق» وعدٌ تجاري بتوفير الصنف عند
        # الطلب — قرارُ صاحب المتجر لا افتراضُ الكود. يسود افتراضي النموذج.

        product = super().create(validated_data)

        for idx, img_url in enumerate(initial_images):
            if img_url and img_url.strip():
                StoreProductImage.objects.create(
                    tenant=tenant,
                    product=product,
                    image_url=img_url.strip(),
                    is_cover=(idx == 0),
                    sort_order=idx + 1,
                )

        return product


