"""task18 DEF-C2 — آخر سعر بيع لمنتج (عام واختيارياً لعميل)."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import last_sale_price, post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="lp", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة الأسعار", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-L", name="ذمم", account_type="Asset", is_active=True)
    c1 = Partner.objects.create(tenant=tenant, name="عميل1", partner_type="Customer", linked_account=ar)
    c2 = Partner.objects.create(tenant=tenant, name="عميل2", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="LP-1", name_ar="منتج", quantity_on_hand=100, avg_cost=Decimal("10"))
    return tenant, cur, c1, c2, product


def _post(tenant, cur, customer, product, *, number, date, price):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=cur, invoice_date=date,
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(str(price)))
    post_sales_invoice(inv)
    return inv


def test_general_last_price_is_most_recent(env):
    tenant, cur, c1, c2, product = env
    _post(tenant, cur, c1, product, number="L-1", date="2026-06-10", price=100)
    _post(tenant, cur, c2, product, number="L-2", date="2026-06-15", price=130)

    data = last_sale_price(tenant_id=tenant.TenantID, product_id=product.id)
    assert Decimal(data["unit_price"]) == Decimal("130.0000")
    assert data["invoice_number"] == "L-2"


def test_per_customer_last_price_preferred(env):
    tenant, cur, c1, c2, product = env
    _post(tenant, cur, c1, product, number="L-1", date="2026-06-10", price=100)
    _post(tenant, cur, c2, product, number="L-2", date="2026-06-15", price=130)

    data = last_sale_price(tenant_id=tenant.TenantID, product_id=product.id, customer_id=c1.id)
    assert Decimal(data["unit_price"]) == Decimal("100.0000")
    assert data["invoice_number"] == "L-1"


def test_no_history_returns_none(env):
    tenant, cur, c1, c2, product = env
    data = last_sale_price(tenant_id=tenant.TenantID, product_id=product.id)
    assert data["unit_price"] is None
