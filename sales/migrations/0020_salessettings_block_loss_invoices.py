# Generated for block_loss_invoices setting

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0019_salessettings_warn_on_duplicate_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='salessettings',
            name='block_loss_invoices',
            field=models.BooleanField(db_column='BlockLossInvoices', default=False, help_text='رفض حفظ/ترحيل فاتورة بيع فيها خسارة (سعر البيع أقل من التكلفة)'),
        ),
    ]
