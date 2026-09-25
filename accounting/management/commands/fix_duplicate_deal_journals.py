"""إصلاح بيانات — قيدُ شراءِ الصفقة مُرحَّلٌ مرّتين (قيدان لصفقةٍ واحدة).

المسارُ القديم الذي كان يكتب `LOGISTICS_DEAL` (شراء بضاعة Auto) لم يكن idempotent:
كلُّ حفظٍ للصفقة كتب قيداً جديداً بلا أن يُلغي سابقَه. النتيجةُ في الإنتاج
(الشركة 1، قيست 2026-09-17): **69 صفقةً و138 قيداً — قيدان لكلِّ صفقة بلا استثناء**،
فمصروفُ الشراء وذمّةُ المورّد **مضاعفان**: 1,702,362.31 مرحَّلةً مقابل 836,174.10
إجماليَ الصفقات نفسِها.

القيدُ الزائد ليس حدثاً تجارياً وقع، فهو يُحذَف كما يَحذف إلغاءُ الترحيلِ قيدَه
(سابقةُ `unpost_document`) لا يُعكَس: العكسُ يُبقي في المصروف والذمّة مبلغاً
مضاعفاً ثمّ يطرحه بتاريخِ اليوم، فيكذب على كلِّ فترةٍ بينهما.

القاعدة (لكلّ صفقة، وكلُّها شرطٌ لا يُتخطّى):
  - مجموعةٌ من **قيدين مرحَّلين بالضبط** لنفس `reference_id` — ثلاثةٌ فأكثر تُترك.
  - كلُّ قيدٍ **سطران**: مدينُ مصروفٍ ودائنُ حسابِ المورّد نفسِه في القيدين.
  - الصفقةُ موجودةٌ في نفس الشركة.
  - **المبلغان متساويان** ⇒ يُحذف الأحدثُ ويبقى الأوّل.
  - **مختلفان وأحدُهما يساوي إجماليَ الصفقة** (الصفقةُ عُدِّلت وأُعيد ترحيلُها)
    ⇒ يبقى المطابقُ ويُحذف الآخر.
  - **مختلفان ولا واحدَ يطابق** ⇒ يُترك ويُعرَض للمراجعة: لا يُعرف أيُّهما الحقّ.

لا يمسّ مبلغاً ولا حساباً في قيدٍ باقٍ — يحذف القيدَ الزائد وأسطرَه وحدها، ويسجّل
في سجلّ التدقيق. آمنٌ للتكرار: التشغيلُ الثاني لا يجد مجموعةً من قيدين.

    python manage.py fix_duplicate_deal_journals [--tenant N]           # تقرير فقط
    python manage.py fix_duplicate_deal_journals [--tenant N] --apply
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from accounting.models import JournalHeader
from accounting.services import create_audit_log
from logistics.models import LogisticsDeal

logger = logging.getLogger(__name__)

DEAL_TYPE = "LOGISTICS_DEAL"


def _journal_total(journal):
    return journal.lines.aggregate(x=Sum("base_debit"))["x"] or Decimal("0")


def _plan_for(deal_id, journals, deals):
    """يعيد (القيدُ الباقي، القيدُ المحذوف، السبب) أو (None, None, سببُ الترك)."""
    if len(journals) != 2:
        return None, None, f"عددُ القيود {len(journals)} لا اثنان"
    for journal in journals:
        if journal.lines.count() != 2:
            return None, None, "قيدٌ ليس سطرين"
    first, second = sorted(journals, key=lambda j: j.id)
    amounts = {j.id: _journal_total(j) for j in (first, second)}
    if amounts[first.id] == amounts[second.id]:
        return first, second, "المبلغان متساويان — يبقى الأوّل"

    deal = deals.get(deal_id)
    if deal is None:
        return None, None, "الصفقةُ غير موجودة"
    total = Decimal(str(deal.total_amount or "0"))
    matches = [j for j in (first, second) if amounts[j.id] == total]
    if len(matches) != 1:
        return None, None, (
            f"لا قيدَ واحداً يطابق إجماليَ الصفقة {total} "
            f"(المبلغان {amounts[first.id]} و{amounts[second.id]})"
        )
    keep = matches[0]
    drop = second if keep.id == first.id else first
    return keep, drop, f"المطابقُ لإجمالي الصفقة {total} يبقى"


class Command(BaseCommand):
    help = "حذفُ قيد شراء الصفقة المكرَّر (قيدان لصفقة واحدة) — تقرير فقط بلا --apply."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="حصر بشركة واحدة (TenantID).")
        parser.add_argument("--apply", action="store_true", help="نفّذ الحذف فعلياً.")

    def handle(self, *args, **opts):
        headers = JournalHeader.objects.filter(reference_type=DEAL_TYPE, is_posted=True)
        if opts["tenant"]:
            headers = headers.filter(tenant_id=opts["tenant"])

        groups = defaultdict(list)
        for journal in headers.order_by("id"):
            groups[(journal.tenant_id, journal.reference_id)].append(journal)

        deal_ids = {ref for _tenant, ref in groups if ref}
        deals = {d.pk: d for d in LogisticsDeal.all_objects.filter(pk__in=deal_ids)}

        planned, skipped = [], []
        for (tenant_id, deal_id), journals in sorted(groups.items()):
            if len(journals) == 1:
                continue
            keep, drop, reason = _plan_for(deal_id, journals, deals)
            if drop is None:
                skipped.append((tenant_id, deal_id, reason))
            else:
                planned.append((tenant_id, deal_id, keep, drop, _journal_total(drop), reason))

        per_tenant = defaultdict(lambda: [0, Decimal("0")])
        for tenant_id, _deal, _keep, _drop, amount, _reason in planned:
            per_tenant[tenant_id][0] += 1
            per_tenant[tenant_id][1] += amount
        for tenant_id, (count, amount) in sorted(per_tenant.items()):
            self.stdout.write(
                f"شركة {tenant_id}: {count} قيداً مكرَّراً بمجموع {amount} "
                "(مصروفٌ وذمّةُ مورّدٍ مضاعفان)"
            )
        for tenant_id, deal_id, reason in skipped:
            self.stdout.write(self.style.WARNING(
                f"شركة {tenant_id} — الصفقة {deal_id}: متروكةٌ للمراجعة — {reason}"
            ))

        if not planned:
            self.stdout.write(self.style.SUCCESS("لا قيدَ صفقةٍ مكرَّراً."))
            return
        if not opts["apply"]:
            self.stdout.write(self.style.WARNING(
                f"\nسيُحذف: {len(planned)} قيداً. أعد التشغيل بـ--apply للتنفيذ."
            ))
            return

        done = 0
        for tenant_id, deal_id, keep, drop, amount, reason in planned:
            with transaction.atomic():
                fresh = JournalHeader.objects.select_for_update().filter(
                    pk=drop.pk, reference_type=DEAL_TYPE, is_posted=True).first()
                if fresh is None or _journal_total(fresh) != amount:
                    self.stdout.write(self.style.WARNING(
                        f"القيد #{drop.pk} تغيّر تحت القفل — تُخُطّي."))
                    continue
                create_audit_log(
                    fresh.tenant, None, "DELETE", "JournalHeader", fresh.pk,
                    {
                        "السبب": "قيدُ شراء صفقةٍ مكرَّر (fix_duplicate_deal_journals)",
                        "الصفقة": deal_id, "المبلغ": str(amount),
                        "القيدُ الباقي": keep.pk, "القاعدة": reason,
                    },
                )
                fresh.lines.all().delete()
                fresh.delete()
                done += 1
        logger.info("fix_duplicate_deal_journals: deleted %s duplicate deal journals.", done)
        self.stdout.write(self.style.SUCCESS(f"\nحُذف: {done} قيداً مكرَّراً."))
