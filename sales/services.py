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
    DeliveryOrderLine,
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


def resolve_default_account(
    tenant_id, code_prefixes=None, acc_type=None, name_kw=None, *, allow_any_of_type=True
):
    """أفضل حساب مطابق من شجرة الشركة: الكود، ثم النوع+الاسم، ثم أول حساب من النوع.

    `allow_any_of_type=False` يمنع الرجوع الأعمى لأول حساب من النوع (قد يكون
    حساباً رئيسياً لا يصلح للترحيل) — يُستخدم عند تعبئة الافتراضيات تلقائياً.
    """
    qs = Account.objects.filter(tenant_id=tenant_id, is_active=True)
    for cp in (code_prefixes or []):
        hit = qs.filter(code__startswith=cp).order_by("code").first()
        if hit:
            return hit
    if acc_type:
        typed = qs.filter(account_type=acc_type)
        if name_kw:
            hit = typed.filter(name__icontains=name_kw).order_by("code").first()
            if hit:
                return hit
        if allow_any_of_type:
            return typed.order_by("code").first()
    return None


def _fill_missing_stock_accounts(settings_obj: SalesSettings, tenant_id) -> list[str]:
    """يملأ حسابَي تكلفة المبيعات والمخزون إن كانا فارغين — يعيد الحقول المعدّلة.

    تركهما NULL كان يوقف ترحيل أي فاتورة مبيعات في شركة جديدة برسالة «عيّن حساب
    تكلفة المبيعات والمخزون…»، مع أن شجرة الحسابات القياسية تحوي الحسابين أصلاً.
    """
    filled: list[str] = []
    if settings_obj.default_cogs_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["5101", "51"], "Expense", "تكلفة", allow_any_of_type=False
        )
        if acc:
            settings_obj.default_cogs_account = acc
            filled.append("default_cogs_account")
    if settings_obj.default_inventory_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["1104"], "Asset", "مخزون", allow_any_of_type=False
        )
        if acc:
            settings_obj.default_inventory_account = acc
            filled.append("default_inventory_account")
    return filled


def get_or_create_sales_settings(tenant) -> SalesSettings:
    """يُعيد (أو يُنشئ) إعدادات المبيعات للشركة، ويضبط قيمًا افتراضية ذكية."""
    tenant_id = getattr(tenant, "TenantID", tenant)
    settings_obj = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if settings_obj:
        updates: list[str] = []
        # تأكد أن العميل الافتراضي موجود
        if settings_obj.default_customer_id is None:
            settings_obj.default_customer = get_or_create_default_customer(tenant_id)
            updates.append("default_customer")
        updates += _fill_missing_stock_accounts(settings_obj, tenant_id)
        if updates:
            settings_obj.save(update_fields=updates)
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
    filled = _fill_missing_stock_accounts(settings_obj, tenant_id)
    if filled:
        settings_obj.save(update_fields=filled)
    return settings_obj


def dormant_customers(*, tenant_id: int, days: int | None = None) -> list[dict]:
    """T-DORMANT: العملاء الذين توقّفوا عن الشراء منذ `days` يوماً أو أكثر.

    «حركة العميل» تُشتقّ من فواتير البيع **المرحّلة** وحدها (لا مسودات ولا مراجع
    بيع) — لا مخزن حركات موازٍ، فالنتيجة تتصالح دائماً مع دفتر المبيعات.
    من لم يشترِ قطّ لا يُعدّ «مختفياً» (لم يكن حاضراً أصلاً)، ومن انتهى تعامله
    (`end_of_dealing_date` حلّ) مستثنى — توقّفه معروف لا مفاجئ.
    `days=None` ⇒ العتبة من إعدادات المبيعات
    (`dormant_customer_days`)، و0 يعطّل التنبيه فتُعاد قائمة فارغة.

    يُعاد [{partner_id, partner_name, last_sale_date, last_invoice_number,
    days_since}] مرتّباً بالأطول صمتاً أولاً — يستهلكه مولّد إشعارات الموقع.
    """
    from datetime import date, timedelta

    from django.db.models import Max

    if days is None:
        days = get_or_create_sales_settings(tenant_id).dormant_customer_days
    days = int(days or 0)
    if days <= 0:
        logger.info("dormant_customers tenant=%s disabled (days=0)", tenant_id)
        return []

    today = date.today()
    cutoff = today - timedelta(days=days)
    latest = (
        SalesInvoice.objects.filter(
            tenant_id=tenant_id,
            status=SalesInvoice.STATUS_POSTED,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        )
        .exclude(customer__end_of_dealing_date__lte=today)
        .values("customer_id", "customer__name")
        .annotate(last_sale_date=Max("invoice_date"))
        .filter(last_sale_date__lte=cutoff)
        .order_by("last_sale_date")
    )

    rows: list[dict] = []
    for entry in latest:
        last_date = entry["last_sale_date"]
        # رقم آخر فاتورة — للعرض داخل الإشعار (لا يُستعلم إلا للمختفين فعلاً).
        last_number = (
            SalesInvoice.objects.filter(
                tenant_id=tenant_id,
                customer_id=entry["customer_id"],
                status=SalesInvoice.STATUS_POSTED,
                invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
                invoice_date=last_date,
            )
            .order_by("-id")
            .values_list("invoice_number", flat=True)
            .first()
        )
        rows.append(
            {
                "partner_id": entry["customer_id"],
                "partner_name": entry["customer__name"],
                "last_sale_date": last_date.isoformat(),
                "last_invoice_number": last_number,
                "days_since": (today - last_date).days,
            }
        )

    logger.info(
        "dormant_customers tenant=%s days=%s -> %s customers",
        tenant_id, days, len(rows),
    )
    return rows


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

    # task11 R2-A1: الخصم النسبي يُوزَّع على الأسطر مثل الخصم المقطوع.
    # سابقاً كان يُطبّق على الترويسة فقط ⇒ الأسطر (وقيد الإيراد) أعلى من
    # الإجمالي ⇒ قيد غير متوازن يفشل ترحيله، والضريبة محسوبة قبل الخصم
    # النسبي (قاعدة VAT خاطئة). الآن: نسبة موحّدة = بعد الخصمين معاً،
    # والضريبة تُحسب بعد كل الخصومات.
    pct = Decimal(str(getattr(invoice, "discount_percent", 0) or 0))
    if pct < 0:
        pct = Decimal("0")
    if pct > 100:
        pct = Decimal("100")
    effective = (sub - disc) * (Decimal("100") - pct) / Decimal("100") if sub > 0 else Decimal("0")
    ratio = (effective / sub) if sub > 0 else Decimal(0)

    excl_sum = Decimal("0.00")
    tax_sum = Decimal("0.00")
    for line, orig_n in pairs:
        adj_net = (orig_n * ratio).quantize(DEC) if sub > 0 else Decimal("0.00")
        line.line_total_excl_tax = adj_net
        excl_sum += adj_net
        if line.tax_rate_id and line.tax_rate:
            t = (adj_net * Decimal(str(line.tax_rate.rate)) / Decimal("100")).quantize(DEC)
        else:
            t = Decimal("0.00")
        line.line_tax_amount = t
        tax_sum += t

    # الترويسة = مجموع الأسطر بالقرش — يضمن توازن القيد دائماً بلا انحراف تقريب
    invoice.subtotal_excl_tax = excl_sum.quantize(DEC)
    invoice.tax_amount = tax_sum.quantize(DEC)
    invoice.grand_total = (invoice.subtotal_excl_tax + invoice.tax_amount).quantize(DEC)


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


def resolve_service_revenue_account(tenant_id: int) -> Account:
    """T-SERVICELINE: حساب «إيرادات الخدمات» — يُطابَق من الشجرة أو يُنشأ ويُثبَّت.

    كان بيع الخدمة يرتدّ إلى حساب إيراد **البضائع** متى كان الإعداد فارغاً (وهو
    حاله في كل شركة لم تُضبط يدوياً)، فيضيع الفصل الذي هو غرض بند الخدمة أصلاً.
    التثبيت على الإعدادات يمنع إنشاء حساب ثانٍ في المرة التالية.
    """
    ss = get_or_create_sales_settings(tenant_id)
    if ss.default_revenue_account_service_id:
        return ss.default_revenue_account_service

    account = resolve_default_account(
        tenant_id, ["4102", "42"], "Revenue", "خدمات", allow_any_of_type=False
    )
    if account is None:
        parent = (
            Account.objects.filter(
                tenant_id=tenant_id, account_type="Revenue", is_active=True,
            )
            .order_by("code")
            .first()
        )
        # get_or_create على (الشركة، الكود): كودٌ معطَّل بنفس الرقم موجود أصلاً
        # يُعاد استعماله بدل أن يصطدم بقيد التفرّد.
        account, created = Account.objects.get_or_create(
            tenant_id=tenant_id,
            code="4102",
            defaults={
                "name": "إيرادات الخدمات",
                "account_type": "Revenue",
                "is_active": True,
                "parent": parent.parent if parent else None,
            },
        )
        if created:
            logger.info(
                "sales.service_revenue_account.created tenant=%s account=%s",
                tenant_id, account.pk,
            )
    ss.default_revenue_account_service = account
    ss.save(update_fields=["default_revenue_account_service"])
    return account


def _default_revenue_account(tenant_id: int, *, is_service: bool = False) -> Account:
    """يفضّل الحساب من إعدادات المبيعات (منتج/خدمة)، ثم أول حساب إيرادات نشط."""
    # T-SERVICELINE: الخدمة لها حسابها دائماً — لا ارتداد إلى إيراد البضائع.
    if is_service:
        return resolve_service_revenue_account(tenant_id)
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
    quantities: dict[int, Decimal] | None = None,
) -> list[dict]:
    """Dr COGS / Cr Inventory — مبالغ من متوسط التكلفة قبل الصرف (نفس منطق حركة المخزون).

    quantities: كمية بديلة لكل سطر (بمعرّف السطر) — يستعملها التسليم الجزئي كي
    تكون التكلفة على المُسلَّم فعلاً لا على كامل السطر. None = كامل الكمية.
    """
    # يعبّئ الحسابين الافتراضيين إن كانا فارغين بدل إسقاط الترحيل
    ss = get_or_create_sales_settings(invoice.tenant_id)
    fb_cogs = ss.default_cogs_account_id
    fb_inv = ss.default_inventory_account_id

    pair_totals: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for line in lines:
        p = products_by_id[line.product_id]
        if getattr(p, 'is_service', False):
            continue
        qty = Decimal(str(
            line.quantity if quantities is None else quantities.get(line.id, 0)
        ))
        if qty <= 0:
            continue
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


def _loss_lines(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    products_by_id: dict[int, Product],
) -> list[tuple]:
    """W1: الأسطر المُباعة بخسارة — صافي إيراد السطر أقل من تكلفته.

    «صافي إيراد السطر» = `line.line_total_excl_tax` (بعد خصم السطر + توزيع خصم الفاتورة
    والنسبة، وتعديل السعر شامل الضريبة) — نفس أساس `invoice_profits` وقيد COGS. التكلفة =
    الكمية × متوسط التكلفة (WAC، مصدر حقيقة واحد). يفترض استدعاء
    `recalculate_invoice_amounts` مسبقاً (يملأ `line_total_excl_tax`). يعيد
    قائمة (line, product, revenue, cost) لكل سطر خاسر.
    """
    offenders: list[tuple] = []
    for line in lines:
        p = products_by_id.get(line.product_id)
        if p is None or getattr(p, "is_service", False):
            continue
        cost = (Decimal(str(line.quantity)) * Decimal(str(p.avg_cost or 0))).quantize(DEC)
        revenue = Decimal(str(line.line_total_excl_tax or 0)).quantize(DEC)
        if (revenue - cost) < 0:
            offenders.append((line, p, revenue, cost))
    return offenders


def guard_loss_invoice(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    products_by_id: dict[int, Product],
) -> None:
    """W1: يمنع حفظ/ترحيل فاتورة بيع فيها **أي سطر** يُباع بخسارة (صافي البيع أقل من
    متوسط التكلفة) عند تفعيل `SalesSettings.block_loss_invoices` — حتى لو كان إجمالي
    الفاتورة رابحاً. المراجيع مُعفاة. المفتاح OFF = السماح بحفظ فاتورة بخسارة (تجاوز
    الحارس). يسمّي الأسطر المخالفة بالعربية (اسم الصنف + التكلفة مقابل صافي البيع).
    """
    kind = invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE
    if kind != SalesInvoice.INVOICE_KIND_SALE:
        return
    ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
    if not (ss and ss.block_loss_invoices):
        return
    offenders = _loss_lines(invoice, lines, products_by_id)
    if not offenders:
        return
    detail = "؛ ".join(
        f"«{p.name_ar or p.name_en or p.sku}» (التكلفة {cost} أعلى من صافي البيع {revenue})"
        for (_line, p, revenue, cost) in offenders
    )
    logger.warning(
        "Blocked loss invoice %s — %d loss line(s): %s",
        invoice.invoice_number, len(offenders), detail,
    )
    raise ValidationError(
        f"لا يُسمح بحفظ فاتورة تحتوي بنداً يُباع بخسارة: {detail}. "
        "عدّل الأسعار أو فعّل «السماح بحفظ فاتورة بخسارة» من إعدادات المبيعات."
    )


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

def resolve_cheques_under_collection_account(tenant_id: int) -> Account:
    """حساب «شيكات برسم التحصيل» للشركة — مصدر واحد لقيود الشيكات الواردة.

    يستهلكه ترحيل الفاتورة (شيكات مرفقة) وترحيل سند القبض (شيكات داخل السند)،
    فلا تختلف وجهة الشيك باختلاف الشاشة التي أُدخِل منها.

    الاحتياط لا يُخمّن بالكود وحده: في الشجرة الاحترافية 1106 =
    «دفعات مقدمة للموردين»، فقبولُه بالكود كان يُهبِط أموال الشيكات في حساب
    لا علاقة له بها. الشرط: اسم الحساب يذكر «شيكات» — وإلا فخطأ صريح.
    """
    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    uc_acc = ss.default_cheques_under_collection_account if ss else None
    if not uc_acc:
        uc_acc = (
            Account.objects.filter(
                tenant_id=tenant_id,
                account_type="Asset",
                is_active=True,
                name__icontains="شيكات",
            )
            .order_by("code")
            .first()
        )
    if not uc_acc:
        raise ValidationError(
            "توجد شيكات واردة لكن لا يوجد حساب «شيكات برسم التحصيل». "
            "عيّن `default_cheques_under_collection_account` في إعدادات "
            "المبيعات، أو أنشئ حساب Asset باسم يتضمّن «شيكات»."
        )
    return uc_acc


def resolve_cheques_payable_account(tenant_id: int) -> Account:
    """حساب «شيكات برسم الدفع» — مرآة حساب الشيكات الواردة للجانب الدائن.

    الشيك الصادر ليس نقداً خرج من الصندوق بل التزام حتى يُصرف، فيُدائَن حساب
    التزام مستقل. لا إعداد له بعد (مسجّل في النواقص) — يُطابَق بالاسم، وبلا
    حساب مطابق يُرفض الترحيل صراحةً بدل تحميل الصندوق ما لم يخرج منه.
    """
    acc = (
        Account.objects.filter(
            tenant_id=tenant_id,
            account_type="Liability",
            is_active=True,
            name__icontains="شيكات",
        )
        .order_by("code")
        .first()
    )
    if not acc:
        raise ValidationError(
            "يوجد شيك صادر لكن لا يوجد حساب «شيكات برسم الدفع». "
            "أنشئ حساب Liability باسم يتضمّن «شيكات» (مثال: «شيكات برسم الدفع»)."
        )
    return acc


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


def _auto_settle_cash_sale(invoice: SalesInvoice, *, user=None) -> None:
    """T-CASH2: البيع النقدي مدفوع فوراً — تسوية تلقائية فور الترحيل.

    يُنشئ ويُرحّل «سند قبض» (CustomerPayment) بكامل المتبقّي على فاتورة بيع
    نقدية، فيُفرّغ ذمم العميل (Dr صندوق / Cr ذمم) ويحوّله من «مدين» إلى «مسدَّد».

    هذا يُكمل تصميم Feature 2 (قيد الفاتورة لا يُسوّي النقدية إطلاقاً؛ التحصيل
    سند مستقل يظهر في كشف حساب العميل) — كانت الأتمتة غير مربوطة سابقاً فبقي
    البيع النقدي مديناً للأبد. لا يلمس قيد الفاتورة، فيبقى اختبار التوجيه الفرعي
    (`test_subledger_routing`) سليماً: التسوية قيد منفصل.

    آمن: يقتصر على فواتير **البيع النقدية** (لا المراجيع/الآجل)، ويعتمد على
    المتبقّي (grand − amount_paid) فلا يُسوّي مرتين عند إعادة الترحيل/الشيكات.
    إن غاب حساب الصندوق يُسجَّل تحذير ويُتخطّى دون كسر الترحيل.
    """
    if invoice.invoice_type != SalesInvoice.INVOICE_CASH:
        return
    if (invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE) != SalesInvoice.INVOICE_KIND_SALE:
        return
    remaining = (
        Decimal(str(invoice.grand_total or 0)) - Decimal(str(invoice.amount_paid or 0))
    ).quantize(DEC)
    if remaining <= DEC:
        return
    # حساب الصندوق: حساب الفاتورة النقدي → النقدي المرفق → افتراضي الإعدادات.
    cash_account_id = invoice.cash_or_bank_account_id or invoice.attached_cash_account_id
    if not cash_account_id:
        ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
        cash_account_id = ss.default_cash_account_id if ss else None
    if not cash_account_id:
        logger.warning(
            "Cash sale %s posted without a cash account — customer left as debtor "
            "(no auto-settlement). Set SalesSettings.default_cash_account.",
            invoice.invoice_number,
        )
        return
    payment = CustomerPayment.objects.create(
        tenant_id=invoice.tenant_id,
        partner_id=invoice.customer_id,
        payment_date=invoice.invoice_date,
        amount=remaining,
        currency_id=invoice.currency_id,
        exchange_rate=invoice.exchange_rate or Decimal("1"),
        cash_or_bank_account_id=cash_account_id,
        notes=f"تحصيل نقدي تلقائي — فاتورة {invoice.invoice_number}",
    )
    PaymentAllocation.objects.create(
        tenant_id=invoice.tenant_id,
        payment=payment,
        invoice=invoice,
        amount=remaining,
    )
    post_customer_payment(payment, user=user)
    from core.activity import log_activity
    log_activity(
        action="payment", entity_type="customer_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="سند قبض نقدي تلقائي",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    log_activity(
        action="post", entity_type="customer_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="ترحيل سند قبض نقدي تلقائي",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    logger.info(
        "Auto-settled cash sale %s via customer payment %s (amount %s).",
        invoice.invoice_number, payment.id, remaining,
    )


def post_sales_invoice(
    invoice: SalesInvoice,
    *,
    user=None,
) -> SalesInvoice:
    """ترحيل فاتورة: قيد محاسبي + (اختياري) خصم مخزون.

    N8-T11: يَدعم الآن 4 أنواع (فاتورة بيع/مرجع بيع/فاتورة شراء/مرجع شراء)
    عبر حقل `invoice_kind`. للمراجيع، تُعكس إشارات القيد والمخزون.

    T-CASH2: بعد ترحيل قيد فاتورة بيع **نقدية** تُسوَّى تلقائياً بسند قبض مستقل
    (`_auto_settle_cash_sale`) فلا يبقى العميل مديناً.
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

    # المراجيع تُخفّض الذمم لا تزيدها ⇒ لا تُخضَع لفحص حدّ الائتمان.
    if invoice.invoice_type == SalesInvoice.INVOICE_CREDIT and not is_return:
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

        # منع فاتورة الخسارة (إعداد اختياري، على مستوى السطر) — بعد قفل الأصناف والإجماليات.
        guard_loss_invoice(invoice, lines, products_by_id)

        # T-RESERVEGUARD: الكمية المحجوزة لطلبية زبون آخر ليست متاحة للبيع —
        # يُفحص بعد قفل الأصناف كي لا تسبق فاتورتان بعضهما على نفس الحجز.
        guard_reserved_stock(invoice, lines, products_by_id)

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

        # ── خصم المصدر (يُحسب مبكراً ليُخصم من التحصيل النقدي) ───────────────
        # خصم المصدر = الجزء الذي يحتجزه العميل كاستقطاع ضريبي ضد البائع
        # (Aseel «خصم مصدر»). أولوية: تجاوز الفاتورة (مبلغ ثم نسبة) ← افتراضي
        # العميل (مبلغ ثم نسبة). يُرحَّل سطره وتُخفَّض الذمم في كتلة الـ G6 أدناه.
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
        if src_disc_amt > grand:
            src_disc_amt = grand

        # ── Section B: القيد يمرّ دائماً عبر حساب ذمم العميل ──────────────────
        # حتى البيع النقدي يُقيَّد أولاً على ذمم العميل بكامل القيمة، ثم يُسوَّى
        # التحصيل (نقدي/شيكات) بحركة دائنة على نفس الحساب — كي يعكس كشف حساب
        # العميل والأعمار كل الحركات (المطلب المحاسبي للمالك). journal_lines[0]
        # هو دائماً سطر الذمم بكامل الإجمالي ليبقى مرجع تخفيض خصم المصدر ثابتاً.
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

        # ── Feature 2: قيد الفاتورة لا يُسوّي النقدية إطلاقاً ────────────────
        # قيد الفاتورة (Entry A) يدين ذمم العميل بالكامل ويدائن الإيراد/الضريبة
        # (+COGS/المخزن). تحصيل النقدية — حتى للبيع النقدي — يصبح سنداً مستقلاً
        # «وصل دفع» (CustomerPayment، Entry B: مدين النقدية / دائن ذمم العميل)
        # يُنشأ بفتح الفاتورة وإضافة وصل دفع إليها. لذا الترحيل هنا **لا يولّد**
        # أي حركة نقدية ولا يستهلك cash_or_bank_account.
        collected_cash = Decimal("0.00")

        # تسوية الشيكات عبر الذمم (مدين شيكات برسم التحصيل / دائن ذمم)
        if cheques_total > 0:
            uc_acc = resolve_cheques_under_collection_account(invoice.tenant_id)
            journal_lines.append(
                {
                    "account": uc_acc.id,
                    # شيكات برسم التحصيل أصل وليس الحساب الرقابي للذمم — بلا شريك
                    # وإلا ضُمّت إلى رصيد كشف حساب العميل فضخّمت ما يدين به.
                    "partner": None,
                    "debit": cheques_total,
                    "credit": Decimal("0"),
                    "description": f"مدفوع شيكات — {invoice.invoice_number}",
                }
            )
            journal_lines.append(
                {
                    "account": ar.id,
                    "partner": invoice.customer_id,
                    "debit": Decimal("0"),
                    "credit": cheques_total,
                    "description": f"تسوية ذمم (شيكات) — {invoice.invoice_number}",
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
        # NOTE: `src_disc_amt`/`src_disc_pct_used` are computed earlier (before
        # the AR/cash settlement block) so the cash collection can net the
        # withheld amount. Here we only emit the line + reduce the AR debit.
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
                # خصم المصدر مطالبة على مصلحة الضرائب لا على العميل — بلا شريك،
                # وإلا أُعيد المبلغُ المخصومُ من سطر الذمم إلى رصيد العميل فضخّمه.
                "partner": None,
                "debit": src_disc_amt,
                "credit": Decimal("0"),
                "description": f"خصم مصدر{desc_pct} — {invoice.invoice_number}",
            })
            # REDUCE the AR debit line by src_disc_amt — customer actually owes
            # `grand − src_disc_amt`; the rest is now a claim on the tax
            # authority. Journal remains balanced because we added a Dr of the
            # same amount on the source-discount account. journal_lines[0] is
            # always the full-grand AR line (built above for every invoice type).
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
            branch_id=invoice.branch_id,
        )

        invoice.journal = jh
        invoice.status = SalesInvoice.STATUS_POSTED
        # M2-T3: amount_paid reflects what came in with the invoice itself.
        # Section B: includes the cash collected on a cash invoice (settled via
        # AR) + attached cheques. Subsequent CustomerPayments add on top via
        # post_customer_payment's allocation logic.
        settled_total = (collected_cash + cheques_total).quantize(DEC)
        if settled_total > 0:
            invoice.amount_paid = (
                Decimal(str(invoice.amount_paid or 0)) + settled_total
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
                        branch=invoice.branch,
                    )
            else:
                _post_stock_out_for_invoice(invoice, lines, user=user)
            # البضاعة خرجت مع الترحيل ⇒ الفاتورة مسلَّمة بالكامل، وتُوثَّق
            # بإرسالية تلقائية بكامل الكمية (مرآة إرسالية الشراء التلقائية).
            for line in lines:
                if getattr(line.product, "is_service", False):
                    continue
                line.delivered_quantity = line.quantity
            SalesInvoiceLine.objects.bulk_update(lines, ["delivered_quantity"])
            _create_auto_delivery_document(invoice, lines)
        sync_invoice_delivery_status(invoice, lines)

        create_audit_log(
            tenant=invoice.tenant,
            user=user,
            action="POST",
            model_name="SalesInvoice",
            object_id=invoice.id,
            change_details=f"Posted sales invoice {invoice.invoice_number} journal={jh.id}",
        )

        # T-CASH2: البيع النقدي = مدفوع فوراً ⇒ سوِّه بسند قبض مستقل داخل نفس
        # المعاملة (ذرّياً مع الترحيل) فلا يبقى العميل مديناً.
        _auto_settle_cash_sale(invoice, user=user)

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
                branch=invoice.branch,
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
                branch=invoice.branch,
            )
        except Exception as e:
            raise ValidationError(f"خطأ في إذن الصرف لصنف {line.product.sku}: {e}")


def _create_auto_delivery_document(
    invoice: SalesInvoice, lines: list[SalesInvoiceLine],
) -> DeliveryOrder | None:
    """إرسالية تلقائية بكامل الكمية للفاتورة التي تخصم المخزون عند الترحيل.

    توثيق فقط — لا حركة مخزون ولا قيد هنا (الترحيل أنجزهما)، فلا ازدواج.
    """
    goods = [l for l in lines if not getattr(l.product, "is_service", False)]
    if not goods:
        return None
    from django.utils import timezone

    delivery = DeliveryOrder.objects.create(
        tenant=invoice.tenant,
        branch=invoice.branch,
        delivery_number=next_delivery_number(invoice.tenant_id, invoice.branch),
        delivery_date=invoice.invoice_date,
        invoice=invoice,
        auto_created=True,
        status=DeliveryOrder.STATUS_DELIVERED,
        delivered_at=timezone.now(),
        notes="إرسالية تلقائية مع ترحيل الفاتورة",
    )
    for line in goods:
        DeliveryOrderLine.objects.create(
            tenant=invoice.tenant,
            delivery=delivery,
            invoice_line=line,
            product=line.product,
            quantity=line.quantity,
        )
    return delivery


def _resolve_delivery_warehouse(tenant_id: int, raw: dict):
    """مستودع سطر الإرسالية — يُتحقَّق من تبعيته للشركة (مرآة استلام الشراء).

    اختياري خلافاً للشراء: حركة الخروج عند ترحيل الفاتورة بلا مستودع أصلاً، وشركة
    بلا مستودعات يجب أن تبقى قادرة على التسليم. المُرسَل يُعتمد ويُثبَّت على السطر.
    """
    from inventory.models import Warehouse

    wh_id = raw.get("warehouse_id")
    if not wh_id:
        return None
    wh = Warehouse.objects.filter(pk=wh_id, tenant_id=tenant_id).first()
    if wh is None:
        raise ValidationError(f"المستودع المحدد ({wh_id}) غير موجود في هذه الشركة.")
    return wh


def _delivery_movement_type(invoice: SalesInvoice) -> str:
    """اتجاه حركة المخزون عند التسليم — نفس قاعدة الترحيل (نوع الفاتورة يحكمه)."""
    kind = invoice.invoice_kind
    if kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
        return "RETURN_IN"
    if kind == SalesInvoice.INVOICE_KIND_PURCHASE_RETURN:
        return "RETURN_OUT"
    return "OUT"


def sync_invoice_delivery_status(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine] | None = None,
    *,
    save: bool = True,
) -> str:
    """يشتقّ حالة التسليم من الكميات المسلَّمة — مصدر حقيقة واحد لا حقل يدوي.

    بنود الخدمات لا تُسلَّم مادياً فتُستثنى؛ فاتورة خدمات صرفة تُعدّ مسلَّمة.
    """
    if lines is None:
        lines = list(invoice.lines.select_related("product"))
    goods = [l for l in lines if not getattr(l.product, "is_service", False)]
    if not goods:
        new_status = SalesInvoice.DELIVERY_FULL
    elif all(
        Decimal(str(l.delivered_quantity or 0)) >= Decimal(str(l.quantity or 0))
        for l in goods
    ):
        new_status = SalesInvoice.DELIVERY_FULL
    elif any(Decimal(str(l.delivered_quantity or 0)) > 0 for l in goods):
        new_status = SalesInvoice.DELIVERY_PARTIAL
    else:
        new_status = SalesInvoice.DELIVERY_NOT
    if save and invoice.delivery_status != new_status:
        invoice.delivery_status = new_status
        invoice.save(update_fields=["delivery_status"])
    else:
        invoice.delivery_status = new_status
    return new_status


def next_delivery_number(tenant_id: int, branch=None) -> str:
    """رقم إرسالية البيع التالي — عبر دفاتر الترقيم المركزية (DN-0001)."""
    from accounting.services import next_document_number

    seq = next_document_number(
        tenant_id, "delivery_note", branch_id=branch.id if branch else None,
    )
    return f"DN-{seq:04d}"


def deliver_invoice_lines(
    invoice: SalesInvoice,
    *,
    lines,
    user=None,
    notes: str = "",
    delivery: DeliveryOrder | None = None,
    delivery_date=None,
) -> DeliveryOrder:
    """تسليم بنود فاتورة بيع للعميل (إرسالية) — خصم المخزون وقيد التكلفة للمُسلَّم فقط.

    lines: قائمة [{'line_id': int, 'quantity': Decimal, 'warehouse_id': int|None}].
    الكمية أكبر من المتبقي مرفوضة، فإعادة الإرسال لا تُكرّر الخصم. المستودع
    اختياري ويُثبَّت على الحركة والسطر (مرآة استلام الشراء).

    حصري للفواتير المرحّلة التي **لا** تخصم المخزون عند الترحيل — الفاتورة التي
    تخصمه عند الترحيل سُلّمت بالكامل لحظتها (مرآة استلام فاتورة الشراء).

    العملية ذرّية: حركات المخزون + قيد التكلفة + بنود الإرسالية معاً أو لا شيء.
    """
    if invoice.status != SalesInvoice.STATUS_POSTED:
        raise ValidationError("الفاتورة غير مرحّلة.")
    if invoice.stock_on_post:
        raise ValidationError(
            "هذه الفاتورة تخصم المخزون عند الترحيل — بنودها مسلَّمة بالفعل."
        )
    if not lines:
        raise ValidationError("حدّد البنود والكميات المراد تسليمها.")

    mv_type = _delivery_movement_type(invoice)
    is_return = invoice.invoice_kind in (
        SalesInvoice.INVOICE_KIND_SALE_RETURN,
        SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
    )

    with transaction.atomic():
        inv_lines = list(
            invoice.lines.select_related(
                "product",
                "product__category",
                "product__category__cogs_account",
                "product__category__inventory_account",
            )
        )
        products_by_id = _lock_products_for_lines(inv_lines)
        for line in inv_lines:
            line.product = products_by_id[line.product_id]
        lines_by_id = {l.id: l for l in inv_lines}

        delivered_now: dict[int, Decimal] = {}
        warehouse_by_line: dict[int, object] = {}
        for raw in lines:
            line_id = raw.get("line_id")
            line = lines_by_id.get(int(line_id)) if line_id is not None else None
            if not line:
                raise ValidationError(f"البند {line_id} لا ينتمي لهذه الفاتورة.")
            try:
                qty = Decimal(str(raw.get("quantity", 0)))
            except Exception:
                raise ValidationError(f"كمية غير صالحة للبند «{line.product}».")
            if qty <= 0:
                continue
            if getattr(line.product, "is_service", False):
                raise ValidationError(
                    f"البند «{line.product}» خدمة — لا يُسلَّم من المخزن."
                )
            ordered = Decimal(str(line.quantity or 0))
            already = Decimal(str(line.delivered_quantity or 0))
            remaining = ordered - already
            if qty > remaining:
                raise ValidationError(
                    f"البند «{line.product}»: الكمية المطلوب تسليمها ({qty}) "
                    f"تتجاوز المتبقي ({remaining})."
                )
            delivered_now[line.id] = delivered_now.get(line.id, Decimal("0")) + qty
            # سطر مُرسَل مرتين: الكميات تُجمع والمستودع الأخير المحدَّد هو المعتمد.
            warehouse_by_line[line.id] = (
                _resolve_delivery_warehouse(invoice.tenant_id, raw)
                or warehouse_by_line.get(line.id)
            )

        if not delivered_now:
            raise ValidationError("لا يوجد ما يُسلَّم — تحقق من الكميات.")

        if delivery is None:
            delivery = DeliveryOrder.objects.create(
                tenant=invoice.tenant,
                branch=invoice.branch,
                delivery_number=next_delivery_number(invoice.tenant_id, invoice.branch),
                delivery_date=delivery_date or invoice.invoice_date,
                invoice=invoice,
                notes=(notes or "")[:500],
            )
        elif delivery.status == DeliveryOrder.STATUS_DELIVERED:
            raise ValidationError("تم تسليم هذه الإرسالية مسبقاً.")
        elif not delivery.delivery_number:
            # إرسالية قديمة أُنشئت قبل الترقيم — تُرقَّم عند تسليمها.
            delivery.delivery_number = next_delivery_number(
                invoice.tenant_id, invoice.branch,
            )
            delivery.delivery_date = delivery.delivery_date or invoice.invoice_date
            delivery.save(update_fields=["delivery_number", "delivery_date"])

        for line_id, qty in delivered_now.items():
            line = lines_by_id[line_id]
            warehouse = warehouse_by_line.get(line_id)
            try:
                movement = record_stock_movement(
                    product=line.product,
                    movement_type=mv_type,
                    quantity=qty,
                    reference_type="SALE",
                    reference_id=invoice.id,
                    partner=invoice.customer,
                    movement_date=invoice.invoice_date,
                    notes=(
                        f"تسليم إرسالية {delivery.delivery_number or f'#{delivery.id}'} "
                        f"— فاتورة {invoice.invoice_number}"
                    ),
                    tenant=invoice.tenant,
                    branch=invoice.branch,
                    warehouse=warehouse,
                )
            except ValidationError as e:
                raise ValidationError(f"مخزون الصنف {line.product.sku}: {e}")
            DeliveryOrderLine.objects.create(
                tenant=invoice.tenant,
                delivery=delivery,
                invoice_line=line,
                product=line.product,
                warehouse=warehouse,
                quantity=qty,
                movement=movement,
            )
            line.delivered_quantity = (
                Decimal(str(line.delivered_quantity or 0)) + qty
            )
            line.save(update_fields=["delivered_quantity"])

        # قيد تكلفة المبيعات للكمية المسلَّمة في هذه الإرسالية وحدها.
        cogs_rows = _build_cogs_journal_line_dicts(
            invoice, inv_lines, products_by_id, quantities=delivered_now,
        )
        cogs_journal = None
        if cogs_rows:
            if is_return:
                for row in cogs_rows:
                    row["debit"], row["credit"] = row["credit"], row["debit"]
            cogs_journal = post_journal(
                tenant_id=invoice.tenant_id,
                transaction_date=invoice.invoice_date,
                reference_type="SALES_DELIVERY_COGS",
                reference_id=invoice.id,
                description=(
                    f"تكلفة مبيعات عند التسليم — {invoice.invoice_number} "
                    f"(إرسالية {delivery.delivery_number or f'#{delivery.id}'})"
                )[:500],
                lines_data=cogs_rows,
                currency=invoice.currency,
                exchange_rate=invoice.exchange_rate,
                user=user,
                branch_id=invoice.branch_id,
                # كل إرسالية قيد تكلفة مستقل — بلا هذا يُعاد أول قيد للإرسالية الثانية.
                idempotent=False,
            )

        delivery.status = DeliveryOrder.STATUS_DELIVERED
        from django.utils import timezone

        delivery.delivered_at = timezone.now()
        delivery.journal = cogs_journal
        delivery.save(update_fields=["status", "delivered_at", "journal"])

        sync_invoice_delivery_status(invoice, inv_lines)

        create_audit_log(
            tenant=invoice.tenant,
            user=user,
            action="UPDATE",
            model_name="DeliveryOrder",
            object_id=delivery.id,
            change_details=(
                f"Delivered {len(delivered_now)} line(s) for invoice "
                f"{invoice.invoice_number} → {invoice.delivery_status}"
            ),
        )

    logger.info(
        "Sales invoice #%s delivery #%s: %d line(s), delivery_status=%s",
        invoice.id, delivery.id, len(delivered_now), invoice.delivery_status,
    )
    return delivery


def resolve_goods_delivered_unbilled_account(tenant_id: int) -> Account:
    """حساب «بضاعة مسلَّمة لم تُفوتَر» (كود 1108) — مرآة وسيط الاستلام 2106.

    يستقبل تكلفة البضاعة التي خرجت بسند تسليم مستقل قبل فوترتها، فحين تُفوتَر
    لاحقاً يُدائنه قيدُ تكلفة الفاتورة فيُصفَّر. يُنشأ تلقائياً إن لم يوجد.
    """
    acc = Account.objects.filter(tenant_id=tenant_id, code="1108").first()
    if acc:
        return acc
    parent = Account.objects.filter(tenant_id=tenant_id, code="11").first()
    acc, _ = Account.objects.get_or_create(
        tenant_id=tenant_id,
        code="1108",
        defaults={
            "name": "بضاعة مسلَّمة لم تُفوتَر",
            "account_type": "Asset",
            "parent": parent,
            "is_active": True,
        },
    )
    return acc


def create_standalone_delivery_note(
    tenant, *, partner, lines, branch=None, user=None, delivery_date=None,
    notes="", customer_ref="", delivery=None,
):
    """سند تسليم مستقل — بضاعة خرجت قبل فوترتها (مرآة سند الاستلام).

    lines: [{'product_id': int, 'quantity': Decimal, 'warehouse_id': int|None}]
    القيد: مدين «بضاعة مسلَّمة لم تُفوتَر» (1108) / دائن المخزون بمتوسط التكلفة —
    لا إيراد هنا، الإيراد يأتي مع الفاتورة لاحقاً.
    """
    import datetime
    from django.utils import timezone

    if not lines:
        raise ValidationError("حدّد الأصناف والكميات المسلَّمة.")
    if partner is None:
        raise ValidationError("حدّد العميل لسند التسليم المستقل.")

    movement_date = delivery_date or datetime.date.today()
    tenant_id = getattr(tenant, "TenantID", tenant)
    products = {
        p.id: p
        for p in Product.objects.select_for_update()
        .select_related("category", "category__inventory_account")
        .filter(
            tenant_id=tenant_id,
            pk__in=[row.get("product_id") for row in lines if row.get("product_id")],
        )
    }

    planned = []
    for raw in lines:
        product = products.get(int(raw.get("product_id") or 0))
        if product is None:
            raise ValidationError(f"الصنف {raw.get('product_id')} غير موجود في هذه الشركة.")
        if getattr(product, "is_service", False):
            raise ValidationError(f"الصنف «{product}» خدمة — لا يُسلَّم من المخزن.")
        try:
            qty = Decimal(str(raw.get("quantity", 0)))
        except Exception:
            raise ValidationError(f"كمية غير صالحة للصنف «{product}».")
        if qty <= 0:
            continue
        planned.append({
            "product": product,
            "qty": qty,
            "cost": (qty * Decimal(str(product.avg_cost or 0))).quantize(DEC),
            "warehouse": _resolve_delivery_warehouse(tenant_id, raw),
        })

    if not planned:
        raise ValidationError("لا يوجد ما يُسلَّم — تحقق من الكميات.")

    total_cost = sum((p["cost"] for p in planned), Decimal("0"))

    with transaction.atomic():
        doc = delivery
        if doc is None:
            doc = DeliveryOrder.objects.create(
                tenant=tenant,
                branch=branch,
                delivery_number=next_delivery_number(tenant_id, branch),
                delivery_date=movement_date,
                invoice=None,
                partner=partner,
                customer_ref=(customer_ref or "")[:100],
                status=DeliveryOrder.STATUS_DELIVERED,
                delivered_at=timezone.now(),
                notes=(notes or "")[:500],
            )
        else:
            doc.lines.all().delete()
            doc.delivery_date = movement_date
            doc.partner = partner
            doc.customer_ref = (customer_ref or "")[:100]
            doc.notes = (notes or "")[:500]
            doc.save(update_fields=[
                "delivery_date", "partner", "customer_ref", "notes",
            ])

        for p in planned:
            try:
                movement = record_stock_movement(
                    product=p["product"],
                    movement_type="OUT",
                    quantity=p["qty"],
                    reference_type="DELIVERY_NOTE",
                    reference_id=doc.id,
                    partner=partner,
                    movement_date=movement_date,
                    notes=f"سند تسليم {doc.delivery_number}",
                    tenant=tenant,
                    branch=branch,
                    warehouse=p["warehouse"],
                )
            except ValidationError as e:
                raise ValidationError(f"مخزون الصنف {p['product'].sku}: {e}")
            DeliveryOrderLine.objects.create(
                tenant=tenant,
                delivery=doc,
                invoice_line=None,
                product=p["product"],
                warehouse=p["warehouse"],
                quantity=p["qty"],
                movement=movement,
            )

        journal = None
        if total_cost > 0:
            ss = get_or_create_sales_settings(tenant_id)
            clearing = resolve_goods_delivered_unbilled_account(tenant_id)
            rows = []
            for p in planned:
                if p["cost"] <= 0:
                    continue
                cat = p["product"].category
                inv_id = (
                    cat.inventory_account_id
                    if cat and cat.inventory_account_id
                    else ss.default_inventory_account_id
                )
                if not inv_id:
                    raise ValidationError(
                        f"الصنف «{p['product']}»: عيّن حساب المخزون في فئة المنتج "
                        "أو حساباً افتراضياً في إعدادات المبيعات."
                    )
                rows.append({
                    "account": inv_id, "partner": None,
                    "debit": Decimal("0"), "credit": p["cost"],
                    "description": f"تخفيض مخزون — سند تسليم {doc.delivery_number}"[:500],
                })
            rows.insert(0, {
                "account": clearing.id, "partner": None,
                "debit": total_cost, "credit": Decimal("0"),
                "description": f"بضاعة مسلَّمة لم تُفوتَر — {doc.delivery_number}"[:500],
            })
            journal = post_journal(
                tenant_id=tenant_id,
                transaction_date=movement_date,
                reference_type="DELIVERY_NOTE",
                reference_id=doc.id,
                description=f"سند تسليم {doc.delivery_number} | {partner.name}"[:500],
                lines_data=rows,
                user=user,
                branch_id=branch.id if branch else None,
                idempotent=False,
            )
            doc.journal = journal
            doc.save(update_fields=["journal"])

    logger.info(
        "Standalone delivery note %s: %d line(s), cost=%s, journal=%s",
        doc.delivery_number, len(planned), total_cost, journal.id if journal else None,
    )
    return doc


def void_delivery_note(delivery: DeliveryOrder, *, user=None) -> dict:
    """يعكس أثر إرسالية بيع واحدة: حركاتها وقيدها وكمياتها المسلَّمة — دون غيرها.

    التتبّع عبر `DeliveryOrderLine.movement`، فلا تُمسّ إرساليات أخرى لنفس الفاتورة.
    """
    from accounting.models import JournalHeader
    from inventory.services import _recompute_product_stock

    with transaction.atomic():
        lines = list(delivery.lines.select_related("invoice_line", "product", "movement"))
        movement_ids = [l.movement_id for l in lines if l.movement_id]
        products = {l.product_id: l.product for l in lines if l.product_id}

        if movement_ids:
            StockMovement.objects.filter(pk__in=movement_ids).delete()
        if delivery.journal_id:
            JournalHeader.objects.filter(pk=delivery.journal_id).delete()

        invoice = delivery.invoice
        if invoice is not None:
            for line in lines:
                if line.invoice_line_id is None:
                    continue
                inv_line = line.invoice_line
                inv_line.delivered_quantity = max(
                    Decimal("0"),
                    Decimal(str(inv_line.delivered_quantity or 0))
                    - Decimal(str(line.quantity or 0)),
                )
                inv_line.save(update_fields=["delivered_quantity"])

        number = delivery.delivery_number or f"#{delivery.id}"
        delivery.delete()

        for product in products.values():
            _recompute_product_stock(product)

        if invoice is not None:
            sync_invoice_delivery_status(invoice)

    logger.info(
        "Delivery note %s voided: %d movement(s) reversed", number, len(movement_ids),
    )
    return {"movements_reversed": len(movement_ids)}


def remaining_delivery_lines(invoice: SalesInvoice) -> list[dict]:
    """بنود الفاتورة مع (المفوتر · المسلَّم · المتبقي) — يغذّي نافذة التسليم.

    مصدر حقيقة واحد مع حارس التسليم، فلا تعرض الواجهة ما يرفضه الخادم.
    """
    rows: list[dict] = []
    for line in invoice.lines.select_related("product"):
        if getattr(line.product, "is_service", False):
            continue
        ordered = Decimal(str(line.quantity or 0))
        delivered = Decimal(str(line.delivered_quantity or 0))
        rows.append({
            "line_id": line.id,
            "product": line.product_id,
            "product_name": str(line.product),
            "quantity": ordered,
            "delivered_quantity": delivered,
            "remaining_quantity": max(Decimal("0"), ordered - delivered),
        })
    return rows


def deliver_delivery_order(delivery: DeliveryOrder, *, user=None) -> DeliveryOrder:
    """تسليم إرسالية قائمة بكامل المتبقي من بنود فاتورتها (المسار القديم).

    يُفوِّض لـ`deliver_invoice_lines` كي لا يوجد منطق تسليم مكرّر.
    """
    inv = delivery.invoice
    if delivery.status == DeliveryOrder.STATUS_DELIVERED:
        raise ValidationError("تم التسليم مسبقاً.")
    lines = [
        {"line_id": r["line_id"], "quantity": r["remaining_quantity"]}
        for r in remaining_delivery_lines(inv)
        if r["remaining_quantity"] > 0
    ]
    return deliver_invoice_lines(inv, lines=lines, user=user, delivery=delivery)


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
    # T-ONACC: التوزيع اختياري — ما لم يُوزَّع يُرحَّل «على الحساب» (Dr صندوق /
    # Cr ذمم العميل) فيؤثّر على كشف حسابه بلا تسديد أي فاتورة، ويُوزَّع لاحقاً
    # عبر allocate_customer_payment. الممنوع فقط: توزيع يتجاوز مبلغ الدفعة.
    if allocated > payment.amount + DEC:
        raise ValidationError("مجموع التوزيعات لا يجوز أن يتجاوز مبلغ الدفعة.")

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

    # ── شيكات داخل السند ─────────────────────────────────────────────────
    # مبلغ السند = نقد + شيكات. الجزء المُغطّى بشيكات لا يدخل الصندوق بل
    # «شيكات برسم التحصيل» حتى تُحصَّل. الاستهلاك بالترتيب على قيود السند
    # (قيد لكل فاتورة ثم قيد «على الحساب») كي يبقى كل قيد متوازناً وحده.
    payment_cheques = list(payment.cheques.all()) if payment.pk else []
    cheques_pool = sum(
        (Decimal(str(c.amount or 0)) for c in payment_cheques), Decimal("0")
    ).quantize(DEC)
    if cheques_pool > Decimal(str(payment.amount)) + DEC:
        raise ValidationError(
            f"مجموع الشيكات ({cheques_pool}) يتجاوز مبلغ السند ({payment.amount})."
        )
    uc_account = (
        resolve_cheques_under_collection_account(payment.tenant_id)
        if cheques_pool > 0 else None
    )

    def _debit_lines(amount: Decimal, description: str) -> list[dict]:
        """يقسم الجانب المدين بين الصندوق والشيكات برسم التحصيل."""
        nonlocal cheques_pool
        from_cheques = min(cheques_pool, amount).quantize(DEC)
        cheques_pool = (cheques_pool - from_cheques).quantize(DEC)
        cash_part = (amount - from_cheques).quantize(DEC)
        rows: list[dict] = []
        if cash_part > 0:
            rows.append({
                # T-CASH2: سطر الصندوق لا يَحمل الشريك (لا يُحسب على ذمم العميل).
                "account": payment.cash_or_bank_account_id,
                "partner": None,
                "debit": cash_part,
                "credit": Decimal("0"),
                "description": description,
            })
        if from_cheques > 0:
            rows.append({
                # شيكات برسم التحصيل أصل لا حساب رقابي للذمم — بلا شريك.
                "account": uc_account.id,
                "partner": None,
                "debit": from_cheques,
                "credit": Decimal("0"),
                "description": f"شيكات — {description}",
            })
        return rows

    with transaction.atomic():
        # T-SPLIT: قفل صفّ الدفعة وإعادة فحص الترحيل — إذ نُنشئ قيداً لكل فاتورة
        # بـ idempotent=False (نفس reference_id)، فلا يحمينا فحص post_journal من
        # ترحيل مزدوج متزامن؛ القفل هنا يُسلسِل الطلبات ويمنع تكرار القيود.
        payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.is_posted:
            raise ValidationError("الدفعة مرحّلة مسبقاً.")

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
        # T-SPLIT: قيد مستقل لكل فاتورة. سند القبض الواحد يُنتج قيداً منفصلاً لكل
        # فاتورة سُدِّدت (Dr صندوق / Cr ذمم العميل [+ فرق عملة إن لزم]) فتظهر كل
        # فاتورة كحركة/قيد مستقل في كشف الحساب ودفتر اليومية. كل القيود بنفس
        # reference_type/reference_id فيُصفّرها التراجع (unpost_document) دفعةً واحدة.
        # لكل فاتورة: cash = ما دُفع فعلاً بعملة الدفعة (مجموعه = مبلغ الدفعة)، و
        # ar = ما يُسدَّد من الذمم (قيمة الفاتورة محوّلة لعملة الدفعة)؛ فرقهما = فرق عملة.
        cash_by_invoice: dict[int, Decimal] = {}
        ar_by_invoice: dict[int, Decimal] = {}
        invoice_order: list[int] = []
        for alloc, amount_in_inv_curr, _rate in alloc_conversions:
            inv_curr_id = alloc.invoice.currency_id
            if payment_currency_id and inv_curr_id and inv_curr_id != payment_currency_id:
                # P-H-8: كل توزيع يُحوَّل من عملة فاتورته إلى عملة الدفعة على حدة.
                ar_amt, _ = convert_amount(
                    amount=amount_in_inv_curr,
                    from_currency_id=inv_curr_id,
                    to_currency_id=payment_currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
            else:
                ar_amt = Decimal(str(alloc.amount))  # نفس العملة — لا فرق صرف
            if alloc.invoice_id not in cash_by_invoice:
                invoice_order.append(alloc.invoice_id)
                cash_by_invoice[alloc.invoice_id] = Decimal("0")
                ar_by_invoice[alloc.invoice_id] = Decimal("0")
            cash_by_invoice[alloc.invoice_id] += Decimal(str(alloc.amount))
            ar_by_invoice[alloc.invoice_id] += ar_amt

        # حساب فروقات العملة يُطلب مرّة واحدة إن اختلف الصندوق عن تسديد الذمم لأي فاتورة.
        forex_acc = None
        if any(
            abs(cash_by_invoice[i] - ar_by_invoice[i]).quantize(DEC) > DEC
            for i in invoice_order
        ):
            forex_acc = resolve_forex_account(payment.tenant_id)
            if not forex_acc:
                raise ValidationError(
                    "فرق عملة مكتشف لكن لا يوجد حساب فروقات عملة. "
                    "أنشئ حساباً باسم 'فرق عمل' من نوع Expense أو Revenue."
                )

        journals = []
        for inv_id in invoice_order:
            inv = locked_invoices[inv_id]
            cash_amt = cash_by_invoice[inv_id].quantize(DEC)
            ar_amt = ar_by_invoice[inv_id].quantize(DEC)
            forex_diff = (cash_amt - ar_amt).quantize(DEC)  # >0 ربح، <0 خسارة
            inv_lines: list[dict] = _debit_lines(
                cash_amt, f"تحصيل عميل — فاتورة {inv.invoice_number}"
            )
            if forex_acc and abs(forex_diff) > DEC:
                # الذمم تُسدَّد بقيمة الفاتورة المحوّلة، والفرق لحساب فروقات العملة.
                inv_lines.append({
                    "account": ar.id,
                    "partner": payment.partner_id,
                    "debit": Decimal("0"),
                    "credit": ar_amt,
                    "description": f"تسديد ذمم — فاتورة {inv.invoice_number}",
                })
                if forex_diff > 0:
                    inv_lines.append({
                        "account": forex_acc.id, "partner": None,
                        "debit": Decimal("0"), "credit": forex_diff,
                        "description": f"ربح فروق عملة — فاتورة {inv.invoice_number}",
                    })
                else:
                    inv_lines.append({
                        "account": forex_acc.id, "partner": None,
                        "debit": abs(forex_diff), "credit": Decimal("0"),
                        "description": f"خسارة فروق عملة — فاتورة {inv.invoice_number}",
                    })
            else:
                # نفس العملة (الشائع) — الذمم تُسدَّد بمبلغ الصندوق تماماً.
                inv_lines.append({
                    "account": ar.id,
                    "partner": payment.partner_id,
                    "debit": Decimal("0"),
                    "credit": cash_amt,
                    "description": f"تسديد ذمم — فاتورة {inv.invoice_number}",
                })
            jh = post_journal(
                tenant_id=payment.tenant_id,
                transaction_date=payment.payment_date,
                reference_type="CUSTOMER_PAYMENT",
                reference_id=payment.id,
                description=(
                    (payment.notes or f"تحصيل عميل {payment.partner.name}")
                    + f" — فاتورة {inv.invoice_number}"
                )[:500],
                lines_data=inv_lines,
                currency=payment.currency,
                exchange_rate=payment.exchange_rate,
                user=user,
                idempotent=False,  # قيد مستقل لكل فاتورة رغم وحدة reference_id
            )
            journals.append(jh)

        # T-ONACC: الجزء غير الموزَّع (أو كامل المبلغ حين لا توزيع) يُرحَّل بقيد
        # واحد «على الحساب»: Dr صندوق / Cr ذمم العميل — يظهر في كشف الحساب
        # كرصيد لصالح العميل ويُوزَّع على الفواتير لاحقاً بلا قيد إضافي.
        unallocated = (Decimal(str(payment.amount)) - allocated).quantize(DEC)
        if unallocated >= DEC:
            jh = post_journal(
                tenant_id=payment.tenant_id,
                transaction_date=payment.payment_date,
                reference_type="CUSTOMER_PAYMENT",
                reference_id=payment.id,
                description=(
                    (payment.notes or f"تحصيل عميل {payment.partner.name}")
                    + " — على الحساب"
                )[:500],
                lines_data=[
                    *_debit_lines(
                        unallocated, f"تحصيل على الحساب — {payment.partner.name}"
                    ),
                    {
                        "account": ar.id,
                        "partner": payment.partner_id,
                        "debit": Decimal("0"),
                        "credit": unallocated,
                        "description": f"دفعة على الحساب — {payment.partner.name}",
                    },
                ],
                currency=payment.currency,
                exchange_rate=payment.exchange_rate,
                user=user,
                idempotent=False,
            )
            journals.append(jh)
            logger.info(
                "Payment %s posted on-account remainder %s (allocated=%s of %s)",
                payment.id, unallocated, allocated, payment.amount,
            )

        # payment.journal حقل مفرد — نخزّن أول قيد للمرجعية؛ التراجع يعتمد
        # reference_id فيشمل كل القيود.
        payment.journal = journals[0] if journals else None
        payment.is_posted = True
        payment.save(update_fields=["journal", "is_posted"])

        # شيكات السند تنتقل من مسودة إلى «برسم التحصيل» بترحيله (كما في الفاتورة).
        if payment_cheques:
            from accounting.models import Cheque
            Cheque.objects.filter(
                customer_payment=payment, status="Draft"
            ).update(status="Under_Collection")

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
                f"Customer payment posted journal={payment.journal_id} "
                f"currency={payment.currency_id} amount={payment.amount} "
                f"allocated={allocated}"
            ),
        )

    return payment


def allocate_customer_payment(
    payment: CustomerPayment, allocations: list[dict], *, user=None
) -> CustomerPayment:
    """T-ONACC: توزيع سند قبض (كامله أو جزء منه) على فواتير — بعد الترحيل أو قبله.

    قرار المالك: التوزيع اللاحق **ربط فقط بلا قيد جديد** — لأن ترحيل السند خفّض
    ذمم العميل أصلاً (على الحساب)، فالتوزيع لا يغيّر أي رصيد دفتري؛ يُحدِّث
    `amount_paid` على الفاتورة ويربط السند بها فقط. إن لم يكن السند مرحّلاً بعد
    فالصفوف تُنشأ فحسب ويتولّى `post_customer_payment` القيود و`amount_paid`.

    allocations: [{"invoice": <id>, "amount": <Decimal|str>}, ...]
    """
    rows = [
        (int(a["invoice"]), Decimal(str(a.get("amount") or "0")))
        for a in (allocations or [])
    ]
    if not rows:
        raise ValidationError("لا توزيعات مُرسَلة.")
    if any(amt <= 0 for _inv_id, amt in rows):
        raise ValidationError("مبلغ التوزيع يجب أن يكون أكبر من صفر.")

    with transaction.atomic():
        payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)
        already = (
            PaymentAllocation.objects.filter(payment=payment).aggregate(t=Sum("amount"))["t"]
            or Decimal("0")
        )
        total_new = sum((amt for _inv_id, amt in rows), Decimal("0"))
        if already + total_new > Decimal(str(payment.amount)) + DEC:
            raise ValidationError(
                f"مجموع التوزيعات ({already + total_new}) يتجاوز مبلغ السند "
                f"({payment.amount}). المتاح للتوزيع: {Decimal(str(payment.amount)) - already}."
            )

        invoices = {
            inv.pk: inv
            for inv in SalesInvoice.objects.select_for_update().filter(
                pk__in={inv_id for inv_id, _amt in rows}, tenant_id=payment.tenant_id
            )
        }
        for inv_id, amt in rows:
            inv = invoices.get(inv_id)
            if inv is None:
                raise ValidationError(f"الفاتورة #{inv_id} غير موجودة في هذه الشركة.")
            if inv.customer_id != payment.partner_id:
                raise ValidationError(
                    f"الفاتورة #{inv.invoice_number} لا تخص نفس العميل."
                )
            if inv.status != SalesInvoice.STATUS_POSTED:
                raise ValidationError(f"الفاتورة #{inv.invoice_number} غير مرحّلة.")

            if payment.currency_id == inv.currency_id:
                amount_in_inv_curr, conv_rate = amt, Decimal("1")
            else:
                amount_in_inv_curr, conv_rate = convert_amount(
                    amount=amt,
                    from_currency_id=payment.currency_id,
                    to_currency_id=inv.currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
            remaining = inv.grand_total - Decimal(str(inv.amount_paid))
            if amount_in_inv_curr > remaining + DEC:
                raise ValidationError(
                    f"مبلغ التوزيع ({amount_in_inv_curr}) يتجاوز المتبقي على "
                    f"الفاتورة #{inv.invoice_number} ({remaining})."
                )

            PaymentAllocation.objects.create(
                tenant_id=payment.tenant_id,
                payment=payment,
                invoice=inv,
                amount=amt,
                amount_in_invoice_currency=amount_in_inv_curr,
                conversion_rate=conv_rate,
            )
            if payment.is_posted:
                inv.amount_paid = Decimal(str(inv.amount_paid)) + amount_in_inv_curr
                inv.save(update_fields=["amount_paid"])
            logger.info(
                "Payment %s allocated %s → invoice %s (posted=%s)",
                payment.id, amt, inv.invoice_number, payment.is_posted,
            )

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="ALLOCATE",
            model_name="CustomerPayment",
            object_id=payment.id,
            change_details=(
                f"Allocated {total_new} to {len(rows)} invoice(s); "
                f"total allocated={already + total_new} of {payment.amount}"
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


def invoice_profits(
    *,
    tenant_id: int,
    branch=None,
    date_from: str | None = None,
    date_to: str | None = None,
    customer_id: int | None = None,
) -> dict:
    """task18 DEF-C4: تقرير أرباح الفواتير المرحَّلة.

    الإيراد = صافي البنود قبل الضريبة (subtotal_excl_tax − خصم الفاتورة) — يطابق
    الدائن في قيد الإيراد. التكلفة = مجموع `total_cost` لحركات مخزون البيع
    (SALE/STOCK_ISSUE) المسجَّلة وقت الترحيل بمتوسط التكلفة آنذاك (تكلفة تاريخية
    دقيقة لا تتأثر بانجراف WAC لاحقاً). الربح = الإيراد − التكلفة.
    محصور بالشركة (والفرع غير الرئيسي إن مُرّر) وبفواتير البيع فقط (لا مراجيع).
    """
    qs = SalesInvoice.objects.filter(
        tenant_id=tenant_id,
        status=SalesInvoice.STATUS_POSTED,
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
    )
    if branch is not None and not getattr(branch, "is_main", False):
        qs = qs.filter(branch=branch)
    if date_from:
        qs = qs.filter(invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice_date__lte=date_to)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    qs = qs.select_related("customer").order_by("-invoice_date", "-id")

    invoice_ids = list(qs.values_list("id", flat=True))
    cogs_map: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    if invoice_ids:
        mv = (
            StockMovement.objects.filter(
                tenant_id=tenant_id,
                reference_type__in=("SALE", "STOCK_ISSUE"),
                reference_id__in=invoice_ids,
            )
            .values("reference_id")
            .annotate(c=Sum("total_cost"))
        )
        for r in mv:
            cogs_map[r["reference_id"]] = Decimal(str(r["c"] or "0"))

    rows: list[dict] = []
    tot_rev = Decimal("0")
    tot_cost = Decimal("0")
    for inv in qs:
        revenue = (inv.subtotal_excl_tax - inv.invoice_discount).quantize(DEC)
        cost = cogs_map.get(inv.id, Decimal("0")).quantize(DEC)
        profit = (revenue - cost).quantize(DEC)
        margin = (profit / revenue * 100).quantize(DEC) if revenue > 0 else Decimal("0")
        rows.append(
            {
                "invoice": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "customer": inv.customer_id,
                "customer_name": getattr(inv.customer, "name", "") or "",
                "revenue": str(revenue),
                "cost": str(cost),
                "profit": str(profit),
                "margin_pct": str(margin),
            }
        )
        tot_rev += revenue
        tot_cost += cost

    tot_profit = (tot_rev - tot_cost).quantize(DEC)
    tot_margin = (tot_profit / tot_rev * 100).quantize(DEC) if tot_rev > 0 else Decimal("0")
    return {
        "rows": rows,
        "totals": {
            "count": len(rows),
            "revenue": str(tot_rev.quantize(DEC)),
            "cost": str(tot_cost.quantize(DEC)),
            "profit": str(tot_profit),
            "margin_pct": str(tot_margin),
        },
    }


def last_sale_price(
    *,
    tenant_id: int,
    product_id: int,
    customer_id: int | None = None,
) -> dict:
    """task18 DEF-C2: آخر سعر بيع للوحدة لهذا الصنف (واختيارياً لهذا العميل).

    يُرجع أحدث `unit_price` من سطور فواتير بيع مرحَّلة. إن مُرّر customer_id
    فُضِّل آخر سعر لذلك العميل، وإلا فآخر سعر عام. يُمكّن الواجهة من اقتراح السعر.
    """
    qs = SalesInvoiceLine.objects.filter(
        tenant_id=tenant_id,
        product_id=product_id,
        invoice__status=SalesInvoice.STATUS_POSTED,
        invoice__invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
    )
    line = None
    if customer_id:
        line = (
            qs.filter(invoice__customer_id=customer_id)
            .order_by("-invoice__invoice_date", "-invoice_id")
            .first()
        )
    if line is None:
        line = qs.order_by("-invoice__invoice_date", "-invoice_id").first()
    if line is None:
        return {"unit_price": None, "invoice_number": None, "invoice_date": None}
    return {
        "unit_price": str(line.unit_price),
        "invoice_number": line.invoice.invoice_number,
        "invoice_date": line.invoice.invoice_date.isoformat() if line.invoice.invoice_date else None,
    }


def customer_price_list(*, tenant_id: int, customer_id: int) -> list[dict]:
    """DEF-004: عرض السعر لكل العميل عبر كامل الكتالوج.

    لكل منتج فعّال:
      - إن اشتراه العميل سابقاً (فاتورة بيع مرحَّلة) → سعر آخر فاتورة (للقراءة فقط).
      - وإلا → عرض السعر اليدوي المحفوظ (قابل للتحرير)، أو فارغ إن لم يُحفظ.
    لا أثر محاسبي — مصدر تسعير احتياطي فقط.
    """
    from .models import CustomerProductQuote

    last_by_product: dict[int, SalesInvoiceLine] = {}
    lowest_by_product: dict[int, SalesInvoiceLine] = {}
    lines = (
        SalesInvoiceLine.objects.filter(
            tenant_id=tenant_id,
            invoice__customer_id=customer_id,
            invoice__status=SalesInvoice.STATUS_POSTED,
            invoice__invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        )
        .select_related("invoice")
        .order_by("product_id", "-invoice__invoice_date", "-invoice_id", "-id")
    )
    for ln in lines:
        if ln.product_id not in last_by_product:
            last_by_product[ln.product_id] = ln
        if ln.product_id not in lowest_by_product or ln.unit_price < lowest_by_product[ln.product_id].unit_price:
            lowest_by_product[ln.product_id] = ln

    quotes = {
        q.product_id: q
        for q in CustomerProductQuote.objects.filter(tenant_id=tenant_id, customer_id=customer_id)
    }

    # عرض سعر «واجهة العروض» (SalesQuotation) — أحدث سطر لكل منتج لهذا العميل. يظهر
    # في القائمة (وخيارات الفاتورة) حتى للعروض القديمة التي لم تُعبّئ كرت الزبون.
    from .models import SalesQuotationLine

    sq_by_product: dict[int, SalesQuotationLine] = {}
    for sl in (
        SalesQuotationLine.objects.filter(
            tenant_id=tenant_id, quotation__customer_id=customer_id,
        )
        .select_related("quotation")
        .order_by("product_id", "-quotation__quotation_date", "-quotation_id", "-id")
    ):
        if sl.product_id not in sq_by_product:
            sq_by_product[sl.product_id] = sl

    rows: list[dict] = []
    products = Product.objects.filter(tenant_id=tenant_id).order_by("name_ar", "sku")
    for p in products:
        ln_last = last_by_product.get(p.id)
        ln_lowest = lowest_by_product.get(p.id)
        q = quotes.get(p.id)
        sq = sq_by_product.get(p.id)
        name = p.name_ar or p.name_en or p.sku or f"#{p.id}"
        
        prices = []
        if ln_last:
            prices.append({
                "label": "آخر فاتورة",
                "unit_price": str(ln_last.unit_price),
                "source_type": "SALES_INVOICE",
                "document_id": ln_last.invoice_id,
                "invoice_number": ln_last.invoice.invoice_number,
            })
        if ln_lowest and (not ln_last or ln_lowest.invoice_id != ln_last.invoice_id):
            prices.append({
                "label": "أقل سعر",
                "unit_price": str(ln_lowest.unit_price),
                "source_type": "SALES_INVOICE",
                "document_id": ln_lowest.invoice_id,
                "invoice_number": ln_lowest.invoice.invoice_number,
            })
            
        if not prices and sq is not None and Decimal(str(sq.unit_price)) > 0:
            prices.append({
                "label": "عرض السعر",
                "unit_price": str(sq.unit_price),
                "source_type": "QUOTE",
                "document_id": None,  # عرض (لا فاتورة) — نتفادى رابط فاتورة خاطئ
                "invoice_number": sq.quotation.quotation_number,
            })
        if not prices and q is not None:
            prices.append({
                "label": "عرض السعر",
                "unit_price": str(q.unit_price),
                "source_type": "QUOTE",
                "document_id": q.id,
                "invoice_number": None,
            })
        # آخر مصدر: «سعر البيع» العام في كرت الصنف — يظهر فقط حين لا شراء سابق
        # لهذا الزبون ولا عرض له. تبقى الخانة قابلة للتحرير لحفظ عرض خاص به.
        if not prices and p.sale_price is not None and Decimal(str(p.sale_price)) > 0:
            prices.append({
                "label": "سعر عام (كرت الصنف)",
                "unit_price": str(p.sale_price),
                "source_type": "PRODUCT",
                "document_id": None,
                "invoice_number": None,
            })

        if prices:
            rows.append({
                "product_id": p.id,
                "sku": p.sku,
                "name": name,
                "price": prices[0]["unit_price"],
                "source": (
                    "last_invoice" if prices[0]["source_type"] == "SALES_INVOICE"
                    else "default" if prices[0]["source_type"] == "PRODUCT"
                    else "quote"
                ),
                "source_label": prices[0]["label"],
                # السعر العام ليس عرضاً للزبون — يبقى قابلاً للتحرير ليُحفظ عرضه الخاص.
                "editable": prices[0]["source_type"] in ("QUOTE", "PRODUCT"),
                "invoice_number": prices[0]["invoice_number"],
                "prices": prices,
            })
        else:
            rows.append({
                "product_id": p.id,
                "sku": p.sku,
                "name": name,
                "price": None,
                "source": "quote",
                "source_label": "عرض السعر / يدوي",
                "editable": True,
                "invoice_number": None,
                "prices": [],
            })
    return rows


@transaction.atomic
def save_customer_quotes(*, tenant_id: int, customer_id: int, entries: list[dict]) -> int:
    """DEF-004: حفظ/تحديث/حذف عروض الأسعار اليدوية لعميل.

    كل عنصر: {"product": id, "unit_price": value}. قيمة فارغة/صفر/سالبة ⇒ حذف
    العرض. يُرجع عدد العروض المحفوظة (غير المحذوفة).
    """
    from .models import CustomerProductQuote

    saved = 0
    for e in entries or []:
        pid = e.get("product")
        if pid in (None, ""):
            continue
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        raw = e.get("unit_price")
        try:
            price = Decimal(str(raw)) if raw not in (None, "") else None
        except (TypeError, ValueError):
            price = None
        if price is None or price <= 0:
            CustomerProductQuote.objects.filter(
                tenant_id=tenant_id, customer_id=customer_id, product_id=pid
            ).delete()
            continue
        CustomerProductQuote.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, product_id=pid,
            defaults={"unit_price": price},
        )
        saved += 1
    return saved


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


def _invoice_number_prefix(tenant_id: int, book_number: int, branch=None) -> str:
    """task11 M4: بادئة رقم الفاتورة — رمز الفرع يدخل البادئة لفصل تسلسلات
    الفروع بصرياً ورقمياً. الفرع الرئيسي/بدون فرع يحافظ على الصيغة القديمة."""
    parts = [f"SI-{tenant_id}"]
    if branch is not None and not branch.is_main:
        parts.append(branch.code)
    if book_number != 0:
        parts.append(f"B{book_number}")
    return "-".join(parts) + "-"


def next_invoice_number(tenant_id: int, book_number: int = 0, branch=None) -> str:
    """Thin wrapper حول next_document_number() — N8-T4 + task11 M4 (فرع).

    book_number=0 → manual (any number accepted), generate with tenant prefix.
    book_number>0 → use book prefix for isolated per-book sequence.
    branch (Branch|None) → تسلسل مستقل لكل فرع (None/رئيسي = مستوى الشركة).
    """
    from accounting.services import next_document_number

    branch_id = branch.pk if (branch is not None and not branch.is_main) else None
    seq = next_document_number(
        tenant_id, 'sales_invoice', book_number=book_number, branch_id=branch_id)
    return f"{_invoice_number_prefix(tenant_id, book_number, branch)}{seq}"


def next_quotation_number(tenant_id: int, book_number: int = 0) -> str:
    """رقم عرض السعر التالي — thin wrapper حول next_document_number (تسلسل مستقل
    لعروض الأسعار). الرقم يُولَّد خادمياً (الواجهة لا تُدخله)."""
    from accounting.services import next_document_number

    seq = next_document_number(tenant_id, 'sales_quotation', book_number=book_number)
    return f"QUO-{seq}"


def preview_next_invoice_number(tenant_id: int, book_number: int = 0, branch=None) -> str:
    """Gets the next invoice number for preview without incrementing/persisting it."""
    from tenants.models import TenantBook

    branch_id = branch.pk if (branch is not None and not branch.is_main) else None
    book = TenantBook.objects.filter(
        tenant_id=tenant_id,
        branch_id=branch_id,
        document_type='sales_invoice',
        book_number=book_number
    ).first()

    next_num = (book.last_used_number + 1) if book else 1
    return f"{_invoice_number_prefix(tenant_id, book_number, branch)}{next_num}"


def next_order_number(tenant_id: int) -> str:
    """رقم الطلبية التالي — تسلسل مستقل عن العروض والفواتير."""
    from accounting.services import next_document_number

    seq = next_document_number(tenant_id, 'sales_order', book_number=0)
    return f"ORD-{seq}"


# ─────────────────────────────────────────────────────────────────────────
# T-ORDERS — عروض الأسعار وطلبيات الزبائن (صلاحية، حجز، عربون، إلغاء)
# ─────────────────────────────────────────────────────────────────────────

def _sales_settings(tenant_id: int):
    from .models import SalesSettings

    return SalesSettings.objects.filter(tenant_id=tenant_id).first()


def default_quotation_valid_until(tenant_id: int, from_date=None):
    """تاريخ انتهاء صلاحية العرض افتراضياً (إعداد الشركة، 14 يوماً افتراضاً).

    0 يوم = بلا انتهاء (None) — لمن لا يريد صلاحية على عروضه.
    """
    from datetime import date as _date, timedelta

    base = from_date or _date.today()
    ss = _sales_settings(tenant_id)
    days = ss.quotation_valid_days if ss else 14
    if not days:
        return None
    return base + timedelta(days=int(days))


def default_order_reserved_until(tenant_id: int, from_date=None):
    """آخر يوم يحجز فيه الطلب الكمية (إعداد الشركة، 7 أيام افتراضاً)."""
    from datetime import date as _date, timedelta

    base = from_date or _date.today()
    ss = _sales_settings(tenant_id)
    days = ss.order_reserve_days if ss else 7
    if not days:
        return None
    return base + timedelta(days=int(days))


def document_delete_allowed(tenant_id: int) -> bool:
    """هل يُسمح بحذف العروض/الطلبيات لهذه الشركة (الإلغاء متاح دائماً)؟"""
    ss = _sales_settings(tenant_id)
    return True if ss is None else bool(ss.allow_document_delete)


def _active_reservation_lines(tenant_id: int, product_ids=None):
    """بنود الحجز السارية — تعريف واحد يخدم الخريطة والحارس والتقرير معاً."""
    from datetime import date as _date

    from .models import SalesOrder, SalesOrderLine

    qs = SalesOrderLine.objects.filter(
        tenant_id=tenant_id,
        order__status=SalesOrder.STATUS_CONFIRMED,
        order__reserved_until__gte=_date.today(),
    )
    if product_ids is not None:
        qs = qs.filter(product_id__in=list(product_ids))
    return qs


def reserved_quantity_map(
    tenant_id: int, product_ids=None, *, exclude_customer_id: int | None = None,
) -> dict:
    """الكمية المحجوزة لكل صنف = بنود طلبيات مؤكَّدة لم ينتهِ حجزها.

    مشتقّة بالكامل من الطلبيات (لا عمود على المنتج): الانتهاء يحرّر الكمية من
    تلقاء نفسه بلا مهمة خلفية، والإلغاء/التحويل يخرجان من الحالة المؤكَّدة.

    `exclude_customer_id`: يتجاهل حجوزات زبون بعينه — حجزُه لا يمنعه هو.
    """
    from django.db.models import Sum

    qs = _active_reservation_lines(tenant_id, product_ids)
    if exclude_customer_id is not None:
        qs = qs.exclude(order__customer_id=exclude_customer_id)
    rows = qs.values("product_id").annotate(total=Sum("quantity"))
    return {r["product_id"]: r["total"] for r in rows if r["total"]}


def reserved_stock_rows(
    tenant_id: int, *, product_id=None, customer_id=None, date_from=None, date_to=None,
) -> list[dict]:
    """«تقرير المحجوزات»: سطر لكل بند طلبية مؤكَّدة ما زال حجزه سارياً.

    يقرأ من نفس مصدر `reserved_quantity_map` كي لا ينحرف التقرير عن الحارس:
    ما يمنعه الترحيل هو بعينه ما يظهر هنا.

    `date_from`/`date_to`: نافذة **«الحجز حتى»** — «ما ينتهي هذا الأسبوع» سؤال
    تشغيلي لا يُجاب بقراءة كل الصفوف بالعين.
    """
    from datetime import date as _date

    qs = (
        _active_reservation_lines(tenant_id, [product_id] if product_id else None)
        .select_related("order", "order__customer", "product")
        .order_by("order__reserved_until", "order__order_number", "id")
    )
    if customer_id:
        qs = qs.filter(order__customer_id=customer_id)
    if date_from:
        qs = qs.filter(order__reserved_until__gte=date_from)
    if date_to:
        qs = qs.filter(order__reserved_until__lte=date_to)
    lines = list(qs)
    reserved_totals = reserved_quantity_map(
        tenant_id, product_ids={line.product_id for line in lines} or None)
    today = _date.today()
    rows = []
    for line in lines:
        product = line.product
        on_hand = Decimal(str(product.quantity_on_hand or 0))
        reserved_total = Decimal(str(reserved_totals.get(line.product_id, 0)))
        rows.append({
            "order_id": line.order_id,
            "order_number": line.order.order_number,
            "order_date": line.order.order_date,
            "reserved_until": line.order.reserved_until,
            "days_left": (line.order.reserved_until - today).days
            if line.order.reserved_until else None,
            "customer_id": line.order.customer_id,
            "customer_name": line.order.customer.name,
            "product_id": line.product_id,
            "product_sku": product.sku,
            "product_name": product.name_ar or product.name_en or product.sku,
            "quantity": str(line.quantity),
            "unit_price": str(line.unit_price),
            "line_total": str(line.line_total),
            "quantity_on_hand": str(on_hand),
            "reserved_quantity": str(reserved_total),
            "available_quantity": str(on_hand - reserved_total),
        })
    logger.debug(
        "reserved_stock.report tenant=%s rows=%s product=%s customer=%s window=%s..%s",
        tenant_id, len(rows), product_id, customer_id, date_from, date_to,
    )
    return rows


def guard_reserved_stock(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    products_by_id: dict[int, Product],
) -> None:
    """T-RESERVEGUARD: يمنع ترحيل فاتورة تسحب كمية محجوزة لطلبية **زبون آخر**.

    الحجز كان عرضاً بلا أثر: تُحجز الكمية بطلبية مؤكَّدة، ثم تُرحَّل فاتورة لزبون
    ثانٍ فتخصمها ويبقى صاحب الطلبية بوعدٍ لا رصيد له. الحارس هنا يقارن كمية
    الفاتورة بالمتاح **بعد** حجوزات الآخرين، ويسمّي الطلبيات الحاجزة.

    مُعفى منه: المراجيع، الخدمات، الأصناف التي تسمح بالسالب، وفاتورة صاحب الحجز
    نفسه. ويتوقف كلياً عند إطفاء `block_reserved_stock_sale`.
    """
    from collections import defaultdict

    kind = invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE
    if kind != SalesInvoice.INVOICE_KIND_SALE or not invoice.stock_on_post:
        return
    ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
    if ss is not None and not ss.block_reserved_stock_sale:
        return

    requested = defaultdict(lambda: Decimal("0"))
    for line in lines:
        product = products_by_id.get(line.product_id) or line.product
        if getattr(product, "is_service", False) or getattr(product, "allow_negative_stock", False):
            continue
        requested[line.product_id] += Decimal(str(line.quantity or 0))
    if not requested:
        return

    others = reserved_quantity_map(
        invoice.tenant_id,
        product_ids=requested.keys(),
        exclude_customer_id=invoice.customer_id,
    )
    if not others:
        return

    shortages = []
    for product_id, quantity in requested.items():
        reserved = Decimal(str(others.get(product_id, 0)))
        if not reserved:
            continue
        product = products_by_id.get(product_id)
        available = Decimal(str(product.quantity_on_hand or 0)) - reserved
        if quantity <= available:
            continue
        blocking = _active_reservation_lines(invoice.tenant_id, [product_id]).exclude(
            order__customer_id=invoice.customer_id
        ).select_related("order", "order__customer")
        holders = "، ".join(
            f"{line.order.order_number} ({line.order.customer.name})" for line in blocking
        )
        shortages.append(
            f"«{product.name_ar or product.name_en or product.sku}»: المطلوب {quantity} "
            f"والمتاح بعد الحجز {available} — محجوز بـ{holders}"
        )
    if not shortages:
        return

    logger.warning(
        "Blocked invoice %s over reserved stock — %s",
        invoice.invoice_number, "؛ ".join(shortages),
    )
    raise ValidationError(
        "لا يمكن ترحيل الفاتورة: الكمية محجوزة لطلبية زبون آخر. "
        + "؛ ".join(shortages)
        + ". ألغِ الحجز أو عدّل الكمية أو أطفئ «منع بيع الكمية المحجوزة» من إعدادات المبيعات."
    )


def _recalculate_order_totals(order) -> None:
    """يعيد حساب إجماليات الطلبية من بنودها (بلا ضريبة سطرية بعد — مسجّل)."""
    subtotal = Decimal("0.00")
    for line in order.lines.all():
        line_total = (
            Decimal(str(line.quantity)) * Decimal(str(line.unit_price))
            - Decimal(str(line.line_discount or 0))
        ).quantize(DEC)
        if line.line_total != line_total:
            line.line_total = line_total
            line.save(update_fields=["line_total"])
        subtotal += line_total
    order.subtotal = subtotal.quantize(DEC)
    order.grand_total = (
        subtotal - Decimal(str(order.discount_amount or 0)) + Decimal(str(order.tax_amount or 0))
    ).quantize(DEC)
    order.save(update_fields=["subtotal", "grand_total"])


def confirm_sales_order(order, *, user=None):
    """تأكيد الطلبية بعد حجز الكمية فعلياً ومنع تجاوز المتاح.

    تُقفل الطلبية والأصناف داخل معاملة واحدة، ثم يُطرح حجز الطلبيات المؤكدة
    الأخرى من الرصيد الحالي. الخدمات والأصناف التي تسمح بالسالب لا تعيق التأكيد.
    """
    from collections import defaultdict

    from .models import SalesOrder

    with transaction.atomic():
        locked = (
            SalesOrder.objects.select_for_update()
            .prefetch_related("lines__product")
            .get(pk=order.pk)
        )
        if locked.status in (SalesOrder.STATUS_CONVERTED, SalesOrder.STATUS_CANCELLED):
            raise ValidationError("لا يمكن تأكيد طلبية محوّلة أو ملغاة.")
        if locked.status == SalesOrder.STATUS_CONFIRMED:
            return locked

        requested = defaultdict(lambda: Decimal("0"))
        for line in locked.lines.all():
            requested[line.product_id] += Decimal(str(line.quantity))
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(
                tenant_id=locked.tenant_id, pk__in=requested.keys())
        }
        existing_reservations = reserved_quantity_map(
            locked.tenant_id, product_ids=requested.keys())
        shortages = []
        for product_id, quantity in requested.items():
            product = products.get(product_id)
            if product is None:
                shortages.append(f"الصنف #{product_id} غير متاح في الشركة الحالية")
                continue
            if product.is_service or product.allow_negative_stock:
                continue
            available = (
                Decimal(str(product.quantity_on_hand or 0))
                - Decimal(str(existing_reservations.get(product_id, 0)))
            )
            if quantity > available:
                shortages.append(
                    f"{product}: المطلوب {quantity} والمتاح بعد الحجوزات {available}"
                )
        if shortages:
            raise ValidationError(
                "لا يمكن تأكيد الطلبية لعدم كفاية الكمية: " + "؛ ".join(shortages)
            )

        locked.status = SalesOrder.STATUS_CONFIRMED
        locked.reserved_until = default_order_reserved_until(locked.tenant_id)
        locked.save(update_fields=["status", "reserved_until"])

    log_order_activity(
        locked, action="update", description="تأكيد طلبية وحجز الكمية", user=user)
    logger.info(
        "sales_order.confirm order=%s tenant=%s reserved_until=%s",
        locked.id, locked.tenant_id, locked.reserved_until,
    )
    return locked


def convert_quotation_to_order(quotation, *, user=None):
    """عرض سعر → طلبية مؤكَّدة تحجز الكمية حتى `reserved_until`.

    idempotent: العرض المحوَّل أو الملغى لا يُحوَّل ثانيةً.
    """
    from .models import SalesOrder, SalesOrderLine, SalesQuotation

    if quotation.status in (SalesQuotation.STATUS_CONVERTED, SalesQuotation.STATUS_CANCELLED):
        raise ValidationError(
            f"عرض السعر {quotation.quotation_number} بحالة "
            f"«{quotation.get_status_display()}» — لا يقبل التحويل."
        )

    tenant_id = quotation.tenant_id
    with transaction.atomic():
        order = SalesOrder.objects.create(
            tenant=quotation.tenant,
            order_number=next_order_number(tenant_id),
            customer=quotation.customer,
            order_date=quotation.quotation_date,
            reserved_until=default_order_reserved_until(tenant_id),
            status=SalesOrder.STATUS_CONFIRMED,
            currency=quotation.currency,
            exchange_rate=quotation.exchange_rate,
            discount_amount=quotation.discount_amount,
            tax_amount=quotation.tax_amount,
            quotation=quotation,
            notes=quotation.notes or "",
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
        for ln in quotation.lines.all():
            SalesOrderLine.objects.create(
                tenant=quotation.tenant,
                order=order,
                product=ln.product,
                quantity=ln.quantity,
                unit_price=ln.unit_price,
                line_discount=ln.line_discount,
                tax_rate=ln.tax_rate,
            )
        _recalculate_order_totals(order)
        quotation.status = SalesQuotation.STATUS_CONVERTED
        quotation.save(update_fields=["status"])

    log_order_activity(
        order, action="create", description="طلبية من عرض سعر", user=user)
    logger.info(
        "sales_order.from_quotation order=%s quotation=%s tenant=%s reserved_until=%s",
        order.id, quotation.id, tenant_id, order.reserved_until,
    )
    return order


def convert_order_to_invoice(order, *, user=None):
    """طلبية → فاتورة بيع (مسودة). التحويل ينهي الحجز — البضاعة صارت مفوترة."""
    from .models import SalesInvoice, SalesOrder
    from .serializers import SalesInvoiceSerializer

    if order.status == SalesOrder.STATUS_CONVERTED and order.invoice_id:
        raise ValidationError(
            f"الطلبية {order.order_number} محوّلة أصلاً إلى فاتورة "
            f"#{order.invoice.invoice_number}."
        )
    if order.status == SalesOrder.STATUS_CANCELLED:
        raise ValidationError(f"الطلبية {order.order_number} ملغاة — لا تُحوَّل.")

    lines_data = [
        {
            "product": ln.product_id,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "line_discount": ln.line_discount,
            "tax_rate": ln.tax_rate_id,
        }
        for ln in order.lines.all()
    ]
    inv_ser = SalesInvoiceSerializer(data={
        "invoice_number": next_invoice_number(order.tenant_id),
        "customer": order.customer_id,
        "invoice_date": order.order_date,
        "currency": order.currency_id,
        "exchange_rate": order.exchange_rate,
        "invoice_type": "credit",
        "invoice_discount": order.discount_amount,
        "lines": lines_data,
    })
    if not inv_ser.is_valid():
        raise ValidationError(f"بيانات الفاتورة غير صالحة: {inv_ser.errors}")

    with transaction.atomic():
        invoice = inv_ser.save(
            tenant=order.tenant,
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
        order.invoice = invoice
        order.status = SalesOrder.STATUS_CONVERTED
        # انتهاء الحجز: الكمية لم تعد محجوزة بل مفوترة.
        order.reserved_until = None
        order.save(update_fields=["invoice", "status", "reserved_until"])

    log_order_activity(
        order, action="convert", description=f"تحويل طلبية إلى فاتورة {invoice.invoice_number}",
        user=user)
    logger.info(
        "sales_order.to_invoice order=%s invoice=%s tenant=%s",
        order.id, invoice.id, order.tenant_id,
    )
    return invoice


def cancel_sales_order(order, *, user=None, reason: str = ""):
    """إلغاء طلبية — تبقى في السجل ويُفرَج عن حجزها فوراً (لا حذف)."""
    from .models import SalesOrder

    if order.status == SalesOrder.STATUS_CONVERTED:
        raise ValidationError("الطلبية محوّلة إلى فاتورة — ألغِ الفاتورة بدلاً منها.")
    if order.status == SalesOrder.STATUS_CANCELLED:
        return order
    order.status = SalesOrder.STATUS_CANCELLED
    order.cancel_reason = (reason or "")[:250]
    order.reserved_until = None
    order.save(update_fields=["status", "cancel_reason", "reserved_until"])
    log_order_activity(order, action="cancel", description=reason or "إلغاء طلبية", user=user)
    logger.info("sales_order.cancel order=%s tenant=%s", order.id, order.tenant_id)
    return order


def cancel_quotation(quotation, *, user=None, reason: str = ""):
    """إلغاء عرض سعر — بديل الحذف: المستند وسجلّه يبقيان."""
    from .models import SalesQuotation

    if quotation.status == SalesQuotation.STATUS_CONVERTED:
        raise ValidationError("عرض السعر محوَّل — ألغِ المستند الناتج عنه بدلاً منه.")
    if quotation.status == SalesQuotation.STATUS_CANCELLED:
        return quotation
    quotation.status = SalesQuotation.STATUS_CANCELLED
    quotation.save(update_fields=["status"])
    from core.activity import log_activity
    log_activity(
        action="cancel", entity_type="sales_quotation", entity_id=quotation.id,
        entity_label=quotation.quotation_number, description=reason or "إلغاء عرض سعر",
        partner_ids=[quotation.customer_id], user=user, tenant=quotation.tenant,
    )
    logger.info("sales_quotation.cancel id=%s tenant=%s", quotation.id, quotation.tenant_id)
    return quotation


def record_order_deposit(order, *, amount, cash_account_id, user=None, payment_date=None):
    """عربون الطلبية = سند قبض «على الحساب» مرحَّل ومربوط بها.

    لا قيد خاص بالطلبية: العربون مالٌ قُبض فعلاً، فيمرّ من نفس محرّك سندات
    القبض (Dr صندوق / Cr ذمم العميل) ويظهر في كشف حسابه كأي دفعة مقدمة.
    """
    from datetime import date as _date

    from .models import CustomerPayment, SalesOrder

    amount = Decimal(str(amount or 0)).quantize(DEC)
    if amount <= 0:
        raise ValidationError("مبلغ العربون يجب أن يكون أكبر من صفر.")
    if not cash_account_id:
        raise ValidationError("اختر حساب الصندوق/البنك لقبض العربون.")

    with transaction.atomic():
        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status == SalesOrder.STATUS_CANCELLED:
            raise ValidationError("الطلبية ملغاة — لا يُسجَّل عليها عربون.")
        if order.status == SalesOrder.STATUS_CONVERTED:
            raise ValidationError(
                "الطلبية محوّلة إلى فاتورة — سجّل الدفعة على الفاتورة الناتجة."
            )
        already = (
            order.deposits.filter(is_posted=True).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        if already + amount > Decimal(str(order.grand_total or 0)) + DEC:
            raise ValidationError(
                f"العربون ({already + amount}) يتجاوز إجمالي الطلبية ({order.grand_total})."
            )
        payment = CustomerPayment.objects.create(
            tenant=order.tenant,
            partner=order.customer,
            payment_date=payment_date or _date.today(),
            amount=amount,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            cash_or_bank_account_id=cash_account_id,
            sales_order=order,
            notes=f"عربون طلبية {order.order_number}"[:500],
        )
        post_customer_payment(payment, user=user)
        payment.refresh_from_db()
        order.deposit_amount = (already + amount).quantize(DEC)
        order.save(update_fields=["deposit_amount"])

    log_order_activity(
        order, action="payment", description=f"عربون {amount}", user=user)
    logger.info(
        "sales_order.deposit order=%s payment=%s tenant=%s",
        order.id, payment.id, order.tenant_id,
    )
    return payment


def log_order_activity(order, *, action: str, description: str = "", user=None) -> None:
    """سجل نشاط موحّد للطلبية — يظهر في السجل العام وفي كرت الزبون."""
    from core.activity import log_activity

    log_activity(
        action=action, entity_type="sales_order", entity_id=order.id,
        entity_label=order.order_number, description=description,
        partner_ids=[order.customer_id], user=user, tenant=order.tenant,
    )


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

    # customer/currency حقول PrimaryKeyRelatedField ⇒ تُمرَّر كـ pk لا ككائن،
    # وtenant/created_by يُحقنان عبر save() تماماً كما يفعل الـ ViewSet (لا حقول
    # على الـ serializer). خلاف ذلك يرفض الـ serializer الكائنات:
    # "Incorrect type. Expected pk value, received Partner/Currency."
    inv_data = {
        "invoice_number": invoice_number,
        "customer": quotation.customer_id,
        "invoice_date": quotation.quotation_date,
        "currency": quotation.currency_id,
        "exchange_rate": quotation.exchange_rate,
        "invoice_type": "credit",
        "lines": lines_data,
    }

    inv_ser = SalesInvoiceSerializer(data=inv_data)
    if not inv_ser.is_valid():
        raise ValueError(f"بيانات الفاتورة غير صالحة: {inv_ser.errors}")

    with transaction.atomic():
        invoice = inv_ser.save(
            tenant=tenant,
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
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

    # T-ONEPAY: شيكات داخل السند — مبلغها جزء من مبلغ السند لا إضافة عليه، ولا
    # يخرج من الصندوق بل يصير التزاماً على «شيكات برسم الدفع» حتى يُصرف.
    total = Decimal(str(payment.amount)).quantize(DEC)
    payment_cheques = list(payment.cheques.all()) if payment.pk else []
    cheques_total = sum(
        (Decimal(str(c.amount or 0)) for c in payment_cheques), Decimal("0")
    ).quantize(DEC)
    if cheques_total > total + DEC:
        raise ValidationError(
            f"مجموع الشيكات ({cheques_total}) يتجاوز مبلغ السند ({total})."
        )
    cash_part = (total - cheques_total).quantize(DEC)

    credit_lines: list[dict] = []
    if cash_part > 0:
        credit_lines.append({
            "account": payment.cash_or_bank_account_id,
            # T-CASH2: حساب الصندوق/البنك لا يَحمل المورد — وإلا حُسبت
            # حركة النقدية ضمن ذمم المورد فلا يُصفّر السند رصيده. فقط
            # سطر الذمم (AP) يَحمل الشريك.
            "partner": None,
            "debit": Decimal("0"),
            "credit": cash_part,
            "description": f"من الصندوق — {payment.partner.name}",
        })
    if cheques_total > 0:
        payable_acc = resolve_cheques_payable_account(payment.tenant_id)
        credit_lines.append({
            "account": payable_acc.id,
            "partner": None,
            "debit": Decimal("0"),
            "credit": cheques_total,
            "description": f"شيكات صادرة — {payment.partner.name}",
        })

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
                    "debit": total,
                    "credit": Decimal("0"),
                    "description": f"دفع مورد — {payment.partner.name}",
                },
                *credit_lines,
            ],
            currency=payment.currency,
            exchange_rate=payment.exchange_rate,
            user=user,
        )
        payment.journal = jh
        payment.is_posted = True
        payment.save(update_fields=["journal", "is_posted"])
        # الشيكات الصادرة تخرج من المسودة بترحيل السند (كما في الجانب الوارد).
        if payment_cheques:
            from accounting.models import Cheque
            Cheque.objects.filter(
                supplier_payment=payment, status="Draft"
            ).update(status="Under_Collection")
        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="POST",
            model_name="SupplierPayment",
            object_id=payment.id,
            change_details=f"Posted supplier payment journal={jh.id}",
        )
    return payment


def allocate_supplier_payment(
    payment: 'SupplierPayment', allocations: list[dict], *, user=None
) -> 'SupplierPayment':
    """T-ONACC (المورد): توزيع سند صرف على فواتير شراء — مرآة
    `allocate_customer_payment`.

    بعد الترحيل التوزيع **ربط فقط بلا قيد جديد**: ذمم المورد دُينت وقت الترحيل
    (Dr AP / Cr صندوق) فالتوزيع لا يغيّر أي رصيد دفتري — يحدّد فقط أي فاتورة
    استهلكت أي جزء من السند (يقود `purchase_invoice_payment_summary`).
    """
    from logistics.models import PurchaseInvoice
    from logistics.services import purchase_invoice_payment_summary
    from sales.models import SupplierPayment as SP, SupplierPaymentAllocation

    rows = [
        (int(a["invoice"]), Decimal(str(a.get("amount") or "0")))
        for a in (allocations or [])
    ]
    if not rows:
        raise ValidationError("لا توزيعات مُرسَلة.")
    if any(amt <= 0 for _inv_id, amt in rows):
        raise ValidationError("مبلغ التوزيع يجب أن يكون أكبر من صفر.")

    with transaction.atomic():
        payment = SP.objects.select_for_update().get(pk=payment.pk)
        already = (
            SupplierPaymentAllocation.objects.filter(payment=payment).aggregate(
                t=Sum("amount")
            )["t"]
            or Decimal("0")
        )
        total_new = sum((amt for _inv_id, amt in rows), Decimal("0"))
        if already + total_new > Decimal(str(payment.amount)) + DEC:
            raise ValidationError(
                f"مجموع التوزيعات ({already + total_new}) يتجاوز مبلغ السند "
                f"({payment.amount}). المتاح للتوزيع: {Decimal(str(payment.amount)) - already}."
            )

        invoices = {
            inv.pk: inv
            for inv in PurchaseInvoice.objects.select_for_update().filter(
                pk__in={inv_id for inv_id, _amt in rows}, tenant_id=payment.tenant_id
            )
        }
        for inv_id, amt in rows:
            inv = invoices.get(inv_id)
            if inv is None:
                raise ValidationError(f"فاتورة الشراء #{inv_id} غير موجودة في هذه الشركة.")
            if inv.partner_id != payment.partner_id:
                raise ValidationError(
                    f"فاتورة الشراء #{inv.invoice_number} لا تخص نفس المورد."
                )
            if not inv.is_posted:
                raise ValidationError(f"فاتورة الشراء #{inv.invoice_number} غير مرحّلة.")

            if payment.currency_id == inv.currency_id:
                amount_in_inv_curr, conv_rate = amt, Decimal("1")
            else:
                amount_in_inv_curr, conv_rate = convert_amount(
                    amount=amt,
                    from_currency_id=payment.currency_id,
                    to_currency_id=inv.currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
            remaining = purchase_invoice_payment_summary(inv)["remaining_balance"]
            if amount_in_inv_curr > remaining + DEC:
                raise ValidationError(
                    f"مبلغ التوزيع ({amount_in_inv_curr}) يتجاوز المتبقي على "
                    f"فاتورة الشراء #{inv.invoice_number} ({remaining})."
                )

            SupplierPaymentAllocation.objects.create(
                tenant_id=payment.tenant_id,
                payment=payment,
                invoice=inv,
                amount=amt,
                amount_in_invoice_currency=amount_in_inv_curr,
                conversion_rate=conv_rate,
            )
            # ملخّص الدفع مُخزَّن على الكائن — نُبطله كي يعكس التوزيع الجديد.
            inv._payment_summary_cache = None
            logger.info(
                "Supplier payment %s allocated %s → purchase invoice %s",
                payment.id, amt, inv.invoice_number,
            )

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="ALLOCATE",
            model_name="SupplierPayment",
            object_id=payment.id,
            change_details=(
                f"Allocated {total_new} to {len(rows)} purchase invoice(s); "
                f"total allocated={already + total_new} of {payment.amount}"
            ),
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

        # task11 R2-A2: المراجيع تُخصم لا تُضاف — مرجع البيع يخفّض ضريبة
        # المخرجات ومرجع الشراء يخفّض ضريبة المدخلات (كانت تُجمع موجبة
        # فيتضخم الكشف من الجهتين).
        for inv in invoices:
            amt = Decimal(str(inv.tax_amount or 0))
            if inv.invoice_kind == SalesInvoice.INVOICE_KIND_SALE:
                total_sales_vat += amt
            elif inv.invoice_kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
                total_sales_vat -= amt
            elif inv.invoice_kind == SalesInvoice.INVOICE_KIND_PURCHASE:
                total_purchase_vat += amt
            else:  # purchase_return
                total_purchase_vat -= amt

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

