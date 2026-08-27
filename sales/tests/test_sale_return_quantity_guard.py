"""T-RETQTY — مرجع البيع لا يتجاوز الكمية القابلة للإرجاع.

`_enforce_return_party` كان يحرس **الطرف** ولا يحرس **الكمية**: مرجعُ فاتورةٍ بها
10 يقبل 100، فتُدائن ذمم العميل بما لم يُبَع وتدخل المخزنَ كميةٌ لم تخرج منه قطّ.
الحارس موجود على جانب الشراء منذ البداية (`create_purchase_return`) — هذا نظيره،
وبنفس مصدر القياس الذي تعرضه الشاشة (`returnable-lines/`) فلا يرى المستخدم رقماً
ويُرفض بآخر.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="retqty", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة كمية المرجع", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1103-RQ", name="ذمم", account_type="Asset", is_active=True)
    buyer = Partner.objects.create(
        tenant=tenant, name="المشتري", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="RQ-1", name_ar="منتج المرجع",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"))
    other = Product.objects.create(
        tenant=tenant, sku="RQ-2", name_ar="منتج لم يُبَع",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"))
    original = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="INV-RQ-1", customer=buyer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=original, product=product,
        quantity=Decimal("10"), unit_price=Decimal("100"))
    return tenant, owner, cur, buyer, product, other, original


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _return_payload(cur, buyer, original, lines):
    return {
        "invoice_kind": SalesInvoice.INVOICE_KIND_SALE_RETURN,
        "invoice_date": "2026-06-20",
        "currency": cur.CurrencyID,
        "customer": buyer.id,
        "original_invoice": original.id,
        "lines": lines,
    }


def test_return_more_than_invoiced_is_rejected(env):
    tenant, owner, cur, buyer, product, other, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": product.id, "quantity": "11", "unit_price": "100"},
        ]),
        format="json",
    )
    assert res.status_code == 400, res.data
    message = str(res.data)
    # الرسالة تحمل الرقمين معاً — المطلوب والمسموح — لا «قيمة غير صالحة».
    assert "11" in message and "10" in message, message


def test_second_return_counts_the_first(env):
    """6 ثم 5 = 11 > 10 ⇒ الثاني مرفوض، ولو كان كلٌّ منهما وحده مقبولاً."""
    tenant, owner, cur, buyer, product, other, original = env
    client = _client(owner, tenant)
    first = client.post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": product.id, "quantity": "6", "unit_price": "100"},
        ]),
        format="json",
    )
    assert first.status_code == 201, first.data

    second = client.post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": product.id, "quantity": "5", "unit_price": "100"},
        ]),
        format="json",
    )
    assert second.status_code == 400, second.data


def test_return_of_a_product_not_on_the_invoice_is_rejected(env):
    """منتجٌ لم يُبَع في الفاتورة الأصلية قابلُه للإرجاع صفر."""
    tenant, owner, cur, buyer, product, other, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": other.id, "quantity": "1", "unit_price": "100"},
        ]),
        format="json",
    )
    assert res.status_code == 400, res.data


def test_return_within_the_limit_passes(env):
    tenant, owner, cur, buyer, product, other, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": product.id, "quantity": "10", "unit_price": "100"},
        ]),
        format="json",
    )
    assert res.status_code == 201, res.data


def test_editing_a_return_does_not_block_itself(env):
    """المرجع المحفوظ يستثني كمياته من «المرتجع سابقاً» — وإلا منع نفسه."""
    tenant, owner, cur, buyer, product, other, original = env
    client = _client(owner, tenant)
    created = client.post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": product.id, "quantity": "8", "unit_price": "100"},
        ]),
        format="json",
    )
    assert created.status_code == 201, created.data
    res = client.patch(
        f"/api/sales/invoices/{created.data['id']}/",
        {"lines": [{"product": product.id, "quantity": "9", "unit_price": "100"}]},
        format="json",
    )
    assert res.status_code == 200, res.data


def test_return_without_original_invoice_is_untouched(env):
    """مرجعٌ حرّ بلا أصل لا يُقاس — الحارس مشروطٌ بوجود الفاتورة الأصلية."""
    tenant, owner, cur, buyer, product, other, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/",
        {
            "invoice_kind": SalesInvoice.INVOICE_KIND_SALE_RETURN,
            "invoice_date": "2026-06-20",
            "currency": cur.CurrencyID,
            "customer": buyer.id,
            "lines": [{"product": product.id, "quantity": "99", "unit_price": "100"}],
        },
        format="json",
    )
    assert res.status_code == 201, res.data


def test_returnable_lines_endpoint_matches_the_guard(env):
    """الشاشة والحارس يقرآن الرقم نفسه — لا رقمٌ يُعرض وآخر يُرفض به."""
    tenant, owner, cur, buyer, product, other, original = env
    client = _client(owner, tenant)
    client.post(
        "/api/sales/invoices/",
        _return_payload(cur, buyer, original, [
            {"product": product.id, "quantity": "4", "unit_price": "100"},
        ]),
        format="json",
    )
    res = client.get(f"/api/sales/invoices/{original.id}/returnable-lines/")
    assert res.status_code == 200, res.data
    row = next(r for r in res.data["lines"] if r["product"] == product.id)
    assert Decimal(row["invoiced_qty"]) == Decimal("10")
    assert Decimal(row["returned_qty"]) == Decimal("4")
    assert Decimal(row["remaining_qty"]) == Decimal("6")
