"""المتجر العام ولوحة التحكم — خدمة الزوار المجهولين وإدارة المتجر المصادق عليها.

**لماذا app مستقلة:** حجّتها أمنية لا تنظيمية. كل كود `AllowAny` يعيش في
مجلد واحد يقرؤه مراجعُ الأمن كاملاً في جلسة، ويبقى `inventory/views.py` مئة
بالمئة خلف المصادقة.
"""
import hashlib
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F, Max, Prefetch, Q, Value, When,
)
from django.db.models.functions import Coalesce, Least
from django.http import Http404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access import require_perm
from core.mixins import BaseTenantViewSet
from core.models import SystemAttachment
from core.pagination import EnforcedPageNumberPagination
from core.permissions import TemplateSurfacePermission
from core.tenant_utils import get_tenant
from store.cache import InvalidatesStoreCacheMixin, products_version
from store.models import (
    StoreBrand,
    StoreCategory,
    StoreCollection,
    StoreCollectionItem,
    StoreProduct,
    StoreProductImage,
    StoreProductView,
    StoreSettings,
)
from store.serializers import (
    StoreBrandAdminSerializer,
    StoreCategoryAdminSerializer,
    StoreCollectionAdminSerializer,
    StoreCollectionDetailSerializer,
    StoreCollectionItemAdminSerializer,
    StoreCollectionSerializer,
    StoreProductAdminSerializer,
    StoreProductImageAdminSerializer,
    StoreProductSerializer,
    StoreProfileSerializer,
    StoreSettingsAdminSerializer,
)
from tenants.models import Tenant

#: أنواع المرفقات التي تُعدّ صورة منتج. الحصر إيجابي عمداً: «كل ما ليس داتا
#: شيت» كان سينشر أي مرفق يُضاف مستقبلاً (عرض سعر، فاتورة مورد) على الملأ.
#: `Product Image` يكتبها `inventory/views.py`، و`Image` تركتها هجرة الوسائط.
PRODUCT_IMAGE_TYPES = ("Product Image", "Image")

#: مدة كاش القائمة. دقيقةٌ تكفي لامتصاص موجة مشاركةٍ على واتساب، وكتابات
#: النشر تُبطله فوراً عبر `store/cache.py` فلا ينتظر صاحب المتجر انتهاءها.
#: **وسقفٌ لظهور/اختفاء الحملات أيضاً** (THA-166 M2): بدء أو انتهاء حملةٍ حدثُ
#: ساعةٍ لا حدثُ حفظٍ يُبطل الكاش، فهذا الرقم هو أقصى تأخيرٍ ممكن لظهور خصمٍ
#: جديد أو اختفاء خصمٍ منتهٍ. يجب أن يبقى ≤ 300 (خمس دقائق).
LIST_CACHE_SECONDS = 60


def _hidden_price_expression():
    """السعر محجوب — ثابتُ `NULL` لا يقرأ عمود السعر من القاعدة أصلاً.

    الحجب هنا لا في العرض ولا في الواجهة: ما لا يُقرَّر نشره لا يغادر القاعدة.
    """
    return Value(None, output_field=DecimalField(max_digits=18, decimal_places=2))


def _prices_are_public(tenant) -> bool:
    """هل يُعلن هذا المتجر أسعاره؟ غياب صفّ الإعدادات يعني نعم (الافتراضي)."""
    return getattr(
        getattr(tenant, "store_theme_settings", None), "show_prices", True
    )


def _active_campaign_discount_percent():
    """أعلى نسبة خصم حملةٍ **سارية الآن** يشترك فيها المنتج — `Max` عبر ضمّ
    على العلاقة العكسيّة، لا استعلامٌ مترابطٌ لكلّ صف (THA-166 M2).

    **لا يُستعمَل `__date` إطلاقاً**: جداول المناطق الزمنية الفارغة في MySQL
    تجعله يعيد صفر صفوفٍ بلا أيّ خطأ (`core/date_ranges.py`) — وحملةٌ لا تبدأ
    في موعدها عطبٌ صامتٌ من هذا النوع بالضبط. المقارنة على `datetime` مباشرةً.
    """
    now = timezone.now()
    is_active_now = (
        Q(collection_items__collection__is_active=True)
        & (
            Q(collection_items__collection__starts_at__isnull=True)
            | Q(collection_items__collection__starts_at__lte=now)
        )
        & (
            Q(collection_items__collection__ends_at__isnull=True)
            | Q(collection_items__collection__ends_at__gte=now)
        )
    )
    return Max("collection_items__collection__discount_percent", filter=is_active_now)


def published_products(tenant):
    """منتجات كتالوج المتجر المستقلّ المنشورة — الاستعلام المقيَّد بنيوياً.

    بوابةٌ واحدة تمرّ منها المسارات الثلاثة (القائمة، المنتج، صفحة الحملة)،
    فحجبُ السعر وحساب الخصم هنا يغطّيانها كلَّها بالبناء لا بثلاثة شروط تُنسى
    إحداها (THA-166 M2).

    `effective_price` هو السعر الفعليّ بعد أكبر خصمٍ ينطبق — منتجٍ مفردٍ أو
    حملة، الأكبر يفوز — مُحسَبٌ في SQL لا بايثون لأنه ما سيُفرَز به ويُفلتَر
    عليه في مرحلةٍ تالية.
    """
    qs = (
        StoreProduct.objects.filter(tenant=tenant, is_active=True)
        .select_related("brand")
        .prefetch_related(
            Prefetch(
                "categories",
                queryset=StoreCategory.objects.order_by("sort_order", "id"),
            )
        )
    )
    if not _prices_are_public(tenant):
        return qs.annotate(effective_price=_hidden_price_expression()).defer(
            "price", "sale_price"
        )

    qs = qs.annotate(campaign_discount_percent=_active_campaign_discount_percent())
    qs = qs.annotate(
        campaign_price=Case(
            When(
                Q(campaign_discount_percent__gt=0) & Q(price__isnull=False),
                then=ExpressionWrapper(
                    F("price")
                    * (Value(Decimal("100")) - F("campaign_discount_percent"))
                    / Value(Decimal("100")),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                ),
            ),
            default=Value(None, output_field=DecimalField(max_digits=18, decimal_places=4)),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        )
    )
    # الأكبر خصماً يفوز: أصغر سعرٍ بين خصم المنتج المفرد (`sale_price`، مبلغٌ
    # مطلق) وخصم الحملة (`campaign_price`)، بعد تعويض الغائب بالسعر الأساس
    # (`Coalesce`) — وإلا أبطل `LEAST`/`MIN` القياسيّ الناتجَ كلّه بـ`NULL`
    # حين يغيب أحد طرفيه. هذا التعويض نفسه هو ما يضمن ألّا يتجاوز الناتج
    # السعرَ الأساس أبداً (فلا يُعرَض «خصمٌ» أعلى من السعر — الحارس الأوّل).
    return qs.annotate(
        effective_price=Case(
            When(
                price__isnull=True,
                then=Value(None, output_field=DecimalField(max_digits=18, decimal_places=2)),
            ),
            default=Least(
                Coalesce(F("sale_price"), F("price"), output_field=DecimalField(max_digits=18, decimal_places=4)),
                Coalesce(F("campaign_price"), F("price"), output_field=DecimalField(max_digits=18, decimal_places=4)),
            ),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )


def _store_media_context(tenant, products):
    """روابط الصور والنصوص الإعلانية المخصصة لمجموعة منتجات — استعلام مجمّع."""
    if not products:
        return {"images": {}, "cover_overlays": {}}
    products = [p for p in products if p]
    product_ids = [p.id for p in products]
    images = {pid: [] for pid in product_ids}
    cover_overlays = {}

    # 1. صور المتجر المخصصة أولاً مع النصوص الإعلانية
    custom_rows = (
        StoreProductImage.objects.filter(
            tenant=tenant,
            store_product_id__in=product_ids,
        )
        .order_by("-is_cover", "sort_order", "id")
        .values(
            "store_product_id",
            "image_url",
            "overlay_text",
            "overlay_style",
            "overlay_color",
            "is_cover",
        )
    )
    for row in custom_rows:
        pid = row["store_product_id"]
        img_url = row["image_url"]
        if pid in images and img_url:
            images[pid].append(img_url)
            if row["is_cover"] and row["overlay_text"] and pid not in cover_overlays:
                cover_overlays[pid] = {
                    "text": row["overlay_text"],
                    "style": row["overlay_style"] or "diagonal_ribbon",
                    "color": row["overlay_color"] or "red_fire",
                }

    # 2. للمنتجات المستوردة من صنفٍ مخزني ولا صورة متجر مخصّصة لها: نسقط إلى
    #    صور المنتج العامة من `SystemAttachment` — منتجٌ أنشأه التاجر من الصفر
    #    لا مرفقاتِ مخزونٍ له أصلاً فلا معنى لهذا السقوط بالنسبة له.
    fallback_targets = {
        p.id: p.imported_from_product_id
        for p in products
        if p.imported_from_product_id and not images.get(p.id)
    }
    if fallback_targets:
        reverse_map = {}
        for store_pid, inv_pid in fallback_targets.items():
            reverse_map.setdefault(inv_pid, []).append(store_pid)
        rows = (
            SystemAttachment.objects.filter(
                tenant=tenant,
                related_table="products",
                related_id__in=list(reverse_map),
                file_type__in=PRODUCT_IMAGE_TYPES,
            )
            .order_by("id")
            .values_list("related_id", "file_path")
        )
        for related_id, file_path in rows:
            if not file_path:
                continue
            for store_pid in reverse_map.get(related_id, ()):
                images[store_pid].append(file_path)

    return {"images": images, "cover_overlays": cover_overlays}


def _image_map(tenant, products):
    """روابط الصور لمجموعة منتجات — استعلام مجمّع، أولوية لصور المتجر المخصصة."""
    return _store_media_context(tenant, products)["images"]


def _tenant_or_404(slug):
    """يحلّ الشركة من معرّف متجرها — و404 لكل ما عداه."""
    slug = (slug or "").strip().lower()
    if not slug:
        raise Http404
    tenant = Tenant.objects.filter(store_slug=slug).first()
    if tenant is None:
        raise Http404
    return tenant


class StorePublicView(APIView):
    """الأساس المشترك: بلا مصادقة، مفتوح للجميع، مخنوق بنطاقه الخاص."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "store_public"


class StoreProfileView(StorePublicView):
    """`GET /api/store/<slug>/` — بطاقة الشركة وإعدادات المظهر والهوية."""

    def get(self, request, slug):
        tenant = _tenant_or_404(slug)
        settings_row = getattr(tenant, "settings", None)
        currency_row = getattr(settings_row, "currency", None)
        theme_row = getattr(tenant, "store_theme_settings", None)
        payload = {
            "slug": tenant.store_slug,
            # الاسم التجاري في ثوابت المجموعة أولاً — هو ما تريد الشركة أن
            # يُعرَض عليها به؛ واسم السجل احتياطٌ لا يترك البطاقة بلا عنوان.
            "name": (
                getattr(settings_row, "company_name_primary", None)
                or tenant.CompanyName
            ),
            "logo_url": getattr(settings_row, "logo_url", None),
            "phone": getattr(theme_row, "whatsapp_number", None) or getattr(settings_row, "phone", None),
            "address": getattr(settings_row, "address", None),
            # الرمز أولاً («₪») فهو ما يعرفه الزبون، والرمز الدولي («JOD») احتياط
            # لعملة لم يُضبَط رمزها. وبلا عملة مضبوطة يبقى الحقل فارغاً: عملةٌ
            # افتراضية مخترَعة هنا تعني سعراً معروضاً بعملةٍ ليست عملة البائع.
            "currency": (
                getattr(currency_row, "Symbol", None)
                or getattr(currency_row, "Code", None)
            ),
            "hero_title": getattr(theme_row, "hero_title", None) or "",
            "hero_subtitle": getattr(theme_row, "hero_subtitle", None) or "",
            "announcement_bar": getattr(theme_row, "announcement_bar", None) or "",
            "show_announcement": getattr(theme_row, "show_announcement", True),
            "theme_preset": getattr(theme_row, "theme_preset", "default") or "default",
            "primary_color": getattr(theme_row, "primary_color", "#2563eb") or "#2563eb",
            "accent_color": getattr(theme_row, "accent_color", "#f59e0b") or "#f59e0b",
            "background_color": getattr(theme_row, "background_color", "#f8fafc") or "#f8fafc",
            "background_image_url": getattr(theme_row, "background_image_url", None),
            "background_style": getattr(theme_row, "background_style", "cover") or "cover",
            "banner_image_url": getattr(theme_row, "banner_image_url", None),
            "instagram_url": getattr(theme_row, "instagram_url", None),
            "tiktok_url": getattr(theme_row, "tiktok_url", None),
            "facebook_url": getattr(theme_row, "facebook_url", None),
            "snapchat_url": getattr(theme_row, "snapchat_url", None),
            "whatsapp_number": getattr(theme_row, "whatsapp_number", None),
            "catalog_mode_default": getattr(theme_row, "catalog_mode_default", "grid") or "grid",
            "allow_cart": getattr(theme_row, "allow_cart", True),
            # الواجهة تحتاج معرفة الحالة لتُخفي الفرز بالسعر ومبالغ السلة.
            "show_prices": getattr(theme_row, "show_prices", True),
        }
        return Response(StoreProfileSerializer(payload).data)


class StoreProductListView(StorePublicView):
    """`GET /api/store/<slug>/products/` — بحث وتصفية وفرز وترقيم، مكاشَة دقيقة."""

    #: المعاملات التي تدخل بصمة الكاش. ما ليس هنا لا يغيّر النتيجة، فلا يُضخّم
    #: عدد المفاتيح (`utm_*` وحدها كانت ستصنع مفتاحاً لكل رابط مشارَك).
    CACHE_PARAMS = ("q", "brand", "category", "sort", "page", "page_size", "ids")

    #: سقف معرّفات `ids` — السلة أكبر مستهلك لها، وطلبٌ مجهول لا يُملي طول قائمته.
    MAX_IDS = 60

    def _cache_key(self, tenant, slug, params):
        """مفتاح يحمل الـslug (عزل الشركة) والنسخة (الإبطال عند النشر)."""
        fingerprint = "&".join(
            f"{name}={(params.get(name) or '').strip()}"
            for name in self.CACHE_PARAMS
        )
        digest = hashlib.md5(fingerprint.encode("utf-8")).hexdigest()
        version = products_version(tenant.pk)
        return f"store:{slug}:products:v{version}:{digest}"

    @classmethod
    def _parse_ids(cls, raw):
        """معرّفات مفصولة بفواصل — ما ليس رقماً موجباً يُهمل، والعدد مسقوف."""
        wanted = []
        for chunk in (raw or "").split(",")[: cls.MAX_IDS]:
            chunk = chunk.strip()
            if chunk.isdigit() and int(chunk) > 0:
                wanted.append(int(chunk))
        return wanted

    @classmethod
    def _filtered(cls, queryset, params):
        # `ids` تخدم إعادة تسعير السلّة بنداءٍ واحد بدل نداءٍ لكل بند. لا تفتح
        # باباً: الاستعلام مفلتر بالشركة والنشر قبل هذا الشرط، فمعرّفُ منتجِ
        # شركةٍ أخرى يعطي فراغاً لا تسريباً.
        raw_ids = (params.get("ids") or "").strip()
        if raw_ids:
            queryset = queryset.filter(id__in=cls._parse_ids(raw_ids))
        search = (params.get("q") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(brand__name__icontains=search)
            )
        brand = (params.get("brand") or "").strip()
        if brand:
            queryset = queryset.filter(brand__name__iexact=brand)
        # الاستعلام مفلتر بالشركة أصلاً، فتصنيف شركةٍ أخرى يعطي نتيجة فارغة لا
        # تسريباً. والاسم مقبول كالمعرّف: الحمولة العامة تنشر `category_name`
        # ولا تنشر معرّف الفئة الأولى وحدَها، فبالمعرّف وحده تعجز الواجهة عن
        # بناء قائمة تصنيفات. `distinct()` لأن `categories` علاقةُ M2M — منتجٌ
        # في أكثر من فئة يتكرّر صفّه في الضمّ بلا هذا.
        category = (params.get("category") or "").strip()
        if category.isdigit():
            queryset = queryset.filter(categories__id=int(category)).distinct()
        elif category:
            queryset = queryset.filter(categories__name__iexact=category).distinct()
        # مُرتِّبٌ ثانٍ بالمعرّف دائماً: بلا فاصلٍ حاسم تتأرجح الصفوف المتساوية
        # بين الصفحات فيظهر منتجٌ مرتين ويختفي آخر. الفرزُ بـ`effective_price`
        # (السعر بعد الخصم) لا بعمود `price` الخام — هو ما يُعرَض فعلياً.
        sort = (params.get("sort") or "").strip()
        if sort == "price_asc":
            return queryset.order_by("effective_price", "id")
        if sort == "price_desc":
            return queryset.order_by("-effective_price", "id")
        return queryset.order_by("name_ar", "id")

    def get(self, request, slug):
        tenant = _tenant_or_404(slug)
        cache_key = self._cache_key(tenant, tenant.store_slug, request.query_params)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        queryset = self._filtered(published_products(tenant), request.query_params)
        paginator = EnforcedPageNumberPagination()
        products = list(paginator.paginate_queryset(queryset, request, view=self))
        context = _store_media_context(tenant, products)
        context["prices_public"] = _prices_are_public(tenant)
        data = StoreProductSerializer(products, many=True, context=context).data
        payload = paginator.get_paginated_response(data).data
        cache.set(cache_key, payload, LIST_CACHE_SECONDS)
        return Response(payload)


class StoreProductDetailView(StorePublicView):
    """`GET /api/store/<slug>/products/<id>/` — منتج واحد، وعدّاد اليوم."""

    def get(self, request, slug, pk):
        tenant = _tenant_or_404(slug)
        # المعرّف يُحلّ **داخل** الاستعلام المقيَّد لا خارجه: منتج شركة أخرى أو
        # منتج غير منشور لا يُوجَد من هنا أصلاً، فيردّ 404 بلا فرعٍ خاص به.
        product = published_products(tenant).filter(pk=pk).first()
        if product is None:
            raise Http404
        self._record_view(tenant, product.id)
        context = _store_media_context(tenant, [product])
        context["prices_public"] = _prices_are_public(tenant)
        return Response(StoreProductSerializer(product, context=context).data)

    @staticmethod
    def _record_view(tenant, store_product_id):
        today = timezone.localdate()
        rows = StoreProductView.objects.filter(
            tenant=tenant, store_product_id=store_product_id, view_date=today,
        ).update(count=F("count") + 1)
        if rows:
            return
        try:
            with transaction.atomic():
                StoreProductView.objects.create(
                    tenant=tenant, store_product_id=store_product_id,
                    view_date=today, count=1,
                )
        except IntegrityError:
            # زائرٌ آخر سبقنا إلى إنشاء صفّ اليوم — نزيد صفَّه بدل خلق ثانٍ.
            StoreProductView.objects.filter(
                tenant=tenant, store_product_id=store_product_id, view_date=today,
            ).update(count=F("count") + 1)


class StoreCollectionListView(StorePublicView):
    """`GET /api/store/<slug>/collections/` — المجموعات والحملات الترويجية النشطة."""

    def get(self, request, slug):
        tenant = _tenant_or_404(slug)
        collections = (
            StoreCollection.objects.filter(tenant=tenant, is_active=True)
            .annotate(items_count=Count("items"))
            .order_by("sort_order", "id")
        )
        # الترقيم إلزامي كقائمة المنتجات: قائمةٌ تنمو بلا حدّ خلف نقطة مجهولة
        # مُضخِّم إساءة لا خيار عرض — درس P0-8 نفسه.
        paginator = EnforcedPageNumberPagination()
        page = paginator.paginate_queryset(collections, request, view=self)
        data = StoreCollectionSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class StoreCollectionDetailView(StorePublicView):
    """`GET /api/store/<slug>/collections/<collection_slug>/` — صفحة الهبوط للحملة ومنتجاتها."""

    def get(self, request, slug, collection_slug):
        tenant = _tenant_or_404(slug)
        collection = (
            StoreCollection.objects.filter(
                tenant=tenant, slug=collection_slug, is_active=True
            ).first()
        )
        if collection is None:
            raise Http404

        product_ids = list(
            StoreCollectionItem.objects.filter(collection=collection)
            .order_by("sort_order", "id")
            .values_list("store_product_id", flat=True)
        )
        queryset = published_products(tenant).filter(id__in=product_ids)
        queryset = StoreProductListView._filtered(queryset, request.query_params)

        paginator = EnforcedPageNumberPagination()
        products = list(paginator.paginate_queryset(queryset, request, view=self))
        prices_public = _prices_are_public(tenant)

        # المنتج المميّز يمرّ من نفس بوابة النشر عبر `featured_store_product` —
        # المرساةُ الحيّة منذ تصحيح تقسيم المراحل (`featured_product` القديم
        # يبقى يشير إلى `inventory.Product` بلا حذف، لكنه لم يعد يُقرأ هنا).
        featured = None
        if collection.featured_store_product_id:
            featured = (
                published_products(tenant)
                .filter(pk=collection.featured_store_product_id)
                .first()
            )
        featured_context = _store_media_context(tenant, [featured] if featured else [])
        featured_context["featured_product"] = featured
        featured_context["prices_public"] = prices_public
        collection_data = StoreCollectionDetailSerializer(
            collection, context=featured_context
        ).data
        products_context = _store_media_context(tenant, products)
        products_context["prices_public"] = prices_public
        products_data = StoreProductSerializer(
            products, many=True, context=products_context
        ).data
        paginated_products = paginator.get_paginated_response(products_data).data

        return Response({
            "collection": collection_data,
            "products": paginated_products,
        })


# ── واجهات إدارة المتجر المصادق عليها (Store Admin) ────────────────────────


class StoreSettingsAdminView(InvalidatesStoreCacheMixin, APIView):
    """`GET /api/store/admin/settings/` و`PATCH` — إدارة مظهر وهوية المتجر."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]

    def get(self, request):
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)
        settings_obj, _ = StoreSettings.objects.get_or_create(tenant=tenant)
        return Response(StoreSettingsAdminSerializer(settings_obj).data)

    def patch(self, request):
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)
        settings_obj, _ = StoreSettings.objects.get_or_create(tenant=tenant)
        serializer = StoreSettingsAdminSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def post(self, request):
        return self.patch(request)


class StoreProductImageAdminViewSet(InvalidatesStoreCacheMixin, BaseTenantViewSet):
    """إدارة صور المتجر المخصصة لمنتجات الكتالوج المستقلّ (`StoreProduct`)."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]
    serializer_class = StoreProductImageAdminSerializer
    queryset = StoreProductImage.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)

    def get_queryset(self):
        qs = super().get_queryset()
        store_product_id = self.request.query_params.get("store_product_id")
        if store_product_id and store_product_id.isdigit():
            qs = qs.filter(store_product_id=int(store_product_id))
        return qs.order_by("sort_order", "id")

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        # إذا تم تعيينها كـ cover، نقوم بإلغاء cover عن الصور الأخرى لهذا المنتج
        is_cover = serializer.validated_data.get("is_cover", False)
        store_product = serializer.validated_data.get("store_product")
        if is_cover and store_product:
            StoreProductImage.objects.filter(
                tenant=tenant, store_product=store_product
            ).update(is_cover=False)
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        is_cover = serializer.validated_data.get("is_cover")
        instance = serializer.instance
        if is_cover and instance:
            StoreProductImage.objects.filter(
                tenant=instance.tenant, store_product=instance.store_product
            ).exclude(pk=instance.pk).update(is_cover=False)
        serializer.save()


class StoreCollectionAdminViewSet(InvalidatesStoreCacheMixin, BaseTenantViewSet):
    """إدارة المجموعات والحملات الإعلانية وصفحات الهبوط."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]
    serializer_class = StoreCollectionAdminSerializer
    queryset = StoreCollection.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.annotate(items_count=Count("items")).order_by("sort_order", "id")


class StoreCollectionItemAdminViewSet(InvalidatesStoreCacheMixin, BaseTenantViewSet):
    """إدارة المنتجات داخل المجموعة الإعلانية."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]
    serializer_class = StoreCollectionItemAdminSerializer
    queryset = StoreCollectionItem.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)

    def get_queryset(self):
        qs = super().get_queryset()
        collection_id = self.request.query_params.get("collection_id")
        if collection_id and collection_id.isdigit():
            qs = qs.filter(collection_id=int(collection_id))
        return qs.select_related("store_product").order_by("sort_order", "id")


class StoreBrandAdminViewSet(InvalidatesStoreCacheMixin, BaseTenantViewSet):
    """إدارة ماركات كتالوج المتجر المستقلّ (THA-166 م٢)."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]
    serializer_class = StoreBrandAdminSerializer
    queryset = StoreBrand.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)

    def get_queryset(self):
        return super().get_queryset().order_by("sort_order", "id")


class StoreCategoryAdminViewSet(InvalidatesStoreCacheMixin, BaseTenantViewSet):
    """إدارة فئات كتالوج المتجر المستقلّ — شجرةٌ بمستويين محروسة عند الحفظ
    (THA-166 م٢)."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]
    serializer_class = StoreCategoryAdminSerializer
    queryset = StoreCategory.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)

    def get_queryset(self):
        return super().get_queryset().select_related("parent").order_by("sort_order", "id")


class StoreProductAdminViewSet(InvalidatesStoreCacheMixin, BaseTenantViewSet):
    """إدارة كتالوج المتجر المستقلّ (`StoreProduct`) مباشرة — لا تكتب على
    `inventory.Product` إطلاقاً (THA-166 م٢ تصحيح: القراءةُ والكتابةُ
    ينتقلان معاً، لا مساراً يقرأ من جدولٍ ويكتب في آخر)."""

    permission_classes = [IsAuthenticated, TemplateSurfacePermission]
    serializer_class = StoreProductAdminSerializer
    queryset = StoreProduct.objects.all()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = get_tenant(request)
        require_perm(request, "store.manage", tenant=tenant)

    def get_queryset(self):
        qs = super().get_queryset().select_related("brand").prefetch_related("categories")
        scope = self.request.query_params.get("scope")
        search = (self.request.query_params.get("search") or "").strip()

        if scope == "published":
            qs = qs.filter(is_active=True)
        elif scope == "unpublished":
            qs = qs.filter(is_active=False)

        if search:
            qs = qs.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(brand__name__icontains=search)
            )

        return qs.order_by("-created_at", "-id")


