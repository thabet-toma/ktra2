"""#237 — الخطوة ١ من ٣: عمود `verify_token` يقبل NULL بلا فرادة.

ثلاث خطوات لا واحدة: إضافةُ عمودٍ فريدٍ غير nullable على جدولٍ فيه صفوف تُعطي
كل الصفوف القيمة الافتراضية نفسها فتنكسر الفرادة. فيُضاف فارغاً (هذه)، ثم تُملأ
الصفوف (0015)، ثم يُشدَّد (0016).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('after_sales', '0013_warrantycard_void_and_service_order_warranty_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='warrantycard',
            name='verify_token',
            field=models.CharField(editable=False, max_length=22, null=True),
        ),
    ]
