from django.db import migrations, models


class Migration(migrations.Migration):
    """صلاحية وحدة الاستيراد (نموذج من مستويين).

    Tenant.import_enabled — يضبطه السوبر أدمن لكل شركة.
    UserCompanyMembership.can_access_import — يضبطه مدير الشركة لكل عضو.
    """

    dependencies = [
        ('tenants', '0009_operational_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='import_enabled',
            field=models.BooleanField(default=False, db_column='ImportEnabled'),
        ),
        migrations.AddField(
            model_name='usercompanymembership',
            name='can_access_import',
            field=models.BooleanField(default=False, db_column='CanAccessImport'),
        ),
    ]
