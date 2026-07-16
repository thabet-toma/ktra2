from django.db import migrations, models


def backfill_calculation_value(apps, schema_editor):
    PurchaseInvoiceFee = apps.get_model('logistics', 'PurchaseInvoiceFee')
    for fee in PurchaseInvoiceFee.objects.all().only('id', 'amount').iterator():
        PurchaseInvoiceFee.objects.filter(pk=fee.pk).update(
            calculation_type='amount',
            calculation_value=fee.amount,
            percentage_basis='goods',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0054_localshipmentpayment'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseinvoicefee',
            name='calculation_type',
            field=models.CharField(
                choices=[('amount', 'مبلغ'), ('percentage', 'نسبة')],
                db_column='CalculationType', default='amount', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='purchaseinvoicefee',
            name='calculation_value',
            field=models.DecimalField(
                db_column='CalculationValue', decimal_places=4,
                default=0, max_digits=18,
                help_text='القيمة المدخلة: مبلغ بالشيكل أو نسبة مئوية حسب calculation_type',
            ),
        ),
        migrations.AddField(
            model_name='purchaseinvoicefee',
            name='percentage_basis',
            field=models.CharField(
                choices=[('goods', 'البضاعة'), ('after_main_vat', 'بعد ضريبة القيمة المضافة')],
                db_column='PercentageBasis', default='goods', max_length=20,
            ),
        ),
        migrations.RunPython(backfill_calculation_value, migrations.RunPython.noop),
    ]
