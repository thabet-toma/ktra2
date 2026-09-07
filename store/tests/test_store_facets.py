"""الفلترةُ بعدّادات — مواصفة #166 المرحلة ٤.

يغطّي هذا الملف ما لا يغطّيه `test_store_catalog_public.py` (الخصم) ولا
`test_store_api.py` (التصفّح الأساسي): شكل `facets`/`price_range`، الاستثناءَ
الانفصاليّ في الاتجاهين، تجاوزَ مجموع محورٍ لعدد النتائج، العدَّ الشجريَّ
الشامل، ظهور/غياب العدّادات بالصفحة، مدى السعر السياقيّ وغيابه حين تُحجَب
الأسعار، `in_stock` دون `preorder`، حدَّ `is_new`، وحارسَي الكاش والأداء.

**لازمةٌ يجب معرفتها قبل قراءة أيّ اختبارٍ هنا:** مجموعُ عدّاداتِ محورٍ
انفصاليٍّ (الفئات تحديداً، M2M) **قد يتجاوز `count`** — منتجٌ في فئتين يُحسَب
في عدّاد كلٍّ منهما. `FacetSumExceedsCountTest` يُثبت هذا اختباراً لا يُصحِّحه.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from store.models import StoreBrand, StoreCategory, StoreProduct, StoreSettings
from store.views import StoreProductListView
from tenants.models import Tenant


def _tenant(slug, **kwargs):
    defaults = dict(CompanyName=f"متجر {slug}", SubscriptionPlan="Pro", Status="Active")
    defaults.update(kwargs)
    return Tenant.objects.create(store_slug=slug, **defaults)


def _store_product(tenant, name_ar, **kwargs):
    defaults = dict(price=Decimal("100.00"), is_active=True)
    defaults.update(kwargs)
    return StoreProduct.objects.create(tenant=tenant, name_ar=name_ar, **defaults)


class DisjunctiveExceptionTest(TestCase):
    """قسم ب — كلُّ محورٍ يُعدُّ بعد إسقاطِ اختيارِ نفسِه، وبإبقاء البقيّة."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("disjunctive")
        cls.phones = StoreCategory.objects.create(tenant=cls.tenant, name="هواتف", slug="phones")
        cls.laptops = StoreCategory.objects.create(tenant=cls.tenant, name="لابتوبات", slug="laptops")
        cls.samsung = StoreBrand.objects.create(tenant=cls.tenant, name="سامسونج")
        cls.apple = StoreBrand.objects.create(tenant=cls.tenant, name="أبل")

        s_phone = _store_product(cls.tenant, "هاتف سامسونج", brand=cls.samsung)
        s_phone.categories.set([cls.phones])
        a_phone = _store_product(cls.tenant, "هاتف أبل", brand=cls.apple)
        a_phone.categories.set([cls.phones])
        s_laptop = _store_product(cls.tenant, "لابتوب سامسونج", brand=cls.samsung)
        s_laptop.categories.set([cls.laptops])

    def _facets(self, **params):
        res = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/", params)
        self.assertEqual(res.status_code, 200, res.content[:300])
        return res.json()["facets"]

    def test_selecting_brand_changes_category_counts_not_brand_counts(self):
        """اختيارُ «سامسونج»: عدّادُ الفئات يُحسَب **داخل** سامسونج، وعدّادُ
        الماركات يبقى **كاملاً** (تبقى «أبل» ظاهرةً بعددها الحقيقيّ)."""
        facets = self._facets(brand=str(self.samsung.id))

        category_counts = {c["id"]: c["count"] for c in facets["categories"]}
        self.assertEqual(category_counts[self.phones.id], 1)
        self.assertEqual(category_counts[self.laptops.id], 1)

        brand_counts = {b["id"]: b["count"] for b in facets["brands"]}
        self.assertEqual(brand_counts[self.samsung.id], 2)
        self.assertEqual(brand_counts[self.apple.id], 1)

    def test_selecting_category_changes_brand_counts_not_category_counts(self):
        """اختيارُ «هواتف»: عدّادُ الماركات يُحسَب **داخل** الفئة، وعدّادُ
        الفئات يبقى **كاملاً** (تبقى «لابتوبات» ظاهرةً بعددها الحقيقيّ)."""
        facets = self._facets(category=str(self.phones.id))

        brand_counts = {b["id"]: b["count"] for b in facets["brands"]}
        self.assertEqual(brand_counts[self.samsung.id], 1)
        self.assertEqual(brand_counts[self.apple.id], 1)

        category_counts = {c["id"]: c["count"] for c in facets["categories"]}
        self.assertEqual(category_counts[self.phones.id], 2)
        self.assertEqual(category_counts[self.laptops.id], 1)


class MultiSelectTest(TestCase):
    """قسم د — OR داخل المحور، AND بين المحاور؛ معرّفاتٌ متعدّدة بفواصل، مع
    إبقاء قبول الاسم المفرد للتوافق الخلفيّ."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("multi-select")
        cls.samsung = StoreBrand.objects.create(tenant=cls.tenant, name="سامسونج")
        cls.apple = StoreBrand.objects.create(tenant=cls.tenant, name="أبل")
        cls.nokia = StoreBrand.objects.create(tenant=cls.tenant, name="نوكيا")
        cls.phones = StoreCategory.objects.create(tenant=cls.tenant, name="هواتف", slug="mphones")
        cls.laptops = StoreCategory.objects.create(tenant=cls.tenant, name="لابتوبات", slug="mlaptops")

        cls.s = _store_product(cls.tenant, "سامسونج جوال", brand=cls.samsung)
        cls.s.categories.set([cls.phones])
        cls.a = _store_product(cls.tenant, "أبل جوال", brand=cls.apple)
        cls.a.categories.set([cls.phones])
        cls.n = _store_product(cls.tenant, "نوكيا جوال", brand=cls.nokia)
        cls.n.categories.set([cls.laptops])

    def _ids(self, **params):
        res = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/", params)
        self.assertEqual(res.status_code, 200, res.content[:300])
        return {item["id"] for item in res.json()["results"]}

    def test_multiple_brand_ids_are_or_ed(self):
        ids = self._ids(brand=f"{self.samsung.id},{self.apple.id}")
        self.assertEqual(ids, {self.s.id, self.a.id})

    def test_multiple_category_ids_are_or_ed_with_distinct(self):
        ids = self._ids(category=f"{self.phones.id},{self.laptops.id}")
        self.assertEqual(ids, {self.s.id, self.a.id, self.n.id})

    def test_brand_and_category_are_and_ed_together(self):
        ids = self._ids(
            brand=f"{self.samsung.id},{self.nokia.id}",
            category=str(self.phones.id),
        )
        self.assertEqual(ids, {self.s.id})

    def test_single_brand_name_still_works_for_backward_compat(self):
        ids = self._ids(brand="سامسونج")
        self.assertEqual(ids, {self.s.id})


class FacetSumExceedsCountTest(TestCase):
    def test_category_facet_sum_can_exceed_result_count(self):
        tenant = _tenant("facet-sum")
        cat_a = StoreCategory.objects.create(tenant=tenant, name="أ", slug="a")
        cat_b = StoreCategory.objects.create(tenant=tenant, name="ب", slug="b")
        p = _store_product(tenant, "منتج في فئتين")
        p.categories.set([cat_a, cat_b])

        res = APIClient().get(f"/api/store/{tenant.store_slug}/products/")
        body = res.json()
        self.assertEqual(body["count"], 1)
        total = sum(c["count"] for c in body["facets"]["categories"])
        self.assertGreater(total, body["count"])


class TreeCategoryCountTest(TestCase):
    """قسم ج — العدُّ شاملٌ للأبناء: أبٌ بلا منتجٍ مباشرٍ وتحته ابنٌ بعشرة ⇒ الأبُ عشرة."""

    def test_parent_with_no_direct_products_shows_childrens_total(self):
        tenant = _tenant("cat-tree")
        parent = StoreCategory.objects.create(tenant=tenant, name="إلكترونيات", slug="electronics")
        child = StoreCategory.objects.create(
            tenant=tenant, name="هواتف", parent=parent, slug="phones-child")
        for i in range(10):
            p = _store_product(tenant, f"هاتف {i}")
            p.categories.set([child])

        res = APIClient().get(f"/api/store/{tenant.store_slug}/products/")
        facets = {c["id"]: c["count"] for c in res.json()["facets"]["categories"]}
        self.assertEqual(facets[parent.id], 10)
        self.assertEqual(facets[child.id], 10)

    def test_product_tagged_with_both_parent_and_child_is_not_double_counted(self):
        """مراجعةُ المنسّق: منتجٌ موسومٌ بالأب وابنه معاً هو الاستعمالُ
        الطبيعيّ لـM2M لا الشاذّ — العدُّ عددُ منتجاتٍ متمايزة لا مجموع
        عدّادين. أبٌ (٢) وابنٌ (٢) وليس أبٌ (٣)."""
        tenant = _tenant("cat-tree-overlap")
        parent = StoreCategory.objects.create(tenant=tenant, name="إلكترونيات", slug="electronics-ov")
        child = StoreCategory.objects.create(
            tenant=tenant, name="هواتف", parent=parent, slug="phones-ov")
        both = _store_product(tenant, "منتجٌ في الأب والابن معاً")
        both.categories.set([parent, child])
        child_only = _store_product(tenant, "منتجٌ في الابن وحده")
        child_only.categories.set([child])

        res = APIClient().get(f"/api/store/{tenant.store_slug}/products/")
        body = res.json()
        self.assertEqual(body["count"], 2)
        facets = {c["id"]: c["count"] for c in body["facets"]["categories"]}
        self.assertEqual(facets[parent.id], 2)
        self.assertEqual(facets[child.id], 2)


class FacetsPagingTest(TestCase):
    """قسم أ — العدّاداتُ عند `page == 1` فقط، وتغيب في الصفحات التالية، وتعود
    صراحةً بـ`include_facets=1`."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("facet-paging")
        for i in range(3):
            _store_product(cls.tenant, f"منتج {i}")

    def test_facets_on_page_one_absent_on_page_two_forced_by_include_facets(self):
        page1 = APIClient().get(
            f"/api/store/{self.tenant.store_slug}/products/",
            {"page": 1, "page_size": 1},
        ).json()
        self.assertIn("facets", page1)
        self.assertIn("price_range", page1)

        page2 = APIClient().get(
            f"/api/store/{self.tenant.store_slug}/products/",
            {"page": 2, "page_size": 1},
        ).json()
        self.assertNotIn("facets", page2)
        self.assertNotIn("price_range", page2)

        page2_forced = APIClient().get(
            f"/api/store/{self.tenant.store_slug}/products/",
            {"page": 2, "page_size": 1, "include_facets": "1"},
        ).json()
        self.assertIn("facets", page2_forced)
        self.assertIn("price_range", page2_forced)

    def test_bare_request_without_page_param_also_returns_facets(self):
        bare = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/").json()
        self.assertIn("facets", bare)
        self.assertIn("price_range", bare)


class PriceRangeContextualTest(TestCase):
    """قسم هـ — `price_range` سياقيٌّ باستثناء فلتر السعر نفسِه، ويغيب كلّياً
    حين `show_prices=false`."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("price-range")
        _store_product(cls.tenant, "رخيص", price=Decimal("10.00"))
        _store_product(cls.tenant, "متوسط", price=Decimal("50.00"))
        _store_product(cls.tenant, "غالٍ", price=Decimal("200.00"))

    def test_price_range_ignores_its_own_filter(self):
        res = APIClient().get(
            f"/api/store/{self.tenant.store_slug}/products/",
            {"min_price": "40", "max_price": "60"},
        )
        body = res.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(Decimal(body["price_range"]["min"]), Decimal("10.00"))
        self.assertEqual(Decimal(body["price_range"]["max"]), Decimal("200.00"))

    def test_price_range_absent_when_prices_hidden(self):
        StoreSettings.objects.create(tenant=self.tenant, show_prices=False)
        res = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/")
        self.assertNotIn("price_range", res.json())

    def test_price_filters_are_ignored_when_prices_hidden(self):
        StoreSettings.objects.create(tenant=self.tenant, show_prices=False)
        res = APIClient().get(
            f"/api/store/{self.tenant.store_slug}/products/",
            {"min_price": "1000", "max_price": "2000"},
        )
        # المدى مستحيلٌ لو طُبِّق فعلياً — المعاملان يُهمَلان تماماً بلا نتائج مفلترة.
        self.assertEqual(res.json()["count"], 3)

    def test_on_sale_flag_is_zero_when_prices_hidden(self):
        """قرارٌ أقرّه المنسّق: لا سعرَ ⇒ لا خصمَ يُعرَض ⇒ لا شيءَ يُفلتَر به.
        `on_sale=0` دائماً حين `show_prices=false`، ولو حمل المنتج `sale_price`
        فعليّاً أدنى من `price` — الحجبُ يسبق حساب الخصم بالكامل."""
        product = _store_product(
            self.tenant, "مخفّضٌ محجوبُ السعر",
            price=Decimal("100.00"), sale_price=Decimal("50.00"),
        )
        StoreSettings.objects.create(tenant=self.tenant, show_prices=False)

        res = APIClient().get(
            f"/api/store/{self.tenant.store_slug}/products/", {"on_sale": "1"},
        )
        body = res.json()
        self.assertEqual(body["results"], [])
        self.assertEqual(body["facets"]["flags"]["on_sale"], 0)


class InStockExcludesPreorderTest(TestCase):
    def test_in_stock_flag_excludes_preorder_and_out_of_stock(self):
        tenant = _tenant("in-stock-filter")
        in_stock = _store_product(tenant, "متوفر", stock_state=StoreProduct.STOCK_IN_STOCK)
        _store_product(tenant, "بالطلب", stock_state=StoreProduct.STOCK_PREORDER)
        _store_product(tenant, "نفد", stock_state=StoreProduct.STOCK_OUT_OF_STOCK)

        res = APIClient().get(
            f"/api/store/{tenant.store_slug}/products/", {"in_stock": "1"},
        )
        body = res.json()
        self.assertEqual({item["id"] for item in body["results"]}, {in_stock.id})
        self.assertEqual(body["facets"]["flags"]["in_stock"], 1)


class IsNewWindowTest(TestCase):
    def test_product_one_day_outside_window_is_not_new(self):
        tenant = _tenant("is-new-window")
        StoreSettings.objects.create(tenant=tenant, new_product_days=30)
        fresh = _store_product(tenant, "جديد فعلاً")
        stale = _store_product(tenant, "قديمٌ بيومٍ واحد")
        StoreProduct.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=31))

        res = APIClient().get(
            f"/api/store/{tenant.store_slug}/products/", {"is_new": "1"},
        )
        body = res.json()
        self.assertEqual({item["id"] for item in body["results"]}, {fresh.id})
        self.assertEqual(body["facets"]["flags"]["is_new"], 1)

    def test_default_new_product_days_is_30_without_settings_row(self):
        """غيابُ صفّ `StoreSettings` ليس خطأً — الافتراضُ ٣٠ يوماً (قسم ج)."""
        tenant = _tenant("is-new-default")
        fresh = _store_product(tenant, "بلا إعدادات")
        res = APIClient().get(
            f"/api/store/{tenant.store_slug}/products/", {"is_new": "1"},
        )
        self.assertEqual({item["id"] for item in res.json()["results"]}, {fresh.id})


class CacheFingerprintGuardTest(TestCase):
    """قسم و — حارسٌ بالبناء لا بالتعداد: كلّ معاملٍ يقرؤه `_filtered` يجب أن
    يكون داخل `CACHE_PARAMS`، وإلا خُدِم قديماً بصمتٍ من الكاش."""

    def test_every_filtered_read_param_is_covered_by_cache_params(self):
        tenant = _tenant("fingerprint-guard")

        class _SpyParams:
            def __init__(self):
                self.read_keys = set()

            def get(self, key, default=None):
                self.read_keys.add(key)
                return default

        spy = _SpyParams()
        StoreProductListView._filtered(StoreProduct.objects.none(), spy, tenant)
        self.assertTrue(spy.read_keys)
        self.assertLessEqual(spy.read_keys, set(StoreProductListView.CACHE_PARAMS))

    def test_min_price_alone_changes_the_cache_key(self):
        """طلبان لا يختلفان إلّا في `min_price` يجب ألّا يتشاركا مفتاح كاش."""
        tenant = _tenant("fingerprint-price")
        view = StoreProductListView()
        key_a = view._cache_key(tenant, tenant.store_slug, {"min_price": "10"})
        key_b = view._cache_key(tenant, tenant.store_slug, {"min_price": "20"})
        self.assertNotEqual(key_a, key_b)

    def test_include_facets_alone_changes_the_cache_key(self):
        tenant = _tenant("fingerprint-facets")
        view = StoreProductListView()
        key_a = view._cache_key(tenant, tenant.store_slug, {"include_facets": "1"})
        key_b = view._cache_key(tenant, tenant.store_slug, {})
        self.assertNotEqual(key_a, key_b)


class FacetQueryBudgetTest(TestCase):
    """قسم ز — الحارسُ الحقيقيّ للأداء: عددُ استعلامات العدّاداتِ ثابتٌ بصرف
    النظر عن عدد المنتجات والفئات والماركات."""

    @staticmethod
    def _build_catalog(tenant, *, product_count, category_count, brand_count):
        categories = [
            StoreCategory.objects.create(
                tenant=tenant, name=f"فئة {i}", slug=f"cat-{tenant.pk}-{i}")
            for i in range(category_count)
        ]
        brands = [
            StoreBrand.objects.create(tenant=tenant, name=f"ماركة {i}")
            for i in range(brand_count)
        ]
        for i in range(product_count):
            p = _store_product(
                tenant, f"منتج {i}",
                brand=brands[i % brand_count] if brands else None,
            )
            if categories:
                p.categories.set([categories[i % category_count]])

    def test_query_count_is_independent_of_catalog_size(self):
        small = _tenant("facet-small")
        self._build_catalog(small, product_count=5, category_count=2, brand_count=1)

        big = _tenant("facet-big")
        self._build_catalog(big, product_count=50, category_count=10, brand_count=5)

        with CaptureQueriesContext(connection) as small_ctx:
            res_small = APIClient().get(
                f"/api/store/{small.store_slug}/products/", {"page_size": 5})
        self.assertEqual(res_small.status_code, 200, res_small.content[:300])

        with CaptureQueriesContext(connection) as big_ctx:
            res_big = APIClient().get(
                f"/api/store/{big.store_slug}/products/", {"page_size": 5})
        self.assertEqual(res_big.status_code, 200, res_big.content[:300])

        self.assertEqual(
            len(small_ctx.captured_queries), len(big_ctx.captured_queries),
            "عددُ استعلامات العدّادات يجب أن يبقى ثابتاً بصرف النظر عن عدد "
            "المنتجات/الفئات/الماركات — تحقّق من عدم وجود استعلامٍ لكل فئةٍ أو ماركة.",
        )
