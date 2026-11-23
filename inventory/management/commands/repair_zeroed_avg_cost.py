# -*- coding: utf-8 -*-
"""إصلاح كلفة المنتجات القديمة التي صُفّرت خطأً دون تغيير الحركات أو الطبقات.

المصدر آخر حركة صادر صفّرت كلفة موجبة، أو آخر لقطة بعد حركة بكلفة موجبة
عندما وقع التصفير بين الحركات. الافتراض معاينة؛ `--apply` يكتب و`--exclude` يستثني،
و`--set pk=cost` يضبط كلفة المالك لمنتجات مصفَّرة مسمّاة.
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from inventory.models import Product, StockMovement
from inventory.services import repair_zeroed_avg_cost, set_owner_avg_cost


class Command(BaseCommand):
    help = (
        "يستعيد avg_cost المصفّرة "
        "(معاينة؛ --apply للتطبيق و--exclude للاستثناء و--set لكلفة المالك)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None,
                            help="معرّف الشركة (اختياري؛ غيابه يشمل كل الشركات).")
        parser.add_argument("--apply", action="store_true",
                            help="تطبيق التحديث على Product.avg_cost فعلاً.")
        parser.add_argument("--exclude", default=None,
                            help="معرّفات المنتجات المستثناة مفصولة بفواصل.")
        parser.add_argument("--set", default=None,
                            help="كلفة المالك لمنتجات مصفَّرة: أزواج pk=cost مفصولة بفواصل.")

    def _parse_exclude(self, raw):
        excluded = set()
        if raw is not None:
            for item in raw.split(","):
                try:
                    excluded.add(int(item))
                except ValueError:
                    raise CommandError(f"عنصر غير صالح في --exclude: {item}")
        return excluded

    def _parse_set(self, raw, excluded):
        owner_costs = {}
        if raw is None:
            return owner_costs
        for item in raw.split(","):
            pk_text, sep, cost_text = item.partition("=")
            if not sep or "=" in cost_text:
                raise CommandError(f"عنصر غير صالح في --set: {item}")
            try:
                pk, cost = int(pk_text), Decimal(cost_text)
            except (ValueError, InvalidOperation):
                raise CommandError(f"عنصر غير صالح في --set: {item}")
            if not cost.is_finite():
                raise CommandError(f"عنصر غير صالح في --set: {item}")
            if cost.quantize(Decimal("0.0001")) <= 0:
                raise CommandError(f"كلفة غير موجبة في --set: {item}")
            if pk in owner_costs:
                raise CommandError(f"معرّف مكرّر في --set: {pk}")
            owner_costs[pk] = cost
        both = sorted(excluded & owner_costs.keys())
        if both:
            raise CommandError(f"منتج مستثنى وموسوم بكلفة المالك معاً: {both}")
        return owner_costs

    def handle(self, *args, **options):
        from tenants.models import Tenant

        tenant_id = options["tenant"]
        apply = options["apply"]
        excluded = self._parse_exclude(options["exclude"])
        owner_costs = self._parse_set(options["set"], excluded)
        if tenant_id is not None:
            tenants = list(Tenant.objects.filter(TenantID=tenant_id))
            if not tenants:
                raise CommandError(f"لا توجد شركة بالمعرّف {tenant_id}.")
        else:
            tenants = list(Tenant.objects.order_by("TenantID"))
        if owner_costs:
            found = set(Product.objects.filter(
                tenant_id__in=[t.TenantID for t in tenants], pk__in=owner_costs,
            ).values_list("pk", flat=True))
            missing = sorted(owner_costs.keys() - found)
            if missing:
                raise CommandError(f"منتجات --set غير موجودة: {missing}")

        counts = dict.fromkeys((
            "excluded", "owner_set", "repaired", "review_later_positive", "review_layer_conflict",
            "review_ambiguous", "skipped_no_history", "skipped_real_layer",
            "skipped_service", "skipped_nonzero",
        ), 0)
        listed = 0
        for tenant in tenants:
            products = Product.objects.filter(
                tenant_id=tenant.TenantID, avg_cost=0,
            ).order_by("pk")
            for product in products.filter(pk__in=excluded):
                counts["excluded"] += 1
                self.stdout.write(self.style.WARNING(
                    f"[{tenant.TenantID}] {product.sku} (مستثنى بأمر المالك): يبقى 0.0000"
                ))
            for product in Product.objects.filter(
                tenant_id=tenant.TenantID, pk__in=owner_costs,
            ).order_by("pk"):
                res = set_owner_avg_cost(product, owner_costs[product.pk], apply=apply)
                counts[res["status"]] += 1
                if res["status"] == "owner_set":
                    self.stdout.write(
                        f"[{tenant.TenantID}] {product.sku} (كلفة المالك): "
                        f"{res['before']} → {res['after']}"
                    )
                else:
                    self.stdout.write(self.style.WARNING(
                        f"[{tenant.TenantID}] {product.sku} (كلفة المالك — skipped_nonzero):"
                        f" يبقى {res['before']}"
                    ))
            to_repair = products.exclude(pk__in=excluded | owner_costs.keys())
            for product in to_repair:
                res = repair_zeroed_avg_cost(product, apply=apply)
                status = res["status"]
                counts[status] += 1
                if status == "repaired":
                    tag = "تحديث" if apply else "سيُحدَّث"
                    self.stdout.write(
                        f"[{tenant.TenantID}] {product.sku} ({tag}): "
                        f"{res['before']} → {res['after']}"
                        f" · المصدر: {res['source']} #{res['source_movement_id']}"
                    )
                elif status.startswith("review_"):
                    self.stdout.write(self.style.WARNING(
                        f"[{tenant.TenantID}] {product.sku} (مراجعة يدوية — {status}): "
                        f"يبقى {res['before']}"
                        f" · المصدر: {res['source']} #{res['source_movement_id']}"
                    ))
                ids = res["zero_cost_movement_ids"]
                listed += len(ids)
                if status.startswith("skipped_") and ids:
                    self.stdout.write(
                        f"[{tenant.TenantID}] {product.sku} ({status}): يبقى {res['before']}"
                    )
                if ids:
                    movements = StockMovement.objects.filter(
                        tenant_id=tenant.TenantID, product_id=product.pk, pk__in=ids,
                    ).order_by("created_at", "id")
                    for movement in movements:
                        self.stdout.write(
                            f"    حركة #{movement.pk} {movement.movement_type}"
                            f" كمية {movement.quantity}"
                            f" · {movement.movement_date} · {movement.reference_type}"
                            f" #{movement.reference_id} · كلفة صفر"
                        )

        self.stdout.write(
            "الملخّص: " + " · ".join(f"{key}={value}" for key, value in counts.items())
            + f" · zero_cost_movements={listed}"
        )
        if apply:
            self.stdout.write(self.style.SUCCESS(
                f"تمّ إصلاح {counts['repaired']} منتج وضبط {counts['owner_set']} بكلفة المالك."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "[معاينة فقط — لم يُكتب شيء. أعد التشغيل بـ --apply للتطبيق.]"
            ))
