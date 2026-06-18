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
    target_currency_id: int | None = None,
    target_exchange_rate: Decimal | str | float = Decimal("1"),
) -> dict:
    """Resolve a purchase unit price for a product per the active strategy.

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
    if strategy == PriceStrategy.LOWEST_PURCHASE:
        # Compare on base currency so multi-currency history is fair (A2: all-time).
        best_base: Decimal | None = None
        for item in qs:
            unit = _dec(item.unit_price)
            if unit <= 0:
                continue
            src_rate = _src_purchase_rate(item)
            base = unit * (src_rate if src_rate > 0 else Decimal("1"))
            if best_base is None or base < best_base:
                best_base = base
                chosen = item
    else:  # LAST_PURCHASE — most recent posted purchase invoice
        chosen = (
            qs.filter(unit_price__gt=0)
            .order_by("-invoice__invoice_date", "-invoice_id", "-id")
            .first()
        )

    if chosen is not None:
        src_rate = _src_purchase_rate(chosen)
        price = _convert_currency(
            _dec(chosen.unit_price), source_rate=src_rate, target_rate=target_rate
        )
        result = _resolved(
            price,
            strategy_requested=strategy,
            strategy_used=strategy,
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
            "price_resolve purchase tenant=%s product=%s strategy=%s -> %s (src_invoice=%s)",
            tenant_id, product_id, strategy, result["unit_price"], chosen.invoice_id,
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

    # Fallback: product default selling price (sale tier #1). Only when the
    # tier currency reconciles to the target (no rate available to convert).
    product = Product.objects.filter(id=product_id, tenant_id=tenant_id).only("id", "online_price").first()
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
