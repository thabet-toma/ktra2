# -*- coding: utf-8 -*-
"""معاينةُ إعادة بناء طبقات FIFO لمقارنة قيمة المخزون المسجَّلة اليوم بقيمةٍ
مُعاد بناؤها من دفتر حركة كل منتج بترتيب FIFO — مواصفة #137.

**لماذا معاينةٌ فقط ولا وجود لـ`--apply` أصلاً**: إعادة بناء الطبقات تُحرّك قيمة
المخزون في الميزانية (Product.avg_cost وبالتبعية حساب المخزون في الميزانية
وحساب تكلفة المبيعات مستقبلاً) — هذا قرارُ مالكٍ ومحاسبٍ لا قرارُ سكربت.
هذا الأمر **يقيس فقط**: يطبع الفرق ليقرّر المالك ومحاسبه هل ينفَّذ ومتى وبأي
قيد تسوية (على نمط `recompute_moving_wac_cogs.py` الذي يُرحّل قيد تسوية —
تنفيذٌ يلزمه تصميمٌ محاسبيٌّ منفصل: أي حساب تسوية، وأي تاريخ، وهل يُرحَّل قيدٌ
إجماليٌّ واحد أم لكل منتج). لا `StockLayer` يُنشأ هنا، ولا `Product` يُعدَّل،
ولا صرفٌ يُستهلَك — كل الحساب في الذاكرة، والمخرَج طباعةٌ فقط.

**مصدر الطبقات**: كل الحركات الواردة — `IN` و`ADJUST_IN` و`RETURN_IN`
(`inventory.services.INBOUND_TYPES`) — لا فواتير الشراء وحدها، لأن المخزون
يدخل من ثلاثة أبواب: الشراء، وفائض الجرد، والمرتجع (وضمنها الأرصدة الافتتاحية
المُدخَلة تسويةً).

**طريقة البناء**: لكل منتجٍ رصيدُه `quantity_on_hand > 0` — الرصيد يُقرأ من
الحقل مباشرةً لا من مجموع الحركات (هو رقم اللحظة الحالية، وهذا بالضبط ما
نقارن قيمته) — نمشي في حركاته الواردة من الأحدث فالأقدم (`movement_date`
تنازلياً ثم `id` تنازلياً) ونأخذ من كلٍّ ما يلزم حتى تُغطّى الكمية. الكمية
التي لا يغطّيها أي واردٍ («اليتيمة» — بضاعةٌ ما قبل البيانات بالتعريف) تأخذ
`Product.avg_cost` الحالي وتقع أقدم طبقةٍ في الرتل (أُخرَج الأولى لو استُهلكت).

**الأداء**: استعلامٌ واحد يجلب كل المنتجات ذات الرصيد الموجب للشركة، واستعلامٌ
واحد يجلب كل حركاتها الواردة معاً، ثم يُجمَّع كل شيء في بايثون — لا استعلام
داخل حلقةٍ لكل منتج (انظر `recompute_moving_wac_cogs.py` لنفس النمط، وإن كان
ذاك يمشي منتجاً منتجاً لأنه يحتاج ترتيب الحركات زمنياً صعوداً لكل منتج على
حدة لحساب متوسطٍ متحرّك — هنا يكفي استعلامان إجماليان لأن الحساب تراكميٌّ من
الأحدث فقط لا يحتاج المشي عبر كامل التاريخ).
"""
from __future__ import annotations

import csv as csv_module
import datetime
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from inventory.models import Product, StockMovement
from inventory.services import INBOUND_TYPES

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")


def _d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def compute_rebuilt_layers(product: Product, movements_desc):
    """يبني طبقات FIFO لمنتجٍ واحد من حركاته الواردة (الأحدث فالأقدم).

    `movements_desc` تكرارٌ من عناصر تحمل `quantity` و`unit_cost` و
    `movement_date` (قواميس أو صفوف `.values()`)، مُرتَّبة مسبقاً من الأحدث
    فالأقدم. يُرجع (layers, orphan_qty):

    - `layers`: قائمة قواميس `{qty, unit_cost, movement_date, is_orphan}` —
      طبقةٌ واحدة لكل حركةٍ وارِدةٍ أُخذ منها (كلياً أو جزئياً)، بالإضافة إلى
      طبقةٍ يتيمة أخيرة إن بقيت كميةٌ غير مغطّاة.
    - `orphan_qty`: الكمية غير المغطّاة (صفرٌ إن غطّتها الواردات كاملةً).

    الكمية اليتيمة تُعطى `movement_date` أقدم من أي طبقةٍ أخرى بُنيت هنا لهذا
    المنتج (يوماً واحداً قبل أقدمها) — فهي أقدم الرتل بالتعريف.
    """
    target = _d(product.quantity_on_hand)
    layers: list[dict] = []
    if target <= 0:
        return layers, Decimal("0.0000")

    covered = Decimal("0")
    for m in movements_desc:
        if covered >= target:
            break
        mqty = _d(m["quantity"])
        if mqty <= 0:
            continue
        take = min(mqty, target - covered)
        if take <= 0:
            continue
        layers.append({
            "qty": take.quantize(Q4),
            "unit_cost": _d(m["unit_cost"]).quantize(Q4),
            "movement_date": m["movement_date"],
            "is_orphan": False,
        })
        covered += take

    orphan_qty = (target - covered).quantize(Q4)
    if orphan_qty > 0:
        dates = [l["movement_date"] for l in layers if l["movement_date"] is not None]
        if dates:
            oldest = min(dates)
            orphan_date = oldest - datetime.timedelta(days=1)
        else:
            created = getattr(product, "created_at", None)
            orphan_date = (created.date() if created else datetime.date(1900, 1, 1))
        layers.append({
            "qty": orphan_qty,
            "unit_cost": _d(product.avg_cost).quantize(Q4),
            "movement_date": orphan_date,
            "is_orphan": True,
        })
    return layers, orphan_qty


class Command(BaseCommand):
    help = (
        "معاينةٌ فقط: يقيس الفرق بين قيمة المخزون المسجَّلة (avg_cost) وقيمةٍ "
        "مُعاد بناؤها من طبقات FIFO للحركات الواردة. لا كتابة إطلاقاً — "
        "لا --apply. مواصفة #137."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id", type=int, default=None,
            help="اقتصر على شركةٍ بعينها (افتراضياً: كل الشركات ذات مخزونٍ موجب)",
        )
        parser.add_argument(
            "--limit", type=int, default=10,
            help="عدد الأصناف المعروضة في جدول الأكثر مساهمةً في الفرق (افتراضي 10)",
        )
        parser.add_argument(
            "--csv", default=None,
            help="مسارٌ اختياري لكتابة تفصيل كل صنف (الملف الوحيد الذي يكتبه هذا الأمر)",
        )

    def handle(self, *args, **opt):
        from tenants.models import Tenant

        tenant_id = opt["tenant_id"]
        limit = opt["limit"]
        csv_path = opt["csv"]

        if tenant_id is not None:
            tenants = list(Tenant.objects.filter(TenantID=tenant_id))
            if not tenants:
                raise CommandError(f"لا توجد شركةٌ بالمعرّف {tenant_id}.")
        else:
            stock_tenant_ids = (
                Product.objects.filter(quantity_on_hand__gt=0)
                .values_list("tenant_id", flat=True)
                .distinct()
            )
            tenants = list(
                Tenant.objects.filter(TenantID__in=stock_tenant_ids).order_by("TenantID")
            )
            if not tenants:
                self.stdout.write("لا توجد أيّ شركةٍ لديها مخزونٌ موجب.")
                return

        csv_file = None
        csv_writer = None
        if csv_path:
            csv_file = open(csv_path, "w", newline="", encoding="utf-8-sig")
            csv_writer = csv_module.writer(csv_file, delimiter=";")
            csv_writer.writerow([
                "TenantID", "CompanyName", "ProductID", "SKU", "Name",
                "QuantityOnHand", "AvgCostOld", "ValueOld", "ValueNew",
                "Diff", "OrphanQty",
            ])

        try:
            for tenant in tenants:
                self._process_tenant(tenant, limit=limit, csv_writer=csv_writer)
        finally:
            if csv_file:
                csv_file.close()

        self.stdout.write(self.style.WARNING(
            "\n[معاينةٌ فقط — لم يُكتَب أو يُعدَّل شيء. تنفيذ إعادة البناء "
            "(--apply) غير موجودٍ في هذا الأمر عمداً: هو قرارُ مالكٍ ومحاسبٍ "
            "منفصل بعد مراجعة هذا التقرير، لا خطوةً تلقائية.]"
        ))

    def _process_tenant(self, tenant, *, limit, csv_writer):
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== {tenant.CompanyName} (#{tenant.TenantID}) ==="
        ))

        products = list(
            Product.objects.filter(tenant_id=tenant.TenantID, quantity_on_hand__gt=0)
            .only("id", "sku", "name_ar", "name_en", "quantity_on_hand", "avg_cost", "created_at")
        )
        if not products:
            self.stdout.write("  لا توجد أصنافٌ برصيدٍ موجب في هذه الشركة.")
            return

        product_ids = [p.id for p in products]
        movements = (
            StockMovement.objects.filter(
                tenant_id=tenant.TenantID,
                product_id__in=product_ids,
                movement_type__in=INBOUND_TYPES,
            )
            .order_by("product_id", "-movement_date", "-id")
            .values("product_id", "quantity", "unit_cost", "movement_date")
        )
        by_product = defaultdict(list)
        for m in movements:
            by_product[m["product_id"]].append(m)

        total_old = Decimal("0")
        total_new = Decimal("0")
        orphan_qty_total = Decimal("0")
        orphan_value_total = Decimal("0")
        orphan_products = 0
        rows = []

        for p in products:
            qty = _d(p.quantity_on_hand)
            avg_cost = _d(p.avg_cost)
            old_value = (qty * avg_cost).quantize(Q4)

            layers, orphan_qty = compute_rebuilt_layers(p, by_product.get(p.id, []))
            new_value = sum(
                (l["qty"] * l["unit_cost"] for l in layers), Decimal("0")
            ).quantize(Q4)
            diff = (new_value - old_value).quantize(Q4)

            total_old += old_value
            total_new += new_value
            if orphan_qty > 0:
                orphan_qty_total += orphan_qty
                orphan_value_total += (orphan_qty * avg_cost).quantize(Q4)
                orphan_products += 1

            name = p.name_ar or p.name_en or p.sku
            rows.append({
                "sku": p.sku, "name": name,
                "old": old_value, "new": new_value, "diff": diff,
                "orphan_qty": orphan_qty,
            })

            if csv_writer:
                csv_writer.writerow([
                    tenant.TenantID, tenant.CompanyName, p.id, p.sku, name,
                    qty.quantize(Q4), avg_cost.quantize(Q4),
                    old_value.quantize(Q2), new_value.quantize(Q2),
                    diff.quantize(Q2), orphan_qty.quantize(Q4),
                ])

        total_diff = (total_new - total_old).quantize(Q4)
        if total_diff > 0:
            sign = "زيادة"
        elif total_diff < 0:
            sign = "نقص"
        else:
            sign = "بلا فرق"

        self.stdout.write(f"  عدد الأصناف ذات رصيدٍ موجب: {len(products)}")
        self.stdout.write(f"  قيمة المخزون المسجَّلة اليوم: {total_old.quantize(Q2)}")
        self.stdout.write(f"  قيمة المخزون بعد إعادة البناء (FIFO): {total_new.quantize(Q2)}")
        if total_old != 0:
            pct = (total_diff / total_old * 100).quantize(Q2)
            self.stdout.write(
                f"  الفرق: {total_diff.quantize(Q2)} ({pct}%) — {sign}"
            )
        else:
            self.stdout.write(
                f"  الفرق: {total_diff.quantize(Q2)} — {sign} "
                "(القيمة المسجَّلة صفر، فالنسبة غير معرَّفة)"
            )

        top = sorted(rows, key=lambda r: abs(r["diff"]), reverse=True)[:limit]
        self.stdout.write(f"  أكثر {len(top)} صنفاً مساهمةً في الفرق (رمز | اسم | قبل | بعد | فرق):")
        for r in top:
            self.stdout.write(
                f"    {r['sku']} | {r['name']} | "
                f"{r['old'].quantize(Q2)} | {r['new'].quantize(Q2)} | {r['diff'].quantize(Q2)}"
            )

        self.stdout.write(
            f"  الكمية اليتيمة الإجمالية: {orphan_qty_total.quantize(Q4)} "
            f"عبر {orphan_products} صنفاً (قيمتها بكلفتها الحالية ≈ "
            f"{orphan_value_total.quantize(Q2)})"
        )
