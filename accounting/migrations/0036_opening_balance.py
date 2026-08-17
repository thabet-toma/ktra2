"""T119-1 — مستند الأرصدة الافتتاحية وبنوده (حسابات + بضاعة أول المدة).

ثلاثة جداول جديدة فقط، بلا أي تعديل على جدول قائم — فلا إعادة كتابة لجدول فيه
بيانات شركات حقيقية، والهجرة آمنة على الإنتاج.

**لا قيد فريد شرطي هنا عمداً.** «قيد افتتاحي مرحّل واحد لكل شركة» يبدو مرشحاً
لـ`UniqueConstraint(condition=Q(status='posted'))`، لكن MySQL لا يدعم الفهارس
الجزئية (`supports_partial_indexes = False` في backend الـMySQL) فيُنشأ القيد في
قاعدة الاختبارات (SQLite) **ويغيب بصمت عن الإنتاج** — أي حارسٌ أخضر في
الاختبارات لا وجود له حيث تعيش البيانات. الثابت نفسه لم يتغيّر؛ يفرضه
`accounting/opening_balance.py` (`post_opening_balance`) داخل المعاملة تحت
`select_for_update`. القيود الفريدة أدناه غير مشروطة فتعمل على المحرّكين معاً.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0035_account_sub_type'),
        ('inventory', '0017_phase5_p0_indexes'),
        ('tenants', '0020_membership_ui_mode'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OpeningBalance',
            fields=[
                ('id', models.AutoField(db_column='OpeningBalanceID', primary_key=True, serialize=False)),
                ('start_date', models.DateField(blank=True, db_column='StartDate', help_text='تاريخ بدء التشغيل على النظام — أول يوم عمل فعلي', null=True)),
                ('entry_date', models.DateField(blank=True, db_column='EntryDate', help_text='تاريخ القيد الافتتاحي = تاريخ البدء ناقص يوماً (يُشتقّ تلقائياً)', null=True)),
                ('status', models.CharField(choices=[('draft', 'مسودة'), ('posted', 'مرحّل')], db_column='Status', default='draft', max_length=20)),
                ('posted_at', models.DateTimeField(blank=True, db_column='PostedAt', null=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='CreatedBy_UserID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opening_balances', to=settings.AUTH_USER_MODEL)),
                ('journal', models.ForeignKey(blank=True, db_column='JournalID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opening_balances', to='accounting.journalheader')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, related_name='opening_balances', to='tenants.tenant')),
            ],
            options={
                'db_table': 'opening_balances',
                'ordering': ['-id'],
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='OpeningBalanceAccountLine',
            fields=[
                ('id', models.AutoField(db_column='OpeningBalanceLineID', primary_key=True, serialize=False)),
                ('debit', models.DecimalField(db_column='Debit', decimal_places=2, default=0, max_digits=18)),
                ('credit', models.DecimalField(db_column='Credit', decimal_places=2, default=0, max_digits=18)),
                ('notes', models.CharField(blank=True, db_column='Notes', default='', max_length=500)),
                ('account', models.ForeignKey(db_column='AccountID', on_delete=django.db.models.deletion.PROTECT, related_name='opening_balance_lines', to='accounting.account')),
                ('opening', models.ForeignKey(db_column='OpeningBalanceID', on_delete=django.db.models.deletion.CASCADE, related_name='account_lines', to='accounting.openingbalance')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
            ],
            options={
                'db_table': 'opening_balance_account_lines',
                'managed': True,
                'constraints': [models.UniqueConstraint(fields=('opening', 'account'), name='uniq_opening_account'), models.CheckConstraint(condition=models.Q(('debit__gte', 0)), name='opening_account_debit_non_negative'), models.CheckConstraint(condition=models.Q(('credit__gte', 0)), name='opening_account_credit_non_negative')],
            },
        ),
        migrations.CreateModel(
            name='OpeningBalanceStockLine',
            fields=[
                ('id', models.AutoField(db_column='OpeningBalanceStockLineID', primary_key=True, serialize=False)),
                ('quantity', models.DecimalField(db_column='Quantity', decimal_places=4, max_digits=18)),
                ('unit_cost', models.DecimalField(db_column='UnitCost', decimal_places=4, max_digits=18)),
                ('opening', models.ForeignKey(db_column='OpeningBalanceID', on_delete=django.db.models.deletion.CASCADE, related_name='stock_lines', to='accounting.openingbalance')),
                ('product', models.ForeignKey(db_column='ProductID', on_delete=django.db.models.deletion.PROTECT, related_name='opening_balance_lines', to='inventory.product')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
                ('warehouse', models.ForeignKey(db_column='WarehouseID', on_delete=django.db.models.deletion.PROTECT, related_name='opening_balance_lines', to='inventory.warehouse')),
            ],
            options={
                'db_table': 'opening_balance_stock_lines',
                'managed': True,
                'constraints': [models.UniqueConstraint(fields=('opening', 'product', 'warehouse'), name='uniq_opening_product_warehouse'), models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='opening_stock_quantity_positive'), models.CheckConstraint(condition=models.Q(('unit_cost__gte', 0)), name='opening_stock_unit_cost_non_negative')],
            },
        ),
    ]
