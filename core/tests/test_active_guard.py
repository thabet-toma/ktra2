"""حارس «غير نشط» (T3) — صنفٌ أو طرفٌ موقوف لا يُرحَّل مستنده ولا يتحوّل إلى مستندٍ قابلٍ للترحيل.

قرار المالك: «اكيد ممنوع الترحيل» — والمسودّة المحفوظة **قبل** الإيقاف لا تُرحَّل أيضاً.
المرتجعات وتسليم/استلام المرحَّل وحركات المخزون المباشرة والسندات والإشعارات تبقى
مسموحة كي تُسوّى الأرصدة (سابقة BC: Blocked يمنع الجديد ويُعفي المرتجع/مذكّرة الدائن).

المحرّك: `core.active_guard.assert_active_for_posting` — يُختبر هنا وحده (وحدة) ثم على
كل مسارٍ يستدعيه عبر الـAPI أو الخدمة، مع إثبات المسارات المُعفاة.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from core.active_guard import assert_active_for_posting
from inventory.models import Product, StockMovement, Warehouse, WarehouseTransfer, WarehouseTransferLine
from inventory.services import post_warehouse_transfer, record_stock_movement
from logistics.models import (
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierQuotation,
)
from logistics.services import (
    convert_local_quotation_to_invoice,
    convert_local_quotation_to_order,
    convert_purchase_order_to_invoice,
    confirm_purchase_order,
    create_purchase_return,
    get_or_create_purchase_settings,
    post_purchase_return,
)
from partners.models import Partner
from sales.models import (
    CustomerPayment,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    SalesQuotation,
    SalesQuotationLine,
    SalesSettings,
    SupplierPayment,
)
from sales.services import (
    confirm_sales_order,
    convert_order_to_invoice,
    convert_quotation_to_invoice,
    convert_quotation_to_order,
    post_customer_payment,
    post_sales_invoice,
    post_supplier_payment,
)
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

WHAT = ["product", "partner", "both"]


# ── وحدة الحارس نفسه ────────────────────────────────────────────────────────

def _prod(pk, name="", *, active=True, sku=""):
    return SimpleNamespace(pk=pk, name_ar=name, name_en="", sku=sku, is_active=active)


def _party(pk, name, ptype, *, active=True):
    return SimpleNamespace(pk=pk, name=name, partner_type=ptype, is_active=active)


def test_helper_passes_when_everything_is_active():
    assert_active_for_posting(
        partner=_party(1, "ع", "Customer"), products=[_prod(1, "س"), _prod(2, "ص")])
    assert_active_for_posting()  # لا شيء يُفحص


def test_helper_names_every_inactive_product_once_and_skips_none():
    p1, p2 = _prod(1, "الأول", active=False), _prod(2, "الثاني", active=False)
    with pytest.raises(ValidationError) as ei:
        assert_active_for_posting(
            products=[p1, None, p2, p1, _prod(3, "نشط")], document_label="الفاتورة")
    msg = ei.value.messages[0]
    assert msg.startswith("لا يمكن ترحيل الفاتورة:")
    assert "«الأول»، «الثاني»" in msg
    assert msg.count("«الأول»") == 1  # المكرَّر مرّة واحدة
    assert "نشط»" not in msg
    assert "نشّطه من قائمة المنتجات أو احذفه من البنود" in msg


def test_helper_partner_role_word_follows_type_and_action_label():
    with pytest.raises(ValidationError) as ei:
        assert_active_for_posting(
            partner=_party(5, "ورشة", "Supplier", active=False),
            action="تأكيد", document_label="الطلبية")
    assert ei.value.messages[0].startswith("لا يمكن تأكيد الطلبية:")
    assert "المورّد «ورشة» غير نشط — نشّطه من ملفه أو غيّر الطرف" in ei.value.messages[0]
    with pytest.raises(ValidationError) as ei:
        assert_active_for_posting(partner=_party(6, "زيد", "Customer", active=False))
    assert "العميل «زيد»" in ei.value.messages[0]
    assert "لا يمكن ترحيل المستند:" in ei.value.messages[0]


def test_helper_reports_both_offenders_in_one_message():
    with pytest.raises(ValidationError) as ei:
        assert_active_for_posting(
            partner=_party(1, "زيد", "Customer", active=False),
            products=[_prod(1, "صنف", active=False)])
    msg = ei.value.messages[0]
    assert "«صنف»" in msg and "العميل «زيد»" in msg


# ── بيئة مشتركة ─────────────────────────────────────────────────────────────

@pytest.fixture
def env():
    owner = User.objects.create_user(username="actguard", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الحارس", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-G", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4001-G", name="مبيعات", account_type="Revenue", is_active=True)
    cogs = Account.objects.create(
        tenant=tenant, code="5001-G", name="تكلفة", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-G", name="مخزون", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-G", name="صندوق", account_type="Asset", is_active=True)
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "default_revenue_account_product": rev,
            "default_cogs_account": cogs,
            "default_inventory_account": inv_acc,
        },
    )
    ap = Account.objects.get(tenant=tenant, code="2101")
    customer = Partner.objects.create(
        tenant=tenant, name="العميل الموقوف", partner_type="Customer", linked_account=ar)
    supplier = Partner.objects.create(
        tenant=tenant, name="المورّد الموقوف", partner_type="Supplier", linked_account=ap)
    product = Product.objects.create(
        tenant=tenant, sku="GRD-1", name_ar="الصنف الموقوف",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("100"),
        unit_cost=Decimal("10"), reference_type="OPENING", reference_id=0,
        movement_date="2026-06-01", tenant=tenant)
    product.refresh_from_db()
    client = APIClient()
    client.force_authenticate(user=owner)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return SimpleNamespace(
        owner=owner, ils=ils, tenant=tenant, customer=customer, supplier=supplier,
        product=product, cash=cash, client=client,
        warehouse=Warehouse.objects.get(tenant=tenant, is_default=True))


def _deactivate(e, what, *, partner=None):
    """يوقف الصنف و/أو الطرف **بعد** حفظ المستند — سيناريو المالك."""
    if what in ("product", "both"):
        Product.objects.filter(pk=e.product.pk).update(is_active=False)
    if what in ("partner", "both"):
        Partner.objects.filter(pk=(partner or e.customer).pk).update(is_active=False)


def _assert_names(msg, what, *, partner_name):
    if what in ("product", "both"):
        assert "الصنف الموقوف" in msg
    else:
        assert "الصنف الموقوف" not in msg
    if what in ("partner", "both"):
        assert partner_name in msg
    else:
        assert partner_name not in msg
    assert "غير نشط" in msg


def _sales_invoice(e, number, *, kind=SalesInvoice.INVOICE_KIND_SALE, stock_on_post=False):
    inv = SalesInvoice.objects.create(
        tenant=e.tenant, invoice_number=number, customer=e.customer, currency=e.ils,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=stock_on_post, invoice_kind=kind)
    SalesInvoiceLine.objects.create(
        tenant=e.tenant, invoice=inv, product=e.product,
        quantity=Decimal("2"), unit_price=Decimal("150"))
    return inv


def _fresh(obj):
    """مستندٌ يُقرأ من القاعدة كما يصل إلى الخدمة من طلب HTTP — لا نسخةَ الاختبار المخبوءة."""
    return type(obj).objects.get(pk=obj.pk)


def _journals(e):
    return JournalHeader.objects.filter(tenant_id=e.tenant.TenantID).count()


# ── فاتورة البيع ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("what", WHAT)
def test_sales_invoice_post_refused_and_names_offenders(env, what):
    inv = _sales_invoice(env, "G-S-1")
    _deactivate(env, what)
    before_j, before_mv = _journals(env), StockMovement.objects.count()
    with pytest.raises(ValidationError) as ei:
        post_sales_invoice(inv)
    msg = "؛ ".join(ei.value.messages)
    assert msg.startswith("لا يمكن ترحيل الفاتورة:")
    _assert_names(msg, what, partner_name="العميل «العميل الموقوف»")
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_DRAFT
    assert (_journals(env), StockMovement.objects.count()) == (before_j, before_mv)


def test_sales_invoice_active_still_posts(env):
    inv = _sales_invoice(env, "G-S-2")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_inactive_service_is_refused_like_any_product(env):
    svc = Product.objects.create(
        tenant=env.tenant, sku="SVC-G", name_ar="خدمة موقوفة", is_service=True, is_active=False)
    inv = _sales_invoice(env, "G-S-SVC")
    SalesInvoiceLine.objects.create(
        tenant=env.tenant, invoice=inv, product=svc, quantity=Decimal("1"), unit_price=Decimal("50"))
    with pytest.raises(ValidationError) as ei:
        post_sales_invoice(inv)
    assert "«خدمة موقوفة»" in ei.value.messages[0]
    assert "الصنف الموقوف" not in ei.value.messages[0]


@pytest.mark.parametrize("what", WHAT)
def test_sales_post_endpoint_returns_400_with_the_message(env, what):
    inv = _sales_invoice(env, "G-S-3")
    _deactivate(env, what)
    res = env.client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    assert res.status_code == 400, res.content
    _assert_names(res.json()["error"], what, partner_name="العميل «العميل الموقوف»")


def test_draft_saved_before_deactivation_is_not_postable(env):
    """سيناريو المالك: مسودّة محفوظة عبر الـAPI ثم يُوقف الصنف ثم يضغط «رحّل»."""
    res = env.client.post("/api/sales/invoices/", {
        "customer": env.customer.id, "currency": env.ils.pk, "invoice_date": "2026-06-20",
        "invoice_type": "credit",
        "lines": [{"product": env.product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert res.status_code == 201, res.content
    assert "auto_post_error" not in res.json()
    invoice_id = res.json()["id"]
    _deactivate(env, "product")
    posted = env.client.post(f"/api/sales/invoices/{invoice_id}/post/", {}, format="json")
    assert posted.status_code == 400, posted.content
    assert "الصنف الموقوف" in posted.json()["error"]
    assert SalesInvoice.objects.get(pk=invoice_id).status == SalesInvoice.STATUS_DRAFT


def test_auto_post_surfaces_the_guard_error_and_keeps_the_draft(env):
    ss = SalesSettings.objects.get(tenant=env.tenant)
    ss.auto_post_invoices = True
    ss.save(update_fields=["auto_post_invoices"])
    _deactivate(env, "product")
    res = env.client.post("/api/sales/invoices/", {
        "customer": env.customer.id, "currency": env.ils.pk, "invoice_date": "2026-06-20",
        "invoice_type": "credit",
        "lines": [{"product": env.product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert res.status_code == 201, res.content
    body = res.json()
    assert "الصنف الموقوف" in body["auto_post_error"]
    assert SalesInvoice.objects.get(pk=body["id"]).status == SalesInvoice.STATUS_DRAFT


def test_serializers_expose_the_active_flags(env):
    inv = _sales_invoice(env, "G-S-4")
    _deactivate(env, "both")
    detail = env.client.get(f"/api/sales/invoices/{inv.id}/").json()
    assert detail["customer_is_active"] is False
    assert detail["lines"][0]["product_is_active"] is False
    listing = env.client.get("/api/sales/invoices/").json()
    rows = listing["results"] if isinstance(listing, dict) else listing
    assert rows[0]["customer_is_active"] is False


# ── طلبيات وعروض البيع ──────────────────────────────────────────────────────

def _quotation(e, number="Q-G-1"):
    q = SalesQuotation.objects.create(
        tenant=e.tenant, quotation_number=number, customer=e.customer,
        quotation_date="2026-07-01", currency=e.ils, grand_total=Decimal("300"))
    SalesQuotationLine.objects.create(
        tenant=e.tenant, quotation=q, product=e.product,
        quantity=Decimal("2"), unit_price=Decimal("150"))
    return q


def _order(e, number="O-G-1"):
    o = SalesOrder.objects.create(
        tenant=e.tenant, order_number=number, customer=e.customer,
        order_date="2026-07-01", currency=e.ils, grand_total=Decimal("300"))
    SalesOrderLine.objects.create(
        tenant=e.tenant, order=o, product=e.product,
        quantity=Decimal("2"), unit_price=Decimal("150"), line_total=Decimal("300"))
    return o


@pytest.mark.parametrize("what", WHAT)
def test_confirm_sales_order_refused(env, what):
    order = _order(env)
    _deactivate(env, what)
    with pytest.raises(ValidationError) as ei:
        confirm_sales_order(_fresh(order))
    msg = "؛ ".join(ei.value.messages)
    assert msg.startswith("لا يمكن تأكيد الطلبية:")
    _assert_names(msg, what, partner_name="العميل «العميل الموقوف»")
    order.refresh_from_db()
    assert order.status == SalesOrder.STATUS_DRAFT


def test_confirm_sales_order_active_confirms(env):
    order = _order(env)
    assert confirm_sales_order(order).status == SalesOrder.STATUS_CONFIRMED


@pytest.mark.parametrize("what", WHAT)
def test_convert_quotation_to_order_refused(env, what):
    q = _quotation(env)
    _deactivate(env, what)
    with pytest.raises(ValidationError) as ei:
        convert_quotation_to_order(_fresh(q))
    assert "لا يمكن تحويل عرض السعر:" in ei.value.messages[0]
    _assert_names(ei.value.messages[0], what, partner_name="العميل «العميل الموقوف»")
    q.refresh_from_db()
    assert q.status == SalesQuotation.STATUS_DRAFT
    assert not SalesOrder.objects.filter(quotation=q).exists()


@pytest.mark.parametrize("what", WHAT)
def test_convert_order_to_invoice_refused(env, what):
    order = _order(env)
    _deactivate(env, what)
    with pytest.raises(ValidationError) as ei:
        convert_order_to_invoice(_fresh(order))
    assert "لا يمكن تحويل الطلبية:" in ei.value.messages[0]
    _assert_names(ei.value.messages[0], what, partner_name="العميل «العميل الموقوف»")
    assert not SalesInvoice.objects.filter(tenant=env.tenant).exists()


@pytest.mark.parametrize("what", WHAT)
def test_convert_quotation_to_invoice_refused(env, what):
    q = _quotation(env)
    _deactivate(env, what)
    with pytest.raises(ValidationError) as ei:
        convert_quotation_to_invoice(_fresh(q))
    assert "لا يمكن تحويل عرض السعر:" in ei.value.messages[0]
    _assert_names(ei.value.messages[0], what, partner_name="العميل «العميل الموقوف»")
    q.refresh_from_db()
    assert q.status == SalesQuotation.STATUS_DRAFT
    assert not SalesInvoice.objects.filter(tenant=env.tenant).exists()


def test_active_documents_still_convert(env):
    assert convert_quotation_to_invoice(_quotation(env, "Q-G-OK")).lines.count() == 1
    assert convert_order_to_invoice(_order(env, "O-G-OK")).lines.count() == 1
    assert convert_quotation_to_order(_quotation(env, "Q-G-OK2")).status == SalesOrder.STATUS_CONFIRMED


def test_order_and_quotation_serializers_expose_product_flag(env):
    _order(env)
    _quotation(env)
    _deactivate(env, "product")
    order = env.client.get("/api/sales/orders/").json()
    order = (order["results"] if isinstance(order, dict) else order)[0]
    assert order["lines"][0]["product_is_active"] is False
    quote_id = SalesQuotation.objects.get().id
    quote = env.client.get(f"/api/sales/quotations/{quote_id}/").json()
    assert quote["lines"][0]["product_is_active"] is False


# ── مسارات البيع المُعفاة ───────────────────────────────────────────────────

def test_exempt_sale_return_posts_with_inactive_product_and_customer(env):
    ret = _sales_invoice(
        env, "G-R-1", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN, stock_on_post=True)
    _deactivate(env, "both")
    post_sales_invoice(ret)
    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED


def test_exempt_delivery_of_a_posted_invoice(env):
    inv = _sales_invoice(env, "G-D-1", stock_on_post=False)
    post_sales_invoice(inv)
    line = inv.lines.get()
    _deactivate(env, "both")
    res = env.client.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 2}]}, format="json")
    assert res.status_code == 200, res.content


def test_exempt_customer_payment_for_an_inactive_customer(env):
    _deactivate(env, "partner")
    pay = CustomerPayment.objects.create(
        tenant=env.tenant, partner=env.customer, currency=env.ils, exchange_rate=Decimal("1"),
        amount=Decimal("100"), cash_or_bank_account=env.cash, payment_date="2026-06-20")
    post_customer_payment(pay)
    pay.refresh_from_db()
    assert pay.is_posted


def test_exempt_credit_note_for_an_inactive_customer(env):
    _deactivate(env, "partner")
    created = env.client.post("/api/sales/credit-debit-notes/", {
        "note_date": "2026-07-10", "note_type": "credit", "partner": env.customer.pk,
        "amount": "100", "reason": "تسوية",
    }, format="json")
    assert created.status_code == 201, created.content
    posted = env.client.post(
        f"/api/sales/credit-debit-notes/{created.json()['id']}/post/", {}, format="json")
    assert posted.status_code == 200, posted.content


def test_exempt_manual_stock_movement_and_warehouse_transfer(env):
    _deactivate(env, "product")
    mv = record_stock_movement(
        product=Product.objects.get(pk=env.product.pk), movement_type="IN",
        quantity=Decimal("5"), unit_cost=Decimal("10"), reference_type="MANUAL",
        reference_id=0, movement_date="2026-06-21", tenant=env.tenant)
    assert mv.pk
    wh_b = Warehouse.objects.create(tenant=env.tenant, name="ب", code="GB")
    t = WarehouseTransfer.objects.create(
        tenant=env.tenant, transfer_date="2026-07-01",
        source_warehouse=env.warehouse, dest_warehouse=wh_b)
    WarehouseTransferLine.objects.create(transfer=t, product=env.product, quantity=Decimal("3"))
    post_warehouse_transfer(t)
    t.refresh_from_db()
    assert t.is_posted


def test_other_tenants_inactive_records_do_not_affect_this_tenant(env):
    other_owner = User.objects.create_user(username="actguard-b", password="x")
    other = create_company("شركة أخرى", other_owner)
    Partner.objects.create(tenant=other, name="موقوف هناك", partner_type="Customer", is_active=False)
    Product.objects.create(tenant=other, sku="X-1", name_ar="موقوف هناك", is_active=False)
    inv = _sales_invoice(env, "G-T-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


# ── فاتورة الشراء ───────────────────────────────────────────────────────────

def _purchase_invoice(e, number, *, international=False):
    """محلية، أو دولية (صفقة + شحنة + بند بتكلفة مستوردة) كما في اختبارات الاستيراد."""
    extra = {}
    if international:
        e.tenant.import_enabled = True
        e.tenant.save(update_fields=["import_enabled"])
        n = LogisticsDeal.objects.count() + 1
        deal = LogisticsDeal.objects.create(
            tenant=e.tenant, ref_number=f"GD-{n:04d}", partner=e.supplier,
            order_date="2026-07-01", total_amount=Decimal("1000"))
        shipment = LogisticsShipment.objects.create(
            tenant=e.tenant, shipment_number=f"GS-{n:04d}", status="Clearing")
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        LogisticsDealItem.objects.create(
            deal=deal, product=e.product, quantity=Decimal("10"), unit_price=Decimal("100"))
        extra = {"deal": deal, "shipment": shipment}
    inv = PurchaseInvoice.objects.create(
        tenant=e.tenant, invoice_number=number, partner=e.supplier, currency=e.ils,
        invoice_date="2026-06-11", exchange_rate=Decimal("1"), grand_total=Decimal("1000.00"),
        invoice_type=(
            PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL if international
            else PurchaseInvoice.INVOICE_TYPE_LOCAL), **extra)
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=e.product, name="صنف", quantity=Decimal("10"),
        unit_price=Decimal("100"), total_price=Decimal("1000"),
        landed_unit_price_ils=Decimal("100"), landed_line_total_ils=Decimal("1000"))
    return inv


SUP_NAME = "المورّد «المورّد الموقوف»"


@pytest.mark.parametrize("what", WHAT)
@pytest.mark.parametrize("international", [False, True])
def test_purchase_post_to_accounting_refused(env, what, international):
    inv = _purchase_invoice(env, "G-P-1", international=international)
    _deactivate(env, what, partner=env.supplier)
    before = _journals(env)
    res = env.client.post(
        f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {}, format="json")
    assert res.status_code == 400, res.content
    msg = res.json()["error"]
    assert msg.startswith("لا يمكن ترحيل الفاتورة:")
    _assert_names(msg, what, partner_name=SUP_NAME)
    inv.refresh_from_db()
    assert not inv.is_posted and not inv.journal_id
    assert _journals(env) == before


@pytest.mark.parametrize("international", [False, True])
def test_purchase_active_still_posts(env, international):
    inv = _purchase_invoice(env, "G-P-2", international=international)
    res = env.client.post(
        f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {}, format="json")
    assert res.status_code == 201, res.content


def test_purchase_pay_with_post_invoice_is_refused_atomically(env):
    inv = _purchase_invoice(env, "G-P-3")
    _deactivate(env, "partner", partner=env.supplier)
    res = env.client.post(f"/api/logistics/purchase-invoices/{inv.pk}/pay/", {
        "post_invoice": True, "cash": "100", "cash_account_id": env.cash.id,
    }, format="json")
    assert res.status_code == 400, res.content
    assert "غير نشط" in res.json()["error"]
    inv.refresh_from_db()
    assert not inv.is_posted
    assert not SupplierPayment.objects.filter(tenant=env.tenant).exists()


def test_receiving_a_draft_invoice_is_posting_so_it_is_guarded(env):
    inv = _purchase_invoice(env, "G-P-4")
    item = inv.items.get()
    _deactivate(env, "product")
    res = env.client.post(
        f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
        {"lines": [{"item_id": item.pk, "quantity": 5, "warehouse_id": env.warehouse.pk}]},
        format="json")
    assert res.status_code == 400, res.content
    assert "الصنف الموقوف" in res.json()["error"]
    inv.refresh_from_db()
    assert not inv.is_posted


def test_exempt_receiving_an_already_posted_invoice(env):
    inv = _purchase_invoice(env, "G-P-5")
    item = inv.items.get()
    first = env.client.post(
        f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
        {"lines": [{"item_id": item.pk, "quantity": 5, "warehouse_id": env.warehouse.pk}]},
        format="json")
    assert first.status_code == 200, first.content
    assert PurchaseInvoice.objects.get(pk=inv.pk).is_posted
    _deactivate(env, "both", partner=env.supplier)
    second = env.client.post(
        f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
        {"lines": [{"item_id": item.pk, "quantity": 5, "warehouse_id": env.warehouse.pk}]},
        format="json")
    assert second.status_code == 200, second.content


def test_exempt_purchase_return_and_supplier_payment(env):
    _deactivate(env, "both", partner=env.supplier)
    product = Product.objects.get(pk=env.product.pk)
    ret = create_purchase_return(
        env.tenant, original_invoice=None, partner=env.supplier, return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 4, "unit_price": 50}], currency=env.ils)
    post_purchase_return(ret, user=None)
    ret.refresh_from_db()
    assert ret.is_posted
    pay = SupplierPayment.objects.create(
        tenant=env.tenant, partner=env.supplier, payment_date="2026-07-08",
        amount=Decimal("100"), currency=env.ils, exchange_rate=Decimal("1"),
        cash_or_bank_account=env.cash)
    post_supplier_payment(pay, user=env.owner)
    pay.refresh_from_db()
    assert pay.is_posted


def test_purchase_serializers_expose_the_active_flags(env):
    inv = _purchase_invoice(env, "G-P-6")
    _deactivate(env, "both", partner=env.supplier)
    detail = env.client.get(f"/api/logistics/purchase-invoices/{inv.pk}/").json()
    assert detail["partner_is_active"] is False
    assert detail["items"][0]["product_is_active"] is False
    listing = env.client.get("/api/logistics/purchase-invoices/").json()
    rows = listing["results"] if isinstance(listing, dict) else listing
    assert rows[0]["partner_is_active"] is False


# ── طلبيات الشراء وعروضه ────────────────────────────────────────────────────

def _purchase_order(e, number="PO-G-1"):
    order = PurchaseOrder.objects.create(
        tenant=e.tenant, order_number=number, supplier=e.supplier, order_date="2026-07-26",
        currency=e.ils, exchange_rate=Decimal("1"), grand_total=Decimal("20"))
    PurchaseOrderLine.objects.create(
        tenant=e.tenant, order=order, product=e.product, seq=1,
        quantity=Decimal("2"), unit_price=Decimal("10"), line_total=Decimal("20"))
    return order


def _supplier_quotation(e, number="SQ-G-1"):
    q = SupplierQuotation.objects.create(
        tenant=e.tenant, quotation_number=number, scope=SupplierQuotation.SCOPE_LOCAL,
        supplier=e.supplier, quotation_date="2026-07-26",
        status=SupplierQuotation.STATUS_ACCEPTED, currency=e.ils, exchange_rate=Decimal("1"),
        grand_total=Decimal("20"))
    q.lines.create(
        tenant=e.tenant, product=e.product, seq=1, quantity=Decimal("2"),
        unit_price=Decimal("10"), line_total=Decimal("20"))
    return q


@pytest.mark.parametrize("what", WHAT)
def test_confirm_purchase_order_refused(env, what):
    order = _purchase_order(env)
    _deactivate(env, what, partner=env.supplier)
    with pytest.raises(ValidationError) as ei:
        confirm_purchase_order(order)
    assert ei.value.messages[0].startswith("لا يمكن تأكيد الطلبية:")
    _assert_names(ei.value.messages[0], what, partner_name=SUP_NAME)
    order.refresh_from_db()
    assert order.status == PurchaseOrder.STATUS_DRAFT


def test_confirm_purchase_order_endpoint_returns_400(env):
    order = _purchase_order(env)
    _deactivate(env, "product")
    res = env.client.post(f"/api/logistics/purchase-orders/{order.pk}/confirm/", {}, format="json")
    assert res.status_code == 400, res.content


def test_confirm_purchase_order_active_confirms(env):
    order = confirm_purchase_order(_purchase_order(env))
    assert order.status == PurchaseOrder.STATUS_CONFIRMED


@pytest.mark.parametrize("what", WHAT)
def test_convert_purchase_order_to_invoice_refused(env, what):
    order = _purchase_order(env)
    confirm_purchase_order(order)
    order.refresh_from_db()
    _deactivate(env, what, partner=env.supplier)
    with pytest.raises(ValidationError) as ei:
        convert_purchase_order_to_invoice(order)
    assert ei.value.messages[0].startswith("لا يمكن تحويل الطلبية:")
    _assert_names(ei.value.messages[0], what, partner_name=SUP_NAME)
    assert not PurchaseInvoice.objects.filter(tenant=env.tenant).exists()


@pytest.mark.parametrize("what", WHAT)
def test_convert_local_quotation_to_order_refused(env, what):
    ps = get_or_create_purchase_settings(env.tenant)
    ps.use_purchase_orders = True
    ps.save(update_fields=["use_purchase_orders"])
    q = _supplier_quotation(env)
    _deactivate(env, what, partner=env.supplier)
    with pytest.raises(ValidationError) as ei:
        convert_local_quotation_to_order(q)
    assert ei.value.messages[0].startswith("لا يمكن تحويل عرض السعر:")
    _assert_names(ei.value.messages[0], what, partner_name=SUP_NAME)
    assert not PurchaseOrder.objects.filter(tenant=env.tenant).exists()
    q.refresh_from_db()
    assert q.status == SupplierQuotation.STATUS_ACCEPTED


@pytest.mark.parametrize("what", WHAT)
def test_convert_local_quotation_to_invoice_refused(env, what):
    q = _supplier_quotation(env)
    _deactivate(env, what, partner=env.supplier)
    with pytest.raises(ValidationError) as ei:
        convert_local_quotation_to_invoice(q)
    assert ei.value.messages[0].startswith("لا يمكن تحويل عرض السعر:")
    _assert_names(ei.value.messages[0], what, partner_name=SUP_NAME)
    assert not PurchaseInvoice.objects.filter(tenant=env.tenant).exists()
    q.refresh_from_db()
    assert q.status == SupplierQuotation.STATUS_ACCEPTED


def test_active_purchase_documents_still_convert(env):
    ps = get_or_create_purchase_settings(env.tenant)
    ps.use_purchase_orders = True
    ps.save(update_fields=["use_purchase_orders"])
    order, created = convert_local_quotation_to_order(_supplier_quotation(env, "SQ-OK1"))
    assert created
    invoice, created = convert_local_quotation_to_invoice(_supplier_quotation(env, "SQ-OK2"))
    assert created and invoice.items.count() == 1
    po = confirm_purchase_order(_purchase_order(env, "PO-OK"))
    invoice, created = convert_purchase_order_to_invoice(po)
    assert created
