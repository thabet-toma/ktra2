from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0069_supplierquotation_supplier_draft_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseinvoiceitem',
            name='serials',
            field=models.JSONField(blank=True, db_column='Serials', default=list, help_text='أرقام تسلسلية للوحدات المشتراة في هذا البند (تُنشأ عند الاستلام)'),
        ),
        migrations.AddField(
            model_name='purchasesettings',
            name='serial_entry_mode',
            field=models.CharField(choices=[('off', 'بدون أرقام تسلسلية'), ('optional', 'اختياري'), ('required', 'إجباري')], db_column='SerialEntryMode', default='off', help_text='إدخال الأرقام التسلسلية في بنود فاتورة الشراء: بدون/اختياري/إجباري', max_length=20),
        ),
    ]
