# -*- coding: utf-8 -*-
"""حارسُ ثابت طبقات FIFO: Σ`remaining_qty` = max(`quantity_on_hand`، 0) لكلّ صنف.

يُشغَّل بعد أيّ تصحيحٍ كبير (سلسلةُ إلغاء ترحيلٍ وإعادته). يطبع نوعين من الخرق
(`inventory.fifo.layer_balance_gaps`):

- **فائض**: طبقاتٌ مفتوحةٌ أكثرُ من الرصيد — بضاعةٌ وهميّة يُكلَّف منها بيعٌ لاحق وتُضخّم
  القيمةَ المشتقّة من الطبقات. **لا يُصلَح آليّاً أبداً**: أيُّ طبقةٍ هي الوهميّة (الافتتاحيّة
  أم طبقةُ استلام) لا يُعرف إلّا بقراءة حركات الصنف، وقصُّ الخطأ يُحرّك كلفةَ مبيعاتٍ قادمة.
- **غيرُ مغطّى**: رصيدٌ موجبٌ بلا طبقاتٍ تغطّيه (بضاعةٌ سبقت FIFO) — يُرأب كسولاً عند أوّل
  حركة. `--apply` يغلقه الآن بـ`fifo.backfill_opening_layer` نفسِها: طبقةٌ افتتاحيّةٌ بكلفة
  `avg_cost` الجارية، **محايدةٌ على الميزانية بالبناء** — لا قيد، ولا يتغيّر رصيدٌ ولا
  `avg_cost`. هذا وحده ما يكتبه الأمر، وبشركةٍ مسمّاةٍ صراحةً.

بلا `--apply`: معاينةٌ لا تكتب صفّاً.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory import fifo
from inventory.models import Product


class Command(BaseCommand):
    help = (
        "يفحص ثابت طبقات FIFO (Σ الطبقات المفتوحة = max(الرصيد، 0)) ويطبع الأصناف "
        "الخارقة. معاينةٌ افتراضياً؛ --apply يرأب غيرَ المغطّى وحده ولا يمسّ الفائض."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant", type=int, default=None,
            help="معرّف الشركة (افتراضياً: كل الشركات). يلزم مع --apply.",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="يرأب الرصيدَ غيرَ المغطّى بطبقةٍ افتتاحيّة بكلفته الدفتريّة. الفائضُ لا يُمسّ.",
        )

    def handle(self, *args, **opt):
        from tenants.models import Tenant

        tenant_id = opt["tenant"]
        apply = opt["apply"]
        if apply and tenant_id is None:
            raise CommandError("--apply يلزمه --tenant: الرأبُ شركةً شركة.")

        if tenant_id is not None:
            tenants = list(Tenant.objects.filter(TenantID=tenant_id))
            if not tenants:
                raise CommandError(f"لا توجد شركةٌ بالمعرّف {tenant_id}.")
        else:
            tenants = list(Tenant.objects.order_by("TenantID"))

        excess_total = 0
        uncovered_total = 0
        backfilled = 0
        for tenant in tenants:
            gaps = fifo.layer_balance_gaps(tenant_id=tenant.TenantID)
            if not gaps:
                continue
            excess = [g for g in gaps if g["excess"] > 0]
            uncovered = [g for g in gaps if g["uncovered"] > 0]
            excess_total += len(excess)
            uncovered_total += len(uncovered)

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n=== {tenant.CompanyName} (#{tenant.TenantID}) ==="
            ))
            for g in excess:
                self.stdout.write(self.style.ERROR(
                    f"  [فائض] {g['sku']} {g['name']}: الرصيد {g['quantity_on_hand']} · "
                    f"الطبقات المفتوحة {g['open_qty']} · الزائد {g['excess']}"
                ))
            for g in uncovered:
                value = (g["uncovered"] * g["avg_cost"]).quantize(Decimal("0.01"))
                self.stdout.write(
                    f"  [غير مغطّى] {g['sku']} {g['name']}: الرصيد {g['quantity_on_hand']} · "
                    f"الطبقات المفتوحة {g['open_qty']} · الناقص {g['uncovered']} "
                    f"× {g['avg_cost']} = {value}"
                )
            if apply:
                for g in uncovered:
                    with transaction.atomic():
                        prod = Product.objects.select_for_update().get(
                            pk=g["product_id"], tenant_id=tenant.TenantID,
                        )
                        layer = fifo.backfill_opening_layer(
                            tenant_id=tenant.TenantID, product_id=prod.pk,
                            quantity_on_hand=prod.quantity_on_hand, avg_cost=prod.avg_cost,
                        )
                    if layer is not None:
                        backfilled += 1

        self.stdout.write(
            f"\nفائض: {excess_total} صنف · غير مغطّى: {uncovered_total} صنف"
        )
        if apply:
            self.stdout.write(self.style.SUCCESS(
                f"رُئب {backfilled} صنف بطبقةٍ افتتاحيّة (بلا قيدٍ ولا تغييرٍ في الرصيد أو الكلفة)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "[معاينةٌ فقط — لم يُكتَب شيء. --apply --tenant N يرأب غيرَ المغطّى.]"
            ))
        if excess_total:
            self.stdout.write(self.style.ERROR(
                "الفائضُ لا يُصلَح آليّاً: راجع حركات كلّ صنفٍ لتحديد الطبقة الوهميّة."
            ))
