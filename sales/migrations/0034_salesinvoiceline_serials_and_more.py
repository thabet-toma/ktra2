from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0033_customerpayment_auto_settled_invoice'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesinvoiceline',
            name='serials',
            field=models.JSONField(blank=True, db_column='Serials', default=list, help_text='أرقام تسلسلية مختارة للوحدات المبيعة في هذا البند (تُستهلَك عند الترحيل)'),
        ),
        migrations.AddField(
            model_name='salessettings',
            name='serial_entry_mode',
            field=models.CharField(choices=[('off', 'بدون أرقام تسلسلية'), ('optional', 'اختياري'), ('required', 'إجباري')], db_column='SerialEntryMode', default='off', help_text='اختيار الأرقام التسلسلية في بنود فاتورة البيع: بدون/اختياري/إجباري', max_length=20),
        ),
    ]
