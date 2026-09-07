"""«استيراد من الأصناف» — الجسر الوحيد المسموح بين المخزون والمتجر (مواصفة
#166 م٣): نسخٌ مرّةً واحدةً بلا علاقةٍ ولا مزامنة، عبر
`POST /api/store/admin/products/import-from-inventory/`.

قاعدة السعر مطابقةٌ حرفياً لـ`store/migrations/0006_...`: `online_price`
الموجب يغلب، وإلا `sale_price`.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.forms.models import model_to_dict
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product
from store.models import StoreBrand, StoreProduct
from store.views import StoreProductAdminViewSet
from tenants.services import create_company


class ImportFromInventoryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="importer", password="pw123456")
        cls.tenant = create_company("شركة الاستيراد", cls.user)
        cls.tenant.store_slug = "import-co"
        cls.tenant.save()

        cls.other_user = User.objects.create_user(username="importer2", password="pw123456")
        cls.other_tenant = create_company("شركة أخرى", cls.other_user)

        cls.p_online = Product.objects.create(
            tenant=cls.tenant, sku="IMP-1", name_ar="جهاز بالسعر الأونلاين",
            brand="Samsung", description="وصفٌ داخلي",
            online_price=Decimal("150.00"), sale_price=Decimal("99.00"),
        )
        cls.p_sale_only = Product.objects.create(
            tenant=cls.tenant, sku="IMP-2", name_ar="جهاز بلا سعر أونلاين",
            brand="samsung ", sale_price=Decimal("75.50"),
        )
        cls.p_foreign = Product.objects.create(
            tenant=cls.other_tenant, sku="IMP-3", name_ar="منتج شركة أخرى",
            online_price=Decimal("50.00"),
        )
        cls.p_preorder = Product.objects.create(
            tenant=cls.tenant, sku="IMP-4", name_ar="جهاز بالطلب المسبق",
            online_price=Decimal("10.00"), allow_preorder=True,
        )

    def setUp(self):
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    def _import(self, ids):
        return self.auth.post(
            "/api/store/admin/products/import-from-inventory/",
            {"product_ids": ids}, format="json",
        )

    # ── نسخٌ صحيح ────────────────────────────────────────────────────────

    def test_copies_name_brand_unit_price_and_description(self):
        res = self._import([self.p_online.id])
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertEqual(body["imported_count"], 1)
        self.assertEqual(body["skipped_count"], 0)

        created = StoreProduct.objects.get(imported_from_product_id=self.p_online.id)
        self.assertEqual(created.name_ar, "جهاز بالسعر الأونلاين")
        self.assertEqual(created.description, "وصفٌ داخلي")
        # online_price الموجب يغلب sale_price — قاعدة الهجرة 0006 حرفياً.
        self.assertEqual(created.price, Decimal("150.00"))
        self.assertEqual(created.brand.name, "Samsung")

    def test_price_falls_back_to_sale_price_when_no_online_price(self):
        self._import([self.p_sale_only.id])
        created = StoreProduct.objects.get(imported_from_product_id=self.p_sale_only.id)
        self.assertEqual(created.price, Decimal("75.50"))

    def test_brand_name_is_unified_case_insensitively(self):
        """`samsung ` و`Samsung` يجب أن يشتركا في نفس صفّ `StoreBrand`."""
        self._import([self.p_online.id, self.p_sale_only.id])
        self.assertEqual(StoreBrand.objects.filter(tenant=self.tenant).count(), 1)
        brand = StoreBrand.objects.get(tenant=self.tenant)
        created_a = StoreProduct.objects.get(imported_from_product_id=self.p_online.id)
        created_b = StoreProduct.objects.get(imported_from_product_id=self.p_sale_only.id)
        self.assertEqual(created_a.brand_id, brand.id)
        self.assertEqual(created_b.brand_id, brand.id)

    # ── تخطّي ما استُورد من قبل ──────────────────────────────────────────

    def test_skips_already_imported_and_reports_it(self):
        first = self._import([self.p_online.id])
        self.assertEqual(first.json()["imported_count"], 1)

        second = self._import([self.p_online.id])
        body = second.json()
        self.assertEqual(body["imported_count"], 0)
        self.assertEqual(body["skipped_count"], 1)
        self.assertEqual(
            StoreProduct.objects.filter(imported_from_product_id=self.p_online.id).count(), 1,
        )

    def test_mixed_batch_imports_new_and_skips_existing(self):
        self._import([self.p_online.id])
        res = self._import([self.p_online.id, self.p_sale_only.id])
        body = res.json()
        self.assertEqual(body["imported_count"], 1)
        self.assertEqual(body["skipped_count"], 1)
        self.assertIn("استُوردت", body["message"])
        self.assertIn("مستوردةً سلفاً", body["message"])

    # ── عزل الشركة ───────────────────────────────────────────────────────

    def test_isolated_by_company_a_foreign_product_id_imports_nothing(self):
        res = self._import([self.p_foreign.id])
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertEqual(body["imported_count"], 0)
        self.assertEqual(body["skipped_count"], 0)
        self.assertFalse(
            StoreProduct.objects.filter(imported_from_product_id=self.p_foreign.id).exists(),
        )

    # ── صفرُ صفٍّ متغيّرٍ في inventory.Product ───────────────────────────

    def test_zero_rows_changed_in_inventory_product(self):
        before = model_to_dict(Product.objects.get(pk=self.p_online.id))
        self._import([self.p_online.id])
        after = model_to_dict(Product.objects.get(pk=self.p_online.id))
        self.assertEqual(before, after)
        self.assertEqual(Product.objects.count(), 4)

    # ── stock_state مطابقٌ لاشتقاق الهجرة 0006 حرفياً ────────────────────

    def test_stock_state_derived_like_the_migration_preorder(self):
        self._import([self.p_preorder.id])
        created = StoreProduct.objects.get(imported_from_product_id=self.p_preorder.id)
        self.assertEqual(created.stock_state, StoreProduct.STOCK_PREORDER)

    def test_stock_state_derived_like_the_migration_in_stock(self):
        """`allow_preorder=False` ⇒ `in_stock` — نفس الاشتقاق حرفياً، لا الافتراض
        الضمنيّ للنموذج فقط (قد يتطابقان صدفةً هنا لكن القاعدة يجب أن تُكتب)."""
        self._import([self.p_online.id])
        created = StoreProduct.objects.get(imported_from_product_id=self.p_online.id)
        self.assertEqual(created.stock_state, StoreProduct.STOCK_IN_STOCK)

    # ── لا نسخَ للفئات عمداً (قرارٌ موثَّق — البند ٥) ────────────────────

    def test_categories_are_never_copied_on_import(self):
        self._import([self.p_online.id])
        created = StoreProduct.objects.get(imported_from_product_id=self.p_online.id)
        self.assertEqual(list(created.categories.all()), [])

    # ── سقفٌ صريحٌ على حجم الدفعة ─────────────────────────────────────────

    def test_batch_over_the_cap_is_a_400_with_a_clear_message(self):
        too_many = list(range(1, StoreProductAdminViewSet.IMPORT_MAX_IDS + 2))
        res = self._import(too_many)
        self.assertEqual(res.status_code, 400)
        text = str(res.content, "utf-8")
        self.assertIn(str(StoreProductAdminViewSet.IMPORT_MAX_IDS), text)
        self.assertIn(str(len(too_many)), text)
        self.assertEqual(StoreProduct.objects.count(), 0)

    def test_batch_exactly_at_the_cap_is_accepted(self):
        # لا نطلب استيراد ٥٠٠ صنفاً فعلياً — فقط أنّ الحدّ ذاته لا يُرفض.
        ids = [self.p_online.id] + list(range(90000, 90000 + StoreProductAdminViewSet.IMPORT_MAX_IDS - 1))
        res = self._import(ids)
        self.assertEqual(res.status_code, 200, res.content[:300])

    # ── الذرّيّة: الطلبُ كلُّه أو لا شيء ──────────────────────────────────

    def test_import_is_atomic_a_mid_batch_failure_leaves_nothing_committed(self):
        real_save = StoreProduct.save
        calls = {"n": 0}

        def flaky_save(self_product, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("عطلٌ مصطنع في منتصف الدفعة")
            return real_save(self_product, *args, **kwargs)

        ids = [self.p_online.id, self.p_sale_only.id, self.p_preorder.id]
        with patch.object(StoreProduct, "save", flaky_save):
            # المستودع يحمل معالج استثناءاتٍ مركزياً (`core.exception_handler`)
            # يحوّل الاستثناء غير المتوقَّع إلى 500 بدل تفجيره — فالإثبات هنا
            # على الحالة بعد الطلب لا على نوع الاستثناء نفسه.
            res = self._import(ids)
        self.assertEqual(res.status_code, 500)

        # الأول كان سينجح لولا الذرّيّة — الوحدةُ الطلبُ كلُّه فلا يبقى أثرٌ لأيٍّ منها.
        self.assertEqual(
            StoreProduct.objects.filter(imported_from_product_id__in=ids).count(), 0,
        )

    # ── التحقّق من المدخل ────────────────────────────────────────────────

    def test_empty_product_ids_is_a_400(self):
        res = self._import([])
        self.assertEqual(res.status_code, 400)

    def test_missing_product_ids_is_a_400(self):
        res = self.auth.post(
            "/api/store/admin/products/import-from-inventory/", {}, format="json",
        )
        self.assertEqual(res.status_code, 400)
