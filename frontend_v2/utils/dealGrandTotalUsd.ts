import type { Deal } from "../types";

/**
 * إجمالي الصفقة بالدولار كما تُعرض في قائمة الصفقات:
 * مجموع البنود (أو subtotal) − خصم + شحن (إن لم يكن مضمّناً) + ضريبة.
 * قد يختلف عن حقل totalAmount إذا كان الأخير قديماً أو معدّلاً يدوياً.
 */
export function getDealGrandTotalUsd(deal: Deal): number {
    const items = deal.items || [];
    let calculatedSubtotal = 0;
    if (items.length > 0) {
        calculatedSubtotal = items.reduce((sum, item) => {
            const qty = parseFloat(String(item.quantity)) || 0;
            const price = parseFloat(String(item.unitPrice)) || 0;
            return sum + qty * price;
        }, 0);
    } else {
        calculatedSubtotal = parseFloat(String(deal.subtotal)) || 0;
    }

    const discountAmount = parseFloat(String(deal.discountAmount)) || 0;
    const shippingCost = deal.shippingIncluded ? 0 : parseFloat(String(deal.shippingCost)) || 0;
    const netAfterDiscount = Math.max(0, calculatedSubtotal - discountAmount);
    const taxableBase = netAfterDiscount + shippingCost;

    let taxAmount = 0;
    if (deal.taxType === "amount") {
        taxAmount = parseFloat(String(deal.taxAmount)) || 0;
    } else {
        const taxRate = parseFloat(String(deal.taxRate)) || 0;
        taxAmount = taxableBase * (taxRate / 100);
    }

    return taxableBase + taxAmount;
}
