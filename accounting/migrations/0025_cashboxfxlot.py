from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0024_voidedjournal'),
    ]

    operations = [
        migrations.CreateModel(
            name='CashBoxFxLot',
            fields=[
                ('id', models.AutoField(db_column='CashBoxFxLotID', primary_key=True, serialize=False)),
                ('lot_date', models.DateField(db_column='LotDate')),
                ('original_fc', models.DecimalField(db_column='OriginalFC', decimal_places=4, help_text='المبلغ الأصلي بالعملة الأجنبية', max_digits=18)),
                ('remaining_fc', models.DecimalField(db_column='RemainingFC', decimal_places=4, help_text='المتبقي بالعملة الأجنبية (يُستهلَك FIFO)', max_digits=18)),
                ('rate', models.DecimalField(db_column='Rate', decimal_places=6, help_text='سعر صرف الطبقة: شيقل لكل وحدة عملة أجنبية', max_digits=18)),
                ('source', models.CharField(choices=[('capital', 'إيداع من رأس المال'), ('transfer_ils', 'تحويل من صندوق الشيقل')], db_column='Source', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='CreatedAt')),
                ('cash_box', models.ForeignKey(db_column='CashBoxLedgerID', help_text='صندوق العملة الأجنبية صاحب الطبقة', on_delete=django.db.models.deletion.CASCADE, related_name='fx_lots', to='accounting.cashboxledgeraccount')),
                ('journal', models.ForeignKey(blank=True, db_column='JournalID', help_text='قيد التمويل', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fx_lots', to='accounting.journalheader')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
            ],
            options={
                'db_table': 'cash_box_fx_lots',
                'ordering': ['lot_date', 'id'],
                'managed': True,
            },
        ),
    ]
