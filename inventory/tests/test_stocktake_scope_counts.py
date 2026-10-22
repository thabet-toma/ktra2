"""K2 (B1): عدّادات نطاق الجرد — القراءة نفسها التي يبني عليها الخادم بنود الجرد.

الغرض الحقيقي لهذه النقطة أن تتطابق **بلا انحراف**: ما يعرضه المنتقي في
«جرد جديد» هو بالضبط عدد البنود التي سيولّدها `POST stocktakes/` للنطاق نفسه.

بعض الاختبارات تقارن العدّاد بعدد البنود المولَّدة فعلاً — فحين تتغيّر قاعدة
التوليد يتباعد الرقمان معاً فيُكشف الانحراف بدل أن يكذب رقمٌ مكتوب باليد.
وبعضها يثبّت رقماً مشتقّاً من بيانات الاختبار نفسها (خدمةٌ لا تُعدّ، ومعطَّلٌ
يدخل بـ`include_inactive`، وشركةٌ أخرى لا تُرى) لأن السؤال هناك قاعدةٌ لا تعداد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, ProductCategory
from tenants.models import UserCompanyMembership
from tenants.services import create_company

COUNTS_URL = "/api/inventory/stocktakes/scope-counts/"
LIST_URL = "/api/inventory/stocktakes/"


class StocktakeScopeCountsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="scc-owner", password="x")
        cls.tenant = create_company("شركة عدّادات النطاق", cls.owner)
        cls.manager = User.objects.create_user(username="scc-manager", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.tenant, role="manager")

        cls.cat_a = ProductCategory.objects.create(tenant=cls.tenant, name="تصنيف أ")
        cls.cat_b = ProductCategory.objects.create(tenant=cls.tenant, name="تصنيف ب")
        cls.cat_child = ProductCategory.objects.create(
            tenant=cls.tenant, name="ابن أ", parent=cls.cat_a)
        cls.cat_empty = ProductCategory.objects.create(
            tenant=cls.tenant, name="فارغ")

        def product(sku, name, category=None, **extra):
            return Product.objects.create(
                tenant=cls.tenant, sku=sku, name_ar=name, category=category,
                quantity_on_hand=extra.pop("quantity_on_hand", Decimal("10")),
                avg_cost=extra.pop("avg_cost", Decimal("10")), **extra)

        cls.p_a1 = product("SCC-A1", "منتج أ١", cls.cat_a)
        cls.p_a2 = product("SCC-A2", "منتج أ٢", cls.cat_a)
        cls.p_child = product("SCC-CH", "منتج الابن", cls.cat_child)
        cls.p_b = product("SCC-B", "منتج ب", cls.cat_b)
        cls.p_none = product("SCC-N", "بلا تصنيف")
        cls.p_inactive = product("SCC-I", "معطَّل", cls.cat_a, is_active=False)
        cls.p_inactive_none = product("SCC-IN", "معطَّل بلا تصنيف", is_active=False)
        cls.p_service = product("SCC-S", "خدمة", cls.cat_a, is_service=True)

        cls.foreign_owner = User.objects.create_user(username="scc-foreign", password="x")
        cls.foreign_tenant = create_company("شركة عدّادات أجنبية", cls.foreign_owner)
        cls.foreign_cat = ProductCategory.objects.create(
            tenant=cls.foreign_tenant, name="تصنيف أجنبي")
        Product.objects.create(
            tenant=cls.foreign_tenant, sku="SCC-F", name_ar="منتج أجنبي",
            category=cls.foreign_cat, quantity_on_hand=Decimal("9"),
            avg_cost=Decimal("9"))
        # براندٌ أجنبي بلا تصنيف أيضاً: لا يُضاف إلى «بدون تصنيف» عندنا.
        Product.objects.create(
            tenant=cls.foreign_tenant, sku="SCC-FN", name_ar="أجنبي بلا تصنيف",
            quantity_on_hand=Decimal("1"), avg_cost=Decimal("1"))

    # ── أدوات ──
    def _as_manager(self):
        self.client.force_authenticate(user=self.manager)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _counts(self, include_inactive=None):
        url = COUNTS_URL
        if include_inactive is not None:
            url = f"{url}?include_inactive={include_inactive}"
        return self.client.get(url)

    def _create_scope(self, scope):
        return self.client.post(
            LIST_URL,
            {"stocktake_date": "2026-07-01", "scope": scope},
            format="json",
        )

    @staticmethod
    def _category_counts(payload):
        return {int(key): value for key, value in payload["categories"].items()}

    def _scope_total(self, payload, scope):
        counts = self._category_counts(payload)
        total = 0
        if scope.get("all"):
            return payload["all"]
        for category_id in scope.get("categories", []):
            total += counts.get(int(category_id), 0)
        if scope.get("uncategorized"):
            total += payload["uncategorized"]
        return total

    # ── التطابق مع البنود المولَّدة ──
    def test_counts_equal_generated_lines_for_every_scope(self):
        self._as_manager()
        scopes = [
            {"categories": [self.cat_a.id]},
            {"categories": [self.cat_a.id, self.cat_b.id]},
            # الدلالة الصريحة: تصنيف الابن غير مختار ⇒ منتجه لا يدخل.
            {"categories": [self.cat_child.id, self.cat_b.id]},
            {"uncategorized": True},
            {"categories": [self.cat_empty.id], "uncategorized": True},
            {"all": True},
            {"categories": [self.cat_a.id], "include_inactive": True},
            {"all": True, "include_inactive": True},
        ]
        for scope in scopes:
            with self.subTest(scope=scope):
                include_inactive = "true" if scope.get("include_inactive") else "false"
                counts_res = self._counts(include_inactive)
                self.assertEqual(counts_res.status_code, 200, counts_res.content)
                expected = self._scope_total(counts_res.data, scope)

                created = self._create_scope(scope)
                self.assertEqual(created.status_code, 201, created.content)
                self.assertEqual(
                    len(created.data["lines"]), expected,
                    f"العدّاد {expected} لا يطابق البنود المولَّدة للنطاق {scope}",
                )

    def test_direct_products_only_and_children_not_counted_upwards(self):
        self._as_manager()
        res = self._counts()
        self.assertEqual(res.status_code, 200, res.content)
        counts = self._category_counts(res.data)
        # أ: منتجان نشطان مباشران — الابن منتجه في عقدته لا في أبيه.
        self.assertEqual(counts[self.cat_a.id], 2)
        self.assertEqual(counts[self.cat_child.id], 1)
        self.assertEqual(counts[self.cat_b.id], 1)
        # تصنيفٌ بلا منتج قد يُحذف من الردّ — وغيابه يعني صفراً.
        self.assertEqual(counts.get(self.cat_empty.id, 0), 0)

    def test_services_are_never_counted(self):
        self._as_manager()
        res = self._counts()
        self.assertEqual(res.status_code, 200, res.content)
        counts = self._category_counts(res.data)
        # في «أ» منتجان نشطان + منتج خدمة — الخدمة لا تُعدّ حتى في تصنيفها.
        self.assertEqual(counts[self.cat_a.id], 2)
        self.assertEqual(res.data["all"], 5)

    def test_inactive_toggle_changes_both_the_counts_and_the_created_lines(self):
        self._as_manager()
        active = self._counts()
        with_inactive = self._counts("true")
        self.assertEqual(active.status_code, 200, active.content)
        self.assertEqual(with_inactive.status_code, 200, with_inactive.content)

        self.assertEqual(self._category_counts(active.data)[self.cat_a.id], 2)
        self.assertEqual(self._category_counts(with_inactive.data)[self.cat_a.id], 3)
        self.assertEqual(active.data["uncategorized"], 1)
        self.assertEqual(with_inactive.data["uncategorized"], 2)
        self.assertEqual(with_inactive.data["all"], active.data["all"] + 2)

        created = self._create_scope({"all": True, "include_inactive": True})
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(len(created.data["lines"]), with_inactive.data["all"])

    def test_include_inactive_defaults_to_false_and_rejects_anything_else(self):
        self._as_manager()
        default = self._counts()
        explicit = self._counts("false")
        self.assertEqual(default.status_code, 200, default.content)
        self.assertEqual(default.data, explicit.data)

        for bad in ("1", "yes", "TRUE", "", "0"):
            with self.subTest(value=bad):
                res = self._counts(bad)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("include_inactive", str(res.data))

    def test_other_tenants_are_never_counted(self):
        self._as_manager()
        res = self._counts("true")
        self.assertEqual(res.status_code, 200, res.content)
        counts = self._category_counts(res.data)
        self.assertNotIn(self.foreign_cat.id, counts)
        self.assertEqual(res.data["uncategorized"], 2)
        # 5 منتجات نشطة + منتجان معطَّلان في شركتنا — لا يُضاف منتج الشركة الأخرى.
        self.assertEqual(res.data["all"], 7)

        # والتصنيف الأجنبي في نطاق الإنشاء ما زال مرفوضاً بالاسم.
        created = self._create_scope({"categories": [self.foreign_cat.id]})
        self.assertEqual(created.status_code, 400, created.content)
        self.assertIn(str(self.foreign_cat.id), str(created.data))

    # ── كلفة القراءة ──
    def test_counts_run_a_bounded_number_of_queries(self):
        self._as_manager()
        # نقطة قراءة واحدة: شركة + صلاحية + استعلام تجميع واحد. لا استعلام
        # لكل تصنيف — الشجرة في الإنتاج آلاف العُقد. الرقم المثبَّت هو ما
        # يُنفَّذ فعلاً؛ أيّ استعلامٍ جديد يهبط هنا لا يمرّ بصمت.
        with self.assertNumQueries(3):
            res = self._counts()
        self.assertEqual(res.status_code, 200, res.content)
