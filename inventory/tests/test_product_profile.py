"""FEAT-3 — Product profile: KPIs, stock ledger (running balance reconciles to
on-hand), and linked invoices with clickable document references.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from inventory.services import (
    product_cost_breakdown,
    product_linked_invoices,
    product_profile,
    product_stock_ledger,
    record_stock_movement,
)
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="pp", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة بطاقة الصنف", owner)
    sup = Partner.objects.create(tenant=tenant, name="مورد", partner_type="Supplier")
    product = Product.objects.create(
        tenant=tenant, sku="PP-1", name_ar="صنف", quantity_on_hand=0, avg_cost=Decimal("0"))
    return tenant, ils, sup, product


def test_stock_ledger_running_balance_reconciles_to_on_hand(env):
    tenant, _ils, _sup, product = env
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-06-01", tenant=tenant)
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("3"),
        movement_date="2026-06-02", tenant=tenant)
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("5"),
        unit_cost=Decimal("6"), movement_date="2026-06-03", tenant=tenant)

    led = product_stock_ledger(tenant_id=tenant.TenantID, product_id=product.id)
    assert led["count"] == 3
    balances = [Decimal(r["running_balance"]) for r in led["results"]]
    assert balances == [Decimal("10"), Decimal("7"), Decimal("12")]
    # in/out columns
    assert led["results"][0]["qty_in"] == "10.0000"
    assert led["results"][1]["qty_out"] == "3.0000"
    # final running balance == current on-hand (A4)
    product.refresh_from_db()
    assert balances[-1] == Decimal(str(product.quantity_on_hand))


def test_profile_kpis(env):
    tenant, ils, sup, product = env
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-06-01", tenant=tenant)
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="P-1", partner=sup, currency=ils,
        invoice_date="2026-06-01", is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="صنف",
        quantity=Decimal("10"), unit_price=Decimal("5"), total_price=Decimal("50"))

    prof = product_profile(tenant_id=tenant.TenantID, product_id=product.id)
    assert prof["sku"] == "PP-1"
    assert Decimal(prof["quantity_on_hand"]) == Decimal("10")
    assert Decimal(prof["inventory_valuation"]) == Decimal("50.00")
    assert Decimal(prof["purchased_qty"]) == Decimal("10")
    assert Decimal(prof["purchased_value"]) == Decimal("50")


def test_linked_invoices_have_clickable_refs(env):
    tenant, ils, sup, product = env
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="P-1", partner=sup, currency=ils,
        invoice_date="2026-06-01", is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="صنف",
        quantity=Decimal("1"), unit_price=Decimal("5"), total_price=Decimal("5"))

    links = product_linked_invoices(tenant_id=tenant.TenantID, product_id=product.id)
    assert len(links) == 1
    assert links[0]["document_type"] == "PURCHASE_INVOICE"
    assert links[0]["document_id"] == inv.id
    assert links[0]["document_number"] == "P-1"


def test_cost_breakdown_weighted_avg_ignores_sold_qty(env):
    """واجهة تكلفة المنتجات: سعر وحدة لكل فاتورة، ثم متوسط مرجّح بكمية الشراء —
    المقام إجمالي المشترى (لا الكمية الحالية)، فبيع جزء لا يضخّم التكلفة."""
    tenant, ils, sup, product = env
    # فاتورة 1: 10 وحدات بإجمالي 1000 → سعر وحدة 100
    inv1 = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="P-1", partner=sup, currency=ils,
        invoice_date="2026-06-01", is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=inv1, product=product, name="صنف",
        quantity=Decimal("10"), unit_price=Decimal("100"), total_price=Decimal("1000"))
    # فاتورة 2: 30 وحدة بإجمالي 2800 → سعر وحدة 93.3333
    inv2 = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="P-2", partner=sup, currency=ils,
        invoice_date="2026-06-05", is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=inv2, product=product, name="صنف",
        quantity=Decimal("30"), unit_price=Decimal("93.3333"), total_price=Decimal("2800"))

    res = product_cost_breakdown(tenant_id=tenant.TenantID, product_id=product.id)
    assert res["invoice_count"] == 2
    assert res["invoices"][0]["unit_cost"] == "100.0000"
    assert res["invoices"][0]["invoice_cost"] == "1000.00"
    assert res["invoices"][1]["unit_cost"] == "93.3333"
    assert Decimal(res["total_purchased_qty"]) == Decimal("40")
    # متوسط مرجّح = (1000 + 2800) / 40 = 95 — لا 3800/13 ولا متوسط بسيط 96.67
    assert Decimal(res["average_cost"]) == Decimal("95.0000")


def test_cost_breakdown_landed_cost_priority(env):
    """تكلفة الفاتورة تأخذ landed cost حين توفّره (السعر النازل الحقيقي)."""
    tenant, ils, sup, product = env
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="P-L", partner=sup, currency=ils,
        invoice_date="2026-06-01", is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="صنف",
        quantity=Decimal("10"), unit_price=Decimal("100"), total_price=Decimal("1000"),
        landed_unit_price_ils=Decimal("120"))

    res = product_cost_breakdown(tenant_id=tenant.TenantID, product_id=product.id)
    # 120 × 10 = 1200 (landed) بدل 1000 (total_price)
    assert res["invoices"][0]["invoice_cost"] == "1200.00"
    assert res["invoices"][0]["unit_cost"] == "120.0000"
    assert Decimal(res["average_cost"]) == Decimal("120.0000")


class ProductProfileEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ppe", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة بطاقة", cls.user)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PPE-1", name_ar="صنف", quantity_on_hand=0, avg_cost=Decimal("0"))
        record_stock_movement(
            product=cls.product, movement_type="IN", quantity=Decimal("4"),
            unit_cost=Decimal("2"), movement_date="2026-06-01", tenant=cls.tenant)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_endpoints(self):
        r = self.client.get(f"/api/inventory/products/{self.product.id}/profile/", **self._auth())
        assert r.status_code == 200, r.content
        assert Decimal(r.json()["quantity_on_hand"]) == Decimal("4")

        r = self.client.get(f"/api/inventory/products/{self.product.id}/stock-ledger/", **self._auth())
        assert r.status_code == 200, r.content
        assert r.json()["count"] == 1
        assert Decimal(r.json()["results"][0]["running_balance"]) == Decimal("4")

        r = self.client.get(f"/api/inventory/products/{self.product.id}/cost-breakdown/", **self._auth())
        assert r.status_code == 200, r.content
        body = r.json()
        assert "invoices" in body and "average_cost" in body
