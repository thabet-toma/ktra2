"""
ترحيل فواتير المبيعات، حركة المخزون، وتحصيل العملاء.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

from accounting.models import Account, JournalLine
from accounting.services import (
    convert_amount,
    create_audit_log,
    post_journal,
    resolve_forex_account,
    unpost_document,
    validate_fiscal_period,
    validate_journal_entry,
)
from inventory.models import Product, StockMovement
from inventory.serials import (
    consume_sales_serials,
    release_sales_serials,
    restore_returned_sales_serials,
)
from inventory.services import record_stock_movement
from partners.models import Partner, PartnerGroup
from accounting.api import ensure_partner_account
from tenants.models import Tenant

from sales.models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    DeliveryOrderLine,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")



# المرحلة 3: مراجع عبر وحدات الحزمة (نفس الملف سابقاً) — الرسم البياني لا-دوري.
from .foundation import get_or_create_sales_settings, resolve_default_account
from .pricing import invoice_profits

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
    # T-DEFACC: حساب الزبون نفسه في الشجرة أولاً. حساب المجموعة هو أب الذمم العام
    # (المدينون التجاريون) — استعماله كان يخلط كل الزبائن في حساب واحد فيضيع
    # كشف الحساب التفصيلي، مع أن للزبون حسابه المولَّد تحت الأب أصلاً.
    p = ensure_partner_account(p) or p
    if p.linked_account_id:
        return p.linked_account
    if p.group_id:
        g = PartnerGroup.objects.filter(pk=p.group_id).first()
        if g and g.account_receivable_id:
            return g.account_receivable
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


def resolve_product_revenue_account(tenant_id: int) -> Account:
    """ISSUE #59: حساب «مبيعات المنتجات» — يُطابَق من الشجرة أو يُنشأ ويُثبَّت.

    نظير `resolve_service_revenue_account` على جانب المنتج: كان بيع البضاعة
    يرتدّ إلى أوّل حساب إيراد **بالكود** متى كان `default_revenue_account_product`
    فارغاً — وهو رأس شجرة الإيرادات «4» في دليل الحسابات المعياري (`'4' < '41'
    < '4101'`)، حسابٌ أب لا يصلح هدفاً للترحيل. التثبيت على الإعدادات يمنع
    إنشاء حساب ثانٍ في المرة التالية.
    """
    ss = get_or_create_sales_settings(tenant_id)
    if ss.default_revenue_account_product_id:
        return ss.default_revenue_account_product

    account = resolve_default_account(
        tenant_id, ["4101", "41"], "Revenue", "مبيعات", allow_any_of_type=False
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
            code="4101",
            defaults={
                "name": "مبيعات المنتجات",
                "account_type": "Revenue",
                "is_active": True,
                "parent": parent.parent if parent else None,
            },
        )
        if created:
            logger.info(
                "sales.product_revenue_account.created tenant=%s account=%s",
                tenant_id, account.pk,
            )
    ss.default_revenue_account_product = account
    ss.save(update_fields=["default_revenue_account_product"])
    return account


def _default_revenue_account(tenant_id: int, *, is_service: bool = False) -> Account:
    """يفضّل الحساب من إعدادات المبيعات (منتج/خدمة)، وإلا يحلّه وينشئه.

    ISSUE #59 / T-SERVICELINE: كلا الجانبين له حسابه دائماً — لا ارتداد إلى
    حساب الآخر ولا إلى رأس شجرة الإيرادات.
    """
    if is_service:
        return resolve_service_revenue_account(tenant_id)
    return resolve_product_revenue_account(tenant_id)


def _resolve_revenue_account_for_line(invoice: SalesInvoice, line: SalesInvoiceLine) -> Account:
    p = line.product
    is_service = bool(getattr(p, "is_service", False))

    # ISSUE #78: تجاوز المنتج (`sale_account_override`) يسري على الخدمة أيضاً —
    # حسابات الأتعاب المزروعة مع قالب «مكتب محاسبة» (4103-4106) كانت ميتة لأن
    # هذا التجاوز وحده كان محروساً بـ`not is_service`. لا تُستدعى
    # `_resolve_line_account` كاملةً للخدمة: سلسلتها الداخلية (تصنيف ← إعدادات
    # ← 4101 مقطوع) منتجيّة الطابع وتُسقط الخدمة إلى حساب البضاعة بدل حساب
    # الخدمات العام. تجاوزا الفاتورة والتصنيف أدناه يبقيان محروسَين كما كانا.
    if is_service:
        if p.sale_account_override_id:
            return p.sale_account_override
    else:
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
        raise ValidationError("بعض منتجات الفاتورة غير موجودة أو مكررة.")
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
                f"المنتج «{p.sku}» — الفئة «{cname}»: عيّن حساب تكلفة المبيعات والمخزون في فئة المنتج "
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
    الحارس). يسمّي الأسطر المخالفة بالعربية (اسم المنتج + التكلفة مقابل صافي البيع).
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
        # CHQ-2: «شيكات في المحفظة» (1109) صار موجوداً في كل شجرة يمرّ بها شيك
        # وارد، واسمه يحوي «شيكات» أيضاً — فمطابقة الاسم المفتوحة قد تعيده هنا
        # في شركة بلا 1107، فيقع قيد الإيداع (1107 ÷ 1109) بطرفيه على الحساب
        # نفسه: **متوازن**، فلا تكشفه موازنة ولا تأكيد رصيد. يُستثنى صراحةً كما
        # في `accounting/services.py` (`_resolve_cheque_under_collection_account`).
        from accounting.services import CHEQUES_IN_HAND_CODE

        uc_acc = (
            Account.objects.filter(
                tenant_id=tenant_id,
                account_type="Asset",
                is_active=True,
                name__icontains="شيكات",
            )
            .exclude(code=CHEQUES_IN_HAND_CODE)
            .exclude(name__icontains="المحفظة")
            .order_by("code")
            .first()
        )
    if not uc_acc:
        # T-CHQ3/هـ: كان يُرفض الترحيل ويُطلب من المستخدم تعيين الحساب بنفسه،
        # فيقف عمله عند أول شيك في شركة شجرتها ناقصة. الحساب المعياري يُنشأ
        # من الكود، ويبقى قابلاً للتغيير من إعدادات المبيعات.
        from tenants.services import ensure_operational_account
        uc_acc = ensure_operational_account(
            ss.tenant if ss else Tenant.objects.get(pk=tenant_id), "1107")
    if not uc_acc:
        raise ValidationError(
            "توجد شيكات واردة لكن تعذّر إنشاء حساب «شيكات برسم التحصيل». "
            "عيّن `default_cheques_under_collection_account` في إعدادات المبيعات."
        )
    # يُثبَّت في الإعدادات كي يظهر للمالك ويغيّره إن أراد حساباً آخر.
    if ss and not ss.default_cheques_under_collection_account_id:
        ss.default_cheques_under_collection_account = uc_acc
        ss.save(update_fields=["default_cheques_under_collection_account"])
    return uc_acc


def resolve_cheques_payable_account(tenant_id: int) -> Account:
    """حساب «شيكات برسم الدفع» — مرآة حساب الشيكات الواردة للجانب الدائن.

    الشيك الصادر ليس نقداً خرج من الصندوق بل التزام حتى يُصرف، فيُدائَن حساب
    التزام مستقل. T-CHQ2: الحساب المبذور 2111 أولاً (مرآة 1107 للوارد) ثم
    مطابقة الاسم للشجرات القديمة، وبلا حساب مطابق يُرفض الترحيل صراحةً بدل
    تحميل الصندوق ما لم يخرج منه.
    """
    base = Account.objects.filter(
        tenant_id=tenant_id, account_type="Liability", is_active=True,
    )
    acc = (
        base.filter(code="2111").first()
        or base.filter(name__icontains="شيكات").order_by("code").first()
    )
    if not acc:
        # T-CHQ3/هـ: مرآة حساب الوارد — يُنشأ من الكود بدل ردّ المستخدم.
        from tenants.services import ensure_operational_account
        acc = ensure_operational_account(Tenant.objects.get(pk=tenant_id), "2111")
    if not acc:
        raise ValidationError(
            "يوجد شيك صادر لكن تعذّر إنشاء حساب «شيكات برسم الدفع»."
        )
    return acc


