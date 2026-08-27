"""T-SUPSKU — رقم المنتج عند المورّد: جدول ربط لا حقل على المنتج.

مطابقة فواتير المورّد تجري برقم كتالوجه (מק"ט)، وهو ليس رقمنا. كان يُحشَر في
`Product.name_en` — ومعناه «اسم المنتج بالإنجليزية». الحشوة كانت **تعمل للبحث**
(`name_en` ضمن `search_fields`)، فالنقل يجب ألّا يفقد تلك القدرة.

الحقل الواحد على المنتج كان سيكذب أوّل مرّة يأتي فيها المنتج من مورّدَين —
والإطارات هي هذه الحالة. الجدول يحلّها، ويحرس ما يجب حراسته فعلاً: رقمٌ واحد
عند مورّدٍ واحد لا يشير إلى منتجين.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from inventory.models import Product, SupplierProduct
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class SupplierProductModelTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="supsku", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الأرقام", cls.user)
        cls.s1 = Partner.objects.create(
            tenant=cls.tenant, name="مورّد أوّل", partner_type="Supplier")
        cls.s2 = Partner.objects.create(
            tenant=cls.tenant, name="مورّد ثانٍ", partner_type="Supplier")
        cls.p1 = Product.objects.create(
            tenant=cls.tenant, sku="001313", name_ar="إطار 205/55",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.p2 = Product.objects.create(
            tenant=cls.tenant, sku="001314", name_ar="إطار 225/45",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def test_same_product_can_carry_a_code_from_each_supplier(self):
        """جوهر السبب في اختيار الجدول: المنتج يأتي من أكثر من مورّد."""
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=self.s1, product=self.p1,
            supplier_sku="3068.82")
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=self.s2, product=self.p1,
            supplier_sku="TY-205-55")
        assert self.p1.supplier_codes.count() == 2

    def test_one_supplier_may_carry_two_codes_for_the_same_product(self):
        """ترقيمٌ قديم وجديد عند المورّد نفسه — مقبول ومفيد."""
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=self.s1, product=self.p1,
            supplier_sku="3068.82")
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=self.s1, product=self.p1,
            supplier_sku="3068.82-OLD")
        assert self.p1.supplier_codes.filter(supplier=self.s1).count() == 2

    def test_one_code_at_one_supplier_cannot_mean_two_products(self):
        """الممنوع الوحيد — وإلا صارت مطابقة فاتورة المورّد تخميناً."""
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=self.s1, product=self.p1,
            supplier_sku="3068.82")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SupplierProduct.objects.create(
                    tenant=self.tenant, supplier=self.s1, product=self.p2,
                    supplier_sku="3068.82")


class SupplierProductApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="supskuapi", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الأرقام", cls.user)
        cls.other_user = User.objects.create_user(username="supskuother", password="x")
        cls.other = create_company("شركة أخرى", cls.other_user)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورّد الإطارات", partner_type="Supplier")
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون", partner_type="Customer")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="001313", name_ar="إطار 205/55",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.rival = Product.objects.create(
            tenant=cls.tenant, sku="001314", name_ar="إطار 225/45",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, **over):
        body = {
            "supplier": self.supplier.pk, "product": self.product.pk,
            "supplier_sku": "3068.82",
        }
        body.update(over)
        return self.client.post(
            "/api/inventory/supplier-products/", body, format="json", **self.headers)

    def test_create_and_filter_by_product(self):
        assert self._create().status_code == 201
        res = self.client.get(
            f"/api/inventory/supplier-products/?product={self.product.pk}",
            **self.headers)
        rows = res.json()
        rows = rows if isinstance(rows, list) else rows["results"]
        assert [r["supplier_sku"] for r in rows] == ["3068.82"]
        assert rows[0]["supplier_display_name"] == "مورّد الإطارات"

    def test_reverse_lookup_by_code(self):
        """«هذا الرقم — أيّ منتج؟» وهو سؤال مطابقة فاتورة المورّد نفسه."""
        self._create()
        res = self.client.get(
            "/api/inventory/supplier-products/?sku=3068.82", **self.headers)
        rows = res.json()
        rows = rows if isinstance(rows, list) else rows["results"]
        assert rows[0]["product"] == self.product.pk

    def test_duplicate_code_is_refused_by_naming_the_holder(self):
        """رسالةٌ تسمّي المنتج المالك — «قيد فريد مخروق» لا يعلّم أحداً شيئاً."""
        self._create()
        res = self._create(product=self.rival.pk)
        assert res.status_code == 400, res.content
        assert "إطار 205/55" in str(res.json())

    def test_a_customer_cannot_hold_supplier_codes(self):
        res = self._create(supplier=self.customer.pk)
        assert res.status_code == 400, res.content
        assert "ليس مورّداً" in str(res.json())

    def test_blank_code_is_refused(self):
        assert self._create(supplier_sku="   ").status_code == 400

    def test_rows_do_not_leak_across_tenants(self):
        self._create()
        self.client.force_authenticate(user=self.other_user)
        res = self.client.get(
            "/api/inventory/supplier-products/",
            HTTP_X_TENANT_ID=str(self.other.TenantID))
        rows = res.json()
        rows = rows if isinstance(rows, list) else rows["results"]
        assert rows == []


class ProductSearchBySupplierCodeTest(APITestCase):
    """البحث بالشاشات يجد المنتج برقم مورّده — وهو الغرض العملي كلّه."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="supskusearch", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة البحث", cls.user)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورّد الإطارات", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="001313", name_ar="إطار 205/55",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.noise = Product.objects.create(
            tenant=cls.tenant, sku="001314", name_ar="إطار 225/45",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        SupplierProduct.objects.create(
            tenant=cls.tenant, supplier=cls.supplier, product=cls.product,
            supplier_sku="3068.82", supplier_name="TYRE 205/55 R16")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _search(self, term):
        res = self.client.get(
            f"/api/inventory/products/?search={term}", **self.headers)
        assert res.status_code == 200, res.content
        rows = res.json()
        rows = rows if isinstance(rows, list) else rows["results"]
        return [r["sku"] for r in rows]

    def test_supplier_code_finds_the_product(self):
        assert self._search("3068.82") == ["001313"]

    def test_supplier_own_item_name_finds_it_too(self):
        assert self._search("TYRE 205/55") == ["001313"]

    def test_our_own_sku_still_works(self):
        assert self._search("001314") == ["001314"]

    def test_two_codes_for_one_product_do_not_duplicate_the_row(self):
        """عبور علاقةٍ متعدّدة يكرّر الصفوف ما لم يُميَّز — والبحث يميّز."""
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=self.supplier, product=self.product,
            supplier_sku="3068.82-OLD")
        assert self._search("3068.82") == ["001313"]
