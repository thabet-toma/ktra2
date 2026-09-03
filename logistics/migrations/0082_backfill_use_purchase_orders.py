"""ISSUE #117: تشعل `use_purchase_orders` لكل شركةٍ لها أمرُ شراءٍ قائمٌ واحد.

`0081` أضافت الحقل بافتراض `False` — السلسلة الجديدة تصير طلبية ← عروض ←
فاتورة بلا أمر شراء. لكن شركةً استعملت أمر الشراء فعلاً (له صفٌّ واحد على
الأقل غير محذوف) لا يجوز أن تفقد خطوةً تعتمد عليها بصمتٍ عند الترقية — فهذه
الهجرة تُشعل المفتاح لها تحديداً، وتترك من لا أمرَ له مطفأً كما هو الافتراض.

أمرُ شراءٍ محذوفٌ ناعماً (`is_deleted=True`) لا يُحتسب: هو ليس «قائماً» —
والاستعلام هنا صريح بذلك بدل الاعتماد على مدير الحذف الناعم الذي لا يُستنسخ
تلقائياً في النموذج التاريخي داخل الهجرات.
"""
from django.db import migrations


def backfill_use_purchase_orders(apps, schema_editor):
    PurchaseOrder = apps.get_model('logistics', 'PurchaseOrder')
    PurchaseSettings = apps.get_model('logistics', 'PurchaseSettings')

    tenant_ids = (
        PurchaseOrder.objects.filter(is_deleted=False)
        .values_list('tenant_id', flat=True)
        .distinct()
    )
    for tenant_id in tenant_ids:
        obj, _created = PurchaseSettings.objects.get_or_create(tenant_id=tenant_id)
        if not obj.use_purchase_orders:
            obj.use_purchase_orders = True
            obj.save(update_fields=['use_purchase_orders'])


def unset_use_purchase_orders(apps, schema_editor):
    # لا رجعة آمنة: قد تكون الشركة أشعلته يدوياً بعد الهجرة. لا نلمس شيئاً.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0081_purchasesettings_use_purchase_orders'),
    ]

    operations = [
        migrations.RunPython(backfill_use_purchase_orders, unset_use_purchase_orders),
    ]
