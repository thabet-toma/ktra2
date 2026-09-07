"""تصليب السطح العام: إبطال كاش النشر، ترقيم الحملات، وانتقاء المنتجات بمعرّفاتها.

THA-166 م٢ (تصحيح): المصدر `store.StoreProduct`، والنشر/الإخفاء PATCH على
`/api/store/admin/products/` (`is_active`) لا `/api/inventory/products/`.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from store.models import StoreCollection, StoreProduct
from tenants.services import create_company

#: اختبارات الكاش تحتاج كاشاً حقيقياً: `core/test_settings.py` يفرض DummyCache
#: على كل الاختبارات، وتحته يمرّ اختبار الإبطال حتى بلا سطر إبطال واحد —
#: فحصٌ لا يقدر أن يفشل. LocMem هنا يجعله فحصاً فعلياً.
REAL_CACHE = override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "store-invalidation-tests",
        }
    }
)


class StorePublicSurfaceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="surf", password="pw123456")
        cls.tenant = create_company("شركة السطح", cls.user)
        cls.tenant.store_slug = "surface"
        cls.tenant.save()

        cls.published = [
            StoreProduct.objects.create(
                tenant=cls.tenant, name_ar=f"منتج {i}",
                price=Decimal("10.00"), is_active=True,
            )
            for i in range(1, 6)
        ]

    def setUp(self):
        cache.clear()
        self.public = APIClient()
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    # ── THA-423: إبطال الكاش عند كتابات النشر ──────────────────────────

    @REAL_CACHE
    def test_publishing_a_product_shows_it_immediately(self):
        """نشر منتج يظهر فوراً — الكاش لا يحجبه دقيقةً كاملة."""
        before = self.public.get("/api/store/surface/products/").json()["count"]

        hidden = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="منتج جديد",
            price=Decimal("20.00"), is_active=False,
        )
        res = self.auth.patch(
            f"/api/store/admin/products/{hidden.id}/",
            {"is_active": True}, format="json",
        )
        self.assertIn(res.status_code, (200, 202), res.content[:300])

        after = self.public.get("/api/store/surface/products/").json()
        self.assertEqual(after["count"], before + 1)
        self.assertIn(hidden.id, [r["id"] for r in after["results"]])

    @REAL_CACHE
    def test_unpublishing_a_product_hides_it_immediately(self):
        """سحب منتج من المتجر يُخفيه فوراً — لا يبقى مطلوباً دقيقةً بعد سحبه."""
        target = self.published[0]
        self.public.get("/api/store/surface/products/")  # يملأ الكاش

        res = self.auth.patch(
            f"/api/store/admin/products/{target.id}/",
            {"is_active": False}, format="json",
        )
        self.assertIn(res.status_code, (200, 202), res.content[:300])

        after = self.public.get("/api/store/surface/products/").json()
        self.assertNotIn(target.id, [r["id"] for r in after["results"]])

    @REAL_CACHE
    def test_cache_version_is_per_tenant(self):
        """رفع نسخة شركة لا يمسح كاش شركة أخرى — العزل يسري على الكاش."""
        other_user = User.objects.create_user(username="surf2", password="pw123456")
        other = create_company("شركة أخرى", other_user)
        other.store_slug = "surface2"
        other.save()
        StoreProduct.objects.create(
            tenant=other, name_ar="منتج الأخرى", price=Decimal("30.00"), is_active=True,
        )
        first = self.public.get("/api/store/surface2/products/").json()["count"]

        self.auth.patch(
            f"/api/store/admin/products/{self.published[0].id}/",
            {"price": "77.00"}, format="json",
        )
        second = self.public.get("/api/store/surface2/products/").json()["count"]
        self.assertEqual(first, second)

    # ── THA-422: ترقيم قائمة الحملات ───────────────────────────────────

    def test_collections_list_is_paginated(self):
        """قائمة الحملات نقطة عامة — ترقيمها إلزامي كقائمة المنتجات."""
        for i in range(3):
            StoreCollection.objects.create(
                tenant=self.tenant, title=f"حملة {i}", slug=f"camp-{i}",
            )
        body = self.public.get("/api/store/surface/collections/").json()
        self.assertIsInstance(body, dict)
        self.assertEqual(
            set(body) & {"count", "next", "previous", "results"},
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(body["count"], 3)

    # ── معامل ids — تحتاجه السلة لإعادة التسعير ────────────────────────

    def test_products_can_be_selected_by_ids(self):
        """السلة تعيد تسعير بنودها بنداء واحد بمعرّفاتها، لا بنداء لكل بند."""
        wanted = [self.published[0].id, self.published[2].id]
        body = self.public.get(
            "/api/store/surface/products/",
            {"ids": ",".join(str(i) for i in wanted)},
        ).json()
        self.assertEqual(sorted(r["id"] for r in body["results"]), sorted(wanted))

    def test_ids_is_capped_and_ignores_garbage(self):
        """معامل مجهول لا يفتح باباً: غير الرقمي يُتجاهل، والعدد مسقوف."""
        body = self.public.get(
            "/api/store/surface/products/", {"ids": "abc,,-1"},
        ).json()
        self.assertEqual(body["count"], 0)

    def test_ids_does_not_leak_another_tenants_product(self):
        other_user = User.objects.create_user(username="surf3", password="pw123456")
        other = create_company("ثالثة", other_user)
        foreign = StoreProduct.objects.create(
            tenant=other, name_ar="منتج أجنبي", price=Decimal("50.00"), is_active=True,
        )
        body = self.public.get(
            "/api/store/surface/products/", {"ids": str(foreign.id)},
        ).json()
        self.assertEqual(body["count"], 0)
