"""
سكريبت تنظيف صفوف الدفعات المكررة (نفس deal + payment_number).
يُشغَّل مرة واحدة قبل تفعيل migration القيد الفريد:

    python manage.py cleanup_duplicate_payments          # معاينة فقط
    python manage.py cleanup_duplicate_payments --apply   # تنفيذ فعلي
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from logistics.models import LogisticsPayment, LogisticsDeal


class Command(BaseCommand):
    help = "كشف وحذف (ناعم) صفوف الدفعات المكررة لنفس الصفقة ورقم القسط"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="تنفيذ الحذف الناعم فعلياً (بدونه: معاينة فقط)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]

        dupes = (
            LogisticsPayment.objects.filter(is_deleted=False, deal__isnull=False)
            .values("deal_id", "payment_number")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .order_by("deal_id", "payment_number")
        )

        if not dupes.exists():
            self.stdout.write(self.style.SUCCESS("لا توجد صفوف مكررة."))
            return

        total_removed = 0
        for g in dupes:
            deal_id = g["deal_id"]
            pn = g["payment_number"]
            rows = list(
                LogisticsPayment.objects.filter(
                    deal_id=deal_id,
                    payment_number=pn,
                    is_deleted=False,
                ).order_by("id")
            )

            posted = [r for r in rows if r.is_posted]
            unposted = [r for r in rows if not r.is_posted]

            if posted:
                keep = posted[0]
                to_remove = posted[1:] + unposted
            else:
                keep = rows[0]
                to_remove = rows[1:]

            try:
                deal_ref = LogisticsDeal.objects.filter(pk=deal_id).values_list(
                    "ref_number", flat=True
                ).first() or deal_id
            except Exception:
                deal_ref = deal_id

            self.stdout.write(
                f"  صفقة {deal_ref} قسط #{pn}: "
                f"{len(rows)} صفوف — إبقاء #{keep.id} "
                f"({'مرحّل' if keep.is_posted else 'غير مرحّل'}) "
                f"— حذف {[r.id for r in to_remove]}"
            )

            if apply:
                for r in to_remove:
                    if r.is_posted and r.journal_id:
                        self.stdout.write(
                            self.style.WARNING(
                                f"    تخطي #{r.id} — مرحّل مع قيد #{r.journal_id}. "
                                f"أَلغِ ترحيله يدوياً أولاً."
                            )
                        )
                        continue
                    r.delete()
                    total_removed += 1
                    self.stdout.write(f"    حذف ناعم #{r.id}")

        if apply:
            self.stdout.write(
                self.style.SUCCESS(f"تم حذف {total_removed} صف(وف) مكرر(ة).")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "معاينة فقط — أضف --apply لتنفيذ الحذف الناعم."
                )
            )
