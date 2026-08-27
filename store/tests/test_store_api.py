"""سلوك تصفّح المتجر: التوفّر، والبحث والتصفية والفرز، والصور، والكاش.

عزل التسريب في `test_public_leakage.py`؛ هذا الملف يغطّي ما يراه الزائر فعلاً
حين يتصفّح — وطبقةَ الكاش التي هي بنفسها سطحُ عزلٍ يجب أن يُثبَت.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import SystemAttachment
from inventory.models import Product, ProductCategory, UnitOfMeasure
from store.views import StoreProductListView, published_products
from tenants.models import Tenant

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _product(tenant, sku, **kwargs):
    defaults = dict(
        name_ar=f"منتج {sku}", name_en=f"Item {sku}", brand="عام",
        is_for_sale_online=True, quantity_on_hand=Decimal("10"),
        avg_cost=Decimal("3"), online_price=Decimal("10.00"),
    )
    defaults.update(kwargs)
    return Product.objects.create(tenant=tenant, sku=sku, **defaults)


class StoreBrowseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uom = UnitOfMeasure.objects.create(
            code="BOX", name_ar="صندوق", name_en="Box")
        cls.tenant = Tenant.objects.create(
            CompanyName="متجر التجربة", SubscriptionPlan="Pro", Status="Active",
            store_slug="demo")
        cls.tyres = ProductCategory.objects.create(tenant=cls.tenant, name="إطارات")
        cls.oils = ProductCategory.objects.create(tenant=cls.tenant, name="زيوت")

        cls.in_stock = _product(
            cls.tenant, "S-IN", name_ar="إطار متوفر", brand="ميشلان",
            category=cls.tyres, uom=cls.uom, min_stock_level=3,
            quantity_on_hand=Decimal("20"), online_price=Decimal("50.00"))
        cls.limited = _product(
            cls.tenant, "S-LOW", name_ar="إطار شحيح", brand="بريجستون",
            category=cls.tyres, min_stock_level=5,
            quantity_on_hand=Decimal("4"), online_price=Decimal("70.00"))
        cls.out = _product(
            cls.tenant, "S-OUT", name_ar="زيت نافد", brand="شل",
            category=cls.oils, min_stock_level=2,
            quantity_on_hand=Decimal("0"), online_price=Decimal("12.00"))
        cls.service = _product(
            cls.tenant, "S-SRV", name_ar="خدمة تركيب", brand="محلي",
            category=cls.oils, is_service=True,
            quantity_on_hand=Decimal("0"), online_price=Decimal("5.00"))

    def setUp(self):
        self.client = APIClient()

    def _list(self, **params):
        res = self.client.get("/api/store/demo/products/", params)
        self.assertEqual(res.status_code, 200, res.content[:300])
        payload = res.json()
        return payload["results"] if isinstance(payload, dict) else payload

    def _by_id(self):
        return {item["id"]: item for item in self._list()}

    # ── التوفّر: حالة مشتقّة بنفس قاعدة جدول المنتجات ──────────────────────
    def test_availability_states_follow_the_min_stock_level_rule(self):
        items = self._by_id()
        self.assertEqual(items[self.in_stock.id]["availability"], "available")
        self.assertEqual(items[self.limited.id]["availability"], "limited")
        self.assertEqual(items[self.out.id]["availability"], "out")

    def test_a_service_is_always_available(self):
        """الخدمة بلا رصيد — «نفد» عليها خطأ يقرؤه الزبون فلا يطلبها."""
        self.assertEqual(self._by_id()[self.service.id]["availability"], "available")

    def test_zero_min_stock_level_never_yields_limited(self):
        """حدّ أدنى غير مضبوط ⇒ لا «كمية محدودة» — لا نخترع عتبة للمالك."""
        loose = _product(
            self.tenant, "S-NOMIN", min_stock_level=None,
            quantity_on_hand=Decimal("1"))
        self.assertEqual(self._by_id()[loose.id]["availability"], "available")

    # ── السعر ────────────────────────────────────────────────────────────
    def test_price_prefers_the_online_price(self):
        self.assertEqual(self._by_id()[self.in_stock.id]["price"], "50.00")

    def test_price_falls_back_to_sale_price_when_no_online_price(self):
        """نفس قاعدة محرّر الفاتورة: `online_price` الموجب أولاً، ثم سعر البيع."""
        fallback = _product(
            self.tenant, "S-FALL", online_price=None,
            sale_price=Decimal("33.0000"))
        self.assertEqual(self._by_id()[fallback.id]["price"], "33.00")

    # ── البحث والتصفية والفرز ────────────────────────────────────────────
    def test_search_matches_arabic_name_and_brand(self):
        self.assertEqual(
            {item["id"] for item in self._list(q="شحيح")}, {self.limited.id})
        self.assertEqual(
            {item["id"] for item in self._list(q="ميشلان")}, {self.in_stock.id})

    def test_brand_and_category_filters(self):
        self.assertEqual(
            {item["id"] for item in self._list(brand="شل")}, {self.out.id})
        self.assertEqual(
            {item["id"] for item in self._list(category=self.tyres.id)},
            {self.in_stock.id, self.limited.id},
        )

    def test_the_category_filter_also_accepts_the_published_name(self):
        """الاسم مقبول كالمعرّف — لأن الاسم وحده هو ما تملكه الواجهة.

        الحمولة العامة تنشر `category_name` ولا تنشر المعرّف (قرار القائمة
        البيضاء)، فتصفيةٌ بالمعرّف وحده تعني قائمة تصنيفات لا تقدر واجهة المتجر
        على بنائها من نتائجها إطلاقاً. والاسم لا يفتح باباً: الاستعلام مفلتر
        بالشركة قبل هذا السطر، فاسم تصنيف شركة أخرى يعطي فراغاً لا تسريباً.
        """
        self.assertEqual(
            {item["id"] for item in self._list(category="إطارات")},
            {self.in_stock.id, self.limited.id},
        )

    def test_a_category_name_from_another_tenant_returns_nothing(self):
        rival = Tenant.objects.create(
            CompanyName="جارتنا", SubscriptionPlan="Basic", Status="Active",
            store_slug="neighbour")
        exclusive = ProductCategory.objects.create(tenant=rival, name="حصري")
        _product(rival, "N-1", name_ar="منتج الجارة", category=exclusive)
        self.assertEqual(self._list(category="حصري"), [])

    def test_price_sort_runs_both_ways(self):
        ascending = [item["price"] for item in self._list(sort="price_asc")]
        self.assertEqual(ascending, sorted(ascending, key=float))
        descending = [item["price"] for item in self._list(sort="price_desc")]
        self.assertEqual(descending, sorted(descending, key=float, reverse=True))

    def test_pagination_is_enforced_not_opt_in(self):
        """بلا `?page=` أيضاً — نقطة مجهولة لا تبثّ الكتالوج كاملاً بطلب واحد."""
        bare = self.client.get("/api/store/demo/products/").json()
        self.assertEqual(set(bare), {"count", "next", "previous", "results"})

    def test_page_size_is_capped(self):
        """سقف `max_page_size` يمنع تحويل `?page_size=` إلى مُضخِّم إساءة."""
        res = self.client.get(
            "/api/store/demo/products/", {"page": 1, "page_size": 100000})
        self.assertEqual(res.status_code, 200)
        self.assertLessEqual(len(res.json()["results"]), 200)

    def test_a_category_from_another_tenant_returns_nothing(self):
        other = Tenant.objects.create(
            CompanyName="شركة أخرى", SubscriptionPlan="Basic", Status="Active",
            store_slug="other")
        foreign = ProductCategory.objects.create(tenant=other, name="مستورد")
        self.assertEqual(self._list(category=foreign.id), [])

    # ── الصور ────────────────────────────────────────────────────────────
    def test_only_image_attachments_are_published(self):
        """الداتا شيت مرفق منتج أيضاً — نشره صورةً يسرّب مستنداً لم يُقصد نشره."""
        SystemAttachment.objects.create(
            tenant=self.tenant, related_table="products", related_id=self.in_stock.id,
            file_type="Product Image", file_path="https://res.cloudinary.com/x/a.jpg")
        SystemAttachment.objects.create(
            tenant=self.tenant, related_table="products", related_id=self.in_stock.id,
            file_type="Datasheet", file_path="https://res.cloudinary.com/x/spec.pdf")
        images = self._by_id()[self.in_stock.id]["images"]
        self.assertEqual(images, ["https://res.cloudinary.com/x/a.jpg"])

    def test_a_product_without_images_gets_an_empty_list(self):
        self.assertEqual(self._by_id()[self.out.id]["images"], [])

    # ── الطبقة الأولى: ما لا يُحمَّل من القاعدة أصلاً ────────────────────
    def test_raw_stock_and_cost_never_reach_python(self):
        """`.only()` ليس تجميلاً: الأعمدة الحسّاسة تبقى مؤجَّلة على الكائن.

        الحارس هنا بنيوي: لو أضاف أحدٌ حقلاً إلى `PUBLIC_PRODUCT_COLUMNS` أو
        قرأ `obj.avg_cost` في السيريالايزر (فيجلبه جانغو باستعلام صامت) لسقط
        هذا الاختبار قبل أن يسقط اختبار الحمولة.
        """
        product = published_products(self.tenant).first()
        deferred = product.get_deferred_fields()
        for field in (
            "quantity_on_hand", "avg_cost", "sale_price", "online_price",
            "min_stock_level", "sku", "barcode", "hs_code",
        ):
            self.assertIn(field, deferred, f"{field} يُحمَّل من القاعدة — يجب ألّا يُحمَّل")
        self.assertNotIn("AvgCost", str(published_products(self.tenant).query))

    # ── الكاش: مفتاحه يحمل الشركة، وإلا صار قناة تسريب ────────────────────
    @override_settings(CACHES=_LOCMEM)
    def test_the_list_cache_does_not_bleed_between_stores(self):
        """كاشٌ بمفتاح لا يحمل الـslug يقدّم متجر شركةٍ لزائر شركةٍ أخرى.

        هذه بالضبط ثغرة عامل الخدمة (2026-08-13): المفتاح كان الرابطَ وحده
        والشركةُ تأتي من مكان آخر.
        """
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        rival = Tenant.objects.create(
            CompanyName="المنافس", SubscriptionPlan="Pro", Status="Active",
            store_slug="rival")
        secret = _product(rival, "R-1", name_ar="منتج المنافس")

        mine = {item["id"] for item in self._list()}
        theirs = {
            item["id"]
            for item in self.client.get("/api/store/rival/products/").json()["results"]
        }
        self.assertNotIn(secret.id, mine)
        self.assertEqual(theirs, {secret.id})
        # وبعد أن سخُن الكاش للطرفين: كلٌّ ما زال يرى متجره هو.
        self.assertEqual({item["id"] for item in self._list()}, mine)

    def test_cache_key_carries_the_slug(self):
        from django.http import QueryDict

        view = StoreProductListView()
        empty = QueryDict("")
        alpha = view._cache_key(self.tenant, "alpha", empty)
        beta = view._cache_key(self.tenant, "beta", empty)
        self.assertTrue(alpha.startswith("store:alpha:"))
        self.assertNotEqual(alpha, beta)
        # والمفتاح يحمل رقم نسخةٍ أيضاً (THA-423): رفعُه يُهجر الحمولة القديمة
        # عند النشر بدل انتظار الـTTL.
        self.assertIn(":products:v", alpha)

    # ── بطاقة الشركة ─────────────────────────────────────────────────────
    def test_a_store_without_a_settings_row_still_has_a_name(self):
        """شركة بلا `TenantSettings` تُعرَض باسمها المسجَّل لا ببطاقة فارغة.

        بطاقةٌ بلا اسم تجعل الزائر يظنّ الرابط مكسوراً — وأول ما يفعله المدير
        هو فتح متجره، لا ملء ثوابت المجموعة.
        """
        bare = Tenant.objects.create(
            CompanyName="شركة بلا إعدادات", SubscriptionPlan="Basic",
            Status="Active", store_slug="bare-shop")
        res = self.client.get("/api/store/bare-shop/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["name"], bare.CompanyName)
        self.assertIsNone(res.json()["phone"])

    def test_the_profile_publishes_the_currency_the_prices_are_in(self):
        """سعرٌ بلا عملة على صفحة عامة رقمٌ لا معنى له.

        المنصة متعدّدة العملات، والزائر ليس في جلسةٍ تعرف عملة الشركة: «50»
        وحدها تُقرأ شيكلاً أو دولاراً حسب مَن يقرأ. الرمز أولاً لأنه ما يعرفه
        الزبون، والرمز الدولي احتياطٌ لعملة بلا رمز مضبوط.
        """
        from tenants.models import Currency, TenantSettings

        shekel = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪")
        TenantSettings.objects.create(tenant=self.tenant, currency=shekel)
        self.assertEqual(self.client.get("/api/store/demo/").json()["currency"], "₪")

        naked = Currency.objects.create(Code="JOD", Name="دينار", Symbol=None)
        TenantSettings.objects.filter(tenant=self.tenant).update(currency=naked)
        self.assertEqual(self.client.get("/api/store/demo/").json()["currency"], "JOD")

    def test_a_store_without_a_currency_says_so_with_null(self):
        """لا نخترع عملة افتراضية — الواجهة تعرض الرقم عارياً بدل عملةٍ كاذبة."""
        self.assertIsNone(self.client.get("/api/store/demo/").json()["currency"])

    def test_the_public_views_carry_the_store_throttle_scope(self):
        """درس P0-8: نقطة عامة بلا سقف مخصّص تُشبع الـworkers الثلاثة."""
        from store.views import StoreProductDetailView, StoreProfileView

        for view in (StoreProfileView, StoreProductListView, StoreProductDetailView):
            self.assertEqual(view.throttle_scope, "store_public")
            self.assertEqual(view.authentication_classes, [])
