"""بضاعةٌ قائمةٌ بلا طبقات — الطبقةُ الافتتاحيّة الكسولة (مواصفة #137).

كلُّ صنفٍ في قاعدةِ إنتاجٍ قائمة يحمل `quantity_on_hand` و`avg_cost` **وصفرَ
طبقات**: الطبقاتُ اختراعُ #137 نفسِها. فما لم يُبنَ شيءٌ لهذه الحالة، تعمل
`consume` على رتلٍ فارغٍ فتُرجع الكميّةَ كلَّها «غيرَ مغطّاة»، فتُنشأ طبقةٌ
**مؤقّتة** وتُستهلَك فوراً — وتبقى `remaining_qty` صفراً بينما الرصيدُ موجب.

وأثرُه ليس نظريّاً: `derived_avg_cost` تقسم قيمةَ الطبقات المفتوحة (صفر) على
كميّتها، فتُرجع **صفراً**، فتُكتب `Product.avg_cost = 0`. أي أنّ **أوّلَ بيعةٍ
لكلّ صنفٍ في الشركة تُصفّر كلفته** ويصير تقييمُ المخزون صفراً. وأسوأ: كلُّ
شراءٍ لاحقٍ يرى طبقةً مؤقّتةً «معلَّقة» فيُطلِع قيدَ فرقٍ لا مبرّرَ له.

والعلاج: قبل أيّ استهلاك، إن كانت طبقاتُ الصنف المفتوحة **أقلَّ** من رصيده،
تُنشأ طبقةٌ افتتاحيّةٌ بالفرق بكلفة `avg_cost` الجارية وبتاريخٍ أقدمَ من كلّ
شيء (فتُستهلَك أوّلاً — بضاعةُ ما قبل البيانات بالتعريف). وهي **محايدةٌ على
الميزانية بالبناء**: كميّة × متوسّط = القيمةُ الدفتريّة نفسُها التي كانت
مسجَّلةً قبلها بالضبط — وهو خيارُ المالك في تذكرة الكميّة اليتيمة (#135).
فلا يلزم تشغيلُ أمرِ إعادة البناء قبل النشر.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import JournalHeader
from inventory.models import Product, StockLayer
from inventory.services import create_product_with_family, record_stock_movement
from tenants.services import create_company

pytestmark = pytest.mark.django_db

D = datetime.date(2026, 1, 1)


def _tenant(name):
    owner = User.objects.create_user(username=f"u-{name}", password="x")
    return create_company(name, owner)


def _legacy_product(tenant, sku, qty, cost):
    """صنفٌ كما هو في قاعدةٍ قائمة: رصيدٌ وكلفةٌ مكتوبان، وصفرُ طبقات."""
    res = create_product_with_family(tenant=tenant, sku=sku, name_ar=sku)
    prod = res[1] if isinstance(res, tuple) else res
    Product.objects.filter(pk=prod.pk).update(
        quantity_on_hand=Decimal(str(qty)), avg_cost=Decimal(str(cost)))
    prod.refresh_from_db()
    assert not StockLayer.objects.filter(product=prod).exists()
    return prod


def _layers_qty(prod):
    return sum(
        (layer.remaining_qty for layer in StockLayer.objects.filter(product=prod)),
        Decimal("0"),
    )


def _pending_provisional(prod):
    """الحفرةُ التي بِيعت ولم تصلها بضاعةٌ بعد. الطبقاتُ لا تحمل كميّةً سالبة،
    فالمخزونُ السالب يُمثَّل هنا لا في `remaining_qty`."""
    return sum(
        (
            layer.original_qty - layer.reconciled_qty
            for layer in StockLayer.objects.filter(product=prod, is_provisional=True)
        ),
        Decimal("0"),
    )


def _assert_invariant(prod):
    """الثابتُ الحقيقيّ: Σ(المتبقّي) − المعلَّقُ المؤقّت = الرصيد.

    وليس Σ(المتبقّي) = الرصيد وحدَه — ذلك يصحّ عند رصيدٍ غير سالبٍ فقط، لأن
    الطبقة لا تُمثِّل كميّةً سالبة.
    """
    prod.refresh_from_db()
    net = _layers_qty(prod) - _pending_provisional(prod)
    assert net == prod.quantity_on_hand, (
        f"انتُهك الثابت: طبقات={_layers_qty(prod)} معلَّق={_pending_provisional(prod)} "
        f"صافٍ={net} رصيد={prod.quantity_on_hand}"
    )


def test_first_sale_of_legacy_stock_does_not_collapse_its_cost():
    """العطبُ الحيّ: بيعُ ٤ من رصيدِ ١٠ بكلفة ٥ كان يُصفّر `avg_cost`."""
    tenant = _tenant("قديم")
    prod = _legacy_product(tenant, "LEG-1", 10, 5)

    record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("4"),
                          movement_date=D, tenant=tenant)

    prod.refresh_from_db()
    assert prod.avg_cost == Decimal("5.0000"), "انهارت كلفةُ الصنف إلى صفر."
    assert prod.quantity_on_hand == Decimal("6.0000")
    _assert_invariant(prod)


def test_legacy_sale_carries_the_books_cost_not_zero():
    """كلفةُ البيعة نفسِها ٤×٥ = ٢٠، لا صفراً — وإلا انتفخ الربح."""
    tenant = _tenant("كلفة")
    prod = _legacy_product(tenant, "LEG-2", 10, 5)

    mv = record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("4"),
                               movement_date=D, tenant=tenant)

    assert mv.total_cost == Decimal("20.00")


def test_the_opening_layer_is_value_neutral():
    """قيمةُ المخزون قبل أوّل حركةٍ وبعد الطبقة الافتتاحيّة **واحدة**."""
    tenant = _tenant("حياد")
    prod = _legacy_product(tenant, "LEG-3", 70, "24.2857")
    book_value_before = Decimal("70") * Decimal("24.2857")

    record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("1"),
                          movement_date=D, tenant=tenant)

    layers = StockLayer.objects.filter(product=prod)
    layers_value = sum((l.remaining_qty * l.unit_cost for l in layers), Decimal("0"))
    sold_cost = Decimal("1") * Decimal("24.2857")
    assert (layers_value + sold_cost).quantize(Decimal("0.01")) == \
        book_value_before.quantize(Decimal("0.01"))


def test_opening_layer_is_oldest_so_it_is_consumed_first():
    """بضاعةُ ما قبل البيانات تخرج أوّلاً — فتُغادر كلفتُها المشكوكة سريعاً."""
    tenant = _tenant("رتل")
    prod = _legacy_product(tenant, "LEG-4", 10, 5)

    record_stock_movement(product=prod, movement_type="IN", quantity=Decimal("10"),
                          unit_cost=Decimal("60"), movement_date=D, tenant=tenant)
    mv = record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("10"),
                               movement_date=D, tenant=tenant)

    assert mv.total_cost == Decimal("50.00"), "لم تُستهلَك الطبقةُ الافتتاحيّة أوّلاً."


def test_opening_layer_is_not_provisional_so_no_phantom_correction_journal():
    """الطبقةُ الافتتاحيّة ليست مؤقّتة — وإلّا رأى كلُّ شراءٍ لاحقٍ «معلَّقاً»
    فأطلع قيدَ فرقٍ لا مبرّرَ له على كلّ صنفٍ في الشركة."""
    tenant = _tenant("قيود")
    prod = _legacy_product(tenant, "LEG-5", 10, 5)
    record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("4"),
                          movement_date=D, tenant=tenant)
    journals_before = JournalHeader.objects.filter(tenant=tenant).count()

    record_stock_movement(product=prod, movement_type="IN", quantity=Decimal("10"),
                          unit_cost=Decimal("9"), movement_date=D, tenant=tenant)

    assert JournalHeader.objects.filter(tenant=tenant).count() == journals_before
    assert not StockLayer.objects.filter(product=prod, is_provisional=True).exists()
    _assert_invariant(prod)


def test_true_negative_stock_still_creates_a_provisional_layer():
    """الحارسُ لا يبتلع الحالة الحقيقيّة: رصيدٌ صفرٌ وبيعٌ ⟵ طبقةٌ مؤقّتة."""
    tenant = _tenant("سالب")
    prod = _legacy_product(tenant, "LEG-6", 0, 0)

    record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("10"),
                          movement_date=D, tenant=tenant)

    assert StockLayer.objects.filter(product=prod, is_provisional=True).exists()
    prod.refresh_from_db()
    assert prod.quantity_on_hand == Decimal("-10.0000")
    _assert_invariant(prod)


def test_legacy_stock_sold_beyond_its_balance_splits_correctly():
    """رصيدٌ قديمٌ ١٠ وبيعُ ١٥: عشرةٌ من الافتتاحيّة وخمسٌ مؤقّتة."""
    tenant = _tenant("مختلط")
    prod = _legacy_product(tenant, "LEG-7", 10, 5)

    mv = record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("15"),
                               movement_date=D, tenant=tenant)

    assert mv.total_cost == Decimal("75.00")  # ١٠×٥ افتتاحيّة + ٥×٥ مؤقّتة
    assert StockLayer.objects.filter(product=prod, is_provisional=True).count() == 1
    _assert_invariant(prod)


def test_backfill_runs_once_not_on_every_movement():
    """الطبقةُ الافتتاحيّة تُنشأ مرّةً — لا واحدةً مع كلّ حركة."""
    tenant = _tenant("مرة")
    prod = _legacy_product(tenant, "LEG-8", 10, 5)

    for _ in range(3):
        record_stock_movement(product=prod, movement_type="OUT", quantity=Decimal("1"),
                              movement_date=D, tenant=tenant)

    assert StockLayer.objects.filter(product=prod, source_movement__isnull=True).count() == 1
    _assert_invariant(prod)


def test_inbound_on_legacy_stock_also_repairs_the_invariant():
    """الوارِدُ أيضاً يرأب الفجوة — لا الصادرُ وحده."""
    tenant = _tenant("وارد")
    prod = _legacy_product(tenant, "LEG-9", 10, 5)

    record_stock_movement(product=prod, movement_type="IN", quantity=Decimal("5"),
                          unit_cost=Decimal("7"), movement_date=D, tenant=tenant)

    prod.refresh_from_db()
    assert prod.quantity_on_hand == Decimal("15.0000")
    _assert_invariant(prod)


def test_backfill_is_isolated_between_companies():
    tenant_a = _tenant("شركة أ")
    tenant_b = _tenant("شركة ب")
    prod_a = _legacy_product(tenant_a, "LEG-X", 10, 5)
    prod_b = _legacy_product(tenant_b, "LEG-X", 10, 9)

    record_stock_movement(product=prod_a, movement_type="OUT", quantity=Decimal("1"),
                          movement_date=D, tenant=tenant_a)

    assert not StockLayer.objects.filter(product=prod_b).exists()
    prod_b.refresh_from_db()
    assert prod_b.avg_cost == Decimal("9.0000")
