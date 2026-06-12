# task14 M2 (DEF-A5): عمود تاريخ الإنشاء — الصفوف القائمة تأخذ تاريخ الترحيل
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_stockmovement_branch'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                db_column='CreatedAt',
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
    ]
