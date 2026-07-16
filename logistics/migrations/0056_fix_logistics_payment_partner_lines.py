from django.db import migrations


def fix_logistics_payment_partner_lines(apps, schema_editor):
    LogisticsPayment = apps.get_model('logistics', 'LogisticsPayment')
    JournalHeader = apps.get_model('accounting', 'JournalHeader')
    JournalLine = apps.get_model('accounting', 'JournalLine')

    journals = JournalHeader.objects.filter(
        reference_type='LOGISTICS_PAYMENT',
    ).only('id', 'reference_id')
    for journal in journals.iterator():
        payment = LogisticsPayment.objects.filter(
            pk=journal.reference_id,
        ).select_related('deal__partner').first()
        if not payment or not payment.deal_id or not payment.deal.partner_id:
            continue
        payable_account_id = payment.deal.partner.linked_account_id
        if not payable_account_id:
            continue
        JournalLine.objects.filter(journal_id=journal.id).exclude(
            account_id=payable_account_id,
        ).update(partner_id=None)
        JournalLine.objects.filter(
            journal_id=journal.id,
            account_id=payable_account_id,
        ).update(partner_id=payment.deal.partner_id)


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0055_purchaseinvoicefee_calculation_fields'),
    ]

    operations = [
        migrations.RunPython(
            fix_logistics_payment_partner_lines,
            migrations.RunPython.noop,
        ),
    ]
