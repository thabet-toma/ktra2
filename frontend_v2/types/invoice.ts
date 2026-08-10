
import { DealStatus, DealStatusHistoryEntry, DealActivity } from './deal';

/** سطر ضمن «بند الضرائب والرسوم» على فاتورة الشيكل */
export interface TaxesAndFeesLine {
    id: string;
    label: string;
    /** مبلغ بالشيكل، أو قيمة النسبة إن كان entryType = percentage */
    amount: number;
    /** قيمة ثابتة (₪) أو نسبة من أساس الضريبة (مجموع البضاعة − خصم ± شحن الفاتورة إن وُجد) */
    entryType?: "amount" | "percentage";
    /**
     * عند entryType = percentage: أساس النسبة.
     * goods (افتراضي): من أساس البضاعة الخاضع لض.ق.م.
     * after_main_vat: من (الأساس + مبلغ ض.ق.م الفاتورة) — مثل رسوم كترا بعد الضريبة.
     */
    percentageBasis?: "goods" | "after_main_vat";
}

export interface PurchaseInvoiceFeeLine {
    id?: string;
    description: string;
    amount: number;
    calculationType?: "amount" | "percentage";
    calculationValue?: number;
    percentageBasis?: "goods" | "after_main_vat";
    expenseAccountId: number | null;
    expenseAccountCode?: string;
    expenseAccountName?: string;
    capitalizeToInventory: boolean;
    isTaxable: boolean;
}

export interface LocalPayments {
    customsClearanceFees?: number;
    customsDuties?: number;
    portFees?: number;
    /** قديم: شحن محلي؛ يُفضَّل تسجيل الشحن من شاشة التخليص الجمركي */
    internalShippingFees?: number;
    palestinianTaxCustoms?: number;
    /** قديم: مبلغ واحد؛ يُستبدل بـ taxesAndFeesLines عند التحرير من الواجهة */
    extraTaxesFees?: number;
    /** بنود متعددة «بند الضرائب والرسوم» (ILS) — تُجمع وتُوزَّع مع ض.ق.م على الأسطر */
    taxesAndFeesLines?: TaxesAndFeesLine[];
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
    /** تكلفة الوحدة النهائية بالشيقل (بضاعة + حصة شحن/تخليص موزّعة) */
    landedUnitPriceIls?: number;
    /** إجمالي السطر بالشيقل شامل التوزيع */
    landedLineTotalIls?: number;
    /** T-SERIAL: أرقام وحدات هذا البند — تُجسَّد في المخزن عند الاستلام. */
    serials?: string[];
}

/** مصدر استيراد الفاتورة من تخليص + شحنة (نفس منطق ربط الصفقات بالشحنة) */
export interface InvoiceImportLogistics {
    shipmentId: string;
    shipmentNumber?: string;
    shipmentName?: string | null;
    clearanceId: number;
    clearanceDeclaration?: string | null;
    brokerName?: string | null;
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
    /** يُعبأ عند الاستيراد من تخليص جمركي — يربط الفاتورة بالشحنة والتخليص */
    importLogistics?: InvoiceImportLogistics;
    conversionMetadata?: {
        dealEffectiveRate: number;
        shipmentEffectiveRate: number;
        internalShippingUsd: number;
        globalShippingUsd: number;
        extraCostsUsd: number;
        totalUsd: number;
        remainingBalanceRate: number;
        dealPaidIls?: number;
        dealUnpaidUsd?: number;
        dealTotalIls?: number;
        shipmentPaidIls?: number;
        shipmentUnpaidUsd?: number;
        shipmentTotalIls?: number;
        /** 0–1: حصة صفقة من مجموع totalAmount لصفقات الشحنة — تخليص ونقل من التخليص */
        dealShareByDealsValue?: number;
        /** 0–1: حصة الصفقة من حجم/وزن صفقات الشحنة — شحن دولي فقط */
        dealShareByVolume?: number;
        /** مجموع totalAmount (USD) لصفقات الشحنة عند التوزيع */
        shipmentDealsTotalUsd?: number;
        /** totalAmount لهذه الصفقة كما دخل في حساب النسبة */
        dealThisTotalUsdForShare?: number;
        dealShareOfShipment?: number;
        dealShipmentAllocatedIls?: number;
        /** @deprecated استخدم dealShareByDealsValue — يُعبأ بنفس النسبة للتوافق */
        dealShareOfClearanceVolume?: number;
        dealClearanceAllocatedIls?: number;
        clearancePaymentsTotalIls?: number;
        /** حوض التخليص بالشيقل الذي ضُرب في النسبة (قد يساوي دفعات أو بنود حسب المصدر) */
        clearancePoolIls?: number;
        /** من الخادم: cost_lines | payments */
        clearanceCostBasis?: string;
        /** مجموع بنود التخليص بالشيقل (للمقارنة عند اختلافها عن الدفعات) */
        costLinesTotalIls?: number;
        /** حصة الصفقة من شحن على التخليص خارج حصة الجمارك: «شحن محلي» و/أو «دفعة الشحن (الناقل)» في cost_lines */
        dealLocalShippingFromClearanceIls?: number;
        /** مجموع أسطر الشحن المحلي في التخليص قبل ضرب نسبة الصفقة */
        clearanceLocalShippingLinesTotalIls?: number;
        dealLocalTransportIls?: number;
        localTransportTotalIls?: number;
        localTransportSource?: string;
        localTransportAllocationBasis?: string;
        allocationMethod?: string;
        /** من الخادم: شحن دولي بالحجم ووزن التخليص بالقيمة — غيابه = فاتورة قبل فصل النسب */
        dualShareAllocations?: boolean;
        /** مجموع عمولات/تكاليف تحويل الدفعات المنفّذة بالشيكل (من transfer_cost × usd_to_ils) */
        dealTransferCommissionsIls?: number;
        /** جزء من دفعات الصفقة فقط */
        dealTransferCommissionsFromDealPaymentsIls?: number;
        /** مجموع عمولات دفعات شحن الشحنة (قبل التوزيع على الصفقات) */
        shipmentTransferCommissionsTotalIls?: number;
        /** حصة هذه الصفقة من عمولات دفعات الشحنة (× نسبة الحجم/الوزن مثل الشحن الدولي) */
        dealTransferCommissionsFromShipmentShareIls?: number;
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
    /** اسم الصفقة المحوَّلة إلى هذه الفاتورة (للعرض في القائمة) */
    dealTitle?: string;
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
    /** معرف قيد استلام المخزون في SQL بعد الترحيل التلقائي */
    glPurchaseReceiptJournalId?: number;
    /** FK شحنة SQL */
    shipment?: string;
    /** FK تخليص SQL */
    clearanceId?: string;
    /** فاتورة شراء SQL مرحّلة إلى المحاسبة — لا يُعاد حساب التكلفة الأرضية تلقائياً */
    isPosted?: boolean;
    /** مرجع شراء (إرجاع بضاعة للمورد) بدل فاتورة شراء عادية. */
    isReturn?: boolean;
    /** رقم الفاتورة الأصلية المرتبطة بالمرجع (W7a). */
    originalInvoiceId?: string;
    originalInvoiceNumber?: string;
    /** T-PLINEAGE: المستند الذي وُلدت منه الفاتورة (عرض سعر أو طلبية شراء). */
    sourceDocument?: {
        kind: 'order' | 'quotation';
        id: number;
        number: string;
        originKind?: 'quotation' | null;
        originId?: number | null;
        originNumber?: string | null;
    };
    /** ضرائب ورسوم إضافية مهيكلة تُرحّل فوق إجمالي الفاتورة الأساسي. */
    fees?: PurchaseInvoiceFeeLine[];
    feesTotal?: number;
    payableTotal?: number;
    amountPaid?: number;
    remainingBalance?: number;
    paymentStatus?: 'paid' | 'partially_paid' | 'unpaid';
    paymentStatusDisplay?: string;
    /** حالة استلام البضاعة للمخزن — مستقلة عن الحالة المالية. */
    receiptStatus?: 'not_received' | 'partially_received' | 'received';
    receiptStatusDisplay?: string;
    partnerBalance?: number;
    partnerBalanceBeforeInvoice?: number;
    partnerBalanceAfterInvoice?: number;
    paymentDetails?: Array<{
        source: 'supplier_payment' | 'purchase_invoice_payment';
        id: number;
        paymentDate: string;
        amount: number;
        currencyCode: string;
        exchangeRate: number;
        cashOrBankAccountName?: string;
        isPosted: boolean;
        journalId?: number;
        notes?: string;
    }>;
    invoiceType?: 'local' | 'international';
}
