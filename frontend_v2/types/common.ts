
export interface ServiceResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

export type Theme = 'light' | 'dark';

export type AppView =
    | "dashboard"
    | "tasks"
    | "task-management"
    | "users"
    | "reports"
    | "sourcing"
    | "settings"
    | "employee-notes"
    | "points-history"
    | "points-management"
    | "attendance"
    | "purchase-invoices"
    | "sales-invoices"
    | "sales-customers"
    | "old-invoices"
    | "items-management"
    | "supplier-management"
    | "price-offers"
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
    | "accounting-general-ledger"
    | "accounting-trial-balance"
    | "accounting-vat-report"
    | "accounting-landed-cost"
    | "sales-customer-payments"
    | "sales-settings"
    | "local-shipping"
    | "sql-products"
    | "sql-partners"
    | "sql-deals"
    | "sql-shipments"
    | "smart-assistant"
    | "accounting-fiscal-periods"
    | "accounting-exchange-rates"
    | "stock-levels"
    | "stock-movements"
    | "property-rental";

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
