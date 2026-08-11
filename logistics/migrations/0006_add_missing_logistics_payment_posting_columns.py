# Generated manually to fix DB/schema drift.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("logistics", "0005_add_missing_logistics_payment_columns"),
        ("accounting", "0003_account_parent_account_tenant_and_more"),
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
                name="is_posted",
                field=models.BooleanField(db_column="IsPosted", default=False),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="journal",
                field=models.ForeignKey(
                    blank=True,
                    null=True,
                    db_column="JournalID",
                    on_delete=django.db.models.deletion.SET_NULL,
                    to="accounting.journalheader",
                ),
            ),
            migrations.AddField(
                model_name="logisticspayment",
                name="bank_account",
                field=models.ForeignKey(
                    blank=True,
                    null=True,
                    db_column="BankAccountID",
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="payment_bank_entries",
                    to="accounting.account",
                ),
            ),
            ],
        ),
    ]
