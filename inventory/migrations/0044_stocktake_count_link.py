# Generated manually — لا MySQL محلّياً، والهجرة بسيطة (CreateModel واحد).
# تطابقها مع النماذج يحرسه `makemigrations --check` في البوّابة.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """K3: صفّ رابط عدّ الجرد — مَن يعدّ ونطاق ما يراه.

    التوكن والانتهاء والإبطال في `docshare.DocumentShare` (OneToOne)، فلا
    عمودَ توكنٍ ثانٍ ولا آلةَ صلاحيةٍ ثانية.
    """

    dependencies = [
        ('docshare', '0005_add_warranty_certificate_doc_type'),
        ('inventory', '0043_stocktake_scope_counted_by'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StocktakeCountLink',
            fields=[
                ('id', models.AutoField(
                    db_column='StocktakeCountLinkID', primary_key=True,
                    serialize=False)),
                ('counter_name', models.CharField(
                    db_column='CounterName', max_length=80)),
                ('categories', models.JSONField(
                    blank=True, db_column='Categories', null=True)),
                ('finished_at', models.DateTimeField(
                    blank=True, db_column='FinishedAt', null=True)),
                ('created_at', models.DateTimeField(
                    auto_now_add=True, db_column='CreatedAt')),
                ('created_by', models.ForeignKey(
                    blank=True, db_column='CreatedByID', null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stocktake_count_links',
                    to=settings.AUTH_USER_MODEL)),
                ('share', models.OneToOneField(
                    db_column='DocumentShareID',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stocktake_count_link',
                    to='docshare.documentshare')),
                ('stocktake', models.ForeignKey(
                    db_column='StocktakeID',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='count_links', to='inventory.stocktake')),
                ('tenant', models.ForeignKey(
                    db_column='TenantID',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stocktake_count_links', to='tenants.tenant')),
            ],
            options={
                'db_table': 'stocktake_count_links',
                'managed': True,
                'ordering': ['-created_at', '-id'],
                'indexes': [
                    models.Index(
                        fields=['tenant', 'stocktake'], name='stk_count_link_idx'),
                ],
            },
        ),
    ]
