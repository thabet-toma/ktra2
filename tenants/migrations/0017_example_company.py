from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0016_tenantsettings_dashboard_month_start_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='is_example',
            field=models.BooleanField(db_column='IsExample', default=False),
        ),
        migrations.AddField(
            model_name='usercompanymembership',
            name='is_example_access',
            field=models.BooleanField(db_column='IsExampleAccess', default=False),
        ),
    ]
