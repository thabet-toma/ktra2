# RFC: Payment-Model Unification

> **Status:** RFC · 2026-05-25 (task6 P-K-4)
> **Decision:** **deferred** — owner input required.
> **Reference:** task6.md VI-3 («Disjoint payment models»).

## The problem

The system currently has **5 separate payment surfaces**, each with its own data model, validation, posting path, and reconciliation rules:

| # | Source | Model | Where it lives |
|---|--------|-------|----------------|
| 1 | Deal-level supplier payments (international) | `LogisticsPayment` | `logistics/models.py` — created via `LogisticsPaymentViewSet`, paid against a `LogisticsDeal`. |
| 2 | Customer payments (sales) | `CustomerPayment` + `PaymentAllocation` | `sales/models.py` — multi-invoice allocations, FX per-allocation (P-H-8), atomic post in `post_customer_payment`. |
| 3 | Clearance broker payments | `LogisticsClearancePayment` | `logistics/models.py` — local-currency, `payment_purpose` choice (P-D-5), posted via `pay_from_cashbox`. |
| 4 | Local-shipment carrier payments | `LocalShipment.payment_type` + journal | `logistics/models.py` — single-row payment baked into the local-shipment row itself. |
| 5 | PI-attached payment voucher | `PurchaseInvoice.attached_cash_amount` + `Cheque` rows | `logistics/models.py` + `accounting/models.py` — added in P-H-1. |

Cross-cutting layer added in P-H-9 (`core/payments.py`):
- `PaymentContext` factory methods know how to read four of the five surfaces (deal, customer, clearance, shipment-agent).
- `validate_payment(ctx)` is wired into the three viewsets (`CustomerPaymentViewSet.perform_create`, `LogisticsPaymentViewSet.perform_create`, `LogisticsClearanceViewSet.pay_from_cashbox`).

That makes the **validation** surface uniform. The **storage** surface is still 5-way disjoint.

## What disjoint storage costs us

- Reconciliation between supplier-AP balance and «what we actually paid» requires unioning 3+ tables.
- Cash-box statement (the cashier's day-end report) is currently assembled by hand from each surface.
- Cheque movements (a Cheque can be issued from a `SalesInvoice`, a `PurchaseInvoice`, or as standalone) work because we have FKs back to both invoice models — but adding a 6th source would mean a 6th FK column. It doesn't scale.
- New payment types (e.g. employee advances) repeat the pattern instead of slotting into an existing one.

## Three options

### Option A — Unify on a polymorphic `Payment` table

Single `Payment(content_type, object_id, ...)` model with a `GenericForeignKey` to the source document (Deal, Invoice, Clearance, LocalShipment, ...). All five surfaces become rows in one table; existing tables shrink to "the source-of-truth document".

**Pros:** one place for cash-box reports, FX logic, and Cheque FKs.
**Cons:** GenericForeignKey is slow to query and weak typing. Migration is large (5 backfill scripts). All viewsets need rewriting.

### Option B — Keep disjoint storage, add a reconciliation view

Define a SQL VIEW or a Django queryset adapter (`PaymentLedgerView`) that UNIONs the 5 sources and exposes a uniform row shape. Reports read from the view; writes still go to each native table.

**Pros:** zero data migration. Low risk. View can be added incrementally.
**Cons:** still 5 places to add new payment types. Read-only — the reconciler can't atomically reverse payments across sources.

### Option C — Status quo

Accept 5-way storage. Add new surfaces (e.g. employee advances) by copying the closest existing template.

**Pros:** no work.
**Cons:** the cost grows with every new payment type. Already noticeable on cash-box reports.

## Recommendation

**Option B as a stepping-stone, with Option A as the longer-term target.** The reconciliation view unlocks the cash-box / AP reports immediately. Then once we have the read-side uniform, migrating the write-side to Option A becomes a fractional refactor (each writer can be moved over independently).

Decision is deferred to owner approval — no code change here.

> **2026-08-17 · THA-118 (T1–T3) — narrowed scope, the RFC itself is untouched.** The owner's task moved the **sales-invoice write path** off surface #5 onto surface #2: `SalesInvoice.attached_cash_amount` is no longer written or posted, and every collection from an invoice now becomes a real `CustomerPayment` + `PaymentAllocation`, guarded by the invariant `amount_paid == posted_allocations_total` and proved by `python manage.py audit_ar_integrity`. That is **all** it decided: storage stays 5-way disjoint, the PI-attached purchase half of #5 remains (THA-370), and neither Option A's polymorphic table nor Option B's reconciliation view was introduced. Historical rows settled inside their own invoice journal were deliberately **not** converted — wrapping a balanced journal in a retroactive voucher would double-credit AR.
