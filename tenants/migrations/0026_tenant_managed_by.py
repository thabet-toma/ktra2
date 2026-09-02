# ISSUE #52 — الدفتر المُدار: مكتب المحاسبة المالك (`Tenant.managed_by`).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0025_tenant_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='managed_by',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='ManagedByTenantID',
                help_text='مكتب المحاسبة المالك لهذا الدفتر المُدار — فارغ يعني شركة عادية',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='managed_books', to='tenants.tenant',
            ),
        ),
    ]
