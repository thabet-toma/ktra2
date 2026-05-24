from django.db import migrations
import logging

logger = logging.getLogger(__name__)

LABEL_TO_LINE_TYPE = {
    'ضريبة القيمة المضافة': 'vat',
    'رسوم البيان الجمركي': 'declaration_fee',
    'محطة الشحن': 'terminal',
    'معالجة التصاريح': 'permits',
    'عمولة المخلص': 'broker_commission',
    'نظام الجمارك «الجيل الجديد»': 'customs_system',
}


def backfill_clearance_lines(apps, schema_editor):
    LogisticsClearance = apps.get_model('logistics', 'LogisticsClearance')
    LogisticsClearanceLine = apps.get_model('logistics', 'LogisticsClearanceLine')

    count = 0
    for clr in LogisticsClearance.objects.iterator():
        if clr.lines.exists():
            continue
        cost_lines = clr.cost_lines
        if not cost_lines or not isinstance(cost_lines, list):
            continue
        for idx, item in enumerate(cost_lines):
            label = str(item.get('label', '') or '')
            amount_raw = item.get('amount', 0)
            amount = 0
            try:
                amount = float(amount_raw) if amount_raw else 0
            except (ValueError, TypeError):
                pass
            debit = abs(amount) if amount > 0 else 0
            credit = abs(amount) if amount < 0 else 0
            line_type = LABEL_TO_LINE_TYPE.get(label, 'other')
            LogisticsClearanceLine.objects.create(
                clearance=clr,
                seq=idx + 1,
                line_type=line_type,
                description=label,
                debit=debit,
                credit=credit,
            )
            count += 1
    if count:
        logger.info("Backfilled %d clearance lines from cost_lines JSON", count)


def reverse_backfill(apps, schema_editor):
    LogisticsClearanceLine = apps.get_model('logistics', 'LogisticsClearanceLine')
    LogisticsClearanceLine.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('logistics', '0028_clearance_line_model'),
    ]
    operations = [
        migrations.RunPython(backfill_clearance_lines, reverse_backfill),
    ]
