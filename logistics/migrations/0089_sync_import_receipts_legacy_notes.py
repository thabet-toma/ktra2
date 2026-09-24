"""إعادة مزامنة استلام الفواتير الدولية — ملاحظاتُ الحركات القديمة بلا فاصل ختامي.

0088 طابقت «| صفقة REF |» وحدها، و`backfill_stock` كتب «شحنة X | صفقة REF» بلا
« | تكلفة: ...» بعدها — فبقيت فواتيرُ بضاعتُها كاملةً في المخزن «غير مستلمة»
(الإنتاج: INV-0010..0013، شحنة 5)، وزرُّ «استلام» يُدخلها مرّتين. هنا منطقُ 0088
نفسه بحدِّ الصفقة المصحَّح (مرآة `logistics.services.legacy_shipment_deal_notes_q`
على النماذج التاريخية — الهجرة لا تستورد الخدمات). 0088 لا تُعدَّل: طُبِّقت على
الإنتاج. idempotent، ولا تُنقص كميةً مستلمة.
"""
from decimal import Decimal

from django.db import migrations
from django.db.models import Q


def sync_receipts(apps, schema_editor):
    PurchaseInvoice = apps.get_model('logistics', 'PurchaseInvoice')
    PurchaseInvoiceItem = apps.get_model('logistics', 'PurchaseInvoiceItem')
    StockMovement = apps.get_model('inventory', 'StockMovement')

    invoices = PurchaseInvoice.objects.filter(
        shipment__isnull=False, is_return=False,
    ).select_related('deal')
    for inv in invoices.iterator():
        moves = StockMovement.objects.filter(
            tenant_id=inv.tenant_id, reference_type='SHIPMENT',
            reference_id=inv.shipment_id, movement_type='IN',
        )
        if inv.deal_id:
            token = f"| صفقة {inv.deal.ref_number}"
            moves = moves.filter(
                Q(notes__contains=f"{token} |")
                | Q(notes__endswith=token)
                | Q(notes__endswith=f"{token} ")
            )
        by_product = {}
        for pid, qty in moves.values_list('product_id', 'quantity'):
            by_product[pid] = by_product.get(pid, Decimal('0')) + Decimal(str(qty or 0))
        if not by_product:
            continue

        items = list(PurchaseInvoiceItem.objects.filter(
            invoice_id=inv.pk, product_id__isnull=False,
        ).order_by('id'))
        for it in items:
            available = by_product.get(it.product_id, Decimal('0'))
            if available <= 0:
                continue
            take = min(available, Decimal(str(it.quantity or 0)))
            by_product[it.product_id] = available - take
            if take > Decimal(str(it.received_quantity or 0)):
                it.received_quantity = take
                it.save(update_fields=['received_quantity'])

        fully = bool(items) and all(
            Decimal(str(it.received_quantity or 0)) >= Decimal(str(it.quantity or 0))
            for it in items
        )
        any_received = any(Decimal(str(it.received_quantity or 0)) > 0 for it in items)
        status = (
            'received' if fully else 'partially_received' if any_received
            else 'not_received'
        )
        if inv.receipt_status != status:
            inv.receipt_status = status
            inv.save(update_fields=['receipt_status'])


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0088_sync_import_invoice_receipts'),
    ]

    operations = [
        migrations.RunPython(sync_receipts, migrations.RunPython.noop),
    ]
