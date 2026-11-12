"""رابطُ تقرير دفتر زبون (#288/ب-١) — `CreateModel` وحده.

الجدولُ **لا يحمل أرقاماً**: التقريرُ يُحسَب من الدفتر عند كل فتح
(`accounting_office/book_reports.py`)، والصفُّ يقول أيُّ تقريرٍ على أيّ فترةٍ
طُلب له رابطُ مشاركة. ولذلك لا هجرةَ بياناتٍ هنا: لا شيءَ يُنقل من الدفتر.

والفهرسُ `(tenant, client_book)` لقرار «هل لهذا الدفتر رابطٌ على هذه الفترة؟»
الذي يمنع تكرارَ الصفوف عند إعادة المشاركة.
"""
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
        migrations.CreateModel(
            name='ClientBookReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=32, verbose_name='نوع التقرير')),
                ('period_from', models.DateField(verbose_name='من')),
                ('period_to', models.DateField(verbose_name='إلى')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('client_book', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shared_reports', to='accounting_office.clientbook', verbose_name='الدفتر')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='office_client_book_reports', to=settings.AUTH_USER_MODEL, verbose_name='أنشأه')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='office_client_book_reports', to='tenants.tenant', verbose_name='المكتب')),
            ],
            options={
                'verbose_name': 'رابط تقرير دفتر زبون',
                'verbose_name_plural': 'روابط تقارير دفاتر الزبائن',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['tenant', 'client_book'], name='office_book_report_tenant')],
            },
        ),
    ]
