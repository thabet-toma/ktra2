"""M0 — حرس شجرة التصنيفات.

كان `CategoryViewSet` يقبل أيّ أبٍ يُرسَل إليه: نفسه، أحد أحفاده (فتنشأ حلقة
في الشجرة)، أو تصنيفاً من شركة أخرى — واسماً فارغاً يظهر سطراً أعمى في المنتقي.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import ProductCategory
from tenants.services import create_company

CATEGORIES_URL = "/api/inventory/categories/"


class CategoryTreeGuardTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="cats_a", password="x")
        cls.owner_b = User.objects.create_user(username="cats_b", password="x")
        cls.t_a = create_company("شركة التصنيفات أ", cls.owner_a)
        cls.t_b = create_company("شركة التصنيفات ب", cls.owner_b)

    def setUp(self):
        self.client.force_authenticate(user=self.owner_a)
        self._tenant_id = str(self.t_a.TenantID)

    def _post(self, payload):
        return self.client.post(CATEGORIES_URL, payload, format="json",
                                HTTP_X_TENANT_ID=self._tenant_id)

    def _patch(self, pk, payload):
        return self.client.patch(f"{CATEGORIES_URL}{pk}/", payload, format="json",
                                 HTTP_X_TENANT_ID=self._tenant_id)

    def test_blank_name_rejected(self):
        res = self._post({"name": "   "})
        assert res.status_code == 400, res.content[:300]
        assert "اسم التصنيف مطلوب" in str(res.json())

    def test_subcategory_under_parent_is_created(self):
        parent = ProductCategory.objects.create(tenant=self.t_a, name="إطارات")
        res = self._post({"name": "شاحنات", "parent": parent.id})
        assert res.status_code == 201, res.content[:300]
        assert res.json()["parent"] == parent.id

    def test_self_parent_rejected(self):
        node = ProductCategory.objects.create(tenant=self.t_a, name="قطع غيار")
        res = self._patch(node.id, {"parent": node.id})
        assert res.status_code == 400, res.content[:300]
        assert "أباً لنفسه" in str(res.json())
        node.refresh_from_db()
        assert node.parent_id is None

    def test_descendant_as_parent_rejected(self):
        root = ProductCategory.objects.create(tenant=self.t_a, name="جذر")
        child = ProductCategory.objects.create(tenant=self.t_a, name="ابن", parent=root)
        grandchild = ProductCategory.objects.create(tenant=self.t_a, name="حفيد", parent=child)

        res = self._patch(root.id, {"parent": grandchild.id})
        assert res.status_code == 400, res.content[:300]
        assert "حلقة" in str(res.json())
        root.refresh_from_db()
        assert root.parent_id is None

    def test_cross_tenant_parent_rejected(self):
        foreign = ProductCategory.objects.create(tenant=self.t_b, name="تصنيف الشركة الأخرى")
        res = self._post({"name": "محاولة", "parent": foreign.id})
        assert res.status_code == 400, res.content[:300]
        assert "غير موجود لهذه الشركة" in str(res.json())

    def test_moving_under_an_unrelated_branch_still_allowed(self):
        """الحرس يمنع الحلقة وحدها — لا يجمّد الشجرة."""
        root = ProductCategory.objects.create(tenant=self.t_a, name="جذر")
        child = ProductCategory.objects.create(tenant=self.t_a, name="ابن", parent=root)
        other = ProductCategory.objects.create(tenant=self.t_a, name="فرع آخر")

        res = self._patch(child.id, {"parent": other.id})
        assert res.status_code == 200, res.content[:300]
        child.refresh_from_db()
        assert child.parent_id == other.id
