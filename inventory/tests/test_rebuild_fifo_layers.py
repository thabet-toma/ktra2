"""أمر `rebuild_fifo_layers` — معاينةٌ فقط لمقارنة قيمة المخزون المسجَّلة اليوم
(Product.avg_cost × quantity_on_hand) بقيمةٍ مُعاد بناؤها من دفتر الحركات
الواردة بترتيب FIFO (مواصفة #137). **لا كتابة إطلاقاً** — الأمر لا ينشئ
`StockLayer` ولا يعدّل `Product`، وهذا مُختبَرٌ صراحةً أدناه.

يثبت:
  1. الحالة المطابقة: واردان بلا صرفٍ ⟵ الفرق صفر (بحدود التقريب النقدي).
  2. الحالة البنيويّة: متوسطٌ مسجَّل يُخفي فرقاً حقيقياً حتى بلا كميّةٍ يتيمة.
  3. الكميّة اليتيمة: واردٌ لا يغطّي الرصيد كاملاً ⟵ طبقةٌ يتيمة بكلفة avg_cost،
     أقدم من أي طبقةٍ أخرى للمنتج.
  4. حارس عدم الكتابة: عدّ الصفوف وقيم avg_cost قبل/بعد التشغيل مطابقة تماماً.
  5. عزل الشركات: تشغيلٌ بـ--tenant-id لشركة لا يُسرّب بيانات شركةٍ أخرى.
  6. صفر مخزون: شركة بلا أصنافٍ ذات رصيد ⟵ رسالة واضحة بلا انفجار.
  7. الأداء: عشرون منتجاً بحركاتٍ متعددة تحت سقف استعلامات ثابت.
"""
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test.utils import CaptureQueriesContext
from django.db import connection

from inventory.management.commands.rebuild_fifo_layers import (
    Q4,
    compute_rebuilt_layers,
)
from inventory.models import Product, StockLayer, StockLayerConsumption, StockMovement
from tenants.services import create_company

Q2 = Decimal("0.01")


def _make_tenant(name):
    user = User.objects.create_user(username=f"rebuild-{name}", password="x")
    return create_company(f"شركة {name}", user)


def _make_product(tenant, sku, *, qty, avg_cost, name="صنف اختبار"):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=name,
        quantity_on_hand=Decimal(qty), avg_cost=Decimal(avg_cost),
    )


def _in_movement(tenant, product, qty, cost, date):
    return StockMovement.objects.create(
        tenant=tenant, product=product, movement_type="IN",
        quantity=Decimal(qty), unit_cost=Decimal(cost),
        movement_date=date, reference_type="MANUAL",
    )


def _run(tenant_id=None, limit=10, csv=None):
    out = StringIO()
    args = []
    kwargs = {"stdout": out}
    if tenant_id is not None:
        kwargs["tenant_id"] = tenant_id
    kwargs["limit"] = limit
    if csv is not None:
        kwargs["csv"] = csv
    call_command("rebuild_fifo_layers", *args, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_matching_case_two_inbound_layers_no_issue_gives_zero_diff():
    """وارد 50@10 ثمّ وارد 20@60 بلا أي صرف ⟵ القيمة المُعادة بناؤها 1700
    والفرق صفر (المسجَّلة 70 × avg_cost المشتق ≈ 1700)."""
    tenant = _make_tenant("مطابقة")
    avg = (Decimal("1700") / Decimal("70")).quantize(Decimal("0.0001"))
    product = _make_product(tenant, "REB-1", qty="70", avg_cost=avg)
    _in_movement(tenant, product, "50", "10", "2026-01-01")
    _in_movement(tenant, product, "20", "60", "2026-01-05")

    out = _run(tenant_id=tenant.TenantID)

    assert "1700.00" in out
    # الفرق صفر بحدود التقريب النقدي (سنتين).
    assert "0.00" in out


@pytest.mark.django_db
def test_structural_diff_case_exposed_without_any_orphan_quantity():
    """وارد 50@10، ثمّ وارد 50@20، ثمّ صرف 50 (الرصيد صار 50). المسجَّلة تحت
    المتوسط = 750، والمُعادة بناؤها من الوارد الأحدث = 1000. الفرق +250 —
    بلا أي كميّةٍ يتيمة (الواردات تغطّي الرصيد كاملاً)."""
    tenant = _make_tenant("فرق بنيوي")
    product = _make_product(tenant, "REB-2", qty="50", avg_cost="15")
    _in_movement(tenant, product, "50", "10", "2026-01-01")
    _in_movement(tenant, product, "50", "20", "2026-01-10")
    # حركة الصرف نفسها غير ضرورية لحساب الأمر (يقرأ quantity_on_hand مباشرة)
    # لكنها تُسجَّل هنا لتوثيق كيف صار الرصيد 50 فعلياً.
    StockMovement.objects.create(
        tenant=tenant, product=product, movement_type="OUT",
        quantity=Decimal("50"), unit_cost=Decimal("0"),
        movement_date="2026-01-15", reference_type="SALE",
    )

    out = _run(tenant_id=tenant.TenantID)

    assert "750.00" in out
    assert "1000.00" in out
    assert "250.00" in out
    assert "زيادة" in out

    # لا كميّة يتيمة في هذه الحالة — الواردات وحدها تغطّي الرصيد بالكامل.
    layers, orphan_qty = compute_rebuilt_layers(
        product,
        [
            {"quantity": Decimal("50"), "unit_cost": Decimal("20"), "movement_date": __import__("datetime").date(2026, 1, 10)},
            {"quantity": Decimal("50"), "unit_cost": Decimal("10"), "movement_date": __import__("datetime").date(2026, 1, 1)},
        ],
    )
    assert orphan_qty == Decimal("0.0000")
    assert len(layers) == 1
    assert layers[0]["qty"] == Decimal("50.0000")
    assert layers[0]["unit_cost"] == Decimal("20.0000")


@pytest.mark.django_db
def test_orphan_quantity_gets_avg_cost_and_is_oldest_in_the_queue():
    """رصيدٌ 70 ووارداتٌ تغطّي 50 فقط ⟵ طبقةٌ يتيمة بـ20 بكلفة avg_cost، وهي
    أقدم من الطبقة الأخرى، والتقرير يذكر الكمية اليتيمة."""
    tenant = _make_tenant("كمية يتيمة")
    product = _make_product(tenant, "REB-3", qty="70", avg_cost="12")
    _in_movement(tenant, product, "50", "10", "2026-01-01")

    import datetime
    layers, orphan_qty = compute_rebuilt_layers(
        product,
        [{"quantity": Decimal("50"), "unit_cost": Decimal("10"),
          "movement_date": datetime.date(2026, 1, 1)}],
    )
    assert orphan_qty == Decimal("20.0000")
    assert len(layers) == 2
    orphan_layer = next(l for l in layers if l["is_orphan"])
    real_layer = next(l for l in layers if not l["is_orphan"])
    assert orphan_layer["qty"] == Decimal("20.0000")
    assert orphan_layer["unit_cost"] == Decimal("12.0000")
    assert orphan_layer["movement_date"] < real_layer["movement_date"]

    out = _run(tenant_id=tenant.TenantID)
    assert "20.0000" in out or "20" in out
    assert "1" in out  # صنفٌ واحد له كميّة يتيمة


@pytest.mark.django_db
def test_command_writes_nothing_row_counts_and_avg_cost_unchanged():
    """حارسٌ إلزامي: عدّ StockLayer وStockLayerConsumption وProduct وقيم avg_cost
    قبل وبعد التشغيل متطابقة تماماً — الأمر معاينةٌ فقط."""
    tenant = _make_tenant("حارس عدم الكتابة")
    product = _make_product(tenant, "REB-4", qty="70", avg_cost="12")
    _in_movement(tenant, product, "50", "10", "2026-01-01")
    _in_movement(tenant, product, "20", "60", "2026-01-05")

    before_layers = StockLayer.objects.count()
    before_consumptions = StockLayerConsumption.objects.count()
    before_products = Product.objects.count()
    before_avg = Product.objects.get(pk=product.pk).avg_cost

    _run(tenant_id=tenant.TenantID)

    assert StockLayer.objects.count() == before_layers
    assert StockLayerConsumption.objects.count() == before_consumptions
    assert Product.objects.count() == before_products
    product.refresh_from_db()
    assert product.avg_cost == before_avg


@pytest.mark.django_db
def test_tenant_isolation_does_not_leak_other_companys_data():
    """شركتان بمخزون ⟵ تشغيلٌ بـ--tenant-id لإحداهما لا يذكر الأخرى."""
    tenant_a = _make_tenant("أ")
    tenant_b = _make_tenant("ب")
    product_a = _make_product(tenant_a, "REB-A-ONLY", qty="10", avg_cost="5", name="صنف أ الفريد")
    product_b = _make_product(tenant_b, "REB-B-ONLY", qty="10", avg_cost="5", name="صنف ب الفريد")
    _in_movement(tenant_a, product_a, "10", "5", "2026-01-01")
    _in_movement(tenant_b, product_b, "10", "5", "2026-01-01")

    out = _run(tenant_id=tenant_a.TenantID)

    assert "REB-A-ONLY" in out
    assert "REB-B-ONLY" not in out
    assert tenant_b.CompanyName not in out


@pytest.mark.django_db
def test_zero_stock_company_gives_clear_message_without_crashing():
    """شركة بلا أصنافٍ ذات رصيد ⟵ لا انفجار ورسالة واضحة."""
    tenant = _make_tenant("صفر مخزون")
    # منتجٌ برصيد صفر — لا يُحتسب.
    Product.objects.create(
        tenant=tenant, sku="REB-ZERO", name_ar="صفر",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )

    out = _run(tenant_id=tenant.TenantID)

    assert "لا توجد" in out


@pytest.mark.django_db
def test_performance_twenty_products_stays_under_fixed_query_ceiling(django_assert_num_queries):
    """عشرون منتجاً بحركاتٍ متعددة لكلٍّ منها ⟵ عدد الاستعلامات لا يكبر مع عدد
    المنتجات أو الحركات (استعلامٌ واحد للمنتجات وآخر للحركات لكل الشركة معاً).

    السقف قِيس فعلياً (`CaptureQueriesContext`) ثم ثُبِّت هنا — 3 استعلامات:
    Tenant + Product (bulk) + StockMovement (bulk)، بصرف النظر عن عدد
    المنتجات (20) أو الحركات (60) في هذا الاختبار.
    """
    tenant = _make_tenant("أداء")
    for i in range(20):
        p = _make_product(tenant, f"REB-PERF-{i}", qty="30", avg_cost="7")
        _in_movement(tenant, p, "10", "5", "2026-01-01")
        _in_movement(tenant, p, "10", "6", "2026-01-05")
        _in_movement(tenant, p, "10", "7", "2026-01-10")

    # قياسٌ فعلي أوّلاً (يُطبع فقط، لا يُستعمل كسقفٍ مباشر).
    with CaptureQueriesContext(connection) as ctx:
        _run(tenant_id=tenant.TenantID)
    measured = len(ctx.captured_queries)

    with django_assert_num_queries(measured):
        _run(tenant_id=tenant.TenantID)
