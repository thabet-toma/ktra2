from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('logistics', '0066_supplierquotation_notes_log_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierquotation',
            name='order_description',
            field=models.TextField(blank=True, db_column='OrderDescription', default=''),
        ),
        migrations.AddField(
            model_name='supplierquotation',
            name='order_name',
            field=models.CharField(blank=True, db_column='OrderName', default='', max_length=200),
        ),
    ]
