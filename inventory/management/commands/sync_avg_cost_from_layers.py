# -*- coding: utf-8 -*-
"""مزامنة `Product.avg_cost` من متوسط طبقات FIFO المفتوحة (`derived_avg_cost`).

يفحص منتجات الشركة (أو كل الشركات) ويحسب المتوسط المشتق عبر
`inventory.services.sync_avg_cost_from_layers`:
- يضبط المنتجات ذات الرصيد `<= 0` أو المغطّاة بالكامل بالطبقات المفتوحة.
- يتخطّى المنتجات ذات الرصيد الموجب غير المغطّى بالطبقات (`skipped_uncovered`)
  كي لا يضيع `avg_cost` الذي يحتاجه `fifo.backfill_opening_layer`.
- يتخطّى المنتجات التي لا تبقى لها طبقة (لم تكن لها قط، أو محا العكسُ طبقاتِ مستندها)
  إن كان هدفها صفراً وكلفتها غير صفرية، فتبقى كلفتها (`skipped_no_layers`).

الافتراض معاينةٌ لا تكتب شيئاً؛ `--apply` يكتب التعديلات.
"""
from django.core.management.base import BaseCommand, CommandError

from inventory.models import Product
from inventory.services import sync_avg_cost_from_layers


class Command(BaseCommand):
    help = (
        "يزامن avg_cost للمنتجات من متوسط طبقات FIFO المفتوحة "
        "(معاينة افتراضياً؛ --apply للتطبيق)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", type=int, default=None,
            help="معرّف الشركة (اختياري؛ غيابه يشمل كل الشركات).",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="تطبيق التحديث على Product.avg_cost فعلاً.",
        )

    def handle(self, *args, **options):
        from tenants.models import Tenant

        tenant_id = options["tenant"]
        apply = options["apply"]

        if tenant_id is not None:
            tenants = list(Tenant.objects.filter(TenantID=tenant_id))
            if not tenants:
                raise CommandError(f"لا توجد شركة بالمعرّف {tenant_id}.")
        else:
            tenants = list(Tenant.objects.order_by("TenantID"))

        counts = {"synced": 0, "unchanged": 0, "skipped_uncovered": 0, "skipped_no_layers": 0}
        for tenant in tenants:
            products = Product.objects.filter(tenant_id=tenant.TenantID).order_by("pk")
            for product in products:
                res = sync_avg_cost_from_layers(product, apply=apply)
                status = res["status"]
                counts[status] += 1
                if status == "synced":
                    tag = "تحديث" if apply else "سيُحدَّث"
                    self.stdout.write(
                        f"[{tenant.TenantID}] {product.sku} ({tag}): "
                        f"{res['before']} → {res['after']}"
                    )
                elif status == "skipped_uncovered":
                    self.stdout.write(self.style.WARNING(
                        f"[{tenant.TenantID}] {product.sku} (تخطّي — غير مغطّى): "
                        f"يبقى {res['before']}"
                    ))
                elif status == "skipped_no_layers":
                    self.stdout.write(self.style.WARNING(
                        f"[{tenant.TenantID}] {product.sku} (تخطّي — بلا طبقات): "
                        f"يبقى {res['before']}"
                    ))

        self.stdout.write(
            f"الملخّص: synced={counts['synced']} · "
            f"unchanged={counts['unchanged']} · "
            f"skipped_uncovered={counts['skipped_uncovered']} · "
            f"skipped_no_layers={counts['skipped_no_layers']}"
        )
        if apply:
            self.stdout.write(self.style.SUCCESS(f"تمّت مزامنة {counts['synced']} منتج."))
        else:
            self.stdout.write(self.style.WARNING(
                "[معاينة فقط — لم يُكتب شيء. أعد التشغيل بـ --apply للتطبيق.]"
            ))
