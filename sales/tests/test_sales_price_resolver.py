"""FEAT-2 — sales line customer-based auto-pricing via the shared PriceResolver.

Covers: last price the selected customer paid, fallback to product default
selling price (price tier), blank when neither, currency normalization, and
the resolve-price endpoint.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from core.pricing import PriceStrategy, resolve_sales_price
from inventory.models import Product, ProductPriceTier
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="spr", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    usd = Currency.objects.create(Code="USD", Name="دولار")
    tenant = create_company("شركة تسعير البيع", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-S", name="ذمم", account_type="Asset", is_active=True)
    c1 = Partner.objects.create(tenant=tenant, name="عميل1", partner_type="Customer", linked_account=ar)
    c2 = Partner.objects.create(tenant=tenant, name="عميل2", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="SPR-1", name_ar="صنف", quantity_on_hand=1000, avg_cost=Decimal("10"))
    return tenant, ils, usd, c1, c2, product


def _post(tenant, cur, customer, product, *, number, date, price, rate="1"):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=cur, invoice_date=date, exchange_rate=Decimal(rate),
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(str(price)))
    post_sales_invoice(inv)
    return inv


def test_last_price_for_this_customer(env):
    tenant, ils, _usd, c1, c2, product = env
    _post(tenant, ils, c1, product, number="S-1", date="2026-06-10", price=100)
    _post(tenant, ils, c2, product, number="S-2", date="2026-06-15", price=130)

    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id)
    assert Decimal(data["unit_price"]) == Decimal("100.0000")
    assert data["strategy_used"] == PriceStrategy.LAST_SALE_TO_CUSTOMER
    assert data["source"]["document_number"] == "S-1"


def test_new_customer_falls_back_to_default_selling_price(env):
    tenant, ils, _usd, c1, c2, product = env
    # c2 bought it, but we resolve for c1 (no history) → tier default.
    _post(tenant, ils, c2, product, number="S-2", date="2026-06-15", price=130)
    ProductPriceTier.objects.create(
        product=product, tier_type=ProductPriceTier.TIER_TYPE_SALE,
        tier_number=1, price=Decimal("199"), currency=ils, tax_inclusive=False)

    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id,
        target_currency_id=ils.CurrencyID)
    assert Decimal(data["unit_price"]) == Decimal("199.0000")
    assert data["strategy_used"] == PriceStrategy.DEFAULT


def test_blank_when_no_history_and_no_default(env):
    tenant, _ils, _usd, c1, _c2, product = env
    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id)
    assert data["unit_price"] is None
    assert data["strategy_used"] is None


def test_no_customer_means_no_history_match(env):
    # FEAT-2 keys on the selected customer; without one, no per-customer price.
    tenant, ils, _usd, c1, _c2, product = env
    _post(tenant, ils, c1, product, number="S-1", date="2026-06-10", price=100)
    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=None)
    assert data["unit_price"] is None


def test_currency_normalized_to_target(env):
    tenant, _ils, usd, c1, _c2, product = env
    # Customer's last buy was in USD at rate 3.6 → 10 USD = 36 base; target base.
    _post(tenant, usd, c1, product, number="S-USD", date="2026-06-10", price=10, rate="3.6")
    data = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id,
        target_exchange_rate=Decimal("1"))
    assert Decimal(data["unit_price"]) == Decimal("36.0000")


class SalesPriceEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="spre", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة منفذ بيع", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-SE", name="ذمم", account_type="Asset", is_active=True)
        cls.c1 = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer", linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SPRE-1", name_ar="صنف", quantity_on_hand=100, avg_cost=Decimal("5"))
        _post(cls.tenant, cls.ils, cls.c1, cls.product, number="S-1", date="2026-06-10", price=77)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_endpoint_resolves_customer_last_price(self):
        res = self.client.get(
            f"/api/sales/invoices/resolve-price/?product={self.product.id}&customer={self.c1.id}",
            **self._auth())
        assert res.status_code == 200, res.content
        assert Decimal(res.json()["unit_price"]) == Decimal("77.0000")
