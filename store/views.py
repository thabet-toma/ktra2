"""المتجر العام — النقاط الوحيدة في المنصة التي تخدم زائراً بلا مصادقة (عدا العملات).

**لماذا app مستقلة:** حجّتها أمنية لا تنظيمية. كل كود `AllowAny` الجديد يعيش في
مجلد واحد يقرؤه مراجعُ الأمن كاملاً في جلسة، ويبقى `inventory/views.py` مئة
بالمئة خلف المصادقة — بدل view عام مدسوس بين عشرين view محمي، حيث يصير سطرٌ
واحد خاطئ في `get_queryset` تسريباً لا يلاحظه أحد.

**ثلاث طبقات تحرس الحمولة**، وكلٌّ تكفي وحدها لو سقطت الأخريان:
1. الاستعلام مقيَّد: `filter(tenant=…, is_for_sale_online=True)` ثم `.only()`
   بالقائمة البيضاء — الرصيد الخام والتكلفة **لا يُحمَّلان من القاعدة أصلاً**.
2. السيريالايزر `Serializer` صِرف بحقول مصرَّحة واحداً واحداً — لا يملك حقلاً
   يحمل ما لم يُقرَّر نشره (`store/serializers.py`).
3. `store/tests/test_public_leakage.py` يقارن **مجموعة** المفاتيح بالقائمة
   البيضاء، فأي حقل يُضاف مستقبلاً يُفشِل البناء لا يمرّ بصمت.

**الشركة تأتي من الـslug في المسار وحده** — لا `X-Tenant-Id` ولا توكن. ولا
مصادقة على الإطلاق (`authentication_classes = []`): توكنٌ يُرسَل إلى نقطة متجر
لا يقدر أن يغيّر حرفاً في الرد، وهي خاصية بنيوية لا وعدٌ في مراجعة.

**الخنق:** `throttle_scope = "store_public"` فوق المصفوفة العامة. الحدّان
يعملان معاً والأضيق هو النافذ — اليوم `anon` (60/دقيقة) لأن `store_public`
افتراضه 120/دقيقة، فالمقبض هنا للتضييق على المتجر وحده بلا لمس بقية المنصة
(`THROTTLE_RATE_STORE`). درس P0-8: نقطة عامة بلا سقف تُشبع الـworkers الثلاثة.
"""
import hashlib

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Case, CharField, DecimalField, F, Q, Value, When
from django.http import Http404
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import SystemAttachment
from core.pagination import EnforcedPageNumberPagination
from inventory.models import Product
from store.models import StoreProductView
from store.serializers import StoreProductSerializer, StoreProfileSerializer
from tenants.models import Tenant

#: الأعمدة التي يُسمح لها بمغادرة القاعدة. ما ليس هنا لا يُحمَّل — بما فيها
#: `quantity_on_hand` و`avg_cost` و`sale_price` و`min_stock_level`.
PUBLIC_PRODUCT_COLUMNS = (
    "id", "name_ar", "name_en", "brand", "online_description",
    "category__name", "uom__name_ar",
)

#: أنواع المرفقات التي تُعدّ صورة منتج. الحصر إيجابي عمداً: «كل ما ليس داتا
#: شيت» كان سينشر أي مرفق يُضاف مستقبلاً (عرض سعر، فاتورة مورد) على الملأ.
#: `Product Image` يكتبها `inventory/views.py`، و`Image` تركتها هجرة الوسائط.
PRODUCT_IMAGE_TYPES = ("Product Image", "Image")

#: مدة كاش القائمة. دقيقةٌ تكفي لامتصاص موجة مشاركةٍ على واتساب، وتُبقي
#: «نشرتُ صنفاً فأين هو؟» ضمن حدود الصبر.
LIST_CACHE_SECONDS = 60


def _availability_expression():
    """حالة التوفّر — نصّ لا رقم، محسوبة في SQL.

    نفس القاعدة المختبَرة في جدول الأصناف (`inventory/views.py` و
    `ProductSerializer.get_stock_status`): نفد ⇐ الرصيد ≤ 0 · محدودة ⇐ رصيد
    موجب لا يتجاوز الحدّ الأدنى (حين يكون الحدّ > 0) · متوفر ⇐ الباقي. الصنف
    الخدمي متوفر دائماً — لا رصيد له أصلاً.

    العتبة هي `min_stock_level` الذي يضبطه صاحب الشركة على كرت الصنف: لا إعداد
    جديد، ولا رقم سحري في كود المتجر.
    """
    return Case(
        When(is_service=True, then=Value("available")),
        When(quantity_on_hand__lte=0, then=Value("out")),
        When(
            min_stock_level__gt=0,
            quantity_on_hand__lte=F("min_stock_level"),
            then=Value("limited"),
        ),
        default=Value("available"),
        output_field=CharField(),
    )


def _price_expression():
    """سعر المتجر — `online_price` الموجب، وإلا `sale_price`.

    **تنبيه رُصد في فحص ST-4:** هذه ليست قاعدة الفوترة. `SalesInvoiceEditor.tsx`
    يبدأ بـ`sale_price` ويسقط إلى `online_price` (الترتيب معكوس)، و`core/pricing.py`
    (`resolve_price`) لا يقرأ `online_price` إطلاقاً. فصنفٌ يحمل السعرين معاً
    يُعلَن هنا بسعرٍ ويُقترح في الفاتورة بآخر — موصوف في `docs/modules/store.md`.
    """
    return Case(
        When(online_price__gt=0, then=F("online_price")),
        default=F("sale_price"),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


def published_products(tenant):
    """أصناف الشركة المنشورة في متجرها — الاستعلام المقيَّد بنيوياً.

    نقطة الدخول الوحيدة لكل قراءة عامة للمنتجات؛ لا نقطة في هذه الـapp تبني
    `Product.objects` بنفسها.
    """
    return (
        Product.objects
        .filter(tenant=tenant, is_for_sale_online=True)
        .select_related("category", "uom")
        .annotate(availability=_availability_expression(), price=_price_expression())
        .only(*PUBLIC_PRODUCT_COLUMNS)
    )


def _image_map(tenant, products):
    """روابط الصور لمجموعة منتجات — استعلام واحد للصفحة، لا واحد لكل صف.

    الروابط عامة أصلاً على Cloudinary (`res.cloudinary.com`) لمن يملكها؛ النشر
    يكشف رابط الصورة ولا يفتح باباً جديداً. `core/media_views.py` يخدم **الرفع**
    لا التسليم، فلا توكن هنا ولا حاجة إليه.
    """
    if not products:
        return {}
    images = {product.id: [] for product in products}
    rows = SystemAttachment.objects.filter(
        tenant=tenant,
        related_table="products",
        related_id__in=list(images),
        file_type__in=PRODUCT_IMAGE_TYPES,
    ).order_by("id").values_list("related_id", "file_path")
    for related_id, file_path in rows:
        if related_id in images and file_path:
            images[related_id].append(file_path)
    return images


def _tenant_or_404(slug):
    """يحلّ الشركة من معرّف متجرها — و404 لكل ما عداه.

    `store_slug = NULL` يعني متجراً مقفلاً؛ ولأن الفلترة بقيمة نصّية غير فارغة
    فإن صفوف NULL لا تُطابَق أبداً — القفل بنيوي لا شرطٌ إضافي يُنسى.
    و**404 لا 403** في كل الحالات: 403 يُثبت وجود الشركة لمن يخمّن المعرّفات.
    """
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
    """`GET /api/store/<slug>/` — بطاقة الشركة من ثوابت المجموعة."""

    def get(self, request, slug):
        tenant = _tenant_or_404(slug)
        settings_row = getattr(tenant, "settings", None)
        # الرمز أولاً («₪») فهو ما يعرفه الزبون، والرمز الدولي («JOD») احتياط
        # لعملة لم يُضبَط رمزها. وبلا عملة مضبوطة يبقى الحقل فارغاً: عملةٌ
        # افتراضية مخترَعة هنا تعني سعراً معروضاً بعملةٍ ليست عملة البائع.
        currency_row = getattr(settings_row, "currency", None)
        payload = {
            "slug": tenant.store_slug,
            # الاسم التجاري في ثوابت المجموعة أولاً — هو ما تريد الشركة أن
            # يُعرَض عليها به؛ واسم السجل احتياطٌ لا يترك البطاقة بلا عنوان.
            "name": (
                getattr(settings_row, "company_name_primary", None)
                or tenant.CompanyName
            ),
            "logo_url": getattr(settings_row, "logo_url", None),
            "phone": getattr(settings_row, "phone", None),
            "address": getattr(settings_row, "address", None),
            "currency": (
                getattr(currency_row, "Symbol", None)
                or getattr(currency_row, "Code", None)
            ),
        }
        return Response(StoreProfileSerializer(payload).data)


class StoreProductListView(StorePublicView):
    """`GET /api/store/<slug>/products/` — بحث وتصفية وفرز وترقيم، مكاشَة دقيقة.

    مفتاح الكاش يحمل الـslug + بصمة معاملات الطلب: عزل الشركة قانونُ المشروع
    ويسري على الكاش كما يسري على الاستعلام — مفتاحٌ بلا slug كان سيقدّم متجر
    شركةٍ لزائر شركةٍ أخرى، وهي بالضبط ثغرة عامل الخدمة في 2026-08-13.

    **الترقيم إلزامي هنا** (`EnforcedPageNumberPagination`) خلافاً لافتراضي
    المشروع الاختياري: كتالوج الأصناف جدولٌ ينمو بلا حدّ — وهي حرفياً حالة
    «الفئة أ» في `core/pagination.py` — والطلب هنا **مجهول**. بلا إلزام يصير
    طلبٌ واحد بـ120 بايت رداً بعدّة ميغابايت، مضروباً في سقف الخنق: مُضخِّم
    إساءةٍ من نفس عائلة درس P0-8. الرد دائماً `{count, next, previous, results}`.
    """

    #: المعاملات التي تدخل بصمة الكاش. ما ليس هنا لا يغيّر النتيجة، فلا يُضخّم
    #: عدد المفاتيح (`utm_*` وحدها كانت ستصنع مفتاحاً لكل رابط مشارَك).
    CACHE_PARAMS = ("q", "brand", "category", "sort", "page", "page_size")

    def _cache_key(self, slug, params):
        fingerprint = "&".join(
            f"{name}={(params.get(name) or '').strip()}"
            for name in self.CACHE_PARAMS
        )
        digest = hashlib.md5(fingerprint.encode("utf-8")).hexdigest()
        return f"store:{slug}:products:{digest}"

    @staticmethod
    def _filtered(queryset, params):
        search = (params.get("q") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(brand__icontains=search)
            )
        brand = (params.get("brand") or "").strip()
        if brand:
            queryset = queryset.filter(brand__iexact=brand)
        category = (params.get("category") or "").strip()
        if category.isdigit():
            # الاستعلام مفلتر بالشركة أصلاً، فتصنيف شركةٍ أخرى يعطي نتيجة
            # فارغة لا تسريباً — ولا حاجة للتحقق من ملكيته بطلب ثانٍ.
            queryset = queryset.filter(category_id=int(category))
        elif category:
            # الاسم أيضاً: الحمولة العامة تنشر `category_name` ولا تنشر المعرّف،
            # فبالمعرّف وحده تعجز واجهة المتجر عن بناء قائمة تصنيفات من نتائجها.
            # نفس حجّة الأمان تسري: الفلترة بالشركة تسبق هذا السطر.
            queryset = queryset.filter(category__name__iexact=category)
        sort = (params.get("sort") or "").strip()
        # مُرتِّبٌ ثانٍ بالمعرّف دائماً: بلا فاصلٍ حاسم تتأرجح الصفوف المتساوية
        # بين الصفحات فيظهر صنفٌ مرتين ويختفي آخر.
        if sort == "price_asc":
            return queryset.order_by("price", "id")
        if sort == "price_desc":
            return queryset.order_by("-price", "id")
        return queryset.order_by("name_ar", "id")

    def get(self, request, slug):
        tenant = _tenant_or_404(slug)
        cache_key = self._cache_key(tenant.store_slug, request.query_params)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        queryset = self._filtered(published_products(tenant), request.query_params)
        paginator = EnforcedPageNumberPagination()
        products = list(paginator.paginate_queryset(queryset, request, view=self))
        data = StoreProductSerializer(
            products, many=True, context={"images": _image_map(tenant, products)},
        ).data
        payload = paginator.get_paginated_response(data).data
        cache.set(cache_key, payload, LIST_CACHE_SECONDS)
        return Response(payload)


class StoreProductDetailView(StorePublicView):
    """`GET /api/store/<slug>/products/<id>/` — صنف واحد، وعدّاد اليوم.

    غير مكاشَة عمداً: هي المسار الذي يكتب العدّاد، وكاشُها يجعل المشاهدات
    تُحتسب مرةً كل دقيقة بدل مرةً لكل زائر.
    """

    def get(self, request, slug, pk):
        tenant = _tenant_or_404(slug)
        # المعرّف يُحلّ **داخل** الاستعلام المقيَّد لا خارجه: صنف شركة أخرى أو
        # صنف غير منشور لا يُوجَد من هنا أصلاً، فيردّ 404 بلا فرعٍ خاص به.
        product = published_products(tenant).filter(pk=pk).first()
        if product is None:
            raise Http404
        self._record_view(tenant, product.id)
        return Response(
            StoreProductSerializer(
                product, context={"images": _image_map(tenant, [product])},
            ).data
        )

    @staticmethod
    def _record_view(tenant, product_id):
        """`+1` ذرّي على صفّ (شركة، صنف، يوم) — بلا قراءة ثم كتابة.

        `UPDATE` أولاً لأنه الحالة الغالبة (أول مشاهدة في اليوم وحدها تُنشئ
        صفّاً)، والإنشاء داخل `atomic` لأن `IntegrityError` يُفسِد المعاملة
        الجارية في PostgreSQL/MySQL ما لم يُعزَل في نقطة حفظ.

        العدّاد ليس بياناً مالياً: لو أخفق، تُفقَد مشاهدة ولا يُحرَم زائرٌ من
        صفحة. لذلك لا يُسمح لخطأ هنا أن يُسقِط الرد.
        """
        today = timezone.localdate()
        rows = StoreProductView.objects.filter(
            tenant=tenant, product_id=product_id, view_date=today,
        ).update(count=F("count") + 1)
        if rows:
            return
        try:
            with transaction.atomic():
                StoreProductView.objects.create(
                    tenant=tenant, product_id=product_id, view_date=today, count=1,
                )
        except IntegrityError:
            # زائرٌ آخر سبقنا إلى إنشاء صفّ اليوم — نزيد صفَّه بدل خلق ثانٍ.
            StoreProductView.objects.filter(
                tenant=tenant, product_id=product_id, view_date=today,
            ).update(count=F("count") + 1)
