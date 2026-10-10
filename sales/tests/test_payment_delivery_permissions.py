"""صلاحيات الخادم على سند القبض والإرسالية — لا تكفي الواجهة حارساً.

- إنشاء سند قبض يتطلّب `sales.payment.create` (كما يتطلّبه «تحصيل» من الفاتورة).
- الترحيل التلقائي عند الحفظ يتطلّب `sales.payment.post`: الراية الصريحة بلا
  صلاحية ⇒ 403 قبل الحفظ، وإعداد الشركة بلا صلاحية ⇒ السند يبقى مسودة.
  نفس عقد فاتورة المبيعات (`SalesInvoiceViewSet.perform_create`)، ومثله سند الصرف.
- إرسالية «قيد التنفيذ» (`invoices/{id}/delivery-order/`) لا تحرّك شيئاً فتكفيها
  `sales.invoice.edit`؛ وتسليمها (`delivery-orders/{id}/deliver/`) يخرج البضاعة
  ويقيّد التكلفة فيتطلّب `sales.invoice.post` — كإنشاء الإرسالية المباشر.
  وكلاهما يُسجَّل في سجل نشاط الإرسالية.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from core.models import ActivityLog
from inventory.models import Product
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import CustomerPayment, DeliveryOrder, SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="perm-owner", password="x")
    cur, _ = Currency.objects.get_or_create(
        Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True})
    tenant = create_company("شركة صلاحيات السندات", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-P", name="ذمم", account_type="Asset", is_active=True)
    ap = Account.objects.create(
        tenant=tenant, code="2101-P", name="ذمم دائنة", account_type="Liability", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-P", name="صندوق", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد", partner_type="Supplier", linked_account=ap)
    return tenant, owner, cur, cash, customer, supplier


def _member(tenant, username, role, *, grant=()):
    user = User.objects.create_user(username=username, password="x")
    membership = UserCompanyMembership.objects.create(user=user, tenant=tenant, role=role)
    for key in grant:
        MemberPermission.objects.create(membership=membership, permission_key=key, allowed=True)
    return user


def _client(user, tenant):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _receipt(cur, cash, customer, **over):
    body = {
        "partner": customer.id, "payment_date": "2026-06-20", "amount": "100",
        "currency": cur.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": cash.id,
    }
    body.update(over)
    return body


# ── سند القبض ──

def test_receipt_create_requires_create_permission(env):
    tenant, _owner, cur, cash, customer, _ = env
    clerk = _member(tenant, "perm-clerk", "staff")
    res = _client(clerk, tenant).post(
        "/api/sales/payments/", _receipt(cur, cash, customer, auto_post=False), format="json")
    assert res.status_code == 403, res.content
    assert not CustomerPayment.objects.filter(tenant=tenant).exists()


def test_receipt_setting_auto_post_without_post_permission_stays_draft(env):
    tenant, _owner, cur, cash, customer, _ = env
    assert get_or_create_sales_settings(tenant).auto_post_payments is True
    clerk = _member(tenant, "perm-clerk", "staff", grant=["sales.payment.create"])
    res = _client(clerk, tenant).post(
        "/api/sales/payments/", _receipt(cur, cash, customer), format="json")
    assert res.status_code == 201, res.content
    assert res.json()["is_posted"] is False
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type="CUSTOMER_PAYMENT").exists()


def test_receipt_explicit_auto_post_without_post_permission_is_refused_before_save(env):
    tenant, _owner, cur, cash, customer, _ = env
    clerk = _member(tenant, "perm-clerk", "staff", grant=["sales.payment.create"])
    res = _client(clerk, tenant).post(
        "/api/sales/payments/", _receipt(cur, cash, customer, auto_post=True), format="json")
    assert res.status_code == 403, res.content
    assert not CustomerPayment.objects.filter(tenant=tenant).exists()


def test_receipt_auto_post_still_works_for_member_with_post_permission(env):
    tenant, _owner, cur, cash, customer, _ = env
    seller = _member(tenant, "perm-seller", "sales")
    res = _client(seller, tenant).post(
        "/api/sales/payments/", _receipt(cur, cash, customer), format="json")
    assert res.status_code == 201, res.content
    assert res.json()["is_posted"] is True


# ── سند الصرف: نفس مصدر القرار المشترك (`core.payments.should_auto_post_payment`) ──

def test_supplier_voucher_setting_auto_post_without_post_permission_stays_draft(env):
    tenant, _owner, cur, cash, _customer, supplier = env
    clerk = _member(tenant, "perm-clerk", "staff", grant=["purchase.payment.create"])
    res = _client(clerk, tenant).post("/api/logistics/supplier-payments/", {
        "partner": supplier.id, "payment_date": "2026-06-20", "amount": "70",
        "currency": cur.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": cash.id,
    }, format="json")
    assert res.status_code == 201, res.content
    assert res.json()["is_posted"] is False


# ── الإرسالية ──

@pytest.fixture
def posted_invoice(env):
    tenant, owner, cur, _cash, customer, _ = env
    product = Product.objects.create(
        tenant=tenant, sku="PD-1", name_ar="منتج", quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"), unit_cost=Decimal("10"),
        reference_type="OPENING", reference_id=0, movement_date="2026-06-01", tenant=tenant)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = Account.objects.create(
        tenant=tenant, code="5101-P", name="تكلفة", account_type="Expense", is_active=True)
    ss.default_inventory_account = Account.objects.create(
        tenant=tenant, code="1104-P", name="مخزون", account_type="Asset", is_active=True)
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="PD-INV-1", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product, quantity=Decimal("5"),
        unit_price=Decimal("100"))
    assert _client(owner, tenant).post(
        f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    return inv, product


def test_pending_delivery_order_requires_edit_permission_and_is_logged(env, posted_invoice):
    tenant, *_ = env
    inv, _product = posted_invoice
    viewer = _member(tenant, "perm-viewer", "viewer")
    refused = _client(viewer, tenant).post(
        f"/api/sales/invoices/{inv.id}/delivery-order/", {}, format="json")
    assert refused.status_code == 403, refused.content

    clerk = _member(tenant, "perm-clerk", "staff")
    res = _client(clerk, tenant).post(
        f"/api/sales/invoices/{inv.id}/delivery-order/", {}, format="json")
    assert res.status_code == 201, res.content
    do = DeliveryOrder.objects.get(pk=res.json()["id"])
    assert do.status == DeliveryOrder.STATUS_PENDING
    assert ActivityLog.objects.filter(
        tenant=tenant, entity_type="sales_delivery_note", entity_id=do.id,
        action="create", user=clerk).exists()


def test_delivering_a_pending_order_requires_post_permission_and_is_logged(env, posted_invoice):
    tenant, owner, *_ = env
    inv, product = posted_invoice
    clerk = _member(tenant, "perm-clerk", "staff")
    do_id = _client(clerk, tenant).post(
        f"/api/sales/invoices/{inv.id}/delivery-order/", {}, format="json").json()["id"]

    refused = _client(clerk, tenant).post(
        f"/api/sales/delivery-orders/{do_id}/deliver/", {}, format="json")
    assert refused.status_code == 403, refused.content
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("50.0000")

    res = _client(owner, tenant).post(
        f"/api/sales/delivery-orders/{do_id}/deliver/", {}, format="json")
    assert res.status_code == 200, res.content
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("45.0000")
    assert ActivityLog.objects.filter(
        tenant=tenant, entity_type="sales_delivery_note", entity_id=do_id,
        action="deliver", user=owner).exists()
