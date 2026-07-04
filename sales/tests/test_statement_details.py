"""كشف الحساب — «تفاصيل الحركة»: سطور فاتورة المبيعات يجب أن تحمل اسم المنتج كي
تُعرض بنودها المُباعة في نافذة التفاصيل (بلا نداء إضافي لحلّ الأسماء بالواجهة).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.serializers import SalesInvoiceSerializer
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="stmtdet", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة التفاصيل", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-D", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="DET-1", name_ar="إطار ميشلان", quantity_on_hand=10, avg_cost=50)
    return tenant, customer, product


def test_sales_invoice_line_exposes_product_name(env):
    tenant, customer, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="DET-INV-1", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("2"), unit_price=Decimal("75"))

    data = SalesInvoiceSerializer(inv).data
    assert data["lines"][0]["product_name"] == "إطار ميشلان"
