"""عيوب مراجعة تطوير المتجر: صفحة الحملة المميّزة، وعزل الشركات في نقاط الإدارة."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product, ProductCategory, UnitOfMeasure
from inventory.services import record_stock_movement
from store.models import StoreCollection, StoreCollectionItem, StoreProductImage
from store.tests.test_public_leakage import PUBLIC_WHITELIST
from tenants.models import Tenant
from tenants.services import create_company


class StoreAdminScopingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uom = UnitOfMeasure.objects.create(code="PCS", name_ar="قطعة")

        cls.user = User.objects.create_user(username="owner_a", password="pw123456")
        cls.tenant = create_company("شركة أ", cls.user)
        cls.tenant.store_slug = "alpha"
        cls.tenant.save()

        cls.other_user = User.objects.create_user(username="owner_b", password="pw123456")
        cls.other = create_company("شركة ب", cls.other_user)
        cls.other.store_slug = "beta"
        cls.other.save()

        cls.p_pub = Product.objects.create(
            tenant=cls.tenant, sku="A-01", name_ar="منتج منشور",
            is_for_sale_online=True, online_price=Decimal("100.00"),
            quantity_on_hand=Decimal("5"), uom=cls.uom,
        )
        cls.p_hidden = Product.objects.create(
            tenant=cls.tenant, sku="A-02", name_ar="منتج غير منشور",
            is_for_sale_online=False, online_price=Decimal("999.00"),
            quantity_on_hand=Decimal("5"), uom=cls.uom,
        )
        cls.p_foreign = Product.objects.create(
            tenant=cls.other, sku="B-01", name_ar="منتج شركة أخرى",
            is_for_sale_online=True, online_price=Decimal("777.00"),
            quantity_on_hand=Decimal("5"), uom=cls.uom,
        )
        cls.foreign_collection = StoreCollection.objects.create(
            tenant=cls.other, title="حملة شركة ب", slug="beta-camp",
        )
        cls.foreign_category = ProductCategory.objects.create(
            tenant=cls.other, name="تصنيف شركة ب",
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
            featured_product=self.p_pub,
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
            featured_product=self.p_hidden,
        )
        res = self.public.get("/api/store/alpha/collections/offers/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["collection"]["featured_product"])

    def test_foreign_featured_product_is_not_exposed(self):
        """منتج شركة أخرى لا يظهر على متجرنا العام."""
        StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="camp",
            featured_product=self.p_foreign,
        )
        res = self.public.get("/api/store/alpha/collections/camp/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["collection"]["featured_product"])

    def test_campaign_payload_respects_the_public_whitelist(self):
        """صفحة الحملة نقطة عامة جديدة — تخضع لنفس قائمة الحقول البيضاء."""
        col = StoreCollection.objects.create(
            tenant=self.tenant, title="عروض", slug="w",
            featured_product=self.p_pub,
        )
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=col, product=self.p_pub,
        )
        body = self.public.get("/api/store/alpha/collections/w/").json()
        self.assertEqual(set(body["collection"]["featured_product"]), PUBLIC_WHITELIST)
        self.assertEqual(set(body["products"]["results"][0]), PUBLIC_WHITELIST)

    # ── عزل الشركات في نقاط الإدارة ────────────────────────────────────

    def test_collection_cannot_feature_foreign_product(self):
        res = self.auth.post(
            "/api/store/admin/collections/",
            {"title": "حملة", "slug": "c1", "featured_product": self.p_foreign.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_collection_item_cannot_reference_foreign_product(self):
        mine = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="c2",
        )
        res = self.auth.post(
            "/api/store/admin/collection-items/",
            {"collection": mine.id, "product": self.p_foreign.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(StoreCollectionItem.objects.filter(product=self.p_foreign).exists())

    def test_collection_item_cannot_target_foreign_collection(self):
        res = self.auth.post(
            "/api/store/admin/collection-items/",
            {"collection": self.foreign_collection.id, "product": self.p_pub.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            StoreCollectionItem.objects.filter(collection=self.foreign_collection).exists()
        )

    def test_product_cannot_reference_foreign_category(self):
        """التصنيف مرجع كتابةٍ كغيره — لا يُقبل تصنيف شركة أخرى."""
        res = self.auth.post(
            "/api/store/admin/products/",
            {"name_ar": "منتج جديد", "category": self.foreign_category.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(
            Product.objects.filter(category=self.foreign_category).exists()
        )

    def test_product_image_cannot_reference_foreign_product(self):
        res = self.auth.post(
            "/api/store/admin/product-images/",
            {"product": self.p_foreign.id, "image_url": "https://x/y.jpg"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(StoreProductImage.objects.filter(product=self.p_foreign).exists())

    # ── حذف منتج له حركة ────────────────────────────────────────────────

    def test_delete_product_with_history_reports_conflict(self):
        """منتج متجرٍ بِيع فعلاً لا يُحذف — والواجهة تُخبر بذلك بدل ادّعاء الحذف."""
        sold = Product.objects.create(
            tenant=self.tenant, sku="ST-SOLD1", name_ar="منتج متجر مبيع",
            is_store_only=True, is_for_sale_online=True, uom=self.uom,
        )
        record_stock_movement(
            product=sold, movement_type="IN", quantity=Decimal("5"),
            unit_cost=Decimal("10"), movement_date=date.today(), tenant=self.tenant,
        )
        res = self.auth.delete(f"/api/store/admin/products/{sold.id}/")
        self.assertEqual(res.status_code, 409)
        sold.refresh_from_db()
        self.assertTrue(Product.objects.filter(pk=sold.pk).exists())
        self.assertFalse(sold.is_for_sale_online)

    def test_inventory_product_is_not_deletable_from_the_store_panel(self):
        """صلاحية المتجر تسويقية — لا تهدم منتجاً مخزنياً ولو لم يتحرّك بعد."""
        stock_item = Product.objects.create(
            tenant=self.tenant, sku="A-09", name_ar="منتج مخزني بكر",
            is_store_only=False, uom=self.uom,
        )
        res = self.auth.delete(f"/api/store/admin/products/{stock_item.id}/")
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=stock_item.pk).exists())

    def test_store_only_product_without_history_is_deletable(self):
        """منتج المتجر الخالص يُحذف فعلاً — الحارس يضيّق ولا يقفل."""
        store_item = Product.objects.create(
            tenant=self.tenant, sku="ST-AAA111", name_ar="منتج متجر",
            is_store_only=True, is_for_sale_online=True, uom=self.uom,
        )
        res = self.auth.delete(f"/api/store/admin/products/{store_item.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Product.objects.filter(pk=store_item.pk).exists())
