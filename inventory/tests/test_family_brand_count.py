"""C2 — عدد براندات «المنتج» على عقد البراند (`family_brand_count`).

`category` **حقلُ عائلةٍ لا حقلُ صفّ**: تغييره على براندٍ واحد ينقل كل براندات
المنتج نفسه (`sync_family_from_product`). فكرتُ المنتج تحتاج الرقمَ **قبل**
التغيير لتقول «سينتقل معه N براند» — وهذا مصدره.

الرقم من `family_brand_counts` نفسها التي يقرأها `has_group` (خريطةٌ واحدة
للشركة كلّها، بلا استعلامٍ لكل صفّ)؛ وحين تغيب الخريطة (سياقٌ لا يمرّ به
`get_serializer_context`) يُحسب استعلامٌ واحدٌ **مقيَّدٌ بالشركة**. ولا يُضاف
الحقل إلى عقد `view=lookup`: `ProductLookupSerializer` يسرد حقوله صراحةً،
فالعقد الضيّق لا يتّسع.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIRequestFactory

from inventory.models import Product
from inventory.serializers import ProductSerializer
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class FamilyBrandCountTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fbc_a", password="x")
        cls.tenant = create_company("شركة عدد البراندات", cls.owner)
        cls.other_owner = User.objects.create_user(username="fbc_b", password="x")
        cls.other_tenant = create_company("شركة عدد البراندات الأخرى", cls.other_owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── أدوات ──────────────────────────────────────────────────────────
    def _register(self, name, brand=None):
        payload = {"name_ar": name}
        if brand:
            payload["brand"] = brand
        res = self.client.post(PRODUCTS_URL, payload, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return res.json()

    def _add_brand(self, family_id, brand):
        res = self.client.post(
            f"{PRODUCTS_URL}add-brand/", {"family_id": family_id, "brand": brand},
            format="json", **self.hdr,
        )
        assert res.status_code in (200, 201), res.content[:300]
        return res.json()

    def _get(self, product_id, query=""):
        res = self.client.get(f"{PRODUCTS_URL}{product_id}/{query}", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()

    def _family_of(self, product):
        return Product.objects.get(pk=product["id"]).family_id

    # ── الحدّان الأساسيان ───────────────────────────────────────────────
    def test_retrieve_reports_every_brand_of_the_family(self):
        # البراند الأوّل في الإنشاء (وإلا «سمّى» أوّلُ add-brand الصفَّ الضمنيّ
        # بدل إنشاء صفٍّ جديد — `add_brand_to_family`).
        brand = self._register("إطار 205/55", brand="ميشلان")
        family_id = self._family_of(brand)
        self._add_brand(family_id, "تويو")
        self._add_brand(family_id, "بيريدجستون")

        assert self._get(brand["id"])["family_brand_count"] == 3

    def test_single_brand_product_reports_one(self):
        brand = self._register("بطارية 70A", brand="فارتا")
        assert self._get(brand["id"])["family_brand_count"] == 1

    def test_product_without_a_family_reports_one(self):
        # صفوف ما قبل #20 بلا أبٍ — براندٌ واحدٌ بذاته.
        legacy = Product.objects.create(
            tenant=self.tenant, sku="LEG-1", name_ar="منتجٌ قديم بلا أب",
        )
        assert self._get(legacy.pk)["family_brand_count"] == 1

    # ── عزل الشركة ─────────────────────────────────────────────────────
    def test_count_never_includes_another_companys_brand(self):
        brand = self._register("طابعة ليزر", brand="HP")
        family_id = self._family_of(brand)
        self._add_brand(family_id, "Canon")
        self._add_brand(family_id, "Epson")
        # صفٌّ دخيلٌ يشير إلى نفس الأب: الـFK لا يعرف الشركة، والمُسلسِل يجب أن يعرف.
        Product.objects.create(
            tenant=self.other_tenant, sku="OTHER-1", name_ar="دخيل", family_id=family_id,
        )

        assert self._get(brand["id"])["family_brand_count"] == 3

    def test_without_the_context_map_the_count_is_one_tenant_scoped_query(self):
        """الفرع الاحتياطيّ نفسه: بلا `family_brand_counts` يُعدّ استعلاماً واحداً بالشركة —
        ولو عدّ الأبَ كلَّه لظهر 4 بدل 3 (صفُّ الشركة الأخرى داخلٌ فيه)."""
        brand = self._register("مضخة مياه", brand="جراندفوس")
        family_id = self._family_of(brand)
        self._add_brand(family_id, "بيدرولو")
        self._add_brand(family_id, "ويرلو")
        Product.objects.create(
            tenant=self.other_tenant, sku="OTHER-2", name_ar="دخيل", family_id=family_id,
        )
        product = Product.objects.get(pk=brand["id"])

        request = APIRequestFactory().get("/", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        request.user = self.owner
        data = ProductSerializer(product, context={"request": request}).data

        assert data["family_brand_count"] == 3

    # ── العقد ──────────────────────────────────────────────────────────
    def test_lookup_contract_does_not_grow(self):
        """`ProductLookupSerializer` يسرد حقوله صراحةً — الحقل لا يتسرّب إلى منتقي
        المستندات (حمولتُه مقيسةٌ على 1490 منتجاً)."""
        brand = self._register("سلك كهرباء")
        res = self.client.get(PRODUCTS_URL, {"view": "lookup"}, **self.hdr)
        assert res.status_code == 200, res.content[:300]
        row = next(r for r in res.json() if r["id"] == brand["id"])
        assert "family_brand_count" not in row
