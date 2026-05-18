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
    """يحدّث حقول الأسطر والفاتورة (بدون حفظ في قاعدة البيانات)."""
    if lines is None:
        lines = list(invoice.lines.select_related("tax_rate"))
    sub = Decimal("0.00")
    pairs: list[tuple[SalesInvoiceLine, Decimal]] = []
    for line in lines:
        n = line_net(line)
        pairs.append((line, n))
        sub += n

    disc = Decimal(str(invoice.invoice_discount or 0))
    if sub > 0 and disc > sub:
        disc = sub
    ratio = ((sub - disc) / sub) if sub > 0 else Decimal(0)
    excl_after = (sub - disc).quantize(DEC) if sub > 0 else Decimal("0.00")

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
    # للمنتجات: ممكن تُثبَّت على الفاتورة. للخدمات: نفضّل إعداد الخدمة دائمًا.
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


def post_sales_invoice(
    invoice: SalesInvoice,
    *,
    user=None,
) -> SalesInvoice:
    """ترحيل فاتورة: قيد محاسبي + (اختياري) خصم مخزون."""
    if invoice.status == SalesInvoice.STATUS_POSTED:
        raise ValidationError("الفاتورة مرحّلة مسبقاً.")
    if invoice.status == SalesInvoice.STATUS_CANCELLED:
        raise ValidationError("لا يمكن ترحيل فاتورة ملغاة.")

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

        if invoice.invoice_type == SalesInvoice.INVOICE_CASH:
            cash = invoice.cash_or_bank_account
            if not cash:
                raise ValidationError("فواتير النقدي تتطلب حساب صندوق/بنك (cash_or_bank_account).")
            journal_lines.append(
                {
                    "account": cash.id,
                    "partner": invoice.customer_id,
                    "debit": grand,
                    "credit": Decimal("0"),
                    "description": f"تحصيل نقدي — {invoice.invoice_number}",
                }
            )
        else:
            ar = _resolve_ar_account(invoice)
            journal_lines.append(
                {
                    "account": ar.id,
                    "partner": invoice.customer_id,
                    "debit": grand,
                    "credit": Decimal("0"),
                    "description": f"ذمم — {invoice.invoice_number}",
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
        desc_parts = []
        if tenant_name:
            desc_parts.append(f"[{tenant_name}]")
        desc_parts.append(f"فاتورة مبيعات {invoice.invoice_number}")
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
        invoice.save(update_fields=["journal", "status"])

        if invoice.stock_on_post:
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

        if payment_currency_id and alloc_conversions:
            first_inv_curr_id = alloc_conversions[0][0].invoice.currency_id
            if payment_currency_id != first_inv_curr_id:
                total_in_pay_curr, _ = convert_amount(
                    amount=total_alloc_in_inv_curr,
                    from_currency_id=first_inv_curr_id,
                    to_currency_id=payment_currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
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


def next_invoice_number(tenant_id: int) -> str:
    """يقفل آخر فاتورة (select_for_update) لتقليل تصادم الأرقام تحت حمل متزامن.

    ملاحظة: الإدراج الفعلي للفاتورة يتم في السيريالايزر، لذا القفل هنا
    يقلّل التصادم عند استدعائه ضمن معاملة المنشئ ولا يلغيه تماماً؛ الضمان
    القاطع يحتاج تسلسل DB أو قيد فريد + إعادة محاولة (مرحلة 4 / I4-01).
    """
    prefix = f"SI-{tenant_id}-"
    with transaction.atomic():
        last = (
            SalesInvoice.objects
            .filter(tenant_id=tenant_id, invoice_number__startswith=prefix)
            .select_for_update()
            .order_by("-id")
            .first()
        )
        if not last:
            return f"{prefix}1"
        try:
            n = int(last.invoice_number.replace(prefix, ""))
        except ValueError:
            n = last.id
        return f"{prefix}{n + 1}"


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

