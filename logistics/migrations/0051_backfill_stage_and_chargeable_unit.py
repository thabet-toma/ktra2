# Import redesign M0: backfill canonical stage + chargeable unit from legacy fields.
from django.db import migrations


# Deterministic map (kept in sync with logistics.domain.stages.STAGE_FROM_WORKFLOW).
STAGE_FROM_WORKFLOW = {
    None: 'draft',
    'sw_mfg_start': 'draft',
    'sw_wait_agent_ship': 'draft',
    'sw_wait_intl_ship': 'ready_to_ship',
    'sw_wait_arrival': 'in_shipment',
    'sw_wait_clearance': 'at_clearance',
    'sw_released': 'invoiced',
}


def forwards(apps, schema_editor):
    Deal = apps.get_model('logistics', 'LogisticsDeal')
    Shipment = apps.get_model('logistics', 'LogisticsShipment')

    for deal in Deal.objects.all().only('id', 'status', 'shipping_workflow_status', 'stage'):
        if deal.stage:
            continue
        if deal.status == 'Cancelled':
            deal.stage = 'cancelled'
        else:
            deal.stage = STAGE_FROM_WORKFLOW.get(deal.shipping_workflow_status, 'draft')
        deal.save(update_fields=['stage'])

    for sh in Shipment.objects.all().only('id', 'unit_type', 'chargeable_unit', 'price_per_unit', 'freight_rate'):
        if not sh.chargeable_unit:
            # 'weight' → kg; 'cbm'/'container'/None → cbm (container folds into CBM).
            sh.chargeable_unit = 'kg' if (sh.unit_type or '').lower() == 'weight' else 'cbm'
        if sh.freight_rate is None and sh.price_per_unit is not None:
            sh.freight_rate = sh.price_per_unit
        sh.save(update_fields=['chargeable_unit', 'freight_rate'])


def backwards(apps, schema_editor):
    # Additive backfill — reverting just clears the new columns.
    Deal = apps.get_model('logistics', 'LogisticsDeal')
    Shipment = apps.get_model('logistics', 'LogisticsShipment')
    Deal.objects.update(stage=None)
    Shipment.objects.update(chargeable_unit=None, freight_rate=None)


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0050_logisticsdeal_stage_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
