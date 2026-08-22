"""مرجع البيع لا يُقيَّد على طرفٍ لم يشترِ.

شاشة «مرجع البيع» تُعبّئ العميل من الفاتورة الأصلية ثم **تتركه قابلاً للتغيير**،
ولم يكن في الخادم ما يمنع الفارق: مرجعٌ مربوطٌ بفاتورة زيدٍ ومُقيَّدٌ على ذمم
عمرو يمرّ ويُرحَّل، فيَنقص دينُ من لم يُرجِع شيئاً ويبقى دينُ من أرجع. خطأٌ
مالي صامت لا يُكتشف إلا من كشف حساب.

الحارس في `SalesInvoiceSerializer.validate` — أي مسارٍ يكتب عبر الـAPI محكومٌ
به، لا شاشة «مرجع البيع» وحدها.
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
    owner = User.objects.create_user(username="retint", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة سلامة المرجع", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1103-RI", name="ذمم", account_type="Asset", is_active=True)
    buyer = Partner.objects.create(
        tenant=tenant, name="المشتري", partner_type="Customer", linked_account=ar)
    stranger = Partner.objects.create(
        tenant=tenant, name="طرفٌ آخر", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="RI-1", name_ar="صنف", quantity_on_hand=Decimal("50"),
        avg_cost=Decimal("10"))
    original = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="INV-RI-1", customer=buyer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=original, product=product,
        quantity=Decimal("2"), unit_price=Decimal("100"))
    return tenant, owner, cur, buyer, stranger, product, original


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _payload(cur, product, *, customer_id=None, original_id=None):
    body = {
        "invoice_kind": SalesInvoice.INVOICE_KIND_SALE_RETURN,
        "invoice_date": "2026-06-20",
        "currency": cur.CurrencyID,
        "lines": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }
    if customer_id is not None:
        body["customer"] = customer_id
    if original_id is not None:
        body["original_invoice"] = original_id
    return body


def test_return_rejects_customer_other_than_the_original_buyer(env):
    tenant, owner, cur, buyer, stranger, product, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/",
        _payload(cur, product, customer_id=stranger.id, original_id=original.id),
        format="json",
    )
    assert res.status_code == 400, res.data
    assert "customer" in res.data
    # الرسالة تسمّي المشتري الحقيقي — لا «قيمة غير صالحة» يقف عندها المستخدم.
    assert buyer.name in str(res.data["customer"])


def test_return_of_the_same_buyer_passes(env):
    tenant, owner, cur, buyer, stranger, product, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/",
        _payload(cur, product, customer_id=buyer.id, original_id=original.id),
        format="json",
    )
    assert res.status_code == 201, res.data
    created = SalesInvoice.objects.get(pk=res.data["id"])
    assert created.customer_id == buyer.id
    assert created.original_invoice_id == original.id


def test_return_without_customer_inherits_the_original_buyer(env):
    """العميل مشتقٌّ لا مُدخَل: إغفالُه يأخذه من الأصل لا من «العميل الافتراضي»."""
    tenant, owner, cur, buyer, stranger, product, original = env
    from sales.services import get_or_create_sales_settings
    ss = get_or_create_sales_settings(tenant)
    ss.default_customer = stranger  # الافتراضي طرفٌ آخر — يجب ألّا يفوز هنا
    ss.save(update_fields=["default_customer"])

    res = _client(owner, tenant).post(
        "/api/sales/invoices/", _payload(cur, product, original_id=original.id),
        format="json",
    )
    assert res.status_code == 201, res.data
    assert SalesInvoice.objects.get(pk=res.data["id"]).customer_id == buyer.id


def test_plain_return_without_original_invoice_is_untouched(env):
    """مرجعٌ بلا فاتورة أصلية يبقى حرّاً — الحارس مشروطٌ بوجود الأصل."""
    tenant, owner, cur, buyer, stranger, product, original = env
    res = _client(owner, tenant).post(
        "/api/sales/invoices/", _payload(cur, product, customer_id=stranger.id),
        format="json",
    )
    assert res.status_code == 201, res.data


def test_patching_a_return_to_another_customer_is_rejected(env):
    """المنع على التعديل أيضاً — وإلا أُنشئ صحيحاً ثم حُوِّل."""
    tenant, owner, cur, buyer, stranger, product, original = env
    client = _client(owner, tenant)
    created = client.post(
        "/api/sales/invoices/",
        _payload(cur, product, customer_id=buyer.id, original_id=original.id),
        format="json",
    )
    assert created.status_code == 201, created.data
    res = client.patch(
        f"/api/sales/invoices/{created.data['id']}/",
        {"customer": stranger.id}, format="json",
    )
    assert res.status_code == 400, res.data
    assert "customer" in res.data
