from decimal import Decimal

import pytest

from accounting.models import Account, JournalHeader, JournalLine
from inventory.cogs_method import MISSING_COST_VARIANCE_ACCOUNT_ERROR
from inventory.models import Product, StockLayer, StockMovement
from inventory.services import _resolve_line_account, product_display_name, record_stock_movement
from inventory.tests.test_unpost_provisional_reconciliation import _receive
from logistics.tests.test_accrual_adjust import D as LD, _AccrualAdjustBase
from sales.models import SalesInvoice, SalesSettings
from sales.services import post_sales_invoice
from sales.tests.test_sale_return_restores_its_layers import D, env, _return, _sell, _remaining
from sales.tests.test_sale_return_unpost_layers import client_for

pytestmark = pytest.mark.django_db


def test_legacy_cost_tools_and_flag_are_removed():
    """يتحقق من عدم تسجيل الأوامر reconcile_cogs وrecompute_product_cost
    وrecompute_moving_wac_cogs وbackfill_stock، وعدم إتاحة
    inventory.services للدالة reconcile_product_cogs، وغياب الحقل
    use_moving_average_cost من SalesSettings.

    كانت الأدوات القديمة تكتب قيماً للكلفة تخالف محرك الكلفة وقد تمسّ قيوداً
    مُرحّلة؛ وحُذفت بقرار المالك (#295)، لذا فإن إعادة أيٍّ منها تستلزم قراراً
    مقصوداً ولا ينبغي أن تحدث مصادفةً.
    """
    from django.core.exceptions import FieldDoesNotExist
    from django.core.management import get_commands
    import inventory.services

    for name in ('reconcile_cogs', 'recompute_product_cost', 'recompute_moving_wac_cogs', 'backfill_stock'):
        assert name not in get_commands()
    with pytest.raises(FieldDoesNotExist):
        SalesSettings._meta.get_field("use_moving_average_cost")
    assert not hasattr(inventory.services, 'reconcile_product_cogs')


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
    adjustment.refresh_from_db()
    assert adjustment.cogs_method is None and movement.cogs_method is None
    assert _remaining(tenant, product) == [Decimal('6'), Decimal('4')]


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


def _linked_avco_delivery_return(env, sale_number, return_number):
    from sales.services import deliver_invoice_lines

    tenant, cur, customer, product = env
    SalesSettings.objects.filter(tenant=tenant).update(cogs_cost_method='avco')
    sale = SalesInvoice.objects.create(tenant=tenant, invoice_number=sale_number, customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    line = sale.lines.create(tenant=tenant, product=product, quantity=35, unit_price=200)
    post_sales_invoice(sale)
    sale.refresh_from_db()
    deliver_invoice_lines(sale, lines=[{'line_id': line.id, 'quantity': 35}])
    origin = StockMovement.objects.get(tenant=tenant, reference_type='SALE', reference_id=sale.id)
    record_stock_movement(product=product, movement_type='IN', quantity=35, unit_cost=100,
                          movement_date=D, tenant=tenant)
    ret = SalesInvoice.objects.create(tenant=tenant, invoice_number=return_number, customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN, original_invoice=sale)
    ret_line = ret.lines.create(tenant=tenant, product=product, quantity=35, unit_price=200)
    post_sales_invoice(ret)
    ret.refresh_from_db()
    return ret, ret_line, origin


def test_linked_avco_delivery_return_restores_origin_layers(env):
    from sales.services import deliver_invoice_lines

    tenant, _, _, product = env
    ret, ret_line, origin = _linked_avco_delivery_return(env, 'AVCO-DEL-S', 'AVCO-DEL-R')
    assert origin.total_cost == Decimal('850')
    layers = list(StockLayer.objects.filter(tenant=tenant, product=product).order_by('id'))
    for qty in (14, 21):
        deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': qty}])
    returns = StockMovement.objects.filter(tenant=tenant, reference_type='SALE', reference_id=ret.id)
    assert list(returns.order_by('id').values_list('total_cost', flat=True)) == [Decimal('340'), Decimal('510')]
    assert StockLayer.objects.filter(tenant=tenant, product=product).count() == 3
    for layer, expected in zip(layers[:2], (Decimal('50'), Decimal('20'))):
        layer.refresh_from_db()
        assert layer.remaining_qty == expected


def test_void_linked_avco_delivery_return_undoes_origin_restoration(env):
    from django.db.models import Sum
    from inventory.models import StockLayerConsumption
    from sales.services import deliver_invoice_lines, void_delivery_note

    tenant, _, _, product = env
    ret, ret_line, origin = _linked_avco_delivery_return(env, 'AVCO-VOID-S', 'AVCO-VOID-R')
    layers = list(StockLayer.objects.filter(tenant=tenant, product=product).order_by('id'))
    before = [layer.remaining_qty for layer in layers]
    consumed = StockLayerConsumption.objects.filter(movement=origin).aggregate(total=Sum('quantity'))['total']
    assert consumed == Decimal('35')
    product.refresh_from_db()
    on_hand = product.quantity_on_hand

    delivery = deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 14}])
    void_delivery_note(delivery)
    for layer, expected in zip(layers, before):
        layer.refresh_from_db()
        assert layer.remaining_qty == expected
    assert StockLayerConsumption.objects.filter(movement=origin).aggregate(total=Sum('quantity'))['total'] == consumed
    product.refresh_from_db()
    assert product.quantity_on_hand == on_hand
    ret_line.refresh_from_db()
    assert ret_line.delivered_quantity == 0

    deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 35}])
    movement = StockMovement.objects.get(tenant=tenant, reference_type='SALE', reference_id=ret.id)
    assert movement.total_cost == Decimal('850')
    for layer, expected in zip(layers[:2], (Decimal('50'), Decimal('20'))):
        layer.refresh_from_db()
        assert layer.remaining_qty == expected


def test_void_earlier_linked_avco_delivery_return_blocked_by_later(env):
    from django.core.exceptions import ValidationError
    from django.db.models import Sum
    from inventory.models import StockLayerConsumption, StockLayerRestoration
    from sales.services import deliver_invoice_lines, void_delivery_note

    tenant, _, _, product = env
    ret, ret_line, origin = _linked_avco_delivery_return(env, 'AVCO-BLOCK-S', 'AVCO-BLOCK-R')
    first = deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 14}])
    deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 21}])
    movement_ids = list(first.lines.values_list('movement_id', flat=True))
    restoration_ids = list(StockLayerRestoration.objects.filter(movement_id__in=movement_ids)
                           .values_list('id', flat=True))
    assert movement_ids and restoration_ids
    layers = StockLayer.objects.filter(tenant=tenant, product=product).order_by('id')
    before_layers = list(layers.values_list('id', 'remaining_qty'))
    consumed = StockLayerConsumption.objects.filter(movement=origin).aggregate(total=Sum('quantity'))['total']
    product.refresh_from_db()
    on_hand = product.quantity_on_hand
    ret_line.refresh_from_db()
    delivered = ret_line.delivered_quantity

    with pytest.raises(ValidationError, match='مرتجعٌ لاحق'):
        void_delivery_note(first)

    assert list(layers.values_list('id', 'remaining_qty')) == before_layers
    assert StockLayerConsumption.objects.filter(movement=origin).aggregate(total=Sum('quantity'))['total'] == consumed
    product.refresh_from_db()
    assert product.quantity_on_hand == on_hand
    ret_line.refresh_from_db()
    assert ret_line.delivered_quantity == delivered
    assert StockMovement.objects.filter(id__in=movement_ids).count() == len(movement_ids)
    assert StockLayerRestoration.objects.filter(id__in=restoration_ids).count() == len(restoration_ids)


def test_redeliver_latest_linked_avco_delivery_return_restores_cleanly(env):
    from django.db.models import Sum
    from inventory.models import StockLayerConsumption
    from sales.services import deliver_invoice_lines, void_delivery_note

    tenant, _, _, product = env
    ret, ret_line, origin = _linked_avco_delivery_return(env, 'AVCO-EDIT-S', 'AVCO-EDIT-R')
    layer_count = StockLayer.objects.filter(tenant=tenant, product=product).count()
    deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 14}])
    latest = deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 21}])
    void_delivery_note(latest)
    before = {row.layer_id: (row.quantity, row.unit_cost)
              for row in StockLayerConsumption.objects.filter(movement=origin)}
    new_delivery = deliver_invoice_lines(ret, lines=[{'line_id': ret_line.id, 'quantity': 20}])
    after = {row.layer_id: row.quantity for row in StockLayerConsumption.objects.filter(movement=origin)}
    restored_cost = sum((quantity - after.get(layer_id, Decimal('0'))) * cost
                        for layer_id, (quantity, cost) in before.items())
    movement = new_delivery.lines.get().movement
    assert movement.movement_type == 'RETURN_IN'
    assert movement.total_cost == restored_cost.quantize(Decimal('0.01')) == Decimal('485.72')
    assert StockLayer.objects.filter(tenant=tenant, product=product).count() == layer_count
    assert StockLayerConsumption.objects.filter(movement=origin).aggregate(total=Sum('quantity'))['total'] == 1
    ret_line.refresh_from_db()
    assert ret_line.delivered_quantity == 34


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


def test_avco_snapshot_without_warning(env):
    tenant, cur, customer, product, ss = setup_purchase_case(env, 'avco', Decimal('11'))
    invoice = SalesInvoice.objects.create(tenant=tenant, invoice_number='AVCO', customer=customer,
        currency=cur, invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
    invoice.lines.create(tenant=tenant, product=product, quantity=10, unit_price=200)
    post_sales_invoice(invoice)
    movement = StockMovement.objects.get(reference_type='SALE', reference_id=invoice.id)
    assert movement.cogs_method == 'avco'
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


class LandedRevaluationSnapshotSyncTest(_AccrualAdjustBase):
    def test_landed_revaluation_syncs_avco_snapshot(self):
        self._invoice()
        record_stock_movement(product=self.product, movement_type='IN', quantity=10, unit_cost=100,
                              movement_date='2026-07-10', tenant=self.tenant)
        SalesSettings.objects.update_or_create(tenant=self.tenant, defaults={'cogs_cost_method': 'avco'})
        sale = self._sell('8')
        before = sale.total_cost
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        sale.refresh_from_db()
        self.assertEqual(sale.total_cost, before + LD('120.00'))
        self.assertEqual(sale.total_cost, LD('3780.00'))
        self.assertEqual(sale.cogs_cost, sale.total_cost)

    def test_landed_revaluation_keeps_avco_non_sale_snapshot_null(self):
        self._invoice()
        SalesSettings.objects.update_or_create(tenant=self.tenant, defaults={'cogs_cost_method': 'avco'})
        movement = record_stock_movement(product=self.product, movement_type='ADJUST_OUT', quantity=4,
            movement_date='2026-07-20', tenant=self.tenant)
        before = movement.total_cost
        self.assertIsNone(movement.cogs_cost)
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        movement.refresh_from_db()
        self.assertEqual(movement.total_cost, before + LD('120.00'))
        self.assertIsNone(movement.cogs_cost)

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
        variance = Account.objects.create(
            tenant=self.tenant, code='5109-REV', name='فروقات تكلفة المبيعات',
            account_type='Expense', is_active=True,
        )
        SalesSettings.objects.update_or_create(
            tenant=self.tenant,
            defaults={'cogs_cost_method': 'standard', 'cost_variance_account': variance},
        )
        sale = self._sell('4')
        sale_cost_before = sale.total_cost
        self.assertEqual((sale.cogs_method, sale.cogs_cost), ('standard', LD('2000.00')))
        SalesSettings.objects.filter(tenant=self.tenant).update(cogs_cost_method='fifo')
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        sale.refresh_from_db()
        self.assertEqual(sale.total_cost, sale_cost_before + LD('120.00'))
        self.assertEqual(sale.cogs_cost, LD('2000.00'))
        self.assertEqual(sale.cogs_method, 'standard')
        [reval] = res.data['revaluations']
        self.assertEqual(reval['variance'], '120.00')
        self.assertEqual(reval['cogs'], '0.00')
        journal = JournalHeader.objects.get(pk=reval['journal_id'])
        cogs_acct = _resolve_line_account(self.product, 'cogs', tenant_id=self.tenant.TenantID)
        self.assertTrue(JournalLine.objects.filter(journal=journal, account=variance, debit=LD('120.00')).exists())
        self.assertFalse(JournalLine.objects.filter(journal=journal, account=cogs_acct).exists())

    def test_landed_revaluation_fixed_without_variance_account_fails_preview_and_apply(self):
        self._invoice()
        Product.objects.filter(pk=self.product.pk).update(standard_cost=LD('500'))
        SalesSettings.objects.update_or_create(
            tenant=self.tenant,
            defaults={'cogs_cost_method': 'standard', 'cost_variance_account': None},
        )
        sale = self._sell('4')
        sale_cost_before = sale.total_cost
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()

        for extra in ({'preview': True}, {}):
            res = self._adjust_clearance(900, **extra)
            self.assertEqual(res.status_code, 400, res.content)
            self.assertIn(MISSING_COST_VARIANCE_ACCOUNT_ERROR, res.data['error'])

        sale.refresh_from_db()
        self.assertEqual(sale.total_cost, sale_cost_before)
        self.assertEqual(JournalHeader.objects.filter(tenant=self.tenant).count(), journals_before)

    def test_landed_revaluation_reconciled_provisional_fixed_routes_to_variance(self):
        variance = Account.objects.create(
            tenant=self.tenant, code='5109-REC', name='فروقات تكلفة المبيعات',
            account_type='Expense', is_active=True,
        )
        Product.objects.filter(pk=self.product.pk).update(standard_cost=LD('500'), avg_cost=LD('500'))
        SalesSettings.objects.update_or_create(
            tenant=self.tenant,
            defaults={'cogs_cost_method': 'standard', 'cost_variance_account': variance},
        )
        sale = self._sell('4')
        self.assertEqual(sale.cogs_method, 'standard')
        self._invoice()

        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        [reval] = res.data['revaluations']
        self.assertEqual(reval['variance'], '120.00')
        self.assertEqual(reval['cogs'], '0.00')
        self.assertEqual(reval['inventory'], '180.00')
        journal = JournalHeader.objects.get(pk=reval['journal_id'])
        cogs_acct = _resolve_line_account(self.product, 'cogs', tenant_id=self.tenant.TenantID)
        self.assertTrue(JournalLine.objects.filter(journal=journal, account=variance, debit=LD('120.00')).exists())
        self.assertFalse(JournalLine.objects.filter(journal=journal, account=cogs_acct).exists())


def test_avco_sale_acceptance(env):
    from inventory import fifo

    tenant, cur, customer, product, ss = setup_purchase_case(env, 'avco')
    sale = _sell(tenant, cur, customer, product, 10, 'AVCO-ACCEPT')
    mv = StockMovement.objects.get(tenant=tenant, reference_type='SALE', reference_id=sale.id)
    assert (mv.total_cost, mv.cogs_cost, mv.cogs_method) == (Decimal('120'), Decimal('120'), 'avco')
    layers = list(
        StockLayer.objects.filter(tenant=tenant, product=product)
        .order_by('layer_date', 'id').values_list('remaining_qty', 'unit_cost')
    )
    assert layers == [(Decimal('1.3334'), Decimal('10')), (Decimal('0.6666'), Decimal('16'))]
    rows = list(JournalLine.objects.filter(journal_id=sale.journal_id))
    assert sum(r.debit for r in rows if r.account_id == ss.default_cogs_account_id) == Decimal('120')
    assert sum(r.credit for r in rows if r.account_id == ss.default_inventory_account_id) == Decimal('120')
    assert not any(r.account_id == ss.cost_variance_account_id for r in rows)
    assert sum(r.debit for r in rows) == sum(r.credit for r in rows)
    assert not fifo.layer_balance_gaps(tenant_id=tenant.pk, product_ids=[product.pk])
    product.refresh_from_db()
    assert product.avg_cost == fifo.derived_avg_cost(tenant_id=tenant.pk, product_id=product.pk)
    # هذا فرق التقريب المقبول في D6 بين total_cost بمنزلتين والطبقات بأربع منازل.
    assert abs(Decimal('144') - mv.total_cost - sum(q * c for q, c in layers)) < Decimal('0.01')


def test_avco_other_outbound_persists_method(env):
    tenant, _, _, product, _ = setup_purchase_case(env, 'avco')
    mv = record_stock_movement(
        product=product, movement_type='ADJUST_OUT', quantity=6, movement_date=D, tenant=tenant,
    )
    mv.refresh_from_db()
    assert (mv.cogs_method, mv.cogs_cost) == ('avco', None)
    assert _remaining(tenant, product) == [Decimal('4'), Decimal('2')]
