"""مبلغ السطر بعملته الأجنبية — أساسُ كشف الحساب بالدولار.

عمودان nullable في آخر الجدول: MySQL 8 يضيفهما INSTANT بلا نسخ الجدول. التعبئة
للقديم أمرٌ منفصل (`backfill_foreign_party_currency`) يُقرأ أولاً ثم يُطبَّق.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0045_updated_at_stamp'),
    ]

    operations = [
        migrations.AddField(
            model_name='journalline',
            name='amount_currency',
            field=models.DecimalField(
                blank=True, db_column='AmountCurrency', decimal_places=2, max_digits=18, null=True,
                help_text='المبلغ بعملة السطر الأجنبية، موقَّعاً: موجبٌ مدين وسالبٌ دائن. NULL = سطرٌ بعملة الأساس.',
            ),
        ),
        migrations.AddField(
            model_name='journalline',
            name='currency_code',
            field=models.CharField(
                blank=True, db_column='CurrencyCode', max_length=3, null=True,
                help_text="رمز عملة amount_currency ('USD'). NULL مع amount_currency.",
            ),
        ),
    ]
