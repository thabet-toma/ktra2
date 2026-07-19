"""يكشف الشحنات التي لا يطابق فيها وكيلُ الشحن الطرفَ المُدائن في قيد الاستحقاق.

كان تغيير/إزالة وكيل الشحن مسموحاً بعد ترحيل الاستحقاق، فتظهر الشحنة «بلا وكيل»
بينما القيد ما يزال يُدائن الوكيل الأصلي. الحفظ صار محروساً؛ هذا الأمر يجد
الشحنات التي انحرفت قبل الحراسة ويُظهر رقم القيد والطرف المُدائن فعلاً.

    python manage.py audit_freight_accruals --tenant 1
"""
from django.core.management.base import BaseCommand, CommandError

from accounting.models import JournalLine
from logistics.models import LogisticsShipment


class Command(BaseCommand):
    help = "كشف تعارض وكيل الشحن مع الطرف المُدائن في قيد استحقاق الشحن."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")

    def handle(self, *args, **options):
        tenant_id = options["tenant"]
        shipments = (
            LogisticsShipment.objects.filter(tenant_id=tenant_id, freight_is_posted=True)
            .select_related("shipping_agent", "freight_journal")
            .order_by("id")
        )
        if not shipments.exists():
            raise CommandError(f"لا توجد شحنات باستحقاق شحن مُرحّل للمستأجر {tenant_id}.")

        problems = 0
        for shipment in shipments:
            journal = shipment.freight_journal
            if journal is None:
                problems += 1
                self.stdout.write(self.style.ERROR(
                    f"  {shipment.shipment_number}: مُعلَّم كمُستحق بلا قيد مرتبط."
                ))
                continue

            credited = list(
                JournalLine.objects.filter(journal=journal, credit__gt=0)
                .select_related("partner")
            )
            credited_partners = {
                line.partner_id: getattr(line.partner, "name", None) for line in credited
            }
            agent_id = shipment.shipping_agent_id
            agent_name = getattr(shipment.shipping_agent, "name", "— بلا وكيل —")

            if agent_id in credited_partners and agent_id is not None:
                continue

            problems += 1
            actual = "، ".join(
                f"{name or '—'} (#{pid})" for pid, name in credited_partners.items()
            ) or "لا يوجد سطر دائن"
            self.stdout.write(self.style.WARNING(
                f"  {shipment.shipment_number}: الشحنة تعرض «{agent_name}» "
                f"لكن القيد #{journal.pk} يُدائن: {actual}"
            ))

        if problems:
            self.stdout.write(self.style.WARNING(
                f"\nشحنات متعارضة: {problems}. "
                "العلاج: ألغِ ترحيل استحقاق الشحن، اضبط الوكيل الصحيح، ثم أعد الاستحقاق."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("كل الاستحقاقات مطابقة لوكلائها."))
