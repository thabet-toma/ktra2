from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_product_allow_negative_stock_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_service",
            field=models.BooleanField(
                db_column="IsService",
                default=False,
                help_text="إذا مفعّل: يُعامل الصنف كخدمة — لا يُخصم من المخزون ويُرحّل لحساب مبيعات الخدمات",
            ),
        ),
    ]
