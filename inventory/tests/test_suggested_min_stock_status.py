"""#44: شاشة الأصناف كانت عمياء عن الحدّ المحسوب — «منخفض» لا تظهر إلا بحدٍّ
يدوي، لأن `suggested_min` لم يكن يُمرَّر من أي موضعٍ غير تقرير التجديد.

سلوكيٌّ عبر HTTP لا استيراد دوالّ داخلية، بنفس نمط `test_brand_grouping.py`:
القراءة تقرأ استجابة `ProductViewSet` كما يراها المالك فعلاً. سجلّ المبيعات
هنا مطابقٌ حرفياً لِـ`_steady_seller` في `core/tests/test_replenishment.py`
(90 وحدة صافية على 90 يوماً ⇒ ADU=1، ذروة أسبوعية 14 ⇒ حدٌّ أدنى مقترَح 42 —
بارامترات `logistics.PurchaseSettings` الافتراضية: مهلة 14 يوماً، مراجعة 30).
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class SuggestedMinHttpTestBase(APITestCase):
    """أدوات مشتركة: تسجيلٌ عبر الواجهة، وبائعٌ ثابتٌ (٩٠/٩٠ ⇒ حدٌّ ٤٢)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username=cls.__name__.lower(), password="x")
        cls.tenant = create_company(f"شركة {cls.__name__}", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        self.today = timezone.localdate()

    def _register(self, name, **extra):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": name, **extra}, format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    def _add_brand(self, family_id, brand):
        res = self.client.post(
            f"{PRODUCTS_URL}add-brand/", {"family_id": family_id, "brand": brand},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    def _steady_seller(self, product, *, quantity_on_hand=None):
        """90 وحدة صافية على 90 يوماً — يطابق `_steady_seller` في محرّك
        التجديد حرفياً، فحدّه الأدنى المقترَح 42 بالبارامترات الافتراضية."""
        StockMovement.objects.create(
            tenant=self.tenant, product=product, movement_type="IN",
            quantity=Decimal("1000"), movement_date=self.today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=self.tenant, product=product, movement_type="OUT",
                quantity=Decimal("14"),
                movement_date=self.today - datetime.timedelta(days=week * 7),
            )
        StockMovement.objects.create(
            tenant=self.tenant, product=product, movement_type="OUT",
            quantity=Decimal("6"), movement_date=self.today - datetime.timedelta(days=49),
        )
        if quantity_on_hand is not None:
            Product.objects.filter(pk=product.id).update(
                quantity_on_hand=Decimal(str(quantity_on_hand)))

    def _get(self, product_id):
        res = self.client.get(f"{PRODUCTS_URL}{product_id}/", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()

    def _list(self):
        res = self.client.get(PRODUCTS_URL, **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return {row["sku"]: row for row in res.json()}


class SuggestedMinBadgeTest(SuggestedMinHttpTestBase):
    """(a)/(b): الشارة تُحاكَم بالحدّ الحاكم فعلاً — المحسوب حين لا يدوي،
    واليدوي دائماً حين وُجد."""

    # (a) هذا هو العيب حرفياً: بلا هذا الإصلاح تعود «متوفّر» (الحدّ صفرٌ).
    def test_product_without_manual_min_below_computed_min_is_low_stock(self):
        product = self._register("منتج بلا حدّ يدوي")
        self._steady_seller(product, quantity_on_hand=10)  # 10 ≤ 42 المحسوب

        body = self._get(product.id)
        assert not body["min_stock_level"]
        assert body["stock_status"] == "low_stock", body

    # (b) اليدوي يفوز حتى لو كان المحسوب سيحكم بغير ذلك — رقم المالك لا يُدهَس.
    def test_product_with_manual_min_ignores_the_computed_one(self):
        product = self._register("منتج بحدّ يدوي", min_stock_level=5)
        self._steady_seller(product, quantity_on_hand=10)  # لو حكم المحسوب (42) لكانت منخفض

        body = self._get(product.id)
        assert body["stock_status"] == "in_stock", body  # اليدوي (5) يحكم: 10 > 5
        assert body["effective_min_stock_level"] == 5, body


class SuggestedMinFamilyTest(SuggestedMinHttpTestBase):
    """(c): الأب بلا حدٍّ يدوي — حدّه المحسوب مجموع حدود إخوته المحسوبة
    (القرار ج في #44)، لا حسابٌ ثانٍ على مجموع النوع."""

    def test_family_with_two_siblings_uses_summed_computed_mins(self):
        first = self._register("عائلة 44")
        first.brand = "أ"
        first.save(update_fields=["brand"])
        second = self._add_brand(first.family_id, "ب")
        self._steady_seller(first, quantity_on_hand=40)
        self._steady_seller(second, quantity_on_hand=40)

        # كلٌّ منهما يُنتج حدّاً محسوباً 42 ⇒ مجموع الأب 84. المتاح المجموع
        # 80 ≤ 84 ⇒ «منخفض» على الاثنين معاً (حكم الأب لا حكم كلٍّ على حدة).
        rows = self._list()
        assert rows[first.sku]["stock_status"] == "low_stock", rows[first.sku]
        assert rows[second.sku]["stock_status"] == "low_stock", rows[second.sku]

    def test_family_with_two_siblings_stays_in_stock_when_abundant(self):
        first = self._register("عائلة 44 وفيرة")
        first.brand = "أ"
        first.save(update_fields=["brand"])
        second = self._add_brand(first.family_id, "ب")
        self._steady_seller(first, quantity_on_hand=100)
        self._steady_seller(second, quantity_on_hand=100)

        # المجموع 200 > 84 (مجموع الحدّين المحسوبين) ⇒ متوفّر.
        rows = self._list()
        assert rows[first.sku]["stock_status"] == "in_stock", rows[first.sku]
        assert rows[second.sku]["stock_status"] == "in_stock", rows[second.sku]


class CombinedUnderMinFilterTest(SuggestedMinHttpTestBase):
    """(d)/(e): الفلتر المركّب «تحت الحدّ الأدنى» = نفذ ∪ منخفض، ونفس
    المسار يغذّي التصدير (بلا مسارٍ ثانٍ)."""

    def _seed(self):
        out_product = self._register("نافذ 44")
        Product.objects.filter(pk=out_product.id).update(quantity_on_hand=Decimal("0"))

        low_product = self._register("منخفض 44")
        self._steady_seller(low_product, quantity_on_hand=10)  # 10 ≤ 42 المحسوب

        ok_product = self._register("متوفر 44", min_stock_level=1)
        Product.objects.filter(pk=ok_product.id).update(quantity_on_hand=Decimal("100"))

        over_product = self._register("فائض 44", max_stock_level=5)
        Product.objects.filter(pk=over_product.id).update(quantity_on_hand=Decimal("100"))
        return out_product, low_product, ok_product, over_product

    # (d)
    def test_combined_filter_returns_out_of_stock_and_low_stock_only(self):
        out_product, low_product, ok_product, over_product = self._seed()

        res = self.client.get(f"{PRODUCTS_URL}?stock_status=under_min", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        skus = {row["sku"] for row in res.json()}

        assert out_product.sku in skus, skus
        assert low_product.sku in skus, skus
        assert ok_product.sku not in skus, skus
        assert over_product.sku not in skus, skus

    # (e): مسار التصدير (page + complete_families=1، كما يرسله `exportProducts`
    # في الواجهة) يعيد **نفس** مجموعة الفلتر المركّب — لا مسارٌ ثانٍ للفلترة.
    def test_export_path_matches_the_combined_filter_exactly(self):
        out_product, low_product, ok_product, over_product = self._seed()

        combined = self.client.get(
            f"{PRODUCTS_URL}?stock_status=under_min&page=1&page_size=200&complete_families=1",
            **self.hdr,
        )
        assert combined.status_code == 200, combined.content[:300]
        combined_skus = {row["sku"] for row in combined.json()["results"]}

        out_res = self.client.get(
            f"{PRODUCTS_URL}?stock_status=out_of_stock&page=1&page_size=200&complete_families=1",
            **self.hdr,
        )
        low_res = self.client.get(
            f"{PRODUCTS_URL}?stock_status=low_stock&page=1&page_size=200&complete_families=1",
            **self.hdr,
        )
        union_skus = (
            {row["sku"] for row in out_res.json()["results"]}
            | {row["sku"] for row in low_res.json()["results"]}
        )
        assert combined_skus == union_skus, (combined_skus, union_skus)
        assert combined_skus == {out_product.sku, low_product.sku}, combined_skus
        assert ok_product.sku not in combined_skus
        assert over_product.sku not in combined_skus


class SuggestedMinQueryBudgetTest(SuggestedMinHttpTestBase):
    """(f): عدد الاستعلامات ثابتٌ مهما كبر عدد الأصناف، والشارة صحيحةٌ في
    كل صفّ — نفس نمط `FamilyStockStatusQueryBudgetTest` في `test_brand_grouping.py`."""

    def test_query_count_stays_flat_and_badges_stay_correct_as_products_grow(self):
        for i in range(2):
            p = self._register(f"صنف 44-{i}")
            self._steady_seller(p, quantity_on_hand=10)  # دون الحدّ المحسوب (42)

        with CaptureQueriesContext(connection) as small:
            r1 = self.client.get(PRODUCTS_URL, **self.hdr)
        assert r1.status_code == 200, r1.content[:300]

        for i in range(2, 8):
            p = self._register(f"صنف 44-{i}")
            self._steady_seller(p, quantity_on_hand=10)

        with CaptureQueriesContext(connection) as large:
            r2 = self.client.get(PRODUCTS_URL, **self.hdr)
        assert r2.status_code == 200, r2.content[:300]

        assert len(r1.json()) == 2
        assert len(r2.json()) == 8
        assert all(row["stock_status"] == "low_stock" for row in r2.json()), r2.json()
        assert len(large) == len(small), (len(small), len(large))

    # نفس الميزانية حين يُفلتَر بالقيمة المركّبة الجديدة.
    def test_combined_filter_query_count_stays_flat(self):
        for i in range(2):
            p = self._register(f"صنف 44-تحت-{i}")
            self._steady_seller(p, quantity_on_hand=10)

        with CaptureQueriesContext(connection) as small:
            r1 = self.client.get(f"{PRODUCTS_URL}?stock_status=under_min", **self.hdr)
        assert r1.status_code == 200, r1.content[:300]

        for i in range(2, 8):
            p = self._register(f"صنف 44-تحت-{i}")
            self._steady_seller(p, quantity_on_hand=10)

        with CaptureQueriesContext(connection) as large:
            r2 = self.client.get(f"{PRODUCTS_URL}?stock_status=under_min", **self.hdr)
        assert r2.status_code == 200, r2.content[:300]

        assert len(r1.json()) == 2
        assert len(r2.json()) == 8
        assert len(large) == len(small), (len(small), len(large))


class LookupViewUnaffectedTest(SuggestedMinHttpTestBase):
    """(g): `?view=lookup` بلا مساس — لا حدود في عقده أصلاً، فالشارة تبقى
    محكومةً بالحدّ اليدوي وحده (غيابه ⇒ صفر)، وعدد استعلاماته لا يتأثّر
    بوجود بياناتٍ تُنتج حدّاً محسوباً لو استُدعيت خرائط #44 هنا خطأً."""

    def test_lookup_ignores_the_computed_min_even_when_available_is_low(self):
        product = self._register("منتج للمنتقي 44")
        self._steady_seller(product, quantity_on_hand=10)  # 10 ≤ 42 لو حُسب

        lookup = self.client.get(f"{PRODUCTS_URL}?view=lookup", **self.hdr)
        assert lookup.status_code == 200, lookup.content[:300]
        row = next(r for r in lookup.json() if r["sku"] == product.sku)
        assert row["stock_status"] == "in_stock", row  # لا حدّ مقترَح في هذا العقد
        assert "suggested_min" not in row, row

        table_row = self._list()[product.sku]
        assert table_row["stock_status"] == "low_stock", table_row  # نفس المنتج، عقدٌ آخر

    def test_lookup_query_count_is_unaffected_by_suggested_min_eligible_data(self):
        self._register("منتج عادي 44")

        with CaptureQueriesContext(connection) as before:
            res_before = self.client.get(f"{PRODUCTS_URL}?view=lookup", **self.hdr)
        assert res_before.status_code == 200, res_before.content[:300]

        rich = self._register("منتج بسجل مبيعات 44")
        self._steady_seller(rich, quantity_on_hand=10)

        with CaptureQueriesContext(connection) as after:
            res_after = self.client.get(f"{PRODUCTS_URL}?view=lookup", **self.hdr)
        assert res_after.status_code == 200, res_after.content[:300]

        assert len(after) == len(before), (len(before), len(after))


class ServiceExclusionTest(SuggestedMinHttpTestBase):
    """(h): الخدمة تبقى خارج هذا كلّه — «متوفّر» دائماً، ولا تدخل الفلتر
    المركّب حتى لو مُنحت سجلّ حركةٍ (لن يُحسب لها اقتراحٌ أصلاً، #44)."""

    def test_service_stays_in_stock_and_out_of_the_combined_filter(self):
        service = self._register("خدمة تركيب 44", is_service=True)

        body = self._get(service.id)
        assert body["stock_status"] == "in_stock", body

        under_min = self.client.get(f"{PRODUCTS_URL}?stock_status=under_min", **self.hdr)
        assert service.sku not in {r["sku"] for r in under_min.json()}


class DashboardAgreesWithTheItemsScreenTest(SuggestedMinHttpTestBase):
    """بطاقة الداشبورد وشاشة الأصناف رقمٌ واحدٌ لا رقمان.

    البطاقة تقول حرفياً «{n} منتج تحت الحد الأدنى» — وهي نفس عبارة الفلتر
    الجديد. فلو قرأت البطاقة بالحدّ اليدوي وحده بينما تقرأ الشاشة بالمحسوب،
    لقال المالكُ صباحاً «ثلاثة» بينما تعرض الشاشة ثلاثمئة. هذا الاختبار يمنع
    ذلك بالبناء لا بالانتباه.
    """

    def test_dashboard_low_stock_count_matches_the_items_screen(self):
        for i in range(3):
            self._steady_seller(self._register(f"بائع لوحة {i}"), quantity_on_hand=10)

        listed = self.client.get(f"{PRODUCTS_URL}?stock_status=low_stock", **self.hdr)
        assert listed.status_code == 200, listed.content[:300]
        listed_count = len(listed.json())
        assert listed_count == 3, listed.json()

        dash = self.client.get("/api/dashboard/", **self.hdr)
        assert dash.status_code == 200, dash.content[:300]
        inventory = dash.json()["inventory"]
        assert inventory["low_stock"] == listed_count, (inventory, listed_count)
