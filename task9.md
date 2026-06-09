# TASK 9 — Audit & Remediation Plan (smart.ktragroup.com / K.T.R.A ERP)

> **Status:** AUDIT + PLAN ONLY. No production code in this file. Awaiting approval.
> **Date:** 2026-06-09 · **Stack verified:** Django 6.0.1 (latest stable 6.0.6, 2026-06-03), DRF 3.16, React 19.2, Vite 6.2, Tailwind 4.3, Dexie 4.4.
> **Author role:** Staff SWE + Tech Lead. Plans are atomic, executable by a cheaper model.

---

## 0. ASSUMPTIONS (Think Before Coding)

1. **Canonical frontend** is `frontend_v2/` (legacy `frontend/` was deleted in task8 M12).
2. **Deployment lag:** task8 (M1–M12) is merged on `main` but the live site `smart.ktragroup.com` appears to run an **older build**. Several items the user reports as "missing" (customer balance + GL drill-down = task8 M5; inline cash/cheque payment = task8 M8) **already exist in repo `main`**. Therefore each related task below is framed as **"verify deployed → close the residual gap,"** not greenfield. **A redeploy of `main` is a prerequisite** and is tracked as M0-T1.
3. **Al-Aseel** remains the reference for layout/semantics (per task8).
4. **No new runtime dependencies** are required for task9 (Simplicity First). Optional: bump Django 6.0.1 → 6.0.6 (patch, safe).
5. Single-tenant in practice today (`resolveTenantId()` → 1); multi-entity is task10 and out of scope here.

> **No blocking ambiguities for task9.** Items below are grounded in current code (file:line cited).

---

## 1. AUDIT FINDINGS (root-caused, evidence-based)

Legend — Category: BE=Backend, FE=Frontend, LOGIC=Business logic, UI=UI/UX. Sev: 🔴Critical / 🟠High / 🟡Medium.

| ID | Cat | Sev | Finding | Root cause (file:line) | Acceptance criteria |
|----|-----|-----|---------|------------------------|---------------------|
| F1 | LOGIC | 🔴 | **Sales settings don't reflect on a new invoice** (e.g. VAT). Changing `default_vat_rate`/flags in Sales Settings does not change the new invoice. | `SalesInvoiceEditor.tsx:302` `defaultVatRateId` memo seeds **only empty lines** (`tax_rate===""`, line 316-318); `salesSettings` is fetched once by the parent page at mount and **never re-fetched** after the settings page saves. No cross-screen invalidation. | After saving Sales Settings and opening a **new** invoice, the line VAT + totals reflect the new `default_vat_rate` without a hard refresh. Toggling a VAT-related flag changes the computed "الضريبة المضافة". |
| F2 | FE/UI | 🟠 | **"مدفوع نقداً" / "مدفوع شيكات" under the invoice total** are not visible/usable as the Al-Aseel layout (screenshot). | task8 M8 relocated the voucher inline (`SalesInvoiceEditor.tsx` ~1699+ cash input, ~1900 totals show "مدفوع نقدا"/"مدفوع شيكات"). Live site shows old build (deploy lag, see A2). Possible residual: the cash field lives in a tab that can be clipped (see U5). | In the live invoice, directly under "مبلغ الفاتورة الإجمالي" there are editable **مدفوع نقداً** + **مدفوع شيكات** rows, plus read-only **المتبقي على الحساب**, matching the screenshot order. Values flow into the payment voucher on save. |
| F3 | LOGIC/FE | 🟠 | **Customer GL summary on select** (debtor/creditor + clickable → General Ledger) reported missing. | Implemented in task8 M5 (`SalesInvoiceEditor.tsx` balance row + `onOpenGeneralLedger` threaded App→Page→editor) but **gated on `creditHint`** load and **not deployed**. Also the balance only shows in the totals dock, not as a header summary near the customer field. | On selecting a customer, a summary "رصيد العميل: X (مدين/دائن)" appears **near the customer field**, color-coded, and clicking it opens the General Ledger filtered to that customer's `linked_account`. Works for cash and credit. |
| F4 | LOGIC/FE | 🟠 | **Invoice number not always shown.** New invoice shows "— جديدة —"; after save shows internal DB id, not the real `invoice_number`. | `SalesInvoiceEditor.tsx:1952` renders `draftId ? '#'+draftId : '— جديدة —'` — it displays the **PK**, never `invoice_number`. No next-number preview endpoint consumed. | A new invoice shows the **next reserved invoice number** (e.g. `D-0105`) on open; a saved draft shows its real `invoice_number` prominently; the number is never blank. |
| U5 | UI | 🔴 | **Tabs not unified → elements get hidden/clipped.** | Two problems: (a) **inconsistent tab systems** — `AseelDocumentShell` tab strip vs. ad-hoc tab state in `AccountingCoaPage.tsx`, `ImportDocumentScreen.tsx`, `ItemForm.tsx`, `CreditDebitNotesPage.tsx`, `SalesCustomerPaymentsPage.tsx`. (b) The `.aseel-tabs` strip (`AseelDocumentShell.tsx:159`) has **no overflow handling** (`styles/index.css` `.aseel-tabs`), so many tabs clip off-screen (matches the circled cut-off tab row in the screenshot). | One shared tab primitive used by all listed screens. The invoice tab strip never clips: tabs **wrap or horizontally scroll** with all of them reachable at every viewport width tested (1366, 1024, 768). No element is unreachable. |
| U6 | UI | 🟠 | **Low contrast / lifeless UI.** Soft ink on beige + opacity dims text; no status color semantics. | `styles/index.css`: `--aseel-ink-soft:#5c5a45` on `--aseel-bg:#e9e6d6` (≈3:1, below WCAG AA 4.5:1); `.aseel-text-soft` + `opacity:.7/.4` used for labels. No green/red debit-credit semantics in the design system. | Body/label text meets **WCAG AA ≥4.5:1**. A documented semantic palette exists: creditor=green, debtor=red, paid=green, due=amber. Applied to balances, payment status, totals. Verified with a contrast checker on 5 key screens. |

### Additional issues discovered during audit (not in the brief)

| ID | Cat | Sev | Finding | Root cause | Acceptance criteria |
|----|-----|-----|---------|-----------|---------------------|
| F7 | FE | 🟠 | **No cross-screen settings invalidation.** Editing settings/partners/products doesn't refresh open editors. Generalizes F1. | Each screen `useState`+`Promise.allSettled` at mount; no event bus / query cache. | A lightweight `settingsVersion` signal (or `BroadcastChannel`) causes the invoice editor to refetch `salesSettings` after a settings save. |
| F8 | BE | 🟡 | **No "next invoice number" preview endpoint.** `next_invoice_number()` exists but is only called at create-time inside the serializer, so the FE can't show it pre-save. | `sales/services.py:1331` is server-internal; no GET action exposes it. | `GET /api/sales/invoices/next-number/?book=<n>` returns the next number for the active tenant/book without consuming the sequence. |
| F9 | BE | 🟡 | **Sequence vs. concurrency.** `next_invoice_number` + unique constraint can yield a 500 on race (two drafts). | `sales/services.py:1331` likely `max()+1`; relies on unique constraint to catch dup → unhandled IntegrityError surfaces as opaque 500 (ties to task8 A2). | Concurrent create of 2 invoices yields 2 distinct numbers, no 500; on collision the create retries once. |
| U10 | UI | 🟡 | **Date control / numeric calculator consistency.** task8 added `AseelDatePicker` + calculator but not every date/numeric field uses them. | Partial adoption (task8 M6/M8). | All date inputs use `AseelDatePicker`; numeric money fields support the calculator popover. |
| BE11 | BE | 🟡 | **`django.request` 500s now shaped (task8 M1)** but client-log sink + tracing are new and **unproven in prod**. | task8 M11 logging just landed. | A forced 500 returns `{detail,code,trace_id}` and the same `trace_id` appears in server logs and (if client-reported) the client-log sink. |

---

## 2. REMEDIATION PLAN — MILESTONES & ATOMIC TASKS

> Each task: **ID · Title · Files · Steps · Verifiable Goal · Depends on.** Sized for a cheaper model.

### M0 — Deploy parity & truth-check (do first)

- **M0-T1 · Redeploy `main` and re-audit live**
  - Files: deployment pipeline (Vercel/host config), none in repo.
  - Steps: trigger production build+deploy of current `main`; reload `smart.ktragroup.com`; re-check F2/F3 against the live UI; record which items are deploy-lag vs. real gaps.
  - Verifiable Goal: a checklist marking F2/F3 as "present after deploy" or "still missing."
  - Depends on: —

### M1 — Sales-settings → invoice live binding (fixes F1, F7)

- **M1-T1 · Add a settings-changed signal**
  - Files: `frontend_v2/services/salesApi.ts` (or new `frontend_v2/utils/settingsBus.ts`).
  - Steps: create a tiny pub/sub (`BroadcastChannel('ktra-settings')` + in-memory fallback). On `updateSalesSettings` success, publish `{type:'sales-settings'}`.
  - Verifiable Goal: calling `updateSalesSettings` emits one event; a unit listener receives it.
  - Depends on: —
- **M1-T2 · Editor refetches settings on signal + on mount-focus**
  - Files: `frontend_v2/components/sales/SalesInvoicesPage.tsx`, `SalesInvoiceEditor.tsx`.
  - Steps: in the page that loads `salesSettings`, subscribe to the bus and re-run the settings fetch; pass fresh `salesSettings` down. Also refetch when the invoice editor opens.
  - Verifiable Goal: save VAT=0 in settings → open new invoice → "الضريبة المضافة" = 0 with no hard refresh; set VAT=16 → new invoice shows 16%.
  - Depends on: M1-T1.
- **M1-T3 · VAT default also applies to the first auto-row + recompute**
  - Files: `SalesInvoiceEditor.tsx:302-318`.
  - Steps: ensure `defaultVatRateId` re-seeds blank lines when `salesSettings.default_vat_rate` changes; recompute totals memo on that dependency.
  - Verifiable Goal: changing the default rate updates totals of empty lines immediately; existing user-edited lines are untouched.
  - Depends on: M1-T2.

### M2 — Payment fields under total (fixes F2)

- **M2-T1 · Verify/relocate cash+cheque rows directly under grand total**
  - Files: `SalesInvoiceEditor.tsx` (totals dock ~1900-1990).
  - Steps: ensure the order is: مجموع البنود → خصم → الضريبة المضافة → **مدفوع نقداً (editable)** → **مدفوع شيكات (editable/opens cheque list)** → الربح الإجمالي → **مبلغ الفاتورة الإجمالي** → **المتبقي على الحساب**. Match screenshot.
  - Verifiable Goal: side-by-side with the screenshot, row order + labels match; cash field is editable and feeds the voucher payload.
  - Depends on: M0-T1.
- **M2-T2 · Cheque sub-list reachable from the total dock**
  - Files: `SalesInvoiceEditor.tsx`.
  - Steps: ensure "مدفوع شيكات" links to the inline cheque editor (already exists post-M8) and the displayed total = sum of cheque amounts.
  - Verifiable Goal: adding cheques updates "مدفوع شيكات" and "المتبقي على الحساب" live.
  - Depends on: M2-T1.

### M3 — Customer GL summary on select (fixes F3)

- **M3-T1 · Header customer-balance summary widget**
  - Files: `SalesInvoiceEditor.tsx`.
  - Steps: render a compact summary near the customer field on select: "رصيد العميل: 1,200 (مدين)" using existing `creditHint.open_balance`; color via U6 palette.
  - Verifiable Goal: selecting a customer shows the summary within ~400ms (debounced) for both cash and credit invoices.
  - Depends on: M0-T1, M6 (palette).
- **M3-T2 · Clickable → General Ledger drill-down**
  - Files: `SalesInvoiceEditor.tsx`, `SalesInvoicesPage.tsx`, `frontend_v2/App.tsx`.
  - Steps: reuse task8 `onOpenGeneralLedger(accountId)`; wire the summary's click to the customer's `linked_account`. Confirm prop is threaded App→Page→editor.
  - Verifiable Goal: clicking the summary opens `accounting-general-ledger` filtered to that account; back returns to the invoice.
  - Depends on: M3-T1.

### M4 — Invoice number always visible (fixes F4, F8, F9)

- **M4-T1 · Backend next-number preview action**
  - Files: `sales/views.py` (SalesInvoiceViewSet), `sales/services.py`.
  - Steps: add `@action(detail=False, methods=['get'], url_path='next-number')` returning `{next_number}` from `next_invoice_number(tenant_id, book)` **without persisting**.
  - Verifiable Goal: `GET /api/sales/invoices/next-number/?book=0` returns a string; calling twice returns the same value (non-consuming).
  - Depends on: —
- **M4-T2 · Harden numbering against races**
  - Files: `sales/services.py:1331`.
  - Steps: wrap create in `transaction.atomic()`; on `IntegrityError` for the unique (tenant, invoice_number) constraint, recompute + retry once.
  - Verifiable Goal: a test creating 2 invoices concurrently yields distinct numbers, no 500.
  - Depends on: M4-T1.
- **M4-T3 · FE shows real number (draft + new)**
  - Files: `SalesInvoiceEditor.tsx:1952`, `frontend_v2/services/salesApi.ts`.
  - Steps: on open of a new invoice, call next-number and display it; after save, display `invoice_number` (not `#id`).
  - Verifiable Goal: number field never blank; new shows `D-####`, saved shows its `invoice_number`.
  - Depends on: M4-T1.

### M5 — Unified tab system (fixes U5)

- **M5-T1 · Make `.aseel-tabs` overflow-safe**
  - Files: `frontend_v2/styles/index.css` (`.aseel-tabs`, `.aseel-tabscol`).
  - Steps: add `flex-wrap:wrap` (or `overflow-x:auto; scrollbar` for horizontal) so all tabs are reachable; ensure the active tab is scrolled into view.
  - Verifiable Goal: at 768/1024/1366 px no tab is clipped; every tab is clickable.
  - Depends on: —
- **M5-T2 · Adopt `AseelDocumentShell` tabs (or a shared `<Tabs>`) on the divergent screens**
  - Files: `AccountingCoaPage.tsx`, `ImportDocumentScreen.tsx`, `ItemForm.tsx`, `CreditDebitNotesPage.tsx`, `SalesCustomerPaymentsPage.tsx`; optional new `frontend_v2/components/ui/Tabs.tsx` if shell is too heavy.
  - Steps: replace ad-hoc tab markup/state with the shared primitive; keep behavior identical.
  - Verifiable Goal: all five screens render tabs with identical markup/classes; no visual regression; tsc + build pass.
  - Depends on: M5-T1.

### M6 — Design system: contrast + status semantics (fixes U6, U10)

- **M6-T1 · Raise text contrast to WCAG AA**
  - Files: `frontend_v2/styles/index.css` (`--aseel-ink`, `--aseel-ink-soft`, `.aseel-text-soft`, `opacity` rules).
  - Steps: darken `--aseel-ink-soft` (e.g. `#3f3d2c`); replace label `opacity:.7` with a token color ≥4.5:1; audit `.aseel-text-soft` usages.
  - Verifiable Goal: a contrast checker reports ≥4.5:1 for body/labels on the 5 main screens.
  - Depends on: —
- **M6-T2 · Define + apply semantic status palette**
  - Files: `frontend_v2/styles/index.css` (new tokens `--status-credit/-debit/-paid/-due`), consuming components (`SalesInvoiceEditor.tsx` balances/totals, payments pages).
  - Steps: add tokens; apply: creditor=green, debtor=red, paid=green, due=amber. Single source of truth (no inline hex like task8 used `#16a34a`).
  - Verifiable Goal: creditor balances render green, debtor red across invoice + GL; values come from tokens (grep shows no scattered hex for these states).
  - Depends on: M6-T1.
- **M6-T3 · Finish date/number control adoption**
  - Files: remaining `type="date"` / money inputs across sales/procurement screens.
  - Steps: convert stray native date inputs to `AseelDatePicker`; attach calculator popover to money fields.
  - Verifiable Goal: grep finds no `type="date"` in sales/procurement editors; money fields show the calculator.
  - Depends on: —

### M7 — Logging proof (closes BE11)

- **M7-T1 · Verify trace correlation end-to-end**
  - Files: none (validation), optionally `core/health.py`.
  - Steps: force a 500; confirm response `trace_id` == server log `trace_id`; POST a client log and confirm it lands in the `client_logs` logger with the same id.
  - Verifiable Goal: a short runbook in PROJECT_MAP shows the correlated ids.
  - Depends on: M0-T1.

---

## 3. EXECUTION ORDER

M0 → (M1, M4, M5 in parallel) → (M2, M3 after M0/M6 palette) → M6 → M7.
**Critical path for the reported pain:** M0 (deploy) → M1 (settings live) → M5 (tabs/hidden) → M4 (number) → M6 (contrast).

---

## 4. VERIFICATION MATRIX (per reported issue)

| Reported | Task(s) | Pass test |
|---|---|---|
| Settings not reflecting (VAT) | M1 | Change VAT in settings → new invoice reflects it |
| Cash/cheque under total | M0,M2 | Rows present & editable in screenshot order |
| Customer GL summary + link | M0,M3 | Summary on select; click → GL |
| Invoice number always shown | M4 | Never blank; real number |
| Tabs hidden/clipped | M5 | No clipped tab at 3 widths |
| Contrast/lifeless | M6 | AA contrast + status colors |
