"""لقطات بنود الاستحقاقات المرحّلة قبل «سجل الاستحقاق» — قراءةٌ افتراضاً.

كل قيد استحقاقٍ (تخليص، شحن الوكيل، إرسالية) وكل قيد «تعديل استحقاق» بلا لقطة يأخذ لقطةً
بسطر «إجمالي» بمستحقّه من قيوده (`logistics.domain.accrual_snapshots.ensure_snapshots`) —
بنودُها الأصلية ضاعت بالكتابة فوقها، فتُعبّأ لاحقاً من الشاشة بمجموعٍ مطابق. لا قيد يُكتب:

    python manage.py backfill_accrual_snapshots --tenant 1          # قراءة
    python manage.py backfill_accrual_snapshots --tenant 1 --apply  # إنشاء اللقطات
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from logistics.domain.accrual_snapshots import _party_credit, ensure_snapshots
from logistics.domain.party_accruals import _label, accrual_journal_ids
from logistics.models import AccrualLineSnapshot, LocalShipment, LogisticsClearance, LogisticsShipment


class Command(BaseCommand):
    help = "لقطات «إجمالي» لقيود الاستحقاق وتعديلاتها القائمة (قراءة افتراضاً، --apply ينشئها)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")
        parser.add_argument("--apply", action="store_true", help="أنشئ اللقطات الناقصة.")

    def _documents(self, tenant_id):
        yield from (('clearance', obj) for obj in LogisticsClearance.objects.filter(
            tenant_id=tenant_id, journal__isnull=False).select_related('shipment').order_by('pk'))
        yield from (('freight', obj) for obj in LogisticsShipment.objects.filter(
            tenant_id=tenant_id, freight_is_posted=True, freight_journal__isnull=False).order_by('pk'))
        yield from (('local', obj) for obj in LocalShipment.objects.filter(
            tenant_id=tenant_id, is_posted=True, journal__isnull=False).order_by('pk'))

    def handle(self, *args, **options):
        w = self.stdout.write
        apply = options["apply"]
        w(self.style.MIGRATE_HEADING("لقطات بنود الاستحقاق الناقصة"))
        documents = journals = 0
        with transaction.atomic():
            for kind, obj in self._documents(options["tenant"]):
                chain = accrual_journal_ids(kind, obj)
                have = set(AccrualLineSnapshot.objects.filter(
                    journal_id__in=chain).values_list('journal_id', flat=True))
                missing = [j for j in chain if j not in have]
                if not missing:
                    continue
                documents += 1
                journals += len(missing)
                steps = ' ← '.join(
                    f"#{j} {_party_credit(chain[:chain.index(j) + 1]):.2f}" for j in missing)
                w(f"  {_label(kind, obj)}: {steps}")
                if apply:
                    ensure_snapshots(kind, obj)
        if not journals:
            w(self.style.SUCCESS("لا ناقص — لكل قيد استحقاقٍ لقطته."))
            return
        if apply:
            w(self.style.SUCCESS(f"أُنشئت {journals} لقطة لـ{documents} مستند (سطر «إجمالي»؛ لا قيود)."))
        else:
            w(f"الناقص {journals} لقطة لـ{documents} مستند. أعد التشغيل بـ --apply لإنشائها.")
