"""ربط واجهتي «عرض السعر» (كرت الزبون ↔ واجهة العروض) + أولوية التسعير:
- إنشاء عرض سعر (واجهة العروض) يملأ عرض سعر كرت الزبون إن كان فارغاً (لا يكتب فوق الموجود).
- مُحلِّل سعر البيع يقدّم عرض سعر «واجهة العروض» (SalesQuotation) على عرض كرت الزبون.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.services import create_fiscal_year
from core.pricing import resolve_sales_price
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerProductQuote
from sales.serializers import SalesQuotationSerializer
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="quolink", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الربط", owner)
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    product = Product.objects.create(
        tenant=tenant, sku="QL-1", name_ar="صنف", quantity_on_hand=10, avg_cost=50)
    return tenant, ils, customer, product


def _make_quote(tenant, customer, product, price):
    ser = SalesQuotationSerializer(data={
        "customer": customer.id, "quotation_date": "2026-06-20",
        "lines": [{"product": product.id, "quantity": "1", "unit_price": str(price)}],
    })
    ser.is_valid(raise_exception=True)
    return ser.save(tenant=tenant, created_by=None)


def test_quotation_backfills_customer_card_when_empty(env):
    tenant, _ils, customer, product = env
    _make_quote(tenant, customer, product, 90)
    q = CustomerProductQuote.objects.get(tenant=tenant, customer=customer, product=product)
    assert Decimal(q.unit_price) == Decimal("90")


def test_quotation_does_not_overwrite_existing_customer_card(env):
    tenant, _ils, customer, product = env
    CustomerProductQuote.objects.create(
        tenant=tenant, customer=customer, product=product, unit_price=Decimal("70"))
    _make_quote(tenant, customer, product, 90)
    q = CustomerProductQuote.objects.get(tenant=tenant, customer=customer, product=product)
    assert Decimal(q.unit_price) == Decimal("70")  # لم يُكتب فوق قيمة كرت الزبون


def test_customer_price_list_includes_sales_quotation(env):
    tenant, _ils, customer, product = env
    _make_quote(tenant, customer, product, 90)
    # نحذف عرض كرت الزبون الذي عبّأه الإنشاء، لعزل مصدر SalesQuotation في القائمة.
    CustomerProductQuote.objects.filter(
        tenant=tenant, customer=customer, product=product).delete()
    from sales.services import customer_price_list
    rows = customer_price_list(tenant_id=tenant.TenantID, customer_id=customer.id)
    row = next(r for r in rows if r["product_id"] == product.id)
    assert row["price"] is not None and Decimal(row["price"]) == Decimal("90")
    assert row["source"] == "quote"  # فيظهر شريحة «عرض سعر» في خيارات الفاتورة


def test_resolver_prefers_sales_quotation_over_customer_card(env):
    tenant, _ils, customer, product = env
    CustomerProductQuote.objects.create(
        tenant=tenant, customer=customer, product=product, unit_price=Decimal("70"))
    _make_quote(tenant, customer, product, 90)
    res = resolve_sales_price(
        tenant_id=tenant.TenantID, product_id=product.id, customer_id=customer.id)
    assert res["source"]["document_type"] == "SALES_QUOTATION"
    assert Decimal(res["unit_price"]) == Decimal("90")
    assert res["source"].get("document_number")  # رقم العرض متاح للربط
