import React from "react";
import { Calculator, Wallet, CreditCard, Ship, TrendingDown, Percent } from "lucide-react";
import type { LocalPayments } from "@/types";
import {
    hasAfterMainVatPercentageLines,
    sumTaxesAndFeesExtras,
} from "@/utils/invoiceTaxesAndFees";
import { formatTaxPercentLabel } from "@/utils/sqlMoneyRound";
import { formatMoney } from "@/utils/formatNumber";

interface NISFinancialSummaryProps {
    subtotal: number;
    discountAmount: number;
    taxAmount: number;
    taxRate: number;
    shippingCost: number;
    grandTotal: number;
    localPayments?: LocalPayments | null;
    /** أساس نسب بنود الضرائب والرسوم */
    taxableBaseIls?: number;
    /** لبنود «بعد ض.ق.م» — مجموع ما قبل ض.ق.م الفاتورة (بضاعة + شحن دولي + تخليص + نقل) */
    invoiceVatBaseIls?: number;
    /** إخفاء سطر شحن الفاتورة (فواتير شيكل) */
    hideShippingRow?: boolean;
}

export const NISFinancialSummary: React.FC<NISFinancialSummaryProps> = ({
    subtotal,
    discountAmount,
    taxAmount,
    taxRate,
    shippingCost,
    grandTotal,
    localPayments,
    taxableBaseIls = 0,
    invoiceVatBaseIls,
    hideShippingRow,
}) => {
    const symbol = "₪";
    const lp = localPayments || {};
    const mainVatForExtras = Math.max(0, Number(taxAmount) || 0);
    const extrasTotal = sumTaxesAndFeesExtras(lp, taxableBaseIls, {
        mainVatIls: mainVatForExtras,
        invoiceVatBaseIls:
            invoiceVatBaseIls != null && Number.isFinite(invoiceVatBaseIls)
                ? Math.max(0, invoiceVatBaseIls)
                : undefined,
    });
    const hasLocalPayments =
        !lp.includedInPrice &&
        ((lp.customsClearanceFees || 0) +
            (lp.customsDuties || 0) +
            (lp.portFees || 0) +
            (lp.palestinianTaxCustoms || 0) >
            0);

    const localSum =
        (lp.customsClearanceFees || 0) +
        (lp.customsDuties || 0) +
        (lp.portFees || 0) +
        (lp.palestinianTaxCustoms || 0);

    return (
        <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl border aseel-border-soft dark:aseel-border-soft shadow-sm overflow-hidden">
            <div className="px-4 py-2.5 border-b aseel-border-soft dark:aseel-border-soft aseel-bg-panel/50 dark:aseel-bg-panel/50 flex items-center justify-between">
                <h3 className="text-sm font-bold aseel-text-ink dark:text-white flex items-center gap-2">
                    <Calculator className="w-4 h-4 aseel-text-soft" />
                    ملخص
                </h3>
                <span className="text-[10px] font-semibold aseel-text-soft">ILS</span>
            </div>

            <div className="p-4 space-y-2.5 text-sm">
                <div className="flex justify-between">
                    <span className="aseel-text-soft flex items-center gap-1.5 text-xs">
                        <CreditCard className="w-3.5 h-3.5" /> أساس البضاعة
                    </span>
                    <span className="font-bold tabular-nums">
                        {symbol}
                        {formatMoney(subtotal)}
                    </span>
                </div>

                {discountAmount > 0 && (
                    <div className="flex justify-between aseel-text-soft dark:aseel-text-soft text-xs">
                        <span className="flex items-center gap-1.5">
                            <TrendingDown className="w-3.5 h-3.5" /> خصم
                        </span>
                        <span className="font-bold tabular-nums">
                            -{symbol}
                            {formatMoney(discountAmount)}
                        </span>
                    </div>
                )}

                <div className="flex justify-between">
                    <span className="aseel-text-soft flex items-center gap-1.5 text-xs">
                        <Percent className="w-3.5 h-3.5" /> ض.ق.م ({formatTaxPercentLabel(taxRate)}%)
                    </span>
                    <span className="font-bold tabular-nums">
                        {symbol}
                        {formatMoney(taxAmount)}
                    </span>
                </div>

                {extrasTotal > 0 && (
                    <div className="flex justify-between text-xs gap-2">
                        <span className="aseel-text-soft">
                            رسوم وضرائب إضافية
                            {hasAfterMainVatPercentageLines(lp) ? (
                                <span className="block text-[9px] aseel-text-soft mt-0.5">
                                    (تشمل نسبة بعد ض.ق.م الفاتورة)
                                </span>
                            ) : null}
                        </span>
                        <span className="font-bold tabular-nums shrink-0">
                            {symbol}
                            {formatMoney(extrasTotal)}
                        </span>
                    </div>
                )}

                {!hideShippingRow && shippingCost > 0 && (
                    <div className="flex justify-between">
                        <span className="aseel-text-soft flex items-center gap-1.5 text-xs">
                            <Ship className="w-3.5 h-3.5" /> شحن
                        </span>
                        <span className="font-bold tabular-nums">
                            {symbol}
                            {formatMoney(shippingCost)}
                        </span>
                    </div>
                )}

                {hasLocalPayments && (
                    <div className="pt-2 border-t aseel-border-soft dark:aseel-border-soft space-y-1">
                        <div className="text-[10px] font-bold aseel-text-soft">تخليص</div>
                        <div className="grid grid-cols-1 gap-0.5 text-[10px]">
                            {lp.customsClearanceFees ? (
                                <div className="flex justify-between">
                                    <span className="aseel-text-soft">مخلص</span>
                                    <span className="font-mono font-bold">₪{lp.customsClearanceFees}</span>
                                </div>
                            ) : null}
                            {lp.customsDuties ? (
                                <div className="flex justify-between">
                                    <span className="aseel-text-soft">جمارك</span>
                                    <span className="font-mono font-bold">₪{lp.customsDuties}</span>
                                </div>
                            ) : null}
                            {lp.portFees ? (
                                <div className="flex justify-between">
                                    <span className="aseel-text-soft">ميناء</span>
                                    <span className="font-mono font-bold">₪{lp.portFees}</span>
                                </div>
                            ) : null}
                            {lp.palestinianTaxCustoms ? (
                                <div className="flex justify-between">
                                    <span className="aseel-text-soft">جمركة ضرائب</span>
                                    <span className="font-mono font-bold">₪{lp.palestinianTaxCustoms}</span>
                                </div>
                            ) : null}
                        </div>
                        <div className="flex justify-between text-[10px] font-bold aseel-text-ink dark:aseel-text-soft pt-1">
                            <span>مجموع التخليص</span>
                            <span className="tabular-nums">₪{localSum.toLocaleString()}</span>
                        </div>
                    </div>
                )}
            </div>

            <div className="p-4 pt-0">
                <div className="aseel-bg-panel p-3 rounded-lg">
                    <div className="flex justify-between items-center">
                        <div>
                            <span className="aseel-text-soft text-[10px] block">الإجمالي</span>
                            <div className="flex items-baseline gap-1 text-white">
                                <span className="text-2xl font-black tabular-nums">
                                    {formatMoney(grandTotal)}
                                </span>
                                <span className="text-sm font-bold opacity-80">{symbol}</span>
                            </div>
                        </div>
                        <div className="p-2 aseel-bg-field/20 rounded-lg">
                            <Wallet className="w-6 h-6 text-white" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
