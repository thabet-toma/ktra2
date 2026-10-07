"""يسوّي عمولات حوالاتٍ رُحّلت دفعاتها قبل أن يكتبها قيد الدفعة — بطلب.

حتى ee6a0c7a كانت `LogisticsPayment.transfer_cost` تُطلب من الصندوق («خصم المبلغ +
العمولة») ولا يكتبها قيد، فرصيد الصندوق الدفتري أعلى من الحقيقي بمجموعها (إنتاج
كترا: 126 دفعة، 2,611.45$). الترحيل الجديد صحيح (`logistics.payment_posting`)؛ هذا
الأمر للقديم.

    python manage.py post_unbooked_transfer_fees --tenant 1
    python manage.py post_unbooked_transfer_fees --tenant 1 --apply [--date 2026-10-07]

القراءة (الافتراض): كل دفعة مرحّلة بعمولة بلا سطر «مصاريف بنكية وعمولات» في قيدها
ولا قيد تسوية حيّ لها، مجمّعةً بصندوقها، بتقدير القيمة بالشيكل؛ وقيود جرد الصندوق
(CASH_COUNT) على الصناديق نفسها، والتواريخ الشاذة.

--apply: قيد تسوية لكل دفعة **بتاريخ --date** (افتراضاً اليوم) — تصحيحٌ في الفترة
المفتوحة لا إعادة كتابة لفتراتٍ مضت: مدين «مصاريف بنكية وعمولات» / دائن الصندوق،
مرجعه `LOGISTICS_PAYMENT_FEE` برقم الدفعة فيعرفه الترحيل (`transfer_fee_adjusted`)
ولا يخصمها ثانيةً إن أُعيد ترحيل الدفعة. صندوق الدولار بطبقات FIFO: تُستهلك الطبقات
بقيمة العمولة وتُقيَّد بتكلفتها (لا بسعر الدفعة — 3.5 الافتراضية القديمة في أغلبها)،
فيتطابق رصيدا الدولار والشيكل للصندوق مع ما فيه فعلاً. غيره: العمولة × سعر الدفعة.

يرفض --apply كاملاً:
  - إن قصر دولار الصندوق عن عمولاته (لا تسوية جزئية).
  - إن وُجد جرد صندوقٍ مرحّل على صندوقٍ منها إلا مع --confirm-not-absorbed: فرقُ
    الجرد ربما امتصّ العمولات «عجزاً»، وتسويتها فوقه تخصمها مرّتين.
صفقات الأرشيف (`archive_deal_ids`) تُعرض ولا تُسوّى: قيدها بوحدةٍ أخرى.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounting.fx_fifo import consume_fifo
from accounting.services import (
    CashBoxLedgerAccount,
    JournalHeader,
    JournalLine,
    create_audit_log,
    post_journal,
)
from logistics.landed_cost import payment_usd_rate
from logistics.models import LogisticsPayment
from logistics.payment_posting import (
    BANK_CHARGES_ACCOUNT_NAME,
    TRANSFER_FEE_ADJUST_REFERENCE,
    _bank_charges_account_id,
    archive_deal_ids,
    transfer_fee_adjusted,
)

Q2 = Decimal('0.01')
Q4 = Decimal('0.0001')
MIN_SANE_YEAR = 2000


def _fifo_link(account_id, tenant_id):
    link = CashBoxLedgerAccount.objects.filter(tenant_id=tenant_id, account_id=account_id).first()
    if link and link.fx_lots.filter(remaining_fc__gt=0).exists():
        return link
    return None


def _simulate_fifo(link, amounts):
    """تكلفة كل مبلغ بالشيكل لو استُهلكت الطبقات بالترتيب — قراءة فقط. None = لا يكفي."""
    lots = [[lot.remaining_fc, lot.rate] for lot in
            link.fx_lots.filter(remaining_fc__gt=0).order_by('lot_date', 'id')]
    costs = []
    for fc in amounts:
        remaining, cost = fc.quantize(Q4), Decimal('0')
        for lot in lots:
            if remaining <= 0:
                break
            take = min(lot[0], remaining)
            cost += (take * lot[1]).quantize(Q2)
            lot[0] -= take
            remaining -= take
        if remaining > 0:
            return None
        costs.append(cost.quantize(Q2))
    return costs


class Command(BaseCommand):
    help = "تسوية عمولات حوالاتٍ مرحّلة بلا قيد عمولة (قراءة افتراضاً، --apply للكتابة)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")
        parser.add_argument("--apply", action="store_true", help="اكتب قيود التسوية.")
        parser.add_argument("--date", help="تاريخ قيود التسوية YYYY-MM-DD (افتراضاً اليوم).")
        parser.add_argument(
            "--confirm-not-absorbed", action="store_true",
            help="جرد الصندوق المعروض لم يمتصّ هذه العمولات «عجزاً» — اسوّها رغم وجوده.")

    def handle(self, *args, **options):
        tenant_id = options["tenant"]
        try:
            date = (datetime.date.fromisoformat(options["date"]) if options["date"]
                    else timezone.localdate())
        except ValueError:
            raise CommandError("--date بصيغة YYYY-MM-DD.")

        rows, skipped_archive = self._collect(tenant_id)
        by_box = defaultdict(list)
        for p in rows:
            by_box[p.bank_account_id].append(p)
        plans = {box_id: self._plan(tenant_id, box_id, pays) for box_id, pays in by_box.items()}
        counts = self._cash_counts(tenant_id, list(by_box))
        self._report(rows, plans, counts, skipped_archive)

        if not options["apply"] or not rows:
            return
        short = [plan['name'] for plan in plans.values() if plan['costs'] is None]
        if short:
            raise CommandError(
                f"رصيد الدولار في {', '.join(short)} غير كافٍ لعمولاته — لا تسوية جزئية؛ "
                "راجع طبقات الصندوق أولاً.")
        if counts and not options["confirm_not_absorbed"]:
            raise CommandError(
                "على هذه الصناديق جرد صندوق مرحّل — ربما امتصّ العمولات «عجزاً». "
                "راجعه، وإن لم يمتصّها فأعد التشغيل بـ--confirm-not-absorbed.")
        self._apply(tenant_id, date, plans)

    # ── القراءة ────────────────────────────────────────────────────────────

    def _collect(self, tenant_id):
        payments = (
            LogisticsPayment.objects
            .filter(Q(deal__tenant_id=tenant_id)
                    | Q(deal__isnull=True, shipment__tenant_id=tenant_id))
            .filter(is_posted=True, journal__isnull=False, bank_account__isnull=False,
                    transfer_cost__gt=0)
            .select_related('deal', 'shipment', 'bank_account')
            .order_by('id')
        )
        booked = set(JournalLine.objects.filter(
            journal_id__in=payments.values('journal_id'),
            account__name=BANK_CHARGES_ACCOUNT_NAME,
        ).values_list('journal_id', flat=True))
        archived = archive_deal_ids(tenant_id)
        rows, skipped = [], []
        for p in payments:
            if p.journal_id in booked or transfer_fee_adjusted(p):
                continue
            (skipped if p.deal_id in archived else rows).append(p)
        return rows, skipped

    def _plan(self, tenant_id, box_id, pays):
        link = _fifo_link(box_id, tenant_id)
        if link:
            costs = _simulate_fifo(link, [Decimal(str(p.transfer_cost)) for p in pays])
        else:
            costs = [(Decimal(str(p.transfer_cost)) * payment_usd_rate(p)).quantize(Q2)
                     for p in pays]
        return {'name': pays[0].bank_account.name, 'link': link, 'pays': pays, 'costs': costs}

    def _cash_counts(self, tenant_id, box_ids):
        return list(JournalHeader.objects.filter(
            tenant_id=tenant_id, reference_type='CASH_COUNT', is_posted=True,
            lines__account_id__in=box_ids,
        ).distinct().order_by('transaction_date'))

    def _report(self, rows, plans, counts, skipped_archive):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"دفعات مرحّلة بعمولة بلا قيد عمولة: {len(rows)}"))
        today = timezone.localdate()
        for plan in plans.values():
            usd = sum((Decimal(str(p.transfer_cost)) for p in plan['pays']), Decimal('0'))
            kind = 'FIFO بتكلفة الطبقات' if plan['link'] else 'بسعر الدفعة'
            if plan['costs'] is None:
                w(self.style.ERROR(
                    f"  {plan['name']}: {len(plan['pays'])} دفعة، {usd:.2f}$ — "
                    "رصيد الدولار في الطبقات غير كافٍ"))
                continue
            w(f"  {plan['name']}: {len(plan['pays'])} دفعة، {usd:.2f}$ ≈ "
              f"{sum(plan['costs'], Decimal('0')):.2f} ₪ ({kind})")
            for p in plan['pays']:
                d = p.transfer_date
                if d and (d.year < MIN_SANE_YEAR or d > today):
                    ref = p.deal.ref_number if p.deal_id else (
                        p.shipment.shipment_number if p.shipment_id else '—')
                    w(self.style.WARNING(f"    تاريخ شاذ: دفعة #{p.pk} ({ref}) بتاريخ {d}"))
        if counts:
            w(self.style.WARNING(f"جرد صندوق مرحّل على هذه الصناديق: {len(counts)} قيد"))
            for jh in counts:
                w(f"    #{jh.pk} {jh.transaction_date} — {jh.description}")
        if skipped_archive:
            w(f"صفقات أرشيف (لا تُسوّى): {', '.join(f'#{p.pk}' for p in skipped_archive)}")

    # ── الكتابة ────────────────────────────────────────────────────────────

    def _apply(self, tenant_id, date, plans):
        from tenants.models import Tenant

        tenant = Tenant.objects.get(pk=tenant_id)
        charges_id = _bank_charges_account_id(tenant)
        done = failed = 0
        for plan in plans.values():
            for p in plan['pays']:
                try:
                    with transaction.atomic():
                        locked = LogisticsPayment.objects.select_for_update().get(pk=p.pk)
                        if transfer_fee_adjusted(locked):
                            continue
                        fee = Decimal(str(locked.transfer_cost))
                        if plan['link']:
                            amount, _breakdown = consume_fifo(
                                plan['link'], fee, reference_type=TRANSFER_FEE_ADJUST_REFERENCE,
                                reference_id=locked.pk)
                        else:
                            amount = (fee * payment_usd_rate(locked)).quantize(Q2)
                        ref = locked.deal.ref_number if locked.deal_id else (
                            locked.shipment.shipment_number if locked.shipment_id else '—')
                        desc = (f"تسوية عمولة حوالة غير مقيّدة | دفعة #{locked.pk} {locked.title} "
                                f"| {ref} | دُفعت {locked.transfer_date} | {fee}$")[:500]
                        jh = post_journal(
                            tenant_id=tenant_id, transaction_date=date,
                            reference_type=TRANSFER_FEE_ADJUST_REFERENCE, reference_id=locked.pk,
                            description=desc, idempotent=False,
                            lines_data=[
                                {"account": charges_id, "debit": amount, "credit": Decimal("0"),
                                 "description": desc},
                                {"account": locked.bank_account_id, "debit": Decimal("0"),
                                 "credit": amount, "description": desc},
                            ])
                        create_audit_log(
                            tenant=tenant, user=None, action='UPDATE',
                            model_name='LogisticsPayment', object_id=locked.pk,
                            change_details=(f"تسوية عمولة حوالة {fee}$ لم يكتبها قيد الدفعة "
                                            f"#{locked.journal_id}: القيد #{jh.pk} بـ{amount} ₪"),
                        )
                    done += 1
                except Exception as exc:  # فترة مغلقة مثلاً — لا تمسّ غيرها
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"  #{p.pk}: {exc}"))
        self.stdout.write(self.style.SUCCESS(f"--apply: سُوّيت {done}، فشلت {failed}."))
