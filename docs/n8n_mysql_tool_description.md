# إعداد MySQL Tool في n8n AI Agent

## 1. إعدادات الـ Node

| الحقل | القيمة |
|-------|--------|
| **Node Type** | MySQL |
| **Operation** | Execute Query |
| **Query** | `{{ $fromAI('query', 'SQL SELECT query to run on the Ktra database') }}` |

---

## 2. Tool Description (الصق هذا في حقل Description)

```
Execute a read-only SQL SELECT query on the Ktra company MySQL database.
Always use SELECT only — never UPDATE, DELETE, INSERT, or DROP.
Always add TenantID = 1 to every query that has a TenantID column.
Always use LIMIT (max 200 rows).

DATABASE SCHEMA — KEY TABLES:

[partners] — Suppliers, brokers, agents
  Columns: PartnerID, Name, LegalName, Type, LinkedAccountID, Country, Phone, Email
  Type values: Supplier | FreightForwarder | CustomsBroker | LocalTransporter | Customer

[logistics_deals] — Purchase deals with suppliers
  Columns: DealID, TenantID, RefNumber, PartnerID, TotalAmount, PaymentStatus, OrderStatus,
           shipping_workflow_status, factory_name, pi_number, subtotal, discount_amount,
           tax_amount, total_cbm, total_weight_kg, CreatedAt
  PaymentStatus: Unpaid | Partially Paid | Fully Paid
  OrderStatus: Open | Manufacturing | ReadyToShip | Shipping | Clearance | Delivered | Closed
  shipping_workflow_status: sw_mfg_start | sw_wait_agent_ship | sw_wait_intl_ship | sw_wait_arrival | sw_wait_clearance | sw_released
  ⚠️ NO ProductID column — use logistics_deal_items to reach products

[logistics_deal_items] — Line items of each deal
  Columns: DealItemID, DealID, ProductID, Quantity, UnitPrice
  JOIN path: logistics_deals → logistics_deal_items → products

[products] — Product catalog
  ⚠️ Name columns are Name_AR and Name_EN (NOT "Name")
  Columns: ProductID, TenantID, SKU, Name_AR, Name_EN, HS_Code, Weight_KG, Volume_CBM

[logistics_payments] — Payments for deals and shipments
  Columns: PaymentID, DealID, LinkedShipmentID, PaymentNumber, Title, Amount, Status,
           TransferDate, ConfirmationDate, IsPosted, JournalID, cash_box_external_id
  Status: Pending | ClaimUploaded | Paid | Confirmed
  DealID is filled for supplier payments; LinkedShipmentID for shipping agent payments

[logistics_shipments] — Shipments
  Columns: ShipmentID, TenantID, ShipmentNumber, ShippingAgentID, Status,
           total_shipping_cost_usd, BillOfLading, ContainerNumber, DepartureDate, ArrivalDate,
           shipment_route_status, shipping_type
  Status: Pending | In-Transit | Arrived | Clearing | Cleared

[logistics_shipment_deals] — Many-to-many: Shipment ↔ Deal
  Columns: LinkID, ShipmentID, DealID

[logistics_clearance] — Customs clearance records (one per shipment)
  Columns: ClearanceID, TenantID, ShipmentID, CustomsBrokerID, DeclarationNumber,
           ClearanceDate, Status, cost_lines (JSON array), Notes
  Status: Processing | Cleared | Hold

[logistics_clearance_payments] — Payments for clearance
  Columns: ClearancePaymentID, TenantID, ClearanceID, CustomsBrokerID, Amount,
           PaymentDate, CashBoxExternalID, IsPosted, JournalID

[journal_headers] — Accounting journal entries
  Columns: JournalID, TenantID, TransactionDate, Description, ReferenceType, ReferenceID, IsPosted
  IsPosted: 1 = posted, 0 = draft

[journal_lines] — Journal entry lines
  Columns: JLineID, TenantID, JournalID, AccountID, Debit, Credit, PartnerID, LineDescription

[chartofaccounts] — Chart of accounts
  Columns: AccountID, TenantID, Code, Name, ParentID, Type, IsActive
  Type: Asset | Liability | Equity | Revenue | Expense

[cash_box_ledger_accounts] — Cash box to GL account mapping
  Columns: CashBoxLedgerID, TenantID, ExternalID, Name, AccountID, CurrencyCode

CRITICAL SQL RULES:
1. For product search: always JOIN via logistics_deal_items, never join products directly to logistics_deals
   CORRECT: logistics_deals d JOIN logistics_deal_items di ON di.DealID=d.DealID JOIN products p ON p.ProductID=di.ProductID
2. Products table: use Name_AR (Arabic) or Name_EN (English) — column "Name" does NOT exist
3. Multiple LIKE conditions must be separate: (col LIKE '%word1%' AND col LIKE '%word2%') — never combine in one LIKE
4. Text search across name variants: (p.Name_AR LIKE '%x%' OR p.Name_EN LIKE '%x%')
5. If result is empty: try a broader search before declaring "not found"
6. Always use table aliases: logistics_deals d, partners p, products pr, etc.
7. Never write raw values in queries that could break encoding — use LIKE with %

SPEED RULES — follow these to answer faster:
- NEVER use SELECT * — always list only needed columns
- Put TenantID = 1 first in WHERE clause, then other filters
- For counts/sums use aggregate functions: SELECT COUNT(*), SUM(Amount) — don't fetch all rows
- For "latest" questions: ORDER BY id DESC LIMIT 10
- For a single specific item: LIMIT 5 is enough
- Combine data in one JOIN query instead of running multiple separate queries
- For open-ended questions: run COUNT first, fetch details only if count <= 50

COMMON QUERY PATTERNS:

-- Deals with supplier name:
SELECT d.RefNumber, d.TotalAmount, d.PaymentStatus, p.Name
FROM logistics_deals d JOIN partners p ON p.PartnerID = d.PartnerID
WHERE p.Name LIKE '%supplier%' AND d.TenantID = 1

-- Products in a deal:
SELECT pr.Name_AR, pr.Name_EN, di.Quantity, di.UnitPrice
FROM logistics_deals d
JOIN logistics_deal_items di ON di.DealID = d.DealID
JOIN products pr ON pr.ProductID = di.ProductID
WHERE d.RefNumber LIKE '%INV-001%' AND d.TenantID = 1

-- Unpaid deals summary:
SELECT d.RefNumber, d.TotalAmount, COALESCE(SUM(py.Amount),0) as Paid
FROM logistics_deals d
LEFT JOIN logistics_payments py ON py.DealID = d.DealID AND py.Status IN ('Paid','Confirmed')
WHERE d.TenantID = 1 AND d.PaymentStatus != 'Fully Paid'
GROUP BY d.DealID, d.RefNumber, d.TotalAmount

-- Shipment and its deals:
SELECT sh.ShipmentNumber, sh.Status, d.RefNumber, p.Name as supplier
FROM logistics_shipments sh
JOIN logistics_shipment_deals sd ON sd.ShipmentID = sh.ShipmentID
JOIN logistics_deals d ON d.DealID = sd.DealID
JOIN partners p ON p.PartnerID = d.PartnerID
WHERE sh.TenantID = 1
```
