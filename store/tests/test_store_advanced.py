"""اختبارات الميزات المتقدمة للمتجر: صور مخصصة، طلب مسبق، مظهر وخلفية، ومجموعات إعلانية."""
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import SystemAttachment
from inventory.models import Product, ProductCategory, UnitOfMeasure
from store.models import (
    StoreCollection,
    StoreCollectionItem,
    StoreProductImage,
    StoreSettings,
)
from tenants.models import RolePermission, Tenant, TenantSettings, UserCompanyMembership
from tenants.services import create_company


class StoreAdvancedFeaturesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uom = UnitOfMeasure.objects.create(code="PCS", name_ar="قطعة")
        cls.user = User.objects.create_user(username="admin_user", password="password123")
        cls.tenant = create_company("شركة المودة", cls.user)
        cls.tenant.store_slug = "almawada"
        cls.tenant.save()

        settings_row = cls.tenant.settings
        settings_row.company_name_primary = "متجر المودة الفاخر"
        settings_row.phone = "0599000000"
        settings_row.save()

        cls.cat = ProductCategory.objects.create(tenant=cls.tenant, name="أزياء")

        cls.p_stock = Product.objects.create(
            tenant=cls.tenant, sku="P-01", name_ar="فستان سهرة",
            is_for_sale_online=True, online_price=Decimal("150.00"),
            quantity_on_hand=Decimal("10"), category=cls.cat, uom=cls.uom,
        )
        cls.p_preorder = Product.objects.create(
            tenant=cls.tenant, sku="P-02", name_ar="عباية فاخرة تفصيل",
            is_for_sale_online=True, online_price=Decimal("220.00"),
            quantity_on_hand=Decimal("0"), allow_preorder=True,
            category=cls.cat, uom=cls.uom,
        )
        cls.p_out = Product.objects.create(
            tenant=cls.tenant, sku="P-03", name_ar="حقيبة نفدت",
            is_for_sale_online=True, online_price=Decimal("80.00"),
            quantity_on_hand=Decimal("0"), allow_preorder=False,
            category=cls.cat, uom=cls.uom,
        )

    def setUp(self):
        self.public_client = APIClient()
        self.auth_client = APIClient()
        self.auth_client.force_authenticate(user=self.user)
        self.auth_client.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    def test_preorder_availability_status(self):
        """المنتج برصيد 0 و allow_preorder=True تظهر حالته preorder."""
        res = self.public_client.get(f"/api/store/almawada/products/{self.p_preorder.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["availability"], "preorder")

        # المنتج برصيد 0 وبلا preorder تظهر حالته out
        res_out = self.public_client.get(f"/api/store/almawada/products/{self.p_out.id}/")
        self.assertEqual(res_out.status_code, 200)
        self.assertEqual(res_out.json()["availability"], "out")

    def test_custom_store_images_priority(self):
        """صور المتجر المخصصة تأخذ الأولوية وترتب بحسب is_cover و sort_order."""
        # 1. صورة عامة في SystemAttachment
        SystemAttachment.objects.create(
            tenant=self.tenant, related_table="products", related_id=self.p_stock.id,
            file_type="Product Image", file_path="https://img.com/fallback.jpg",
        )
        # قبل إضافة صور مخصصة: يظهر fallback
        res1 = self.public_client.get(f"/api/store/almawada/products/{self.p_stock.id}/")
        self.assertEqual(res1.json()["images"], ["https://img.com/fallback.jpg"])

        # 2. إضافة صورتين مخصصتين للمتجر
        StoreProductImage.objects.create(
            tenant=self.tenant, product=self.p_stock,
            image_url="https://img.com/custom-2.jpg", sort_order=2, is_cover=False,
        )
        StoreProductImage.objects.create(
            tenant=self.tenant, product=self.p_stock,
            image_url="https://img.com/custom-cover.jpg", sort_order=1, is_cover=True,
        )

        res2 = self.public_client.get(f"/api/store/almawada/products/{self.p_stock.id}/")
        images = res2.json()["images"]
        self.assertEqual(images, ["https://img.com/custom-cover.jpg", "https://img.com/custom-2.jpg"])

    def test_store_theme_settings_management_and_public_view(self):
        """إدارة ثيم وخلفية المتجر من لوحة الإدارة وقراءتها من الواجهة العامة."""
        patch_res = self.auth_client.patch("/api/store/admin/settings/", {
            "hero_title": "موسم صيف 2026",
            "background_image_url": "https://img.com/bg.jpg",
            "theme_preset": "warm_luxury",
            "primary_color": "#b45309",
            "instagram_url": "https://instagram.com/almawada",
            "whatsapp_number": "970599000000",
        }, format="json")
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["hero_title"], "موسم صيف 2026")

        # التحقق من ظهورها في نقطة المتجر العامة
        pub_res = self.public_client.get("/api/store/almawada/")
        self.assertEqual(pub_res.status_code, 200)
        data = pub_res.json()
        self.assertEqual(data["hero_title"], "موسم صيف 2026")
        self.assertEqual(data["background_image_url"], "https://img.com/bg.jpg")
        self.assertEqual(data["theme_preset"], "warm_luxury")
        self.assertEqual(data["primary_color"], "#b45309")
        self.assertEqual(data["instagram_url"], "https://instagram.com/almawada")
        self.assertEqual(data["phone"], "970599000000")

    def test_collections_and_campaign_landing_pages(self):
        """إنشاء مجموعة / حملة إعلانية واستعراض صفحة الهبوط العامة لها."""
        col_res = self.auth_client.post("/api/store/admin/collections/", {
            "title": "عروض العيد الحصرية",
            "slug": "eid-offers",
            "description": "تشكيلة خاصة بأفضل الأسعار مع توصيل فوري",
            "badge_text": "خصم 20%",
            "featured_product": self.p_preorder.id,
            "is_active": True,
        }, format="json")
        self.assertEqual(col_res.status_code, 201)
        col_id = col_res.json()["id"]

        # إضافة منتجات للمجموعة
        item_res = self.auth_client.post("/api/store/admin/collection-items/", {
            "collection": col_id,
            "product": self.p_stock.id,
            "sort_order": 1,
        }, format="json")
        self.assertEqual(item_res.status_code, 201)

        # استعراض قائمة المجموعات العامة
        list_res = self.public_client.get("/api/store/almawada/collections/")
        self.assertEqual(list_res.status_code, 200)
        # مُرقَّمة كقائمة المنتجات (THA-422): نقطة عامة لا تردّ قائمة بلا حدّ.
        listing = list_res.json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["results"][0]["slug"], "eid-offers")
        self.assertEqual(listing["results"][0]["items_count"], 1)

        # استعراض صفحة هبوط الحملة العامة
        detail_res = self.public_client.get("/api/store/almawada/collections/eid-offers/")
        self.assertEqual(detail_res.status_code, 200)
        body = detail_res.json()
        self.assertEqual(body["collection"]["title"], "عروض العيد الحصرية")
        self.assertEqual(body["collection"]["featured_product"]["id"], self.p_preorder.id)
        self.assertEqual(len(body["products"]["results"]), 1)
        self.assertEqual(body["products"]["results"][0]["id"], self.p_stock.id)

    def test_direct_store_product_creation_and_management(self):
        """إضافة منتج جديد مباشرة للمتجر دون اشتراط وجوده في المخزن أو شجرة المنتجات."""
        # 1. إنشاء منتج متجر مباشر (ثلاجة مثلاً)
        create_res = self.auth_client.post("/api/store/admin/products/", {
            "name_ar": "ثلاجة دولابي فاخرة LG 18 قدم",
            "name_en": "LG Side-by-Side Refrigerator 18 Cu Ft",
            "brand": "LG",
            "online_price": "3500.00",
            "online_description": "تبريد ذكي إنفرتر مع موزع مياه وضمان 10 سنوات",
            "allow_preorder": True,
            "initial_images": ["https://img.com/fridge1.jpg", "https://img.com/fridge2.jpg"],
        }, format="json")
        self.assertEqual(create_res.status_code, 201)
        prod_data = create_res.json()
        prod_id = prod_data["id"]
        self.assertTrue(prod_data["sku"].startswith("ST-"))
        self.assertTrue(prod_data["is_for_sale_online"])
        self.assertTrue(prod_data["is_store_only"])
        self.assertTrue(prod_data["allow_preorder"])
        self.assertEqual(prod_data["name_ar"], "ثلاجة دولابي فاخرة LG 18 قدم")
        self.assertEqual(len(prod_data["images"]), 2)

        # 2. التحقق من عزل المنتج عن شاشات المنتجات المخزنية ومحددات فواتير البيع (ERP Isolation)
        erp_lookup_res = self.auth_client.get("/api/inventory/products/?view=lookup&search=ثلاجة")
        self.assertEqual(erp_lookup_res.status_code, 200)
        # يجب ألا يظهر المنتج في محددات الفواتير إطلاقاً
        erp_lookup_data = erp_lookup_res.json()
        erp_lookup_items = erp_lookup_data if isinstance(erp_lookup_data, list) else erp_lookup_data.get("results", [])
        erp_lookup_ids = [p["id"] for p in erp_lookup_items]
        self.assertNotIn(prod_id, erp_lookup_ids)

        erp_list_res = self.auth_client.get("/api/inventory/products/?search=ثلاجة")
        self.assertEqual(erp_list_res.status_code, 200)
        # يجب ألا يظهر في شاشة إدارة المنتجات والمخزن
        erp_list_data = erp_list_res.json()
        erp_list_items = erp_list_data if isinstance(erp_list_data, list) else erp_list_data.get("results", [])
        erp_list_ids = [p["id"] for p in erp_list_items]
        self.assertNotIn(prod_id, erp_list_ids)

        # 3. التحقق من ظهور المنتج في قائمة المتجر العامة للزوار
        pub_list_res = self.public_client.get("/api/store/almawada/products/?q=ثلاجة")
        self.assertEqual(pub_list_res.status_code, 200)
        pub_data = pub_list_res.json()
        self.assertEqual(pub_data["count"], 1)
        self.assertEqual(pub_data["results"][0]["id"], prod_id)
        self.assertEqual(pub_data["results"][0]["price"], "3500.00")
        self.assertEqual(pub_data["results"][0]["availability"], "preorder")
        self.assertEqual(len(pub_data["results"][0]["images"]), 2)

        # 3. تعديل سعر ووصف المنتج
        patch_res = self.auth_client.patch(f"/api/store/admin/products/{prod_id}/", {
            "online_price": "3399.00",
            "brand": "LG Electronics",
        }, format="json")
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["online_price"], "3399.00")

        # 4. حذف المنتج من المتجر
        del_res = self.auth_client.delete(f"/api/store/admin/products/{prod_id}/")
        self.assertIn(del_res.status_code, [200, 204])

        # التأكد من عدم ظهوره في المتجر العام
        pub_after_del = self.public_client.get("/api/store/almawada/products/?q=ثلاجة")
        self.assertEqual(pub_after_del.json()["count"], 0)

    def test_product_image_overlay_customization_and_storefront_display(self):
        """تخصيص نص إعلاني وبادج مائل فوق صورة المنتج والتحقق من ظهوره في المتجر العام."""
        # 1. إضافة صورة مخصصة مع شريط إعلاني ترويجي
        img_res = self.auth_client.post("/api/store/admin/product-images/", {
            "product": self.p_stock.id,
            "image_url": "https://img.com/promo-stock.jpg",
            "is_cover": True,
            "sort_order": 1,
            "overlay_text": "🔥 عرض خاص لأسبوع — السعر 100 ₪",
            "overlay_style": "diagonal_ribbon",
            "overlay_color": "red_fire",
        }, format="json")
        self.assertEqual(img_res.status_code, 201)
        img_data = img_res.json()
        self.assertEqual(img_data["overlay_text"], "🔥 عرض خاص لأسبوع — السعر 100 ₪")
        self.assertEqual(img_data["overlay_style"], "diagonal_ribbon")
        self.assertEqual(img_data["overlay_color"], "red_fire")

        # 2. التحقق من عودة بيانات الشريط الإعلاني في المتجر العام (قائمة المنتجات)
        list_res = self.public_client.get("/api/store/almawada/products/")
        self.assertEqual(list_res.status_code, 200)
        items = list_res.json()["results"]
        target_prod = next((p for p in items if p["id"] == self.p_stock.id), None)
        self.assertIsNotNone(target_prod)
        self.assertIsNotNone(target_prod.get("cover_overlay"))
        self.assertEqual(target_prod["cover_overlay"]["text"], "🔥 عرض خاص لأسبوع — السعر 100 ₪")
        self.assertEqual(target_prod["cover_overlay"]["style"], "diagonal_ribbon")
        self.assertEqual(target_prod["cover_overlay"]["color"], "red_fire")

        # 3. التحقق من عودة بيانات الشريط في صفحة تفاصيل المنتج المنفردة
        detail_res = self.public_client.get(f"/api/store/almawada/products/{self.p_stock.id}/")
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.json()
        self.assertIsNotNone(detail_data.get("cover_overlay"))
        self.assertEqual(detail_data["cover_overlay"]["text"], "🔥 عرض خاص لأسبوع — السعر 100 ₪")


