from django.db import migrations
import re
import logging

logger = logging.getLogger(__name__)


def backfill_payment_purpose(apps, schema_editor):
    LogisticsClearancePayment = apps.get_model('logistics', 'LogisticsClearancePayment')
    count = 0
    for pay in LogisticsClearancePayment.objects.iterator():
        if pay.payment_purpose != 'other':
            continue
        notes = str(pay.notes or '')
        notes_stripped = notes.lstrip()
        if notes_stripped.startswith('[شحن]') or notes_stripped.startswith('شحن'):
            pay.payment_purpose = 'shipping'
        elif '[تخليص]' in notes:
            pay.payment_purpose = 'clearance_fee'
        elif 'عمولة' in notes or '[مخلِّص]' in notes:
            pay.payment_purpose = 'broker_fee'
        else:
            pay.payment_purpose = 'other'
        pay.save(update_fields=['payment_purpose'])
        count += 1
    if count:
        logger.info("Backfilled payment_purpose for %d clearance payments", count)


def reverse_backfill(apps, schema_editor):
    LogisticsClearancePayment = apps.get_model('logistics', 'LogisticsClearancePayment')
    LogisticsClearancePayment.objects.all().update(payment_purpose='other')


class Migration(migrations.Migration):
    dependencies = [
        ('logistics', '0031_add_payment_purpose'),
    ]
    operations = [
        migrations.RunPython(backfill_payment_purpose, reverse_backfill),
    ]
