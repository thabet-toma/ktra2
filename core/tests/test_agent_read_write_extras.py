"""مسارات الوكيل الإضافية: عرض فواتير مرحّلة (بيع/شراء)، وإضافة موردين/أصناف.

كل مسار بلا حذف. الكتابة تمر بنفس السيريالايزرز المستخدَمة بالواجهة، فتُفرَض
نفس القواعد (partner_type=Supplier قسراً، SKU مُولَّد خادمياً عند غيابه).
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

KEY = "test-agent-key"


@pytest.fixture
def env(settings):
    settings.AGENT_DB_API_KEY = KEY
    owner = User.objects.create_user(username="agentextra", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الوكيل الإضافية", owner)
    create_fiscal_year(tenant, 2026)
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    product = Product.objects.create(
        tenant=tenant, sku="AGX-1", name_ar="صنف", quantity_on_hand=10, avg_cost=50)
    return tenant, customer, product


def _hdr(**extra):
    return {"HTTP_X_AGENT_KEY": KEY, **extra}


# ─── فواتير مرحّلة (بيع/شراء) ────────────────────────────────────────────

def test_list_invoices_filters_by_status_and_kind(env):
    tenant, customer, product = env
    client = APIClient()
    ils = Currency.objects.get(Code="ILS")
    inv = SalesInvoice.objects.create(
        tenant=tenant, customer=customer, invoice_number="INV-1", currency=ils,
        invoice_date="2026-06-20", invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
    )
    from sales.models import SalesInvoiceLine
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product, quantity=1, unit_price=100)
    post_sales_invoice(inv, user=None)

    resp = client.get(
        f"/api/agent/invoices/?tenant_id={tenant.TenantID}&status=posted&invoice_kind=sale",
        **_hdr(),
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["status"] == "posted"

    empty = client.get(
        f"/api/agent/invoices/?tenant_id={tenant.TenantID}&invoice_kind=purchase",
        **_hdr(),
    )
    assert empty.data["count"] == 0


def test_list_invoices_requires_key(env):
    tenant, _customer, _product = env
    resp = APIClient().get(f"/api/agent/invoices/?tenant_id={tenant.TenantID}")
    assert resp.status_code == 401


# ─── موردون ──────────────────────────────────────────────────────────────

def test_create_supplier_forces_partner_type(env):
    tenant, _customer, _product = env
    client = APIClient()
    resp = client.post(
        "/api/agent/suppliers/",
        {"tenant_id": tenant.TenantID, "name": "مورد الحديد", "partner_type": "Customer"},
        format="json", **_hdr(),
    )
    assert resp.status_code == 201, resp.data
    supplier = Partner.objects.get(pk=resp.data["id"])
    assert supplier.partner_type == "Supplier"
    assert supplier.tenant_id == tenant.TenantID


def test_list_suppliers_excludes_customers(env):
    tenant, customer, _product = env
    Partner.objects.create(tenant=tenant, name="مورد1", partner_type="Supplier")
    client = APIClient()
    resp = client.get(f"/api/agent/suppliers/?tenant_id={tenant.TenantID}", **_hdr())
    assert resp.status_code == 200
    names = [r["name"] for r in resp.data["results"]]
    assert "مورد1" in names
    assert customer.name not in names


def test_create_supplier_requires_name(env):
    tenant, _customer, _product = env
    resp = APIClient().post(
        "/api/agent/suppliers/", {"tenant_id": tenant.TenantID}, format="json", **_hdr(),
    )
    assert resp.status_code == 400


# ─── أصناف ───────────────────────────────────────────────────────────────

def test_create_product_generates_sku_when_missing(env):
    tenant, _customer, _product = env
    resp = APIClient().post(
        "/api/agent/products/",
        {"tenant_id": tenant.TenantID, "name_ar": "صنف جديد بلا رقم"},
        format="json", **_hdr(),
    )
    assert resp.status_code == 201, resp.data
    product = Product.objects.get(pk=resp.data["id"])
    assert product.sku
    assert product.tenant_id == tenant.TenantID


def test_create_product_rejects_duplicate_sku(env):
    tenant, _customer, product = env
    resp = APIClient().post(
        "/api/agent/products/",
        {"tenant_id": tenant.TenantID, "name_ar": "نسخة", "sku": product.sku},
        format="json", **_hdr(),
    )
    assert resp.status_code == 400


def test_list_products_search(env):
    tenant, _customer, product = env
    resp = APIClient().get(
        f"/api/agent/products/?tenant_id={tenant.TenantID}&search={product.sku}", **_hdr(),
    )
    assert resp.status_code == 200
    assert resp.data["count"] == 1
