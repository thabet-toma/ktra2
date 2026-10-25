"""K1: الجرد من نطاق تصنيفات — البنود تولَّد في الخادم، والتعديل upsert، والتزامن المتفائل.

يثبت هذا الملف سلوك العقد الجديد (خطة `docs/plans/2026-10-21-inventory-count-category-tree.md`):
نطاقٌ صريح لا يوسّع الأحفاد، وعزل المستأجر، ورسائل رفضٍ متمايزة، وترقيم/ترحيل لا يمسّ
الأسطر غير المعدودة، و`If-Match` يمنع محو عمل العادّ.
"""
import importlib
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.migrations.state import ModelState, ProjectState
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.serializers import ValidationError as SerializerValidationError
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from inventory import services as inventory_services
from inventory.models import (
    Product, ProductCategory, Stocktake, StocktakeLine, StockMovement, Warehouse,
)
from inventory.serializers import StocktakeSerializer
from inventory.services import post_stocktake
from tenants.models import TenantBook, UserCompanyMembership
from tenants.services import create_company


class StocktakeScopeTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="sc-owner", password="x")
        cls.tenant = create_company("شركة نطاق الجرد", cls.owner)
        cls.manager = User.objects.create_user(
            username="sc-manager", password="x", first_name="مدير", last_name="الجرد")
        cls.counter = User.objects.create_user(username="sc-counter", password="x")
        UserCompanyMembership.objects.create(user=cls.manager, tenant=cls.tenant, role="manager")
        UserCompanyMembership.objects.create(user=cls.counter, tenant=cls.tenant, role="staff")

        cls.inv_acct = Account.objects.create(
            tenant=cls.tenant, code="7104", name="مخزون الجرد", account_type="Asset", is_active=True)
        cls.cogs_acct = Account.objects.create(
            tenant=cls.tenant, code="7101", name="ت.ب.م الجرد", account_type="Expense", is_active=True)
        cls.cat_a = ProductCategory.objects.create(
            tenant=cls.tenant, name="تصنيف أ",
            inventory_account=cls.inv_acct, cogs_account=cls.cogs_acct)
        cls.cat_b = ProductCategory.objects.create(
            tenant=cls.tenant, name="تصنيف ب",
            inventory_account=cls.inv_acct, cogs_account=cls.cogs_acct)
        cls.cat_child = ProductCategory.objects.create(
            tenant=cls.tenant, name="ابن أ", parent=cls.cat_a,
            inventory_account=cls.inv_acct, cogs_account=cls.cogs_acct)
        cls.cat_empty = ProductCategory.objects.create(
            tenant=cls.tenant, name="فارغ",
            inventory_account=cls.inv_acct, cogs_account=cls.cogs_acct)
        # مستودعُ الشركة — تاجٌ على حركات الجرد، ووسيلةُ إظهار غياب
        # `select_related('warehouse')` في اختبارَي عدّ الاستعلامات.
        cls.warehouse = Warehouse.objects.create(
            tenant=cls.tenant, name="مستودع النطاق", code="SC-W")

        def product(sku, name, category=None, **extra):
            return Product.objects.create(
                tenant=cls.tenant, sku=sku, name_ar=name, category=category,
                quantity_on_hand=extra.pop("quantity_on_hand", Decimal("10")),
                avg_cost=extra.pop("avg_cost", Decimal("10")), **extra)

        cls.p_a1 = product("SC-A1", "منتج أ", cls.cat_a)
        cls.p_child = product("SC-CH", "منتج الابن", cls.cat_child)
        cls.p_b = product("SC-B", "منتج ب", cls.cat_b, quantity_on_hand=Decimal("5"))
        cls.p_none = product("SC-N", "بلا تصنيف")
        cls.p_inactive = product("SC-I", "معطَّل", cls.cat_a, is_active=False)
        cls.p_service = product("SC-S", "خدمة", cls.cat_a, is_service=True)

        cls.foreign_owner = User.objects.create_user(username="sc-foreign", password="x")
        cls.foreign_tenant = create_company("شركة جرد أجنبية", cls.foreign_owner)
        cls.foreign_cat = ProductCategory.objects.create(
            tenant=cls.foreign_tenant, name="تصنيف أجنبي")
        cls.foreign_product = Product.objects.create(
            tenant=cls.foreign_tenant, sku="SC-F", name_ar="منتج أجنبي",
            category=cls.foreign_cat, quantity_on_hand=Decimal("9"))

    # ── أدوات ──
    def _as(self, user):
        self.client.force_authenticate(user=user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _create_scope(self, scope, **over):
        body = {"stocktake_date": "2026-07-01", "scope": scope}
        body.update(over)
        return self.client.post("/api/inventory/stocktakes/", body, format="json")

    def _create_manual(self, user, rows, **over):
        self._as(user)
        body = {"stocktake_date": "2026-07-01", "lines": rows}
        body.update(over)
        return self.client.post("/api/inventory/stocktakes/", body, format="json")

    def _line_ids(self, res):
        return {ln["product"] for ln in res.data["lines"]}

    def _rows(self, res):
        return res.data["results"] if isinstance(res.data, dict) else res.data

    def _manual_stocktake(self, rows, user=None, warehouse=None):
        st = Stocktake.objects.create(
            tenant=self.tenant, stocktake_date="2026-07-01", created_by=user,
            warehouse=warehouse)
        for product, quantity in rows:
            StocktakeLine.objects.create(
                stocktake=st, product=product, counted_quantity=quantity)
        return st

    # ── توليد البنود من النطاق ──
    def test_two_categories_match_direct_products_only(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_a.id, self.cat_b.id]})
        self.assertEqual(res.status_code, 201, res.content)
        # ابن «أ» ليس ضمن المختار: الدلالة صريحة لا أحفاد ضمنياً (قرار ٣).
        self.assertEqual(self._line_ids(res), {self.p_a1.id, self.p_b.id})
        st = Stocktake.objects.get(pk=res.data["id"])
        self.assertEqual(st.created_by_id, self.manager.id)
        detail = self.client.get(f"/api/inventory/stocktakes/{st.id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        # البطاقة تعرض اسم مَن أنشأ الجرد كالقائمة — لا حقلاً غائباً ولا اسمَ دخول.
        self.assertEqual(detail.data["created_by_name"], "مدير الجرد")
        self.assertEqual(
            st.scope,
            {"all": False, "categories": sorted([self.cat_a.id, self.cat_b.id]),
             "uncategorized": False, "include_inactive": False})
        self.assertTrue(all(ln.counted_quantity is None for ln in st.lines.all()))

    def test_uncategorized_adds_products_without_category(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_a.id], "uncategorized": True})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._line_ids(res), {self.p_a1.id, self.p_none.id})

    def test_all_takes_every_active_non_service_product(self):
        self._as(self.manager)
        res = self._create_scope({"all": True})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(
            self._line_ids(res),
            {self.p_a1.id, self.p_child.id, self.p_b.id, self.p_none.id})

    def test_include_inactive_includes_it_but_never_services(self):
        self._as(self.manager)
        res = self._create_scope({"all": True, "include_inactive": True})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIn(self.p_inactive.id, self._line_ids(res))
        self.assertNotIn(self.p_service.id, self._line_ids(res))

    def test_duplicate_category_ids_are_deduplicated(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_a.id, self.cat_a.id]})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["scope"]["categories"], [self.cat_a.id])
        self.assertEqual(self._line_ids(res), {self.p_a1.id})

    # ── منتجاتٌ صريحة اتحاداً مع التصنيفات (ST-1) ──
    def test_products_only_scope_generates_exactly_those_products(self):
        self._as(self.manager)
        res = self._create_scope({"products": [self.p_a1.id, self.p_none.id]})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._line_ids(res), {self.p_a1.id, self.p_none.id})
        self.assertEqual(
            Stocktake.objects.get(pk=res.data["id"]).scope["products"],
            sorted([self.p_a1.id, self.p_none.id]))

    def test_products_union_with_categories_and_uncategorized(self):
        self._as(self.manager)
        res = self._create_scope({
            "products": [self.p_child.id], "categories": [self.cat_a.id],
            "uncategorized": True,
        })
        self.assertEqual(res.status_code, 201, res.content)
        # منتج الابن لا يدخل بتصنيف أبيه (قرار ٣)، ويدخل هنا لأنّه مذكورٌ صريحاً.
        self.assertEqual(
            self._line_ids(res), {self.p_a1.id, self.p_child.id, self.p_none.id})
        self.assertEqual(
            Stocktake.objects.get(pk=res.data["id"]).scope["products"], [self.p_child.id])

    def test_product_inside_checked_category_is_dropped_as_redundant(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_a.id], "products": [self.p_a1.id]})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._line_ids(res), {self.p_a1.id})
        # مُسقَطٌ لا مرفوض: المفتاح لا يُخزَّن فارغاً في النطاق المعياري.
        self.assertNotIn("products", Stocktake.objects.get(pk=res.data["id"]).scope)
        self.assertNotIn("products", res.data["scope"])

    def test_all_drops_products(self):
        self._as(self.manager)
        res = self._create_scope({"all": True, "products": [self.p_a1.id, self.p_child.id]})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertNotIn("products", Stocktake.objects.get(pk=res.data["id"]).scope)
        self.assertEqual(
            self._line_ids(res),
            {self.p_a1.id, self.p_child.id, self.p_b.id, self.p_none.id})

    def test_products_dropped_deduplicated_and_rejected(self):
        """ثلاثة مصائر للمنتج الصريح — وكلٌّ منها يُختبَر على حِدة فيسقط وحده.

        الإسقاط **يسبق** الرفض: منتجُ تصنيفٍ مؤشَّرٍ غيرُ مؤهّل يُرفض ولا يُسقَط
        بصمت (وإلا مرّت حمولةٌ بمنتجٍ لا يدخل الجرد أبداً)، والمغطّى بمؤهّلٍ يُسقَط
        ولا يُخزَّن، والتكرار يُطوى إلى معرّفٍ واحد.
        """
        self._as(self.manager)

        # (١) «بدون تصنيف» يغطّي منتجاً بلا تصنيف ⇒ يُسقَط فلا يُخزَّن المفتاح.
        res = self._create_scope(
            {"uncategorized": True, "products": [self.p_none.id, self.p_none.id]})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._line_ids(res), {self.p_none.id})
        self.assertNotIn("products", Stocktake.objects.get(pk=res.data["id"]).scope)

        # (٢) التكرار يُطوى: المُخزَّن معرّفٌ واحد لا اثنان.
        res = self._create_scope({"products": [self.p_child.id, self.p_child.id]})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._line_ids(res), {self.p_child.id})
        self.assertEqual(
            Stocktake.objects.get(pk=res.data["id"]).scope["products"], [self.p_child.id])

        # (٣) غير المؤهّل يُرفض ولو غطّاه تصنيفٌ مؤشَّر — ولا يُنشأ شيء.
        before = Stocktake.objects.count()
        res = self._create_scope(
            {"categories": [self.cat_a.id], "products": [self.p_inactive.id]})
        self.assertEqual(res.status_code, 400, res.content)
        message = f"منتجات لا تدخل هذا الجرد (خدمة أو غير فعّال): {self.p_inactive.id}"
        self.assertIn(message, res.data["scope"])
        self.assertEqual(Stocktake.objects.count(), before)

    def test_category_only_scope_keeps_four_keys(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_a.id]})
        self.assertEqual(res.status_code, 201, res.content)
        # النطاق الخالي من منتجاتٍ صريحة يبقى على مفاتيحه الأربعة حرفاً.
        self.assertEqual(
            Stocktake.objects.get(pk=res.data["id"]).scope,
            {"all": False, "categories": [self.cat_a.id],
             "uncategorized": False, "include_inactive": False})

    def test_products_validation_messages(self):
        self._as(self.manager)
        cases = [
            ({"products": "x"}, "قائمة المنتجات في نطاق الجرد غير صالحة"),
            ({"products": ["x"]}, "معرّفات المنتجات يجب أن تكون أعداداً صحيحة"),
            ({"products": [1.5]}, "معرّفات المنتجات يجب أن تكون أعداداً صحيحة"),
            ({"products": [True]}, "معرّفات المنتجات يجب أن تكون أعداداً صحيحة"),
            ({"products": list(range(1, 5002))},
             "الحد الأقصى 5000 منتج في الجرد الواحد"),
        ]
        for scope, message in cases:
            with self.subTest(scope=str(scope)[:40]):
                res = self._create_scope(scope)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("scope", res.data)
                self.assertIsInstance(res.data["scope"], list)
                self.assertIn(message, res.data["scope"])
                self.assertIn(message, str(res.data))
                self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    # ── العزل والتحقق ──
    def test_foreign_category_is_rejected_and_nothing_is_created(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_a.id, self.foreign_cat.id]})
        self.assertEqual(res.status_code, 400, res.content)
        message = f"تصنيفات غير موجودة لهذه الشركة: {self.foreign_cat.id}"
        # الشكل نفسه جزءٌ من العقد: خطأُ حقل `scope` لا قائمةً عائمةً ولا `detail`.
        self.assertIn("scope", res.data)
        self.assertIsInstance(res.data["scope"], list)
        self.assertIn(message, res.data["scope"])
        self.assertIn(message, str(res.data))
        self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    def test_foreign_product_is_rejected_and_nothing_is_created(self):
        self._as(self.manager)
        before = Stocktake.objects.count()
        res = self._create_scope({"products": [self.p_a1.id, self.foreign_product.id]})
        self.assertEqual(res.status_code, 400, res.content)
        message = f"منتجات غير موجودة لهذه الشركة: {self.foreign_product.id}"
        self.assertIn("scope", res.data)
        self.assertIsInstance(res.data["scope"], list)
        self.assertIn(message, res.data["scope"])
        self.assertEqual(Stocktake.objects.count(), before)
        self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    def test_service_or_inactive_product_rejected_unless_flag(self):
        self._as(self.manager)
        cases = [
            ({"products": [self.p_inactive.id]}, self.p_inactive.id),
            ({"products": [self.p_service.id]}, self.p_service.id),
            ({"products": [self.p_service.id], "include_inactive": True},
             self.p_service.id),
        ]
        for scope, rejected in cases:
            with self.subTest(scope=scope):
                res = self._create_scope(scope)
                self.assertEqual(res.status_code, 400, res.content)
                message = f"منتجات لا تدخل هذا الجرد (خدمة أو غير فعّال): {rejected}"
                self.assertIn(message, res.data["scope"])
                self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

        # غير الفعّال يدخل بالعلم الصريح — والخدمة لا تدخل أبداً.
        res = self._create_scope(
            {"products": [self.p_inactive.id], "include_inactive": True})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._line_ids(res), {self.p_inactive.id})

    def test_scope_validation_messages(self):
        self._as(self.manager)
        cases = [
            (["not", "a", "dict"], "نطاق الجرد غير صالح"),
            ({"bogus": True}, "مفتاح غير معروف في نطاق الجرد: bogus"),
            ({"all": 1}, "قيمة «all» في نطاق الجرد يجب أن تكون صحيحاً أو خطأً"),
            ({"include_inactive": "true"},
             "قيمة «include_inactive» في نطاق الجرد يجب أن تكون صحيحاً أو خطأً"),
            ({"categories": "x"}, "قائمة التصنيفات في نطاق الجرد غير صالحة"),
            ({"categories": ["x"]}, "معرّفات التصنيفات يجب أن تكون أعداداً صحيحة"),
            ({"categories": [1.5]}, "معرّفات التصنيفات يجب أن تكون أعداداً صحيحة"),
            ({"categories": [True]}, "معرّفات التصنيفات يجب أن تكون أعداداً صحيحة"),
            ({"categories": list(range(1, 2003))},
             "الحد الأقصى 2000 تصنيف في الجرد الواحد"),
            ({}, "اختر تصنيفاً واحداً على الأقل"),
        ]
        for scope, message in cases:
            with self.subTest(scope=str(scope)[:40]):
                res = self._create_scope(scope)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("scope", res.data)
                self.assertIsInstance(res.data["scope"], list)
                self.assertIn(message, res.data["scope"])
                self.assertIn(message, str(res.data))
                self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    def test_scope_and_lines_together_rejected(self):
        self._as(self.manager)
        res = self._create_scope(
            {"all": True}, lines=[{"product": self.p_a1.id, "counted_quantity": "4"}])
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("اختر نطاقاً أو بنوداً لا الاثنين", str(res.data))
        self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    def test_zero_matched_products_rejected(self):
        self._as(self.manager)
        res = self._create_scope({"categories": [self.cat_empty.id]})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("لا منتجات في هذا الاختيار", str(res.data))
        self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    # ── الإنشاء اليدوي كما كان ──
    def test_manual_create_still_works_and_stamps_counted_lines(self):
        res = self._create_manual(self.counter, [{
            "product": self.p_a1.id, "counted_quantity": "12",
        }])
        self.assertEqual(res.status_code, 201, res.content)
        ln = StocktakeLine.objects.get(stocktake_id=res.data["id"])
        self.assertEqual(ln.counted_quantity, Decimal("12.0000"))
        self.assertEqual(ln.counted_by_name, "sc-counter")
        self.assertIsNotNone(ln.counted_at)
        self.assertIsNone(Stocktake.objects.get(pk=res.data["id"]).scope)

    def test_manual_line_can_stay_uncounted(self):
        res = self._create_manual(self.counter, [{
            "product": self.p_a1.id, "counted_quantity": None,
        }])
        self.assertEqual(res.status_code, 201, res.content)
        ln = StocktakeLine.objects.get(stocktake_id=res.data["id"])
        self.assertIsNone(ln.counted_quantity)
        self.assertEqual(ln.counted_by_name, "")
        self.assertIsNone(ln.counted_at)

    # ── التعديل: upsert لا استبدال ──
    def test_update_upserts_and_stamps_only_changed_line(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
            {"product": self.p_b.id, "counted_quantity": "5"},
        ])
        st_id = created.data["id"]
        before = {ln.product_id: ln for ln in StocktakeLine.objects.filter(stocktake_id=st_id)}

        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"lines": [{"product": self.p_a1.id, "counted_quantity": "14"},
                       {"product": self.p_b.id, "counted_quantity": "5"}]},
            format="json")
        self.assertEqual(res.status_code, 200, res.content)
        after = {ln.product_id: ln for ln in StocktakeLine.objects.filter(stocktake_id=st_id)}
        self.assertEqual(after[self.p_a1.id].counted_quantity, Decimal("14.0000"))
        self.assertEqual(after[self.p_a1.id].counted_by_name, "مدير الجرد")
        # بندٌ لم تتغيّر كميته يحتفظ بخاتم من عدّه أوّلاً.
        self.assertEqual(after[self.p_b.id].counted_by_name, "sc-counter")
        self.assertEqual(after[self.p_b.id].counted_at, before[self.p_b.id].counted_at)
        # والردّ نفسه حديث لا من جلبٍ مسبقٍ قبل التعديل.
        response_lines = {ln["product"]: ln for ln in res.data["lines"]}
        self.assertEqual(response_lines[self.p_a1.id]["counted_by_name"], "مدير الجرد")
        self.assertEqual(
            Decimal(response_lines[self.p_a1.id]["counted_quantity"]), Decimal("14.0000"))

    def test_update_keeps_unsent_line_unless_replace_lines(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
            {"product": self.p_b.id, "counted_quantity": "5"},
        ])
        st_id = created.data["id"]
        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"lines": [{"product": self.p_a1.id, "counted_quantity": "13"}]},
            format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(StocktakeLine.objects.filter(stocktake_id=st_id, product=self.p_b).exists())

        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"replace_lines": True,
             "lines": [{"product": self.p_a1.id, "counted_quantity": "13"}]},
            format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(StocktakeLine.objects.filter(stocktake_id=st_id, product=self.p_b).exists())
        self.assertTrue(StocktakeLine.objects.filter(stocktake_id=st_id, product=self.p_a1).exists())
        self.assertEqual({ln["product"] for ln in res.data["lines"]}, {self.p_a1.id})
        self.assertEqual(res.data["line_count"], 1)

    def test_update_null_clears_the_stamps(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
        ])
        st_id = created.data["id"]
        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"lines": [{"product": self.p_a1.id, "counted_quantity": None}]},
            format="json")
        self.assertEqual(res.status_code, 200, res.content)
        ln = StocktakeLine.objects.get(stocktake_id=st_id, product=self.p_a1)
        self.assertIsNone(ln.counted_quantity)
        self.assertEqual(ln.counted_by_name, "")
        self.assertIsNone(ln.counted_at)

    def test_update_rejects_a_different_scope(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
        ])
        st_id = created.data["id"]
        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/", {"scope": {"all": True}}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("النطاق يُحدَّد عند إنشاء الجرد فقط", str(res.data))
        self.assertEqual(
            StocktakeLine.objects.get(stocktake_id=st_id, product=self.p_a1).counted_quantity,
            Decimal("12.0000"))

    def test_update_accepts_the_scope_it_read_back(self):
        """عميلٌ يعيد ما قرأه (حمولة البطاقة كما هي) لا يُردّ 400: نطاقٌ مطابقٌ
        للمخزَّن يُقبل ويُهمَل — والاختلاف وحده مرفوض."""
        self._as(self.manager)
        created = self._create_scope({"categories": [self.cat_a.id]})
        st_id = created.data["id"]
        detail = self.client.get(f"/api/inventory/stocktakes/{st_id}/")
        res = self.client.put(f"/api/inventory/stocktakes/{st_id}/", {
            "stocktake_date": detail.data["stocktake_date"],
            "notes": "تعديل بعد قراءة البطاقة",
            "scope": detail.data["scope"],
            "lines": [{"product": ln["product"], "counted_quantity": "7"}
                      for ln in detail.data["lines"]],
        }, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["scope"], detail.data["scope"])
        self.assertEqual(Stocktake.objects.get(pk=st_id).notes, "تعديل بعد قراءة البطاقة")
        self.assertEqual(
            StocktakeLine.objects.get(stocktake_id=st_id, product=self.p_a1).counted_quantity,
            Decimal("7.0000"))

    def test_update_accepts_a_null_scope_echo(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
        ])
        st_id = created.data["id"]
        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/", {"scope": None}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNone(Stocktake.objects.get(pk=st_id).scope)

    # ── الصدى المكافئ يُقبل والمختلف يبقى مرفوضاً (المقارنة بعد التطبيع المعياري) ──
    def test_update_accepts_an_echo_with_unsorted_categories(self):
        """ترتيبُ التصنيفات لا معنى له: صدىً مرتّباً بشكلٍ آخر ليس تعديلاً."""
        self._as(self.manager)
        created = self._create_scope({"categories": [self.cat_a.id, self.cat_b.id]})
        st_id = created.data["id"]
        res = self.client.patch(f"/api/inventory/stocktakes/{st_id}/", {
            "scope": {"all": False, "uncategorized": False, "include_inactive": False,
                      "categories": [self.cat_b.id, self.cat_a.id]},
        }, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        # والمخزَّن لم يتغيّر: الصدى يُهمَل ولا يُكتب.
        self.assertEqual(
            Stocktake.objects.get(pk=st_id).scope["categories"],
            sorted([self.cat_a.id, self.cat_b.id]))

    def test_update_accepts_an_echo_missing_default_keys(self):
        """مفتاحُ افتراضٍ غائبٌ (`false`/`[]`) هو نفسه — لا فارق في الشكل."""
        self._as(self.manager)
        created = self._create_scope({"categories": [self.cat_a.id]})
        st_id = created.data["id"]
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"scope": {"categories": [self.cat_a.id]}}, format="json")
        self.assertEqual(res.status_code, 200, res.content)

    def test_update_accepts_an_echo_with_empty_products_key(self):
        """المفتاح الجديد (`products`) يأتي `[]` في صدى العملاء القدامى — صدىً لا اختلافاً."""
        self._as(self.manager)
        created = self._create_scope({"categories": [self.cat_a.id]})
        st_id = created.data["id"]
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"scope": {"categories": [self.cat_a.id], "products": []}}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn("products", Stocktake.objects.get(pk=st_id).scope)

    def test_update_rejects_different_categories_after_canonicalization(self):
        """الترتيب لا يفرّق والمحتوى يفرّق: تصنيفٌ آخر يبقى 400 بعد التطبيع."""
        self._as(self.manager)
        created = self._create_scope({"categories": [self.cat_a.id]})
        st_id = created.data["id"]
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"scope": {"categories": [self.cat_b.id]}}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("النطاق يُحدَّد عند إنشاء الجرد فقط", str(res.data))

    def test_update_line_without_quantity_is_rejected_and_keeps_the_stamps(self):
        """بندٌ بلا مفتاح `counted_quantity` ليس «امسح العدّ»: الحقل إلزاميٌّ في
        الكتابة (`null` وحدها تمسح)، وإلا محا تعديلٌ جزئيّ عدَّ موظف الرابط بصمت."""
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
        ])
        st_id = created.data["id"]
        before = StocktakeLine.objects.get(stocktake_id=st_id, product=self.p_a1)
        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"lines": [{"product": self.p_a1.id}]},
            format="json")
        self.assertEqual(res.status_code, 400, res.content)
        after = StocktakeLine.objects.get(stocktake_id=st_id, product=self.p_a1)
        self.assertEqual(after.counted_quantity, Decimal("12.0000"))
        self.assertEqual(after.counted_by_name, before.counted_by_name)
        self.assertEqual(after.counted_at, before.counted_at)

    def test_negative_quantity_is_rejected(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
        ])
        st_id = created.data["id"]
        self._as(self.manager)
        res = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/",
            {"lines": [{"product": self.p_a1.id, "counted_quantity": "-1"}]},
            format="json")
        self.assertEqual(res.status_code, 400, res.content)
        ln = StocktakeLine.objects.get(stocktake_id=st_id, product=self.p_a1)
        self.assertEqual(ln.counted_quantity, Decimal("12.0000"))

    # ── الذرّية والقفل ──
    def test_manual_create_is_one_transaction(self):
        """عطلٌ في منتصف كتابة البنود لا يترك رأساً بلا بنوده — وإلا بقي جردٌ
        ناقصٌ يبدو كأنّه أُنشئ بنجاح. الرأس والبنود معاملةٌ واحدة."""
        def half_lines(stocktake, rows, user):
            StocktakeLine.objects.create(stocktake=stocktake, product=self.p_a1)
            raise RuntimeError("عطل محاكى في منتصف كتابة البنود")

        self._as(self.counter)
        with mock.patch(
            "inventory.serializers.StocktakeSerializer._create_lines",
            staticmethod(half_lines),
        ):
            res = self.client.post(
                "/api/inventory/stocktakes/",
                {"stocktake_date": "2026-07-01",
                 "lines": [{"product": self.p_a1.id, "counted_quantity": "12"}]},
                format="json")
        # العطل يصل 500 (معالج الاستثناءات الموحّد) — والمهمّ: لا يبقى رأسٌ يتيم.
        self.assertEqual(res.status_code, 500, res.content)
        self.assertFalse(Stocktake.objects.filter(tenant=self.tenant).exists())

    def test_update_rechecks_is_posted_on_the_locked_row(self):
        """نسخةٌ قديمة (`is_posted=False`) لا تمرّ: الصفّ المقفول هو من يُسأل، وإلا
        كتب تعديلٌ على جردٍ رُحّل بين قراءته وكتابته."""
        st = self._manual_stocktake([(self.p_a1, Decimal("12"))], user=self.manager)
        stale = Stocktake.objects.get(pk=st.pk)   # نسخةٌ قرئت قبل الترحيل
        post_stocktake(st)
        serializer = StocktakeSerializer(
            stale, data={"notes": "محاولة على جردٍ مُرحَّل"}, partial=True)
        serializer.is_valid(raise_exception=True)
        with self.assertRaisesMessage(
                SerializerValidationError, "لا يمكن تعديل جرد مُرحَّل."):
            serializer.save()
        self.assertEqual(Stocktake.objects.get(pk=st.pk).notes, "")

    # ── التزامن المتفائل ──
    def test_etag_round_trip_and_stale_if_match(self):
        created = self._create_manual(self.counter, [
            {"product": self.p_a1.id, "counted_quantity": "12"},
        ])
        st_id = created.data["id"]
        self._as(self.manager)
        detail = self.client.get(f"/api/inventory/stocktakes/{st_id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertIn("ETag", detail)

        stale = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/", {"notes": "محاولة قديمة"}, format="json",
            HTTP_IF_MATCH='"0"')
        self.assertEqual(stale.status_code, 412, stale.content)
        self.assertEqual(stale.data["code"], "stale_document")
        self.assertEqual(Stocktake.objects.get(pk=st_id).notes, "")

        fresh = self.client.patch(
            f"/api/inventory/stocktakes/{st_id}/", {"notes": "تعديل صحيح"}, format="json",
            HTTP_IF_MATCH=detail["ETag"])
        self.assertEqual(fresh.status_code, 200, fresh.content)
        self.assertEqual(Stocktake.objects.get(pk=st_id).notes, "تعديل صحيح")

    # ── القائمة المختصرة والأداء ──
    def test_list_returns_summary_without_lines(self):
        self._manual_stocktake(
            [(self.p_a1, Decimal("12")), (self.p_b, None)], user=self.manager)
        self._manual_stocktake(
            [(self.p_a1, Decimal("1")), (self.p_b, Decimal("2")), (self.p_none, Decimal("3"))],
            user=self.manager)
        self._as(self.manager)
        res = self.client.get("/api/inventory/stocktakes/")
        self.assertEqual(res.status_code, 200, res.content)
        rows = self._rows(res)
        self.assertEqual(len(rows), 2)
        first = next(r for r in rows if r["line_count"] == 2)
        self.assertNotIn("lines", first)
        self.assertEqual(first["counted_count"], 1)
        self.assertEqual(first["created_by_name"], "مدير الجرد")
        second = next(r for r in rows if r["line_count"] == 3)
        self.assertEqual(second["counted_count"], 3)

    def test_list_query_count_is_constant(self):
        self._manual_stocktake(
            [(self.p_a1, Decimal("1"))], user=self.manager, warehouse=self.warehouse)
        self._as(self.manager)
        self.client.get("/api/inventory/stocktakes/")  # تسخين المصادقة/الشركة
        with CaptureQueriesContext(connection) as small:
            self.client.get("/api/inventory/stocktakes/")
        for _ in range(4):
            self._manual_stocktake(
                [(self.p_a1, Decimal("1"))], user=self.manager, warehouse=self.warehouse)
        with CaptureQueriesContext(connection) as large:
            self.client.get("/api/inventory/stocktakes/")
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))

    def test_detail_query_count_is_constant_across_line_counts(self):
        def make_stocktake(count, warehouse=None, tag=""):
            st = Stocktake.objects.create(
                tenant=self.tenant, stocktake_date="2026-07-01", created_by=self.manager,
                warehouse=warehouse)
            for index in range(count):
                product = Product.objects.create(
                    tenant=self.tenant, sku=f"SC-P{count}{tag}-{index}", name_ar=f"منتج {index}",
                    category=self.cat_a, quantity_on_hand=Decimal("1"), avg_cost=Decimal("1"))
                StocktakeLine.objects.create(
                    stocktake=st, product=product, counted_quantity=Decimal("1"),
                    counted_by_name="مدير الجرد", counted_at=timezone.now())
            return st

        small_st = make_stocktake(3, warehouse=self.warehouse)
        large_st = make_stocktake(12, warehouse=self.warehouse)
        # جردٌ بلا مستودع — الفرق الوحيد عن `small_st`: غيابُ `select_related('warehouse')`
        # كان يُظهر استعلاماً إضافياً للمستودع في ذي المستودع وحده فيختلف العدّان.
        bare_st = make_stocktake(3, tag="B")
        self._as(self.manager)
        self.client.get(f"/api/inventory/stocktakes/{small_st.id}/")
        with CaptureQueriesContext(connection) as small:
            self.client.get(f"/api/inventory/stocktakes/{small_st.id}/")
        with CaptureQueriesContext(connection) as large:
            self.client.get(f"/api/inventory/stocktakes/{large_st.id}/")
        with CaptureQueriesContext(connection) as bare:
            self.client.get(f"/api/inventory/stocktakes/{bare_st.id}/")
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))
        self.assertEqual(len(small.captured_queries), len(bare.captured_queries))

    # ── الترحيل: الاستثناء أو الصفر ──
    def test_post_excludes_uncounted_lines_without_movement(self):
        st = self._manual_stocktake(
            [(self.p_a1, Decimal("12")), (self.p_b, None)], user=self.manager)
        post_stocktake(st, user=self.manager)
        st.refresh_from_db()
        self.assertTrue(st.is_posted)
        self.p_a1.refresh_from_db()
        self.p_b.refresh_from_db()
        self.assertEqual(self.p_a1.quantity_on_hand, Decimal("12.0000"))
        self.assertEqual(self.p_b.quantity_on_hand, Decimal("5.0000"))
        moves = StockMovement.objects.filter(reference_type="STOCKTAKE", reference_id=st.id)
        self.assertEqual(moves.count(), 1)
        self.assertEqual(moves.first().product_id, self.p_a1.id)
        skipped = StocktakeLine.objects.get(stocktake=st, product=self.p_b)
        self.assertIsNone(skipped.counted_quantity)
        self.assertEqual(skipped.variance, Decimal("0.0000"))
        self.assertEqual(skipped.system_quantity, Decimal("5.0000"))
        self.assertTrue(JournalHeader.objects.filter(
            reference_type="STOCKTAKE", reference_id=st.id).exists())

    def test_posting_locks_only_products_that_will_move(self):
        """قفل الترحيل على منتجات الأسطر التي ستُرحَّل وحدها، ولقطة المستثناة كتابةٌ
        واحدة مجمّعة بدل UPDATE لكل سطر.

        SQLite يُهمل `FOR UPDATE` من الـSQL، فيُقاس **مجموعة المعرّفات** التي تمرّ
        من نقطة القفل الواحدة (`services._lock_stocktake_products`) بمراقبتها،
        ويُقاس الثاني على الـSQL نفسه: كتابة لقطةٍ مجمّعة واحدة (`CASE WHEN`) لا
        سطراً لكل بندٍ مستثنى.
        """
        st = self._manual_stocktake(
            [(self.p_a1, Decimal("12")), (self.p_b, None), (self.p_none, None)],
            user=self.manager)
        locked = []
        real_lock = inventory_services._lock_stocktake_products

        def spy(tenant_id, product_ids):
            locked.append(set(product_ids))
            return real_lock(tenant_id, product_ids)

        with mock.patch("inventory.services._lock_stocktake_products", side_effect=spy):
            with CaptureQueriesContext(connection) as ctx:
                post_stocktake(st, user=self.manager)

        self.assertEqual(locked, [{self.p_a1.id}])
        bulk_writes = [
            query["sql"] for query in ctx.captured_queries
            if query["sql"].startswith("UPDATE") and "CASE WHEN" in query["sql"]
            and "SystemQuantity" in query["sql"]
        ]
        self.assertEqual(len(bulk_writes), 1, bulk_writes)
        # واللقطةُ للتدقيق ما زالت تُكتب للمستثنَيتين — بلا حركةٍ ولا تصفير.
        self.p_b.refresh_from_db()
        self.p_none.refresh_from_db()
        self.assertEqual(self.p_b.quantity_on_hand, Decimal("5.0000"))
        self.assertEqual(self.p_none.quantity_on_hand, Decimal("10.0000"))
        self.assertEqual(
            StocktakeLine.objects.get(stocktake=st, product=self.p_b).system_quantity,
            Decimal("5.0000"))

    def test_post_uncounted_as_zero_posts_them_as_zero(self):
        st = self._manual_stocktake([(self.p_b, None)], user=self.manager)
        self._as(self.manager)
        res = self.client.post(
            f"/api/inventory/stocktakes/{st.id}/post/",
            {"uncounted_as_zero": True}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.p_b.refresh_from_db()
        self.assertEqual(self.p_b.quantity_on_hand, Decimal("0.0000"))
        ln = StocktakeLine.objects.get(stocktake=st)
        self.assertEqual(ln.counted_quantity, Decimal("0.0000"))
        self.assertEqual(ln.counted_by_name, "مدير الجرد")
        self.assertIsNotNone(ln.counted_at)
        self.assertEqual(
            StockMovement.objects.get(reference_type="STOCKTAKE", reference_id=st.id).movement_type,
            "ADJUST_OUT")
        # الردّ يحمل القيمة التي كتبها الترحيل لا `null` القديمة من الجلب المسبق.
        self.assertEqual(Decimal(res.data["lines"][0]["counted_quantity"]), Decimal("0.0000"))
        self.assertEqual(res.data["lines"][0]["counted_by_name"], "مدير الجرد")

    def test_post_all_null_without_flag_is_rejected_before_any_write(self):
        def stocktake_book():
            return TenantBook.objects.filter(
                tenant=self.tenant, document_type="stocktake",
            ).values_list("last_used_number", flat=True).first()

        st = self._manual_stocktake([(self.p_a1, None), (self.p_b, None)], user=self.manager)
        book_before = stocktake_book()
        with self.assertRaisesMessage(ValidationError, "لم يُعدّ أيّ بند"):
            post_stocktake(st, user=self.manager)
        st.refresh_from_db()
        self.assertFalse(st.is_posted)
        # لا ترقيم ولا دفتر قبل الكتابة: الرقم يبقى فارغاً والدفتر كما كان.
        self.assertEqual(st.stocktake_number, "")
        self.assertEqual(stocktake_book(), book_before)
        self.assertFalse(StockMovement.objects.filter(reference_type="STOCKTAKE").exists())
        self.assertFalse(JournalHeader.objects.filter(reference_type="STOCKTAKE").exists())
        self.assertEqual(
            StocktakeLine.objects.filter(stocktake=st, counted_quantity__isnull=False).count(), 0)

    def test_post_flag_must_be_a_json_bool(self):
        # بندٌ معدودٌ مع غير معدود: تجاهلُ العلم يمرّ (200) فلا يُنتج 400 من غيره.
        st = self._manual_stocktake(
            [(self.p_a1, Decimal("12")), (self.p_b, None)], user=self.manager)
        self._as(self.manager)
        res = self.client.post(
            f"/api/inventory/stocktakes/{st.id}/post/",
            {"uncounted_as_zero": "yes"}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(
            res.data["error"], "قيمة uncounted_as_zero يجب أن تكون true أو false")
        self.assertFalse(Stocktake.objects.get(pk=st.id).is_posted)

    def test_post_accepts_an_empty_json_body(self):
        """`postStocktake()` في الواجهة يرسل POST بترويسة JSON وبلا جسم: الجسم
        الفارغ يُفسَّر خريطةً فارغة، فلا يُردّ 400 على الواجهة القائمة."""
        st = self._manual_stocktake([(self.p_a1, Decimal("12"))], user=self.manager)
        self._as(self.manager)
        res = self.client.post(
            f"/api/inventory/stocktakes/{st.id}/post/",
            data="", content_type="application/json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(Stocktake.objects.get(pk=st.id).is_posted)

    def test_post_body_must_be_a_json_object(self):
        """جسمٌ ليس كائناً JSON (مصفوفةٌ مثلاً) يُرفض برسالته — لا 500."""
        st = self._manual_stocktake([(self.p_a1, Decimal("12"))], user=self.manager)
        self._as(self.manager)
        res = self.client.post(
            f"/api/inventory/stocktakes/{st.id}/post/",
            ["not", "an", "object"], format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.data["error"], "جسم الطلب يجب أن يكون كائناً JSON")
        self.assertFalse(Stocktake.objects.get(pk=st.id).is_posted)

    def test_service_call_keeps_positional_form(self):
        """المستدعي القديم `post_stocktake(s)` يبقى يعمل — السلوك الافتراضي استثناءُ غير المعدود."""
        st = self._manual_stocktake(
            [(self.p_a1, Decimal("10")), (self.p_b, None)], user=self.manager)
        post_stocktake(st)
        st.refresh_from_db()
        self.assertTrue(st.is_posted)

    # ── نقطة المنتجات المباشرة لتصنيفٍ واحد (ST-1) ──
    def _scope_products(self, query=""):
        self._as(self.manager)
        url = "/api/inventory/stocktakes/scope-products/" + query
        return self.client.get(url)

    def test_scope_products_lists_direct_products_only(self):
        # اسمٌ يسبق «منتج أ» ترتيباً ليُقاس الترتيب لا المجموعة وحدها.
        first = Product.objects.create(
            tenant=self.tenant, sku="SC-AA", name_ar="أقدم منتج", category=self.cat_a,
            quantity_on_hand=Decimal("1"), avg_cost=Decimal("1"))
        res = self._scope_products(f"?category={self.cat_a.id}")
        self.assertEqual(res.status_code, 200, res.content)
        # منتج الابن ليس هنا (دلالةٌ مباشرة، قرار ٣)، والخدمة والمعطَّل خارجها.
        self.assertEqual([row["id"] for row in res.data], [first.id, self.p_a1.id])

        res = self._scope_products(f"?category={self.cat_a.id}&include_inactive=true")
        self.assertEqual(
            {row["id"] for row in res.data},
            {first.id, self.p_a1.id, self.p_inactive.id})
        self.assertNotIn(self.p_service.id, {row["id"] for row in res.data})

    def test_scope_products_none_lists_uncategorized(self):
        res = self._scope_products("?category=none")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual({row["id"] for row in res.data}, {self.p_none.id})

    def test_scope_products_rejects_missing_bad_or_foreign_category(self):
        for query in ("", "?category=", "?category=abc", "?category=1.5"):
            with self.subTest(query=query):
                res = self._scope_products(query)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("category", res.data)
                self.assertIsInstance(res.data["category"], list)
                self.assertIn(
                    "معرّف التصنيف يجب أن يكون عدداً صحيحاً أو none",
                    res.data["category"])

        res = self._scope_products(f"?category={self.foreign_cat.id}")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("category", res.data)
        self.assertIsInstance(res.data["category"], list)
        self.assertIn("تصنيف غير موجود لهذه الشركة", res.data["category"])

    def test_scope_products_keys_are_an_allow_list(self):
        res = self._scope_products(f"?category={self.cat_a.id}")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.data), 1)
        row = res.data[0]
        self.assertEqual(set(row), {"id", "name", "sku", "is_active"})
        self.assertEqual(row["sku"], "SC-A1")
        self.assertEqual(row["name"], "منتج أ")
        self.assertIs(row["is_active"], True)

    def test_scope_products_query_count_is_constant(self):
        def add(category, sku, name):
            Product.objects.create(
                tenant=self.tenant, sku=sku, name_ar=name, category=category,
                quantity_on_hand=Decimal("1"), avg_cost=Decimal("1"))

        add(self.cat_a, "SC-C1", "منتج تصنيف أ")
        for index in range(19):
            add(self.cat_b, f"SC-D{index}", f"منتج {index}")
        self._as(self.manager)
        url = "/api/inventory/stocktakes/scope-products/"
        # تسخين المصادقة/الشركة قبل القياس كما في بقيّة عدّادات هذا الملف.
        self.client.get(f"{url}?category={self.cat_a.id}")
        with CaptureQueriesContext(connection) as small:
            small_res = self.client.get(f"{url}?category={self.cat_a.id}")
        with CaptureQueriesContext(connection) as large:
            large_res = self.client.get(f"{url}?category={self.cat_b.id}")
        self.assertEqual(len(small_res.data), 2)
        self.assertEqual(len(large_res.data), 20)
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))

    def test_scope_products_matches_generated_lines(self):
        listed = {row["id"] for row in self._scope_products(
            f"?category={self.cat_a.id}").data}
        generated = self._create_scope({"categories": [self.cat_a.id]})
        self.assertEqual(generated.status_code, 201, generated.content)
        self.assertEqual(listed, self._line_ids(generated))


class StocktakeScopeSignatureTest(SimpleTestCase):
    """الشكل المعياري للنطاق — دالةٌ صرفة تقرّب الصدى المكافئ وتبقي الاختلاف اختلافاً."""

    def test_non_dict_values_are_returned_as_is(self):
        for value in (None, [], ["a"], "all", 3):
            with self.subTest(value=value):
                self.assertIs(inventory_services.stocktake_scope_signature(value), value)

    def test_missing_keys_take_the_defaults(self):
        self.assertEqual(
            inventory_services.stocktake_scope_signature({"categories": [2, 1, 2]}),
            inventory_services.stocktake_scope_signature({
                "all": False, "uncategorized": False, "include_inactive": False,
                "categories": [1, 2], "products": [],
            }))

    def test_a_list_that_is_not_all_int_is_returned_raw(self):
        # التطبيع للمعرّفات الرقمية وحدها؛ قائمةُ نصوصٍ تُقارن كما هي فلا تُقارَب صورُها.
        self.assertNotEqual(
            inventory_services.stocktake_scope_signature({"categories": ["b", "a"]}),
            inventory_services.stocktake_scope_signature({"categories": ["a", "b"]}))

    def test_unknown_key_keeps_the_two_shapes_different(self):
        self.assertIn("bogus", inventory_services.stocktake_scope_signature({"bogus": True}))
        self.assertNotEqual(
            inventory_services.stocktake_scope_signature({"categories": [1]}),
            inventory_services.stocktake_scope_signature({"categories": [1], "bogus": True}))

    def test_int_one_is_not_the_true_flag(self):
        # `1 == True` في بايثون: بلا وسمِ النوع يمرّ علمٌ غير صالح كأنه `true`.
        self.assertNotEqual(
            inventory_services.stocktake_scope_signature({"all": 1}),
            inventory_services.stocktake_scope_signature({"all": True}))
        self.assertNotEqual(
            inventory_services.stocktake_scope_signature({"all": "true"}),
            inventory_services.stocktake_scope_signature({"all": True}))
        self.assertEqual(
            inventory_services.stocktake_scope_signature({"all": True}),
            inventory_services.stocktake_scope_signature({"all": True}))


class StocktakeScopeMigrationTest(TransactionTestCase):
    """الهجرة ذهاباً وإياباً على SQLite.

    `pytest` يعمل بـ`--nomigrations` فلا `MigrationExecutor` هنا (جدول الهجرات فارغ
    والجداول مبنيّة من النماذج). نتبع سابقة `sales/tests/test_policy_migration.py`:
    نطارد عمليّات الهجرة الحقيقية على جدولٍ مؤقّتٍ مبنيٍّ من حالة 0042.
    """

    def test_round_trip(self):
        migration = importlib.import_module(
            "inventory.migrations.0043_stocktake_scope_counted_by").Migration
        state = ProjectState()
        state.add_model(ModelState(
            "auth", "User", [("id", models.AutoField(primary_key=True))],
            options={"db_table": "auth_user"}))
        state.add_model(ModelState(
            "inventory", "Stocktake",
            [
                ("id", models.AutoField(primary_key=True)),
                ("stocktake_number", models.CharField(
                    max_length=30, blank=True, default="", db_column="StocktakeNumber")),
                ("stocktake_date", models.DateField(db_column="StocktakeDate")),
                ("notes", models.CharField(
                    max_length=500, blank=True, default="", db_column="Notes")),
                ("is_posted", models.BooleanField(default=False, db_column="IsPosted")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_column="CreatedAt")),
                ("updated_at", models.DateTimeField(auto_now=True, db_column="UpdatedAt")),
            ],
            options={"db_table": "tmp_stocktake_round_trip"}))
        state.add_model(ModelState(
            "inventory", "StocktakeLine",
            [
                ("id", models.AutoField(primary_key=True)),
                ("counted_quantity", models.DecimalField(
                    max_digits=18, decimal_places=4, db_column="CountedQuantity")),
                ("system_quantity", models.DecimalField(
                    max_digits=18, decimal_places=4, default=0, db_column="SystemQuantity")),
                ("variance", models.DecimalField(
                    max_digits=18, decimal_places=4, default=0, db_column="Variance")),
            ],
            options={"db_table": "tmp_stocktake_line_round_trip"}))

        stocktake_table = "tmp_stocktake_round_trip"
        line_table = "tmp_stocktake_line_round_trip"

        def columns(table):
            with connection.cursor() as cursor:
                return {
                    col.name: col.null_ok
                    for col in connection.introspection.get_table_description(cursor, table)
                }

        with connection.schema_editor() as editor:
            editor.create_model(state.apps.get_model("inventory", "Stocktake"))
            editor.create_model(state.apps.get_model("inventory", "StocktakeLine"))
        try:
            before = columns(line_table)
            self.assertNotIn("CountedByName", before)
            self.assertFalse(before["CountedQuantity"])

            # حالة ما بعد كل عملية — `state_forwards` يعدّل الحالة في مكانها.
            states = [state]
            for operation in migration.operations:
                next_state = states[-1].clone()
                operation.state_forwards("inventory", next_state)
                states.append(next_state)

            with connection.schema_editor() as editor:
                for index, operation in enumerate(migration.operations):
                    operation.database_forwards(
                        "inventory", editor, states[index], states[index + 1])

            stock_columns = columns(stocktake_table)
            self.assertIn("CreatedByID", stock_columns)
            self.assertIn("Scope", stock_columns)
            line_columns = columns(line_table)
            self.assertIn("CountedByName", line_columns)
            self.assertIn("CountedAt", line_columns)
            self.assertTrue(line_columns["CountedQuantity"])

            with connection.schema_editor() as editor:
                for index in reversed(range(len(migration.operations))):
                    migration.operations[index].database_backwards(
                        "inventory", editor, states[index + 1], states[index])

            self.assertNotIn("CreatedByID", columns(stocktake_table))
            self.assertNotIn("Scope", columns(stocktake_table))
            reverted = columns(line_table)
            self.assertNotIn("CountedByName", reverted)
            self.assertNotIn("CountedAt", reverted)
            self.assertFalse(reverted["CountedQuantity"])
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(state.apps.get_model("inventory", "StocktakeLine"))
                editor.delete_model(state.apps.get_model("inventory", "Stocktake"))
