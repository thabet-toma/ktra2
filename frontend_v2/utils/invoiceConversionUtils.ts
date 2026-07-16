import {
    Deal,
    Shipment,
    Invoice,
    InvoiceItem,
    InvoiceImportLogistics,
    DealPayment,
    ShipmentPayment,
    ShipmentDealInfo,
} from "../types";
import {
    invoiceGrandTotalIls,
    invoiceVatBaseIls,
} from "./invoiceTaxesAndFees";

export function getPurchaseInvoiceCostLabels(isShipmentLinkedImport: boolean) {
    return isShipmentLinkedImport
        ? {
            unitPrice: "تكلفة الوحدة الشاملة للاستيراد",
            lineTotal: "إجمالي السطر الشامل للاستيراد",
            merchandiseBase: "قيمة البضاعة قبل تكاليف الاستيراد",
        }
        : {
            unitPrice: "سعر الوحدة",
            lineTotal: "الإجمالي",
            merchandiseBase: "سعر الأساس (المنتجات)",
        };
}

export function mergeClearanceImportDeals(
    shipmentDeals: ShipmentDealInfo[],
    optionDeals: Array<{ deal_id: number; deal_ref: string }>
): ShipmentDealInfo[] {
    const merged = new Map(shipmentDeals.map((deal) => [String(deal.dealId), deal]));
    optionDeals.forEach((row) => {
        const dealId = String(row.deal_id);
        if (merged.has(dealId)) return;
        merged.set(dealId, {
            dealId,
            dealNumber: row.deal_ref,
            originalOfferNumber: "",
            totalAmount: 0,
            totalVolume: 0,
            totalWeightKg: 0,
            distributedCost: 0,
        });
    });
    return Array.from(merged.values());
}

/** سطر عرض موحّد: شحنة + تخليص (للقائمة ونموذج الفاتورة) */
export function formatInvoiceImportLogisticsLine(il: InvoiceImportLogistics): string {
    const name = (il.shipmentName || "").trim();
    const num = (il.shipmentNumber || "").trim();
    let ship: string;
    if (name && num && name !== num) ship = `${name} — ${num}`;
    else if (num) ship = num;
    else if (name) ship = name;
    else ship = `شحنة #${il.shipmentId}`;
    const dec = (il.clearanceDeclaration || "").trim();
    const clr = dec ? `تخليص: ${dec}` : `تخليص #${il.clearanceId}`;
    const broker = (il.brokerName || "").trim();
    return broker ? `${ship} · ${clr} · مخلص: ${broker}` : `${ship} · ${clr}`;
}

export function isPaymentSettled(p: DealPayment | ShipmentPayment): boolean {
    return !!(
        p.bankSwiftImage ||
        p.confirmedBySupplier ||
        (p as { cashBoxWithdrawalAt?: string }).cashBoxWithdrawalAt
    );
}

function sumSettledUsdIls(
    payments: (DealPayment | ShipmentPayment)[] | undefined
): { paidUsd: number; paidIls: number } {
    let paidUsd = 0;
    let paidIls = 0;
    for (const p of payments || []) {
        if (!isPaymentSettled(p)) continue;
        const a = Number(p.amount) || 0;
        const r = Number(p.usdToIls) || 0;
        paidUsd += a;
        paidIls += a * r;
    }
    return { paidUsd, paidIls };
}

/** عمولات/تكاليف تحويل دفعات الصفقة المنفّذة بالشيكل (transferCost × usdToIls) */
export function sumSettledDealTransferCommissionsIls(deal: Deal): number {
    let s = 0;
    for (const p of deal.payments || []) {
        if (!isPaymentSettled(p)) continue;
        const tc = Number((p as DealPayment).transferCost) || 0;
        if (tc <= 0) continue;
        const r = Number((p as DealPayment).usdToIls) || 0;
        if (r <= 0) continue;
        s += tc * r;
    }
    return Math.round(s * 100) / 100;
}

/** عمولات تحويل دفعات شحن الشحنة (مصفوفة payments على الشحنة = دفعات الوكيل بدون صفقة) */
export function sumSettledShipmentTransferCommissionsIls(shipment: Shipment): number {
    let s = 0;
    for (const p of shipment.payments || []) {
        if (!isPaymentSettled(p)) continue;
        const tc = Number(p.transferCost) || 0;
        if (tc <= 0) continue;
        const r = Number(p.usdToIls) || 0;
        if (r <= 0) continue;
        s += tc * r;
    }
    return Math.round(s * 100) / 100;
}

/** قيمة الصفقة بالشيقل: كل دفعة منفّذة بسعرها الفعلي + المتبقي بالدولار × سعر المتبقي */
export function dealTotalIlsFromActualPayments(
    deal: Deal,
    remainingBalanceRate: number
): { totalIls: number; paidUsd: number; paidIls: number; unpaidUsd: number } {
    const totalUsd = Math.max(0, Number(deal.totalAmount) || 0);
    const { paidUsd, paidIls } = sumSettledUsdIls(deal.payments);
    const unpaidUsd = Math.max(0, totalUsd - paidUsd);
    const totalIls = paidIls + unpaidUsd * remainingBalanceRate;
    return { totalIls, paidUsd, paidIls, unpaidUsd };
}

/** قيمة شحن الشحنة بالشيقل من دفعات الوكيل الفعلية + المتبقي */
export function shipmentTotalIlsFromActualPayments(
    shipment: Shipment,
    remainingBalanceRate: number
): { totalIls: number; paidUsd: number; paidIls: number; unpaidUsd: number } {
    const totalUsd = Math.max(0, Number(shipment.totalShippingCostUsd) || 0);
    const { paidUsd, paidIls } = sumSettledUsdIls(shipment.payments);
    const unpaidUsd = Math.max(0, totalUsd - paidUsd);
    const totalIls = paidIls + unpaidUsd * remainingBalanceRate;
    return { totalIls, paidUsd, paidIls, unpaidUsd };
}

/** حجم/وزن الصفقة بنفس منطق الشحنة (CBM أو كغ حسب unitType + pricingMethod). */
function dealMeasureForVolumeShare(
    shipment: Shipment,
    dealId: string,
    allDeals?: Deal[]
): number {
    const method = (shipment.pricingMethod || "total").toLowerCase();
    const utype = (shipment.unitType || "cbm").toLowerCase();
    const d = allDeals?.find((x) => x.id === dealId);
    const row = shipment.deals.find((r) => r.dealId === dealId);
    if (method === "unit" && utype === "weight") {
        const kg = d?.totalWeightKg ?? d?.totalWeight ?? row?.totalWeightKg;
        return Math.max(0, Number(kg) || 0);
    }
    const cbm = d?.totalVolume ?? row?.totalVolume;
    return Math.max(0, Number(cbm) || 0);
}

/** حصة الصفقة من حجم/وزن صفقات الشحنة — لشحن دولي فقط. */
function dealVolumeShareOnShipment(
    shipment: Shipment,
    dealId: string,
    allDeals?: Deal[]
): { share: number } {
    const rows = shipment.deals || [];
    const n = Math.max(1, rows.length);
    const measures = rows.map((r) => dealMeasureForVolumeShare(shipment, r.dealId, allDeals));
    const wsum = measures.reduce((a, b) => a + b, 0);
    const idx = rows.findIndex((r) => r.dealId === dealId);
    const thisM = idx >= 0 ? measures[idx]! : 0;
    if (wsum > 0) {
        return { share: Math.min(1, Math.max(0, thisM / wsum)) };
    }
    return { share: 1 / n };
}

/**
 * نسبة صفقة من إجمالي «سعر الصفقات» على الشحنة:
 * totalAmount لكل صفقة مرتبطة بالشحنة / مجموعها.
 */
function dealShareByDealsTotalValue(
    shipment: Shipment,
    dealId: string,
    allDeals?: Deal[]
): { share: number; totalDealsUsd: number; thisDealUsd: number } {
    const rows = shipment.deals || [];
    const n = Math.max(1, rows.length);

    const usdForLinkedDeal = (linkedId: string): number => {
        if (allDeals?.length) {
            const d = allDeals.find((x) => x.id === linkedId);
            if (d != null) return Math.max(0, Number(d.totalAmount) || 0);
        }
        const row = rows.find((r) => r.dealId === linkedId);
        return Math.max(0, Number(row?.totalAmount) || 0);
    };

    const totalDealsUsd = rows.reduce((s, r) => s + usdForLinkedDeal(r.dealId), 0);
    const thisDealUsd = usdForLinkedDeal(dealId);

    if (totalDealsUsd > 0) {
        return {
            share: Math.min(1, Math.max(0, thisDealUsd / totalDealsUsd)),
            totalDealsUsd,
            thisDealUsd,
        };
    }
    return { share: 1 / n, totalDealsUsd: 0, thisDealUsd };
}

function distributeByWeights(
    total: number,
    weights: number[]
): number[] {
    const n = weights.length;
    if (n === 0) return [];
    const wsum = weights.reduce((a, b) => a + b, 0);
    const base =
        wsum > 0
            ? weights.map((w) => (total * w) / wsum)
            : weights.map(() => total / n);
    const rounded = base.map((x) => Math.round(x * 100) / 100);
    const drift = Math.round((total - rounded.reduce((a, b) => a + b, 0)) * 100) / 100;
    if (Math.abs(drift) >= 0.005 && rounded.length) {
        rounded[rounded.length - 1] =
            Math.round((rounded[rounded.length - 1] + drift) * 100) / 100;
    }
    return rounded;
}

export type PrepareInvoiceConversionOptions = {
    dealRemainingRate: number;
    shipmentRemainingRate: number;
    /** دفعات التخليص بالشيقل — تُوزَّع بنسبة قيمة الصفقة من مجموع صفقات الشحنة */
    clearancePaymentsIls?: Array<{ amount: number }>;
    /** يُفضَّل: كل الصفقات (أو صفقات الشحنة) لحساب مجموع totalAmount بدقة */
    allDeals?: Deal[];
    /** يُعبأ عند الاستيراد من تخليص — يربط الفاتورة بالشحنة والتخليص في Firestore */
    importLogistics?: InvoiceImportLogistics;
};

/**
 * فاتورة بالشيقل من صفقة + شحنة (+ دفعات تخليص):
 * - بضاعة: نسبة من إجمالي قيمة الصفقة بالشيقل (من كل دفعة صفقة فعلية + المتبقي)
 * - شحن دولي: (إجمالي شحن الشحنة بالشيقل من الدفعات + المتبقي) × (حجم الصفقة / مجموع أحجام صفقات الشحنة)
 * - تخليص: (مجموع دفعات التخليص) × (قيمة الصفقة / مجموع قيم صفقات الشحنة)
 * - تُظهر لكل سطر تكلفة وحدة نهائية (بضاعة + شحن محلي/دولي/تخليص موزّع على البنود)
 */
export const prepareInvoiceFromDeal = (
    deal: Deal,
    shipment: Shipment,
    options: PrepareInvoiceConversionOptions
): Partial<Invoice> => {
    const {
        dealRemainingRate,
        shipmentRemainingRate,
        clearancePaymentsIls = [],
        allDeals,
        importLogistics,
    } = options;

    const {
        totalIls: dealValIls,
        paidUsd: dealPaidUsd,
        paidIls: dealPaidIls,
        unpaidUsd: dealUnpaidUsd,
    } = dealTotalIlsFromActualPayments(deal, dealRemainingRate);

    const {
        totalIls: shipCostIlsForShare,
        paidUsd: shipPaidUsd,
        paidIls: shipPaidIls,
        unpaidUsd: shipUnpaidUsd,
    } = shipmentTotalIlsFromActualPayments(shipment, shipmentRemainingRate);

    const dealTotUsd = Math.max(0, Number(deal.totalAmount) || 0);
    const impliedDealRate = dealTotUsd > 0 ? dealValIls / dealTotUsd : dealRemainingRate;

    const shipTotUsd = Math.max(0, Number(shipment.totalShippingCostUsd) || 0);
    /** تكلفة الشحنة بالشيكل للتوزيع: مدفوع بالشيكل بأسعار دفعاته + المتبقي×سعر المتبقي (مطابق للخادم). */
    const impliedShipRate =
        shipTotUsd > 0 ? shipCostIlsForShare / shipTotUsd : shipmentRemainingRate;

    const internalShippingUsd = Number(deal.shippingCost) || 0;
    const dealShipmentInfo = shipment.deals.find((d) => d.dealId === deal.id);
    const distributedCostUsd = Number(dealShipmentInfo?.distributedCost) || 0;
    const extraCostsUsd = Number(dealShipmentInfo?.extraCosts) || 0;
    const globalShipUsd = distributedCostUsd + extraCostsUsd;

    const { share: shareByDealsValue, totalDealsUsd, thisDealUsd } =
        dealShareByDealsTotalValue(shipment, deal.id, allDeals);
    const { share: shareByVolume } = dealVolumeShareOnShipment(shipment, deal.id, allDeals);

    const dealXferFromPaymentsIls = sumSettledDealTransferCommissionsIls(deal);
    const shipXferTotalIls = sumSettledShipmentTransferCommissionsIls(shipment);
    const dealShareShipXferIls = Math.round(shipXferTotalIls * shareByVolume * 100) / 100;
    const dealTransferCommissionsIls = Math.round((dealXferFromPaymentsIls + dealShareShipXferIls) * 100) / 100;

    const dealShipAllocatedIls = Math.round(shipCostIlsForShare * shareByVolume * 100) / 100;

    const clearancePaidSumIls = (clearancePaymentsIls || []).reduce(
        (s, p) => s + (Number(p.amount) || 0),
        0
    );
    const dealClearanceAllocatedIls = clearancePaidSumIls * shareByDealsValue;

    const internalShippingIls =
        dealTotUsd > 0
            ? dealValIls * (internalShippingUsd / dealTotUsd)
            : internalShippingUsd * dealRemainingRate;

    const items = deal.items || [];
    const weightsUsd = items.map((it) => Math.max(0, Number(it.totalPrice) || 0));
    const W = weightsUsd.reduce((a, b) => a + b, 0);

    const merchandiseUsdPool =
        W > 0 && dealTotUsd > 0 ? dealValIls * (W / dealTotUsd) : dealValIls;

    const lineMerchIls =
        W > 0 ? distributeByWeights(merchandiseUsdPool, weightsUsd) : items.map(() => 0);

    /* إن كان الشحن الداخلي مضمّناً في سعر البضاعة، لا نُكرّره في التوزيع على الأسطر */
    const internalInLanded = deal.shippingIncluded ? 0 : internalShippingIls;
    const logisticsPoolIls =
        internalInLanded + dealShipAllocatedIls + dealClearanceAllocatedIls;
    const lineLogisticsIls =
        W > 0 ? distributeByWeights(logisticsPoolIls, weightsUsd) : items.map(() => 0);

    const nisItems: InvoiceItem[] = items.map((item, idx) => {
        const qty = Math.max(1, Number(item.quantity) || 1);
        const merch = lineMerchIls[idx] ?? 0;
        const log = lineLogisticsIls[idx] ?? 0;
        const landedLine = Math.round((merch + log) * 100) / 100;
        const landedUnit = Math.round((landedLine / qty) * 100) / 100;
        const unitMerch = Math.round((merch / qty) * 100) / 100;
        const totalMerch = Math.round(merch * 100) / 100;
        return {
            ...item,
            id: crypto.randomUUID(),
            unitPrice: unitMerch,
            totalPrice: totalMerch,
            landedUnitPriceIls: landedUnit,
            landedLineTotalIls: landedLine,
        };
    });

    const subtotalIls = nisItems.reduce((sum, item) => sum + item.totalPrice, 0);

    const discountIls =
        dealTotUsd > 0
            ? Math.round((Number(deal.discountAmount) || 0) * impliedDealRate * 100) / 100
            : Math.round((Number(deal.discountAmount) || 0) * dealRemainingRate * 100) / 100;

    const totalShippingCostIls =
        Math.round((internalShippingIls + dealShipAllocatedIls) * 100) / 100;

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
        discountAmount: discountIls,
        taxRate: deal.taxRate,
        taxType: deal.taxType,
        currency: "ILS" as Invoice["currency"],
        invoiceDate: deal.dealDate || new Date().toISOString().split("T")[0],
        invoiceName:
            (deal.dealDescription || "").trim() ||
            (deal.internalNotes || "").split(/\r?\n/)[0]?.trim()?.slice(0, 200) ||
            "",
        supplierInvoiceNumber: deal.supplierInvoiceNumber || "",
        alibabaOrderLink: deal.alibabaOrderLink || "",
        notes: deal.internalNotes || "",
        status: "incomplete",
        totalWeight: deal.totalWeight,
        totalVolume: deal.totalVolume,
        supplierSnapshot: deal.supplierSnapshot,
        quoteImages: deal.quoteImages || [],
        quotePdfs: deal.quotePdfs || [],
        localPayments: {
            calculationMethod: "detailed",
            customsClearanceFees: Math.round(dealClearanceAllocatedIls * 100) / 100,
            customsDuties: 0,
            portFees: 0,
            internalShippingFees: 0,
            palestinianTaxCustoms: 0,
            includedInPrice: false,
        },
        ...(importLogistics ? { importLogistics } : {}),
        conversionMetadata: {
            dealEffectiveRate: impliedDealRate,
            shipmentEffectiveRate: impliedShipRate,
            internalShippingUsd,
            globalShippingUsd: distributedCostUsd,
            extraCostsUsd,
            totalUsd: deal.totalAmount,
            remainingBalanceRate: dealRemainingRate,
            dealPaidIls: Math.round(dealPaidIls * 100) / 100,
            dealUnpaidUsd: Math.round(dealUnpaidUsd * 100) / 100,
            dealTotalIls: Math.round(dealValIls * 100) / 100,
            shipmentPaidIls: Math.round(shipPaidIls * 100) / 100,
            shipmentUnpaidUsd: Math.round(shipUnpaidUsd * 100) / 100,
            shipmentTotalIls: Math.round(shipCostIlsForShare * 100) / 100,
            dealShareByDealsValue: Math.round(shareByDealsValue * 10000) / 10000,
            dealShareByVolume: Math.round(shareByVolume * 10000) / 10000,
            shipmentDealsTotalUsd: Math.round(totalDealsUsd * 100) / 100,
            dealShareOfShipment: Math.round(shareByVolume * 10000) / 10000,
            dealShipmentAllocatedIls: Math.round(dealShipAllocatedIls * 100) / 100,
            dealShareOfClearanceVolume: Math.round(shareByDealsValue * 10000) / 10000,
            dealClearanceAllocatedIls: Math.round(dealClearanceAllocatedIls * 100) / 100,
            dealThisTotalUsdForShare: Math.round(thisDealUsd * 100) / 100,
            clearancePaymentsTotalIls: Math.round(clearancePaidSumIls * 100) / 100,
            allocationMethod: "per_payment_and_share",
            dualShareAllocations: true,
            dealTransferCommissionsIls,
            dealTransferCommissionsFromDealPaymentsIls: dealXferFromPaymentsIls,
            shipmentTransferCommissionsTotalIls: shipXferTotalIls,
            dealTransferCommissionsFromShipmentShareIls: dealShareShipXferIls,
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
            supplierSnapshot: deal.supplierSnapshot as any,
        },
    };

    const afterDiscount = Math.max(0, subtotalIls - (invoice.discountAmount || 0));
    const shippingToInclude = invoice.shippingIncluded ? 0 : totalShippingCostIls;
    const taxableBase = afterDiscount + shippingToInclude;
    const lpPre = invoice.localPayments || {};
    const vatBaseIls = invoiceVatBaseIls(
        taxableBase,
        invoice.conversionMetadata as Record<string, unknown> | null,
        lpPre
    );

    let taxAmountIls = 0;
    if (invoice.taxType === "amount") {
        taxAmountIls =
            Math.round((Number(deal.taxAmount) || 0) * impliedDealRate * 100) / 100;
    } else {
        taxAmountIls = vatBaseIls * ((invoice.taxRate || 0) / 100);
    }

    invoice.taxAmount = Math.round(taxAmountIls * 100) / 100;

    const lp = invoice.localPayments || {};
    const mainVatForTotal = Number(invoice.taxAmount) || taxAmountIls;
    invoice.grandTotal =
        Math.round(
            invoiceGrandTotalIls(
                taxableBase,
                mainVatForTotal,
                invoice.conversionMetadata as Record<string, unknown> | null,
                lp
            ) * 100
        ) / 100;

    return invoice;
};

/** @deprecated استخدم dealTotalIlsFromActualPayments — مُبقى للتوافق */
export const calculateEffectiveRate = (
    totalAmountUsd: number,
    payments: (DealPayment | ShipmentPayment)[],
    remainingBalanceRate: number
): number => {
    if (totalAmountUsd <= 0) return remainingBalanceRate;
    const { paidUsd, paidIls } = sumSettledUsdIls(payments);
    const unpaidUsd = Math.max(0, totalAmountUsd - paidUsd);
    const totalIlsValue = paidIls + unpaidUsd * remainingBalanceRate;
    return totalIlsValue / totalAmountUsd;
};
