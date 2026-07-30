"""فاتورة مبيعات: حالة التسليم (غير مسلَّمة/جزئياً/مسلَّمة) والتسليم ببنوده.

يغطي المطلب: «عمود حالة التسليم للفواتير، وعند التسليم تُعرض كل بنود الفاتورة
وأختار ما سُلِّم — عندما يكون خصم المخزون مع الترحيل غير مفعّل».
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement, Warehouse
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import DeliveryOrder, SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="deliv", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة التسليم", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-D", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="DL-1", name_ar="صنف التسليم",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("100"),
        unit_cost=Decimal("10"), reference_type="OPENING", reference_id=0,
        movement_date="2026-06-01", tenant=tenant)
    product.refresh_from_db()
    cogs = Account.objects.create(
        tenant=tenant, code="5101-D", name="تكلفة", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-D", name="مخزون", account_type="Asset", is_active=True)
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


def _invoice(tenant, cur, customer, product, *, number, stock_on_post, qty="10"):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=stock_on_post)
    line = SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(qty), unit_price=Decimal("100"))
    return inv, line


def test_stock_on_post_invoice_is_delivered_on_post(env):
    """الفاتورة التي تخصم المخزون عند الترحيل تُعدّ مسلَّمة لحظتها — بلا إرسالية."""
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-1", stock_on_post=True)
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    inv.refresh_from_db()
    line.refresh_from_db()
    assert inv.delivery_status == SalesInvoice.DELIVERY_FULL
    assert line.delivered_quantity == Decimal("10.0000")


def test_posted_invoice_without_stock_on_post_is_not_delivered(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-2", stock_on_post=False)
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    inv.refresh_from_db()
    assert inv.delivery_status == SalesInvoice.DELIVERY_NOT
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("100.0000")  # لم يُخصم شيء بعد
    assert not StockMovement.objects.filter(
        reference_type="SALE", reference_id=inv.id).exists()


def test_delivery_lines_endpoint_lists_remaining(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-3", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.get(f"/api/sales/invoices/{inv.id}/delivery-lines/")
    assert res.status_code == 200, res.content
    data = res.json()
    assert data["delivery_status"] == SalesInvoice.DELIVERY_NOT
    assert len(data["lines"]) == 1
    row = data["lines"][0]
    assert row["line_id"] == line.id
    assert Decimal(row["remaining_quantity"]) == Decimal("10")


def test_partial_then_full_delivery(env):
    """تسليم جزئي ⇒ «مسلَّمة جزئياً»، وإكمال المتبقي ⇒ «مسلَّمة»؛
    المخزون وقيد التكلفة على المُسلَّم فعلاً لا على كامل الفاتورة."""
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-4", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 4}]}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["delivery_status"] == SalesInvoice.DELIVERY_PARTIAL

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("96.0000")
    line.refresh_from_db()
    assert line.delivered_quantity == Decimal("4.0000")

    cogs_journals = JournalHeader.objects.filter(
        tenant=tenant, reference_type="SALES_DELIVERY_COGS", reference_id=inv.id)
    assert cogs_journals.count() == 1
    # 4 وحدات × متوسط تكلفة 10
    assert cogs_journals.first().lines.filter(debit=Decimal("40.00")).exists()

    # المتبقي
    res = c.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 6}]}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["delivery_status"] == SalesInvoice.DELIVERY_FULL

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("90.0000")
    # كل إرسالية قيد تكلفة مستقل — لا يُعاد استعمال قيد الأولى
    assert cogs_journals.count() == 2
    assert DeliveryOrder.objects.filter(invoice=inv).count() == 2


def test_cannot_deliver_more_than_remaining(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-5", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 11}]}, format="json")
    assert res.status_code == 400, res.content
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("100.0000")


def test_deliver_rejected_when_stock_deducted_on_post(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-6", stock_on_post=True)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 1}]}, format="json")
    assert res.status_code == 400, res.content
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("90.0000")  # خصم الترحيل فقط


def test_deliver_rejected_on_draft(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-7", stock_on_post=False)
    c = _client(owner, tenant)
    res = c.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 1}]}, format="json")
    assert res.status_code == 400, res.content


def test_unpost_resets_delivery_state(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-8", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    c.post(f"/api/sales/invoices/{inv.id}/deliver/",
           {"lines": [{"line_id": line.id, "quantity": 10}]}, format="json")

    res = c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json")
    assert res.status_code == 200, res.content

    inv.refresh_from_db()
    line.refresh_from_db()
    assert inv.delivery_status == SalesInvoice.DELIVERY_NOT
    assert line.delivered_quantity == Decimal("0.0000")
    assert DeliveryOrder.objects.filter(invoice=inv).count() == 0
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("100.0000")
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type="SALES_DELIVERY_COGS", reference_id=inv.id).exists()


def test_stock_on_post_creates_auto_delivery_note(env):
    """الخصم مع الترحيل يوثَّق بإرسالية تلقائية بكامل الكمية."""
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-10", stock_on_post=True)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.get(f"/api/sales/delivery-orders/?invoice={inv.id}")
    assert res.status_code == 200, res.content
    data = res.json()
    rows = data["results"] if isinstance(data, dict) else data
    assert len(rows) == 1
    assert rows[0]["auto_created"] is True
    assert rows[0]["delivery_number"].startswith("DN-")
    assert rows[0]["invoice_number"] == "D-10"
    assert Decimal(rows[0]["total_quantity"]) == Decimal("10")
    # لا حركة مخزون إضافية — الترحيل خصمها مرة واحدة
    assert StockMovement.objects.filter(
        reference_type="SALE", reference_id=inv.id).count() == 1


def test_create_delivery_note_from_notes_screen_moves_stock(env):
    """إنشاء إرسالية من شاشة الإرساليات = تسليم فعلي (مخزون + قيد تكلفة)."""
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-11", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "delivery_date": "2026-06-16", "notes": "سائق أحمد",
         "lines": [{"line_id": line.id, "quantity": 3}]}, format="json")
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["delivery_number"].startswith("DN-")
    assert body["delivery_date"] == "2026-06-16"
    assert len(body["lines"]) == 1
    assert Decimal(body["lines"][0]["quantity"]) == Decimal("3")
    assert Decimal(body["lines"][0]["ordered_quantity"]) == Decimal("10")

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("97.0000")
    inv.refresh_from_db()
    assert inv.delivery_status == SalesInvoice.DELIVERY_PARTIAL


def test_delivery_notes_filtered_by_invoice(env):
    tenant, owner, cur, customer, product = env
    inv_a, line_a = _invoice(tenant, cur, customer, product, number="D-12", stock_on_post=False)
    inv_b, line_b = _invoice(tenant, cur, customer, product, number="D-13", stock_on_post=False)
    c = _client(owner, tenant)
    for inv, line in ((inv_a, line_a), (inv_b, line_b)):
        c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
        c.post(f"/api/sales/invoices/{inv.id}/deliver/",
               {"lines": [{"line_id": line.id, "quantity": 1}]}, format="json")

    res = c.get(f"/api/sales/delivery-orders/?invoice={inv_a.id}")
    rows = res.json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert len(rows) == 1
    assert rows[0]["invoice"] == inv_a.id


def test_standalone_delivery_note_moves_stock_against_clearing(env):
    """سند تسليم بلا فاتورة: مدين «بضاعة مسلَّمة لم تُفوتَر» / دائن المخزون."""
    tenant, owner, cur, customer, product = env
    c = _client(owner, tenant)
    res = c.post(
        "/api/sales/delivery-orders/",
        {"partner": customer.id, "delivery_date": "2026-06-20",
         "customer_ref": "طلب 55", "notes": "خرجت قبل الفاتورة",
         "lines": [{"product_id": product.id, "quantity": 5}]}, format="json")
    assert res.status_code == 201, res.content
    body = res.json()
    assert body["is_standalone"] is True
    assert body["invoice"] is None
    assert body["customer_ref"] == "طلب 55"
    assert body["doc_label"] == "سند تسليم"

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("95.0000")
    clearing = Account.objects.get(tenant=tenant, code="1108")
    jh = JournalHeader.objects.get(
        tenant=tenant, reference_type="DELIVERY_NOTE", reference_id=body["id"])
    # 5 وحدات × متوسط تكلفة 10
    assert jh.lines.filter(account=clearing, debit=Decimal("50.00")).exists()


def test_standalone_delivery_blocked_when_setting_disabled(env):
    tenant, owner, cur, customer, product = env
    ss = get_or_create_sales_settings(tenant)
    ss.allow_standalone_delivery = False
    ss.save(update_fields=["allow_standalone_delivery"])
    c = _client(owner, tenant)
    res = c.post(
        "/api/sales/delivery-orders/",
        {"partner": customer.id, "lines": [{"product_id": product.id, "quantity": 1}]},
        format="json")
    assert res.status_code == 400, res.content
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("100.0000")


def test_edit_delivery_note_reverses_old_and_applies_new(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-14", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    created = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 4}]},
        format="json")
    assert created.status_code == 201, created.content
    note_id = created.json()["id"]
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("96.0000")

    res = c.put(
        f"/api/sales/delivery-orders/{note_id}/",
        {"invoice": inv.id, "notes": "تصحيح",
         "lines": [{"line_id": line.id, "quantity": 7}]}, format="json")
    assert res.status_code == 200, res.content

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("93.0000")  # 7 لا 11
    line.refresh_from_db()
    assert line.delivered_quantity == Decimal("7.0000")
    assert DeliveryOrder.objects.filter(invoice=inv).count() == 1
    # قيد تكلفة واحد فقط (القديم حُذف مع الإرسالية القديمة)
    assert JournalHeader.objects.filter(
        tenant=tenant, reference_type="SALES_DELIVERY_COGS", reference_id=inv.id
    ).count() == 1


def test_delete_delivery_note_reverses_its_effect_only(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-15", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    first = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 3}]},
        format="json").json()
    c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 2}]},
        format="json")
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("95.0000")

    res = c.delete(f"/api/sales/delivery-orders/{first['id']}/")
    assert res.status_code == 200, res.content

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("98.0000")  # عادت 3 فقط
    line.refresh_from_db()
    assert line.delivered_quantity == Decimal("2.0000")
    inv.refresh_from_db()
    assert inv.delivery_status == SalesInvoice.DELIVERY_PARTIAL


def test_delivery_note_lines_expose_remaining(env):
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-16", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    created = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 4}]},
        format="json").json()

    assert Decimal(created["total_remaining"]) == Decimal("6")
    row = created["lines"][0]
    assert Decimal(row["ordered_quantity"]) == Decimal("10")
    assert Decimal(row["quantity"]) == Decimal("4")
    assert Decimal(row["delivered_total"]) == Decimal("4")
    assert Decimal(row["remaining_quantity"]) == Decimal("6")


def test_delivery_document_label_follows_settings(env):
    tenant, owner, cur, customer, product = env
    ss = get_or_create_sales_settings(tenant)
    ss.delivery_doc_label = "إذن تسليم"
    ss.save(update_fields=["delivery_doc_label"])
    inv, line = _invoice(tenant, cur, customer, product, number="D-17", stock_on_post=True)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    rows = c.get(f"/api/sales/delivery-orders/?invoice={inv.id}").json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert rows[0]["doc_label"] == "إذن تسليم"


def test_delivery_records_movement_in_the_chosen_warehouse(env):
    """T-DELIVPAR: المستودع بُعد على إرسالية البيع كما في إرسالية الشراء."""
    tenant, owner, cur, customer, product = env
    wh = Warehouse.objects.create(tenant=tenant, name="مستودع رام الله", is_default=True)
    inv, line = _invoice(tenant, cur, customer, product, number="D-18", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id,
         "lines": [{"line_id": line.id, "quantity": 4, "warehouse_id": wh.id}]},
        format="json")
    assert res.status_code == 201, res.content
    row = res.json()["lines"][0]
    assert row["warehouse"] == wh.id
    assert row["warehouse_name"] == "مستودع رام الله"

    movement = StockMovement.objects.get(
        reference_type="SALE", reference_id=inv.id, movement_type="OUT")
    assert movement.warehouse_id == wh.id


def test_standalone_delivery_records_the_chosen_warehouse(env):
    tenant, owner, cur, customer, product = env
    wh = Warehouse.objects.create(tenant=tenant, name="مستودع نابلس", is_default=True)
    c = _client(owner, tenant)
    res = c.post(
        "/api/sales/delivery-orders/",
        {"partner": customer.id,
         "lines": [{"product_id": product.id, "quantity": 2, "warehouse_id": wh.id}]},
        format="json")
    assert res.status_code == 201, res.content
    assert res.json()["lines"][0]["warehouse"] == wh.id
    movement = StockMovement.objects.get(
        reference_type="DELIVERY_NOTE", reference_id=res.json()["id"])
    assert movement.warehouse_id == wh.id


def test_delivery_rejects_a_warehouse_of_another_company(env):
    tenant, owner, cur, customer, product = env
    other_owner = User.objects.create_user(username="deliv-other", password="x")
    other = create_company("شركة أخرى للتسليم", other_owner)
    stranger = Warehouse.objects.create(tenant=other, name="مستودع غريب")
    inv, line = _invoice(tenant, cur, customer, product, number="D-19", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    res = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id,
         "lines": [{"line_id": line.id, "quantity": 1, "warehouse_id": stranger.id}]},
        format="json")
    assert res.status_code == 400, res.content
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("100.0000")


def test_outstanding_report_lists_only_invoices_awaiting_delivery(env):
    """تقرير البواقي = ما لم تخرج بضاعته فعلاً.

    الفاتورة التي تخصم المخزون عند الترحيل خرجت بضاعتها لحظتها ⇒ لا باقي لها،
    وهو ما يجعل منتقي الإرساليات يعرضها غير قابلة للاختيار لا مخفية.
    """
    tenant, owner, cur, customer, product = env
    partial, p_line = _invoice(
        tenant, cur, customer, product, number="D-20", stock_on_post=False)
    on_post, _ = _invoice(
        tenant, cur, customer, product, number="D-21", stock_on_post=True)
    c = _client(owner, tenant)
    for inv in (partial, on_post):
        c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    c.post(f"/api/sales/invoices/{partial.id}/deliver/",
           {"lines": [{"line_id": p_line.id, "quantity": 4}]}, format="json")

    res = c.get("/api/sales/delivery-orders/outstanding/")
    assert res.status_code == 200, res.content
    rows = res.json()["rows"]
    numbers = {r["invoice_number"] for r in rows}
    assert "D-20" in numbers
    # المخصومة عند الترحيل مسلَّمة بالكامل ⇒ لا باقي لها
    assert "D-21" not in numbers
    row = next(r for r in rows if r["invoice_number"] == "D-20")
    assert Decimal(row["remaining_quantity"]) == Decimal("6")


def test_legacy_delivery_order_endpoint_delivers_remaining(env):
    """المسار القديم (أمر إخراج ثم تسليمه) ما زال يعمل ويسلّم كامل المتبقي."""
    tenant, owner, cur, customer, product = env
    inv, line = _invoice(tenant, cur, customer, product, number="D-9", stock_on_post=False)
    c = _client(owner, tenant)
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")

    created = c.post(f"/api/sales/invoices/{inv.id}/delivery-order/", {}, format="json")
    assert created.status_code == 201, created.content
    do_id = created.json()["id"]
    res = c.post(f"/api/sales/delivery-orders/{do_id}/deliver/", {}, format="json")
    assert res.status_code == 200, res.content

    inv.refresh_from_db()
    assert inv.delivery_status == SalesInvoice.DELIVERY_FULL
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("90.0000")
