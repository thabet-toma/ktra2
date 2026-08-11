"""إنشاء عرض سعر: يجب أن ينجح دون إرسال رقم العرض أو العملة من الواجهة (يُولَّد الرقم
ويُفترَض العملة الأساسية خادمياً)، وبند بلا ضريبة (tax_rate=None) مقبول.
كان الإنشاء يفشل دائماً: «This field is required» (رقم/عملة) + tax_rate=0 غير صالح.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesQuotation
from sales.serializers import SalesQuotationSerializer
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="quocreate", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة العروض", owner)
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    product = Product.objects.create(
        tenant=tenant, sku="Q-1", name_ar="صنف", quantity_on_hand=10, avg_cost=50)
    return tenant, ils, customer, product


def test_create_quotation_without_number_or_currency(env):
    tenant, ils, customer, product = env
    data = {
        "customer": customer.id,
        "quotation_date": "2026-06-20",
        "lines": [
            {"product": product.id, "quantity": "2", "unit_price": "75", "line_discount": "0"},
        ],
    }
    ser = SalesQuotationSerializer(context={"tenant": tenant}, data=data)
    ser.is_valid(raise_exception=True)  # كان يفشل: رقم/عملة مطلوبان
    q = ser.save(tenant=tenant, created_by=None)

    assert q.quotation_number  # مُولَّد خادمياً
    assert q.currency_id == ils.CurrencyID  # افتُرضت العملة الأساسية
    assert q.lines.count() == 1
    assert q.lines.first().tax_rate_id is None  # بند بلا ضريبة مقبول


def test_quotation_numbers_are_unique_sequence(env):
    tenant, _ils, customer, product = env
    base = {"customer": customer.id, "quotation_date": "2026-06-20",
            "lines": [{"product": product.id, "quantity": "1", "unit_price": "10"}]}
    nums = []
    for _ in range(2):
        ser = SalesQuotationSerializer(context={"tenant": tenant}, data=dict(base))
        ser.is_valid(raise_exception=True)
        nums.append(ser.save(tenant=tenant, created_by=None).quotation_number)
    assert nums[0] != nums[1]
    assert SalesQuotation.objects.filter(tenant=tenant).count() == 2
