"""محرّك FIFO لطبقات كلفة المخزون (`inventory/fifo.py`) — مواصفة #137 المرحلة 1.

يثبت:
  1. مثال المالك: طبقتان بسعرين مختلفين ⟵ كلفة كل استهلاكٍ من سعر طبقته الفعلي
     لا من متوسطٍ مرجَّح (٥٠٠ لا ١٢١٤٫٥).
  2. استهلاكٌ يعبر طبقتين في نداءٍ واحد ⟵ كلفة كل جزءٍ بسعر طبقته + صفّا استهلاك.
  3. الرَّدّ الدقيق (`restore`): `remaining_qty` يعود كما كان بالضبط، وصفوف
     الاستهلاك تُحذف، والطبقات نفسها (بمعرّفها) لا تُحذف.
  4. حارس التآكل: عشر دورات استهلاك/ردّ ⟵ الحالة النهائية مطابقة للبداية تماماً.
  5. نفاد الطبقات (مخزون سالب): كلفة ما تيسّر + كمية غير مغطّاة صريحة، بلا استثناء.
  6. العزل بين الشركات: شركتان بنفس اسم المنتج ⟵ الاستهلاك لا يمسّ الأخرى.
  7. عدّ الاستعلامات: `open_layers_value`/`open_layers_quantity` استعلامٌ واحد
     لعشرة منتجات معاً.
  8. `derived_avg_cost` بصفر كمية ⟵ صفر بلا انفجار.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from inventory.fifo import (
    consume,
    create_layer,
    derived_avg_cost,
    open_layers_quantity,
    open_layers_value,
    restore,
)
from inventory.models import Product, StockLayer, StockLayerConsumption, StockMovement
from tenants.services import create_company


def _make_tenant(name):
    user = User.objects.create_user(username=f"fifo-{name}", password="x")
    return create_company(f"شركة {name}", user)


def _make_product(tenant, sku, name="صنف اختبار"):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=name,
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )


def _movement(tenant, product, *, mtype="IN", qty, unit_cost=Decimal("0"), date="2026-01-01"):
    return StockMovement.objects.create(
        tenant=tenant, product=product, movement_type=mtype,
        quantity=Decimal(qty), unit_cost=Decimal(unit_cost),
        movement_date=date, reference_type="MANUAL",
    )


def _lay_in(tenant, product, qty, cost, date="2026-01-01"):
    mv = _movement(tenant, product, mtype="IN", qty=qty, unit_cost=cost, date=date)
    return create_layer(movement=mv, quantity=qty, unit_cost=cost)


@pytest.mark.django_db
def test_owner_example_two_layers_consumed_separately_at_actual_layer_cost():
    """طبقتان ٥٠@١٠ ثمّ ٢٠@٦٠ ⟵ استهلاك ٥٠ كلفته ٥٠٠ (لا ١٢١٤٫٥ متوسطاً مرجّحاً)،
    ثمّ استهلاك ٢٠ كلفته ١٢٠٠."""
    tenant = _make_tenant("مثال المالك")
    product = _make_product(tenant, "FIFO-1")
    _lay_in(tenant, product, "50", "10", date="2026-01-01")
    _lay_in(tenant, product, "20", "60", date="2026-01-05")

    out1 = _movement(tenant, product, mtype="OUT", qty="50")
    result1 = consume(movement=out1, quantity="50")
    assert result1.cost == Decimal("500.0000")
    assert result1.uncovered_qty == Decimal("0")

    out2 = _movement(tenant, product, mtype="OUT", qty="20")
    result2 = consume(movement=out2, quantity="20")
    assert result2.cost == Decimal("1200.0000")
    assert result2.uncovered_qty == Decimal("0")


@pytest.mark.django_db
def test_consume_crosses_two_layers_in_one_call_and_creates_two_consumption_rows():
    """٦٠ من (٥٠@١٠ + ٢٠@٦٠) في نداءٍ واحد ⟵ ٥٠٠ + ١٠×٦٠ = ١١٠٠، وصفّا استهلاك."""
    tenant = _make_tenant("عبور طبقتين")
    product = _make_product(tenant, "FIFO-2")
    layer1 = _lay_in(tenant, product, "50", "10", date="2026-01-01")
    layer2 = _lay_in(tenant, product, "20", "60", date="2026-01-05")

    out = _movement(tenant, product, mtype="OUT", qty="60")
    result = consume(movement=out, quantity="60")

    assert result.cost == Decimal("1100.0000")
    assert result.uncovered_qty == Decimal("0")

    consumptions = StockLayerConsumption.objects.filter(movement=out).order_by("id")
    assert consumptions.count() == 2
    assert consumptions[0].layer_id == layer1.id
    assert consumptions[0].quantity == Decimal("50.0000")
    assert consumptions[1].layer_id == layer2.id
    assert consumptions[1].quantity == Decimal("10.0000")

    layer1.refresh_from_db()
    layer2.refresh_from_db()
    assert layer1.remaining_qty == Decimal("0.0000")
    assert layer2.remaining_qty == Decimal("10.0000")


@pytest.mark.django_db
def test_restore_returns_remaining_qty_exactly_and_deletes_consumption_rows_only():
    """استهلك ثمّ `restore` ⟵ `remaining_qty` عاد كما كان بالضبط، وصفوف الاستهلاك
    حُذفت، والطبقات نفسها (نفس الـpk) بقيت موجودة."""
    tenant = _make_tenant("الرد الدقيق")
    product = _make_product(tenant, "FIFO-3")
    layer1 = _lay_in(tenant, product, "50", "10")
    layer2 = _lay_in(tenant, product, "20", "60")
    layer1_pk, layer2_pk = layer1.pk, layer2.pk

    out = _movement(tenant, product, mtype="OUT", qty="60")
    consume(movement=out, quantity="60")

    restored_count = restore(out)
    assert restored_count == 2

    assert StockLayerConsumption.objects.filter(movement=out).count() == 0

    layer1.refresh_from_db()
    layer2.refresh_from_db()
    assert layer1.pk == layer1_pk
    assert layer2.pk == layer2_pk
    assert layer1.remaining_qty == Decimal("50.0000")
    assert layer2.remaining_qty == Decimal("20.0000")

    # الطبقتان لم تُحذفا.
    assert StockLayer.objects.filter(pk__in=[layer1_pk, layer2_pk]).count() == 2


@pytest.mark.django_db
def test_ten_cycles_of_consume_then_restore_leave_layers_exactly_as_they_started():
    """حارس التآكل: عشر دورات (استهلاك ثمّ ردّ) ⟵ الحالة النهائية مطابقة تماماً."""
    tenant = _make_tenant("حارس التآكل")
    product = _make_product(tenant, "FIFO-4")
    layer1 = _lay_in(tenant, product, "50", "10")
    layer2 = _lay_in(tenant, product, "20", "60")

    for _ in range(10):
        out = _movement(tenant, product, mtype="OUT", qty="60")
        consume(movement=out, quantity="60")
        restore(out)

    layer1.refresh_from_db()
    layer2.refresh_from_db()
    assert layer1.remaining_qty == Decimal("50.0000")
    assert layer2.remaining_qty == Decimal("20.0000")
    assert StockLayerConsumption.objects.filter(layer__in=[layer1, layer2]).count() == 0


@pytest.mark.django_db
def test_consume_returns_partial_cost_and_uncovered_qty_when_layers_run_out():
    """طلب ١٠٠ وفي الرتل ٧٠ ⟵ الكلفة كلفة السبعين فقط، وغير المغطّى ٣٠، بلا استثناء."""
    tenant = _make_tenant("نفاد الطبقات")
    product = _make_product(tenant, "FIFO-5")
    _lay_in(tenant, product, "70", "5")

    out = _movement(tenant, product, mtype="OUT", qty="100")
    result = consume(movement=out, quantity="100")

    assert result.cost == Decimal("350.0000")  # 70 * 5
    assert result.uncovered_qty == Decimal("30.0000")

    remaining_layers = StockLayer.objects.filter(product=product, remaining_qty__gt=0)
    assert remaining_layers.count() == 0


@pytest.mark.django_db
def test_consumption_is_isolated_between_tenants_with_same_product_name():
    """شركتان لهما منتج بنفس الاسم ⟵ استهلاك إحداهما لا يمسّ طبقات الأخرى."""
    tenant_a = _make_tenant("شركة أ")
    tenant_b = _make_tenant("شركة ب")
    product_a = _make_product(tenant_a, "FIFO-6A", name="نفس الاسم")
    product_b = _make_product(tenant_b, "FIFO-6B", name="نفس الاسم")
    _lay_in(tenant_a, product_a, "50", "10")
    layer_b = _lay_in(tenant_b, product_b, "50", "10")

    out = _movement(tenant_a, product_a, mtype="OUT", qty="50")
    result = consume(movement=out, quantity="50")
    assert result.cost == Decimal("500.0000")
    assert result.uncovered_qty == Decimal("0")

    layer_b.refresh_from_db()
    assert layer_b.remaining_qty == Decimal("50.0000")


@pytest.mark.django_db
def test_open_layers_value_and_quantity_use_a_single_aggregate_query(django_assert_num_queries):
    """`open_layers_value`/`open_layers_quantity` لعشرة منتجات ⟵ استعلامٌ واحد."""
    tenant = _make_tenant("عدّ الاستعلامات")
    products = [_make_product(tenant, f"FIFO-Q{i}") for i in range(10)]
    for i, product in enumerate(products):
        _lay_in(tenant, product, "10", str(5 + i))

    product_ids = [p.id for p in products]
    with django_assert_num_queries(1):
        value_map = open_layers_value(tenant_id=tenant.TenantID, product_ids=product_ids)
    with django_assert_num_queries(1):
        qty_map = open_layers_quantity(tenant_id=tenant.TenantID, product_ids=product_ids)

    for i, product in enumerate(products):
        assert qty_map[product.id] == Decimal("10.0000")
        assert value_map[product.id] == Decimal(str(10 * (5 + i))) + Decimal("0.0000")


@pytest.mark.django_db
def test_open_layers_value_returns_empty_dict_without_query_for_empty_product_list(
    django_assert_num_queries,
):
    tenant = _make_tenant("قائمة فارغة")
    with django_assert_num_queries(0):
        assert open_layers_value(tenant_id=tenant.TenantID, product_ids=[]) == {}
    with django_assert_num_queries(0):
        assert open_layers_quantity(tenant_id=tenant.TenantID, product_ids=[]) == {}


@pytest.mark.django_db
def test_derived_avg_cost_is_zero_when_open_quantity_is_zero():
    tenant = _make_tenant("صفر كمية")
    product = _make_product(tenant, "FIFO-7")
    assert derived_avg_cost(tenant_id=tenant.TenantID, product_id=product.id) == Decimal("0")


@pytest.mark.django_db
def test_derived_avg_cost_matches_value_over_quantity():
    tenant = _make_tenant("متوسط مشتق")
    product = _make_product(tenant, "FIFO-8")
    _lay_in(tenant, product, "50", "10")
    _lay_in(tenant, product, "20", "60")
    # (50*10 + 20*60) / 70 = (500+1200)/70 = 24.285714... -> quantized 4 decimals
    expected = (Decimal("1700") / Decimal("70")).quantize(Decimal("0.0001"))
    assert derived_avg_cost(tenant_id=tenant.TenantID, product_id=product.id) == expected
