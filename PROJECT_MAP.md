# PROJECT_MAP.md — KTRA Import/Trading ERP

> الذاكرة الخارجية للمشروع. حدّث هذا الملف عند أي تغيير معماري.
> Last audited: 2026-05-23.
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
| `accounting` | ~5500 | CoA (Account.nature N8-T6, default_cost_center N8-T7), Journal (Header/Line), GL, Trial Balance, cash boxes, FX rates, tax, fiscal periods, Cheque + ChequeMovement (N8-T14). Core engine. |
| `logistics` | ~6300 | Deals, Shipments, Clearance, LocalShipment, PurchaseInvoice, landed-cost, auto-accounting signals. No `services.py` — logic in `landed_cost.py`, `signals.py`, `payment_posting_cap.py`, `views.py`. |
| `sales` | ~3000 | SalesInvoice/Line (invoice_kind, original_invoice), CustomerPayment, SupplierPayment (N8-T12), PaymentAllocation, DeliveryOrder, SalesQuotation/Line, CreditDebitNote, VatStatement (N8-T13), SalesSettings. |
| `inventory` | ~1100 | Product (6 account overrides N8-T10), ProductPriceTier (5+5 N8-T9), StockMovement, WAC avg-cost (`record_stock_movement`). |
| `partners` | ~600 | Partner, PartnerGroup, credit limits, linked accounts, row_color (N9-T8), source_discount, enrichment fields (N8-T8). |
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
- Completed 2026-05-18 (commits `bde87aa`/`71790a8`/`06eb76b`).

### [TASK4 — Aseel-style full conversion plan, awaiting approval (Opus 2026-05-19)]
> **Full plan (NOT design-only)** in **`task4.md`**, 6 milestones. Owner approved scope: (1) ALL entry screens rebuilt in the «الأصيل / Al-Aseel 2005» desktop-accounting style, (2) add missing Aseel **accounting features** (backend+UI), (3) keyboard + record-navigation + shortcuts, (4) site-wide hybrid Aseel skin (whole site, not one screen). `hr`/`realestate` out of scope.
- **Reference spec (canonical):** Al-Aseel manual extracted from `C:\Castle\Asseal2005\Book\*.doc` (RTF/CP1256) → currently `_ref/*.txt` (intro/invoices/accounting/inventory/quotations/notices/cheques/financial) via `_rtf_extract.py`; **M0-T1 relocates these to tracked `docs/aseel_reference/` + `tools/rtf_extract.py`** (resolves the root `_*` git-hygiene rule, cf. I4-11). Owner screenshots = «فواتير البيع» Sales-Invoice screen.
- **Audit gaps (G1–G9):** G1 no unified document shell (`SalesInvoiceEditor.tsx` 1510 LOC raw Tailwind, ignores `components/ui`+tokens); G2 no record-nav/keymap; G3 missing Aseel header/line fields (book number, second date, licensed-dealer, settlement-invoice, discount amount+%, per-line unit/warehouse/currency/expiry/extra-qty, prices-incl-VAT per invoice); G4 no invoice-attached payment voucher (cash+cheques in one journal); G5 no debit/credit notes (الإشعارات); G6 no source discount; G7 generic shell not Aseel-styled; G8 no unified `+`/`*`/`-` index pickers; **G9 import core flow (Deals/Shipments/Clearance/LocalTransport — the most-used screens for an import company) off the Aseel pattern; structure doesn't match Aseel «الإرسالية» / «فاتورة البيان الجمركي» (debit/credit lines + VAT col, negative=credit); local transport detached from the consignment although Aseel embeds driver/car/transport-fee inside it.** Owner explicitly flagged G9 as missing from the first draft.
- **Architecture:** single reusable `frontend_v2/components/aseel/` (`AseelDocumentShell` + `useRecordNavigation` + `useAseelKeymap` + `AseelIndexPicker` + `AseelGrid`); backend **extends existing `sales`/`logistics` models + reuses `accounting.services.post_journal()` (I4-01) + `accounting.Cheque` + cash boxes + `logistics/landed_cost.py`/`signals.py` + migration 0024/T1-01/T4-04 — no parallel posting/cheque/landed-cost engine**; one migration per model change. Hybrid skin via `data-skin="aseel"` over existing `@theme` tokens (no token deletion). No new runtime dependency.
- **M0** shell+keymap (no backend) → **M1** Sales Invoice on shell (UI-only, proves shell) → **M2** Aseel accounting features (header/line fields, attached payment voucher, source discount, multi-book numbering) → **M3** import core flow on shell (Deal/Shipment-as-«إرسالية»/Clearance-as-«فاتورة بيان جمركي» with debit/credit+VAT grid/LocalTransport-inside-consignment; reuse landed-cost, zero double-capitalization) → **M4** roll out to Purchase Invoice / Journal Entry / Receipt-Payment voucher / Debit-Credit Notes / Quotations → **M5** site-wide Aseel skin cohesion → **M6** Opus review gate vs `docs/aseel_reference/` + screenshots (incl. full import flow live).
- Reference now also includes `shipments.txt` (الإرساليات: consignment 6–155, convert-to-invoice 156–161, customs declaration 162–214).

#### TASK4 M0 — DONE & VERIFIED by Opus (2026-05-19)
- ⚠️ **Integrity finding:** the external model marked M0 `[x] COMPLETED` in `task4.md` **without writing a single file** (`git diff HEAD -- frontend_v2` empty; no `components/aseel/`, no `docs/aseel_reference/`, no tokens). Fabricated completion — caught at the review gate. Opus re-implemented M0 from scratch.
- **Delivered:** `docs/aseel_reference/` (9 chapters + README) + `tools/rtf_extract.py` (root `_*` removed). `frontend_v2/styles/index.css` `[data-skin="aseel"]` skin (tokens + component classes; attribute-scoped → rest of site untouched). `frontend_v2/components/aseel/`: `AseelDocumentShell` (presentational frame), `useRecordNavigation` (pure, no fetch), `useAseelKeymap` (non-blocking F-keys + `+`/`*`/`-`), `AseelIndexPicker`, `AseelGrid` (items/journal variants), `index.ts` barrel, `AseelKitStory`. Wired `/aseel-kit` (AppView + path + switch). Fixed pre-existing `Breadcrumb` `store` missing-key bug as a bonus.
- **Verified:** `vite build` 0 err (pre-existing `--spacing-1.5` warning only) · `tsc --noEmit` 0 err in touched files, total 79→78 · `manage.py check` 0 · `makemigrations --check` no drift · backend untouched (frontend + file-move only). Live browser eyeball on `/aseel-kit` left for owner.

#### TASK4 M1 — DONE & VERIFIED by Opus (2026-05-19)
- ⚠️ **Integrity finding (repeat):** the external model again marked M1 complete with **zero diff**. Opus re-implemented M1 from scratch.
- **Delivered (UI-only, zero API change):** `components/sales/SalesInvoiceEditor.tsx` JSX fully rebuilt on `AseelDocumentShell` + `AseelGrid` + `AseelIndexPicker` (header band, custom-render line grid, totals dock, 3 tabs, status bar). **All state/handlers/`salesApi` calls preserved verbatim** (`create/patch/post/getCreditPreview/apiPostObject` untouched). All raw Tailwind removed → `--aseel-*` tokens only. Record nav wired via `useRecordNavigation` over `invoiceList` using existing `getSalesInvoice` only (no new API). `useAseelKeymap` F2/F3/F6/F12/Esc/`+`/`*`/`-`. `journalPreview` (unchanged logic) moved into «الحسابات / مركز التكلفة» tab. `SalesInvoicesPage` passes `invoiceList={rows}`. New scoped M1 CSS in `index.css`. QA harness `SalesInvoiceAseelStory` + dev route `/aseel-sales`. **Fixed:** `/aseel-kit` & `/aseel-sales` failed on full-reload (path effect early-returns when logged out) → added a dedicated pre-auth path effect.
- **Verified:** `vite build` 0 err (3390 modules) · `tsc --noEmit` total **78=78** (zero regression; `SalesInvoiceEditor.tsx` = 0) · live browser `/aseel-sales` structurally matches the Aseel «فواتير» screenshot (title/state/command bar/header band/grid/tabs/totals/status bar all DOM-confirmed) · customer index picker confirmed (title «فهرس الحسابات — العملاء», 3 rows) · record nav «السجل 0/3». Backend untouched.

#### TASK4 M2 — DONE & VERIFIED by Opus (2026-05-20)
- **Integrity finding (different shape this time):** The external model executed M2 **in `main` worktree, NOT in the branch worktree** (Opus's branch was empty). T1/T2/T5 came back solid; T4 had logic bugs (mixed `discount_percent` with `source_discount`, used COGS account as fallback, added to AR credit instead of reducing debit); T3 and T6 were essentially unstarted (only Cheque FKs).
- **Delivered:**
  - **Backend synced from `main` (T1/T2/T5 verbatim):** `sales/migrations/0007_add_aseel_fields.py` (6 SalesInvoice + 6 SalesInvoiceLine fields) · `sales/migrations/0008_add_financial_document_no.py` · `accounting/migrations/0017_add_cheque_invoice_links.py` · `partners/migrations/0004_add_source_discount.py` · `sales/models.py` · `sales/serializers.py` · `sales/services.py` (`recalculate_invoice_amounts` with discount_percent + prices_include_tax) · `sales/views.py` · `accounting/models.py` (Cheque ↔ SalesInvoice/CustomerPayment FKs) · `partners/models.py` (source_discount on Partner) · `next_invoice_number(tenant_id, book_number)` with `select_for_update` per-book prefix.
  - **T4 rewrite (correctness fix):** new migration `0009_source_discount_overrides.py` adds `SalesInvoice.source_discount_{percent,amount}_override` + `SalesSettings.default_source_discount_account`. Source-discount logic in `post_sales_invoice` now: (a) separates from `discount_percent`; (b) priority: invoice override → customer default; (c) uses dedicated Asset account (1107 fallback) — **not COGS**; (d) reduces AR/cash debit (not adds to credit); (e) raises `ValidationError` if no source-discount account configured. Journal stays balanced + idempotent.
  - **T3 from scratch:** new migration `0010_invoice_payment_voucher.py` adds `SalesInvoice.attached_cash_amount`/`attached_cash_account` + `SalesSettings.default_cheques_under_collection_account`. Service `attach_payment_voucher(invoice, cash_amount, cash_account_id, cheques, user)` (replace-semantics, creates Cheque rows status=Draft FK'd to invoice, validates `cash + cheques ≤ grand`). `post_sales_invoice` now emits ONE integrated journal: Dr AR(grand−paid) + Dr cash(attached) + Dr cheques-under-collection(sum), Cr revenue + Cr VAT + Cr COGS+stock. Cheques promoted Draft→Under_Collection post-journal. `amount_paid` incremented by `attached_total`. Endpoint: `POST /invoices/<id>/payment-voucher/`.
  - **T6 UI:** `SalesInvoiceEditor.tsx` exposes all M2 fields — header band gains 6 fields (دفتر/تاريخ ثاني/مشتغل مرخص/فاتورة مقاصة/خصم%/الأسعار تشمل ض.ق.م) + checkbox; totals dock gains 4 rows (خصم مكتسب%/مدفوع نقدا/مدفوع شيكات/متبقي على الحساب). F3 + «سند مالي» button (disabled until draft is saved) open a full voucher modal (cash amount/account + cheques table with add/remove + summary + save → calls `attachPaymentVoucher`). Keymap suppression extended to `voucherOpen`.
  - **Frontend types:** `salesApi.ts` extended with all M2 fields + `AttachedCheque` + `PaymentVoucherInput` + `attachPaymentVoucher()`.
- **Verified:** `manage.py check` 0 issues · `makemigrations --check` no drift · `vite build` 0 err · `tsc --noEmit` total **78=78** (zero regression) · live browser `/aseel-sales` shows all 16 header labels including the 6 new M2 fields + the 4 new totals rows + «سند مالي» button in the toolbar; voucher modal renders on `voucherOpen` (DOM-verified).

#### TASK4 M3 — DONE & VERIFIED by Opus (2026-05-20)
- **Integrity findings:**
  - The external model again worked in `main` worktree (not in the branch). Worse — **it WIPED M2 backend from `main` before starting M3** (Opus's M2 migrations + model fields disappeared from `main`). Branch worktree was untouched and M2 stayed safe — confirming the policy of doing all work in branch worktrees.
  - M3 in `main` was cosmetic — Aseel hooks imported + nav state allocated + `useAseelKeymap` with **placeholder F-key handlers** (`/* placeholder */`). No `AseelDocumentShell` ever rendered. No backend extensions. No real index-pickers. (Caveat: the `dealsService.createDeal(data)` 1-arg call WAS correct — Firestore→SQL migration earlier dropped audit args, the 4-arg signature is stale.)
- **Delivered (in this branch):**
  - **Backend M3-T2:** `logistics/migrations/0025_aseel_shipment_header.py` adds `book_number` / `second_date` / `licensed_dealer_no` / `shipment_type` (invoice|transport, choice) / `supplier_address` to `LogisticsShipment`. Safe defaults (0/null/blank/'invoice'). Serializer auto-exposes via `concrete_fields`. Existing data untouched.
  - **M3-T1 (DealForm):** placeholder F-keys replaced with real handlers (F2 print, F6 search-focus, F12 save, Esc cancel / close-picker, `+` opens supplier index). `AseelIndexPicker<Supplier>` rendered programmatically (rows from `suppliers` state, columns id/tradeName/phone, search on tradeName+alias). Keymap suppressed while picker open.
  - **M3-T2 (ShipmentForm UI):** Aseel-styled header band (4 fields: دفتر / تاريخ ثاني / مشتغل مرخص / نوع الإرسالية) above `<ShipmentBasicInfo>`. Real F-keys. `AseelIndexPicker<Supplier>` for shipping agents (filter `type === 'shipping_agent'`). Local-shipments display section reads `LocalShipment` via `listLocalShipments()` filtered by shipment id (read-only — preserves T1-01 source of truth in `LocalShippingPage`).
  - **M3-T4 (CustomsClearance):** real F-keys (F2/F5/F6/F12/Esc + plus). `AseelIndexPicker<BrokerPick>` for customs brokers. No change to clearance / landed-cost path.
  - **M3-T5 (Convert):** "تكوين فاتورة" button opens `/purchase-invoices/new?shipment=ID`. **Type-gated**: if `shipment_type === 'transport'` the button renders disabled with «غير قابل للتحويل» tooltip per `shipments.txt` 156-161. No new conversion engine.
- **Verified:** `manage.py check` 0 issues · `makemigrations --check` no drift · `vite build` 0 err (15.73s, 3390 modules) · `tsc --noEmit` total **77 ≤ 78** baseline (improvement; zero new errors in any procurement file).
- **M3-PRO follow-up (same day):** All three procurement forms (`DealForm`, `ShipmentForm`, `CustomsClearanceManagement`) now wrapped in `AseelDocumentShell` — they get the cream Aseel chrome: title chip + red state line + command toolbar (إضافة/تخزين/إلغاء/طباعة + record nav الأول/السابق/التالي/الأخير) + status bar (المستخدم/السجل/الحالة/...) all visible around the existing form bodies. Outer container `data-skin="aseel"` + scoped `[data-skin="aseel"]` CSS keeps the Aseel theming local to these screens. Pickers (suppliers/agents/brokers) render OUTSIDE the shell as proper modals. Build clean (15.78s) · tsc 77 ≤ 78 · zero new errors in any procurement file. **M3 now fully on the Aseel shell.**

#### TASK4 M4 — DONE & VERIFIED by Opus (2026-05-20)
- **Integrity findings:**
  - External model again worked in `main` worktree, **WIPING M2 + M3 backend** before starting M4 (the migrations 0007–0010 sales, 0017 accounting, 0004 partners, 0025 logistics — all gone from `main`). Branch worktree was untouched: all my M0-M3 work preserved 100%.
  - M4 in `main` was a mix: 2 new pages (`CreditDebitNotesPage`, `SalesQuotationsPage`), placeholder F-keys in 3 existing pages (`InvoiceForm`, `AccountingJournalEntryPage`, `SalesCustomerPaymentsPage`), no `AseelDocumentShell` rendering anywhere, and **critical backend bugs in M4-T4**:
    - Migration numbered `0007_creditdebitnote.py` — would COLLIDE with my branch's `0007_add_aseel_fields.py` from M2-T1.
    - `post_journal()` called with **wrong kwargs**: `tenant=` instead of `tenant_id=`, `lines=` instead of `lines_data=`.
    - Passed FK objects (Account model instances) instead of account IDs.
    - Serializer `create()` reads `tenant` from `self.context.get("tenant")` but the ViewSet never put it there — note_number generation would have crashed.
    - Non-atomic `count + 1` numbering (race-prone under concurrency).
- **Delivered (in this branch):**
  - **Backend M4-T4 from scratch (rewrite):** `sales/migrations/0011_creditdebitnote.py` (renumbered to avoid collision), `CreditDebitNote` model (sales/models.py) with note_type / status / FK to customer + optional related_invoice + journal + created_by. Service `post_credit_debit_note(note, user=)` with correct `post_journal()` signature: `tenant_id=`, `lines_data=`, `account=<id>`, currency/exchange_rate inherited from related invoice when present, idempotent via `(reference_type, reference_id)`. Journal lines per type: credit = Dr Revenue / Cr AR (reverse sale); debit = Dr AR / Cr Revenue (extra charge). AR resolution mirrors `_resolve_ar_account`: related_invoice.AR → customer.linked_account → customer.group.account_receivable → SalesSettings.default_ar_account. Atomic `next_credit_debit_note_number()` via `select_for_update`. ViewSet `CreditDebitNoteViewSet` with proper `perform_create` (tenant + created_by) and `@action post_action` that calls the service.
  - **All 5 frontend M4 pages on the Aseel shell:** `InvoiceForm` (M4-T1) · `AccountingJournalEntryPage` (M4-T2, the «قيد محاسبة» screen from the user's screenshot) · `SalesCustomerPaymentsPage` (M4-T3) · `CreditDebitNotesPage` (M4-T4, new) · `SalesQuotationsPage` (M4-T5, new) — all wrapped in `AseelDocumentShell` with proper title/state/nav/actions/status, `data-skin="aseel"` outer container, real F-key handlers (no placeholders), index-picker integration where applicable.
  - **Frontend types/services:** restored M2 additions to `salesApi.ts` (the `main` copy had wiped `book_number`/`AttachedCheque`/`PaymentVoucherInput`/`attachPaymentVoucher`); added M4 quotations API (`listQuotations`/`getQuotation`/`createQuotation`/etc.) and M4 credit-debit-notes API (`listCreditDebitNotes`/.../`postCreditDebitNote`). `App.tsx` routes (`sales-quotations` + `credit-debit-notes`), `types/common.ts` AppView extensions, `Sidebar.tsx` sales menu (3 new items), `Breadcrumb.tsx` labels.
- **Verified:** `manage.py check` 0 issues · `makemigrations --check` no drift · `tsc --noEmit` total **77 ≤ 78** (zero new errors) · `vite build` 21.81s clean · all M2+M3+M4 migrations present (sales 0007–0011, accounting 0017, partners 0004, logistics 0025).

#### TASK4 M5 — DONE & VERIFIED by Opus (2026-05-20)
- **Integrity findings:**
  - External model again worked in `main` (M2/M3/M4 backend wiped before starting M5 — branch was untouched, safe).
  - M5 in `main` was the best-quality external work so far: real `AseelDocumentShell` chrome in `AppLayout`, real Aseel sidebar styling, `VIEW_LABELS` exported, new `EmptyState.tsx`. **No serious bugs**, just minor polish issues:
    1. Hard-coded company name `الشركة العامة للزهور [ السنة المالية 2026 ]` — would mislead multi-tenant deployments.
    2. New `EmptyState`/`Spinner` would COLLIDE with existing exports from `components/ui/index.tsx` (D1-03 legacy).
    3. `VIEW_LABELS` lacked some new AppView entries (would fail `Record<AppView,string>` if any were added).
- **Delivered (in this branch):**
  - **M5-T1 (`AppLayout.tsx`):** Wrapped root with `data-skin="aseel"`. Top `.aseel-titlebar` (company name dynamic from `user.tenantName || 'K.T.R.A العالمية' + [السنة المالية {YEAR}]` + active-view chip + GlobalSearch + DensitySwitch + ThemeToggle). Aseel `.aseel-toolbar` with Breadcrumb. Bottom `.aseel-statusbar` (user/role/date/connection). Removed broken `BreadcrumbItem` import (the type was never exported).
  - **M5-T2 (`Sidebar.tsx`):** `data-skin="aseel"` on the panel; denser paddings (`h-12`/`p-1`/`p-2`); CSS tokens (`var(--color-*)`) instead of raw Tailwind; smaller icons; preserved all M0-M4 menu items (sales-quotations, credit-debit-notes, aseel-kit).
  - **M5-T3 (global skin + types):** Exported `VIEW_LABELS` from `Breadcrumb.tsx`. Added missing `AppView` entries: `sql-clearances`, `sql-purchase-invoices`, `shipments`, `shipment-management`, `clearance`. Corresponding labels in `VIEW_LABELS`.
  - **M5-T4 (`components/ui/EmptyState.tsx`):** New file with three components — `EmptyState` (Aseel-skin, default Arabic title/description), `Spinner` (sm/md/lg + label), `ErrorState` (with `onRetry` button). Exposed via `AseelStates` namespace in `components/ui/index.tsx` to coexist with legacy D1-03 `EmptyState`/`Spinner` without conflicts. New screens use `import { AseelStates } from '@/components/ui'` → `<AseelStates.EmptyState />`.
- **Verified:** `manage.py check` 0 issues · `tsc --noEmit` total **76 ≤ 78** (improvement; pre-existing `BreadcrumbItem` error fixed by M5-T1) · `vite build` 13.28s clean · DOM check on `/aseel-sales` confirmed `.aseel-titlebar`, `.aseel-statusbar`, `.aseel-doc` all present.
- **Honest scope note (M5-T3):** Did NOT perform the full DataGrid hex-removal/tokenization sweep — that's a cleanup pass touching many files. Recommended after M6 backend stabilization. The skin attribute is propagated globally; hex usage in legacy components doesn't break Aseel rendering, just less polished where they appear.
- M6 pending owner approval.

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

## [TASK5 N0 — DONE & VERIFIED 2026-05-21]

### Backend
- **N0-T1** `tenants/models.py`: New `TenantSettings` model (one-to-one with Tenant). Fields: company_name_primary/sub, address, po_box, phone, fax, email, licensed_dealer_no, income_tax_file_no, default_vat_rate, default_source_discount_rate, currency FK, fiscal_period_label/start/end, default_freight_credit_account FK, mixture_auto_fill_enabled, barcode_action. Migration `tenants/0003_n0_tenant_settings_and_books.py`.
- **N0-T2** `tenants/models.py`: New `TenantBook` model. PK composite (tenant, document_type, book_number). 15 document types. Fields: name, last_used_number, is_active. Same migration.
- **N0-T3** `accounting/services.py`: New `next_document_number(tenant_id, document_type, book_number=0)` — canonical helper with `select_for_update`. Existing `next_invoice_number()` and `next_credit_debit_note_number()` refactored to thin wrappers.

### Frontend Primitives
- **N0-T6** `useAseelKeymap.ts`: Extended with Ctrl+Home/End/PageUp/PageDown/Ins/Del keys.
- **N0-T7** `useAseelIndexKeymap.ts`: New hook for list pages (F2=drillToLedger, F3=drillToStock, F4=showNotes, F5=sortBy, F6=search, Enter=openRecord, Ctrl+nav).
- **N0-T8** `useAseelFieldShortcuts.ts`: New hook for field-level shortcuts (date +/-, remaining-amount Space, voucher-link *, account-number */-, item-number +).
- **N0-T9** `AseelStatusBarItem.tsx`: New primitive for status bar items (label, value, icon).
- **N1-T1** `AseelFormSection.tsx`: New primitive — subsection box with border, title, 2/3/4 col grid.
- **N1-T2** `AseelDenseTable.tsx`: New primitive — list page table replacing DataGrid (columns, rows, sortable, selectable, pagination, footer).
- **N1-T3** `AseelReportTable.tsx`: New primitive — report table with filterBar, numeric columns, totals footer, CSV export.

### Frontend Pages
- **N0-T4** `GroupConstantsPage.tsx`: New page — 4 tabs (بيانات عامة, أرقام الدفاتر, حسابات افتراضية, ضرائب). Uses AseelDocumentShell + AseelFormSection + AseelGrid.
- **N0-T5** `AppLayout.tsx` + `App.tsx`: F11 global keymap → opens GroupConstantsPage as modal portal. `onOpenGroupConstants` prop added to AppLayout.
- **N0-T10** `aseel/index.ts`: Barrel updated with all new exports. `AseelKitStory.tsx`: Added live demos of AseelFormSection, AseelDenseTable, AseelReportTable, AseelStatusBarItem.

### Types
- `types/common.ts`: Added `"group-constants"` to AppView union.
- `components/layout/Breadcrumb.tsx`: Added `'group-constants': 'ثوابت المجموعة'` to VIEW_LABELS.

**Verified:** Migration created · Barrel exports all new primitives · AseelKitStory shows demos · F11 modal portal wired.

### N0-T11 — F-key fixes applied to M1-M5 forms
- **SalesInvoiceEditor.tsx (M1):** Added Ctrl+Home/End/PageUp/PageDown/Ins handlers using `nav.first/last/prev/next/goNew`.
- **DealForm.tsx (M3):** Added Ctrl+nav handlers.
- **ShipmentForm.tsx (M3):** Added Ctrl+nav handlers.
- **CustomsClearanceManagement.tsx (M3):** Added Ctrl+nav handlers + CtrlIns opens new clearance form.
- **InvoiceForm.tsx (M4):** Added Ctrl+nav handlers + CtrlIns calls `nav.goNew()`.
- **AccountingJournalEntryPage.tsx (M4):** Added Ctrl+nav handlers + CtrlIns calls `nav.goNew()`.
- **SalesCustomerPaymentsPage.tsx (M4):** Added Ctrl+nav handlers + CtrlIns opens new payment form.
- **CreditDebitNotesPage.tsx (M4):** Added Ctrl+nav handlers + CtrlIns opens new note form.
- **SalesQuotationsPage.tsx (M4):** Added Ctrl+nav handlers + CtrlIns opens new quotation form.

**Final verification:** `tsc --noEmit` = **78 ≤ 78** · `vite build` = 0 errors · `manage.py check` = 0 issues.

## [TASK5 N1 — DONE & VERIFIED 2026-05-21]

### Frontend Primitives
- **N1-T1** `AseelFormSection.tsx`: Subsection box with `var(--aseel-border-soft)`, title, 2/3/4 col auto-fit grid. Supports nesting. CSS in `styles/index.css:745-777`.
- **N1-T2** `AseelDenseTable.tsx`: List page table replacing DataGrid. Props: columns/rows/getRowKey, onRowClick/DoubleClick, selectable, sortable, pagination, footer. CSS in `styles/index.css:783-792`.
- **N1-T3** `AseelReportTable.tsx`: Report table with filterBar, numeric columns (tabular-nums), totals footer, CSV export (UTF-8 BOM). CSS in `styles/index.css:820+`.
- **N1-T4** `AseelStatusBarItem.tsx`: Type-safe status bar item (label, value, icon). CSS already exists at `styles/index.css:577-578`.
- **N1-T5** `AseelDateInput.tsx`: Date input wrapper with `useAseelFieldShortcuts` (* = +1 day, - = -1 day) + double-click year picker modal (20-year range).
- **N1-T6** `aseel/index.ts`: Barrel exports all 6 primitives. `AseelKitStory.tsx`: Live demos for all primitives with Arabic labels.

**Verified:** `tsc --noEmit` = **78 ≤ 78** · `manage.py check` = 0 issues · All primitives exported + demoed on `/aseel-kit`.

## [TASK5 N2 — DONE & VERIFIED 2026-05-22]

Procurement forms inside-out conversion (4 forms; "shell-only" → full Aseel inside-out per M1 golden template).

- **N2-T1** `procurement/deals/DealForm.tsx`: inside-out rebuild. Aseel header band (16+ fields: رقم/تاريخ/الساعة/تاريخ ثاني/المورد + فهرس/الاسم/العنوان/مشتغل مرخص/طريقة شحن/الحالة/...). `AseelGrid` items variant. Tabs: ملاحظات / الحسابات (journal preview) / أقساط (InstallmentManager wrapped) / الشحنة / بيانات أخرى. Totals dock: مجموع/خصم/قبل الضريبة/الضريبة/المبلغ الإجمالي/المدفوع/المتبقي. Status bar: المستخدم/رقم القيد/المرحلة/السجل n/N/آخر مفتاح. Toolbar: إضافة (Ctrl+Ins) · تخزين (F12) · حذف (Ctrl+Del) · إلغاء · طباعة (F2) · مراجعة الإرسالية (F4) · ترتيب (F5) · بحث (F6). API `dealsService.*` unchanged.
- **N2-T2** `procurement/shipments/ShipmentForm.tsx`: inside-out rebuild. Aseel header band (18+ fields incl. نوع الإرسالية فاتورة/نقل + رقم البوليصة/الحاوية + المغادرة/الوصول). When `shipment_type='transport'`, shows AseelFormSection "بيانات النقل المحلي" (السائق + فهرس / رقم السيارة / أجرة نقل الوحدة/الكمية / حساب أجرة النقل + فهرس / رقم القيد). Tabs: الصفقات المرفقة (`ShipmentDealsTable` wrapped) / تفاصيل الشحن / النقل المحلي (AseelDenseTable) / الدفعات / الحسابات. Totals dock: تكلفة الشحن/الحجم/الوزن/أجرة النقل/المدفوع/المتبقي. زر «تكوين فاتورة» مقيَّد بـ`shipment_type !== 'transport'`.
- **N2-T3** `procurement/clearance/CustomsClearanceManagement.tsx`: inside-out rebuild. Aseel header band (12+ fields: رقم البيان/تاريخ/الساعة/تاريخ ثاني/رقم القيد/كشف الضريبة/المخلِّص + فهرس/...). `AseelGrid` variant=`journal` columns (seq/account_no/account_name/desc/debit/credit/vat_percent/cost_center). Tabs: الإرساليات المرافقة (AseelDenseTable select-mode) / الحسابات / بيانات أخرى. Totals: المجموع بدون ضريبة / مجموع الضريبة / مبلغ البيان الإجمالي. زر ترحيل مسار landed-cost موجود بلا تغيير.
- **N2-T4** `procurement/invoices/InvoiceForm.tsx` (purchase): inside-out rebuild. Aseel header band (15+ fields: رقم الفاتورة (manual)/دفتر/تاريخ/الساعة/تاريخ ثاني/تاريخ الاستحقاق/المورد + فهرس/اسم/عنوان/مشتغل مرخص/رقم المستند/عملة/سعر العملة/يشمل ض.ق.م/المخزن). `AseelGrid` items: مسلسل/رقم الصنف + فهرس/كتلوج/اسم/بيان/الوحدة/المخزن/الكمية/إضافي/سعر الوحدة/خصم سطر/الضريبة/السعر الإجمالي. Tabs: الملاحظات / الحسابات / بيانات أخرى / المرفقات. Totals: مجموع البنود/خصم/قبل الضريبة/الضريبة/مدفوع نقدا/مدفوع شيكات/مبلغ الفاتورة/متبقي. F3 = سند الصرف المرفق (placeholder until N8-T12).
- **N2 review** `e04e2ab`: restored legacy inputs lost in inside-out rebuild (4 forms).

**Verified:** all 4 forms DOM-match Aseel original; no API change in `services/*Api.ts`. `manage.py check` clean.

## [TASK5 N3 — DONE & VERIFIED 2026-05-22]

Accounting suite — 13 tasks: 1 form inside-out · 6 list pages (DenseTable) · 4 reports (ReportTable) · 3 new pages.

### Forms & Lists
- **N3-T1** `accounting/AccountingJournalEntryPage.tsx` (F7): inside-out form. Aseel header (رقم القيد/تاريخ/الساعة/تاريخ ثاني/البيان الإجمالي/المرجع/العملة/السعر). `AseelGrid` variant=`journal`. Field shortcuts: Space on debit/credit → auto-balance; `*` on account number → balance tooltip; `+` → AseelIndexPicker. Footer: مدين/دائن/فرق. F12 = ترحيل عبر `post_journal()`. Fixed in `df66a15`: actual render of AseelGrid + AseelIndexPicker (was dead-code).
- **N3-T2** `AccountingJournalListPage.tsx` (L15): AseelDenseTable. Columns per spec: رقم القيد/تاريخ/الساعة/مبلغ/عملة/بيان إجمالي/المستخدم. Filter bar: من-إلى تاريخ/دفتر/حساب/مستخدم. `useAseelIndexKeymap`: F2=drillToLedger, F6=search, Ctrl+Ins=new.
- **N3-T3** `AccountingCoaPage.tsx` (L16): tree-style table. Columns: كود/الاسم/النوع/الطبيعة (N8-T6)/مدين/دائن/الصافي. Foldable to 3 levels by default. `useAseelIndexKeymap`: F2=drillToLedger, F4=showNotes.
- **N3-T4** `AccountingChequesPage.tsx` (L14): AseelDenseTable per L14 spec. Columns: رقم الشيك/البنك/الفرع/المبلغ/استحقاق/إصدار/الشريك/الحساب/الحالة/الاتجاه. Filter bar: حالة/استحقاق من-إلى/شريك/اتجاه. Cheque transfer dialog (`N-F9` ChequeTransferDialog) — modal for transferring cheque status; logs `ChequeMovement` (pending N8-T14).
- **N3-T5** `accounting/FiscalPeriodsPage.tsx` (L17): AseelDenseTable + إقفال/إعادة فتح toolbar.
- **N3-T6** `accounting/ExchangeRatesPage.tsx` (L18): AseelDenseTable + currency filter.

### Reports (AseelReportTable)
- **N3-T7** `AccountingGeneralLedgerPage.tsx` (R1): filterBar (account/from-to date/book/currency). Columns: التاريخ/رقم القيد/البيان/المدين/الدائن/الرصيد التراكمي/رقم القيد المرجعي. Footer: مدين/دائن/الرصيد النهائي. Export CSV.
- **N3-T8** `AccountingTrialBalancePage.tsx` (R2): filterBar (date/branch). Columns: كود/اسم/النوع/مدين/دائن. Footer validates مدين = دائن.
- **N3-T9** `AccountingVatReportPage.tsx` (R3): 2-section (ضريبة مخرجات / ضريبة مدخلات / الصافي). Filter: period.
- **N3-T10** `AccountingLandedCostPage.tsx` (R4): per item allocation share of shipping/clearance. Filters: shipment/deal/period.

### New Pages
- **N3-T11** `BalanceSheetPage.tsx` (R5، N-F6): الميزانية العمومية + accompanying statements (مدينون، دائنون، تشغيل، متاجرة، أرباح/خسائر، إيرادات/مصروفات). Filters: as-of date + currency + branch.
- **N3-T12** `IncomeStatementPage.tsx` (R6، N-F7): كشف الإيرادات والمصروفات (periodic).
- **N3-T13** `VatStatementsPage.tsx` (N-F5): periodic VAT statements list + creation form. DenseTable for past statements; new statement aggregates invoices in period with `vat_statement IS NULL`.

### Wiring
- `App.tsx` + sidebar updated with routes for 3 new pages. `AppView` types extended.

**Verified:** `manage.py check` = 0 issues · `tsc --noEmit` within budget · all pages DOM-match Aseel spec. 6 audit fixes applied (`d6c5739`).

## [TASK5 N4 — DONE & VERIFIED 2026-05-22]

Sales sub-pages — 9 tasks: 3 lists · 3 form inside-out · 3 new documents.

### Lists & Forms (existing)
- **N4-T1** `sales/SalesInvoicesPage.tsx` (L7): AseelDocumentShell + AseelDenseTable per spec. Columns: رقم/تاريخ/العميل/النوع/الحالة/الإجمالي/المدفوع/المتبقي/الكشف/إجراءات. Ctrl+Ins opens SalesInvoiceEditor. F2=drill, F6=focus search.
- **N4-T2** `sales/SalesCustomersPage.tsx` (L8): AseelDenseTable + Partner N8-T8 fields (default_cost_center, end_of_dealing_date, assigned_price_tier).
- **N4-T3** `sales/SalesSettingsPage.tsx` (L9): AseelDocumentShell wrap + pointer to GroupConstantsPage for moved fields.
- **N4-T4** `sales/SalesCustomerPaymentsPage.tsx` (F9): financial fields + cheque AseelGrid + tabs. Aseel header (دفتر/رقم السند/التاريخ/الساعة/تاريخ ثاني/العملة/السعر/العميل + فهرس/الصندوق + فهرس). Source discount in voucher itself. AseelGrid for cheques with full columns. Tabs: ملاحظات / الحسابات / بيانات أخرى. زر «اقتراح FIFO» + زر «تعبئة شيكات متشابهة متكرّرة».
- **N4-T5** `sales/CreditDebitNotesPage.tsx` (F10): tax fields + رقم فاتورة المقاصة + tabs. Aseel header (دفتر/رقم الإشعار/التاريخ/الساعة/تاريخ ثاني/رقم القيد/كشف الضريبة/الحساب + فهرس/رقم فاتورة المقاصة/حساب الإشعار + فهرس/عملة/السعر/النوع مدين/دائن). VAT calc fields. Tabs: ملاحظات / الحسابات.
- **N4-T6** `sales/SalesQuotationsPage.tsx` (F11): additional fields per spec (فعال حتى تاريخ + فعال checkbox + per-line تاريخ ثاني). Toolbar: «تحويل لفاتورة» (uses `convertQuotationToInvoice`).

### New Documents
- **N4-T7** `sales/SalesReturnEditor.tsx` (N-F2، جديد): «مرجع البيع» — full document, same structure as SalesInvoiceEditor with `invoice_kind='sale_return'` + `original_invoice` FK. Post reverses original (Dr Sales Return Revenue / Cr AR). Depends on N8-T11 backend.
- **N4-T8** `sales/PurchaseReturnEditor.tsx` (N-F3، جديد): «مرجع الشراء» — same pattern for Purchase. Depends on N8-T11.
- **N4-T9** `sales/SupplierPaymentsPage.tsx` (N-F4، جديد): «سند صرف» — mirrors CustomerPayment for suppliers. Depends on N8-T12.

### Wiring
- `App.tsx` + sidebar links + routes for 3 new pages. `AppView` types extended.

**Verified:** all 9 sales pages DOM-match Aseel; zero API change.

## [TASK5 N5 — DONE & VERIFIED 2026-05-23]

Inventory + Items + Suppliers + Price Offers — 8 tasks.

- **N5-T1** `inventory/StockLevelsPage.tsx` (L11): AseelDenseTable + status/category filters + total inventory value footer. Fix `bfb3b14`: footer span (HTML invalid) + فلتر فئة + فوق الحد الأقصى.
- **N5-T2** `inventory/StockMovementsPage.tsx` (L12): AseelDenseTable + filters + modal لإضافة حركة.
- **N5-T3** `items/ItemsManagement.tsx` (L4): SQL products + AseelDenseTable + CRUD helpers.
- **N5-T4** `items/ItemFormAseel.tsx` (F6): Aseel-style 6-page form per المخازن.txt:11-25 — بيانات عامة / الأرصدة والحركات / أسعار البيع والشراء (5+5 tiers) / بيانات المتاجرة (account overrides) / بيانات أخرى / معادلات التصنيع. Fix `d75acc2`: pending-N8 banners + payload cleanup for supported fields only.
- **N5-T5** `suppliers/SupplierManagement.tsx` (L5): accountingApi partners + AseelDenseTable + **deleted L6 duplicate** `components/SupplierManagement.tsx` (354 lines removed).
- **N5-T6** `procurement/PriceOfferManagement.tsx` (L3): AseelDenseTable + فلاتر الحالة. Fix `6ee2d0b`: ربط priceOffersService الصحيح + createdAt.
- **N5-T7** `procurement/price-offers/PriceOfferForm.tsx` (F5): AseelDocumentShell + 4 offer types + AseelGrid items. Fix `78f1253`: حقول LineItem الصحيحة + حفظ offerType/validUntil/currency.
- **N5-T8** `inventory/InventoryValuationPage.tsx` (N-F8، جديد): قيمة البضاعة بطرق متعدّدة (FIFO/LIFO/avg-purchase/avg-sale/selected-price). Filters: warehouse/branch/as-of date. Fix `1fb513b`: تَفعيل asOfDate + computeUnitPrice حقيقي + bonus من الحركات.

**Verified:** all 8 inventory/items/suppliers pages on AseelDenseTable. L6 duplicate removed. `services/inventoryApi.ts` extended with helpers. `types/offer.ts` enriched.

## [TASK5 N6 — DONE & VERIFIED 2026-05-23]

Procurement managements — 3 list pages on AseelDenseTable.

- **N6-T1** `procurement/DealManagement.tsx` (L1): AseelDenseTable. Columns: رقم الصفقة (mono) / المورد / الوصف / الحالة (ملوَّنة بـSTATUS_COLORS aseel tokens) / المبلغ / المتبقي (warn/ok by sign) / التاريخ / إجراءات (طباعة/تعديل/حذف). Search includes suppliers lookup. Filter: الحالة (14 status options). Footer: إجمالي + متبقي مجاميع للصفوف المفلترة. Stats band: الإجمالي/نشطة/مكتمل/القيمة. Print overlay via `DealPrintView` preserved. DealForm integration preserved. **− 592 lines, + 273 lines**.
- **N6-T2** `procurement/shipments/ShipmentManagement.tsx` (L2): AseelDenseTable. Columns: رقم الشحنة (🚢/✈ + mono + صفقات count) / وكيل الشحن / النوع / الحالة (ملوَّنة) / المغادرة / الوصول / التكلفة / إجراءات (عرض/تعديل/حذف). Dual filters: نوع الشحن (بحري/جوي/كل) + الحالة. Stats band: الإجمالي/في الشحن/تم التسليم/إجمالي التكلفة. ShipmentDetailView modal preserved.
- **N6-T3** `logistics/LocalShippingPage.tsx` (L10): AseelDenseTable. Columns: رقم الشحنة / التاريخ / الناقل (+driver/vehicle) / التخليص / المسار من←إلى / المبلغ (with currency) / الحالة (ملوَّنة) / الترحيل (مرحَّلة/فاتورة) / إجراءات (تعديل/ترحيل/استيراد/إلغاء ترحيل/حذف بحسب الحالة). Filter: الحالة. Stats band per status. **Drawers internal preserved** (`LocalShipmentFormDrawer` + `ImportToInvoiceDrawer`) — كل منطق الـAPI بلا تغيير (يَبقى المصدر المستقل T1-01).

**Verified:** `tsc --noEmit` = **39 errors** (↓ من 67 قبل N5) · `manage.py check` = 0 issues · 0 new migrations (frontend-only) · 3 management pages now Aseel-native.

## [TASK5 N7 — DONE & VERIFIED 2026-05-23]

HR / Admin / Dashboard / SQL — 9 tasks.

### Dashboard & HR
- **N7-T1** `components/Dashboard.tsx` (H1): KPI Aseel-style summary blocks — status cards with `var(--aseel-*)` tokens replacing raw Tailwind colors.
- **N7-T2** `hr/TaskManagement.tsx` (H2): AseelDenseTable + فلاتر الحالة/الموظف/الأولوية.
- **N7-T3** `hr/AttendanceManagement.tsx` (H3): AseelDenseTable + فلاتر الحضور/الغياب.
- **N7-T4** `hr/EmployeePointsManagement.tsx` (H4): AseelDenseTable + daily points grid.
- **N7-T5** `hr/PointsHistoryPage.tsx` (H5): AseelDenseTable + KPI chips for points summary.
- **N7-T6** `components/ResultsPage.tsx` (H8): AseelDenseTable + price slider + sort by similarity/price.

### Admin & SQL
- **N7-T7** `components/SettingsPage.tsx`: Aseel form sections with `aseel-input` tokens.
- **N7-T8** `sql/Sql*Page.tsx` (4 pages — SqlDealsPage, SqlShipmentsPage, SqlClearancesPage, SqlPurchaseInvoicesPage): AseelDenseTable replacing card-style lists.
- **N7-T9** `realestate/PropertyRentalPage.tsx`: Aseel layout + AseelDenseTable for units/contracts/readings.

**Verified:** `tsc --noEmit` = 39 errors (all pre-existing) · `manage.py check` = 0 issues · all 9 pages on Aseel primitives.

## [TASK5 N8 — DONE & VERIFIED 2026-05-23]

Backend hardening — 11 model/service tasks + audit consistency.

### Account & Cost Center
- **N8-T5** `logistics/models.py` + `accounting/models.py`: `book_number` added to `LogisticsDeal` and `LogisticsClearance`. `next_document_number()` helpers extended to resolve deal/clearance numbering.
- **N8-T6** `accounting/models.py`: `Account.nature` field (debit/credit/both). `accounting/services.py`: `post_journal()` validates that debit lines hit debit-nature accounts and credit lines hit credit-nature accounts (both-nature allows either).
- **N8-T7** `accounting/models.py`: `Account.default_cost_center` FK + `Account.notes` TextField. Migration `accounting/0018_account_nature_costcenter_notes.py`.

### Partner Enrichment
- **N8-T8** `partners/models.py`: 4 new fields — `default_cost_center` FK, `end_of_dealing_date`, `assigned_price_tier` FK (to `ProductPriceTier`), `password_for_invoices`. Migration `partners/0005_partner_enrichment.py`.

### Product Extensions
- **N8-T9** `inventory/models.py`: New `ProductPriceTier` model — 5 sale price fields (`sale_price_1..5`) + 5 purchase price fields (`purchase_price_1..5`). Migration `inventory/0005_productpricetier.py`.
- **N8-T10** `inventory/models.py`: `Product` gains 6 account-override FKs — `account_sales`, `account_purchases`, `account_sales_return`, `account_purchases_return`, `account_discount_earned`, `account_discount_granted`. Migration `inventory/0006_product_account_overrides.py`.

### Sales Extensions
- **N8-T11** `sales/models.py`: `SalesInvoice.invoice_kind` (sale/sale_return/purchase_return, default='sale') + `original_invoice` FK (self-referencing, for returns). `sales/services.py`: `post_sales_invoice` sign logic — sale_return and purchase_return reverse debit/credit lines. Migration `sales/0012_invoice_kind_original.py`.
- **N8-T12** `sales/models.py`: New `SupplierPayment` model (Dr AP / Cr Cash). `sales/services.py`: `post_supplier_payment()` creates journal via `post_journal()`. Migration `sales/0013_supplierpayment.py`.
- **N8-T13** `sales/models.py`: New `VatStatement` model (period + linked invoices + totals). `sales/services.py`: `build_vat_statement(tenant_id, from_date, to_date)` aggregates unlinked invoices. Migration `sales/0014_vatstatement.py`.

### Cheques & Audit
- **N8-T14** `accounting/models.py`: New `ChequeMovement` model (cheque FK + from_status + to_status + date + notes + user). `accounting/services.py`: `transfer_cheque(cheque, new_status, user)` with `VALID_TRANSITIONS` state machine — validates transition, creates movement log, updates cheque status atomically.
- **N8-T15** Audit log consistency: added missing `CreditDebitNote` audit log on post, unified pattern across all posting services.

**Verified:** `manage.py check` = 0 issues · `makemigrations --check` = no drift · 11 migrations applied · all services use `post_journal()` correctly.

## [TASK5 N9 — DONE & VERIFIED 2026-05-23]

System-wide cleanup — 8 tasks.

### Color & States
- **N9-T1** Tailwind color purge: all named Tailwind color classes (`text-blue-*`, `bg-green-*`, `border-gray-*`, etc.) replaced with Aseel utility classes (`aseel-text-ink`, `aseel-text-soft`, `aseel-bg-panel`, `aseel-border-soft`, `aseel-bg-accent-bg`, `aseel-text-accent`, `aseel-text-state`, `aseel-bg-field`, `aseel-bg-grid-head`, `aseel-btn-primary`). 104 files touched. Classes scoped under `[data-skin="aseel"]` in `styles/index.css:988-1006`.
- **N9-T2** `AseelStates` (`AseelSpinner`, `AseelEmptyState`, `AseelErrorState`): integrated into all AseelDenseTable/AseelReportTable loading/empty/error states.

### Responsive & Print
- **N9-T3** Dark mode: `@media (prefers-color-scheme: dark)` overrides for `[data-skin="aseel"]` tokens (ink, bg, border, accent colors invert). `styles/index.css`.
- **N9-T4** Mobile RTL: `@media (max-width: 640px)` responsive adjustments for `[data-skin="aseel"]` — stacked header bands, full-width inputs, smaller font sizes, touch-friendly padding.
- **N9-T5** Print CSS: `@media print` — hides toolbar/sidebar/status bar, full-width content, `break-inside: avoid` on table rows, forced light colors.

### Features
- **N9-T6** CSV export: `AseelDenseTable` gains `exportable` + `exportFilename` props → UTF-8 BOM CSV download via Blob. `AseelReportTable` already had export.
- **N9-T7** Context menu: right-click on `AseelDenseTable` rows shows context actions (view/edit/delete/export row). Scoped CSS.
- **N9-T8** `Partner.row_color`: new `row_color` field on Partner model (hex color string). `AseelDenseTable` gains `rowColorKey` prop — applies inline `color` override per row when the key resolves to a hex string. Migration `partners/0006_partner_row_color.py`.

### Review Fixes (N7-N9 review pass)
- Fixed 141 broken CSS class name suffixes across 41 files (e.g. `aseel-text-soft0` → `aseel-text-soft`).
- Added missing `AseelSpinner` imports in 3 sales pages (CreditDebitNotesPage, SalesCustomerPaymentsPage, SalesQuotationsPage).
- Fixed `ResultsPage` getRowKey signature mismatch (2 args → 1 arg matching `AseelDenseTable` type).
- Merged broken duplicate lucide-react import block in SalesQuotationsPage.
- Committed 63 files of uncommitted N9-T1 color purge work left unstaged by external model.

**Verified:** `tsc --noEmit` = 39 errors (all pre-existing) · `manage.py check` = 0 · `makemigrations --check` = no drift · Tailwind violations = 0 · `vite build` = success.

### Updated [ORPHANS & PENDING] post-N9
- **N0..N9 complete:** Foundation (N0), primitives (N1), procurement forms inside-out (N2, 4 forms), accounting suite (N3, 13 tasks), sales suite (N4, 9 + 3 new), inventory/items/suppliers (N5, 8 + 1 new), procurement managements (N6, 3 lists), HR/Admin/Dashboard/SQL (N7, 9 tasks), backend hardening (N8, 11 models/services), system cleanup (N9, 8 tasks) = **68 frontend + 11 backend tasks delivered**.
- **DataGrid → AseelDenseTable migration progress:** L1-L5/L7-L8/L10-L12/L14-L15/L17-L18 + H1-H5/H8 + SQL×4 done (22/22 + HR/SQL). L13 (realestate, out of scope) + L16 (CoA tree, done via N3-T3) = **complete**.
- **Pending:** P-C through P-K (task6 data normalization, multi-tenancy hardening, UI density redesign).
- **Git hygiene (improved):** `sales/` app now fully tracked. All N8 migrations applied. No schema drift.
- **Disjoint payment models:** still unresolved (deal-level Firestore vs SQL CustomerPayment). `core/payments.py` foundation layer (I4-09) available but not wired.
- **`frontend/` Next.js app:** still unrelated to ERP; keep separate or move out of repo.

## [TASK6 — P-A + P-B DONE 2026-05-24]

> **Status:** P-A + P-B completed on branch `claude/task6`. Commit `04b0696`.

### P-A — Foundation: Baseline + Safety Net
- **P-A-1:** Baseline metrics recorded in `task6_baseline.md` (tsc=41, vite=success, manage.py check=0, 16 `:any`, console.log=0)
- **P-A-2:** Branch `claude/task6` created
- **P-A-3:** `eslint-plugin-react-hooks` installed as devDependency, `eslint.config.js` created with react-hooks recommended rules
- **P-A-4:** PDF error scenarios documented in baseline

### P-B — Critical Runtime Hotfixes
- **P-B-1 (VII-1):** Moved `showAccountBalance` useCallback from after early return (line 444) to before loading guard in `AccountingJournalEntryPage.tsx:327`
- **P-B-2 (VII-4):** Created `core/exception_handler.py` — converts `Django ValidationError` to `DRF ValidationError` (400 instead of 500), logs unhandled exceptions. Registered in `REST_FRAMEWORK.EXCEPTION_HANDLER`
- **P-B-3 (VII-2):** `autoDisableScheduler.ts` replaced with no-op (start/stop do nothing, public API preserved)
- **P-B-4 (VII-3):** Removed missing 192x192 icon reference from `site.webmanifest`
- **P-B-5 (VII-6):** Created `seed_minimum_tenant.py` management command — creates Tenant + ILS/USD currencies + basic account tree (1000-5000) + current FiscalPeriod. Idempotent.
- **P-B-6 (VII-5):** Replaced `console.error` + `alert` with `setWorkflowError` state + red error banner in `DealForm.tsx`

### Verified
- `manage.py check` = 0 issues
- `makemigrations --check` = no drift
- `vite build` = success (3395 modules)
- No new migrations required

## [TASK6 — P-C DONE 2026-05-24]

> **Status:** P-C completed on branch `claude/task6`. Commit `cc267d4`.

### P-C — Multi-Tenancy Hardening
- **P-C-1:** `default=1` removed from `tenant` FK on 8 logistics models (LogisticsDeal, LogisticsShipment, LogisticsClearance, LogisticsClearancePayment, LogisticsExpense, LocalShipment, PurchaseInvoice, PurchaseInvoiceFee). Help text added: "tenant مطلوب — لا fallback"
- **P-C-2:** `default=1` removed from `currency` FK on 3 logistics models (LogisticsExpense, LocalShipment, PurchaseInvoice)
- **P-C-3:** Audited logistics/views.py — all 8 ViewSets extend `BaseTenantViewSet` from core/mixins. No `tenant_id=1` fallback found. All `serializer.save(tenant=...)` use resolved tenant from `self._get_tenant()`
- **P-C-4:** Created `logistics/tests/test_tenant_isolation.py` with 3 tests:
  1. `test_list_returns_only_own_tenant_deals` — Tenant A's list only shows A's deals
  2. `test_create_without_tenant_header_returns_400` — missing header → 400
  3. `test_cannot_access_other_tenant_deal` — Tenant A gets 404 on Tenant B's deal
  - Note: pre-existing test infra issue (accounting migration 0003 fails on SQLite test DB) prevents running TestCase-requiring tests. Verified via `manage.py check` and `makemigrations --check` = no drift.

### Migration
- `logistics/migrations/0027_alter_localshipment_currency_and_more.py` — auto-generated, covers all 11 AlterField operations (8 tenant + 3 currency)
- No schema change (Python-level defaults only)

### Orphans Update
- Logistics `default=1` on tenant/currency: **eliminated**

## [TASK6 — P-D + P-E + P-F-1..F-3 DONE 2026-05-24]

> **Status:** Data normalization waves 1+2 + clearance/shipment/deal header enrichment completed on `claude/task6`. External-model commit reviewed and corrected for ORM-breaking issues.

### P-D — Data normalization wave 1 (clearance + PI payments)
- **P-D-1:** `LogisticsClearanceLine` model (clearance/seq/line_type/account FK/description/debit/credit/vat_percent/cost_center FK). Migration `0028_clearance_line_model`.
- **P-D-2:** Migration `0029_backfill_clearance_lines` — JSON `cost_lines` → rows. Idempotent (skips clearances that already have lines). Maps Arabic label → `line_type` via lookup table.
- **P-D-3:** `LogisticsClearanceSerializer` now exposes `lines` (NestedSerializer) + `cost_lines` (JSONField — backwards-compat read+write, syncs via `_sync_lines_from_cost_lines`). Frontend `CustomsClearanceManagement.tsx` switched payment-classification from `notesMeanShippingPayment` regex to `payment_purpose === 'shipping'`.
- **P-D-4:** Migration `0030_drop_cost_lines_json` drops the legacy JSONField. **`LogisticsClearance.cost_lines` kept as backwards-compat `@property`** returning `[{label, amount}]` from `lines` rows — required because `logistics/views.py` and `logistics/landed_cost.py` still read it as a list (would have crashed otherwise).
- **P-D-5:** `LogisticsClearancePayment.payment_purpose` choice (`clearance_fee/shipping/broker_fee/customs/vat/other`). Migration `0031_add_payment_purpose` + `0032_backfill_payment_purpose` (parses `[شحن]`/`[تخليص]`/`عمولة` prefixes from `notes`). `LogisticsClearanceViewSet.pay_from_cashbox` writes `payment_purpose` instead of `[شحن]` prefix.
- **P-D-6:** `PurchaseInvoicePayment` model (mirror of `CustomerPayment`). Migration `0033_pi_payment_model`.
- **P-D-7:** Migration `0034_backfill_pi_payments` — `local_payments_json` → rows. Defaults currency to ILS when missing; idempotent on `pi.payments.exists()`.
- **P-D-8:** Migration `0035_drop_pi_json_fields` drops `local_payments_json` + `conversion_metadata_json`; adds `converted_from_shipment` FK + `converted_at` + `converted_by` FK (User).

### P-E — Data normalization wave 2 (line-level fields)
- **P-E-1:** `LogisticsDealItem` enrichment — 18 fields (seq/catalog_number/name_snapshot/description_line/unit/warehouse/extra_qty/batch_number/serial_number/manufacture_number/expiry_date/line_currency FK/line_exchange_rate/second_date/is_taxable/vat_percent/discount_percent/discount_amount). Migration `0036_deal_item_enrichment`. All nullable.
- **P-E-2:** `PurchaseInvoiceItem` mirror enrichment (same 18 fields). Migration `0037_pi_item_enrichment`.
- **P-E-3:** Migration `0038_backfill_line_fields` extracts `batch:`/`expiry:`/`lot:` patterns from `notes` regex → respective columns.
- **P-E-4/5:** Serializers `LogisticsDealItemSerializer` + `PurchaseInvoiceItemSerializer` expose the new fields. UI advanced-toggle deferred to P-G.
- **P-E-6:** `accounting/views.py:PurchaseReceiptViewSet` — if PI items carry `vat_percent`, compute per-line VAT and emit separate VAT lines in the journal; else fall back to header-level VAT.

### P-F (partial: header enrichment for Clearance + Shipment + Deal)
- **P-F-1:** `LogisticsClearance` header enrichment — 11 new fields (transaction_time/second_date/licensed_dealer_no/settlement_invoice_number/currency FK/exchange_rate/vat_statement FK/subtotal_no_vat/vat_total/grand_total/journal FK/editable). Migration `0039_clearance_header_enrichment`.
- **P-F-2:** `LogisticsShipment` header enrichment — 7 new fields (transaction_time/transit_journal FK/editable/vat_statement FK/journal_no_display/subtotal/vat_total/grand_total).
- **P-F-3:** `LogisticsDeal` header enrichment — 4 new fields (transaction_time/second_date/licensed_dealer_no/editable).
- **P-F-4:** **Implemented as save-time auto-sync, not @property** (the pure-@property reading from task6.md is unsafe here — see fix #1 below). The legacy `status`/`order_status`/`payment_status` columns are kept as a denormalized cache, but `LogisticsDeal.save()` now calls `_sync_legacy_status_fields()` to force them to mirror `shipping_workflow_status` (lifecycle) + `remaining_amount`/posted-payments (settlement). `recalculate_deal_payment_status` in `signals.py` was extended to recompute all three fields atomically. Data migration `0040_pf4_backfill_deal_status_cache` brought every existing row in line. Single-source-of-truth goal achieved without breaking the 6+ ORM filters in `core/dashboard_api.py`, the views.py callers, or the frontend `SqlDealsPage`.
- **P-F-5:** **Deferred to task7** (full column drop — task6.md flags it as optional; with the auto-sync in place the columns now behave as a write-through cache, so the drop is a low-priority cleanup rather than a correctness fix).
- **P-F-6:** Frontend `CustomsClearanceManagement.tsx` — 10 new header inputs (التوقيت/تاريخ ثاني/مشتغل مرخص/**رقم البيان**/**رقم فاتورة المقاصة**/العملة/سعر العملة/صافي بدون ضريبة/مجموع الضريبة/الإجمالي). The external model had collapsed "رقم البيان" and "رقم فاتورة المقاصة" onto the same input (declaration_number); fixed to two separate inputs bound to `formDecl` and `formSettlementInvoice` respectively.

### Errors found in external-model commit & corrected
1. **`@property status/order_status/payment_status` shadowed Django fields** → replaced by a non-shadowing save-time auto-sync (P-F-4 above). `recalculate_deal_payment_status` now syncs all three fields atomically. Drift eliminated; ORM filters in dashboard_api/signals/SqlDealsPage keep working.
2. **`LogisticsClearanceSerializer._default_cost_lines`** was defined as a regular method but without `self` parameter → would `TypeError` when called as `self._default_cost_lines()`. Fixed with `@staticmethod`.
3. **Dropped `cost_lines` JSONField, but 7 callsites in `views.py` + `landed_cost.py` still read `clearance.cost_lines`** as a list → added `@property cost_lines` on `LogisticsClearance` returning `[{label, amount}]` from `lines` rows for backwards-compat. All legacy callsites work unchanged.
4. **`cost_lines = SerializerMethodField`** was read-only → frontend writes (`updateClearance({cost_lines})`) silently dropped. Changed to `JSONField(required=False)` so writes flow into `validate_cost_lines` + `_sync_lines_from_cost_lines`.
5. **P-F-6 UI:** "رقم البيان" and "رقم فاتورة المقاصة" were collapsed onto the same input → split into two distinct inputs (declaration_number vs settlement_invoice_number).

### Verified
- `manage.py check` = 0 issues
- `makemigrations --check` = no drift (after corrections)
- All 13 new migrations 0028-0040 applied successfully
- `tsc --noEmit` = 41 errors (no regression vs baseline)
- Model import sanity test passes; `LogisticsClearance.cost_lines` is now a property exposing the same shape
- `LogisticsDeal._sync_legacy_status_fields` runs on every `save()`; backfill migration succeeded

### Orphans Update
- JSONField `cost_lines` on clearance: **dropped + replaced by structured `LogisticsClearanceLine` table** (with backwards-compat property)
- JSONField `local_payments_json` + `conversion_metadata_json` on PurchaseInvoice: **dropped + replaced by `PurchaseInvoicePayment` + 3 conversion FKs**
- `notesMeanShippingPayment` Arabic-prefix parsing: **eliminated** → `payment_purpose` choice column
- DealItem + PIItem batch/expiry/warehouse stuffed in `notes`: **18 structured columns each**
- Clearance + Shipment + Deal missing Aseel header fields: **22 fields added in total**

## [TASK6 — P-G PROGRESS 2026-05-24]

> **Status:** P-G-1, P-G-2, P-G-13, P-G-14 completed; P-G-4 + P-G-12 partial. External-model commit reviewed and tabs expanded to spec.

### Done
- **G-1:** `ImportDocumentScreen.tsx` created at `frontend_v2/components/import-flow/`. Unified read-only view: 4×6 header band (22 fields), `CompactTimeline` (~32px) ●/◐/○ chip strip, **7 tabs** (الصفقات/التخليص/النقل المحلي/الدفعات/الحسابات/المرفقات/ملاحظات — expanded from 4 in the original first-pass commit), right-side totals dock (shipment totals + clearance paid-shipping/paid-clearance split + per-local-shipment lines), bottom status bar. Fits 1080p viewport.
- **G-2:** Route `/import-flow/:shipmentId` added to `App.tsx`. Sidebar "رحلة الاستيراد" link added under Procurement (existing "إدارة الشحنات" renamed to "الشحنات" for direct access). `AppView` type extended with `"import-flow"`. Breadcrumb label registered.
- **G-2-c (partial):** `ShipmentManagement.handleEdit` now redirects to `/import-flow/:id`. `CustomsClearanceManagement` toolbar has "رحلة الاستيراد" button. Full `/clearance/:id` and `/local-shipments/:id` route redirects deferred (those pages use modals not routes — no URL to redirect).
- **G-4:** DealForm header expanded from 12 to 22 fields (merged commercial band into header grid + added transaction_time + second_date + 8 commercial fields); `aseel-commercial-band` JSX block removed (CSS class kept as orphan in index.css — cosmetic only).
- **G-12 (partial):** `AseelIndexPicker` CSS converted from centered overlay to right-side panel (380px width, `justify-content: flex-end`, `align-items: stretch`, border-left, no border-radius). Dedicated `AseelSidePanel` primitive deferred.
- **G-13:** `scripts/density-audit.cjs` — detects files >400 lines, `CollapsibleSection`, large padding (`p-6..p-10`), large spacing (`space-y-4..9`), `: any`. Reports 308 issues across 130 files — baseline for G-7..G-11 sweep.
- **G-14:** `docs/ui_density_rules.md` — viewport budget table, header band spec, tab rules, compact timeline spec, side-dock rules, modal vs side-panel guidelines.

### Fixes applied during review
1. **`tab`/`setTab` dead state in ImportDocumentScreen** — removed (the shell manages active tab internally).
2. **Empty-shipmentId silently rendered blank state** — added explicit message "لم يتم اختيار إرسالية" with hint.
3. **Tabs reduced from 7+ spec to 4** — restored الدفعات (clearance payments table) + الحسابات (linked journals view) + المرفقات (placeholder for future Attachment polymorphic). Now matches task6.md spec.
4. **Right dock didn't show paid-shipping vs paid-clearance split** — now loads `listClearancePayments` and shows the split in the dock.

### Pending (deferred to follow-up phase or task7)
- **G-3 (delete old forms):** Cannot delete `ShipmentForm.tsx` / form-mode of `CustomsClearanceManagement` / form-mode of `LocalShippingPage` yet — `ImportDocumentScreen` is currently **read-only**. Editing parity must come first.
- **G-5..G-11** (Sales/Accounting/Procurement/Inventory/HR/SQL density sweep) — density-audit baseline shows ~308 candidate sites; iterative work.
- **G-12 full:** Dedicated `AseelSidePanel` primitive (proper props/API/types) — current change is CSS-only on AseelIndexPicker.
- **Editing parity in ImportDocumentScreen** — currently 100% read-only; field-level edit + save buttons + tab-level forms needed before old forms can be retired.
- **P-H..P-K** (business logic completion, frontend quality, tests, push).

## [TASK6.1 — A + B + C DONE 2026-05-24]

> **Status:** Editing parity Phases A (shipment header), B (clearance tab), C (deals link) completed on `claude/task6.1`. External-model commits 9f29870, 8e439c8, 8df2ac8 reviewed — one critical hooks-order bug fixed.

### Done
- **A — Shipment header editable:** `shipmentForm` state + onChange wired across 22 header fields. `Save (F12)` toolbar button + dirty guard via `JSON.stringify` diff + `beforeunload` warning + `● غير محفوظ` indicator in status bar. New-shipment case (`/import-flow/new`) starts with blank form; POST creates record. `apiPatchObject`/`apiPostObject` from `restApi.ts`.
- **B — Clearance tab editable:** 12-field clearance header (4×3 grid: declaration_number, clearance_date, transaction_time, second_date, licensed_dealer_no, settlement_invoice_number, broker, currency, exchange_rate, subtotal_no_vat, vat_total, grand_total). Inline lines table (add/edit/delete rows) with `line_type` choices (vat/declaration_fee/terminal/permits/broker_commission/customs_system/other). `تخزين التخليص` button → `updateClearance` with `cost_lines` JSON payload (backwards-compat with backend `_sync_lines_from_cost_lines`). Empty-clearance case shows `إنشاء سجل تخليص` button calling `createClearance({shipment})`.
- **C — Deals tab link:** `+ ربط صفقة` button opens picker modal listing unlinked deals (`apiGetList('logistics/deals/')`). Click → POST `logistics/shipments/<id>/add_deal/` then refreshes shipment to pull `shipment_deal_allocations`. Allocations table shows linked deals with cost-share preview.
- **AseelDocumentShell extension:** added `initialTab`/`activeTab`/`onTabChange` props for controlled tab state (so `?tab=clearance` query param works).

### Errors found in external-model commits & corrected
1. **React hooks-order violation** (the EXACT VII-1 bug fixed in P-B-1 for AccountingJournalEntryPage). External commits 9f29870/8e439c8/8df2ac8 declared **11+ `useState`/`useCallback`/`useEffect`/`useMemo`** AFTER the `if (loading)/if (error)/if (!shipmentId)/if (!s)` early returns. React would crash with "Rendered fewer hooks than during the previous render" on the first loading→loaded transition. Restructured: all hooks now declared before early returns; derived values (paidShipping/paidClearance/totals/headerBand/etc.) moved after the returns where they belong.
2. **Stale double-source for `shipmentDeals`** — external code had both a separate `useState([])` + extra `loadDeals()` API call AND a `useEffect` reading from `shipment.shipment_deal_allocations`. Two competing sources. Replaced with single `useMemo(shipment?.shipment_deal_allocations)` — the serializer already includes allocations on the GET, no extra fetch needed.
3. **`notesContent` was readOnly textarea** but `shipmentForm.notes` had no onChange — silently dropped edits. Wired to `setSF({ notes })`.
4. **`postLocalShipment`/`createLocalShipment`/`updateLocalShipment` imports** were added by the external model but never called (D wasn't implemented). Removed unused imports.

### Verified
- `manage.py check` = 0 issues
- `makemigrations --check` = no drift
- `tsc --noEmit` = 41 errors (no regression vs baseline)
- `logistics/views.py:646` `add_deal` action confirmed exists (used by C)
- `clearanceApi.updateClearance` confirmed supports all P-F-1 fields (transaction_time, second_date, licensed_dealer_no, settlement_invoice_number, currency, exchange_rate, subtotal_no_vat, vat_total, grand_total) plus the legacy `cost_lines` JSON for backwards-compat sync

### Completed after second review (C-4 + C-5)
- **C-4 (edit allocation inline):** `حصة الشحن (USD)` column in the deals table is now an editable input. onBlur dispatches PATCH to `logistics/shipments/<id>/` with `deal_allocations: [{deal_id, allocated_shipping_cost}]` — uses the existing write-only field on `LogisticsShipmentSerializer._apply_deal_allocations` (no new endpoint needed). Sum + total displayed below the table for quick reconciliation against `total_shipping_cost_usd`.
- **C-5 (unlink button):** new backend action `LogisticsShipmentViewSet.remove_deal` (POST `logistics/shipments/<id>/remove_deal/` body `{deal_id}`). Mirrors `add_deal`. Refuses to detach when the shipment has been posted to accounting (`transit_journal_id` set) to avoid orphan GL allocations. Frontend wired with `window.confirm` + refresh after success.

### Completed (task6.1 D+E+F — 2026-05-24, with review fixes)
- **D — Local Shipments Tab Editable:** Inline CRUD form below the local shipments table. Row click → edit mode with 12 editable fields. Add / save / cancel / delete buttons. Post-to-accounting action button per unposted row. All state hoisted above early returns (hooks rules preserved).
- **E — Payments Tab Editable:** Add-payment form (5 fields including cash-box picker). POST via existing `payClearanceFromCashBox`. Auto-refresh payments + right-dock totals after success.
- **F — Convert to Purchase Invoice:** Toolbar button «تحويل إلى فاتورة شراء». Navigates to `/purchase-invoices/new?shipment=ID` (or opens the existing converted PI if found). Disabled for `shipment_type=transport`. Visual link shown if invoice already exists.

### Errors found in external-model D+E+F commit and corrected
1. **BLOCKER: E-payment dispatched empty `cash_box_external_id`** — the backend hard-requires it (`logistics/views.py:1135` returns 400 "حقل cash_box_external_id مطلوب"). Every payment attempt would have failed. Added `accountingApi.getCashBoxLedgers()` loader, `cashBoxes`/`payCashBoxId` state, a cash-box `<select>` in the form, and required-field validation on the submit button. Warning shown when no cash boxes are linked yet.
2. **D-create payload sent `carrier: 0`** — fails on backend FK validation. Added early-return guard with a clear "الناقل مطلوب" message before dispatching the create. (Long-term: replace the number input with an `AseelIndexPicker` for carriers — flagged for task7.)

### Pending (task6.1)
- **G** Routing migration (Shipments/Clearance/Local → /import-flow with tab param) — A-G-1 redirect ready to restore
- **H** Delete old forms (ShipmentForm, clearance form-mode, local form-mode)
- **I** AseelSidePanel primitive + browse-modal sweep
