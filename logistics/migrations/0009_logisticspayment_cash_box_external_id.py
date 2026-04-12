from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0008_alter_logisticsdeal_total_weight_kg"),
    ]

    operations = [
        migrations.AddField(
            model_name="logisticspayment",
            name="cash_box_external_id",
            field=models.CharField(
                blank=True,
                db_column="cash_box_external_id",
                max_length=128,
                null=True,
            ),
        ),
    ]
