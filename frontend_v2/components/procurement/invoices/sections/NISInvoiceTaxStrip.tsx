import React, { useMemo, useState, useCallback } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { LocalPayments, TaxesAndFeesLine } from "@/types";
import {
    effectiveTaxesAndFeesLines,
    hasAfterMainVatPercentageLines,
    lineTaxFeeIls,
    sumTaxesAndFeesExtras,
} from "@/utils/invoiceTaxesAndFees";
import { normalizeTaxRatePercent, roundSqlMoney2 } from "@/utils/sqlMoneyRound";

interface NISInvoiceTaxStripProps {
    taxType?: "percentage" | "amount";
    taxRate: number;
    taxAmount: number;
    localPayments: LocalPayments;
    /** أساس نسب بنود الرسوم الإضافية (البضاعة + شحن الفاتورة) */
    taxableBaseIls: number;
    /** أساس احتساب ض.ق.م الفاتورة (يشمل التخليص/الميناء… إن وُجدت) — إن لم يُمرَّر يُساوي taxableBaseIls */
    vatBaseIls?: number;
    readOnly?: boolean;
    onFinancial: (field: string, value: unknown) => void;
}

type Draft = {
    label: string;
    entryType: "amount" | "percentage";
    amount: number;
    percentageBasis: "goods" | "after_main_vat";
};

const emptyDraft = (): Draft => ({
    label: "",
    entryType: "amount",
    amount: 0,
    percentageBasis: "goods",
});

const cellIn =
    "h-7 w-full min-w-0 rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-1.5 text-[11px] leading-none";

export const NISInvoiceTaxStrip: React.FC<NISInvoiceTaxStripProps> = ({
    taxType = "percentage",
    taxRate,
    taxAmount,
    localPayments,
    taxableBaseIls,
    vatBaseIls,
    readOnly,
    onFinancial,
}) => {
    const basisForInvoiceVat = vatBaseIls ?? taxableBaseIls;
    const lp = localPayments || {};
    const lines = useMemo(() => effectiveTaxesAndFeesLines(lp), [lp]);
    const [draft, setDraft] = useState<Draft>(() => emptyDraft());

    const mainVatIls = useMemo(() => {
        if (taxType === "amount") return Math.max(0, Number(taxAmount) || 0);
        return roundSqlMoney2(
            Math.max(0, basisForInvoiceVat) * (normalizeTaxRatePercent(taxRate) / 100)
        );
    }, [taxType, taxAmount, basisForInvoiceVat, taxRate]);

    const extrasCtx = useMemo(
        () => ({
            mainVatIls,
            invoiceVatBaseIls: Math.max(0, basisForInvoiceVat),
        }),
        [mainVatIls, basisForInvoiceVat]
    );

    const pushLocalPayments = useCallback(
        (nextLines: TaxesAndFeesLine[]) => {
            onFinancial("localPayments", {
                ...lp,
                taxesAndFeesLines: nextLines,
                extraTaxesFees: 0,
            });
        },
        [lp, onFinancial]
    );

    const updateLine = (id: string, patch: Partial<TaxesAndFeesLine>) => {
        const next = lines.map((row) => (row.id === id ? { ...row, ...patch } : row));
        pushLocalPayments(next);
    };

    const removeLine = (id: string) => {
        pushLocalPayments(lines.filter((r) => r.id !== id));
    };

    const commitDraft = () => {
        const amt = Number(draft.amount) || 0;
        const lab = draft.label.trim();
        if (amt <= 0) return;
        const newL: TaxesAndFeesLine = {
            id: crypto.randomUUID(),
            label: lab,
            amount: amt,
            entryType: draft.entryType,
            percentageBasis:
                draft.entryType === "percentage" ? draft.percentageBasis : undefined,
        };
        pushLocalPayments([...lines, newL]);
        setDraft(emptyDraft());
    };

    const draftPreview = useMemo(
        () =>
            lineTaxFeeIls(
                {
                    id: "_draft",
                    label: draft.label,
                    amount: draft.amount,
                    entryType: draft.entryType,
                    percentageBasis:
                        draft.entryType === "percentage" ? draft.percentageBasis : undefined,
                },
                taxableBaseIls,
                extrasCtx
            ),
        [draft.label, draft.amount, draft.entryType, draft.percentageBasis, taxableBaseIls, extrasCtx]
    );

    const canCommitDraft = (Number(draft.amount) || 0) > 0;

    const extrasSum = useMemo(
        () => sumTaxesAndFeesExtras(lp, taxableBaseIls, extrasCtx),
        [lp, taxableBaseIls, extrasCtx]
    );

    return (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden text-[11px]">
            <div className="px-2 py-1 border-b border-gray-200 dark:border-gray-700 bg-gray-50/90 dark:bg-gray-900/90">
                <h3 className="text-right font-bold text-gray-800 dark:text-gray-100 text-xs">
                    بنود الضرائب والرسوم والقيمة المضافة
                </h3>
                <p className="text-right text-[9px] text-gray-500 dark:text-gray-400 mt-0.5">
                    الصف البنفسجي للإدخال المؤقت فقط — لن يُحفظ مع «حفظ الفاتورة» إلا بعد الضغط على «إضافة
                    للقائمة» (يُضاف السطر فوق ثم يُخزَّن مع الحفظ). لسطر نسبة: أساس «بعد ض.ق.م» = (مجموع قبل
                    ض.ق.م الفاتورة) + مبلغ ض.ق.م الفاتورة.
                </p>
            </div>

            <div className="px-1 py-0.5 overflow-x-auto">
                <table className="w-full border-collapse min-w-[520px]">
                    <thead>
                        <tr className="text-[9px] font-bold text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                            <th className="py-1 px-1 text-right w-[28%]">الاسم</th>
                            <th className="py-1 px-1 text-center w-[12%]">النوع</th>
                            <th className="py-1 px-1 text-center w-[18%]">أساس %</th>
                            <th className="py-1 px-1 text-center w-[14%]">قيمة / %</th>
                            <th
                                className="py-1 px-1 text-center w-[20%]"
                                title={`ض.ق.م الفاتورة ≈ ₪${mainVatIls.toFixed(2)} — أساس «بعد ض.ق.م» = مجموع قبل ض.ق.م + هذا المبلغ`}
                            >
                                ₪ للفاتورة
                            </th>
                            <th className="w-10 py-1 px-0 text-center"> </th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {/* صف ض.ق.م — ثابت، بنفس أعمدة الجدول */}
                        <tr className="align-middle bg-emerald-50/50 dark:bg-emerald-950/25">
                            <td className="py-0.5 px-1 font-bold text-emerald-900 dark:text-emerald-100">
                                بند القيمة المضافة
                            </td>
                            <td className="py-0.5 px-1">
                                <select
                                    value={taxType}
                                    disabled={readOnly}
                                    onChange={(e) =>
                                        onFinancial("taxType", e.target.value as "percentage" | "amount")
                                    }
                                    className={cellIn + " text-center text-[10px]"}
                                    title="نوع ض.ق.م"
                                >
                                    <option value="percentage">%</option>
                                    <option value="amount">₪</option>
                                </select>
                            </td>
                            <td
                                className="py-0.5 px-1 text-center text-[9px] text-emerald-800 dark:text-emerald-200"
                                title={`أساس ض.ق.م: ₪${Math.max(0, basisForInvoiceVat).toFixed(2)} — بضاعة + شحن دولي + عمولات تحويل دفعات + تخليص/ميناء/جمركة + نقل محلي (قبل ض.ق.م الفاتورة)`}
                            >
                                {basisForInvoiceVat > taxableBaseIls + 0.005
                                    ? "مجموع قبل ض.ق.م"
                                    : "أساس البضاعة"}
                            </td>
                            <td className="py-0.5 px-1">
                                {taxType === "percentage" ? (
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        disabled={readOnly}
                                        value={
                                            taxRate ? normalizeTaxRatePercent(taxRate) : ""
                                        }
                                        onChange={(e) =>
                                            onFinancial("taxRate", parseFloat(e.target.value) || 0)
                                        }
                                        className={cellIn + " text-center font-semibold tabular-nums"}
                                        title="نسبة ض.ق.م"
                                    />
                                ) : (
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        disabled={readOnly}
                                        value={taxAmount || ""}
                                        onChange={(e) =>
                                            onFinancial("taxAmount", parseFloat(e.target.value) || 0)
                                        }
                                        className={cellIn + " text-center font-semibold tabular-nums"}
                                        title="مبلغ ض.ق.م"
                                    />
                                )}
                            </td>
                            <td
                                className="py-0.5 px-1 text-center font-black text-emerald-900 dark:text-emerald-100 tabular-nums"
                                title={
                                    taxType === "percentage"
                                        ? `محسوبة من الأساس (₪${Math.max(0, basisForInvoiceVat).toFixed(2)} × ${normalizeTaxRatePercent(taxRate)}%)`
                                        : "مبلغ ثابت"
                                }
                            >
                                ₪
                                {(taxType === "percentage" ? mainVatIls : Math.max(0, Number(taxAmount) || 0)).toLocaleString(
                                    undefined,
                                    {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 3,
                                    }
                                )}
                            </td>
                            <td className="py-0.5 px-0 text-center text-[9px] text-emerald-700 dark:text-emerald-300">
                                {taxType === "percentage" ? "محسوبة" : "—"}
                            </td>
                        </tr>

                        {/* أسطر الرسوم المحفوظة */}
                        {lines.map((row) => {
                            const isPct = row.entryType === "percentage";
                            const basis = row.percentageBasis === "after_main_vat" ? "after_main_vat" : "goods";
                            const lineIls = lineTaxFeeIls(row, taxableBaseIls, extrasCtx);
                            const afterVatBasis = Math.max(0, basisForInvoiceVat) + mainVatIls;
                            const basisTitle =
                                isPct && basis === "after_main_vat"
                                    ? `نسبة من ₪${afterVatBasis.toFixed(2)} (مجموع قبل ض.ق.م + ض.ق.م)`
                                    : isPct
                                      ? `نسبة من ₪${Math.max(0, taxableBaseIls).toFixed(2)} (أساس البضاعة)`
                                      : undefined;
                            return (
                                <tr key={row.id} className="align-middle hover:bg-gray-50/60 dark:hover:bg-gray-800/40">
                                    <td className="py-0.5 px-1">
                                        <input
                                            type="text"
                                            disabled={readOnly}
                                            value={row.label}
                                            onChange={(e) =>
                                                updateLine(row.id, { label: e.target.value })
                                            }
                                            placeholder="اسم البند"
                                            className={cellIn}
                                        />
                                    </td>
                                    <td className="py-0.5 px-1">
                                        <select
                                            value={isPct ? "percentage" : "amount"}
                                            disabled={readOnly}
                                            onChange={(e) =>
                                                updateLine(row.id, {
                                                    entryType:
                                                        e.target.value === "percentage"
                                                            ? "percentage"
                                                            : "amount",
                                                    percentageBasis:
                                                        e.target.value === "percentage"
                                                            ? row.percentageBasis || "goods"
                                                            : undefined,
                                                })
                                            }
                                            className={cellIn + " text-center"}
                                        >
                                            <option value="amount">₪</option>
                                            <option value="percentage">%</option>
                                        </select>
                                    </td>
                                    <td className="py-0.5 px-1">
                                        {isPct ? (
                                            <select
                                                value={basis}
                                                disabled={readOnly}
                                                onChange={(e) =>
                                                    updateLine(row.id, {
                                                        percentageBasis:
                                                            e.target.value === "after_main_vat"
                                                                ? "after_main_vat"
                                                                : "goods",
                                                    })
                                                }
                                                className={cellIn + " text-center text-[10px]"}
                                                title="أساس احتساب النسبة"
                                            >
                                                <option value="goods">البضاعة</option>
                                                <option value="after_main_vat">بعد ض.ق.م</option>
                                            </select>
                                        ) : (
                                            <span className="text-center text-gray-400 block py-0.5">—</span>
                                        )}
                                    </td>
                                    <td className="py-0.5 px-1">
                                        <input
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            disabled={readOnly}
                                            value={row.amount || ""}
                                            onChange={(e) =>
                                                updateLine(row.id, {
                                                    amount: parseFloat(e.target.value) || 0,
                                                })
                                            }
                                            className={cellIn + " text-center font-semibold tabular-nums"}
                                        />
                                    </td>
                                    <td
                                        className="py-0.5 px-1 text-center font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] tabular-nums"
                                        title={basisTitle}
                                    >
                                        {lineIls.toLocaleString(undefined, {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2,
                                        })}
                                    </td>
                                    <td className="py-0.5 px-0 text-center">
                                        {!readOnly && (
                                            <button
                                                type="button"
                                                title="حذف من القائمة"
                                                onClick={() => removeLine(row.id)}
                                                className="p-0.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}

                        {/* صف إدخال جديد — يُضاف للقائمة بزر واحد */}
                        {!readOnly && (
                            <tr className="align-middle bg-[var(--color-surface-2)]/40 dark:bg-[var(--color-surface-2)]/20 border-t border-dashed border-[var(--color-border)] dark:border-[var(--color-border)]">
                                <td className="py-0.5 px-1">
                                    <input
                                        type="text"
                                        value={draft.label}
                                        onChange={(e) =>
                                            setDraft((d) => ({ ...d, label: e.target.value }))
                                        }
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") {
                                                e.preventDefault();
                                                commitDraft();
                                            }
                                        }}
                                        placeholder="اسم الرسم / الضريبة"
                                        className={cellIn + " border-[var(--color-border)] dark:border-[var(--color-border)]"}
                                    />
                                </td>
                                <td className="py-0.5 px-1">
                                    <select
                                        value={draft.entryType}
                                        onChange={(e) =>
                                            setDraft((d) => ({
                                                ...d,
                                                entryType:
                                                    e.target.value === "percentage"
                                                        ? "percentage"
                                                        : "amount",
                                                percentageBasis:
                                                    e.target.value === "percentage"
                                                        ? d.percentageBasis
                                                        : "goods",
                                            }))
                                        }
                                        className={cellIn + " text-center border-[var(--color-border)] dark:border-[var(--color-border)]"}
                                    >
                                        <option value="amount">₪</option>
                                        <option value="percentage">%</option>
                                    </select>
                                </td>
                                <td className="py-0.5 px-1">
                                    {draft.entryType === "percentage" ? (
                                        <select
                                            value={draft.percentageBasis}
                                            onChange={(e) =>
                                                setDraft((d) => ({
                                                    ...d,
                                                    percentageBasis:
                                                        e.target.value === "after_main_vat"
                                                            ? "after_main_vat"
                                                            : "goods",
                                                }))
                                            }
                                            className={cellIn + " text-center text-[10px] border-[var(--color-border)] dark:border-[var(--color-border)]"}
                                        >
                                            <option value="goods">البضاعة</option>
                                            <option value="after_main_vat">بعد ض.ق.م</option>
                                        </select>
                                    ) : (
                                        <span className="text-gray-400 text-center block py-0.5">—</span>
                                    )}
                                </td>
                                <td className="py-0.5 px-1">
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        value={draft.amount || ""}
                                        onChange={(e) =>
                                            setDraft((d) => ({
                                                ...d,
                                                amount: parseFloat(e.target.value) || 0,
                                            }))
                                        }
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter") {
                                                e.preventDefault();
                                                commitDraft();
                                            }
                                        }}
                                        placeholder="0"
                                        className={cellIn + " text-center tabular-nums border-[var(--color-border)] dark:border-[var(--color-border)]"}
                                    />
                                </td>
                                <td
                                    className="py-0.5 px-1 text-center text-[10px] font-semibold tabular-nums text-[var(--color-primary)] dark:text-[var(--color-primary)]"
                                    title="معاينة قبل الإضافة"
                                >
                                    {draftPreview.toLocaleString(undefined, {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })}
                                </td>
                                <td className="py-0.5 px-0.5 text-center">
                                    <button
                                        type="button"
                                        disabled={!canCommitDraft}
                                        onClick={commitDraft}
                                        className="inline-flex items-center gap-0.5 rounded border border-[var(--color-border)] dark:border-[var(--color-border)] bg-[var(--color-primary)] dark:bg-[var(--color-surface-2)] px-1.5 py-0.5 text-[9px] font-bold text-white shadow-sm disabled:opacity-40 disabled:pointer-events-none hover:bg-[var(--color-primary-hover)] dark:hover:bg-[var(--color-primary-hover)]"
                                        title="يضيف السطر أعلاه ويفرغ الخانات"
                                    >
                                        <Plus className="w-3 h-3 shrink-0" />
                                        إضافة للقائمة
                                    </button>
                                </td>
                            </tr>
                        )}
                    </tbody>
                    <tfoot>
                        <tr className="border-t border-gray-200 dark:border-gray-700 bg-gray-50/70 dark:bg-gray-900/60">
                            <td
                                colSpan={4}
                                className="py-1 px-1 text-[10px] font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] text-right"
                            >
                                مجموع الرسوم والضرائب الإضافية (بدون ض.ق.م)
                                {hasAfterMainVatPercentageLines(lp) ? (
                                    <span className="block font-normal text-[var(--color-primary)]/90 dark:text-[var(--color-primary)]/90 mt-0.5">
                                        يشمل سطراً بنسبة من (مجموع قبل ض.ق.م + ض.ق.م الفاتورة).
                                    </span>
                                ) : null}
                            </td>
                            <td className="py-1 px-1 text-center font-black text-[var(--color-primary)] dark:text-[var(--color-primary)] tabular-nums">
                                ₪
                                {extrasSum.toLocaleString(undefined, {
                                    minimumFractionDigits: 2,
                                })}
                            </td>
                            <td />
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
};
