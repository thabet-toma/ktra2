"""تصليب السطح العام: إبطال كاش النشر، ترقيم الحملات، وانتقاء الأصناف بمعرّفاتها."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from inventory.models import Product, UnitOfMeasure
from store.models import StoreCollection
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
        cls.uom = UnitOfMeasure.objects.create(code="PCS", name_ar="قطعة")
        cls.user = User.objects.create_user(username="surf", password="pw123456")
        cls.tenant = create_company("شركة السطح", cls.user)
        cls.tenant.store_slug = "surface"
        cls.tenant.save()

        cls.published = [
            Product.objects.create(
                tenant=cls.tenant, sku=f"S-{i:02d}", name_ar=f"صنف {i}",
                is_for_sale_online=True, online_price=Decimal("10.00"),
                quantity_on_hand=Decimal("5"), uom=cls.uom,
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
        """نشر صنف يظهر فوراً — الكاش لا يحجبه دقيقةً كاملة."""
        before = self.public.get("/api/store/surface/products/").json()["count"]

        hidden = Product.objects.create(
            tenant=self.tenant, sku="S-NEW", name_ar="صنف جديد",
            is_for_sale_online=False, online_price=Decimal("20.00"),
            quantity_on_hand=Decimal("3"), uom=self.uom,
        )
        res = self.auth.patch(
            f"/api/inventory/products/{hidden.id}/",
            {"is_for_sale_online": True}, format="json",
        )
        self.assertIn(res.status_code, (200, 202), res.content[:300])

        after = self.public.get("/api/store/surface/products/").json()
        self.assertEqual(after["count"], before + 1)
        self.assertIn(hidden.id, [r["id"] for r in after["results"]])

    @REAL_CACHE
    def test_unpublishing_a_product_hides_it_immediately(self):
        """سحب صنف من المتجر يُخفيه فوراً — لا يبقى مطلوباً دقيقةً بعد سحبه."""
        target = self.published[0]
        self.public.get("/api/store/surface/products/")  # يملأ الكاش

        res = self.auth.patch(
            f"/api/inventory/products/{target.id}/",
            {"is_for_sale_online": False}, format="json",
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
        Product.objects.create(
            tenant=other, sku="O-01", name_ar="صنف الأخرى",
            is_for_sale_online=True, online_price=Decimal("30.00"),
            quantity_on_hand=Decimal("1"), uom=self.uom,
        )
        first = self.public.get("/api/store/surface2/products/").json()["count"]

        self.auth.patch(
            f"/api/inventory/products/{self.published[0].id}/",
            {"online_price": "77.00"}, format="json",
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
        foreign = Product.objects.create(
            tenant=other, sku="F-01", name_ar="صنف أجنبي",
            is_for_sale_online=True, online_price=Decimal("50.00"),
            quantity_on_hand=Decimal("1"), uom=self.uom,
        )
        body = self.public.get(
            "/api/store/surface/products/", {"ids": str(foreign.id)},
        ).json()
        self.assertEqual(body["count"], 0)
