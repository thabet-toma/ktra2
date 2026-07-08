import React from "react";
import { Calculator, Ship } from "lucide-react";
import type { Invoice, InvoiceImportLogistics } from "@/types";
import { formatInvoiceImportLogisticsLine } from "@/utils/invoiceConversionUtils";
import { formatNumber, formatMoney } from "@/utils/formatNumber";

type ConversionMetadata = NonNullable<Invoice["conversionMetadata"]>;

/** قيم JSON من الـ API قد تكون snake_case أو camelCase — نمنع undefined قبل .toFixed() */
function num(v: unknown, fallback = 0): number {
    if (v === null || v === undefined || v === "") return fallback;
    const n = typeof v === "number" ? v : Number(v);
    return Number.isFinite(n) ? n : fallback;
}

function optionalNum(v: unknown): number | undefined {
    if (v === null || v === undefined || v === "") return undefined;
    const n = typeof v === "number" ? v : Number(v);
    return Number.isFinite(n) ? n : undefined;
}

/** يدمج بيانات الاستيراد من الخادم (server_pro_rata) مع الشكل القديم للواجهة */
function normalizeConversionMetadata(meta: ConversionMetadata): ConversionMetadata {
    const r = meta as Record<string, unknown>;
    const lineMeta =
        r.line_meta && typeof r.line_meta === "object" && !Array.isArray(r.line_meta)
            ? (r.line_meta as Record<string, unknown>)
            : {};

    return {
        ...meta,
        dealEffectiveRate: num(r.dealEffectiveRate ?? r.deal_effective_rate),
        shipmentEffectiveRate: num(r.shipmentEffectiveRate ?? r.shipment_effective_rate),
        internalShippingUsd: num(r.internalShippingUsd ?? r.internal_shipping_usd),
        globalShippingUsd: num(r.globalShippingUsd ?? r.global_shipping_usd),
        extraCostsUsd: num(r.extraCostsUsd ?? r.extra_costs_usd),
        totalUsd: num(r.totalUsd ?? r.total_usd),
        remainingBalanceRate: num(
            r.remainingBalanceRate ??
                r.remaining_balance_rate_deal ??
                r.remaining_balance_rate_shipment,
            3.6
        ),
        dealPaidIls: optionalNum(r.dealPaidIls ?? r.deal_paid_ils),
        dealUnpaidUsd: optionalNum(r.dealUnpaidUsd ?? r.deal_unpaid_usd),
        dealTotalIls: optionalNum(r.dealTotalIls ?? r.deal_total_ils),
        shipmentPaidIls: optionalNum(r.shipmentPaidIls ?? r.ship_paid_ils),
        shipmentUnpaidUsd: optionalNum(r.shipmentUnpaidUsd ?? r.ship_unpaid_usd),
        shipmentTotalIls: optionalNum(r.shipmentTotalIls ?? r.shipment_total_ils),
        dealShareByDealsValue: optionalNum(r.dealShareByDealsValue ?? r.deal_share_by_value),
        dealShareByVolume: optionalNum(r.dealShareByVolume ?? r.deal_share_by_volume),
        shipmentDealsTotalUsd: optionalNum(r.shipmentDealsTotalUsd ?? r.shipment_deals_total_usd),
        dealThisTotalUsdForShare: optionalNum(r.dealThisTotalUsdForShare ?? r.deal_this_total_usd_for_share),
        dealShareOfShipment: optionalNum(r.dealShareOfShipment ?? r.deal_share_of_shipment),
        dealShipmentAllocatedIls: optionalNum(
            r.dealShipmentAllocatedIls ??
                r.deal_shipment_allocated_ils ??
                lineMeta.deal_ship_allocated_ils
        ),
        dealShareOfClearanceVolume: optionalNum(
            r.dealShareOfClearanceVolume ?? r.deal_share_of_clearance_volume
        ),
        dealClearanceAllocatedIls: optionalNum(
            r.dealClearanceAllocatedIls ??
                r.deal_clearance_allocated_ils ??
                lineMeta.deal_clearance_allocated_ils
        ),
        clearancePaymentsTotalIls: optionalNum(
            r.clearancePaymentsTotalIls ?? r.clearance_payments_total_ils
        ),
        clearancePoolIls: optionalNum(r.clearancePoolIls ?? r.clearance_pool_ils),
        clearanceCostBasis: String(r.clearanceCostBasis ?? r.clearance_cost_basis ?? "").trim(),
        costLinesTotalIls: optionalNum(r.costLinesTotalIls ?? r.cost_lines_total_ils),
        dealLocalShippingFromClearanceIls: optionalNum(
            r.dealLocalShippingFromClearanceIls ??
                r.deal_local_shipping_from_clearance_ils ??
                lineMeta.local_shipping_from_clearance_ils
        ),
        clearanceLocalShippingLinesTotalIls: optionalNum(
            r.clearanceLocalShippingLinesTotalIls ?? r.clearance_local_shipping_lines_total_ils
        ),
        dealTransferCommissionsIls: optionalNum(
            r.dealTransferCommissionsIls ??
                r.deal_transfer_commissions_ils ??
                lineMeta.deal_transfer_commissions_ils
        ),
        dealTransferCommissionsFromDealPaymentsIls: optionalNum(
            r.dealTransferCommissionsFromDealPaymentsIls ??
                r.deal_transfer_commissions_from_deal_payments_ils ??
                lineMeta.deal_transfer_commissions_from_deal_payments_ils
        ),
        shipmentTransferCommissionsTotalIls: optionalNum(
            r.shipmentTransferCommissionsTotalIls ??
                r.shipment_transfer_commissions_total_ils ??
                lineMeta.shipment_transfer_commissions_total_ils
        ),
        dealTransferCommissionsFromShipmentShareIls: optionalNum(
            r.dealTransferCommissionsFromShipmentShareIls ??
                r.deal_transfer_commissions_from_shipment_share_ils ??
                lineMeta.deal_transfer_commissions_from_shipment_share_ils
        ),
        allocationMethod: String(r.allocationMethod ?? r.allocation_method ?? ""),
    };
}

interface ConversionDetailsSectionProps {
    metadata?: ConversionMetadata;
    importLogistics?: InvoiceImportLogistics | null;
    /** من الفاتورة: الشحن المحلي مضمّن بسعر البضاعة — لا يُعرض كمبلغ منفصل في التوزيع */
    shippingIncluded?: boolean;
    /** حقل شحن الفاتورة بالشيكل — يُستخدم لعرض حصة النقل من التخليص إن كانت metadata قديمة */
    invoiceShippingCostIls?: number;
    /** ربط الفاتورة بالتخليص — لعرض رسالة قصيرة عند غياب حصة النقل في metadata */
    invoiceClearanceId?: string | number | null;
}

/** نسبة تقدير الشحن الداخلي (USD) من إجمالي قيمة الصفقة بالدولار — تُقارَب بما يُحوَّل لشيكل للصفقة */
function internalShippingPctOfDealUsd(internalShippingUsd: number, dealTotalUsd: number): number | undefined {
    if (dealTotalUsd <= 0 || internalShippingUsd <= 0) return undefined;
    return (internalShippingUsd / dealTotalUsd) * 100;
}

export const ConversionDetailsSection: React.FC<ConversionDetailsSectionProps> = ({
    metadata,
    importLogistics,
    shippingIncluded = false,
    invoiceShippingCostIls,
    invoiceClearanceId,
}) => {
    if (!metadata && !importLogistics) return null;

    if (!metadata) {
        return (
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl border border-[var(--color-border)] dark:border-[var(--color-border)]/30 overflow-hidden shadow-sm p-4">
                <div className="flex items-start gap-3 text-sm text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                    <Ship className="w-5 h-5 shrink-0 text-[var(--color-primary)]" />
                    <div>
                        <p className="font-bold">مصدر الاستيراد</p>
                        <p className="text-[var(--color-primary)]/90 dark:text-[var(--color-primary)]/90 mt-1">
                            {formatInvoiceImportLogisticsLine(importLogistics!)}
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    const meta = normalizeConversionMetadata(metadata);
    const {
        internalShippingUsd,
        totalUsd,
        dealShareByDealsValue,
        dealShareByVolume,
        dealShareOfShipment,
        dealShareOfClearanceVolume,
        dealShipmentAllocatedIls,
        dealClearanceAllocatedIls,
        dealLocalShippingFromClearanceIls,
        dealTransferCommissionsIls,
        dealTransferCommissionsFromDealPaymentsIls,
        shipmentTransferCommissionsTotalIls,
        dealTransferCommissionsFromShipmentShareIls,
        allocationMethod,
    } = meta;

    const rawMeta = metadata as Record<string, unknown>;
    const dualShareAllocations = Boolean(
        rawMeta.dual_share_allocations ?? rawMeta.dualShareAllocations
    );
    const lineMetaRaw = rawMeta.line_meta;
    const lineMeta =
        lineMetaRaw && typeof lineMetaRaw === "object" && !Array.isArray(lineMetaRaw)
            ? (lineMetaRaw as Record<string, unknown>)
            : {};
    const internalShippingIls = optionalNum(lineMeta.internal_shipping_ils);
    const subtotalMerchIls = optionalNum(lineMeta.subtotal_merch_ils);

    const clearanceIdRaw =
        rawMeta.clearance_id ??
        rawMeta.clearanceId ??
        importLogistics?.clearanceId ??
        invoiceClearanceId;
    const clearanceLinked =
        clearanceIdRaw != null &&
        clearanceIdRaw !== "" &&
        Number.isFinite(Number(clearanceIdRaw)) &&
        Number(clearanceIdRaw) > 0;

    /** إن لم تُحدَّث metadata بعد، نُظهر حصة النقل من التخليص من فرق «شحن الفاتورة» − دولي − تقدير الصفقة */
    const metaLocalClr = dealLocalShippingFromClearanceIls ?? 0;
    const shipField = optionalNum(invoiceShippingCostIls);
    const intlPart = dealShipmentAllocatedIls ?? 0;
    const intDealPart = shippingIncluded ? 0 : internalShippingIls ?? 0;
    const impliedLocalFromClearanceIls =
        metaLocalClr > 0.005 || shipField == null || !Number.isFinite(shipField)
            ? 0
            : Math.max(0, Number((shipField - intlPart - intDealPart).toFixed(2)));
    const effectiveLocalFromClearanceIls =
        metaLocalClr > 0.005 ? metaLocalClr : impliedLocalFromClearanceIls;
    const localFromInvoiceImplied = metaLocalClr <= 0.005 && impliedLocalFromClearanceIls > 0.005;

    const serverProRata = allocationMethod === "server_pro_rata";
    /** نسبة قيمة الصفقة من صفقات الشحنة — تخليص ونقل من التخليص */
    const clearanceValueSharePct = (dealShareByDealsValue ?? dealShareOfClearanceVolume ?? 0) * 100;
    /** نسبة حجم/وزن الصفقة من الشحنة — شحن دولي (بعد dual_share_allocations) */
    const freightVolumeSharePct = dualShareAllocations
        ? (dealShareByVolume ?? dealShareOfShipment ?? 0) * 100
        : clearanceValueSharePct;

    const hasIlsLogisticsBreakdown =
        serverProRata &&
        ((subtotalMerchIls ?? 0) > 0 ||
            (internalShippingIls ?? 0) > 0 ||
            effectiveLocalFromClearanceIls > 0 ||
            (dealShipmentAllocatedIls ?? 0) > 0 ||
            (dealClearanceAllocatedIls ?? 0) > 0 ||
            (dealTransferCommissionsIls ?? 0) > 0);

    const fmtIls = (v: number | undefined) =>
        v != null && Number.isFinite(v) && v > 0
            ? `₪${formatMoney(v)}`
            : "—";

    const fmtIlsZero = (v: number | undefined) => {
        if (v == null || !Number.isFinite(v)) return "—";
        return `₪${formatMoney(v)}`;
    };

    const internalShippingMoney = () => {
        const ils = internalShippingIls ?? 0;
        const localClr = effectiveLocalFromClearanceIls;
        const totalLocal = ils + localClr;

        if (shippingIncluded) {
            return (
                <div className="space-y-1">
                    {localClr > 0 ? (
                        <div>
                            <div className="text-sm font-black aseel-text-accent dark:aseel-text-soft">
                                {fmtIlsZero(localClr)}
                            </div>
                            {localFromInvoiceImplied ? (
                                <span className="text-[9px] aseel-text-soft dark:aseel-text-soft block">
                                    مُستنتج من إجمالي شحن الفاتورة — يُفضَّل «إعادة حساب التكلفة» لمزامنة البيانات
                                </span>
                            ) : (
                                <span className="text-[9px] aseel-text-soft dark:aseel-text-soft block">
                                    من بنود التخليص (نقل / شحن محلي أو دفعة الناقل)
                                </span>
                            )}
                        </div>
                    ) : null}
                    {ils > 0 ? (
                        <div>
                            <div className="text-sm font-black aseel-text-accent dark:aseel-text-soft">
                                {fmtIlsZero(ils)}
                            </div>
                            <span className="text-[10px] aseel-text-soft dark:aseel-text-soft">
                                تقدير من الصفقة — مضمّن بسعر البضاعة
                            </span>
                        </div>
                    ) : null}
                    {totalLocal === 0 ? (
                        <span className="text-xs aseel-text-soft dark:aseel-text-soft">
                            {clearanceLinked
                                ? "لا مبلغ نقل من التخليص في البيانات المحفوظة — «إعادة حساب التكلفة»."
                                : "—"}
                        </span>
                    ) : null}
                </div>
            );
        }
        if (totalLocal > 0) {
            return (
                <div className="space-y-0.5">
                    <span className="text-sm font-black aseel-text-accent dark:aseel-text-soft">
                        {fmtIlsZero(totalLocal)}
                    </span>
                    {localClr > 0 && ils > 0 ? (
                        <span className="text-[9px] aseel-text-soft dark:aseel-text-soft block">
                            من الصفقة {fmtIlsZero(ils)} + من التخليص {fmtIlsZero(localClr)}
                        </span>
                    ) : localClr > 0 ? (
                        <span className="text-[9px] aseel-text-soft dark:aseel-text-soft block">
                            {localFromInvoiceImplied
                                ? "من التخليص (مُستنتج من شحن الفاتورة — يُفضَّل إعادة الحساب)"
                                : "من التخليص (نقل / شحن محلي أو دفعة الناقل)"}
                        </span>
                    ) : null}
                </div>
            );
        }
        if (internalShippingUsd > 0) {
            return (
                <span className="text-xs aseel-text-soft dark:aseel-text-soft">
                    {fmtIlsZero(ils)} — تقدير الشحن المحلي من الصفقة
                </span>
            );
        }
        return (
            <span className="text-xs aseel-text-soft dark:aseel-text-soft">
                {clearanceLinked
                    ? "لا مبلغ نقل من التخليص في البيانات المحفوظة — «إعادة حساب التكلفة»."
                    : "—"}
            </span>
        );
    };

    const localClrForFooter = effectiveLocalFromClearanceIls;
    const totalFreightIlsForInvoice =
        (shippingIncluded ? 0 : (internalShippingIls ?? 0)) +
        (dealShipmentAllocatedIls ?? 0) +
        localClrForFooter;

    const internalPctOfDeal = internalShippingPctOfDealUsd(internalShippingUsd, totalUsd);

    const sharePctLabel = (pct: number, suffix: string) =>
        pct > 0 ? (
            <span className="block text-[9px] font-semibold aseel-text-soft dark:aseel-text-soft mt-0.5 tabular-nums">
                {formatNumber(pct, { maxDecimals: 2 })}% {suffix}
            </span>
        ) : (
            <span className="block text-[9px] aseel-text-soft dark:aseel-text-soft mt-0.5">—</span>
        );

    const internalPctLabel = () => {
        if (internalPctOfDeal != null && internalPctOfDeal > 0) {
            return (
                <span className="block text-[9px] font-semibold aseel-text-soft dark:aseel-text-soft mt-0.5 tabular-nums">
                    {formatNumber(internalPctOfDeal, { maxDecimals: 2 })}% من إجمالي الصفقة ($)
                </span>
            );
        }
        if ((internalShippingIls ?? 0) > 0) {
            return (
                <span className="block text-[9px] aseel-text-soft dark:aseel-text-soft mt-0.5">
                    تقدير بالشيكل (بدون نسبة $)
                </span>
            );
        }
        return <span className="block text-[9px] aseel-text-soft dark:aseel-text-soft mt-0.5">—</span>;
    };

    if (hasIlsLogisticsBreakdown) {
        return (
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl border aseel-border-soft dark:aseel-border-soft shadow-sm p-3 space-y-3">
                <h4 className="flex items-center gap-2 text-sm font-bold aseel-text-ink dark:aseel-text-soft">
                    <Calculator className="w-4 h-4 aseel-text-soft shrink-0" />
                    توزيع التكلفة (شيكل) — أساس أعمدة التكلفة النهائية
                </h4>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
                    <div className="p-3 aseel-bg-panel dark:aseel-bg-panel/80 border aseel-border-soft dark:aseel-border-soft rounded-lg">
                        <span className="text-[10px] aseel-text-soft dark:aseel-text-soft block mb-1">
                            بضاعة (أساس الجدول)
                        </span>
                        <div className="text-sm font-black aseel-text-ink dark:text-white">
                            {fmtIls(subtotalMerchIls)}
                        </div>
                    </div>
                    <div className="p-3 aseel-bg-panel dark:aseel-bg-panel/80 border aseel-border-soft dark:aseel-border-soft rounded-lg">
                        <span className="text-[10px] aseel-text-soft dark:aseel-text-soft block mb-1">
                            حصة شحن دولي للصفقة
                        </span>
                        {sharePctLabel(
                            freightVolumeSharePct,
                            dualShareAllocations
                                ? "من حجم/وزن الصفقة على الشحنة"
                                : "من تكلفة الشحنة (شيكل)"
                        )}
                        <div className="text-sm font-black text-[var(--color-primary)] dark:text-[var(--color-primary)] mt-0.5">
                            {fmtIls(dealShipmentAllocatedIls)}
                        </div>
                    </div>
                    <div className="p-3 aseel-bg-panel dark:aseel-bg-panel/80 border aseel-border-soft dark:aseel-border-soft rounded-lg">
                        <span className="text-[10px] aseel-text-soft dark:aseel-text-soft block mb-1">
                            نقل من التخليص (حصة الصفقة)
                        </span>
                        {internalPctLabel()}
                        <div className="mt-0.5">{internalShippingMoney()}</div>
                    </div>
                    <div className="p-3 aseel-bg-panel dark:aseel-bg-panel/80 border aseel-border-soft dark:aseel-border-soft rounded-lg">
                        <span className="text-[10px] aseel-text-soft dark:aseel-text-soft block mb-1">
                            حصة تخليص للصفقة
                        </span>
                        {sharePctLabel(
                            clearanceValueSharePct,
                            "من إجمالي الصفقات (بنود+ضريبة…) / مجموع صفقات الشحنة — مطابق لقائمة الصفقات"
                        )}
                        <div className="text-sm font-black aseel-text-ink dark:aseel-text-soft mt-0.5">
                            {fmtIls(dealClearanceAllocatedIls)}
                        </div>
                    </div>
                    <div className="p-3 aseel-bg-panel/80 dark:aseel-bg-panel/20 border aseel-border-soft/80 dark:aseel-border-soft/50 rounded-lg">
                        <span className="text-[10px] aseel-text-ink/90 dark:aseel-text-soft/90 block mb-1">
                            عمولات تحويل (إجمالي للصفقة)
                        </span>
                        <span className="block text-[9px] aseel-text-ink/85 dark:aseel-text-soft/85 mb-0.5 leading-snug">
                            دفعات الصفقة + حصة من عمولات دفعات شحن الشحنة (بنفس نسبة الشحن الدولي)
                        </span>
                        <div className="text-sm font-black aseel-text-ink dark:aseel-text-soft mt-0.5">
                            {fmtIlsZero(dealTransferCommissionsIls)}
                        </div>
                        {(dealTransferCommissionsFromDealPaymentsIls ?? 0) > 0.005 ||
                        (dealTransferCommissionsFromShipmentShareIls ?? 0) > 0.005 ? (
                            <div className="mt-1.5 space-y-0.5 text-[9px] aseel-text-ink/80 dark:aseel-text-soft/80 tabular-nums">
                                {(dealTransferCommissionsFromDealPaymentsIls ?? 0) > 0.005 ? (
                                    <div>
                                        من دفعات الصفقة: {fmtIlsZero(dealTransferCommissionsFromDealPaymentsIls)}
                                    </div>
                                ) : null}
                                {(shipmentTransferCommissionsTotalIls ?? 0) > 0.005 ? (
                                    <div className="aseel-text-ink/75 dark:aseel-text-soft/75">
                                        إجمالي شحن الشحنة: {fmtIlsZero(shipmentTransferCommissionsTotalIls)} → حصة
                                        الصفقة: {fmtIlsZero(dealTransferCommissionsFromShipmentShareIls)}
                                    </div>
                                ) : (dealTransferCommissionsFromShipmentShareIls ?? 0) > 0.005 ? (
                                    <div>
                                        حصة من شحن الشحنة: {fmtIlsZero(dealTransferCommissionsFromShipmentShareIls)}
                                    </div>
                                ) : null}
                            </div>
                        ) : null}
                    </div>
                </div>

                {totalFreightIlsForInvoice > 0 ? (
                    <div className="text-[11px] aseel-text-soft dark:aseel-text-soft rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-panel/80 dark:aseel-bg-panel/40 px-3 py-2">
                        <span className="font-bold aseel-text-ink dark:aseel-text-soft">
                            إجمالي شحن الفاتورة (تقريباً):
                        </span>{" "}
                        <span className="font-mono font-bold">
                            ₪
                            {totalFreightIlsForInvoice.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                            })}
                        </span>
                    </div>
                ) : null}
            </div>
        );
    }

    if (importLogistics) {
        return (
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl border border-[var(--color-border)] dark:border-[var(--color-border)]/30 shadow-sm p-3">
                <div className="flex items-start gap-2 text-xs text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                    <Ship className="w-4 h-4 shrink-0 text-[var(--color-primary)] mt-0.5" />
                    <p className="leading-relaxed">{formatInvoiceImportLogisticsLine(importLogistics)}</p>
                </div>
            </div>
        );
    }

    return null;
};
