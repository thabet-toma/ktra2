"""المتجر العام ولوحة التحكم — خدمة الزوار المجهولين وإدارة المتجر المصادق عليها.

**لماذا app مستقلة:** حجّتها أمنية لا تنظيمية. كل كود `AllowAny` يعيش في
مجلد واحد يقرؤه مراجعُ الأمن كاملاً في جلسة، ويبقى `inventory/views.py` مئة
بالمئة خلف المصادقة.
"""
import hashlib
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F, Max, Min, Prefetch, Q, Value, When,
)
from django.db.models.functions import Coalesce, Least
from django.http import Http404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access import require_perm
from core.mixins import BaseTenantViewSet
from core.models import SystemAttachment
from core.pagination import EnforcedPageNumberPagination
from core.permissions import TemplateSurfacePermission
from core.tenant_utils import get_tenant
from inventory.models import Product
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


def _format_money(value):
    """نصٌّ ثابتُ الخانتين أو `None` — نفس منطق `StoreProductSerializer._money`
    لكن هنا لملخّص `price_range` لا لبند منتج."""
    if value is None:
        return None
    return str(value.quantize(Decimal("0.01")))


def _new_product_days(tenant):
    """عمر «الجديد» بالأيام لهذه الشركة — ٣٠ افتراضاً حين لا صفّ إعداداتٍ أصلاً
    (نفس نمط `_prices_are_public`: غياب الصفّ ليس خطأً)."""
    return getattr(
        getattr(tenant, "store_theme_settings", None), "new_product_days", 30
    )


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
    """`GET /api/store/<slug>/products/` — بحث وتصفية وفرز وترقيم وعدّاداتٌ سياقية.

    **العدّاداتُ سياقيّةٌ بالاستثناء الانفصاليّ (مواصفة #166 م٤):** كلُّ محورٍ
    (فئة، ماركة، رايةٌ، مدى سعر) يُحسَب بعد إسقاط فلترِ نفسِه وحدَه، مع إبقاء
    بقيّة المحاور. **لازمةٌ يجب معرفتها قبل قراءة الأرقام:** مجموعُ عدّاداتِ
    محورٍ انفصاليٍّ (الفئات تحديداً، لأنها M2M) **قد يتجاوز `count`** — منتجٌ
    في فئتين يُحسَب في عدّاد كلٍّ منهما، فمجموعُهما يفوق عدد المنتجات الفعليّ.
    هذا ليس عطباً: هو نفسُ نمط WooCommerce/Algolia الموثَّق في بحث #157.
    """

    #: المعاملات التي تدخل بصمة الكاش. ما ليس هنا لا يغيّر النتيجة، فلا يُضخّم
    #: عدد المفاتيح (`utm_*` وحدها كانت ستصنع مفتاحاً لكل رابط مشارَك).
    CACHE_PARAMS = (
        "q", "brand", "category", "sort", "page", "page_size", "ids",
        "min_price", "max_price", "on_sale", "is_new", "in_stock",
        "include_facets",
    )

    #: سقف معرّفات `ids` — السلة أكبر مستهلك لها، وطلبٌ مجهول لا يُملي طول قائمته.
    MAX_IDS = 60

    #: أسماء محاور الاستثناء الانفصاليّ — تُمرَّر إلى `_filtered(exclude_axis=…)`.
    FACET_AXES = ("brand", "category", "on_sale", "is_new", "in_stock", "price")

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

    @staticmethod
    def _parse_multi(raw):
        """قيمةٌ مفصولةٌ بفواصل ← (معرّفاتٌ، أسماء) — المعرّفاتُ لا الأسماء
        هي طريق تعدّد الاختيار (مواصفة #166 م٤)؛ الاسمُ يبقى مقبولاً للتوافق
        الخلفيّ (الواجهة الحاليّة تستعمله) بمفردٍ كان أو عدّة."""
        ids, names = [], []
        for chunk in (raw or "").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.isdigit():
                ids.append(int(chunk))
            else:
                names.append(chunk)
        return ids, names

    @staticmethod
    def _truthy(raw):
        return (raw or "").strip().lower() in ("1", "true", "yes")

    @staticmethod
    def _parse_decimal(raw):
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    @classmethod
    def _apply_brand(cls, queryset, raw):
        ids, names = cls._parse_multi(raw)
        if not ids and not names:
            return queryset
        q = Q()
        if ids:
            q |= Q(brand_id__in=ids)
        for name in names:
            q |= Q(brand__name__iexact=name)
        return queryset.filter(q)

    @classmethod
    def _apply_category(cls, queryset, raw):
        # `distinct()` **لا** هنا: هذا الفلتر يُستعمَل أيضاً لبناء عدّادات
        # المحاور الأخرى (`_filtered(exclude_axis=…)`)، وقائمةُ النتائج
        # النهائية وحدَها هي التي تحتاج `distinct()` — العدّ يستعمل
        # `Count('id', distinct=True)` بدلاً منه (قسم و في المواصفة).
        ids, names = cls._parse_multi(raw)
        if not ids and not names:
            return queryset
        q = Q()
        if ids:
            q |= Q(categories__id__in=ids)
        for name in names:
            q |= Q(categories__name__iexact=name)
        return queryset.filter(q)

    @classmethod
    def _apply_is_new(cls, queryset, tenant):
        threshold = timezone.now() - timedelta(days=_new_product_days(tenant))
        return queryset.filter(created_at__gte=threshold)

    @classmethod
    def _apply_price_range(cls, queryset, params, prices_public):
        # **حين `show_prices=false` معاملا السعر يُهمَلان تماماً** — لا معنى
        # لفلترة عمودٍ محجوبٍ أصلاً عن القراءة (`published_products`).
        if not prices_public:
            return queryset
        min_price = cls._parse_decimal(params.get("min_price"))
        max_price = cls._parse_decimal(params.get("max_price"))
        if min_price is not None:
            queryset = queryset.filter(effective_price__gte=min_price)
        if max_price is not None:
            queryset = queryset.filter(effective_price__lte=max_price)
        return queryset

    @classmethod
    def _filtered(cls, queryset, params, tenant, exclude_axis=None):
        """يطبّق كلّ الفلاتر عدا `exclude_axis` — هو ما يتيح الاستثناء
        الانفصاليّ: عدّادُ محورٍ يُحسَب بعد إسقاط فلترِ نفسِه وحدَه (قسم ب).

        **كل معاملٍ يُقرَأ هنا يجب أن يدخل `CACHE_PARAMS` أعلاه** — وإلا
        خُدِم قديماً بصمتٍ من الكاش (قسم و). `store/tests/test_store_facets.py`
        (`test_cache_fingerprint_covers_every_filtered_param`) يحرس هذا آلياً.
        """
        # `ids` تخدم إعادة تسعير السلّة بنداءٍ واحد بدل نداءٍ لكل بند. لا تفتح
        # باباً: الاستعلام مفلتر بالشركة والنشر قبل هذا الشرط، فمعرّفُ منتجِ
        # شركةٍ أخرى يعطي فراغاً لا تسريباً. ليست محور استثناءٍ (نطاقٌ لا فلترة).
        raw_ids = (params.get("ids") or "").strip()
        if raw_ids:
            queryset = queryset.filter(id__in=cls._parse_ids(raw_ids))
        # البحث النصّي كذلك ليس محور استثناء — لا عدّاد له في هذه المرحلة.
        search = (params.get("q") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(brand__name__icontains=search)
            )
        if exclude_axis != "brand":
            queryset = cls._apply_brand(queryset, params.get("brand"))
        if exclude_axis != "category":
            queryset = cls._apply_category(queryset, params.get("category"))
        if exclude_axis != "on_sale" and cls._truthy(params.get("on_sale")):
            # خصمٌ سارٍ من `sale_price` أو حملة — تماماً ما يحسبه `effective_price`.
            queryset = queryset.filter(price__isnull=False, effective_price__lt=F("price"))
        if exclude_axis != "is_new" and cls._truthy(params.get("is_new")):
            queryset = cls._apply_is_new(queryset, tenant)
        if exclude_axis != "in_stock" and cls._truthy(params.get("in_stock")):
            # `in_stock` وحدَها — `preorder` مقصودٌ خارج هذا الفلتر (قسم ج).
            queryset = queryset.filter(stock_state=StoreProduct.STOCK_IN_STOCK)
        if exclude_axis != "price":
            queryset = cls._apply_price_range(
                queryset, params, _prices_are_public(tenant)
            )
        return queryset

    @staticmethod
    def _sorted(queryset, params):
        # مُرتِّبٌ ثانٍ بالمعرّف دائماً: بلا فاصلٍ حاسم تتأرجح الصفوف المتساوية
        # بين الصفحات فيظهر منتجٌ مرتين ويختفي آخر. الفرزُ بـ`effective_price`
        # (السعر بعد الخصم) لا بعمود `price` الخام — هو ما يُعرَض فعلياً.
        sort = (params.get("sort") or "").strip()
        if sort == "price_asc":
            return queryset.order_by("effective_price", "id")
        if sort == "price_desc":
            return queryset.order_by("-effective_price", "id")
        return queryset.order_by("name_ar", "id")

    def _category_facet(self, base_qs, params, tenant):
        """عدّادٌ شجريٌّ شاملٌ للأبناء — أبٌ بلا منتجٍ مباشرٍ وتحته ابنٌ بعشرة
        يُظهر عشرة لا صفراً (قسم ج). **العدُّ عدد منتجاتٍ متمايزة لا مجموع
        عدّادات** — منتجٌ موسومٌ بالأب وابنه معاً `M2M` هو الاستعمالُ الطبيعيّ
        لا الشاذّ، وجمعُ عدّادين مباشرين كان يحسبه مرّتين فيَعِد الأبُ بعددٍ
        أكبر من منتجاته الفعليّة (تصحيحٌ بعد المراجعة: هذا عطبٌ مستقلٌّ عن
        لازمة «مجموع عدّاداتِ محاورَ مختلفة قد يتجاوز count» — تلك عن محاور
        منفصلة، وهذه عن قيمةٍ واحدةٍ تكذب على نفسها).

        استعلامان ثابتان بصرف النظر عن عدد الفئات أو المنتجات: قراءةُ أزواج
        (منتج، فئة) خاماً مرّةً واحدة، وقراءةٌ واحدة لشجرة الفئات كاملةً —
        ثم اتحادُ مجموعتي معرّفات المنتجات (الأب + كل ابن) في بايثون، لا
        `SUM` على عدّين مستقلّين."""
        qs = self._filtered(base_qs, params, tenant, exclude_axis="category")
        product_ids_by_category = {}
        for product_id, category_id in (
            qs.exclude(categories__isnull=True).values_list("id", "categories__id")
        ):
            product_ids_by_category.setdefault(category_id, set()).add(product_id)
        categories = list(
            StoreCategory.objects.filter(tenant=tenant, is_active=True)
            .order_by("sort_order", "id")
        )
        children_by_parent = {}
        for c in categories:
            if c.parent_id:
                children_by_parent.setdefault(c.parent_id, []).append(c.id)
        payload = []
        for c in categories:
            own = product_ids_by_category.get(c.id, set())
            if c.parent_id is None:
                union = set(own)
                for child_id in children_by_parent.get(c.id, []):
                    union |= product_ids_by_category.get(child_id, set())
                total = len(union)
            else:
                total = len(own)
            payload.append({
                "id": c.id, "name": c.name, "parent_id": c.parent_id, "count": total,
            })
        return payload

    def _brand_facet(self, base_qs, params, tenant):
        qs = self._filtered(base_qs, params, tenant, exclude_axis="brand")
        rows = (
            qs.exclude(brand_id__isnull=True)
            .values("brand_id", "brand__name", "brand__sort_order")
            .annotate(cnt=Count("id", distinct=True))
            .order_by("brand__sort_order", "brand_id")
        )
        return [
            {"id": row["brand_id"], "name": row["brand__name"], "count": row["cnt"]}
            for row in rows
        ]

    def _flags_facet(self, base_qs, params, tenant, prices_public):
        if prices_public:
            on_sale_qs = self._filtered(base_qs, params, tenant, exclude_axis="on_sale")
            on_sale_count = (
                on_sale_qs.filter(price__isnull=False, effective_price__lt=F("price"))
                .distinct().count()
            )
        else:
            on_sale_count = 0
        is_new_qs = self._filtered(base_qs, params, tenant, exclude_axis="is_new")
        is_new_count = self._apply_is_new(is_new_qs, tenant).distinct().count()
        in_stock_qs = self._filtered(base_qs, params, tenant, exclude_axis="in_stock")
        in_stock_count = (
            in_stock_qs.filter(stock_state=StoreProduct.STOCK_IN_STOCK).distinct().count()
        )
        return {
            "on_sale": on_sale_count,
            "is_new": is_new_count,
            "in_stock": in_stock_count,
        }

    def _price_range_facet(self, base_qs, params, tenant):
        """مدى السعر سياقيٌّ باستثناء فلتر السعر نفسِه — قرارُ استعمالٍ لا
        سابقة (قسم هـ): لو حُسب شاملاً لاختيار الزبون لانطبق المنزلقُ على
        قبضته ولما استطاع توسيعه ثانيةً."""
        qs = self._filtered(base_qs, params, tenant, exclude_axis="price")
        agg = qs.aggregate(min_price=Min("effective_price"), max_price=Max("effective_price"))
        return {
            "min": _format_money(agg["min_price"]),
            "max": _format_money(agg["max_price"]),
        }

    def _build_facets(self, base_qs, params, tenant, prices_public):
        return {
            "categories": self._category_facet(base_qs, params, tenant),
            "brands": self._brand_facet(base_qs, params, tenant),
            "flags": self._flags_facet(base_qs, params, tenant, prices_public),
        }

    def get(self, request, slug):
        tenant = _tenant_or_404(slug)
        cache_key = self._cache_key(tenant, tenant.store_slug, request.query_params)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        base_qs = published_products(tenant)
        queryset = self._sorted(
            self._filtered(base_qs, request.query_params, tenant).distinct(),
            request.query_params,
        )
        paginator = EnforcedPageNumberPagination()
        products = list(paginator.paginate_queryset(queryset, request, view=self))
        prices_public = _prices_are_public(tenant)
        context = _store_media_context(tenant, products)
        context["prices_public"] = prices_public
        data = StoreProductSerializer(products, many=True, context=context).data
        payload = paginator.get_paginated_response(data).data

        # العدّاداتُ تعود عند `page == 1` فقط، وتُحذَف من الصفحات التالية —
        # التصفّحُ لا يغيّرها، وحسابُها في كلّ صفحةٍ إهدارُ تجميعٍ محضٌ على
        # مسارٍ عامٍّ مخنوق. `include_facets=1` يفتحها صراحةً لمن وصل مباشرةً
        # إلى صفحةٍ تالية (قسم أ).
        page_param = (request.query_params.get("page") or "").strip()
        is_first_page = page_param in ("", "1")
        if is_first_page or self._truthy(request.query_params.get("include_facets")):
            payload["facets"] = self._build_facets(base_qs, request.query_params, tenant, prices_public)
            if prices_public:
                payload["price_range"] = self._price_range_facet(
                    base_qs, request.query_params, tenant
                )

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
        queryset = StoreProductListView._sorted(
            StoreProductListView._filtered(
                queryset, request.query_params, tenant
            ).distinct(),
            request.query_params,
        )

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

    #: سقفُ عدد المعرّفات لكل طلب استيراد — لكل عنصرٍ ثلاثةُ استعلامات فعلياً
    #: (`save()` تفحص فرادة الـslug وتكتب `StorePriceHistory`)، فطلبٌ بلا سقفٍ
    #: من مستخدمٍ مصادَقٍ يُشغّل عشرات الآلاف من الاستعلامات (نفس عائلة درس
    #: `MAX_IDS` في `StoreProductListView` أعلاه).
    IMPORT_MAX_IDS = 500

    @action(detail=False, methods=["post"], url_path="import-from-inventory")
    def import_from_inventory(self, request):
        """`POST /api/store/admin/products/import-from-inventory/` — الجسرُ
        الوحيدُ المسموح بين المخزون والمتجر: نسخٌ مرّةً واحدةً بلا علاقةٍ ولا
        مزامنة (مواصفة #166 م٣). لا يمسّ `inventory.Product` بصفٍّ واحد.

        قاعدة السعر مطابقةٌ حرفياً لـ`store/migrations/0006_...` (`_price_expression`
        المجمَّدة): `online_price` الموجب يغلب، وإلا `sale_price`. وكذلك
        `stock_state`: `preorder` إن كان `allow_preorder` وإلا `in_stock` —
        نفس الاشتقاق حرفياً، وإلا هبط المنتج نفسُه بحالتين مختلفتين حسب
        الطريق الذي جاء منه.

        **لا تُنسخ الفئات عمداً** (خلافاً للهجرة التي سطّحت فئات المخزون
        مرّةً واحدة): شجرة فئات المتجر صارت ملكَ التاجر بعد الانفصال، وإعادةُ
        اشتقاق فئاتٍ تسويقيةٍ من فئاتٍ محاسبيةٍ عند كل استيرادٍ تُعيد ربط
        الشجرتين وتُولّد فئاتٍ لم يطلبها أحد. المستورَد يصل بلا فئة، والتاجر
        يصنّفه بنفسه — والواجهة تنبّه لهذا صراحةً (`docs/modules/store.md`).
        """
        tenant = get_tenant(request)
        raw_ids = request.data.get("product_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValidationError({"product_ids": "يجب إرسال قائمة معرّفات أصنافٍ غير فارغة."})
        if len(raw_ids) > self.IMPORT_MAX_IDS:
            raise ValidationError({
                "product_ids": (
                    f"الحدّ الأقصى {self.IMPORT_MAX_IDS} صنفاً في الطلب الواحد "
                    f"— أُرسل {len(raw_ids)}."
                ),
            })
        try:
            product_ids = sorted({int(pid) for pid in raw_ids})
        except (TypeError, ValueError):
            raise ValidationError({"product_ids": "كل معرّفٍ يجب أن يكون رقماً صحيحاً."})

        products = list(
            Product.objects.filter(tenant=tenant, id__in=product_ids)
            .select_related("uom")
            .only(
                "id", "tenant_id", "name_ar", "name_en", "description", "brand",
                "online_price", "sale_price", "allow_preorder", "uom_id", "uom__name_ar",
            )
        )
        found_ids = [p.id for p in products]

        already_imported_ids = set(
            StoreProduct.objects.filter(
                tenant=tenant, imported_from_product_id__in=found_ids,
            ).values_list("imported_from_product_id", flat=True)
        )
        to_import = [p for p in products if p.id not in already_imported_ids]

        # ── الماركات: استعلامان لا استعلامٌ لكل منتج، وأوّل إملاءٍ يبقى ────
        wanted_brand_first_seen = {}
        for p in to_import:
            raw = (p.brand or "").strip()
            if raw:
                wanted_brand_first_seen.setdefault(raw.lower(), raw)
        existing_brands = {
            b.name.strip().lower(): b for b in StoreBrand.objects.filter(tenant=tenant)
        }
        missing_brand_names = [
            name for key, name in wanted_brand_first_seen.items() if key not in existing_brands
        ]
        if missing_brand_names:
            StoreBrand.objects.bulk_create(
                [StoreBrand(tenant=tenant, name=name) for name in missing_brand_names]
            )
            existing_brands = {
                b.name.strip().lower(): b for b in StoreBrand.objects.filter(tenant=tenant)
            }

        # الوحدةُ الطلبُ كلُّه: إمّا استوردتَ ما طلبتَ أو لم تستورد — بلا هذا
        # القفل، فشلٌ في منتصف القائمة يترك دفعةً جزئيةً والرسالةُ التي يراها
        # التاجر تكذب عليه (يقرأ خطأً ويظنّ أن شيئاً لم يقع).
        created = []
        with transaction.atomic():
            for p in to_import:
                brand_key = (p.brand or "").strip().lower()
                brand = existing_brands.get(brand_key) if brand_key else None
                # قاعدة الهجرة 0006 حرفياً — `online_price` الموجب يغلب.
                price = p.online_price if (p.online_price or 0) > 0 else p.sale_price
                stock_state = (
                    StoreProduct.STOCK_PREORDER if p.allow_preorder
                    else StoreProduct.STOCK_IN_STOCK
                )
                uom_name = p.uom.name_ar if p.uom_id and p.uom else ""
                store_product = StoreProduct(
                    tenant=tenant,
                    name_ar=p.name_ar or p.name_en or "",
                    name_en=p.name_en or "",
                    brand=brand,
                    unit=uom_name or "",
                    price=price,
                    stock_state=stock_state,
                    description=p.description or "",
                    imported_from_product_id=p.id,
                )
                # `save()` تبقى داخل الحلقة عمداً — لا `bulk_create`: هي التي
                # تولّد الـslug الفريد وتكتب `StorePriceHistory`، ونقلُهما
                # إلى مسارٍ ثالث يُكرّر منطقاً يعيش في مكانٍ واحد بالفعل.
                # السقفُ أعلاه (`IMPORT_MAX_IDS`) هو ما يحدّ كلفة الاستعلامات
                # هنا، لا استبدال `save()`.
                store_product.save()
                created.append(store_product)

        skipped_count = len(already_imported_ids)
        imported_count = len(created)
        if imported_count and skipped_count:
            message = f"{imported_count} استُوردت، {skipped_count} كانت مستوردةً سلفاً."
        elif imported_count:
            message = f"{imported_count} استُوردت."
        elif skipped_count:
            message = f"لا جديد — {skipped_count} كانت مستوردةً سلفاً."
        else:
            message = "لم يُعثر على أصنافٍ صالحة للاستيراد."

        return Response({
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "imported_ids": [sp.id for sp in created],
            "message": message,
        })


