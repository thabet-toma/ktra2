"""ترحيل دفعات وكيل الشحن المؤكَّدة غير المرحّلة — بالمسار نفسه للدفع من الصندوق.

    python manage.py post_pending_agent_payments --tenant 1                       # تقرير فقط
    python manage.py post_pending_agent_payments --tenant 1 --apply --box <ext> --ids 183 189

كانت الشاشة تحفظ دفعة الوكيل بـPATCH قائمة الدفعات «مؤكّدة» بلا قيد، وزرّ الترحيل بلا
مستدعٍ منذ f1afc66b. التقرير يعرض كل دفعة (بلا صفقة، مؤكّدة/مدفوعة، غير مرحّلة) مع
موانعها (`payment_posting.agent_payment_blockers`) وتنبيهاتٍ للمراجعة: السعر 3.6 (غالباً ما
كانت الشاشة تعبّئه)، ومبلغ أقل من 1$، ووكيلٌ نوعه مورد. `--apply` يرحّل **المختار وحده**
من الصندوق المحدّد، كل دفعة في معاملتها (`post_shipment_agent_payment`)؛ فشلُ واحدة لا
يوقف الباقي. لا يحذف ولا يعدّل مبلغاً ولا سعراً.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounting.api import cash_box_ledger_account
from logistics.models import LogisticsPayment
from logistics.payment_posting import agent_payment_blockers, post_shipment_agent_payment
from tenants.models import Tenant

SUSPECT_RATE = Decimal('3.6')


def _warnings(payment) -> list[str]:
    notes = []
    if payment.usd_to_ils is not None and Decimal(str(payment.usd_to_ils)) == SUSPECT_RATE:
        notes.append('السعر 3.6 — غالباً ما كانت الشاشة تعبّئه تلقائياً')
    if Decimal(str(payment.amount or 0)) < 1:
        notes.append('مبلغ أقل من 1$')
    agent = getattr(payment.shipment, 'shipping_agent', None) if payment.shipment else None
    if agent is not None and agent.partner_type != 'FreightForwarder':
        notes.append(f'الوكيل نوعه {agent.partner_type} لا وكيل شحن')
    return notes


class Command(BaseCommand):
    help = "يعرض دفعات وكيل الشحن المؤكَّدة غير المرحّلة؛ --apply --box --ids يرحّل المختار."

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=int, required=True)
        parser.add_argument('--apply', action='store_true', help='رحّل الدفعات المحددة بـ--ids')
        parser.add_argument('--box', help='external_id للصندوق الذي خرجت منه الدفعات')
        parser.add_argument('--ids', type=int, nargs='+', help='أرقام الدفعات المراد ترحيلها')

    def handle(self, *args, tenant, apply, box, ids, **options):
        company = Tenant.objects.filter(pk=tenant).first()
        if company is None:
            raise CommandError(f"الشركة {tenant} غير موجودة.")
        pending = list(
            LogisticsPayment.objects.filter(
                tenant=company, deal__isnull=True, shipment__isnull=False, is_posted=False,
            ).filter(
                Q(status__in=('Confirmed', 'Paid')) | Q(confirmed_by_supplier=True),
            ).select_related('shipment', 'shipment__shipping_agent').order_by('pk')
        )
        for payment in pending:
            ship = payment.shipment
            agent = ship.shipping_agent.name if ship.shipping_agent_id else '—'
            blockers = agent_payment_blockers(payment)
            flags = '؛ '.join(blockers) if blockers else 'قابلة للترحيل'
            warns = _warnings(payment)
            self.stdout.write(
                f"#{payment.pk} {ship.shipment_number or ship.pk} · {agent} · {payment.amount}$ × "
                f"{payment.usd_to_ils or '—'} · {payment.transfer_date or '—'} — {flags}"
                + (f" ⚠ {'؛ '.join(warns)}" if warns else ""))
        self.stdout.write(f"{len(pending)} دفعة وكيل مؤكَّدة غير مرحّلة.")

        if not apply:
            self.stdout.write("تقرير فقط — للترحيل: --apply --box <external_id> --ids <أرقام>")
            return
        if not box or not ids:
            raise CommandError("--apply يحتاج --box و--ids: لا يُرحَّل شيءٌ لم يُختَر.")
        box_account = cash_box_ledger_account(company.pk, box)
        if box_account is None:
            raise CommandError(f"الصندوق {box} غير مربوط بحساب محاسبي في هذه الشركة.")
        by_id = {p.pk: p for p in pending}
        posted = 0
        for pk in ids:
            payment = by_id.get(pk)
            if payment is None:
                self.stdout.write(self.style.ERROR(f"✗ #{pk}: ليست دفعة وكيل مؤكَّدة غير مرحّلة في هذه الشركة"))
                continue
            try:
                if not (payment.cash_box_external_id or '').strip():
                    payment.cash_box_external_id = box[:128]
                    payment.save(update_fields=['cash_box_external_id'])
                journal = post_shipment_agent_payment(payment, box_account=box_account)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"✗ #{pk}: {getattr(exc, 'message', exc)}"))
                continue
            posted += 1
            self.stdout.write(self.style.SUCCESS(f"✓ #{pk} ← قيد #{journal.pk}"))
        self.stdout.write(f"رُحّلت {posted} من {len(ids)}.")
