"""THA-166 م٧ — رأسُ صفحة الفئة العامّ: `GET /api/store/<slug>/categories/<id>/`.

سدُّ فجوةٍ: `facets.categories` في `/products/` تنشر `id`/`name`/`parent_id`/
`count` وحدها (كافيةٌ لعدّادات الفلترة، لا لرأس صفحةٍ فيه صورة). هذه النقطة
وحدها تنشر `slug`/`image_url`/أباً كاملاً — لرأس صفحة الفئة في الواجهة.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from store.models import StoreCategory
from tenants.models import Tenant


def _tenant(slug, **kwargs):
    defaults = dict(CompanyName=f"شركة {slug}", SubscriptionPlan="Pro", Status="Active")
    defaults.update(kwargs)
    return Tenant.objects.create(store_slug=slug, **defaults)


class StoreCategoryDetailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _tenant("cat-detail")
        cls.other_tenant = _tenant("cat-detail-other")
        cls.parent = StoreCategory.objects.create(
            tenant=cls.tenant, name="إلكترونيات", slug="electronics")
        cls.child = StoreCategory.objects.create(
            tenant=cls.tenant, name="هواتف", parent=cls.parent, slug="phones",
            image_url="https://example.test/phones.jpg")
        cls.inactive = StoreCategory.objects.create(
            tenant=cls.tenant, name="مُعطَّلة", slug="disabled", is_active=False)
        cls.other_category = StoreCategory.objects.create(
            tenant=cls.other_tenant, name="فئة شركة أخرى", slug="other")

    def _get(self, category_id, slug="cat-detail"):
        return APIClient().get(f"/api/store/{slug}/categories/{category_id}/")

    def test_child_category_carries_name_slug_image_and_parent(self):
        res = self._get(self.child.id)
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertEqual(set(body.keys()), {"id", "name", "slug", "image_url", "parent"})
        self.assertEqual(body["name"], "هواتف")
        self.assertEqual(body["slug"], "phones")
        self.assertEqual(body["image_url"], "https://example.test/phones.jpg")
        self.assertEqual(
            body["parent"], {"id": self.parent.id, "name": "إلكترونيات", "slug": "electronics"},
        )

    def test_parent_category_has_null_parent_and_null_image_when_unset(self):
        """`image_url` فارغةٌ (`blank=True, default=""`) على النموذج — تُنشَر `null` لا نصّاً فارغاً."""
        res = self._get(self.parent.id)
        body = res.json()
        self.assertIsNone(body["parent"])
        self.assertIsNone(body["image_url"])

    def test_inactive_category_is_404_not_leaked(self):
        self.assertEqual(self._get(self.inactive.id).status_code, 404)

    def test_other_tenants_category_id_is_404(self):
        self.assertEqual(self._get(self.other_category.id).status_code, 404)

    def test_unknown_category_id_is_404(self):
        self.assertEqual(self._get(999999).status_code, 404)

    def test_unknown_slug_is_404(self):
        self.assertEqual(self._get(self.child.id, slug="nope").status_code, 404)
