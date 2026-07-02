"""إصلاح بيانات — أسطر «تحصيل نقدي» القديمة الموسومة بالعميل بالخطأ.

فواتير البيع النقدية التي رُحِّلت بالكود القديم (قبل Feature 2 / T-CASH2) كانت
تُقيَّد: «مدين الصندوق (موسوم بالعميل!) / دائن الإيراد» — بلا سطر ذمم. وسمُ سطر
الصندوق بالعميل جعل كشف الحساب (`partner_account_statement` يجمع كل أسطر الشريك
بلا فلترة حساب) يَحسب مدين الصندوق على العميل، فبقي «تحصيل نقدي — <رقم>» مديناً
بلا دائن مقابل ⇒ رصيد شبح لا يُصفَّر (بلاغ المالك: العميل لسا عليه 250).

الكود الحالي لا يُنتج هذا الوصف على أي سطر قيد إطلاقاً، فالمطابقة بالتوقيع
(`reference_type='SALES_INVOICE'` + وصف يبدأ بـ «تحصيل نقدي —» + شريك غير فارغ)
تلمس البيانات القديمة فقط. الإصلاح:
  1. إزالة وسم الشريك عن سطر الصندوق (partner → None) — الصندوق ليس الحساب
     الرقابي للذمم فلا يجوز أن يَحمل شريكاً.
  2. ضبط `amount_paid = grand_total` للفاتورة (نقداً مقبوضة بالكامل) فتظهر مدفوعة
     ويتخطّاها `backfill_cash_settlements` (فلا يُنشئ سند قبض يُضاعف النقدية).

آمن للتكرار: يعتمد على وجود الوسم فعلاً، فإعادة التشغيل بلا أثر.

    python manage.py fix_legacy_cash_partner_tags            # عرض فقط (dry-run)
    python manage.py fix_legacy_cash_partner_tags --apply     # تطبيق الإصلاح
    python manage.py fix_legacy_cash_partner_tags --apply --tenant 1
"""
import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models import JournalLine
from sales.models import SalesInvoice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "إزالة وسم العميل عن أسطر «تحصيل نقدي» القديمة وضبط تسديد فواتيرها."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='طبّق الإصلاح فعلياً.')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        apply = opts['apply']
        lines = JournalLine.objects.filter(
            journal__is_posted=True,
            journal__reference_type="SALES_INVOICE",
            description__startswith="تحصيل نقدي",
            partner__isnull=False,
        ).select_related("journal", "partner")
        if opts['tenant']:
            lines = lines.filter(tenant_id=opts['tenant'])

        affected_lines = list(lines)
        invoice_ids = {jl.journal.reference_id for jl in affected_lines}

        for jl in affected_lines:
            self.stdout.write(
                f"قيد {jl.journal_id} — {jl.description} — "
                f"عميل {getattr(jl.partner, 'name', '') or jl.partner_id}: "
                f"مدين {jl.base_debit}"
            )

        if not affected_lines:
            self.stdout.write(self.style.SUCCESS("لا أسطر قديمة بحاجة إصلاح."))
            return

        if apply:
            with transaction.atomic():
                # bulk update يتخطّى save() فلا يُعيد حساب base (غير متغيّر).
                count = lines.update(partner=None)
                invs = SalesInvoice.objects.filter(pk__in=invoice_ids)
                if opts['tenant']:
                    invs = invs.filter(tenant_id=opts['tenant'])
                paid = 0
                for inv in invs:
                    grand = Decimal(str(inv.grand_total or 0))
                    if Decimal(str(inv.amount_paid or 0)) < grand:
                        inv.amount_paid = grand
                        inv.save(update_fields=["amount_paid"])
                        paid += 1
            logger.info(
                "fix_legacy_cash_partner_tags: unset partner on %s lines, "
                "settled %s invoices.", count, paid,
            )
            self.stdout.write(self.style.SUCCESS(
                f"\nأُصلح: {count} سطراً، وسُدِّدت {paid} فاتورة."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"\nسيُصلَح: {len(affected_lines)} سطراً في {len(invoice_ids)} فاتورة."
            ))
            self.stdout.write("أعد التشغيل بـ --apply للتطبيق.")
