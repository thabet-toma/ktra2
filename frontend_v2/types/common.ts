
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
    | "old-invoices"
    | "items-management"
    | "supplier-management"
    | "price-offers"
    | "deals-management"
    | "shipments-management"
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
    | "sql-products"
    | "sql-partners"
    | "sql-deals"
    | "sql-shipments";

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
