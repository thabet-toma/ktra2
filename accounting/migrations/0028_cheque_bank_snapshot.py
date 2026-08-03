from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0027_cheque_supplier_payment'),
    ]

    operations = [
        migrations.AddField(
            model_name='cheque',
            name='account_number',
            field=models.CharField(blank=True, db_column='AccountNumber', max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='cheque',
            name='bank_branch',
            field=models.CharField(blank=True, db_column='BankBranch', max_length=100, null=True),
        ),
    ]
