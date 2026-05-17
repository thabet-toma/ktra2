"""
إضافة نموذج PurchaseInvoiceFee — لتمثيل رسوم فاتورة الشراء المنفصلة محاسبياً
(شحن، تخليص، رسوم جمركية، تأمين، ...). كل رسم مرتبط بحساب مصروف.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0019_widen_tax_rate_decimals"),
        ("accounting", "0013_seed_import_accounts_and_fix_vat"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseInvoiceFee",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False, db_column="FeeID")),
                ("description", models.CharField(max_length=255, db_column="Description", help_text="وصف الرسم (مثال: رسوم جمركية، شحن دولي، تخليص)")),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=18, db_column="Amount")),
                ("capitalize_to_inventory", models.BooleanField(default=False, db_column="CapitalizeToInventory", help_text="إذا True يُرسمل على المخزون (landed cost) بدل تسجيله كمصروف في الفترة")),
                ("is_taxable", models.BooleanField(default=False, db_column="IsTaxable", help_text="إذا True يُحتسب ضريبة VAT على هذا الرسم ضمن فاتورة الشراء")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_column="CreatedAt")),
                ("tenant", models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant", db_column="TenantID")),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to="logistics.purchaseinvoice",
                    db_column="PurchaseInvoiceID",
                    related_name="fees",
                )),
                ("expense_account", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to="accounting.account",
                    db_column="ExpenseAccountID",
                    related_name="purchase_invoice_fees",
                    help_text="الحساب المدين للرسم — عادةً حساب مصروف (5xxx) أو جزء من تكلفة المخزون",
                )),
            ],
            options={
                "db_table": "purchase_invoice_fees",
                "managed": True,
            },
        ),
    ]
