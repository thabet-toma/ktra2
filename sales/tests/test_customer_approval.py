"""موافقة الزبون على الفاتورة والإرسالية وسند القبض (T2).

تطبيق المستودع الخارجي يجهّز المسودات ثم يوافق عليها الزبون أو يعترض من تطبيقه. العقد:

- الافتراضي «غير مطلوبة» لكل مستند — مستخدمو المنصة لا يتأثرون.
- `POST .../customer-approval/` بجسم `{status, by_name, note}`؛ `not_required` لا يُضبط من الـAPI.
- موافقةٌ ثم تعديلٌ في **المال** (بنود/مبالغ) ⇒ تسقط تلقائياً إلى «بانتظار» ويُسجَّل؛ تعديل
  الملاحظة وحدها لا يُسقطها (بصمة المحتوى لا تشمل الملاحظات).
- الترحيل يقرأ هذه الحالة (T3، `test_customer_approval_post_policy.py`): تحذير افتراضاً أو منع بإعداد الشركة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, Cheque
from accounting.services import create_fiscal_year
from core.concurrency import etag_for
from core.models import ActivityLog
from inventory.models import Product
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import CustomerPayment, DeliveryOrder, SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from sales.services.customer_approval import approval_fingerprint
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

KINDS = ["invoice", "delivery", "payment"]
URLS = {
    "invoice": "/api/sales/invoices/{id}/",
    "delivery": "/api/sales/delivery-orders/{id}/",
    "payment": "/api/sales/payments/{id}/",
}
ENTITY = {
    "invoice": "sales_invoice",
    "delivery": "sales_delivery_note",
    "payment": "customer_payment",
}


@pytest.fixture
def env():
    owner = User.objects.create_user(username="ca-owner", password="x")
    cur, _ = Currency.objects.get_or_create(
        Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True})
    tenant = create_company("شركة موافقة الزبون", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-A", name="ذمم", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-A", name="صندوق", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="CA-1", name_ar="منتج", quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"), unit_cost=Decimal("10"),
        reference_type="OPENING", reference_id=0, movement_date="2026-06-01", tenant=tenant)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = Account.objects.create(
        tenant=tenant, code="5101-A", name="تكلفة", account_type="Expense", is_active=True)
    ss.default_inventory_account = Account.objects.create(
        tenant=tenant, code="1104-A", name="مخزون", account_type="Asset", is_active=True)
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    return {
        "tenant": tenant, "owner": owner, "cur": cur, "cash": cash,
        "customer": customer, "product": product, "client": _client(owner, tenant),
    }


def _client(user, tenant):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _member(tenant, username, role, *, grant=()):
    user = User.objects.create_user(username=username, password="x")
    membership = UserCompanyMembership.objects.create(user=user, tenant=tenant, role=role)
    for key in grant:
        MemberPermission.objects.create(membership=membership, permission_key=key, allowed=True)
    return user


def _invoice(env, number="CA-INV-1"):
    inv = SalesInvoice.objects.create(
        tenant=env["tenant"], invoice_number=number, customer=env["customer"],
        currency=env["cur"], invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    line = SalesInvoiceLine.objects.create(
        tenant=env["tenant"], invoice=inv, product=env["product"], quantity=Decimal("5"),
        unit_price=Decimal("100"))
    return inv, line


def _payment(env):
    return CustomerPayment.objects.create(
        tenant=env["tenant"], partner=env["customer"], payment_date="2026-06-20",
        amount=Decimal("100"), currency=env["cur"], exchange_rate=Decimal("1"),
        cash_or_bank_account=env["cash"])


def _delivery(env):
    """إرسالية مُسلَّمة (2 من 5) على فاتورة مرحَّلة بلا خصم مخزون عند الترحيل."""
    client = env["client"]
    inv, line = _invoice(env, number="CA-INV-D")
    assert client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    res = client.post("/api/sales/delivery-orders/", {
        "invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "2"}],
    }, format="json")
    assert res.status_code == 201, res.content
    return inv, line, DeliveryOrder.objects.get(pk=res.json()["id"])


def _make(env, kind):
    if kind == "invoice":
        return _invoice(env)[0]
    if kind == "payment":
        return _payment(env)
    return _delivery(env)[2]


def _approve_url(kind, doc):
    return URLS[kind].format(id=doc.id) + "customer-approval/"


def _post(client, kind, doc, **body):
    return client.post(_approve_url(kind, doc), body, format="json")


def _events(tenant, kind, doc_id):
    return ActivityLog.objects.filter(
        tenant=tenant, action="customer_approval", entity_type=ENTITY[kind], entity_id=doc_id)


# ── الافتراضي ──

@pytest.mark.parametrize("kind", KINDS)
def test_every_document_defaults_to_not_required(env, kind):
    doc = _make(env, kind)
    assert doc.customer_approval_status == "not_required"
    assert doc.customer_approval_at is None
    assert doc.customer_approval_by == ""
    assert doc.customer_approval_note == ""
    assert doc.customer_approval_fingerprint == ""
    body = env["client"].get(URLS[kind].format(id=doc.id)).json()
    assert body["customer_approval_status"] == "not_required"
    assert body["customer_approval_status_display"] == "غير مطلوبة"
    assert body["customer_approval_at"] is None
    assert "customer_approval_fingerprint" not in body


def test_list_serializers_expose_the_status(env):
    inv = _invoice(env)[0]
    pay = _payment(env)
    _inv2, _line, delivery = _delivery(env)
    client = env["client"]
    for path in ("invoices", "delivery-orders", "payments"):
        rows = client.get(f"/api/sales/{path}/").json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        assert rows, path
        assert all(r["customer_approval_status"] == "not_required" for r in rows), path
        assert all("customer_approval_status_display" in r for r in rows), path
    assert inv.pk and pay.pk and delivery.pk


def test_platform_flows_are_unchanged_by_the_new_fields(env):
    """إنشاء وترحيل فاتورة بلا أي ذكر للموافقة يعمل ويبقى «غير مطلوبة»."""
    client = env["client"]
    created = client.post("/api/sales/invoices/", {
        "customer": env["customer"].id, "currency": env["cur"].CurrencyID,
        "invoice_date": "2026-06-16", "invoice_type": "credit", "stock_on_post": False,
        "auto_post": False,
        "lines": [{"product": env["product"].id, "quantity": "1", "unit_price": "10"}],
    }, format="json")
    assert created.status_code == 201, created.content
    inv_id = created.json()["id"]
    assert client.post(f"/api/sales/invoices/{inv_id}/post/", {}, format="json").status_code == 200
    inv = SalesInvoice.objects.get(pk=inv_id)
    assert inv.status == SalesInvoice.STATUS_POSTED
    assert inv.customer_approval_status == "not_required"


def test_approval_fields_are_not_writable_through_the_normal_update(env):
    inv = _invoice(env)[0]
    res = env["client"].patch(
        URLS["invoice"].format(id=inv.id),
        {"customer_approval_status": "approved", "notes": "x"}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.customer_approval_status == "not_required"
    assert inv.notes == "x"


# ── نقطة الموافقة لكل نوع ──

@pytest.mark.parametrize("kind", KINDS)
def test_pending_then_approved_stores_decision_and_logs(env, kind):
    doc = _make(env, kind)
    client = env["client"]

    res = _post(client, kind, doc, status="pending")
    assert res.status_code == 200, res.content
    assert res.json()["customer_approval_status"] == "pending"
    doc.refresh_from_db()
    assert doc.customer_approval_status == "pending"
    assert doc.customer_approval_at is None
    assert doc.customer_approval_fingerprint == ""

    res = _post(client, kind, doc, status="approved", by_name="أبو أحمد", note="استلمت كل شيء")
    assert res.status_code == 200, res.content
    body = res.json()
    assert body["customer_approval_status"] == "approved"
    assert body["customer_approval_status_display"] == "وافق الزبون"
    assert body["customer_approval_by"] == "أبو أحمد"
    assert body["customer_approval_note"] == "استلمت كل شيء"
    assert body["customer_approval_at"]
    doc.refresh_from_db()
    assert doc.customer_approval_status == "approved"
    assert doc.customer_approval_by == "أبو أحمد"
    assert doc.customer_approval_at is not None
    assert doc.customer_approval_fingerprint == approval_fingerprint(doc)
    assert len(doc.customer_approval_fingerprint) == 64

    rows = list(_events(env["tenant"], kind, doc.id).order_by("id"))
    assert len(rows) == 2
    approved = rows[-1]
    assert "وافق الزبون" in approved.description
    assert "أبو أحمد" in approved.description
    assert "استلمت كل شيء" in approved.description
    assert approved.metadata["old_status"] == "pending"
    assert approved.metadata["new_status"] == "approved"
    assert approved.metadata["by_name"] == "أبو أحمد"
    assert approved.metadata["note"] == "استلمت كل شيء"
    assert rows[0].description == "بانتظار موافقة الزبون"


@pytest.mark.parametrize("kind", KINDS)
def test_rejected_path(env, kind):
    doc = _make(env, kind)
    res = _post(env["client"], kind, doc, status="rejected", by_name="خالد", note="الكمية ناقصة")
    assert res.status_code == 200, res.content
    doc.refresh_from_db()
    assert doc.customer_approval_status == "rejected"
    assert doc.customer_approval_at is not None
    assert doc.customer_approval_fingerprint
    event = _events(env["tenant"], kind, doc.id).get()
    assert "اعترض الزبون" in event.description
    assert "خالد" in event.description
    assert event.metadata["old_status"] == "not_required"
    assert event.metadata["new_status"] == "rejected"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("bad", ["not_required", "bogus", ""])
def test_not_required_and_unknown_statuses_are_refused(env, kind, bad):
    doc = _make(env, kind)
    res = _post(env["client"], kind, doc, status=bad)
    assert res.status_code == 400, res.content
    doc.refresh_from_db()
    assert doc.customer_approval_status == "not_required"
    assert not _events(env["tenant"], kind, doc.id).exists()


@pytest.mark.parametrize("kind", KINDS)
def test_missing_status_and_oversized_text_are_refused(env, kind):
    doc = _make(env, kind)
    assert env["client"].post(_approve_url(kind, doc), {}, format="json").status_code == 400
    assert _post(env["client"], kind, doc, status="approved", by_name="ا" * 151).status_code == 400
    assert _post(env["client"], kind, doc, status="approved", note="ا" * 501).status_code == 400
    doc.refresh_from_db()
    assert doc.customer_approval_status == "not_required"


def test_cancelled_invoice_and_delivery_are_refused(env):
    inv = _invoice(env)[0]
    SalesInvoice.objects.filter(pk=inv.pk).update(status=SalesInvoice.STATUS_CANCELLED)
    res = _post(env["client"], "invoice", inv, status="approved", by_name="س")
    assert res.status_code == 400, res.content
    assert "ملغ" in res.json()["error"]

    _inv, _line, delivery = _delivery(env)
    DeliveryOrder.objects.filter(pk=delivery.pk).update(status=DeliveryOrder.STATUS_CANCELLED)
    res = _post(env["client"], "delivery", delivery, status="approved", by_name="س")
    assert res.status_code == 400, res.content
    assert "ملغ" in res.json()["error"]


def test_approval_is_allowed_after_posting_and_after_delivery(env):
    inv = _invoice(env)[0]
    client = env["client"]
    assert client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    assert _post(client, "invoice", inv, status="approved", by_name="س").status_code == 200

    pay = _payment(env)
    assert client.post(f"/api/sales/payments/{pay.id}/post/", {}, format="json").status_code == 200
    assert _post(client, "payment", pay, status="approved", by_name="س").status_code == 200

    _inv, _line, delivery = _delivery(env)
    assert delivery.status == DeliveryOrder.STATUS_DELIVERED
    assert _post(client, "delivery", delivery, status="approved", by_name="س").status_code == 200


def test_another_tenants_document_is_404(env):
    other_owner = User.objects.create_user(username="ca-other", password="x")
    other = create_company("شركة أخرى", other_owner)
    doc = _make(env, "invoice")
    res = _post(_client(other_owner, other), "invoice", doc, status="approved", by_name="س")
    assert res.status_code == 404, res.content
    doc.refresh_from_db()
    assert doc.customer_approval_status == "not_required"


# ── الصلاحيات ──

@pytest.mark.parametrize("kind", KINDS)
def test_viewer_gets_403(env, kind):
    doc = _make(env, kind)
    viewer = _member(env["tenant"], "ca-viewer", "viewer")
    res = _post(_client(viewer, env["tenant"]), kind, doc, status="approved", by_name="س")
    assert res.status_code == 403, res.content
    doc.refresh_from_db()
    assert doc.customer_approval_status == "not_required"


@pytest.mark.parametrize("kind", ["invoice", "delivery"])
def test_staff_may_record_approval_on_invoice_and_delivery(env, kind):
    doc = _make(env, kind)
    staff = _member(env["tenant"], "ca-staff", "staff")
    res = _post(_client(staff, env["tenant"]), kind, doc, status="approved", by_name="س")
    assert res.status_code == 200, res.content


def test_payment_needs_the_payment_create_permission(env):
    pay = _payment(env)
    staff = _member(env["tenant"], "ca-staff", "staff")
    assert _post(_client(staff, env["tenant"]), "payment", pay,
                 status="approved", by_name="س").status_code == 403
    granted = _member(env["tenant"], "ca-granted", "staff", grant=["sales.payment.create"])
    res = _post(_client(granted, env["tenant"]), "payment", pay, status="approved", by_name="س")
    assert res.status_code == 200, res.content


# ── الإسقاط التلقائي ──

def _approve(env, kind, doc):
    res = _post(env["client"], kind, doc, status="approved", by_name="الزبون", note="تمام")
    assert res.status_code == 200, res.content
    doc.refresh_from_db()
    assert doc.customer_approval_status == "approved"


def _drop_events(tenant, kind, doc_id):
    return [e for e in _events(tenant, kind, doc_id).order_by("id")
            if "سقطت موافقة الزبون" in e.description]


def test_invoice_line_edit_after_approval_drops_to_pending_and_logs(env):
    inv, line = _invoice(env)
    _approve(env, "invoice", inv)
    res = env["client"].patch(URLS["invoice"].format(id=inv.id), {"lines": [
        {"id": line.id, "product": env["product"].id, "quantity": "7", "unit_price": "100"},
    ]}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["customer_approval_status"] == "pending"
    inv.refresh_from_db()
    assert inv.customer_approval_status == "pending"
    assert inv.customer_approval_at is None
    assert inv.customer_approval_fingerprint == ""
    drops = _drop_events(env["tenant"], "invoice", inv.id)
    assert len(drops) == 1
    assert "عُدّل المستند بعد موافقته" in drops[0].description
    assert drops[0].metadata["old_status"] == "approved"
    assert drops[0].metadata["new_status"] == "pending"
    assert drops[0].metadata["by_name"] == "الزبون"
    assert drops[0].metadata["note"] == "تمام"


def test_invoice_notes_only_edit_keeps_approval(env):
    inv, _line = _invoice(env)
    _approve(env, "invoice", inv)
    fingerprint = inv.customer_approval_fingerprint
    res = env["client"].patch(
        URLS["invoice"].format(id=inv.id), {"notes": "ملاحظة جديدة"}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.notes == "ملاحظة جديدة"
    assert inv.customer_approval_status == "approved"
    assert inv.customer_approval_fingerprint == fingerprint
    assert not _drop_events(env["tenant"], "invoice", inv.id)


def test_invoice_header_money_edit_drops_approval(env):
    inv, _line = _invoice(env)
    _approve(env, "invoice", inv)
    res = env["client"].patch(
        URLS["invoice"].format(id=inv.id), {"invoice_discount": "10"}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.customer_approval_status == "pending"


def test_posted_invoice_notes_edit_keeps_approval(env):
    inv, _line = _invoice(env)
    client = env["client"]
    assert client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    _approve(env, "invoice", inv)
    res = client.patch(URLS["invoice"].format(id=inv.id), {"notes": "بعد الترحيل"}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.notes == "بعد الترحيل"
    assert inv.customer_approval_status == "approved"
    assert not _drop_events(env["tenant"], "invoice", inv.id)


def test_payment_amount_edit_after_approval_drops_to_pending(env):
    pay = _payment(env)
    _approve(env, "payment", pay)
    res = env["client"].patch(URLS["payment"].format(id=pay.id), {"amount": "150"}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["customer_approval_status"] == "pending"
    pay.refresh_from_db()
    assert pay.amount == Decimal("150.00")
    assert pay.customer_approval_status == "pending"
    assert pay.customer_approval_fingerprint == ""
    assert len(_drop_events(env["tenant"], "payment", pay.id)) == 1


def test_payment_notes_only_edit_keeps_approval(env):
    pay = _payment(env)
    _approve(env, "payment", pay)
    res = env["client"].patch(URLS["payment"].format(id=pay.id), {"notes": "ملاحظة"}, format="json")
    assert res.status_code == 200, res.content
    pay.refresh_from_db()
    assert pay.customer_approval_status == "approved"
    assert not _drop_events(env["tenant"], "payment", pay.id)


def test_posted_payment_notes_edit_keeps_approval(env):
    pay = _payment(env)
    client = env["client"]
    assert client.post(f"/api/sales/payments/{pay.id}/post/", {}, format="json").status_code == 200
    _approve(env, "payment", pay)
    res = client.patch(URLS["payment"].format(id=pay.id), {"notes": "بعد الترحيل"}, format="json")
    assert res.status_code == 200, res.content
    pay.refresh_from_db()
    assert pay.customer_approval_status == "approved"
    assert not _drop_events(env["tenant"], "payment", pay.id)


def test_delivery_edit_carries_approval_to_the_new_row_and_drops_on_line_change(env):
    inv, line, delivery = _delivery(env)
    _approve(env, "delivery", delivery)
    client = env["client"]

    # نفس البنود: الصفّ الجديد يحمل الموافقة كما هي (لم يتغيّر المحتوى).
    same = client.patch(URLS["delivery"].format(id=delivery.id), {
        "invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "2"}],
        "notes": "ملاحظة فقط",
    }, format="json")
    assert same.status_code == 200, same.content
    new_id = same.json()["id"]
    assert new_id != delivery.id
    assert not DeliveryOrder.objects.filter(pk=delivery.id).exists()
    carried = DeliveryOrder.objects.get(pk=new_id)
    assert carried.customer_approval_status == "approved"
    assert carried.customer_approval_by == "الزبون"
    assert carried.customer_approval_at is not None
    assert carried.customer_approval_fingerprint == approval_fingerprint(carried)
    assert same.json()["customer_approval_status"] == "approved"
    assert not _drop_events(env["tenant"], "delivery", new_id)

    # كمية مختلفة: تسقط إلى «بانتظار» على الصفّ الجديد.
    changed = client.patch(URLS["delivery"].format(id=new_id), {
        "invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "3"}],
    }, format="json")
    assert changed.status_code == 200, changed.content
    final_id = changed.json()["id"]
    final = DeliveryOrder.objects.get(pk=final_id)
    assert final.customer_approval_status == "pending"
    assert final.customer_approval_fingerprint == ""
    assert changed.json()["customer_approval_status"] == "pending"
    assert len(_drop_events(env["tenant"], "delivery", final_id)) == 1


def test_delivery_edit_keeps_not_required_untouched(env):
    inv, line, delivery = _delivery(env)
    res = env["client"].patch(URLS["delivery"].format(id=delivery.id), {
        "invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "3"}],
    }, format="json")
    assert res.status_code == 200, res.content
    new = DeliveryOrder.objects.get(pk=res.json()["id"])
    assert new.customer_approval_status == "not_required"
    assert not ActivityLog.objects.filter(action="customer_approval").exists()


def test_pending_and_rejected_documents_are_not_touched_by_edits(env):
    inv, line = _invoice(env)
    assert _post(env["client"], "invoice", inv, status="rejected", by_name="خالد").status_code == 200
    res = env["client"].patch(URLS["invoice"].format(id=inv.id), {"lines": [
        {"id": line.id, "product": env["product"].id, "quantity": "9", "unit_price": "100"},
    ]}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.customer_approval_status == "rejected"
    assert not _drop_events(env["tenant"], "invoice", inv.id)


def test_reapproval_after_a_drop_works(env):
    pay = _payment(env)
    _approve(env, "payment", pay)
    env["client"].patch(URLS["payment"].format(id=pay.id), {"amount": "150"}, format="json")
    _approve(env, "payment", pay)
    pay.refresh_from_db()
    assert pay.customer_approval_fingerprint == approval_fingerprint(pay)


# ── البصمة ──

def test_fingerprint_ignores_notes_and_decimal_spelling_but_sees_money(env):
    pay = _payment(env)
    base = approval_fingerprint(pay)
    assert approval_fingerprint(pay) == base
    pay.notes = "لا أثر"
    assert approval_fingerprint(pay) == base
    pay.amount = Decimal("100.000")
    assert approval_fingerprint(pay) == base
    pay.amount = Decimal("100.01")
    assert approval_fingerprint(pay) != base


def test_payment_fingerprint_sees_attached_cheques(env):
    pay = _payment(env)
    base = approval_fingerprint(pay)
    Cheque.objects.create(
        tenant=env["tenant"], customer_payment=pay, partner=env["customer"],
        direction="Incoming", status="Draft", cheque_number="123", amount=Decimal("40"),
        currency=env["cur"], due_date="2026-08-01")
    with_cheque = approval_fingerprint(pay)
    assert with_cheque != base
    Cheque.objects.filter(customer_payment=pay).update(amount=Decimal("41"))
    assert approval_fingerprint(pay) != with_cheque


def test_invoice_fingerprint_sees_lines_and_ignores_notes(env):
    inv, line = _invoice(env)
    base = approval_fingerprint(inv)
    inv.notes = "x"
    assert approval_fingerprint(inv) == base
    SalesInvoiceLine.objects.filter(pk=line.pk).update(quantity=Decimal("5.0000"))
    assert approval_fingerprint(inv) == base
    SalesInvoiceLine.objects.filter(pk=line.pk).update(unit_price=Decimal("101"))
    assert approval_fingerprint(inv) != base


# ── التزامن المتفائل ──

@pytest.mark.parametrize("kind", KINDS)
def test_endpoint_honours_if_match_and_returns_a_moved_etag(env, kind):
    doc = _make(env, kind)
    client = env["client"]
    before = client.get(URLS[kind].format(id=doc.id))["ETag"]

    # نسخةٌ قديمة ⇒ 412 ولا كتابة
    doc.refresh_from_db()
    doc.notes = "كتبه الطرف الآخر"
    doc.save()
    stale = client.post(_approve_url(kind, doc), {"status": "approved", "by_name": "س"},
                        format="json", HTTP_IF_MATCH=before)
    assert stale.status_code == 412, stale.content
    assert stale.json()["code"] == "stale_document"
    doc.refresh_from_db()
    assert doc.customer_approval_status == "not_required"
    assert not _events(env["tenant"], kind, doc.id).exists()

    # نسخةٌ حالية ⇒ تنجح، والـETag الجديد يتحرّك ويطابق القاعدة
    current = etag_for(doc)
    ok = client.post(_approve_url(kind, doc), {"status": "approved", "by_name": "س"},
                     format="json", HTTP_IF_MATCH=current)
    assert ok.status_code == 200, ok.content
    assert ok["ETag"] != current
    doc.refresh_from_db()
    assert ok["ETag"] == etag_for(doc)
