"""THA-166 م٦ — كتلُ الصفحة الرئيسية.

قسم ب (قاعدة السقوط، أهمُّ قرارٍ في المرحلة): متجرٌ بلا كتلةٍ واحدةٍ مفعَّلة
يعرض ما يعرضه اليوم بالضبط — `/products/` و`/<slug>/` لا يستوردان من هذا
الملف إطلاقاً، و`/home/` وحدها الجديدة وتردّ `{"blocks": []}`.

قسم ج (الأداء): عددُ استعلامات `/home/` **ثابتٌ** بصرف النظر عن عدد الكتل
أو حجم الكتالوج — نفس منهج `store/tests/test_store_facets.py::FacetQueryBudgetTest`
(درسُ ٣٥٠١ استعلام).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from datetime import timedelta

from rest_framework.test import APIClient

from store.models import (
    StoreCategory,
    StoreCollection,
    StoreCollectionItem,
    StoreHomeBlock,
    StoreProduct,
    StoreProductView,
)
from tenants.models import Tenant
from tenants.services import create_company


def _tenant(slug):
    return Tenant.objects.create(
        CompanyName=f"شركة {slug}", SubscriptionPlan="Pro", Status="Active",
        store_slug=slug,
    )


class HomeFallbackRuleTest(TestCase):
    """قسم ب — أهمُّ قرارٍ في المرحلة."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("home-fallback")
        StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج", price=Decimal("10.00"), is_active=True,
        )

    def test_home_endpoint_with_no_rows_returns_an_empty_block_list(self):
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json(), {"blocks": []})

    def test_products_endpoint_response_is_unchanged_by_the_feature_existing(self):
        """المنتجات لا تستورد من هذا الملف — ردُّها واحدٌ بصرف النظر عن
        وجود صفٍّ في `StoreHomeBlock` من عدمه."""
        before = self.client.get(f"/api/store/{self.tenant.store_slug}/products/").json()
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_HERO, is_active=False,
        )
        after = self.client.get(f"/api/store/{self.tenant.store_slug}/products/").json()
        self.assertEqual(before, after)

    def test_profile_endpoint_response_is_unchanged_by_the_feature_existing(self):
        before = self.client.get(f"/api/store/{self.tenant.store_slug}/").json()
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_HERO, is_active=True, title="لافتة",
        )
        after = self.client.get(f"/api/store/{self.tenant.store_slug}/").json()
        self.assertEqual(before, after)

    def test_inactive_block_does_not_appear_in_home(self):
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_HERO, title="غير مفعّلة",
            is_active=False,
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.json(), {"blocks": []})


class HomeEmptyBlockDisappearsTest(TestCase):
    """كتلةٌ بلا محتوىً تُحذف كلّياً — لا عنوانٌ فوق فراغ (قسم ب)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("home-empty")

    def test_category_row_with_no_products_is_dropped_entirely(self):
        category = StoreCategory.objects.create(
            tenant=self.tenant, name="فئة فارغة", slug="empty-cat",
        )
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_CATEGORY_ROW,
            title="فئة بلا منتجات", source_id=category.id,
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["blocks"], [])

    def test_most_viewed_with_zero_views_is_dropped(self):
        StoreProduct.objects.create(tenant=self.tenant, name_ar="منتج", is_active=True)
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_MOST_VIEWED, title="الأكثر مشاهدة",
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.json()["blocks"], [])

    def test_active_campaigns_with_no_active_campaign_is_dropped(self):
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_ACTIVE_CAMPAIGNS, title="الحملات",
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.json()["blocks"], [])

    def test_campaign_row_with_populated_active_collection_appears_with_its_products(self):
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="camp-1", is_active=True,
        )
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="منتج الحملة", price=Decimal("5.00"), is_active=True,
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=collection, store_product=product,
        )
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_CAMPAIGN_ROW,
            title="صفّ الحملة", source_id=collection.id,
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        blocks = res.json()["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["kind"], "campaign_row")
        self.assertEqual([p["id"] for p in blocks[0]["products"]], [product.id])


class HomeCampaignWindowTest(TestCase):
    """حملةٌ خارج نافذتها لا تظهر في `active_campaigns`، ولا كمصدرٍ لـ`campaign_row`."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("home-window")
        cls.product = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج", price=Decimal("9.00"), is_active=True,
        )

    def test_expired_campaign_is_absent_from_active_campaigns_block(self):
        now = timezone.now()
        StoreCollection.objects.create(
            tenant=self.tenant, title="حملة منتهية", slug="expired",
            is_active=True, starts_at=now - timedelta(days=10),
            ends_at=now - timedelta(days=1),
        )
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_ACTIVE_CAMPAIGNS, title="السارية",
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.json()["blocks"], [])

    def test_future_campaign_row_has_no_products_and_the_block_is_dropped(self):
        now = timezone.now()
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="حملةٌ مستقبلية", slug="future",
            is_active=True, starts_at=now + timedelta(days=5),
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=collection, store_product=self.product,
        )
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_CAMPAIGN_ROW,
            title="صفّ حملة مستقبلية", source_id=collection.id,
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        self.assertEqual(res.json()["blocks"], [])

    def test_active_campaign_within_window_appears(self):
        now = timezone.now()
        StoreCollection.objects.create(
            tenant=self.tenant, title="حملة سارية", slug="live",
            is_active=True, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=1),
        )
        StoreHomeBlock.objects.create(
            tenant=self.tenant, kind=StoreHomeBlock.KIND_ACTIVE_CAMPAIGNS, title="السارية",
        )
        res = self.client.get(f"/api/store/{self.tenant.store_slug}/home/")
        blocks = res.json()["blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual([c["slug"] for c in blocks[0]["campaigns"]], ["live"])


class HomeBlockModelGuardsTest(TestCase):
    """قسم ج/أ — سقفُ العشر ووجهةٌ مصنَّفةٌ لشركةٍ أخرى، على مستوى النموذج."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = _tenant("home-guard-a")
        cls.tenant_b = _tenant("home-guard-b")
        cls.collection_b = StoreCollection.objects.create(
            tenant=cls.tenant_b, title="حملة الشركة الأخرى", slug="other-camp", is_active=True,
        )

    def test_eleventh_active_block_is_rejected(self):
        for _ in range(StoreHomeBlock.MAX_ACTIVE_BLOCKS):
            StoreHomeBlock.objects.create(
                tenant=self.tenant_a, kind=StoreHomeBlock.KIND_HERO, is_active=True,
            )
        with self.assertRaises(Exception):
            StoreHomeBlock.objects.create(
                tenant=self.tenant_a, kind=StoreHomeBlock.KIND_HERO, is_active=True,
            )

    def test_inactive_block_does_not_count_toward_the_cap(self):
        for _ in range(StoreHomeBlock.MAX_ACTIVE_BLOCKS):
            StoreHomeBlock.objects.create(
                tenant=self.tenant_a, kind=StoreHomeBlock.KIND_HERO, is_active=True,
            )
        block = StoreHomeBlock.objects.create(
            tenant=self.tenant_a, kind=StoreHomeBlock.KIND_HERO, is_active=False,
        )
        self.assertIsNotNone(block.pk)

    def test_link_target_from_another_tenant_is_rejected(self):
        with self.assertRaises(Exception):
            StoreHomeBlock.objects.create(
                tenant=self.tenant_a, kind=StoreHomeBlock.KIND_HERO,
                link_kind=StoreHomeBlock.LINK_COLLECTION, link_id=self.collection_b.id,
            )

    def test_source_from_another_tenant_is_rejected(self):
        with self.assertRaises(Exception):
            StoreHomeBlock.objects.create(
                tenant=self.tenant_a, kind=StoreHomeBlock.KIND_CAMPAIGN_ROW,
                source_id=self.collection_b.id,
            )


class HomeBlockAdminApiTest(TestCase):
    """نفس الحرّاسين، لكن عبر `/api/store/admin/home-blocks/` — يعودان 400
    عبر `_ConvertsModelValidationErrors` لا 500."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="hb", password="pw123456")
        cls.tenant = create_company("شركة الكتل", cls.user)
        cls.tenant.store_slug = "home-admin"
        cls.tenant.save()
        cls.other_tenant = _tenant("home-admin-other")
        cls.other_collection = StoreCollection.objects.create(
            tenant=cls.other_tenant, title="حملة غريبة", slug="foreign", is_active=True,
        )

    def setUp(self):
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    def test_create_minimal_hero_block(self):
        res = self.auth.post(
            "/api/store/admin/home-blocks/", {"kind": "hero", "title": "لافتة"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertEqual(res.json()["limit"], StoreHomeBlock.DEFAULT_LIMIT)

    def test_eleventh_active_block_returns_400_with_a_specific_message(self):
        for _ in range(StoreHomeBlock.MAX_ACTIVE_BLOCKS):
            res = self.auth.post(
                "/api/store/admin/home-blocks/", {"kind": "hero", "is_active": True}, format="json",
            )
            self.assertEqual(res.status_code, 201, res.content[:300])
        res = self.auth.post(
            "/api/store/admin/home-blocks/", {"kind": "hero", "is_active": True}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("is_active", res.json())

    def test_link_target_from_another_tenant_returns_400(self):
        res = self.auth.post(
            "/api/store/admin/home-blocks/", {
                "kind": "hero", "link_kind": "collection", "link_id": self.other_collection.id,
            }, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("link_id", res.json())

    def test_source_from_another_tenant_returns_400(self):
        res = self.auth.post(
            "/api/store/admin/home-blocks/", {
                "kind": "campaign_row", "source_id": self.other_collection.id,
            }, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("source_id", res.json())

    def test_deleting_a_collection_used_by_a_block_is_blocked(self):
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="حملةٌ مستخدَمة", slug="used-camp", is_active=True,
        )
        res = self.auth.post(
            "/api/store/admin/home-blocks/", {
                "kind": "campaign_row", "source_id": collection.id, "title": "صفّ",
            }, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        del_res = self.auth.delete(f"/api/store/admin/collections/{collection.id}/")
        self.assertEqual(del_res.status_code, 400, del_res.content[:300])
        self.assertTrue(StoreCollection.objects.filter(pk=collection.id).exists())


class HomeQueryBudgetTest(TestCase):
    """قسم ج — الحارسُ الحقيقيّ للأداء: عددُ استعلامات `/home/` ثابتٌ بصرف
    النظر عن عدد الكتل وحجم الكتالوج (نفس منهج `FacetQueryBudgetTest`)."""

    @staticmethod
    def _build_home(tenant, *, block_count):
        collection = StoreCollection.objects.create(
            tenant=tenant, title="حملة", slug=f"camp-{tenant.pk}", is_active=True,
        )
        category = StoreCategory.objects.create(
            tenant=tenant, name="فئة", slug=f"cat-{tenant.pk}",
        )
        products = [
            StoreProduct.objects.create(
                tenant=tenant, name_ar=f"منتج {i}", price=Decimal("10.00"), is_active=True,
            )
            for i in range(block_count)
        ]
        for i, product in enumerate(products):
            StoreCollectionItem.objects.create(
                tenant=tenant, collection=collection, store_product=product, sort_order=i,
            )
            product.categories.add(category)
            StoreProductView.objects.create(
                tenant=tenant, store_product=product, view_date=timezone.localdate(), count=i + 1,
            )

        kinds = [
            (StoreHomeBlock.KIND_HERO, {}),
            (StoreHomeBlock.KIND_CAMPAIGN_ROW, {"source_id": collection.id}),
            (StoreHomeBlock.KIND_CATEGORY_ROW, {"source_id": category.id}),
            (StoreHomeBlock.KIND_FEATURED, {"source_id": collection.id}),
            (StoreHomeBlock.KIND_MOST_VIEWED, {}),
            (StoreHomeBlock.KIND_ACTIVE_CAMPAIGNS, {}),
        ]
        for i, (kind, extra) in enumerate(kinds):
            StoreHomeBlock.objects.create(
                tenant=tenant, kind=kind, title=f"كتلة {i}", sort_order=i, **extra,
            )

    def test_query_count_is_independent_of_block_and_catalog_size(self):
        small = _tenant("home-budget-small")
        self._build_home(small, block_count=3)

        big = _tenant("home-budget-big")
        self._build_home(big, block_count=40)

        with CaptureQueriesContext(connection) as small_ctx:
            res_small = self.client.get(f"/api/store/{small.store_slug}/home/")
        self.assertEqual(res_small.status_code, 200, res_small.content[:300])

        with CaptureQueriesContext(connection) as big_ctx:
            res_big = self.client.get(f"/api/store/{big.store_slug}/home/")
        self.assertEqual(res_big.status_code, 200, res_big.content[:300])

        self.assertEqual(
            len(small_ctx.captured_queries), len(big_ctx.captured_queries),
            "عددُ استعلامات /home/ يجب أن يبقى ثابتاً بصرف النظر عن عدد "
            "المنتجات في كل كتلة — تحقّق من عدم وجود استعلامٍ لكل كتلةٍ أو منتج.",
        )
