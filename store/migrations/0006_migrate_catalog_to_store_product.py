"""نسخُ الأصناف المستحقّة من `inventory.Product` إلى كتالوج المتجر المستقلّ
`StoreProduct` (مواصفة #166 — المرحلة ١).

**مُضيفةٌ محضة**: لا تحذف ولا تعدّل صفّاً واحداً في `inventory.Product` ولا في
أيّ جدول مخزونٍ أو محاسبة. **قابلةٌ لإعادة التشغيل** بلا ازدواج — يحرسها
`imported_from_product_id`: إن كان صفرَ أصنافٍ مستحقّةٍ جديدة (كل الأصناف
المستحقّة سبق نسخُها) تعود الدالة فوراً بلا أثر.

معيارُ الاستحقاق أوسعُ من راية `is_for_sale_online` عمداً: الصورةُ في
`StoreProductImage` والعضويّةُ في `StoreCollectionItem` إعلانا نيّةٍ لا يقلّان
صراحةً عن الراية. لذلك لا يتيمَ ممكناً في هذين التابعين — ظهورُ واحدٍ يعني
أنّ المعيار خطأ، فتتوقّف الهجرة بخطأٍ صريح لا بحذفٍ صامت. `StoreProductView`
مختلفٌ: منتجٌ شوهد ثمّ لم يُستحقّ النسخ عدّادُه يُحذَف (بيانٌ لا يُقرأ أبداً
أفضل من صفٍّ معلَّق).
"""
from django.db import migrations
from django.utils import timezone
from django.utils.text import slugify


def _build_unique_slug_frozen(name, slug_exists):
    """نسخةٌ مجمَّدةٌ من `store/slugs.py` (`build_unique_slug`) — **مقصودةٌ**.

    الهجرةُ أثرٌ مُجمَّدٌ يجب أن يُنتج نفسَ النتيجة بعد سنوات، وأيّ تعديلٍ لاحقٍ
    على النسخة الحيّة في `store/slugs.py` يجب ألّا يُغيّر بصمتٍ سلوكَ إعادة
    تشغيل هذه السلسلة على قاعدةٍ جديدة (`fresh-db-migration-chain`). **لا توحّد
    هذه الدالّةَ مع `store/slugs.py` ولا تستوردها منه** — التكرارُ هنا صحيحٌ:
    نسخةُ الهجرة تبقى ثابتة، ونسخةُ التطبيق تتطوّر.
    """
    base = slugify(name or '', allow_unicode=True)
    if not base:
        base = str(int(timezone.now().timestamp() * 1000))
    candidate = base
    suffix = 2
    while slug_exists(candidate):
        candidate = f'{base}-{suffix}'
        suffix += 1
    return candidate


def migrate_catalog(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    ProductCategory = apps.get_model('inventory', 'ProductCategory')
    StoreProduct = apps.get_model('store', 'StoreProduct')
    StoreBrand = apps.get_model('store', 'StoreBrand')
    StoreCategory = apps.get_model('store', 'StoreCategory')
    StoreProductImage = apps.get_model('store', 'StoreProductImage')
    StoreCollectionItem = apps.get_model('store', 'StoreCollectionItem')
    StoreProductView = apps.get_model('store', 'StoreProductView')
    StorePriceHistory = apps.get_model('store', 'StorePriceHistory')

    already_imported = set(
        StoreProduct.objects
        .exclude(imported_from_product_id__isnull=True)
        .values_list('imported_from_product_id', flat=True)
    )

    flagged_ids = set(
        Product.objects.filter(is_for_sale_online=True).values_list('id', flat=True)
    )
    image_product_ids = set(
        StoreProductImage.objects.values_list('product_id', flat=True)
    )
    collection_product_ids = set(
        StoreCollectionItem.objects.values_list('product_id', flat=True)
    )

    eligible_ids = (
        flagged_ids | image_product_ids | collection_product_ids
    ) - already_imported
    if not eligible_ids:
        return

    products = list(
        Product.objects.filter(id__in=eligible_ids)
        .select_related('uom')
        .only(
            'id', 'tenant_id', 'name_ar', 'name_en', 'description', 'brand',
            'online_price', 'sale_price', 'allow_preorder', 'category_id',
            'uom_id', 'uom__name_ar',
        )
    )

    # ── الماركات: توحيدٌ غيرُ حسّاسٍ لحالة الأحرف لكلّ شركة، أوّل إملاءٍ يبقى ──
    brand_first_seen = {}
    for p in products:
        raw = (p.brand or '').strip()
        if not raw:
            continue
        key = (p.tenant_id, raw.lower())
        brand_first_seen.setdefault(key, raw)

    existing_brand_map = {
        (b.tenant_id, b.name.strip().lower()): b.id
        for b in StoreBrand.objects.all()
    }
    new_brands = [
        StoreBrand(tenant_id=key[0], name=name)
        for key, name in brand_first_seen.items()
        if key not in existing_brand_map
    ]
    if new_brands:
        StoreBrand.objects.bulk_create(new_brands)
    brand_map = {
        (b.tenant_id, b.name.strip().lower()): b.id
        for b in StoreBrand.objects.all()
    }

    # ── الفئات: تسطيحٌ بمستوىً واحد من فئات المخزون التي تستعملها المنتجات
    #    المُرحَّلة فعلاً — لا رابط دائم بـ`inventory.ProductCategory` بعدها ──
    category_ids_used = {p.category_id for p in products if p.category_id}
    source_categories = {
        row['id']: row
        for row in ProductCategory.objects.filter(id__in=category_ids_used)
        .values('id', 'tenant_id', 'name')
        if (row['name'] or '').strip()
    }

    existing_category_slugs = {}
    for c in StoreCategory.objects.all():
        existing_category_slugs.setdefault(c.tenant_id, set()).add(c.slug)

    new_categories = []
    category_key_by_source_id = {}
    for cat_id, row in source_categories.items():
        tenant_id = row['tenant_id']
        name = row['name'].strip()
        slug = _build_unique_slug_frozen(
            name,
            lambda candidate, _t=tenant_id: candidate in existing_category_slugs.get(_t, set()),
        )
        existing_category_slugs.setdefault(tenant_id, set()).add(slug)
        new_categories.append(StoreCategory(tenant_id=tenant_id, name=name, slug=slug))
        category_key_by_source_id[cat_id] = (tenant_id, slug)

    if new_categories:
        StoreCategory.objects.bulk_create(new_categories)

    category_id_by_slug_key = {
        (c.tenant_id, c.slug): c.id
        for c in StoreCategory.objects.filter(
            tenant_id__in={row['tenant_id'] for row in source_categories.values()}
        )
    } if source_categories else {}
    store_category_id_by_source = {
        cat_id: category_id_by_slug_key.get(key)
        for cat_id, key in category_key_by_source_id.items()
    }

    # ── المنتجات: نسخٌ واحدٌ لكلّ صنفٍ مستحقّ ──
    existing_product_slugs = {}
    for sp in StoreProduct.objects.all():
        existing_product_slugs.setdefault(sp.tenant_id, set()).add(sp.slug)

    new_store_products = []
    for p in products:
        price = p.online_price if (p.online_price or 0) > 0 else p.sale_price
        stock_state = 'preorder' if p.allow_preorder else 'in_stock'
        name_ar = p.name_ar or p.name_en or ''
        slug = _build_unique_slug_frozen(
            name_ar,
            lambda candidate, _t=p.tenant_id: candidate in existing_product_slugs.get(_t, set()),
        )
        existing_product_slugs.setdefault(p.tenant_id, set()).add(slug)
        brand_key = (p.tenant_id, (p.brand or '').strip().lower())
        brand_id = brand_map.get(brand_key) if brand_key[1] else None
        uom_name = p.uom.name_ar if p.uom_id and p.uom else ''
        new_store_products.append(StoreProduct(
            tenant_id=p.tenant_id,
            name_ar=name_ar,
            name_en=p.name_en or '',
            slug=slug,
            brand_id=brand_id,
            unit=uom_name or '',
            price=price,
            stock_state=stock_state,
            description=p.description or '',
            is_active=True,
            imported_from_product_id=p.id,
        ))

    if new_store_products:
        StoreProduct.objects.bulk_create(new_store_products)

    # خريطةٌ كاملة (لا تقتصر على هذه الدفعة) تغطّي كلّ ما نُسخ حتى الآن.
    store_product_by_source_id = {
        sp.imported_from_product_id: sp.id
        for sp in StoreProduct.objects.exclude(imported_from_product_id__isnull=True)
    }

    # ── ربط الفئات (M2M) بدفعةٍ واحدة عبر جدول الوسيط مباشرةً ──
    Through = StoreProduct.categories.through
    m2m_rows = []
    for p in products:
        if not p.category_id:
            continue
        store_category_id = store_category_id_by_source.get(p.category_id)
        store_product_id = store_product_by_source_id.get(p.id)
        if store_category_id and store_product_id:
            m2m_rows.append(Through(
                storeproduct_id=store_product_id,
                storecategory_id=store_category_id,
            ))
    if m2m_rows:
        Through.objects.bulk_create(m2m_rows, ignore_conflicts=True)

    # ── سجلّ سعرٍ أوّليّ لكلّ منتجٍ مُنسوخ في هذه الدفعة ──
    price_history_rows = [
        StorePriceHistory(
            tenant_id=sp.tenant_id, store_product_id=sp.id, price=sp.price,
        )
        for sp in StoreProduct.objects.filter(
            imported_from_product_id__in=[p.id for p in products]
        )
    ]
    if price_history_rows:
        StorePriceHistory.objects.bulk_create(price_history_rows)

    # ── نقل التوابع الثلاثة ──
    # الصور والعضويّات: لا يتيمَ ممكن — ظهورُه يعني أنّ معيار الاستحقاق خطأ.
    images = list(StoreProductImage.objects.filter(store_product__isnull=True))
    orphan_image_products = {img.product_id for img in images} - set(store_product_by_source_id)
    if orphan_image_products:
        raise RuntimeError(
            'معيار الاستحقاق أخفق: صور متجر ليتيمة لمنتجات لم تُرحَّل: '
            f'{sorted(orphan_image_products)}'
        )
    for img in images:
        img.store_product_id = store_product_by_source_id[img.product_id]
    if images:
        StoreProductImage.objects.bulk_update(images, ['store_product'], batch_size=500)

    collection_items = list(StoreCollectionItem.objects.filter(store_product__isnull=True))
    orphan_collection_products = (
        {ci.product_id for ci in collection_items} - set(store_product_by_source_id)
    )
    if orphan_collection_products:
        raise RuntimeError(
            'معيار الاستحقاق أخفق: عضويّاتُ حملةٍ يتيمة لمنتجات لم تُرحَّل: '
            f'{sorted(orphan_collection_products)}'
        )
    for ci in collection_items:
        ci.store_product_id = store_product_by_source_id[ci.product_id]
    if collection_items:
        StoreCollectionItem.objects.bulk_update(
            collection_items, ['store_product'], batch_size=500
        )

    # المشاهدات: يتيمها ممكنٌ ومتوقَّع (منتجٌ شوهد ثمّ لم يُستحقّ النسخ) — يُحذَف.
    views = list(StoreProductView.objects.filter(store_product__isnull=True))
    matched_views = []
    orphan_view_ids = []
    for v in views:
        store_product_id = store_product_by_source_id.get(v.product_id)
        if store_product_id:
            v.store_product_id = store_product_id
            matched_views.append(v)
        else:
            orphan_view_ids.append(v.id)
    if matched_views:
        StoreProductView.objects.bulk_update(matched_views, ['store_product'], batch_size=500)
    if orphan_view_ids:
        StoreProductView.objects.filter(id__in=orphan_view_ids).delete()


def reverse_migrate_catalog(apps, schema_editor):
    StoreProduct = apps.get_model('store', 'StoreProduct')
    StoreBrand = apps.get_model('store', 'StoreBrand')
    StoreCategory = apps.get_model('store', 'StoreCategory')
    StoreProductImage = apps.get_model('store', 'StoreProductImage')
    StoreCollectionItem = apps.get_model('store', 'StoreCollectionItem')
    StoreProductView = apps.get_model('store', 'StoreProductView')

    migrated_ids = list(
        StoreProduct.objects
        .exclude(imported_from_product_id__isnull=True)
        .values_list('id', flat=True)
    )
    if not migrated_ids:
        return

    # فكّ الارتباط أوّلاً كي لا يحذف CASCADE صفوفَ التوابع الأصليّة (الصور
    # والعضويّات موجودةٌ قبل هذه الهجرة) عند حذف صفوف `StoreProduct` تالياً.
    StoreProductImage.objects.filter(store_product_id__in=migrated_ids).update(
        store_product=None
    )
    StoreCollectionItem.objects.filter(store_product_id__in=migrated_ids).update(
        store_product=None
    )
    StoreProductView.objects.filter(store_product_id__in=migrated_ids).update(
        store_product=None
    )

    brand_ids = list(
        StoreProduct.objects.filter(id__in=migrated_ids, brand__isnull=False)
        .values_list('brand_id', flat=True).distinct()
    )
    category_ids = list(
        StoreCategory.objects.filter(products__id__in=migrated_ids)
        .values_list('id', flat=True).distinct()
    )

    StoreProduct.objects.filter(id__in=migrated_ids).delete()
    StoreCategory.objects.filter(id__in=category_ids, products__isnull=True).delete()
    StoreBrand.objects.filter(id__in=brand_ids, products__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0032_product_reference_image'),
        ('store', '0005_storecollection_discount_percent_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_catalog, reverse_migrate_catalog),
    ]
