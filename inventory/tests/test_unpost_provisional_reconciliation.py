"""إلغاءُ ترحيل وارِدٍ سدّ طبقاتٍ مؤقّتة يُرجع السدَّ ويحذف قيدَ فرقه.

بيعٌ على مخزونٍ سالب يُنشئ طبقةً مؤقّتة بكلفةٍ مخمَّنة؛ والوارِدُ الحقيقيّ يسدّها
(`fifo.reconcile_provisional`: `reconciled_qty` يزيد) ويُرحّل قيدَ الفرق بين الكلفتين
(`STOCK_PROVISIONAL_RECONCILE` بمرجع حركة الوارد). وإلغاءُ ترحيل ذلك الوارد كان:

1. **يترك قيدَ الفرق يتيماً في الدفتر** — `unpost_document` يحذف قيودَ المستند بأنواعه
   وحدها، وهذا القيد بمرجع الحركة لا المستند. وإعادةُ الترحيل تُطلع قيداً ثانياً
   للفرق نفسه: ت.ب.م والمخزون ينحرفان بمثليه.
2. **يترك الطبقةَ المؤقّتة «مسدودة»** بوارِدٍ لم يعد موجوداً: المعلَّقُ ينقص بغير حقّ
   فينكسر الثابت Σ`remaining_qty` − المعلَّق = الرصيد، ووارِدٌ لاحقٌ لا يجد ما يسدّه.

ولا يُشتقّ «أيُّ طبقةٍ سدّها أيُّ وارِد» اشتقاقاً صادقاً حين يتعدّد الواردون بكلفٍ
مختلفة، فالسدُّ صار سجلّاً (`StockLayerReconciliation`) نظيرَ سجلّ الاستهلاك.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models import F, Sum

from accounting.models import Account, FiscalPeriod, JournalHeader
from inventory.models import (
    Product, ProductCategory, StockLayer, StockLayerReconciliation, StockMovement,
)
from inventory.services import record_stock_movement, reverse_stock_movements
from tenants.services import create_company

pytestmark = pytest.mark.django_db

Q4 = Decimal("0.0001")
RECON = "STOCK_PROVISIONAL_RECONCILE"


@pytest.fixture
def product():
    user = User.objects.create_user(username="unrecon", password="x")
    tenant = create_company("شركة السدّ", user)
    FiscalPeriod.objects.create(
        tenant=tenant, name="2026", start_date="2026-01-01", end_date="2026-12-31",
        status="Open", is_closed=False)
    inv = Account.objects.create(
        tenant=tenant, code="1104-UR", name="المخزون", account_type="Asset", is_active=True)
    cogs = Account.objects.create(
        tenant=tenant, code="5101-UR", name="ت.ب.م", account_type="Expense", is_active=True)
    cat = ProductCategory.objects.create(
        tenant=tenant, name="فئة", inventory_account=inv, cogs_account=cogs)
    return Product.objects.create(
        tenant=tenant, sku="UR-1", name_ar="صنف", category=cat,
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))


def _sell_on_negative(product, qty, guessed_cost, date="2026-01-05"):
    Product.objects.filter(pk=product.pk).update(avg_cost=Decimal(guessed_cost))
    product.refresh_from_db()
    return record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal(qty),
        movement_date=date, tenant=product.tenant)


def _receive(product, qty, cost, ref, date="2026-01-10"):
    return record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal(qty), unit_cost=Decimal(cost),
        reference_type="PURCHASE_INVOICE", reference_id=ref, movement_date=date,
        tenant=product.tenant)


def _unpost(product, ref):
    reverse_stock_movements(
        tenant_id=product.tenant_id, reference_id=ref, reference_types=["PURCHASE_INVOICE"])


def _recon_journals(product):
    return JournalHeader.objects.filter(tenant_id=product.tenant_id, reference_type=RECON)


def _assert_invariant(product):
    product.refresh_from_db()
    layers = StockLayer.objects.filter(product=product)
    remaining = layers.aggregate(s=Sum("remaining_qty"))["s"] or Decimal("0")
    pending = layers.filter(is_provisional=True).aggregate(
        s=Sum(F("original_qty") - F("reconciled_qty")))["s"] or Decimal("0")
    assert (remaining - pending).quantize(Q4) == Decimal(str(product.quantity_on_hand)).quantize(Q4), (
        f"انكسر الثابت: متبقٍّ={remaining} معلَّق={pending} رصيد={product.quantity_on_hand}")


def test_unposting_the_receipt_reopens_the_provisional_layer_and_drops_its_diff_journal(product):
    _sell_on_negative(product, "10", "4")
    _receive(product, "10", "5", ref=901)
    assert _recon_journals(product).count() == 1

    _unpost(product, 901)

    assert _recon_journals(product).count() == 0, "بقي قيدُ فرق التسوية يتيماً بعد إلغاء الوارد."
    provisional = StockLayer.objects.get(product=product, is_provisional=True)
    assert provisional.reconciled_qty == Decimal("0.0000"), "بقيت الطبقةُ المؤقّتة «مسدودة»."
    assert not StockLayerReconciliation.objects.filter(layer=provisional).exists()
    _assert_invariant(product)


def test_repost_after_unpost_books_the_difference_once_not_twice(product):
    _sell_on_negative(product, "10", "4")
    _receive(product, "10", "5", ref=902)
    _unpost(product, 902)

    _receive(product, "10", "5", ref=902)

    journals = list(_recon_journals(product))
    assert len(journals) == 1, f"قيودُ فرقٍ للتسوية نفسِها: {len(journals)}"
    total = sum((l.debit for l in journals[0].lines.all()), Decimal("0"))
    assert total == Decimal("10.00")
    _assert_invariant(product)


def test_unposting_the_first_of_two_receipts_reopens_exactly_the_layer_it_filled(product):
    """مؤقّتتان بكلفتين (10 ثمّ 20)، وواردان بـ15 يسدّ كلٌّ منهما واحدة. إلغاءُ الأوّل
    يفتح **الأولى** — لا الأحدث — فيبقى الدفترُ صادقاً عند إعادة ترحيله."""
    first_sale = _sell_on_negative(product, "5", "10", date="2026-01-03")
    _sell_on_negative(product, "5", "20", date="2026-01-04")
    _receive(product, "5", "15", ref=903)
    _receive(product, "5", "15", ref=904)
    p_first = StockLayer.objects.get(product=product, is_provisional=True, source_movement=first_sale)

    _unpost(product, 903)

    reopened = {l.pk: l.original_qty - l.reconciled_qty
                for l in StockLayer.objects.filter(product=product, is_provisional=True)}
    assert reopened[p_first.pk] == Decimal("5.0000")
    assert sum(reopened.values()) == Decimal("5.0000")
    remaining = list(_recon_journals(product))
    assert len(remaining) == 1
    assert remaining[0].reference_id == StockMovement.objects.get(reference_id=904).id
    _assert_invariant(product)


def test_a_reconciliation_recorded_before_the_ledger_existed_is_still_reversed(product):
    """سدٌّ جرى قبل سجلّ التسوية (على الإنتاج منذ نشر FIFO): الكميّةُ تُشتقّ من طبقة
    الوارد نفسها (الأصل − المتبقّي − المستهلَك)، فلا يبقى معلَّقٌ ضائع."""
    _sell_on_negative(product, "10", "4")
    receipt = _receive(product, "10", "5", ref=905)
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("3"), unit_cost=Decimal("5"),
        reference_type="PURCHASE_INVOICE", reference_id=906, movement_date="2026-01-11",
        tenant=product.tenant)
    StockLayerReconciliation.objects.filter(movement=receipt).delete()

    _unpost(product, 905)

    provisional = StockLayer.objects.get(product=product, is_provisional=True)
    assert provisional.reconciled_qty == Decimal("0.0000")
    assert _recon_journals(product).count() == 0
    _assert_invariant(product)
