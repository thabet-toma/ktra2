"""واجهة الوكيل للكتابة: /api/agent/invoices/draft/

تتحقق من: رفض المفتاح الخاطئ، إنشاء فاتورة **مسوّدة دائماً** بالـ ORM
(ترقيم خادمي + احتساب الإجمالي)، وتجاهل محاولة فرض status/auto_post من الجسم.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

URL = "/api/agent/invoices/draft/"
KEY = "test-agent-key"


@pytest.fixture
def env(settings):
    settings.AGENT_DB_API_KEY = KEY
    owner = User.objects.create_user(username="agentwrite", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الوكيل", owner)
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    product = Product.objects.create(
        tenant=tenant, sku="AG-1", name_ar="صنف", quantity_on_hand=10, avg_cost=50)
    return tenant, customer, product


def _body(customer, product, **extra):
    return {
        "customer": customer.id,
        "invoice_date": "2026-06-20",
        "lines": [{"product": product.id, "quantity": "2", "unit_price": "75"}],
        **extra,
    }


def test_rejects_missing_or_wrong_key(env):
    _tenant, customer, product = env
    client = APIClient()
    assert client.post(URL, _body(customer, product), format="json").status_code == 401
    resp = client.post(
        URL, _body(customer, product), format="json", HTTP_X_AGENT_KEY="wrong")
    assert resp.status_code == 401
    assert SalesInvoice.objects.count() == 0


def test_creates_draft_invoice(env):
    tenant, customer, product = env
    client = APIClient()
    resp = client.post(
        URL, _body(customer, product, tenant_id=tenant.TenantID),
        format="json", HTTP_X_AGENT_KEY=KEY,
    )
    assert resp.status_code == 201, resp.data

    inv = SalesInvoice.objects.get(pk=resp.data["id"])
    assert inv.status == SalesInvoice.STATUS_DRAFT
    assert inv.tenant_id == tenant.TenantID
    assert inv.invoice_number  # رقم مُولَّد خادمياً
    assert inv.grand_total == Decimal("150.00")
    assert inv.lines.count() == 1


def test_cannot_force_posted_status_or_auto_post(env):
    tenant, customer, product = env
    resp = APIClient().post(
        URL,
        _body(customer, product, tenant_id=tenant.TenantID,
              status="posted", auto_post=True),
        format="json", HTTP_X_AGENT_KEY=KEY,
    )
    assert resp.status_code == 201, resp.data
    inv = SalesInvoice.objects.get(pk=resp.data["id"])
    assert inv.status == SalesInvoice.STATUS_DRAFT
    assert not inv.journal_id  # لا قيود محاسبية بلا ترحيل


def test_any_origin_is_allowed(env):
    """موقع ثاني بدومين مجهول: preflight ونداء فعلي كلاهما يمرّ (الهوية بالمفتاح)."""
    client = APIClient()
    pre = client.options(URL, HTTP_ORIGIN="https://any-unknown-site.example")
    assert pre.status_code == 200
    assert pre["Access-Control-Allow-Origin"] == "*"
    assert "X-Agent-Key" in pre["Access-Control-Allow-Headers"]

    _tenant, customer, product = env
    resp = client.post(
        URL, _body(customer, product), format="json",
        HTTP_X_AGENT_KEY=KEY, HTTP_ORIGIN="https://any-unknown-site.example",
    )
    assert resp.status_code == 201, resp.data
    assert resp["Access-Control-Allow-Origin"] == "*"


def test_unknown_tenant_is_rejected(env):
    _tenant, customer, product = env
    resp = APIClient().post(
        URL, _body(customer, product, tenant_id=99999),
        format="json", HTTP_X_AGENT_KEY=KEY,
    )
    assert resp.status_code == 400
    assert SalesInvoice.objects.count() == 0
