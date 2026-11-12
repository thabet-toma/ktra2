# #288/ب-٢: الضريبةُ المسجَّلةُ على بند الحركة — عمودان محضان.
#
# تقريرُ ض.ق.م للفترة يجمع هذين العمودين ولا يضرب مبلغاً في نسبةٍ حيّة: النسبةُ
# تتغيّر، وإقرارُ شهرٍ مضى لا يتغيّر. و`tax_base` عمودٌ ثالثٌ لا اشتقاقٌ من
# المدين/الدائن — بندٌ معفًى وخاضعٌ في الحركة نفسها يعطيان أساساً لا يساوي أيَّ
# مبلغٍ في البند. والافتراضُ صفرٌ فلا يتغيّر سلوكُ قيدٍ قائم.
#
# و`AlterField BookEntry.kind` توسيعُ الاختيارات بنوعَي «يدوي» و«رصيد افتتاحي»
# (خياراتٌ في الميتاداتا لا قيدٌ في القاعدة) — لا حذفَ ولا `RunSQL`.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting_office', '0019_client_book_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='bookentryline',
            name='tax_base',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=14,
                verbose_name='الأساس الخاضع للضريبة',
            ),
        ),
        migrations.AddField(
            model_name='bookentryline',
            name='tax_amount',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=14,
                verbose_name='قيمة الضريبة',
            ),
        ),
        migrations.AlterField(
            model_name='bookentry',
            name='kind',
            field=models.CharField(
                choices=[
                    ('sales_invoice', 'فاتورة بيع'),
                    ('purchase_invoice', 'فاتورة شراء'),
                    ('expense', 'مصروف'),
                    ('bank_movement', 'حركة بنك'),
                    ('daily_report', 'تقرير يومي'),
                    ('manual', 'يدوي'),
                    ('opening', 'رصيد افتتاحي'),
                ],
                max_length=20,
                verbose_name='نوع الحركة',
            ),
        ),
    ]
