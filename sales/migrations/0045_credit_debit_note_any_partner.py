"""إشعار مدين/دائن لأيّ طرف (عميلٍ أو دائن) — لا للعميل وحده.

`customer` ← `partner` بإعادة تسميةٍ للحقل والعمود معاً (`CustomerID` ← `PartnerID`)،
فلا يُفقد صفٌّ ولا ربط. ويُضاف: الحساب المقابل، والعملة وسعرها، والضريبة، وأربعُ
روابط اختيارية لمستندات الدائنين (فاتورة شراء · تخليص · إرسالية · استحقاق شحن).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0046_journalline_amount_currency'),
        ('logistics', '0095_clearance_item_types'),
        ('sales', '0044_updated_at_stamp'),
        ('tenants', '0035_grant_import_procurement_view'),
    ]

    operations = [
        migrations.RenameField(
            model_name='creditdebitnote',
            old_name='customer',
            new_name='partner',
        ),
        migrations.AlterField(
            model_name='creditdebitnote',
            name='partner',
            field=models.ForeignKey(
                db_column='PartnerID', on_delete=django.db.models.deletion.PROTECT,
                related_name='credit_debit_notes', to='partners.partner',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='related_purchase_invoice',
            field=models.ForeignKey(
                blank=True, db_column='RelatedPurchaseInvoiceID', null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='credit_debit_notes',
                to='logistics.purchaseinvoice',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='related_clearance',
            field=models.ForeignKey(
                blank=True, db_column='RelatedClearanceID', null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='credit_debit_notes',
                to='logistics.logisticsclearance',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='related_local_shipment',
            field=models.ForeignKey(
                blank=True, db_column='RelatedLocalShipmentID', null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='credit_debit_notes',
                to='logistics.localshipment',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='related_shipment',
            field=models.ForeignKey(
                blank=True, db_column='RelatedShipmentID', null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='credit_debit_notes',
                to='logistics.logisticsshipment',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='counter_account',
            field=models.ForeignKey(
                blank=True, db_column='CounterAccountID', null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='+',
                to='accounting.account',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='currency',
            field=models.ForeignKey(
                blank=True, db_column='CurrencyID', null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='+',
                to='tenants.currency',
            ),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='exchange_rate',
            field=models.DecimalField(db_column='ExchangeRate', decimal_places=6, default=1, max_digits=18),
        ),
        migrations.AddField(
            model_name='creditdebitnote',
            name='tax_amount',
            field=models.DecimalField(db_column='TaxAmount', decimal_places=2, default=0, max_digits=18),
        ),
    ]
