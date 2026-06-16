"""Section B / Feature 2 — قيد الفاتورة يدين ذمم العميل بالكامل ولا يُسوّي النقدية.

المطلب (المالك — Feature 2): قيد الفاتورة (Entry A) يدين ذمم العميل بكامل
الإجمالي ويدائن الإيراد فقط. تحصيل النقدية أصبح سنداً مستقلاً «وصل دفع»
(CustomerPayment، Entry B: مدين النقدية / دائن ذمم العميل) لا يولّده ترحيل
الفاتورة إطلاقاً. لذا قيد فاتورة نقدية يلمس الذمم مديناً فقط — بلا سطر صندوق
ولا تسوية دائنة على الذمم.
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
    # Feature 2: ذمم العميل تُدين بكامل الفاتورة ولا تُسوّى داخل قيد الفاتورة
    assert ar_debit == inv.grand_total, "ذمم العميل تُدين بكامل قيمة الفاتورة"
    assert ar_credit == Decimal("0"), "ترحيل الفاتورة لا يُسوّي النقدية عبر الذمم"
    # كل أسطر الذمم تحمل العميل في الحقل المرجعي
    assert all(l.partner_id == customer.id for l in ar_lines)

    # Feature 2: لا سطر صندوق في قيد الفاتورة — التحصيل سند مستقل
    cash_debit = sum(l.debit for l in jl if l.account_id == cash.id)
    assert cash_debit == Decimal("0")
    # الفاتورة تبقى غير مدفوعة بعد الترحيل (تُسوّى بوصل دفع لاحقاً)
    assert inv.amount_paid == Decimal("0")
