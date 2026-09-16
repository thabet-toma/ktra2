"""إلغاءُ الترحيل لا يُصفّر كلفةَ صنفٍ بلا طبقاتٍ تغطّي رصيده.

ما حدث على الإنتاج (شركة 6، 16/09/2026): صنفٌ رصيده 7 وكلفته 190 وصفرُ طبقات
(بيعتُه الأخيرة سبقت نشرَ FIFO فلم تمرّ بالرأب الكسول). إلغاءُ ترحيل تلك البيعة
أعاد الرصيدَ من دفتر الحركات، ثمّ كتب `avg_cost` من `derived_avg_cost` على رتلٍ
فارغ ⟵ **صفر**؛ وإعادةُ الترحيل قيّدت ت.ب.م صفراً (نقص 760 = 4×190).

والجذر: `_recompute_product_stock` لا تمرّ بـ`fifo.backfill_opening_layer` التي
يمرّ بها كلُّ ترحيلٍ عاديّ. والعلاج عبرها هي لا منطقَ رأبٍ ثانٍ:
- الكميّةُ اليتيمةُ القائمةُ قبل الإلغاء ⟵ بكلفة `avg_cost` الملتقطة قبل الكتابة
  فوقها (القيمةُ الدفتريّة، كما في `record_stock_movement`).
- ووحداتُ صرفٍ مُلغًى بلا صفوف استهلاكٍ تُردّ ⟵ بكلفة حركته نفسِها: هي عينُ ما
  يعود إلى حساب المخزون بحذف قيده، فالطبقاتُ تطابق الدفترَ قرشاً بقرش.

ومسارٌ ثانٍ بنفس العطب: إلغاءُ إرساليّة بيع (`void_delivery_note`) كان يحذف
حركةَ الصرف **بلا** `fifo.restore`، فتسقط صفوفُ الاستهلاك بالتتالي وتبقى الطبقاتُ
مستهلَكة — فيعود الرصيدُ بلا كلفة حتى لصنفٍ طبقاتُه كاملة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APIClient

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product, StockLayer, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

Q2 = Decimal("0.01")


@pytest.fixture
def env():
    owner = User.objects.create_user(username="orphancost", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة الرصيد اليتيم", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-OC", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    cogs = Account.objects.create(
        tenant=tenant, code="5101-OC", name="تكلفة مبيعات", account_type="Expense",
        is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-OC", name="مخزون", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-OC", name="مبيعات", account_type="Revenue", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv_acc
    ss.default_revenue_account_product = rev
    ss.save(update_fields=[
        "default_cogs_account", "default_inventory_account",
        "default_revenue_account_product",
    ])
    return tenant, owner, cur, customer, cogs


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _product(tenant, sku):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=f"منتج {sku}",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )


def _receive(tenant, product, qty, unit_cost, *, date="2026-06-01"):
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal(qty),
        unit_cost=Decimal(unit_cost), reference_type="OPENING", reference_id=0,
        movement_date=date, tenant=tenant,
    )


def _invoice(tenant, cur, customer, product, *, number, qty, stock_on_post=True):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=stock_on_post)
    line = SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(qty), unit_price=Decimal("500"))
    return inv, line


def _strip_layers_as_before_fifo(product):
    """حالةُ ما قبل FIFO: الحركاتُ والرصيدُ والكلفةُ كما هي، وصفرُ طبقات
    (وصفوفُ الاستهلاك تسقط معها بالتتالي)."""
    StockLayer.objects.filter(product=product).delete()


def _layers_qty_value(product):
    layers = list(StockLayer.objects.filter(product=product, remaining_qty__gt=0))
    qty = sum((l.remaining_qty for l in layers), Decimal("0"))
    value = sum((l.remaining_qty * l.unit_cost for l in layers), Decimal("0"))
    return qty, value.quantize(Q2)


def _sale_cost(invoice_id):
    total = StockMovement.objects.filter(
        reference_type="SALE", reference_id=invoice_id,
    ).aggregate(t=Sum("total_cost"))["t"]
    return Decimal(str(total or 0)).quantize(Q2)


def _cogs_debit(journal_id, cogs_account):
    total = JournalLine.objects.filter(
        journal_id=journal_id, account=cogs_account, debit__gt=0,
    ).aggregate(t=Sum("debit"))["t"]
    return Decimal(str(total or 0)).quantize(Q2)


def test_unposting_a_sale_of_layerless_stock_keeps_its_cost_and_repost_books_it(env):
    """حالةُ الإنتاج بأرقامها: 11 بكلفة 190، بيعةُ 4 سبقت FIFO، فبقي 7 بلا طبقات."""
    tenant, owner, cur, customer, cogs = env
    product = _product(tenant, "OC-1")
    _receive(tenant, product, "11", "190")
    inv, _ = _invoice(tenant, cur, customer, product, number="OC-INV-1", qty="4")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    _strip_layers_as_before_fifo(product)
    product.refresh_from_db()
    assert (product.quantity_on_hand, product.avg_cost) == (Decimal("7.0000"), Decimal("190.0000"))

    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("11.0000")
    assert product.avg_cost == Decimal("190.0000"), "إلغاءُ الترحيل صفّر كلفةَ الصنف."
    assert _layers_qty_value(product) == (Decimal("11.0000"), Decimal("2090.00"))

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert _sale_cost(inv.id) == Decimal("760.00"), "أُعيد ترحيلُ البيعة بكلفةٍ غيرِ 4×190."
    assert _cogs_debit(inv.journal_id, cogs) == Decimal("760.00")
    product.refresh_from_db()
    assert product.avg_cost == Decimal("190.0000")


def test_unposting_when_layers_cover_part_of_the_balance_does_not_drift_the_value(env):
    """طبقاتٌ تغطّي جزءاً من الرصيد: 6 يتيمةٌ بكلفة 100، ووارِدٌ حقيقيٌّ 5@130،
    ثمّ يُلغى ترحيلُ بيعة 4 سبقت FIFO (قُيّدت بـ400). القيمةُ بعد الإلغاء =
    القيمةُ قبله + 400 بالضبط — لا 4 × متوسّطِ الطبقات الجاري (113.64)."""
    tenant, owner, cur, customer, cogs = env
    product = _product(tenant, "OC-2")
    _receive(tenant, product, "10", "100")
    inv, _ = _invoice(tenant, cur, customer, product, number="OC-INV-2", qty="4")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    assert _sale_cost(inv.id) == Decimal("400.00")
    _strip_layers_as_before_fifo(product)
    _receive(tenant, product, "5", "130", date="2026-06-20")
    product.refresh_from_db()
    value_before = (product.quantity_on_hand * product.avg_cost).quantize(Q2)
    assert _layers_qty_value(product) == (Decimal("11.0000"), value_before)

    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("15.0000")
    assert _layers_qty_value(product) == (Decimal("15.0000"), value_before + Decimal("400.00"))
    assert product.avg_cost == Decimal("110.0000")  # (6×100 + 5×130 + 4×100) ÷ 15


def test_unposting_a_fifo_era_sale_creates_no_extra_layer(env):
    """الرأبُ لا يُضاعف ما أعاده `fifo.restore` للتوّ."""
    tenant, owner, cur, customer, cogs = env
    product = _product(tenant, "OC-3")
    _receive(tenant, product, "10", "20")
    inv, _ = _invoice(tenant, cur, customer, product, number="OC-INV-3", qty="10")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    layers_before = StockLayer.objects.filter(product=product).count()

    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200

    assert StockLayer.objects.filter(product=product).count() == layers_before
    assert not StockLayer.objects.filter(product=product, source_movement__isnull=True).exists()
    assert _layers_qty_value(product) == (Decimal("10.0000"), Decimal("200.00"))
    product.refresh_from_db()
    assert product.avg_cost == Decimal("20.0000")


def test_voiding_a_delivery_note_returns_goods_to_their_layers_with_cost(env):
    """إرساليّةٌ تستهلك الطبقاتِ كلَّها ثمّ تُلغى: البضاعةُ تعود لطبقتها بكلفتها،
    وإعادةُ تسليمها تُقيَّد بنفس الكلفة لا بصفر."""
    tenant, owner, cur, customer, cogs = env
    product = _product(tenant, "OC-4")
    _receive(tenant, product, "5", "10")
    inv, line = _invoice(tenant, cur, customer, product, number="OC-INV-4", qty="5",
                         stock_on_post=False)
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    first = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 5}]},
        format="json")
    assert first.status_code in (200, 201), first.content
    assert _sale_cost(inv.id) == Decimal("50.00")

    res = c.delete(f"/api/sales/delivery-orders/{first.json()['id']}/")
    assert res.status_code == 200, res.content

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("5.0000")
    assert product.avg_cost == Decimal("10.0000"), "إلغاءُ الإرساليّة صفّر كلفةَ الصنف."
    assert _layers_qty_value(product) == (Decimal("5.0000"), Decimal("50.00"))
    assert not StockLayer.objects.filter(product=product, source_movement__isnull=True).exists()

    again = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 5}]},
        format="json")
    assert again.status_code in (200, 201), again.content
    assert _sale_cost(inv.id) == Decimal("50.00")
