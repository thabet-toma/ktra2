"""تسوية الطبقات المؤقّتة حين تصل البضاعة الحقيقيّة (مواصفة #137، تذكرة #136).

يثبت:
  1. الثابتُ المخروق — بيعُ 10 على رصيدٍ صفر ثم استلامُ 10 بكلفة 5 كان ينتج
     `quantity_on_hand == 0` بينما `Σ layers.remaining_qty == 10` (السبب:
     الاستلامُ كان يُنشئ طبقةً جديدةً كاملةً بدل أن يسدّ الحفرة المؤقّتة أوّلاً).
     بعد الإصلاح: `Σ remaining_qty == quantity_on_hand` دائماً.
  2. نفس الثابت عبر تسلسلٍ أطول ومختلط (استلام·بيع·بيعٌ على السالب·استلام·مرتجع).
  3. قيدُ الفرق: الاتجاهان (الحقيقية أعلى/أقلّ من المخمَّنة)، بتاريخ الاستلام
     دائماً، وبلا قيدٍ عند فرقٍ صفري.
  4. النجاح رغم إقفال فترة البيعة الأصلية — القيد بتاريخ الاستلام فقط.
  5. تسويةٌ جزئية عبر أكثر من وارِد، ووصولٌ أكبر من المعلَّق.
  6. عزلُ الشركات في التسوية، وتقريرُ «الطبقات المعلَّقة» بلا حذفٍ.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models import F, Sum

from accounting.models import Account, FiscalPeriod, JournalHeader
from inventory.models import Product, ProductCategory, StockLayer
from inventory.services import record_stock_movement
from tenants.services import create_company

pytestmark = pytest.mark.django_db

Q4 = Decimal("0.0001")


def _make_tenant(name):
    user = User.objects.create_user(username=f"provrec-{name}", password="x")
    return create_company(f"شركة {name}", user)


def _make_product_with_accounts(tenant, sku, name="صنف اختبار"):
    """منتجٌ بفئةٍ تحمل حسابَي مخزون/ت.ب.م — نمط `StocktakeTest`
    (`inventory/tests/test_inventory_documents.py`) كي يحلّ `_resolve_line_account`
    دون سقوطٍ على الافتراضي المُشترك (`code`s قد تتعارض بين اختبارات الشركات)."""
    inv_acct = Account.objects.create(
        tenant=tenant, code=f"1104-{sku}", name="المخزون", account_type="Asset", is_active=True,
    )
    cogs_acct = Account.objects.create(
        tenant=tenant, code=f"5101-{sku}", name="ت.ب.م", account_type="Expense", is_active=True,
    )
    cat = ProductCategory.objects.create(
        tenant=tenant, name=f"فئة {sku}", inventory_account=inv_acct, cogs_account=cogs_acct,
    )
    product = Product.objects.create(
        tenant=tenant, sku=sku, name_ar=name, category=cat,
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )
    return product, inv_acct, cogs_acct


def _open_period(tenant, name, start, end):
    return FiscalPeriod.objects.create(
        tenant=tenant, name=name, start_date=start, end_date=end,
        status="Open", is_closed=False,
    )


def _closed_period(tenant, name, start, end):
    return FiscalPeriod.objects.create(
        tenant=tenant, name=name, start_date=start, end_date=end,
        status="Closed", is_closed=True,
    )


def _assert_layer_invariant(product):
    """الثابت الحقيقي (يعمّم الصيغة المخروقة في مواصفة #137): Σ remaining_qty
    لكل طبقات المنتج، مطروحاً منه المعلَّق غير المُسوَّى بعد لطبقاته المؤقّتة
    (Σ original_qty − reconciled_qty حيث is_provisional=True)، == quantity_on_hand.

    لماذا الطرح: طبقةٌ مؤقّتة تُستهلك بالكامل فور إنشائها (`remaining_qty` تهبط
    لصفر فوراً — سلوكٌ قائمٌ من قبل هذه المواصفة، انظر
    `test_negative_stock_creates_provisional_layer_and_consumes_it_without_exception`
    في `test_fifo_movements.py`)، فـ«الدَّين» غير المسدود لا يظهر في `remaining_qty`
    بل في الفارق `original_qty − reconciled_qty` وحده. حين لا توجد طبقاتٌ مؤقّتة
    معلَّقة (المعلَّق = صفر) تختزل هذه الصيغة تماماً إلى المقارنة الحرفية
    Σ remaining_qty == quantity_on_hand — وهي بالضبط المقارنة المُبلَّغة في
    السبر (سطرا العطب الأول أعلى الملف)."""
    product.refresh_from_db()
    layers = StockLayer.objects.filter(product=product)
    total_remaining = layers.aggregate(s=Sum("remaining_qty"))["s"] or Decimal("0")
    total_pending = (
        layers.filter(is_provisional=True).aggregate(
            s=Sum(F("original_qty") - F("reconciled_qty"))
        )["s"]
        or Decimal("0")
    )
    adjusted = (total_remaining - total_pending).quantize(Q4)
    expected = Decimal(str(product.quantity_on_hand)).quantize(Q4)
    assert adjusted == expected, (
        f"انتهك الثابت: (Σremaining_qty={total_remaining} − Σpending={total_pending}) "
        f"= {adjusted} != quantity_on_hand={product.quantity_on_hand}"
    )


# ────────────────────────────────────────────────────────────────────
# 1) الثابت المخروق — الاختبار الأحمر أولاً
# ────────────────────────────────────────────────────────────────────

def test_layer_invariant_sell_on_zero_then_receive_matches_quantity_on_hand():
    """بيعُ 10 على رصيدٍ صفر، ثمّ استلامُ 10 بكلفة 5 ⟵
    Σ remaining_qty == quantity_on_hand == 0 (المخرج المُبلَّغ: كانا 10 و0)."""
    tenant = _make_tenant("ثابت الطبقات")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, _, _ = _make_product_with_accounts(tenant, "INV-1")

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("-10.0000")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant,
    )
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("0.0000")
    _assert_layer_invariant(product)


def test_layer_invariant_holds_after_mixed_sequence():
    """تسلسلٌ مختلط: استلام·بيع·بيعٌ على السالب·استلام·مرتجع — الثابت يصمد
    بعد كل خطوة."""
    tenant = _make_tenant("تسلسل مختلط")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, _, _ = _make_product_with_accounts(tenant, "INV-2")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("20"),
        unit_cost=Decimal("4"), movement_date="2026-01-01", tenant=tenant,
    )
    _assert_layer_invariant(product)

    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("5"),
        movement_date="2026-01-02", tenant=tenant,
    )
    _assert_layer_invariant(product)

    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("30"),
        movement_date="2026-01-03", tenant=tenant,
    )
    _assert_layer_invariant(product)
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("-15.0000")

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("6"), movement_date="2026-01-04", tenant=tenant,
    )
    _assert_layer_invariant(product)

    # مرتجعٌ بلا `restores_movement` (لا يشير لحركة صرفٍ بعينها — `restore()`
    # يعكس *كامل* استهلاك الحركة المشار إليها فلا يصلح لإرجاعٍ جزئي؛ هذا
    # سيناريو «مرتجعٌ عام» عادي) — يمرّ عبر نفس مسار الوارد العادي فيُسوّي هو
    # الآخر ما تبقّى من المعلَّق (5 من أصل 15، بعد أن سدّت الحركة السابقة 10).
    product.refresh_from_db()
    record_stock_movement(
        product=product, movement_type="RETURN_IN", quantity=Decimal("3"),
        movement_date="2026-01-05", tenant=tenant,
    )
    _assert_layer_invariant(product)


# ────────────────────────────────────────────────────────────────────
# 2) قيد الفرق
# ────────────────────────────────────────────────────────────────────

def test_reconciliation_diff_entry_when_real_cost_higher_debits_cogs():
    """بيعُ 10 على صفرٍ بكلفةٍ مخمَّنةٍ 4، ثمّ استلامُ 10 بكلفة 5 ⟵ قيدٌ بفرق 10
    (10 وحدة × فرق 1)، مدين ت.ب.م / دائن المخزون، بتاريخ الاستلام."""
    tenant = _make_tenant("فرق أعلى")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, inv_acct, cogs_acct = _make_product_with_accounts(tenant, "INV-3")
    product.avg_cost = Decimal("4")
    product.save(update_fields=["avg_cost"])

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    in_mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant,
    )

    journal = JournalHeader.objects.get(
        reference_type="STOCK_PROVISIONAL_RECONCILE", reference_id=in_mv.id,
    )
    assert journal.is_posted
    assert str(journal.transaction_date) == "2026-01-10"

    lines = {l.account_id: l for l in journal.lines.all()}
    assert lines[cogs_acct.id].debit == Decimal("10.00")
    assert lines[cogs_acct.id].credit == Decimal("0.00")
    assert lines[inv_acct.id].credit == Decimal("10.00")
    assert lines[inv_acct.id].debit == Decimal("0.00")


def test_reconciliation_diff_entry_when_real_cost_lower_debits_inventory():
    """مخمَّنةٌ 6 والحقيقيّةُ 5 ⟵ فرقٌ 10 (10 وحدة × فرق 1) بالاتجاه المقلوب:
    مدين المخزون / دائن ت.ب.م."""
    tenant = _make_tenant("فرق معكوس")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, inv_acct, cogs_acct = _make_product_with_accounts(tenant, "INV-4")
    product.avg_cost = Decimal("6")
    product.save(update_fields=["avg_cost"])

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    in_mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant,
    )

    journal = JournalHeader.objects.get(
        reference_type="STOCK_PROVISIONAL_RECONCILE", reference_id=in_mv.id,
    )
    lines = {l.account_id: l for l in journal.lines.all()}
    assert lines[inv_acct.id].debit == Decimal("10.00")
    assert lines[inv_acct.id].credit == Decimal("0.00")
    assert lines[cogs_acct.id].credit == Decimal("10.00")
    assert lines[cogs_acct.id].debit == Decimal("0.00")


def test_zero_diff_creates_no_journal():
    """الكلفةُ المخمَّنة == الحقيقيّة ⟵ لا قيدَ إطلاقاً."""
    tenant = _make_tenant("فرق صفري")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, _, _ = _make_product_with_accounts(tenant, "INV-5")
    product.avg_cost = Decimal("5")
    product.save(update_fields=["avg_cost"])

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    before = JournalHeader.objects.count()
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant,
    )
    after = JournalHeader.objects.count()
    assert after == before


def test_reconciliation_succeeds_when_sale_period_is_closed():
    """أقفِل الفترة التي وقع فيها البيع، ثمّ استلِم في فترةٍ مفتوحة لاحقة ⟵
    ينجح، والقيد بتاريخ الاستلام، بلا حاجةٍ لفتح فترة البيع أبداً."""
    tenant = _make_tenant("فترة مقفلة")
    product, inv_acct, cogs_acct = _make_product_with_accounts(tenant, "INV-6")
    product.avg_cost = Decimal("4")
    product.save(update_fields=["avg_cost"])

    _closed_period(tenant, "يناير المقفلة", "2026-01-01", "2026-01-31")
    _open_period(tenant, "فبراير المفتوحة", "2026-02-01", "2026-02-28")

    # البيع على مخزونٍ سالب هنا لا يستدعي post_journal (لا فحص فترة على
    # حركة المخزون نفسها) — الفحص فقط عند ترحيل قيد الفرق لاحقاً.
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-15", tenant=tenant,
    )
    product.refresh_from_db()

    in_mv = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-02-01", tenant=tenant,
    )
    product.refresh_from_db()
    _assert_layer_invariant(product)

    journal = JournalHeader.objects.get(
        reference_type="STOCK_PROVISIONAL_RECONCILE", reference_id=in_mv.id,
    )
    assert str(journal.transaction_date) == "2026-02-01"
    assert journal.is_posted


# ────────────────────────────────────────────────────────────────────
# 3) تسويةٌ جزئية / وصولٌ أكبر من المعلَّق
# ────────────────────────────────────────────────────────────────────

def test_partial_reconciliation_across_two_receipts():
    """معلَّقٌ 10، يصل 4 ⟵ reconciled_qty=4 والقيد على أربعٍ لا عشر، والباقي
    ستٌّ معلَّقة يذكرها التقرير؛ ثمّ يصل 6 ⟵ تُسوَّى وتخرج من التقرير."""
    from inventory.fifo import pending_provisional_layers

    tenant = _make_tenant("تسوية جزئية")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, inv_acct, cogs_acct = _make_product_with_accounts(tenant, "INV-7")
    product.avg_cost = Decimal("4")
    product.save(update_fields=["avg_cost"])

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    provisional_layer = StockLayer.objects.get(product=product, is_provisional=True)
    assert provisional_layer.original_qty == Decimal("10.0000")
    assert provisional_layer.reconciled_qty == Decimal("0.0000")

    in_mv1 = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("4"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant,
    )
    provisional_layer.refresh_from_db()
    assert provisional_layer.reconciled_qty == Decimal("4.0000")

    journal1 = JournalHeader.objects.get(
        reference_type="STOCK_PROVISIONAL_RECONCILE", reference_id=in_mv1.id,
    )
    lines1 = {l.account_id: l for l in journal1.lines.all()}
    # فرق 1 × 4 وحدات = 4
    assert lines1[cogs_acct.id].debit == Decimal("4.00")
    assert lines1[inv_acct.id].credit == Decimal("4.00")

    pending = pending_provisional_layers(tenant_id=tenant.TenantID)
    assert len(pending) == 1
    assert pending[0]["layer_id"] == provisional_layer.pk
    assert pending[0]["pending_qty"] == Decimal("6.0000")

    product.refresh_from_db()
    _assert_layer_invariant(product)

    in_mv2 = record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("6"),
        unit_cost=Decimal("5"), movement_date="2026-01-15", tenant=tenant,
    )
    provisional_layer.refresh_from_db()
    assert provisional_layer.reconciled_qty == Decimal("10.0000")

    journal2 = JournalHeader.objects.get(
        reference_type="STOCK_PROVISIONAL_RECONCILE", reference_id=in_mv2.id,
    )
    lines2 = {l.account_id: l for l in journal2.lines.all()}
    # فرق 1 × 6 وحدات = 6
    assert lines2[cogs_acct.id].debit == Decimal("6.00")
    assert lines2[inv_acct.id].credit == Decimal("6.00")

    pending_after = pending_provisional_layers(tenant_id=tenant.TenantID)
    assert pending_after == []

    product.refresh_from_db()
    _assert_layer_invariant(product)


def test_receipt_larger_than_pending_creates_open_remainder():
    """معلَّقٌ 10 ويصل 25 ⟵ الطبقة الجديدة remaining_qty=15 وoriginal_qty=25،
    والثابت سليم."""
    tenant = _make_tenant("وصول أكبر")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product, _, _ = _make_product_with_accounts(tenant, "INV-8")
    product.avg_cost = Decimal("4")
    product.save(update_fields=["avg_cost"])

    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product.refresh_from_db()

    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("25"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant,
    )
    product.refresh_from_db()

    new_layer = StockLayer.objects.get(
        product=product, is_provisional=False, original_qty=Decimal("25.0000"),
    )
    assert new_layer.original_qty == Decimal("25.0000")
    assert new_layer.remaining_qty == Decimal("15.0000")
    _assert_layer_invariant(product)


# ────────────────────────────────────────────────────────────────────
# 4) عزل الشركات + التقرير
# ────────────────────────────────────────────────────────────────────

def test_tenant_isolation_provisional_not_reconciled_by_other_tenant_receipt():
    """معلَّقٌ في شركةٍ لا يُسوّى بواردِ شركةٍ أخرى إطلاقاً — نفس SKU، منتجان
    مستقلّان بالكامل."""
    tenant_a = _make_tenant("عزل أ")
    tenant_b = _make_tenant("عزل ب")
    _open_period(tenant_a, "2026", "2026-01-01", "2026-12-31")
    _open_period(tenant_b, "2026", "2026-01-01", "2026-12-31")
    product_a, _, _ = _make_product_with_accounts(tenant_a, "INV-9A")
    product_b, _, _ = _make_product_with_accounts(tenant_b, "INV-9B")

    record_stock_movement(
        product=product_a, movement_type="OUT", quantity=Decimal("10"),
        movement_date="2026-01-05", tenant=tenant_a,
    )
    product_a.refresh_from_db()

    layer_a = StockLayer.objects.get(product=product_a, is_provisional=True)
    assert layer_a.reconciled_qty == Decimal("0.0000")

    # وارِدٌ في الشركة ب على منتجها المستقل — لا يجوز أن يمسّ معلَّق الشركة أ.
    record_stock_movement(
        product=product_b, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), movement_date="2026-01-10", tenant=tenant_b,
    )

    layer_a.refresh_from_db()
    assert layer_a.reconciled_qty == Decimal("0.0000")
    assert layer_a.remaining_qty == Decimal("0.0000")


def test_pending_provisional_layers_report_excludes_reconciled_and_deletes_nothing():
    """التقرير يعيد المعلَّق فقط، لا المُسوّى، ولا يحذف شيئاً."""
    from inventory.fifo import pending_provisional_layers

    tenant = _make_tenant("تقرير المعلَّق")
    _open_period(tenant, "2026", "2026-01-01", "2026-12-31")
    product_pending, _, _ = _make_product_with_accounts(tenant, "INV-10A")
    product_reconciled, _, _ = _make_product_with_accounts(tenant, "INV-10B")

    record_stock_movement(
        product=product_pending, movement_type="OUT", quantity=Decimal("7"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product_pending.refresh_from_db()

    record_stock_movement(
        product=product_reconciled, movement_type="OUT", quantity=Decimal("3"),
        movement_date="2026-01-05", tenant=tenant,
    )
    product_reconciled.refresh_from_db()
    record_stock_movement(
        product=product_reconciled, movement_type="IN", quantity=Decimal("3"),
        unit_cost=Decimal("5"), movement_date="2026-01-06", tenant=tenant,
    )

    layers_before = StockLayer.objects.count()
    pending = pending_provisional_layers(tenant_id=tenant.TenantID)
    layers_after = StockLayer.objects.count()

    assert layers_before == layers_after  # بلا حذف
    product_ids = {row["product_id"] for row in pending}
    assert product_pending.id in product_ids
    assert product_reconciled.id not in product_ids
