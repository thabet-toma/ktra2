
export interface ShipmentDealInfo {
    dealId: string;
    dealNumber: string;
    originalOfferNumber: string;
    totalAmount: number;
    totalVolume: number;
    totalWeightKg: number;
    distributedCost: number;
    extraCosts?: number;
    notes?: string;
}

export type ShipmentStatus =
    | 'draft'
    | 'payment_pending'
    | 'partially_paid'
    | 'paid'
    | 'shipped'
    | 'delivered'
    | 'cancelled';

export interface ShipmentInstallment {
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

export interface ShipmentPayment {
    id: string;
    type: string;
    amount: number;
    usdToIls: number;
    transferCost: number;
    paymentDate: string;
    paymentConfirmationDate?: string;
    notes: string;
    claimImage?: string;
    bankSwiftImage?: string;
    confirmedBySupplier?: boolean;
    confirmedAt?: string;
    confirmedBy?: string;
    supplierConfirmationImage?: string;
    supplierNotes?: string;
    cashBoxId?: string;
    cashBoxName?: string;
    cashBoxWithdrawalAt?: string;
    cashBoxWithdrawalBy?: string;
    cashBoxTransactionIds?: string[];
    _cashBoxSettled?: boolean;
    shipmentNumber?: string;
    installmentId?: string;
    installmentNumber?: number;
}

export interface ShipmentShippingInfo {
    shippingType: 'sea' | 'air';
    shipName?: string;
    containerNumber?: string;
    departureDate?: string;
    arrivalDate?: string;
    internationalShippingCompany?: string;
    billOfLadingNumber?: string;
    billOfLadingFile?: string;
    flightNumber?: string;
    airwayBillNumber?: string;
    airwayBillFile?: string;
    shipmentStatus?: {
        status: string;
        statusDate?: string;
        notes?: string;
        completed?: boolean;
    };
    fromTerm?: string;
    toTerm?: string;
    imoNumber?: string;
    mmsiNumber?: string;
    trackingLink?: string;
}

export interface Shipment {
    id: string;
    shipmentNumber: string;
    agentShipmentNumber?: string;
    shippingAgentId: string;
    shippingAgentName: string;
    israeliSideName?: string;
    shippingInfo?: ShipmentShippingInfo;
    deals: ShipmentDealInfo[];
    totalShippingCostUsd: number;
    totalVolume: number;
    totalWeightKg: number;
    status: ShipmentStatus;
    notes?: string;
    shipmentName?: string;
    pricingMethod?: 'total' | 'unit';
    unitType?: 'cbm' | 'weight' | 'container';
    pricePerUnit?: number;
    installments: ShipmentInstallment[];
    installmentPlanEnabled: boolean;
    payments: ShipmentPayment[];
    remainingAmount: number;
    createdAt: string;
    updatedAt: string;
    createdBy: string;
    updatedBy: string;
}
