import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics", "0011_logisticsshipment_shipment_route_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="logisticspayment",
            name="deal",
            field=models.ForeignKey(
                blank=True,
                db_column="DealID",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payments",
                to="logistics.logisticsdeal",
            ),
        ),
        migrations.AddField(
            model_name="logisticspayment",
            name="shipment",
            field=models.ForeignKey(
                blank=True,
                db_column="LinkedShipmentID",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="agent_payments",
                to="logistics.logisticsshipment",
            ),
        ),
    ]
