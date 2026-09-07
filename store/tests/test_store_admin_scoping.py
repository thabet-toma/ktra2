"""عيوب مراجعة تطوير المتجر: صفحة الحملة المميّزة، وعزل الشركات في نقاط الإدارة.

THA-166 م٢ (تصحيح): لوحة إدارة المتجر تكتب على `StoreProduct`/`StoreCategory`
حصراً. حذفٌ لثلاثة اختباراتٍ هنا موثَّقٌ أسفل الملف — الضمانة التي كانت
تحرسها (حمايةُ منتجٍ مخزنيٍّ من الحذف بسبب حركة `ProtectedError`) لم تعد
ممكنة الحدوث أصلاً: `StoreProduct` لا علاقة `PROTECT` تشير إليه إطلاقاً
(كل التوابع الثلاثة `CASCADE`)، ولا يحمل `is_store_only` — المفهوم بأكمله
خاصّ بـ`inventory.Product` الذي لم تعد لوحة المتجر تكتب عليه.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product
from store.models import StoreCategory, StoreCollection, StoreCollectionItem, StoreProduct, StoreProductImage
from store.tests.test_public_leakage import PUBLIC_WHITELIST
from tenants.services import create_company


class StoreAdminScopingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="owner_a", password="pw123456")
        cls.tenant = create_company("شركة أ", cls.user)
        cls.tenant.store_slug = "alpha"
        cls.tenant.save()

        cls.other_user = User.objects.create_user(username="owner_b", password="pw123456")
        cls.other = create_company("شركة ب", cls.other_user)
        cls.other.store_slug = "beta"
        cls.other.save()

        cls.p_pub = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج منشور", price=Decimal("100.00"),
            is_active=True,
        )
        cls.p_hidden = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج غير منشور", price=Decimal("999.00"),
            is_active=False,
        )
        cls.p_foreign = StoreProduct.objects.create(
            tenant=cls.other, name_ar="منتج شركة أخرى", price=Decimal("777.00"),
            is_active=True,
        )
        cls.foreign_collection = StoreCollection.objects.create(
            tenant=cls.other, title="حملة شركة ب", slug="beta-camp",
        )
        cls.foreign_category = StoreCategory.objects.create(
            tenant=cls.other, name="تصنيف شركة ب", slug="foreign-cat",
        )
        # منتجٌ مخزنيٌّ حقيقيٌّ لشركة أخرى — لاختبار عزل الحقل القديم
        # `featured_product` (لا يزال FK إلى `inventory.Product`) وحده.
        cls.foreign_inventory_product = Product.objects.create(
            tenant=cls.other, sku="B-INV-1", name_ar="منتج مخزني لشركة ب",
        )

    def setUp(self):
        self.public = APIClient()
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    # ── صفحة الحملة والمنتج المميّز ────────────────────────────────────

    def test_campaign_page_with_featured_product_returns_200(self):
        """حملة لها منتج مميّز تُفتح للزائر بدل أن تنهار."""
        StoreCollection.objects.create(
            tenant=self.tenant, title="عروض الصيف", slug="summer",
            featured_store_product=self.p_pub,
        )
        res = self.public.get("/api/store/alpha/collections/summer/")
        self.assertEqual(res.status_code, 200)
        featured = res.json()["collection"]["featured_product"]
        self.assertIsNotNone(featured)
        self.assertEqual(featured["id"], self.p_pub.id)
        self.assertEqual(Decimal(featured["price"]), Decimal("100.00"))
        self.assertEqual(featured["availability"], "available")

    def test_unpublished_featured_product_is_not_exposed(self):
        """منتج غير منشور لا يتسرّب للزائر لمجرّد تعيينه منتجاً مميّزاً."""
        StoreCollection.objects.create(
            tenant=self.tenant, title="عروض", slug="offers",
            featured_store_product=self.p_hidden,
        )
        res = self.public.get("/api/store/alpha/collections/offers/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["collection"]["featured_product"])

    def test_foreign_featured_product_is_not_exposed(self):
        """منتج شركة أخرى لا يظهر على متجرنا العام."""
        StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="camp",
            featured_store_product=self.p_foreign,
        )
        res = self.public.get("/api/store/alpha/collections/camp/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["collection"]["featured_product"])

    def test_campaign_payload_respects_the_public_whitelist(self):
        """صفحة الحملة نقطة عامة جديدة — تخضع لنفس قائمة الحقول البيضاء."""
        col = StoreCollection.objects.create(
            tenant=self.tenant, title="عروض", slug="w",
            featured_store_product=self.p_pub,
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=col, store_product=self.p_pub,
        )
        body = self.public.get("/api/store/alpha/collections/w/").json()
        self.assertEqual(set(body["collection"]["featured_product"]), PUBLIC_WHITELIST)
        self.assertEqual(set(body["products"]["results"][0]), PUBLIC_WHITELIST)

    # ── عزل الشركات في نقاط الإدارة ────────────────────────────────────

    def test_collection_cannot_feature_foreign_product(self):
        """الحقل القديم (`featured_product`، لا يزال FK إلى `inventory.Product`)
        يبقى محروساً بعزل الشركات كغيره من مراجع الكتابة."""
        res = self.auth.post(
            "/api/store/admin/collections/",
            {
                "title": "حملة", "slug": "c1",
                "featured_product": self.foreign_inventory_product.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_collection_cannot_feature_a_foreign_store_product(self):
        res = self.auth.post(
            "/api/store/admin/collections/",
            {
                "title": "حملة", "slug": "c1b",
                "featured_store_product": self.p_foreign.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_collection_item_cannot_reference_foreign_product(self):
        mine = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="c2",
        )
        res = self.auth.post(
            "/api/store/admin/collection-items/",
            {"collection": mine.id, "store_product": self.p_foreign.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            StoreCollectionItem.objects.filter(store_product=self.p_foreign).exists()
        )

    def test_collection_item_cannot_target_foreign_collection(self):
        res = self.auth.post(
            "/api/store/admin/collection-items/",
            {"collection": self.foreign_collection.id, "store_product": self.p_pub.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            StoreCollectionItem.objects.filter(collection=self.foreign_collection).exists()
        )

    def test_product_cannot_reference_foreign_category(self):
        """الفئة مرجع كتابةٍ كغيره — لا يُقبل تصنيف شركة أخرى."""
        res = self.auth.post(
            "/api/store/admin/products/",
            {"name_ar": "منتج جديد", "categories": [self.foreign_category.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            StoreProduct.objects.filter(
                name_ar="منتج جديد", categories=self.foreign_category
            ).exists()
        )

    def test_product_image_cannot_reference_foreign_product(self):
        res = self.auth.post(
            "/api/store/admin/product-images/",
            {"store_product": self.p_foreign.id, "image_url": "https://x/y.jpg"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            StoreProductImage.objects.filter(store_product=self.p_foreign).exists()
        )

    # ── الحذف ────────────────────────────────────────────────────────────

    def test_a_store_product_without_dependents_is_deletable(self):
        """منتجُ متجرٍ بلا توابع (صور/عضويّات حملة) يُحذف مباشرةً — `204`.

        THA-166 م٢ (تصحيح): لا `ProtectedError` ممكنة على `StoreProduct` (كل
        علاقاته `CASCADE`)، فلا حارس ٤٠٩ يُشبه القديم. حُذفت من هنا ثلاثة
        اختبارات كانت تحرس ذلك الحارس تحديداً على `inventory.Product`:
        `test_delete_product_with_history_reports_conflict` (409 عند حركة
        مخزنية) و`test_inventory_product_is_not_deletable_from_the_store_panel`
        (403 لمنتجٍ ليس `is_store_only`) و`test_store_only_product_without_history_is_deletable`
        (204 للمنتج الخالص) — الثلاثة افترضت أن لوحة المتجر تكتب على
        `Product`، وهذا لم يعد صحيحاً؛ `is_store_only` نفسه لا معنى له على
        `StoreProduct` لأن كل صفٍّ فيه **هو** ملك اللوحة بالتعريف.
        """
        res = self.auth.delete(f"/api/store/admin/products/{self.p_pub.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(StoreProduct.objects.filter(pk=self.p_pub.pk).exists())
