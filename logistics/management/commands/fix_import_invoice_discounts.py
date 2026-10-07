"""خصم الصفقة المنسوخ على الفواتير الدولية — قراءةٌ افتراضاً.

كان بناء الفاتورة الدولية (`logistics.landed_cost.build_purchase_invoice_row`) ينسخ خصم
الصفقة (دولاراً) إلى فاتورةٍ بالشيكل بضاعتُها من الدفعات التي تشمله أصلاً ⇒ يُخصم مرّتين
(INV-0024/D-0107: 1,200 ⇒ حصّة المورد 40,855.20 لا 42,055.20 ₪، والضريبة على الناقص).
صار صفراً عند البناء وإعادة الحساب؛ والأمر يصلح القائم:

    python manage.py fix_import_invoice_discounts --tenant 1          # قراءة
    python manage.py fix_import_invoice_discounts --tenant 1 --apply  # المسودات

`--apply` يعيد احتساب شحنة كل مسودة (`recalculate_landed_for_shipment` يأخذ الخصم من
الصفّ: صفر) فتُعاد ضريبتها ورسومها وإجماليها. المرحّلة تُعرض فقط — «متأخّرة» في الشاشة،
وتُصحَّح بـ«أعد الاحتساب والترحيل» على شحنتها. صفقات الأرشيف مستثناة (ترحيلها مقفل).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from logistics.landed_cost import recalculate_landed_for_shipment
from logistics.models import PurchaseInvoice
from logistics.payment_posting import invoice_archive_locks
from tenants.models import Tenant


class Command(BaseCommand):
    help = "الفواتير الدولية بخصمٍ منسوخ من الصفقة (قراءة افتراضاً، --apply يصفّر المسودات)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")
        parser.add_argument("--apply", action="store_true", help="صفّر خصم المسودات وأعد احتسابها.")

    def handle(self, *args, **options):
        w = self.stdout.write
        tenant = Tenant.objects.get(pk=options["tenant"])
        invoices = list(PurchaseInvoice.objects.filter(
            tenant=tenant, invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            is_return=False, discount_amount__gt=0,
        ).select_related('shipment', 'deal').order_by('invoice_date', 'pk'))
        locks = invoice_archive_locks(invoices)
        invoices = [inv for inv in invoices if inv.pk not in locks]
        if not invoices:
            w(self.style.SUCCESS("لا فواتير دولية بخصم — لا شيء يُصلح."))
            return

        drafts = [inv for inv in invoices if not inv.is_posted]
        posted = [inv for inv in invoices if inv.is_posted]
        w(self.style.MIGRATE_HEADING("فواتير دولية بخصمٍ منسوخ من الصفقة"))
        for inv in invoices:
            shipment = inv.shipment.shipment_number if inv.shipment_id else '—'
            deal = inv.deal.ref_number if inv.deal_id else '—'
            state = "مرحّلة" if inv.is_posted else "مسودة"
            w(f"  {inv.invoice_number} ({state}، صفقة {deal}، شحنة {shipment}): "
              f"خصم {Decimal(str(inv.discount_amount)):.2f} · إجمالي {Decimal(str(inv.grand_total or 0)):.2f}")
        if posted:
            w(f"المرحّلة ({len(posted)}): «أعد الاحتساب والترحيل» على شحنة كلٍّ منها من الشاشة.")
        if not drafts:
            return
        if not options["apply"]:
            w(f"المسودات ({len(drafts)}): أعد التشغيل بـ --apply لتصفير خصمها وإعادة احتسابها.")
            return

        shipment_ids = sorted({inv.shipment_id for inv in drafts if inv.shipment_id})
        with transaction.atomic():
            for shipment_id in shipment_ids:
                result = recalculate_landed_for_shipment(tenant=tenant, shipment_id=shipment_id)
                w(f"  شحنة #{shipment_id}: {result['message']}")
        for inv in drafts:
            inv.refresh_from_db(fields=['discount_amount', 'grand_total'])
            w(f"  {inv.invoice_number}: خصم {Decimal(str(inv.discount_amount)):.2f} · "
              f"إجمالي {Decimal(str(inv.grand_total or 0)):.2f}")
        w(self.style.SUCCESS(f"أُعيد احتساب {len(drafts)} مسودة بلا خصم."))
