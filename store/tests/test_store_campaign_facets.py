"""THA-166 م٧ — `StoreCollectionDetailView` يبني `facets`/`price_range` الآن،
بإعادة استعمال دوالّ `StoreProductListView` حرفياً (لا نسخةً ثانية) — `base_qs`
مقيَّدٌ بمنتجات هذه الحملة وحدها، فمنتجٌ منشورٌ خارج الحملة لا يدخل عدّاداتها.

قبل هذه المرحلة كانت هذه النقطة بلا `facets` إطلاقاً — صفحةُ الحملة في
الواجهة كانت الوحيدة بلا شريط فلاتر بعدّادات من بين الصفحات الثلاث
(الرئيسية/الفئة/الحملة) رغم مشاركتها الجسدَ نفسَه.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from store.models import StoreBrand, StoreCollection, StoreCollectionItem, StoreProduct, StoreSettings
from tenants.models import Tenant


def _tenant(slug, **kwargs):
    defaults = dict(CompanyName=f"شركة {slug}", SubscriptionPlan="Pro", Status="Active")
    defaults.update(kwargs)
    return Tenant.objects.create(store_slug=slug, **defaults)


class CampaignFacetsScopedToCollectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("camp-facets")
        cls.samsung = StoreBrand.objects.create(tenant=cls.tenant, name="سامسونج")
        cls.apple = StoreBrand.objects.create(tenant=cls.tenant, name="أبل")

        cls.in_campaign_1 = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="داخل الحملة ١", brand=cls.samsung,
            price=Decimal("100.00"), is_active=True)
        cls.in_campaign_2 = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="داخل الحملة ٢", brand=cls.apple,
            price=Decimal("200.00"), is_active=True)
        # منتجٌ منشورٌ بنفس ماركة الحملة لكن **خارجها** — لا يجوز أن يدخل عدّاداتها.
        cls.outside = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="خارج الحملة", brand=cls.samsung,
            price=Decimal("50.00"), is_active=True)

        cls.collection = StoreCollection.objects.create(
            tenant=cls.tenant, title="حملة الاختبار", slug="camp-facets-collection",
            is_active=True)
        StoreCollectionItem.objects.create(
            tenant=cls.tenant, collection=cls.collection, store_product=cls.in_campaign_1)
        StoreCollectionItem.objects.create(
            tenant=cls.tenant, collection=cls.collection, store_product=cls.in_campaign_2)

    def _get(self, **params):
        return APIClient().get(
            f"/api/store/{self.tenant.store_slug}/collections/{self.collection.slug}/", params,
        )

    def test_facets_present_and_scoped_to_campaign_products_only(self):
        res = self._get()
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertIn("facets", body["products"])
        brand_counts = {b["id"]: b["count"] for b in body["products"]["facets"]["brands"]}
        self.assertEqual(brand_counts[self.samsung.id], 1, "المنتج خارج الحملة لا يُحسَب")
        self.assertEqual(brand_counts[self.apple.id], 1)

    def test_price_range_scoped_to_campaign_products_only(self):
        body = self._get().json()
        self.assertIn("price_range", body["products"])
        self.assertEqual(Decimal(body["products"]["price_range"]["min"]), Decimal("100.00"))
        self.assertEqual(Decimal(body["products"]["price_range"]["max"]), Decimal("200.00"))

    def test_disjunctive_exception_holds_within_campaign_scope(self):
        """اختيارُ سامسونج: النتائج تصير منتجاً واحداً، وعدّادُ أبل يبقى ظاهراً بعدده الحقيقي — لا صفراً."""
        body = self._get(brand=str(self.samsung.id)).json()
        ids = {item["id"] for item in body["products"]["results"]}
        self.assertEqual(ids, {self.in_campaign_1.id})
        brand_counts = {b["id"]: b["count"] for b in body["products"]["facets"]["brands"]}
        self.assertEqual(brand_counts[self.apple.id], 1)

    def test_facets_absent_on_page_two_without_include_facets(self):
        body = self._get(page=2, page_size=1).json()
        self.assertNotIn("facets", body["products"])
        self.assertNotIn("price_range", body["products"])

    def test_include_facets_forces_them_on_page_two(self):
        body = self._get(page=2, page_size=1, include_facets="1").json()
        self.assertIn("facets", body["products"])

    def test_price_range_absent_when_prices_hidden(self):
        StoreSettings.objects.create(tenant=self.tenant, show_prices=False)
        body = self._get().json()
        self.assertNotIn("price_range", body["products"])
        self.assertIn("facets", body["products"])
