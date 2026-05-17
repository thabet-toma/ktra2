"""
إضافة حقول نوع الدفع إلى PurchaseInvoice:
- payment_type: credit (ذمم مورد) | cash (صندوق/بنك)
- cash_or_bank_account: الحساب المُخصم منه عند الدفع النقدي
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0020_purchase_invoice_fees"),
        ("accounting", "0013_seed_import_accounts_and_fix_vat"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoice",
            name="payment_type",
            field=models.CharField(
                max_length=10,
                choices=[("credit", "آجل (ذمم مورد)"), ("cash", "نقدي (صندوق/بنك)")],
                default="credit",
                db_column="PaymentType",
                help_text="credit: دائنة على ذمم المورد | cash: يُخصم من صندوق/بنك مباشرة",
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="cash_or_bank_account",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="accounting.account",
                db_column="CashBankAccountID",
                related_name="purchase_invoices_paid_from",
                help_text="حساب الصندوق/البنك — مطلوب عند payment_type=cash",
            ),
        ),
    ]
