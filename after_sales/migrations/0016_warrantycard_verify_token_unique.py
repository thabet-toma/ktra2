"""#237 — الخطوة ٣ من ٣: `verify_token` غير nullable وفريد، ويُولَّد عند الإدراج."""
import after_sales.verify
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('after_sales', '0015_backfill_warranty_verify_tokens'),
    ]

    operations = [
        migrations.AlterField(
            model_name='warrantycard',
            name='verify_token',
            field=models.CharField(
                default=after_sales.verify.new_verify_token, editable=False,
                max_length=22, unique=True,
            ),
        ),
    ]
