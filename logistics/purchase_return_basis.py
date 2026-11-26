"""أساس العكس المحاسبي لكل بند فاتورة شراء، وتصنيف/تنفيذ الإسناد الخلفي لمرتجعات الشراء القديمة.

تحتوي هذه الوحدة على:
1. `compute_invoice_line_basis` و`basis_matches_journal` (§10.1.2).
2. `classify_return_product_group`: دالّة التصنيف المشتركة بين `audit_purchase_returns` (S6)
   و`backfill_purchase_returns`.
3. منطق الإسناد الخلفي القابل للتراجع (`run_backfill_for_tenant`, `rollback_backfill_for_tenant`).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from django.db import transaction
from django.db.models import Prefetch

from accounting.services import Account, JournalLine
from logistics.domain.allocation import reconcile
from logistics.models import (
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseReturnBackfill,
)
from logistics.payment_posting import invoice_journal_commission_ils, import_invoice_booked_commission
from logistics.services import (
    GR_IR_ACCOUNT_CODE,
    QTY,
    goods_clearing_unit_costs,
    import_invoice_capitalized_tax,
    import_invoice_capitalizes_all,
    purchase_fee_capitalized,
    resolve_purchase_vat_input_account,
)

logger = logging.getLogger(__name__)

DEC = Decimal("0.01")
ZERO = Decimal("0.00")
ZERO_Q = Decimal("0.0000")


@dataclass(frozen=True)
class LineBasis:
    """أساس بند واحد من فاتورة الشراء بالعملة الأساسية."""

    account_id: int | None
    net_base: Decimal
    tax_base: Decimal
    clearing_base: Decimal


def _q2(val) -> Decimal:
    return Decimal(str(val or 0)).quantize(DEC)


def _qq(val) -> Decimal:
    return Decimal(str(val or 0)).quantize(QTY)


def _resolve_goods_account_readonly(invoice: PurchaseInvoice, items: list[PurchaseInvoiceItem]) -> int | None:
    """يحدّد حساب البضاعة (2110 أو حساب المخزون) قراءةً فقط دون إنشاء أيّ حساب."""
    tenant_id = invoice.tenant_id
    gr_ir_acc = Account.objects.filter(tenant_id=tenant_id, code=GR_IR_ACCOUNT_CODE).first()

    # حساب المخزون بنفس أولوية `post_to_accounting` (`logistics/views/invoices.py`)
    inventory_account = None
    if items:
        from inventory.services import _resolve_line_account

        line_accounts: dict[int, Decimal] = {}
        for it in items:
            if it.product_id:
                try:
                    acc = _resolve_line_account(it.product, 'purchase', tenant_id=tenant_id)
                except Exception:
                    continue
                line_accounts.setdefault(acc.id, Decimal('0'))
                line_total = Decimal(str(it.total_price or it.quantity * it.unit_price or 0))
                line_accounts[acc.id] += line_total
        if line_accounts:
            inventory_account = Account.objects.filter(
                tenant_id=tenant_id, pk=max(line_accounts, key=line_accounts.get),
            ).first()

    if not inventory_account:
        inventory_account = (
            Account.objects.filter(tenant_id=tenant_id, code="1104").first()
            or Account.objects.filter(
                tenant_id=tenant_id, account_type="Asset", name__icontains="مخزون",
            ).first()
            or Account.objects.filter(
                tenant_id=tenant_id, account_type="Expense", name__icontains="مشتريات",
            ).first()
        )

    if invoice.is_posted and invoice.journal_id:
        debit_accs = set(
            JournalLine.objects.filter(
                tenant_id=tenant_id, journal_id=invoice.journal_id, debit__gt=0,
            ).values_list('account_id', flat=True)
        )
        if gr_ir_acc and gr_ir_acc.id in debit_accs:
            return gr_ir_acc.id
        if inventory_account and inventory_account.id in debit_accs:
            return inventory_account.id

    is_local = not (invoice.deal_id or invoice.shipment_id or invoice.clearance_id)
    use_gr_ir = bool(gr_ir_acc and (is_local or invoice.receipt_status == PurchaseInvoice.RECEIPT_NOT))
    if use_gr_ir:
        return gr_ir_acc.id
    return inventory_account.id if inventory_account else None


def compute_invoice_line_basis(invoice: PurchaseInvoice) -> dict[int, LineBasis]:
    """يحسب أساس العكس لكل بند من بنود فاتورة الشراء بالعملة الأساسية (`{}` حين لا أساس)."""
    return _compute_invoice_line_basis_with_reason(invoice)[0]


def _compute_invoice_line_basis_with_reason(
    invoice: PurchaseInvoice,
) -> tuple[dict[int, LineBasis], str | None]:
    """يحسب أساس العكس لكل بند، ومعه سبب الأساس الفارغ (`None` حين يُحسب الأساس).

    تنبيه: هذه الدالّة مرآة حرفية لتوزيع الترحيل في `logistics/views/invoices.py` (`post_to_accounting`).
    أي تغيير في منطق توزيع الترحيل المحاسبي للفاتورة يجب أن يمرّ عليها (ستعتمدها M3 في الترحيل).
    """
    items = list(invoice.items.select_related('product__category').order_by('id'))
    if not items:
        return {}, "الفاتورة بلا بنود"

    if invoice.journal_id and invoice.journal is not None:
        rate = Decimal(str(invoice.journal.exchange_rate or invoice.exchange_rate or 1))
    else:
        rate = Decimal(str(invoice.exchange_rate or 1))
    if rate <= 0:
        rate = Decimal('1')

    grand = Decimal(str(invoice.grand_total or 0))
    tax_amt = Decimal(str(invoice.tax_amount or 0))
    merchandise_net = grand - tax_amt

    fees_qs = list(invoice.fees.all())
    capitalized_total = sum(
        (Decimal(str(f.amount or 0)) for f in fees_qs if purchase_fee_capitalized(invoice, f)),
        Decimal('0'),
    )

    if invoice.is_posted and invoice.journal_id:
        commission = invoice_journal_commission_ils(invoice)
    else:
        commission, _ = import_invoice_booked_commission(invoice)

    capitalize_all = import_invoice_capitalizes_all(invoice)
    if capitalize_all:
        if invoice.is_posted and invoice.journal_id:
            capitalized_tax = import_invoice_capitalized_tax(invoice)
            vat_debit_nominal = max(tax_amt - capitalized_tax, Decimal('0')).quantize(DEC)
        else:
            capitalized_tax = tax_amt
            vat_debit_nominal = Decimal('0')
    else:
        capitalized_tax = Decimal('0')
        vat_debit_nominal = tax_amt

    inventory_debit = merchandise_net + capitalized_total + commission + capitalized_tax

    use_landed = False
    if any(it.landed_line_total_ils for it in items if it.landed_line_total_ils is not None):
        landed_sum = sum(
            (Decimal(str(it.landed_line_total_ils or 0)) for it in items),
            Decimal('0'),
        )
        if landed_sum > 0:
            use_landed = True

    subtotal = sum(
        (Decimal(str(it.total_price or it.quantity * it.unit_price or 0)) for it in items),
        Decimal('0'),
    )
    discount = Decimal(str(invoice.discount_amount or 0))

    raw_shares: dict[int, Decimal] = {}
    for it in items:
        if use_landed and it.landed_line_total_ils is not None:
            raw_share = Decimal(str(it.landed_line_total_ils))
        else:
            raw_amt = Decimal(str(it.total_price or it.quantity * it.unit_price or 0))
            if subtotal > 0 and discount > 0:
                raw_share = raw_amt - (raw_amt / subtotal * discount)
            else:
                raw_share = raw_amt
        raw_shares[it.id] = raw_share

    mapped_debit = Decimal('0')
    mapped_acc_totals: dict[int, Decimal] = {}
    mapped_acc_items: dict[int, list[PurchaseInvoiceItem]] = {}
    for it in items:
        if not it.expense_account_id:
            continue
        amt = raw_shares[it.id]
        if amt <= 0:
            continue
        mapped_debit += amt
        mapped_acc_totals[it.expense_account_id] = (
            mapped_acc_totals.get(it.expense_account_id, Decimal('0')) + amt
        )
        mapped_acc_items.setdefault(it.expense_account_id, []).append(it)

    inventory_debit -= mapped_debit
    # مرآة رفض الترحيل (`inventory_debit < -0.02` في `post_to_accounting`): لا أساس لفاتورة لا تُرحَّل
    if inventory_debit < Decimal('-0.02'):
        return {}, "الترحيل كان سيرفض الفاتورة: مدين مخزون سالب"
    if Decimal('-0.02') <= inventory_debit < Decimal('0') and mapped_acc_totals:
        biggest = max(mapped_acc_totals, key=lambda k: mapped_acc_totals[k])
        mapped_acc_totals[biggest] += inventory_debit
        inventory_debit = Decimal('0')

    goods_clearing_amt = inventory_debit if inventory_debit > 0 else Decimal('0')

    # توزيع الصافي بالعملة الأساسية لكل بند
    net_bases: dict[int, Decimal] = {it.id: ZERO for it in items}
    clearing_bases: dict[int, Decimal] = {it.id: ZERO for it in items}
    account_ids: dict[int, int | None] = {}

    for acc_id, acc_items in mapped_acc_items.items():
        acc_target_base = _q2(_q2(mapped_acc_totals[acc_id]) * rate)
        shares = reconcile(acc_target_base, [raw_shares[it.id] for it in acc_items])
        for it, sh in zip(acc_items, shares):
            net_bases[it.id] = sh

    for it in items:
        if it.expense_account_id:
            account_ids[it.id] = it.expense_account_id

    goods_items = [it for it in items if not it.expense_account_id]
    if goods_items:
        # الجهة الآمنة: أي بند بضاعة بلا منتج يُسجَّل استثناءً وتُترك حقول الأساس فارغة
        if any(not it.product_id for it in goods_items):
            return {}, "بند بضاعة بلا منتج"
        goods_acc_id = _resolve_goods_account_readonly(invoice, items)
        for it in goods_items:
            account_ids[it.id] = goods_acc_id

        goods_net_nominal = max(merchandise_net - mapped_debit, Decimal('0'))
        goods_net_base_target = _q2(_q2(goods_net_nominal) * rate)
        goods_weights = [max(raw_shares[it.id], Decimal('0')) for it in goods_items]
        for it, sh in zip(goods_items, reconcile(goods_net_base_target, goods_weights)):
            net_bases[it.id] = sh

        goods_clearing_base_target = _q2(_q2(goods_clearing_amt) * rate)
        pos_goods_items = [it for it in goods_items if Decimal(str(it.quantity or 0)) > 0]
        if pos_goods_items:
            clearing_map = goods_clearing_unit_costs(invoice, goods_clearing_base_target)
            if not (
                clearing_map
                and len(clearing_map) == len(pos_goods_items)
                and all(it.id in clearing_map for it in pos_goods_items)
            ):
                return {}, "خريطة التصفية لا تغطي كل البنود"
            for it in pos_goods_items:
                clearing_bases[it.id] = _q2(clearing_map[it.id][1])
        elif goods_clearing_base_target > ZERO:
            return {}, "رصيد وسيط موجب بلا خريطة تصفية"

    # توزيع الضريبة بأكبر باقٍ على البنود الخاضعة نسبةً لـ(الصافي × نسبة الضريبة) مع الرجوع للصافي عند التصفير
    tax_bases: dict[int, Decimal] = {it.id: ZERO for it in items}
    vat_base_target = _q2(_q2(vat_debit_nominal) * rate)
    if vat_base_target > 0:
        taxable_items = [it for it in items if it.is_taxable]
        if taxable_items:
            tax_weights = [
                max(net_bases[it.id], Decimal('0')) * max(Decimal(str(it.vat_percent or 0)), Decimal('0'))
                for it in taxable_items
            ]
            if sum(tax_weights, Decimal('0')) <= 0:
                tax_weights = [max(net_bases[it.id], Decimal('0')) for it in taxable_items]
            for it, t_sh in zip(taxable_items, reconcile(vat_base_target, tax_weights)):
                tax_bases[it.id] = t_sh

    return {
        it.id: LineBasis(
            account_id=account_ids.get(it.id),
            net_base=net_bases[it.id],
            tax_base=tax_bases[it.id],
            clearing_base=clearing_bases[it.id],
        )
        for it in items
    }, None


def basis_matches_journal(
    invoice: PurchaseInvoice,
    basis: dict[int, LineBasis],
) -> tuple[bool, str]:
    """يقارن مجموع أساس البنود بأسطر قيد الفاتورة لكل حساب بدقّة القرش."""
    if not invoice.is_posted or not invoice.journal_id:
        return False, "الفاتورة غير مرحّلة أو بلا قيد محاسبي."

    items = list(invoice.items.order_by('id'))
    if not items:
        return False, "الفاتورة بلا بنود."

    goods_items = [it for it in items if not it.expense_account_id]
    if any(not it.product_id for it in goods_items):
        return False, "بند بضاعة بلا منتج"
    if not basis:
        _, why = _compute_invoice_line_basis_with_reason(invoice)
        return False, why or "أساس البنود المُمرَّر فارغ"

    journal_debits: dict[int, Decimal] = {}
    for line in JournalLine.objects.filter(
        tenant_id=invoice.tenant_id, journal_id=invoice.journal_id,
    ).values("account_id", "base_debit"):
        bd = _q2(line["base_debit"])
        if bd != ZERO:
            aid = line["account_id"]
            journal_debits[aid] = _q2(journal_debits.get(aid, ZERO) + bd)

    expected_by_acc: dict[int, Decimal] = {}
    total_tax = ZERO
    missing_basis = []
    for it in items:
        lb = basis.get(it.id)
        if lb is None:
            missing_basis.append(it.id)
            continue
        total_tax = _q2(total_tax + lb.tax_base)
        if it.expense_account_id:
            aid = lb.account_id
            expected_by_acc[aid] = _q2(expected_by_acc.get(aid, ZERO) + lb.net_base)
        else:
            if lb.account_id:
                expected_by_acc[lb.account_id] = _q2(
                    expected_by_acc.get(lb.account_id, ZERO) + lb.clearing_base
                )
            elif lb.clearing_base > ZERO:
                return False, "تعذّر تحديد حساب المخزون/الوسيط لبند البضاعة."

    if missing_basis:
        return False, f"بنود بلا أساس محسوب: {missing_basis}"

    diffs: list[str] = []
    for acc_id, expected_amt in expected_by_acc.items():
        actual_amt = journal_debits.get(acc_id, ZERO)
        if actual_amt != expected_amt:
            diffs.append(f"حساب #{acc_id}: الأساس={expected_amt} القيد={actual_amt}")

    vat_acc = resolve_purchase_vat_input_account(invoice.tenant)
    if total_tax > ZERO:
        if vat_acc is None:
            diffs.append(f"ضريبة مدخلات={total_tax} بلا حساب ضريبة في الشجرة")
        else:
            actual_vat = journal_debits.get(vat_acc.id, ZERO)
            if actual_vat != total_tax:
                diffs.append(f"ضريبة مدخلات: الأساس={total_tax} القيد={actual_vat}")
    elif vat_acc is not None and not import_invoice_capitalizes_all(invoice):
        actual_vat = journal_debits.get(vat_acc.id, ZERO)
        if actual_vat != ZERO:
            diffs.append(f"ضريبة مدخلات: الأساس=0.00 القيد={actual_vat}")

    if diffs:
        return False, "؛ ".join(diffs)
    return True, ""


# ── التصنيف المشترك S6 ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReturnProductClassification:
    """نتيجة تصنيف زوج (فاتورة أصلية، منتج) للإسناد الخلفي ولتدقيق M0."""

    absent: bool
    exc_multi_price: bool
    exc_same_price_multi_line: bool
    exc_exceeds_received: bool
    ret_qty: Decimal
    recv_qty: Decimal

    @property
    def is_s6_deterministic(self) -> bool:
        return (
            not self.absent
            and not self.exc_multi_price
            and not self.exc_same_price_multi_line
            and not self.exc_exceeds_received
        )

    @property
    def is_backfill_assignable(self) -> bool:
        """الإسناد الخلفي يقبل البند الوحيد وأيضاً عدّة بنود بسعر واحد متى كفى المستلم."""
        return not self.absent and not self.exc_multi_price and not self.exc_exceeds_received

    @property
    def reason_labels(self) -> list[str]:
        if self.absent:
            return ["غير_موجود_بالأصل"]
        labels: list[str] = []
        if self.exc_multi_price:
            labels.append("أ:تعدد_أسعار")
        if self.exc_same_price_multi_line:
            labels.append("أسطر_متعددة_بسعر_واحد")
        if self.exc_exceeds_received:
            labels.append("ب:تجاوز_مستلم")
        return labels


def classify_return_product_group(
    *,
    prices: set[Decimal] | None,
    line_count: int,
    total_received: Decimal,
    ret_qty: Decimal,
) -> ReturnProductClassification:
    """يصنّف زوج (فاتورة أصلية، منتج) — تستعمله `audit_purchase_returns` (S6) و`backfill_purchase_returns`."""
    ret_q = _qq(ret_qty)
    if prices is None or line_count == 0:
        return ReturnProductClassification(
            absent=True,
            exc_multi_price=False,
            exc_same_price_multi_line=False,
            exc_exceeds_received=False,
            ret_qty=ret_q,
            recv_qty=ZERO_Q,
        )
    recv_q = _qq(total_received)
    exc_a = len(prices) > 1
    exc_same = line_count > 1 and len(prices) == 1
    exc_b = ret_q > recv_q
    return ReturnProductClassification(
        absent=False,
        exc_multi_price=exc_a,
        exc_same_price_multi_line=exc_same,
        exc_exceeds_received=exc_b,
        ret_qty=ret_q,
        recv_qty=recv_q,
    )


# ── الإسناد الخلفي والتراجع ────────────────────────────────────────────────────

@dataclass(frozen=True)
class BackfillExceptionDetail:
    """تفصيل استثناءٍ واحد كما رُصد في التشغيل (أرقام ونصّ السبب فقط، بلا أسماء ولا بيانات شخصية).

    - `kind`: `"quantities"` (بند مرتجع) أو `"basis"` (فاتورة).
    - `invoice_id`/`invoice_number`: فاتورة الأصل لاستثناء الكميات، والفاتورة نفسها لاستثناء الأساس،
      وفاتورة **المرتجع** حين تكون الفاتورة الأصلية في شركة أخرى.
    - `return_item_id`: بند المرتجع (`None` للأساس)؛ `product_id`: المنتج أو `None`.
    """

    kind: str
    invoice_id: int
    invoice_number: str
    return_item_id: int | None
    product_id: int | None
    reason: str


@dataclass
class BackfillTenantResult:
    """نتيجة الإسناد الخلفي لشركة واحدة.

    - `exceptions_count`: عدد استثناءات الكميات وحدها (بند مرتجع واحد لكل استثناء).
    - `basis_mismatched`: عدد الفواتير ذات استثناء/عدم تطابق في الأساس (لا يُضاف إلى `exceptions_count`).
    - `groups_assigned`: عدد مجموعات (فاتورة الأصل، المنتج) المسندة، معاينةً وكتابةً.
    - `exceptions`: تفصيل كل استثناء لحظة رصده، فـ`len(exceptions) == exceptions_count + basis_mismatched`
      حتى حين يتخطّى `_exception_exists` صفاً مسجّلاً من تشغيلٍ سابق.
    """

    tenant_id: int
    company_name: str
    returns_assigned: int = 0
    applied_rows: int = 0
    exceptions_count: int = 0
    basis_matched: int = 0
    basis_mismatched: int = 0
    groups_assigned: int = 0
    exceptions: list[BackfillExceptionDetail] = field(default_factory=list)


@dataclass
class RollbackTenantResult:
    tenant_id: int
    company_name: str
    rolled_back: int = 0
    conflicts: int = 0
    conflict_messages: list[str] = field(default_factory=list)


def _record_applied_or_dry(
    records: list[PurchaseReturnBackfill],
    *,
    tenant_id: int,
    run_id: str,
    unit_key: str,
    invoice_id: int,
    item_id: int | None,
    source_return_item_id: int | None,
    field: str,
    value_before: str | None,
    value_after: str | None,
) -> None:
    records.append(
        PurchaseReturnBackfill(
            tenant_id=tenant_id,
            run_id=run_id,
            unit_key=unit_key,
            invoice_id=invoice_id,
            item_id=item_id,
            source_return_item_id=source_return_item_id,
            field=field,
            value_before=value_before,
            value_after=value_after,
            status=PurchaseReturnBackfill.STATUS_APPLIED,
            reason="",
        )
    )


def _exception_exists(
    *,
    tenant_id: int,
    invoice_id: int,
    item_id: int | None,
    source_return_item_id: int | None,
    field: str,
    reason: str,
) -> bool:
    return PurchaseReturnBackfill.objects.filter(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        item_id=item_id,
        source_return_item_id=source_return_item_id,
        field=field,
        status=PurchaseReturnBackfill.STATUS_EXCEPTION,
        reason=reason[:255],
    ).exists()


def lock_invoices_with_items(
    invoice_ids: Iterable[int], *, tenant_id: int, lock: bool = True,
) -> dict[int, PurchaseInvoiceItem]:
    """يقفل كل فاتورة (بترتيب الـid تصاعدياً) ثم بنودها مرتّبةً بالـid، ويعيد البنود مقروءةً بعد القفل.

    ترتيب القفل ثابت (§10.1.3) كي لا يتشابك مع ترحيل مرتجعٍ أو إلغائه (`select_for_update` داخل
    `transaction.atomic`). فاتورة ليست من الشركة لا تُقفل ولا تُقرأ بنودها. `lock=False` للمعاينة:
    قراءة بلا قفل."""
    items_by_id: dict[int, PurchaseInvoiceItem] = {}
    for invoice_id in sorted(set(invoice_ids)):
        invoice_qs = PurchaseInvoice.objects.filter(pk=invoice_id, tenant_id=tenant_id)
        items_qs = PurchaseInvoiceItem.objects.filter(invoice_id=invoice_id).order_by("id")
        if lock:
            invoice_qs = invoice_qs.select_for_update()
            items_qs = items_qs.select_for_update()
        if not list(invoice_qs.values_list("pk", flat=True)):
            continue
        for it in items_qs:
            items_by_id[it.id] = it
    return items_by_id


def _applied_return_item_ids(tenant_id: int) -> set[int]:
    """بنود المرتجع التي أسندها تشغيلٌ سابق (صفّ `applied` بمصدرٍ)، فلا تُسند ثانيةً."""
    return set(
        PurchaseReturnBackfill.objects.filter(
            tenant_id=tenant_id,
            status=PurchaseReturnBackfill.STATUS_APPLIED,
            source_return_item_id__isnull=False,
        ).values_list("source_return_item_id", flat=True)
    )


def _backfill_quantities_for_tenant(
    tenant,
    *,
    run_id: str,
    dry_run: bool,
    res: BackfillTenantResult,
    pending_logs: list[PurchaseReturnBackfill],
) -> tuple[dict[int, Decimal], set[int]]:
    """المرحلة أ: إسناد كميات المرتجعات القديمة.

    تعيد `(R, unassigned)`: `R` خريطة `بند الأصل ← returned_quantity بعد الإسناد` للبنود التي
    مسّتها المرحلة (من الذاكرة، فيطابق المعاينةُ الكتابةَ الفعلية)، و`unassigned` معرّفات فواتير
    الأصل التي بقي عليها مرتجعٌ مرحَّل غير مُسند (استثناء)."""
    tenant_id = tenant.TenantID
    returned_after: dict[int, Decimal] = {}
    unassigned_invoice_ids: set[int] = set()
    applied_return_item_ids = _applied_return_item_ids(tenant_id)

    # المرتجعات القديمة وحدها (`legacy_combined`)؛ مرتجع الفاتورة (`invoice`) يكتب كمياته بخدمته في M3
    ret_items = list(
        PurchaseInvoiceItem.objects.filter(
            invoice__tenant_id=tenant_id,
            invoice__is_return=True,
            invoice__is_posted=True,
            invoice__return_mode=PurchaseInvoice.RETURN_MODE_LEGACY_COMBINED,
            invoice__original_invoice_id__isnull=False,
            quantity__gt=0,
        )
        .exclude(id__in=applied_return_item_ids)
        .select_related("invoice", "invoice__original_invoice")
        .order_by("id")
    )
    if not ret_items:
        return returned_after, unassigned_invoice_ids

    # فصل المرتجعات العابرة للشركات وبنود المرتجع بلا منتج كاستثناءات مباشرة
    grouped: dict[tuple[int, int], list[PurchaseInvoiceItem]] = {}
    for rit in ret_items:
        if rit.invoice.original_invoice.tenant_id != tenant_id:
            reason = "الفاتورة الأصلية في شركة أخرى"
            res.exceptions_count += 1
            res.exceptions.append(
                BackfillExceptionDetail(
                    kind="quantities",
                    invoice_id=rit.invoice_id,
                    invoice_number=rit.invoice.invoice_number,
                    return_item_id=rit.id,
                    product_id=rit.product_id,
                    reason=reason,
                )
            )
            if not _exception_exists(
                tenant_id=tenant_id,
                invoice_id=rit.invoice_id,
                item_id=None,
                source_return_item_id=rit.id,
                field="returned_quantity",
                reason=reason,
            ):
                pending_logs.append(
                    PurchaseReturnBackfill(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        invoice_id=rit.invoice_id,
                        item_id=None,
                        source_return_item_id=rit.id,
                        field="returned_quantity",
                        value_before=None,
                        value_after=None,
                        status=PurchaseReturnBackfill.STATUS_EXCEPTION,
                        reason=reason,
                    )
                )
            continue
        if not rit.product_id:
            reason = "بند مرتجع بلا منتج"
            res.exceptions_count += 1
            res.exceptions.append(
                BackfillExceptionDetail(
                    kind="quantities",
                    invoice_id=rit.invoice.original_invoice_id,
                    invoice_number=rit.invoice.original_invoice.invoice_number,
                    return_item_id=rit.id,
                    product_id=None,
                    reason=reason,
                )
            )
            unassigned_invoice_ids.add(rit.invoice.original_invoice_id)
            if not _exception_exists(
                tenant_id=tenant_id,
                invoice_id=rit.invoice.original_invoice_id,
                item_id=None,
                source_return_item_id=rit.id,
                field="returned_quantity",
                reason=reason,
            ):
                pending_logs.append(
                    PurchaseReturnBackfill(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        invoice_id=rit.invoice.original_invoice_id,
                        item_id=None,
                        source_return_item_id=rit.id,
                        field="returned_quantity",
                        value_before=None,
                        value_after=None,
                        status=PurchaseReturnBackfill.STATUS_EXCEPTION,
                        reason=reason,
                    )
                )
            continue
        grouped.setdefault((rit.invoice.original_invoice_id, rit.product_id), []).append(rit)

    if not grouped:
        return returned_after, unassigned_invoice_ids

    orig_ids = sorted({oid for oid, _pid in grouped})
    prod_ids = sorted({pid for _oid, pid in grouped})

    # الكتابة الحقيقية: فاتورة الأصل ثم بنودها بالـid، وتُقرأ الكميات بعد القفل (§10.1.3)
    locked_items = lock_invoices_with_items(orig_ids, tenant_id=tenant_id, lock=not dry_run)
    if not dry_run:
        # سجلّ «مُطبَّق» يُعاد قراءته بعد القفل: تشغيلٌ متزامن ربما أسند بعض هذه المرتجعات قبلنا
        applied_after_lock = _applied_return_item_ids(tenant_id)
        grouped = {
            key: [rit for rit in rits if rit.id not in applied_after_lock]
            for key, rits in grouped.items()
        }
        grouped = {key: rits for key, rits in grouped.items() if rits}
    orig_items_map: dict[tuple[int, int], list[PurchaseInvoiceItem]] = {}
    for oit in sorted(locked_items.values(), key=lambda x: x.id):
        if oit.product_id in prod_ids:
            orig_items_map.setdefault((oit.invoice_id, oit.product_id), []).append(oit)

    assigned_return_ids: set[int] = set()

    for (orig_id, prod_id), group_ret_items in sorted(grouped.items()):
        orig_lines = orig_items_map.get((orig_id, prod_id), [])
        total_ret_q = sum((_qq(rit.quantity) for rit in group_ret_items), ZERO_Q)
        if orig_lines:
            prices = {Decimal(str(oit.unit_price or 0)) for oit in orig_lines}
            total_recv = sum((_qq(oit.received_quantity) for oit in orig_lines), ZERO_Q)
            cls = classify_return_product_group(
                prices=prices,
                line_count=len(orig_lines),
                total_received=total_recv,
                ret_qty=total_ret_q,
            )
        else:
            cls = classify_return_product_group(
                prices=None,
                line_count=0,
                total_received=ZERO_Q,
                ret_qty=total_ret_q,
            )

        if not cls.is_backfill_assignable:
            # نحتفظ بأسباب الاستثناء العربية الواضحة (دون اعتبار «أسطر_متعددة_بسعر_واحد» استثناءً)
            exc_reasons = [
                lbl for lbl in cls.reason_labels if lbl != "أسطر_متعددة_بسعر_واحد"
            ]
            reason_txt = "+".join(exc_reasons) if exc_reasons else "غير_قابل_للإسناد"
            unassigned_invoice_ids.add(orig_id)
            for rit in group_ret_items:
                res.exceptions_count += 1
                res.exceptions.append(
                    BackfillExceptionDetail(
                        kind="quantities",
                        invoice_id=orig_id,
                        invoice_number=rit.invoice.original_invoice.invoice_number,
                        return_item_id=rit.id,
                        product_id=prod_id,
                        reason=reason_txt[:255],
                    )
                )
                if not _exception_exists(
                    tenant_id=tenant_id,
                    invoice_id=orig_id,
                    item_id=None,
                    source_return_item_id=rit.id,
                    field="returned_quantity",
                    reason=reason_txt,
                ):
                    pending_logs.append(
                        PurchaseReturnBackfill(
                            tenant_id=tenant_id,
                            run_id=run_id,
                            invoice_id=orig_id,
                            item_id=None,
                            source_return_item_id=rit.id,
                            field="returned_quantity",
                            value_before=None,
                            value_after=None,
                            status=PurchaseReturnBackfill.STATUS_EXCEPTION,
                            reason=reason_txt[:255],
                        )
                    )
            continue

        res.groups_assigned += 1
        # تتبّع الكميات الجارية في الذاكرة عند إسناد عدّة سطور مرتجع على نفس المجموعة
        unit_key = f"qty:{orig_id}:{prod_id}"
        cur_returned = {oit.id: _qq(oit.returned_quantity) for oit in orig_lines}
        cur_received = {oit.id: _qq(oit.received_quantity) for oit in orig_lines}
        dirty_orig_ids: set[int] = set()

        for rit in group_ret_items:
            rem = _qq(rit.quantity)
            touched_orig_lines: list[PurchaseInvoiceItem] = []
            for oit in orig_lines:
                if rem <= ZERO_Q:
                    break
                avail_r = cur_received[oit.id]
                if avail_r <= ZERO_Q:
                    continue
                take = min(rem, avail_r)
                before_c = cur_returned[oit.id]
                after_c = _qq(before_c + take)
                before_r = cur_received[oit.id]
                after_r = _qq(before_r - take)

                cur_returned[oit.id] = after_c
                cur_received[oit.id] = after_r
                dirty_orig_ids.add(oit.id)
                touched_orig_lines.append(oit)

                _record_applied_or_dry(
                    pending_logs,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    unit_key=unit_key,
                    invoice_id=orig_id,
                    item_id=oit.id,
                    source_return_item_id=rit.id,
                    field="returned_quantity",
                    value_before=str(before_c),
                    value_after=str(after_c),
                )
                _record_applied_or_dry(
                    pending_logs,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    unit_key=unit_key,
                    invoice_id=orig_id,
                    item_id=oit.id,
                    source_return_item_id=rit.id,
                    field="received_quantity",
                    value_before=str(before_r),
                    value_after=str(after_r),
                )
                res.applied_rows += 2
                rem = _qq(rem - take)

            # `return_of_item` يُضبط فقط حين يُسند سطر المرتجع كله إلى بند أصل واحد
            if len(touched_orig_lines) == 1:
                target_oit = touched_orig_lines[0]
                before_roi = str(rit.return_of_item_id) if rit.return_of_item_id else None
                after_roi = str(target_oit.id)
                if before_roi != after_roi:
                    _record_applied_or_dry(
                        pending_logs,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        unit_key=unit_key,
                        invoice_id=rit.invoice_id,
                        item_id=rit.id,
                        source_return_item_id=rit.id,
                        field="return_of_item",
                        value_before=before_roi,
                        value_after=after_roi,
                    )
                    res.applied_rows += 1
                    if not dry_run:
                        PurchaseInvoiceItem.objects.filter(
                            pk=rit.id, invoice__tenant_id=tenant_id,
                        ).update(return_of_item_id=target_oit.id)

            assigned_return_ids.add(rit.invoice_id)

        if not dry_run and dirty_orig_ids:
            for oit in orig_lines:
                if oit.id in dirty_orig_ids:
                    PurchaseInvoiceItem.objects.filter(
                        pk=oit.id, invoice__tenant_id=tenant_id,
                    ).update(
                        returned_quantity=cur_returned[oit.id],
                        received_quantity=cur_received[oit.id],
                    )
        returned_after.update(cur_returned)

    res.returns_assigned = len(assigned_return_ids)
    return returned_after, unassigned_invoice_ids


def already_reversed_basis(posted: Decimal, *, quantity, returned) -> Decimal:
    """`returned_*_base`: ما عُكس من أساسٍ مسبقاً لمرتجعٍ قديم = `posted_*_base` كلّه إن
    `returned_quantity` ≥ `quantity` (البند كله)، وإلا round(posted × returned / quantity, 2)
    بـROUND_HALF_UP، وصفر إن `returned_quantity` = 0. يُطبَّق على كل مكوّنٍ (صافٍ/ضريبة/2110) على حدة (§10.1.2)."""
    q, r = _qq(quantity), _qq(returned)
    p = _q2(posted)
    if r <= ZERO_Q or q <= ZERO_Q:
        return ZERO
    if r >= q:
        return p
    return (p * r / q).quantize(DEC, rounding=ROUND_HALF_UP)


def _log_basis_exception(
    pending_logs: list[PurchaseReturnBackfill],
    *,
    tenant_id: int,
    run_id: str,
    invoice_id: int,
    reason: str,
) -> None:
    reason_trimmed = reason[:255]
    if _exception_exists(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        item_id=None,
        source_return_item_id=None,
        field="basis",
        reason=reason_trimmed,
    ):
        return
    pending_logs.append(
        PurchaseReturnBackfill(
            tenant_id=tenant_id,
            run_id=run_id,
            invoice_id=invoice_id,
            item_id=None,
            source_return_item_id=None,
            field="basis",
            value_before=None,
            value_after=None,
            status=PurchaseReturnBackfill.STATUS_EXCEPTION,
            reason=reason_trimmed,
        )
    )


def _refresh_returned_basis(
    inv: PurchaseInvoice,
    items: list[PurchaseInvoiceItem],
    *,
    tenant_id: int,
    run_id: str,
    dry_run: bool,
    res: BackfillTenantResult,
    pending_logs: list[PurchaseReturnBackfill],
    returned_quantities: dict[int, Decimal],
) -> None:
    """فاتورة أساسها معبّأ: بندٌ مسّته مرحلة الكميات في هذا التشغيل يُعاد حساب `returned_*_base` له من
    `posted_*_base` المخزَّن و`returned_quantity` الجديد. لا مساس بـ`posted_*` ولا `posted_account`،
    ويُسجَّل كل حقلٍ تغيّر فقط (قابلاً للتراجع بوحدة `basis:<الفاتورة>`)؛ المعاينة تحسب وتسجّل بلا كتابة."""
    unit_key = f"basis:{inv.id}"
    for it in items:
        if it.id not in returned_quantities:
            continue
        returned_q = returned_quantities[it.id]
        changes: dict[str, Decimal] = {}
        for posted_fld, returned_fld in (
            ("posted_net_base", "returned_net_base"),
            ("posted_tax_base", "returned_tax_base"),
            ("posted_clearing_base", "returned_clearing_base"),
        ):
            before = getattr(it, returned_fld)
            after = already_reversed_basis(
                getattr(it, posted_fld), quantity=it.quantity, returned=returned_q,
            )
            if before is not None and _q2(before) == after:
                continue
            changes[returned_fld] = after
            _record_applied_or_dry(
                pending_logs,
                tenant_id=tenant_id,
                run_id=run_id,
                unit_key=unit_key,
                invoice_id=inv.id,
                item_id=it.id,
                source_return_item_id=None,
                field=returned_fld,
                value_before=str(_q2(before)) if before is not None else None,
                value_after=str(after),
            )
            res.applied_rows += 1
        if changes and not dry_run:
            PurchaseInvoiceItem.objects.filter(
                pk=it.id, invoice__tenant_id=tenant_id,
            ).update(**changes)


def _backfill_basis_for_tenant(
    tenant,
    *,
    run_id: str,
    dry_run: bool,
    res: BackfillTenantResult,
    pending_logs: list[PurchaseReturnBackfill],
    returned_quantities: dict[int, Decimal] | None = None,
    unassigned_invoice_ids: set[int] | None = None,
) -> None:
    """المرحلة ب: أساس الفواتير المرحّلة. `returned_quantities`/`unassigned_invoice_ids` من المرحلة أ
    في التشغيل نفسه (R بعد الإسناد من الذاكرة، فالمعاينة تطابق الكتابة الفعلية)."""
    tenant_id = tenant.TenantID
    returned_quantities = returned_quantities or {}
    unassigned_invoice_ids = unassigned_invoice_ids or set()
    invoices = list(
        PurchaseInvoice.objects.filter(
            tenant_id=tenant_id,
            is_return=False,
            is_posted=True,
            journal_id__isnull=False,
        )
        .select_related("tenant", "journal")
        .prefetch_related(
            Prefetch("items", queryset=PurchaseInvoiceItem.objects.order_by("id")),
            "fees",
        )
        .order_by("id")
    )

    for inv in invoices:
        if not dry_run:
            # الكتابة الحقيقية: الفاتورة ثم بنودها بالـid، وتُعاد قراءتها بعد القفل قبل أي قرار (§10.1.3)
            locked_items = lock_invoices_with_items([inv.id], tenant_id=tenant_id, lock=True)
            inv = (
                PurchaseInvoice.objects.filter(pk=inv.id, tenant_id=tenant_id)
                .select_related("tenant", "journal")
                .first()
            )
            if inv is None or not inv.is_posted or not inv.journal_id:
                continue
            items = sorted(locked_items.values(), key=lambda x: x.id)
        else:
            items = list(inv.items.all())
        if not items:
            continue
        # حالة التعبئة: كل البنود معبّأة ⇒ تحديث returned_*_base لما تغيّر R له؛ كلها فارغة ⇒ تعبئة؛
        # خلاف ذلك ⇒ استثناء بلا كتابة
        filled = [
            it.posted_net_base is not None
            and it.posted_tax_base is not None
            and it.posted_clearing_base is not None
            for it in items
        ]
        empty = [
            it.posted_net_base is None
            and it.posted_tax_base is None
            and it.posted_clearing_base is None
            for it in items
        ]
        # مرتجعٌ مرحَّل لم يُسنَد على الفاتورة ⇒ E مجهول ⇒ لا أساس ولا تحديث لـreturned_*_base (الجانب الآمن)
        if inv.id in unassigned_invoice_ids:
            reason = "مرتجع غير مُسند على الفاتورة"
            res.basis_mismatched += 1
            res.exceptions.append(
                BackfillExceptionDetail(
                    kind="basis", invoice_id=inv.id, invoice_number=inv.invoice_number,
                    return_item_id=None, product_id=None, reason=reason,
                )
            )
            _log_basis_exception(
                pending_logs, tenant_id=tenant_id, run_id=run_id,
                invoice_id=inv.id, reason=reason,
            )
            continue
        if all(filled):
            _refresh_returned_basis(
                inv, items, tenant_id=tenant_id, run_id=run_id, dry_run=dry_run, res=res,
                pending_logs=pending_logs, returned_quantities=returned_quantities,
            )
            continue
        if not all(empty):
            reason = "أساس معبّأ جزئياً"
            res.basis_mismatched += 1
            res.exceptions.append(
                BackfillExceptionDetail(
                    kind="basis", invoice_id=inv.id, invoice_number=inv.invoice_number,
                    return_item_id=None, product_id=None, reason=reason,
                )
            )
            _log_basis_exception(
                pending_logs, tenant_id=tenant_id, run_id=run_id,
                invoice_id=inv.id, reason=reason,
            )
            continue

        basis, empty_reason = _compute_invoice_line_basis_with_reason(inv)
        if empty_reason:
            # الأساس فارغ لسببٍ معروف: يُسجَّل السبب الحقيقي بلا مقارنةٍ بالقيد
            matched, reason = False, empty_reason
        else:
            matched, reason = basis_matches_journal(inv, basis)
        if not matched:
            res.basis_mismatched += 1
            res.exceptions.append(
                BackfillExceptionDetail(
                    kind="basis", invoice_id=inv.id, invoice_number=inv.invoice_number,
                    return_item_id=None, product_id=None, reason=reason[:255],
                )
            )
            _log_basis_exception(
                pending_logs, tenant_id=tenant_id, run_id=run_id,
                invoice_id=inv.id, reason=reason,
            )
            continue

        res.basis_matched += 1
        unit_key = f"basis:{inv.id}"
        for it in items:
            lb = basis[it.id]
            returned_q = returned_quantities.get(it.id, it.returned_quantity)
            e_net = already_reversed_basis(lb.net_base, quantity=it.quantity, returned=returned_q)
            e_tax = already_reversed_basis(lb.tax_base, quantity=it.quantity, returned=returned_q)
            e_clearing = already_reversed_basis(
                lb.clearing_base, quantity=it.quantity, returned=returned_q,
            )
            field_updates = [
                (
                    "posted_account",
                    str(it.posted_account_id) if it.posted_account_id else None,
                    str(lb.account_id) if lb.account_id else None,
                ),
                (
                    "posted_net_base",
                    str(_q2(it.posted_net_base)) if it.posted_net_base is not None else None,
                    str(lb.net_base),
                ),
                (
                    "posted_tax_base",
                    str(_q2(it.posted_tax_base)) if it.posted_tax_base is not None else None,
                    str(lb.tax_base),
                ),
                (
                    "posted_clearing_base",
                    str(_q2(it.posted_clearing_base)) if it.posted_clearing_base is not None else None,
                    str(lb.clearing_base),
                ),
                (
                    "returned_net_base",
                    str(_q2(it.returned_net_base)) if it.returned_net_base is not None else None,
                    str(e_net),
                ),
                (
                    "returned_tax_base",
                    str(_q2(it.returned_tax_base)) if it.returned_tax_base is not None else None,
                    str(e_tax),
                ),
                (
                    "returned_clearing_base",
                    str(_q2(it.returned_clearing_base)) if it.returned_clearing_base is not None else None,
                    str(e_clearing),
                ),
            ]
            for fld, before_v, after_v in field_updates:
                _record_applied_or_dry(
                    pending_logs,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    unit_key=unit_key,
                    invoice_id=inv.id,
                    item_id=it.id,
                    source_return_item_id=None,
                    field=fld,
                    value_before=before_v,
                    value_after=after_v,
                )
                res.applied_rows += 1

            if not dry_run:
                PurchaseInvoiceItem.objects.filter(
                    pk=it.id, invoice__tenant_id=tenant_id,
                ).update(
                    posted_account_id=lb.account_id,
                    posted_net_base=lb.net_base,
                    posted_tax_base=lb.tax_base,
                    posted_clearing_base=lb.clearing_base,
                    returned_net_base=e_net,
                    returned_tax_base=e_tax,
                    returned_clearing_base=e_clearing,
                )


def run_backfill_for_tenant(
    tenant,
    *,
    run_id: str | None = None,
    dry_run: bool = True,
) -> BackfillTenantResult:
    """ينفّذ الإسناد الخلفي (أ: الكميات، ب: الأساس) لشركة واحدة داخل معاملة ذرية.

    معاينةٌ افتراضياً بلا كتابة (`dry_run=True`) مثل الأمر؛ الكتابة بـ`dry_run=False` صراحةً."""
    run_id = run_id or str(uuid.uuid4())
    res = BackfillTenantResult(
        tenant_id=tenant.TenantID,
        company_name=tenant.CompanyName,
    )
    pending_logs: list[PurchaseReturnBackfill] = []

    if dry_run:
        returned_after, unassigned = _backfill_quantities_for_tenant(
            tenant, run_id=run_id, dry_run=True, res=res, pending_logs=pending_logs,
        )
        _backfill_basis_for_tenant(
            tenant, run_id=run_id, dry_run=True, res=res, pending_logs=pending_logs,
            returned_quantities=returned_after, unassigned_invoice_ids=unassigned,
        )
    else:
        with transaction.atomic():
            returned_after, unassigned = _backfill_quantities_for_tenant(
                tenant, run_id=run_id, dry_run=False, res=res, pending_logs=pending_logs,
            )
            _backfill_basis_for_tenant(
                tenant, run_id=run_id, dry_run=False, res=res, pending_logs=pending_logs,
                returned_quantities=returned_after, unassigned_invoice_ids=unassigned,
            )
            if pending_logs:
                PurchaseReturnBackfill.objects.bulk_create(pending_logs)

    logger.info(
        "backfill_purchase_returns run_id=%s tenant=%s dry_run=%s returns=%s groups=%s applied=%s exc=%s basis_ok=%s basis_diff=%s",
        run_id,
        tenant.TenantID,
        dry_run,
        res.returns_assigned,
        res.groups_assigned,
        res.applied_rows,
        res.exceptions_count,
        res.basis_matched,
        res.basis_mismatched,
    )
    return res


_QTY_FIELDS = {"returned_quantity", "received_quantity"}
_MONEY_FIELDS = {
    "posted_net_base",
    "posted_tax_base",
    "posted_clearing_base",
    "returned_net_base",
    "returned_tax_base",
    "returned_clearing_base",
}
_FK_FIELDS = {"return_of_item", "posted_account"}
_BASIS_FIELDS = _MONEY_FIELDS | {"posted_account"}


def _values_match(field: str, current_val, expected_str: str | None) -> bool:
    if field in _FK_FIELDS:
        exp = None if expected_str is None else int(expected_str)
        return current_val == exp
    if field in _QTY_FIELDS:
        if current_val is None or expected_str is None:
            return current_val is None and expected_str is None
        return _qq(current_val) == _qq(expected_str)
    if field in _MONEY_FIELDS:
        if current_val is None or expected_str is None:
            return current_val is None and expected_str is None
        return _q2(current_val) == _q2(expected_str)
    return (None if current_val is None else str(current_val)) == expected_str


def _parse_restore_value(field: str, val_str: str | None):
    if val_str is None:
        return None
    if field in _FK_FIELDS:
        return int(val_str)
    if field in _QTY_FIELDS:
        return _qq(val_str)
    if field in _MONEY_FIELDS:
        return _q2(val_str)
    return val_str


def _rollback_unit_key(row: PurchaseReturnBackfill) -> str:
    """مفتاح وحدة التراجع الذرّي: مجموعة (أصل، منتج) للكميات، وفاتورة واحدة للأساس."""
    if row.unit_key:
        return row.unit_key
    if row.field in _BASIS_FIELDS:
        return f"basis:{row.invoice_id}" if row.invoice_id else f"basis_row:{row.id}"
    sri = row.source_return_item
    if sri and sri.invoice and sri.invoice.original_invoice_id and sri.product_id:
        return f"qty:{sri.invoice.original_invoice_id}:{sri.product_id}"
    return f"qty_row:{row.id}"


def rollback_backfill_for_tenant(
    tenant,
    *,
    run_id: str,
    dry_run: bool = True,
) -> RollbackTenantResult:
    """يتراجع ذرّياً عن كل وحدة `applied` لتشغيل معيّن في شركة واحدة بترتيب عكسي.

    معاينةٌ افتراضياً بلا كتابة (`dry_run=True`) مثل الأمر؛ التراجع الفعلي بـ`dry_run=False` صراحةً."""
    tenant_id = tenant.TenantID
    res = RollbackTenantResult(tenant_id=tenant_id, company_name=tenant.CompanyName)

    rows = list(
        PurchaseReturnBackfill.objects.filter(
            tenant_id=tenant_id,
            run_id=run_id,
            status=PurchaseReturnBackfill.STATUS_APPLIED,
        )
        .select_related("source_return_item__invoice")
        .order_by("-id")
    )
    if not rows:
        return res

    units: dict[str, list[PurchaseReturnBackfill]] = {}
    for row in rows:
        units.setdefault(_rollback_unit_key(row), []).append(row)

    def _rollback_body():
        for u_key, unit_rows in units.items():
            # فحص كل صفوف الوحدة أولاً قبل أي كتابة: تعارض أيّ صفٍ يترك الوحدة كاملةً بلا تغيير
            unit_cached: dict[tuple[int, str], object] = {}
            unit_conflicts: list[str] = []
            unit_updates: list[tuple[PurchaseReturnBackfill, str, object]] = []

            # §10.1.3: فواتير الأصل أولاً ثم فواتير المرتجع (كلٌّ بالـid تصاعدياً)، وكل فاتورةٍ
            # يليها بنودها؛ وقيمة الفحص تُقرأ من البنود بعد القفل لا من تحميل الصفوف.
            original_ids = {
                r.invoice_id for r in unit_rows if r.invoice_id and r.field != "return_of_item"
            }
            return_ids = {
                r.invoice_id for r in unit_rows if r.invoice_id and r.field == "return_of_item"
            } - original_ids
            locked_items = {
                **lock_invoices_with_items(original_ids, tenant_id=tenant_id, lock=not dry_run),
                **lock_invoices_with_items(return_ids, tenant_id=tenant_id, lock=not dry_run),
            }

            for row in unit_rows:
                locked = locked_items.get(row.item_id) if row.item_id else None
                if locked is None:
                    unit_conflicts.append(
                        f"صف #{row.id} (الهدف محذوف للحقل {row.field})"
                    )
                    continue
                attr = f"{row.field}_id" if row.field in _FK_FIELDS else row.field
                cache_key = (row.item_id, attr)
                if cache_key in unit_cached:
                    current_val = unit_cached[cache_key]
                else:
                    current_val = getattr(locked, attr)

                if not _values_match(row.field, current_val, row.value_after):
                    unit_conflicts.append(
                        f"صف #{row.id} على البند #{row.item_id} حقل {row.field}: "
                        f"الحالي={current_val} المتوقّع={row.value_after}"
                    )
                    continue

                restored = _parse_restore_value(row.field, row.value_before)
                unit_cached[cache_key] = restored
                unit_updates.append((row, attr, restored))

            if unit_conflicts:
                res.conflicts += 1
                res.conflict_messages.append(
                    f"تعارض في وحدة {u_key} (تُركت بلا أي كتابة): " + "؛ ".join(unit_conflicts)
                )
                continue

            for row, attr, restored in unit_updates:
                if not dry_run:
                    PurchaseInvoiceItem.objects.filter(
                        pk=row.item_id, invoice__tenant_id=tenant_id,
                    ).update(**{attr: restored})
                    PurchaseReturnBackfill.objects.filter(
                        pk=row.id, tenant_id=tenant_id,
                    ).update(status=PurchaseReturnBackfill.STATUS_ROLLED_BACK)
                res.rolled_back += 1

    if dry_run:
        _rollback_body()
    else:
        with transaction.atomic():
            _rollback_body()

    logger.info(
        "backfill_purchase_returns rollback run_id=%s tenant=%s dry_run=%s rolled_back=%s conflicts=%s",
        run_id, tenant_id, dry_run, res.rolled_back, res.conflicts,
    )
    return res
