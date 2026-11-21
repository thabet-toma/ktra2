"""أمر `check_fifo_layers` — حارسُ الثابت «Σ`remaining_qty` ≤ max(الرصيد، 0)» بعد أيّ تصحيح.

يُبلغ صنفين: **فائضٌ** (طبقاتٌ أكثرُ من الرصيد — طبقةٌ وهميّة تُكلِّف بيعاً لاحقاً) و**غيرُ
مغطّى** (رصيدٌ موجبٌ بلا طبقات — ينتظر الرأبَ الكسول). الافتراضُ معاينةٌ لا تكتب؛ و`--apply`
يرأب غيرَ المغطّى وحده بـ`fifo.backfill_opening_layer` (محايدٌ على الميزانية بالبناء)،
ولا يمسّ الفائض: أيُّ طبقةٍ هي الوهميّة قرارُ محاسبٍ يقرأ الحركات، لا سكربت.
"""
import datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from accounting.models import JournalHeader
from inventory.models import Product, StockLayer, StockMovement
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _tenant(name):
    return create_company(name, User.objects.create_user(username=f"chk-{name}", password="x"))


def _product(tenant, sku, qty, avg):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=sku,
        quantity_on_hand=Decimal(qty), avg_cost=Decimal(avg))


def _layer(tenant, product, qty, cost):
    mv = StockMovement.objects.create(
        tenant=tenant, product=product, movement_type="IN", quantity=Decimal(qty),
        unit_cost=Decimal(cost), reference_type="PURCHASE_INVOICE", reference_id=1,
        movement_date=datetime.date(2026, 6, 1))
    return StockLayer.objects.create(
        tenant=tenant, product=product, layer_date=mv.movement_date, original_qty=Decimal(qty),
        remaining_qty=Decimal(qty), unit_cost=Decimal(cost), source_movement=mv)


def _run(*args):
    out = StringIO()
    call_command("check_fifo_layers", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def broken():
    tenant = _tenant("فحص")
    excess = _product(tenant, "EXCESS-109", "0", "270")
    _layer(tenant, excess, "12", "270")
    uncovered = _product(tenant, "ORPHAN-46", "7", "190")
    clean = _product(tenant, "CLEAN-1", "5", "80")
    _layer(tenant, clean, "5", "80")
    return tenant, excess, uncovered, clean


def test_preview_reports_both_breaches_and_writes_nothing(broken):
    tenant, excess, uncovered, clean = broken
    layers_before = StockLayer.objects.count()

    out = _run("--tenant", str(tenant.TenantID))

    assert "EXCESS-109" in out and "ORPHAN-46" in out
    assert "CLEAN-1" not in out
    assert StockLayer.objects.count() == layers_before


def test_apply_backfills_only_the_uncovered_balance_at_book_cost(broken):
    tenant, excess, uncovered, clean = broken
    journals_before = JournalHeader.objects.count()

    _run("--tenant", str(tenant.TenantID), "--apply")

    opening = StockLayer.objects.get(product=uncovered, source_movement__isnull=True)
    assert (opening.remaining_qty, opening.unit_cost) == (Decimal("7.0000"), Decimal("190.0000"))
    assert StockLayer.objects.get(product=excess).remaining_qty == Decimal("12.0000"), \
        "الفائضُ لا يُقصّ آليّاً."
    uncovered.refresh_from_db()
    assert (uncovered.quantity_on_hand, uncovered.avg_cost) == (Decimal("7.0000"), Decimal("190.0000"))
    assert JournalHeader.objects.count() == journals_before

    again = _run("--tenant", str(tenant.TenantID))
    assert "ORPHAN-46" not in again and "EXCESS-109" in again


def test_scoped_to_one_tenant(broken):
    tenant, *_ = broken
    other = _tenant("أخرى")
    _product(other, "OTHER-ORPHAN", "3", "10")

    out = _run("--tenant", str(tenant.TenantID))
    assert "OTHER-ORPHAN" not in out


def test_apply_requires_a_tenant(broken):
    with pytest.raises(CommandError):
        _run("--apply")


def test_m0_t5_sync_avg_cost_from_layers_command():
    """T5: أمر sync_avg_cost_from_layers — المعاينة لا تكتب، --apply يضبط المغطّى والصفر، يترك المتطابق (unchanged)، يتخطّى غير المغطّى، ويعزل الشركات بعدّادات دقيقة."""
    tenant_a = _tenant("مزامنة-أ")
    tenant_b = _tenant("مزامنة-ب")

    covered = _product(tenant_a, "SYNC-COV", "10", "15")
    _layer(tenant_a, covered, "4", "10")
    _layer(tenant_a, covered, "6", "20")  # (40 + 120) / 10 = 16.0000

    unchanged_a = _product(tenant_a, "SYNC-SAME", "5", "30")
    _layer(tenant_a, unchanged_a, "5", "30")  # avg_cost يطابق متوسط الطبقات المفتوحة

    zero_qoh = _product(tenant_a, "SYNC-ZERO", "0", "99")
    uncovered = _product(tenant_a, "SYNC-UNC", "7", "55")
    other_b = _product(tenant_b, "SYNC-B", "0", "88")

    dry_out = StringIO()
    call_command("sync_avg_cost_from_layers", "--tenant", str(tenant_a.TenantID), stdout=dry_out)
    for prod, expected in (
        (covered, "15"),
        (unchanged_a, "30"),
        (zero_qoh, "99"),
        (uncovered, "55"),
        (other_b, "88"),
    ):
        prod.refresh_from_db()
        assert prod.avg_cost == Decimal(expected)

    apply_out = StringIO()
    with patch.object(Product, "save", autospec=True, side_effect=Product.save) as save:
        call_command("sync_avg_cost_from_layers", "--tenant", str(tenant_a.TenantID), "--apply", stdout=apply_out)
    assert unchanged_a.pk not in [call.args[0].pk for call in save.call_args_list]
    apply_txt = apply_out.getvalue()
    covered.refresh_from_db()
    unchanged_a.refresh_from_db()
    zero_qoh.refresh_from_db()
    uncovered.refresh_from_db()
    other_b.refresh_from_db()

    assert covered.avg_cost == Decimal("16.0000")
    assert unchanged_a.avg_cost == Decimal("30.0000")
    assert zero_qoh.avg_cost == Decimal("0.0000")
    assert uncovered.avg_cost == Decimal("55.0000")
    assert other_b.avg_cost == Decimal("88.0000")
    assert "SYNC-COV" in apply_txt
    assert "SYNC-UNC" in apply_txt
    # (a) المتطابق لا يُمسّ ولا يطبع سطر تحديث/تخطّي
    assert "SYNC-SAME" not in apply_txt
    # (b) سطر الملخّص لـ --apply --tenant A يطابق التركيبات بالضبط
    assert "الملخّص: synced=2 · unchanged=1 · skipped_uncovered=1" in apply_txt
    assert "تمّت مزامنة 2 منتج." in apply_txt


def test_m0_t5_sync_avg_cost_from_layers_dry_run_without_tenant():
    """T5(c): معاينة sync_avg_cost_from_layers بدون --tenant تعرض الشركتين ولا تكتب شيئاً."""
    tenant_a = _tenant("مزامنة-كل-أ")
    tenant_b = _tenant("مزامنة-كل-ب")

    cov_a = _product(tenant_a, "ALL-COV-A", "10", "15")
    _layer(tenant_a, cov_a, "10", "20")
    same_a = _product(tenant_a, "ALL-SAME-A", "5", "30")
    _layer(tenant_a, same_a, "5", "30")
    unc_b = _product(tenant_b, "ALL-UNC-B", "4", "45")
    zero_b = _product(tenant_b, "ALL-ZERO-B", "0", "88")

    out = StringIO()
    with patch.object(Product, "save", autospec=True, side_effect=Product.save) as save:
        call_command("sync_avg_cost_from_layers", stdout=out)
    save.assert_not_called()
    txt = out.getvalue()

    assert f"[{tenant_a.TenantID}] ALL-COV-A" in txt
    assert f"[{tenant_b.TenantID}] ALL-UNC-B" in txt
    assert f"[{tenant_b.TenantID}] ALL-ZERO-B" in txt
    assert "الملخّص: synced=2 · unchanged=1 · skipped_uncovered=1" in txt
    for prod, expected in ((cov_a, "15"), (same_a, "30"), (unc_b, "45"), (zero_b, "88")):
        prod.refresh_from_db()
        assert prod.avg_cost == Decimal(expected)
