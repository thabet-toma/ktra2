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
  9. AVCO: توزيع تناسبي، فائض يعود للخلف، ونفاد الطبقات.
  10. ردّ تناسبي وأصول مختلطة، وبقاء ردّ FIFO كما هو.
  11. عدد الاستعلامات ثابت؛ وترتيب الرد ثابت بعد إعادة إنشاء الصفوف.
  12. رفض طريقة صرف مجهولة، وصرف الطرق الأخرى بترتيب FIFO.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from inventory.fifo import (
    consume,
    create_layer,
    derived_avg_cost,
    open_layers_quantity,
    open_layers_value,
    restore,
    restore_partial,
)
from inventory.models import Product, StockLayer, StockLayerConsumption, StockLayerRestoration, StockMovement
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


def _avco_setup(name):
    tenant = _make_tenant(name)
    product = _make_product(tenant, name)
    a = _lay_in(tenant, product, "8", "10", "2026-01-01")
    b = _lay_in(tenant, product, "4", "16", "2026-01-02")
    out = _movement(tenant, product, mtype="OUT", qty="10")
    return tenant, product, a, b, out


def _rows(model, **filters):
    return list(model.objects.filter(**filters).order_by("id").values_list(
        "layer_id", "quantity", "unit_cost"))


def _remaining(*layers):
    for layer in layers:
        layer.refresh_from_db()
    return [layer.remaining_qty for layer in layers]


@pytest.mark.django_db
def test_avco_restore_after_replayed_rows():
    """يثبت ترتيب ردّ AVCO بعد إعادة إنشاء صفوف الاستهلاك."""
    tenant, product, a, b, out = _avco_setup("AVCO-REPLAY")
    out.cogs_method = "avco"
    out.save(update_fields=["cogs_method"])
    for layer, qty, remaining in [(b, "3.3334", "0.6666"), (a, "6.6666", "1.3334")]:
        layer.remaining_qty = Decimal(remaining)
        layer.save(update_fields=["remaining_qty"])
        StockLayerConsumption.objects.create(
            tenant=tenant, movement=out, layer=layer,
            quantity=Decimal(qty), unit_cost=layer.unit_cost,
        )
    ret = _movement(tenant, product, mtype="IN", qty="4")
    result = restore_partial(movements=[out], quantity="4", restored_by=ret)
    assert _rows(StockLayerRestoration, movement=ret) == [
        (a.pk, Decimal("2.6666"), Decimal("10")),
        (b.pk, Decimal("1.3334"), Decimal("16")),
    ]
    assert result.cost == Decimal("48.0004")
    assert dict(StockLayerConsumption.objects.filter(movement=out).values_list(
        "layer_id", "quantity",
    )) == {a.pk: Decimal("4.0000"), b.pk: Decimal("2.0000")}
    assert _remaining(a, b) == [Decimal("4.0000"), Decimal("2.0000")]


@pytest.mark.django_db
@pytest.mark.parametrize("method", [None, "AVCO", "x"])
def test_consume_rejects_unknown_method(method):
    """يرفض طريقة الصرف المجهولة قبل الاستعلام."""
    tenant, product, a, b, out = _avco_setup("INVALID-" + str(method))
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(ValueError, match="Unknown COGS method"):
            consume(movement=out, quantity="10", method=method)
    assert len(queries) == 0
    assert _remaining(a, b) == [Decimal("8"), Decimal("4")]
    assert not StockLayerConsumption.objects.filter(movement=out).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["fifo", "standard", "last_purchase"])
def test_fifo_wise_methods(method):
    """تستهلك الطرق المحددة بترتيب FIFO."""
    tenant, product, a, b, out = _avco_setup("METHOD-" + method)
    result = consume(movement=out, quantity="10", method=method)
    assert (result.cost, result.uncovered_qty) == (Decimal("112"), Decimal("0"))
    assert _remaining(a, b) == [Decimal("0"), Decimal("2")]
    assert _rows(StockLayerConsumption, movement=out) == [
        (a.pk, Decimal("8"), Decimal("10")),
        (b.pk, Decimal("2"), Decimal("16")),
    ]


@pytest.mark.django_db
def test_avco_owner_example():
    """يتحقق من مثال المالك للصرف التناسبي."""
    tenant, product, a, b, out = _avco_setup("AVCO-T1")
    result = consume(movement=out, quantity="10", method="avco")
    assert _rows(StockLayerConsumption, movement=out) == [
        (a.pk, Decimal("6.6666"), Decimal("10")),
        (b.pk, Decimal("3.3334"), Decimal("16")),
    ]
    assert (result.cost, result.uncovered_qty) == (Decimal("120.0004"), Decimal("0"))
    assert _remaining(a, b) == [Decimal("1.3334"), Decimal("0.6666")]
    c = _lay_in(tenant, product, "8", "20", "2026-01-03")
    out2 = _movement(tenant, product, mtype="OUT", qty="10")
    result = consume(movement=out2, quantity="10", method="avco")
    assert result.cost == Decimal("183.9996")
    assert result.uncovered_qty == 0
    assert _remaining(a, b, c) == [0, 0, 0]


@pytest.mark.django_db
def test_avco_spill_back():
    """الباقي الساذج في الطبقة الأخيرة يجعلها سالبة بمقدار 0.0002."""
    tenant = _make_tenant("AVCO-T2")
    product = _make_product(tenant, "AVCO-T2")
    layers = [
        _lay_in(tenant, product, qty, str(10 + i), f"2026-01-0{i + 1}")
        for i, qty in enumerate(["1", "1", "1", "0.0001"])
    ]
    out = _movement(tenant, product, mtype="OUT", qty="3")
    consume(movement=out, quantity="3", method="avco")
    quantities = [r[1] for r in _rows(StockLayerConsumption, movement=out)]
    assert quantities == list(map(Decimal, ["0.9999", "1.0000", "1.0000", "0.0001"]))
    assert sum(quantities) == Decimal("3.0000")
    assert all(q >= 0 for q in _remaining(*layers))


@pytest.mark.django_db
def test_avco_running_out():
    """يعيد الكمية غير المغطّاة عند نفاد الطبقات."""
    tenant = _make_tenant("AVCO-T3")
    product = _make_product(tenant, "AVCO-T3")
    layers = [_lay_in(tenant, product, "2", "10"), _lay_in(tenant, product, "3", "20")]
    out = _movement(tenant, product, mtype="OUT", qty="7")
    result = consume(movement=out, quantity="7", method="avco")
    assert (result.cost, result.uncovered_qty) == (Decimal("80.0000"), Decimal("2.0000"))
    assert _remaining(*layers) == [0, 0]


@pytest.mark.django_db
def test_avco_proportional_restore():
    """يردّ استهلاك AVCO تناسبياً إلى طبقاته."""
    tenant, product, a, b, out = _avco_setup("AVCO-T4")
    consume(movement=out, quantity="10", method="avco")
    out.cogs_method = "avco"
    out.save(update_fields=["cogs_method"])
    ret = _movement(tenant, product, mtype="IN", qty="4")
    result = restore_partial(movements=[out], quantity="4", restored_by=ret)
    assert (result.quantity, result.cost, result.rows) == (
        Decimal("4.0000"), Decimal("48.0004"), 2,
    )
    assert result.by_origin == {out.pk: (Decimal("4.0000"), Decimal("48.0004"))}
    assert _rows(StockLayerRestoration, movement=ret) == [
        (a.pk, Decimal("2.6666"), Decimal("10")),
        (b.pk, Decimal("1.3334"), Decimal("16")),
    ]
    assert set(StockLayerRestoration.objects.filter(movement=ret).values_list(
        "origin_movement_id", flat=True,
    )) == {out.pk}
    assert _rows(StockLayerConsumption, movement=out) == [
        (a.pk, Decimal("4"), Decimal("10")), (b.pk, Decimal("2"), Decimal("16")),
    ]
    assert _remaining(a, b) == [Decimal("4"), Decimal("2")]
    restore_partial(movements=[out], quantity="6", restored_by=ret)
    assert not StockLayerConsumption.objects.filter(movement=out).exists()
    assert _remaining(a, b) == [Decimal("8"), Decimal("4")]


@pytest.mark.django_db
def test_avco_mixed_origins():
    """يردّ الأصول المختلطة حسب طريقة كل أصل."""
    tenant = _make_tenant("AVCO-T5")
    product = _make_product(tenant, "AVCO-T5")
    a = _lay_in(tenant, product, "8", "10")
    b = _lay_in(tenant, product, "8", "20", "2026-01-02")
    avco = _movement(tenant, product, mtype="OUT", qty="6")
    avco.cogs_method = "avco"
    avco.save(update_fields=["cogs_method"])
    consume(movement=avco, quantity="6", method="avco")
    fifo = _movement(tenant, product, mtype="OUT", qty="4")
    fifo.cogs_method = "fifo"
    fifo.save(update_fields=["cogs_method"])
    consume(movement=fifo, quantity="4")
    ret = _movement(tenant, product, mtype="IN", qty="7")
    restore_partial(movements=[fifo, avco], quantity="7", restored_by=ret)
    assert _remaining(a, b) == [Decimal("6.5"), Decimal("6.5")]
    assert list(StockLayerRestoration.objects.filter(movement=ret).order_by("id").values_list(
        "origin_movement_id", "layer_id", "quantity", "unit_cost",
    )) == [
        (fifo.pk, a.pk, Decimal("4"), Decimal("10")),
        (avco.pk, a.pk, Decimal("1.5"), Decimal("10")),
        (avco.pk, b.pk, Decimal("1.5"), Decimal("20")),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("method", [None, "fifo"])
def test_fifo_restore_unchanged(method):
    """يبقى ردّ FIFO بعكس ترتيب الاستهلاك."""
    tenant, product, a, b, out = _avco_setup("FIFO-T6-" + str(method))
    out.cogs_method = method
    out.save(update_fields=["cogs_method"])
    # نفس صفّي مثال AVCO، لكن الأصل FIFO.
    for layer, qty in [(a, "6.6666"), (b, "3.3334")]:
        layer.remaining_qty -= Decimal(qty)
        layer.save(update_fields=["remaining_qty"])
        StockLayerConsumption.objects.create(
            tenant=tenant, movement=out, layer=layer,
            quantity=Decimal(qty), unit_cost=layer.unit_cost,
        )
    ret = _movement(tenant, product, mtype="IN", qty="4")
    result = restore_partial(movements=[out], quantity="4", restored_by=ret)
    assert result.cost == Decimal("60.0004")
    assert _rows(StockLayerRestoration, movement=ret) == [
        (b.pk, Decimal("3.3334"), Decimal("16")),
        (a.pk, Decimal("0.6666"), Decimal("10")),
    ]
    assert _remaining(a, b) == [Decimal("2"), Decimal("4")]


@pytest.mark.django_db
def test_avco_query_count_is_constant():
    """يبقى عدد استعلامات AVCO ثابتاً مع زيادة الطبقات."""
    tenant = _make_tenant("AVCO-T7")
    samples = []
    for count in (20, 200):
        product = _make_product(tenant, f"AVCO-T7-{count}")
        for _ in range(count):
            _lay_in(tenant, product, "10", "10")
        out = _movement(tenant, product, mtype="OUT", qty=str(count * 5))
        out.cogs_method = "avco"
        out.save(update_fields=["cogs_method"])
        ret = _movement(tenant, product, mtype="IN", qty=str(count))
        samples.append((count, out, ret))
    consume_counts, restore_counts = [], []
    for count, out, ret in samples:
        with CaptureQueriesContext(connection) as queries:
            consume(movement=out, quantity=str(count * 5), method="avco")
        consume_counts.append(len(queries))
        with CaptureQueriesContext(connection) as queries:
            restore_partial(movements=[out], quantity=str(count), restored_by=ret)
        restore_counts.append(len(queries))
    assert consume_counts[0] == consume_counts[1]
    assert restore_counts[0] == restore_counts[1]
    assert consume_counts[0] == 5
    assert restore_counts[0] == 8
