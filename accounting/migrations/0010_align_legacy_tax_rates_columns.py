"""
قواعد قديمة: tax_rates بأعمدة TaxName فقط بدون Name/Code/TaxAccountID — يُسبب 500 عند قراءة TaxRate.
"""

from django.db import migrations


def align_legacy_tax_rates(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "mysql":
        return

    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM tax_rates")
        cols = [row[0] for row in cursor.fetchall()]

    # TaxName → Name (كما يتوقف النموذج)
    if "TaxName" in cols and "Name" not in cols:
        schema_editor.execute(
            "ALTER TABLE tax_rates CHANGE COLUMN TaxName Name VARCHAR(100) NOT NULL"
        )
        cols = [c for c in cols if c != "TaxName"] + ["Name"]

    if "Code" not in cols:
        schema_editor.execute(
            "ALTER TABLE tax_rates ADD COLUMN Code VARCHAR(20) NOT NULL DEFAULT '' AFTER Name"
        )
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE tax_rates SET Code = CONCAT('T', TaxRateID) WHERE Code = '' OR Code IS NULL"
            )

    if "TaxAccountID" not in cols:
        schema_editor.execute("ALTER TABLE tax_rates ADD COLUMN TaxAccountID INT NULL")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tax_rates tr
                SET TaxAccountID = (
                    SELECT MIN(c.AccountID) FROM chartofaccounts c WHERE c.TenantID = tr.TenantID
                )
                WHERE TaxAccountID IS NULL
                """
            )
            cursor.execute(
                """
                UPDATE tax_rates
                SET TaxAccountID = (SELECT MIN(AccountID) FROM chartofaccounts)
                WHERE TaxAccountID IS NULL
                """
            )
        schema_editor.execute(
            "ALTER TABLE tax_rates MODIFY COLUMN TaxAccountID INT NOT NULL"
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("accounting", "0009_tax_rates_ensure_code_column"),
    ]

    operations = [
        migrations.RunPython(align_legacy_tax_rates, noop_reverse),
    ]
