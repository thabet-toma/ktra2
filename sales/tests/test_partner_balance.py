"""task18 DEF-C1 — رصيد الشريك من الـ subledger (قبل/بعد الفاتورة).

عميل (ذمم مدينة): الرصيد = مدين − دائن. مورد (ذمم دائنة): الرصيد = دائن − مدين.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="bal", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة الأرصدة", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-B", name="ذمم العميل", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل الرصيد", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="BAL-1", name_ar="منتج", quantity_on_hand=100, avg_cost=Decimal("10"))
    return tenant, cur, customer, product, ar


def test_customer_balance_after_posted_credit_sale(env):
    tenant, cur, customer, product, ar = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="BAL-CR-1", customer=customer,
        currency=cur, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("500.00"))
    post_sales_invoice(inv)

    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    # ذمم العميل تُدين بكامل الإجمالي (500) بلا تسوية داخل قيد الفاتورة
    assert debit == Decimal("500.00")
    assert credit == Decimal("0.00")
    # العميل: الرصيد = مدين − دائن = 500 (مدين علينا = له علينا؟ لا — علينا له: العميل مدين لنا)
    assert (debit - credit) == Decimal("500.00")


def test_supplier_balance_sign_is_credit_minus_debit(env):
    tenant, cur, customer, product, ar = env
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد", partner_type="Supplier")
    ap = Account.objects.create(
        tenant=tenant, code="2101-B", name="ذمم المورد", account_type="Liability", is_active=True)
    exp = Account.objects.create(
        tenant=tenant, code="5102-B", name="مصروف", account_type="Expense", is_active=True)
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-15", description="شراء", is_posted=True)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=exp, debit=Decimal("200"), credit=0,
        base_debit=Decimal("200"), base_credit=0)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ap, debit=0, credit=Decimal("200"),
        base_debit=0, base_credit=Decimal("200"), partner=supplier)

    debit, credit = partner_posted_balance(tenant.TenantID, supplier.id)
    assert debit == Decimal("0.00")
    assert credit == Decimal("200.00")
    # مورد: الرصيد = دائن − مدين = 200 (نحن مدينون له)
    assert (credit - debit) == Decimal("200.00")


def test_unposted_lines_excluded(env):
    tenant, cur, customer, product, ar = env
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-15", description="مسودة", is_posted=False)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ar, debit=Decimal("999"), credit=0,
        base_debit=Decimal("999"), base_credit=0, partner=customer)
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert debit == Decimal("0.00") and credit == Decimal("0.00")
