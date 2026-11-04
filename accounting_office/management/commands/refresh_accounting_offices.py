"""`refresh_accounting_offices` — «حدّث المكتب ليوم X» لكلّ مكتبٍ مرخَّص.

**الـcron على الخادم خطوةُ نشرٍ لا كود**: الأمرُ يُشغَّل صباح كل يوم،
و`GET today/` يُشغّله أيضاً عند أوّل فتحٍ في اليوم — فالمكتبُ يعمل حتّى قبل أن
يُضاف الـcron. **ولا مُجدوِل في المستودع.**

**المكاتبُ المرخَّصة وحدها** (`core.modules.module_enabled`): شركةٌ بقالبٍ آخر لا
زبائنَ مكتبٍ لها، وتشغيلُ تحديثها صفُّ سجلٍّ في غير محلّه.

    python manage.py refresh_accounting_offices                # اليوم
    python manage.py refresh_accounting_offices --day 2026-02-01

وتشغيلُه مرّتين في اليوم نفسه لا يغيّر شيئاً: `refresh_office` idempotent،
و`OfficeRefreshRun` صفٌّ واحدٌ لكل (مكتب، يوم).
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounting_office import services
from core.modules import MODULES, module_enabled
from tenants.models import Tenant

MODULE_KEY = "accounting_office"


class Command(BaseCommand):
    help = "يحفظ ما حان وقته من التزامات وشغلات مكاتب المحاسبة المرخَّصة ليوم."

    def add_arguments(self, parser):
        parser.add_argument(
            "--day",
            default="",
            help="اليوم بصيغة YYYY-MM-DD (الافتراض: تاريخ اليوم المحلّي).",
        )

    def handle(self, *args, **options):
        day = self._day(options.get("day") or "")
        if MODULE_KEY not in MODULES:
            raise CommandError(f"الوحدة «{MODULE_KEY}» غير معروفةٍ في MODULES.")
        offices = [
            tenant for tenant in Tenant.objects.order_by("pk")
            if module_enabled(tenant, MODULE_KEY)
        ]
        for tenant in offices:
            counts = services.refresh_office(tenant, day=day)
            self.stdout.write(
                f"{tenant.pk} · {tenant.CompanyName} — "
                f"{day.isoformat()}: شغلات {counts['created_tasks']} · "
                f"التزامات {counts['created_obligations']}"
            )
        if not offices:
            self.stdout.write("لا مكاتب محاسبة مرخَّصة — لا شيء يُحدَّث.")

    def _day(self, raw):
        """`--day` كما ورد، والافتراضُ `timezone.localdate()` — وفسادُه `CommandError`."""
        value = (raw or "").strip()
        if not value:
            return timezone.localdate()
        try:
            day = parse_date(value)
        except ValueError:
            day = None
        if day is None:
            raise CommandError(f"--day غير صالح: «{value}» — الصيغة YYYY-MM-DD.")
        return day
