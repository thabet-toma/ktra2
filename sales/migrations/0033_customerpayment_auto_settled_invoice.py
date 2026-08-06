from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0032_salessettings_block_reserved_stock_sale'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerpayment',
            name='auto_settled_invoice',
            field=models.ForeignKey(
                blank=True, db_column='AutoSettledInvoiceID', null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='auto_settlements', to='sales.salesinvoice',
            ),
        ),
    ]
