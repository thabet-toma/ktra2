"""استحقاق النقل المحلي القديم وسم سطر المصروف بالناقل مع سطر ذممه.

`partner_posted_balance` يجمع كل أسطر الطرف بلا فلتر حساب، فالمدين الموسوم يُلغي
الدائن وكشف الناقل لا يتحرّك (إنتاج: قيد #10961، LS-0002، اسامه، 2,000). يُزال
الوسم عن أسطر المدين في قيود LOCAL_SHIPMENT التي يحمل طرفُها طرفَ سطر الدائن.
الوسم وحده — لا مبالغ ولا حسابات؛ وإعادة التشغيل لا تجد شيئاً.
"""
from django.db import migrations


def untag_local_shipment_expense_lines(apps, schema_editor):
    JournalLine = apps.get_model('accounting', 'JournalLine')
    credit_tags = (
        JournalLine.objects
        .filter(journal__reference_type='LOCAL_SHIPMENT', credit__gt=0, partner_id__isnull=False)
        .values_list('journal_id', 'partner_id')
    )
    for journal_id, partner_id in credit_tags.iterator():
        JournalLine.objects.filter(
            journal_id=journal_id, debit__gt=0, partner_id=partner_id,
        ).update(partner_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0089_sync_import_receipts_legacy_notes'),
    ]

    operations = [
        migrations.RunPython(untag_local_shipment_expense_lines, migrations.RunPython.noop),
    ]
