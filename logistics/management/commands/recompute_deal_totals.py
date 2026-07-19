"""يعيد اشتقاق إجمالي الصفقة (بضاعة − خصم + شحن داخل الصين).

الصفقات التي عُدِّل فيها «شحن داخل الصين» أو الخصم بلا تعديل البنود بقي
`total_amount` فيها قديماً (بضاعة فقط)، فظهرت نسبة إنجاز > 100% و«رصيد لصالحك
عند المورد» وهمي يساوي الشحن بالضبط. الخادم صار يشتقّه في كل حفظ؛ هذا الأمر
يعالج الصفقات القائمة.

    python manage.py recompute_deal_totals --tenant 1            # عرض فقط
    python manage.py recompute_deal_totals --tenant 1 --apply    # تنفيذ
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from logistics.models import LogisticsDeal
from logistics.serializers import _apply_lines_subtotal_and_grand_total


class Command(BaseCommand):
    help = "إعادة اشتقاق total_amount للصفقات (بضاعة − خصم + شحن داخل الصين)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")
        parser.add_argument("--apply", action="store_true", help="نفّذ فعلياً (بدونه عرض فقط)")

    def handle(self, *args, **options):
        tenant_id = options["tenant"]
        apply_changes = options["apply"]

        deals = (
            LogisticsDeal.objects.filter(tenant_id=tenant_id)
            .prefetch_related("items")
            .order_by("id")
        )
        if not deals.exists():
            raise CommandError(f"لا توجد صفقات للمستأجر {tenant_id}.")

        drifted = []
        for deal in deals:
            before = Decimal(str(deal.total_amount or 0))
            lines_subtotal = sum(
                (item.quantity * item.unit_price for item in deal.items.all()),
                Decimal("0"),
            )
            _apply_lines_subtotal_and_grand_total(deal, lines_subtotal)
            after = Decimal(str(deal.total_amount or 0))
            if abs(after - before) > Decimal("0.01"):
                drifted.append((deal, before, after))

        if not drifted:
            self.stdout.write(self.style.SUCCESS("كل الإجماليات مطابقة — لا شيء لتعديله."))
            return

        self.stdout.write(f"صفقات بإجمالي منحرف: {len(drifted)}")
        for deal, before, after in drifted:
            self.stdout.write(
                f"  {deal.ref_number or deal.pk}: {before} → {after} (فرق {after - before})"
            )

        if not apply_changes:
            self.stdout.write(self.style.WARNING("عرض فقط — أضف --apply للتنفيذ."))
            return

        with transaction.atomic():
            for deal, _, _ in drifted:
                deal.save(update_fields=["subtotal", "tax_amount", "total_amount"])
        self.stdout.write(self.style.SUCCESS(f"تم تصحيح {len(drifted)} صفقة."))
