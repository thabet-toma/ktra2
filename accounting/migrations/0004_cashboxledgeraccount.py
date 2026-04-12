# Generated manually for cash box GL links

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("accounting", "0003_account_parent_account_tenant_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashBoxLedgerAccount",
            fields=[
                ("id", models.AutoField(db_column="CashBoxLedgerID", primary_key=True, serialize=False)),
                ("external_id", models.CharField(db_column="ExternalID", max_length=128)),
                ("name", models.CharField(db_column="Name", max_length=200)),
                ("currency_code", models.CharField(db_column="CurrencyCode", default="USD", max_length=3)),
                (
                    "account",
                    models.OneToOneField(
                        db_column="AccountID",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cash_box_ledger",
                        to="accounting.account",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_column="TenantID",
                        default=1,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "cash_box_ledger_accounts",
                "managed": True,
                "unique_together": {("tenant", "external_id")},
            },
        ),
    ]
