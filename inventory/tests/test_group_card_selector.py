"""الكرت المجمّع: المحدِّد في جسم الطلب لا في عنوانه.

كانت الواجهة تعدّ أعضاء المجموعة في سطر الطلب (`?ids=1,2,3…`). تصنيفُ جذرٍ فيه
~1500 منتج ⇒ ~7.5KB في سطر الطلب، وهو فوق `large_client_header_buffers 8k` في
nginx ⇒ **414/400 في الإنتاج بينما التطوير يمرّ** (runserver أسخى بكثير).

هنا يُثبَّت العقد الجديد: POST يحمل `ids` (بعددٍ كبير) أو `category` (فيشتقّ
الخادم منتجاته وأحفاده)، والعنوان يبقى قصيراً؛ و`?ids=` بـGET يبقى مفهوماً
لتوافق الروابط القديمة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, ProductCategory
from tenants.models import UserCompanyMembership
from tenants.services import create_company

PROFILE_URL = "/api/inventory/products/group-profile/"
LEDGER_URL = "/api/inventory/products/group-ledger/"
INVOICES_URL = "/api/inventory/products/group-invoices/"

# أكبر من عدد منتجات «منتجات عامة» في شركة الجرابعه (1490) التي كسرت الإنتاج.
MANY = 1500


class GroupCardSelectorTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="grpsel", password="x")
        cls.tenant = create_company("شركة الكرت المجمّع", cls.owner)
        cls.root = ProductCategory.objects.create(tenant=cls.tenant, name="منتجات عامة")
        cls.child = ProductCategory.objects.create(
            tenant=cls.tenant, name="إطارات", parent=cls.root)
        # معرّفات من ستّ خانات كما في قاعدة الإنتاج — لأن طول العنوان هو
        # موضوع الاختبار، وترقيمُ قاعدةٍ فارغة (1، 2، 3…) يجعله أقصر بالثلث.
        Product.objects.bulk_create([
            Product(
                id=100000 + i,
                tenant=cls.tenant, sku=f"S-{i}", name_ar=f"منتج {i}",
                category=cls.child if i % 2 else cls.root,
                quantity_on_hand=Decimal("2"), avg_cost=Decimal("5"),
            )
            for i in range(MANY)
        ])
        cls.products = list(Product.objects.filter(tenant=cls.tenant).order_by("id"))
        # شركة أخرى: لا يجوز أن يظهر منتجها في أي محدِّد.
        cls.other_owner = User.objects.create_user(username="grpsel_b", password="x")
        cls.other = create_company("شركة أخرى", cls.other_owner)
        cls.other_cat = ProductCategory.objects.create(tenant=cls.other, name="منتجات عامة")
        cls.other_product = Product.objects.create(
            tenant=cls.other, sku="X-1", name_ar="منتج غريب", category=cls.other_cat)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.tenant_id = str(self.tenant.TenantID)

    def _post(self, url, payload, tenant_id=None):
        return self.client.post(
            url, payload, format="json",
            HTTP_X_TENANT_ID=tenant_id or self.tenant_id)

    # ── العلّة الأصلية: عددٌ كبير من المعرّفات يمرّ لأنه في الجسم ──
    def test_post_carries_many_ids_in_the_body_not_the_url(self):
        ids = [p.id for p in self.products]
        # العنوان القديم (`?ids=…`) كان سيتجاوز حدّ سطر الطلب في nginx (8KB).
        self.assertGreater(len(",".join(str(i) for i in ids)), 8 * 1024)

        res = self._post(PROFILE_URL, {"ids": ids})
        self.assertEqual(res.status_code, 200, res.content[:300])
        data = res.json()
        self.assertEqual(data["member_count"], MANY)
        self.assertEqual(Decimal(data["quantity_on_hand"]), Decimal(MANY * 2))
        # والعنوان نفسه بقي قصيراً — هذا هو الإصلاح.
        self.assertLess(len(PROFILE_URL), 100)

    def test_ledger_and_invoices_accept_many_ids_by_post(self):
        ids = [p.id for p in self.products]
        led = self._post(LEDGER_URL, {"ids": ids, "limit": 10, "offset": 0})
        self.assertEqual(led.status_code, 200, led.content[:300])
        self.assertEqual(led.json()["limit"], 10)

        inv = self._post(INVOICES_URL, {"ids": ids})
        self.assertEqual(inv.status_code, 200, inv.content[:300])
        self.assertEqual(inv.json(), [])

    # ── البديل الأوجز: التصنيف، والخادم يشتقّ الأعضاء ──
    def test_category_selector_covers_descendants(self):
        res = self._post(PROFILE_URL, {"category": self.root.id})
        self.assertEqual(res.status_code, 200, res.content[:300])
        # الجذر يشمل منتجاته ومنتجات ابنه معاً.
        self.assertEqual(res.json()["member_count"], MANY)

        leaf = self._post(PROFILE_URL, {"category": self.child.id})
        self.assertEqual(leaf.json()["member_count"], MANY // 2)

    def test_category_of_another_company_yields_nothing(self):
        res = self._post(PROFILE_URL, {"category": self.other_cat.id})
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["member_count"], 0)

    def test_ids_of_another_company_are_filtered_out(self):
        res = self._post(PROFILE_URL, {"ids": [self.other_product.id, self.products[0].id]})
        self.assertEqual(res.json()["member_count"], 1)
        self.assertEqual(res.json()["members"][0]["sku"], self.products[0].sku)

    # ── التوافق: الروابط القديمة بـGET ──
    def test_legacy_get_with_ids_query_still_works(self):
        ids = ",".join(str(p.id) for p in self.products[:3])
        res = self.client.get(
            f"{PROFILE_URL}?ids={ids}", HTTP_X_TENANT_ID=self.tenant_id)
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["member_count"], 3)

    def test_legacy_get_accepts_category_too(self):
        res = self.client.get(
            f"{PROFILE_URL}?category={self.child.id}", HTTP_X_TENANT_ID=self.tenant_id)
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["member_count"], MANY // 2)

    # ── POST هنا قراءة لا كتابة: «مستعرض» يبقى يراها ──
    def test_viewer_role_can_still_open_the_group_card(self):
        viewer = User.objects.create_user(username="grpsel_viewer", password="x")
        UserCompanyMembership.objects.create(
            user=viewer, tenant=self.tenant, role="viewer")
        self.client.force_authenticate(user=viewer)
        res = self._post(PROFILE_URL, {"category": self.root.id})
        self.assertEqual(res.status_code, 200, res.content[:300])

    def test_category_lookup_query_count_is_flat(self):
        from inventory.services import category_descendant_product_ids

        with self.assertNumQueries(2):
            ids = category_descendant_product_ids(
                tenant_id=self.tenant.pk, category_id=self.root.id)
        self.assertEqual(len(ids), MANY)
