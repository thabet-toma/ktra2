# #283/ب: صفُّ «كشف حساب الأتعاب» (هويّةُ مستند `fee_statement` في `docshare`)،
# ونوعُ تذكيرٍ خامس `fee_receipt` في اختيارات حقول التذكير الأربعة.
# إضافيّةٌ محضة: `CreateModel` واحد و`AlterField` على `choices` وحدها — **بلا
# `RunSQL` ولا `RemoveField` ولا `DeleteModel` ولا `RunPython`**، ولا بياناتَ
# أولية (القيمُ الافتراضية في السجلّ لا في صفوف).
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting_office', '0015_office_client_partner'),
        ('tenants', '0037_alter_rolepermission_role_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientreminderrecipient',
            name='reminder_type',
            field=models.CharField(choices=[('documents', 'أوراق ناقصة'), ('deadline', 'موعد رسمي قريب'), ('balance', 'اللي عليه'), ('appointment', 'تذكير موعد'), ('fee_receipt', 'إشعار قبض')], max_length=20, verbose_name='نوع التذكير'),
        ),
        migrations.AlterField(
            model_name='reminderlog',
            name='reminder_type',
            field=models.CharField(choices=[('documents', 'أوراق ناقصة'), ('deadline', 'موعد رسمي قريب'), ('balance', 'اللي عليه'), ('appointment', 'تذكير موعد'), ('fee_receipt', 'إشعار قبض')], max_length=20, verbose_name='نوع التذكير'),
        ),
        migrations.AlterField(
            model_name='reminderpostpone',
            name='reminder_type',
            field=models.CharField(choices=[('documents', 'أوراق ناقصة'), ('deadline', 'موعد رسمي قريب'), ('balance', 'اللي عليه'), ('appointment', 'تذكير موعد'), ('fee_receipt', 'إشعار قبض')], max_length=20, verbose_name='نوع التذكير'),
        ),
        migrations.AlterField(
            model_name='remindertemplate',
            name='reminder_type',
            field=models.CharField(choices=[('documents', 'أوراق ناقصة'), ('deadline', 'موعد رسمي قريب'), ('balance', 'اللي عليه'), ('appointment', 'تذكير موعد'), ('fee_receipt', 'إشعار قبض')], max_length=20, verbose_name='نوع التذكير'),
        ),
        migrations.CreateModel(
            name='FeeStatement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_from', models.DateField(verbose_name='من تاريخ')),
                ('period_to', models.DateField(verbose_name='إلى تاريخ')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإصدار')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fee_statements', to='accounting_office.officeclient', verbose_name='الزبون')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='office_fee_statements', to=settings.AUTH_USER_MODEL, verbose_name='أصدره')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='office_fee_statements', to='tenants.tenant', verbose_name='المكتب')),
            ],
            options={
                'verbose_name': 'كشف حساب أتعاب',
                'verbose_name_plural': 'كشوف حسابات الأتعاب',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['tenant', 'client', 'created_at'], name='office_fee_statement_client')],
            },
        ),
    ]
