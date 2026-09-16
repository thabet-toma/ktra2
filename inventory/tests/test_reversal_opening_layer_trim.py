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
