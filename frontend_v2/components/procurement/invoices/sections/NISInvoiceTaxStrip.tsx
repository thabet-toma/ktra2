import React, { useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { PurchaseInvoiceFeeLine } from "@/types";
import { formatMoney, formatNumber } from "@/utils/formatNumber";
import { purchaseInvoiceFeeAmount } from "@/utils/invoiceTaxesAndFees";
import { normalizeTaxRatePercent, roundSqlMoney2 } from "@/utils/sqlMoneyRound";

interface FeeAccountOption {
    id: number;
    code?: string;
    name?: string;
}

interface NISInvoiceTaxStripProps {
    taxType?: "percentage" | "amount";
    taxRate: number;
    taxAmount: number;
    taxableBaseIls: number;
    vatBaseIls?: number;
    fees: PurchaseInvoiceFeeLine[];
    defaultFeeAccount?: FeeAccountOption | null;
    readOnly?: boolean;
    onFinancial: (field: string, value: unknown) => void;
    onFeesChange: (fees: PurchaseInvoiceFeeLine[]) => void;
}

type Draft = {
    label: string;
    calculationType: "amount" | "percentage";
    calculationValue: number;
    percentageBasis: "goods" | "after_main_vat";
};

const emptyDraft = (): Draft => ({
    label: "",
    calculationType: "amount",
    calculationValue: 0,
    percentageBasis: "goods",
});

const cellIn =
    "h-7 w-full min-w-0 rounded border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel px-1.5 text-[11px] leading-none";

export const NISInvoiceTaxStrip: React.FC<NISInvoiceTaxStripProps> = ({
    taxType = "percentage",
    taxRate,
    taxAmount,
    taxableBaseIls,
    vatBaseIls,
    fees,
    defaultFeeAccount,
    readOnly,
    onFinancial,
    onFeesChange,
}) => {
    const basisForInvoiceVat = vatBaseIls ?? taxableBaseIls;
    const [draft, setDraft] = useState<Draft>(() => emptyDraft());

    const mainVatIls = useMemo(() => {
        if (taxType === "amount") return Math.max(0, Number(taxAmount) || 0);
        return roundSqlMoney2(
            Math.max(0, basisForInvoiceVat) * (normalizeTaxRatePercent(taxRate) / 100)
        );
    }, [taxType, taxAmount, basisForInvoiceVat, taxRate]);

    const withResolvedAmount = (fee: PurchaseInvoiceFeeLine): PurchaseInvoiceFeeLine => ({
        ...fee,
        amount: purchaseInvoiceFeeAmount(
            fee,
            taxableBaseIls,
            basisForInvoiceVat,
            mainVatIls
        ),
    });

    const updateFee = (index: number, patch: Partial<PurchaseInvoiceFeeLine>) => {
        onFeesChange(fees.map((fee, i) => (
            i === index ? withResolvedAmount({ ...fee, ...patch }) : fee
        )));
    };

    const removeFee = (index: number) => {
        onFeesChange(fees.filter((_, i) => i !== index));
    };

    const draftFee = withResolvedAmount({
        description: draft.label,
        amount: 0,
        calculationType: draft.calculationType,
        calculationValue: draft.calculationValue,
        percentageBasis: draft.percentageBasis,
        expenseAccountId: defaultFeeAccount?.id || null,
        expenseAccountCode: defaultFeeAccount?.code,
        expenseAccountName: defaultFeeAccount?.name,
        capitalizeToInventory: false,
        isTaxable: false,
    });

    const commitDraft = () => {
        if (!defaultFeeAccount || draft.calculationValue <= 0) return;
        onFeesChange([
            ...fees,
            { ...draftFee, id: crypto.randomUUID(), description: draft.label.trim() || "رسم إضافي" },
        ]);
        setDraft(emptyDraft());
    };

    const feesTotal = fees.reduce((sum, fee) => sum + (Number(fee.amount) || 0), 0);

    return (
        <div className="rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel overflow-hidden text-[11px]">
            <div className="px-2 py-1 border-b aseel-border-soft dark:aseel-border-soft aseel-bg-panel/90 dark:aseel-bg-panel/90">
                <h3 className="text-right font-bold aseel-text-ink dark:aseel-text-soft text-xs">
                    ضريبة القيمة المضافة والرسوم
                </h3>
                <p className="text-right text-[9px] aseel-text-soft dark:aseel-text-soft mt-0.5">
                    أضف الرسم هنا كمبلغ أو نسبة، واختر إن كانت النسبة على البضاعة أو بعد ضريبة القيمة المضافة. يُحفظ السطر مع الفاتورة.
                </p>
            </div>

            <div className="px-1 py-0.5 overflow-x-auto">
                <table className="w-full border-collapse min-w-[520px]">
                    <thead>
                        <tr className="text-[9px] font-bold aseel-text-soft dark:aseel-text-soft border-b aseel-border-soft dark:aseel-border-soft">
                            <th className="py-1 px-1 text-right w-[28%]">الاسم</th>
                            <th className="py-1 px-1 text-center w-[12%]">النوع</th>
                            <th className="py-1 px-1 text-center w-[18%]">أساس النسبة</th>
                            <th className="py-1 px-1 text-center w-[14%]">قيمة / %</th>
                            <th className="py-1 px-1 text-center w-[20%]">₪ للفاتورة</th>
                            <th className="w-10 py-1 px-0 text-center"> </th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        <tr className="align-middle aseel-bg-panel/50 dark:aseel-bg-panel/25">
                            <td className="py-0.5 px-1 font-bold aseel-text-ink dark:aseel-text-soft">
                                بند القيمة المضافة
                            </td>
                            <td className="py-0.5 px-1">
                                <select
                                    value={taxType}
                                    disabled={readOnly}
                                    onChange={(e) => onFinancial("taxType", e.target.value)}
                                    className={cellIn + " text-center text-[10px]"}
                                >
                                    <option value="percentage">%</option>
                                    <option value="amount">₪</option>
                                </select>
                            </td>
                            <td className="py-0.5 px-1 text-center text-[9px] aseel-text-ink dark:aseel-text-soft">
                                أساس الفاتورة
                            </td>
                            <td className="py-0.5 px-1">
                                <input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    disabled={readOnly}
                                    value={taxType === "percentage" ? taxRate || "" : taxAmount || ""}
                                    onChange={(e) => onFinancial(
                                        taxType === "percentage" ? "taxRate" : "taxAmount",
                                        parseFloat(e.target.value) || 0
                                    )}
                                    className={cellIn + " text-center font-semibold tabular-nums"}
                                />
                            </td>
                            <td className="py-0.5 px-1 text-center font-black aseel-text-ink dark:aseel-text-soft tabular-nums">
                                ₪{formatNumber(mainVatIls, { maxDecimals: 3, group: true })}
                            </td>
                            <td className="py-0.5 px-0 text-center text-[9px] aseel-text-ink dark:aseel-text-soft">
                                {taxType === "percentage" ? "محسوبة" : "—"}
                            </td>
                        </tr>

                        {fees.map((fee, index) => {
                            const calculationType = fee.calculationType || "amount";
                            const isPercentage = calculationType === "percentage";
                            return (
                                <tr key={fee.id || index} className="align-middle hover:aseel-bg-panel/60 dark:hover:aseel-bg-panel/40">
                                    <td className="py-0.5 px-1">
                                        <input
                                            type="text"
                                            disabled={readOnly}
                                            value={fee.description}
                                            onChange={(e) => updateFee(index, { description: e.target.value })}
                                            className={cellIn}
                                        />
                                    </td>
                                    <td className="py-0.5 px-1">
                                        <select
                                            value={calculationType}
                                            disabled={readOnly}
                                            onChange={(e) => updateFee(index, {
                                                calculationType: e.target.value === "percentage" ? "percentage" : "amount",
                                            })}
                                            className={cellIn + " text-center"}
                                        >
                                            <option value="amount">₪</option>
                                            <option value="percentage">%</option>
                                        </select>
                                    </td>
                                    <td className="py-0.5 px-1">
                                        {isPercentage ? (
                                            <select
                                                value={fee.percentageBasis || "goods"}
                                                disabled={readOnly}
                                                onChange={(e) => updateFee(index, {
                                                    percentageBasis: e.target.value === "after_main_vat" ? "after_main_vat" : "goods",
                                                })}
                                                className={cellIn + " text-center text-[10px]"}
                                            >
                                                <option value="goods">على البضاعة</option>
                                                <option value="after_main_vat">بعد الضريبة</option>
                                            </select>
                                        ) : <span className="aseel-text-soft text-center block">—</span>}
                                    </td>
                                    <td className="py-0.5 px-1">
                                        <input
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            disabled={readOnly}
                                            value={(fee.calculationValue ?? fee.amount) || ""}
                                            onChange={(e) => updateFee(index, {
                                                calculationValue: parseFloat(e.target.value) || 0,
                                            })}
                                            className={cellIn + " text-center font-semibold tabular-nums"}
                                        />
                                    </td>
                                    <td className="py-0.5 px-1 text-center font-bold text-[var(--color-primary)] tabular-nums">
                                        ₪{formatMoney(fee.amount)}
                                    </td>
                                    <td className="py-0.5 px-0 text-center">
                                        {!readOnly && (
                                            <button type="button" title="حذف" onClick={() => removeFee(index)} className="p-0.5 aseel-text-soft rounded">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}

                        {!readOnly && (
                            <tr className="align-middle bg-[var(--color-surface-2)]/40 border-t border-dashed border-[var(--color-border)]">
                                <td className="py-0.5 px-1">
                                    <input type="text" value={draft.label} onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))} placeholder="اسم الرسم / الضريبة" className={cellIn} />
                                </td>
                                <td className="py-0.5 px-1">
                                    <select value={draft.calculationType} onChange={(e) => setDraft((d) => ({ ...d, calculationType: e.target.value === "percentage" ? "percentage" : "amount" }))} className={cellIn + " text-center"}>
                                        <option value="amount">₪</option>
                                        <option value="percentage">%</option>
                                    </select>
                                </td>
                                <td className="py-0.5 px-1">
                                    {draft.calculationType === "percentage" ? (
                                        <select value={draft.percentageBasis} onChange={(e) => setDraft((d) => ({ ...d, percentageBasis: e.target.value === "after_main_vat" ? "after_main_vat" : "goods" }))} className={cellIn + " text-center text-[10px]"}>
                                            <option value="goods">على البضاعة</option>
                                            <option value="after_main_vat">بعد الضريبة</option>
                                        </select>
                                    ) : <span className="aseel-text-soft text-center block">—</span>}
                                </td>
                                <td className="py-0.5 px-1">
                                    <input type="number" step="0.01" min="0" value={draft.calculationValue || ""} onChange={(e) => setDraft((d) => ({ ...d, calculationValue: parseFloat(e.target.value) || 0 }))} className={cellIn + " text-center tabular-nums"} />
                                </td>
                                <td className="py-0.5 px-1 text-center font-semibold text-[var(--color-primary)] tabular-nums">
                                    ₪{formatMoney(draftFee.amount)}
                                </td>
                                <td className="py-0.5 px-0.5 text-center">
                                    <button type="button" disabled={!defaultFeeAccount || draft.calculationValue <= 0} onClick={commitDraft} className="inline-flex items-center gap-0.5 rounded bg-[var(--color-primary)] px-1.5 py-0.5 text-[9px] font-bold text-white disabled:opacity-40" title={defaultFeeAccount ? "إضافة الرسم" : "لا يوجد حساب رسوم متاح"}>
                                        <Plus className="w-3 h-3" /> إضافة
                                    </button>
                                </td>
                            </tr>
                        )}
                    </tbody>
                    <tfoot>
                        <tr className="border-t aseel-border-soft aseel-bg-panel/70">
                            <td colSpan={4} className="py-1 px-1 text-[10px] font-bold text-right">مجموع الرسوم الإضافية</td>
                            <td className="py-1 px-1 text-center font-black tabular-nums">₪{formatMoney(feesTotal)}</td>
                            <td />
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
};
