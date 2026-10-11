"""التزامن المتفائل: `ETag` على القراءة و`If-Match` على الكتابة — فاتورة البيع وسند القبض والإرسالية.

مستندٌ واحد يعدّله طرفان (تطبيق المستودع الخارجي والمحاسب في المنصة) ⇒ آخرُ كاتبٍ كان يمحو
تعديل الأول بصمت. العقد (RFC 9110):

- كل استجابة قراءة/إنشاء/تعديل تحمل `ETag` = توكن قويّ مقتبس من `updated_at` بدقّة الميكروثانية.
- PUT/PATCH بـ`If-Match` لا يطابق الحالي ⇒ 412 قبل أيّ كتابة؛ `*` أو غياب الترويسة ⇒ كما كان.
- الترحيل وإلغاؤه تعديلٌ حقيقي: يغيّر الـETag (لا يبقى توكن المسودة صالحاً على مستندٍ مرحَّل).
"""
import re
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from core.concurrency import etag_for, parse_if_match
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import CustomerPayment, DeliveryOrder, SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

ETAG_SHAPE = re.compile(r'^"\d+"$')


@pytest.fixture
def env():
    owner = User.objects.create_user(username="occ-owner", password="x")
    cur, _ = Currency.objects.get_or_create(
        Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True})
    tenant = create_company("شركة التزامن المتفائل", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-O", name="ذمم", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-O", name="صندوق", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="OCC-1", name_ar="منتج", quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"), unit_cost=Decimal("10"),
        reference_type="OPENING", reference_id=0, movement_date="2026-06-01", tenant=tenant)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = Account.objects.create(
        tenant=tenant, code="5101-O", name="تكلفة", account_type="Expense", is_active=True)
    ss.default_inventory_account = Account.objects.create(
        tenant=tenant, code="1104-O", name="مخزون", account_type="Asset", is_active=True)
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    client = APIClient()
    client.force_authenticate(user=owner)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return tenant, client, cur, cash, customer, product


def _draft_invoice(env, number="OCC-INV-1"):
    tenant, _client, cur, _cash, customer, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False)
    line = SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product, quantity=Decimal("5"),
        unit_price=Decimal("100"))
    return inv, line


def _etag(client, url):
    res = client.get(url)
    assert res.status_code == 200, res.content
    return res["ETag"]


def _touch(obj, **fields):
    """طرفٌ آخر يعدّل الصفّ: `save()` كاملاً فيتحرّك `updated_at`."""
    for name, value in fields.items():
        setattr(obj, name, value)
    obj.save()


# ── المساعدان الخالصان ──

def test_etag_is_quoted_microseconds_since_epoch():
    class Doc:
        updated_at = datetime(2026, 10, 11, 12, 0, 0, 123456, tzinfo=dt_timezone.utc)

    expected = int(datetime(2026, 10, 11, 12, 0, 0, tzinfo=dt_timezone.utc).timestamp()) * 1_000_000 + 123456
    assert etag_for(Doc) == f'"{expected}"'


def test_parse_if_match_handles_absent_star_and_comma_lists():
    assert parse_if_match(None) is None
    assert parse_if_match("") is None
    assert parse_if_match("   ") is None
    assert parse_if_match("*") == ["*"]
    assert parse_if_match('"1", "2" ,"3"') == ['"1"', '"2"', '"3"']


# ── فاتورة البيع ──

def test_invoice_retrieve_and_create_carry_etag(env):
    tenant, client, cur, _cash, customer, product = env
    inv, _ = _draft_invoice(env)
    res = client.get(f"/api/sales/invoices/{inv.id}/")
    assert res.status_code == 200, res.content
    assert ETAG_SHAPE.match(res["ETag"]), res["ETag"]
    inv.refresh_from_db()
    assert res["ETag"] == etag_for(inv)

    created = client.post("/api/sales/invoices/", {
        "customer": customer.id, "currency": cur.CurrencyID, "invoice_date": "2026-06-16",
        "invoice_type": "credit", "stock_on_post": False, "auto_post": False,
        "lines": [{"product": product.id, "quantity": "1", "unit_price": "10"}],
    }, format="json")
    assert created.status_code == 201, created.content
    assert ETAG_SHAPE.match(created["ETag"]), created.get("ETag")
    assert created["ETag"] == etag_for(SalesInvoice.objects.get(pk=created.json()["id"]))


def test_invoice_patch_with_current_if_match_succeeds_and_etag_changes(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    before = _etag(client, url)
    res = client.patch(url, {"notes": "تعديل أول"}, format="json", HTTP_IF_MATCH=before)
    assert res.status_code == 200, res.content
    assert res["ETag"] != before
    assert res["ETag"] == _etag(client, url)
    inv.refresh_from_db()
    assert inv.notes == "تعديل أول"


def test_invoice_patch_with_stale_if_match_is_412_and_writes_nothing(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    stale = _etag(client, url)
    inv.refresh_from_db()
    _touch(inv, notes="كتبه الطرف الآخر")
    current = etag_for(inv)

    res = client.patch(url, {"notes": "تعديلي"}, format="json", HTTP_IF_MATCH=stale)
    assert res.status_code == 412, res.content
    body = res.json()
    assert body["code"] == "stale_document"
    assert body["current_etag"] == current
    assert body["updated_at"]
    assert "أعد قراءته" in body["error"]
    inv.refresh_from_db()
    assert inv.notes == "كتبه الطرف الآخر"
    assert etag_for(inv) == current


def test_invoice_put_with_stale_if_match_is_412_too(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    stale = _etag(client, url)
    inv.refresh_from_db()
    _touch(inv, notes="x")
    res = client.put(url, {"notes": "تعديلي"}, format="json", HTTP_IF_MATCH=stale)
    assert res.status_code == 412, res.content


def test_invoice_patch_without_if_match_behaves_as_before(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    res = client.patch(f"/api/sales/invoices/{inv.id}/", {"notes": "بلا شرط"}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.notes == "بلا شرط"


def test_invoice_patch_with_star_or_list_containing_current_succeeds(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    assert client.patch(url, {"notes": "نجمة"}, format="json", HTTP_IF_MATCH="*").status_code == 200
    current = _etag(client, url)
    res = client.patch(url, {"notes": "قائمة"}, format="json", HTTP_IF_MATCH=f'"1", {current}')
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.notes == "قائمة"


def test_invoice_lines_only_patch_changes_the_etag(env):
    _t, client, _cur, _cash, _customer, product = env
    inv, line = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    before = _etag(client, url)
    res = client.patch(url, {"lines": [
        {"id": line.id, "product": product.id, "quantity": "7", "unit_price": "100"},
    ]}, format="json", HTTP_IF_MATCH=before)
    assert res.status_code == 200, res.content
    line.refresh_from_db()
    assert line.quantity == Decimal("7")
    after = _etag(client, url)
    assert after != before
    # والتوكن القديم صار قديماً فعلاً
    again = client.patch(url, {"notes": "متأخر"}, format="json", HTTP_IF_MATCH=before)
    assert again.status_code == 412, again.content


def test_posting_an_invoice_changes_the_etag(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    before = _etag(client, url)
    assert client.post(f"{url}post/", {}, format="json").status_code == 200
    assert _etag(client, url) != before


def test_posted_invoice_notes_edit_honours_if_match(env):
    _t, client, *_ = env
    inv, _ = _draft_invoice(env)
    url = f"/api/sales/invoices/{inv.id}/"
    assert client.post(f"{url}post/", {}, format="json").status_code == 200
    stale = _etag(client, url)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
    _touch(inv, notes="كتبه الطرف الآخر")

    res = client.patch(url, {"notes": "تعديلي"}, format="json", HTTP_IF_MATCH=stale)
    assert res.status_code == 412, res.content
    inv.refresh_from_db()
    assert inv.notes == "كتبه الطرف الآخر"

    fresh = _etag(client, url)
    ok = client.patch(url, {"notes": "تعديلي"}, format="json", HTTP_IF_MATCH=fresh)
    assert ok.status_code == 200, ok.content
    assert ok["ETag"] != fresh
    inv.refresh_from_db()
    assert inv.notes == "تعديلي"


# ── سند القبض ──

def _draft_payment(env):
    _t, client, cur, cash, customer, _p = env
    res = client.post("/api/sales/payments/", {
        "partner": customer.id, "payment_date": "2026-06-20", "amount": "100",
        "currency": cur.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": cash.id,
        "auto_post": False,
    }, format="json")
    assert res.status_code == 201, res.content
    return res, CustomerPayment.objects.get(pk=res.json()["id"])


def test_payment_create_carries_etag_and_exposes_updated_at(env):
    res, pay = _draft_payment(env)
    assert ETAG_SHAPE.match(res["ETag"]), res.get("ETag")
    assert res["ETag"] == etag_for(pay)
    assert res.json()["updated_at"]


def test_payment_patch_with_current_if_match_succeeds_and_etag_changes(env):
    _t, client, *_ = env
    _res, pay = _draft_payment(env)
    url = f"/api/sales/payments/{pay.id}/"
    before = _etag(client, url)
    res = client.patch(url, {"notes": "ملاحظة"}, format="json", HTTP_IF_MATCH=before)
    assert res.status_code == 200, res.content
    assert res["ETag"] != before
    pay.refresh_from_db()
    assert pay.notes == "ملاحظة"


def test_payment_patch_with_stale_if_match_is_412_and_writes_nothing(env):
    _t, client, *_ = env
    _res, pay = _draft_payment(env)
    url = f"/api/sales/payments/{pay.id}/"
    stale = _etag(client, url)
    pay.refresh_from_db()
    _touch(pay, notes="كتبه الطرف الآخر")

    res = client.patch(url, {"notes": "تعديلي"}, format="json", HTTP_IF_MATCH=stale)
    assert res.status_code == 412, res.content
    assert res.json()["code"] == "stale_document"
    pay.refresh_from_db()
    assert pay.notes == "كتبه الطرف الآخر"


def test_payment_patch_without_if_match_and_with_star_succeed(env):
    _t, client, *_ = env
    _res, pay = _draft_payment(env)
    url = f"/api/sales/payments/{pay.id}/"
    assert client.patch(url, {"notes": "أ"}, format="json").status_code == 200
    assert client.patch(url, {"notes": "ب"}, format="json", HTTP_IF_MATCH="*").status_code == 200
    pay.refresh_from_db()
    assert pay.notes == "ب"


def test_posting_a_payment_changes_the_etag_and_posted_notes_honour_if_match(env):
    _t, client, *_ = env
    _res, pay = _draft_payment(env)
    url = f"/api/sales/payments/{pay.id}/"
    before = _etag(client, url)
    assert client.post(f"{url}post/", {}, format="json").status_code == 200
    posted = _etag(client, url)
    assert posted != before
    pay.refresh_from_db()
    assert pay.is_posted is True

    stale = client.patch(url, {"notes": "متأخر"}, format="json", HTTP_IF_MATCH=before)
    assert stale.status_code == 412, stale.content
    ok = client.patch(url, {"notes": "حديث"}, format="json", HTTP_IF_MATCH=posted)
    assert ok.status_code == 200, ok.content
    assert ok["ETag"] != posted


# ── الإرسالية ──

def _delivery(env):
    """إرسالية مُسلَّمة على فاتورة مرحَّلة (تُخرج 2 من المخزون وتقيّد التكلفة)."""
    tenant, client, *_ = env
    inv, line = _draft_invoice(env, number="OCC-INV-D")
    assert client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    res = client.post("/api/sales/delivery-orders/", {
        "invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "2"}],
    }, format="json")
    assert res.status_code == 201, res.content
    return inv, line, res, DeliveryOrder.objects.get(pk=res.json()["id"])


def _delivery_effects(tenant, product):
    product.refresh_from_db()
    return (
        StockMovement.objects.filter(tenant=tenant).count(),
        JournalHeader.objects.filter(tenant=tenant).count(),
        product.quantity_on_hand,
    )


def test_delivery_create_and_retrieve_carry_etag(env):
    _inv, _line, created, delivery = _delivery(env)
    _t, client, *_ = env
    assert ETAG_SHAPE.match(created["ETag"]), created.get("ETag")
    assert created["ETag"] == etag_for(delivery)
    assert _etag(client, f"/api/sales/delivery-orders/{delivery.id}/") == created["ETag"]


def test_delivery_patch_with_stale_if_match_is_412_and_voids_nothing(env):
    tenant, client, _cur, _cash, _customer, product = env
    inv, line, created, delivery = _delivery(env)
    url = f"/api/sales/delivery-orders/{delivery.id}/"
    stale = created["ETag"]
    delivery.refresh_from_db()
    _touch(delivery, customer_ref="كتبه الطرف الآخر")
    effects = _delivery_effects(tenant, product)

    res = client.patch(url, {
        "invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "3"}],
    }, format="json", HTTP_IF_MATCH=stale)
    assert res.status_code == 412, res.content
    assert res.json()["code"] == "stale_document"
    assert DeliveryOrder.objects.filter(pk=delivery.pk).exists()
    assert _delivery_effects(tenant, product) == effects
    delivery.refresh_from_db()
    assert delivery.customer_ref == "كتبه الطرف الآخر"


def test_delivery_patch_with_current_if_match_and_star_and_none_succeed(env):
    tenant, client, _cur, _cash, _customer, product = env
    inv, line, created, delivery = _delivery(env)
    body = {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": "3"}]}

    ok = client.patch(f"/api/sales/delivery-orders/{delivery.id}/", body, format="json",
                      HTTP_IF_MATCH=created["ETag"])
    assert ok.status_code == 200, ok.content
    assert ok["ETag"] != created["ETag"]
    assert ETAG_SHAPE.match(ok["ETag"])
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("47.0000")

    # الإرسالية استُبدلت بصفٍّ جديد (عكسٌ ثم إعادة تطبيق) — نكمل على المعرّف الجديد.
    new_id = ok.json()["id"]
    body["lines"][0]["quantity"] = "4"
    starred = client.patch(f"/api/sales/delivery-orders/{new_id}/", body, format="json",
                           HTTP_IF_MATCH="*")
    assert starred.status_code == 200, starred.content
    plain = client.patch(f"/api/sales/delivery-orders/{starred.json()['id']}/", body, format="json")
    assert plain.status_code == 200, plain.content


def test_delivering_a_pending_order_changes_its_etag(env):
    tenant, client, *_ = env
    inv, _line = _draft_invoice(env, number="OCC-INV-P")
    assert client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    do_id = client.post(
        f"/api/sales/invoices/{inv.id}/delivery-order/", {}, format="json").json()["id"]
    url = f"/api/sales/delivery-orders/{do_id}/"
    before = _etag(client, url)
    assert client.post(f"{url}deliver/", {}, format="json").status_code == 200
    assert _etag(client, url) != before
