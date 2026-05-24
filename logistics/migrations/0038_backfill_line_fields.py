from django.db import migrations
import re
import logging

logger = logging.getLogger(__name__)


BATCH_RE = re.compile(r'batch[:\s]+([A-Za-z0-9\-_]+)', re.I)
EXPIRY_RE = re.compile(r'expiry[:\s]+(\d{4}-\d{2}-\d{2})', re.I)
LOT_RE = re.compile(r'lot[:\s]+([A-Za-z0-9\-_]+)', re.I)


def backfill_deal_items(apps, schema_editor):
    LogisticsDealItem = apps.get_model('logistics', 'LogisticsDealItem')
    count = 0
    for item in LogisticsDealItem.objects.iterator():
        notes = str(item.notes or '')
        if not notes:
            continue
        changed = False
        m = BATCH_RE.search(notes)
        if m and not item.batch_number:
            item.batch_number = m.group(1)
            changed = True
        m = EXPIRY_RE.search(notes)
        if m and not item.expiry_date:
            item.expiry_date = m.group(1)
            changed = True
        m = LOT_RE.search(notes)
        if m and not item.manufacture_number:
            item.manufacture_number = m.group(1)
            changed = True
        if changed:
            item.save(update_fields=['batch_number', 'expiry_date', 'manufacture_number'])
            count += 1
    if count:
        logger.info("Backfilled %d deal items from notes", count)


def backfill_pi_items(apps, schema_editor):
    PurchaseInvoiceItem = apps.get_model('logistics', 'PurchaseInvoiceItem')
    count = 0
    for item in PurchaseInvoiceItem.objects.iterator():
        notes = str(item.notes or '')
        if not notes:
            continue
        changed = False
        m = BATCH_RE.search(notes)
        if m and not item.batch_number:
            item.batch_number = m.group(1)
            changed = True
        m = EXPIRY_RE.search(notes)
        if m and not item.expiry_date:
            item.expiry_date = m.group(1)
            changed = True
        m = LOT_RE.search(notes)
        if m and not item.manufacture_number:
            item.manufacture_number = m.group(1)
            changed = True
        if changed:
            item.save(update_fields=['batch_number', 'expiry_date', 'manufacture_number'])
            count += 1
    if count:
        logger.info("Backfilled %d PI items from notes", count)


class Migration(migrations.Migration):
    dependencies = [
        ('logistics', '0037_pi_item_enrichment'),
    ]
    operations = [
        migrations.RunPython(backfill_deal_items, migrations.RunPython.noop),
        migrations.RunPython(backfill_pi_items, migrations.RunPython.noop),
    ]
