from django.db import migrations, models


def backfill_invoice_type(apps, schema_editor):
    """الفواتير المرتبطة بمسار الاستيراد (صفقة/شحنة/تخليص/محوّلة من شحنة) = دولية؛
    البقية محلية. يطابق منطق is_local القديم في المُسلسِل."""
    PurchaseInvoice = apps.get_model('logistics', 'PurchaseInvoice')
    PurchaseInvoice.objects.filter(
        models.Q(deal__isnull=False)
        | models.Q(shipment__isnull=False)
        | models.Q(clearance__isnull=False)
        | models.Q(converted_from_shipment__isnull=False)
    ).update(invoice_type='international')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0046_purchasesettings_default_cash_account'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseinvoice',
            name='invoice_type',
            field=models.CharField(
                choices=[('local', 'محلية'), ('international', 'دولية (استيراد)')],
                db_column='InvoiceType', default='local', max_length=20,
            ),
        ),
        migrations.RunPython(backfill_invoice_type, noop_reverse),
    ]
