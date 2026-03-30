
export type SupplierType = 'factory' | 'shipping_agent' | 'international_trader' | 'local_company' | 'service_provider';

export interface Supplier {
    id: string;
    tradeName: string;
    alias?: string;
    phone?: string;
    mobile?: string;
    street?: string;
    city?: string;
    region?: string;
    postalCode?: string;
    country?: string;
    supplierId: string;
    currency?: string;
    openingBalance?: number;
    balanceDate?: string;
    email?: string;
    notes?: string;
    logoUrl?: string;
    salesRepName?: string;
    salesRepWechat?: string;
    salesRepPhone?: string;
    type?: SupplierType;
    createdAt: string;
    updatedAt: string;
}

export interface SupplierItemPrice {
    id: string;
    supplierId: string;
    supplierName: string;
    itemId: string;
    itemName: string;
    price: number;
    currency: string;
    date: string;
    invoiceId: string;
    createdAt: string;
}
