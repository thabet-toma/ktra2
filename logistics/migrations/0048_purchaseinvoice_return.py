from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0047_purchaseinvoice_invoice_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseinvoice',
            name='is_return',
            field=models.BooleanField(
                default=False, db_column='IsReturn',
                help_text='مرجع شراء (إرجاع بضاعة للمورد) — يعكس القيد ويُخرج الكمية.',
            ),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='original_invoice',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                db_column='OriginalInvoiceID',
                related_name='return_invoices',
                to='logistics.purchaseinvoice',
                help_text='فاتورة الشراء الأصلية التي يُرجَع منها (للمراجيع).',
            ),
        ),
    ]
