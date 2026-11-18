"""عقد بيانات طرق تكلفة المبيعات (M1A): يغطي الملف التخزين فقط، ومحرّك اللقطة
يُختبر في `sales/tests/test_cogs_method_snapshot.py`.

هذه الشريحة تُثبت **الحقول** التي ستبني عليها الطرق الأربع لاحقاً، ولا تدّعي
تنفيذَ أيٍّ منها. يثبت الملف:

  1. عقود الحقول في `_meta`: القابلية للفراغ، ودقّة الخانات، و`db_column`،
     ومصدرُ الاختيارات الواحد (قائمةٌ واحدة يقرؤها النموذجان).
  2. الافتراضُ `fifo` محفوظٌ فعلاً لشركةٍ جديدة، والطرقُ الأربع تُحفظ وتُقرأ.
  3. طريقةٌ غير معروفة تُرفض على `full_clean` في الإعداد وفي لقطة الحركة.
  4. `standard_cost`: `NULL` تعني «غير محدّدة» وهي غيرُ الصفر الصريح، وأربعُ
     خاناتٍ عشرية تُحفظ كما هي، والسالبُ يُرفض.
  5. لقطةُ الحركة تبقى `NULL` على المسار القائم (لا تعبئة تاريخية)، وصفرٌ صريح
     يظلّ صفراً لا `None`.
  6. اللقطة لا تتبع الإعدادات إذا تغيّرت بعدها.
  7. مسار FIFO الافتراضي القائم لم يتغيّر: وارد 8@10 و4@16 ثم بيع 10 ⟵
     `total_cost = 112` وقيمةُ الطبقات المتبقّية 32.

نمطُ التهيئة من `inventory/tests/test_fifo_movements.py`: شركةٌ حقيقية عبر
`create_company`، وحركاتٌ عبر `record_stock_movement` وحدها (لا حركة مخزون
مخترعة، ولا قيد — الحسابُ نفسه لا يُلمس في هذه الشريحة).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from inventory.models import Product, StockLayer, StockMovement
from inventory.services import record_stock_movement
from sales.models import SalesSettings
from tenants.services import create_company

pytestmark = pytest.mark.django_db

# القيم المحسومة للطرق الأربع — تُقارن بها قوائم الاختيارات في النموذجين.
METHODS = ["fifo", "avco", "standard", "last_purchase"]


def _make_tenant(name):
    user = User.objects.create_user(username=f"cogscm-{name}", password="x")
    return create_company(f"شركة {name}", user)


def _make_product(tenant, sku):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar="صنف تكلفة",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )


def _sales_settings(tenant):
    """صفُّ الإعدادات يُنشأ عند أوّل طلبٍ فعليّ (كما يفعل العرضُ)، فلا يفترضه الاختبار."""
    return SalesSettings.objects.get_or_create(tenant=tenant)[0]


def _has_zero_floor(field):
    """القيدُ غيرُ السالب على العمود: `MinValueValidator(Decimal('0'))`."""
    return any(
        isinstance(validator, MinValueValidator)
        and validator.limit_value == Decimal("0")
        for validator in field.validators
    )


def _choice_values(choices):
    return [value for value, _label in choices]


def test_model_field_contract_matches_the_decided_design():
    """الحقولُ الأربعة موجودةٌ بالدقّة والفراغية وأنواع الحذف المحسومة."""
    from inventory.models import COGS_METHOD_CHOICES

    standard = Product._meta.get_field("standard_cost")
    assert standard.null is True
    assert (standard.max_digits, standard.decimal_places) == (18, 4)
    assert standard.db_column == "StandardCost"
    assert _has_zero_floor(standard)

    snapshot_cost = StockMovement._meta.get_field("cogs_cost")
    assert snapshot_cost.null is True
    assert (snapshot_cost.max_digits, snapshot_cost.decimal_places) == (18, 2)
    assert snapshot_cost.db_column == "CogsCost"
    assert _has_zero_floor(snapshot_cost)

    snapshot_method = StockMovement._meta.get_field("cogs_method")
    assert snapshot_method.null is True
    assert snapshot_method.db_column == "CogsMethod"
    assert _choice_values(snapshot_method.choices) == METHODS

    method = SalesSettings._meta.get_field("cogs_cost_method")
    assert method.null is False
    assert method.default == "fifo"
    assert method.db_column == "CogsCostMethod"
    assert _choice_values(method.choices) == METHODS
    assert _choice_values(method.choices) == _choice_values(COGS_METHOD_CHOICES)
    assert _choice_values(snapshot_method.choices) == _choice_values(COGS_METHOD_CHOICES)

    variance = SalesSettings._meta.get_field("cost_variance_account")
    assert variance.null is True
    assert variance.related_model._meta.label == "accounting.Account"
    assert variance.remote_field.on_delete is models.SET_NULL
    assert variance.remote_field.related_name == "sales_settings_cost_variance"


def test_default_is_fifo_and_the_four_methods_persist():
    """شركةٌ جديدة تبدأ على FIFO، وكلُّ طريقةٍ من الأربع تُحفظ وتُقرأ بعدها."""
    tenant = _make_tenant("افتراضي")
    settings_row = _sales_settings(tenant)

    assert settings_row.cogs_cost_method == "fifo"
    assert settings_row.cost_variance_account is None

    for method_value in METHODS:
        settings_row.cogs_cost_method = method_value
        settings_row.full_clean()
        settings_row.save(update_fields=["cogs_cost_method"])
        settings_row.refresh_from_db()
        assert settings_row.cogs_cost_method == method_value


def test_unknown_method_is_rejected_on_clean_in_settings_and_movement():
    """طريقةٌ خارج الأربع لا تدخل الإعداد ولا لقطةَ الحركة."""
    tenant = _make_tenant("رفض")
    settings_row = _sales_settings(tenant)
    settings_row.cogs_cost_method = "weighted_average"
    with pytest.raises(ValidationError) as caught:
        settings_row.full_clean()
    assert "cogs_cost_method" in caught.value.message_dict

    product = _make_product(tenant, "BAD-METHOD")
    movement = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("1"),
        unit_cost=Decimal("5"), movement_date="2026-03-01", tenant=tenant,
    )
    movement.cogs_method = "weighted_average"
    with pytest.raises(ValidationError) as caught:
        movement.full_clean()
    assert "cogs_method" in caught.value.message_dict


def test_standard_cost_null_zero_and_four_decimals_are_distinct_states():
    """`NULL` ≠ صفر: الأول يعني «غير محدّدة»، والثاني كلفةٌ صريحةٌ صفر."""
    tenant = _make_tenant("معياري")
    unspecified = _make_product(tenant, "STD-NULL")
    explicit_zero = _make_product(tenant, "STD-ZERO")
    measured = _make_product(tenant, "STD-4DP")

    unspecified.full_clean()
    explicit_zero.standard_cost = Decimal("0")
    explicit_zero.full_clean()
    explicit_zero.save(update_fields=["standard_cost"])
    measured.standard_cost = Decimal("12.3456")
    measured.full_clean()
    measured.save(update_fields=["standard_cost"])

    unspecified.refresh_from_db()
    explicit_zero.refresh_from_db()
    measured.refresh_from_db()
    assert unspecified.standard_cost is None
    assert explicit_zero.standard_cost is not None
    assert explicit_zero.standard_cost == Decimal("0")
    assert measured.standard_cost == Decimal("12.3456")

    measured.standard_cost = Decimal("-0.0001")
    with pytest.raises(ValidationError) as caught:
        measured.full_clean()
    assert "standard_cost" in caught.value.message_dict


def test_movement_snapshot_stays_null_on_the_existing_path_and_zero_is_explicit():
    """لا تعبئة تاريخية: الحركةُ الجديدة عبر المسار القائم تبقى بلا لقطة، والصفرُ صريح."""
    tenant = _make_tenant("لقطة")
    product = _make_product(tenant, "SNAP-1")

    movement = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("3"),
        unit_cost=Decimal("7"), movement_date="2026-03-02", tenant=tenant,
    )
    movement.refresh_from_db()
    assert movement.cogs_cost is None
    assert movement.cogs_method is None

    movement.cogs_cost = Decimal("0")
    movement.save(update_fields=["cogs_cost"])
    movement.refresh_from_db()
    assert movement.cogs_cost is not None
    assert movement.cogs_cost == Decimal("0")

    movement.cogs_cost = Decimal("-1.00")
    with pytest.raises(ValidationError) as caught:
        movement.full_clean()
    assert "cogs_cost" in caught.value.message_dict


def test_movement_method_snapshot_does_not_follow_later_settings_changes():
    """اللقطةُ تسجّل طريقةَ لحظتها؛ تغييرُ الإعداد بعدها لا يعيد كتابتها."""
    tenant = _make_tenant("استقلال اللقطة")
    product = _make_product(tenant, "SNAP-2")
    movement = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("2"),
        unit_cost=Decimal("9"), movement_date="2026-03-03", tenant=tenant,
    )
    movement.cogs_method = "avco"
    movement.save(update_fields=["cogs_method"])

    settings_row = _sales_settings(tenant)
    assert settings_row.cogs_cost_method == "fifo"
    settings_row.cogs_cost_method = "standard"
    settings_row.save(update_fields=["cogs_cost_method"])

    movement.refresh_from_db()
    settings_row.refresh_from_db()
    assert settings_row.cogs_cost_method == "standard"
    assert movement.cogs_method == "avco"


def test_default_fifo_stock_path_is_unchanged():
    """الثمنُ المحسوبُ اليوم لا يتغيّر: 8@10 و4@16 ثم بيع 10 ⟵ 112، والمتبقّي 32."""
    tenant = _make_tenant("FIFO قائم")
    product = _make_product(tenant, "FIFO-112")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("8"),
        unit_cost=Decimal("10"), movement_date="2026-03-04", tenant=tenant,
    )
    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("4"),
        unit_cost=Decimal("16"), movement_date="2026-03-05", tenant=tenant,
    )
    product.refresh_from_db()

    sale = record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-03-06", tenant=tenant,
    )
    assert sale.total_cost == Decimal("112.00")

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("2.0000")
    remaining_value = sum(
        (layer.remaining_qty * layer.unit_cost
         for layer in StockLayer.objects.filter(product=product)),
        Decimal("0"),
    )
    assert remaining_value == Decimal("32.00")
    assert sale.cogs_cost is None
    assert sale.cogs_method is None
