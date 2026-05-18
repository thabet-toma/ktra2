# PROJECT_MAP.md — KTRA Import/Trading ERP

> الذاكرة الخارجية للمشروع. حدّث هذا الملف عند أي تغيير معماري.
> Last audited: 2026-05-18.
> Phase 1 completed: 2026-05-17 — 18/18 catastrophic fixes applied.
> Phase 2 completed: 2026-05-17 — 14/14 medium fixes applied.
> Phase 3 completed: 2026-05-18 — 10/10 minor fixes applied (m3-10 done in Phase 4 pass).
> Phase 4 completed: 2026-05-18 — 8/11 professional-grade improvements applied; I4-05 + m3-10 finished and I4-07 made enforceable in 2nd review (Opus). I4-06/09/11 deferred (non-bug / needs separate approval).

## [TECH_STACK]

- **Backend:** Django 6.0.1 + Django REST Framework. Python 3.13.
- **DB:** MySQL (`django.db.backends.mysql`, mysqlclient). DB name `smartktra_smart-ktra`. `foreign_key_checks=0` + `STRICT_TRANS_TABLES` in `init_command`.
- **Auth:** DRF `TokenAuthentication` + `SessionAuthentication`, `IsAuthenticated` (see `core/api_defaults.py`).
- **Multi-tenancy:** header `X-Tenant-Id` resolved by `core/tenant_utils.get_tenant()`. Single-tenant auto-resolve if exactly 1 tenant. ViewSets scope via `core/mixins.py` (`TenantQuerySetMixin`/`TenantCreateMixin`/`BaseTenantViewSet`); accounting models no longer carry `default=1` tenant FK (a missing tenant now fails loudly with 400 instead of silently writing to tenant 1).
- **Frontend (active):** `frontend_v2/` — React 19 + Vite 6 + TypeScript 5.8 + Tailwind (CDN) + import-map CDN (aistudiocdn). Port 3000.
- **Integrations:** OpenClaw AI assistant (HTTP BFF via Django), Cloudinary storage, `bridge` app (SQL↔legacy mapper).
- **ORPHAN:** `frontend/` is a **separate unrelated Next.js app** ("جيتك / توصيل سريع"). NOT part of this ERP. Also occupies port 3000 — source of the "wrong site" confusion. `smart-product-search-platform/` likewise unrelated.

## [SYSTEM_FLOW]

Core trade → accounting pipeline:

```
Deal (صفقة) ──┐
Deal ─────────┼──► Shipment (شحنة) ──► Customs Clearance (تخليص) ──► Local Transport (نقل محلي)
Deal ─────────┘            │
                           ▼
                  Purchase Invoice (فاتورة شراء)  ── landed-cost allocation ──► Inventory WAC (موسط التكلفة)
                           │
                           ▼
                  Journal (قيد) ──► General Ledger (أستاذ عام) ──► Trial Balance (ميزان مراجعة)
                                          ▲
Sales Invoice (فاتورة مبيعات) ── post ────┤── COGS / Revenue / AR / VAT / Cash
Customer Payment (تحصيل) ── post ─────────┘
Cash Box (صندوق) deposits/payments ───────┘
```

- **Payments exist at two levels:** deal-level (`LogisticsDealPayment`, Firestore-linked cashboxes) and shipment/clearance-level (`LogisticsClearancePayment`) and sales-level (`CustomerPayment`, SQL ledger). These are **disjoint sources of truth** — see [ORPHANS & PENDING].
- **Auto-accounting:** `logistics/signals.py` auto-posts journals on confirm/pay (toggles: `LOGISTICS_DISABLE_AUTO_ACCOUNTING`, `LOGISTICS_PAYMENT_SKIP_AUTO_JOURNAL`).

## [ARCHITECTURE]

Django apps (LOC = non-migration .py):

| App | LOC | Role |
|---|---|---|
| `accounting` | ~5100 | CoA, Journal (Header/Line), GL, Trial Balance, cash boxes, FX rates, tax, fiscal periods. Core engine. |
| `logistics` | ~6300 | Deals, Shipments, Clearance, LocalShipment, PurchaseInvoice, landed-cost, auto-accounting signals. No `services.py` — logic in `landed_cost.py`, `signals.py`, `payment_posting_cap.py`, `views.py`. |
| `sales` | ~2200 | SalesInvoice/Line, CustomerPayment, PaymentAllocation, DeliveryOrder, SalesSettings. **Untracked by git.** |
| `inventory` | ~800 | Product, StockMovement, WAC avg-cost (`record_stock_movement`). |
| `partners` | ~500 | Partner, PartnerGroup, credit limits, linked accounts. |
| `tenants` | ~60 | Tenant, Currency. |
| `core` | ~1600 | settings, urls, tenant_utils, api_defaults, assistant/agent/dashboard views. |
| `bridge` | ~290 | legacy/SQL mapper. |
| `hr`, `realestate` | ~430/~550 | **Out of audit scope** (per owner). `realestate` untracked. |

URL roots: `/api/accounting/ /api/inventory/ /api/logistics/ /api/sales/ /api/ (partners) /api/hr/ /api/realestate/ /api/mapper/ /api/assistant/ /api/agent/ /api/dashboard/`.

## [ORPHANS & PENDING]

- **Git hygiene:** `sales/` app + many migrations (`accounting/0008-0013`, `inventory/0002-0003`, `logistics/0020-0022`, `realestate/`) are **untracked**. Root contains ad-hoc DB-surgery scripts: `FIX_PAYMENT_CURRENCY.sql`, `_patch_services.py`, `_test_sales.py`, `backfill_base_amounts.py`. Schema drift risk — DB may not match models.
- **Disjoint payment models:** deal payments (Firestore cashbox) vs SQL `CustomerPayment` ledger never reconcile. Unification is a Phase-4 item.
- ~~Dead code: `frontend_v2/.../deal-specific/PaymentRegistration.tsx`~~ — **deleted (I4-08)**.
- ~~`resolve_forex_account()` never called~~ — **now called by `post_customer_payment` (I4-03)**.
- ~~No year-end closing routine~~ — **`year_end_close()` added (I4-04)**.
- **`frontend/` Next.js app** unrelated to ERP; keep separate or move out of repo.
- **The active 500 fix** (tenant-None guard in `sales/views.py perform_create`) converts an opaque crash to a clear 400; the underlying environment cause (likely no `Tenant(TenantID=1)` seeded in the fresh MySQL DB) still needs the user to seed a tenant.

## [PHASE 1 FIXES — 2026-05-17]

### Accounting
- **C1-02** `accounting/views.py:301-343`: `validate_journal_entry` now runs BEFORE `serializer.save()` using a mock header. Unbalanced entries are rejected without creating any DB rows.
- **C1-03** `accounting/services.py:288-316`: `post_journal_entry` wrapped in `transaction.atomic()` + `select_for_update()` + re-validates balance on actual saved lines before posting.
- **C1-04** `accounting/views.py:198-262`: `reverse_entry` now checks `JournalHeader.objects.filter(reference_type='JOURNAL_REVERSAL', reference_id=orig.id).exists()` and rejects duplicate reversals.
- **C1-05** `accounting/models.py:99-119`: `JournalLine.save()` base currency calculation fixed — replaced broken `JournalLine.journal.is_cached(self)` with `self._meta.get_field('journal').is_cached(self)`. Removed broad `except Exception` that silently defaulted `rate=1`.
- **C1-06** `accounting/serializers.py:307-343`: `JournalHeaderSerializer.update()` now raises ValidationError if `instance.is_posted` — prevents modifying posted entries via serializer.
- **C1-07** `accounting/views.py:839-942, 945-1124`: `deposit_journal` and `PurchaseReceiptViewSet` now call `validate_fiscal_period()` before creating posted journals.
- **C1-08** `accounting/models.py:73`: `JournalLine.account` changed from `on_delete=CASCADE` to `on_delete=PROTECT`. Migration `0014_change_journal_line_account_to_protect` created.
- **C1-09** `accounting/views.py:48-51, 122-156, 392-403`: Added tenant filter to `AccountViewSet.get_queryset()`, `JournalViewSet.get_queryset()`, and GL opening/transactions queries. Router basename added for AccountViewSet.

### Logistics / Inventory
- **C1-10** `logistics/landed_cost.py:478-481`: Removed erroneous `merch_pool` rescaling by `wsum/deal_tot_usd`. Now uses `deal_val_ils` directly — prevents under-valuing merchandise when `deal.total_amount` includes tax/shipping.
- **C1-11** `logistics/views.py:1681-1684`: GL inventory debit now uses `sum(landed_line_total_ils)` from invoice items when available, aligning GL with WAC.
- **C1-12** `logistics/views.py:656-671`: `add_deal` now checks if deal is already linked to another shipment and rejects duplicate links.
- **C1-13** `logistics/views.py:968-1034`: `LogisticsShipmentViewSet.post_to_accounting` now checks for existing `LOGISTICS_SHIPMENT` journal (idempotency).
- **C1-14** `logistics/views.py:1815-1834, 2052-2070`: Both `PurchaseInvoiceViewSet.unpost` and `LocalShipmentViewSet.unpost` now create reversal journals instead of deleting posted journals.
- **C1-15** `inventory/services.py:167-173`: `receive_shipment_stock` idempotency key now includes deal reference (via `notes__contains=f"صفقة {deal.ref_number}"`) — same product across multiple deals on one shipment now receives correctly.
- **C1-16** `inventory/services.py:58-66`: `RETURN_IN` now uses `avg_before` as `unit_cost` when `unit_cost=0` — prevents WAC dilution towards zero on sales returns.

### Sales
- **C1-17** `sales/services.py:568-592, 595-659`: `_post_stock_out_for_invoice` and `deliver_delivery_order` now check for existing `SALE` StockMovement and `SALES_DELIVERY_COGS` JournalHeader before creating (idempotency).
- **C1-18** `sales/services.py:757-811`: `post_customer_payment` now uses `SalesInvoice.objects.select_for_update().filter(pk__in=inv_ids)` inside the atomic block to prevent lost-update on `amount_paid`.

## [PHASE 2 FIXES — 2026-05-17]

### Accounting
- **M2-01** `accounting/views.py:397-413`: `get_all_child_accounts` now filters by tenant and uses a `visited` set to prevent infinite recursion on parent self-loops.
- **M2-02** `accounting/services.py:126-166`: `validate_fiscal_period` no longer silently bypasses on `tenant_id in (0, None)` or invalid date — raises ValidationError instead.
- **M2-03** `accounting/views.py:1201-1222`: `ExchangeRateViewSet.get_rate` now filters by tenant.
- **M2-04** `accounting/views.py:1253-1271`: Fiscal period `close_period` now logs audit entry and warns about unposted journals; `reopen_period` also logs audit.

### Logistics
- **M2-05** `logistics/views.py:1173-1191`: `pay_from_cashbox` budget check now only counts `is_posted=True` payments. `logistics/landed_cost.py:292-317`: `clearance_payment_amount_ils` now tries ExchangeRate for non-USD/ILS currencies instead of 1:1 fallback.
- **M2-06** `logistics/serializers.py:100-109`: `_payments_total_exceeds_deal` now uses Decimal instead of float for precision.
- **M2-07** `logistics/views.py:1371-1411`: `PurchaseInvoiceViewSet` now extends `BaseTenantViewSet` — all actions (including `post_to_accounting` via detail) are tenant-filtered.
- **M2-08** `logistics/models.py:257-267`: `LogisticsShipment.save()` shipment numbering now uses `select_for_update()` per-tenant to prevent collision.
- **M2-09** `logistics/views.py:1496-1501`: `allow_unpaid_freight` now requires admin permission (`user_is_admin`).

### Sales / Core / Frontend
- **M2-10** `sales/services.py:671-680`: `_resolve_ar_account_for_partner` now includes fallback to `SalesSettings.default_ar_account` (matches `_resolve_ar_account`).
- **M2-11** `core/tenant_utils.py:127-135`: `_validate_user_tenant_access` now raises `PermissionDenied` instead of just logging when user accesses wrong tenant.
- **M2-12** `sales/views.py:37-46, 58-77`: `SalesInvoiceViewSet.create` now returns `auto_post_error` in response when auto-post fails instead of silently swallowing it.
- **M2-13** `frontend_v2/services/restApi.ts:81-97, 101-107, 124-130, 150-156, 178-184, 203-207, 220-225`: Added `flattenDrfError()` function that recursively flattens DRF nested field errors into readable text. Applied to all API methods.
- **M2-14** `sales/serializers.py:21-50`: `_validate_stock_lines` now respects `product.allow_negative_stock` — skips stock check when enabled.

## [PHASE 3 FIXES — 2026-05-17]

### Accounting
- **m3-01** `accounting/services.py:259-263`: Balance tolerance changed from `abs(diff) > 0.01` to quantize-then-`!= 0` — exact double-entry enforcement.
- **m3-02** `accounting/models.py:99-110`: Added `CheckConstraint` on `JournalLine.debit >= 0` and `credit >= 0`. Migration `0015_add_journal_constraints`.
- **m3-03** `accounting/models.py:62-69`: Added `UniqueConstraint(tenant, reference_type, reference_id)` on `JournalHeader` (partial: only when both non-null). Migration `0015_add_journal_constraints`.
- **m3-04** Narrowed `except Exception` in: `accounting/views.py` (post_entry, reverse_entry, deposit_journal, purchase_receipt, cashbox_ledger), `logistics/views.py` (post_payment, unpost_payment, post_agent_payment, post_freight_cost, pay_from_cashbox, post_to_accounting), `sales/services.py` (tenant/cust name → AttributeError), `logistics/signals.py` (expense → ValidationError/IntegrityError). All unexpected errors now return 500 with `logger.exception`.

### Sales
- **m3-05** `sales/services.py:323-336`: `_partner_open_balance_excluding_invoice` now iterates invoices and converts each `grand_total - amount_paid` via `exchange_rate` to base currency before summing — prevents mixing currencies in credit limit checks.
- **m3-06** `sales/services.py:920-934`: `next_invoice_number` now uses `select_for_update()` inside `transaction.atomic()` with 3-retry loop — prevents collision under concurrent requests.

### Logistics
- **m3-08** `logistics/landed_cost.py:485-503`: Hardcoded `internal_usd * 3.6` fallback replaced with `ExchangeRate` lookup (USD→ILS), falling back to 3.6 only if no rate found.
- **m3-09** `logistics/signals.py:86-112`: `automate_expense_accounting` dead `is_foreign` branch fixed — now calls `get_exchange_rate()` for foreign-currency expenses instead of 1:1.

## [PHASE 4 FIXES — 2026-05-17]

### Accounting — Centralized Posting
- **I4-01** `accounting/services.py:330-423`: New `post_journal()` function — single atomic entry point for ALL journal creation+posting. Enforces: open fiscal period, exact balance, same-tenant lines, idempotency via `(reference_type, reference_id)`, `select_for_update` race prevention. **Migrated callers:** accounting/deposit_journal, accounting/purchase_receipt, sales/post_sales_invoice, sales/post_customer_payment, sales/deliver_delivery_order (COGS), logistics/post_payment (deal), logistics/post_agent_payment (shipment), logistics/post_to_accounting (shipment freight), logistics/post_to_accounting (purchase invoice), logistics/signals (expense).
- **I4-02** `accounting/models.py:70-81`: `JournalHeader.save()` now raises ValidationError if attempting to modify a posted journal — model-level immutability enforcement.
- **I4-03** `sales/services.py:760-797`: `post_customer_payment` now posts forex gain/loss lines when payment currency differs from invoice currency — uses `resolve_forex_account()` to find the forex account.
- **I4-04** `accounting/services.py:436-558`: New `year_end_close()` routine — closes all Revenue/Expense accounts for a fiscal year to retained earnings via `YEAR_END_CLOSE` journal. Endpoint: `POST /api/accounting/fiscal-periods/year-end-close/`.

### Accounting — Tenant Isolation (I4-05)
- **I4-05** New `core/mixins.py` — `TenantQuerySetMixin` (scopes `get_queryset()` to request tenant, returns `.none()` when unresolved), `TenantCreateMixin` (raises 400 instead of falling back to tenant 1), `BaseTenantViewSet`. Adopted by `logistics/views.py` and `hr/views.py` (local duplicate `BaseTenantViewSet` definitions removed) and the accounting ViewSets. Removed `default=1` from **all** accounting FK fields (`Account/CostCenter/JournalHeader/JournalLine/Cheque/AccountingAuditLog/CashBoxLedgerAccount/FiscalPeriod/ExchangeRate/TaxRate.tenant` + `JournalLine.journal/account`). Replaced every `serializer.save(tenant_id=1)` fallback in `accounting/views.py` (Account/CostCenter/Cheque/Journal create+update/ExchangeRate/FiscalPeriod/TaxRate) with explicit tenant + loud 400. Added missing tenant filters to `CostCenter/Cheque/FiscalPeriod` querysets and `ExchangeRate/TaxRate` (returned global rows when no tenant). Migration `accounting/0016`.

### m3-10 — Explicit VAT Input Account
- **m3-10** `sales/models.py` `SalesSettings.vat_input_account` FK added (+ serializer field, migration `sales/0005`). `logistics/views.py` purchase-invoice posting now resolves VAT input account by priority: (1) `SalesSettings.vat_input_account`, (2) `TaxRate(direction='purchase')`, (3) account code `1105`. Removed the fragile `name__icontains="ضريبة"` search.

### Logistics — State Machine (I4-07, re-fixed in 2nd review)
- **I4-07** `logistics/models.py` `LogisticsDeal` + `LogisticsShipment`: transition tables now **enforced in `save()`** (via `_assert_valid_workflow_transition` / `_assert_valid_status_transition`), not only `clean()`. **Why:** DRF never calls `full_clean()`, so the original `clean()`-only implementation was dead code — invalid transitions (e.g. Pending→Cleared) succeeded silently via the API. `clean()` retained for admin/`full_clean`. System-driven state advances in `logistics/signals.py` use bulk `.update()` and deliberately bypass the guard (same escape-hatch pattern as the I4-02 posted-journal guard). Verified: Pending→Cleared rejected, Pending→In-Transit allowed.

### UI Cleanup
- **I4-08** Deleted `frontend_v2/components/forms/deal-specific/PaymentRegistration.tsx` — 100% commented-out dead code. No imports found.

> **2nd Phase-4 review (Opus 2026-05-18):** I4-01/02/03/04 verified correct (post_journal idempotency inside atomic w/ `select_for_update`; immutability guard exempts create + bulk-update unpost; forex journal balances in gain/loss/equal cases; year-end-close debit/credit math proven balanced). **I4-07 was non-functional dead code → fixed** (moved to `save()`). I4-05 + m3-10 (left pending by the external model) completed. Known accepted limitation: `post_customer_payment` forex assumes a single invoice currency per payment; `resolve_forex_account()` still name-based (acceptable — I4-03 spec asked for it). `manage.py check` clean, no migration drift, end-to-end smoke test passed.
