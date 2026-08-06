from django.db import migrations, models


class Migration(migrations.Migration):
    """صور توضيحية للملاحظة، وإسقاط عمود «المسؤول» غير المستعمَل (بطلب المالك)."""

    dependencies = [
        ('core', '0005_tenantmodule'),
    ]

    operations = [
        migrations.AddField(
            model_name='developmentnote',
            name='images',
            field=models.JSONField(
                blank=True, default=list,
                help_text='[{url,caption}] صور توضيحية مرفوعة للملاحظة',
            ),
        ),
        migrations.RemoveField(
            model_name='developmentnote',
            name='assignee',
        ),
    ]
