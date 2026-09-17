"""
تصحيح دورات إلغاء ترحيل قديمة لدفعات الصفقات تركت الدفاتر بأثرٍ معكوس (F-1).

النمط القديم (قبل 3358bf7) لإلغاء ترحيل دفعة صفقة كان يُنشئ عكساً مرحّلاً
`LOGISTICS_PAYMENT_UNPOST` **ويُلغي ترحيل الأصل** ويسِمه
«[ملغى ترحيل — عكس مرحّل #R]» ⇒ الدفاتر المرحّلة تحمل العكس وحده. النمط الحالي
يُبقي الأصل مرحّلاً فيتعادلان. هذا الأمر يُعيد الدورات القديمة إلى النمط الحالي:

- فترة الأصل مفتوحة (`assert_dates_open_for_unpost`: فترة مالية مفتوحة + حرّاس
  الفترة الضريبية + لا كشف ض.ق.م نهائي) ⇒ **repost**: يُرحَّل الأصل نفسه عبر
  `post_journal_entry` فيتعادل مع عكسه.
- فترته مقفلة ⇒ **adjust**: قيد تسوية واحد بتاريخ اليوم عبر `post_journal` يعيد
  تطبيق أسطر الأصل (نفس المرجع `LOGISTICS_PAYMENT` للدفعة — فإلغاء ترحيل الصفقة
  و`purge_deals` يشملانه)، والأصل يبقى غير مرحّل ويُوسَم بقيد التسوية.
- العكس القديم لم ينسخ عملة الأصل (سعر 1): إن اختلف أثر الأصل والعكس بالعملة
  الأساسية فإعادة ترحيل الأصل تصفّر الاسمي وتترك فرقاً أساسياً — فتُختار التسوية
  بعملة العكس وسعره (تعادله حرفياً اسمياً وأساسياً).

الشكل الثاني (دفعة `is_posted=True` وقيدها غائب/غير مرحّل/معكوس بوسم) **تقرير فقط**:
الصحيح يتوقف على نيّة لا يقرؤها الكود (هل الدفعة مرحّلة فعلاً؟ هل تغيّر مبلغها بعد
القيد؟) — والدورة القديمة المرتبطة بها تُتخطّى كذلك.

الاستعمال:
  python manage.py fix_logistics_unpost_cycles [--tenant N]           # تقرير فقط
  python manage.py fix_logistics_unpost_cycles [--tenant N] --apply   # تنفيذ

كل صفّ في معاملة ذرّية مستقلة، ويُعاد التحقق منه تحت القفل؛ التشغيل الثاني لا يجد
ما يفعله. لا يُحذف أي قيد.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounting.models import JournalHeader
from accounting.services import (
    assert_dates_open_for_unpost,
    create_audit_log,
    post_journal,
    post_journal_entry,
)
from logistics.models import LogisticsPayment

logger = logging.getLogger(__name__)

ORIGINAL_TYPE = "LOGISTICS_PAYMENT"
REVERSAL_TYPE = "LOGISTICS_PAYMENT_UNPOST"
UNPOST_MARKER = "ملغى ترحيل — عكس مرحّل #"
UNPOST_MARKER_RE = re.compile(r"ملغى ترحيل — عكس مرحّل #(\d+)")
ADJUSTED_MARKER = "صُحِّح بقيد تسوية #"
TOLERANCE = Decimal("0.01")

SHAPE_CYCLE = "reversed_cycle"
SHAPE_PAYMENT = "posted_payment_unposted_journal"


def _effects(journal):
    """صافي الأثر لكل (حساب، طرف): اسمياً وبالعملة الأساسية."""
    nominal, base = defaultdict(Decimal), defaultdict(Decimal)
    for line in journal.lines.all():
        key = (line.account_id, line.partner_id)
        nominal[key] += Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        base[key] += Decimal(str(line.base_debit or 0)) - Decimal(str(line.base_credit or 0))
    return nominal, base


def _cancels(a, b):
    return all(abs(a.get(k, 0) + b.get(k, 0)) <= TOLERANCE for k in set(a) | set(b))


def _amount(journal):
    return sum((Decimal(str(l.debit or 0)) for l in journal.lines.all()), Decimal("0"))


def _lock_reason(original):
    """سبب قفل فترة الأصل، أو None إن كانت مفتوحة لإعادة الترحيل."""
    if not original.transaction_date:
        return "الأصل بلا تاريخ"
    try:
        assert_dates_open_for_unpost(
            original.tenant_id, [original.transaction_date],
            document_label=f"القيد #{original.id}")
    except ValidationError as exc:
        return "؛ ".join(exc.messages)
    return None


def _payment_journal_neutralized(payment):
    journal = payment.journal
    if journal is None:
        return "الدفعة مرحّلة بلا قيد مرتبط"
    if not journal.is_posted:
        return f"قيد الدفعة #{journal.id} غير مرحّل"
    if UNPOST_MARKER in (journal.description or ""):
        return f"قيد الدفعة #{journal.id} معكوسٌ بدورة إلغاء قديمة"
    return None


def collect_rows(tenant_id=None):
    """يبني خطة التصحيح دون أي كتابة. كل صفّ dict."""
    rows = []
    journals = JournalHeader.objects.filter(
        reference_type=ORIGINAL_TYPE, description__contains=UNPOST_MARKER,
    ).prefetch_related("lines")
    if tenant_id:
        journals = journals.filter(tenant_id=tenant_id)
    journals = list(journals.order_by("id"))

    reversal_ids = {
        int(rid) for j in journals for rid in UNPOST_MARKER_RE.findall(j.description or "")
    }
    reversals = {
        r.id: r for r in JournalHeader.objects.filter(
            pk__in=reversal_ids, reference_type=REVERSAL_TYPE, is_posted=True,
        ).prefetch_related("lines")
    }
    payments = {
        p.id: p for p in LogisticsPayment.all_objects.filter(
            pk__in={j.reference_id for j in journals if j.reference_id},
        ).only("id", "journal_id", "is_posted")
    }

    # عكسٌ صُحِّح سابقاً: أصلٌ يسمّيه صار مرحّلاً أو وُسم بقيد تسوية.
    claimed = {}
    pending = []
    for j in journals:
        rids = [int(x) for x in UNPOST_MARKER_RE.findall(j.description or "")]
        if j.is_posted or ADJUSTED_MARKER in (j.description or ""):
            for rid in rids:
                claimed.setdefault(rid, j.id)
        else:
            pending.append((j, rids))

    # عكسٌ يسمّيه أصلٌ ما زالت دفعته تشير إليه (الشكل الثاني) — لا يُصحَّح أيٌّ من أصوله.
    overlap = {
        rid: j.reference_id for j, rids in pending for rid in rids
        if j.reference_id in payments and payments[j.reference_id].journal_id == j.id
    }

    for j, rids in pending:
        row = {
            "tenant": j.tenant_id, "payment": j.reference_id, "shape": SHAPE_CYCLE,
            "orig": j, "rev": None, "action": "skip", "reason": "",
        }
        rows.append(row)
        if len(set(rids)) != 1:
            row["reason"] = "وسم العكس يسمّي أكثر من قيد — مراجعة يدوية"
            continue
        rev = reversals.get(rids[0])
        row["rev_id"] = rids[0]
        if rev is None or rev.tenant_id != j.tenant_id or rev.reference_id != j.reference_id:
            row["reason"] = (
                f"العكس #{rids[0]} غير موجود مرحّلاً بنوع {REVERSAL_TYPE} "
                "على نفس الدفعة والشركة")
            continue
        row["rev"] = rev
        orig_nominal, orig_base = _effects(j)
        rev_nominal, rev_base = _effects(rev)
        if not _cancels(orig_nominal, rev_nominal):
            row["reason"] = f"أسطر العكس #{rev.id} لا تعاكس أسطر الأصل — مراجعة يدوية"
            continue
        if rev.id in claimed:
            row["reason"] = (
                f"العكس #{rev.id} يُعادَل بالأصل #{claimed[rev.id]} — "
                "أصلٌ مكرر لا يُرحَّل ثانيةً")
            continue
        if rev.id in overlap:
            row["reason"] = (
                f"الدفعة #{overlap[rev.id]} ما زالت تشير إلى أصلٍ لهذا العكس (الشكل الثاني) — "
                "تصحيح الدورة وحده يترك دفعةً مرحّلة بلا أثر؛ قرار يدوي")
            continue
        claimed[rev.id] = j.id

        base_cancels = _cancels(orig_base, rev_base)
        # التسوية تعادل العكس القائم في الدفاتر: بعملة الأصل وسعره إن تطابق
        # أثرهما الأساسي، وإلا بعملة العكس وسعره (العكس القديم لم ينسخ العملة).
        row["fx_source"] = j if base_cancels else rev
        lock = _lock_reason(j)
        if lock:
            row["action"], row["reason"] = "adjust", f"فترة الأصل مقفلة: {lock}"
        elif not base_cancels:
            row["action"] = "adjust"
            row["reason"] = (
                f"سعر الأصل {j.exchange_rate} ≠ سعر العكس {rev.exchange_rate}: "
                "إعادة الترحيل تترك فرقاً بالعملة الأساسية")
        else:
            row["action"], row["reason"] = "repost", "فترة الأصل مفتوحة"

    shape2 = LogisticsPayment.all_objects.filter(is_posted=True).filter(
        Q(journal__isnull=True) | Q(journal__is_posted=False)
        | Q(journal__description__contains=UNPOST_MARKER)
    ).select_related("journal", "deal", "shipment")
    if tenant_id:
        shape2 = shape2.filter(
            Q(tenant_id=tenant_id) | Q(deal__tenant_id=tenant_id)
            | Q(shipment__tenant_id=tenant_id))
    for payment in shape2.order_by("id"):
        reason = _payment_journal_neutralized(payment)
        if reason is None:
            continue
        tenant = payment.tenant_id or getattr(payment.deal, "tenant_id", None) or getattr(
            payment.shipment, "tenant_id", None)
        rows.append({
            "tenant": tenant, "payment": payment.id, "shape": SHAPE_PAYMENT,
            "orig": payment.journal, "rev": None, "action": "report",
            "reason": (
                f"{reason} — تقرير فقط: إعادة الترحيل أو إلغاؤه قرارٌ على نيّة الدفعة "
                "ومبلغها الحالي لا يُستنتج من الكود"),
        })
    return rows


def _format(row):
    orig = row["orig"]
    rev = row["rev"]
    rev_id = rev.id if rev is not None else row.get("rev_id")
    return " | ".join([
        f"tenant={row['tenant']}",
        f"payment=#{row['payment']}",
        f"orig=#{orig.id}" if orig is not None else "orig=-",
        f"date={orig.transaction_date}" if orig is not None else "date=-",
        f"amount={_amount(orig)}" if orig is not None else "amount=-",
        f"rev=#{rev_id}" if rev_id else "rev=-",
        f"shape={row['shape']}",
        f"action={row['action']}",
        row["reason"],
    ])


def _repost(row):
    orig_id, rev_id = row["orig"].id, row["rev"].id
    with transaction.atomic():
        orig = JournalHeader.objects.select_for_update().get(pk=orig_id)
        if orig.is_posted or ADJUSTED_MARKER in (orig.description or ""):
            return f"تخطٍّ: الأصل #{orig_id} صُحِّح سابقاً"
        if not JournalHeader.objects.filter(pk=rev_id, is_posted=True).exists():
            return f"تخطٍّ: العكس #{rev_id} لم يعد مرحّلاً"
        lock = _lock_reason(orig)
        if lock:
            raise ValidationError(f"فترة الأصل صارت مقفلة: {lock}")
        tag = f" [أُعيد ترحيله يعادل العكس #{rev_id} — fix_logistics_unpost_cycles]"
        JournalHeader.objects.filter(pk=orig_id).update(
            description=((orig.description or "").strip() + tag)[:500])
        post_journal_entry(orig_id)
        create_audit_log(
            tenant=orig.tenant, user=None, action="POST", model_name="JournalHeader",
            object_id=orig_id,
            change_details=(
                f"تصحيح دورة إلغاء ترحيل قديمة: أُعيد ترحيل القيد #{orig_id} ليعادل "
                f"العكس المرحّل #{rev_id} (دفعة #{row['payment']})"),
        )
    return f"repost: القيد #{orig_id} مرحّل"


def _adjust(row):
    orig_id, rev_id = row["orig"].id, row["rev"].id
    with transaction.atomic():
        orig = JournalHeader.objects.select_for_update().get(pk=orig_id)
        if orig.is_posted or ADJUSTED_MARKER in (orig.description or ""):
            return f"تخطٍّ: الأصل #{orig_id} صُحِّح سابقاً"
        if not JournalHeader.objects.filter(pk=rev_id, is_posted=True).exists():
            return f"تخطٍّ: العكس #{rev_id} لم يعد مرحّلاً"
        lines_data = [
            {
                "account": line.account_id,
                "debit": line.debit or Decimal("0"),
                "credit": line.credit or Decimal("0"),
                "partner": line.partner_id,
                "cost_center": line.cost_center_id,
                "description": f"تسوية قيد #{orig_id}: {line.description or ''}",
            }
            for line in orig.lines.all().order_by("id")
        ]
        fx = row["fx_source"]
        adj = post_journal(
            tenant_id=orig.tenant_id,
            transaction_date=timezone.localdate(),
            reference_type=ORIGINAL_TYPE,
            reference_id=orig.reference_id,
            description=(
                f"[تصحيح دورة إلغاء ترحيل] إعادة تطبيق القيد #{orig_id} المعكوس "
                f"بالقيد #{rev_id} — {row['reason']}"),
            lines_data=lines_data,
            currency=fx.currency,
            exchange_rate=Decimal(str(fx.exchange_rate or 1)),
            idempotent=False,
        )
        tag = f" [{ADJUSTED_MARKER}{adj.id} — fix_logistics_unpost_cycles]"
        JournalHeader.objects.filter(pk=orig_id).update(
            description=((orig.description or "").strip() + tag)[:500])
        create_audit_log(
            tenant=orig.tenant, user=None, action="POST", model_name="JournalHeader",
            object_id=adj.id,
            change_details=(
                f"تصحيح دورة إلغاء ترحيل قديمة: قيد تسوية #{adj.id} يعيد تطبيق القيد "
                f"#{orig_id} (فترته مقفلة/سعره مختلف) ويعادل العكس #{rev_id} "
                f"(دفعة #{row['payment']})"),
        )
    return f"adjust: قيد تسوية #{adj.id} بتاريخ {adj.transaction_date}"


class Command(BaseCommand):
    help = (
        "كشف وتصحيح دورات إلغاء ترحيل دفعات الصفقات القديمة (أصل غير مرحّل + عكس مرحّل). "
        "تقرير فقط افتراضياً؛ --apply للتنفيذ."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="TenantID (الافتراضي: كل الشركات)")
        parser.add_argument("--apply", action="store_true", help="نفّذ التصحيح (الافتراضي تقرير فقط)")

    def handle(self, *args, **options):
        tenant_id = options.get("tenant")
        apply = options.get("apply")
        rows = collect_rows(tenant_id)
        self.stdout.write(
            f"fix_logistics_unpost_cycles: {len(rows)} صفّاً"
            f"{f' (tenant={tenant_id})' if tenant_id else ''} — "
            f"{'تنفيذ' if apply else 'تقرير فقط (مرّر --apply للتنفيذ)'}"
        )
        for row in rows:
            self.stdout.write(_format(row))

        if not apply:
            return
        done = failed = 0
        for row in rows:
            handler = {"repost": _repost, "adjust": _adjust}.get(row["action"])
            if handler is None:
                continue
            label = f"orig=#{row['orig'].id} payment=#{row['payment']}"
            try:
                result = handler(row)
            except Exception as exc:  # صفٌّ فاشل لا يوقف البقية — معاملته تراجعت وحدها
                failed += 1
                logger.exception("fix_logistics_unpost_cycles failed: %s", label)
                messages = getattr(exc, "messages", None) or [str(exc)]
                self.stdout.write(self.style.ERROR(f"  خطأ {label}: {'؛ '.join(messages)}"))
                continue
            done += 1
            logger.info("fix_logistics_unpost_cycles %s → %s", label, result)
            self.stdout.write(self.style.SUCCESS(f"  {label} → {result}"))
        self.stdout.write(f"انتهى: {done} نُفِّذ، {failed} فشل.")
