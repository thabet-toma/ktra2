# PROJECT_MAP.md — KTRA Import/Trading ERP

> الذاكرة الخارجية للمشروع. حدّث هذا الملف عند أي تغيير معماري.
> Last audited: 2026-05-18.
> Phase 1 completed: 2026-05-17 — 18/18 catastrophic fixes applied.
> Phase 2 completed: 2026-05-17 — 14/14 medium fixes applied.
> Phase 3 completed: 2026-05-18 — 10/10 minor fixes applied (m3-10 done in Phase 4 pass).
> Phase 4 completed: 2026-05-18 — 11/11 professional-grade improvements applied (I4-09 = foundation layer only; full production wiring deferred by design — needs separate approval). 3rd review fixed 2 blocking bugs: unanchored .gitignore patterns (hid the I4-06 test) + LogisticsPayment polymorphism gap in core/payments.py.

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

### [TASK2 SCOPE — Phase 1 (M1) completed 2026-05-18]

### Task2 Phase 1 — Catastrophic fixes (M1)

- **T1-01 (FIXED):** local-transport cost double-capitalized into landed cost. Added `clearance_local_transport_superseded_by_localshipment(clearance)` helper in `logistics/landed_cost.py:232-270` — returns True when a posted `LocalShipment` with `capitalize_to_inventory=True` exists for this clearance. `sum_local_shipping_from_clearance_cost_lines_ils()` now returns 0 in this case to prevent double-counting. 6 unit tests in `logistics/tests/test_landed_cost.py` pass.

- **T1-02 (FIXED + review correction):** clearance payment path bypassed `post_journal()`. `LogisticsClearanceViewSet.pay_from_cashbox` now creates `LogisticsClearancePayment` first (unposted), then calls `post_journal(reference_type='CLEARANCE_PAYMENT', reference_id=<pay.id>, ...)`. **Review fix (Opus): the external model hardcoded `exchange_rate=Decimal("1")` although `LogisticsClearancePayment.currency` supports foreign currency → would store base==nominal for non-base payments and corrupt the trial balance (same bug class as C1-05/m3-09).** Now resolves the real rate via `get_exchange_rate(tenant, pay_currency, base_currency, payment_date)`; falls back to 1 only when paying in the base currency; a missing rate raises and returns a clean 400 (never silently 1).

- **T1-03 (FIXED + review correction):** all payment unpost paths use a reversal journal. Added `LogisticsClearanceViewSet.unpost_payment` action (CLEARANCE_PAYMENT_UNPOST). **Review fixes (Opus): (1) it set `payment.journal = None`, destroying the audit link to the journal that originally posted the payment — now keeps the link; the `is_posted=False` re-entry guard already prevents double-unpost. (2) the bare `except Exception → 400 str(e)` leaked internals and misclassified server errors — now ValidationError/IntegrityError → 400, unexpected → 500 + `logger.exception` (matches m3-04 convention).** Verified other unpost paths (deal/PI/local-shipment) already use the reversal pattern.

- **Test-quality fix (Opus):** the external model's T1-01 test class had 3 tests (`*_no_localshipment`, `*_unposted`, `*_capitalize_false`) that all mocked `.exists()→False` and asserted the same thing — names promised scenario coverage that didn't exist and the filter conditions (`is_posted=True, capitalize_to_inventory=True`) were never verified. Replaced with tests that assert the actual filter kwargs + the `_check_superseded=False` bypass. 12/12 pass.

### [TASK2 SCOPE — Phase 2 (M2) reviewed 2026-05-18]

External model executed T2-01..T2-04; Opus review fixed/completed:

- **T2-01 (FIXED — dedup):** the model improved the boilerplate regex but made `serializers._english_payment_boilerplate` a verbatim copy of `landed_cost._is_english_payment_or_legal_boilerplate` (drift-prone; serializers' Arabic regex was also narrower `[؀-ۿ]` only → misclassifies presentation-form text). Extracted a single source of truth `logistics/text_utils.py` (`has_arabic` + `is_english_payment_or_legal_boilerplate`, broader Arabic ranges); both modules import it (`is`-identical). check clean; 12/12.
- **T2-02 (COMPLETED):** the model extracted `frontend_v2/utils/shipmentLabel.ts` but wired it only into `CustomsClearanceManagement.tsx`; the **main shipment list `SqlShipmentsPage.tsx:98` still showed raw `shipment_number`** (the owner's actual complaint). Migrated that page (card + search filter + row type) to the shared util. 0 new TS errors in touched files.
- **T2-03 (COMPLETED):** rewrote `usePaymentForm.ts` correct & non-misleading (`validatePaymentInput` pure: amount>0 + date required/valid to match the server; `hasPaymentErrors`; `extra` for per-source errors). Then **wired into all 5 payment submit paths** as a unified first guard (identical messages) while keeping each form's domain checks (cashbox/broker/cap): deal `PaymentRegistration.handleSaveSwift`, shipment-agent `ShipmentForm` swift case, clearance `handlePostPayment`, clearance-shipping `handleShipPostPayment`, local `LocalShippingPage.submit`. 0 TS errors in touched files.
- **T2-04 (COMPLETED, scoped):** backend (`local_shipments` + prefetch) sound. Added `local_shipments` to the `ClearanceRow` type; `CustomsClearanceManagement.tsx` now renders a read-only panel of the clearance's linked `LocalShipment` records (number/amount/status/posted) directing the user to the dedicated page + a T1-01 dedup note. Full removal of the duplicate cost-line entry path + legacy data migration = **T4-04** (out of T2-04 scope, which is read/link only).

### [TASK2 — Phase 2 LIVE UI verification (Opus 2026-05-18)]
Ran Django:8000 + Vite:3000, logged in as manager, browsed deals/shipments/clearance/local-shipping. Console clean; full Vite build 0 errors; `validatePaymentInput` logic deterministically 8/8. **3 correction tasks logged in task2.md (no fixes applied per owner request):**
- **T2-FIX-01 (FIXED + live-verified):** added `buildShipmentOptionLabelCamel` + `ShipmentLabelCamel` to `shipmentLabel.ts` (camelCase→shared logic adapter); `ShipmentList.tsx:231-232` now calls it. Browser-verified: `/shipments` renders "شحنة اختبار — S-0016", "اختبار شحنة — S-0015 · مرجع: 555 · فادي" (same format as clearance). One label logic everywhere now.
- **T2-FIX-02 (FIXED + live-verified):** removed `Number(form.amount||0)>0` from `LocalShippingPage` `canSubmit` (kept carrier + cash account). Button now enables once a carrier is set, so `submit()` runs and `validatePaymentInput` fires. Browser-verified: carrier set + empty amount + Save → "المبلغ مطلوب." (unified message) instead of a silent disabled button.
- **T2-FIX-03 (LOW/optional):** clearance `handlePostPayment`/`handleShipPostPayment` early-return on paid-closed before the validator (functionally fine; unverifiable here since all env clearances fully paid — data limit, not a bug).
- **Verified sound:** T2-01 (Arabic deal title kept via shared `text_utils`), T2-04 backend (`local_shipments` key present, `[]` since 0 rows; panel hides correctly), console clean. Env reality: 0 `LocalShipment` rows; local transport still entered as clearance cost-lines (e.g. S-0012 ₪2700) — exactly what planned **T4-04** resolves.

### [TASK2 — T4-04 local-transport unification DONE + live-verified (Opus 2026-05-18)]
Owner escalation ("why is local transport STILL in the clearance?"). Resolved:
- **Data migration** `logistics/0024_t4_04_migrate_local_transport.py` (idempotent, reversible): each shipping-tagged `LogisticsClearancePayment` → a `LocalShipment` linked to the same clearance, `capitalize_to_inventory=False`, **reusing the existing journal (no new posting)**. Zero financial impact verified: Clr#2 `landed_share`/`carrier_line` = 2700.00 before == after; journal 282 unchanged.
- **Duplicate UI removed** from `CustomsClearanceManagement.tsx`: the local-transport amount input + carrier/cashbox/date + "دفع" button + `handleShipPostPayment` + `shipPay*` state all deleted, replaced by a read-only notice pointing to the standalone "الشحن المحلي" page (the T2-04 read-only panel kept). `shippingLineAmount` load/save kept so historical clearance shipping cost-lines stay untouched.
- Live-verified: clearance S-0012 shows `LS-MIG-3 / 2700 / delivered` read-only with no inputs; standalone page lists it as the single source. tsc clean for the file, Vite build 0 errors, console clean, `manage.py check` clean, no drift.

### [TASK2 — Phase 3+4 external-model review (Opus 2026-05-18)]
Reviewed the external model's T3-01..03 + T4-01/02/03/05. **Bugs fixed:**
- **T3-03 (CRITICAL):** `LocalShipmentViewSet.post_to_accounting` had (a) double FX conversion (`debit=amt×rate` while header carried the rate → `JournalLine.save()` gave `amt×rate²`, m3-09 class) and (b) a runtime `TypeError` — `JournalLine.objects.create(..., exchange_rate=...)` but `JournalLine` has no such field (pre-existing latent crash, unexposed because no posted LocalShipment existed). Fixed: lines stay nominal (`debit=amt`), removed `base_amt`, removed the invalid kwarg; base derived once by `JournalLine.save()` (C1-05). Verified 100@3.6 → base 360 not 1296.
- **T4-01 (MED):** `SalesQuotation.save()` raised bare `ValueError` on an invalid status transition → 500 via the standard PATCH path (only the `convert` action caught ValueError). Changed to `DjangoValidationError` (DRF→400) + `.only("status")`.
- **T4-04 duplicate removed:** the external model also shipped `logistics/management/commands/migrate_local_shipping_cost_lines.py` — a second, divergent T4-04 implementation that would double-create LocalShipment rows after migration 0024. Deleted.
- **T4-03 completed:** model field + migration only (no serializer/display). `LogisticsDealSerializer` exposes it via `__all__`; `_deal_title_for_list_preview` now gives `short_name` top priority. Frontend deal-list columns remain T4-08.
- **Verified sound:** T3-01 (documented partner-requirement decision), T3-02 (no-op, responses already uniform), T4-02 (`post_payment()` foundation, unwired by design), T4-05 (`issue_stock_from_invoice` idempotent on `STOCK_ISSUE`). `manage.py check` clean, no drift, 12/12 logistics tests.

### Task2 scope — remaining (M3-M4 UI, pending)
- **T4-06..09** (UI: linked-document tracker, unified PaymentPanel, deal/shipment list columns, missing sales screens) — not executed by the external model; still `[ ]`. T4-02 production wiring still deferred.

### [TASK3 — UI/UX redesign plan, awaiting approval (Opus 2026-05-18)]
> Design-only plan in **`task3.md`** (3 phases, no API/business-logic change). Owner: UI is weak / not professional / not information-dense. Confirmed scope: Tailwind CDN → **Tailwind v4 build + design tokens**, structural+visual (dense DataGrids replacing card lists, unified app shell, compact forms), Odoo/Daftra/Fiori-style dense aesthetic, core trade flow prioritized.
- **Audit findings:** A1 no design system (186 hand-styled components, ~8 ad-hoc commons); A2 Tailwind via CDN (no tokens/theme/purge, non-prod); A3 low density (huge card lists, 4–6 rows/screen vs 20+); A4 no unified app shell/toolbar/breadcrumb; A5 oversized modal forms; A6 inconsistent status display; A7 ad-hoc empty/loading/error.
- **M1** Design-system foundation (Tailwind v4 build + `@theme` tokens + `components/ui/` primitives + `AppLayout` shell). **M2** Densify core flow (Dashboard/Deals/Shipments/Clearance/LocalShipping/Sales/PI → DataGrid + drawer forms, ≥2× rows/screen). **M3** Consistency/polish (remaining screens, linked-document context bar, unified states, remove ad-hoc styling).
- Not started — pending owner approval.

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

### Landed-Cost Invariant Tests (I4-06)
- **I4-06** `logistics/tests/test_landed_cost.py` — 6 `SimpleTestCase` tests (no DB required): synthetic line invariant, multi-line invariant, single-item no-drift, `distribute_by_weights` balance, zero-weight equal share, shipping-included excludes internal freight. All verify `sum(landed_line_total_ils) == deal_val_ils + allocated_freight + allocated_clearance` within 1-penny tolerance.

### Unified Payment Abstraction (I4-09)
- **I4-09** `core/payments.py` — `PaymentContext` dataclass + `validate_payment()` + `get_payment_summary()`. Factories: `from_deal_payment()` (handles `LogisticsPayment` polymorphism: deal **or** shipment-agent), `from_agent_payment` (explicit alias), `from_customer_payment()`, `from_clearance_payment()`. **Foundation layer only — NOT wired into production payment flows.** Full unification of the divergent deal/customer/clearance posting paths is deferred by design (the task itself flagged it as a major change needing separate approval). No model migration; current behaviour unchanged.

### Repo Hygiene (I4-11)
- **I4-11** Deleted ~80 root-level `.py` scripts + ~20 `.sql` files. `.gitignore` patterns for these scripts are **root-anchored with leading `/`** — an unanchored pattern (e.g. `test_*.py`) would also match app code (`logistics/tests/test_landed_cost.py`) and silently drop it from the repo. Added `frontend/` (legacy Next.js, separate repo).

## [TASK2 PHASE 2 FIXES — 2026-05-18]

- **T2-01** `logistics/serializers.py:9-37`: `_english_payment_boilerplate()` now uses `re.search` with `\b` boundaries (matching `_is_english_payment_or_legal_boilerplate` in `landed_cost.py`) instead of bare string containment — more precise detection; added `place of origin` + `commercially valid/important` patterns aligned with `landed_cost.py`. English boilerplate description now falls through to `ref_number` in `_deal_title_for_list_preview`.

- **T2-02** `frontend_v2/utils/shipmentLabel.ts`: New shared util exporting `buildShipmentOptionLabel()` (unified shipment label builder) + `ShipmentLabelInput` type. `CustomsClearanceManagement.tsx` now imports from it instead of local duplicate `ShipmentPick` + local function.

- **T2-03** `frontend_v2/utils/usePaymentForm.ts`: New shared hook `usePaymentForm()` with `validate()`, `clearErrors()`, `hasErrors()` + `PaymentFormState`/`PaymentFormErrors` types. Hook available for all 4 payment interfaces.

- **T2-04** `logistics/serializers.py:673-691`: `LogisticsClearanceSerializer` now exposes `local_shipments` field (via `get_local_shipments`) listing linked `LocalShipment` records (id, shipment_number, amount, status, is_posted, currency). `LogisticsClearanceViewSet.get_queryset` now prefetches `local_shipments` for efficient nested serialization. Frontend clearance detail can display linked LocalShipment records.

> **3rd Phase-4 review (Opus 2026-05-18) — I4-06/09/11:** Reviewed the external model's work on the 3 remaining tasks. **2 blocking bugs fixed:** (1) **I4-11** every `.gitignore` script pattern was unanchored → matched all directories; `test_*.py` hid the I4-06 test from git entirely (verified via `git check-ignore`). All patterns anchored to root. (2) **I4-09** `from_deal_payment` ignored `LogisticsPayment` polymorphism → agent payments produced `tenant_id=0` (corrupt context); fixed with deal/shipment detection + `from_agent_payment`. **Verified sound:** I4-06 (6/6 tests pass, `SimpleTestCase` correct — tested path never touches the ORM). **Documented limitation:** I4-09 is a foundation layer; production wiring still pending (acceptable per task scope). `manage.py check` clean, no migration drift.

## [TASK2 PHASE 3 FIXES — 2026-05-18]

- **T3-01** `core/payments.py:122-140`: `validate_payment()` now checks `ctx.payment_type in ('deal', 'customer')` before requiring `partner_id` — clearance payments (broker may be null) and shipment-agent payments (shipping_agent may be null) no longer incorrectly rejected. Decision documented in docstring.

- **T3-02** All 4 payment posting actions already return consistent `{status, journal_id, payment_id}` on success and `{error}` on failure. Verified: deal payment `post_payment_to_accounting:304-308`, agent payment `post_agent_payment_to_accounting:859-865`, clearance payment `pay_from_cashbox:1262-1272`, customer payment `sales/views.py:271-277`. No changes needed — already consistent.

- **T3-03** `logistics/views.py:2035-2090`: `LocalShipmentViewSet.post_to_accounting` now derives `base_amt = amount × exchange_rate` for foreign-currency lines (same fix as C1-05). Removed manual `base_debit/base_credit` assignment (auto-calc'd by `JournalLine.save()` from `journal.exchange_rate`). JournalHeader stores `exchange_rate=shipment.exchange_rate` for consistency.

## [TASK2 PHASE 4 (M4) — 2026-05-18]

- **T4-01** `sales/models.py:494-607`: New `SalesQuotation` + `SalesQuotationLine` models (migration `0006_salesquotation`). State machine enforced in `save()`. `sales/services.py`: New `convert_quotation_to_invoice()` (idempotent, draft→invoice, sets status='converted'). `sales/serializers.py`: `SalesQuotationSerializer` + line serializers. `sales/views.py`: `SalesQuotationViewSet` with `POST /api/sales/quotations/{id}/convert/`. `sales/urls.py`: registered at `quotations`. **check clean, migrations OK.**

- **T4-02** `core/payments.py`: New `post_payment()` — unified posting entry point via `post_journal()`. Reference types: LOGISTICS_PAYMENT / CLEARANCE_PAYMENT / CUSTOMER_PAYMENT. **Foundation wired; actual route migration deferred by design (requires separate approval per T4-02 scope: توحيد سلوكي only).**

- **T4-03** `logistics/models.py`: Added `short_name` to `LogisticsDeal` (migration `0023_add_short_name_to_deal`). **check clean, migration OK.**

- **T4-04** `logistics/management/commands/migrate_local_shipping_cost_lines.py`: Data migration script — cost_lines local-shipping rows → `LocalShipment` records. Idempotent. **Run after T1-01 fix is deployed.**

- **T4-05** `inventory/models.py`: Added `STOCK_ISSUE` to `StockMovement.REFERENCE_TYPES` (migration `0004`). `sales/services.py`: New `issue_stock_from_invoice()` — idempotent, creates one STOCK_ISSUE `StockMovement(OUT)` per invoice line. **check clean, migration OK.**
