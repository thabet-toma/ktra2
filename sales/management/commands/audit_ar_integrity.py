"""T-ARINT — كشف (وإصلاح) فساد ذمم العملاء الناتج عن إلغاء ترحيل ترك سنداته معلّقة.

كان إلغاء ترحيل فاتورة بيع يصفّر `amount_paid` ويحذف قيود الفاتورة وحدها، تاركاً
سندات القبض المرحّلة وصفوف توزيعها وقيودها (CUSTOMER_PAYMENT) حيّة ⇒ دائنٌ في
الذمم بلا مقابل، وتكرارُ سند التسوية النقدية عند كل إعادة ترحيل. الكود مُحصَّن
الآن؛ هذا الأمر لكشف الأثر المتراكم في البيانات وإصلاحه.

يفحص كل شركة ويطبع أربعة أقسام:
  1. فواتير مجموع توزيعاتها المرحّلة > إجماليها (ازدواج تحصيل).
  2. فواتير `amount_paid` لا يساوي مجموع توزيعاتها المرحّلة.
  3. فواتير عليها توزيعات مرحّلة وهي «مسودة» (يتيمة بعد إلغاء ترحيل).
  4. عملاء (partner_type='Customer' فقط) برصيد ذمم دائن — أرصدة الموردين
     الدائنة طبيعية فلا تُفحص إطلاقاً.
  ويُلحق بها: فواتير نقدية سُوّيت داخل قيدها (بلا مدين ذمم) ومع ذلك أُنشئ لها
  سند قبض ⇒ ازدواج نقدية.

الإصلاح (`--fix`) محافظ ولا يلمس إلا ما توقيعه مؤكَّد:
  - سند التسوية النقدية التلقائي الزائد/الخاطئ ⇒ يُلغى ترحيله ويُحذف (قيوده معه).
  - صفّ توزيع على فاتورة مسودة ⇒ يُحذف الصفّ وحده، فيبقى السند مرحّلاً «على
    الحساب» (تحصيلٌ حصل فعلاً) ويُوزَّع يدوياً لاحقاً.
  - `amount_paid` ⇒ يُعاد احتسابه من التوزيعات المرحّلة.
ما عدا ذلك (سندات مستخدم زائدة) يُبلَّغ عنه ويُترك للمراجعة اليدوية.

    python manage.py audit_ar_integrity                 # عرض فقط (dry-run افتراضي)
    python manage.py audit_ar_integrity --fix           # تطبيق الإصلاح
    python manage.py audit_ar_integrity --fix --tenant 6
"""
import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.services import partner_posted_balance
from partners.models import Partner
from sales.models import CustomerPayment, PaymentAllocation, SalesInvoice
from sales.services import (
    invoice_journal_debits_ar,
    is_auto_cash_settlement,
    posted_allocations_total,
    unpost_customer_payment,
)
from tenants.models import Tenant

logger = logging.getLogger(__name__)

DEC = Decimal("0.01")


class Command(BaseCommand):
    help = "فحص سلامة ذمم العملاء (ازدواج تحصيل/توزيعات يتيمة/أرصدة دائنة) وإصلاحها."

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='طبّق الإصلاح فعلياً.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='عرض فقط (السلوك الافتراضي — يُذكر للتصريح).')
        parser.add_argument('--tenant', type=int, default=None, help='حصر بشركة واحدة (TenantID).')

    def handle(self, *args, **opts):
        fix = opts['fix'] and not opts['dry_run']
        tenants = Tenant.objects.all().order_by("TenantID")
        if opts['tenant']:
            tenants = tenants.filter(TenantID=opts['tenant'])

        totals = {"over": 0, "mismatch": 0, "orphan": 0, "credit": 0, "cash": 0, "fixed": 0}
        for tenant in tenants:
            totals_before = dict(totals)
            self.stdout.write(f"\n=== شركة {tenant.TenantID}: {tenant.CompanyName} ===")
            self._audit_tenant(tenant, fix, totals)
            if totals == totals_before:
                self.stdout.write("  لا ملاحظات.")

        self.stdout.write(self.style.SUCCESS(
            f"\nالمجموع — ازدواج: {totals['over']}، تباين مدفوع: {totals['mismatch']}، "
            f"توزيعات يتيمة: {totals['orphan']}، نقدية مزدوجة: {totals['cash']}، "
            f"عملاء برصيد دائن: {totals['credit']}."
        ))
        if fix:
            self.stdout.write(self.style.SUCCESS(f"أُصلح: {totals['fixed']} بنداً."))
        elif any(totals[k] for k in ("over", "mismatch", "orphan", "cash")):
            self.stdout.write("أعد التشغيل بـ --fix لتطبيق الإصلاح.")

    # ── الفحص لكل شركة ──────────────────────────────────────────────────────
    def _audit_tenant(self, tenant, fix, totals):
        invoices = (
            SalesInvoice.objects.filter(
                tenant_id=tenant.TenantID,
                payment_allocations__payment__is_posted=True,
            )
            .select_related("customer", "journal")
            .distinct()
            .order_by("id")
        )
        for inv in invoices:
            allocated = posted_allocations_total(inv.pk)
            grand = Decimal(str(inv.grand_total or 0)).quantize(DEC)
            paid = Decimal(str(inv.amount_paid or 0)).quantize(DEC)

            if allocated > grand + DEC:
                totals["over"] += 1
                self.stdout.write(self.style.WARNING(
                    f"  [ازدواج] {inv.invoice_number}: توزيعات مرحّلة {allocated} "
                    f"> إجمالي {grand}"
                ))
                if fix:
                    totals["fixed"] += self._drop_surplus_auto_settlements(inv, grand)
                    allocated = posted_allocations_total(inv.pk)

            # فاتورة نقدية سوّت الصندوق داخل قيدها ومع ذلك عليها سند قبض
            if (
                inv.status == SalesInvoice.STATUS_POSTED
                and inv.invoice_type == SalesInvoice.INVOICE_CASH
                and allocated > 0
                and not invoice_journal_debits_ar(inv)
            ):
                totals["cash"] += 1
                self.stdout.write(self.style.WARNING(
                    f"  [نقدية مزدوجة] {inv.invoice_number}: قيدها بلا مدين ذمم "
                    f"وعليها تحصيل {allocated}"
                ))
                if fix:
                    totals["fixed"] += self._drop_surplus_auto_settlements(
                        inv, Decimal("0"))
                    allocated = posted_allocations_total(inv.pk)

            if inv.status != SalesInvoice.STATUS_POSTED and allocated > 0:
                totals["orphan"] += 1
                self.stdout.write(self.style.WARNING(
                    f"  [توزيع يتيم] {inv.invoice_number} (حالتها {inv.status}): "
                    f"توزيعات مرحّلة {allocated}"
                ))
                if fix:
                    totals["fixed"] += self._detach_allocations(inv)
                    allocated = posted_allocations_total(inv.pk)

            inv.refresh_from_db()
            paid = Decimal(str(inv.amount_paid or 0)).quantize(DEC)
            if inv.status == SalesInvoice.STATUS_POSTED and paid != allocated:
                totals["mismatch"] += 1
                self.stdout.write(self.style.WARNING(
                    f"  [تباين مدفوع] {inv.invoice_number}: amount_paid {paid} ≠ "
                    f"توزيعات {allocated}"
                ))
                if fix:
                    SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=allocated)
                    totals["fixed"] += 1
                    logger.info(
                        "audit_ar_integrity: invoice %s amount_paid %s → %s",
                        inv.invoice_number, paid, allocated,
                    )

        self._report_credit_customers(tenant, totals)

    # ── عملاء برصيد دائن (بلا الموردين) ─────────────────────────────────────
    def _report_credit_customers(self, tenant, totals):
        customers = Partner.objects.filter(
            tenant_id=tenant.TenantID, partner_type="Customer",
        ).order_by("id")
        for partner in customers:
            debit, credit = partner_posted_balance(tenant.TenantID, partner.id)
            net = (debit - credit).quantize(DEC)
            if net < -DEC:
                totals["credit"] += 1
                self.stdout.write(
                    f"  [رصيد دائن] {partner.name} (#{partner.id}): {net}"
                )

    # ── إصلاحات ─────────────────────────────────────────────────────────────
    def _drop_surplus_auto_settlements(self, inv, keep_up_to: Decimal) -> int:
        """يحذف سندات التسوية التلقائية الزائدة (الأحدث أولاً) حتى بلوغ السقف."""
        payments = list(
            CustomerPayment.objects.filter(
                tenant_id=inv.tenant_id, is_posted=True,
                allocations__invoice_id=inv.pk,
            ).distinct().prefetch_related("allocations").order_by("-id")
        )
        removed = 0
        for payment in payments:
            allocated = posted_allocations_total(inv.pk)
            if allocated <= keep_up_to + DEC:
                break
            if not is_auto_cash_settlement(payment, inv):
                self.stdout.write(
                    f"    ↳ سند #{payment.id} من إنشاء المستخدم — يحتاج مراجعة يدوية."
                )
                continue
            with transaction.atomic():
                unpost_customer_payment(payment)
                payment_id = payment.id
                payment.delete()
            removed += 1
            self.stdout.write(f"    ↳ حُذف سند التسوية التلقائي #{payment_id}.")
            logger.info(
                "audit_ar_integrity: removed auto settlement %s of invoice %s",
                payment_id, inv.invoice_number,
            )
        return removed

    def _detach_allocations(self, inv) -> int:
        """يفكّ ارتباط التوزيعات اليتيمة بفاتورة غير مرحّلة — السند يبقى «على الحساب»."""
        rows = list(
            PaymentAllocation.objects.filter(invoice=inv, payment__is_posted=True)
        )
        for row in rows:
            row.delete()
            logger.info(
                "audit_ar_integrity: detached allocation %s (payment %s) from "
                "draft invoice %s", row.pk, row.payment_id, inv.invoice_number,
            )
        if rows:
            SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("0"))
            self.stdout.write(
                f"    ↳ فُكّ {len(rows)} توزيعاً — السندات تبقى مرحّلة «على الحساب»."
            )
        return len(rows)
