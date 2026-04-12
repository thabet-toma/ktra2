

/** مراحل الشحن والتصنيع (مخزّنة في SQL shipping_workflow_status) */
export type ShippingWorkflowStatus =
    | 'sw_mfg_start'
    | 'sw_wait_agent_ship'
    | 'sw_wait_intl_ship'
    | 'sw_wait_arrival'
    | 'sw_wait_clearance'
    | 'sw_released';

export type DealStatus =
    | 'initial'
    | 'first_payment_pending'
    | 'first_payment_done'
    | 'first_payment_confirmed'
    | 'production_completed'
    | 'second_payment_pending'
    | 'second_payment_done'
    | 'second_payment_confirmed'
    | 'shipping_preparation'
    | 'shipped'
    | 'manufacturing_started'
    | 'shipping_in_progress'
    | 'completed'
    | 'cancelled';

export interface DealItem {
    id: string;
    itemId: string;
    name: string;
    modelNumber?: string;
    categoryId: string;
    categoryName: string;
    specifications: string;
    imageUrls: string[];
    hsCodePrimary?: string;
    quantity: number;
    unitPrice: number;
    totalPrice: number;
    factoryImageUrl?: string;
    notes?: string;
}

export interface DealPayment {
    id: string;
    type: string;
    amount: number;
    usdToIls: number;
    transferCost: number;
    paymentDate: string;
    paymentConfirmationDate?: string;
    notes: string;
    alibabaClaimImage?: string;
    bankSwiftImage?: string;
    confirmedBySupplier?: boolean;
    confirmedAt?: string;
    confirmedBy?: string;
    supplierConfirmationImage?: string;
    supplierNotes?: string;
    /** من SQL: مرحّل للمحاسبة */
    isPosted?: boolean;
    /** معرّف قيد اليومية بعد الترحيل */
    journalId?: number;
    cashBoxId?: string;
    cashBoxName?: string;
    cashBoxWithdrawalAt?: string;
    cashBoxWithdrawalBy?: string;
    cashBoxTransactionIds?: string[];
    _cashBoxSettled?: boolean;
    dealNumber?: string;
    installmentId?: string;
    installmentNumber?: number;
}

export interface DealActivity {
    id: string;
    type: 'status_change' | 'payment' | 'item_update' | 'note' | 'attachment';
    action: string;
    details?: string;
    userId: string;
    userName: string;
    userRole: string;
    timestamp: string;
    metadata?: Record<string, any>;
}

export interface DealProductionPath {
    productionDays: number;
    startDate?: string;
    endDate?: string;
    completed: boolean;
    notes?: string;
}

export interface DealShippingDetails {
    address: string;
    shipmentImageUrl?: string;
    preparedDate?: string;
    trackingNumber?: string;
    notes?: string;
}

export interface DealStatusHistory {
    status: DealStatus;
    timestamp: string;
    notes: string;
    changedBy: string;
}

export interface DealStatusHistoryEntry {
    status: DealStatus;
    timestamp: string;
    notes?: string;
    changedBy?: string;
}

export interface DealInstallment {
    id: string;
    installmentNumber: number;
    percentage: number;
    amount: number;
    status: 'unpaid' | 'partially_paid' | 'paid' | 'cancelled';
    dueDate?: string;
    notes?: string;
    paymentData?: {
        paymentId?: string;
        amountPaid?: number;
        paymentDate?: string;
        transactionId?: string;
    };
    createdAt: string;
    updatedAt: string;
    locked?: boolean;
}

export interface Deal {
    id: string;
    dealNumber: string;
    priceOfferId: string;
    originalOfferNumber?: string;
    supplierId: string;
    factoryName: string;
    supplierInvoiceNumber?: string;
    /** عنوان / وصف قصير للصفقة (عادة عربي) — عمود description في SQL */
    dealDescription?: string;
    quoteImages?: string[];
    quotePdfs?: {
        name: string;
        url: string;
        size: number;
        type: string;
    }[];
    status: DealStatus;
    /** مرحلة الشحن (يدوي/تلقائي) — مصدر الحقيقة في قاعدة البيانات */
    shippingWorkflowStatus?: ShippingWorkflowStatus | null;
    installments: DealInstallment[];
    installmentPlanEnabled: boolean;
    currentInstallmentNumber?: number;
    payments: DealPayment[];
    items: DealItem[];
    totalAmount: number;
    remainingAmount: number;
    subtotal: number;
    shippingCost: number;
    shippingIncluded: boolean;
    discountAmount: number;
    taxRate: number;
    taxAmount: number;
    taxType?: 'percentage' | 'amount';
    shippingMethod?: string;
    alibabaOrderLink?: string;
    internalNotes?: string;
    paymentMethod?: string;
    warrantyDuration?: number;
    totalWeight?: number;
    totalVolume?: number;
    totalWeightKg?: number;
    certificates?: string;
    shipmentNotes?: string;
    dealDate?: string;
    firstPaymentDate?: string;
    paymentDate?: string;
    productionDays?: number;
    deliveryDays?: number;
    startedProductionAt?: string;
    statusHistory: DealStatusHistory[];
    activityLog: DealActivity[];
    createdBy: string;
    createdAt: string;
    updatedAt: string;
    updatedBy: string;
    supplierSnapshot?: {
        tradeName?: string;
        /** اسم محلي / مستعار — غالباً من اسم الشريك في النظام */
        alias?: string;
        /** الاسم القانوني / الإنجليزي عند الحاجة */
        legalName?: string;
        address?: string;
        salesRepName?: string;
        salesRepPhone?: string;
    };
    invoiceId?: string;
    hasHistoricalInvoice?: boolean;
}
