"""هجرة بيانات #231 — كل منتج `warranty_months>0` يأخذ `WarrantyPolicy`.

**لكل الشركات** عمداً (لا فلترة على ترخيص الوحدة): نقلُ بياناتٍ أدخلها
المستخدم على المنتج، والصفّ خاملٌ خلف `module_enabled` حتى لو لم تشترِ الشركة
الوحدة — نفس الاستثناء المُعلَن في مواصفة #228 §هجرات البيانات.

المطابقة: `serial` إن كان المنتج مرقّماً (`is_serialized`)، وإلا `invoice`.
`dealer_months` من `warranty_months`، و`supplier_months` من
`supplier_warranty_months`. لا جهة كفالة مصنع (`manufacturer_warrantor=None`،
`manufacturer_months=0`) — لم يكن للمصنع عمودٌ منفصل قبل هذا المعلم.

**لا رجوع (`RunPython.noop`) بقصد**: هذا نقلٌ إضافي محض لا يُعدِّل عمود
المنتج القديم ولا يحذفه (تلك هجرةٌ لاحقة في `inventory`)، فأي تراجعٍ حقيقي
سيفقد بياناته أصلاً حين تُعكس هجرة حذف العمودين قبل هذه — إعادة توليد الصفوف
هنا من نفس المعيار (`warranty_months__gt=0`) ليست له معنى عندها. حذفٌ يدويٌّ
لصفوف `WarrantyPolicy` المتأثرة يبقى ممكناً من لوحة الإدارة إن استدعى الأمر.
"""
from django.db import migrations


def policy_kwargs_from_legacy_product(product) -> dict:
    """التحويل نفسه، معزولٌ في دالّةٍ نقية — `after_sales/tests/test_warranty_policies.py`
    يختبرها مباشرةً بكائنٍ يحاكي شكل المنتج **قبل** حذف عمودَيه (#231 §هجرات
    البيانات، الخطوة ٣)، لأن حقلَي `Product` الحقيقيّين ما عادا موجودين على
    النموذج الحيّ بعد أن طُبِّقت هجرة الحذف.
    """
    return dict(
        tenant_id=product.tenant_id,
        product_id=product.id,
        method='serial' if product.is_serialized else 'invoice',
        dealer_months=product.warranty_months or 0,
        manufacturer_warrantor=None,
        manufacturer_months=0,
        supplier_months=product.supplier_warranty_months or 0,
        terms_override='',
    )


def backfill_policies(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    WarrantyPolicy = apps.get_model('after_sales', 'WarrantyPolicy')

    already = set(
        WarrantyPolicy.objects.values_list('product_id', flat=True)
    )
    products = (
        Product.objects
        .filter(warranty_months__gt=0)
        .exclude(id__in=already)
        .only('id', 'tenant_id', 'is_serialized', 'warranty_months', 'supplier_warranty_months')
    )

    to_create = [
        WarrantyPolicy(**policy_kwargs_from_legacy_product(product))
        for product in products.iterator()
    ]
    if to_create:
        WarrantyPolicy.objects.bulk_create(to_create, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('after_sales', '0007_warrantypolicy_and_card_terms_text'),
    ]

    operations = [
        migrations.RunPython(backfill_policies, migrations.RunPython.noop),
    ]
