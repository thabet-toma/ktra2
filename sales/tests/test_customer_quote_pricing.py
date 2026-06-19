"""DEF-004/005 — per-customer manual quote ("عرض السعر") + resolver priority.

Priority matrix (DEF-005):
  purchased + quote  → last-invoice price wins (quote ignored)
  purchased only     → last-invoice price
  quote only         → quote price
  neither            → blank (or tier default)
Plus the customer-price-list endpoint (catalog + save).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from core.pricing import PriceStrategy, resolve_sales_price
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerProductQuote, SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="cqp", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة عرض السعر", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-Q", name="ذمم", account_type="Asset", is_active=True)
    c1 = Partner.objects.create(tenant=tenant, name="عميل1", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="CQP-1", name_ar="صنف", quantity_on_hand=1000, avg_cost=Decimal("10"))
    return tenant, ils, c1, product


def _post(tenant, cur, customer, product, *, number, date, price):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=cur, invoice_date=date, exchange_rate=Decimal("1"),
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(str(price)))
    post_sales_invoice(inv)
    return inv


def test_quote_only_uses_manual_quote(env):
    tenant, _ils, c1, product = env
    CustomerProductQuote.objects.create(
        tenant=tenant, customer=c1, product=product, unit_price=Decimal("85"))
    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id)
    assert Decimal(data["unit_price"]) == Decimal("85.0000")
    assert data["source"]["document_type"] == "CUSTOMER_QUOTE"
    assert data["strategy_used"] == PriceStrategy.DEFAULT


def test_last_invoice_beats_quote_for_purchased(env):
    # DEF-005: even when a manual quote exists, the last invoice price wins.
    tenant, ils, c1, product = env
    CustomerProductQuote.objects.create(
        tenant=tenant, customer=c1, product=product, unit_price=Decimal("85"))
    _post(tenant, ils, c1, product, number="S-1", date="2026-06-10", price=120)
    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id)
    assert Decimal(data["unit_price"]) == Decimal("120.0000")
    assert data["source"]["document_type"] == "SALES_INVOICE"


def test_neither_is_blank(env):
    tenant, _ils, c1, product = env
    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id)
    assert data["unit_price"] is None


class CustomerPriceListEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cple", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة قائمة الأسعار", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-CPL", name="ذمم", account_type="Asset", is_active=True)
        cls.c1 = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer", linked_account=cls.ar)
        cls.bought = Product.objects.create(
            tenant=cls.tenant, sku="CPL-B", name_ar="مشترى", quantity_on_hand=100, avg_cost=Decimal("5"))
        cls.fresh = Product.objects.create(
            tenant=cls.tenant, sku="CPL-F", name_ar="جديد", quantity_on_hand=100, avg_cost=Decimal("5"))
        _post(cls.tenant, cls.ils, cls.c1, cls.bought, number="S-1", date="2026-06-10", price=77)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_list_marks_source_and_editability(self):
        res = self.client.get(
            f"/api/sales/customer-price-list/?customer={self.c1.id}", **self._auth())
        assert res.status_code == 200, res.content
        by_id = {r["product_id"]: r for r in res.json()}
        assert by_id[self.bought.id]["source"] == "last_invoice"
        assert by_id[self.bought.id]["editable"] is False
        assert Decimal(by_id[self.bought.id]["price"]) == Decimal("77.0000")
        assert by_id[self.fresh.id]["source"] == "quote"
        assert by_id[self.fresh.id]["editable"] is True
        assert by_id[self.fresh.id]["price"] is None

    def test_save_persists_quote_and_resolver_uses_it(self):
        res = self.client.post(
            "/api/sales/customer-price-list/save/",
            {"customer": self.c1.id, "entries": [{"product": self.fresh.id, "unit_price": "42.5"}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["saved"] == 1
        # persisted + reload shows it
        res2 = self.client.get(
            f"/api/sales/customer-price-list/?customer={self.c1.id}", **self._auth())
        by_id = {r["product_id"]: r for r in res2.json()}
        assert Decimal(by_id[self.fresh.id]["price"]) == Decimal("42.5000")
        # resolver falls back to the quote for the never-purchased product
        data = resolve_sales_price(
            tenant_id=self.tenant.TenantID, product_id=self.fresh.id, customer_id=self.c1.id)
        assert Decimal(data["unit_price"]) == Decimal("42.5000")
        assert data["source"]["document_type"] == "CUSTOMER_QUOTE"

    def test_save_empty_deletes_quote(self):
        CustomerProductQuote.objects.create(
            tenant=self.tenant, customer=self.c1, product=self.fresh, unit_price=Decimal("9"))
        res = self.client.post(
            "/api/sales/customer-price-list/save/",
            {"customer": self.c1.id, "entries": [{"product": self.fresh.id, "unit_price": ""}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert not CustomerProductQuote.objects.filter(
            tenant=self.tenant, customer=self.c1, product=self.fresh).exists()
