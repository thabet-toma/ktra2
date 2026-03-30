
import { DealStatus, DealStatusHistoryEntry, DealActivity } from './deal';

export interface LocalPayments {
    customsClearanceFees?: number;
    customsDuties?: number;
    portFees?: number;
    internalShippingFees?: number;
    palestinianTaxCustoms?: number;
    lumpSumAmount?: number;
    includedInPrice?: boolean;
    calculationMethod?: 'detailed' | 'lump_sum';
}

export interface InvoiceInstallment {
    id: string;
    installmentNumber: number;
    amount: number;
    status: 'unpaid' | 'paid';
    notes?: string;
    dueDate?: string;
    bankSlipUrl?: string;
    paymentDate?: string;
}

export interface InvoiceItem {
    id: string;
    itemId: string;
    name: string;
    categoryId: string;
    categoryName: string;
    specifications: string;
    imageUrls: string[];
    hsCodePrimary?: string;
    quantity: number;
    unitPrice: number;
    totalPrice: number;
    modelNumber?: string;
    factoryImageUrl?: string;
    notes?: string;
}

export interface DealInvoiceInfo {
    dealId?: string;
    dealNumber?: string;
    originalStatus?: DealStatus;
    shippingMethod?: string;
    shippingCost?: number;
    shippingIncluded?: boolean;
    deliveryDays?: number;
    productionDays?: number;
    alibabaOrderLink?: string;
    internalNotes?: string;
    dealDate?: string;
    firstPaymentDate?: string;
    startedProductionAt?: string;
    completedAt?: string;
    statusHistory?: DealStatusHistoryEntry[];
    activityLog?: DealActivity[];
    createdBy: string;
    updatedBy?: string;
    createdAt?: string;
    updatedAt?: string;
    supplierSnapshot?: {
        tradeName: string;
        alias?: string;
        phone?: string;
        email?: string;
        address?: string;
        salesRepName?: string;
        salesRepPhone?: string;
    };
    warrantyDuration?: number;
    certificates?: string;
    paymentMethod?: string;
    shipmentNotes?: string;
    totalWeight?: number;
    totalVolume?: number;
    quoteImages?: string[];
    quotePdfs?: {
        name: string;
        url: string;
        size: number;
        type: string;
    }[];
}

export interface Invoice {
    id: string;
    serialNumber: string;
    invoiceNumber: string;
    invoiceName?: string;
    supplierId: string;
    factoryName?: string;
    factoryEmail?: string;
    factoryPhone?: string;
    factoryWebsite?: string;
    factoryAddress?: string;
    salesRepName?: string;
    salesRepWechat?: string;
    salesRepPhone?: string;
    notes?: string;
    totalWeight?: number;
    totalVolume?: number;
    shippingCost?: number;
    shippingIncluded?: boolean;
    localPayments?: LocalPayments;
    supplierInvoiceNumber?: string;
    alibabaOrderLink?: string;
    invoiceLink?: string;
    items: InvoiceItem[];
    status: 'incomplete' | 'completed' | 'deposit_paid' | 'archived' | 'historical' | 'partially_paid' | 'fully_paid';
    subtotal?: number;
    discountAmount?: number;
    taxRate?: number;
    taxAmount?: number;
    taxType?: 'percentage' | 'amount';
    grandTotal?: number;
    conversionMetadata?: {
        dealEffectiveRate: number;
        shipmentEffectiveRate: number;
        internalShippingUsd: number;
        globalShippingUsd: number;
        extraCostsUsd: number;
        totalUsd: number;
        remainingBalanceRate: number;
    };
    currency?: 'USD' | 'ILS';
    imageUrls?: string[];
    quoteImages?: string[];
    quotePdfs?: {
        name: string;
        url: string;
        size: number;
        type: string;
    }[];
    isHistorical?: boolean;
    dealId?: string;
    dealNumber?: string;
    installments?: InvoiceInstallment[];
    installmentPlanEnabled?: boolean;
    dealInfo?: DealInvoiceInfo;
    supplierSnapshot?: {
        tradeName?: string;
        alias?: string;
        address?: string;
        salesRepName?: string;
        salesRepPhone?: string;
    };
    invoiceDate?: string;
    createdAt: string;
    updatedAt: string;
    createdBy: string;
    supplierLogoUrl?: string;
}
