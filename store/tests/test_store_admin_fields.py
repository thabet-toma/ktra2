"""حدود لوحة إدارة المتجر: ماذا تُعدّل، وكيف تُرقّم، وما لا تفرضه على المستخدم.

`store.manage` صلاحية **تسويقية** لا صلاحية مخزون. اللوحة تنشر المنتج المخزني
وتسحبه، لكنها لا تُعيد تعريفه: `sale_price` و`sku` و`name_ar` حقول تقرؤها
الفوترة والتقارير، وتغييرها من هنا يجعل مسؤول تسويق يصيب سعر البيع المعتمَد
بلا أن يدري.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product, UnitOfMeasure
from tenants.services import create_company


class StoreAdminFieldScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uom = UnitOfMeasure.objects.create(code="PCS", name_ar="قطعة")
        cls.user = User.objects.create_user(username="fs", password="pw123456")
        cls.tenant = create_company("شركة الحقول", cls.user)
        cls.tenant.store_slug = "fields"
        cls.tenant.save()

        cls.stock_item = Product.objects.create(
            tenant=cls.tenant, sku="INV-01", name_ar="منتج مخزني",
            sale_price=Decimal("50.00"), is_store_only=False, uom=cls.uom,
        )

    def setUp(self):
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    def _patch(self, product, payload):
        return self.auth.patch(
            f"/api/store/admin/products/{product.id}/", payload, format="json",
        )

    # ── THA-427: حقول المتجر وحدها على المنتج المخزني ───────────────────

    def test_store_fields_are_editable_on_an_inventory_product(self):
        """النشر والسعر المتجري والوصف والطلب المسبق — هذا غرض اللوحة."""
        res = self._patch(self.stock_item, {
            "is_for_sale_online": True,
            "online_price": "60.00",
            "online_description": "وصف للمتجر",
            "allow_preorder": True,
        })
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.stock_item.refresh_from_db()
        self.assertTrue(self.stock_item.is_for_sale_online)
        self.assertEqual(self.stock_item.online_price, Decimal("60.00"))

    def test_operational_fields_are_refused_on_an_inventory_product(self):
        """`sale_price` تقرؤه الفوترة — لا يُمسّ بصلاحية تسويقية."""
        res = self._patch(self.stock_item, {"sale_price": "5.00"})
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.sale_price, Decimal("50.00"))

    def test_identity_fields_are_refused_on_an_inventory_product(self):
        for payload in ({"sku": "HACK"}, {"name_ar": "اسم آخر"}, {"brand": "براند"}):
            with self.subTest(payload=payload):
                res = self._patch(self.stock_item, payload)
                self.assertEqual(res.status_code, 400, res.content[:300])
        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.sku, "INV-01")
        self.assertEqual(self.stock_item.name_ar, "منتج مخزني")

    def test_the_refusal_names_the_rejected_fields(self):
        """رسالة تقول ماذا رُفض وأين يُعدَّل — لا رفضٌ صامت."""
        res = self._patch(self.stock_item, {"sale_price": "5.00"})
        body = str(res.content, "utf-8")
        self.assertIn("sale_price", body)

    def test_a_store_only_product_stays_fully_editable(self):
        """منتج المتجر الخالص ملكُ اللوحة — الحارس يضيّق ولا يقفل."""
        mine = Product.objects.create(
            tenant=self.tenant, sku="ST-X", name_ar="منتج متجر",
            is_store_only=True, uom=self.uom,
        )
        res = self._patch(mine, {"name_ar": "اسم جديد", "sale_price": "12.00"})
        self.assertEqual(res.status_code, 200, res.content[:300])
        mine.refresh_from_db()
        self.assertEqual(mine.name_ar, "اسم جديد")

    # ── THA-425: الطلب المسبق قرار المستخدم ────────────────────────────

    def test_preorder_is_not_forced_on_new_products(self):
        """«طلب مسبق» وعدٌ تجاري — لا يفرضه الكود على كل منتج يُنشأ."""
        res = self.auth.post(
            "/api/store/admin/products/", {"name_ar": "منتج بلا وعد"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertFalse(Product.objects.get(pk=res.json()["id"]).allow_preorder)

    def test_preorder_can_still_be_asked_for(self):
        res = self.auth.post(
            "/api/store/admin/products/",
            {"name_ar": "منتج بطلب مسبق", "allow_preorder": True}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertTrue(Product.objects.get(pk=res.json()["id"]).allow_preorder)

    # ── THA-426: الترقيم تسلسلي لا عشوائي ──────────────────────────────

    def test_generated_skus_are_sequential_and_do_not_collide(self):
        codes = []
        for i in range(3):
            res = self.auth.post(
                "/api/store/admin/products/", {"name_ar": f"منتج {i}"}, format="json",
            )
            self.assertEqual(res.status_code, 201, res.content[:300])
            codes.append(Product.objects.get(pk=res.json()["id"]).sku)
        self.assertEqual(len(set(codes)), 3, codes)
        for code in codes:
            self.assertRegex(code, r"^ST-\d{6}$")

    def test_a_duplicate_explicit_sku_is_a_400_not_a_500(self):
        """رمزٌ مكرّر يُدخله المستخدم خطأُ إدخال لا انهيار خادم."""
        first = self.auth.post(
            "/api/store/admin/products/",
            {"name_ar": "الأول", "sku": "DUP-1"}, format="json",
        )
        self.assertEqual(first.status_code, 201, first.content[:300])
        second = self.auth.post(
            "/api/store/admin/products/",
            {"name_ar": "الثاني", "sku": "DUP-1"}, format="json",
        )
        self.assertEqual(second.status_code, 400, second.content[:300])

    def test_a_generated_sku_skips_one_a_user_already_took(self):
        """المستخدم حجز `ST-000001` يدوياً — التوليد يتخطّاه بدل أن ينهار."""
        Product.objects.create(
            tenant=self.tenant, sku="ST-000001", name_ar="محجوز يدوياً",
            is_store_only=True, uom=self.uom,
        )
        res = self.auth.post(
            "/api/store/admin/products/", {"name_ar": "التالي"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertNotEqual(Product.objects.get(pk=res.json()["id"]).sku, "ST-000001")
