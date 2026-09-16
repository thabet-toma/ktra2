"""حذفُ وارِدٍ سبق FIFO لا يترك طبقاتٍ أكثر من الرصيد.

وارِدٌ سبق FIFO لا طبقةَ له؛ بضاعتُه ذابت في الطبقة الافتتاحيّة التي أنشأها الرأبُ
الكسول (`fifo.backfill_opening_layer`) عند أوّل حركةٍ بعده. فإلغاءُ ترحيله ينقص
الرصيدَ ولا ينقص الطبقات: Σ`remaining_qty` > `quantity_on_hand`، وأوّلُ بيعةٍ بعدها
تستهلك بضاعةً غيرَ موجودة، و`rebuild_fifo_layers` يُبلغ فرقاً بنيويّاً بلا سبب.

العلاجُ مرآةُ الرأب: `fifo.trim_opening_layers` تنقص **الطبقاتِ الافتتاحيّة وحدَها**
بمقدار ما حُذف من وارِدٍ بلا طبقة — لا تمسّ طبقةً حقيقيّةً لها حركةُ ورود، ولا مرتجعَ
بيعٍ عاد إلى طبقته الأصليّة (`RETURN_IN` بلا طبقةٍ خاصّة به ليس علامةَ ما قبل FIFO).
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from inventory.models import Product, StockLayer, StockMovement
from inventory.services import record_stock_movement, reverse_stock_movements
from tenants.services import create_company

pytestmark = pytest.mark.django_db

D = datetime.date(2026, 6, 1)


def _tenant(name):
    owner = User.objects.create_user(username=f"trim-{name}", password="x")
    return create_company(name, owner)


def _product(tenant, sku):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=sku,
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))


def _open_layers(product):
    layers = StockLayer.objects.filter(product=product, remaining_qty__gt=0)
    return (
        sum((l.remaining_qty for l in layers), Decimal("0")),
        sum((l.remaining_qty * l.unit_cost for l in layers), Decimal("0")).quantize(Decimal("0.01")),
    )


def _pre_fifo_purchase(tenant, product, qty, cost, ref):
    """شراءٌ كما سُجّل قبل FIFO: حركةٌ ورصيدٌ وكلفة، وصفرُ طبقات."""
    mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal(qty), unit_cost=Decimal(cost),
        reference_type="PURCHASE_INVOICE", reference_id=ref, movement_date=D, tenant=tenant)
    StockLayer.objects.filter(source_movement=mv).delete()
    return mv


def test_reversing_a_pre_fifo_purchase_trims_the_opening_layer_it_dissolved_into():
    tenant = _tenant("قبل")
    product = _product(tenant, "TR-1")
    _pre_fifo_purchase(tenant, product, "10", "100", ref=501)
    # أوّلُ حركةٍ بعد FIFO: الرأبُ يُنشئ افتتاحيّةً 10@100 ثمّ طبقةَ الوارد الجديد.
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("5"), unit_cost=Decimal("100"),
        reference_type="PURCHASE_INVOICE", reference_id=502, movement_date=D, tenant=tenant)
    assert _open_layers(product) == (Decimal("15.0000"), Decimal("1500.00"))

    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=501, reference_types=["PURCHASE_INVOICE"])

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("5.0000")
    assert _open_layers(product) == (Decimal("5.0000"), Decimal("500.00")), \
        "بقيت الطبقاتُ أكثرَ من الرصيد بعد حذف وارِدٍ سبق FIFO."
    assert not StockLayer.objects.filter(
        product=product, source_movement__isnull=True, remaining_qty__gt=0).exists()
    assert product.avg_cost == Decimal("100.0000")


def test_trim_never_takes_from_a_real_layer_or_below_what_was_consumed():
    """الافتتاحيّةُ مستهلَكةٌ جزئيّاً: يُنقص منها ما بقي فقط، والطبقةُ الحقيقيّة لا تُمسّ."""
    tenant = _tenant("جزئي")
    product = _product(tenant, "TR-2")
    _pre_fifo_purchase(tenant, product, "10", "100", ref=601)
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("7"),
        movement_date=D, tenant=tenant)  # الرأب: افتتاحيّة 10، تُستهلك 7 فيبقى 3
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("5"), unit_cost=Decimal("120"),
        reference_type="PURCHASE_INVOICE", reference_id=602, movement_date=D, tenant=tenant)

    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=601, reference_types=["PURCHASE_INVOICE"])

    opening = StockLayer.objects.get(product=product, source_movement__isnull=True)
    assert opening.remaining_qty == Decimal("0.0000")
    assert opening.original_qty - opening.remaining_qty == Decimal("7.0000"), \
        "انكسر سجلُّ ما استُهلك من الافتتاحيّة."
    real = StockLayer.objects.get(product=product, source_movement__reference_id=602)
    assert real.remaining_qty == Decimal("5.0000")


def test_reversing_a_layered_purchase_does_not_trim_anything():
    tenant = _tenant("عادي")
    product = _product(tenant, "TR-3")
    _pre_fifo_purchase(tenant, product, "4", "50", ref=701)
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("6"), unit_cost=Decimal("80"),
        reference_type="PURCHASE_INVOICE", reference_id=702, movement_date=D, tenant=tenant)

    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=702, reference_types=["PURCHASE_INVOICE"])

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("4.0000")
    assert _open_layers(product) == (Decimal("4.0000"), Decimal("200.00"))
    assert StockMovement.objects.filter(product=product).count() == 1


@pytest.mark.parametrize("with_real_layer", [False, True])
def test_full_unpost_repost_chain_never_leaves_more_layers_than_stock(with_real_layer):
    """سلسلةُ الإنتاج (شركة 6، 16/09/2026): صنفٌ بلا طبقات ← بيعٌ يُنشئ الافتتاحيّة ←
    إلغاءُ البيع ← إلغاءُ الشراء الذي منه البضاعة ← إعادتُه ← إعادةُ البيع.
    الثابت: Σ`remaining_qty` = max(الرصيد، 0) — لا طبقةَ استلامٍ مفتوحةٌ بلا بضاعة."""
    tenant = _tenant(f"سلسلة{int(with_real_layer)}")
    product = _product(tenant, f"TR-C{int(with_real_layer)}")
    _pre_fifo_purchase(tenant, product, "12", "270", ref=16)
    sold = "12"
    if with_real_layer:
        record_stock_movement(
            product=product, movement_type="IN", quantity=Decimal("3"), unit_cost=Decimal("270"),
            reference_type="PURCHASE_INVOICE", reference_id=17, movement_date=D, tenant=tenant)
        sold = "14"

    def sale():
        record_stock_movement(
            product=product, movement_type="OUT", quantity=Decimal(sold),
            reference_type="SALES_INVOICE", reference_id=900, movement_date=D, tenant=tenant)

    sale()
    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=900, reference_types=["SALES_INVOICE"])
    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=16, reference_types=["PURCHASE_INVOICE"])
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("12"), unit_cost=Decimal("270"),
        reference_type="PURCHASE_INVOICE", reference_id=16, movement_date=D, tenant=tenant)
    sale()

    product.refresh_from_db()
    expected = max(product.quantity_on_hand, Decimal("0"))
    assert _open_layers(product)[0] == expected, \
        "بقيت طبقةُ استلامٍ مفتوحةً بلا بضاعة بعد سلسلة الإلغاء وإعادة الترحيل."
    assert _open_layers(product)[1] == (expected * Decimal("270")).quantize(Decimal("0.01"))


def test_trim_takes_the_deleted_purchase_cost_out_of_the_opening_layer():
    """الافتتاحيّةُ بمتوسّط شراءين (100 و200 ⇒ 150). حذفُ شراء الـ200 يُنقص حسابَ المخزون
    10 × 200 بحذف قيده — فالطبقاتُ تنقص بالقدر نفسه، لا 10 × 150 (فرقٌ صامتٌ 500)."""
    tenant = _tenant("كلفة")
    product = _product(tenant, "TR-4")
    _pre_fifo_purchase(tenant, product, "10", "100", ref=801)
    _pre_fifo_purchase(tenant, product, "10", "200", ref=802)
    StockLayer.objects.filter(product=product).delete()  # الشراءان كلاهما قبل FIFO
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("1"), unit_cost=Decimal("150"),
        reference_type="PURCHASE_INVOICE", reference_id=803, movement_date=D, tenant=tenant)
    assert _open_layers(product) == (Decimal("21.0000"), Decimal("3150.00"))

    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=802, reference_types=["PURCHASE_INVOICE"])

    assert _open_layers(product) == (Decimal("11.0000"), Decimal("1150.00")), \
        "قُصّت الافتتاحيّةُ بمتوسّطها لا بكلفة الشراء المحذوف."
    opening = StockLayer.objects.get(product=product, source_movement__isnull=True)
    assert opening.unit_cost == Decimal("100.0000")


def test_trim_keeps_the_layer_cost_when_the_opening_layer_was_consumed():
    """صفوفُ استهلاكٍ قائمة تحمل كلفةَ الطبقة — تغييرُها يجعل ردَّها لاحقاً بكلفةٍ أخرى."""
    tenant = _tenant("مستهلكة")
    product = _product(tenant, "TR-5")
    _pre_fifo_purchase(tenant, product, "10", "100", ref=811)
    _pre_fifo_purchase(tenant, product, "10", "200", ref=812)
    StockLayer.objects.filter(product=product).delete()
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("2"),
        reference_type="SALES_INVOICE", reference_id=813, movement_date=D, tenant=tenant)

    reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=812, reference_types=["PURCHASE_INVOICE"])

    opening = StockLayer.objects.get(product=product, source_movement__isnull=True)
    assert opening.remaining_qty == Decimal("8.0000")
    assert opening.unit_cost == Decimal("150.0000")


def test_recompute_warns_when_layers_still_exceed_the_balance(caplog):
    """فائضٌ لا يقصّه الإلغاء (سببُه غيرُ وارِدٍ محذوف) لا يمرّ صامتاً."""
    from inventory.services import _recompute_product_stock
    tenant = _tenant("تحذير")
    product = _product(tenant, "TR-6")
    mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("5"), unit_cost=Decimal("10"),
        reference_type="PURCHASE_INVOICE", reference_id=901, movement_date=D, tenant=tenant)
    StockLayer.objects.create(
        tenant=tenant, product=product, layer_date=D, original_qty=Decimal("2"),
        remaining_qty=Decimal("2"), unit_cost=Decimal("10"), source_movement=mv)

    with caplog.at_level("WARNING", logger="inventory.services"):
        _recompute_product_stock(product)

    assert any("TR-6" in r.getMessage() for r in caplog.records), \
        "طبقاتٌ أكثرُ من الرصيد بعد إعادة الاحتساب ولا تحذير."
