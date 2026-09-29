from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('after_sales', '0017_warrantycard_end_reason_withdrawn'),
    ]

    operations = [
        migrations.AddField(
            model_name='warrantycard',
            name='phone_key',
            field=models.CharField(blank=True, default='', editable=False, max_length=9),
        ),
        migrations.AddIndex(
            model_name='warrantycard',
            index=models.Index(fields=['tenant', 'phone_key'], name='warranty_tenant_phone_idx'),
        ),
    ]
