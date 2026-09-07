"""الكتالوجُ المستقلّ على السطح العام (مواصفة #166 — المرحلة ٢): القراءةُ من
`StoreProduct`، والخصمُ (منتجٍ مفردٍ أو حملة، الأكبر يفوز)، وسريانُ الحملة
بالتاريخ، والحرّاسُ الأربعة، وحدُّ الاستعلامات.

عزلُ التسريب في `test_public_leakage.py`؛ هذا الملف يغطّي حساب السعر الفعليّ
والخصم كما يراهما الزائر فعلاً عبر `/api/store/<slug>/products/`.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from store.models import StoreCollection, StoreCollectionItem, StoreProduct, StoreSettings
from tenants.models import Tenant


def _tenant(slug):
    return Tenant.objects.create(
        CompanyName=f"متجر {slug}", SubscriptionPlan="Pro", Status="Active",
        store_slug=slug,
    )


class DiscountWinnerTest(TestCase):
    """الأكبرُ خصماً يفوز — منتجٌ مقابل حملة، وحملةٌ مقابل حملة."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("disc")

    def _list(self):
        res = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        return {item["id"]: item for item in res.json()["results"]}

    def test_no_discount_leaves_price_and_original_null(self):
        StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة عادية", price=Decimal("100.00"),
        )
        row = list(self._list().values())[0]
        self.assertEqual(Decimal(row["price"]), Decimal("100.00"))
        self.assertIsNone(row["original_price"])
        self.assertIsNone(row["discount_percent"])

    def test_product_discount_alone(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
            sale_price=Decimal("90.00"),
        )
        row = self._list()[p.id]
        self.assertEqual(Decimal(row["price"]), Decimal("90.00"))
        self.assertEqual(Decimal(row["original_price"]), Decimal("100.00"))
        self.assertEqual(row["discount_percent"], 10)

    def test_campaign_discount_beats_smaller_product_discount(self):
        """منتجٌ خصمه ١٠٪ داخل حملةٍ خصمها ٣٠٪ ⇐ يظهر ٣٠٪ — الأفضل للزبون."""
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
            sale_price=Decimal("90.00"),
        )
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة الصيف", slug="summer-disc",
            discount_percent=Decimal("30.00"),
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=collection, store_product=p,
        )
        row = self._list()[p.id]
        self.assertEqual(Decimal(row["price"]), Decimal("70.00"))
        self.assertEqual(Decimal(row["original_price"]), Decimal("100.00"))
        self.assertEqual(row["discount_percent"], 30)

    def test_bigger_product_discount_beats_smaller_campaign(self):
        """والعكس: خصمٌ مفردٌ أكبر من خصم الحملة يفوز هو."""
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
            sale_price=Decimal("60.00"),
        )
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة صغيرة", slug="small-disc",
            discount_percent=Decimal("10.00"),
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=collection, store_product=p,
        )
        row = self._list()[p.id]
        self.assertEqual(Decimal(row["price"]), Decimal("60.00"))
        self.assertEqual(row["discount_percent"], 40)

    def test_campaign_against_campaign_the_bigger_percent_wins(self):
        """حملتان معاً — النسبة الأكبر تفوز بصرف النظر عن الأولوية."""
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة", price=Decimal("200.00"),
        )
        weak = StoreCollection.objects.create(
            tenant=self.tenant, title="ضعيفة", slug="weak-camp",
            discount_percent=Decimal("10.00"), priority=100,
        )
        strong = StoreCollection.objects.create(
            tenant=self.tenant, title="قوية", slug="strong-camp",
            discount_percent=Decimal("30.00"), priority=0,
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=weak, store_product=p,
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=strong, store_product=p,
        )
        row = self._list()[p.id]
        self.assertEqual(Decimal(row["price"]), Decimal("140.00"))
        self.assertEqual(row["discount_percent"], 30)

    def test_product_with_null_price_has_no_discount_fields(self):
        """«السعر عند الطلب» — لا خصمَ ولا أصليَّ ولا نسبة، ولو حمل sale_price."""
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="عند الطلب", price=None,
            sale_price=Decimal("50.00"),
        )
        row = self._list()[p.id]
        self.assertIsNone(row["price"])
        self.assertIsNone(row["original_price"])
        self.assertIsNone(row["discount_percent"])

    def test_stale_sale_price_higher_than_price_shows_no_discount(self):
        """الحارس الأوّل: `sale_price` ليس أدنى من `price` فعلياً ⇐ لا خصم."""
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سعرٌ باطل", price=Decimal("100.00"),
        )
        # نتجاوز الحارس التصاعدي عمداً (`sale_price` أعلى من `price` نفسه ليس
        # مرفوضاً عند الحفظ — الحارسُ يرفض فقط ما يُنزل السعر إلى صفرٍ فأقل)
        # لإثبات أن القراءة تحمي العرض حتى من بياناتٍ قديمة غير متّسقة.
        StoreProduct.objects.filter(pk=p.pk).update(sale_price=Decimal("150.00"))
        row = self._list()[p.id]
        self.assertEqual(Decimal(row["price"]), Decimal("100.00"))
        self.assertIsNone(row["original_price"])
        self.assertIsNone(row["discount_percent"])

    def test_zero_percent_campaign_shows_no_badge(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
        )
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="بلا خصم", slug="zero-disc",
            discount_percent=Decimal("0.00"),
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=collection, store_product=p,
        )
        row = self._list()[p.id]
        self.assertEqual(Decimal(row["price"]), Decimal("100.00"))
        self.assertIsNone(row["original_price"])
        self.assertIsNone(row["discount_percent"])


class CampaignWindowTest(TestCase):
    """سريانُ الحملة بالتاريخ — بلا `__date` إطلاقاً."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("window")
        cls.now = timezone.now()

    def setUp(self):
        self.client = APIClient()

    def _price_of(self, product):
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/products/{product.id}/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        return res.json()["price"]

    def _campaign(self, **kwargs):
        return StoreCollection.objects.create(
            tenant=self.tenant, discount_percent=Decimal("50.00"), **kwargs,
        )

    def test_both_null_bounds_means_always_active(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="دائمة", price=Decimal("100.00"))
        c = self._campaign(title="دائمة", slug="always")
        StoreCollectionItem.objects.create(tenant=self.tenant, collection=c, store_product=p)
        self.assertEqual(Decimal(self._price_of(p)), Decimal("50.00"))

    def test_future_start_is_not_active_yet(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="قادمة", price=Decimal("100.00"))
        c = self._campaign(
            title="قادمة", slug="future", starts_at=self.now + timedelta(days=1))
        StoreCollectionItem.objects.create(tenant=self.tenant, collection=c, store_product=p)
        self.assertEqual(Decimal(self._price_of(p)), Decimal("100.00"))

    def test_past_end_is_no_longer_active(self):
        """إعادةُ تشغيل حملةٍ منتهيةٍ تعديلُ تاريخٍ لا إعادةُ إدخال — لكن هنا لم تُعَد."""
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="منتهية", price=Decimal("100.00"))
        c = self._campaign(
            title="منتهية", slug="ended", ends_at=self.now - timedelta(days=1))
        StoreCollectionItem.objects.create(tenant=self.tenant, collection=c, store_product=p)
        self.assertEqual(Decimal(self._price_of(p)), Decimal("100.00"))
        # `discount_percent` لم يُمسَح — الحملة تسكت وحدها بشرط التاريخ فقط.
        c.refresh_from_db()
        self.assertEqual(c.discount_percent, Decimal("50.00"))

    def test_inactive_campaign_flag_overrides_valid_dates(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="معطّلة", price=Decimal("100.00"))
        c = self._campaign(title="معطّلة", slug="disabled", is_active=False)
        StoreCollectionItem.objects.create(tenant=self.tenant, collection=c, store_product=p)
        self.assertEqual(Decimal(self._price_of(p)), Decimal("100.00"))

    def test_within_open_window_is_active(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="نشطة", price=Decimal("100.00"))
        c = self._campaign(
            title="نشطة", slug="within",
            starts_at=self.now - timedelta(days=1),
            ends_at=self.now + timedelta(days=1),
        )
        StoreCollectionItem.objects.create(tenant=self.tenant, collection=c, store_product=p)
        self.assertEqual(Decimal(self._price_of(p)), Decimal("50.00"))


class PriceKillingDiscountGuardTest(TestCase):
    """الحارس الثاني: خصمٌ يُنزل السعرَ إلى صفرٍ أو دونه يُرفَض عند الحفظ."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("guard")

    def test_zero_sale_price_is_rejected(self):
        with self.assertRaises(ValidationError):
            StoreProduct.objects.create(
                tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
                sale_price=Decimal("0.00"),
            )

    def test_negative_sale_price_is_rejected(self):
        with self.assertRaises(ValidationError):
            StoreProduct.objects.create(
                tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
                sale_price=Decimal("-5.00"),
            )

    def test_positive_sale_price_is_fine(self):
        p = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="سلعة", price=Decimal("100.00"),
            sale_price=Decimal("1.00"),
        )
        self.assertEqual(p.sale_price, Decimal("1.00"))

    def test_hundred_percent_campaign_discount_is_rejected(self):
        with self.assertRaises(ValidationError):
            StoreCollection.objects.create(
                tenant=self.tenant, title="حملة", slug="c100",
                discount_percent=Decimal("100.00"),
            )

    def test_over_hundred_percent_campaign_discount_is_rejected(self):
        with self.assertRaises(ValidationError):
            StoreCollection.objects.create(
                tenant=self.tenant, title="حملة", slug="c150",
                discount_percent=Decimal("150.00"),
            )

    def test_99_percent_campaign_discount_is_fine(self):
        c = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="c99",
            discount_percent=Decimal("99.00"),
        )
        self.assertEqual(c.discount_percent, Decimal("99.00"))

    def test_objects_create_does_not_bypass_the_guard(self):
        """نفس فخّ `StoreCategory`: `clean()` وحدها لا تُستدعى من `save()`."""
        with self.assertRaises(ValidationError):
            StoreProduct.objects.create(
                tenant=self.tenant, name_ar="سلعة", sale_price=Decimal("0.00"),
            )


class ShowPricesHidesDiscountTest(TestCase):
    """الحارس الرابع: `show_prices=false` يُصفّر الثلاثة معاً."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("hidden-disc")
        cls.product = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="سلعة", price=Decimal("100.00"),
            sale_price=Decimal("80.00"),
        )
        StoreSettings.objects.create(tenant=cls.tenant, show_prices=False)

    def test_price_original_and_discount_are_all_null(self):
        res = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/{self.product.id}/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertIsNone(body["price"])
        self.assertIsNone(body["original_price"])
        self.assertIsNone(body["discount_percent"])


class TenantIsolationOnDiscountTest(TestCase):
    """عزلُ الشركات — خصمُ حملة شركةٍ لا يُطبَّق على منتج شركةٍ أخرى."""

    def test_a_foreign_campaign_never_touches_this_tenants_product(self):
        mine = _tenant("iso-a")
        theirs = _tenant("iso-b")
        p_mine = StoreProduct.objects.create(
            tenant=mine, name_ar="منتجي", price=Decimal("100.00"))
        p_theirs = StoreProduct.objects.create(
            tenant=theirs, name_ar="منتجهم", price=Decimal("100.00"))
        camp = StoreCollection.objects.create(
            tenant=theirs, title="حملتهم", slug="their-camp",
            discount_percent=Decimal("50.00"),
        )
        StoreCollectionItem.objects.create(
            tenant=theirs, collection=camp, store_product=p_theirs)

        res = APIClient().get(f"/api/store/{mine.store_slug}/products/{p_mine.id}/")
        self.assertEqual(Decimal(res.json()["price"]), Decimal("100.00"))
        res2 = APIClient().get(f"/api/store/{theirs.store_slug}/products/{p_theirs.id}/")
        self.assertEqual(Decimal(res2.json()["price"]), Decimal("50.00"))


class QueryBudgetTest(TestCase):
    """الحارسُ الحقيقيّ للأداء: عددُ الاستعلامات ثابتٌ لا يتناسب مع عدد المنتجات."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("budget")
        campaign = StoreCollection.objects.create(
            tenant=cls.tenant, title="حملة", slug="budget-camp",
            discount_percent=Decimal("15.00"),
        )
        for i in range(20):
            p = StoreProduct.objects.create(
                tenant=cls.tenant, name_ar=f"منتج {i}", price=Decimal("100.00"),
            )
            if i % 2 == 0:
                StoreCollectionItem.objects.create(
                    tenant=cls.tenant, collection=campaign, store_product=p)

    def test_query_count_does_not_grow_with_product_count(self):
        """THA-166 م٤: الصفحة الأولى بلا `?page=` صريح تحمل العدّاداتِ أيضاً
        (قسم أ)، فالأساس ارتفع من 6 إلى 13 — سبعةٌ إضافيةٌ لبناء `facets` و
        `price_range` (عدّاد الفئات: تجميعٌ + شجرة الفئات، عدّاد الماركات:
        تجميعٌ واحد، ثلاثُ راياتٍ: `on_sale`/`is_new`/`in_stock`، ومدى السعر)
        — كلّها ثابتةُ العدد بصرف النظر عن عدد المنتجات، وهو ما يبقى الاختبار
        يحرسه فعلياً. حارسُ التناسب مع عدد الفئات/الماركات في
        `test_store_facets.py` (`FacetQueryBudgetTest`)."""
        with CaptureQueriesContext(connection) as ctx:
            res = APIClient().get(
                f"/api/store/{self.tenant.store_slug}/products/",
                {"page_size": 20},
            )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(len(res.json()["results"]), 20)
        query_count = len(ctx.captured_queries)
        self.assertLessEqual(
            query_count, 13,
            f"عددُ الاستعلامات ({query_count}) يجب أن يبقى ثابتاً لا متناسباً "
            "مع عدد المنتجات (20 هنا) — تحقّق من عدم وجود استعلامٍ لكل صفّ. "
            "الأساس اليوم 13 (بعد THA-166 م٤): الشركة، إعدادات الأسعار، عدّ "
            "الصفحة، الاستعلام الرئيسي (بضمّ Max لخصم الحملة)، تحضير فئات "
            "المنتجات، صور المتجر، وسبعُ استعلاماتٍ للعدّادات السياقية.",
        )
