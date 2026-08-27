"""اختبارات أدوات المساعد الذكي — صحة الأرقام والعزل الإلزامي بين الشركات.

الأدوات قراءة فقط ومقفولة على شركة المستخدم. نُنشئ فواتير بحالة «مرحّلة»
مباشرة (بلا ترحيل كامل) لأن الأدوات تقرأ status/invoice_kind/grand_total فقط.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from core.assistant_tools import (
    purchases_from_supplier,
    run_tool,
    sales_to_customer,
    search_products,
)
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _posted_invoice(tenant, cur, party, *, kind, total, paid="0", when="2026-06-15", num="X"):
    return SalesInvoice.objects.create(
        tenant=tenant, invoice_number=num, customer=party, currency=cur,
        invoice_date=when, invoice_kind=kind, status=SalesInvoice.STATUS_POSTED,
        grand_total=Decimal(total), amount_paid=Decimal(paid),
    )


@pytest.fixture
def env():
    owner = User.objects.create_user(username="asst", password="x", is_superuser=True)
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")

    a = create_company("شركة أ", owner)
    b = create_company("شركة ب", owner)

    # شركة أ: عميل أشرف، مورد سامي، منتج إطار
    ashraf = Partner.objects.create(tenant=a, name="أشرف عجل", partner_type="Customer")
    sami = Partner.objects.create(tenant=a, name="سامي للتوريد", partner_type="Supplier")
    Product.objects.create(tenant=a, sku="TIRE-185", name_ar="إطار 185/65/14",
                           quantity_on_hand=Decimal("40"), avg_cost=Decimal("120"))

    _posted_invoice(a, cur, ashraf, kind="sale", total="500", paid="300", num="S-1")
    _posted_invoice(a, cur, ashraf, kind="sale", total="200", num="S-2")
    _posted_invoice(a, cur, ashraf, kind="sale_return", total="100", num="SR-1")
    _posted_invoice(a, cur, sami, kind="purchase", total="700", paid="700", num="P-1")

    # شركة ب: بيانات يجب ألا تتسرّب لأ
    ashraf_b = Partner.objects.create(tenant=b, name="أشرف عجل", partner_type="Customer")
    Product.objects.create(tenant=b, sku="TIRE-185", name_ar="إطار 185/65/14",
                           quantity_on_hand=Decimal("999"), avg_cost=Decimal("1"))
    _posted_invoice(b, cur, ashraf_b, kind="sale", total="8888", num="S-B1")

    return owner, cur, a, b


def test_search_products_returns_on_hand(env):
    _, _, a, _ = env
    res = search_products(a, query="إطار")
    assert res["count"] == 1
    assert res["matches"][0]["quantity_on_hand"] == 40.0
    assert res["matches"][0]["inventory_value"] == 4800.0  # 40 × 120


def test_sales_to_customer_net_of_returns(env):
    _, _, a, _ = env
    res = sales_to_customer(a, customer="أشرف")
    assert res["customer"] == "أشرف عجل"
    assert res["gross_total"] == 700.0      # 500 + 200
    assert res["returns_total"] == 100.0
    assert res["net_total"] == 600.0
    assert res["amount_paid"] == 300.0
    assert res["outstanding"] == 300.0      # 600 − 300
    assert res["invoice_count"] == 2


def test_purchases_from_supplier(env):
    _, _, a, _ = env
    res = purchases_from_supplier(a, supplier="سامي")
    assert res["supplier"] == "سامي للتوريد"
    assert res["net_total"] == 700.0
    assert res["outstanding"] == 0.0


def test_date_filter_scopes_range(env):
    _, _, a, _ = env
    res = sales_to_customer(a, customer="أشرف", date_from="2027-01-01")
    assert res["gross_total"] == 0.0  # لا فواتير بعد 2027


def test_run_tool_is_tenant_scoped(env):
    """الأداة عبر run_tool محصورة بشركة tenant المُمرَّرة — لا تسريب من شركة ب."""
    _, _, a, _ = env
    res = run_tool("search_products", {"query": "إطار"}, a)
    # يرى كمية شركة أ (40) لا شركة ب (999)
    assert res["count"] == 1
    assert res["matches"][0]["quantity_on_hand"] == 40.0

    sres = run_tool("sales_to_customer", {"customer": "أشرف"}, a)
    assert sres["gross_total"] == 700.0  # لا 8888 من شركة ب


def test_unknown_tool_returns_error(env):
    _, _, a, _ = env
    res = run_tool("drop_everything", {}, a)
    assert "error" in res
