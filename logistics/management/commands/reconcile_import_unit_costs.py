"""فحص فواتير الاستيراد المرحّلة ومزامنة متوسط تكلفة أصنافها (`Product.avg_cost`) من الطبقات المفتوحة.

يعرض لكل فاتورة دولية مرحّلة مدين البضاعة في وسيطها (`open_goods_clearing`)، وقيمة
حركات استلامها، وقيمتها بالسعر المستورد، والفرق (ما رسمله قيدها فوق السعر
المستورد من عمولات التحويل والرسوم المرسملة عبر `logistics.services.posted_goods_line_costs`).
ولكل صنف متأثّر: `avg_cost` الحالي مقابل هدف الطبقات المفتوحة عبر
`inventory.services.sync_avg_cost_from_layers`:

    python manage.py reconcile_import_unit_costs --tenant 1          # قراءة
    python manage.py reconcile_import_unit_costs --tenant 1 --apply  # تصحيح

`--apply` يزامن `Product.avg_cost` من الطبقات المفتوحة (`sync_avg_cost_from_layers`) —
بلا قيد ولا كتابة لحركات الاستلام.

**المبيع لا يحتاج تسوية**: قيد ت.ب.م يُبنى من كلفة حركة البيع (`total_cost`) وهي من طبقة
FIFO لا من `avg_cost` — فخرجت العمولة من 1104 مع البيع. الأمر يتحقّق من ذلك لكل بيعٍ
استهلك طبقات الفاتورة (كلفة الحركة = كلفة استهلاكها)، ويعرض المختلف للمراجعة دون تصحيح.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Product, StockLayerConsumption, StockMovement
from inventory.services import sync_avg_cost_from_layers
from logistics.models import PurchaseInvoice
from logistics.services import open_goods_clearing, posted_goods_line_costs

Q2 = Decimal('0.01')


def _sales_off_fifo(tenant_id, receipt_movements) -> list:
    """حركات صرفٍ استهلكت طبقات هذه الاستلامات وكلفتُها ≠ كلفة استهلاكها من الطبقات."""
    consumers = {
        c.movement for c in StockLayerConsumption.objects.filter(
            tenant_id=tenant_id, layer__source_movement__in=receipt_movements,
        ).select_related('movement')
    }
    out = []
    for mv in sorted(consumers, key=lambda m: m.pk):
        fifo_cost = sum((
            Decimal(str(c.quantity)) * Decimal(str(c.unit_cost))
            for c in StockLayerConsumption.objects.filter(movement=mv)
        ), Decimal('0')).quantize(Q2)
        booked = Decimal(str(mv.total_cost or 0)).quantize(Q2)
        if abs(booked - fifo_cost) > Q2:
            out.append((mv, booked, fifo_cost))
    return out


class Command(BaseCommand):
    help = "متوسط تكلفة أصناف الفواتير الدولية = ما دخل المخزون (قراءة افتراضاً، --apply للتصحيح)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")
        parser.add_argument("--apply", action="store_true", help="اضبط المتوسط فعلاً.")

    def handle(self, *args, **options):
        tenant_id = options["tenant"]
        apply = options["apply"]
        w = self.stdout.write
        invoices = PurchaseInvoice.objects.filter(
            tenant_id=tenant_id, invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            is_return=False, is_posted=True,
        ).order_by('invoice_date', 'pk')

        products = set()
        total_diff = Decimal('0')
        w(self.style.MIGRATE_HEADING("الفواتير الدولية المرحّلة: قيمة المخزون مقابل السعر المستورد"))
        for inv in invoices:
            line_costs = posted_goods_line_costs(inv)
            if line_costs is None:
                continue
            _acc, goods_debit, _open = open_goods_clearing(inv)
            items = {it.pk: it for it in inv.items.all()}
            landed = sum(
                (Decimal(str(items[i].landed_line_total_ils or items[i].total_price or 0))
                 for i in line_costs), Decimal('0')).quantize(Q2)
            diff = (sum(line_costs.values(), Decimal('0')) - landed).quantize(Q2)
            receipts = list(StockMovement.objects.filter(
                tenant_id=tenant_id, reference_type='PURCHASE_INVOICE',
                reference_id=inv.pk, movement_type='IN'))
            received = sum((Decimal(str(m.total_cost or 0)) for m in receipts), Decimal('0')).quantize(Q2)
            fully = inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
            mismatch = fully and abs(received - goods_debit.quantize(Q2)) > Q2
            off_fifo = _sales_off_fifo(tenant_id, receipts)
            if not diff and not mismatch and not off_fifo:
                continue
            total_diff += diff
            products |= {items[i].product_id for i in line_costs if items[i].product_id}
            w(f"  {inv.invoice_number}: مدين البضاعة {goods_debit:.2f} · حركات الاستلام {received:.2f} "
              f"· بالسعر المستورد {landed:.2f} · الفرق {diff:.2f}")
            if mismatch:
                # الحركات من توزيع مدين البضاعة نفسه — افتراقهما خارج ما يصلحه الأمر.
                w(self.style.WARNING(
                    f"    ⚠ قيمة حركات الاستلام ≠ مدين البضاعة ({received - goods_debit:.2f}) — يُراجَع يدوياً."))
            for mv, booked, fifo_cost in off_fifo:
                w(self.style.WARNING(
                    f"    ⚠ حركة صرف #{mv.pk} ({mv.reference_type} #{mv.reference_id}): كلفتها {booked} "
                    f"وكلفة طبقاتها {fifo_cost} — يُراجَع يدوياً."))
        w(f"صافي الفرق على الفواتير: {total_diff:.2f}")
        if not products:
            w(self.style.SUCCESS("لا أصناف تحتاج تصحيحاً."))
            return

        w(self.style.MIGRATE_HEADING("الأصناف: المتوسط (avg_cost)"))
        synced = 0
        with transaction.atomic():
            for product in Product.objects.filter(tenant_id=tenant_id, pk__in=products).order_by('pk'):
                res = sync_avg_cost_from_layers(product, apply=apply)
                if res['status'] == 'synced':
                    synced += 1
                if apply:
                    w(f"  {product.sku}: {res['before']} → {res['after']} ({res['status']})")
                else:
                    w(f"  {product.sku}: الآن {res['before']} · من الطبقات المفتوحة {res['after']} ({res['status']})")
        if apply:
            w(self.style.SUCCESS(f"ضُبط متوسط {synced} صنف — بلا قيد."))
        else:
            w("أعد التشغيل بـ --apply لضبط المتوسط (بلا قيد).")
