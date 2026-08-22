"""نقل رقم كتالوج المورّد من `Product.name_en` إلى `SupplierProduct.supplier_sku`.

رقم المورّد (מק"ט) حُشِر مؤقّتاً في `name_en` لغياب مكانٍ له. الحشوة تعمل اليوم
فعلاً — `ProductViewSet.search_fields` يشمل `name_en` فيجدها البحث — لذلك النقل
**يجب ألّا يفقد القدرة**: يُنشئ الصفّ في `SupplierProduct` أوّلاً (والبحث صار
يشمله)، ثم يفرّغ `name_en` بعد التأكّد.

بلا `--commit` لا يُكتب شيء: يطبع ما سيفعله ويقف. وبلا `--pattern` صريح لا
يعمل أصلاً — «فرّغ حقلاً على أصنافٍ يختارها تخمين» ليس أمراً يُشغَّل بلا نيّة.

مثال:
    python manage.py migrate_supplier_sku_from_name_en \\
        --tenant 3 --supplier 41 --pattern "^\\d+\\.\\d+$" --sku-from 001313 --sku-to 001345
    # ثم بعد مراجعة الخرج:
    python manage.py migrate_supplier_sku_from_name_en ... --commit
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.models import Product, SupplierProduct
from partners.models import Partner


class Command(BaseCommand):
    help = 'نقل رقم كتالوج المورّد من Product.name_en إلى SupplierProduct'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=int, required=True)
        parser.add_argument('--supplier', type=int, required=True,
                            help='معرّف المورّد صاحب هذا الترقيم')
        parser.add_argument('--pattern', required=True,
                            help=r'نمط يطابق الرقم وحده، مثل "^\d+\.\d+$"')
        parser.add_argument('--sku-from', default='', help='حدّ أدنى لرقم الصنف عندنا (اختياري)')
        parser.add_argument('--sku-to', default='', help='حدّ أعلى لرقم الصنف عندنا (اختياري)')
        parser.add_argument('--keep-name-en', action='store_true',
                            help='انسخ الرقم ولا تفرّغ name_en (نقلٌ على مرحلتين)')
        parser.add_argument('--commit', action='store_true',
                            help='اكتب فعلاً. بدونه معاينة فقط.')

    def handle(self, *args, **opts):
        try:
            rx = re.compile(opts['pattern'])
        except re.error as exc:
            raise CommandError(f'نمط غير صالح: {exc}')

        supplier = Partner.objects.filter(
            pk=opts['supplier'], tenant_id=opts['tenant'],
        ).first()
        if supplier is None:
            raise CommandError('المورّد غير موجود في هذه الشركة.')
        if supplier.partner_type != 'Supplier':
            raise CommandError(f'«{supplier.name}» ليس مورّداً.')

        qs = Product.objects.filter(tenant_id=opts['tenant']).exclude(name_en__isnull=True)
        if opts['sku_from']:
            qs = qs.filter(sku__gte=opts['sku_from'])
        if opts['sku_to']:
            qs = qs.filter(sku__lte=opts['sku_to'])

        planned, skipped_shape, clashes = [], 0, []
        for product in qs.order_by('sku'):
            code = (product.name_en or '').strip()
            if not code or not rx.match(code):
                skipped_shape += 1
                continue
            taken = SupplierProduct.objects.filter(
                tenant_id=opts['tenant'], supplier=supplier, supplier_sku=code,
            ).exclude(product=product).first()
            if taken is not None:
                clashes.append((product.sku, code, taken.product_id))
                continue
            planned.append((product, code))

        self.stdout.write(f'المورّد: {supplier.name} (#{supplier.pk})')
        self.stdout.write(f'مرشَّحة للنقل: {len(planned)}')
        self.stdout.write(f'تُركت — لا تطابق النمط: {skipped_shape}')
        for product, code in planned[:20]:
            self.stdout.write(f'  {product.sku}: name_en="{code}" -> supplier_sku="{code}"')
        if len(planned) > 20:
            self.stdout.write(f'  … و{len(planned) - 20} غيرها')
        for sku, code, other in clashes:
            self.stderr.write(
                f'  تعارض: الصنف {sku} رقمه "{code}" وهو مأخوذ للصنف #{other} — تُرك.')

        if not opts['commit']:
            self.stdout.write(self.style.WARNING(
                'معاينة فقط — لم يُكتب شيء. أضف --commit للتنفيذ.'))
            return

        with transaction.atomic():
            for product, code in planned:
                SupplierProduct.objects.update_or_create(
                    tenant_id=opts['tenant'], supplier=supplier, supplier_sku=code,
                    defaults={'product': product},
                )
                if not opts['keep_name_en']:
                    # `name_en` معناه «اسم الصنف بالإنجليزية» — يُترك فارغاً لا
                    # يحمل رقماً. والبحث لم يخسر شيئاً: صار يشمل supplier_sku.
                    product.name_en = ''
                    product.save(update_fields=['name_en'])

        self.stdout.write(self.style.SUCCESS(
            f'تمّ: {len(planned)} رقماً'
            + ('' if opts['keep_name_en'] else '، وأُفرغ name_en لها')))
