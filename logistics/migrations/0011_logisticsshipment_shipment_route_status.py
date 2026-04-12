from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0010_logisticsdeal_shipping_workflow_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="logisticsshipment",
            name="shipment_route_status",
            field=models.CharField(
                blank=True,
                db_column="shipment_route_status",
                max_length=64,
                null=True,
            ),
        ),
    ]
