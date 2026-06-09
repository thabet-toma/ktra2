# TASK 10 — Multi-Entity (Multi-Company / Multi-Shop) Feature Plan

> **Status:** PLAN ONLY. No production code. Awaiting approval.
> **Date:** 2026-06-09 · **Author role:** Staff SWE + Tech Lead.
> **Goal:** Let one owner run **multiple independent shops/companies** — separate chart of accounts, separate invoices, separate invoice sequences, separate reports — without merging data.

---

## 0. DECISIONS (confirmed with stakeholder) & ASSUMPTIONS

**Confirmed answers:**
1. **Access model:** *Single login + company switcher.* One user owns the shops and switches the **active company** from a top-bar selector; all work is scoped to one company at a time (no consolidation).
2. **New-company COA:** *Copy a default template* (standard Arabic COA: cash, bank, sales, COGS, VAT, AR/AP…).
3. **Permissions:** *Independent role per company* — the same user can be Manager in shop A and Staff in shop B.

**Assumptions (Simplicity First):**
- A1. **"Company/Shop" == the existing `Tenant` model.** The data layer is **already row-scoped by `tenant_id`** on every domain table; COA is `unique_together=[['tenant','code']]`; invoice numbers are `unique_together=[['tenant','invoice_number']]` via `next_invoice_number(tenant_id, book)`. **We reuse this. We do NOT add a parallel `company_id`.** (Justification in §1.)
- A2. Existing data all lives under `tenant_id=1` (FK `default=1`); it becomes the user's **first company** ("Default Company").
- A3. No cross-company consolidated reports in scope (matches "تقارير مستقلة").
- A4. No new SaaS/billing tenancy concepts. This is in-app multi-company for one customer, not a hosting boundary.
- A5. Currency/base-currency stays per `TenantSettings` (already exists).

> **No remaining blocking ambiguity.** Open the plan for approval.

---

## 1. ISOLATION STRATEGY — chosen vs. rejected

| Strategy | Verdict | Why |
|---|---|---|
| **(A) Reuse `Tenant` as the company; row-level scoping by `tenant_id` (already present)** | ✅ **CHOSEN** | Zero schema duplication. COA, sequences, journals, partners, inventory, sales are **already** `tenant`-FK'd and filtered via `core/tenant_utils.get_tenant`. The feature becomes *membership + switcher + scoping audit + COA bootstrap*, not a data redesign. Lowest risk, smallest diff. |
| (B) Add a new `company_id` column to every table | ❌ Rejected | Duplicates the existing `tenant_id` isolation → two parallel scoping systems, massive migration, high regression risk. Violates Simplicity First. |
| (C) Separate DB schema/database per company | ❌ Rejected | Operationally heavy (migrations × N, connection routing), unrequested multi-tenant complexity. The brief explicitly forbids it. |

**Conclusion:** The product already *is* multi-company at the storage layer; it is merely not *exposed*. Task10 exposes it safely.

---

## 2. CURRENT-STATE FACTS (audited, file:line)

- `tenants/models.py` — `Tenant(TenantID, CompanyName, …)`, `TenantSettings` (per-company VAT, currency, fiscal period, official numbers). ✅ already a "company."
- `core/tenant_utils.py:get_tenant` — resolves from `X-Tenant-Id` header → `user.tenant_id` → single-tenant auto. Has `_validate_user_tenant_access` but **no membership model** backing it.
- `accounting/models.py` — `Account` is `tenant`-scoped, `unique_together=[['tenant','code']]`. ✅ COA already per-company.
- `sales/services.py:1331 next_invoice_number(tenant_id, book)` + `SalesInvoice` `unique_together=[['tenant','invoice_number']]`. ✅ sequences already per-company.
- `frontend_v2/utils/tenantContext.ts:resolveTenantId()` — reads `localStorage.tenantId` → `VITE_TENANT_ID` → `1`. ✅ the switch point already exists; nothing exposes it in the UI.
- **Gaps to build:** (1) User↔Company membership **with per-company role**; (2) company switcher UI + active-company persistence/echo in `X-Tenant-Id`; (3) "create company" flow that clones a COA template + seeds `TenantSettings`; (4) a scoping-completeness audit (some FKs use `default=1`, some viewsets must be re-checked); (5) data migration assigning legacy rows to Default Company; (6) login → company-pick journey.

---

## 3. USER JOURNEY (verifiable target)

```
Login → (has ≥1 company?) 
   ├─ 1 company  → auto-select it → app scoped to it
   └─ ≥2 companies → company picker → choose active → app scoped to it
Top bar shows active company + switch dropdown.
Switch company → X-Tenant-Id changes → all lists/COA/invoices/reports reload scoped.
"إضافة شركة" (Manager only) → name + template → new Tenant + cloned COA + TenantSettings → membership(role=Manager) → becomes switchable.
Invoice numbering, COA, reports are independent per company (verified).
```

---

## 4. MILESTONES & ATOMIC TASKS

> Each task: **ID · Title · Files · Steps · Verifiable Goal · Depends on.**

### M1 — Membership model (User ↔ Company + per-company role)

- **M1-T1 · `UserCompanyMembership` model**
  - Files: `tenants/models.py`, new migration `tenants/migrations/00xx_membership.py`.
  - Steps: add `UserCompanyMembership(user FK→auth.User, tenant FK→Tenant, role CharField[choices: manager/accountant/staff/viewer], is_default Bool, created_at)`; `unique_together=[['user','tenant']]`.
  - Verifiable Goal: `makemigrations`+`migrate` clean; admin can create a membership; querying `user.company_memberships` returns rows.
  - Depends on: —
- **M1-T2 · Membership-backed access check**
  - Files: `core/tenant_utils.py` (`_validate_user_tenant_access`).
  - Steps: replace the loose `getattr(user,'tenant_id')` check with: superuser → allow; else require a `UserCompanyMembership(user, tenant)` to exist, else `PermissionDenied`.
  - Verifiable Goal: a user without membership gets 403 for that `X-Tenant-Id`; with membership gets 200. Unit test both.
  - Depends on: M1-T1.
- **M1-T3 · Per-company role resolution**
  - Files: `core/user_roles.py`, `core/tenant_utils.py`.
  - Steps: expose `get_active_role(user, tenant)` = membership.role; have existing role gates read **the active company's role** instead of a global role.
  - Verifiable Goal: same user resolves role=manager for company A, staff for B in two requests differing only by `X-Tenant-Id`.
  - Depends on: M1-T1.

### M2 — "My companies" + switch API

- **M2-T1 · List-my-companies endpoint**
  - Files: `tenants/views.py`, `tenants/urls.py`, `tenants/serializers.py`.
  - Steps: `GET /api/tenants/my-companies/` → `[{tenant_id, name, role, is_default}]` from the caller's memberships.
  - Verifiable Goal: returns exactly the caller's companies with roles; empty list if none.
  - Depends on: M1-T1.
- **M2-T2 · Set-default-company endpoint (optional persistence)**
  - Files: `tenants/views.py`, `tenants/urls.py`.
  - Steps: `POST /api/tenants/set-default/ {tenant_id}` flips `is_default` for that user.
  - Verifiable Goal: default persists across logins; only one default per user.
  - Depends on: M1-T1.

### M3 — Company switcher UI (single login)

- **M3-T1 · Active-company context + switcher component**
  - Files: new `frontend_v2/contexts/CompanyContext.tsx`, `frontend_v2/components/layout/CompanySwitcher.tsx`, `frontend_v2/utils/tenantContext.ts`.
  - Steps: on login, fetch `my-companies`; store active id (reuse `localStorage.tenantId` so `resolveTenantId()` keeps working); render a top-bar dropdown; switching writes `tenantId` and triggers a global reload/refetch.
  - Verifiable Goal: switching the dropdown reloads lists/COA/invoices scoped to the new company; refresh keeps the choice.
  - Depends on: M2-T1.
- **M3-T2 · Login → company-pick gate**
  - Files: `frontend_v2/App.tsx`, `LoginPage.tsx`.
  - Steps: after auth: 0 companies → block with message; 1 → auto-select; ≥2 → show picker before the app shell.
  - Verifiable Goal: the three branches behave as specified (manual walkthrough).
  - Depends on: M3-T1.

### M4 — Create company + COA template clone

- **M4-T1 · Default COA template source**
  - Files: new `accounting/management/commands/seed_coa_template.py` **or** `accounting/coa_template.py` (a Python list of standard accounts).
  - Steps: define the standard Arabic COA (assets 1xxx incl. cash/bank, liabilities 2xxx incl. VAT/AP, equity 3xxx, revenue 4xxx, COGS/expense 5xxx) as data.
  - Verifiable Goal: the template lists the accounts the sales/inventory engines need (cash, bank, AR, AP, sales revenue, COGS, inventory, output VAT).
  - Depends on: —
- **M4-T2 · `create_company` service (atomic)**
  - Files: `tenants/services.py` (new), `accounting/services.py`.
  - Steps: in one `transaction.atomic()`: create `Tenant` + `TenantSettings` (default VAT/currency) → clone COA template into that tenant (respecting `unique_together[tenant,code]`) → create `UserCompanyMembership(user, role=manager, is_default=False)`.
  - Verifiable Goal: calling the service yields a new tenant with a full COA and a manager membership; rolls back fully on any error.
  - Depends on: M4-T1, M1-T1.
- **M4-T3 · Create-company endpoint + UI (Manager only)**
  - Files: `tenants/views.py`, `tenants/urls.py`, `frontend_v2/components/settings/` new `CreateCompanyModal.tsx`, `CompanySwitcher.tsx`.
  - Steps: `POST /api/tenants/companies/ {name}` → calls `create_company`; UI form (name + "نسخ القالب الافتراضي" note); on success refresh `my-companies` and switch to it.
  - Verifiable Goal: a manager creates "محل 2", lands in it with an empty-but-structured COA and its own invoice sequence starting fresh.
  - Depends on: M4-T2, M3-T1.

### M5 — Scoping-completeness audit (regression guard)

- **M5-T1 · Enumerate every tenant-scoped viewset & confirm filter**
  - Files: all `*/views.py` (sales, accounting, inventory, logistics, partners, hr, realestate), `*/services.py` report builders.
  - Steps: grep each `get_queryset` / report for `get_tenant` + `.filter(tenant_id=…)`; list any that don't scope.
  - Verifiable Goal: a checklist showing every list/report endpoint filters by the active tenant; zero unscoped leaks.
  - Depends on: —
- **M5-T2 · Replace silent `default=1` reliance on create**
  - Files: models/serializers where FK `tenant` has `default=1` (`partners/models.py:6,31,102`, others).
  - Steps: ensure `perform_create` always sets tenant from `get_tenant(request)` (most already do); keep `default=1` only as a migration backstop, never as a create-time path.
  - Verifiable Goal: creating any record under company B never writes `tenant_id=1`; test on partners + an invoice.
  - Depends on: M5-T1.
- **M5-T3 · Cross-company isolation tests**
  - Files: new `tenants/tests/test_company_isolation.py`.
  - Steps: seed 2 companies; assert company A's user cannot read/modify B's invoices/accounts (403/empty), invoice numbers are independent, COA codes can repeat across companies.
  - Verifiable Goal: the isolation test suite passes; both companies can have account code `1101` independently and invoice `D-0001` independently.
  - Depends on: M4-T2.

### M6 — Data migration (existing data → Default Company)

- **M6-T1 · Backfill memberships for existing users**
  - Files: new data migration `tenants/migrations/00xx_backfill_default_company.py`.
  - Steps: ensure Tenant #1 exists ("Default Company"); create `UserCompanyMembership(user, tenant=1, role=<existing/global role or manager>, is_default=True)` for every existing user.
  - Verifiable Goal: post-migrate, every existing user has exactly one default membership to company 1 and can log in unchanged.
  - Depends on: M1-T1.
- **M6-T2 · Verify legacy rows are attributed**
  - Files: migration / one-off check script.
  - Steps: assert no domain rows have NULL tenant; any stray rows get `tenant_id=1`.
  - Verifiable Goal: a count query shows 0 unscoped rows across sales/accounting/inventory/partners.
  - Depends on: M6-T1.

### M7 — Lightweight, non-blocking logging (per protocol)

- **M7-T1 · Reuse the task8 async logging for company events**
  - Files: `core/logger_middleware.py` (exists), call sites in `tenants/services.py`.
  - Steps: log INFO on `company.create` / `company.switch` (user, tenant_id, trace_id) via the existing `core.request_tracing` logger — non-blocking, no new infra.
  - Verifiable Goal: creating/switching a company emits one INFO line with the trace id; no measurable latency added.
  - Depends on: M4-T2.

---

## 5. EXECUTION ORDER

M1 → M6-T1 (backfill so nobody is locked out) → M2 → M3 → M4 → M5 → M7.
**Safety gate:** M6-T1 must run with M1 in the same deploy so existing logins keep working.

---

## 6. DEPENDENCY VALIDATION (time-aware, 2026-06)

- **No new runtime dependencies.** Reuses Django ORM, DRF, existing React/Tailwind.
- Optional patch bump: **Django 6.0.1 → 6.0.6** (latest stable, 2026-06-03) — safe, recommended before adding migrations.
- No deprecated APIs used (membership = standard FK/M2M; no removed Django features).

---

## 7. OUT OF SCOPE (No Feature Creep)

- Cross-company consolidated reporting/dashboards.
- Per-account or per-field permissions (role is per-company, coarse).
- Company-level billing/subscription gating.
- Schema/DB-per-company, sharding, or hosting-level tenancy.
