from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0009_logisticspayment_cash_box_external_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="logisticsdeal",
            name="shipping_workflow_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("sw_mfg_start", "Start manufacturing"),
                    ("sw_wait_agent_ship", "Mfg done wait ship to agent"),
                    ("sw_wait_intl_ship", "At agent wait international ship"),
                    ("sw_wait_arrival", "Wait shipment arrival"),
                    ("sw_wait_clearance", "Wait clearance"),
                    ("sw_released", "Released cleared"),
                ],
                db_column="shipping_workflow_status",
                max_length=32,
                null=True,
            ),
        ),
    ]
