import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_developmentnote_images'),
        ('tenants', '0018_alter_rolepermission_role_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantLimit',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('limit_key', models.CharField(db_column='LimitKey', max_length=40)),
                ('max_value', models.PositiveIntegerField(blank=True, db_column='MaxValue', help_text='NULL = بلا حدّ لهذه الشركة', null=True)),
                ('note', models.CharField(blank=True, db_column='Note', default='', max_length=120)),
                ('updated_at', models.DateTimeField(auto_now=True, db_column='UpdatedAt')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, related_name='plan_limits', to='tenants.tenant')),
                ('updated_by', models.ForeignKey(blank=True, db_column='UpdatedBy_UserID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_tenant_limits', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tenant_limits',
                'constraints': [models.UniqueConstraint(fields=('tenant', 'limit_key'), name='uniq_tenant_limit')],
            },
        ),
    ]
