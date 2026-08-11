"""T-IMPOFFER — تصنيف الموردين القائمين محلياً/دولياً من سجلّهم الفعلي.

الحقل الجديد افتراضه '' (غير مصنَّف) ليظهر المورد في الجانبين، لكن ترك كل
الموردين غير مصنَّفين يفرغ الفصل من معناه في أول استخدام. هذا الترحيل يصنّف
ما يمكن استنتاجه بيقين من المستندات نفسها:

- **دولي**: ظهر في صفقة استيراد، أو عرض سعر نطاقه `import`، أو فاتورة شراء
  نوعها `international`.
- **محلي**: ظهر في مستند شراء محلي (طلبية/عرض محلي/فاتورة محلية) **ولم** يظهر
  في أي مستند استيراد.
- من لم يظهر في شيء يبقى غير مصنَّف — لا نخترع تصنيفاً بلا دليل.
"""
from django.db import migrations


def classify(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    LogisticsDeal = apps.get_model('logistics', 'LogisticsDeal')
    SupplierQuotation = apps.get_model('logistics', 'SupplierQuotation')
    PurchaseOrder = apps.get_model('logistics', 'PurchaseOrder')
    PurchaseInvoice = apps.get_model('logistics', 'PurchaseInvoice')

    international = set(
        LogisticsDeal.objects.values_list('partner_id', flat=True)
    )
    international |= set(
        SupplierQuotation.objects
        .filter(scope='import')
        .values_list('supplier_id', flat=True)
    )
    international |= set(
        PurchaseInvoice.objects
        .filter(invoice_type='international')
        .values_list('partner_id', flat=True)
    )
    international.discard(None)

    local = set(PurchaseOrder.objects.values_list('supplier_id', flat=True))
    local |= set(
        SupplierQuotation.objects
        .filter(scope='local')
        .values_list('supplier_id', flat=True)
    )
    local |= set(
        PurchaseInvoice.objects
        .filter(invoice_type='local')
        .values_list('partner_id', flat=True)
    )
    local.discard(None)
    # مورد ظهر في الجانبين يُعدّ دولياً: شاشة الاستيراد هي التي لا يجوز أن تفقده.
    local -= international

    if international:
        Partner.objects.filter(pk__in=international, supplier_scope='').update(
            supplier_scope='international',
        )
    if local:
        Partner.objects.filter(pk__in=local, supplier_scope='').update(
            supplier_scope='local',
        )


def unclassify(apps, schema_editor):
    """العكس يُرجع الحقل لفراغه — الفراغ هو حالة «قبل الفصل» تماماً."""
    Partner = apps.get_model('partners', 'Partner')
    Partner.objects.exclude(supplier_scope='').update(supplier_scope='')


class Migration(migrations.Migration):

    dependencies = [
        ('partners', '0010_partner_supplier_scope'),
        ('logistics', '0064_supplierquotation_alibaba_link_and_more'),
    ]

    operations = [
        migrations.RunPython(classify, unclassify),
    ]
