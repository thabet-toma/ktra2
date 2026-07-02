"""إعداد «منع فاتورة الخسارة» — عند تفعيل `SalesSettings.block_loss_invoices`، يُرفض
ترحيل فاتورة بيع ربحها الإجمالي سالب (سعر البيع < متوسط التكلفة). معطّلاً افتراضياً
فلا يؤثر على السلوك القائم.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from accounting.models import Account
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
    owner = User.objects.create_user(username="lossblk", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الخسارة", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-B", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    # الصنف تكلفته 100 — البيع بأقل منه = خسارة، وبأكثر = ربح.
    product = Product.objects.create(
        tenant=tenant, sku="LOSS-1", name_ar="صنف", quantity_on_hand=100, avg_cost=100)
    return tenant, customer, product


def _invoice(tenant, customer, product, *, unit_price, number):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(str(unit_price)))
    return inv


def _settings(tenant, *, block):
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"block_loss_invoices": block})


def test_loss_invoice_blocked_when_setting_on(env):
    tenant, customer, product = env
    _settings(tenant, block=True)
    inv = _invoice(tenant, customer, product, unit_price=80, number="LOSS-INV-1")
    with pytest.raises(ValidationError):
        post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status != SalesInvoice.STATUS_POSTED


def test_profit_invoice_allowed_when_setting_on(env):
    tenant, customer, product = env
    _settings(tenant, block=True)
    inv = _invoice(tenant, customer, product, unit_price=150, number="PROFIT-INV-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_loss_invoice_allowed_when_setting_off(env):
    tenant, customer, product = env
    _settings(tenant, block=False)
    inv = _invoice(tenant, customer, product, unit_price=80, number="LOSS-OFF-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
