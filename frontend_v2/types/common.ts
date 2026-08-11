
export interface ServiceResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

export type Theme = 'light' | 'dark';

export type AppView =
    | "dashboard"
    | "super-admin"
    | "development-notes"
    | "tasks"
    | "task-management"
    | "users"
    | "reports"
    | "report-runner"
    | "team-time-report"
    | "sourcing"
    | "settings"
    | "employee-notes"
    | "points-history"
    | "points-management"
    | "attendance"
    | "purchase-invoices"
    | "international-invoices"
    | "sales-invoices"
    | "sales-customers"
    | "old-invoices"
    | "items-management"
    | "items-categories"
    | "supplier-management"
    | "price-offers"
    | "import-offers"
    | "deals-management"
    | "shipments-management"
    | "customs-clearance"
    | "cash-boxes"
    | "cash-box-details"
    | "gallery"
    | "store"
    | "accounting-coa"
    | "accounting-journals"
    | "accounting-journal-entry"
    | "accounting-cheques"
    | "accounting-banks"
    | "accounting-bank-reconciliation"
    | "accounting-general-ledger"
    | "accounting-trial-balance"
    | "accounting-vat-report"
    | "accounting-landed-cost"
    | "sales-customer-payments"
    | "sales-settings"
    | "purchase-settings"
    | "purchase-receipts"
    | "sales-delivery-notes"
    | "product-profile"
    | "product-group"
    | "local-shipping"
    | "sql-products"
    | "sql-partners"
    | "sql-deals"
    | "sql-shipments"
    | "group-constants"
    | "smart-assistant"
    | "accounting-fiscal-periods"
    | "accounting-exchange-rates"
    | "stock-levels"
    | "stock-movements"
    | "warehouses"
    | "warehouse-transfer"
    | "stocktake"
    | "product-cost"
    | "property-rental"
    | "aseel-kit"
    | "aseel-sales"
    | "sales-quotations"
    | "sales-orders"
    | "credit-debit-notes"
    | "sql-clearances"
    | "sql-purchase-invoices"
    | "shipments"
    | "shipment-management"
    | "clearance"
    | "accounting-balance-sheet"
    | "accounting-income-statement"
    | "accounting-vat-statements"
    | "accounting-year-end-close"
    | "sales-return"
    | "purchase-return"
    | "supplier-payments"
    | "invoice-profits"
    | "reserved-stock"
    | "partner-profile"
    | "import-flow"
    | "activity-log"
    | "permissions"
    | "personal-expenses"
    | "payroll"
    | "company-accountant-engagements"
    | "sensitive-devices"
    | "after-sales"
    | "about-us"
    | "contact";

export interface Attachment {
    id: string;
    url: string;
    name: string;
    type: 'image' | 'file';
    format?: string;
    storageSource?: 'cloudinary' | 'firebase';
    fileData?: {
        name: string;
        type: string;
        size: number;
        lastModified: number;
    };
}
