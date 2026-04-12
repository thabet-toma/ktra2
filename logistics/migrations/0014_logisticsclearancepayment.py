from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("partners", "0001_initial"),
        ("accounting", "0004_cashboxledgeraccount"),
        ("logistics", "0013_logisticsclearance_cost_lines"),
    ]

    operations = [
        migrations.CreateModel(
            name="LogisticsClearancePayment",
            fields=[
                ("id", models.AutoField(db_column="ClearancePaymentID", primary_key=True, serialize=False)),
                ("amount", models.DecimalField(db_column="Amount", decimal_places=2, max_digits=18)),
                ("payment_date", models.DateField(blank=True, db_column="PaymentDate", null=True)),
                ("cash_box_external_id", models.CharField(db_column="CashBoxExternalID", max_length=128)),
                ("notes", models.TextField(blank=True, db_column="Notes", null=True)),
                ("is_posted", models.BooleanField(db_column="IsPosted", default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_column="CreatedAt")),
                ("clearance", models.ForeignKey(db_column="ClearanceID", on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="logistics.logisticsclearance")),
                ("customs_broker", models.ForeignKey(blank=True, db_column="CustomsBrokerID", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="clearance_payments", to="partners.partner")),
                ("journal", models.ForeignKey(blank=True, db_column="JournalID", null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounting.journalheader")),
                ("tenant", models.ForeignKey(db_column="TenantID", default=1, on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant")),
            ],
            options={
                "db_table": "logistics_clearance_payments",
                "managed": True,
            },
        ),
        migrations.AddIndex(
            model_name="logisticsclearancepayment",
            index=models.Index(fields=["clearance", "payment_date"], name="logistics_l_clearan_4d1c2a_idx"),
        ),
        migrations.AddIndex(
            model_name="logisticsclearancepayment",
            index=models.Index(fields=["tenant", "cash_box_external_id"], name="logistics_l_tenant__24c8f5_idx"),
        ),
    ]

