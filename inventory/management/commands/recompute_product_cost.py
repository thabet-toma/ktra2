"""أعد احتساب متوسط تكلفة كل صنف بطريقة «تكلفة المنتجات»: متوسط أسعار وحدات فواتير
الشراء مرجّحاً بكمية كل فاتورة (Σ تكلفة الفواتير ÷ Σ كميات الشراء) — المقام إجمالي
المشترى لا الكمية الحالية، فلا ينحرف المتوسط بسبب البيع قبل وصول الشراء.

يصحّح القيم المنحرفة الموجودة (مثل 3800÷13=292.31 ⇐ 3800÷40=95).

    python manage.py recompute_product_cost            # عرض فقط (dry-run)
    python manage.py recompute_product_cost --apply     # تطبيق التغيير
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from inventory.models import Product
from inventory.services import product_cost_breakdown


class Command(BaseCommand):
    help = "إعادة احتساب avg_cost لكل صنف من فواتير الشراء (متوسط مرجّح بالكمية)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='طبّق التغيير فعلياً.')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        qs = Product.objects.all()
        if opts['tenant']:
            qs = qs.filter(tenant_id=opts['tenant'])

        changed = 0
        for p in qs.iterator():
            res = product_cost_breakdown(tenant_id=p.tenant_id, product_id=p.id)
            if res['invoice_count'] == 0:
                continue
            new_avg = Decimal(res['average_cost'])
            old_avg = Decimal(str(p.avg_cost or 0))
            if abs(new_avg - old_avg) < Decimal('0.0001'):
                continue
            changed += 1
            self.stdout.write(
                f"{p.sku}: {old_avg} → {new_avg} "
                f"({res['invoice_count']} فاتورة، كمية {res['total_purchased_qty']})"
            )
            if apply:
                p.avg_cost = new_avg
                p.save(update_fields=['avg_cost'])

        verb = 'حُدِّث' if apply else 'سيُحدَّث'
        self.stdout.write(self.style.SUCCESS(f"\n{verb}: {changed} صنف."))
        if not apply and changed:
            self.stdout.write("أعد التشغيل بـ --apply لتطبيق التغيير.")
