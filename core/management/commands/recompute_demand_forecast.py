"""يملأ `inventory.ProductDemandForecast`: يشغّل هولت أسبوعياً — #32 على الخريطة.

لا Celery هنا (قرارٌ مقيس، `core/replenishment.py`) — مجدول النظام (cron/Task
Scheduler) يستدعي هذا الأمر مرّةً في الأسبوع. مُعاوَد الاستدعاء بلا أثر:
هولت يُعاد حسابه من حركة المخزون الخام في كل تشغيل، فتشغيلان في نفس الأسبوع
يعطيان نفس الأرقام بالضبط.

    python manage.py recompute_demand_forecast              # كل الشركات
    python manage.py recompute_demand_forecast --tenant 3    # شركةٌ واحدة

لا شيء يقرأ الجدول بعد هذا الأمر في هذه التذكرة — التقرير (#33) يُوصَل لاحقاً.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core.replenishment import holt_forecast, weekly_demand_series
from inventory.models import ProductDemandForecast

#: سقف دفعة الكتابة الواحدة — كافٍ لتغطية كتالوج شركة كاملة بنداءٍ واحد
#: (`bulk_update`/`bulk_create`)، فلا يكبر عدد الاستعلامات مع عدد المنتجات.
BATCH_SIZE = 2000


def _recompute_tenant(tenant_id: int) -> int:
    """يكتب/يحدّث سلسلة كل منتجٍ له حركةٌ في هذه الشركة. يُعيد عدد الصفوف المكتوبة."""
    series, last_week = weekly_demand_series(tenant_id)
    if not series:
        return 0

    existing = {
        row.product_id: row
        for row in ProductDemandForecast.objects.filter(
            tenant_id=tenant_id, product_id__in=list(series.keys()),
        )
    }

    to_update = []
    to_create = []
    for product_id, weekly in series.items():
        result = holt_forecast(weekly)
        row = existing.get(product_id)
        if row is not None:
            row.level = result["level"]
            row.trend = result["trend"]
            row.weeks_observed = result["weeks_observed"]
            row.mad = result["mad"]
            row.last_week_start = last_week
            to_update.append(row)
        else:
            to_create.append(ProductDemandForecast(
                tenant_id=tenant_id,
                product_id=product_id,
                level=result["level"],
                trend=result["trend"],
                weeks_observed=result["weeks_observed"],
                mad=result["mad"],
                last_week_start=last_week,
            ))

    if to_update:
        ProductDemandForecast.objects.bulk_update(
            to_update, ["level", "trend", "weeks_observed", "mad", "last_week_start"],
            batch_size=BATCH_SIZE,
        )
    if to_create:
        ProductDemandForecast.objects.bulk_create(to_create, batch_size=BATCH_SIZE)
    return len(to_update) + len(to_create)


class Command(BaseCommand):
    help = (
        "يحسب سلسلة الطلب الأسبوعية بهولت لكل منتجٍ له حركة مخزون، ويكتب "
        "المستوى والاتجاه في inventory.ProductDemandForecast. مُعاوَد "
        "الاستدعاء بلا أثر — يُشغَّل أسبوعياً من مجدول النظام."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", type=int, default=None,
            help="شركةٌ واحدة بمعرِّفها. بلا هذا الخيار: كل الشركات.",
        )

    def handle(self, *args, **options):
        tenant_id = options.get("tenant")
        if tenant_id is not None:
            tenant_ids = [tenant_id]
        else:
            from tenants.models import Tenant

            tenant_ids = list(Tenant.objects.values_list("TenantID", flat=True))

        total = 0
        for tid in tenant_ids:
            written = _recompute_tenant(tid)
            total += written
            self.stdout.write(f"شركة #{tid}: {written} منتجاً")

        self.stdout.write(self.style.SUCCESS(f"تم — {total} صفّاً عبر {len(tenant_ids)} شركة."))
