"""يملأ `StoreCollection.featured_store_product` من `featured_product` القديم
(مواصفة #166 — المرحلة ٢، تصحيح): مطابقةٌ عبر `imported_from_product_id` —
فضاءا معرّفَي `inventory.Product` و`StoreProduct` منفصلان تماماً، فلا يصحّ
نسخُ المعرّف حرفياً. **مُضيفةٌ محضة**: لا تمسّ `featured_product` ولا تحذفه.
حملةٌ مميَّزُها منتجٌ لم يُستورَد من صنفٍ مخزني (`imported_from_product_id`
غائب) تبقى بلا `featured_store_product` — لا مطابقة ممكنة له أصلاً.
"""
from django.db import migrations


def populate(apps, schema_editor):
    StoreCollection = apps.get_model('store', 'StoreCollection')
    StoreProduct = apps.get_model('store', 'StoreProduct')

    pending = list(
        StoreCollection.objects
        .filter(featured_product__isnull=False, featured_store_product__isnull=True)
        .values('id', 'tenant_id', 'featured_product_id')
    )
    if not pending:
        return

    store_product_by_source = {
        (sp['tenant_id'], sp['imported_from_product_id']): sp['id']
        for sp in StoreProduct.objects.exclude(imported_from_product_id__isnull=True)
        .values('id', 'tenant_id', 'imported_from_product_id')
    }

    to_update = []
    for row in pending:
        key = (row['tenant_id'], row['featured_product_id'])
        store_product_id = store_product_by_source.get(key)
        if store_product_id:
            to_update.append(
                StoreCollection(id=row['id'], featured_store_product_id=store_product_id)
            )
    if to_update:
        StoreCollection.objects.bulk_update(to_update, ['featured_store_product'], batch_size=500)


def reverse(apps, schema_editor):
    StoreCollection = apps.get_model('store', 'StoreCollection')
    StoreCollection.objects.exclude(featured_store_product__isnull=True).update(
        featured_store_product=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0008_m2_featured_store_product'),
    ]

    operations = [
        migrations.RunPython(populate, reverse),
    ]
