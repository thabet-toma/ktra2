from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from accounting.models import Account, JournalLine
from inventory.models import Product, StockLayer, StockMovement
from inventory.services import product_display_name, record_stock_movement
from inventory.tests.test_unpost_provisional_reconciliation import _receive
from logistics.tests.test_accrual_adjust import D as LD, _AccrualAdjustBase
from sales.models import SalesInvoice, SalesSettings
from sales.services import post_sales_invoice
from sales.tests.test_sale_return_restores_its_layers import D, env, _return, _sell
from sales.tests.test_sale_return_unpost_layers import client_for

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('method,price,cost,debit,credit', [
    ('fifo', None, '112', '0', '0'),
    ('standard', '11', '110', '2', '0'),
    ('last_purchase', None, '160', '0', '48'),
    ('standard', '0', '0', '112', '0'),
])
def test_sale_snapshot_and_journal(env, method, price, cost, debit, credit):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='SNAP', name_ar='snapshot', standard_cost=price)
    _receive(product, '8', '10', 1001, date='2026-06-10')
    _receive(product, '4', '16', 1002, date='2026-06-12')
    ss = SalesSettings.objects.get(tenant=tenant)
    variance = Account.objects.create(tenant=tenant, code='5100-SNAP', name='variance', account_type='Expense')
    if method != 'fifo':
        ss.cogs_cost_method = method
    ss.cost_variance_account = variance
    ss.save(update_fields=['cogs_cost_method', 'cost_variance_account'])
    sale = _sell(tenant, cur, customer, product, 10, 'SNAP-S')
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=sale.id, product=product)
    assert movement.total_cost == Decimal('112')
    assert movement.cogs_cost == Decimal(cost)
    assert movement.cogs_method == method
    rows = {r.account_id: (r.debit, r.credit) for r in JournalLine.objects.filter(journal_id=sale.journal_id)}
    if Decimal(cost):
        assert rows[ss.default_cogs_account_id] == (Decimal(cost), 0)
    else:
        assert ss.default_cogs_account_id not in rows
    assert rows[ss.default_inventory_account_id] == (0, Decimal('112'))
    if Decimal(debit) or Decimal(credit):
        assert rows[variance.id] == (Decimal(debit), Decimal(credit))
    else:
        assert variance.id not in rows
    assert sum(v[0] for v in rows.values()) == sum(v[1] for v in rows.values())


def setup_purchase_case(env, method='last_purchase', standard_cost=None):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='SNAP', name_ar='snapshot', standard_cost=standard_cost)
    _receive(product, '8', '10', 1001, date='2026-06-10')
    _receive(product, '4', '16', 1002, date='2026-06-12')
    ss = SalesSettings.objects.get(tenant=tenant)
    ss.cogs_cost_method = method
    ss.cost_variance_account = Account.objects.create(
        tenant=tenant, code='5100-SNAP', name='variance', account_type='Expense')
    ss.save(update_fields=['cogs_cost_method', 'cost_variance_account'])
    return tenant, cur, customer, product, ss


def test_future_purchase_is_not_price(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env)
    StockLayer.objects.filter(product=product, unit_cost=16).update(layer_date='2026-06-16')
    sale = _sell(tenant, cur, customer, product, 10, 'FUTURE')
    mv = StockMovement.objects.get(reference_type='SALE', reference_id=sale.id, product=product)
    assert mv.cogs_cost == Decimal('100')
    assert JournalLine.objects.filter(journal_id=sale.journal_id, account=ss.cost_variance_account, debit=12).exists()


def test_last_purchase_ignores_other_layers(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env)
    for kind, ref in [('ADJUST_IN', 'STOCKTAKE'), ('RETURN_IN', 'SALE')]:
        record_stock_movement(product=product, movement_type=kind, quantity=Decimal('1'),
                              unit_cost=Decimal('99'), reference_type=ref,
                              movement_date=D, tenant=tenant)
    source = StockMovement.objects.filter(product=product, reference_type='PURCHASE_INVOICE').first()
    StockLayer.objects.create(tenant=tenant, product=product, layer_date=D, unit_cost=99,
                              original_qty=0, remaining_qty=0, is_provisional=True, source_movement=source)
    sale = _sell(tenant, cur, customer, product, 10, 'OTHER')
    assert StockMovement.objects.get(reference_type='SALE', reference_id=sale.id, movement_type='OUT').cogs_cost == Decimal('160')


def test_last_purchase_reads_current_layer_cost(env):
    """Update the layer in place, as landed revaluation does."""
    tenant, cur, customer, product, ss = setup_purchase_case(env)
    StockLayer.objects.filter(product=product, unit_cost=16).update(unit_cost=18)
    sale = _sell(tenant, cur, customer, product, 10, 'REVALUE')
    assert StockMovement.objects.get(reference_type='SALE', reference_id=sale.id).cogs_cost == Decimal('180')


def test_sale_return_uses_real_snapshot(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard', Decimal('11'))
    sale = _sell(tenant, cur, customer, product, 10, 'RETURN-S')
    ret = _return(tenant, cur, customer, product, 4, 'RETURN-R', sale)
    rows = {r.account_id: (r.debit, r.credit) for r in JournalLine.objects.filter(journal_id=ret.journal_id)}
    assert rows[ss.default_inventory_account_id] == (Decimal('52'), 0)
    assert rows[ss.default_cogs_account_id] == (0, Decimal('44'))
    assert rows[ss.cost_variance_account_id] == (0, Decimal('8'))


def test_missing_standard_warns_post_view(env):
    from sales.models import SalesInvoice
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='WARN', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    invoice.lines.create(tenant=tenant, product=product, quantity=10, unit_price=200)
    response = client_for(tenant).post(f'/api/sales/invoices/{invoice.pk}/post/', {}, format='json')
    assert response.status_code == 200, response.content
    invoice.refresh_from_db()
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert (movement.cogs_cost, movement.cogs_method) == (Decimal('112'), 'fifo')
    assert not JournalLine.objects.filter(journal_id=invoice.journal_id, account=ss.cost_variance_account).exists()
    assert response.data['cogs_warnings'] == [{'product_id': product.id, 'product_name': product_display_name(product),
        'method': 'standard', 'reason': 'no_standard_cost'}]


def test_missing_purchase_warns(env):
    from sales.models import SalesInvoice
    from sales.services import post_sales_invoice
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='NO-PURCHASE', name_ar='missing')
    record_stock_movement(product=product, movement_type='ADJUST_IN', quantity=10,
        unit_cost=10, movement_date=D, tenant=tenant)
    ss = SalesSettings.objects.get(tenant=tenant)
    ss.cogs_cost_method = 'last_purchase'
    ss.save(update_fields=['cogs_cost_method'])
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='NO-P', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    invoice.lines.create(tenant=tenant, product=product, quantity=10, unit_price=200)
    post_sales_invoice(invoice)
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert (movement.cogs_cost, movement.cogs_method) == (movement.total_cost, 'fifo')
    assert invoice._cogs_warnings[0]['reason'] == 'no_prior_purchase'


def test_repost_uses_current_method(env):
    from sales.tests.test_sale_return_unpost_layers import unpost, repost
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard', Decimal('11'))
    invoice = _sell(tenant, cur, customer, product, 10, 'REPOST')
    old_id = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id).id
    response = unpost(tenant, invoice)
    assert response.status_code == 200, response.content
    ss.cogs_cost_method = 'last_purchase'
    ss.save(update_fields=['cogs_cost_method'])
    response = repost(tenant, invoice)
    assert response.status_code == 200, response.content
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert movement.id != old_id
    assert (movement.cogs_cost, movement.cogs_method) == (Decimal('160'), 'last_purchase')


def test_other_outbound_movements_have_no_snapshot(env):
    from sales.services import create_standalone_delivery_note
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard', Decimal('11'))
    adjustment = record_stock_movement(product=product, movement_type='ADJUST_OUT', quantity=1,
        movement_date=D, tenant=tenant)
    delivery = create_standalone_delivery_note(tenant, partner=customer, delivery_date=D,
        lines=[{'product_id': product.id, 'quantity': 1}])
    movement = StockMovement.objects.get(reference_type='DELIVERY_NOTE', reference_id=delivery.id)
    assert adjustment.cogs_cost is None and movement.cogs_cost is None


def test_linked_delivery_snapshot(env):
    from sales.models import SalesInvoice
    from sales.services import post_sales_invoice, deliver_invoice_lines
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard', Decimal('11'))
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='LINK', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    line = invoice.lines.create(tenant=tenant, product=product, quantity=10, unit_price=200)
    post_sales_invoice(invoice)
    invoice.refresh_from_db()
    delivery = deliver_invoice_lines(invoice, lines=[{'line_id': line.id, 'quantity': 10}])
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert (movement.cogs_cost, movement.cogs_method) == (Decimal('110'), 'standard')
    assert delivery.journal.reference_type == 'SALES_DELIVERY_COGS'
    assert JournalLine.objects.filter(journal=delivery.journal, account=ss.cost_variance_account, debit=2).exists()


@pytest.mark.parametrize('method,expected', [('fifo', Decimal('120')), ('standard', Decimal('110'))])
def test_reconcile_syncs_only_fifo(env, method, expected):
    from unittest.mock import patch
    from inventory.services import reconcile_product_cogs
    tenant, cur, customer, product, ss = setup_purchase_case(env, method, Decimal('11'))
    invoice = _sell(tenant, cur, customer, product, 10, 'RECON')
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    with patch('inventory.services.product_cost_breakdown', return_value={'average_cost': '12', 'invoice_count': 1}):
        reconcile_product_cogs(tenant_id=tenant.pk, product_id=product.id, apply=True)
    movement.refresh_from_db()
    assert movement.total_cost == Decimal('120')
    assert movement.cogs_cost == expected


def test_method_unit_cost_is_tenant_scoped_and_breaks_date_ties(env):
    from inventory.cogs_method import method_unit_cost
    from django.contrib.auth.models import User
    from tenants.services import create_company
    tenant, cur, customer, product, ss = setup_purchase_case(env)
    _receive(product, '1', '17', 1003, date='2026-06-12')
    other_tenant = create_company('Other', User.objects.create_user(username='other'))
    source = StockMovement.objects.filter(product=product, reference_type='PURCHASE_INVOICE').first()
    StockLayer.objects.create(tenant=other_tenant, product=product, source_movement=source,
                              layer_date='2026-06-14', unit_cost=99, original_qty=1, remaining_qty=1,
                              is_provisional=False)
    assert method_unit_cost(product=product, method='last_purchase', as_of=D) == Decimal('17')


def test_purchase_on_sale_date_is_included(env):
    from inventory.cogs_method import method_unit_cost
    tenant, cur, customer, product, ss = setup_purchase_case(env)
    _receive(product, '1', '19', 1005, date='2026-06-15')
    assert method_unit_cost(product=product, method='last_purchase', as_of=D) == Decimal('19')


def test_warnings_deduplicate_product(env):
    from sales.models import SalesInvoice
    from sales.services import post_sales_invoice
    tenant, cur, customer, product = env
    ss = SalesSettings.objects.get(tenant=tenant)
    ss.cogs_cost_method = 'last_purchase'
    ss.save(update_fields=['cogs_cost_method'])
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='DEDUP', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    for _ in range(2):
        invoice.lines.create(tenant=tenant, product=product, quantity=1, unit_price=200)
    post_sales_invoice(invoice)
    assert invoice._cogs_warnings == [{'product_id': product.id, 'product_name': product_display_name(product),
        'method': 'last_purchase', 'reason': 'no_prior_purchase'}]


def test_auto_post_create_returns_warning(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    ss.auto_post_invoices = True
    ss.save(update_fields=['auto_post_invoices'])
    response = client_for(tenant).post('/api/sales/invoices/', {
        'customer': customer.id, 'currency': cur.pk, 'invoice_date': str(D),
        'invoice_type': 'credit', 'stock_on_post': True,
        'lines': [{'product': product.id, 'quantity': '1', 'unit_price': '200'}],
    }, format='json')
    assert response.status_code == 201, response.data
    assert response.data['cogs_warnings'][0]['reason'] == 'no_standard_cost'


def test_deliver_returns_warning(env):
    from sales.models import SalesInvoice
    from sales.services import post_sales_invoice
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='WARN-DEL', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    line = invoice.lines.create(tenant=tenant, product=product, quantity=1, unit_price=200)
    post_sales_invoice(invoice)
    response = client_for(tenant).post(f'/api/sales/invoices/{invoice.pk}/deliver/',
        {'lines': [{'line_id': line.id, 'quantity': 1}]}, format='json')
    assert response.status_code == 200, response.data
    assert response.data['cogs_warnings'][0]['reason'] == 'no_standard_cost'


def test_existing_delivery_order_returns_warning(env):
    from sales.models import SalesInvoice
    from sales.services import post_sales_invoice
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='WARN-ORDER', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    invoice.lines.create(tenant=tenant, product=product, quantity=1, unit_price=200)
    post_sales_invoice(invoice)
    client = client_for(tenant)
    created = client.post(f'/api/sales/invoices/{invoice.pk}/delivery-order/', {}, format='json')
    assert created.status_code == 201, created.data
    response = client.post(f"/api/sales/delivery-orders/{created.data['id']}/deliver/", {}, format='json')
    assert response.status_code == 200, response.data
    assert response.data['cogs_warnings'][0]['reason'] == 'no_standard_cost'


def test_collect_post_returns_warning(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    cash = Account.objects.create(tenant=tenant, code='1110-SNAP', name='cash', account_type='Asset', is_active=True)
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='WARN-COL', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    invoice.lines.create(tenant=tenant, product=product, quantity=1, unit_price=200)
    response = client_for(tenant).post(f'/api/sales/invoices/{invoice.pk}/collect/', {
        'post_invoice': True, 'cash': '200', 'cash_account_id': cash.id, 'payment_date': str(D),
    }, format='json')
    assert response.status_code == 200, response.data
    assert response.data['cogs_warnings'] == [{
        'product_id': product.id,
        'product_name': product_display_name(product),
        'method': 'standard',
        'reason': 'no_standard_cost',
    }]


def test_payment_voucher_post_returns_warning(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='WARN-PV', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    invoice.lines.create(tenant=tenant, product=product, quantity=1, unit_price=200)
    response = client_for(tenant).post(f'/api/sales/invoices/{invoice.pk}/payment-voucher/', {
        'post': True,
    }, format='json')
    assert response.status_code == 200, response.data
    assert response.data['cogs_warnings'] == [{
        'product_id': product.id,
        'product_name': product_display_name(product),
        'method': 'standard',
        'reason': 'no_standard_cost',
    }]


def test_avco_is_fifo_without_warning(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'avco', Decimal('11'))
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='AVCO', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    invoice.lines.create(tenant=tenant, product=product, quantity=10, unit_price=200)
    post_sales_invoice(invoice)
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert movement.cogs_method == 'fifo'
    assert movement.cogs_cost == movement.total_cost
    assert not getattr(invoice, '_cogs_warnings', None)


def test_delivery_order_create_returns_warning(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard')
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='WARN-DN', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    line = invoice.lines.create(tenant=tenant, product=product, quantity=1, unit_price=200)
    post_sales_invoice(invoice)
    response = client_for(tenant).post('/api/sales/delivery-orders/', {
        'invoice': invoice.id,
        'delivery_date': str(D),
        'lines': [{'line_id': line.id, 'quantity': 1}],
    }, format='json')
    assert response.status_code == 201, response.data
    assert response.data['cogs_warnings'] == [{
        'product_id': product.id,
        'product_name': product_display_name(product),
        'method': 'standard',
        'reason': 'no_standard_cost',
    }]


def test_stock_issue_snapshot(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'standard', Decimal('10.125'))
    movement = record_stock_movement(
        product=product, movement_type='OUT', quantity=Decimal('1'),
        reference_type='STOCK_ISSUE', reference_id=777, movement_date=D, tenant=tenant,
    )
    assert movement.total_cost == Decimal('10.00')
    assert movement.cogs_method == 'standard'
    assert movement.cogs_cost == Decimal('10.13')


@pytest.mark.parametrize('method,standard_cost,expected_cogs', [
    ('fifo', None, Decimal('120.00')),
    ('standard', Decimal('11'), Decimal('110.00')),
])
def test_recompute_moving_wac_syncs_only_fifo(env, tmp_path, method, standard_cost, expected_cogs):
    tenant, cur, customer, product, ss = setup_purchase_case(env, method, standard_cost)
    tenant.CompanyName = 'الجرابعه'
    tenant.save(update_fields=['CompanyName'])
    Account.objects.get_or_create(tenant=tenant, code='5101', defaults={'name': 'cogs', 'account_type': 'Expense'})
    Account.objects.get_or_create(tenant=tenant, code='1104', defaults={'name': 'inv', 'account_type': 'Asset'})
    invoice = _sell(tenant, cur, customer, product, 10, f'WAC-{method}')
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id, product=product)
    assert movement.total_cost == Decimal('112.00')
    call_command('recompute_moving_wac_cogs', csv_dir=str(tmp_path), tenant_id=tenant.pk, apply=True, stdout=StringIO())
    movement.refresh_from_db()
    assert movement.total_cost == Decimal('120.00')
    assert movement.cogs_cost == expected_cogs
    assert movement.cogs_method == method


class LandedRevaluationSnapshotSyncTest(_AccrualAdjustBase):
    def test_landed_revaluation_syncs_fifo_snapshot(self):
        self._invoice()
        sale = self._sell('4')
        sale_cost_before = sale.total_cost
        self.assertEqual((sale.cogs_method, sale.cogs_cost), ('fifo', sale_cost_before))
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        sale.refresh_from_db()
        self.assertEqual(sale.total_cost, sale_cost_before + LD('120.00'))
        self.assertEqual(sale.cogs_cost, sale.total_cost)
        self.assertEqual(sale.cogs_method, 'fifo')

    def test_landed_revaluation_keeps_fixed_snapshot(self):
        self._invoice()
        Product.objects.filter(pk=self.product.pk).update(standard_cost=LD('500'))
        SalesSettings.objects.update_or_create(tenant=self.tenant, defaults={'cogs_cost_method': 'standard'})
        sale = self._sell('4')
        sale_cost_before = sale.total_cost
        self.assertEqual((sale.cogs_method, sale.cogs_cost), ('standard', LD('2000.00')))
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        sale.refresh_from_db()
        self.assertEqual(sale.total_cost, sale_cost_before + LD('120.00'))
        self.assertEqual(sale.cogs_cost, LD('2000.00'))
        self.assertEqual(sale.cogs_method, 'standard')
