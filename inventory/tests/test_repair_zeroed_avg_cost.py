import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError

from inventory.models import Product, StockLayer, StockMovement
from inventory.services import (
    _recompute_product_stock, repair_zeroed_avg_cost, set_owner_avg_cost,
    sync_avg_cost_from_layers,
)
from tenants.services import create_company

pytestmark = pytest.mark.django_db
D = datetime.date(2026, 6, 1)


def _tenant(name):
    return create_company(name, User.objects.create_user(username=f'repair-{name}', password='x'))


def _product(tenant, sku, **kwargs):
    return Product.objects.create(tenant=tenant, sku=sku, name_ar=sku, avg_cost=0, **kwargs)


def _movement(product, kind, before=0, after=0, **kwargs):
    movement = StockMovement.objects.create(
        tenant_id=product.tenant_id, product=product, movement_type=kind,
        quantity=Decimal('2'), movement_date=D, avg_cost_before=before,
        avg_cost_after=after, **kwargs)
    Product.objects.filter(pk=product.pk).update(avg_cost=Decimal('0'))
    return movement


def _trigger(product):
    _movement(product, 'IN', after=40)
    return _movement(product, 'OUT', before=40)


def _repair(product, **kwargs):
    return repair_zeroed_avg_cost(product, **kwargs)


def _cost(product):
    product.refresh_from_db()
    return product.avg_cost


def _layer(product, movement, cost, provisional=True):
    return StockLayer.objects.create(tenant_id=product.tenant_id, product=product,
        layer_date=D, original_qty=1, remaining_qty=0, unit_cost=cost,
        source_movement=movement, is_provisional=provisional)


def test_trigger_preview_and_apply():
    product = _product(_tenant('trigger'), 'T')
    trigger = _trigger(product)
    result = _repair(product)
    assert (result['status'], result['after'], result['source'], result['source_movement_id']) == (
        'repaired', Decimal('40.0000'), 'trigger', trigger.pk)
    assert _cost(product) == 0
    _repair(product, apply=True)
    assert _cost(product) == 40


def test_repeat_apply_skips_nonzero():
    product = _product(_tenant('repeat'), 'T')
    _trigger(product)
    _repair(product, apply=True)
    assert _repair(product, apply=True)['status'] == 'skipped_nonzero'
    assert _cost(product) == 40


def test_later_positive_requires_review():
    product = _product(_tenant('later'), 'T')
    trigger = _trigger(product)
    _movement(product, 'IN', after=20)
    result = _repair(product, apply=True)
    assert result['status'] == 'review_later_positive'
    assert result['source'] == 'trigger' and result['source_movement_id'] == trigger.pk
    assert result['after'] == result['before']
    assert _cost(product) == 0


def test_later_nonzero_before_requires_review():
    product = _product(_tenant('later-before'), 'T')
    _trigger(product)
    _movement(product, 'IN', before=25, after=0)
    assert _repair(product, apply=True)['status'] == 'review_later_positive'
    assert _cost(product) == 0


@pytest.mark.parametrize('cost,status', [(55, 'review_layer_conflict'), (40, 'repaired')])
def test_provisional_layer_cost_conflict(cost, status):
    product = _product(_tenant(f'layer{cost}'), 'T')
    trigger = _trigger(product)
    _layer(product, trigger, cost)
    result = _repair(product, apply=True)
    assert result['status'] == status
    if status == 'review_layer_conflict':
        assert result['source'] == 'trigger' and result['source_movement_id'] == trigger.pk
        assert result['after'] == result['before']
    assert _cost(product) == (40 if cost == 40 else 0)


def test_service_is_skipped():
    product = _product(_tenant('service'), 'T', is_service=True)
    _trigger(product)
    assert _repair(product, apply=True)['status'] == 'skipped_service'
    assert _cost(product) == 0


def test_exhausted_real_layer_is_skipped():
    product = _product(_tenant('real'), 'T')
    _layer(product, _trigger(product), 40, provisional=False)
    assert _repair(product, apply=True)['status'] == 'skipped_real_layer'
    assert _cost(product) == 0


def test_no_positive_history_is_skipped():
    product = _product(_tenant('history'), 'T')
    _movement(product, 'OUT')
    assert _repair(product, apply=True)['status'] == 'skipped_no_history'
    assert _cost(product) == 0


@pytest.mark.parametrize('following,cost', [(True, 70), (False, 10)])
def test_last_positive_after_is_restored(following, cost):
    product = _product(_tenant(f'last{cost}'), 'T')
    source = _movement(product, 'IN', after=cost)
    if following:
        _movement(product, 'OUT')
    result = _repair(product, apply=True)
    assert (result['status'], result['after'], result['source'], result['source_movement_id']) == (
        'repaired', cost, 'last_positive_after', source.pk)
    assert _cost(product) == cost


def test_nonzero_later_snapshot_is_ambiguous():
    product = _product(_tenant('ambiguous'), 'T')
    source = _movement(product, 'IN', after=70)
    _movement(product, 'IN', before=5)
    result = _repair(product, apply=True)
    assert result['status'] == 'review_ambiguous'
    assert result['source'] == 'last_positive_after' and result['source_movement_id'] == source.pk
    assert result['after'] == result['before']
    assert _cost(product) == 0


def test_zero_cost_listing_uses_cogs_when_present():
    product = _product(_tenant('cogs'), 'T')
    a = _movement(product, 'OUT', total_cost=0, cogs_cost=None)
    _movement(product, 'OUT', total_cost=0, cogs_cost=80)
    c = _movement(product, 'OUT', total_cost=80, cogs_cost=0)
    _movement(product, 'IN', total_cost=0, cogs_cost=None)
    assert _repair(product)['zero_cost_movement_ids'] == [a.pk, c.pk]


@pytest.mark.parametrize('kind', ['service', 'nonzero'])
def test_early_skips_do_not_list_zero_cost_movements(kind):
    product = _product(_tenant(f'listing-{kind}'), 'T', is_service=kind == 'service')
    _movement(product, 'OUT', total_cost=0)
    if kind == 'nonzero':
        Product.objects.filter(pk=product.pk).update(avg_cost=10)
    result = _repair(product)
    assert result['status'] == f'skipped_{kind}'
    assert result['zero_cost_movement_ids'] == []


def test_last_trigger_wins():
    product = _product(_tenant('last-trigger'), 'T')
    _trigger(product)
    last = _movement(product, 'OUT', before=60)
    result = _repair(product, apply=True)
    assert (result['status'], result['after'], result['source_movement_id']) == (
        'repaired', 60, last.pk)
    assert _cost(product) == 60


def test_last_positive_wins():
    product = _product(_tenant('last-positive'), 'T')
    _movement(product, 'IN', after=30)
    last = _movement(product, 'IN', before=30, after=50)
    _movement(product, 'OUT')
    result = _repair(product, apply=True)
    assert (result['status'], result['after'], result['source'], result['source_movement_id']) == (
        'repaired', 50, 'last_positive_after', last.pk)
    assert _cost(product) == 50


def test_trigger_order_uses_created_at_before_id():
    product = _product(_tenant('trigger-order'), 'T')
    later = _movement(product, 'OUT', before=90)
    earlier = _movement(product, 'OUT', before=40)
    StockMovement.objects.filter(pk=later.pk).update(
        created_at=earlier.created_at + datetime.timedelta(days=1))
    result = _repair(product, apply=True)
    assert (result['status'], result['after'], result['source_movement_id']) == (
        'repaired', 90, later.pk)
    assert _cost(product) == 90


@pytest.mark.parametrize('layer_position', ['zero_cost', 'before_trigger'])
def test_nonconflicting_provisional_layers_are_ignored(layer_position):
    product = _product(_tenant(f'scope-{layer_position}'), 'T')
    earlier = _movement(product, 'IN', after=40)
    trigger = _movement(product, 'OUT', before=40)
    _layer(product, trigger if layer_position == 'zero_cost' else earlier,
           0 if layer_position == 'zero_cost' else 55)
    assert _repair(product, apply=True)['status'] == 'repaired'
    assert _cost(product) == 40


def test_repair_survives_sync_and_recompute():
    product = _product(_tenant('survive'), 'T')
    _trigger(product)
    _repair(product, apply=True)
    assert sync_avg_cost_from_layers(product, apply=True)['status'] == 'skipped_no_layers'
    _recompute_product_stock(product)
    assert _cost(product) == 40


def test_command_preview_apply_tenant_and_unknown():
    tenant = _tenant('command')
    product = _product(tenant, 'T')
    trigger = _trigger(product)
    other = _product(_tenant('other'), 'OTHER')
    _trigger(other)
    out = StringIO()
    call_command('repair_zeroed_avg_cost', tenant=tenant.pk, stdout=out)
    assert 'سيُحدَّث' in out.getvalue()
    assert f'حركة #{trigger.pk} OUT' in out.getvalue()
    assert '[معاينة فقط' in out.getvalue()
    assert _cost(product) == 0
    call_command('repair_zeroed_avg_cost', tenant=tenant.pk, apply=True, stdout=StringIO())
    assert _cost(product) == 40
    assert _cost(other) == 0
    with pytest.raises(CommandError):
        call_command('repair_zeroed_avg_cost', tenant=999999, stdout=StringIO())


def test_command_names_skipped_product_before_zero_cost_movement():
    tenant = _tenant('command-skipped')
    product = _product(tenant, 'SKIPPED')
    _layer(product, _trigger(product), 40, provisional=False)
    movement = _movement(product, 'OUT', total_cost=0, cogs_cost=None)
    out = StringIO()
    call_command('repair_zeroed_avg_cost', tenant=tenant.pk, stdout=out)
    output = out.getvalue()
    assert output.index('SKIPPED (skipped_real_layer)') < output.index(f'حركة #{movement.pk}')


def test_command_review_names_source_and_does_not_write():
    tenant = _tenant('command-review')
    product = _product(tenant, 'REVIEW')
    trigger = _trigger(product)
    _movement(product, 'IN', after=20)
    out = StringIO()
    call_command('repair_zeroed_avg_cost', tenant=tenant.pk, apply=True, stdout=out)
    assert (
        'REVIEW (مراجعة يدوية — review_later_positive): يبقى 0.0000'
        f' · المصدر: trigger #{trigger.pk}'
    ) in out.getvalue()
    assert _cost(product) == 0


def test_command_excludes_owner_product():
    tenant = _tenant('command-exclude')
    a = _product(tenant, 'EXCLUDED')
    b = _product(tenant, 'REPAIRED')
    _trigger(a)
    _trigger(b)
    out = StringIO()
    call_command('repair_zeroed_avg_cost', '--tenant', str(tenant.pk), '--apply',
                 '--exclude', str(a.pk), stdout=out)
    assert _cost(a) == 0
    assert _cost(b) == 40
    assert f'{a.sku} (مستثنى بأمر المالك): يبقى 0.0000' in out.getvalue()
    assert 'excluded=1' in out.getvalue()


def test_command_rejects_noninteger_exclusion():
    with pytest.raises(CommandError, match='عنصر غير صالح.*abc'):
        call_command('repair_zeroed_avg_cost', '--exclude', '12,abc', stdout=StringIO())


def _set_cost(product, cost, **kwargs):
    return set_owner_avg_cost(product, cost, **kwargs)


def test_set_owner_cost_preview_and_apply():
    product = _product(_tenant('set-owner'), 'T')
    result = _set_cost(product, Decimal('5'))
    assert (result['status'], result['before'], result['after']) == (
        'owner_set', Decimal('0.0000'), Decimal('5.0000'))
    assert _cost(product) == 0
    _set_cost(product, Decimal('5'), apply=True)
    assert _cost(product) == 5


def test_set_owner_cost_skips_nonzero():
    product = _product(_tenant('set-nonzero'), 'T')
    Product.objects.filter(pk=product.pk).update(avg_cost=10)
    result = _set_cost(product, Decimal('5'), apply=True)
    assert (result['status'], result['after']) == ('skipped_nonzero', Decimal('10.0000'))
    assert _cost(product) == 10


def test_set_owner_cost_rejects_nonpositive():
    product = _product(_tenant('set-zero'), 'T')
    with pytest.raises(ValueError):
        _set_cost(product, 0, apply=True)
    assert _cost(product) == 0


def test_set_owner_cost_overrides_real_layer():
    product = _product(_tenant('set-real'), 'T')
    _layer(product, _trigger(product), 40, provisional=False)
    assert _repair(product, apply=True)['status'] == 'skipped_real_layer'
    assert _set_cost(product, Decimal('5'), apply=True)['status'] == 'owner_set'
    assert _cost(product) == 5


def test_set_owner_cost_survives_sync_and_recompute():
    product = _product(_tenant('set-survive'), 'T')
    _trigger(product)
    _set_cost(product, Decimal('5'), apply=True)
    assert sync_avg_cost_from_layers(product, apply=True)['status'] == 'skipped_no_layers'
    _recompute_product_stock(product)
    assert _cost(product) == 5


def test_command_set_owner_cost_apply_and_preview():
    tenant = _tenant('command-set')
    a = _product(tenant, 'REPAIRED')
    b = _product(tenant, 'OWNERSET')
    _trigger(a)
    _trigger(b)
    out = StringIO()
    call_command('repair_zeroed_avg_cost', '--tenant', str(tenant.pk), '--apply',
                 '--set', f'{b.pk}=5', stdout=out)
    assert _cost(a) == 40
    assert _cost(b) == 5
    assert f'{b.sku} (كلفة المالك): 0.0000 → 5.0000' in out.getvalue()
    assert 'excluded=0 · owner_set=1 · repaired=1' in out.getvalue()
    assert 'تمّ إصلاح 1 منتج وضبط 1 بكلفة المالك.' in out.getvalue().splitlines()
    fresh = _tenant('command-set-preview')
    c = _product(fresh, 'PREVIEW')
    _trigger(c)
    out = StringIO()
    call_command('repair_zeroed_avg_cost', '--tenant', str(fresh.pk),
                 '--set', f'{c.pk}=5', stdout=out)
    assert _cost(c) == 0
    assert f'{c.sku} (كلفة المالك): 0.0000 → 5.0000' in out.getvalue()
    assert f'{c.sku} (سيُحدَّث)' not in out.getvalue()
    assert '· repaired=0 ·' in out.getvalue()


@pytest.mark.parametrize('args,message', [
    (['--set', '12'], 'عنصر غير صالح.*12'),
    (['--set', 'abc=5'], 'عنصر غير صالح.*abc=5'),
    (['--set', '12=x'], 'عنصر غير صالح.*12=x'),
    (['--set', '12=0'], 'كلفة.*12=0'),
    (['--set', '12=0.00004'], 'كلفة.*12=0.00004'),
    (['--set', '12=5,12=6'], 'مكرّر.*12'),
    (['--exclude', '12', '--set', '12=5'], 'مستثنى.*12'),
])
def test_command_rejects_bad_set(args, message):
    with pytest.raises(CommandError, match=message):
        call_command('repair_zeroed_avg_cost', *args, stdout=StringIO())


def test_command_rejects_unknown_set_product():
    tenant = _tenant('command-set-unknown')
    with pytest.raises(CommandError, match='999999'):
        call_command('repair_zeroed_avg_cost', '--tenant', str(tenant.pk),
                     '--set', '999999=5', stdout=StringIO())


def test_command_rejects_set_product_of_other_tenant():
    tenant = _tenant('command-set-scope')
    other = _product(_tenant('command-set-scope-other'), 'FOREIGN')
    with pytest.raises(CommandError, match=str(other.pk)):
        call_command('repair_zeroed_avg_cost', '--tenant', str(tenant.pk),
                     '--set', f'{other.pk}=5', stdout=StringIO())
    assert _cost(other) == 0
