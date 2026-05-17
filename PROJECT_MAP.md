# PROJECT_MAP.md — KTRA Import/Trading ERP

> الذاكرة الخارجية للمشروع. حدّث هذا الملف عند أي تغيير معماري.
> Last audited: 2026-05-17.

## [TECH_STACK]

- **Backend:** Django 6.0.1 + Django REST Framework. Python 3.13.
- **DB:** MySQL (`django.db.backends.mysql`, mysqlclient). DB name `smartktra_smart-ktra`. `foreign_key_checks=0` + `STRICT_TRANS_TABLES` in `init_command`.
- **Auth:** DRF `TokenAuthentication` + `SessionAuthentication`, `IsAuthenticated` (see `core/api_defaults.py`).
- **Multi-tenancy:** header `X-Tenant-Id` resolved by `core/tenant_utils.get_tenant()`. Single-tenant auto-resolve if exactly 1 tenant. **No hard tenant isolation enforced** (cross-tenant access only logged).
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
- **Dead code:** `frontend_v2/components/forms/deal-specific/PaymentRegistration.tsx` is 100% commented out (fossil of `deal-parts/PaymentRegistration.tsx`).
- **`resolve_forex_account()`** exists in `accounting/services.py` but is never called — forex gain/loss not actually posted.
- **No year-end closing** routine (P&L → retained earnings) exists.
- **`frontend/` Next.js app** unrelated to ERP; keep separate or move out of repo.
- **The active 500 fix** (tenant-None guard in `sales/views.py perform_create`) converts an opaque crash to a clear 400; the underlying environment cause (likely no `Tenant(TenantID=1)` seeded in the fresh MySQL DB) still needs the user to seed a tenant.
