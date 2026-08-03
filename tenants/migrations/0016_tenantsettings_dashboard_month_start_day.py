import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0015_memberpermission'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsettings',
            name='dashboard_month_start_day',
            field=models.PositiveSmallIntegerField(
                db_column='DashboardMonthStartDay',
                default=1,
                help_text='يوم بداية شهر ملخص الأعمال (1..31)',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(31),
                ],
            ),
        ),
    ]
