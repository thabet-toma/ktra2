# ISSUE #52 — زبون المكتب: الربط الثاني الاختياري بدفتر مُدار (`managed_tenant`).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0026_tenant_managed_by'),
        ('accountant_portal', '0003_practiceclient_practiceprogram_practicedocument_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='practiceclient',
            name='managed_tenant',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='practice_clients', to='tenants.tenant',
            ),
        ),
    ]
