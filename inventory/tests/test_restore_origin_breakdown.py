from decimal import Decimal

import pytest

from inventory import fifo
from inventory.models import StockMovement
from sales.tests.test_sale_return_restores_its_layers import env, _sell

pytestmark = pytest.mark.django_db


def test_restore_partial_reports_each_origin(env):
    tenant, cur, customer, product = env
    first = _sell(tenant, cur, customer, product, 2, 'BREAK-1')
    second = _sell(tenant, cur, customer, product, 3, 'BREAK-2')
    movements = list(StockMovement.objects.filter(
        reference_type='SALE', reference_id__in=[first.id, second.id]).order_by('id'))
    result = fifo.restore_partial(movements=movements, quantity=Decimal('4'))
    assert result.by_origin == {
        movements[0].id: (Decimal('1'), Decimal('10')),
        movements[1].id: (Decimal('3'), Decimal('30')),
    }
