"""T2 — منتج المخزون غير النشط لا يبلغ المتجر: لا يظهر ما نُسخ منه، ولا يُستورَد.

`StoreProduct` نسخةٌ مستقلة (`imported_from_product_id` رقمٌ مجرَّد لا FK)، فتعطيل
المنتج في المخزون لا يمسّها تلقائياً — يحجبها `published_products` (البوابة الوحيدة
للسطح العام) بقراءة حالة المنتج الأصل **في الشركة نفسها**، ويرفض الاستيرادُ
منتجاً معطَّلاً باسمه.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product
from store.models import StoreProduct
from tenants.services import create_company


class StoreInactiveProductTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="st_inact", password="pw123456")
        cls.tenant = create_company("شركة المتجر", cls.user)
        cls.tenant.store_slug = "inact-co"
        cls.tenant.save()
        cls.other_user = User.objects.create_user(username="st_inact2", password="pw123456")
        cls.other = create_company("شركة أخرى", cls.other_user)

        cls.live = Product.objects.create(tenant=cls.tenant, sku="SI-1", name_ar="حيّ")
        cls.dead = Product.objects.create(
            tenant=cls.tenant, sku="SI-2", name_ar="معطَّل", is_active=False)
        # منتجٌ بنفس الرقم عند شركةٍ أخرى معطَّل — يجب ألّا يحجب متجر هذه الشركة.
        cls.foreign_dead = Product.objects.create(
            tenant=cls.other, sku="SI-3", name_ar="معطَّل عند غيرنا", is_active=False)

    def _public_ids(self):
        res = APIClient().get(f"/api/store/{self.tenant.store_slug}/products/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        return {r["id"] for r in res.json()["results"]}

    def test_published_list_excludes_copies_of_inactive_products(self):
        from_live = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="نسخة الحيّ", imported_from_product_id=self.live.id)
        from_dead = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="نسخة المعطَّل", imported_from_product_id=self.dead.id)
        manual = StoreProduct.objects.create(tenant=self.tenant, name_ar="يدوي بلا أصل")
        ids = self._public_ids()
        self.assertIn(from_live.id, ids)
        self.assertIn(manual.id, ids)
        self.assertNotIn(from_dead.id, ids)

    def test_inactive_product_of_another_tenant_does_not_hide_ours(self):
        """المعرّف نفسه عند شركتين مستحيل (AutoField) لكن العزل يُثبَت بالاستعلام."""
        sp = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="نسخة", imported_from_product_id=self.foreign_dead.id)
        self.assertIn(sp.id, self._public_ids())

    def test_reactivating_makes_copy_visible_again(self):
        sp = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="نسخة المعطَّل", imported_from_product_id=self.dead.id)
        self.assertNotIn(sp.id, self._public_ids())
        Product.objects.filter(pk=self.dead.pk).update(is_active=True)
        try:
            self.assertIn(sp.id, self._public_ids())
        finally:
            Product.objects.filter(pk=self.dead.pk).update(is_active=False)

    def test_import_refuses_inactive_product_naming_it(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        client.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)
        res = client.post(
            "/api/store/admin/products/import-from-inventory/",
            {"product_ids": [self.live.id, self.dead.id]}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("معطَّل", str(res.json()))
        # الوحدة الطلبُ كلّه: لا يُستورَد الحيّ أيضاً.
        self.assertFalse(StoreProduct.objects.filter(tenant=self.tenant).exists())

    def test_import_still_accepts_active_products(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        client.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)
        res = client.post(
            "/api/store/admin/products/import-from-inventory/",
            {"product_ids": [self.live.id]}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["imported_count"], 1)
