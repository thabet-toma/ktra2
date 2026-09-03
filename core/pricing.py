"""Shared price-resolution service (FEAT-1 purchase + FEAT-2 sales auto-pricing).

A single strategy-pattern resolver consumed by BOTH the purchase-invoice line
auto-pricing (FEAT-1) and the sales-invoice line customer-pricing (FEAT-2).
The UI layer never duplicates the price-lookup logic — it calls one of the two
public entry points below (or `PriceResolver.resolve`).

Design rules (per [ARCHITECTURE]):
- Reads ONLY canonical posted documents (PurchaseInvoiceItem / SalesInvoiceLine)
  plus the product's own standard cost / default selling price. No parallel
  price store (the legacy `supplier_prices` mapper collection is bypassed) — so
  every suggestion reconciles to the ledger.
- Currency normalization uses the per-document exchange rate (Currency carries
  no rate field). A historical price is taken to base currency via the source
  document's rate, then to the target invoice currency via its rate. A fallback
  whose currency cannot be reconciled to the target is skipped — never mix
  currencies.
- Tax-inclusive/exclusive basis follows the existing invoice convention. A
  source price recorded under a different convention is converted using the
  line's tax rate so the returned value matches the target convention.
- Every resolution path is logged (strategy, inputs, resolved value).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Unit prices are stored at 4 decimal places (see SalesInvoiceLine.unit_price).
_UNIT_Q = Decimal("0.0001")
_ZERO = Decimal("0")


class PriceStrategy:
    """Supported resolution strategies."""

    LAST_PURCHASE = "LAST_PURCHASE"
    LOWEST_PURCHASE = "LOWEST_PURCHASE"
    LAST_SALE_TO_CUSTOMER = "LAST_SALE_TO_CUSTOMER"
    DEFAULT = "DEFAULT"

    PURCHASE_CHOICES = (LAST_PURCHASE, LOWEST_PURCHASE)
    ALL = (LAST_PURCHASE, LOWEST_PURCHASE, LAST_SALE_TO_CUSTOMER, DEFAULT)


def _dec(value, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _convert_currency(amount: Decimal, *, source_rate: Decimal, target_rate: Decimal) -> Decimal:
    """Re-express `amount` (in the source document currency) into the target
    invoice currency, bridging through base currency.

    base = amount * source_rate ;  target = base / target_rate
    """
    src = source_rate if source_rate and source_rate > 0 else Decimal("1")
    tgt = target_rate if target_rate and target_rate > 0 else Decimal("1")
    base = amount * src
    return base / tgt


def _convert_tax_basis(
    amount: Decimal,
    *,
    source_inclusive: bool,
    target_inclusive: bool,
    tax_percent: Decimal,
) -> Decimal:
    """Convert a unit price between tax-inclusive and tax-exclusive bases.

    No-op when the conventions match or the tax rate is zero.
    """
    if source_inclusive == target_inclusive or not tax_percent:
        return amount
    factor = Decimal("1") + (_dec(tax_percent) / Decimal("100"))
    if factor <= 0:
        return amount
    if source_inclusive and not target_inclusive:
        # strip the embedded tax
        return amount / factor
    # exclusive -> inclusive: add the tax
    return amount * factor


def _blank(strategy: str, *, reason: str) -> dict:
    return {
        "unit_price": None,
        "strategy_used": None,
        "strategy_requested": strategy,
        "source": None,
        "reason": reason,
    }


def _resolved(
    price: Decimal,
    *,
    strategy_requested: str,
    strategy_used: str,
    source: dict | None,
) -> dict:
    return {
        "unit_price": str(price.quantize(_UNIT_Q)),
        "strategy_used": strategy_used,
        "strategy_requested": strategy_requested,
        "source": source,
        "reason": None,
    }


# ──────────────────────────────────────────────────────────────────────────
# FEAT-1 — purchase line auto-pricing
# ──────────────────────────────────────────────────────────────────────────
def resolve_purchase_price(
    *,
    tenant_id: int,
    product_id: int,
    strategy: str | None = None,
    supplier_id: int | None = None,
    target_currency_id: int | None = None,
    target_exchange_rate: Decimal | str | float = Decimal("1"),
) -> dict:
    """Resolve a purchase unit price for a product per the active strategy.

    `supplier_id` (اختياري): «آخر شراء» يُحصر بذلك المورد وحده — أما «أقل شراء»
    فيبقى عاماً عبر كل الموردين. إن لم يسبق الشراء من هذا المورد يُرجَع أقل سعر
    عام (مطابقةً لما تعرضه `purchase_price_list`).

    Fallback chain: posted-purchase history (per strategy) → product standard
    cost (`avg_cost`, base currency) → blank.
    """
    from inventory.models import Product
    from logistics.models import PurchaseInvoiceItem

    strategy = strategy if strategy in PriceStrategy.PURCHASE_CHOICES else PriceStrategy.LAST_PURCHASE
    target_rate = _dec(target_exchange_rate, Decimal("1"))

    qs = PurchaseInvoiceItem.objects.filter(
        invoice__tenant_id=tenant_id,
        invoice__is_posted=True,
        product_id=product_id,
    ).select_related("invoice", "invoice__currency", "line_currency")

    chosen = None
    strategy_used = strategy
    if strategy == PriceStrategy.LOWEST_PURCHASE:
        chosen = _lowest_purchase_item(qs)
    else:  # LAST_PURCHASE — most recent posted purchase invoice
        last_qs = qs.filter(unit_price__gt=0)
        if supplier_id:
            last_qs = last_qs.filter(invoice__partner_id=supplier_id)
        chosen = last_qs.order_by("-invoice__invoice_date", "-invoice_id", "-id").first()
        if chosen is None and supplier_id:
            # لم يسبق الشراء من هذا المورد → أقل سعر عام (كل الموردين).
            chosen = _lowest_purchase_item(qs)
            if chosen is not None:
                strategy_used = PriceStrategy.LOWEST_PURCHASE

    if chosen is not None:
        src_rate = _src_purchase_rate(chosen)
        price = _convert_currency(
            _dec(chosen.unit_price), source_rate=src_rate, target_rate=target_rate
        )
        result = _resolved(
            price,
            strategy_requested=strategy,
            strategy_used=strategy_used,
            source={
                "document_type": "PURCHASE_INVOICE",
                "document_id": chosen.invoice_id,
                "document_number": chosen.invoice.invoice_number,
                "document_date": chosen.invoice.invoice_date.isoformat()
                if chosen.invoice.invoice_date
                else None,
            },
        )
        logger.info(
            "price_resolve purchase tenant=%s product=%s strategy=%s supplier=%s used=%s -> %s (src_invoice=%s)",
            tenant_id, product_id, strategy, supplier_id, strategy_used,
            result["unit_price"], chosen.invoice_id,
        )
        return result

    # Fallback: product standard / last-known cost (avg_cost is base currency).
    product = Product.objects.filter(id=product_id, tenant_id=tenant_id).only("avg_cost").first()
    if product and _dec(product.avg_cost) > 0:
        price = _convert_currency(
            _dec(product.avg_cost), source_rate=Decimal("1"), target_rate=target_rate
        )
        result = _resolved(
            price,
            strategy_requested=strategy,
            strategy_used=PriceStrategy.DEFAULT,
            source={"document_type": "PRODUCT_AVG_COST", "document_id": product_id},
        )
        logger.info(
            "price_resolve purchase tenant=%s product=%s strategy=%s fallback=avg_cost -> %s",
            tenant_id, product_id, strategy, result["unit_price"],
        )
        return result

    logger.info(
        "price_resolve purchase tenant=%s product=%s strategy=%s -> blank (no history/cost)",
        tenant_id, product_id, strategy,
    )
    return _blank(strategy, reason="no_history")


def purchase_price_list(
    *, tenant_id: int, strategy: str | None = None, supplier_id: int | None = None,
) -> dict[int, dict]:
    """task24: سعر الشراء المقترح لكل المنتجات دفعة واحدة (لعرضه داخل خيارات
    منتقي المنتجات في فاتورة الشراء بلا نقر).

    يُرجع {product_id: {"unit_price", "source_type", "source_label", "prices"}}.
    `unit_price` هو **آخر** سعر شراء (وهو ما تُعبَّأ به الخلية)، و`prices` تعرض
    «آخر شراء» و«أقل شراء» معاً دائماً عند وجود تاريخ (بصرف النظر عن الاستراتيجية).
    `supplier_id` (اختياري): «آخر شراء» يُحصر بذلك المورد وحده بوسم «آخر شراء من
    المورد»، بينما «أقل شراء» يبقى عاماً عبر كل الموردين؛ وإن لم يسبق الشراء من
    هذا المورد تُعبَّأ الخلية بأقل سعر عام.
    «آخر شراء» أحادي العملة كما سُجِّل — تحويل العملة لكل سطر يبقى في
    `resolve_purchase_price`. أما «أقل شراء» (ISSUE #111) فبالعملة **الأساسية**
    مُحوَّلاً بسعر صرف فاتورته هو (لا سعر اليوم)، ومعه المورد والتاريخ — انظر
    `_purchase_lowest_prices_base_currency`.
    السلسلة: تاريخ الشراء المرحَّل ← متوسط تكلفة المنتج (لـ«آخر شراء» فقط، ولا
    يُستعمَل أبداً لـ«أقل شراء») ← لا شيء. (`strategy` يبقى للتوافق مع نداء الـ
    endpoint ولا يؤثّر على القيمة الأساسية هنا.)
    """
    from inventory.models import Product
    from logistics.models import PurchaseInvoiceItem

    qs = (
        PurchaseInvoiceItem.objects.filter(
            invoice__tenant_id=tenant_id,
            invoice__is_posted=True,
            unit_price__gt=0,
        )
        .select_related("invoice")
        .order_by("product_id", "-invoice__invoice_date", "-invoice_id", "-id")
    )
    result: dict[int, dict] = {}
    for item in qs:
        unit = _dec(item.unit_price)
        cur = result.setdefault(item.product_id, {"last": None})

        if cur["last"] is None and (
            not supplier_id or item.invoice.partner_id == supplier_id
        ):
            cur["last"] = {
                "unit_price": str(unit.quantize(_UNIT_Q)),
                "source_type": "PURCHASE_INVOICE",
                "source_label": "آخر شراء من المورد" if supplier_id else "آخر شراء",
                "document_id": item.invoice_id,
            }

    # ISSUE #111: «أقل شراء» بالعملة الأساسية — تجميعٌ واحد في SQL عبر كل
    # المنتجات دفعة واحدة، لا مقارنة بايثون على أرقام بعملات مختلفة.
    lowest_by_product = _purchase_lowest_prices_base_currency(tenant_id=tenant_id)

    # احتياطي: متوسط تكلفة المنتج لمن لا تاريخ شراء له — لـ«آخر شراء» وحدها.
    # «أقل شراء» لا يسقط إلى avg_cost أبداً (ISSUE #111 #5): متوسط التكلفة ليس
    # سعر سوق.
    for p in Product.objects.filter(tenant_id=tenant_id).only("id", "avg_cost"):
        if p.id in result:
            continue
        cost = _dec(p.avg_cost)
        if cost > 0:
            result[p.id] = {
                "last": {
                    "unit_price": str(cost.quantize(_UNIT_Q)),
                    "source_type": "PRODUCT_AVG_COST",
                    "source_label": "متوسط التكلفة",
                    "document_id": None,
                },
            }

    final_result: dict[int, dict] = {}
    all_product_ids = set(result.keys()) | set(lowest_by_product.keys())
    for pid in all_product_ids:
        data = result.get(pid) or {}
        last = data.get("last")
        lowest = lowest_by_product.get(pid)

        prices = []
        if last:
            prices.append(last)
        # القائمة تعرض «آخر شراء» و«أقل شراء» معاً دائماً عند وجود تاريخ شراء (بصرف
        # النظر عن الاستراتيجية) ليطّلع المستخدم على الاثنين؛ القيمة الأساسية
        # (unit_price) هي آخر سعر إن وُجد، وإلا أقل سعر (بالأساسية). لا تكرار:
        # إن كان «أقل شراء» نفس مستند «آخر شراء» تُعرض رقاقة واحدة.
        if lowest and not (last and last["document_id"] == lowest["document_id"]):
            prices.append(lowest)

        if prices:
            final_result[pid] = {
                "unit_price": prices[0]["unit_price"],
                "source_type": prices[0]["source_type"],
                "source_label": prices[0]["source_label"],
                "prices": prices,
            }

    logger.info(
        "price_list purchase tenant=%s supplier=%s -> %s products",
        tenant_id, supplier_id, len(final_result),
    )
    return final_result


def _purchase_lowest_prices_base_currency(
    *, tenant_id: int, product_ids=None,
) -> dict[int, dict]:
    """ISSUE #111: أقل سعر شراء لكل منتج، **بالعملة الأساسية**، مُحوَّلاً بسعر
    صرف فاتورته هو (سعرُ الأمس بصرف الأمس — لا سعر اليوم). المصدر فواتيرُ
    الشراء المرحَّلة وحدها، ولا سقوطَ إلى `avg_cost` أبداً: منتجٌ بلا شراء
    مرحَّل ببساطة **لا يظهر** في القاموس المُعاد.

    تجميعٌ واحد في SQL عبر كل المنتجات المطلوبة دفعة واحدة (استعلامٌ واحد
    بترتيبٍ على القيمة المحوَّلة محسوبةً في قاعدة البيانات) — لا استعلامٌ لكل
    منتج ولا استعلامٌ مترابط (correlated) لكل صفّ (درس
    `correlated-subquery-on-lists`: 17 ثانية لصفحةٍ واحدة).

    يُرجع {product_id: {"unit_price" (أساسية), "source_type", "source_label",
    "document_id", "document_number", "document_date", "supplier_id",
    "supplier_name"}}.
    """
    from django.db.models import Case, DecimalField, ExpressionWrapper, F, Value, When

    from logistics.models import PurchaseInvoiceItem

    # سعر صرف السطر إن وُجد وإلا سعر صرف الفاتورة (مطابقةً لـ `_src_purchase_rate`).
    # وصفرُ الصرف يُعامَل واحداً لا صفراً: لولا ذلك لصارت فاتورةٌ بسعر صرفٍ
    # صفر «أقلَّ شراءٍ» أبديّاً بقيمة صفر — كذبةٌ صامتة تتصدّر كل مقارنة.
    eff_rate = Case(
        When(line_exchange_rate__gt=0, then=F("line_exchange_rate")),
        When(invoice__exchange_rate__gt=0, then=F("invoice__exchange_rate")),
        default=Value(Decimal("1")),
        output_field=DecimalField(max_digits=18, decimal_places=6),
    )
    base_price_expr = ExpressionWrapper(
        F("unit_price") * eff_rate,
        output_field=DecimalField(max_digits=24, decimal_places=6),
    )

    qs = PurchaseInvoiceItem.objects.filter(
        invoice__tenant_id=tenant_id,
        invoice__is_posted=True,
        unit_price__gt=0,
    )
    if product_ids is not None:
        qs = qs.filter(product_id__in=product_ids)

    # استعلامٌ واحد: التحويل والترتيب على القيمة المحوَّلة يحدثان في قاعدة
    # البيانات؛ أولّ سطر لكل منتج (بعد الترتيب) هو أقلّ سعرٍ بالأساسية —
    # ومرور بايثون بعدها خطّيٌّ واحد (لا متداخل) لالتقاط رأس كل مجموعة فقط.
    rows = (
        qs.annotate(base_price=base_price_expr)
        .select_related("invoice", "invoice__partner")
        .order_by("product_id", "base_price", "invoice__invoice_date", "invoice_id", "id")
    )

    result: dict[int, dict] = {}
    for item in rows:
        pid = item.product_id
        if pid in result:
            continue  # المنتج مُعالَج — الصفّ الحالي أعلى من أقلّه بالترتيب
        price = _dec(item.base_price)
        inv = item.invoice
        result[pid] = {
            "unit_price": str(price.quantize(_UNIT_Q)),
            "source_type": "PURCHASE_INVOICE",
            "source_label": "أقل شراء",
            "document_id": inv.id,
            "document_number": inv.invoice_number,
            "document_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            "supplier_id": inv.partner_id,
            "supplier_name": inv.partner.name if inv.partner_id else None,
        }
    return result


def _lowest_purchase_item(qs):
    """أقل سعر شراء عبر **كل** الموردين. تُقارَن الأسعار بعملة الأساس ليكون
    التاريخ متعدّد العملات عادلاً (A2: كل الفترات)."""
    best_base: Decimal | None = None
    chosen = None
    for item in qs:
        unit = _dec(item.unit_price)
        if unit <= 0:
            continue
        src_rate = _src_purchase_rate(item)
        base = unit * (src_rate if src_rate > 0 else Decimal("1"))
        if best_base is None or base < best_base:
            best_base = base
            chosen = item
    return chosen


def _src_purchase_rate(item) -> Decimal:
    """Source exchange rate for a purchase line: per-line override, else invoice."""
    rate = _dec(getattr(item, "line_exchange_rate", None), _ZERO)
    if rate > 0:
        return rate
    return _dec(getattr(item.invoice, "exchange_rate", None), Decimal("1"))


# ──────────────────────────────────────────────────────────────────────────
# FEAT-2 — sales line customer-based auto-pricing
# ──────────────────────────────────────────────────────────────────────────
def resolve_sales_price(
    *,
    tenant_id: int,
    product_id: int,
    customer_id: int | None = None,
    target_currency_id: int | None = None,
    target_exchange_rate: Decimal | str | float = Decimal("1"),
    target_tax_inclusive: bool = False,
) -> dict:
    """Resolve a sales unit price for a product, preferring the last price the
    given customer paid.

    Fallback chain (A3): last posted sale to this customer → product default
    selling price (sale price-tier #1, currency-matched) → blank.
    """
    from inventory.models import Product, ProductPriceTier
    from sales.models import SalesInvoice, SalesInvoiceLine

    target_rate = _dec(target_exchange_rate, Decimal("1"))

    line = None
    if customer_id:
        line = (
            SalesInvoiceLine.objects.filter(
                tenant_id=tenant_id,
                product_id=product_id,
                invoice__status=SalesInvoice.STATUS_POSTED,
                invoice__invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
                invoice__customer_id=customer_id,
            )
            .select_related("invoice", "invoice__currency", "tax_rate")
            .order_by("-invoice__invoice_date", "-invoice_id", "-id")
            .first()
        )

    if line is not None:
        inv = line.invoice
        price = _convert_currency(
            _dec(line.unit_price),
            source_rate=_dec(inv.exchange_rate, Decimal("1")),
            target_rate=target_rate,
        )
        price = _convert_tax_basis(
            price,
            source_inclusive=bool(inv.prices_include_tax),
            target_inclusive=bool(target_tax_inclusive),
            tax_percent=_dec(line.tax_rate.rate) if line.tax_rate_id and line.tax_rate else _ZERO,
        )
        result = _resolved(
            price,
            strategy_requested=PriceStrategy.LAST_SALE_TO_CUSTOMER,
            strategy_used=PriceStrategy.LAST_SALE_TO_CUSTOMER,
            source={
                "document_type": "SALES_INVOICE",
                "document_id": inv.id,
                "document_number": inv.invoice_number,
                "document_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            },
        )
        logger.info(
            "price_resolve sales tenant=%s product=%s customer=%s -> %s (src_invoice=%s)",
            tenant_id, product_id, customer_id, result["unit_price"], inv.id,
        )
        return result

    # عرض سعر «واجهة العروض» (SalesQuotation) — يُستخدم حين لم يشترِ العميل المنتج بعد.
    # أولوية أعلى من عرض كرت الزبون، وأقل من آخر بيع فعلي. يُعاد رقم/معرّف العرض للربط
    # (النقر على الشارة في الفاتورة يفتح العرض في واجهة العروض).
    if customer_id:
        from sales.models import SalesQuotationLine

        qline = (
            SalesQuotationLine.objects.filter(
                tenant_id=tenant_id,
                product_id=product_id,
                quotation__customer_id=customer_id,
            )
            .select_related("quotation")
            .order_by("-quotation__quotation_date", "-quotation_id", "-id")
            .first()
        )
        if qline is not None and _dec(qline.unit_price) > 0:
            price = _convert_currency(
                _dec(qline.unit_price), source_rate=Decimal("1"), target_rate=target_rate
            )
            price = _convert_tax_basis(
                price, source_inclusive=False, target_inclusive=bool(target_tax_inclusive),
                tax_percent=_ZERO,
            )
            result = _resolved(
                price,
                strategy_requested=PriceStrategy.LAST_SALE_TO_CUSTOMER,
                strategy_used=PriceStrategy.DEFAULT,
                source={
                    "document_type": "SALES_QUOTATION",
                    "document_id": qline.quotation_id,
                    "document_number": qline.quotation.quotation_number,
                },
            )
            logger.info(
                "price_resolve sales tenant=%s product=%s customer=%s fallback=quotation -> %s",
                tenant_id, product_id, customer_id, result["unit_price"],
            )
            return result

    # DEF-005 fallback #1: the customer's manual quote ("عرض السعر") — used only
    # when the customer has NO posted sale of this product (last-sale always wins
    # above). Sales-only, no ledger impact. Stored in base currency.
    if customer_id:
        from sales.models import CustomerProductQuote

        quote = (
            CustomerProductQuote.objects.filter(
                tenant_id=tenant_id, customer_id=customer_id, product_id=product_id,
            )
            .only("id", "unit_price")
            .first()
        )
        if quote is not None and _dec(quote.unit_price) > 0:
            price = _convert_currency(
                _dec(quote.unit_price), source_rate=Decimal("1"), target_rate=target_rate
            )
            # quote is recorded tax-exclusive (a plain entered price); only adjust
            # if the target line is tax-inclusive.
            price = _convert_tax_basis(
                price, source_inclusive=False, target_inclusive=bool(target_tax_inclusive),
                tax_percent=_ZERO,
            )
            result = _resolved(
                price,
                strategy_requested=PriceStrategy.LAST_SALE_TO_CUSTOMER,
                strategy_used=PriceStrategy.DEFAULT,
                source={"document_type": "CUSTOMER_QUOTE", "document_id": quote.id},
            )
            logger.info(
                "price_resolve sales tenant=%s product=%s customer=%s fallback=quote -> %s",
                tenant_id, product_id, customer_id, result["unit_price"],
            )
            return result

    # Fallback #2: «سعر البيع» العام في كرت المنتج — سعر يُدخله المالك يدوياً ولا
    # يظهر إلا هنا: لا آخر بيع لهذا الزبون ولا عرض سعر له. مخزَّن بالعملة الأساسية
    # (كـ avg_cost) فيُحوَّل بسعر صرف المستند، وبأساس غير شامل للضريبة.
    product = (
        Product.objects.filter(id=product_id, tenant_id=tenant_id)
        .only("id", "online_price", "sale_price").first()
    )
    if product and _dec(product.sale_price) > 0:
        price = _convert_currency(
            _dec(product.sale_price), source_rate=Decimal("1"), target_rate=target_rate
        )
        price = _convert_tax_basis(
            price, source_inclusive=False, target_inclusive=bool(target_tax_inclusive),
            tax_percent=_ZERO,
        )
        result = _resolved(
            price,
            strategy_requested=PriceStrategy.LAST_SALE_TO_CUSTOMER,
            strategy_used=PriceStrategy.DEFAULT,
            source={"document_type": "PRODUCT_SALE_PRICE", "document_id": product_id},
        )
        logger.info(
            "price_resolve sales tenant=%s product=%s customer=%s fallback=product_sale_price -> %s",
            tenant_id, product_id, customer_id, result["unit_price"],
        )
        return result

    # Fallback #3: product default selling price (sale tier #1) — بيانات مستوردة
    # قديمة. Only when the tier currency reconciles to the target (no rate to convert).
    if product:
        tier = (
            ProductPriceTier.objects.filter(
                product_id=product_id,
                tier_type=ProductPriceTier.TIER_TYPE_SALE,
            )
            .order_by("tier_number")
            .first()
        )
        if tier and _dec(tier.price) > 0 and (
            target_currency_id is None or tier.currency_id == target_currency_id
        ):
            price = _convert_tax_basis(
                _dec(tier.price),
                source_inclusive=bool(tier.tax_inclusive),
                target_inclusive=bool(target_tax_inclusive),
                tax_percent=_ZERO,  # tier carries no tax rate; convention-only
            )
            result = _resolved(
                price,
                strategy_requested=PriceStrategy.LAST_SALE_TO_CUSTOMER,
                strategy_used=PriceStrategy.DEFAULT,
                source={"document_type": "PRODUCT_PRICE_TIER", "document_id": tier.id},
            )
            logger.info(
                "price_resolve sales tenant=%s product=%s customer=%s fallback=tier -> %s",
                tenant_id, product_id, customer_id, result["unit_price"],
            )
            return result

    logger.info(
        "price_resolve sales tenant=%s product=%s customer=%s -> blank (no history/default)",
        tenant_id, product_id, customer_id,
    )
    return _blank(PriceStrategy.LAST_SALE_TO_CUSTOMER, reason="no_history")


class PriceResolver:
    """Strategy-pattern dispatcher. Thin facade over the two entry points so a
    single call site can resolve either side by strategy name."""

    @staticmethod
    def resolve(*, tenant_id, product_id, strategy, **kwargs) -> dict:
        if strategy in PriceStrategy.PURCHASE_CHOICES:
            return resolve_purchase_price(
                tenant_id=tenant_id, product_id=product_id, strategy=strategy,
                target_currency_id=kwargs.get("target_currency_id"),
                target_exchange_rate=kwargs.get("target_exchange_rate", Decimal("1")),
            )
        if strategy == PriceStrategy.LAST_SALE_TO_CUSTOMER:
            return resolve_sales_price(
                tenant_id=tenant_id, product_id=product_id,
                customer_id=kwargs.get("customer_id"),
                target_currency_id=kwargs.get("target_currency_id"),
                target_exchange_rate=kwargs.get("target_exchange_rate", Decimal("1")),
                target_tax_inclusive=kwargs.get("target_tax_inclusive", False),
            )
        raise ValueError(f"Unknown price strategy: {strategy}")
