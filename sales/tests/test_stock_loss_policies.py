"""سياستا «المخزون السالب» و«فاتورة البيع بخسارة» — ثلاث حالات لا حالتان.

بلاغ المالك: اختار «السماح بالحفظ (افتراضي)» في «فاتورة البيع بخسارة» فرحّل
النظامُ الفاتورة — قرأ «السماح بالحفظ» حفظاً فقط. الإعدادان كانا منطقيَّين
(سماح = حفظ+ترحيل، منع = لا حفظ ولا ترحيل) فغابت الحالة الوسطى:

- `allow`     : تحذيرٌ فقط — يُحفظ ويُرحَّل.
- `save_only` : يُحفظ مسودةً (لا حركة مخزون ولا قيد) ويُمنع ترحيله.
- `block`     : لا حفظ ولا ترحيل.

كل حارسٍ × كل سياسةٍ × (حفظ، ترحيل).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.serializers import SalesInvoiceSerializer
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

ALLOW = SalesSettings.POLICY_ALLOW
SAVE_ONLY = SalesSettings.POLICY_SAVE_ONLY
BLOCK = SalesSettings.POLICY_BLOCK


@pytest.fixture
def env():
    owner = User.objects.create_user(username="policies", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة السياسات", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-P", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    # للخسارة: التكلفة 100 والرصيد وافر. للسالب: رصيدٌ 1 والمطلوب 2.
    loss_product = Product.objects.create(
        tenant=tenant, sku="POL-LOSS", name_ar="منتج الخسارة", quantity_on_hand=100, avg_cost=100)
    short_product = Product.objects.create(
        tenant=tenant, sku="POL-SHORT", name_ar="منتج ناقص", quantity_on_hand=1, avg_cost=10)
    return tenant, customer, loss_product, short_product


def _set(tenant, **fields):
    SalesSettings.objects.update_or_create(tenant=tenant, defaults=fields)


def _body(tenant, customer, product, *, number, qty, price, stock_on_post):
    return {
        "invoice_number": number,
        "customer": customer.id,
        "currency": tenant._test_currency.pk,
        "invoice_date": "2026-06-15",
        "invoice_type": SalesInvoice.INVOICE_CREDIT,
        "stock_on_post": stock_on_post,
        "invoice_kind": SalesInvoice.INVOICE_KIND_SALE,
        "lines": [{"product": product.id, "quantity": str(qty), "unit_price": str(price)}],
    }


def _save(tenant, **kw):
    ser = SalesInvoiceSerializer(data=_body(tenant, **kw))
    ser.is_valid(raise_exception=True)
    return ser.save(tenant=tenant)


def _draft(tenant, customer, product, *, number, qty, price, stock_on_post):
    """مسودةٌ بالـORM مباشرةً — تتخطّى حارس الحفظ لنختبر حارس الترحيل وحده."""
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=stock_on_post,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(str(qty)), unit_price=Decimal(str(price)))
    return inv


# ── الافتراضات: لا تغيّر في سلوك أي شركة قائمة ──

def test_defaults_keep_the_old_behaviour(env):
    tenant, *_ = env
    ss = SalesSettings.objects.get_or_create(tenant=tenant)[0]
    assert ss.negative_stock_policy == ALLOW
    assert ss.loss_invoice_policy == ALLOW


# ── المخزون السالب: الحفظ ──

@pytest.mark.parametrize("policy,saved", [(ALLOW, True), (SAVE_ONLY, True), (BLOCK, False)])
def test_negative_stock_save(env, policy, saved):
    tenant, customer, _loss, short = env
    _set(tenant, negative_stock_policy=policy)
    kw = dict(customer=customer, product=short, number=f"NEG-S-{policy}",
              qty=2, price=50, stock_on_post=True)
    if saved:
        inv = _save(tenant, **kw)
        assert SalesInvoice.objects.filter(pk=inv.pk).exists()
    else:
        # حارس الرصيد عند الحفظ يرفع خطأ DRF (حقل `lines`) لا خطأ Django.
        with pytest.raises(DRFValidationError) as exc:
            _save(tenant, **kw)
        msg = str(exc.value.detail)
        assert "تتجاوز المتوفر" in msg
        assert "سياسة الرصيد السالب" in msg
        assert not SalesInvoice.objects.filter(
            tenant=tenant, invoice_number=f"NEG-S-{policy}").exists()


# ── المخزون السالب: الترحيل ──

def test_negative_stock_post_allowed_when_allow(env):
    tenant, customer, _loss, short = env
    _set(tenant, negative_stock_policy=ALLOW)
    inv = _draft(tenant, customer, short, number="NEG-P-allow", qty=2, price=50, stock_on_post=True)
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
    short.refresh_from_db()
    assert Decimal(str(short.quantity_on_hand)) == Decimal("-1")


@pytest.mark.parametrize("policy", [SAVE_ONLY, BLOCK])
def test_negative_stock_post_refused_when_not_allow(env, policy):
    tenant, customer, _loss, short = env
    _set(tenant, negative_stock_policy=policy)
    inv = _draft(tenant, customer, short, number=f"NEG-P-{policy}", qty=2, price=50, stock_on_post=True)
    with pytest.raises(ValidationError) as exc:
        post_sales_invoice(inv)
    msg = str(exc.value)
    assert "لا يمكن صرف" in msg
    # الرسالة تسمّي الإعداد والخيار الحالي.
    assert "سياسة الرصيد السالب" in msg
    assert dict(SalesSettings.POLICY_CHOICES)[policy] in msg
    inv.refresh_from_db()
    assert inv.status != SalesInvoice.STATUS_POSTED
    short.refresh_from_db()
    assert Decimal(str(short.quantity_on_hand)) == Decimal("1")


# ── فاتورة الخسارة: الحفظ ──

@pytest.mark.parametrize("policy,saved", [(ALLOW, True), (SAVE_ONLY, True), (BLOCK, False)])
def test_loss_invoice_save(env, policy, saved):
    tenant, customer, loss, _short = env
    _set(tenant, loss_invoice_policy=policy)
    kw = dict(customer=customer, product=loss, number=f"LOSS-S-{policy}",
              qty=1, price=80, stock_on_post=False)
    if saved:
        inv = _save(tenant, **kw)
        assert SalesInvoice.objects.filter(pk=inv.pk).exists()
    else:
        with pytest.raises(ValidationError) as exc:
            _save(tenant, **kw)
        assert "فاتورة البيع بخسارة" in str(exc.value)
        assert not SalesInvoice.objects.filter(
            tenant=tenant, invoice_number=f"LOSS-S-{policy}").exists()


# ── فاتورة الخسارة: الترحيل ──

def test_loss_invoice_post_allowed_when_allow(env):
    tenant, customer, loss, _short = env
    _set(tenant, loss_invoice_policy=ALLOW)
    inv = _draft(tenant, customer, loss, number="LOSS-P-allow", qty=1, price=80, stock_on_post=False)
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


@pytest.mark.parametrize("policy", [SAVE_ONLY, BLOCK])
def test_loss_invoice_post_refused_when_not_allow(env, policy):
    tenant, customer, loss, _short = env
    _set(tenant, loss_invoice_policy=policy)
    inv = _draft(tenant, customer, loss, number=f"LOSS-P-{policy}", qty=1, price=80, stock_on_post=False)
    with pytest.raises(ValidationError) as exc:
        post_sales_invoice(inv)
    msg = str(exc.value)
    assert "فاتورة البيع بخسارة" in msg
    assert dict(SalesSettings.POLICY_CHOICES)[policy] in msg
    inv.refresh_from_db()
    assert inv.status != SalesInvoice.STATUS_POSTED


def test_save_only_draft_then_post_is_the_owners_scenario(env):
    """سيناريو المالك بالحرف: «السماح بالحفظ كمسودة» تُحفظ ولا تُرحَّل."""
    tenant, customer, loss, _short = env
    _set(tenant, loss_invoice_policy=SAVE_ONLY)
    inv = _save(tenant, customer=customer, product=loss, number="OWNER-1",
                qty=1, price=80, stock_on_post=False)
    assert inv.status != SalesInvoice.STATUS_POSTED
    with pytest.raises(ValidationError):
        post_sales_invoice(inv)


def test_profit_invoice_posts_under_every_policy(env):
    tenant, customer, loss, _short = env
    for i, policy in enumerate((ALLOW, SAVE_ONLY, BLOCK)):
        _set(tenant, loss_invoice_policy=policy)
        inv = _draft(tenant, customer, loss, number=f"PROFIT-{i}", qty=1, price=150, stock_on_post=False)
        post_sales_invoice(inv)
        inv.refresh_from_db()
        assert inv.status == SalesInvoice.STATUS_POSTED


# ── الإعفاءات تبقى: الخدمة والمرجع ──

def test_service_line_exempt_from_negative_stock_under_block(env):
    tenant, customer, _loss, _short = env
    _set(tenant, negative_stock_policy=BLOCK)
    service = Product.objects.create(tenant=tenant, sku="POL-SVC", name_ar="خدمة", is_service=True)
    inv = _save(tenant, customer=customer, product=service, number="SVC-1",
                qty=5, price=100, stock_on_post=True)
    assert SalesInvoice.objects.filter(pk=inv.pk).exists()


def test_sale_return_exempt_from_loss_guard_under_block(env):
    tenant, customer, loss, _short = env
    _set(tenant, loss_invoice_policy=BLOCK)
    body = _body(tenant, customer, loss, number="RET-1", qty=1, price=80, stock_on_post=False)
    body["invoice_kind"] = SalesInvoice.INVOICE_KIND_SALE_RETURN
    ser = SalesInvoiceSerializer(data=body)
    ser.is_valid(raise_exception=True)
    inv = ser.save(tenant=tenant)
    assert SalesInvoice.objects.filter(pk=inv.pk).exists()


# ── واجهة الإعدادات (API) ──

def test_settings_api_exposes_and_validates_the_new_fields(env, client):
    tenant, *_ = env
    owner = User.objects.get(username="policies")
    client.force_login(owner)
    hdr = {"HTTP_X_TENANT_ID": str(tenant.TenantID)}
    res = client.patch(
        "/api/sales/settings/current/",
        {"negative_stock_policy": SAVE_ONLY, "loss_invoice_policy": BLOCK},
        content_type="application/json", **hdr)
    assert res.status_code == 200, res.content
    body = res.json()
    assert body["negative_stock_policy"] == SAVE_ONLY
    assert body["loss_invoice_policy"] == BLOCK
    assert "allow_negative_stock_default" not in body
    assert "block_loss_invoices" not in body
    bad = client.patch(
        "/api/sales/settings/current/", {"loss_invoice_policy": "maybe"},
        content_type="application/json", **hdr)
    assert bad.status_code == 400
