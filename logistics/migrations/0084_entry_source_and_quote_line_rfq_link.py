"""ISSUE #122: مصدرُ إدخال العرض، ونَسَبُ سطرِه إلى بند الطلبية.

خطوةُ البيانات تختم `supplier_link` على كلّ صفٍّ يحمل `rfq_id` غيرَ فارغ: هذا
اليومَ هو تعريفُ «جاء من رابط المورّد» حرفياً — لا مسارَ آخرَ كان يربط عرضاً
بطلبية. وما عداه يبقى على الافتراض `manual`.

ولا يُملأ `rfq_line` بأثرٍ رجعيّ: الصفوفُ القائمة كتبها مسارُ الرابط وحدَه وهو
يمرّ على بنود الطلبية بالترتيب، فمطابقةُ `seq` عليها صادقةٌ — والمصفوفةُ تسقط
إليها حين يكون `rfq_line` فارغاً.
"""
import django.db.models.deletion
from django.db import migrations, models


def stamp_supplier_link(apps, schema_editor):
    SupplierQuotation = apps.get_model('logistics', 'SupplierQuotation')
    SupplierQuotation.objects.filter(rfq_id__isnull=False).update(
        entry_source='supplier_link',
    )


def unstamp(apps, schema_editor):
    """العكسُ لا يستعيد شيئاً — العمود نفسه يُحذف في `AddField` العكسية."""


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0083_supplierquotationline_unit_of_measure'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierquotation',
            name='entry_source',
            field=models.CharField(choices=[('supplier_link', 'سعّره المورّد'), ('manual', 'أُدخل عنه')], db_column='EntrySource', default='manual', help_text='مصدر إدخال العرض: سعّره المورّد على رابطه، أم أُدخل عنه', max_length=20),
        ),
        migrations.AddField(
            model_name='supplierquotationline',
            name='rfq_line',
            field=models.ForeignKey(blank=True, db_column='PurchaseRFQLineID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quotation_lines', to='logistics.purchaserfqline'),
        ),
        migrations.RunPython(stamp_supplier_link, unstamp),
    ]
