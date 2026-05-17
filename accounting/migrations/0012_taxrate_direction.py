"""
إضافة حقل `direction` إلى TaxRate لتمييز ضريبة المبيعات (Output) عن ضريبة المشتريات (Input).
- sales   → ضريبة مخرجات (مطلوب أن يكون tax_account من نوع Liability)
- purchase → ضريبة مدخلات (مطلوب أن يكون tax_account من نوع Asset)
- both    → للاستخدام المؤقت/المختلط
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0011_ensure_default_vat16_per_tenant"),
    ]

    operations = [
        migrations.AddField(
            model_name="taxrate",
            name="direction",
            field=models.CharField(
                max_length=10,
                choices=[
                    ("sales", "Sales / Output"),
                    ("purchase", "Purchase / Input"),
                    ("both", "Both"),
                ],
                default="both",
                db_column="Direction",
                help_text="اتجاه الضريبة: sales (مخرجات) / purchase (مدخلات) / both",
            ),
        ),
    ]
