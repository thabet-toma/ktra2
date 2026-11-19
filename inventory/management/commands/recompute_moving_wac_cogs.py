# -*- coding: utf-8 -*-
"""إعادة احتساب تكلفة المبيعات التاريخية بالمتوسط المرجّح المتحرك (moving WAC)
«لحظة البيع» لشركة الجرابعه — بدل التكلفة المسجّلة وقت الاستيراد (لقطة AverageCost).

المنهج: يُعاد تشغيل دفتر حركة كل منتج **زمنياً** (حسب movement_date ثم id):
  - تكلفة افتتاحية لكل منتج = AverageCost من الملف (أفضل تقدير لتكلفة ما قبل البيانات).
  - كل حركة IN ترفع المتوسط (WAC)؛ إن كان الرصيد ≤ 0 يُضبط المتوسط = تكلفة الوارد
    (حارس ضد انحراف المخزون السالب — مشكلة name-mismatch/negative stock).
  - كل حركة بيع (OUT/SALE): التكلفة = الكمية × المتوسط **لحظتها** (لا يتغيّر المتوسط).

يحدّث `StockMovement.total_cost` لحركات البيع (مصدر تقرير أرباح الفواتير) و
`Product.avg_cost` النهائي، ويُرحّل **قيد تسوية إجمالي واحد** يوجّه حصة الحركات
ذات اللقطة الثابتة (`standard`/`last_purchase`) إلى حساب فروقات تكلفة المبيعات،
والباقي إلى ت.ب.م (5101)، والمخزون (1104) بالمجموع الكلّي، فتبقى قائمة الدخل
والميزانية متوازنة.

افتراضياً **معاينة فقط** (لا تعديل). --apply للتنفيذ. خاص بشركة «الجرابعه».
"""
from __future__ import annotations

import csv
import datetime
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from inventory.cogs_method import (
    FIXED_SNAPSHOT_METHODS, MISSING_COST_VARIANCE_ACCOUNT_ERROR,
    build_cogs_adjustment_lines, cost_variance_account_id, sync_fifo_snapshot,
)

DEC = Decimal("0.01")
Q4 = Decimal("0.0001")
TENANT_NAME = 'الجرابعه'
IN_TYPES = {'IN', 'ADJUST_IN', 'RETURN_IN'}


def _norm(s):
    if not s:
        return ''
    return ' '.join(str(s).replace('\t', ' ').split())


class Command(BaseCommand):
    help = 'إعادة احتساب COGS التاريخي بالمتوسط المرجّح المتحرك (لحظة البيع) لشركة الجرابعه.'

    def add_arguments(self, parser):
        parser.add_argument('--csv-dir', required=True, help='مجلد CSV (لقراءة AverageCost الافتتاحي)')
        parser.add_argument('--tenant-id', type=int, default=None)
        parser.add_argument('--apply', action='store_true', help='نفّذ التعديل (الافتراضي: معاينة)')

    def handle(self, *args, **opt):
        from tenants.models import Tenant
        from inventory.models import Product, StockMovement
        from accounting.models import Account
        from accounting.services import post_journal

        csv_dir = Path(opt['csv_dir'])
        # ── حارس الأمان: الجرابعه فقط ──
        if opt['tenant_id'] is not None:
            tenant = Tenant.objects.filter(TenantID=opt['tenant_id']).first()
        else:
            tenant = Tenant.objects.filter(CompanyName=TENANT_NAME).first()
        if not tenant or (tenant.CompanyName or '').strip() != TENANT_NAME:
            raise CommandError(f'حارس الأمان: الشركة ليست «{TENANT_NAME}». رُفض التنفيذ.')
        tid = tenant.TenantID
        apply = opt['apply']

        # ── تكلفة افتتاحية لكل منتج من الملف (norm_name → AverageCost) ──
        opening = {}
        pf = csv_dir / 'Products.csv'
        if pf.exists():
            with open(pf, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f, delimiter=';'):
                    name = _norm(r.get('Name'))
                    if not name:
                        continue
                    try:
                        ac = Decimal(str((r.get('AverageCost') or '0').strip() or '0'))
                    except Exception:
                        ac = Decimal('0')
                    if ac <= 0:
                        try:
                            ac = Decimal(str((r.get('BuyPrice') or '0').strip() or '0'))
                        except Exception:
                            ac = Decimal('0')
                    opening.setdefault(name, ac)

        products = list(Product.objects.filter(tenant_id=tid))
        self.stdout.write(f'المنتجات: {len(products)} | تكاليف افتتاحية من الملف: {len(opening)}')

        total_old = Decimal('0')
        total_new = Decimal('0')
        variance_raw = Decimal('0')
        changed_moves = []      # (movement_id, new_total_cost)
        product_final_avg = {}  # product_id -> final avg
        inv917_old = inv917_new = None

        # فاتورة 917 للمقارنة مع الموقع الأصلي
        from sales.models import SalesInvoice
        inv917 = SalesInvoice.objects.filter(tenant_id=tid, invoice_number='00917').first()
        inv917_id = inv917.id if inv917 else None

        for p in products:
            moves = list(
                StockMovement.objects.filter(tenant_id=tid, product_id=p.id)
                .order_by('movement_date', 'id')
                .only('id', 'movement_type', 'reference_type', 'reference_id',
                      'quantity', 'unit_cost', 'total_cost', 'cogs_method')
            )
            if not moves:
                continue
            avg = opening.get(_norm(p.name_ar), Decimal('0'))
            qty = Decimal('0')
            for m in moves:
                mq = Decimal(str(m.quantity or 0))
                if m.movement_type in IN_TYPES:
                    cost = Decimal(str(m.unit_cost or 0))
                    if qty <= 0:
                        avg = cost if cost > 0 else avg   # حارس السالب
                    else:
                        avg = ((qty * avg) + (mq * cost)) / (qty + mq)
                    qty += mq
                else:
                    # حركة صرف — تكلفة البيع لحظتها
                    if m.reference_type in ('SALE', 'STOCK_ISSUE'):
                        new_tc = (mq * avg).quantize(DEC)
                        old_tc = Decimal(str(m.total_cost or 0))
                        total_old += old_tc
                        total_new += new_tc
                        if m.cogs_method in FIXED_SNAPSHOT_METHODS:
                            variance_raw += (new_tc - old_tc)
                        if new_tc != old_tc:
                            changed_moves.append((m.id, new_tc))
                        if inv917_id and m.reference_id == inv917_id:
                            inv917_old = (inv917_old or Decimal('0')) + old_tc
                            inv917_new = (inv917_new or Decimal('0')) + new_tc
                    qty -= mq
            product_final_avg[p.id] = avg.quantize(Q4)

        delta = (total_new - total_old).quantize(DEC)
        variance_delta = variance_raw.quantize(DEC)
        cogs_delta = delta - variance_delta
        self.stdout.write(self.style.WARNING(
            f'\n=== نتيجة {"التنفيذ" if apply else "المعاينة"} ==='))
        self.stdout.write(f'  ت.ب.م القديمة (لقطة AverageCost) = {total_old.quantize(DEC)}')
        self.stdout.write(f'  ت.ب.م الجديدة (متوسط متحرك لحظة البيع) = {total_new.quantize(DEC)}')
        self.stdout.write(f'  الفرق (Δ) = {delta}  ({"زيادة تكلفة ⇒ ربح أقل" if delta>0 else "نقص تكلفة ⇒ ربح أكثر"})')
        self.stdout.write(f'  حصة ت.ب.م = {cogs_delta}')
        self.stdout.write(f'  حصة فروقات تكلفة المبيعات = {variance_delta}')
        self.stdout.write(f'  حركات بيع ستتغيّر = {len(changed_moves)}')
        if inv917_new is not None:
            rev = Decimal(str(inv917.subtotal_excl_tax - inv917.invoice_discount))
            self.stdout.write(
                f'  فاتورة 00917: تكلفة {inv917_old.quantize(DEC)} → {inv917_new.quantize(DEC)} | '
                f'ربح {(rev-inv917_old).quantize(DEC)} → {(rev-inv917_new).quantize(DEC)} '
                f'(الموقع الأصلي ≈ −682)')

        if not apply:
            self.stdout.write(self.style.SUCCESS('\n[معاينة فقط — لم يُعدَّل شيء. أضف --apply للتنفيذ.]'))
            return

        variance_account_id = None
        if variance_delta != 0:
            try:
                variance_account_id = cost_variance_account_id(tid)
            except ValidationError as exc:
                raise CommandError(MISSING_COST_VARIANCE_ACCOUNT_ERROR) from exc

        # ── التنفيذ ──
        with transaction.atomic():
            for mid, tc in changed_moves:
                movement = StockMovement.objects.get(id=mid, tenant_id=tid)
                fields = {'total_cost': tc, 'unit_cost': (tc / Decimal(str(movement.quantity or 1))).quantize(Q4)}
                movement.total_cost = tc
                if sync_fifo_snapshot(movement):
                    fields['cogs_cost'] = movement.cogs_cost
                StockMovement.objects.filter(id=mid, tenant_id=tid).update(**fields)
            for pid, avg in product_final_avg.items():
                Product.objects.filter(id=pid).update(avg_cost=avg)
            # قيد تسوية إجمالي لفرق ت.ب.م
            journal = None
            if delta != 0 or variance_delta != 0:
                cogs = Account.objects.get(tenant_id=tid, code='5101') if cogs_delta != 0 else None
                invacc = Account.objects.get(tenant_id=tid, code='1104') if delta != 0 else None
                lines = build_cogs_adjustment_lines(
                    cogs_diff=cogs_delta,
                    variance_diff=variance_delta,
                    inv_diff=delta,
                    cogs_account_id=cogs.id if cogs else None,
                    variance_account_id=variance_account_id,
                    inv_account_id=invacc.id if invacc else None,
                    cogs_description='تسوية ت.ب.م (متوسط متحرك)',
                    variance_description='فروقات تكلفة المبيعات (متوسط متحرك)',
                    inv_description='تسوية مخزون (متوسط متحرك)',
                )
                last = (StockMovement.objects.filter(tenant_id=tid, reference_type='SALE')
                        .order_by('-movement_date').values_list('movement_date', flat=True).first())
                txn_date = last or timezone.localdate()
                journal = post_journal(
                    tenant_id=tid, transaction_date=txn_date,
                    reference_type='COGS_MOVING_WAC', reference_id=tid,
                    description='تسوية تكلفة المبيعات — تحويل للمتوسط المرجّح المتحرك (لحظة البيع)',
                    lines_data=lines, idempotent=False,
                )
            self.stdout.write(self.style.SUCCESS(
                f'\n[تم التنفيذ] حركات محدّثة={len(changed_moves)} · منتجات={len(product_final_avg)} · '
                f'قيد التسوية={journal.id if journal else "لا يوجد"}'))
