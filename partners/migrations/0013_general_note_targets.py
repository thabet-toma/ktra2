from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('partners', '0012_alter_partner_partner_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customernote',
            name='partner',
            field=models.ForeignKey(
                blank=True, db_column='PartnerID', null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notes', to='partners.partner',
            ),
        ),
        migrations.AddField(
            model_name='customernote',
            name='target_type',
            field=models.CharField(
                blank=True, db_column='TargetType', default='',
                help_text='نوع الهدف العام، مثل supplier_quotation أو page', max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='customernote',
            name='target_id',
            field=models.CharField(
                blank=True, db_column='TargetID', default='',
                help_text='معرّف ثابت للهدف داخل نوعه', max_length=100,
            ),
        ),
        migrations.AddField(
            model_name='customernote',
            name='target_label',
            field=models.CharField(
                blank=True, db_column='TargetLabel', default='',
                help_text='اسم الهدف كما يظهر في التذكير', max_length=200,
            ),
        ),
        migrations.AddField(
            model_name='customernote',
            name='target_path',
            field=models.CharField(
                blank=True, db_column='TargetPath', default='',
                help_text='مسار داخلي يبدأ بـ / للعودة إلى الهدف', max_length=500,
            ),
        ),
        migrations.AddIndex(
            model_name='customernote',
            index=models.Index(
                fields=['tenant', 'target_type', 'target_id'], name='pcn_tenant_target',
            ),
        ),
    ]
