# partners: أولوية ملاحظة الطرف (عاجل/متوسط/عادي) — «عاجل» تُنبّه عند المعاملات.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('partners', '0008_partnerbankaccount_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='customernote',
            name='priority',
            field=models.CharField(
                choices=[('urgent', 'عاجل'), ('medium', 'متوسط'), ('normal', 'عادي')],
                db_column='Priority', default='normal',
                help_text='أولوية الملاحظة — «عاجل» تُنبّه عند أي معاملة للطرف بعد حلول موعدها',
                max_length=10,
            ),
        ),
        migrations.AddIndex(
            model_name='customernote',
            index=models.Index(
                fields=['tenant', 'partner', 'priority', 'is_done'],
                name='pcn_tenant_partner_prio',
            ),
        ),
    ]
