"""أمر إصلاح ترويسة فواتير الشراء المرحّلة الصفرية وربط سنداتها التلقائية (PRET-ZERO-HEADERS).

الأمر معاينةٌ افتراضياً (DRY-RUN): بلا `--apply` لا يُكتب شيء في قاعدة البيانات.

الاستعمال:
    python manage.py repair_zero_purchase_headers                    # معاينة لكل الشركات
    python manage.py repair_zero_purchase_headers --tenant 3         # معاينة شركة بعينها
    python manage.py repair_zero_purchase_headers --tenant 3 --apply # تنفيذ فعلي
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounting.models import Account, JournalLine
from logistics.models import PurchaseInvoice
from logistics.purchase_return_basis import (
    basis_matches_journal,
    compute_invoice_line_basis,
)
from partners.models import PartnerGroup
from sales.models import SupplierPayment
from tenants.models import Tenant

logger = logging.getLogger(__name__)

DEC = Decimal("0.01")
ZERO = Decimal("0.00")
ONE = Decimal("1")
AUTO_PAYMENT_NOTE_PREFIX = "دفع تلقائي — فاتورة شراء "
PREVIEW_NOTICE = "معاينة فقط (DRY-RUN) — مرّر --apply للكتابة. لم يُكتب شيء في قاعدة البيانات."


def _q2(val) -> Decimal:
    return Decimal(str(val or 0)).quantize(DEC)


def _resolve_ap_account_readonly(partner) -> int | None:
    """يحلّ حساب ذمم المورد قراءةً فقط (بنفس أولوية `receive_purchase_invoice` دون كتابة)."""
    if partner is None:
        return None
    if partner.linked_account_id:
        return partner.linked_account_id
    if partner.group_id:
        grp = PartnerGroup.objects.filter(pk=partner.group_id).values("account_payable_id").first()
        if grp and grp["account_payable_id"]:
            return grp["account_payable_id"]
    ap_id = (
        Account.objects.filter(tenant_id=partner.tenant_id, code="2101")
        .values_list("id", flat=True)
        .first()
    )
    if ap_id:
        return ap_id
    return (
        Account.objects.filter(
            tenant_id=partner.tenant_id, account_type="Liability", is_active=True,
        )
        .values_list("id", flat=True)
        .first()
    )


def _journal_matches_for_zero_header(invoice: PurchaseInvoice, s_total: Decimal) -> bool:
    """يتحقّق من مطابقة القيد للبنود عبر `purchase_return_basis` ودائن حساب المورد."""
    if not invoice.journal_id or not invoice.journal or not invoice.journal.is_posted:
        return False

    orig_sub = invoice.subtotal
    orig_grand = invoice.grand_total
    orig_tax = invoice.tax_amount
    try:
        invoice.subtotal = s_total
        invoice.grand_total = s_total
        invoice.tax_amount = ZERO
        basis = compute_invoice_line_basis(invoice)
        matched, _reason = basis_matches_journal(invoice, basis)
    finally:
        invoice.subtotal = orig_sub
        invoice.grand_total = orig_grand
        invoice.tax_amount = orig_tax

    if not matched:
        return False

    ap_acc_id = _resolve_ap_account_readonly(invoice.partner)
    if ap_acc_id is None:
        return False

    lines = list(
        JournalLine.objects.filter(
            tenant_id=invoice.tenant_id, journal_id=invoice.journal_id,
        ).values("account_id", "partner_id", "debit", "credit", "base_debit", "base_credit")
    )
    total_base_debit = sum((_q2(ln["base_debit"]) for ln in lines), ZERO)
    total_base_credit = sum((_q2(ln["base_credit"]) for ln in lines), ZERO)
    if total_base_debit != s_total or total_base_credit != s_total:
        return False

    ap_credit = sum(
        (
            _q2(ln["credit"])
            for ln in lines
            if ln["account_id"] == ap_acc_id
            and ln["partner_id"] == invoice.partner_id
            and _q2(ln["credit"]) > ZERO
        ),
        ZERO,
    )
    ap_base_credit = sum(
        (
            _q2(ln["base_credit"])
            for ln in lines
            if ln["account_id"] == ap_acc_id
            and ln["partner_id"] == invoice.partner_id
            and _q2(ln["credit"]) > ZERO
        ),
        ZERO,
    )
    return ap_credit == s_total and ap_base_credit == s_total


def _evaluate_invoice(
    invoice: PurchaseInvoice,
    *,
    lock_payments: bool = False,
) -> tuple[str | None, Decimal, SupplierPayment | None]:
    """يفحص أهلية الفاتورة وسندها التلقائي؛ يعيد `(سبب_التخطّي_أو_None, S, السند_المطابق)`."""
    items = list(invoice.items.order_by("id"))
    s_total = sum((_q2(it.total_price) for it in items), ZERO)

    if invoice.invoice_type != PurchaseInvoice.INVOICE_TYPE_LOCAL:
        return "فاتورة دولية", s_total, None
    if invoice.is_return:
        return "مرتجع (is_return)", s_total, None
    if not invoice.is_posted:
        return "غير مرحّلة", s_total, None
    if not items:
        return "بلا بنود", s_total, None
    if _q2(invoice.subtotal) != ZERO:
        return "ترويسة غير صفرية (subtotal)", s_total, None
    if _q2(invoice.grand_total) != ZERO:
        return "ترويسة غير صفرية (grand_total)", s_total, None
    if _q2(invoice.tax_amount) != ZERO or Decimal(str(invoice.tax_rate or 0)) != Decimal("0"):
        return "ضريبة في الترويسة (tax_rate/tax_amount)", s_total, None
    if _q2(invoice.discount_amount) != ZERO:
        return "خصم على الترويسة (discount_amount)", s_total, None
    if _q2(invoice.shipping_cost) != ZERO:
        return "تكلفة شحن (shipping_cost)", s_total, None
    if Decimal(str(invoice.exchange_rate or 0)) != ONE:
        return "سعر صرف غير 1 (exchange_rate)", s_total, None
    if invoice.fees.exists():
        return "توجد رسوم على الفاتورة", s_total, None
    if any(it.is_taxable for it in items):
        return "بند خاضع للضريبة (is_taxable)", s_total, None
    if any(
        (it.discount_amount is not None and _q2(it.discount_amount) != ZERO)
        or (it.discount_percent is not None and _q2(it.discount_percent) != ZERO)
        for it in items
    ):
        return "بند بخصم (discount_amount/discount_percent)", s_total, None
    if s_total <= ZERO:
        return "مجموع البنود غير موجب", s_total, None
    if not _journal_matches_for_zero_header(invoice, s_total):
        return "قيد لا يطابق البنود", s_total, None

    expected_note = f"{AUTO_PAYMENT_NOTE_PREFIX}{invoice.invoice_number}"
    if lock_payments:
        pay_ids = list(
            SupplierPayment.objects.filter(
                tenant_id=invoice.tenant_id, notes=expected_note,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        if not pay_ids:
            payments = []
        else:
            locked_rows = list(
                SupplierPayment.objects.filter(pk__in=pay_ids)
                .select_for_update(of=("self",))
                .order_by("id")
            )
            payments = [
                p for p in locked_rows
                if p.tenant_id == invoice.tenant_id and p.notes == expected_note
            ]
    else:
        payments = list(
            SupplierPayment.objects.filter(
                tenant_id=invoice.tenant_id, notes=expected_note,
            ).order_by("id")
        )

    if not payments:
        return None, s_total, None
    if len(payments) > 1:
        return "سند تلقائي مكرّر", s_total, None

    sp = payments[0]
    if sp.partner_id != invoice.partner_id:
        return "سند تلقائي لمورد مختلف", s_total, None
    if _q2(sp.amount) != s_total:
        return "سند تلقائي بمبلغ مختلف", s_total, None
    if not sp.is_posted:
        return "سند تلقائي غير مرحّل", s_total, None
    if sp.purchase_invoice_id is not None or sp.auto_settled_invoice_id is not None:
        return "سند تلقائي مربوط مسبقاً", s_total, None
    if sp.allocations.exists() or sp.logistics_allocations.exists():
        return "سند تلقائي موزَّع", s_total, None

    return None, s_total, sp


class Command(BaseCommand):
    help = (
        "إصلاح ترويسة فواتير الشراء المرحّلة الصفرية من بنودها وربط سنداتها التلقائية "
        "(PRET-ZERO-HEADERS). معاينةٌ افتراضياً (DRY-RUN)؛ --apply للكتابة."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="الكتابة الفعلية في قاعدة البيانات. بدونه الأمر معاينةٌ لا تكتب شيئاً.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="معاينة كاملة دون كتابة أي صف (مرادفٌ للسلوك الافتراضي؛ لا يُجمع مع --apply).",
        )
        parser.add_argument(
            "--tenant",
            type=int,
            help="معرّف الشركة (افتراضياً كل الشركات).",
        )

    def handle(self, *args, **options):
        if options.get("apply") and options.get("dry_run"):
            raise CommandError("--apply و--dry-run متعارضان: اختر أحدهما.")
        dry_run = not options.get("apply")
        mode_label = "DRY-RUN" if dry_run else "APPLIED"

        tenants = Tenant.objects.all().order_by("TenantID")
        if options.get("tenant") is not None:
            tenants = tenants.filter(TenantID=options["tenant"])
            if not tenants.exists():
                raise CommandError(f"الشركة غير موجودة (tenant={options['tenant']}).")

        skip_counts: dict[str, int] = defaultdict(int)
        skip_sums: dict[str, Decimal] = defaultdict(lambda: ZERO)

        elig_with_pay_count = 0
        elig_with_pay_sum = ZERO
        elig_no_pay_count = 0
        elig_no_pay_sum = ZERO

        self.stdout.write(f"=== repair_zero_purchase_headers [{mode_label}] ===")

        for tenant in tenants:
            candidates = (
                PurchaseInvoice.objects.filter(tenant=tenant, grand_total=ZERO)
                .select_related("partner", "partner__group", "journal")
                .order_by("id")
            )
            for inv in candidates:
                reason, s_total, sp = _evaluate_invoice(inv, lock_payments=False)
                if reason is not None:
                    skip_counts[reason] += 1
                    skip_sums[reason] += s_total
                    continue

                if not dry_run:
                    with transaction.atomic():
                        locked_inv = (
                            PurchaseInvoice.objects.select_for_update(of=("self",))
                            .select_related("partner", "partner__group", "journal")
                            .get(pk=inv.pk)
                        )
                        reason, s_total, locked_sp = _evaluate_invoice(
                            locked_inv, lock_payments=True,
                        )
                        if reason is not None:
                            skip_counts[reason] += 1
                            skip_sums[reason] += s_total
                            continue

                        PurchaseInvoice.objects.filter(pk=locked_inv.pk).update(
                            subtotal=s_total,
                            grand_total=s_total,
                            tax_amount=ZERO,
                        )
                        if locked_sp is not None:
                            SupplierPayment.objects.filter(pk=locked_sp.pk).update(
                                purchase_invoice_id=locked_inv.pk,
                            )
                        logger.info(
                            "repaired zero purchase invoice header invoice_id=%s "
                            "payment_id=%s total=%s",
                            locked_inv.pk,
                            locked_sp.pk if locked_sp is not None else None,
                            s_total,
                        )
                        sp = locked_sp

                if sp is not None:
                    elig_with_pay_count += 1
                    elig_with_pay_sum += s_total
                else:
                    elig_no_pay_count += 1
                    elig_no_pay_sum += s_total

        total_elig_count = elig_with_pay_count + elig_no_pay_count
        total_elig_sum = elig_with_pay_sum + elig_no_pay_sum

        self.stdout.write(
            f"مؤهّلة (مع سند / بلا سند): الإجمالي={total_elig_count} "
            f"({elig_with_pay_count} مع سند / {elig_no_pay_count} بلا سند) · "
            f"مجموع_S={total_elig_sum.quantize(DEC)} "
            f"({elig_with_pay_sum.quantize(DEC)} / {elig_no_pay_sum.quantize(DEC)})"
        )
        for reason in sorted(skip_counts):
            self.stdout.write(
                f"تخطّي [{reason}]: عدد={skip_counts[reason]} · "
                f"مجموع_S={skip_sums[reason].quantize(DEC)}"
            )
        if dry_run:
            self.stdout.write(PREVIEW_NOTICE)
