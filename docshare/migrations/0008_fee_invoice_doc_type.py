# #282/أ٢/١: يسجّل `fee_invoice` في choices العمود — العمود نفسه (40 محرفاً) لا
# يتغيّر، و«fee_invoice» (11 محرفاً) يتّسع فيه. زيادةٌ محضة: لا حقلَ يُحذف ولا
# نموذجَ يُعاد بناؤه، ولا `RunSQL`.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docshare', '0007_payment_notice_doc_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentshare',
            name='doc_type',
            field=models.CharField(choices=[('sales_invoice', 'فاتورة بيع'), ('sales_quotation', 'عرض سعر'), ('purchase_invoice', 'فاتورة شراء'), ('purchase_order', 'أمر شراء'), ('logistics_deal', 'صفقة استيراد'), ('supplier_quotation', 'عرض سعر مورّد'), ('local_purchase_invoice', 'فاتورة شراء محلّية'), ('sales_order', 'طلبية زبون'), ('delivery_order', 'سند تسليم'), ('customer_payment', 'سند قبض'), ('supplier_payment', 'سند صرف'), ('credit_debit_note', 'إشعار دائن/مدين'), ('warranty_card', 'بطاقة كفالة'), ('service_order', 'أمر صيانة'), ('purchase_rfq', 'طلب عرض سعر'), ('warranty_certificate', 'شهادة كفالة'), ('stocktake_count', 'رابط عدّ جرد'), ('payment_notice', 'إشعار دفع'), ('fee_invoice', 'فاتورة أتعاب')], db_column='DocType', max_length=40),
        ),
    ]
