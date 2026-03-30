# Full Backend Technical Documentation: Accounting System

This document provides a detailed technical overview of the backend implementation for the accounting module, intended for developers and architects.

## 1. Tech Stack & Environment
- **Framework:** [Django 4.2+](https://www.djangoproject.com/)
- **API Engine:** [Django REST Framework (DRF)](https://www.django-rest-framework.org/)
- **Database:** MariaDB / MySQL (interfaced via `mysqlclient`)
- **Integration:** Existing Database Schema Integration (`managed = False`)

---

## 2. Model Architecture & Data Mapping
Since we are integrating with an existing ERP database, models are configured with `managed = False`.

### Core Models:
- **`Account` (`chartofaccounts`):**
    - Uses `db_column='TenantID'` for multi-tenancy.
    - `Parent` field utilizes a self-referencing `ForeignKey` to build hierarchical trees.
    - Unique constraints are enforced at the DB level, but mirrored in code for validation.
- **`JournalHeader` (`journal_headers`):**
    - Primary entity for a financial transaction.
    - Tracks `IsPosted` status. Once `True`, the business logic locks the record.
- **`JournalLine` (`journal_lines`):**
    - Related to `JournalHeader` via `JournalID`.
    - Stores `Debit` and `Credit` as `DecimalField` (18,2) to prevent floating-point precision issues.

---

## 3. Multi-Tenancy Strategy (The "Tenant 0" Logic)
The system is designed to handle multiple companies (Tenants). 

### Tenant Context Helper (`_get_tenant_context`):
```python
def _get_tenant_context(self):
    # Logic: Attempt to fetch tenant from session/header.
    # Fallback: If no tenant found (or during setup), return TenantID=0.
    # Implementation: In views.py, this provides the 'Tenant' object or ID 
    # for all creation/query operations.
```
- **Fallback Mechanism:** To prevent foreign key failures during empty-state testing, the system allows `TenantID=0`.
- **Integrity Handling:** `services.py` implements "Relaxed Tenant Validation", allowing transactions across accounts if the tenant context is set to 0.

---

## 4. Transaction Management & Atomicity
To ensure accounting integrity (Double-Entry), we use Django's `transaction.atomic()`.

### The "Poisoned Transaction" Solution:
We avoid catching exceptions *inside* a transaction block that would leave the transaction in an unusable state.
1. **Transaction Phase:** Header and Lines are saved within an `atomic` block.
2. **Post-Transaction Phase:** Audit logs and non-critical operations are executed *after* the commit.
3. **Error Distinguishing:** We explicitly catch `IntegrityError` (DB constraint violations) and `ValidationError` (logical failures) to provide high-level "Hints" to the API consumer.

---

## 5. Business Logic Layer (`services.py`)

### `validate_journal_entry(header, lines_data)`:
This is the core accounting validator:
- **Balance Check:** `sum(debit) == sum(credit)`.
- **Sign Check:** Ensures no negative debits/credits.
- **Account Validation:** Verifies that all target accounts are active and belong to the correct tenant (unless fallback is active).
- **Execution:** Called inside the transaction before commit.

### `create_audit_log(...)`:
- **Resilience:** Implemented with a broad `try-except` block and executed outside primary transactions. 
- **Purpose:** Tracks `CREATE`, `UPDATE`, `DELETE`, and `POST` actions for compliance.

---

## 6. API Interaction (DRF)
- **ViewSets:** `AccountViewSet` and `JournalViewSet` provide standard REST actions.
- **Custom Actions:** 
    - `post_entry`: A specialized `POST` endpoint that handles the transition from "Draft" to "Posted", performing final persistence locks.
- **Serializers:** Handle nested `JournalLine` inputs, allowing the frontend to send a single JSON payload for a header and all its lines.

---

## 7. Known Constraints & Design Decisions
- **Manual Table Mapping:** All models use explicit `db_table` names to match the legacy schema.
- **Soft-Locking:** Instead of database triggers, the `IsPosted` flag is used in `views.py` and the Frontend to disable `DELETE` and `PATCH` operations.
- **Performance:** Related data (lines) are fetched using `select_related` or sub-serializers to minimize "N+1" query problems.
