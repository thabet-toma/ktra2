"""سلوك تصفّح المتجر: التوفّر، والبحث والتصفية والفرز، والصور، والكاش.

عزل التسريب في `test_public_leakage.py`؛ هذا الملف يغطّي ما يراه الزائر فعلاً
حين يتصفّح — وطبقةَ الكاش التي هي بنفسها سطحُ عزلٍ يجب أن يُثبَت.

THA-166 م٢ (تصحيح): المصدر `store.StoreProduct` لا `inventory.Product`.
حالاتٌ سقطت مع القراءة العامة القديمة لأن جوهرها رصيدٌ مخزنيّ لا وجود له على
هذا الكتالوج: `limited` (حدّ أدنى)، والخدمة (`is_service`) الدائمة التوفّر،
وتفضيل `online_price` على `sale_price` (لم يعودا نفس الحقلين أصلاً — `price`
هو الأساس الوحيد الآن و`sale_price` خصمٌ مطلق مستقلّ، مواصفة #166 م٢).
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import SystemAttachment
from store.models import StoreBrand, StoreCategory, StoreProduct
from store.views import StoreProductListView
from tenants.models import Tenant

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _store_product(tenant, name_ar, **kwargs):
    defaults = dict(price=Decimal("10.00"), is_active=True)
    defaults.update(kwargs)
    return StoreProduct.objects.create(tenant=tenant, name_ar=name_ar, **defaults)


class StoreBrowseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="متجر التجربة", SubscriptionPlan="Pro", Status="Active",
            store_slug="demo")
        cls.tyres = StoreCategory.objects.create(
            tenant=cls.tenant, name="إطارات", slug="tyres")
        cls.oils = StoreCategory.objects.create(
            tenant=cls.tenant, name="زيوت", slug="oils")
        cls.michelin = StoreBrand.objects.create(tenant=cls.tenant, name="ميشلان")
        cls.bridgestone = StoreBrand.objects.create(tenant=cls.tenant, name="بريجستون")
        cls.shell = StoreBrand.objects.create(tenant=cls.tenant, name="شل")

        cls.in_stock = _store_product(
            cls.tenant, "إطار متوفر", brand=cls.michelin,
            price=Decimal("50.00"), stock_state=StoreProduct.STOCK_IN_STOCK)
        cls.in_stock.categories.set([cls.tyres])

        cls.preorder_item = _store_product(
            cls.tenant, "إطار بالطلب", brand=cls.bridgestone,
            price=Decimal("70.00"), stock_state=StoreProduct.STOCK_PREORDER)
        cls.preorder_item.categories.set([cls.tyres])

        cls.out = _store_product(
            cls.tenant, "زيت نافد", brand=cls.shell,
            price=Decimal("12.00"), stock_state=StoreProduct.STOCK_OUT_OF_STOCK)
        cls.out.categories.set([cls.oils])

    def setUp(self):
        self.client = APIClient()

    def _list(self, **params):
        res = self.client.get("/api/store/demo/products/", params)
        self.assertEqual(res.status_code, 200, res.content[:300])
        payload = res.json()
        return payload["results"] if isinstance(payload, dict) else payload

    def _by_id(self):
        return {item["id"]: item for item in self._list()}

    # ── التوفّر: حالة مشتقّة من `stock_state` لا من رصيد ───────────────────
    def test_availability_states_are_derived_from_stock_state(self):
        items = self._by_id()
        self.assertEqual(items[self.in_stock.id]["availability"], "available")
        self.assertEqual(items[self.preorder_item.id]["availability"], "preorder")
        self.assertEqual(items[self.out.id]["availability"], "out")

    # ── السعر ────────────────────────────────────────────────────────────
    def test_price_reads_the_base_price_column(self):
        self.assertEqual(self._by_id()[self.in_stock.id]["price"], "50.00")

    # ── البحث والتصفية والفرز ────────────────────────────────────────────
    def test_search_matches_arabic_name_and_brand(self):
        self.assertEqual(
            {item["id"] for item in self._list(q="نافد")}, {self.out.id})
        self.assertEqual(
            {item["id"] for item in self._list(q="ميشلان")}, {self.in_stock.id})

    def test_brand_and_category_filters(self):
        self.assertEqual(
            {item["id"] for item in self._list(brand="شل")}, {self.out.id})
        self.assertEqual(
            {item["id"] for item in self._list(category=self.tyres.id)},
            {self.in_stock.id, self.preorder_item.id},
        )

    def test_the_category_filter_also_accepts_the_published_name(self):
        """الاسم مقبول كالمعرّف — لأن الاسم وحده هو ما تملكه الواجهة.

        الحمولة العامة تنشر `category_name` (أوّل فئة) وقد لا تكفي وحدها
        لبناء قائمة تصنيفات، فالاسم مقبولٌ كالمعرّف. والاسم لا يفتح باباً:
        الاستعلام مفلتر بالشركة قبل هذا الشرط، فاسم تصنيف شركة أخرى يعطي
        فراغاً لا تسريباً.
        """
        self.assertEqual(
            {item["id"] for item in self._list(category="إطارات")},
            {self.in_stock.id, self.preorder_item.id},
        )

    def test_a_category_name_from_another_tenant_returns_nothing(self):
        rival = Tenant.objects.create(
            CompanyName="جارتنا", SubscriptionPlan="Basic", Status="Active",
            store_slug="neighbour")
        exclusive = StoreCategory.objects.create(
            tenant=rival, name="حصري", slug="exclusive")
        neighbour_product = _store_product(rival, "منتج الجارة")
        neighbour_product.categories.set([exclusive])
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
        foreign = StoreCategory.objects.create(
            tenant=other, name="مستورد", slug="imported")
        self.assertEqual(self._list(category=foreign.id), [])

    # ── الصور ────────────────────────────────────────────────────────────
    def test_only_image_attachments_are_published(self):
        """الداتا شيت مرفق منتج أيضاً — نشره صورةً يسرّب مستنداً لم يُقصد نشره.

        السقوط إلى `SystemAttachment` لا يعمل إلّا للمنتجات **المستوردة**
        (`imported_from_product_id`) — منتجٌ أنشأه التاجر من الصفر لا مرفقات
        مخزونٍ له أصلاً.
        """
        imported = _store_product(
            self.tenant, "منتج مستورد", imported_from_product_id=9001)
        SystemAttachment.objects.create(
            tenant=self.tenant, related_table="products", related_id=9001,
            file_type="Product Image", file_path="https://res.cloudinary.com/x/a.jpg")
        SystemAttachment.objects.create(
            tenant=self.tenant, related_table="products", related_id=9001,
            file_type="Datasheet", file_path="https://res.cloudinary.com/x/spec.pdf")
        images = self._by_id()[imported.id]["images"]
        self.assertEqual(images, ["https://res.cloudinary.com/x/a.jpg"])

    def test_a_product_without_images_gets_an_empty_list(self):
        self.assertEqual(self._by_id()[self.out.id]["images"], [])

    # ── الطبقة الأولى: ما لا وجود له على النموذج أصلاً ────────────────────
    def test_store_product_has_no_stock_or_cost_columns_at_all(self):
        """THA-166 م٢: الضمانة صارت **بنيوية** لا اعتماداً على `.only()` —
        `StoreProduct` لا يحمل هذه الأعمدة أصلاً (لا مخزون ولا محاسبة أبداً،
        قرار مالكٍ حاكم منذ م١)، فلا طريق لتسريبها من القاعدة إطلاقاً.
        هذه أقوى من الحارس القديم (حقول مؤجَّلة بـ`.only()` على `Product`).
        """
        field_names = {f.name for f in StoreProduct._meta.get_fields()}
        for forbidden in (
            "quantity_on_hand", "avg_cost", "min_stock_level", "sku",
            "barcode", "hs_code", "is_service", "online_price",
        ):
            self.assertNotIn(
                forbidden, field_names,
                f"{forbidden} صار عموداً على StoreProduct — راجع نشره العام",
            )

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
        secret = _store_product(rival, "منتج المنافس")

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
