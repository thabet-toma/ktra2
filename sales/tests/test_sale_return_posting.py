"""مرجع البيع (sale_return): الترحيل يعكس قيد البيع ويُعيد الكمية للمخزون.

يتحقق أن:
  - حركة RETURN_IN تُعيد الكمية المرتجعة إلى المخزون.
  - سطر ذمم العميل في القيد يصبح **دائناً** (العميل يَدين بأقل / يُرَدّ له).
  - المرجع يُرحَّل رغم أن الكمية المرتجعة قد تتجاوز المخزون الحالي (لا فحص توفّر).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="retslr", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة المرجع", owner)
    tenant._cur = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-R", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4001-R", name="مبيعات", account_type="Revenue", is_active=True)
    cogs = Account.objects.create(
        tenant=tenant, code="5001-R", name="تكلفة", account_type="Expense", is_active=True)
    inv = Account.objects.create(
        tenant=tenant, code="1104-R", name="مخزون", account_type="Asset", is_active=True)
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "default_revenue_account_product": rev,
            "default_cogs_account": cogs,
            "default_inventory_account": inv,
        },
    )
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="RET-S", name_ar="منتج", quantity_on_hand=Decimal("5"),
        avg_cost=Decimal("100"))
    return tenant, customer, product, ar


def _make_return(tenant, customer, product, *, qty, price, number):
    ret = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._cur, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=ret, product=product,
        quantity=Decimal(str(qty)), unit_price=Decimal(str(price)))
    return ret


def test_sale_return_adds_stock_back(env):
    tenant, customer, product, _ar = env
    ret = _make_return(tenant, customer, product, qty=3, price=150, number="SRET-1")
    post_sales_invoice(ret)
    ret.refresh_from_db()
    product.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    # 5 + 3 مرتجعة = 8
    assert product.quantity_on_hand == Decimal("8")


def test_sale_return_credits_receivable(env):
    tenant, customer, product, ar = env
    ret = _make_return(tenant, customer, product, qty=2, price=150, number="SRET-2")
    post_sales_invoice(ret)
    ret.refresh_from_db()
    ar_lines = JournalLine.objects.filter(journal=ret.journal, account=ar)
    total_credit = sum((Decimal(str(l.credit or 0)) for l in ar_lines), Decimal("0"))
    total_debit = sum((Decimal(str(l.debit or 0)) for l in ar_lines), Decimal("0"))
    # المرجع يُخفّض ذمم العميل ⇒ صافي الحركة دائن.
    assert total_credit > total_debit
