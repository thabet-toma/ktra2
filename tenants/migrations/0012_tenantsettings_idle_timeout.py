# tenants: per-company session idle timeout (minutes) on TenantSettings.
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0011_tenantsettings_appearance'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsettings',
            name='idle_timeout_minutes',
            field=models.PositiveIntegerField(
                db_column='IdleTimeoutMinutes', default=180,
                help_text='مهلة إنهاء الجلسة عند الخمول بالدقائق (5..1440)',
                validators=[
                    django.core.validators.MinValueValidator(5),
                    django.core.validators.MaxValueValidator(1440),
                ],
            ),
        ),
    ]
