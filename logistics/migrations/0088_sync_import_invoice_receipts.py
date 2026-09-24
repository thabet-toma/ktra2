"""الفواتير الدولية التي دخلت بضاعتها من الشحنة تُعرَف «مستلَمة».

إشارة «Cleared» القديمة كانت تُدخل بضاعة الاستيراد بحركات `SHIPMENT` لا تلمس
الفاتورة، فبقيت مرحّلةً وبضاعتها في المخزن وعليها «غير مستلمة» — والاستلام من
الفاتورة (المسار الجديد) كان سيُدخلها ثانيةً. هذه الهجرة تنسخ منطق
`logistics.services.sync_import_receipt_from_shipment_stock` على النماذج
التاريخية (الهجرة لا تستورد الخدمات). idempotent، ولا تُنقص كميةً مستلمة.
"""
from decimal import Decimal

from django.db import migrations


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
            moves = moves.filter(notes__contains=f"| صفقة {inv.deal.ref_number} |")
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
        ('logistics', '0087_updated_at_stamp'),
        ('inventory', '0037_remove_product_allow_negative_stock_and_more'),
    ]

    operations = [
        migrations.RunPython(sync_receipts, migrations.RunPython.noop),
    ]
