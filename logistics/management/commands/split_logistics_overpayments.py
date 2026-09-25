"""فصل الدفعات الزائدة المرحّلة على مستحقّات التخليص والإرساليات إلى «دفعة تحت الحساب».

    python manage.py split_logistics_overpayments --tenant 1            # تقرير فقط
    python manage.py split_logistics_overpayments --tenant 1 --apply    # تنفيذ

لكل تخليصٍ/إرساليةٍ مرحَّلة الاستحقاق دُفع لها أكثر من مستحقّها: يُعكس قيد أحدث
دفعةٍ (`reverse_journal` — لا حذف)، وتُعاد بالمستحق، ويُنشأ بالزائد سند صرفٍ «تحت
الحساب» للطرف بتاريخها وصندوقها، بلا توزيع — كلّه في `transaction.atomic` لكل دفعة
مع `AccountingAuditLog`. رصيد الطرف والصندوق لا يتغيّران. idempotent: بعد الفصل لا
زائد، فالتشغيل الثاني لا يجد شيئاً. استحقاق الشحن الدولي (دفعات الوكيل بالدولار)
يُعرض تقريراً فقط. المنطق في `logistics/domain/overpayment_split.py`.
"""
from django.core.management.base import BaseCommand, CommandError

from logistics.domain.overpayment_split import split_posted_overpayment
from logistics.domain.party_accruals import accrual_status
from logistics.models import LocalShipment, LogisticsClearance, LogisticsShipment
from tenants.models import Tenant


class Command(BaseCommand):
    help = "يفصل زائد دفعات التخليص/النقل المرحّلة إلى سند صرف «تحت الحساب» (تقرير افتراضاً؛ --apply للتنفيذ)."

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=int, required=True)
        parser.add_argument('--apply', action='store_true', help='نفّذ الفصل (بدونه تقرير فقط)')

    def handle(self, *args, tenant, apply, **options):
        company = Tenant.objects.filter(pk=tenant).first()
        if company is None:
            raise CommandError(f"الشركة {tenant} غير موجودة.")
        docs = [
            ('clearance', c) for c in LogisticsClearance.objects.filter(
                tenant=company, journal__isnull=False).select_related('shipment').order_by('pk')
        ] + [
            ('local', s) for s in LocalShipment.objects.filter(
                tenant=company, is_posted=True, journal__isnull=False).order_by('pk')
        ]
        rows, failed = [], 0
        for kind, obj in docs:
            try:
                row = split_posted_overpayment(kind, obj, apply=apply)
            except Exception as exc:  # فترة مقفلة أو قيدٌ غير متوازن — لا يُسقط الباقي
                failed += 1
                self.stdout.write(self.style.ERROR(f"✗ {kind} #{obj.pk}: {exc}"))
                continue
            if row:
                rows.append(row)
                self._print(row)

        for shipment in LogisticsShipment.objects.filter(
                tenant=company, freight_is_posted=True, freight_journal__isnull=False).order_by('pk'):
            overpaid = accrual_status('freight', shipment)['overpaid']
            if overpaid > 0:
                self.stdout.write(
                    f"• شحن {shipment.shipment_number or shipment.pk}: زائد {overpaid} — "
                    "دفعات الوكيل بالدولار، تُراجَع يدوياً (لا فصل)")

        pending = [r for r in rows if r['action'] in ('report', 'split')]
        verb = "فُصلت" if apply else "قابلة للفصل"
        self.stdout.write(self.style.SUCCESS(
            f"{len(pending)} دفعة زائدة {verb}، {len(rows) - len(pending)} متروكة، {failed} فشلت."
            + ("" if apply else " (تقرير فقط — --apply للتنفيذ)")))

    def _print(self, row):
        head = f"{row['label']} — دفعة #{row['payment']}" if row['payment'] else row['label']
        if row['action'] == 'skip':
            self.stdout.write(f"• {head}: زائد {row['excess']} — متروكة: {row['reason']}")
            return
        tail = f" ← سند #{row['voucher']}" if row['voucher'] else ""
        self.stdout.write(
            f"• {head}: {row['amount']} → {row['new_amount']} + تحت الحساب {row['excess']}{tail}")
