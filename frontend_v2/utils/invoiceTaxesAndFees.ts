import type { LocalPayments, PurchaseInvoiceFeeLine, TaxesAndFeesLine } from "@/types";

type ConvMeta = Record<string, unknown> | null | undefined;

function num(v: unknown, fallback = 0): number {
    if (v === null || v === undefined || v === "") return fallback;
    const n = typeof v === "number" ? v : Number(v);
    return Number.isFinite(n) ? n : fallback;
}

export type InvoiceFinalCostItem = {
    quantity?: number | string | null;
    totalPrice?: number | string | null;
    landedLineTotalIls?: number | string | null;
};

export type InvoiceFinalCostAllocation = {
    share: number;
    landedBase: number;
    transferAllocation: number;
    taxAndFeesAllocation: number;
    preTaxLine: number;
    finalLine: number;
    finalUnit: number;
};

export function allocateInvoiceFinalCosts(
    items: InvoiceFinalCostItem[],
    pools: { transferTotalIls?: number; taxAndFeesTotalIls?: number },
): InvoiceFinalCostAllocation[] {
    const weights = items.map((item) => {
        const landed = num(item.landedLineTotalIls);
        if (landed > 0) return landed;
        return Math.max(0, num(item.totalPrice));
    });
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
    const transferTotal = Math.max(0, num(pools.transferTotalIls));
    const taxAndFeesTotal = Math.max(0, num(pools.taxAndFeesTotalIls));
    return items.map((item, index) => {
        const share = totalWeight > 0
            ? weights[index] / totalWeight
            : items.length > 0 ? 1 / items.length : 0;
        const landedBase = weights[index];
        const transferAllocation = transferTotal * share;
        const taxAndFeesAllocation = taxAndFeesTotal * share;
        const preTaxLine = landedBase + transferAllocation;
        const finalLine = preTaxLine + taxAndFeesAllocation;
        const quantity = Math.max(num(item.quantity), 0.0001);
        return {
            share,
            landedBase,
            transferAllocation,
            taxAndFeesAllocation,
            preTaxLine,
            finalLine,
            finalUnit: finalLine / quantity,
        };
    });
}

function lineMetaFrom(meta: ConvMeta): Record<string, unknown> {
    if (!meta || typeof meta !== "object") return {};
    const r = meta as Record<string, unknown>;
    const lm = r.line_meta;
    if (lm && typeof lm === "object" && !Array.isArray(lm)) return lm as Record<string, unknown>;
    return {};
}

function hasEmbeddedLandedAllocations(meta: ConvMeta): boolean {
    if (!meta || typeof meta !== "object") return false;
    const r = meta as Record<string, unknown>;
    return (r.allocation_method ?? r.allocationMethod) === "server_pro_rata";
}

export function purchaseInvoiceFeeAmount(
    fee: Pick<PurchaseInvoiceFeeLine, "amount" | "calculationType" | "calculationValue" | "percentageBasis">,
    goodsBaseIls: number,
    invoiceVatBaseIls: number,
    mainVatIls: number
): number {
    const calculationType = fee.calculationType || "amount";
    const value = Math.max(0, Number(fee.calculationValue ?? fee.amount) || 0);
    if (calculationType !== "percentage") return Math.round(value * 100) / 100;
    const basis = fee.percentageBasis === "after_main_vat"
        ? Math.max(0, invoiceVatBaseIls) + Math.max(0, mainVatIls)
        : Math.max(0, goodsBaseIls);
    return Math.round(((basis * value) / 100) * 100) / 100;
}

/** مخلص + جمارك + ميناء + جمركة ضرائب (بدون شحن محلي منفصل — يُدار مع metadata) */
export function clearanceStructuredFeesSubtotal(lp: LocalPayments | null | undefined): number {
    if (!lp || lp.includedInPrice) return 0;
    if (lp.calculationMethod === "lump_sum") return 0;
    return (
        (lp.customsClearanceFees || 0) +
        (lp.customsDuties || 0) +
        (lp.portFees || 0) +
        (lp.palestinianTaxCustoms || 0)
    );
}

/** حصة الشحن الدولي بالشيكل (من landed / إعادة حساب التكلفة) */
export function internationalFreightIlsForVat(meta: ConvMeta): number {
    if (!meta) return 0;
    const r = meta as Record<string, unknown>;
    const lm = lineMetaFrom(meta);
    const v =
        r.dealShipmentAllocatedIls ??
        r.deal_shipment_allocated_ils ??
        lm.deal_ship_allocated_ils ??
        lm.dealShipAllocatedIls;
    return Math.max(0, num(v));
}

/** عمولات/تكاليف تحويل دفعات الصفقة المنفّذة (USD×سعر الدفعة) — من الخادم */
export function transferCommissionsIlsForVat(meta: ConvMeta): number {
    if (!meta) return 0;
    const r = meta as Record<string, unknown>;
    const lm = lineMetaFrom(meta);
    const v =
        r.dealTransferCommissionsIls ??
        r.deal_transfer_commissions_ils ??
        lm.deal_transfer_commissions_ils;
    return Math.max(0, num(v));
}

/** نقل محلي: من metadata إن وُجد، وإلا من المدفوعات المحلية */
export function localTransportIlsForVat(meta: ConvMeta, lp: LocalPayments | null | undefined): number {
    if (!meta) {
        if (!lp || lp.includedInPrice) return 0;
        return Math.max(0, num(lp.internalShippingFees));
    }
    const r = meta as Record<string, unknown>;
    const lm = lineMetaFrom(meta);
    const fromMeta = num(
        r.dealLocalShippingFromClearanceIls ??
            r.deal_local_shipping_from_clearance_ils ??
            lm.deal_local_shipping_from_clearance_ils ??
            lm.local_shipping_from_clearance_ils
    );
    if (fromMeta > 0) return fromMeta;
    if (!lp || lp.includedInPrice) return 0;
    return Math.max(0, num(lp.internalShippingFees));
}

/**
 * أساس ض.ق.م الفاتورة: بضاعة + شحن دولي + تخليص (مخلص/جمارك/ميناء/جمركة) + نقل محلي
 * + عمولات تحويل دفعات الصفقة (كل ما قبل ض.ق.م الفاتورة وبنود النسب الإضافية مثل كترا)
 */
export function invoiceVatBaseIls(
    merchandiseBase: number,
    meta: ConvMeta,
    lp: LocalPayments | null | undefined
): number {
    if (hasEmbeddedLandedAllocations(meta)) {
        return (
            Math.max(0, merchandiseBase) +
            transferCommissionsIlsForVat(meta)
        );
    }
    return (
        Math.max(0, merchandiseBase) +
        internationalFreightIlsForVat(meta) +
        transferCommissionsIlsForVat(meta) +
        clearanceStructuredFeesSubtotal(lp) +
        localTransportIlsForVat(meta, lp)
    );
}

/** مجموع تخليص + نقل محلي (بدون شحن دولي) — نقل واحد: metadata أو حقل النموذج */
export function clearanceAndLogisticsFeesForGrandTotal(
    lp: LocalPayments | null | undefined,
    meta?: ConvMeta
): number {
    if (!lp || lp.includedInPrice) return 0;
    if (lp.calculationMethod === "lump_sum") return lp.lumpSumAmount || 0;
    return clearanceStructuredFeesSubtotal(lp) + localTransportIlsForVat(meta, lp);
}

/**
 * إجمالي الفاتورة بالشيكل: أساس ض.ق.م كامل (بضاعة + شحن دولي + تخليص + نقل) + ض.ق.م + بنود إضافية.
 * lump_sum: يُضاف المبلغ الشامل + البنود الإضافية (بدون تفكيك لأساس ض.ق.م هنا).
 */
export function invoiceGrandTotalIls(
    merchandiseBase: number,
    mainVatIls: number,
    meta: ConvMeta,
    lp: LocalPayments | null | undefined
): number {
    const mb = Math.max(0, merchandiseBase);
    const vatAmt = Math.max(0, Number(mainVatIls) || 0);
    const vatBase = invoiceVatBaseIls(mb, meta, lp);
    const extras = sumTaxesAndFeesExtras(lp, mb, {
        mainVatIls: vatAmt,
        invoiceVatBaseIls: vatBase,
    });
    if (!lp || lp.includedInPrice) {
        return mb + vatAmt + extras;
    }
    if (lp.calculationMethod === "lump_sum") {
        const lump = Math.max(0, Number(lp.lumpSumAmount) || 0);
        return mb + vatAmt + lump + extras;
    }
    return vatBase + vatAmt + extras;
}

/** مبالغ تخليص/شحن محلي (للتوافق) — مخلص + جمارك + ميناء + شحن محلي من النموذج + جمركة */
export function clearanceAndLogisticsFeesSubtotal(
    lp: LocalPayments | null | undefined
): number {
    if (!lp || lp.includedInPrice) return 0;
    if (lp.calculationMethod === "lump_sum") return 0;
    return clearanceStructuredFeesSubtotal(lp) + Math.max(0, num(lp.internalShippingFees));
}

export type TaxExtrasContext = {
    /** مبلغ ض.ق.م الفاتورة الرئيسي (بعد حسابه من النسبة أو المبلغ الثابت) — لأساس after_main_vat */
    mainVatIls?: number;
    /**
     * مجموع ما قبل ض.ق.م الفاتورة (بضاعة + شحن دولي + تخليص + نقل…).
     * لأساس «بعد ض.ق.م»: (هذا + mainVatIls). إن لم يُمرَّر يُستخدم أساس البضاعة فقط (سلوك قديم).
     */
    invoiceVatBaseIls?: number;
};

function percentageBasisForRow(row: TaxesAndFeesLine): "goods" | "after_main_vat" {
    return row.percentageBasis === "after_main_vat" ? "after_main_vat" : "goods";
}

/** مبلغ السطر بالشيكل: قيمة أو نسبة من الأساس (حسب percentageBasis) */
export function lineTaxFeeIls(
    row: TaxesAndFeesLine,
    taxableBaseIls: number,
    ctx?: TaxExtrasContext
): number {
    const n = Number(row.amount) || 0;
    if (row.entryType === "percentage") {
        const baseGoods = Math.max(0, taxableBaseIls);
        const mainVat = Math.max(0, Number(ctx?.mainVatIls) || 0);
        const preVatFull =
            ctx?.invoiceVatBaseIls != null && Number.isFinite(Number(ctx.invoiceVatBaseIls))
                ? Math.max(0, Number(ctx.invoiceVatBaseIls))
                : baseGoods;
        const basis =
            percentageBasisForRow(row) === "after_main_vat"
                ? preVatFull + mainVat
                : baseGoods;
        return (basis * n) / 100;
    }
    return n;
}

/** مجموع بنود «الضرائب والرسوم» الإضافية (مع دعم extraTaxesFees القديم) */
export function sumTaxesAndFeesExtras(
    lp: LocalPayments | null | undefined,
    taxableBaseIls = 0,
    ctx?: TaxExtrasContext
): number {
    if (!lp) return 0;
    const lines = lp.taxesAndFeesLines;
    if (lines && lines.length > 0) {
        return lines.reduce((s, row) => s + lineTaxFeeIls(row, taxableBaseIls, ctx), 0);
    }
    return Number(lp.extraTaxesFees) || 0;
}

/** هل يوجد سطر نسبة يُحسب بعد ض.ق.م الفاتورة؟ (للتلميح في الملخص) */
export function hasAfterMainVatPercentageLines(lp: LocalPayments | null | undefined): boolean {
    const lines = lp?.taxesAndFeesLines;
    if (!lines?.length) return false;
    return lines.some(
        (l) =>
            l.entryType === "percentage" && percentageBasisForRow(l) === "after_main_vat"
    );
}

/** عرض/تحرير: بنود من JSON أو صف واحد من القيمة القديمة */
export function effectiveTaxesAndFeesLines(lp: LocalPayments | null | undefined): TaxesAndFeesLine[] {
    if (!lp) return [];
    const raw = lp.taxesAndFeesLines;
    if (raw && raw.length > 0) {
        return raw.map((l, i) => ({
            id: l.id || `tf-${i}`,
            label: l.label == null ? "" : String(l.label),
            amount: Number(l.amount) || 0,
            entryType: l.entryType === "percentage" ? "percentage" : "amount",
            percentageBasis:
                l.percentageBasis === "after_main_vat" ? "after_main_vat" : "goods",
        }));
    }
    const legacy = Number(lp.extraTaxesFees) || 0;
    if (legacy > 0) {
        return [{ id: "legacy-extra", label: "رسوم إضافية", amount: legacy, entryType: "amount" }];
    }
    return [];
}
