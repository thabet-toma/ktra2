"""
ترحيل فواتير المبيعات، حركة المخزون، وتحصيل العملاء.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from accounting.models import Account
from accounting.services import (
    convert_amount,
    create_audit_log,
    post_journal,
    resolve_forex_account,
    validate_fiscal_period,
    validate_journal_entry,
)
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner, PartnerGroup

from .models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)

logger = logging.getLogger(__name__)

DEC = Decimal("0.01")


def get_or_create_default_customer(tenant) -> Partner:
    """يُعيد (أو يُنشئ) العميل الافتراضي «الزبون العام» لشركة معيّنة.

    - name = "الزبون العام"
    - partner_type = Customer
    - لا يُخصَّص له credit_limit
    """
    tenant_id = getattr(tenant, "TenantID", tenant)
    existing = (
        Partner.objects.filter(
            tenant_id=tenant_id,
            partner_type="Customer",
            name__in=["الزبون العام", "العميل الافتراضي", "General Customer", "Cash Customer"],
        )
        .order_by("id")
        .first()
    )
    if existing:
        return existing
    # إنشاء مجموعة افتراضية إن لم تكن موجودة
    group = (
        PartnerGroup.objects.filter(
            tenant_id=tenant_id, group_type="Customer"
        )
        .order_by("id")
        .first()
    )
    if not group:
        group = PartnerGroup.objects.create(
            tenant_id=tenant_id, name="عملاء عامون", group_type="Customer"
        )
    return Partner.objects.create(
        tenant_id=tenant_id,
        name="الزبون العام",
        legal_name="الزبون العام",
        partner_type="Customer",
        group=group,
    )


def get_or_create_sales_settings(tenant) -> SalesSettings:
    """يُعيد (أو يُنشئ) إعدادات المبيعات للشركة، ويضبط قيمًا افتراضية ذكية."""
    tenant_id = getattr(tenant, "TenantID", tenant)
    settings_obj = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if settings_obj:
        # تأكد أن العميل الافتراضي موجود
        if settings_obj.default_customer_id is None:
            settings_obj.default_customer = get_or_create_default_customer(tenant_id)
            settings_obj.save(update_fields=["default_customer"])
        return settings_obj

    default_customer = get_or_create_default_customer(tenant_id)

    # محاولة استنتاج عملة أساسية
    default_currency = None
    try:
        from tenants.models import Currency
        default_currency = (
            Currency.objects.filter(IsBaseCurrency=True).order_by("CurrencyID").first()
            or Currency.objects.order_by("CurrencyID").first()
        )
    except (Currency.DoesNotExist, Currency.MultipleObjectsReturned):
        default_currency = None

    # محاولة استنتاج حساب إيرادات افتراضي
    default_rev = (
        Account.objects.filter(
            tenant_id=tenant_id, account_type="Revenue", is_active=True
        )
        .order_by("code")
        .first()
    )

    # ضريبة VAT افتراضية
    default_vat = None
    try:
        from accounting.models import TaxRate
        default_vat = (
            TaxRate.objects.filter(tenant_id=tenant_id, is_active=True)
            .filter(direction__in=["sales", "both", "output"])
            .order_by("id")
            .first()
            or TaxRate.objects.filter(tenant_id=tenant_id, is_active=True).order_by("id").first()
        )
    except (TaxRate.DoesNotExist, TaxRate.MultipleObjectsReturned):
        default_vat = None

    settings_obj = SalesSettings.objects.create(
        tenant_id=tenant_id,
        default_customer=default_customer,
        default_currency=default_currency,
        default_revenue_account_product=default_rev,
        default_revenue_account_service=default_rev,
        default_vat_rate=default_vat,
    )
    return settings_obj


def line_net(line: SalesInvoiceLine) -> Decimal:
    q = Decimal(str(line.quantity))
    p = Decimal(str(line.unit_price))
    d = Decimal(str(line.line_discount or 0))
    return (q * p - d).quantize(DEC)


def recalculate_invoice_amounts(invoice: SalesInvoice, lines: list[SalesInvoiceLine] | None = None) -> None:
    """يحدّث حقول الأسطر والفاتورة (بدون حفظ في قاعدة البيانات).
    M2-T1: supports discount_percent (per-invoice %) and prices_include_tax per-invoice override.
    """
    if lines is None:
        lines = list(invoice.lines.select_related("tax_rate"))
    sub = Decimal("0.00")
    pairs: list[tuple[SalesInvoiceLine, Decimal]] = []
    for line in lines:
        net = line_net(line)
        if invoice.prices_include_tax and line.tax_rate:
            rate = Decimal(str(line.tax_rate.rate))
            tax_inclusive = net / (Decimal("1") + rate / Decimal("100"))
            net = tax_inclusive.quantize(DEC)
        pairs.append((line, net))
        sub += net

    disc = Decimal(str(invoice.invoice_discount or 0))
    if sub > 0 and disc > sub:
        disc = sub
    ratio = ((sub - disc) / sub) if sub > 0 else Decimal(0)
    excl_after = (sub - disc).quantize(DEC) if sub > 0 else Decimal("0.00")

    pct = Decimal(str(getattr(invoice, "discount_percent", 0) or 0))
    if pct > 0:
        excl_after = (excl_after * (Decimal("100") - pct) / Decimal("100")).quantize(DEC)

    tax_sum = Decimal("0.00")
    for line, orig_n in pairs:
        adj_net = (orig_n * ratio).quantize(DEC) if sub > 0 else Decimal("0.00")
        line.line_total_excl_tax = adj_net
        if line.tax_rate_id and line.tax_rate:
            t = (adj_net * Decimal(str(line.tax_rate.rate)) / Decimal("100")).quantize(DEC)
        else:
            t = Decimal("0.00")
        line.line_tax_amount = t
        tax_sum += t

    invoice.subtotal_excl_tax = excl_after
    invoice.tax_amount = tax_sum.quantize(DEC)
    invoice.grand_total = (excl_after + invoice.tax_amount).quantize(DEC)


def _resolve_ar_account(invoice: SalesInvoice) -> Account:
    if invoice.accounts_receivable_account_id:
        return invoice.accounts_receivable_account
    p: Partner = invoice.customer
    if p.group_id:
        g = PartnerGroup.objects.filter(pk=p.group_id).first()
        if g and g.account_receivable_id:
            return g.account_receivable
    if p.linked_account_id:
        return p.linked_account
    # fallback إلى إعدادات المبيعات
    ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
    if ss and ss.default_ar_account_id:
        return ss.default_ar_account
    raise ValidationError(
        "لا يوجد حساب ذمم للعميل: عيّن مجموعة عملاء بذمم، أو حساب مرتبط بالعميل، "
        "أو حقل ذمم افتراضي في إعدادات المبيعات."
    )


def _default_revenue_account(tenant_id: int, *, is_service: bool = False) -> Account:
    """يفضّل الحساب من إعدادات المبيعات (منتج/خدمة)، ثم أول حساب إيرادات نشط."""
    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if ss:
        if is_service and ss.default_revenue_account_service_id:
            return ss.default_revenue_account_service
        if (not is_service) and ss.default_revenue_account_product_id:
            return ss.default_revenue_account_product
        # fallback على أي من الاثنين
        if ss.default_revenue_account_product_id:
            return ss.default_revenue_account_product
        if ss.default_revenue_account_service_id:
            return ss.default_revenue_account_service
    acc = (
        Account.objects.filter(
            tenant_id=tenant_id,
            account_type="Revenue",
            is_active=True,
        )
        .order_by("id")
        .first()
    )
    if not acc:
        raise ValidationError(
            "لا يوجد حساب إيرادات نشط للشركة. أنشئ حساب إيرادات أو حدّده على الفاتورة/فئة المنتج "
            "أو في إعدادات المبيعات."
        )
    return acc


def _resolve_revenue_account_for_line(invoice: SalesInvoice, line: SalesInvoiceLine) -> Account:
    p = line.product
    is_service = bool(getattr(p, "is_service", False))

    # P-H-7: product-level override (from inventory.Product account overrides)
    if not is_service:
        from inventory.services import _resolve_line_account
        try:
            return _resolve_line_account(p, 'revenue', tenant_id=invoice.tenant_id)
        except Exception:
            pass  # fall through to legacy resolution

    if invoice.revenue_account_id and not is_service:
        return invoice.revenue_account
    cat = getattr(p, "category", None)
    if cat and cat.revenue_account_id and not is_service:
        return cat.revenue_account
    return _default_revenue_account(invoice.tenant_id, is_service=is_service)


def _revenue_credit_journal_rows(invoice: SalesInvoice, lines: list[SalesInvoiceLine]) -> list[tuple[int, Decimal]]:
    """(account_id, مبلغ دائن) لمجموع الإيرادات، مع تفريق المنتج/الخدمة."""
    buckets: dict[int, Decimal] = defaultdict(Decimal)
    for line in lines:
        acc = _resolve_revenue_account_for_line(invoice, line)
        buckets[acc.id] += Decimal(str(line.line_total_excl_tax))
    return [(aid, amt.quantize(DEC)) for aid, amt in buckets.items() if amt > 0]


def _lock_products_for_lines(lines: list[SalesInvoiceLine]) -> dict[int, Product]:
    pids = list({l.product_id for l in lines})
    qs = list(
        Product.objects.select_for_update()
        .select_related(
            "category",
            "category__revenue_account",
            "category__cogs_account",
            "category__inventory_account",
        )
        .filter(pk__in=pids)
    )
    found = {p.id: p for p in qs}
    if len(found) != len(pids):
        raise ValidationError("بعض أصناف الفاتورة غير موجودة أو مكررة.")
    return found


def _build_cogs_journal_line_dicts(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    products_by_id: dict[int, Product],
) -> list[dict]:
    """Dr COGS / Cr Inventory — مبالغ من متوسط التكلفة قبل الصرف (نفس منطق حركة المخزون)."""
    ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
    fb_cogs = ss.default_cogs_account_id if ss else None
    fb_inv = ss.default_inventory_account_id if ss else None

    pair_totals: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for line in lines:
        p = products_by_id[line.product_id]
        if getattr(p, 'is_service', False):
            continue
        qty = Decimal(str(line.quantity))
        avg = Decimal(str(p.avg_cost))
        amt = (qty * avg).quantize(DEC)
        if amt <= 0:
            continue
        cat = p.category
        cogs_id = cat.cogs_account_id if cat and cat.cogs_account_id else fb_cogs
        inv_id = cat.inventory_account_id if cat and cat.inventory_account_id else fb_inv
        if not cogs_id or not inv_id:
            cname = cat.name if cat else "(بدون فئة)"
            raise ValidationError(
                f"الصنف «{p.sku}» — الفئة «{cname}»: عيّن حساب تكلفة المبيعات والمخزون في فئة المنتج "
                f"أو حسابات افتراضية في إعدادات المبيعات، أو عطّل خصم المخزون عند الترحيل."
            )
        pair_totals[(cogs_id, inv_id)] += amt

    rows: list[dict] = []
    for (cid, iid), amt in pair_totals.items():
        if amt <= 0:
            continue
        rows.append(
            {
                "account": cid,
                "partner": None,
                "debit": amt,
                "credit": Decimal("0"),
                "description": f"تكلفة مبيعات — {invoice.invoice_number}",
            }
        )
        rows.append(
            {
                "account": iid,
                "partner": None,
                "debit": Decimal("0"),
                "credit": amt,
                "description": f"تخفيض مخزون — {invoice.invoice_number}",
            }
        )
    return rows


def _partner_open_balance_excluding_invoice(partner: Partner, exclude_invoice_id: int | None) -> Decimal:
    """يجمع المتبقي على الفواتير بالعملة الأساسية (exchange_rate) لتجنّب خلط عملات مختلفة."""
    qs = SalesInvoice.objects.filter(
        customer=partner,
        status=SalesInvoice.STATUS_POSTED,
    )
    if exclude_invoice_id:
        qs = qs.exclude(pk=exclude_invoice_id)
    total = Decimal("0")
    for inv in qs:
        rate = Decimal(str(getattr(inv, "exchange_rate", 1) or 1))
        due = (Decimal(str(inv.grand_total or 0)) - Decimal(str(inv.amount_paid or 0))) * rate
        total += due.quantize(DEC)
    return total.quantize(DEC)


def _build_tax_buckets(lines: list[SalesInvoiceLine]) -> dict[int, Decimal]:
    """يجمع ضرائب الأسطر في دلاء (bucket) حسب حساب الضريبة.

    يرفض إنشاء دلو بمفتاح None — لأن ذلك يؤدي إلى سطر قيد بحساب غير صالح.
    إن وُجد سطر له tax_rate لكن بدون tax_account، يُرفع ValidationError لوقف الترحيل.
    كما يفحص أن اتجاه الـ TaxRate مناسب لفاتورة مبيعات (sales أو both).
    """
    buckets: dict[int, Decimal] = {}
    for line in lines:
        if not line.tax_rate_id or not line.tax_rate:
            continue
        amt = Decimal(str(line.line_tax_amount or 0))
        if amt <= 0:
            continue
        tr = line.tax_rate
        tid = tr.tax_account_id
        if not tid:
            raise ValidationError(
                f"سطر الفاتورة يستخدم ضريبة '{tr.code}' بدون حساب محاسبي مربوط. "
                f"اذهب إلى إعدادات الضرائب واربط tax_account بهذه النسبة."
            )
        # فحص اتجاه الضريبة — المبيعات تتطلب sales أو both
        direction = getattr(tr, 'direction', 'both') or 'both'
        if direction not in ('sales', 'both'):
            raise ValidationError(
                f"نسبة الضريبة '{tr.code}' اتجاهها '{direction}' — لا يمكن استخدامها في فاتورة مبيعات. "
                f"استخدم نسبة بـ direction='sales' أو 'both'."
            )
        # فحص نوع الحساب — ضريبة مبيعات يجب أن تكون التزاماً
        acc_type = getattr(tr.tax_account, 'account_type', None)
        if acc_type and acc_type != 'Liability':
            raise ValidationError(
                f"حساب ضريبة المبيعات '{tr.tax_account.code}' نوعه {acc_type} — "
                f"يجب أن يكون Liability (التزام لسلطة الضرائب)."
            )
        buckets[tid] = buckets.get(tid, Decimal("0")) + amt
    return buckets


# ─────────────────────────────────────────────────────────────────────────
# M2-T3 — Invoice-attached payment voucher (cash + cheques)
# ─────────────────────────────────────────────────────────────────────────

def attach_payment_voucher(
    invoice: SalesInvoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
) -> SalesInvoice:
    """يربط سند مالي (نقدي + شيكات) بالفاتورة قبل الترحيل.

    - Replace-semantics: each call replaces previously-attached cheques on the
      invoice (no duplicates). Use empty `cheques=[]` to clear.
    - The journal is NOT posted here — `post_sales_invoice` reads the attached
      cash + cheques and posts ONE integrated journal (M2-T3 spec).
    - Idempotency: posting goes through `post_journal()` which deduplicates by
      (reference_type, reference_id). Calling this function multiple times
      pre-post just updates the attachment state.

    cheques: list of dicts with keys:
        cheque_number (str, required)
        amount        (Decimal/str, required)
        bank_name     (str, optional)
        due_date      (date or ISO str, optional)
        issue_date    (date or ISO str, optional)
        payee_name    (str, optional)
        notes         (str, optional)
    """
    from accounting.models import Cheque

    if invoice.status == SalesInvoice.STATUS_POSTED:
        raise ValidationError("لا يمكن تعديل السند بعد ترحيل الفاتورة.")

    cash_amount = Decimal(str(cash_amount or 0)).quantize(DEC)
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")

    cheques = cheques or []
    # Validate each cheque payload
    for i, c in enumerate(cheques):
        if not str(c.get("cheque_number", "")).strip():
            raise ValidationError(f"الشيك #{i+1}: رقم الشيك مطلوب.")
        try:
            amt = Decimal(str(c.get("amount", 0)))
        except Exception:
            raise ValidationError(f"الشيك #{i+1}: مبلغ غير صالح.")
        if amt <= 0:
            raise ValidationError(f"الشيك #{i+1}: المبلغ يجب أن يكون أكبر من صفر.")

    cheques_total = sum(
        (Decimal(str(c.get("amount", 0))) for c in cheques), Decimal("0")
    ).quantize(DEC)

    # Compute current invoice total to validate against (without saving)
    if invoice.pk:
        recalculate_invoice_amounts(invoice)
    grand = Decimal(str(invoice.grand_total or 0)).quantize(DEC)
    if (cash_amount + cheques_total) > grand:
        raise ValidationError(
            f"مجموع السند ({cash_amount} نقدي + {cheques_total} شيكات) "
            f"يتجاوز مبلغ الفاتورة {grand}."
        )

    if cash_amount > 0 and not cash_account_id:
        raise ValidationError("لا بدّ من تحديد حساب الصندوق عند وجود مبلغ نقدي.")

    with transaction.atomic():
        # 1) Cash side on the invoice
        invoice.attached_cash_amount = cash_amount
        if cash_amount > 0:
            invoice.attached_cash_account_id = cash_account_id
        else:
            invoice.attached_cash_account_id = None
        invoice.save(update_fields=[
            "attached_cash_amount", "attached_cash_account",
        ])

        # 2) Cheques side — REPLACE previously-linked DRAFT cheques only
        # (don't touch cheques already in Under_Collection or beyond).
        Cheque.objects.filter(
            sales_invoice=invoice, status="Draft"
        ).delete()
        for c in cheques:
            Cheque.objects.create(
                tenant_id=invoice.tenant_id,
                sales_invoice=invoice,
                partner=invoice.customer,
                direction="Incoming",
                status="Draft",  # promoted to Under_Collection on invoice post
                cheque_number=str(c.get("cheque_number")).strip(),
                bank_name=(c.get("bank_name") or "")[:100],
                amount=Decimal(str(c.get("amount"))).quantize(DEC),
                currency_id=invoice.currency_id,
                due_date=c.get("due_date") or None,
                issue_date=c.get("issue_date") or None,
                payee_name=(c.get("payee_name") or "")[:150],
                notes=c.get("notes") or "",
                created_by=user if user and not getattr(user, "is_anonymous", False) else None,
            )

    return invoice


def attach_voucher_and_post(
    invoice: SalesInvoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
) -> SalesInvoice:
    """P-H-5: atomic attach + post.

    Wraps `attach_payment_voucher` and `post_sales_invoice` in a single
    `transaction.atomic()` block. If `post_sales_invoice` raises, the
    cheques created in the attach step are rolled back along with the
    posting attempt. This closes the gap where a user calls the two
    endpoints separately and gets a half-applied state (Draft cheques
    attached but no journal posted).

    Use this for the «sign+post in one click» UX; the separate endpoints
    remain available for the «build the voucher, review, then post»
    flow.
    """
    with transaction.atomic():
        attach_payment_voucher(
            invoice,
            cash_amount=cash_amount,
            cash_account_id=cash_account_id,
            cheques=cheques,
            user=user,
        )
        post_sales_invoice(invoice, user=user)
    return invoice


def post_sales_invoice(
    invoice: SalesInvoice,
    *,
    user=None,
) -> SalesInvoice:
    """ترحيل فاتورة: قيد محاسبي + (اختياري) خصم مخزون.

    N8-T11: يَدعم الآن 4 أنواع (فاتورة بيع/مرجع بيع/فاتورة شراء/مرجع شراء)
    عبر حقل `invoice_kind`. للمراجيع، تُعكس إشارات القيد والمخزون.
    """
    if invoice.status == SalesInvoice.STATUS_POSTED:
        raise ValidationError("الفاتورة مرحّلة مسبقاً.")
    if invoice.status == SalesInvoice.STATUS_CANCELLED:
        raise ValidationError("لا يمكن ترحيل فاتورة ملغاة.")

    # N8-T11: sign multiplier للمراجيع
    kind = invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE
    is_return = kind in (SalesInvoice.INVOICE_KIND_SALE_RETURN, SalesInvoice.INVOICE_KIND_PURCHASE_RETURN)
    sign = -1 if is_return else 1

    lines = list(
        invoice.lines.select_related("product", "tax_rate", "tax_rate__tax_account", "product__tenant")
    )
    if not lines:
        raise ValidationError("الفاتورة بلا بنود.")

    if invoice.customer.tenant_id != invoice.tenant_id:
        raise ValidationError("العميل لا يتبع نفس الشركة (Tenant).")

    recalculate_invoice_amounts(invoice, lines)
    SalesInvoiceLine.objects.bulk_update(
        lines,
        ["line_total_excl_tax", "line_tax_amount"],
    )
    SalesInvoice.objects.filter(pk=invoice.pk).update(
        subtotal_excl_tax=invoice.subtotal_excl_tax,
        tax_amount=invoice.tax_amount,
        grand_total=invoice.grand_total,
    )
    invoice.refresh_from_db()
    lines = list(
        invoice.lines.select_related("product", "tax_rate", "tax_rate__tax_account", "product__tenant")
    )

    validate_fiscal_period(invoice.tenant_id, invoice.invoice_date)

    if invoice.invoice_type == SalesInvoice.INVOICE_CREDIT:
        if invoice.customer.partner_type != "Customer":
            raise ValidationError("الطرف المحدد ليس عميلاً.")
        limit = invoice.customer.credit_limit
        if limit is not None:
            open_bal = _partner_open_balance_excluding_invoice(
                invoice.customer, exclude_invoice_id=invoice.pk
            )
            if open_bal + invoice.grand_total > Decimal(str(limit)) + DEC:
                raise ValidationError(
                    f"تجاوز حد الائتمان. الحد: {limit} — الرصيد المفتوح: {open_bal} — إجمالي الفاتورة: {invoice.grand_total}"
                )

    grand = invoice.grand_total

    with transaction.atomic():
        lines = list(
            invoice.lines.select_related(
                "tax_rate",
                "tax_rate__tax_account",
                "product__tenant",
                "product__category",
                "product__category__revenue_account",
                "product__category__cogs_account",
                "product__category__inventory_account",
            )
        )
        products_by_id = _lock_products_for_lines(lines)
        for line in lines:
            line.product = products_by_id[line.product_id]

        journal_lines: list[dict] = []

        # ── M2-T3: Attached payment voucher (cash + cheques) ─────────────────
        # The Aseel invoice carries optional «مدفوع نقدا» + «مدفوع شيكات»
        # alongside the invoice itself. Both reduce the primary debit (AR for
        # credit invoices, cash for cash invoices) and post as additional Dr
        # lines in the SAME integrated journal — Aseel-style single voucher.
        attached_cash = Decimal(str(invoice.attached_cash_amount or 0)).quantize(DEC)
        # Cheques attached via accounting.Cheque.sales_invoice FK (M2-T3 migration)
        attached_cheques = list(invoice.cheques.all()) if invoice.pk else []
        cheques_total = sum(
            (Decimal(str(c.amount or 0)) for c in attached_cheques),
            Decimal("0.00"),
        ).quantize(DEC)
        attached_total = (attached_cash + cheques_total).quantize(DEC)
        if attached_total > grand:
            raise ValidationError(
                f"مجموع السند المرفق (نقدي {attached_cash} + شيكات {cheques_total}) "
                f"يتجاوز مبلغ الفاتورة {grand}."
            )

        if invoice.invoice_type == SalesInvoice.INVOICE_CASH:
            cash = invoice.cash_or_bank_account
            if not cash:
                raise ValidationError("فواتير النقدي تتطلب حساب صندوق/بنك (cash_or_bank_account).")
            # Cash invoice: primary cash line = grand − cheques_total (cheques
            # go to under-collection bucket). attached_cash on cash invoices is
            # redundant — its account is the same as cash_or_bank_account.
            primary_debit = (grand - cheques_total).quantize(DEC)
            if primary_debit > 0:
                journal_lines.append(
                    {
                        "account": cash.id,
                        "partner": invoice.customer_id,
                        "debit": primary_debit,
                        "credit": Decimal("0"),
                        "description": f"تحصيل نقدي — {invoice.invoice_number}",
                    }
                )
        else:
            ar = _resolve_ar_account(invoice)
            ar_debit = (grand - attached_total).quantize(DEC)
            # NOTE: We always emit the AR line first so the source-discount
            # logic below can adjust its debit. If everything is paid (cash +
            # cheques == grand), AR debit is 0 — we still emit a placeholder
            # so source-discount reduction logic has a stable target index.
            journal_lines.append(
                {
                    "account": ar.id,
                    "partner": invoice.customer_id,
                    "debit": ar_debit if ar_debit > 0 else Decimal("0"),
                    "credit": Decimal("0"),
                    "description": f"ذمم — {invoice.invoice_number}",
                }
            )
            # Attached cash (different cashbox than the AR resolution)
            if attached_cash > 0:
                pay_acc = invoice.attached_cash_account
                if not pay_acc:
                    raise ValidationError(
                        "السند المرفق فيه مبلغ نقدي لكن لم يُحدَّد حساب الصندوق "
                        "(attached_cash_account)."
                    )
                journal_lines.append(
                    {
                        "account": pay_acc.id,
                        "partner": invoice.customer_id,
                        "debit": attached_cash,
                        "credit": Decimal("0"),
                        "description": f"مدفوع نقدا — {invoice.invoice_number}",
                    }
                )

        # Cheques bucket (شيكات برسم التحصيل) — both cash and credit invoices.
        if cheques_total > 0:
            ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
            uc_acc = (
                ss.default_cheques_under_collection_account if ss else None
            )
            if not uc_acc:
                # Fall back to any Asset account named «شيكات…» or coded 1106.
                from django.db.models import Q
                uc_acc = (
                    Account.objects.filter(
                        tenant_id=invoice.tenant_id,
                        account_type="Asset",
                        is_active=True,
                    )
                    .filter(Q(code__startswith="1106") | Q(name__icontains="شيكات"))
                    .first()
                )
            if not uc_acc:
                raise ValidationError(
                    "فاتورة بها شيكات مرفقة لكن لا يوجد حساب «شيكات برسم التحصيل». "
                    "عيّن `default_cheques_under_collection_account` في إعدادات "
                    "المبيعات، أو أنشئ حساب Asset بكود يبدأ بـ 1106."
                )
            journal_lines.append(
                {
                    "account": uc_acc.id,
                    "partner": invoice.customer_id,
                    "debit": cheques_total,
                    "credit": Decimal("0"),
                    "description": f"مدفوع شيكات — {invoice.invoice_number}",
                }
            )

        for acc_id, cred_amt in _revenue_credit_journal_rows(invoice, lines):
            if cred_amt > 0:
                journal_lines.append(
                    {
                        "account": acc_id,
                        "partner": None,
                        "debit": Decimal("0"),
                        "credit": cred_amt,
                        "description": f"مبيعات — {invoice.invoice_number}",
                    }
                )

        tax_buckets = _build_tax_buckets(lines)
        for tax_account_id, amt in tax_buckets.items():
            if amt <= 0:
                continue
            journal_lines.append(
                {
                    "account": tax_account_id,
                    "partner": None,
                    "debit": Decimal("0"),
                    "credit": amt.quantize(DEC),
                    "description": f"ضريبة مخرجات — {invoice.invoice_number}",
                }
            )

        if invoice.stock_on_post:
            journal_lines.extend(_build_cogs_journal_line_dicts(invoice, lines, products_by_id))

        # ── M2-T4 (G6): Source-discount / withholding ──────────────────────
        # Source discount = the slice of the invoice the customer holds back as
        # withholding tax against the seller (Aseel «خصم مصدر»). It is NOT the
        # regular invoice discount (`discount_percent`/`invoice_discount`) which
        # is ALREADY netted into `subtotal_excl_tax`/`grand_total` upstream.
        #
        # Lookup priority (per-invoice override → customer default):
        #   1. invoice.source_discount_amount_override (explicit amount)
        #   2. invoice.source_discount_percent_override (% of grand_total)
        #   3. customer.source_discount_amount  (default amount)
        #   4. customer.source_discount_percent (default % of grand_total)
        src_disc_amt = Decimal("0.00")
        src_disc_pct_used = Decimal("0.00")
        if invoice.source_discount_amount_override is not None:
            src_disc_amt = Decimal(str(invoice.source_discount_amount_override)).quantize(DEC)
        elif invoice.source_discount_percent_override is not None:
            src_disc_pct_used = Decimal(str(invoice.source_discount_percent_override))
            src_disc_amt = (grand * src_disc_pct_used / Decimal("100")).quantize(DEC)
        elif invoice.customer:
            cust_amt = Decimal(str(getattr(invoice.customer, "source_discount_amount", 0) or 0))
            cust_pct = Decimal(str(getattr(invoice.customer, "source_discount_percent", 0) or 0))
            if cust_amt > 0:
                src_disc_amt = cust_amt
            elif cust_pct > 0:
                src_disc_pct_used = cust_pct
                src_disc_amt = (grand * src_disc_pct_used / Decimal("100")).quantize(DEC)

        # Clamp: cannot exceed the receivable/cash debit
        if src_disc_amt > grand:
            src_disc_amt = grand

        if src_disc_amt > 0:
            ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
            disc_acct = None
            # Priority: dedicated SalesSettings setting → COA code 1107 (Asset).
            if ss and ss.default_source_discount_account_id:
                disc_acct = ss.default_source_discount_account
            if not disc_acct:
                disc_acct = Account.objects.filter(
                    tenant_id=invoice.tenant_id,
                    code__startswith="1107",
                    account_type="Asset",
                    is_active=True,
                ).first()
            if not disc_acct:
                raise ValidationError(
                    "خصم المصدر مفعّل (افتراضي العميل أو تجاوز الفاتورة) لكن لا يوجد حساب "
                    "خصم مصدر مهيّأ. عيّن `default_source_discount_account` في إعدادات "
                    "المبيعات، أو أنشئ حساب Asset بكود يبدأ بـ 1107 (خصم مصدر مقدّم)."
                )
            # Add Dr source-discount-receivable for the withheld amount.
            desc_pct = (
                f" ({src_disc_pct_used}%)" if src_disc_pct_used > 0 else ""
            )
            journal_lines.append({
                "account": disc_acct.id,
                "partner": invoice.customer_id,
                "debit": src_disc_amt,
                "credit": Decimal("0"),
                "description": f"خصم مصدر{desc_pct} — {invoice.invoice_number}",
            })
            # REDUCE the receivable/cash debit line by src_disc_amt — customer
            # actually owes (or pays) `grand − src_disc_amt`; the rest is now a
            # claim on the tax authority.  Journal remains balanced because we
            # added a Dr of the same amount on the source-discount account.
            # The first journal line is always AR (credit invoice) or cash (cash
            # invoice) — both built immediately above with `debit=grand`.
            recv_line = journal_lines[0]
            recv_line["debit"] = (Decimal(str(recv_line["debit"])) - src_disc_amt).quantize(DEC)

        tenant_name = ""
        try:
            tenant_name = (invoice.tenant.CompanyName or "").strip()
        except AttributeError:
            tenant_name = ""
        cust_name = ""
        try:
            cust_name = (invoice.customer.name or "").strip()
        except AttributeError:
            cust_name = ""
        # N8-T11: عكس إشارات القيد للمراجيع
        if is_return:
            kind_label = dict(SalesInvoice.INVOICE_KIND_CHOICES).get(kind, kind)
            for jl in journal_lines:
                jl["debit"], jl["credit"] = jl["credit"], jl["debit"]

        desc_parts = []
        if tenant_name:
            desc_parts.append(f"[{tenant_name}]")
        kind_label = dict(SalesInvoice.INVOICE_KIND_CHOICES).get(kind, "فاتورة")
        desc_parts.append(f"{kind_label} {invoice.invoice_number}")
        if cust_name:
            desc_parts.append(f"— {cust_name}")
        if invoice.notes:
            desc_parts.append(f"· {invoice.notes}")
        final_desc = " ".join(desc_parts)[:500]

        jh = post_journal(
            tenant_id=invoice.tenant_id,
            transaction_date=invoice.invoice_date,
            reference_type="SALES_INVOICE",
            reference_id=invoice.id,
            description=final_desc,
            lines_data=journal_lines,
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate,
            user=user,
        )

        invoice.journal = jh
        invoice.status = SalesInvoice.STATUS_POSTED
        # M2-T3: amount_paid reflects what came in with the invoice itself
        # (cash + cheques). Subsequent CustomerPayments will add on top of this
        # via post_customer_payment's allocation logic.
        if attached_total > 0:
            invoice.amount_paid = (
                Decimal(str(invoice.amount_paid or 0)) + attached_total
            ).quantize(DEC)
            invoice.save(update_fields=["journal", "status", "amount_paid"])
        else:
            invoice.save(update_fields=["journal", "status"])

        # M2-T3: promote attached cheques from Draft → Under_Collection now that
        # the journal is posted. Cheques already past Draft are untouched.
        if attached_cheques:
            from accounting.models import Cheque
            Cheque.objects.filter(
                sales_invoice=invoice, status="Draft"
            ).update(status="Under_Collection")

        if invoice.stock_on_post:
            if is_return:
                # N8-T11 + P-H-2: stock reconciliation by return direction.
                # sale_return → RETURN_IN  (goods come back from customer)
                # purchase_return → RETURN_OUT (goods leave back to supplier)
                is_purchase_return = kind == SalesInvoice.INVOICE_KIND_PURCHASE_RETURN
                mv_type = "RETURN_OUT" if is_purchase_return else "RETURN_IN"
                for line in lines:
                    if getattr(line.product, "is_service", False):
                        continue
                    record_stock_movement(
                        product=line.product,
                        movement_type=mv_type,
                        quantity=line.quantity,
                        reference_type="SALE",
                        reference_id=invoice.id,
                        partner=invoice.customer,
                        movement_date=invoice.invoice_date,
                        notes=f"مرجع {invoice.invoice_number}",
                        tenant=invoice.tenant,
                    )
            else:
                _post_stock_out_for_invoice(invoice, lines, user=user)

        create_audit_log(
            tenant=invoice.tenant,
            user=user,
            action="POST",
            model_name="SalesInvoice",
            object_id=invoice.id,
            change_details=f"Posted sales invoice {invoice.invoice_number} journal={jh.id}",
        )

    return invoice


def _post_stock_out_for_invoice(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    *,
    user=None,
) -> None:
    # Idempotency: skip if stock movement already exists for this invoice
    if StockMovement.objects.filter(
        reference_type="SALE", reference_id=invoice.id
    ).exists():
        return
    for line in lines:
        if getattr(line.product, "is_service", False):
            continue
        if line.product.tenant_id != invoice.tenant_id:
            raise ValidationError(f"الصنف {line.product_id} لا يتبع نفس الشركة.")
        try:
            record_stock_movement(
                product=line.product,
                movement_type="OUT",
                quantity=line.quantity,
                reference_type="SALE",
                reference_id=invoice.id,
                partner=invoice.customer,
                movement_date=invoice.invoice_date,
                notes=f"بيع فاتورة {invoice.invoice_number}",
                tenant=invoice.tenant,
            )
        except ValidationError as e:
            raise ValidationError(f"مخزون الصنف {line.product.sku}: {e}")


def issue_stock_from_invoice(invoice: SalesInvoice, *, user=None):
    """T4-05: إصدار إذن صرف صريح للمبيعات (STOCK_ISSUE).

    Idempotent: إن وُجد StockMovement بـ STOCK_ISSUE لنفس الفاتورة يُرجع مبكراً.
    يُستدعى من frontend_v2 بعد ترحيل الفاتورة وقبل التسليم.
    """
    if StockMovement.objects.filter(
        reference_type="STOCK_ISSUE", reference_id=invoice.id
    ).exists():
        return
    lines = list(invoice.lines.select_related("product"))
    for line in lines:
        if getattr(line.product, "is_service", False):
            continue
        try:
            record_stock_movement(
                product=line.product,
                movement_type="OUT",
                quantity=line.quantity,
                reference_type="STOCK_ISSUE",
                reference_id=invoice.id,
                partner=invoice.customer,
                movement_date=invoice.invoice_date,
                notes=f"إذن صرف من فاتورة {invoice.invoice_number}",
                tenant=invoice.tenant,
            )
        except Exception as e:
            raise ValidationError(f"خطأ في إذن الصرف لصنف {line.product.sku}: {e}")


def deliver_delivery_order(delivery: DeliveryOrder, *, user=None) -> DeliveryOrder:
    """تسليم أمر إخراج وخصم المخزون إذا كانت الفاتورة بدون خصم عند الترحيل + قيد COGS عندها فقط."""
    inv = delivery.invoice
    if delivery.status == DeliveryOrder.STATUS_DELIVERED:
        raise ValidationError("تم التسليم مسبقاً.")
    if inv.status != SalesInvoice.STATUS_POSTED:
        raise ValidationError("الفاتورة غير مرحّلة.")

    with transaction.atomic():
        lines = list(
            inv.lines.select_related(
                "product",
                "product__category",
                "product__category__cogs_account",
                "product__category__inventory_account",
            )
        )
        products_by_id = _lock_products_for_lines(lines)
        for line in lines:
            line.product = products_by_id[line.product_id]

        if not inv.stock_on_post:
            _post_stock_out_for_invoice(inv, lines, user=user)
            cogs_rows = _build_cogs_journal_line_dicts(inv, lines, products_by_id)
            if cogs_rows:
                post_journal(
                    tenant_id=inv.tenant_id,
                    transaction_date=inv.invoice_date,
                    reference_type="SALES_DELIVERY_COGS",
                    reference_id=inv.id,
                    description=(f"تكلفة مبيعات عند التسليم — {inv.invoice_number}")[:500],
                    lines_data=cogs_rows,
                    currency=inv.currency,
                    exchange_rate=inv.exchange_rate,
                    user=user,
                )

        delivery.status = DeliveryOrder.STATUS_DELIVERED
        from django.utils import timezone

        delivery.delivered_at = timezone.now()
        delivery.save(update_fields=["status", "delivered_at"])
        create_audit_log(
            tenant=inv.tenant,
            user=user,
            action="UPDATE",
            model_name="DeliveryOrder",
            object_id=delivery.id,
            change_details=f"Delivered DO for invoice {inv.invoice_number}",
        )
    return delivery


def _resolve_ar_account_for_partner(partner: Partner) -> Account:
    if partner.group_id:
        g = PartnerGroup.objects.filter(pk=partner.group_id).first()
        if g and g.account_receivable_id:
            return g.account_receivable
    if partner.linked_account_id:
        return partner.linked_account
    # Fallback to sales settings (matches _resolve_ar_account)
    ss = SalesSettings.objects.filter(tenant_id=partner.tenant_id).first()
    if ss and ss.default_ar_account_id:
        return ss.default_ar_account
    raise ValidationError("لا يوجد حساب ذمم للعميل.")


def post_customer_payment(payment: CustomerPayment, *, user=None) -> CustomerPayment:
    """ترحيل دفعة عميل مع دعم كامل لتعدد العملات.

    إذا كانت عملة الدفعة مختلفة عن عملة الفاتورة:
    - يتم تحويل مبلغ التوزيع لعملة الفاتورة باستخدام سعر الصرف
    - يُحدَّث amount_paid بالمبلغ المحوّل (بعملة الفاتورة)
    - يُسجَّل فرق العملة (forex gain/loss) إذا وُجد
    """
    if payment.is_posted:
        raise ValidationError("الدفعة مرحّلة مسبقاً.")

    if payment.partner.tenant_id != payment.tenant_id:
        raise ValidationError("العميل لا يتبع نفس الشركة.")

    validate_fiscal_period(payment.tenant_id, payment.payment_date)

    allocated = (
        PaymentAllocation.objects.filter(payment=payment).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    if allocated != payment.amount:
        raise ValidationError("مجموع التوزيعات يجب أن يساوي مبلغ الدفعة.")

    # ── التحقق من التوزيعات + تحويل العملات مسبقاً ──
    payment_currency_id = payment.currency_id
    alloc_conversions: list[tuple[PaymentAllocation, Decimal, Decimal]] = []

    for alloc in payment.allocations.select_related("invoice", "invoice__currency"):
        if alloc.invoice.customer_id != payment.partner_id:
            raise ValidationError("توزيع الدفعة على فاتورة لا تخص نفس العميل.")
        if alloc.invoice.status != SalesInvoice.STATUS_POSTED:
            raise ValidationError(f"الفاتورة #{alloc.invoice.invoice_number} غير مرحّلة.")

        inv = alloc.invoice
        inv_currency_id = inv.currency_id

        # ── تحويل مبلغ التوزيع من عملة الدفعة إلى عملة الفاتورة ──
        if payment_currency_id == inv_currency_id:
            # نفس العملة — لا تحويل
            amount_in_inv_curr = Decimal(str(alloc.amount))
            conv_rate = Decimal("1")
        else:
            amount_in_inv_curr, conv_rate = convert_amount(
                amount=Decimal(str(alloc.amount)),
                from_currency_id=payment_currency_id,
                to_currency_id=inv_currency_id,
                tenant_id=payment.tenant_id,
                effective_date=payment.payment_date,
            )

        # ملاحظة: التحقق من تجاوز المتبقي يتم لاحقاً تحت قفل select_for_update
        # داخل transaction.atomic() لمنع سباق lost-update / الدفع الزائد.
        alloc_conversions.append((alloc, amount_in_inv_curr, conv_rate))

    ar = _resolve_ar_account_for_partner(payment.partner)

    with transaction.atomic():
        # قفل الفواتير (select_for_update) ومادّتها فعلياً في dict لمنع
        # سباق lost-update على amount_paid. لا بد من تقييم الـ queryset
        # (التكرار) حتى يصدر SELECT ... FOR UPDATE فعلياً.
        inv_ids = sorted({alloc.invoice_id for alloc, _amt, _rate in alloc_conversions})
        locked_invoices = {
            inv.pk: inv
            for inv in SalesInvoice.objects.select_for_update().filter(pk__in=inv_ids)
        }

        # إجمالي الزيادة لكل فاتورة (قد تتعدّد التوزيعات على نفس الفاتورة)
        increment_by_invoice: dict[int, Decimal] = {}
        for alloc, amount_in_inv_curr, _conv in alloc_conversions:
            increment_by_invoice[alloc.invoice_id] = (
                increment_by_invoice.get(alloc.invoice_id, Decimal("0"))
                + amount_in_inv_curr
            )

        # إعادة التحقق من تجاوز المتبقي على الصفوف المقفلة (القراءة الحديثة)
        for inv_id, total_increment in increment_by_invoice.items():
            inv = locked_invoices[inv_id]
            remaining = inv.grand_total - Decimal(str(inv.amount_paid))
            if total_increment > remaining + DEC:
                raise ValidationError(
                    f"مبلغ التوزيع المحوّل ({total_increment} بعملة الفاتورة) "
                    f"يتجاوز المتبقي على الفاتورة #{inv.invoice_number} ({remaining})."
                )

        # ── بناء أسطر القيد المحاسبي ──
        # فرق العملة (I4-03): إذا اختلفت عملة الدفعة عن عملة الفاتورة نحسب
        # المبلغ المعادل بعملة الدفعة ونضبط سطر الذمم + نضيف سطر فروقات عملة.
        # هذا يضمن توازن القيد دائماً:
        #   Dr صندوق/بنك  = payment.amount
        #   Cr ذمم مدينة  = payment.amount - forex_diff  (إن كان ربح) أو payment.amount + abs(forex_diff) (إن كان خسارة)
        #   Cr/Dr فروقات عملة = |forex_diff|
        # المجموع: Dr = Cr = payment.amount (ربح) أو payment.amount + abs(loss) (خسارة)

        total_alloc_in_inv_curr = sum(
            (amt for _alloc, amt, _rate in alloc_conversions), Decimal("0")
        )
        forex_diff = Decimal("0")
        forex_acc = None

        # P-H-8: per-allocation FX. The previous implementation took
        # alloc_conversions[0][0].invoice.currency_id as "the" source
        # currency and converted the SUM of all allocations through it.
        # That sum is meaningless when the payment covers invoices in
        # mixed currencies (e.g. EUR invoice + ILS invoice with a USD
        # payment): the EUR and ILS amounts get added before either is
        # converted. The fix is to convert each allocation separately
        # from its own invoice currency to the payment currency and
        # accumulate the result.
        if payment_currency_id and alloc_conversions:
            total_in_pay_curr = Decimal("0")
            any_mismatch = False
            for alloc, amount_in_inv_curr, _rate in alloc_conversions:
                inv_curr_id = alloc.invoice.currency_id
                if inv_curr_id == payment_currency_id:
                    total_in_pay_curr += amount_in_inv_curr
                else:
                    any_mismatch = True
                    converted, _ = convert_amount(
                        amount=amount_in_inv_curr,
                        from_currency_id=inv_curr_id,
                        to_currency_id=payment_currency_id,
                        tenant_id=payment.tenant_id,
                        effective_date=payment.payment_date,
                    )
                    total_in_pay_curr += converted
            if any_mismatch:
                forex_diff = (payment.amount - total_in_pay_curr).quantize(DEC)
                if abs(forex_diff) > DEC:
                    forex_acc = resolve_forex_account(payment.tenant_id)
                    if not forex_acc:
                        raise ValidationError(
                            "فرق عملة مكتشف لكن لا يوجد حساب فروقات عملة. "
                            "أنشئ حساباً باسم 'فرق عمل' من نوع Expense أو Revenue."
                        )

        # forex_diff > 0 → ربح (دفعنا أكثر من قيمة الفاتورة بالعملة المحوّلة)
        # forex_diff < 0 → خسارة
        ar_credit = (payment.amount - forex_diff).quantize(DEC)

        lines_data: list[dict] = [
            {
                "account": payment.cash_or_bank_account_id,
                "partner": payment.partner_id,
                "debit": payment.amount,
                "credit": Decimal("0"),
                "description": f"تحصيل عميل — دفعة {payment.id}",
            },
            {
                "account": ar.id,
                "partner": payment.partner_id,
                "debit": Decimal("0"),
                "credit": ar_credit,
                "description": f"تخفيض ذمم — دفعة {payment.id}",
            },
        ]

        if forex_acc and abs(forex_diff) > DEC:
            if forex_diff > 0:
                # ربح صرف: دائن في حساب فروقات العملة يوازن فرق الذمم
                lines_data.append({
                    "account": forex_acc.id,
                    "partner": None,
                    "debit": Decimal("0"),
                    "credit": forex_diff,
                    "description": f"ربح فروق عملة — دفعة {payment.id}",
                })
            else:
                # خسارة صرف: مدين في حساب فروقات العملة + الذمم دائن بأكثر
                lines_data.append({
                    "account": forex_acc.id,
                    "partner": None,
                    "debit": abs(forex_diff),
                    "credit": Decimal("0"),
                    "description": f"خسارة فروق عملة — دفعة {payment.id}",
                })

        jh = post_journal(
            tenant_id=payment.tenant_id,
            transaction_date=payment.payment_date,
            reference_type="CUSTOMER_PAYMENT",
            reference_id=payment.id,
            description=(payment.notes or f"تحصيل عميل {payment.partner.name}")[:500],
            lines_data=lines_data,
            currency=payment.currency,
            exchange_rate=payment.exchange_rate,
            user=user,
        )

        payment.journal = jh
        payment.is_posted = True
        payment.save(update_fields=["journal", "is_posted"])

        # ── حفظ مبلغ/سعر تحويل كل توزيع للمرجعية ──
        for alloc, amount_in_inv_curr, conv_rate in alloc_conversions:
            alloc.amount_in_invoice_currency = amount_in_inv_curr
            alloc.conversion_rate = conv_rate
            alloc.save(update_fields=["amount_in_invoice_currency", "conversion_rate"])
            logger.info(
                "Payment %s alloc → invoice %s: %s (pay currency) → %s (inv currency) @ rate %s",
                payment.id, locked_invoices[alloc.invoice_id].invoice_number,
                alloc.amount, amount_in_inv_curr, conv_rate,
            )

        # ── تحديث amount_paid على الصفوف المقفلة (مرّة واحدة لكل فاتورة) ──
        for inv_id, total_increment in increment_by_invoice.items():
            inv = locked_invoices[inv_id]
            inv.amount_paid = Decimal(str(inv.amount_paid)) + total_increment
            inv.save(update_fields=["amount_paid"])

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="POST",
            model_name="CustomerPayment",
            object_id=payment.id,
            change_details=(
                f"Customer payment posted journal={jh.id} "
                f"currency={payment.currency_id} amount={payment.amount}"
            ),
        )

    return payment


def credit_preview_for_sale(
    *,
    tenant_id: int,
    partner_id: int,
    proposed_total: Decimal,
    exclude_invoice_id: int | None = None,
) -> dict:
    """معاينة حد الائتمان قبل الترحيل (وللمسودة من الواجهة)."""
    partner = Partner.objects.filter(pk=partner_id, tenant_id=tenant_id).first()
    if not partner:
        raise ValidationError("عميل غير موجود.")
    open_bal = _partner_open_balance_excluding_invoice(partner, exclude_invoice_id)
    prop = Decimal(str(proposed_total)).quantize(DEC)
    limit = partner.credit_limit
    projected = open_bal + prop
    would_exceed = limit is not None and projected > Decimal(str(limit)) + DEC
    return {
        "credit_limit": str(limit) if limit is not None else None,
        "open_balance": str(open_bal),
        "proposed_total": str(prop),
        "projected_balance": str(projected),
        "would_exceed": would_exceed,
    }


def suggest_fifo_allocations(
    *,
    tenant_id: int,
    partner_id: int,
    amount: Decimal,
) -> list[dict]:
    """اقتراح توزيع دفعة على الفواتير من الأقدم (FIFO) حسب المتبقي."""
    remaining = Decimal(str(amount)).quantize(DEC)
    if remaining <= 0:
        return []
    invs = (
        SalesInvoice.objects.filter(
            tenant_id=tenant_id,
            customer_id=partner_id,
            status=SalesInvoice.STATUS_POSTED,
        )
        .order_by("invoice_date", "id")
    )
    out: list[dict] = []
    for inv in invs:
        if remaining <= 0:
            break
        due = (inv.grand_total - Decimal(str(inv.amount_paid))).quantize(DEC)
        if due <= 0:
            continue
        take = min(due, remaining)
        out.append(
            {
                "invoice": inv.id,
                "invoice_number": inv.invoice_number,
                "amount": str(take),
            }
        )
        remaining -= take
    return out


def next_invoice_number(tenant_id: int, book_number: int = 0) -> str:
    """Thin wrapper حول next_document_number() — N8-T4.

    book_number=0 → manual (any number accepted), generate with tenant prefix.
    book_number>0 → use book prefix for isolated per-book sequence.
    """
    from accounting.services import next_document_number

    if book_number == 0:
        prefix = f"SI-{tenant_id}-"
        seq = next_document_number(tenant_id, 'sales_invoice', book_number=0)
        return f"{prefix}{seq}"
    else:
        prefix = f"SI-{tenant_id}-B{book_number}-"
        seq = next_document_number(tenant_id, 'sales_invoice', book_number=book_number)
        return f"{prefix}{seq}"


def preview_next_invoice_number(tenant_id: int, book_number: int = 0) -> str:
    """Gets the next invoice number for preview without incrementing/persisting it."""
    from tenants.models import TenantBook

    book = TenantBook.objects.filter(
        tenant_id=tenant_id,
        document_type='sales_invoice',
        book_number=book_number
    ).first()

    next_num = (book.last_used_number + 1) if book else 1

    if book_number == 0:
        prefix = f"SI-{tenant_id}-"
    else:
        prefix = f"SI-{tenant_id}-B{book_number}-"

    return f"{prefix}{next_num}"


def convert_quotation_to_invoice(quotation, user=None):
    """إنشاء SalesInvoice من SalesQuotation (T4-01).

    idempotent: عرض بـ status='converted' و invoice != None يُرفض.
    """
    from .models import SalesInvoice, SalesInvoiceLine, SalesQuotation
    from .serializers import SalesInvoiceSerializer

    if quotation.status == SalesQuotation.STATUS_CONVERTED and quotation.invoice_id:
        raise ValueError(
            f"عرض السعر {quotation.quotation_number} محوّل بالفعل إلى فاتورة "
            f"#{quotation.invoice.invoice_number}."
        )

    if quotation.status not in (SalesQuotation.STATUS_ACCEPTED, SalesQuotation.STATUS_DRAFT):
        raise ValueError(
            f"لا يمكن تحويل عرض بسالة '{quotation.status}' إلى فاتورة. "
            f"الحالات المقبولة: مسودة أو مقبول."
        )

    tenant = quotation.tenant
    invoice_number = next_invoice_number(tenant.TenantID)

    lines_data = []
    for ln in quotation.lines.all():
        lines_data.append({
            "product": ln.product_id,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "line_discount": ln.line_discount,
            "tax_rate": ln.tax_rate_id,
        })

    inv_data = {
        "tenant": tenant,
        "invoice_number": invoice_number,
        "customer": quotation.customer,
        "invoice_date": quotation.quotation_date,
        "currency": quotation.currency,
        "exchange_rate": quotation.exchange_rate,
        "invoice_type": "credit",
        "lines": lines_data,
    }

    inv_ser = SalesInvoiceSerializer(data=inv_data)
    if not inv_ser.is_valid():
        raise ValueError(f"بيانات الفاتورة غير صالحة: {inv_ser.errors}")

    with transaction.atomic():
        invoice = inv_ser.save()
        quotation.status = SalesQuotation.STATUS_CONVERTED
        quotation.invoice = invoice
        quotation.save(update_fields=["status", "invoice"])

    return invoice


# ─────────────────────────────────────────────────────────────────────────
# M4-T4 — Credit / Debit notes posting
# ─────────────────────────────────────────────────────────────────────────

def next_credit_debit_note_number(tenant_id: int, note_type: str) -> str:
    """Thin wrapper حول next_document_number() — N8-T4.

    Prefix: `CN-` for credit, `DN-` for debit.
    """
    from accounting.services import next_document_number

    doc_type = 'credit_note' if note_type == CreditDebitNote.TYPE_CREDIT else 'debit_note'
    prefix = "CN" if note_type == CreditDebitNote.TYPE_CREDIT else "DN"
    seq = next_document_number(tenant_id, doc_type)
    return f"{prefix}-{seq:04d}"


def post_credit_debit_note(note: CreditDebitNote, *, user=None) -> CreditDebitNote:
    """Post a credit/debit note via the canonical `post_journal()`.

    Account resolution (in priority order):
      • Revenue: related_invoice.revenue_account → SalesSettings default → first Revenue account.
      • AR:      related_invoice.accounts_receivable_account → customer.linked_account
                 → customer.group.account_receivable → SalesSettings default.

    Journal lines (both note types balance Dr=Cr=note.amount):
      • Credit note: Dr Revenue (reverse sale) / Cr AR (release receivable).
      • Debit  note: Dr AR (extra receivable) / Cr Revenue (extra sale).

    Idempotent via `post_journal()`'s `(reference_type, reference_id)` lock.
    """
    if note.status == CreditDebitNote.STATUS_POSTED:
        raise ValidationError("الإشعار مرحَّل مسبقاً.")
    if note.status == CreditDebitNote.STATUS_CANCELLED:
        raise ValidationError("لا يمكن ترحيل إشعار ملغي.")
    amt = Decimal(str(note.amount or 0)).quantize(DEC)
    if amt <= 0:
        raise ValidationError("مبلغ الإشعار يجب أن يكون أكبر من صفر.")

    # ── Resolve revenue account ─────────────────────────────────────────
    revenue_account_id = None
    if note.related_invoice_id and note.related_invoice.revenue_account_id:
        revenue_account_id = note.related_invoice.revenue_account_id
    if not revenue_account_id:
        revenue_account_id = _default_revenue_account(note.tenant_id).id

    # ── Resolve AR account (mirror `_resolve_ar_account` semantics) ────
    ar_account_id = None
    if note.related_invoice_id and note.related_invoice.accounts_receivable_account_id:
        ar_account_id = note.related_invoice.accounts_receivable_account_id
    if not ar_account_id:
        cust: Partner = note.customer
        if cust.linked_account_id:
            ar_account_id = cust.linked_account_id
        elif cust.group_id:
            g = PartnerGroup.objects.filter(pk=cust.group_id).first()
            if g and g.account_receivable_id:
                ar_account_id = g.account_receivable_id
        if not ar_account_id:
            ss = SalesSettings.objects.filter(tenant_id=note.tenant_id).first()
            if ss and ss.default_ar_account_id:
                ar_account_id = ss.default_ar_account_id
    if not ar_account_id:
        raise ValidationError(
            "لا يوجد حساب ذمم: عيّن حساباً مرتبطاً بالعميل أو في إعدادات المبيعات."
        )

    # ── Build journal lines per note type ──────────────────────────────
    if note.note_type == CreditDebitNote.TYPE_CREDIT:
        dr_acc, cr_acc = revenue_account_id, ar_account_id
        dr_desc, cr_desc = "تخفيض إيراد", "إشعار دائن للعميل"
    else:  # debit
        dr_acc, cr_acc = ar_account_id, revenue_account_id
        dr_desc, cr_desc = "إشعار مدين للعميل", "زيادة إيراد"

    journal_lines = [
        {
            "account": dr_acc,
            "partner": note.customer_id if dr_acc == ar_account_id else None,
            "debit": amt,
            "credit": Decimal("0"),
            "description": dr_desc,
        },
        {
            "account": cr_acc,
            "partner": note.customer_id if cr_acc == ar_account_id else None,
            "debit": Decimal("0"),
            "credit": amt,
            "description": cr_desc,
        },
    ]

    # ── Currency: inherit from related invoice if any, else first tenant currency
    currency = None
    exchange_rate = Decimal("1")
    if note.related_invoice_id:
        currency = note.related_invoice.currency
        exchange_rate = Decimal(str(note.related_invoice.exchange_rate or 1))

    with transaction.atomic():
        jh = post_journal(
            tenant_id=note.tenant_id,
            transaction_date=note.note_date,
            reference_type="CREDIT_DEBIT_NOTE",
            reference_id=note.id,
            description=f"إشعار {note.get_note_type_display()} — {note.note_number}",
            lines_data=journal_lines,
            currency=currency,
            exchange_rate=exchange_rate,
            user=user,
        )
        note.journal = jh
        note.status = CreditDebitNote.STATUS_POSTED
        note.save(update_fields=["journal", "status"])

        create_audit_log(
            tenant=note.tenant,
            user=user,
            action="POST",
            model_name="CreditDebitNote",
            object_id=note.id,
            change_details=f"Posted {note.get_note_type_display()} — journal={jh.id}",
        )

    return note


# ── N8-T12: Supplier Payment ──────────────────────────────────

def post_supplier_payment(payment: 'SupplierPayment', *, user=None) -> 'SupplierPayment':
    """ترحيل سند صرف لمورد: Dr AP / Cr Cash."""
    from sales.models import SupplierPayment as SP
    if payment.is_posted:
        raise ValidationError("سند الصرف مرحّل مسبقاً.")
    if payment.partner.tenant_id != payment.tenant_id:
        raise ValidationError("المورد لا يتبع نفس الشركة.")
    validate_fiscal_period(payment.tenant_id, payment.payment_date)

    from logistics.services import _resolve_ap_account
    ap_account = _resolve_ap_account(payment.partner)

    with transaction.atomic():
        jh = post_journal(
            tenant_id=payment.tenant_id,
            transaction_date=payment.payment_date,
            reference_type='SUPPLIER_PAYMENT',
            reference_id=payment.id,
            description=f"سند صرف — {payment.partner.name} ({payment.amount})",
            lines_data=[
                {
                    "account": ap_account.id,
                    "partner": payment.partner_id,
                    "debit": Decimal(str(payment.amount)),
                    "credit": Decimal("0"),
                    "description": f"دفع مورد — {payment.partner.name}",
                },
                {
                    "account": payment.cash_or_bank_account_id,
                    "partner": payment.partner_id,
                    "debit": Decimal("0"),
                    "credit": Decimal(str(payment.amount)),
                    "description": f"من الصندوق — {payment.partner.name}",
                },
            ],
            currency=payment.currency,
            exchange_rate=payment.exchange_rate,
            user=user,
        )
        payment.journal = jh
        payment.is_posted = True
        payment.save(update_fields=["journal", "is_posted"])
        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="POST",
            model_name="SupplierPayment",
            object_id=payment.id,
            change_details=f"Posted supplier payment journal={jh.id}",
        )
    return payment


# ── N8-T13: VatStatement builder ─────────────────────────────

def build_vat_statement(
    tenant_id: int,
    period_from,
    period_to,
    *,
    user=None,
):
    """يُولّد كشف ض.ق.م دوري — يَجمع الفواتير المرحَّلة في الفترة بـvat_statement IS NULL.

    P-H-6: مَلفوف بـtransaction.atomic() + select_for_update على الفواتير المؤهَّلة
    لمنع سباق مُولِّدَيْن مُتزامنَيْن. كما يَرفض الفترات المتداخلة مع كشوف موجودة.
    """
    from sales.models import VatStatement
    from accounting.services import next_document_number

    with transaction.atomic():
        # P-H-6: reject overlapping period windows for the same tenant.
        # Combined with the DB-level UniqueConstraint on
        # (tenant, period_from, period_to) this catches both exact-match
        # races and accidental overlap.
        overlap = VatStatement.objects.filter(
            tenant_id=tenant_id,
            period_from__lte=period_to,
            period_to__gte=period_from,
        ).first()
        if overlap:
            raise ValidationError(
                f"يوجد كشف ضريبة يُغطّي هذه الفترة بالفعل: «{overlap.statement_number}» "
                f"({overlap.period_from} → {overlap.period_to})."
            )

        # Lock the candidate invoices so a concurrent generator cannot
        # claim the same rows under a different statement.
        invoices = list(
            SalesInvoice.objects.select_for_update().filter(
                tenant_id=tenant_id,
                status=SalesInvoice.STATUS_POSTED,
                invoice_date__gte=period_from,
                invoice_date__lte=period_to,
                vat_statement__isnull=True,
            ).select_related('currency')
        )

        total_sales_vat = Decimal('0.00')
        total_purchase_vat = Decimal('0.00')

        for inv in invoices:
            if inv.invoice_kind in (SalesInvoice.INVOICE_KIND_SALE, SalesInvoice.INVOICE_KIND_SALE_RETURN):
                total_sales_vat += Decimal(str(inv.tax_amount or 0))
            else:
                total_purchase_vat += Decimal(str(inv.tax_amount or 0))

        net_vat = (total_sales_vat - total_purchase_vat).quantize(Decimal('0.01'))
        stmt_no = f"VAT-{next_document_number(tenant_id, 'vat_statement')}"

        stmt = VatStatement.objects.create(
            tenant_id=tenant_id,
            statement_number=stmt_no,
            period_from=period_from,
            period_to=period_to,
            total_sales_vat=total_sales_vat.quantize(Decimal('0.01')),
            total_purchase_vat=total_purchase_vat.quantize(Decimal('0.01')),
            net_vat=net_vat,
            created_by=user,
        )

        # Re-issue the update by pk to use the lock acquired above.
        invoice_ids = [inv.pk for inv in invoices]
        updated = SalesInvoice.objects.filter(pk__in=invoice_ids).update(vat_statement=stmt)

        create_audit_log(
            tenant=stmt.tenant,
            user=user,
            action="CREATE",
            model_name="VatStatement",
            object_id=stmt.id,
            change_details=f"Created VAT statement {stmt_no}: {updated} invoices linked, net={net_vat}",
        )
        return stmt

