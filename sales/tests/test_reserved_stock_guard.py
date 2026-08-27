"""حجز الطلبية يمنع بيع نفس الكمية لزبون آخر (T-RESERVEGUARD).

الثغرة التي يحرسها هذا الملف: الحجز كان **عرضاً فقط** — طلبية مؤكَّدة تحجز
الكمية في الشاشات، لكن فاتورة بيع لزبون آخر كانت تُرحَّل وتخصم المخزون بلا
اعتراض، فتنقلب الطلبية المحجوزة إلى وعد لا يمكن الوفاء به.

القواعد:
1. الحجز يمنع **الزبون الآخر** فقط — صاحب الطلبية يسحب حجزه بلا عائق.
2. الحجز المنتهي/الملغى/المحوَّل لا يمنع شيئاً (نفس مصدر `reserved_quantity_map`).
3. المفتاح `block_reserved_stock_sale` يوقف الحارس عند إطفائه.
4. «تقرير المحجوزات» يعرض نفس الحجوزات التي يحرسها الحارس — مصدر واحد.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    SalesSettings,
)
from sales.services import post_sales_invoice, reserved_stock_rows
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="reserveguard", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الحجز", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-R", name="ذمم", account_type="Asset", is_active=True)
    holder = Partner.objects.create(
        tenant=tenant, name="صاحب الطلبية", partner_type="Customer", linked_account=ar)
    other = Partner.objects.create(
        tenant=tenant, name="زبون آخر", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="RSV-1", name_ar="منتج محجوز",
        quantity_on_hand=Decimal("10"), avg_cost=Decimal("1"))
    return tenant, holder, other, product


def _order(tenant, customer, product, *, qty="8", number="SO-RSV-1",
           status=SalesOrder.STATUS_CONFIRMED, reserved_until=None):
    order = SalesOrder.objects.create(
        tenant=tenant, order_number=number, customer=customer,
        order_date=date(2026, 6, 1), currency=tenant._test_currency,
        status=status,
        reserved_until=reserved_until if reserved_until is not None
        else date.today() + timedelta(days=7),
    )
    SalesOrderLine.objects.create(
        tenant=tenant, order=order, product=product,
        quantity=Decimal(qty), unit_price=Decimal("10"), line_total=Decimal(qty) * 10)
    return order


def _invoice(tenant, customer, product, *, qty="5", number="INV-RSV-1"):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(qty), unit_price=Decimal("20"))
    return inv


def test_reserved_quantity_blocks_an_invoice_for_another_customer(env):
    tenant, holder, other, product = env
    _order(tenant, holder, product, qty="8")
    inv = _invoice(tenant, other, product, qty="5")
    with pytest.raises(ValidationError) as exc:
        post_sales_invoice(inv)
    assert "SO-RSV-1" in str(exc.value)
    inv.refresh_from_db()
    assert inv.status != SalesInvoice.STATUS_POSTED


def test_reservation_holder_may_invoice_its_own_reserved_quantity(env):
    tenant, holder, _other, product = env
    _order(tenant, holder, product, qty="8")
    inv = _invoice(tenant, holder, product, qty="8", number="INV-RSV-OWN")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_free_quantity_beyond_the_reservation_still_sells(env):
    tenant, holder, other, product = env
    _order(tenant, holder, product, qty="8")
    inv = _invoice(tenant, other, product, qty="2", number="INV-RSV-FREE")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_expired_reservation_does_not_block(env):
    tenant, holder, other, product = env
    _order(tenant, holder, product, qty="8",
           reserved_until=date.today() - timedelta(days=1))
    inv = _invoice(tenant, other, product, qty="5", number="INV-RSV-EXP")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_cancelled_order_does_not_block(env):
    tenant, holder, other, product = env
    _order(tenant, holder, product, qty="8", status=SalesOrder.STATUS_CANCELLED)
    inv = _invoice(tenant, other, product, qty="5", number="INV-RSV-CAN")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_guard_is_disabled_by_the_company_setting(env):
    tenant, holder, other, product = env
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"block_reserved_stock_sale": False})
    _order(tenant, holder, product, qty="8")
    inv = _invoice(tenant, other, product, qty="5", number="INV-RSV-OFF")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


# ── تقرير المحجوزات ────────────────────────────────────────────────────
def test_reserved_stock_report_lists_the_active_reservation(env):
    tenant, holder, _other, product = env
    _order(tenant, holder, product, qty="8")
    rows = reserved_stock_rows(tenant.TenantID)
    assert len(rows) == 1
    row = rows[0]
    assert row["order_number"] == "SO-RSV-1"
    assert row["customer_id"] == holder.pk
    assert row["product_id"] == product.pk
    assert Decimal(row["quantity"]) == Decimal("8.000")
    assert Decimal(row["quantity_on_hand"]) == Decimal("10.000")
    assert Decimal(row["available_quantity"]) == Decimal("2.000")


def test_reserved_stock_report_skips_expired_reservations(env):
    tenant, holder, _other, product = env
    _order(tenant, holder, product, qty="8",
           reserved_until=date.today() - timedelta(days=1))
    assert reserved_stock_rows(tenant.TenantID) == []


def test_reserved_stock_report_filters_by_reservation_end_date(env):
    """التقرير بلا فلترة زمنية يخلط ما ينتهي غداً بما ينتهي بعد شهر — فلترة
    «الحجز حتى» تحصر النافذة على نفس مصدر الحارس بلا نسخة ثانية منه."""
    tenant, holder, other, product = env
    soon = _order(tenant, holder, product, qty="2", number="SO-RSV-SOON",
                  reserved_until=date.today() + timedelta(days=1))
    later = _order(tenant, other, product, qty="3", number="SO-RSV-LATER",
                   reserved_until=date.today() + timedelta(days=30))

    within = reserved_stock_rows(
        tenant.TenantID, date_to=date.today() + timedelta(days=7))
    assert [r["order_number"] for r in within] == [soon.order_number]

    beyond = reserved_stock_rows(
        tenant.TenantID, date_from=date.today() + timedelta(days=7))
    assert [r["order_number"] for r in beyond] == [later.order_number]


def test_reserved_stock_report_endpoint(env, client):
    tenant, holder, _other, product = env
    _order(tenant, holder, product, qty="8")
    user = User.objects.get(username="reserveguard")
    client.force_login(user)
    response = client.get(
        "/api/sales/reports/reserved-stock/",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert response.status_code == 200
    payload = response.json()
    assert [r["order_number"] for r in payload] == ["SO-RSV-1"]
    assert payload[0]["customer_name"] == "صاحب الطلبية"


def test_reserved_stock_report_endpoint_accepts_a_date_window(env, client):
    tenant, holder, other, product = env
    _order(tenant, holder, product, qty="2", number="SO-RSV-SOON",
           reserved_until=date.today() + timedelta(days=1))
    _order(tenant, other, product, qty="3", number="SO-RSV-LATER",
           reserved_until=date.today() + timedelta(days=30))
    client.force_login(User.objects.get(username="reserveguard"))
    response = client.get(
        "/api/sales/reports/reserved-stock/",
        {"to": (date.today() + timedelta(days=7)).isoformat()},
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert response.status_code == 200
    assert [r["order_number"] for r in response.json()] == ["SO-RSV-SOON"]
