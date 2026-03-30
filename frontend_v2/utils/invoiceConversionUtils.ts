import { Deal, Shipment, Invoice, InvoiceItem, DealPayment, ShipmentPayment } from "../types";

/**
 * Calculates the effective exchange rate for a given total amount and payments.
 * 
 * Logic:
 * 1. Paid_USD = Sum of all USD payment amounts that are confirmed or have a bank swift.
 * 2. Paid_ILS = Sum of (Payment_Amount_USD * usdToIls_Rate) for those payments.
 * 3. Unpaid_USD = Total_USD - Paid_USD.
 * 4. Unpaid_ILS = Unpaid_USD * remainingBalanceRate.
 * 5. Effective_Rate = (Paid_ILS + Unpaid_ILS) / Total_USD.
 */
export const calculateEffectiveRate = (
    totalAmountUsd: number,
    payments: (DealPayment | ShipmentPayment)[],
    remainingBalanceRate: number
): number => {
    if (totalAmountUsd <= 0) return remainingBalanceRate;

    let paidUsd = 0;
    let paidIls = 0;

    payments.forEach((p) => {
        // Only count payments that are actually executed (confirmed or swift uploaded)
        if (p.bankSwiftImage || p.confirmedBySupplier || (p as any).cashBoxWithdrawalAt) {
            paidUsd += p.amount || 0;
            paidIls += (p.amount || 0) * (p.usdToIls || 0);
        }
    });

    const unpaidUsd = Math.max(0, totalAmountUsd - paidUsd);
    const unpaidIls = unpaidUsd * remainingBalanceRate;

    const totalIlsValue = paidIls + unpaidIls;

    return totalIlsValue / totalAmountUsd;
};

/**
 * Prepares a partial Invoice object from a Deal and its parent Shipment.
 */
export const prepareInvoiceFromDeal = (
    deal: Deal,
    shipment: Shipment,
    dealRemainingRate: number,
    shipmentRemainingRate: number
): Partial<Invoice> => {
    // 1. Calculate Effective Rate for the Deal (Items)
    const dealEffectiveRate = calculateEffectiveRate(
        deal.totalAmount,
        deal.payments || [],
        dealRemainingRate
    );

    // 2. Calculate Effective Rate for the Shipment (Shipping Cost)
    const shipmentEffectiveRate = calculateEffectiveRate(
        shipment.totalShippingCostUsd,
        shipment.payments || [],
        shipmentRemainingRate
    );

    // 3. Convert Items to NIS
    const nisItems: InvoiceItem[] = (deal.items || []).map((item) => {
        const unitPriceIls = item.unitPrice * dealEffectiveRate;
        return {
            ...item,
            id: crypto.randomUUID(), // New ID for invoice item
            unitPrice: Math.round(unitPriceIls * 100) / 100,
            totalPrice: Math.round(unitPriceIls * (item.quantity || 0) * 100) / 100,
        };
    });

    // 4. Calculate Subtotal in NIS
    const subtotalIls = nisItems.reduce((sum, item) => sum + item.totalPrice, 0);

    // 5. Convert Shipping Cost to NIS
    // Logic updated:
    // a) Internal Shipping from Deal (e.g. within China) -> use Deal Rate
    const internalShippingUsd = deal.shippingCost || 0;
    const internalShippingIls = internalShippingUsd * dealEffectiveRate;

    // b) Global Shipping from Shipment (Distributed + Extra) -> use Shipment Rate
    const dealShipmentInfo = shipment.deals.find(d => d.dealId === deal.id);
    const distributedCostUsd = dealShipmentInfo?.distributedCost || 0;
    const extraCostsUsd = dealShipmentInfo?.extraCosts || 0;

    const globalShippingIls = (distributedCostUsd + extraCostsUsd) * shipmentEffectiveRate;

    // Total Shipping in NIS
    const totalShippingCostIls = Math.round((internalShippingIls + globalShippingIls) * 100) / 100;

    // 6. Final Invoice Construction
    const invoice: Partial<Invoice> = {
        invoiceNumber: `${deal.dealNumber}-INV`,
        supplierId: deal.supplierId,
        factoryName: deal.factoryName,
        dealId: deal.id,
        dealNumber: deal.dealNumber,
        items: nisItems,
        subtotal: subtotalIls,
        shippingCost: totalShippingCostIls,
        shippingIncluded: deal.shippingIncluded,
        discountAmount: Math.round((deal.discountAmount || 0) * dealEffectiveRate * 100) / 100,
        taxRate: deal.taxRate,
        taxType: deal.taxType,
        currency: 'ILS' as any, // Explicitly NIS
        invoiceDate: deal.dealDate || new Date().toISOString().split('T')[0],
        invoiceName: deal.internalNotes || '',
        supplierInvoiceNumber: deal.supplierInvoiceNumber || '',
        alibabaOrderLink: deal.alibabaOrderLink || '',
        notes: deal.internalNotes || '',
        status: 'incomplete',
        totalWeight: deal.totalWeight,
        totalVolume: deal.totalVolume,
        supplierSnapshot: deal.supplierSnapshot,
        quoteImages: deal.quoteImages || [],
        quotePdfs: deal.quotePdfs || [],
        conversionMetadata: {
            dealEffectiveRate,
            shipmentEffectiveRate,
            internalShippingUsd,
            globalShippingUsd: distributedCostUsd,
            extraCostsUsd: extraCostsUsd,
            totalUsd: deal.totalAmount,
            remainingBalanceRate: dealRemainingRate
        },
        dealInfo: {
            dealId: deal.id,
            dealNumber: deal.dealNumber,
            shippingMethod: deal.shippingMethod,
            paymentMethod: deal.paymentMethod,
            warrantyDuration: deal.warrantyDuration,
            certificates: deal.certificates,
            shipmentNotes: deal.shipmentNotes,
            productionDays: deal.productionDays,
            deliveryDays: deal.deliveryDays,
            createdBy: deal.createdBy,
            createdAt: deal.createdAt,
            alibabaOrderLink: deal.alibabaOrderLink,
            internalNotes: deal.internalNotes,
            firstPaymentDate: deal.firstPaymentDate,
            startedProductionAt: deal.startedProductionAt,
            originalStatus: deal.status,
            totalWeight: deal.totalWeight,
            totalVolume: deal.totalVolume,
            quoteImages: deal.quoteImages || [],
            quotePdfs: deal.quotePdfs || [],
            supplierSnapshot: deal.supplierSnapshot,
        } as any
    };

    // Recalculate Financials
    // 1. Discount is already converted
    const afterDiscount = Math.max(0, subtotalIls - (invoice.discountAmount || 0));

    // 2. Shipping Influence on Tax (if not included in price)
    const shippingToInclude = invoice.shippingIncluded ? 0 : totalShippingCostIls;
    const taxableBase = afterDiscount + shippingToInclude;

    let taxAmountIls = 0;
    if (invoice.taxType === 'amount') {
        // If tax was a fixed USD amount in the deal, convert it using deal rate
        taxAmountIls = Math.round((deal.taxAmount || 0) * dealEffectiveRate * 100) / 100;
    } else {
        // If tax is a percentage, calculate it from the new NIS taxable base
        taxAmountIls = taxableBase * ((invoice.taxRate || 0) / 100);
    }

    invoice.taxAmount = Math.round(taxAmountIls * 100) / 100;
    invoice.grandTotal = Math.round((taxableBase + taxAmountIls) * 100) / 100;

    return invoice;
};
