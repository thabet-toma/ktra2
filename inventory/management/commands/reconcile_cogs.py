"""يصحّح تكلفة البضاعة المباعة وقائمة الدخل لكل منتج وفق نموذج «تكلفة المنتجات»
(متوسط مرجّح بالكمية). يعيد تقييم حركات البيع ويُرحّل قيد تسوية واحداً لكل منتج
بفرق التكلفة (Dr ت.ب.م / Cr المخزون أو العكس) — يعالج البيع قبل وصول الشراء
(COGS=0) والقيم المنحرفة الموجودة.

    python manage.py reconcile_cogs                 # معاينة فقط (dry-run)
    python manage.py reconcile_cogs --apply          # ترحيل التسويات فعلياً
    python manage.py reconcile_cogs --apply --tenant 3
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from inventory.models import Product
from inventory.services import reconcile_product_cogs


class Command(BaseCommand):
    help = "تسوية تكلفة المبيعات لكل منتج (متوسط مرجّح) — يصحّح قائمة الدخل."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='رحّل قيود التسوية فعلياً.')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        qs = Product.objects.all()
        if opts['tenant']:
            qs = qs.filter(tenant_id=opts['tenant'])

        adjusted = 0
        total_diff = Decimal('0')
        for p in qs.iterator():
            res = reconcile_product_cogs(
                tenant_id=p.tenant_id, product_id=p.id, apply=apply)
            diff = Decimal(res['diff'])
            if diff == 0:
                continue
            adjusted += 1
            total_diff += diff
            self.stdout.write(
                f"{p.sku}: COGS {res['old_cogs']} → {res['new_cogs']} "
                f"(فرق {res['diff']}، متوسط {res['average_cost']}"
                + (f"، قيد {res['journal_id']}" if res['journal_id'] else "") + ")"
            )

        verb = 'رُحِّلت تسويات' if apply else 'ستُرحَّل تسويات'
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb}: {adjusted} منتج · صافي فرق التكلفة {total_diff}."))
        if not apply and adjusted:
            self.stdout.write("أعد التشغيل بـ --apply لترحيل قيود التسوية.")
