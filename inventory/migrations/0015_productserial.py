import django.db.models.deletion
from django.db import migrations, models


# المخطَّط القديم (ما قبل المنصّة) فيه أصلاً جدول باسم `product_serials` بأعمدة
# أخرى (`SerialNumberID · ProductID · SerialNumber · WarehouseID · Status ·
# PO_LineID · SalesInvoice_LineID`) — فارغ لكنه موجود، وقاعدة الإنتاج مستورَدة من
# نفس المصدر. بلا هذا الحارس يسقط `CreateModel` أدناه بـ
# `(1050, "Table 'product_serials' already exists")` عند النشر.
# نُزيحه بإعادة تسمية (لا حذف: إعادة التسمية تحفظ أي صفوف لو وُجدت).
LEGACY_TABLE = 'product_serials'
LEGACY_FINGERPRINT = 'serialnumberid'   # عمود لا وجود له في النموذج الجديد


def _existing_tables(connection):
    with connection.cursor() as cursor:
        return {name.lower() for name in connection.introspection.table_names(cursor)}


def _is_legacy_shaped(connection):
    """جدول `product_serials` موجودٌ بأعمدة المخطَّط القديم؟"""
    if LEGACY_TABLE not in _existing_tables(connection):
        return False
    with connection.cursor() as cursor:
        columns = {
            field.name.lower()
            for field in connection.introspection.get_table_description(
                cursor, LEGACY_TABLE
            )
        }
    return LEGACY_FINGERPRINT in columns


def rename_legacy_product_serials(apps, schema_editor):
    connection = schema_editor.connection
    if not _is_legacy_shaped(connection):
        # لا جدول، أو جدولٌ بالشكل الجديد (سلاسل SQLite النظيفة تمرّ من هنا).
        return

    taken = _existing_tables(connection)
    target = f'{LEGACY_TABLE}_legacy'
    suffix = 1
    while target.lower() in taken:
        # جهاز المالك أُصلح يدوياً فصار عنده `product_serials_legacy` — لا نفشل.
        suffix += 1
        target = f'{LEGACY_TABLE}_legacy_{suffix}'

    quote = connection.ops.quote_name
    # `ALTER TABLE … RENAME TO` بدل `RENAME TABLE` الخاص بـMySQL: نفس الأثر
    # وتدعمه كل الواجهات الخلفية التي نبني عليها. ونمرّ بمؤشِّر خام لا
    # بـ`schema_editor.execute` لأنه يرفض DDL داخل معاملة على MySQL — والاسمان
    # ثابتان في هذا الملف فلا مدخل لأي حقن.
    with connection.cursor() as cursor:
        cursor.execute(
            f'ALTER TABLE {quote(LEGACY_TABLE)} RENAME TO {quote(target)}'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0014_product_sale_price'),
        ('logistics', '0070_purchaseinvoiceitem_serials_and_more'),
        ('sales', '0034_salesinvoiceline_serials_and_more'),
        ('tenants', '0018_alter_rolepermission_role_and_more'),
    ]

    operations = [
        migrations.RunPython(
            rename_legacy_product_serials,
            migrations.RunPython.noop,
            elidable=False,
        ),
        migrations.CreateModel(
            name='ProductSerial',
            fields=[
                ('id', models.AutoField(db_column='ProductSerialID', primary_key=True, serialize=False)),
                ('serial', models.CharField(db_column='Serial', max_length=100)),
                ('status', models.CharField(choices=[('in_stock', 'في المخزن'), ('sold', 'مُباع')], db_column='Status', default='in_stock', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='CreatedAt')),
                ('product', models.ForeignKey(db_column='ProductID', on_delete=django.db.models.deletion.CASCADE, related_name='serials', to='inventory.product')),
                ('purchase_item', models.ForeignKey(blank=True, db_column='PurchaseInvoiceItemID', help_text='بند فاتورة الشراء الذي أدخل هذه الوحدة للمخزن', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serial_units', to='logistics.purchaseinvoiceitem')),
                ('sales_line', models.ForeignKey(blank=True, db_column='SalesInvoiceLineID', help_text='بند فاتورة البيع الذي استهلك هذه الوحدة', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serial_units', to='sales.salesinvoiceline')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
            ],
            options={
                'db_table': 'product_serials',
                'managed': True,
                'indexes': [models.Index(fields=['tenant', 'product', 'status'], name='prodserial_tenant_prod_stat')],
                'unique_together': {('tenant', 'product', 'serial')},
            },
        ),
    ]
