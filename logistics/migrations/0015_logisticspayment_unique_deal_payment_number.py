from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0014_logisticsclearancepayment"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="logisticspayment",
            constraint=models.UniqueConstraint(
                fields=["deal", "payment_number"],
                condition=models.Q(is_deleted=False),
                name="unique_active_deal_payment_number",
            ),
        ),
    ]
