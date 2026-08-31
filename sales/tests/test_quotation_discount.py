"""خصم عرض السعر (خصم المستند) — القاعدة والانتقال إلى الفاتورة.

كان `discount_amount` على العرض حقلاً ميتاً: الواجهة لا ترسله، والخادم — إن
أُرسل — يخصمه **بعد** الضريبة (`subtotal + tax − discount`)، فيخالف قاعدة
ض.ق.م ويخالف الفاتورة نفسها (`recalculate_invoice_amounts` يخصم قبل الضريبة
ويحسبها على الأساس المخصوم). وكان التحويل إلى فاتورة يُسقط الخصم كلّه —
فيُفوتَر الزبون بأكثر ممّا عُرض عليه.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounting.models import Account, TaxRate
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.serializers import SalesQuotationSerializer
from sales.services import convert_quotation_to_invoice, recalculate_invoice_amounts
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="quodisc", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة خصم العرض", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    vat_out = Account.objects.get(tenant=tenant, code="2104")
    tax16 = TaxRate.objects.create(
        tenant=tenant, code="VAT16", name="ض.ق.م 16%", rate=Decimal("16.00"),
        tax_account=vat_out, direction="sales", is_active=True,
    )
    product = Product.objects.create(
        tenant=tenant, sku="Q-D1", name_ar="منتج", quantity_on_hand=100, avg_cost=10)
    return tenant, customer, tax16, product


def _quote(tenant, customer, product, tax=None, *, discount="0", lines=None):
    data = {
        "customer": customer.id,
        "quotation_date": "2026-06-20",
        "discount_amount": discount,
        "lines": lines or [{
            "product": product.id,
            "quantity": "10",
            "unit_price": "100",
            "line_discount": "0",
            "tax_rate": tax.id if tax else None,
        }],
    }
    ser = SalesQuotationSerializer(context={"tenant": tenant}, data=data)
    ser.is_valid(raise_exception=True)
    return ser.save(tenant=tenant, created_by=None)


def test_document_discount_reduces_taxable_base(env):
    """1000 − 200 = 800 ⇒ ضريبة 128 (لا 160) ⇒ الإجمالي 928 (لا 960)."""
    tenant, customer, tax, product = env
    q = _quote(tenant, customer, product, tax, discount="200")

    assert q.subtotal == Decimal("1000.00")       # مجموع البنود قبل خصم المستند
    assert q.discount_amount == Decimal("200.00")
    assert q.tax_amount == Decimal("128.00")      # الضريبة على الأساس المخصوم
    assert q.grand_total == Decimal("928.00")


def test_quotation_totals_match_invoice_math(env):
    """العرض والفاتورة على نفس البنود ونفس الخصم ⇒ نفس الضريبة ونفس الإجمالي."""
    tenant, customer, tax, product = env
    q = _quote(tenant, customer, product, tax, discount="333.33", lines=[
        {"product": product.id, "quantity": "3", "unit_price": "33.33",
         "line_discount": "0", "tax_rate": tax.id},
        {"product": product.id, "quantity": "7", "unit_price": "66.67",
         "line_discount": "5", "tax_rate": tax.id},
    ])

    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="QD-PARITY", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-20",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
        invoice_discount=Decimal("333.33"),
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("3"), unit_price=Decimal("33.33"), tax_rate=tax)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("7"), unit_price=Decimal("66.67"),
        line_discount=Decimal("5"), tax_rate=tax)
    recalculate_invoice_amounts(inv)

    assert q.tax_amount == inv.tax_amount
    assert q.grand_total == inv.grand_total


def test_convert_to_invoice_carries_document_discount(env):
    """الخصم المعروض هو الخصم المفوتر — وإلا فُوتِر الزبون بأكثر ممّا قَبِل."""
    tenant, customer, tax, product = env
    q = _quote(tenant, customer, product, tax, discount="200")

    inv = convert_quotation_to_invoice(q)

    assert inv.invoice_discount == Decimal("200.00")
    assert inv.grand_total == q.grand_total == Decimal("928.00")


def test_negative_document_discount_rejected(env):
    tenant, customer, tax, product = env
    with pytest.raises(DRFValidationError):
        _quote(tenant, customer, product, tax, discount="-1")


def test_discount_larger_than_subtotal_is_capped(env):
    """خصم يتجاوز مجموع البنود لا يصنع إجمالياً سالباً (كما في الفاتورة)."""
    tenant, customer, tax, product = env
    q = _quote(tenant, customer, product, tax, discount="5000")

    assert q.grand_total == Decimal("0.00")
    assert q.tax_amount == Decimal("0.00")
