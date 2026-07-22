# Generated manually to fix DB/schema drift.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics", "0004_add_missing_logistics_deal_columns"),
    ]

    # هجرة ترقيع انحراف: كُتبت يدوياً لأعمدة كانت مفقودة من قاعدة الإنتاج القديمة.
    # على قاعدة نظيفة تُنشئها الهجرات الأولى أصلاً ⇒ DDL هنا = "Duplicate column".
    # الأثر محفوظ على الحالة فقط؛ وقد طُبِّق على الإنتاج قبل هذا التعديل.
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
            migrations.AddField(
                model_name="logisticspayment",
                name="usd_to_ils",
                field=models.DecimalField(
                    default=3.5,
                    max_digits=18,
                    decimal_places=6,
                    db_column="usd_to_ils",
                ),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="transfer_cost",
                field=models.DecimalField(
                    default=0.00,
                    max_digits=18,
                    decimal_places=2,
                    db_column="transfer_cost",
                ),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="bank_swift_image",
                field=models.CharField(
                    blank=True,
                    max_length=500,
                    null=True,
                    db_column="bank_swift_image",
                ),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="supplier_confirmation_image",
                field=models.CharField(
                    blank=True,
                    max_length=500,
                    null=True,
                    db_column="supplier_confirmation_image",
                ),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="supplier_notes",
                field=models.TextField(
                    blank=True,
                    null=True,
                    db_column="supplier_notes",
                ),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="confirmed_by_supplier",
                field=models.BooleanField(
                    default=False,
                    db_column="confirmed_by_supplier",
                ),
            ),
            ],
        ),
    ]
