from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0018_landed_cost_phase_a"),
    ]

    operations = [
        migrations.AlterField(
            model_name="logisticsdeal",
            name="tax_rate",
            field=models.DecimalField(
                db_column="tax_rate",
                decimal_places=4,
                default=0.0,
                max_digits=10,
            ),
        ),
        migrations.AlterField(
            model_name="purchaseinvoice",
            name="tax_rate",
            field=models.DecimalField(
                db_column="TaxRate",
                decimal_places=4,
                default=0,
                max_digits=10,
            ),
        ),
    ]
