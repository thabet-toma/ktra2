"""يكشف دفعات الاستيراد (LogisticsPayment) المرحّلة بغير قيمتها بالشيكل — ويصحّحها بطلب.

الدفعة دولار (`amount`) بسعرها (`usd_to_ils`)، وتكلفة البضاعة في الفاتورة الدولية
تحسبها amount × usd_to_ils. لكن قيد الدفعة كان يُدين المورد بـamount كأنه شيكل متى
قالت عملة الصفقة ILS (إنتاج D-0105: 5,500 بدل 17,820 ₪)، وفرعٌ آخر كان يحوّل مرتين.
الترحيل الجديد صار صحيحاً (`logistics.payment_posting`)؛ هذا الأمر للقديم.

المجموعات (لكل دفعة استيراد مرحّلة):
  (أ) صفقتها لها فاتورة دولية مرحّلة — الفاتورة دائنة بالشيكل والدفعة مدينة بالدولار
      كأنه شيكل ⇒ رصيد المورد خاطئ.
  (ب) صفقة أرشيف بقيد LOGISTICS_DEAL — القيد والدفعات بنفس الوحدة ⇒ تقرير فقط.
  (ج) صفقة بلا فاتورة ولا قيد صفقة — مدين المورد ودائن الصندوق كلاهما خطأ الآن،
      فتصحيحها لا ينتظر فاتورتها؛ وترحيل الفاتورة لاحقاً لا يحتاج شيئاً.
  (وكيل) دفعات وكيل الشحن — تحويل مزدوج أو دولار كشيكل (إنتاج #175: 13,928.63
      والصحيح 4,298.96).

    python manage.py audit_deal_payment_currency --tenant 1
    python manage.py audit_deal_payment_currency --tenant 1 --apply
    python manage.py audit_deal_payment_currency --tenant 1 --apply --groups a,c,agent

--apply: لكل دفعة بفرق في مجموعات --groups (الافتراضي a؛ ب ممنوعة): قيد عكسي
للأصل (reverse_journal، لا حذف) بتاريخه، ثم قيد جديد بـamount × usd_to_ils على نفس حسابَي الأصل وبتاريخه، وربط الدفعة
بالجديد، وسجلّ تدقيق — كلّ دفعة في transaction.atomic وحدها، فرفضُ واحدة (فترة مغلقة) لا يمسّ غيرها.
طبقات صندوق الدولار FIFO لا تُستهلك بأثر رجعي (الأصل لم يستهلكها).
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from accounting.services import CashBoxLedgerAccount, JournalHeader, JournalLine
from logistics.landed_cost import payment_ils
from logistics.models import LogisticsPayment, PurchaseInvoice

Q2 = Decimal('0.01')
APPLICABLE_GROUPS = ('a', 'c', 'agent')
GROUP_LABELS = {
    'a': '(أ) صفقة لها فاتورة دولية مرحّلة',
    'b': '(ب) صفقة أرشيف بقيد LOGISTICS_DEAL',
    'c': '(ج) صفقة بلا فاتورة ولا قيد صفقة',
    'agent': '(وكيل) دفعات وكيل الشحن',
}


def _base_sum(journal, field, **filters):
    return (JournalLine.objects.filter(journal=journal, **filters)
            .aggregate(s=Sum(field))['s'] or Decimal('0')).quantize(Q2)


class Command(BaseCommand):
    help = "كشف دفعات الاستيراد المرحّلة بالدولار كأنه شيكل، وتصحيح المجموعات المختارة بـ--apply."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="رقم المستأجر")
        parser.add_argument("--apply", action="store_true",
                            help="صحّح مجموعات --groups: عكس القيد وإعادة ترحيله بالشيكل.")
        parser.add_argument("--groups", default="a",
                            help="المجموعات التي يصحّحها --apply، مفصولة بفواصل من a,c,agent "
                                 "(الافتراضي a). b (الأرشيف) لا تُصحَّح.")

    def handle(self, *args, **options):
        tenant_id = options["tenant"]
        groups = [g.strip() for g in options["groups"].split(",") if g.strip()]
        if 'b' in groups:
            raise CommandError(
                "المجموعة b (صفقات الأرشيف بقيد LOGISTICS_DEAL) لا تُصحَّح: قيد الصفقة "
                "ودفعاتها بنفس الوحدة فرصيد المورد ≈ صفر — تقرير فقط.")
        unknown = [g for g in groups if g not in APPLICABLE_GROUPS]
        if unknown or not groups:
            raise CommandError(f"--groups: قيم غير معروفة {unknown or groups} — المسموح a,c,agent.")
        payments = (
            LogisticsPayment.objects
            .filter(is_posted=True, journal__isnull=False)
            .filter(deal__tenant_id=tenant_id) | LogisticsPayment.objects.filter(
                is_posted=True, journal__isnull=False, deal__isnull=True,
                shipment__tenant_id=tenant_id)
        ).select_related('deal', 'deal__partner', 'shipment', 'shipment__shipping_agent',
                         'journal', 'bank_account').order_by('id')

        invoiced_deals = set(PurchaseInvoice.objects.filter(
            tenant_id=tenant_id, invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            is_posted=True, deal__isnull=False,
        ).values_list('deal_id', flat=True))
        archived_deals = set(JournalHeader.objects.filter(
            tenant_id=tenant_id, reference_type='LOGISTICS_DEAL', is_posted=True,
        ).values_list('reference_id', flat=True))
        box_currency = dict(CashBoxLedgerAccount.objects.filter(tenant_id=tenant_id)
                            .values_list('account_id', 'currency_code'))

        rows = []
        for p in payments:
            if p.deal_id:
                group = ('a' if p.deal_id in invoiced_deals
                         else 'b' if p.deal_id in archived_deals else 'c')
                party = p.deal.partner
                label, kind = p.deal.ref_number, 'صفقة'
            else:
                group, party = 'agent', p.shipment.shipping_agent
                label, kind = p.shipment.shipment_number, 'شحنة'
            party_account = getattr(party, 'linked_account_id', None)
            party_debit = _base_sum(p.journal, 'base_debit', account_id=party_account)
            box_credit = _base_sum(p.journal, 'base_credit', account_id=p.bank_account_id)
            expected = payment_ils(p)
            rows.append({
                'p': p, 'group': group, 'label': label, 'kind': kind, 'party': party,
                'party_account': party_account, 'party_debit': party_debit,
                'box_credit': box_credit, 'expected': expected,
                'diff': (expected - party_debit).quantize(Q2),
                'box_diff': (expected - box_credit).quantize(Q2),
                'box_cur': box_currency.get(p.bank_account_id, '—'),
            })

        self._report(rows)
        if options["apply"]:
            self._apply([r for r in rows if r['group'] in groups and r['diff'] != 0], groups)
        else:
            self.stdout.write("\nقراءة فقط. --apply يصحّح --groups (الافتراضي a؛ المسموح a,c,agent).")

    def _report(self, rows):
        w = self.stdout.write
        for group, title in GROUP_LABELS.items():
            members = [r for r in rows if r['group'] == group]
            if not members:
                continue
            w(self.style.MIGRATE_HEADING(f"\n{title} — {len(members)} دفعة"))
            w("  دفعة | صفقة/شحنة | الطرف | amount$ | سعر | amount_local | مدين الطرف (أساس) "
              "| دائن الصندوق (أساس) | عملة الصندوق | الفرق = amount×rate − مدين")
            by_party = defaultdict(Decimal)
            by_box = defaultdict(Decimal)
            for r in members:
                p = r['p']
                w(f"  #{p.pk} | {r['label']} | {getattr(r['party'], 'name', '—')} | {p.amount} | "
                  f"{p.usd_to_ils} | {p.amount_local} | {r['party_debit']} | {r['box_credit']} | "
                  f"{r['box_cur']} | {r['diff']}")
                by_party[getattr(r['party'], 'name', '—')] += r['diff']
                box_name = getattr(p.bank_account, 'name', '—')
                by_box[f"{box_name} ({r['box_cur']})"] += r['box_diff']
            w("  أثر التصحيح على الأطراف (مدين إضافي = ينقص ما ندين به):")
            for name, amt in sorted(by_party.items()):
                if amt:
                    w(f"    {name}: {amt}")
            w("  أثر التصحيح على الصناديق/البنوك (دائن إضافي = ينقص رصيدها الدفتري):")
            for name, amt in sorted(by_box.items()):
                if amt:
                    w(f"    {name}: {amt}")
            ils_boxes = [r for r in members if r['box_diff'] and r['box_cur'] != 'USD']
            if ils_boxes:
                w(self.style.WARNING(
                    f"  تنبيه: {len(ils_boxes)} دفعة خرجت من صندوق/بنك غير دولاري بقيمة دولارية "
                    "مسجّلة كشيكل — رصيده الدفتري خاطئ أيضاً، لا رصيد المورد وحده."))

    def _apply(self, rows, groups):
        from accounting import api as accounting_api
        from accounting.services import create_audit_log, post_journal
        from logistics.payment_posting import build_usd_payment_journal

        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"\n--apply: {len(rows)} دفعة في المجموعات {','.join(groups)}"))
        done = failed = 0
        for r in rows:
            p = r['p']
            try:
                with transaction.atomic():
                    locked = LogisticsPayment.objects.select_for_update().get(pk=p.pk)
                    if not locked.is_posted or locked.journal_id != p.journal_id:
                        raise ValueError('تغيّرت الدفعة منذ القراءة — أعد التشغيل.')
                    if r['party'] is None or not r['party_account']:
                        raise ValueError('لا طرف مدين بحساب مربوط (وكيل الشحن محذوف أو بلا حساب).')
                    orig = p.journal
                    rev = accounting_api.reverse_journal(
                        orig,
                        reference_type='LOGISTICS_PAYMENT_UNPOST',
                        reference_id=p.pk,
                        transaction_date=orig.transaction_date,
                        description=(f"[تصحيح عملة دفعة] {r['kind']} {r['label']} — {p.title} — "
                                     f"عكس القيد #{orig.id} (قيمته بالشيكل خاطئة)")[:500],
                        line_description_prefix=f"عكس قيد #{orig.id}: ",
                        copy_currency=True,
                        copy_project=True,
                    )
                    desc = f"دفعة {p.title} | {r['kind']}: {r['label']}"
                    lines, currency, rate = build_usd_payment_journal(
                        p, debit_account_id=r['party_account'], partner_id=r['party'].pk,
                        box_account=p.bank_account, tenant=orig.tenant,
                        description=desc, use_fifo=False)
                    new = post_journal(
                        tenant_id=orig.tenant_id,
                        transaction_date=orig.transaction_date,
                        reference_type='LOGISTICS_PAYMENT',
                        reference_id=p.pk,
                        description=(f"{desc} | الطرف: {r['party'].name} "
                                     f"| تصحيح عملة للقيد #{orig.id}")[:500],
                        lines_data=lines,
                        currency=currency,
                        exchange_rate=rate,
                        idempotent=False,
                    )
                    LogisticsPayment.objects.filter(pk=p.pk).update(journal=new)
                    create_audit_log(
                        tenant=orig.tenant, user=None, action='UPDATE',
                        model_name='LogisticsPayment', object_id=p.pk,
                        change_details=(
                            f"تصحيح عملة دفعة {r['kind']} {r['label']}: القيد #{orig.id} رحّل "
                            f"{r['party_debit']} كشيكل لدفعة {p.amount}$ بسعر {p.usd_to_ils}؛ "
                            f"عُكس بالقيد #{rev.id} وأعيد بالقيد #{new.id} بقيمة {r['expected']} ₪"
                        )[:2000],
                    )
                done += 1
                w(self.style.SUCCESS(
                    f"  #{p.pk} {r['label']}: عكس #{rev.id}، جديد #{new.id} ({r['expected']} ₪)"))
            except Exception as exc:  # noqa: BLE001 — كل دفعة مستقلة، والسبب يُطبع للمالك
                failed += 1
                w(self.style.ERROR(f"  #{p.pk} {r['label']}: لم يتغيّر شيء — {exc}"))
        w(f"\nصُحّح: {done} · فشل: {failed}")
