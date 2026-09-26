from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0047_party_refund_allocations'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierpayment',
            name='adjust_surplus',
            field=models.DecimalField(db_column='AdjustSurplus', decimal_places=2, default=0, max_digits=18),
        ),
    ]
