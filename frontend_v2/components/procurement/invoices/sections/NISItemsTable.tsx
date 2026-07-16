import React, { useMemo } from "react";
import { Package, Tag, Layers, Anchor, Receipt } from "lucide-react";
import type { Invoice, InvoiceItem, LocalPayments } from "@/types";
import {
    allocateInvoiceFinalCosts,
    sumTaxesAndFeesExtras,
    transferCommissionsIlsForVat,
} from "@/utils/invoiceTaxesAndFees";
import { formatMoney } from "@/utils/formatNumber";

interface NISItemsTableProps {
    items: InvoiceItem[];
    conversionRate: number;
    invoiceTaxAmount?: number;
    localPayments?: LocalPayments | null;
    /** أساس احتساب بنود النسبة ضمن الضرائب والرسوم */
    taxableBaseIls?: number;
    /** لبنود «بعد ض.ق.م» — مجموع ما قبل ض.ق.م الفاتورة */
    invoiceVatBaseIls?: number;
    /** لتوزيع عمولات التحويل على أسطر الجدول (نفس أوزان الضريبة والرسوم) */
    conversionMetadata?: Invoice["conversionMetadata"] | null;
    /** رسوم PurchaseInvoiceFee المحفوظة — تدخل في التكلفة النهائية المعروضة. */
    additionalFeesTotal?: number;
    /** الفاتورة مرتبطة بشحنة، فتكون أسعار البنود تكاليف استيراد موزعة لا أسعار شراء خام. */
    isShipmentLinkedImport?: boolean;
}

function fmtIls(v: number) {
    return `₪${formatMoney(v)}`;
}

export const NISItemsTable: React.FC<NISItemsTableProps> = ({
    items,
    conversionRate,
    invoiceTaxAmount = 0,
    localPayments,
    taxableBaseIls = 0,
    invoiceVatBaseIls,
    conversionMetadata,
    additionalFeesTotal = 0,
    isShipmentLinkedImport = false,
}) => {
    const showLanded = items.some(
        (it) =>
            it.landedUnitPriceIls != null &&
            it.landedUnitPriceIls > 0 &&
            it.landedLineTotalIls != null
    );

    const lp = localPayments || {};
    const extrasPool = sumTaxesAndFeesExtras(lp, taxableBaseIls, {
        mainVatIls: Math.max(0, Number(invoiceTaxAmount) || 0),
        invoiceVatBaseIls:
            invoiceVatBaseIls != null && Number.isFinite(invoiceVatBaseIls)
                ? Math.max(0, invoiceVatBaseIls)
                : undefined,
    });
    const taxFeesPool =
        (Number(invoiceTaxAmount) || 0) +
        extrasPool +
        Math.max(0, Number(additionalFeesTotal) || 0);
    const transferPoolIls = useMemo(
        () => transferCommissionsIlsForVat(conversionMetadata as Record<string, unknown> | null),
        [conversionMetadata]
    );
    const showAllocColumns = items.length > 0;

    const perRowAlloc = useMemo(() => {
        return allocateInvoiceFinalCosts(items, {
            transferTotalIls: transferPoolIls,
            taxAndFeesTotalIls: taxFeesPool,
        }).map((row) => ({
            taxFeesAlloc: row.taxAndFeesAllocation,
            transferAlloc: row.transferAllocation,
            preTaxWithTransfer: row.preTaxLine,
            afterLine: row.finalLine,
            afterUnit: row.finalUnit,
        }));
    }, [items, taxFeesPool, transferPoolIls]);

    const sumMerchIls = items.reduce((s, it) => s + (Number(it.totalPrice) || 0), 0);
    const sumLandedWithTransferIls = perRowAlloc.reduce((s, r) => s + r.preTaxWithTransfer, 0);
    const sumTaxFeesAlloc = perRowAlloc.reduce((s, r) => s + r.taxFeesAlloc, 0);
    const sumAfter = perRowAlloc.reduce((s, r) => s + r.afterLine, 0);
    const totalQty = items.reduce((s, it) => s + (Number(it.quantity) || 0), 0);
    const avgUnitAfterAll = totalQty > 0 ? sumAfter / totalQty : 0;

    const colCount = 4 + (showLanded ? 2 : 0) + (showAllocColumns ? 2 : 0);

    return (
        <div className="overflow-hidden rounded-2xl border aseel-border-soft dark:aseel-border-soft aseel-bg-field dark:aseel-bg-panel shadow-sm">
            <div className="overflow-x-auto">
                <table
                    className="w-full text-right border-collapse"
                    style={{ minWidth: Math.max(640, colCount * 100) }}
                >
                    <thead>
                        <tr className="aseel-bg-panel/50 dark:aseel-bg-panel/20 border-b aseel-border-soft dark:aseel-border-soft/50">
                            <th className="px-3 py-2 text-xs font-bold aseel-text-ink dark:aseel-text-soft">
                                المنتج
                            </th>
                            <th className="px-2 py-2 text-xs font-bold aseel-text-ink dark:aseel-text-soft text-center">
                                كمية
                            </th>
                            <th className="px-2 py-2 text-xs font-bold aseel-text-ink dark:aseel-text-soft">
                                {isShipmentLinkedImport ? "تكلفة الاستيراد/وحدة ₪" : "وحدة أساس ₪"}
                            </th>
                            {showLanded && (
                                <th className="px-2 py-2 text-xs font-bold aseel-text-ink dark:aseel-text-soft aseel-bg-panel/80 dark:aseel-bg-panel/20">
                                    <span className="inline-flex items-center gap-1">
                                        <Anchor className="w-3.5 h-3.5" />
                                        {isShipmentLinkedImport ? "قبل ض.ق.م/وحدة ₪" : "وحدة نهائية ₪"}
                                    </span>
                                </th>
                            )}
                            <th className="px-2 py-2 text-xs font-bold aseel-text-ink dark:aseel-text-soft">
                                {isShipmentLinkedImport ? "إجمالي تكلفة الاستيراد ₪" : "إجمالي أساس ₪"}
                            </th>
                            {showLanded && (
                                <th className="px-2 py-2 text-xs font-bold aseel-text-ink dark:aseel-text-soft aseel-bg-panel/80 dark:aseel-bg-panel/20">
                                    {isShipmentLinkedImport ? "الإجمالي قبل ض.ق.م ₪" : "إجمالي نهائي ₪"}
                                </th>
                            )}
                            {showAllocColumns ? (
                                <>
                                    <th className="px-2 py-2 text-xs font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] bg-[var(--color-surface-2)]/90 dark:bg-[var(--color-surface-2)]/40 border-s border-[var(--color-border)] dark:border-[var(--color-border)]/50">
                                        <span className="inline-flex items-center gap-1">
                                            <Receipt className="w-3 h-3" />
                                            ض.ق.م + رسوم
                                        </span>
                                    </th>
                                    <th className="px-2 py-2 text-xs font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] bg-[var(--color-surface-2)]/90 dark:bg-[var(--color-surface-2)]/40 border-s border-[var(--color-border)] dark:border-[var(--color-border)]/50">
                                        <div className="leading-tight">تكلفة الوحدة</div>
                                        <div className="text-[9px] font-normal opacity-90">بعد الضريبة والرسوم</div>
                                    </th>
                                </>
                            ) : null}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {items.map((item, idx) => {
                            const rate = conversionRate > 0 ? conversionRate : 1;
                            const usdUnitPrice = item.unitPrice / rate;
                            const usdTotalPrice = item.totalPrice / rate;
                            const alloc = perRowAlloc[idx];

                            return (
                                <tr
                                    key={item.id || idx}
                                    className="hover:aseel-bg-panel dark:hover:aseel-bg-panel/50 transition-colors group"
                                >
                                    <td className="px-3 py-2">
                                        <div className="flex items-start gap-2">
                                            <div className="w-10 h-10 rounded-md aseel-bg-panel dark:aseel-bg-panel flex-shrink-0 overflow-hidden border aseel-border-soft dark:aseel-border-soft">
                                                {item.imageUrls?.[0] ? (
                                                    <img
                                                        src={item.imageUrls[0]}
                                                        alt={item.name}
                                                        className="w-full h-full object-cover"
                                                    />
                                                ) : (
                                                    <div className="w-full h-full flex items-center justify-center aseel-text-soft">
                                                        <Package className="w-4 h-4" />
                                                    </div>
                                                )}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs font-bold aseel-text-ink dark:text-white truncate">
                                                    {item.name}
                                                </div>
                                                <div className="text-[10px] aseel-text-soft flex items-center gap-0.5 mt-0.5">
                                                    <Tag className="w-2.5 h-2.5" />
                                                    {item.categoryName}
                                                    {item.modelNumber && ` · ${item.modelNumber}`}
                                                </div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-2 py-2 text-center">
                                        <span className="text-xs font-bold aseel-text-ink dark:aseel-text-soft">
                                            {item.quantity}
                                        </span>
                                    </td>
                                    <td className="px-2 py-2">
                                        <div className="text-xs font-bold aseel-text-ink dark:text-white tabular-nums">
                                            ₪
                                            {formatMoney(item.unitPrice)}
                                        </div>
                                        <div className="text-[9px] aseel-text-soft tabular-nums">
                                            ${formatMoney(usdUnitPrice)}
                                        </div>
                                    </td>
                                    {showLanded && (
                                        <td className="px-2 py-2 aseel-bg-panel/40 dark:aseel-bg-panel/10">
                                            {alloc &&
                                            (item.landedLineTotalIls != null ||
                                                item.landedUnitPriceIls != null ||
                                                (Number(item.totalPrice) || 0) > 0) ? (
                                                <span className="text-xs font-bold aseel-text-ink dark:aseel-text-soft tabular-nums">
                                                    ₪
                                                    {formatMoney(
                                                        alloc.preTaxWithTransfer /
                                                        Math.max(Number(item.quantity) || 0, 0.0001)
                                                    )}
                                                </span>
                                            ) : (
                                                <span className="aseel-text-soft text-xs">—</span>
                                            )}
                                        </td>
                                    )}
                                    <td className="px-2 py-2">
                                        <div className="text-xs font-bold aseel-text-ink dark:aseel-text-soft tabular-nums">
                                            ₪
                                            {formatMoney(item.totalPrice)}
                                        </div>
                                        <div className="text-[9px] aseel-text-soft tabular-nums">
                                            ${formatMoney(usdTotalPrice)}
                                        </div>
                                    </td>
                                    {showLanded && (
                                        <td className="px-2 py-2 aseel-bg-panel/40 dark:aseel-bg-panel/10">
                                            {alloc && (item.landedLineTotalIls != null || (Number(item.totalPrice) || 0) > 0) ? (
                                                <div className="space-y-0.5">
                                                    <span className="text-xs font-bold aseel-text-ink dark:aseel-text-soft tabular-nums">
                                                        ₪
                                                        {alloc.preTaxWithTransfer.toLocaleString(undefined, {
                                                            minimumFractionDigits: 2,
                                                        })}
                                                    </span>
                                                    {alloc.transferAlloc > 0.005 ? (
                                                        <span className="block text-[9px] aseel-text-ink/90 dark:aseel-text-soft/80 tabular-nums">
                                                            منها عمولات تحويل ₪
                                                            {alloc.transferAlloc.toLocaleString(undefined, {
                                                                minimumFractionDigits: 2,
                                                            })}
                                                        </span>
                                                    ) : null}
                                                </div>
                                            ) : (
                                                <span className="aseel-text-soft text-xs">—</span>
                                            )}
                                        </td>
                                    )}
                                    {showAllocColumns && alloc ? (
                                        <>
                                            <td className="px-2 py-2 text-xs font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] bg-[var(--color-surface-2)]/30 dark:bg-[var(--color-surface-2)]/20 border-s border-[var(--color-border)]/80 dark:border-[var(--color-border)]/40 tabular-nums">
                                                {alloc.taxFeesAlloc > 0 ? fmtIls(alloc.taxFeesAlloc) : "—"}
                                            </td>
                                            <td className="px-2 py-2 bg-[var(--color-surface-2)]/40 dark:bg-[var(--color-surface-2)]/20 border-s border-[var(--color-border)]/80 dark:border-[var(--color-border)]/40">
                                                <div className="text-base font-black text-[var(--color-primary)] dark:text-[var(--color-primary)] tabular-nums leading-tight">
                                                    {fmtIls(alloc.afterUnit)}
                                                </div>
                                                <div className="text-[9px] text-[var(--color-primary)]/90 dark:text-[var(--color-primary)]/90 mt-0.5 tabular-nums">
                                                    سطر {fmtIls(alloc.afterLine)}
                                                </div>
                                            </td>
                                        </>
                                    ) : null}
                                </tr>
                            );
                        })}
                    </tbody>
                    {items.length > 0 ? (
                        <tfoot>
                            <tr className="aseel-bg-panel/40 dark:aseel-bg-panel/40 border-t aseel-border-soft dark:aseel-border-soft">
                                <td
                                    colSpan={3}
                                    className="px-3 py-2 text-[10px] font-bold aseel-text-ink dark:aseel-text-soft"
                                >
                                    المجاميع
                                </td>
                                {showLanded ? <td className="px-2 py-2" /> : null}
                                <td className="px-2 py-2 text-xs font-black aseel-text-ink dark:aseel-text-soft tabular-nums">
                                    {fmtIls(sumMerchIls)}
                                </td>
                                {showLanded ? (
                                    <td className="px-2 py-2 text-xs font-black aseel-text-ink dark:aseel-text-soft aseel-bg-panel/60 dark:aseel-bg-panel/50 tabular-nums">
                                        {fmtIls(sumLandedWithTransferIls)}
                                    </td>
                                ) : null}
                                {showAllocColumns ? (
                                    <>
                                        <td className="px-2 py-2 text-xs font-black text-[var(--color-primary)] dark:text-[var(--color-primary)] bg-[var(--color-surface-2)]/50 dark:bg-[var(--color-surface-2)]/30 tabular-nums">
                                            {taxFeesPool > 0 ? fmtIls(sumTaxFeesAlloc) : "—"}
                                        </td>
                                        <td className="px-2 py-2 text-[var(--color-primary)] dark:text-[var(--color-primary)] bg-[var(--color-surface-2)]/50 dark:bg-[var(--color-surface-2)]/30 tabular-nums">
                                            <div className="text-sm font-black leading-tight">
                                                {fmtIls(avgUnitAfterAll)}
                                            </div>
                                            <div className="text-[9px] opacity-90 mt-0.5">متوسط مرجّح</div>
                                            <div className="text-[9px] font-bold mt-1">مجموع أسطر {fmtIls(sumAfter)}</div>
                                        </td>
                                    </>
                                ) : null}
                            </tr>
                        </tfoot>
                    ) : null}
                </table>
            </div>

            {items.length === 0 && (
                <div className="p-8 text-center">
                    <Layers className="w-10 h-10 aseel-text-soft dark:aseel-text-ink mx-auto mb-2" />
                    <p className="aseel-text-soft text-xs">لا توجد بنود</p>
                </div>
            )}
        </div>
    );
};
