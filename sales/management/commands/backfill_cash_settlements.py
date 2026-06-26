"""T-CASH2 — تسوية البيع النقدي للفواتير المرحَّلة قديماً (قبل الأتمتة).

فواتير البيع النقدية التي رُحِّلت قبل ربط التسوية التلقائية بقيت تَدين ذمم العميل
بلا تحصيل، فظهر العميل «مديناً» في كشف الحساب. يُنشئ هذا الأمر «سند قبض» تلقائياً
بكامل المتبقّي لكل فاتورة بيع نقدية مرحَّلة غير مسدَّدة — بإعادة استخدام نفس منطق
الترحيل (`_auto_settle_cash_sale`)، فهو آمن للتكرار (يعتمد على المتبقّي فلا يُسوّي
مرتين).

    python manage.py backfill_cash_settlements            # عرض فقط (dry-run)
    python manage.py backfill_cash_settlements --apply     # تطبيق التسوية فعلياً
    python manage.py backfill_cash_settlements --apply --tenant 1
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from sales.models import SalesInvoice
from sales.services import _auto_settle_cash_sale


class Command(BaseCommand):
    help = "تسوية فواتير البيع النقدية المرحَّلة غير المسدَّدة بسند قبض تلقائي."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='طبّق التسوية فعلياً.')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        qs = SalesInvoice.objects.filter(
            status=SalesInvoice.STATUS_POSTED,
            invoice_type=SalesInvoice.INVOICE_CASH,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        )
        if opts['tenant']:
            qs = qs.filter(tenant_id=opts['tenant'])

        settled = 0
        total = Decimal("0")
        for inv in qs.iterator():
            remaining = (
                Decimal(str(inv.grand_total or 0)) - Decimal(str(inv.amount_paid or 0))
            ).quantize(Decimal("0.01"))
            if remaining <= Decimal("0.01"):
                continue
            settled += 1
            total += remaining
            self.stdout.write(
                f"{inv.invoice_number}: متبقٍّ {remaining} — "
                f"{getattr(inv.customer, 'name', '') or inv.customer_id}"
            )
            if apply:
                _auto_settle_cash_sale(inv, user=None)

        verb = 'سُوِّيت' if apply else 'ستُسوّى'
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb}: {settled} فاتورة نقدية (إجمالي {total})."
        ))
        if not apply and settled:
            self.stdout.write("أعد التشغيل بـ --apply لتطبيق التسوية.")
