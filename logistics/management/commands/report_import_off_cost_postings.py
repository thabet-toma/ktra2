"""الفواتير الدولية المرحّلة قبل «كل ما فيها تكلفة» — قراءةٌ فقط.

قرار المالك (2026-10-07): ضريبة الفاتورة الدولية وكل رسومها تكلفةُ بضاعتها
(`logistics.services.import_invoice_capitalizes_all`). ما رُحِّل قبله ضريبتُه على المدخلات
(1105) أو رسمٌ منه مصروفاً (INV-0022: رسم كترا 1,192.34 على 5309). يعرضها الأمر:

    python manage.py report_import_off_cost_postings --tenant 1

والتصحيح من الشاشة: «أعد الاحتساب والترحيل» على شحنتها (يعيد قيدها تكلفةً ويستلمها كما
كانت)، ثم `reconcile_import_unit_costs --tenant 1 --apply` لمتوسط أصنافها. صفقات الأرشيف
مستثناة — ترحيلها مقفل (`payment_posting.invoice_archive_locks`).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from logistics.models import PurchaseInvoice
from logistics.payment_posting import invoice_archive_locks
from logistics.services import import_invoice_posted_off_cost


class Command(BaseCommand):
    help = "الفواتير الدولية المرحّلة بضريبةٍ على المدخلات أو رسمٍ مصروفاً (قراءة فقط)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")

    def handle(self, *args, **options):
        w = self.stdout.write
        invoices = list(PurchaseInvoice.objects.filter(
            tenant_id=options["tenant"], invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            is_return=False, is_posted=True,
        ).select_related('shipment').order_by('invoice_date', 'pk'))
        locks = invoice_archive_locks(invoices)
        w(self.style.MIGRATE_HEADING("فواتير دولية مرحّلة خارج «كل ما فيها تكلفة»"))
        count, total = 0, Decimal('0')
        for inv in invoices:
            if inv.pk in locks:
                continue
            off = import_invoice_posted_off_cost(inv)
            if not off['tax'] and not off['fees']:
                continue
            count += 1
            amount = off['tax'] + sum((a for _f, a in off['fees']), Decimal('0'))
            total += amount
            shipment = inv.shipment.shipment_number if inv.shipment_id else '—'
            w(f"  {inv.invoice_number} (شحنة {shipment}): خارج التكلفة {amount:.2f}")
            if off['tax']:
                w(f"    ضريبة على المدخلات: {off['tax']:.2f}")
            for fee, fee_amount in off['fees']:
                w(f"    رسم «{fee.description}» مصروفاً: {fee_amount:.2f}")
        if not count:
            w(self.style.SUCCESS("لا فواتير — كل الدولية المرحّلة على القاعدة."))
            return
        w(f"العدد {count} · المجموع {total:.2f}")
        w("التصحيح: «أعد الاحتساب والترحيل» لشحنة كلٍّ منها، ثم "
          "reconcile_import_unit_costs --tenant <n> --apply.")
