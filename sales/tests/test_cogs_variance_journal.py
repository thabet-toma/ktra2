from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest
from django.core.exceptions import ValidationError

from accounting.models import Account, JournalLine
from inventory import fifo
from inventory.models import Product, StockMovement
from inventory.services import _fixed_cogs_reversal, record_stock_movement
from sales.models import SalesInvoice, SalesSettings
from sales.services import deliver_invoice_lines, post_sales_invoice, sales_cogs_map
from sales.services.calc import _build_cogs_journal_line_dicts
from sales.tests.test_sale_return_restores_its_layers import env, _sell, _return, D

pytestmark = pytest.mark.django_db


def setup_case(env, qty=10):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='VAR', name_ar='variance')
    record_stock_movement(product=product, movement_type='IN', quantity=Decimal('8'),
                          unit_cost=Decimal('10'), movement_date=D, tenant=tenant)
    record_stock_movement(product=product, movement_type='IN', quantity=Decimal('4'),
                          unit_cost=Decimal('16'), movement_date=D, tenant=tenant)
    sale = _sell(tenant, cur, customer, product, qty, 'VAR-S')
    origin = StockMovement.objects.get(reference_type='SALE', reference_id=sale.id, product=product)
    ss = SalesSettings.objects.get(tenant=tenant)
    variance = Account.objects.create(
        tenant=tenant, code='5100-V', name='variance', account_type='Expense', is_active=True)
    ss.cost_variance_account = variance
    ss.save(update_fields=['cost_variance_account'])
    return tenant, cur, customer, product, sale, origin, ss, variance


@pytest.mark.parametrize('cost, debit, credit', [('110', '2', '0'), ('160', '0', '48')])
def test_builder_variance_and_equal_parity(env, cost, debit, credit):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env)
    lines = list(sale.lines.all())
    args = (sale, lines, {product.id: product})
    inv = {product.id: Decimal('112')}
    baseline = _build_cogs_journal_line_dicts(*args, costs_by_product=inv)
    assert _build_cogs_journal_line_dicts(*args, costs_by_product=inv, cogs_by_product=inv) == baseline
    rows = _build_cogs_journal_line_dicts(*args, costs_by_product=inv, cogs_by_product={product.id: Decimal(cost)})
    assert [(r['account'], r['debit'], r['credit']) for r in rows] == [
        (ss.default_cogs_account_id, Decimal(cost), 0),
        (ss.default_inventory_account_id, 0, Decimal('112')),
        (variance.id, Decimal(debit), Decimal(credit)),
    ]
    assert sum(r['debit'] for r in rows) == sum(r['credit'] for r in rows)


def test_builder_requires_variance_account(env):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env)
    ss.cost_variance_account = None
    ss.save(update_fields=['cost_variance_account'])
    with pytest.raises(ValidationError, match='حساب فروقات تكلفة المبيعات'):
        _build_cogs_journal_line_dicts(
            sale, list(sale.lines.all()), {product.id: product},
            costs_by_product={product.id: Decimal('112')}, cogs_by_product={product.id: Decimal('110')})


@pytest.mark.parametrize('method,cost,reversal,variance_debit,variance_credit', [
    ('standard', '110', '44', '0', '8'),
    ('last_purchase', '160', '64', '12', '0'),
    ('fifo', None, None, '0', '0'),
    ('fifo', '112', None, '0', '0'),
    ('standard', None, None, '0', '0'),
    (None, None, None, '0', '0'),
])
def test_return_snapshots_and_journal(env, method, cost, reversal, variance_debit, variance_credit):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env)
    origin.cogs_method = method
    origin.cogs_cost = Decimal(cost) if cost is not None else None
    origin.save(update_fields=['cogs_method', 'cogs_cost'])
    ret = _return(tenant, cur, customer, product, 4, 'VAR-R', sale)
    mv = StockMovement.objects.get(movement_type='RETURN_IN', reference_id=ret.id, product=product)
    assert mv.total_cost == Decimal('52')
    assert mv.cogs_cost == (Decimal(reversal) if reversal else None)
    assert mv.cogs_method == (method if reversal else None)
    entries = {
        r.account_id: (r.debit, r.credit) for r in JournalLine.objects.filter(
            journal_id=ret.journal_id,
            account_id__in=[ss.default_cogs_account_id, ss.default_inventory_account_id, variance.id])
    }
    assert entries[ss.default_inventory_account_id] == (Decimal('52'), 0)
    assert entries[ss.default_cogs_account_id] == (0, Decimal(reversal or '52'))
    if reversal:
        assert entries[variance.id] == (Decimal(variance_debit), Decimal(variance_credit))
    else:
        assert variance.id not in entries
    all_rows = JournalLine.objects.filter(journal_id=ret.journal_id)
    assert sum(r.debit for r in all_rows) == sum(r.credit for r in all_rows)


def test_telescoping_returns(env):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env, 3)
    origin.cogs_method, origin.cogs_cost = 'standard', Decimal('100')
    origin.save(update_fields=['cogs_method', 'cogs_cost'])
    costs = []
    for i in range(3):
        ret = _return(tenant, cur, customer, product, 1, f'VAR-R{i}', sale)
        costs.append(StockMovement.objects.get(
            movement_type='RETURN_IN', reference_id=ret.id, product=product).cogs_cost)
    assert costs == [Decimal('33.33'), Decimal('33.34'), Decimal('33.33')]
    assert sum(costs) == Decimal('100')


def test_sales_cogs_map_prefers_snapshot(env):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env)
    key = (sale.id, product.id)
    assert sales_cogs_map(tenant_id=tenant.pk, invoice_ids=[sale.id])[key]['cost'] == Decimal('112')
    origin.cogs_cost = Decimal('0')
    origin.save(update_fields=['cogs_cost'])
    assert sales_cogs_map(tenant_id=tenant.pk, invoice_ids=[sale.id])[key]['cost'] == Decimal('0')


def test_builder_nets_opposite_variances(env):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env)
    other = Product.objects.create(tenant=tenant, sku='VAR-2', name_ar='other')
    lines = [sale.lines.first(), SimpleNamespace(product_id=other.id, quantity=1, id=-1)]
    rows = _build_cogs_journal_line_dicts(
        sale, lines, {product.id: product, other.id: other},
        costs_by_product={product.id: Decimal('112'), other.id: Decimal('50')},
        cogs_by_product={product.id: Decimal('110'), other.id: Decimal('52')},
    )
    assert [(r['account'], r['debit'], r['credit']) for r in rows] == [
        (ss.default_cogs_account_id, Decimal('162'), 0),
        (ss.default_inventory_account_id, 0, Decimal('162')),
    ]
    assert sum(r['debit'] for r in rows) == sum(r['credit'] for r in rows)


def test_partial_delivery_passes_effective_cogs(env):
    tenant, cur, customer, product = env
    invoice = SalesInvoice.objects.create(
        tenant=tenant, invoice_number='VAR-DEL', customer=customer, currency=cur,
        invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    line = invoice.lines.create(tenant=tenant, product=product, quantity=3, unit_price=200)
    post_sales_invoice(invoice)
    invoice.refresh_from_db()
    ss = SalesSettings.objects.get(tenant=tenant)
    variance = Account.objects.create(
        tenant=tenant, code='5100-V', name='variance', account_type='Expense', is_active=True)
    ss.cost_variance_account = variance
    ss.save(update_fields=['cost_variance_account'])
    with patch('sales.services.flow._build_cogs_journal_line_dicts',
               wraps=_build_cogs_journal_line_dicts) as builder, patch(
        'inventory.models.StockMovement.effective_cogs', new_callable=PropertyMock,
        return_value=Decimal('18'),
    ):
        delivery = deliver_invoice_lines(invoice, lines=[{'line_id': line.id, 'quantity': 2}])
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert movement.total_cost == Decimal('20')
    assert builder.call_args.kwargs['cogs_by_product'] == {product.id: Decimal('18')}
    rows = JournalLine.objects.filter(journal=delivery.journal)
    ss = SalesSettings.objects.get(tenant=tenant)
    assert delivery.journal.reference_type == 'SALES_DELIVERY_COGS'
    assert {(r.account_id, r.debit, r.credit) for r in rows} == {
        (ss.default_cogs_account_id, Decimal('18'), Decimal('0')),
        (ss.default_inventory_account_id, Decimal('0'), Decimal('20')),
        (variance.id, Decimal('2'), Decimal('0')),
    }
    assert sum(r.debit for r in rows) == sum(r.credit for r in rows)


def test_return_mixed_origins(env):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='MIX', name_ar='mixed')
    record_stock_movement(product=product, movement_type='IN', quantity=Decimal('5'),
                          unit_cost=Decimal('10'), movement_date=D, tenant=tenant)
    record_stock_movement(product=product, movement_type='IN', quantity=Decimal('2'),
                          unit_cost=Decimal('16'), movement_date=D, tenant=tenant)
    standard_sale = _sell(tenant, cur, customer, product, 5, 'MIX-S1')
    fifo_sale = _sell(tenant, cur, customer, product, 2, 'MIX-S2')
    standard = StockMovement.objects.get(reference_type='SALE', reference_id=standard_sale.id)
    fifo_origin = StockMovement.objects.get(reference_type='SALE', reference_id=fifo_sale.id)
    standard.cogs_method, standard.cogs_cost = 'standard', Decimal('55')
    standard.save(update_fields=['cogs_method', 'cogs_cost'])
    fifo_origin.cogs_method, fifo_origin.cogs_cost = 'fifo', Decimal('32')
    fifo_origin.save(update_fields=['cogs_method', 'cogs_cost'])
    movement = record_stock_movement(
        product=product, movement_type='RETURN_IN', quantity=Decimal('4'),
        movement_date=D, tenant=tenant, restores_movement=[standard, fifo_origin])
    assert movement.total_cost == Decimal('52')
    assert movement.cogs_cost == Decimal('54')
    assert movement.cogs_method is None


def test_return_surplus_on_fixed_origin(env):
    tenant, cur, customer, product, sale, origin, ss, variance = setup_case(env, 5)
    origin.cogs_method, origin.cogs_cost = 'standard', Decimal('55')
    origin.save(update_fields=['cogs_method', 'cogs_cost'])
    ret = _return(tenant, cur, customer, product, 7, 'VAR-SURPLUS', sale)
    movement = StockMovement.objects.get(movement_type='RETURN_IN', reference_id=ret.id, product=product)
    assert movement.total_cost == Decimal('70')
    assert movement.cogs_cost == Decimal('75')


def test_fixed_reversal_rounds_restored_value_like_total(env):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='TIE', name_ar='tie')
    record_stock_movement(product=product, movement_type='IN', quantity=Decimal('2'),
                          unit_cost=Decimal('0.8233'), movement_date=D, tenant=tenant)
    sale = _sell(tenant, cur, customer, product, 2, 'TIE-S')
    origin = StockMovement.objects.get(reference_type='SALE', reference_id=sale.id)
    origin.cogs_method, origin.cogs_cost = 'standard', Decimal('2')
    origin.save(update_fields=['cogs_method', 'cogs_cost'])
    restored = fifo.restore_partial(movements=[origin], quantity=Decimal('1.5'))
    assert restored.cost == Decimal('1.2350')
    assert _fixed_cogs_reversal(restored, [origin], Decimal('1.24')) == (Decimal('1.50'), 'standard')
