"""THA-132 — تبويبات سياق الفاتورة: أثر المخزون · حساب العميل · المرفقات.

المهمة ليست إضافةً بحتة: «رصيد قبل/بعد» كان معروضاً على الشاشة فعلاً محسوباً
من `remaining_balance` مطروحاً من رصيد **اليوم** — رقمٌ لا يطابق كشف الحساب
(فاتورة مدفوعة بالكامل كانت تُظهر أثراً صفرياً وهي دائنةُ ذمم بكامل إجماليها).
هنا تُثبَّت المطابقة بالبناء: نفس `partner_account_statement` بمرساة المستند.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account
from accounting.services import create_fiscal_year, partner_account_statement
from core.models import SystemAttachment
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="ctxtabs", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة التبويبات", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1103-C", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل السياق", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="CTX-1", name_ar="منتج السياق",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("100"),
        unit_cost=Decimal("10"), reference_type="OPENING", reference_id=0,
        movement_date="2026-06-01", tenant=tenant)
    product.refresh_from_db()
    cogs = Account.objects.create(
        tenant=tenant, code="5101-C", name="تكلفة", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-C", name="مخزون", account_type="Asset", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv_acc
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    return tenant, owner, cur, customer, product


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _invoice(tenant, cur, customer, product, *, number, qty="10", price="100",
             stock_on_post=True):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=stock_on_post)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(qty), unit_price=Decimal(price))
    return inv


# ── تبويب أثر المخزون ───────────────────────────────────────────────────────

def test_stock_tab_lists_only_this_invoices_movements(env):
    """حركات هذه الفاتورة وحدها — لا حركات فاتورة أخرى لنفس المنتج."""
    tenant, owner, cur, customer, product = env
    mine = _invoice(tenant, cur, customer, product, number="CTX-A", qty="10")
    other = _invoice(tenant, cur, customer, product, number="CTX-B", qty="7")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{mine.id}/post/", {}, format="json").status_code == 200
    assert c.post(f"/api/sales/invoices/{other.id}/post/", {}, format="json").status_code == 200

    resp = c.get(f"/api/sales/invoices/{mine.id}/stock-movements/")
    assert resp.status_code == 200, resp.content[:300]
    body = resp.data
    assert body["count"] == 1
    row = body["results"][0]
    assert row["qty_out"] == "10.0000"
    assert row["product_id"] == product.id
    # لقطتا المخزون مخزَّنتان لا محسوبتان: 100 قبل، 90 بعد.
    assert Decimal(row["quantity_before"]) == Decimal("100")
    assert Decimal(row["running_balance"]) == Decimal("90")
    # «رقم الحركة» (مسلسل الأصيل) يصل الواجهة.
    assert row["id"] == StockMovement.objects.get(
        reference_type="SALE", reference_id=mine.id).id


def test_stock_tab_declares_reason_when_empty(env):
    """مسودّة: صفر صفوف **مع سبب** — الجدول الفارغ بلا تفسير يُقرأ كعطل."""
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-DRAFT")
    c = _client(owner, tenant)

    resp = c.get(f"/api/sales/invoices/{inv.id}/stock-movements/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0
    assert resp.data["is_posted"] is False
    assert resp.data["stock_on_post"] is True


def test_stock_tab_flags_deferred_deduction(env):
    """مرحّلة بلا خصم عند الترحيل: فارغة الآن، والحمولة تقول لماذا."""
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-DEF", stock_on_post=False)
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    resp = c.get(f"/api/sales/invoices/{inv.id}/stock-movements/")
    assert resp.data["count"] == 0
    assert resp.data["is_posted"] is True
    assert resp.data["stock_on_post"] is False


def test_stock_tab_isolated_across_tenants(env):
    """فاتورة شركة أخرى لا تُبلَغ أصلاً (العدد تسريبٌ أيضاً)."""
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-ISO")
    intruder = User.objects.create_user(username="ctx_intruder", password="x")
    other_tenant = create_company("شركة غريبة", intruder)
    c = APIClient()
    c.force_authenticate(user=intruder)
    c.credentials(HTTP_X_TENANT_ID=str(other_tenant.TenantID))

    assert c.get(f"/api/sales/invoices/{inv.id}/stock-movements/").status_code == 404


# ── تبويب حساب العميل: قبل/بعد يطابق كشف الحساب ─────────────────────────────

def test_ledger_tab_effect_is_full_total_not_remaining(env):
    """العطل الأصلي: فاتورة محصَّلة بالكامل كانت تُظهر أثراً صفرياً.

    القيد يدين الذمم بكامل الإجمالي والتحصيل قيدٌ منفصل، فأثر الفاتورة على
    الحساب = إجماليها مهما بلغ المدفوع.
    """
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-PAID", qty="10", price="100")
    c = _client(owner, tenant)
    assert c.post(
        f"/api/sales/invoices/{inv.id}/collect/",
        {"post_invoice": True, "cash": "1000"}, format="json",
    ).status_code in (200, 201)

    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("1000.00")  # محصَّلة بالكامل

    resp = c.get(f"/api/sales/invoices/{inv.id}/customer-ledger/")
    assert resp.status_code == 200, resp.content[:300]
    anchor = resp.data["anchor"]
    assert anchor is not None
    # الأثر = كامل الإجمالي، لا صفر.
    assert Decimal(anchor["effect"]) == Decimal("1000.00")
    assert Decimal(anchor["balance_after"]) - Decimal(anchor["balance_before"]) \
        == Decimal("1000.00")


def test_ledger_tab_matches_full_statement_row(env):
    """المطابقة بالبناء: نفس الأرقام التي يعطيها كشف الحساب لسطر الفاتورة."""
    tenant, owner, cur, customer, product = env
    first = _invoice(tenant, cur, customer, product, number="CTX-S1", qty="2", price="50")
    target = _invoice(tenant, cur, customer, product, number="CTX-S2", qty="3", price="50")
    later = _invoice(tenant, cur, customer, product, number="CTX-S3", qty="4", price="50")
    c = _client(owner, tenant)
    for inv in (first, target, later):
        assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    tab = c.get(f"/api/sales/invoices/{target.id}/customer-ledger/").data
    full = partner_account_statement(
        tenant_id=tenant.TenantID, partner_id=customer.id, is_supplier=False,
        limit=200, ordering="oldest",
    )
    target_rows = [
        r for r in full["results"]
        if r["reference_type"] == "SALES_INVOICE" and r["reference_id"] == target.id
    ]
    assert len(target_rows) == 1
    assert tab["anchor"]["balance_before"] == target_rows[0]["balance_before"]
    assert tab["anchor"]["balance_after"] == target_rows[0]["running_balance"]
    # 100 قبلها (فاتورة 2×50) و150 أثرها ⇒ 250 بعدها.
    assert Decimal(tab["anchor"]["balance_before"]) == Decimal("100.00")
    assert Decimal(tab["anchor"]["balance_after"]) == Decimal("250.00")


def test_ledger_tab_window_contains_old_anchor(env):
    """فاتورة قديمة تلتها حركات كثيرة تبقى داخل النافذة — لا «أحدث N» أعمى."""
    tenant, owner, cur, customer, product = env
    c = _client(owner, tenant)
    oldest = _invoice(tenant, cur, customer, product, number="CTX-OLD", qty="1", price="10")
    assert c.post(f"/api/sales/invoices/{oldest.id}/post/", {}, format="json").status_code == 200
    for n in range(8):
        later = _invoice(
            tenant, cur, customer, product, number=f"CTX-L{n}", qty="1", price="10")
        assert c.post(
            f"/api/sales/invoices/{later.id}/post/", {}, format="json").status_code == 200

    tab = c.get(f"/api/sales/invoices/{oldest.id}/customer-ledger/?limit=3").data
    assert tab["anchor"] is not None
    assert any(r.get("is_anchor") for r in tab["results"]), tab["results"]
    assert Decimal(tab["anchor"]["balance_before"]) == Decimal("0.00")


def test_ledger_tab_draft_has_no_anchor(env):
    """مسودّة: لا مرساة وحالةٌ معلنة — لا خطأ ولا صفرٌ يبدو رصيداً."""
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-NOJ")
    c = _client(owner, tenant)

    resp = c.get(f"/api/sales/invoices/{inv.id}/customer-ledger/")
    assert resp.status_code == 200
    assert resp.data["anchor"] is None


def test_statement_unchanged_without_anchor(env):
    """بلا مرساة: الحمولة كما كانت حرفياً — مستهلكو بطاقة الطرف لا يتأثرون."""
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-PLAIN")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    plain = partner_account_statement(
        tenant_id=tenant.TenantID, partner_id=customer.id, is_supplier=False)
    assert "anchor" not in plain
    assert all("is_anchor" not in r for r in plain["results"])


# ── تبويب المرفقات ──────────────────────────────────────────────────────────

def test_attachment_can_be_added_to_posted_invoice(env):
    """جوهر القرار: الفاتورة المرحّلة لا تُعدَّل، والمرفق يُضاف إليها رغم ذلك."""
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-ATT")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED

    url = "https://res.cloudinary.com/demo/image/upload/receipt.jpg"
    created = c.post(
        f"/api/sales/invoices/{inv.id}/attachments/", {"url": url}, format="json")
    assert created.status_code == 201, created.content[:300]
    assert created.data["file_type"] == "Image"
    assert created.data["filename"] == "receipt.jpg"

    listed = c.get(f"/api/sales/invoices/{inv.id}/attachments/")
    assert [a["url"] for a in listed.data] == [url]

    gone = c.delete(
        f"/api/sales/invoices/{inv.id}/attachments/{created.data['id']}/")
    assert gone.status_code == 204
    assert c.get(f"/api/sales/invoices/{inv.id}/attachments/").data == []


def test_attachment_pdf_detected_and_duplicate_is_idempotent(env):
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-PDF")
    c = _client(owner, tenant)
    url = "https://res.cloudinary.com/demo/raw/upload/contract.pdf"

    first = c.post(f"/api/sales/invoices/{inv.id}/attachments/", {"url": url}, format="json")
    assert first.data["file_type"] == "PDF"
    c.post(f"/api/sales/invoices/{inv.id}/attachments/", {"url": url}, format="json")

    assert SystemAttachment.objects.filter(
        related_table="sales_invoices", related_id=inv.id).count() == 1


def test_attachment_rejects_non_http_url(env):
    tenant, owner, cur, customer, product = env
    inv = _invoice(tenant, cur, customer, product, number="CTX-BAD")
    c = _client(owner, tenant)

    resp = c.post(
        f"/api/sales/invoices/{inv.id}/attachments/",
        {"url": "javascript:alert(1)"}, format="json")
    assert resp.status_code == 400


def test_attachment_delete_scoped_to_its_invoice(env):
    """معرّف مرفقٍ من فاتورة أخرى يعود «غير موجود» ولا يُحذف."""
    tenant, owner, cur, customer, product = env
    a = _invoice(tenant, cur, customer, product, number="CTX-X1")
    b = _invoice(tenant, cur, customer, product, number="CTX-X2")
    c = _client(owner, tenant)
    made = c.post(
        f"/api/sales/invoices/{a.id}/attachments/",
        {"url": "https://res.cloudinary.com/demo/image/upload/a.jpg"}, format="json")

    resp = c.delete(f"/api/sales/invoices/{b.id}/attachments/{made.data['id']}/")
    assert resp.status_code == 404
    assert SystemAttachment.objects.filter(id=made.data["id"]).exists()
