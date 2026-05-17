# قواعد MySQL قديمة: جدول tax_rates بدون عمود Code يُسبب OperationalError وبالتالي 500 على /api/accounting/tax-rates/

from django.db import migrations


def ensure_code_column(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "mysql":
        return
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'tax_rates'
              AND COLUMN_NAME = 'Code'
            """
        )
        if cursor.fetchone()[0]:
            return
    try:
        schema_editor.execute(
            "ALTER TABLE tax_rates ADD COLUMN Code VARCHAR(20) NOT NULL DEFAULT ''"
        )
    except Exception:
        return
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE tax_rates SET Code = CONCAT('T', TaxRateID) WHERE Code = '' OR Code IS NULL"
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0008_add_base_currency_fields"),
    ]

    operations = [
        migrations.RunPython(ensure_code_column, noop_reverse),
    ]
