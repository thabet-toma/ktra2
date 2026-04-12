from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0004_cashboxledgeraccount'),
    ]

    operations = [
        migrations.AddField(
            model_name='journalline',
            name='description',
            field=models.CharField(blank=True, db_column='LineDescription', max_length=500, null=True),
        ),
    ]
