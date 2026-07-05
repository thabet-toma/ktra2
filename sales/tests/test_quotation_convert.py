"""تحويل عرض السعر إلى فاتورة (convert_quotation_to_invoice).

كان التحويل يفشل دائماً لأن الخدمة تُمرّر كائنات (Partner/Currency) إلى
SalesInvoiceSerializer الذي يتوقّع pk:
  "Incorrect type. Expected pk value, received Partner/Currency."
وحتى بعد ذلك كان tenant يُسقَط لأنه ليس حقلاً على الـ serializer.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesQuotation
from sales.serializers import SalesQuotationSerializer
from sales.services import convert_quotation_to_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="quoconv", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة التحويل", owner)
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل التحويل", partner_type="Customer")
    product = Product.objects.create(
        tenant=tenant, sku="C-1", name_ar="صنف", quantity_on_hand=10, avg_cost=50)
    return tenant, ils, customer, product, owner


def _make_quotation(tenant, customer, product, owner):
    ser = SalesQuotationSerializer(data={
        "customer": customer.id,
        "quotation_date": "2026-06-20",
        "lines": [{"product": product.id, "quantity": "2", "unit_price": "50", "line_discount": "0"}],
    })
    ser.is_valid(raise_exception=True)
    return ser.save(tenant=tenant, created_by=owner)


def test_convert_quotation_to_invoice(env):
    tenant, ils, customer, product, owner = env
    quo = _make_quotation(tenant, customer, product, owner)

    invoice = convert_quotation_to_invoice(quo, user=owner)

    # الفاتورة أُنشئت بالحقول الصحيحة (pk) وبنفس الشركة
    assert isinstance(invoice, SalesInvoice)
    assert invoice.tenant_id == tenant.TenantID
    assert invoice.customer_id == customer.id
    assert invoice.currency_id == ils.CurrencyID
    assert invoice.created_by_id == owner.id
    assert invoice.lines.count() == 1

    # العرض صار «محوّلاً» ومربوطاً بالفاتورة
    quo.refresh_from_db()
    assert quo.status == SalesQuotation.STATUS_CONVERTED
    assert quo.invoice_id == invoice.id


def test_convert_is_idempotent(env):
    tenant, _ils, customer, product, owner = env
    quo = _make_quotation(tenant, customer, product, owner)
    convert_quotation_to_invoice(quo, user=owner)
    quo.refresh_from_db()

    with pytest.raises(ValueError):
        convert_quotation_to_invoice(quo, user=owner)
