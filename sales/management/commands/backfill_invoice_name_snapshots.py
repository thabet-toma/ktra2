"""THA-18 — تعبئة لقطة الاسم للبنود القائمة (~30,879 سطراً في الإنتاج).

**تحذير مهم**: هذا ليس التقاطاً تاريخياً حقيقياً لما كان اسم المنتج لحظة ترحيل كل
فاتورة قديمة — تلك اللحظة ضاعت، فلا سجلّ يحفظها. ما يفعله هذا الأمر هو تجميد
الاسم *الحالي* للمنتج على كل بند لا يحمل لقطة بعد، بدءاً من لحظة تشغيله فصاعداً.
فواتير رُحِّلت قبل اليوم تعرض بعد هذا الأمر الاسم الذي كان للمنتج *يوم التشغيل*
لا يوم الترحيل الفعلي.

**المرحَّلة وحدها**: المسودّة لا تُجمَّد إطلاقاً — عقدُ الحقل أن الفارغة تعني
«اتبع اسم المنتج الحي»، وتجميدُ مسودّة يكسر ذلك بلا رجعة (إلغاء الترحيل هو ما
يمسح اللقطة، والمسودّة لا تمرّ به أصلاً فتبقى مجمَّدةً إلى الأبد).

آمن للتكرار: يطابق البنود بـ`name_snapshot=''` وحدها، فلا يلمس بنداً له لقطة
سابقة (من ترحيلٍ جرى بعد نشر THA-18) ولا يُعيد الكتابة على تشغيلة ثانية.

    python manage.py backfill_invoice_name_snapshots            # عرض فقط (dry-run)
    python manage.py backfill_invoice_name_snapshots --apply     # تطبيق التعبئة
    python manage.py backfill_invoice_name_snapshots --apply --tenant 1
"""
import logging

from django.core.management.base import BaseCommand

from inventory.services import product_display_name
from sales.models import SalesInvoice, SalesInvoiceLine

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "تعبئة لقطة اسم بند فاتورة البيع من اسم المنتج الحالي — تجميدٌ من الآن لا تاريخ حقيقي."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='طبّق التعبئة فعلياً.')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        lines = SalesInvoiceLine.objects.filter(
            name_snapshot='', product__isnull=False,
            invoice__status=SalesInvoice.STATUS_POSTED,
        ).select_related('product')
        if opts['tenant']:
            lines = lines.filter(tenant_id=opts['tenant'])

        total = lines.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("لا بنود بحاجة تعبئة."))
            return

        if not apply:
            self.stdout.write(self.style.WARNING(f"سيُعبَّأ: {total} بنداً."))
            self.stdout.write("أعد التشغيل بـ --apply للتطبيق.")
            return

        updated = 0
        batch = []
        for line in lines.iterator(chunk_size=2000):
            # #22: `product_display_name` لا `str(product)` — يتفق مع الترحيل
            # الجديد وطباعة «اسم المنتج (البراند)» (راجع قرار #22 على التذكرة).
            name = product_display_name(line.product)
            if not name:
                continue
            line.name_snapshot = name
            batch.append(line)
            if len(batch) >= 2000:
                SalesInvoiceLine.objects.bulk_update(batch, ['name_snapshot'])
                updated += len(batch)
                batch = []
        if batch:
            SalesInvoiceLine.objects.bulk_update(batch, ['name_snapshot'])
            updated += len(batch)

        logger.info("backfill_invoice_name_snapshots: filled %s of %s line(s).", updated, total)
        self.stdout.write(self.style.SUCCESS(f"\nعُبِّئ: {updated} من {total} بنداً."))
