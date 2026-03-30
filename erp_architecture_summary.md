# ERP Full Stack Technical Documentation (Architecture V2)

This document provides a detailed technical overview of the Integrated ERP System, aligning the Backend implementation with the actual Database Schema.

## 1. System Ecosystem (Full ERP)
Beyond the Accounting module, the system integrates the following modules as mapped in the database:
- **Core CRM:** Leads, Opportunities, Pipeline Stages, Contact Management.
- **Supply Chain:** Purchase Orders (`purchaseorders`), Shipments (`shipments`), Landed Costs.
- **Retail & Sales:** Sales Invoices, Sales Orders, POS Sessions/Terminals.
- **Human Resources:** Employees, Payroll Runs, Salary Slips.
- **Operations:** Service Requests, Technician Assignments, Work Orders.
- **Inventory/Warehouse:** Multi-warehouse support, Stock Ledger, Reservations.
- **Fixed Assets:** Tracking and Periodical Depreciation logic.

## 2. Standardized Naming Conventions
To maintain professional Django standards while interfacing with a legacy SQL schema:
- **Database Layer:** Uses PascalCase/SnakeCase mix (e.g., `PartnerID`, `CostCenterID`).
- **Application Layer (Django):** Standardized to `snake_case`. Mapping is handled via `db_column` in the Model Meta or field definitions:
  ```python
  tenant = models.ForeignKey(Tenant, db_column='TenantID', ...)
  transaction_date = models.DateField(db_column='TransactionDate', ...)
  ```

## 3. Data Integrity & Persistence Strategies
### Soft Delete (Logical Deletion)
Critical tables implement logical deletion to preserve historical audit trails:
- **`is_deleted` (Boolean):** Indicates if the record is active.
- **`deleted_at` (Timestamp):** Tracks when the deletion occurred.
Django Managers are utilized to automatically filter out deleted records from standard queries.

### Performance Indexing
High-traffic tables like `journal_lines` and `stock_ledger` utilize composite indexes:
- `idx_journal_report`: `(TenantID, PartnerID, AccountID)`
- `idx_stock_balance`: `(TenantID, ProductID, WarehouseID)`

## 4. Analytical Views (Reporting Layer)
The system offloads complex calculations to the Database Layer using SQL Views:
- **`vw_trial_balance`:** Real-time balance calculations across the Chart of Accounts.
- **`vw_aged_receivable`:** Calculates overdue invoices grouped by aging buckets (30/60/90 days).
- **`vw_product_stock_balance`:** Aggregates ledger entries to show current available stock.

## 5. Unified Identity Management
The system reconciles Django's built-in `auth_user` with the ERP's `users` table:
- **Primary Auth:** Django Auth System.
- **Extended Profile:** The custom `users` table stores ERP-specific metadata (Tenant context, specific roles).
- **Direction:** Future unification into a single Custom User Model.
