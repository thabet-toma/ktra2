"""ربطُ زبون المكتب بطرفٍ في الدفاتر (#284، الجزء أ) — `AddField` وحده.

`partners.Partner` هو الطرفُ المحاسبيّ نفسه لا سجلٌّ ثانٍ: الزبون يبقى سجلَّ
المكتب (بطاقتُه ومواعيدُه)، والطرفُ هو من تُوسَم به أسطرُ الذمم. والاعتمادُ على
آخر هجرةٍ في `partners` لأن المفتاحَ يشير إلى جدولها.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting_office', '0014_fee_payments'),
        ('partners', '0018_customernote_is_pinned'),
    ]

    operations = [
        migrations.AddField(
            model_name='officeclient',
            name='partner',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='office_clients',
                to='partners.partner',
                verbose_name='الطرف في الدفاتر',
            ),
        ),
    ]
