"""task11 R2-A1 — discount_percent جعل قيد الفاتورة غير متوازن.

الجذر: recalculate_invoice_amounts كان يطبق discount_percent على
subtotal_excl_tax (الترويسة) فقط دون الأسطر، بينما قيد الإيراد يُبنى من
الأسطر والمدين من grand_total ⇒ مدين ≠ دائن ⇒ الترحيل يفشل (أو لو نجح
لكانت الضريبة محسوبة على أساس قبل الخصم النسبي — قاعدة VAT خاطئة).

بعد الإصلاح: الخصم النسبي يُوزَّع على الأسطر مثل الخصم المقطوع، الضريبة
تُحسب بعد كل الخصومات، والترويسة = مجموع الأسطر بالقرش.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, TaxRate
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice, recalculate_invoice_amounts
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="acct", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الخصومات", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    vat_out = Account.objects.get(tenant=tenant, code="2104")
    tax16 = TaxRate.objects.create(
        tenant=tenant, code="VAT16", name="ض.ق.م 16%", rate=Decimal("16.00"),
        tax_account=vat_out, is_active=True,
    )
    product = Product.objects.create(
        tenant=tenant, sku="P-1", name_ar="منتج", quantity_on_hand=100, avg_cost=10)
    return tenant, customer, tax16, product


def _make_invoice(tenant, customer, tax, product, **kwargs):
    inv = SalesInvoice.objects.create(
        tenant=tenant,
        invoice_number=kwargs.pop("number", "DISC-1"),
        customer=customer,
        currency=tenant._test_currency,
        invoice_date="2026-06-11",
        invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False,
        **kwargs,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("1000.00"), tax_rate=tax,
    )
    return inv


def test_discount_percent_posts_balanced(env):
    tenant, customer, tax, product = env
    inv = _make_invoice(tenant, customer, tax, product, discount_percent=Decimal("10"))

    post_sales_invoice(inv)  # كان يفشل: Unbalanced entry
    inv.refresh_from_db()

    assert inv.status == SalesInvoice.STATUS_POSTED
    # 1000 − 10% = 900 · ضريبة بعد الخصم = 144 · الإجمالي 1044
    assert inv.subtotal_excl_tax == Decimal("900.00")
    assert inv.tax_amount == Decimal("144.00")
    assert inv.grand_total == Decimal("1044.00")

    # القيد متوازن والإيراد = 900 (وليس 1000)
    jl = list(inv.journal.lines.all())
    assert sum(l.debit for l in jl) == sum(l.credit for l in jl)
    revenue_credit = sum(l.credit for l in jl if l.account.account_type == "Revenue")
    assert revenue_credit == Decimal("900.00")


def test_fixed_and_percent_discount_combined(env):
    tenant, customer, tax, product = env
    inv = _make_invoice(
        tenant, customer, tax, product, number="DISC-2",
        invoice_discount=Decimal("100"), discount_percent=Decimal("10"),
    )
    lines = list(inv.lines.all())
    recalculate_invoice_amounts(inv, lines)

    # (1000 − 100) × 90% = 810 · ضريبة 129.60 · إجمالي 939.60
    assert inv.subtotal_excl_tax == Decimal("810.00")
    assert inv.tax_amount == Decimal("129.60")
    assert inv.grand_total == Decimal("939.60")
    # الترويسة = مجموع الأسطر بالقرش (لا انحراف تقريب)
    assert sum(l.line_total_excl_tax for l in lines) == inv.subtotal_excl_tax
    assert sum(l.line_tax_amount for l in lines) == inv.tax_amount


def test_header_equals_sum_of_lines_with_rounding(env):
    """ثلاثة أسطر بمبالغ تكسر القرش — الترويسة يجب أن تساوي مجموع الأسطر."""
    tenant, customer, tax, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="DISC-3", customer=customer,
        currency=tenant._test_currency,
        invoice_date="2026-06-11", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False, discount_percent=Decimal("7.5"),
    )
    for i, price in enumerate(["33.33", "66.67", "99.99"]):
        SalesInvoiceLine.objects.create(
            tenant=tenant, invoice=inv, product=product,
            quantity=Decimal("1"), unit_price=Decimal(price), tax_rate=tax,
        )
    lines = list(inv.lines.all())
    recalculate_invoice_amounts(inv, lines)
    assert sum(l.line_total_excl_tax for l in lines) == inv.subtotal_excl_tax
    assert sum(l.line_tax_amount for l in lines) == inv.tax_amount
    assert inv.grand_total == inv.subtotal_excl_tax + inv.tax_amount
