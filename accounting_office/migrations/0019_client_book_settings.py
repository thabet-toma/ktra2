# #288/ب-٢: السنةُ المالية والعملة لكل زبون — **حقلان إضافيّان محضان** (#288/ب-٢).
#
# `fiscal_year_start` «شهر-يوم» نصّاً (`07-01`) لا تاريخاً بسنةٍ وهمية: لا تاريخَ
# حقيقيّ لبداية سنةٍ ماليةٍ يتكرّر كلَّ عام، و`DateField` كان يخزّن سنةً لا معنى
# لها ثم تُقرأ منها. والافتراضُ 1/1 فلا يتغيّر سلوكُ دفترٍ قائم.
# و`currency` رمزُ ISO 4217 كما تطلبه التذكرة، لا مفتاحَ `Currency` — العملةُ
# وسمٌ على الدفتر لا حسبةُ تحويلٍ تُعاد بها الحركات.
#
# **ولا `RemoveField` ولا `DeleteModel` ولا `RunSQL`**: هجرةٌ إضافيّةٌ محضة.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting_office', '0018_client_book_report'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientbook',
            name='currency',
            field=models.CharField(
                blank=True, default='', max_length=3, verbose_name='العملة',
            ),
        ),
        migrations.AddField(
            model_name='clientbook',
            name='fiscal_year_start',
            field=models.CharField(
                default='01-01', max_length=5, verbose_name='بداية السنة المالية',
            ),
        ),
    ]
