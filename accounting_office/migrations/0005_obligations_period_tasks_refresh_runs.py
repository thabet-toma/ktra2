"""الالتزامات والشغلات وسجلُّ تحديث المكتب — #275.

**نموذجان جديدان وثالثٌ للسجلّ**: الشغلةُ (`PeriodTask`) خدمةُ زبونٍ × فترة،
والالتزامُ (`Obligation`) سطرُ لائحةٍ محفوظٌ بفترته وتواريخه وحالته ومبلغه،
و`OfficeRefreshRun` صفٌّ واحدٌ لكل (مكتب، يوم) يُثبت تشغيلَ «حدّث المكتب مرّةً».

**والفرادةُ غير مشروطةٍ** في الثلاثة — الشرطُ في `UniqueConstraint` تتجاهله
MySQL بصمت فتمرّ الهجرة ويغيب القيد في الإنتاج.

**و`ClientService.last_period_ours`** عمودٌ افتراضُه «علينا»: إيقافُ خدمةٍ مع
«آخر فترةٍ ليست علينا» يمنع توليد التزاماتها، ويُسكِتُ ما كان منها منتظراً.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting_office', '0004_deadline_schedules'),
        ('tenants', '0037_alter_rolepermission_role_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='clientservice',
            name='last_period_ours',
            field=models.BooleanField(default=True, verbose_name='آخر فترة علينا'),
        ),
        migrations.CreateModel(
            name='PeriodTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField(verbose_name='بداية الفترة')),
                ('period_end', models.DateField(verbose_name='نهاية الفترة')),
                ('internal_deadline', models.DateField(verbose_name='الموعد الداخلي الأبكر')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('assignee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='office_period_tasks', to=settings.AUTH_USER_MODEL, verbose_name='المحوَّلة له')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tasks', to='accounting_office.officeclient', verbose_name='الزبون')),
                ('client_service', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tasks', to='accounting_office.clientservice', verbose_name='خدمة الزبون')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='office_period_tasks', to='tenants.tenant', verbose_name='المكتب')),
            ],
            options={
                'verbose_name': 'شغلة فترة',
                'verbose_name_plural': 'شغلات الفترات',
                'ordering': ['-period_end', '-id'],
            },
        ),
        migrations.CreateModel(
            name='Obligation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rule_code', models.SlugField(max_length=60, verbose_name='كود السطر')),
                ('name', models.CharField(max_length=200, verbose_name='الاسم')),
                ('origin', models.CharField(choices=[('official', 'رسمي'), ('office', 'من المكتب')], default='official', max_length=20, verbose_name='الأصل')),
                ('period_start', models.DateField(verbose_name='بداية الفترة')),
                ('period_end', models.DateField(verbose_name='نهاية الفترة')),
                ('legal_date', models.DateField(verbose_name='التاريخ بالقاعدة')),
                ('official_date', models.DateField(verbose_name='الموعد الرسمي')),
                ('actual_deadline', models.DateField(verbose_name='آخر موعد فعلي')),
                ('internal_deadline', models.DateField(verbose_name='الموعد الداخلي')),
                ('estimated', models.BooleanField(default=False, verbose_name='تقديري')),
                ('postponed', models.BooleanField(default=False, verbose_name='مؤجَّل')),
                ('warnings', models.JSONField(blank=True, default=list, verbose_name='تنبيهات')),
                ('status', models.CharField(choices=[('pending', 'لسا ما انقدّم'), ('submitted', 'انقدّم'), ('not_required', 'مش لازم هالفترة')], default='pending', max_length=20, verbose_name='الحالة')),
                ('submitted_on', models.DateField(blank=True, null=True, verbose_name='تاريخ التقديم')),
                ('submission_number', models.CharField(blank=True, default='', max_length=60, verbose_name='رقم التقديم')),
                ('prior_to_office', models.BooleanField(default=False, verbose_name='انقدّم قبل المكتب')),
                ('amount', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name='المبلغ')),
                ('direction', models.CharField(blank=True, choices=[('due', 'عليه'), ('refund', 'إله')], default='', max_length=10, verbose_name='الاتجاه')),
                ('client_paid', models.BooleanField(default=False, verbose_name='الزبون دفع')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obligations', to='accounting_office.officeclient', verbose_name='الزبون')),
                ('client_service', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obligations', to='accounting_office.clientservice', verbose_name='خدمة الزبون')),
                ('rule', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obligations', to='accounting_office.deadlinerule', verbose_name='سطر اللائحة')),
                ('submitted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='office_submitted_obligations', to=settings.AUTH_USER_MODEL, verbose_name='قدّمها')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='office_obligations', to='tenants.tenant', verbose_name='المكتب')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obligations', to='accounting_office.periodtask', verbose_name='شغلة الفترة')),
            ],
            options={
                'verbose_name': 'التزام',
                'verbose_name_plural': 'الالتزامات',
                'ordering': ['actual_deadline', 'internal_deadline', 'id'],
            },
        ),
        migrations.CreateModel(
            name='OfficeRefreshRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(verbose_name='اليوم')),
                ('ran_at', models.DateTimeField(auto_now_add=True, verbose_name='وقت التشغيل')),
                ('created_obligations', models.PositiveIntegerField(default=0, verbose_name='التزامات أُنشئت')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='office_refresh_runs', to='tenants.tenant', verbose_name='المكتب')),
            ],
            options={
                'verbose_name': 'تشغيل تحديث مكتب',
                'verbose_name_plural': 'تشغيلات تحديث المكاتب',
                'ordering': ['-day', '-id'],
                'constraints': [models.UniqueConstraint(fields=('tenant', 'day'), name='uniq_office_refresh_run_day')],
            },
        ),
        migrations.AddIndex(
            model_name='periodtask',
            index=models.Index(fields=['tenant', 'assignee'], name='office_task_tenant_assignee'),
        ),
        migrations.AddConstraint(
            model_name='periodtask',
            constraint=models.UniqueConstraint(fields=('client_service', 'period_start', 'period_end'), name='uniq_period_task_span'),
        ),
        migrations.AddIndex(
            model_name='obligation',
            index=models.Index(fields=['tenant', 'status'], name='office_oblig_tenant_status'),
        ),
        migrations.AddConstraint(
            model_name='obligation',
            constraint=models.UniqueConstraint(fields=('client_service', 'rule_code', 'period_end'), name='uniq_obligation_period_rule'),
        ),
    ]
