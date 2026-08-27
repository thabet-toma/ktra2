"""THA-128 — حركات المخزون المرتبطة بالشريك، داخل تبويب «المال» في كرته.

الهدف القابل للتحقق:
- `/api/partners/<id>/stock-movements/` يعيد حركات هذا الشريك وحدها، مجمَّعةً
  تحت المستند المسبِّب (النوع + المعرّف) الذي يحملانه أصلاً في `StockMovement`.
- **العزل**: حركة شركة أخرى لا تظهر ولو تطابق معرّف الشريك — العدد تسريبٌ أيضاً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class PartnerStockMovementsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="psm", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة حركات الشريك", cls.user)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الحركات", partner_type="Customer")
        cls.product = Product.objects.create(
            tenant=cls.tenant, name_ar="منتج الحركات", sku="SKU-PSM")

        # شركة أخرى بشريكها ومنتجها — لإثبات العزل.
        cls.other_user = User.objects.create_user(username="psm2", password="x")
        cls.other_tenant = create_company("شركة أخرى", cls.other_user)
        cls.other_partner = Partner.objects.create(
            tenant=cls.other_tenant, name="عميل غريب", partner_type="Customer")
        cls.other_product = Product.objects.create(
            tenant=cls.other_tenant, name_ar="منتج غريب", sku="SKU-OTHER")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _movement(self, *, tenant, product, partner, ref_type, ref_id, qty, after):
        return StockMovement.objects.create(
            tenant=tenant, product=product, partner=partner,
            movement_type="OUT", quantity=Decimal(str(qty)),
            reference_type=ref_type, reference_id=ref_id,
            movement_date="2026-06-01", quantity_after=Decimal(str(after)))

    def test_returns_only_this_partners_movements_grouped_by_document(self):
        self._movement(tenant=self.tenant, product=self.product, partner=self.customer,
                       ref_type="SALE", ref_id=11, qty=2, after=8)
        self._movement(tenant=self.tenant, product=self.product, partner=self.customer,
                       ref_type="SALE", ref_id=11, qty=3, after=5)
        self._movement(tenant=self.tenant, product=self.product, partner=self.customer,
                       ref_type="DELIVERY_NOTE", ref_id=4, qty=1, after=4)
        # حركة بلا شريك في الشركة نفسها — ليست حركته.
        self._movement(tenant=self.tenant, product=self.product, partner=None,
                       ref_type="SALE", ref_id=99, qty=1, after=3)

        res = self.client.get(
            f"/api/partners/{self.customer.id}/stock-movements/", **self._auth())
        assert res.status_code == 200, res.content
        groups = res.json()["results"]
        assert [(g["reference_type"], g["reference_id"], len(g["movements"]))
                for g in groups] == [("DELIVERY_NOTE", 4, 1), ("SALE", 11, 2)]

    def test_other_tenants_movement_never_appears(self):
        self._movement(tenant=self.tenant, product=self.product, partner=self.customer,
                       ref_type="SALE", ref_id=11, qty=2, after=8)
        self._movement(tenant=self.other_tenant, product=self.other_product,
                       partner=self.other_partner, ref_type="SALE", ref_id=11,
                       qty=7, after=1)

        res = self.client.get(
            f"/api/partners/{self.customer.id}/stock-movements/", **self._auth())
        groups = res.json()["results"]
        assert res.json()["count"] == 1
        assert len(groups) == 1 and len(groups[0]["movements"]) == 1
        assert Decimal(groups[0]["movements"][0]["qty_out"]) == Decimal("2")

    def test_other_tenants_partner_is_not_reachable(self):
        res = self.client.get(
            f"/api/partners/{self.other_partner.id}/stock-movements/", **self._auth())
        assert res.status_code == 404, res.content
