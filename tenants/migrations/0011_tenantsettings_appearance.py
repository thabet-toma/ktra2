# tenants: per-company appearance (font scale/family) on TenantSettings.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0010_import_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsettings',
            name='font_scale',
            field=models.CharField(db_column='FontScale', default='normal', help_text='small | normal | large | xlarge', max_length=10),
        ),
        migrations.AddField(
            model_name='tenantsettings',
            name='font_family',
            field=models.CharField(db_column='FontFamily', default='default', help_text='default | tahoma | segoe | arial', max_length=20),
        ),
    ]
