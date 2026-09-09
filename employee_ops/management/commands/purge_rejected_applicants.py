"""حذفُ بيانات المتقدّمين المرفوضين بعد أجل الاحتفاظ (المواصفة #186 — §٨).

**العطبُ الذي يُصلحه هذا الأمر:** `EmployeeOpsSettings.rejected_retention_months`
كان حقلاً في الجدول وشاشةً في الإعدادات **بلا قارئٍ واحد** — أي وعدٌ للشركة بأنّ
بياناتِ المرفوضين تُحذف بعد أجلٍ، ولا شيءَ يحذفها. وحقلُ سياسةٍ لا ينفّذه كودٌ
أسوأُ من غيابه: يطمئنّ المالكُ إلى ما لا يقع.

والمواصفة صريحة: «سِيَرُ المرفوضين وبياناتُهم تُحذف بعد ١٢ شهراً (إعدادٌ للشركة،
والصفرُ يعني لا حذف)، **والحذف يشمل الملفّ المرفوع لا السجلّ وحده**» — لأنّ
حذفَ الصفّ وحده يترك السيرةَ حيّةً على المزوّد الخارجيّ، ورابطُها هو الصلاحية.

هؤلاء ليسوا مستخدمي المنصة ولا عملاءها، والاحتفاظُ ببياناتهم بلا أجلٍ التزامٌ
بلا مقابل.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.media_views import destroy_cloudinary_asset

from employee_ops.models import EmployeeOpsSettings, JobApplicant

#: متوسّطُ طول الشهر بالأيّام — الأجلُ سياسةُ احتفاظٍ لا موعدُ استحقاق، فالتقريبُ
#: هنا مقصودٌ ولا يستدعي `dateutil` لأجل يومٍ أو يومين.
DAYS_PER_MONTH = 30


class Command(BaseCommand):
    help = "حذف بيانات المتقدّمين المرفوضين بعد انقضاء أجل الاحتفاظ لكل شركة."

    #: عدّاداتُ آخرِ تشغيل — يقرؤها المستدعي بعد `call_command(Command(), ...)`.
    stats: dict | None = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="حساب وطباعة ما سيُحذف دون حذف أي صف أو ملف.",
        )
        parser.add_argument(
            "--tenant",
            type=int,
            default=None,
            help="قصر التشغيل على شركة واحدة.",
        )

    def handle(self, *args, **opts):
        dry_run = opts.get("dry_run", False)
        tenant_filter = opts.get("tenant")

        stats = {
            "deleted": 0,
            "files_deleted": 0,
            "tenants_scanned": 0,
            "tenants_disabled": 0,
        }

        settings_qs = EmployeeOpsSettings.objects.all()
        if tenant_filter is not None:
            settings_qs = settings_qs.filter(tenant_id=tenant_filter)

        now = timezone.now()
        for row in settings_qs.iterator():
            stats["tenants_scanned"] += 1
            months = row.rejected_retention_months or 0
            if months <= 0:
                # **الصفرُ يعني لا حذف** — قرارُ الشركة، لا قيمةٌ فارغةٌ تُعامَل
                # كـ«احذف الآن». الخلطُ بينهما يمحو بياناتِ شركةٍ اختارت الاحتفاظ.
                stats["tenants_disabled"] += 1
                continue

            cutoff = now - timezone.timedelta(days=months * DAYS_PER_MONTH)
            # الشركةُ في الفلتر صراحةً: أمرُ إدارةٍ لا يمرّ بحارس `require_module`،
            # فلا شيءَ يفلتر عنه غير هذا السطر.
            doomed = JobApplicant.objects.filter(
                tenant_id=row.tenant_id,
                status=JobApplicant.STATUS_REJECTED,
                updated_at__lt=cutoff,
            )

            for applicant in doomed.iterator():
                if applicant.cv_url:
                    if not dry_run:
                        # أفضلُ جهد: فشلُ المزوّد لا يمنع حذفَ الصفّ، لكنّه يُسجَّل.
                        destroy_cloudinary_asset(applicant.cv_url)
                    stats["files_deleted"] += 1
                if not dry_run:
                    applicant.delete()
                stats["deleted"] += 1

        self.stats = stats
        self.stdout.write(self._format(stats, dry_run=dry_run))
        return None

    def _format(self, stats: dict, *, dry_run: bool) -> str:
        lines = ["\nتقرير حذف بيانات المتقدّمين المرفوضين:"]
        if dry_run:
            lines.append("  [وضع المعاينة --dry-run: لم يُحذف شيء]")
        lines.extend([
            f"  - شركات فُحصت: {stats['tenants_scanned']}",
            f"  - شركات أوقفت الحذف (أجل الاحتفاظ = صفر): {stats['tenants_disabled']}",
            f"  - متقدّمون حُذفوا: {stats['deleted']}",
            f"  - سِيَر ذاتية حُذفت من التخزين: {stats['files_deleted']}",
        ])
        return "\n".join(lines)
