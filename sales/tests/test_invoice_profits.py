"""task18 DEF-C4 — تقرير أرباح الفواتير.

الربح = الإيراد (صافي البنود قبل الضريبة) − التكلفة (مجموع total_cost لحركات
مخزون البيع المسجَّلة وقت الترحيل). محصور بالشركة وبفواتير البيع المرحَّلة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings, invoice_profits, post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="profit", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة الأرباح", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-P", name="ذمم العميل", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل الأرباح", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="PR-1", name_ar="صنف ربح", quantity_on_hand=100, avg_cost=Decimal("10"))
    # حسابا التكلفة والمخزون مطلوبان لترحيل فاتورة تخصم المخزون (قيد COGS).
    cogs_acc = Account.objects.create(
        tenant=tenant, code="5101-P", name="تكلفة المبيعات", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-P", name="المخزون", account_type="Asset", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs_acc
    ss.default_inventory_account = inv_acc
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    return tenant, cur, customer, product


def _post_sale(tenant, cur, customer, product, *, number, qty, price):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=cur, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CASH, stock_on_post=True,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(str(qty)), unit_price=Decimal(str(price)))
    post_sales_invoice(inv)
    inv.refresh_from_db()
    return inv


def test_profit_equals_revenue_minus_recorded_cogs(env):
    tenant, cur, customer, product = env
    inv = _post_sale(tenant, cur, customer, product, number="P-1", qty=5, price=100)

    # تأكيد أن حركة مخزون البيع سجّلت تكلفة 5×10 = 50
    cogs = sum(
        m.total_cost
        for m in StockMovement.objects.filter(
            tenant=tenant, reference_type="SALE", reference_id=inv.id)
    )
    assert cogs == Decimal("50.00")

    data = invoice_profits(tenant_id=tenant.TenantID)
    assert data["totals"]["count"] == 1
    row = data["rows"][0]
    assert row["invoice"] == inv.id
    assert Decimal(row["revenue"]) == Decimal("500.00")
    assert Decimal(row["cost"]) == Decimal("50.00")
    assert Decimal(row["profit"]) == Decimal("450.00")
    assert Decimal(data["totals"]["profit"]) == Decimal("450.00")


def test_totals_aggregate_and_customer_filter(env):
    tenant, cur, customer, product = env
    _post_sale(tenant, cur, customer, product, number="P-1", qty=5, price=100)   # profit 450
    _post_sale(tenant, cur, customer, product, number="P-2", qty=2, price=50)    # rev 100, cost 20, profit 80

    data = invoice_profits(tenant_id=tenant.TenantID)
    assert data["totals"]["count"] == 2
    assert Decimal(data["totals"]["revenue"]) == Decimal("600.00")
    assert Decimal(data["totals"]["cost"]) == Decimal("70.00")
    assert Decimal(data["totals"]["profit"]) == Decimal("530.00")

    # فلتر عميل غير موجود → صفر صفوف
    empty = invoice_profits(tenant_id=tenant.TenantID, customer_id=999999)
    assert empty["totals"]["count"] == 0


def test_isolated_per_tenant(env):
    tenant, cur, customer, product = env
    _post_sale(tenant, cur, customer, product, number="P-1", qty=5, price=100)

    other_owner = User.objects.create_user(username="other", password="x")
    other = create_company("شركة أخرى", other_owner)
    data = invoice_profits(tenant_id=other.TenantID)
    assert data["totals"]["count"] == 0
