"""نقطة الوكيل «آخر سعر بيع» — `GET /api/agent/last-price/`.

البوت يسأل عنها قبل كل بند ليقترح سعراً على الموظف. تُثبِّت هذه الاختبارات
العقد الذي يعتمد عليه: التفضيل للعميل ثم الرجوع للسعر العام، والمرحَّل وحده،
والعزل بالشركة، والحارس بالمفتاح.

القاعدة نفسها مُختبَرة على مستوى الدالة في `test_last_price.py` — هنا نختبر
**النقطة** (المفتاح، العزل، شكل الرد) لا نعيد اختبار القاعدة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

URL = "/api/agent/last-price/"
KEY = "test-agent-key-strong"


@pytest.fixture
def env(settings):
    settings.AGENT_DB_API_KEY = KEY
    owner = User.objects.create_user(username="alp", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة الوكيل", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-A", name="ذمم", account_type="Asset", is_active=True)
    c1 = Partner.objects.create(
        tenant=tenant, name="عميل1", partner_type="Customer", linked_account=ar)
    c2 = Partner.objects.create(
        tenant=tenant, name="عميل2", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="ALP-1", name_ar="منتج", quantity_on_hand=100,
        avg_cost=Decimal("10"))
    return tenant, cur, c1, c2, product


def _post_invoice(tenant, cur, customer, product, *, number, date, price):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=cur, invoice_date=date,
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(str(price)))
    post_sales_invoice(inv)
    return inv


def _ask(client, tenant, product, customer=None, key=KEY):
    params = {"tenant_id": tenant.TenantID, "product": product.id}
    if customer is not None:
        params["customer"] = customer.id
    headers = {"HTTP_X_AGENT_KEY": key} if key is not None else {}
    return client.get(URL, params, **headers)


def test_returns_last_price_this_customer_paid(client, env):
    """بيع سابق لهذا العميل ⇒ سعره هو، لا أحدث سعر في السوق."""
    tenant, cur, c1, c2, product = env
    _post_invoice(tenant, cur, c1, product, number="A-1", date="2026-06-10", price=100)
    _post_invoice(tenant, cur, c2, product, number="A-2", date="2026-06-15", price=130)

    res = _ask(client, tenant, product, customer=c1)

    assert res.status_code == 200, res.content[:300]
    assert Decimal(res.json()["unit_price"]) == Decimal("100.0000")


def test_falls_back_to_general_price_when_customer_never_bought_it(client, env):
    """عميل بلا تاريخ على المنتج ⇒ آخر سعر عام — البوت يحتاج رقماً يقترحه لا فراغاً."""
    tenant, cur, c1, c2, product = env
    _post_invoice(tenant, cur, c1, product, number="A-1", date="2026-06-10", price=100)

    res = _ask(client, tenant, product, customer=c2)

    assert res.status_code == 200, res.content[:300]
    assert Decimal(res.json()["unit_price"]) == Decimal("100.0000")


def test_returns_null_when_never_sold(client, env):
    tenant, cur, c1, c2, product = env

    res = _ask(client, tenant, product)

    assert res.status_code == 200, res.content[:300]
    assert res.json()["unit_price"] is None


def test_another_company_cannot_see_the_price(client, env):
    """العزل: نفس معرّف المنتج تحت شركة أخرى لا يكشف سعرها."""
    tenant, cur, c1, c2, product = env
    _post_invoice(tenant, cur, c1, product, number="A-1", date="2026-06-10", price=100)

    other_owner = User.objects.create_user(username="alp2", password="x")
    other = create_company("شركة أخرى", other_owner)

    res = client.get(
        URL, {"tenant_id": other.TenantID, "product": product.id},
        HTTP_X_AGENT_KEY=KEY,
    )

    assert res.status_code == 200, res.content[:300]
    assert res.json()["unit_price"] is None


def test_draft_invoice_does_not_set_the_price(client, env):
    """المسوّدة ليست بيعاً — وإلا اقترح البوت سعراً من فاتورة لم تحدث بعد."""
    tenant, cur, c1, c2, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="A-DRAFT", customer=c1, currency=cur,
        invoice_date="2026-06-20", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("999"))

    res = _ask(client, tenant, product, customer=c1)

    assert res.status_code == 200, res.content[:300]
    assert res.json()["unit_price"] is None


def test_missing_key_is_rejected(client, env):
    tenant, cur, c1, c2, product = env

    assert _ask(client, tenant, product, key=None).status_code == 401
    assert _ask(client, tenant, product, key="wrong").status_code == 401


def test_product_param_is_required(client, env):
    tenant, cur, c1, c2, product = env

    res = client.get(URL, {"tenant_id": tenant.TenantID}, HTTP_X_AGENT_KEY=KEY)

    assert res.status_code == 400
