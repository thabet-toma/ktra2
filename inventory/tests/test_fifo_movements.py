"""التحام محرّك FIFO (`inventory/fifo.py`) بـ`inventory.services.record_stock_movement`
(مواصفة #137 المرحلة 2).

يثبت:
  1. مثال المالك عبر `record_stock_movement` نفسها: وارد 50@10 ثم وارد 20@60
     ثم صادر 50 ⟵ `total_cost == 500` (لا 1214.50 التي يعطيها المتوسط 24.29)،
     ثم صادر 20 ⟵ 1200.
  2. `avg_cost` بعد الواردين = 24.2857 (مشتقّ من قيمة الطبقات ÷ كميّتها).
  3. الرَّدّ عبر `reverse_stock_movements`: بِع ثم اعكس ⟵ `remaining_qty` عاد
     كما كان، والطبقات نفسها (نفس pk) لم تُحذف.
  4. حارس التآكل: عشر دورات (صرف ثم عكس) ⟵ الحالة كما بدأت بالضبط.
  5. الحارس الجديد (الثغرة #8): اشترِ، بِع جزءاً، ثم حاول عكس حركة الشراء ⟵
     `ValidationError` عربية، ولا شيء حُذف.
  6. المخزون السالب: بلا طبقات، بيع 10 ⟵ طبقة `is_provisional=True` أُنشئت
     واستُهلكت، والكمية صارت -10، بلا استثناء.
  7. `restores_movement`: بِع (فتُستهلك طبقة)، ثم سجّل RETURN_IN بـ
     `restores_movement=<حركة البيع>` ⟵ الطبقة عادت لموقعها، ولم تُنشأ طبقة
     جديدة (عدّ الطبقات ثابت).
  8. عزل الشركات في `restores_movement`: تمرير حركة من شركة أخرى ⟵ `ValidationError`.
  9. قياس الأداء: فاتورة من 50 بنداً (50 نداءً لـ`record_stock_movement`) —
     سقف استعلامات مقيسٌ فعلياً (انظر التعليق أعلى الاختبار).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from inventory.models import Product, StockLayer, StockLayerConsumption, StockMovement
from inventory.services import record_stock_movement, reverse_stock_movements
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _make_tenant(name):
    user = User.objects.create_user(username=f"fifomv-{name}", password="x")
    return create_company(f"شركة {name}", user)


def _make_product(tenant, sku, name="صنف اختبار"):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=name,
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )


def test_owner_example_total_cost_is_fifo_not_weighted_average():
    """50@10 ثم 20@60 ثم صرف 50 ⟵ 500 (لا 1214.50)، ثم صرف 20 ⟵ 1200."""
    tenant = _make_tenant("مثال المالك RSM")
    product = _make_product(tenant, "RSM-1")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant,
    )
    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("20"),
        unit_cost=Decimal("60"), movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    out1 = record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("50"),
        movement_date="2026-01-10", tenant=tenant,
    )
    assert out1.total_cost == Decimal("500.00")
    product.refresh_from_db()

    out2 = record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("20"),
        movement_date="2026-01-11", tenant=tenant,
    )
    assert out2.total_cost == Decimal("1200.00")


def test_avg_cost_after_two_inbounds_is_derived_from_open_layers():
    """avg_cost بعد وارِدين = قيمة الطبقات المفتوحة ÷ كميّتها = 24.2857."""
    tenant = _make_tenant("متوسط مشتق RSM")
    product = _make_product(tenant, "RSM-2")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant,
    )
    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("20"),
        unit_cost=Decimal("60"), movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    expected = (Decimal("1700") / Decimal("70")).quantize(Decimal("0.0001"))
    assert product.avg_cost == expected


def test_reverse_stock_movements_restores_layers_to_original_position():
    """بِع ثم اعكس المستند ⟵ remaining_qty عاد كما كان، والطبقات نفسها لم تُحذف."""
    tenant = _make_tenant("رد الترحيل RSM")
    product = _make_product(tenant, "RSM-3")

    in_mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant,
        reference_type="MANUAL", reference_id=1,
    )
    layer = StockLayer.objects.get(source_movement=in_mv)
    layer_pk = layer.pk
    product.refresh_from_db()

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("30"),
        movement_date="2026-01-02", tenant=tenant,
        reference_type="SALE", reference_id=99,
    )
    layer.refresh_from_db()
    assert layer.remaining_qty == Decimal("20.0000")

    deleted = reverse_stock_movements(
        tenant_id=tenant.TenantID, reference_id=99, reference_types=["SALE"],
    )
    assert deleted == 1

    layer.refresh_from_db()
    assert layer.pk == layer_pk
    assert layer.remaining_qty == Decimal("50.0000")
    assert StockLayer.objects.filter(pk=layer_pk).count() == 1


def test_ten_cycles_of_sell_then_reverse_leave_state_exactly_as_it_started():
    """حارس التآكل: عشر دورات (صرف عبر السند ثم عكسه) ⟵ الحالة النهائية مطابقة للبداية."""
    tenant = _make_tenant("حارس التآكل RSM")
    product = _make_product(tenant, "RSM-4")

    in_mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant,
    )
    layer = StockLayer.objects.get(source_movement=in_mv)

    for i in range(10):
        product.refresh_from_db()
        record_stock_movement(
            product=product, movement_type="OUT", quantity=Decimal("30"),
            movement_date="2026-01-02", tenant=tenant,
            reference_type="SALE", reference_id=1000 + i,
        )
        reverse_stock_movements(
            tenant_id=tenant.TenantID, reference_id=1000 + i, reference_types=["SALE"],
        )

    layer.refresh_from_db()
    product.refresh_from_db()
    assert layer.remaining_qty == Decimal("50.0000")
    assert product.quantity_on_hand == Decimal("50.0000")
    assert StockLayerConsumption.objects.filter(layer=layer).count() == 0


def test_reversing_purchase_after_partial_sale_raises_and_deletes_nothing():
    """اشترِ، بع جزءاً، ثم حاول عكس حركة الشراء ⟵ ValidationError عربية، ولا شيء حُذف."""
    tenant = _make_tenant("حارس الثغرة RSM")
    product = _make_product(tenant, "RSM-5")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant,
        reference_type="PURCHASE_INVOICE", reference_id=7,
    )
    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-02", tenant=tenant,
        reference_type="SALE", reference_id=8,
    )

    movements_before = StockMovement.objects.count()
    layers_before = StockLayer.objects.count()
    consumptions_before = StockLayerConsumption.objects.count()

    with pytest.raises(ValidationError):
        reverse_stock_movements(
            tenant_id=tenant.TenantID, reference_id=7,
            reference_types=["PURCHASE_INVOICE"],
        )

    assert StockMovement.objects.count() == movements_before
    assert StockLayer.objects.count() == layers_before
    assert StockLayerConsumption.objects.count() == consumptions_before


def test_negative_stock_creates_provisional_layer_and_consumes_it_without_exception():
    """بلا طبقات، بيع 10 ⟵ طبقة is_provisional=True أُنشئت واستُهلكت، والكمية -10."""
    tenant = _make_tenant("مخزون سالب RSM")
    product = _make_product(tenant, "RSM-6")
    product.allow_negative_stock = True
    product.save(update_fields=["allow_negative_stock"])

    mv = record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-01", tenant=tenant,
    )
    product.refresh_from_db()

    assert product.quantity_on_hand == Decimal("-10.0000")
    provisional = StockLayer.objects.filter(product=product, is_provisional=True)
    assert provisional.count() == 1
    layer = provisional.first()
    assert layer.remaining_qty == Decimal("0.0000")
    assert layer.original_qty == Decimal("10.0000")
    assert StockLayerConsumption.objects.filter(movement=mv, layer=layer).exists()


def test_restores_movement_returns_stock_to_original_layer_without_new_layer():
    """بِع (فتُستهلك طبقة)، ثم RETURN_IN بـrestores_movement=<حركة البيع> ⟵
    الطبقة عادت لموقعها، ولم تُنشأ طبقة جديدة (عدّ الطبقات ثابت)."""
    tenant = _make_tenant("استعادة RSM")
    product = _make_product(tenant, "RSM-7")

    in_mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant,
    )
    layer = StockLayer.objects.get(source_movement=in_mv)
    product.refresh_from_db()

    out_mv = record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("20"),
        movement_date="2026-01-02", tenant=tenant,
    )
    layer.refresh_from_db()
    assert layer.remaining_qty == Decimal("30.0000")

    layers_before = StockLayer.objects.filter(product=product).count()
    product.refresh_from_db()

    return_mv = record_stock_movement(
        product=product, movement_type="RETURN_IN", quantity=Decimal("20"),
        movement_date="2026-01-03", tenant=tenant,
        restores_movement=out_mv,
    )

    layer.refresh_from_db()
    assert layer.remaining_qty == Decimal("50.0000")
    assert StockLayer.objects.filter(product=product).count() == layers_before
    assert not StockLayerConsumption.objects.filter(movement=out_mv).exists()
    # الكلفة اشتُقّت من كلفة الاستهلاك المستعاد (10 للوحدة) لا من الوارد (صفر).
    assert return_mv.unit_cost == Decimal("10.0000")
    assert return_mv.total_cost == Decimal("200.00")


def test_restores_movement_from_another_tenant_is_rejected():
    """تمرير حركة من شركة أخرى إلى restores_movement ⟵ ValidationError (عزل الشركات)."""
    tenant_a = _make_tenant("شركة أ RSM")
    tenant_b = _make_tenant("شركة ب RSM")
    product_a = _make_product(tenant_a, "RSM-8A")
    product_b = _make_product(tenant_b, "RSM-8B")

    record_stock_movement(
        product=product_a, movement_type="IN", quantity=Decimal("50"),
        unit_cost=Decimal("10"), movement_date="2026-01-01", tenant=tenant_a,
    )
    product_a.refresh_from_db()
    out_a = record_stock_movement(
        product=product_a, movement_type="OUT", quantity=Decimal("20"),
        movement_date="2026-01-02", tenant=tenant_a,
    )

    with pytest.raises(ValidationError):
        record_stock_movement(
            product=product_b, movement_type="RETURN_IN", quantity=Decimal("20"),
            movement_date="2026-01-03", tenant=tenant_b,
            restores_movement=out_a,
        )


def test_fifty_line_invoice_stays_within_measured_query_budget(django_assert_num_queries):
    """قياس الأداء: 50 نداءً لـ`record_stock_movement` (فاتورة 50 بنداً، منتج
    مختلف لكل بند، كل بند وارد ثم صادر) — سقفٌ مقيسٌ فعلياً لا مخمَّناً.

    القياس الفعلي (شُغِّل الاختبار فعلياً وقُرئت رسالة django_assert_num_queries
    عند فشلها الأول): 50 نداء OUT ⟵ **650 استعلاماً** بالضبط (13 استعلاماً
    لكل حركة صادرة: select_for_update للمنتج، select_for_update لطبقاته،
    INSERT الحركة، UPDATE الطبقة، INSERT صفّ الاستهلاك، استعلاما
    `derived_avg_cost` (قيمة+كمية)، UPDATE الحركة، UPDATE المنتج، + عمليات
    SAVEPOINT/RELEASE لتداخل `transaction.atomic()` في `fifo.consume`).
    الحدّ أدناه 650 + هامش 5% ليتحمّل فروقاً طفيفة بين إصدارات Django/SQLite
    بلا أن يُخفي انحرافاً حقيقياً (N+1 مثلاً كان سيُظهر رقماً أعلى بكثير).
    لا تحسين مسبق للتجميع — هذا قياسٌ لا تصميم.
    """
    tenant = _make_tenant("أداء RSM")
    products = [_make_product(tenant, f"RSM-PERF-{i}") for i in range(50)]

    for p in products:
        record_stock_movement(
            product=p, movement_type="IN", quantity=Decimal("10"),
            unit_cost=Decimal("5"), movement_date="2026-01-01", tenant=tenant,
        )

    fresh_products = list(Product.objects.filter(pk__in=[p.pk for p in products]))

    with django_assert_num_queries(683, exact=False):
        for p in fresh_products:
            record_stock_movement(
                product=p, movement_type="OUT", quantity=Decimal("1"),
                movement_date="2026-01-02", tenant=tenant,
                reference_type="SALE", reference_id=1,
            )
