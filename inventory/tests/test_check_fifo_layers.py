"""أمر `check_fifo_layers` — حارسُ الثابت «Σ`remaining_qty` ≤ max(الرصيد، 0)» بعد أيّ تصحيح.

يُبلغ صنفين: **فائضٌ** (طبقاتٌ أكثرُ من الرصيد — طبقةٌ وهميّة تُكلِّف بيعاً لاحقاً) و**غيرُ
مغطّى** (رصيدٌ موجبٌ بلا طبقات — ينتظر الرأبَ الكسول). الافتراضُ معاينةٌ لا تكتب؛ و`--apply`
يرأب غيرَ المغطّى وحده بـ`fifo.backfill_opening_layer` (محايدٌ على الميزانية بالبناء)،
ولا يمسّ الفائض: أيُّ طبقةٍ هي الوهميّة قرارُ محاسبٍ يقرأ الحركات، لا سكربت.
"""
import datetime
from decimal import Decimal
from io import StringIO

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
