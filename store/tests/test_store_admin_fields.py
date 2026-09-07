"""لوحة إدارة المتجر على `StoreProduct` — CRUD كامل، وحرّاسا الحفظ يعودان 400.

THA-166 م٢ (تصحيح): هذا الملف كان يحرس حصر الحقول القابلة للتعديل على منتجٍ
**مخزني** (`inventory.Product`, `STORE_EDITABLE_ON_INVENTORY`) وتوليد رمزٍ
تسلسليٍّ (`sku`) — كلاهما مفهومٌ خاصٌّ بالمسار القديم الذي لم تعد لوحة المتجر
تكتب عليه. `StoreProduct` لا `sku` له، ولا تمييز «مخزني/متجر خالص»: كل صفٍّ
فيه ملكُ اللوحة كاملاً بالتعريف (يُنسَخ مرّةً من `inventory.Product` إن وُجد
ثم يتباعدان — `imported_from_product_id` رقمٌ مجرَّدٌ لا يعيد فتح تلك الصلة).
لذلك حُذف حصر الحقول من الكود (`STORE_EDITABLE_ON_INVENTORY`) ومن هنا،
واستُبدلت اختبارات توليد الـSKU باختبار الحرّاسين الفعليّين (م٢).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from store.models import StoreBrand, StoreCategory, StoreProduct
from tenants.services import create_company


class StoreProductAdminCrudTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="fs", password="pw123456")
        cls.tenant = create_company("شركة الحقول", cls.user)
        cls.tenant.store_slug = "fields"
        cls.tenant.save()
        cls.brand = StoreBrand.objects.create(tenant=cls.tenant, name="عام")
        cls.category = StoreCategory.objects.create(
            tenant=cls.tenant, name="فئة", slug="cat-1")

    def setUp(self):
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    # ── إنشاءٌ كاملٌ وأدنى ────────────────────────────────────────────────

    def test_minimal_creation_needs_only_the_arabic_name(self):
        res = self.auth.post(
            "/api/store/admin/products/", {"name_ar": "منتجٌ بسيط"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        body = res.json()
        self.assertTrue(body["is_active"])
        self.assertEqual(body["stock_state"], StoreProduct.STOCK_IN_STOCK)
        self.assertTrue(body["slug"])  # يُولَّد تلقائياً

    def test_name_ar_is_required(self):
        res = self.auth.post("/api/store/admin/products/", {}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_full_creation_with_brand_categories_and_images(self):
        res = self.auth.post("/api/store/admin/products/", {
            "name_ar": "ثلاجة دولابي فاخرة", "name_en": "Fridge",
            "brand": self.brand.id, "categories": [self.category.id],
            "unit": "قطعة", "price": "3500.00", "sale_price": "3200.00",
            "stock_state": StoreProduct.STOCK_PREORDER,
            "description": "وصفٌ كامل",
            "initial_images": ["https://img.com/a.jpg", "https://img.com/b.jpg"],
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content[:300])
        body = res.json()
        self.assertEqual(body["brand"], self.brand.id)
        self.assertEqual(body["categories"], [self.category.id])
        self.assertEqual(body["stock_state"], "preorder")
        self.assertEqual(len(body["images"]), 2)

    def test_the_slug_is_read_only_and_auto_generated(self):
        res = self.auth.post(
            "/api/store/admin/products/",
            {"name_ar": "منتج", "slug": "attempted-override"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertNotEqual(res.json()["slug"], "attempted-override")

    # ── التعديل — كل الحقول مفتوحة (لا حصر «مخزني/متجر») ────────────────

    def test_every_field_is_editable_because_the_product_is_wholly_the_panels(self):
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="قديم", price=Decimal("50.00"),
        )
        res = self.auth.patch(f"/api/store/admin/products/{product.id}/", {
            "name_ar": "اسمٌ جديد", "price": "60.00",
            "stock_state": StoreProduct.STOCK_OUT_OF_STOCK,
            "description": "وصفٌ جديد",
        }, format="json")
        self.assertEqual(res.status_code, 200, res.content[:300])
        product.refresh_from_db()
        self.assertEqual(product.name_ar, "اسمٌ جديد")
        self.assertEqual(product.price, Decimal("60.00"))
        self.assertEqual(product.stock_state, StoreProduct.STOCK_OUT_OF_STOCK)

    def test_categories_can_be_replaced_on_update(self):
        product = StoreProduct.objects.create(tenant=self.tenant, name_ar="منتج")
        other_cat = StoreCategory.objects.create(
            tenant=self.tenant, name="فئة أخرى", slug="cat-2")
        res = self.auth.patch(f"/api/store/admin/products/{product.id}/", {
            "categories": [other_cat.id],
        }, format="json")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(list(product.categories.values_list("id", flat=True)), [other_cat.id])

    # ── THA-166 م٢: حرّاسا الحفظ يعودان 400 لا 500 ──────────────────────

    def test_zero_sale_price_is_a_400_not_a_500(self):
        res = self.auth.post("/api/store/admin/products/", {
            "name_ar": "منتج", "price": "100.00", "sale_price": "0.00",
        }, format="json")
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("sale_price", str(res.content, "utf-8"))

    def test_negative_sale_price_is_a_400_not_a_500(self):
        res = self.auth.post("/api/store/admin/products/", {
            "name_ar": "منتج", "price": "100.00", "sale_price": "-5.00",
        }, format="json")
        self.assertEqual(res.status_code, 400, res.content[:300])

    def test_updating_into_a_non_positive_sale_price_is_also_a_400(self):
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="منتج", price=Decimal("100.00"),
        )
        res = self.auth.patch(f"/api/store/admin/products/{product.id}/", {
            "sale_price": "0.00",
        }, format="json")
        self.assertEqual(res.status_code, 400, res.content[:300])
        product.refresh_from_db()
        self.assertIsNone(product.sale_price)

    # ── الحذف والفلترة بالحالة ───────────────────────────────────────────

    def test_scope_published_and_unpublished_filter_by_is_active(self):
        StoreProduct.objects.create(tenant=self.tenant, name_ar="منشور", is_active=True)
        StoreProduct.objects.create(tenant=self.tenant, name_ar="مسحوب", is_active=False)

        published = self.auth.get("/api/store/admin/products/?scope=published").json()
        unpublished = self.auth.get("/api/store/admin/products/?scope=unpublished").json()
        published_rows = published["results"] if isinstance(published, dict) else published
        unpublished_rows = unpublished["results"] if isinstance(unpublished, dict) else unpublished
        self.assertTrue(all(r["is_active"] for r in published_rows))
        self.assertTrue(all(not r["is_active"] for r in unpublished_rows))


class StoreBrandAndCategoryAdminCrudTest(TestCase):
    """CRUD بسيط للماركات والفئات — نفس الحراسة ونفس فلتر الشركة (THA-166 م٢)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bc", password="pw123456")
        cls.tenant = create_company("شركة الماركات", cls.user)
        cls.tenant.store_slug = "brands-cats"
        cls.tenant.save()

    def setUp(self):
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    def test_brand_crud(self):
        res = self.auth.post(
            "/api/store/admin/brands/", {"name": "سامسونج"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        brand_id = res.json()["id"]

        listed = self.auth.get("/api/store/admin/brands/").json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertIn(brand_id, [r["id"] for r in rows])

        res = self.auth.patch(
            f"/api/store/admin/brands/{brand_id}/", {"sort_order": 5}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])

    def test_category_depth_guard_returns_400_via_the_api(self):
        """`StoreCategory._reject_third_level` يعود 400 عبر الـAPI — نفس نمط
        الحارس على `StoreProduct.sale_price`، لا 500."""
        grandparent = StoreCategory.objects.create(
            tenant=self.tenant, name="جد", slug="grandparent")
        parent = StoreCategory.objects.create(
            tenant=self.tenant, name="أب", slug="parent", parent=grandparent)
        res = self.auth.post("/api/store/admin/categories/", {
            "name": "حفيد", "slug": "grandchild", "parent": parent.id,
        }, format="json")
        self.assertEqual(res.status_code, 400, res.content[:300])

    def test_category_and_brand_are_scoped_to_the_tenant(self):
        other_user = User.objects.create_user(username="bc2", password="pw123456")
        other = create_company("شركة أخرى", other_user)
        foreign_category = StoreCategory.objects.create(
            tenant=other, name="فئة أجنبية", slug="foreign")

        res = self.auth.patch(
            f"/api/store/admin/categories/{foreign_category.id}/",
            {"name": "استيلاء"}, format="json",
        )
        self.assertEqual(res.status_code, 404)
