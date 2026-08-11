from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('partners', '0007_customer_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='partnerbankaccount',
            name='branch_name',
            field=models.CharField(blank=True, db_column='BranchName', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='partnerbankaccount',
            name='is_default',
            field=models.BooleanField(db_column='IsDefault', default=False),
        ),
    ]
