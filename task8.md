# TASK 8 — Enterprise Audit & Remediation Plan (K.T.R.A ERP)

> **Status:** AUDIT ONLY — no code changes proposed yet. Awaiting approval before implementation.
> **Date:** 2026-06-08 · **Auditor role:** Principal Architect / Staff Eng / ERP Consultant / Product Designer
> **Reference target:** Al-Aseel ERP (الأصيل) workflow, layout, and business behavior.
> **Scope:** Sales, Purchasing, Inventory, Receivables/Payables, GL, Real-Estate, Offline/PWA, API stability, UX.

---

## 1. EXECUTIVE SUMMARY

K.T.R.A is a Django 5 + DRF backend with a React 19 / Vite 6 / Tailwind 4 PWA frontend (`frontend_v2`), multi-tenant, with an offline layer (Dexie + service worker + mutation queue) added across task7. The accounting core (double-entry posting, COGS, FIFO, journals) is **substantially implemented and is the strongest part of the system**. The weakest areas — and the source of almost every confirmed complaint — are:

1. **A systemic "API Error" failure mode** rooted in (a) all-or-nothing `Promise.all` data loading on composite screens, (b) unshaped HTTP 500s from `custom_exception_handler` (returns `None` → opaque generic error), and (c) a missing tenant/auth precondition surfacing as a generic message. This is **the single highest-leverage fix** — it explains the Sales Settings error, intermittent save errors, and "random red errors."

2. **The offline connectivity indicator is built on a non-existent endpoint.** `useOnlineStatus` heartbeats `GET/HEAD /api/health/`, which **is not registered in `core/urls.py`**. The 404 path (`if (res.ok)`) silently no-ops, so the indicator cannot self-heal and "Connected" sticks. This is a concrete root cause, not a symptom.

3. **Sales Invoice UX diverges from Al-Aseel** in exactly the ways listed: native `type="date"` instead of the Al-Aseel calendar; no auto-expanding line grid; no live customer balance / debtor-creditor status / GL drill-down; no profit display; no draft auto-save or unsaved-changes guard.

4. **Negative-stock policy is inverted from the business requirement.** The backend *blocks* over-selling by default (`Product.allow_negative_stock=False`); the business mandates selling below stock must be **allowed**. Today this requires a per-product flag and has no global/settings switch.

5. **Purchase invoice defaults to USD-leaning currency logic** (`currency_code === 'ILS' ? 'ILS' : 'USD'`) rather than ILS (NIS)-first, with an undersized non-expanding item grid.

None of these require a rewrite. The accounting engine is sound; the remediation is concentrated in the Sales/Purchase editors, the API error contract, and the offline heartbeat. **Recommended sequencing: fix the API error contract and health endpoint first (unblocks everything), then accounting-policy correctness (negative stock), then Sales/Purchase UX parity, then offline polish.**

### Severity tally
| Severity | Count | Examples |
|---|---|---|
| 🔴 Critical (blocks operation) | 5 | Missing `/api/health/`, unshaped 500s, settings-page all-or-nothing load, negative-stock policy, unsaved-invoice loss |
| 🟠 High | 9 | No live customer balance/GL link, no profit, date picker parity, no auto-row-expand, draft auto-save, purchase currency default |
| 🟡 Medium | 8 | OfflineBanner dead branch, payment placement, real-estate nav placement, calculator popup, label/input alignment |
| 🟢 Low | several | Spacing, color-coding, density |

---

## 2. ARCHITECTURE AUDIT

### Stack (verified from code, not docs)
- **Frontend:** React 19, TS 5.8, Vite 6, Tailwind 4, react-router-dom 7, Dexie 4.4, vite-plugin-pwa 1.3, workbox-window 7.4, lucide-react, recharts.
- **Backend:** Django 5.x, DRF, MySQL (prod) / SQLite (test), Token auth (`Authorization: Token …`), multi-tenant via `X-Tenant-Id` header (`core/tenant_utils.get_tenant`).
- **Two frontends exist:** legacy `frontend/` and active `frontend_v2/`. There is also a `smart-product-search-platform/` and a 125 MB `github.zip` checked into the repo root.

| # | Issue | Sev | Impact | Root cause | Recommended fix |
|---|---|---|---|---|---|
| A1 | `useOnlineStatus` calls `${VITE_API_URL}/api/health/` which is **not in `core/urls.py`** | 🔴 | Offline indicator unreliable; cannot confirm/recover "online" via heartbeat | Endpoint never implemented; heartbeat's `if(res.ok)` no-ops on 404 | Add a `GET/HEAD /api/health/` view returning 200; on non-ok treat as degraded, not silent |
| A2 | `custom_exception_handler` returns `None` for unhandled exceptions (only logs) | 🔴 | Every uncaught backend error becomes a bare DRF 500 with no shaped body → frontend shows generic "API Error" | DRF default returns `None` for non-API exceptions; handler doesn't build a 500 envelope | Build a `{detail, code, trace_id}` 500 response with a correlation id; keep logging |
| A3 | `125 MB github.zip` + `dist.zip` / `dist (2).zip` committed into the repo | 🟠 | Bloated clones, slow CI, accidental deploys of stale builds | Build artifacts committed | Remove from VCS, add to `.gitignore` |
| A4 | Two parallel frontends (`frontend/`, `frontend_v2/`) + `OldPurchaseInvoice.tsx` legacy components | 🟡 | Maintenance ambiguity; dead code drift (recurring theme in task6/7) | Incremental migration never finalized | Confirm `frontend_v2` is canonical; quarantine/delete `frontend/` legacy |
| A5 | `VITE_API_URL` resolution differs between `restApi.ts` (adds `/api`) and `useOnlineStatus.ts` (assumes root) | 🟠 | Heartbeat URL can be wrong in deployments where `VITE_API_URL` already ends in `/api` → `…/api/api/health/` | Two independent base-URL resolvers | Single shared `apiBase()` util used by both |
| A6 | Token in `localStorage`; no refresh/expiry handling | 🟡 | Expired token → 401 surfaces as generic error; no auto-logout | Simple token scheme | Centralize 401 → redirect-to-login in one fetch wrapper |

**State management:** local `useState` per screen; no global store for partners/products/accounts → each composite screen re-fetches via `Promise.all`. **Caching:** Dexie mirror wired only for `products` (ItemsManagement) and `accountingApi.getPartners`; `getAccounts`/`getCostCenters`/`getCheques`/`tax-rates` are **not** mirrored, so offline composite screens partially fail.

---

## 3. ERP BUSINESS-LOGIC AUDIT

### 3.1 Sales Invoices
Engine reviewed in `sales/services.py` (1669 lines), `sales/serializers.py`, `sales/models.py`.

| Area | State | Finding |
|---|---|---|
| Invoice numbering | ✅ `next_invoice_number(tenant, book_num)`, unique constraint per tenant | OK server-side. **Gap:** frontend doesn't pre-fetch/preview the next number on a new invoice (confirmed: "new invoice number not generated correctly" — it's blank until save). |
| Customer balance on select | ⚠️ Only via `credit-preview` action returning `projected_balance`, shown **only when `invType==='credit'` AND after async load** | Confirmed: balance not shown immediately; cash invoices show nothing. |
| Debtor/creditor status | ❌ Not displayed | No debit/credit label anywhere in editor. |
| Customer summary → GL drill-down | ❌ Not clickable | No link from balance to General Ledger. |
| AR posting | ✅ `_build_…` journal builders, balanced check enforced | Sound double-entry. |
| Profit display | ❌ Not shown | COGS journal computed (`_build_cogs_journal_line_dicts`) but **profit = revenue − COGS is never surfaced** in the editor. |
| Cost / COGS | ✅ Average-cost at post, FIFO allocation suggestions | Sound. |
| Inventory movement | ✅ `stock_on_post` gate; deducts on post/deliver | OK. |
| Partial / cash / cheque payments | ⚠️ `attach_payment_voucher` + `attach_voucher_and_post` exist | Backend OK; **frontend cash+cheque workflow incomplete & misplaced** vs Al-Aseel. |
| Credit invoices / draft | ✅ STATUS_DRAFT, auto-post setting | OK. |
| Auto-save | ❌ None | `dirtyRef` exists but is only used to decide PATCH-on-save; no timer, no localStorage. |
| Unsaved-changes guard | ❌ None | **No `beforeunload` / router blocker** → leaving the page loses the draft (confirmed). |
| Negative-stock prevention | ⚠️ **Inverted** | `serializers.py:64-71` + `inventory/services.py:71-82` block over-sell unless `product.allow_negative_stock`. Business requires selling below stock to be **allowed** → needs global/settings default = allow. |
| Multi-currency | ✅ `currency`, `exchange_rate` on invoice | Present. |

### 3.2 Purchase Invoices
- Default currency logic `currency_code === 'ILS' ? 'ILS' : 'USD'` (`PurchaseInvoice.tsx:49`) — **not ILS-first**; should default to ILS (NIS).
- Item grid small / non-expanding; field rendering inconsistent across breakpoints (UX section).
- Supplier balances/costing/landed-cost (`landed_unit_price_ils`) present — backend costing OK.

### 3.3 Receipts & Payments
- `CustomerPaymentViewSet` supports independent creation + FIFO allocation suggestion + shared `validate_payment`. ✅
- Cheque management workflow incomplete on the frontend (receipt voucher), navigation returns to wrong screen (confirmed).

### 3.4 Inventory
- Negative-stock guard centralized in `inventory/services.py` (good — single source of truth) but policy default is wrong for this business.
- Costing = moving average; quantity consistency enforced at post.

### 3.5 General Ledger
- Double-entry integrity enforced (`balanced` check, post_journal idempotency). ✅
- **Gap:** no UI drill-down from customer/supplier balance into their ledger.

### 3.6 Real Estate
- `realestate` app + `PropertyRentalPage` wired into Sidebar as "تأجير العقارات والعدادات". **Placement is wrong per Al-Aseel** (should sit within the accounting/assets workspace, not as a flat sidebar peer) — confirmed.

---

## 4. UX / UI AUDIT

Compared against the two Al-Aseel screenshots provided (purchase-invoice header + Al-Aseel native date calendar).

| # | Issue | Sev | Notes |
|---|---|---|---|
| U1 | Date picker uses native `<input type="date">` (editor lines 1448/1461/1609/2066) | 🟠 | Al-Aseel uses a custom Arabic calendar popover (يونيو 2026, اليوم/إغلاق/مسح buttons). Native control can't match RTL header, "اليوم"/"مسح" actions, or month/year dropdowns. |
| U2 | Invoice line grid does not auto-expand | 🟠 | `addRow` only appends on explicit click; typing into the last row does not spawn a new blank row (Al-Aseel behavior). |
| U3 | Header layout differs from Al-Aseel | 🟠 | Field order/grouping (مسلسل، رقم الصنف، اسم الصنف، الكمية، سعر الوحدة، الإجمالي) and the top meta band differ from the screenshot. |
| U4 | Forms don't use available width; side nav wastes space | 🟡 | Invoices should open as full-page workspace; maximize usable area. |
| U5 | Payment section placement ≠ Al-Aseel | 🟡 | Cash/cheque block位置 differs. |
| U6 | Label/input alignment inconsistent; weak accounting visual hierarchy | 🟡 | Needs consistent RTL label-above/right alignment + status color-coding (debtor red / creditor green / paid). |
| U7 | No calculator popup on numeric fields | 🟡 | Al-Aseel pops a calculator and transfers the result into the active field. |
| U8 | Real-estate module nav placement | 🟡 | See 3.6. |

---

## 5. BACKEND ENGINEERING AUDIT

| # | Issue | Sev | Root cause | Fix |
|---|---|---|---|---|
| B1 | Unshaped 500s (`exception_handler` returns `None`) | 🔴 | Default DRF behavior for non-API exceptions | Construct 500 envelope `{detail, code, trace_id}`; attach correlation id to logs |
| B2 | Broad `except Exception as e: return Response({"error": str(e)}, 400)` in many actions (`post_invoice`, `convert`, `payment_voucher`, …) | 🟠 | Catch-all hides real status (a 500-class bug returns 400) and leaks internals | Narrow to domain exceptions; map unknown → 500 with trace_id |
| B3 | No `/api/health/` view | 🔴 | Never added | Add lightweight health view (DB ping optional) |
| B4 | Tenant-missing returns long Arabic validation string | 🟡 | Helpful but inconsistent error shape | Standardize error envelope/code (`TENANT_MISSING`) |
| B5 | No request/response logging middleware for tracing recurring API failures | 🟠 | Logging is exception-only | Add async-safe structured logger (see §12) |
| B6 | `auto_post` swallows post errors onto `invoice._auto_post_error` then returns 201 | 🟡 | Silent partial success | Surface as a structured warning the UI must display |

**Validation/transactions:** posting paths use `transaction.atomic()` and idempotent `post_journal()` — good. Concurrency on `next_invoice_number` should be checked for race under load (unique constraint will catch it but yields a 500 today — see B1).

---

## 6. FRONTEND ENGINEERING AUDIT

| # | Issue | Sev | Root cause | Fix |
|---|---|---|---|---|
| F1 | Composite screens load via `Promise.all([...])` (Sales Settings loads 5 endpoints) | 🔴 | One rejection rejects all → whole page shows "API Error" | `Promise.allSettled`; degrade per-section; show which datasource failed |
| F2 | No draft auto-save / `beforeunload` guard in `SalesInvoiceEditor` | 🔴 | Feature absent | Debounced autosave to Dexie + router `useBlocker` + `beforeunload` |
| F3 | Errors rendered as raw `e.message` strings (`flattenDrfError`) | 🟠 | No typed error model | Typed `ApiError {status, code, detail, fieldErrors}`; field-level surfacing |
| F4 | `SalesInvoiceEditor.tsx` is 2218 lines, single component | 🟡 | Organic growth | Extract header / line-grid / totals / payment subcomponents (no behavior change) |
| F5 | Heartbeat base URL mismatch (A5) | 🟠 | Duplicate base resolver | Share `apiBase()` |
| F6 | Offline Dexie mirror only for products + partners | 🟠 | Wiring incomplete from task7 | Mirror accounts/tax-rates/cost-centers used by composite screens |

---

## 7. OFFLINE MODE AUDIT

| # | Issue | Sev | Root cause | Fix |
|---|---|---|---|---|
| O1 | Connectivity heartbeat hits non-existent `/api/health/` | 🔴 | Endpoint missing (A1) | Add endpoint; on non-ok → "degraded" state |
| O2 | `heartbeat()` only acts on `res.ok`; a reachable-but-erroring server leaves state stale | 🟠 | Missing `else` branch | Treat non-ok as offline/degraded; update on every result |
| O3 | `OfflineBanner` has `const hasOfflineData = true;` (hardcoded dead branch) | 🟡 | Placeholder never wired | Compute from Dexie `cache_meta`; show real "آخر مزامنة"; red vs yellow meaningfully |
| O4 | Offline notification text not configurable from admin | 🟡 | Hardcoded Arabic string | Settings-driven message |
| O5 | "Random red errors" while offline | 🟠 | Write paths throw network errors instead of routing to mutation queue uniformly | Funnel all writes through `offlinePost/Patch/Delete` with consistent toast |
| O6 | Warning sometimes persists after reconnect | 🟡 | Banner keyed off `status.online`, but heartbeat can't flip back to online (O1/O2) | Fixing O1/O2 resolves this |
| O7 | Offline activity / sync status unclear | 🟡 | `PendingMutationsPanel` exists but no high-level sync state surface | Add explicit sync status chip (idle/queued N/syncing/conflict) |

---

## 8. GAP ANALYSIS MATRIX

| Module | Current State | Expected (Al-Aseel / best practice) | Gap | Severity |
|---|---|---|---|---|
| API errors | Bare 500 / 400 catch-all, generic message | Shaped envelope + trace id + field errors | Error contract redesign | 🔴 |
| Health/Offline | Heartbeat to missing endpoint | Real health check + self-healing indicator | Add endpoint + fix heartbeat | 🔴 |
| Sales settings load | `Promise.all` all-or-nothing | Resilient per-section load | `allSettled` + degrade | 🔴 |
| Sales invoice draft | Lost on navigate | Auto-saved draft, restore on return | Autosave + guard | 🔴 |
| Negative stock | Blocked by default | Selling below stock allowed | Global policy flag → allow | 🔴 |
| Customer balance | Async, credit-only, no status | Immediate balance + debtor/creditor + GL link | Live balance widget | 🟠 |
| Invoice profit | Not shown | Revenue − COGS per invoice | Profit line in totals | 🟠 |
| Date picker | Native `type=date` | Al-Aseel Arabic calendar | Custom DatePicker | 🟠 |
| Line grid | Manual add only | Auto-expand on last-row fill | Auto-row logic | 🟠 |
| Purchase currency | USD-leaning default | ILS (NIS) default | Default + override | 🟠 |
| Item picker UX | Modal, inefficient | Fast inline search/keyboard | Picker UX upgrade | 🟠 |
| Receipt voucher nav | Returns to wrong screen | Correct back-stack | Nav fix | 🟠 |
| Workspace | Sidebar wastes space | Full-page invoice workspace | Layout | 🟡 |
| Real-estate nav | Flat sidebar peer | Inside accounting/assets | Re-parent nav | 🟡 |
| Calculator | None | Popup, transfers to field | Calculator component | 🟡 |
| Offline banner | Hardcoded branch | Data-driven freshness | Wire to cache_meta | 🟡 |

---

## 9. REMEDIATION PLAN — MILESTONES

> Each milestone: Objective · Files · DB · API · Frontend · Risks · Verification · Rollback.

### M1 — API Error Contract & Health (🔴 unblocks everything)
- **Objective:** Eliminate the systemic "API Error" and the broken offline heartbeat.
- **Files:** `core/exception_handler.py`, `core/urls.py`, new `core/health.py`, `frontend_v2/services/restApi.ts`, `frontend_v2/hooks/useOnlineStatus.ts`.
- **DB:** none.
- **API:** add `GET/HEAD /api/health/`; shape 500 envelope `{detail, code, trace_id}`; correlation-id header.
- **Frontend:** typed `ApiError`; single `apiBase()`; heartbeat handles non-ok as degraded.
- **Risks:** changing error shape may break callers that read `e.message` — keep `detail` human-readable.
- **Verify:** force a 500 → see shaped body + trace id in logs; disconnect network → banner flips; reconnect → banner clears.
- **Rollback:** revert handler + remove route; heartbeat falls back to `navigator.onLine`.

### M2 — Resilient Composite Loads (🔴)
- **Objective:** Sales Settings (and similar) never white-screen on one bad endpoint.
- **Files:** `SalesSettingsPage.tsx`, other `Promise.all` screens (audit list).
- **Frontend:** `Promise.allSettled`; per-section error chips.
- **Verify:** kill `accounting/tax-rates/` → page still renders, only that section degraded.
- **Rollback:** revert to `Promise.all`.

### M3 — Negative-Stock Policy (🔴 accounting integrity)
- **Objective:** Allow selling below available stock per business rule, with audit trail.
- **Files:** `sales/serializers.py:64-71`, `inventory/services.py:71-82`, `SalesSettings` model, `SalesSettingsPage.tsx`.
- **DB:** add `SalesSettings.allow_negative_stock_default` (or reuse) migration.
- **API:** posting respects global default unless product overrides.
- **Frontend:** settings toggle + non-blocking warning ("الكمية تتجاوز المتوفر — سيُسمح بالبيع").
- **Risks:** over-permissive if mis-toggled; keep a visible warning + log line (already logs `NEGATIVE STOCK ALLOWED`).
- **Verify:** sell qty > on-hand → succeeds with warning; stock goes negative; journal still balanced.
- **Rollback:** flip default to block.

### M4 — Sales Invoice Draft Safety (🔴/🟠)
- **Objective:** No lost invoices; auto-save drafts.
- **Files:** `SalesInvoiceEditor.tsx`, `services/offline/mutationClient.ts`, Dexie schema.
- **Frontend:** debounced autosave to Dexie; `beforeunload` + router blocker; restore-draft prompt.
- **Verify:** type, navigate away → prompt; reload → draft restored.

### M5 — Customer Balance / Debtor-Creditor / GL Drill-down + Profit (🟠)
- **Objective:** Al-Aseel-style customer panel + invoice profit.
- **Files:** `SalesInvoiceEditor.tsx`, `partners` balance endpoint, GL route.
- **API:** lightweight `GET /api/partners/{id}/balance/` (immediate net balance + debtor/creditor).
- **Frontend:** balance widget on customer select (cash + credit); clickable → GL; profit line (revenue − COGS) in totals.

### M6 — Al-Aseel Date Picker + Auto-Expanding Grid + Header Parity (🟠)
- **Files:** new `components/ui/AseelDatePicker.tsx`, `SalesInvoiceEditor.tsx`, line-grid component.
- **Frontend:** custom RTL calendar (اليوم/إغلاق/مسح, month/year dropdowns); auto-append blank row on last-row fill; header layout to match screenshot.

### M7 — Purchase Invoice Parity (🟠)
- **Files:** `PurchaseInvoice.tsx`.
- **Frontend:** ILS-first currency default; responsive field layout; auto-expanding, larger item grid.

### M8 — Item Picker UX + Calculator + Payment Placement (🟡)
- **Files:** `SalesProductPickerModal.tsx`, new `Calculator` component, payment section.

### M9 — Offline Polish (🟡)
- **Files:** `OfflineBanner.tsx`, `useOnlineStatus.ts`, settings, write paths.
- Wire banner freshness to `cache_meta`; configurable message; funnel all writes through queue; sync-status chip.

### M10 — Navigation & Workspace (🟡)
- Full-page invoice workspace; re-parent real-estate; fix receipt-voucher back-stack.

### M11 — Logging & Observability (🟡)
- Async structured logger (§12) + request/trace middleware.

### M12 — Repo Hygiene (🟢)
- Remove `github.zip`/`dist*.zip` from VCS; confirm `frontend_v2` canonical; quarantine legacy `frontend/`.

---

## 10. IMPLEMENTATION ORDER (Phases)

- **Phase A — Critical Bugs:** M1, M2, M4 (save/load/error/health).
- **Phase B — Accounting Integrity:** M3 (negative stock), M5 profit/balance correctness.
- **Phase C — ERP Workflow Completion:** M5 GL drill-down, M7 purchase, M8 payments/picker, M10 receipt nav.
- **Phase D — UX Modernization:** M6 date/grid/header, M8 calculator, M10 workspace, real-estate.
- **Phase E — Performance & Stability:** M9 offline, M11 logging, M6 Dexie mirror completion, M12 hygiene.

---

## 11. MISSING INFORMATION & ASSUMPTIONS (Rule 2)

**Missing / needs confirmation:**
1. Exact Al-Aseel header field order and which fields are required vs optional (only two screenshots provided).
2. Whether negative-stock-allow should be **global default**, per-warehouse, per-user-permission, or per-product override priority.
3. Where exactly real-estate should live in the Al-Aseel menu tree.
4. Calculator behavior spec (basic vs tape/memory; rounding rules).
5. Whether multi-currency on sales must show dual-currency totals (ILS + foreign) like Al-Aseel.
6. Production error budget / whether 500s are currently logged anywhere centrally.

**Assumptions (stated, not silently applied):**
- A1: `frontend_v2` is the canonical/production frontend; `frontend/` is legacy.
- A2: "Selling below stock must be allowed" means a **business-wide default** with a visible non-blocking warning, not silent over-sell.
- A3: ILS = NIS = شيكل is the house currency for purchases.
- A4: The Al-Aseel calendar in screenshot 1 is the required date-picker pattern for both sales and purchase.

---

## 12. LOGGING STRATEGY (design only)

Lightweight async, non-blocking:
- **Backend:** Python `logging` with a `QueueHandler`/`QueueListener` (stdlib, no new dep) so writes never block the request; levels INFO/WARN/ERROR; attach `trace_id` (correlation id from M1) to every record; one ERROR per unhandled exception with stack + request path + tenant.
- **Frontend:** thin `logger.ts` buffering WARN/ERROR and flushing to a `POST /api/client-logs/` on `requestIdleCallback`; never throws; drops on offline.
- **Goal:** make recurring API failures traceable end-to-end by `trace_id` without UX impact.

---

## 13. PROJECT_MAP.md DRAFT (delta to existing)

The existing `PROJECT_MAP.md` is accurate for the offline/PWA layer. Task-8 additions:

```
[KNOWN_ISSUES]  (root-caused)
- /api/health/ missing → offline indicator broken (core/urls.py, useOnlineStatus.ts)
- custom_exception_handler returns None on unhandled exc → opaque 500 "API Error"
- Composite screens use Promise.all → one bad endpoint breaks whole page
- SalesInvoiceEditor: no autosave, no beforeunload guard, native date input, no auto-row
- Negative-stock blocked by default; business requires allow
- OfflineBanner hasOfflineData hardcoded true
- Purchase currency defaults USD-leaning, grid non-expanding
- Dexie mirror only covers products + partners (accounts/tax-rates/cheques uncovered)

[ORPHANS_AND_PENDING]
- frontend/ (legacy) vs frontend_v2/ (canonical) — confirm + quarantine
- github.zip (125MB), dist*.zip committed — remove from VCS
- OldPurchaseInvoice.tsx legacy component
- SyncConflictModal manual-merge editor (deferred from task7)

[IMPLEMENTATION_ROADMAP]
Phase A (M1,M2,M4) → Phase B (M3,M5) → Phase C (M5,M7,M8,M10)
→ Phase D (M6,M8,M10) → Phase E (M9,M11,M12)
```

---

## 14. EVIDENCE INDEX (file:line)

- `frontend_v2/hooks/useOnlineStatus.ts:20` — heartbeat → `/api/health/` (missing)
- `core/urls.py:23-39` — no health route
- `core/exception_handler.py` — returns `None` on unhandled exc
- `frontend_v2/components/sales/SalesSettingsPage.tsx:87-93` — `Promise.all` of 5 endpoints
- `sales/serializers.py:64-71`, `inventory/services.py:71-82` — negative-stock block
- `frontend_v2/components/sales/SalesInvoiceEditor.tsx:1448,1461,1609,2066` — native `type="date"`
- `…/SalesInvoiceEditor.tsx:849-853` — manual `addRow`, no auto-expand
- `…/SalesInvoiceEditor.tsx:231,645,791` — `dirtyRef` used only for PATCH; no `beforeunload`
- `…/SalesInvoiceEditor.tsx:1772-1783` — balance shown only for credit + after `creditHint`
- `frontend_v2/components/offline/OfflineBanner.tsx:21` — `hasOfflineData = true` hardcoded
- `frontend_v2/components/procurement/PurchaseInvoice.tsx:49` — `currency_code === 'ILS' ? 'ILS' : 'USD'`
- `frontend_v2/components/Sidebar.tsx:101` — real-estate as flat sidebar peer

---

> **AWAITING APPROVAL.** No code will change until you approve the plan or pick which phase to start. Reply with the phase/milestone to begin (recommend **Phase A → M1**).
