# partners: CustomerNote (CRM notes + reminders on the customer card).
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('partners', '0006_n9_t8_partner_row_color'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerNote',
            fields=[
                ('id', models.AutoField(db_column='CustomerNoteID', primary_key=True, serialize=False)),
                ('title', models.CharField(db_column='Title', max_length=200)),
                ('body', models.TextField(blank=True, db_column='Body', default='')),
                ('remind_on', models.DateField(blank=True, db_column='RemindOn', help_text='يوم التذكير — يظهر في إشعارات الموقع عند حلوله', null=True)),
                ('is_done', models.BooleanField(db_column='IsDone', default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='CreatedAt')),
                ('updated_at', models.DateTimeField(auto_now=True, db_column='UpdatedAt')),
                ('created_by', models.ForeignKey(blank=True, db_column='CreatedBy_UserID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('partner', models.ForeignKey(db_column='PartnerID', on_delete=django.db.models.deletion.CASCADE, related_name='notes', to='partners.partner')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, related_name='customer_notes', to='tenants.tenant')),
            ],
            options={
                'db_table': 'partner_customer_notes',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='customernote',
            index=models.Index(fields=['tenant', 'partner', '-created_at'], name='pcn_tenant_partner_created'),
        ),
        migrations.AddIndex(
            model_name='customernote',
            index=models.Index(fields=['tenant', 'is_done', 'remind_on'], name='pcn_tenant_done_remind'),
        ),
    ]
