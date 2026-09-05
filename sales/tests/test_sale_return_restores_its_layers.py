"""مرتجعُ البيع يعود إلى **طبقاتِ فاتورته هي** لا إلى متوسّطٍ جارٍ (#137).

قرارُ المالك: «الراجعُ يعود لطبقته وموقعِه في الرتل». وإلغاءُ الترحيل كان
يحقّقه منذ المرحلة الثانية؛ أمّا **مستندُ المرتجع الصريح** فكان يدخل بالمتوسّط
المشتقّ — سلوكٌ آمنٌ لكنّه ليس ما قُرِّر.

والمرتجعُ الجزئيّ هو ما استلزم قدرةً جديدة: الردُّ **بعكس ترتيب الاستهلاك**
(`fifo.restore_partial`). بيعُ ٦٠ يستهلك ٥٠ من طبقةِ العشرة وعشراً من طبقةِ
الستّين؛ ومرتجعُ ١٥ يفكّ العشرَ الغالية أوّلاً ثمّ خمساً رخيصة — فتصير حالةُ
الرتل **مطابقةً حرفاً بحرف** لما لو بيعت ٤٥ ابتداءً. ولو رُدَّ بترتيب
الاستهلاك نفسِه لبقيت وحداتٌ من الطبقة الأحدث مستهلَكةً بلا سبب، وانقلبت
كلفةُ ما تبقّى في المخزن.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, StockLayer
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

D = datetime.date(2026, 6, 15)


@pytest.fixture
def env():
    owner = User.objects.create_user(username="retlayer", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة طبقات المرتجع", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-L", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4001-L", name="مبيعات", account_type="Revenue", is_active=True)
    cogs = Account.objects.create(
        tenant=tenant, code="5001-L", name="تكلفة", account_type="Expense", is_active=True)
    inv = Account.objects.create(
        tenant=tenant, code="1104-L", name="مخزون", account_type="Asset", is_active=True)
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "default_revenue_account_product": rev,
            "default_cogs_account": cogs,
            "default_inventory_account": inv,
        },
    )
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="LAY-1", name_ar="منتج", quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"))
    # طبقتان حقيقيّتان — مثالُ المالك.
    record_stock_movement(product=product, movement_type="IN", quantity=Decimal("50"),
                          unit_cost=Decimal("10"), movement_date=D, tenant=tenant)
    record_stock_movement(product=product, movement_type="IN", quantity=Decimal("20"),
                          unit_cost=Decimal("60"), movement_date=D, tenant=tenant)
    return tenant, ils, customer, product


def _sell(tenant, ils, customer, product, qty, number):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=ils,
        invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(str(qty)), unit_price=Decimal("200"))
    post_sales_invoice(inv)
    inv.refresh_from_db()
    return inv


def _return(tenant, ils, customer, product, qty, number, original):
    ret = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=ils,
        invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN, original_invoice=original)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=ret, product=product,
        quantity=Decimal(str(qty)), unit_price=Decimal("200"))
    post_sales_invoice(ret)
    ret.refresh_from_db()
    return ret


def _layers(product):
    return {
        layer.unit_cost: layer.remaining_qty
        for layer in StockLayer.objects.filter(product=product)
    }


def test_partial_return_undoes_the_tail_of_the_consumption(env):
    """مرتجعُ ١٥ من بيعةِ ٦٠ يفكّ العشرَ الغالية ثمّ خمساً رخيصة."""
    tenant, ils, customer, product = env
    sale = _sell(tenant, ils, customer, product, 60, "S-1")

    _return(tenant, ils, customer, product, 15, "R-1", sale)

    assert _layers(product) == {
        Decimal("10.0000"): Decimal("5.0000"),
        Decimal("60.0000"): Decimal("20.0000"),
    }


def test_the_result_matches_a_smaller_sale_exactly(env):
    """الحالةُ بعد بيعِ ٦٠ ومرتجعِ ١٥ = الحالةُ بعد بيعِ ٤٥ ابتداءً."""
    tenant, ils, customer, product = env
    sale = _sell(tenant, ils, customer, product, 60, "S-2")
    _return(tenant, ils, customer, product, 15, "R-2", sale)
    after_return = _layers(product)

    other = Product.objects.create(
        tenant=tenant, sku="LAY-2", name_ar="مقارن", quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"))
    record_stock_movement(product=other, movement_type="IN", quantity=Decimal("50"),
                          unit_cost=Decimal("10"), movement_date=D, tenant=tenant)
    record_stock_movement(product=other, movement_type="IN", quantity=Decimal("20"),
                          unit_cost=Decimal("60"), movement_date=D, tenant=tenant)
    _sell(tenant, ils, customer, other, 45, "S-3")

    assert after_return == _layers(other)


def test_partial_return_cost_is_the_tail_not_the_average(env):
    """كلفةُ المرتجع ١٠×٦٠ + ٥×١٠ = ٦٥٠، لا ١٥ × متوسّطٍ جارٍ."""
    tenant, ils, customer, product = env
    sale = _sell(tenant, ils, customer, product, 60, "S-4")

    ret = _return(tenant, ils, customer, product, 15, "R-4", sale)

    from inventory.models import StockMovement
    mv = StockMovement.objects.get(reference_id=ret.id, movement_type="RETURN_IN")
    assert mv.total_cost == Decimal("650.00")


def test_full_return_restores_the_queue_exactly_and_zeroes_the_profit(env):
    """مرتجعٌ كاملٌ يُعيد الرتل كما كان، وكلفتُه = كلفةُ البيعة بالضبط."""
    tenant, ils, customer, product = env
    sale = _sell(tenant, ils, customer, product, 60, "S-5")

    ret = _return(tenant, ils, customer, product, 60, "R-5", sale)

    assert _layers(product) == {
        Decimal("10.0000"): Decimal("50.0000"),
        Decimal("60.0000"): Decimal("20.0000"),
    }
    from inventory.models import StockMovement
    out = StockMovement.objects.get(reference_id=sale.id, movement_type="OUT")
    back = StockMovement.objects.get(reference_id=ret.id, movement_type="RETURN_IN")
    assert back.total_cost == out.total_cost == Decimal("1100.00")


def test_two_partial_returns_walk_the_consumption_backwards(env):
    """مرتجعان متتاليان: الثاني يجد ما يفكّه — الصفُّ المنقوصُ لم يُحذف."""
    tenant, ils, customer, product = env
    sale = _sell(tenant, ils, customer, product, 60, "S-6")

    _return(tenant, ils, customer, product, 5, "R-6a", sale)
    _return(tenant, ils, customer, product, 10, "R-6b", sale)

    assert _layers(product) == {
        Decimal("10.0000"): Decimal("5.0000"),
        Decimal("60.0000"): Decimal("20.0000"),
    }


def test_return_without_an_original_invoice_still_posts(env):
    """مرتجعٌ حرٌّ بلا فاتورةٍ أصليّة لا ينكسر — يدخل بطبقةٍ جديدة كما كان."""
    tenant, ils, customer, product = env
    _sell(tenant, ils, customer, product, 60, "S-7")

    ret = _return(tenant, ils, customer, product, 5, "R-7", None)

    assert ret.status == SalesInvoice.STATUS_POSTED
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("15.0000")


def test_returning_more_than_was_sold_adds_the_surplus_as_a_layer(env):
    """مرتجعٌ أكبرُ من البيعة: يُفكّ ما استُهلك، والفائضُ طبقةٌ جديدة."""
    tenant, ils, customer, product = env
    sale = _sell(tenant, ils, customer, product, 10, "S-8")  # ١٠ من طبقةِ العشرة

    _return(tenant, ils, customer, product, 15, "R-8", sale)

    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("75.0000")
    assert sum(
        (layer.remaining_qty for layer in StockLayer.objects.filter(product=product)),
        Decimal("0"),
    ) == Decimal("75.0000")
