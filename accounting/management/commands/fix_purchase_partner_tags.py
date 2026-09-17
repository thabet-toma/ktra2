"""إصلاح بيانات — قيود الشراء القديمة الموسومة بالمورد على غير حساب الذمم.

قبل fddfcce (فاتورة الشراء) وقبل A1-1 (الاستلام قبل الترحيل، مرجع الشراء، ونقطة
`purchase-receipts/` القديمة) كانت أسطر المخزون/الضريبة/الوسيط/المصروف تُوسَم
بالمورد. `partner_posted_balance` ومعه قارئا القوائم يجمعون **كل** أسطر الشريك
بلا فلتر حساب، فيُلغي مدينُ المخزون دائنَ الذمم ويظهر المورد برصيد ~صفر رغم
استحقاق المبلغ. الكود الحالي لا يَسِم إلا الحساب الرقابي؛ هذا الأمر يُصلح القديم.

الحساب الرقابي = ذمم مدينة/دائنة: `Account.sub_type` بـ`payable`/`receivable`، أو
حساب مربوط بطرف (`Partner.linked_account`)، أو حساب ذمم مجموعة طرف.

القاعدة (لكل قيد × شريك):
  - أنواع قيدٍ فيها سطر ذمم بطبيعتها (`PURCHASE_INVOICE`/`PURCHASE_RECEIPT`/
    `PURCHASE_RETURN`): يُزال الوسم عن غير الرقابي **فقط إن وُجد سطر رقابي موسوم
    بنفس الشريك** — وإلا لا يُعرف أين ساق الذمم فيُترك القيد ويُعرض للمراجعة.
  - أنواع قيدٍ لا ذمم فيها بطبيعتها (`PURCHASE_GRN`/`GOODS_RECEIPT`: مخزون ↔ وسيط):
    يُزال الوسم عن غير الرقابي مباشرةً.

لا يمسّ مبلغاً ولا حساباً ولا تاريخاً ولا حالة ترحيل — `partner` وحده. ومثل سابقته
`sales/.../fix_legacy_cash_partner_tags.py` يكتب بـ`QuerySet.update` لا عبر
`post_journal`: هو تصحيح وسمٍ على أسطر قائمة لا قيدٌ جديد، و`update` يتخطّى
`save()` فلا تُعاد الأرصدة الأساسية (لم تتغيّر). آمن للتكرار: يلمس الموسوم وحده.

    python manage.py fix_purchase_partner_tags                 # عرض فقط
    python manage.py fix_purchase_partner_tags --apply
    python manage.py fix_purchase_partner_tags --apply --tenant 1
"""
import logging
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.account_classification import SUB_TYPE_PAYABLE, SUB_TYPE_RECEIVABLE
from accounting.models import JournalLine
from partners.models import Partner, PartnerGroup

logger = logging.getLogger(__name__)

# أنواع قيود الشراء التي يكتبها الكود (logistics/services.py، logistics/views/invoices.py،
# accounting/views.py (`PurchaseReceiptViewSet`)).
TYPES_WITH_CONTROL_LINE = ("PURCHASE_INVOICE", "PURCHASE_RECEIPT", "PURCHASE_RETURN")
TYPES_WITHOUT_CONTROL_LINE = ("PURCHASE_GRN", "GOODS_RECEIPT")
PURCHASE_REFERENCE_TYPES = TYPES_WITH_CONTROL_LINE + TYPES_WITHOUT_CONTROL_LINE

_CHUNK = 500


def _control_account_ids(tenant_ids):
    ids = set(
        Partner.objects.filter(tenant_id__in=tenant_ids, linked_account__isnull=False)
        .values_list("linked_account_id", flat=True)
    )
    for ap_id, ar_id in PartnerGroup.objects.filter(tenant_id__in=tenant_ids).values_list(
        "account_payable_id", "account_receivable_id",
    ):
        ids.update(i for i in (ap_id, ar_id) if i)
    return ids


class Command(BaseCommand):
    help = "إزالة وسم المورد عن أسطر قيود الشراء غير الرقابية (مخزون/ضريبة/وسيط)."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='طبّق الإصلاح فعلياً.')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        lines = JournalLine.objects.filter(
            journal__reference_type__in=PURCHASE_REFERENCE_TYPES,
            partner__isnull=False,
        )
        if opts['tenant']:
            lines = lines.filter(tenant_id=opts['tenant'])
        rows = list(lines.values(
            'id', 'tenant_id', 'journal_id', 'partner_id', 'account_id',
            'account__sub_type', 'journal__reference_type',
        ))
        control_ids = _control_account_ids({r['tenant_id'] for r in rows})

        groups = defaultdict(list)
        for r in rows:
            groups[(r['journal_id'], r['partner_id'])].append(r)

        fix_ids = []
        # (tenant, reference_type) → [قيود تُصلَح، أسطر تُصلَح، قيود متروكة للمراجعة]
        stats = defaultdict(lambda: [set(), 0, set()])
        for (journal_id, _partner_id), group in groups.items():
            ref_type = group[0]['journal__reference_type']
            key = (group[0]['tenant_id'], ref_type)
            is_control = [
                r['account_id'] in control_ids
                or r['account__sub_type'] in (SUB_TYPE_PAYABLE, SUB_TYPE_RECEIVABLE)
                for r in group
            ]
            others = [r['id'] for r, ctl in zip(group, is_control) if not ctl]
            if not others:
                continue
            if ref_type in TYPES_WITH_CONTROL_LINE and not any(is_control):
                stats[key][2].add(journal_id)
                continue
            fix_ids.extend(others)
            stats[key][0].add(journal_id)
            stats[key][1] += len(others)

        for (tenant_id, ref_type), (journals, count, skipped) in sorted(stats.items()):
            line = f"شركة {tenant_id} — {ref_type}: {count} سطراً في {len(journals)} قيداً"
            if skipped:
                line += (
                    f" · متروك للمراجعة (لا سطر ذمم معروف): {len(skipped)} قيداً "
                    f"{sorted(skipped)[:20]}"
                )
            self.stdout.write(line)

        if not fix_ids:
            self.stdout.write(self.style.SUCCESS("لا أسطر شراء بحاجة إصلاح."))
            return

        if not opts['apply']:
            self.stdout.write(self.style.WARNING(f"\nسيُصلَح: {len(fix_ids)} سطراً."))
            self.stdout.write("أعد التشغيل بـ --apply للتطبيق.")
            return

        count = 0
        with transaction.atomic():
            for i in range(0, len(fix_ids), _CHUNK):
                count += JournalLine.objects.filter(
                    pk__in=fix_ids[i:i + _CHUNK], partner__isnull=False,
                ).update(partner=None)
        logger.info("fix_purchase_partner_tags: unset partner on %s lines.", count)
        self.stdout.write(self.style.SUCCESS(f"\nأُصلح: {count} سطراً."))
