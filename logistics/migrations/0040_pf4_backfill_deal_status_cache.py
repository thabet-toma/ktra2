# P-F-4: backfill legacy status/order_status/payment_status cache columns from
# shipping_workflow_status (lifecycle) and posted payments (settlement).
#
# Rationale: task6 P-F-4 calls for `shipping_workflow_status` to be the single
# source of truth and the legacy columns to mirror it. We implement that via a
# save() auto-sync + signals-level sync in code; this one-shot data migration
# brings existing rows in line with the new invariant.

from decimal import Decimal
from django.db import migrations
from django.db.models import Sum

STATUS_FROM_WORKFLOW = {
    None: 'Open',
    'sw_mfg_start': 'Open',
    'sw_wait_agent_ship': 'Shipped',
    'sw_wait_intl_ship': 'Shipped',
    'sw_wait_arrival': 'Shipped',
    'sw_wait_clearance': 'Cleared',
    'sw_released': 'Closed',
}
ORDER_FROM_WORKFLOW = {
    'sw_mfg_start': 'Manufacturing',
    'sw_wait_agent_ship': 'Shipping',
    'sw_wait_intl_ship': 'Shipping',
    'sw_wait_arrival': 'Shipping',
    'sw_wait_clearance': 'Clearance',
    'sw_released': 'Delivered',
}


def backfill(apps, schema_editor):
    LogisticsDeal = apps.get_model('logistics', 'LogisticsDeal')
    LogisticsPayment = apps.get_model('logistics', 'LogisticsPayment')
    for deal in LogisticsDeal.objects.all().only(
        'id', 'shipping_workflow_status', 'status', 'order_status',
        'payment_status', 'total_amount',
    ).iterator():
        sw = deal.shipping_workflow_status
        new_status = STATUS_FROM_WORKFLOW.get(sw, deal.status)
        new_order = ORDER_FROM_WORKFLOW.get(sw, deal.order_status)
        posted = (
            LogisticsPayment.objects.filter(deal_id=deal.id, is_posted=True)
            .aggregate(t=Sum('amount'))['t']
        ) or Decimal('0')
        total = deal.total_amount or Decimal('0')
        try:
            posted_d = Decimal(str(posted))
            total_d = Decimal(str(total))
        except Exception:
            posted_d, total_d = Decimal('0'), Decimal('0')
        if total_d <= 0:
            new_ps = 'Unpaid'
        elif posted_d >= total_d:
            new_ps = 'Fully Paid'
        elif posted_d > 0:
            new_ps = 'Partially Paid'
        else:
            new_ps = 'Unpaid'
        updates = {}
        if deal.status != new_status:
            updates['status'] = new_status
        if deal.order_status != new_order:
            updates['order_status'] = new_order
        if deal.payment_status != new_ps:
            updates['payment_status'] = new_ps
        if updates:
            LogisticsDeal.objects.filter(pk=deal.id).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ('logistics', '0039_clearance_header_enrichment'),
    ]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
