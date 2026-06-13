"""Section B — قيد الفاتورة يجب أن يمرّ دائماً عبر حساب العميل (ذمم) حتى النقدي.

المطلب (المالك): حتى البيع النقدي يجب أن يُقيَّد أولاً على ذمم العميل (AR)
ثم يُسوّى التحصيل النقدي بحركة ثانية (مدين صندوق / دائن ذمم) في نفس السند،
كي يعكس كشف حساب العميل والأعمار كل الحركات. القيد القديم كان يدين الصندوق
مباشرة ويتجاوز حساب العميل تماماً.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import _resolve_ar_account, post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="subl", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الذمم", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-S", name="ذمم العميل", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="أشرف أبو الرجال", partner_type="Customer", linked_account=ar)
    cash = Account.objects.create(
        tenant=tenant, code="1110-S", name="الصندوق الرئيسي", account_type="Asset", is_active=True)
    product = Product.objects.create(
        tenant=tenant, sku="SB-1", name_ar="صنف", quantity_on_hand=100, avg_cost=10)
    return tenant, customer, cash, product, ar


def test_cash_sale_routes_through_customer_ar(env):
    tenant, customer, cash, product, ar = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="CASH-AR-1", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-11",
        invoice_type=SalesInvoice.INVOICE_CASH, cash_or_bank_account=cash,
        stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("1000.00"))
    post_sales_invoice(inv)
    inv.refresh_from_db()

    jl = list(inv.journal.lines.all())
    # القيد متوازن
    assert sum(l.debit for l in jl) == sum(l.credit for l in jl)

    ar_lines = [l for l in jl if l.account_id == ar.id]
    assert ar_lines, "البيع النقدي يجب أن يلمس حساب ذمم العميل"
    ar_debit = sum(l.debit for l in ar_lines)
    ar_credit = sum(l.credit for l in ar_lines)
    # ذمم العميل تُدين بكامل الفاتورة ثم تُسوّى بالتحصيل النقدي
    assert ar_debit == inv.grand_total, "ذمم العميل تُدين بكامل قيمة الفاتورة"
    assert ar_credit == inv.grand_total, "التحصيل النقدي يُسوّى عبر ذمم العميل"
    # كل أسطر الذمم تحمل العميل في الحقل المرجعي
    assert all(l.partner_id == customer.id for l in ar_lines)

    # الصندوق يُدين بالمبلغ المُحصَّل
    cash_debit = sum(l.debit for l in jl if l.account_id == cash.id)
    assert cash_debit == inv.grand_total
