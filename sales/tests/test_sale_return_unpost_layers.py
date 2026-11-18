from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from inventory import fifo
from inventory.models import Product, StockLayer, StockLayerConsumption, StockLayerRestoration, StockMovement
from inventory.services import record_stock_movement, reverse_stock_movements
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from sales.tests.test_cogs_variance_journal import setup_case
from sales.tests.test_sale_return_restores_its_layers import D, env, _return, _sell

pytestmark = pytest.mark.django_db


def client_for(tenant):
    client = APIClient()
    client.force_authenticate(user=User.objects.get(username='retlayer'))
    client.credentials(HTTP_X_TENANT_ID=str(tenant.pk))
    return client


def unpost(tenant, invoice):
    return client_for(tenant).post(f'/api/sales/invoices/{invoice.pk}/unpost/', {}, format='json')


def repost(tenant, invoice):
    return client_for(tenant).post(f'/api/sales/invoices/{invoice.pk}/post/', {}, format='json')


def state(product, origin):
    layers = list(StockLayer.objects.filter(product=product).order_by('id').values_list('remaining_qty', 'unit_cost'))
    consumption = list(StockLayerConsumption.objects.filter(movement=origin).order_by('id').values_list('quantity', 'unit_cost'))
    return layers, consumption


def make_return(env, qty=4):
    tenant, cur, customer, product, sale, origin, _, _ = setup_case(env)
    ret = _return(tenant, cur, customer, product, qty, 'R-UNPOST', sale)
    return tenant, cur, customer, product, sale, origin, ret


def test_a_unpost_restores_layers_and_consumption(env):
    tenant, _, _, product, _, origin, ret = make_return(env)
    response = unpost(tenant, ret)
    assert response.status_code == 200, response.content
    layers, consumption = state(product, origin)
    assert layers == [(Decimal('0'), Decimal('10')), (Decimal('2'), Decimal('16'))]
    assert consumption == [(Decimal('8'), Decimal('10')), (Decimal('2'), Decimal('16'))]
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal('2')
    assert sum(q * cost for q, cost in layers) == Decimal('32')


def test_b_repost_retains_fifo_cost(env):
    tenant, _, _, product, _, _, ret = make_return(env)
    assert unpost(tenant, ret).status_code == 200
    assert repost(tenant, ret).status_code == 200
    assert StockMovement.objects.get(product=product, reference_id=ret.pk, movement_type='RETURN_IN').total_cost == Decimal('52')


def test_c_guard_preserves_state(env):
    tenant, cur, customer, product, _, origin, ret = make_return(env)
    _sell(tenant, cur, customer, product, 6, 'LATER')
    before = state(product, origin)
    movements = list(StockMovement.objects.filter(product=product).order_by('id').values_list('id', flat=True))
    all_consumptions = list(StockLayerConsumption.objects.filter(layer__product=product).order_by('id').values_list('id', 'quantity'))
    movement = StockMovement.objects.get(product=product, reference_id=ret.pk, movement_type='RETURN_IN')
    with pytest.raises(ValidationError, match='إلغاء ترحيل المرتجع'):
        reverse_stock_movements(tenant_id=tenant.pk, reference_id=ret.pk, reference_types=[movement.reference_type])
    response = unpost(tenant, ret)
    assert response.status_code == 400, response.content
    assert 'توجد مستندات لاحقة بُنيت عليه' in str(response.data) and product.name_ar in str(response.data)
    assert state(product, origin) == before
    assert list(StockMovement.objects.filter(product=product).order_by('id').values_list('id', flat=True)) == movements
    assert list(StockLayerConsumption.objects.filter(layer__product=product).order_by('id').values_list('id', 'quantity')) == all_consumptions


def test_d_unpost_second_partial_return(env):
    tenant, cur, customer, product, sale, origin, _ = make_return(env, 1)
    before = state(product, origin)
    second = _return(tenant, cur, customer, product, 1, 'R-SECOND', sale)
    assert unpost(tenant, second).status_code == 200
    assert state(product, origin) == before


def test_e_legacy_return_unposts(env):
    tenant, _, _, product, _, origin, ret = make_return(env)
    StockLayerRestoration.objects.filter(tenant=tenant, movement__reference_id=ret.pk).delete()
    before = state(product, origin)
    assert [qty for qty, _ in before[0]] == [2, 4]
    assert not StockLayerRestoration.objects.filter(tenant=tenant, layer__product=product).exists()
    assert unpost(tenant, ret).status_code == 200
    assert state(product, origin) == before
    assert not StockLayerRestoration.objects.filter(tenant=tenant, layer__product=product).exists()


def test_f_fixed_snapshot_repost_regression(env):
    """فحص تراجع للقطة الثابتة؛ خطّيتها لا تكشف خلل ترتيب الطبقات."""
    tenant, cur, customer, product, sale, origin, _, _ = setup_case(env)
    origin.cogs_method, origin.cogs_cost = 'standard', Decimal('110')
    origin.save(update_fields=['cogs_method', 'cogs_cost'])
    ret = _return(tenant, cur, customer, product, 4, 'R-FIXED', sale)
    def cost():
        return StockMovement.objects.get(product=product, reference_id=ret.pk, movement_type='RETURN_IN').cogs_cost
    assert cost() == Decimal('44')
    assert unpost(tenant, ret).status_code == 200
    assert repost(tenant, ret).status_code == 200
    assert cost() == Decimal('44')


def test_g_restore_without_restored_by_has_no_provenance(env):
    tenant, _, _, product, _, origin, _, _ = setup_case(env)
    fifo.restore_partial(movements=[origin], quantity=Decimal('1'))
    assert not StockLayerRestoration.objects.filter(tenant=tenant, layer__product=product).exists()


def test_h_later_return_must_be_unposted_first(env):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='LIFO', name_ar='ترتيب', quantity_on_hand=0, avg_cost=0)
    for qty, cost in [(5, 10), (3, 16), (2, 20)]:
        record_stock_movement(product=product, movement_type='IN', quantity=Decimal(qty),
                              unit_cost=Decimal(cost), movement_date=D, tenant=tenant)
    sale = _sell(tenant, cur, customer, product, 10, 'S-LIFO')
    origin = StockMovement.objects.get(product=product, reference_id=sale.pk, movement_type='OUT')
    first = _return(tenant, cur, customer, product, 2, 'R-LIFO-1', sale)
    second = _return(tenant, cur, customer, product, 3, 'R-LIFO-2', sale)
    assert StockMovement.objects.get(product=product, reference_id=first.pk, movement_type='RETURN_IN').total_cost == Decimal('40')
    assert StockMovement.objects.get(product=product, reference_id=second.pk, movement_type='RETURN_IN').total_cost == Decimal('48')
    before = state(product, origin)
    movements = list(StockMovement.objects.filter(product=product).order_by('id').values())
    consumptions = list(StockLayerConsumption.objects.filter(layer__product=product).order_by('id').values())
    response = unpost(tenant, first)
    assert response.status_code == 400, response.content
    assert 'المرتجع اللاحق' in str(response.data)
    assert state(product, origin) == before
    assert list(StockMovement.objects.filter(product=product).order_by('id').values()) == movements
    assert list(StockLayerConsumption.objects.filter(layer__product=product).order_by('id').values()) == consumptions
    assert unpost(tenant, second).status_code == 200
    assert unpost(tenant, first).status_code == 200
    layers, consumption = state(product, origin)
    assert consumption == [(Decimal('5'), Decimal('10')), (Decimal('3'), Decimal('16')), (Decimal('2'), Decimal('20'))]
    assert [qty for qty, _ in layers] == [0, 0, 0]
    assert repost(tenant, first).status_code == 200
    assert StockMovement.objects.get(product=product, reference_id=first.pk, movement_type='RETURN_IN').total_cost == Decimal('40')


def test_i_restorations_are_deleted_with_the_movement(env):
    tenant, _, _, product, _, origin, ret = make_return(env)
    movement = StockMovement.objects.get(product=product, reference_id=ret.pk, movement_type='RETURN_IN')
    kwargs = dict(tenant_id=tenant.pk, reference_id=ret.pk, reference_types=[movement.reference_type])
    assert reverse_stock_movements(**kwargs) == 1
    before = state(product, origin)
    assert reverse_stock_movements(**kwargs) == 0
    assert state(product, origin) == before
    assert not StockLayerRestoration.objects.filter(tenant=tenant, movement_id=movement.pk).exists()


def invoice_with_lines(tenant, cur, customer, product, quantities, number, original=None):
    invoice = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date=D, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        invoice_kind=(SalesInvoice.INVOICE_KIND_SALE_RETURN if original else SalesInvoice.INVOICE_KIND_SALE),
        original_invoice=original,
    )
    for qty in quantities:
        SalesInvoiceLine.objects.create(tenant=tenant, invoice=invoice, product=product,
                                        quantity=Decimal(qty), unit_price=Decimal('200'))
    post_sales_invoice(invoice)
    return invoice


def test_j_later_return_from_another_origin_must_be_unposted_first(env):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='LIFO-MULTI', name_ar='ترتيب متعدد', quantity_on_hand=0, avg_cost=0)
    for qty, cost in [(5, 10), (3, 16), (2, 20)]:
        record_stock_movement(product=product, movement_type='IN', quantity=Decimal(qty),
                              unit_cost=Decimal(cost), movement_date=D, tenant=tenant)
    sale = invoice_with_lines(tenant, cur, customer, product, [8, 2], 'S-MULTI')
    origins = list(StockMovement.objects.filter(tenant=tenant, product=product, reference_id=sale.pk, movement_type='OUT').order_by('id'))
    first = _return(tenant, cur, customer, product, 2, 'R-MULTI-1', sale)
    second = _return(tenant, cur, customer, product, 3, 'R-MULTI-2', sale)
    assert list(StockMovement.objects.filter(tenant=tenant, reference_id__in=[first.pk, second.pk], movement_type='RETURN_IN').order_by('id').values_list('total_cost', flat=True)) == [Decimal('40'), Decimal('48')]
    layers = list(StockLayer.objects.filter(product=product).order_by('id').values())
    movements = list(StockMovement.objects.filter(product=product).order_by('id').values())
    consumptions = list(StockLayerConsumption.objects.filter(layer__product=product).order_by('id').values())
    response = unpost(tenant, first)
    assert response.status_code == 400, response.content
    assert 'المرتجع اللاحق' in str(response.data)
    assert list(StockLayer.objects.filter(product=product).order_by('id').values()) == layers
    assert list(StockMovement.objects.filter(product=product).order_by('id').values()) == movements
    assert list(StockLayerConsumption.objects.filter(layer__product=product).order_by('id').values()) == consumptions
    assert unpost(tenant, second).status_code == 200
    assert unpost(tenant, first).status_code == 200
    assert list(StockLayerConsumption.objects.filter(movement__in=origins).order_by('id').values_list('quantity', 'unit_cost')) == [(Decimal('5'), Decimal('10')), (Decimal('3'), Decimal('16')), (Decimal('2'), Decimal('20'))]
    assert repost(tenant, first).status_code == 200
    assert StockMovement.objects.get(tenant=tenant, product=product, reference_id=first.pk, movement_type='RETURN_IN').total_cost == Decimal('40')


def test_k_two_return_lines_merge_recreated_consumption(env):
    tenant, cur, customer, _ = env
    product = Product.objects.create(tenant=tenant, sku='MERGE', name_ar='دمج', quantity_on_hand=0, avg_cost=0)
    for qty, cost in [(1, 10), (2, 16)]:
        record_stock_movement(product=product, movement_type='IN', quantity=Decimal(qty),
                              unit_cost=Decimal(cost), movement_date=D, tenant=tenant)
    sale = _sell(tenant, cur, customer, product, 3, 'S-MERGE')
    origin = StockMovement.objects.get(tenant=tenant, product=product, reference_id=sale.pk, movement_type='OUT')
    before = state(product, origin)
    ret = invoice_with_lines(tenant, cur, customer, product, [1, 1], 'R-MERGE', sale)
    costs = list(StockMovement.objects.filter(tenant=tenant, product=product, reference_id=ret.pk, movement_type='RETURN_IN').order_by('id').values_list('total_cost', flat=True))
    assert costs == [Decimal('16'), Decimal('16')]
    assert unpost(tenant, ret).status_code == 200
    assert state(product, origin) == before
    assert list(StockLayerConsumption.objects.filter(movement=origin, layer__unit_cost=16).values_list('quantity', 'unit_cost')) == [(Decimal('2'), Decimal('16'))]
    assert repost(tenant, ret).status_code == 200
    assert list(StockMovement.objects.filter(tenant=tenant, product=product, reference_id=ret.pk, movement_type='RETURN_IN').order_by('id').values_list('total_cost', flat=True)) == costs
