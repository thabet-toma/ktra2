import React, { useState, useEffect, useCallback } from "react";
import {
    Shipment,
    Deal,
    User,
    ShipmentDealInfo,
} from "@/types";
import {
    effectiveDealTitleForDisplay,
    hasDedicatedShortDescription,
} from "@/utils/dealTitleDisplay";
import { shipmentsService } from "@/services/shipmentsService";
import { dealsService } from "@/services/dealsService";
import {
    listClearances,
    formatClearanceShipmentLine,
    type ClearanceRow,
} from "@/services/clearanceApi";
import {
    purchaseInvoiceApi,
    type ClearanceImportOptionDeal,
} from "@/services/purchaseInvoiceApi";
import { formatMoney, formatNumber } from "@/utils/formatNumber";
import { useToast } from "@/contexts/ToastContext";
import {
    Search,
    X,
    ScrollText,
    ChevronRight,
    TrendingUp,
    CheckCircle2,
    Package,
    ArrowLeftRight,
    Loader2,
    Truck,
    ExternalLink,
} from "lucide-react";
import { openInNewTab } from "@/utils/openInNewTab";
import { mergeClearanceImportDeals } from "@/utils/invoiceConversionUtils";

/** يمنع الاستيراد إذا أرجع الخادم تفصيلاً بالدولار وما زال هناك شحن غير مدفوع ومؤكّد. */
function clearancePreviewBlocksImportForUnpaidFreight(
    preview: Record<string, unknown> | null
): boolean {
    if (!preview || preview.shipment_freight_total_usd == null) return false;
    if (preview.shipment_freight_unpaid_usd == null) return false;
    const unpaid = Number(preview.shipment_freight_unpaid_usd);
    return Number.isFinite(unpaid) && unpaid > 0.02;
}

type ImportFooterHint = { text: string; tone: "muted" | "danger" };

/** يشرح للمستخدم لماذا زر الاستيراد معطّل (يظهر بجانب الزر في الشريط السفلي). */
function importButtonFooterHint(args: {
    selectedDealsCount: number;
    importBusy: boolean;
    previewLoading: boolean;
    preview: Record<string, unknown> | null;
    freightImportBlocked: boolean;
}): ImportFooterHint | null {
    const {
        selectedDealsCount,
        importBusy,
        previewLoading,
        preview,
        freightImportBlocked,
    } = args;
    if (selectedDealsCount === 0 || importBusy) return null;
    if (previewLoading) {
        return {
            text: "الزر معطّل مؤقتاً: جاري التحقق من المعاينة ومن حالة دفع شحن الشحنة على الخادم…",
            tone: "muted",
        };
    }
    if (freightImportBlocked && preview) {
        const u = preview.shipment_freight_unpaid_usd;
        const unpaid =
            u != null && Number.isFinite(Number(u))
                ? formatMoney(u)
                : "—";
        return {
            text: `الزر معطّل لأن شحن الشحنة غير مكتمل كدفع مؤكّد بالدولار على الخادم (المتبقي تقريباً $${unpaid}). أكمل دفعات وكيل الشحن من شاشة الشحنة حتى يساوي المدفوع إجمالي الشحن بالدولار ثم أعد المحاولة. ملاحظة: شارة حالة التخليص (مثل PROCESSING) لا تعطّل هذا الزر.`,
            tone: "danger",
        };
    }
    return null;
}

function shipmentTitleAndNumber(s: Shipment): { title: string; numberLine: string } {
    const num = (s.shipmentNumber || "").trim() || "—";
    const name = (s.shipmentName || "").trim();
    if (name && name !== num) return { title: name, numberLine: `رقم الشحنة: ${num}` };
    return { title: num, numberLine: `رقم الشحنة: ${num}` };
}

function supplierLocalFromRow(deal: Deal | undefined, sd: ShipmentDealInfo): string {
    const a = (deal?.supplierSnapshot?.alias || "").trim();
    if (a) return a;
    const p = (sd.partnerName || "").trim();
    if (p) return p;
    return "—";
}

/** مصنع / قانوني — يظهر تحت الاسم المحلي */
function supplierFormalFromRow(deal: Deal | undefined, sd: ShipmentDealInfo): string | null {
    const local = supplierLocalFromRow(deal, sd);
    const factory = (deal?.factoryName || sd.factoryName || "").trim();
    const legal = (deal?.supplierSnapshot?.legalName || "").trim();
    const trade = (deal?.supplierSnapshot?.tradeName || "").trim();
    const formal = factory || legal || trade;
    if (!formal) return null;
    if (formal === local) return null;
    return formal;
}

/** نفس السياق السابق لصفحة الفواتير (تحديث مسار الشحنة + مراحل الصفقات) */
export type ShipmentImportContext = {
    shipmentId: string;
    shippingType: "sea" | "air";
    dealIds: string[];
    currentRouteStatus: string;
};

interface ClearanceImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    /** يُستدعى بعد نجاح الاستيراد من الخادم (تحديث مسار الشحنة + الصفقات) */
    onImport: (ctx: ShipmentImportContext, meta: { createdCount: number }) => void;
    currentUser: User;
    /** اختيار مسبق لتخليص شحنة معيّنة — يصل من زر «تحويل إلى فاتورة شراء» في شاشة الاستيراد */
    initialShipmentId?: number | null;
}

export const ClearanceImportModal: React.FC<ClearanceImportModalProps> = ({
    isOpen,
    onClose,
    onImport,
    currentUser: _currentUser,
    initialShipmentId = null,
}) => {
    const toast = useToast();
    const [clearances, setClearances] = useState<ClearanceRow[]>([]);
    const [allDeals, setAllDeals] = useState<Deal[]>([]);
    const [searchTerm, setSearchTerm] = useState("");
    const [listLoading, setListLoading] = useState(false);
    const [listError, setListError] = useState<string | null>(null);

    const [selectedClearance, setSelectedClearance] = useState<ClearanceRow | null>(null);
    const [resolvedShipment, setResolvedShipment] = useState<Shipment | null>(null);
    const [shipmentLoading, setShipmentLoading] = useState(false);
    const [shipmentError, setShipmentError] = useState<string | null>(null);

    const [selectedDeals, setSelectedDeals] = useState<string[]>([]);
    const [dealImportStates, setDealImportStates] = useState<Record<string, {
        isConverted: boolean;
        invoiceId: number | null;
        invoiceNumber: string | null;
    }>>({});
    const [importOptionDeals, setImportOptionDeals] = useState<ClearanceImportOptionDeal[]>([]);
    const [importOptionsLoading, setImportOptionsLoading] = useState(false);
    const [importOptionsError, setImportOptionsError] = useState<string | null>(null);

    const [shipmentRemainingRate, setShipmentRemainingRate] = useState<number>(3.6);
    const [dealRemainingRate, setDealRemainingRate] = useState<number>(3.6);
    const [importBusy, setImportBusy] = useState(false);
    const [useCostLines, setUseCostLines] = useState(false);
    const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
    const [previewLoading, setPreviewLoading] = useState(false);

    const refreshClearances = useCallback(async () => {
        setListLoading(true);
        setListError(null);
        try {
            const rows = await listClearances();
            setClearances(rows);
        } catch {
            setClearances([]);
            setListError("تعذّر تحميل قائمة التخليصات الجمركية");
        } finally {
            setListLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!isOpen) return;
        const unsubDeals = dealsService.subscribeToDeals(setAllDeals);
        void refreshClearances();
        return () => {
            unsubDeals();
        };
    }, [isOpen, refreshClearances]);

    // اختيار مسبق: تخليص الشحنة القادمة من شاشة الاستيراد (T12-A4)
    useEffect(() => {
        if (!isOpen || !initialShipmentId || selectedClearance) return;
        const match = clearances.find((c) => Number(c.shipment) === Number(initialShipmentId));
        if (match) setSelectedClearance(match);
    }, [isOpen, initialShipmentId, clearances, selectedClearance]);

    useEffect(() => {
        if (!isOpen || !selectedClearance) {
            setResolvedShipment(null);
            setShipmentError(null);
            return;
        }
        let cancelled = false;
        setShipmentLoading(true);
        setShipmentError(null);
        shipmentsService
            .getShipment(String(selectedClearance.shipment))
            .then((s) => {
                if (!cancelled) setResolvedShipment(s);
            })
            .catch(() => {
                if (!cancelled) {
                    setResolvedShipment(null);
                    setShipmentError("تعذّر تحميل بيانات الشحنة المرتبطة بهذا التخليص");
                }
            })
            .finally(() => {
                if (!cancelled) setShipmentLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [isOpen, selectedClearance]);

    useEffect(() => {
        if (!isOpen || !selectedClearance) {
            setDealImportStates({});
            setImportOptionDeals([]);
            setImportOptionsError(null);
            return;
        }
        let cancelled = false;
        setImportOptionsLoading(true);
        setImportOptionsError(null);
        void purchaseInvoiceApi.getClearanceImportOptions(selectedClearance.id)
            .then((result) => {
                if (cancelled) return;
                const next: Record<string, { isConverted: boolean; invoiceId: number | null; invoiceNumber: string | null }> = {};
                result.deals.forEach((row) => {
                    next[String(row.deal_id)] = {
                        isConverted: row.is_converted,
                        invoiceId: row.invoice_id,
                        invoiceNumber: row.invoice_number,
                    };
                });
                setImportOptionDeals(result.deals);
                setDealImportStates(next);
                setSelectedDeals((current) => current.filter((id) => !next[id]?.isConverted));
            })
            .catch(() => {
                if (!cancelled) {
                    setDealImportStates({});
                    setImportOptionDeals([]);
                    setImportOptionsError("تعذّر التحقق من الصفقات المحوّلة. أعد المحاولة قبل إنشاء الفواتير.");
                }
            })
            .finally(() => {
                if (!cancelled) setImportOptionsLoading(false);
            });
        return () => { cancelled = true; };
    }, [isOpen, selectedClearance]);

    useEffect(() => {
        if (!isOpen || !selectedClearance || !resolvedShipment || selectedDeals.length === 0) {
            setPreview(null);
            return;
        }
        let cancelled = false;
        setPreviewLoading(true);
        void purchaseInvoiceApi
            .previewClearanceImport({
                clearance_id: selectedClearance.id,
                deal_ids: selectedDeals.map((id) => Number(id)),
                deal_remaining_rate: dealRemainingRate,
                shipment_remaining_rate: shipmentRemainingRate,
                use_cost_lines: useCostLines,
            })
            .then((p) => {
                if (!cancelled) setPreview(p);
            })
            .catch(() => {
                if (!cancelled) setPreview(null);
            })
            .finally(() => {
                if (!cancelled) setPreviewLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [
        isOpen,
        selectedClearance,
        resolvedShipment,
        selectedDeals,
        dealRemainingRate,
        shipmentRemainingRate,
        useCostLines,
    ]);

    if (!isOpen) return null;

    const freightImportBlocked = clearancePreviewBlocksImportForUnpaidFreight(preview);
    const hasUsdFreightPreview =
        preview != null && preview.shipment_freight_total_usd != null;
    const unpaidFreightUsd = hasUsdFreightPreview
        ? Number(preview!.shipment_freight_unpaid_usd ?? NaN)
        : null;
    const importFooterHint = importButtonFooterHint({
        selectedDealsCount: selectedDeals.length,
        importBusy,
        previewLoading,
        preview,
        freightImportBlocked,
    });
    const importButtonDisabled =
        importBusy ||
        importOptionsLoading ||
        Boolean(importOptionsError) ||
        selectedDeals.length === 0 ||
        freightImportBlocked ||
        (selectedDeals.length > 0 && previewLoading);

    const q = searchTerm.trim().toLowerCase();
    const filteredClearances = clearances.filter((c) => {
        const sn = (c.shipment_number || "").toLowerCase();
        const sname = (c.shipment_name || "").toLowerCase();
        const dec = (c.declaration_number || "").toLowerCase();
        const broker = (c.broker_name || "").toLowerCase();
        const notes = (c.notes || "").toLowerCase();
        const preview = (c.deals_preview || "").toLowerCase();
        const shipLine = formatClearanceShipmentLine(c).toLowerCase();
        if (!q) return true;
        return (
            sn.includes(q) ||
            sname.includes(q) ||
            dec.includes(q) ||
            broker.includes(q) ||
            notes.includes(q) ||
            preview.includes(q) ||
            shipLine.includes(q)
        );
    });

    const handleSelectClearance = (row: ClearanceRow) => {
        setSelectedClearance(row);
        setSelectedDeals([]);
    };

    const handleToggleDeal = (dealId: string) => {
        if (importOptionsLoading || importOptionsError) return;
        if (dealImportStates[dealId]?.isConverted) return;
        setSelectedDeals((prev) =>
            prev.includes(dealId) ? prev.filter((id) => id !== dealId) : [...prev, dealId]
        );
    };

    const visibleDeals = mergeClearanceImportDeals(
        resolvedShipment?.deals || [],
        importOptionDeals
    );
    const remainingDealIds = visibleDeals
        .filter((deal) => !dealImportStates[deal.dealId]?.isConverted)
        .map((deal) => deal.dealId);

    const handleImportClick = async () => {
        if (!resolvedShipment || !selectedClearance) return;
        if (selectedDeals.length === 0) {
            toast("الرجاء اختيار صفقة واحدة على الأقل", "info");
            return;
        }
        if (previewLoading) {
            toast("انتظر حتى تنتهي معاينة التكلفة من الخادم ثم أعد المحاولة.", "info");
            return;
        }
        if (clearancePreviewBlocksImportForUnpaidFreight(preview)) {
            toast(
                "لا يمكن الاستيراد: شحن الشحنة غير مكتمل الدفع بالدولار. سجّل دفعات وكيل الشحن المؤكّدة من شاشة الشحنة ثم أعد المحاولة.",
                "error"
            );
            return;
        }

        setImportBusy(true);
        try {
            const res = await purchaseInvoiceApi.importFromClearance({
                clearance_id: selectedClearance.id,
                deal_ids: selectedDeals.map((id) => Number(id)),
                deal_remaining_rate: dealRemainingRate,
                shipment_remaining_rate: shipmentRemainingRate,
                use_cost_lines: useCostLines,
            });
            const shippingType =
                resolvedShipment.shippingInfo?.shippingType === "air" ? "air" : "sea";
            const currentRouteStatus =
                resolvedShipment.shippingInfo?.shipmentStatus?.status || "agent_warehouse";
            onImport(
                {
                shipmentId: resolvedShipment.id,
                shippingType,
                dealIds: [...selectedDeals],
                currentRouteStatus,
                },
                { createdCount: Array.isArray(res.created) ? res.created.length : 0 }
            );
            onClose();
        } catch (e) {
            // console suppressed
            toast(e instanceof Error ? e.message : "فشل استيراد الفواتير من الخادم", "error");
        } finally {
            setImportBusy(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-stretch sm:items-center justify-center p-0 sm:p-4 bg-black/60 backdrop-blur-sm overflow-y-auto">
            <div
                className="aseel-bg-field dark:aseel-bg-panel sm:rounded-3xl w-full max-w-5xl min-h-0 flex flex-col shadow-2xl overflow-hidden border-0 sm:border aseel-border-soft dark:aseel-border-soft my-0 sm:my-auto
                h-[100dvh] max-h-[100dvh] sm:h-[min(92vh,900px)] sm:max-h-[min(92vh,900px)]"
            >
                <div className="px-4 sm:px-8 py-4 sm:py-5 bg-gradient-to-r from-[var(--color-primary)] aseel-bg-panel text-white flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <h2 className="text-lg sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <ScrollText className="w-6 h-6 sm:w-7 sm:h-7 shrink-0" />
                            <span className="leading-tight">استيراد فواتير من تخليص جمركي</span>
                        </h2>
                        <p className="aseel-text-soft text-xs sm:text-sm mt-1 leading-snug max-w-[52ch]">
                            التخليص مرتبط بشحنة واحدة؛ اختر الصفقات داخل تلك الشحنة لإنشاء فاتورة لكل صفقة
                            (شحنة ← عدة صفقات)
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:aseel-bg-field/20 rounded-xl transition-colors"
                        type="button"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex flex-1 min-h-0 overflow-hidden">
                    <div className="w-[min(100%,320px)] sm:w-[34%] max-w-sm shrink-0 border-s aseel-border-soft dark:aseel-border-soft flex flex-col aseel-bg-panel/50 dark:aseel-bg-panel/50 min-h-0">
                        <div className="p-4 space-y-3 shrink-0">
                            <div className="relative">
                                <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 aseel-text-soft" />
                                <input
                                    type="text"
                                    placeholder="بحث: اسم الشحنة، رقم الشحنة، بيان، صفقات..."
                                    className="w-full pr-10 pl-4 py-2.5 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl text-sm focus:ring-2 focus:ring-[var(--color-primary)] transition-all outline-none"
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                />
                            </div>
                            {listError && (
                                <p className="text-xs aseel-text-state dark:aseel-text-soft">{listError}</p>
                            )}
                        </div>

                        <div className="flex-1 overflow-y-auto p-2 space-y-2 custom-scrollbar">
                            {listLoading ? (
                                <div className="flex justify-center py-12 aseel-text-soft">
                                    <Loader2 className="w-8 h-8 animate-spin" />
                                </div>
                            ) : (
                                filteredClearances.map((c) => (
                                    <button
                                        key={c.id}
                                        type="button"
                                        onClick={() => handleSelectClearance(c)}
                                        className={`w-full text-right p-4 rounded-2xl border transition-all duration-200 group ${
                                            selectedClearance?.id === c.id
                                                ? "bg-[var(--color-primary)] border-[var(--color-border)] text-white shadow-lg shadow-indigo-200 dark:shadow-none"
                                                : "aseel-bg-field dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft hover:border-[var(--color-border)] dark:hover:border-[var(--color-border)] hover:shadow-md"
                                        }`}
                                    >
                                        <div className="flex justify-between items-start mb-2">
                                            <span className="font-bold text-lg">
                                                {c.declaration_number?.trim() ||
                                                    `تخليص #${c.id}`}
                                            </span>
                                            <span
                                                className={`text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wider font-semibold ${
                                                    selectedClearance?.id === c.id
                                                        ? "aseel-bg-field/20 text-white"
                                                        : "aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft"
                                                }`}
                                            >
                                                {c.status}
                                            </span>
                                        </div>
                                        <div
                                            className={`mt-1 flex items-start gap-2 text-sm font-bold leading-snug ${
                                                selectedClearance?.id === c.id
                                                    ? "text-white"
                                                    : "aseel-text-ink dark:text-white"
                                            }`}
                                        >
                                            <Truck className="w-4 h-4 shrink-0 mt-0.5 opacity-80" />
                                            <span className="min-w-0 break-words">
                                                {formatClearanceShipmentLine(c)}
                                            </span>
                                        </div>
                                        {(Number(c.deals_count) > 0 || (c.deals_preview || "").trim()) && (
                                            <div
                                                className={`mt-2 text-xs leading-relaxed line-clamp-3 text-right ${
                                                    selectedClearance?.id === c.id
                                                        ? "text-[var(--color-primary)]"
                                                        : "aseel-text-soft dark:aseel-text-soft"
                                                }`}
                                                title={c.deals_preview || undefined}
                                            >
                                                {Number(c.deals_count) > 0 ? (
                                                    <span className="font-semibold">
                                                        {c.deals_count} صفقة
                                                        {c.deals_preview ? " · " : ""}
                                                    </span>
                                                ) : null}
                                                {c.deals_preview || ""}
                                            </div>
                                        )}
                                        <div
                                            className={`mt-2 text-xs ${
                                                selectedClearance?.id === c.id
                                                    ? "text-[var(--color-primary)]"
                                                    : "aseel-text-soft dark:aseel-text-soft"
                                            }`}
                                        >
                                            المخلص: {c.broker_name || "—"}
                                        </div>
                                    </button>
                                ))
                            )}
                        </div>
                    </div>

                    <div className="flex-1 flex flex-col min-h-0 min-w-0 aseel-bg-field dark:aseel-bg-panel">
                        {selectedClearance ? (
                            shipmentLoading ? (
                                <div className="flex-1 flex flex-col items-center justify-center p-20 gap-4">
                                    <Loader2 className="w-10 h-10 text-[var(--color-primary)] animate-spin" />
                                    <p className="aseel-text-soft">جاري تحميل بيانات الشحنة...</p>
                                    <p className="text-sm font-semibold aseel-text-ink dark:aseel-text-soft text-center max-w-md">
                                        {formatClearanceShipmentLine(selectedClearance)}
                                    </p>
                                </div>
                            ) : shipmentError || !resolvedShipment ? (
                                <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                                    <p className="aseel-text-state dark:aseel-text-soft">
                                        {shipmentError || "لا توجد بيانات شحنة"}
                                    </p>
                                </div>
                            ) : (
                                <div className="flex flex-col flex-1 min-h-0 min-w-0">
                                    {/* منطقة تمرير واحدة: تفاصيل الشحنة + المعاينة + الصفقات — حتى لا تُضغط قائمة الصفقات */}
                                    <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
                                    <div className="p-4 sm:p-8 border-b aseel-border-soft dark:aseel-border-soft bg-[var(--color-surface-2)]/30 dark:bg-[var(--color-surface-2)]/10">
                                        <div className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-2 text-xs aseel-text-ink dark:aseel-text-soft">
                                            <span className="inline-flex items-center gap-1 rounded-full aseel-bg-field/90 dark:aseel-bg-panel/90 px-3 py-1 font-bold border border-[var(--color-border)] dark:border-[var(--color-border)]">
                                                <span className="text-[var(--color-primary)] dark:text-[var(--color-primary)]">١</span>
                                                التخليص
                                            </span>
                                            <span className="aseel-text-soft px-0.5" aria-hidden>
                                                ·
                                            </span>
                                            <span
                                                className={`inline-flex items-center gap-1 rounded-full px-3 py-1 font-bold border ${
                                                    selectedDeals.length > 0
                                                        ? "aseel-bg-field/90 dark:aseel-bg-panel/90 border-[var(--color-border)] dark:border-[var(--color-border)]"
                                                        : "aseel-bg-panel dark:aseel-bg-panel/90 aseel-border-soft dark:aseel-border-soft aseel-text-ink dark:aseel-text-soft"
                                                }`}
                                            >
                                                <span className="text-[var(--color-primary)] dark:text-[var(--color-primary)]">٢</span>
                                                اختر صفقة أو أكثر
                                            </span>
                                            <span className="aseel-text-soft px-0.5" aria-hidden>
                                                ·
                                            </span>
                                            <span className="inline-flex items-center gap-1 rounded-full aseel-bg-field/90 dark:aseel-bg-panel/90 px-3 py-1 font-bold border aseel-border-soft dark:aseel-border-soft">
                                                <span className="text-[var(--color-primary)] dark:text-[var(--color-primary)]">٣</span>
                                                «استيراد الفواتير» في الأسفل
                                            </span>
                                        </div>
                                        <div className="flex justify-between items-end flex-wrap gap-4">
                                            <div className="space-y-1 min-w-0">
                                                <p className="text-[10px] font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] uppercase tracking-wider">
                                                    اسم الشحنة (عربي / تعريفي)
                                                </p>
                                                <h3 className="text-xl font-bold aseel-text-ink dark:text-white truncate">
                                                    {shipmentTitleAndNumber(resolvedShipment).title}
                                                </h3>
                                                <p className="aseel-text-soft dark:aseel-text-soft text-sm">
                                                    {shipmentTitleAndNumber(resolvedShipment).numberLine}
                                                    {resolvedShipment.shippingAgentName ? (
                                                        <>
                                                            {" "}
                                                            · وكيل الشحن: {resolvedShipment.shippingAgentName}
                                                        </>
                                                    ) : null}
                                                </p>
                                                <p className="aseel-text-soft text-sm mt-2">
                                                    <span className="font-semibold aseel-text-ink dark:aseel-text-soft">
                                                        التخليص الجمركي:
                                                    </span>{" "}
                                                    {selectedClearance.declaration_number?.trim() ||
                                                        `مرجع #${selectedClearance.id}`}
                                                    {selectedClearance.broker_name
                                                        ? ` · المخلص: ${selectedClearance.broker_name}`
                                                        : ""}
                                                    {" — "}
                                                    اختر الصفقات أدناه لإنشاء فواتير بالشيكل
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="px-4 sm:px-8 py-4 border-b aseel-border-soft dark:aseel-border-soft aseel-bg-panel/80 dark:aseel-bg-panel/30 space-y-3">
                                        <label className="flex items-center gap-2 text-sm font-semibold aseel-text-ink dark:aseel-text-soft cursor-pointer">
                                            <input
                                                type="checkbox"
                                                className="rounded aseel-border-soft text-[var(--color-primary)] focus:ring-[var(--color-primary)]"
                                                checked={useCostLines}
                                                onChange={(e) => setUseCostLines(e.target.checked)}
                                            />
                                            استخدام بنود التخليص (تقدير) بدل مجموع الدفعات الفعلية
                                        </label>
                                        {previewLoading ? (
                                            <p className="text-xs aseel-text-soft flex items-center gap-2">
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                جاري حساب المعاينة…
                                            </p>
                                        ) : preview ? (
                                            <div className="space-y-3 text-sm">
                                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 aseel-text-ink dark:aseel-text-soft">
                                                    <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft aseel-bg-field/80 dark:aseel-bg-panel/60 px-3 py-2.5">
                                                        <div className="text-[11px] font-bold aseel-text-soft dark:aseel-text-soft mb-1">
                                                            إجمالي بنود التخليص
                                                        </div>
                                                        <div className="font-mono font-bold text-base tabular-nums">
                                                            {Number(preview.cost_lines_total_ils ?? 0).toLocaleString()}{" "}
                                                            ₪
                                                        </div>
                                                    </div>
                                                    <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft aseel-bg-field/80 dark:aseel-bg-panel/60 px-3 py-2.5">
                                                        <div className="text-[11px] font-bold aseel-text-soft dark:aseel-text-soft mb-1">
                                                            مجموع دفعات التخليص
                                                        </div>
                                                        <div className="font-mono font-bold text-base tabular-nums">
                                                            {Number(
                                                                preview.clearance_payments_total_ils ?? 0
                                                            ).toLocaleString()}{" "}
                                                            ₪
                                                        </div>
                                                    </div>
                                                    <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft aseel-bg-field/80 dark:aseel-bg-panel/60 px-3 py-2.5">
                                                        <div className="text-[11px] font-bold aseel-text-soft dark:aseel-text-soft mb-1">
                                                            تكلفة شحن الشحنة
                                                        </div>
                                                        <div className="font-mono font-bold text-base tabular-nums">
                                                            {Number(
                                                                preview.shipment_freight_total_ils ?? 0
                                                            ).toLocaleString()}{" "}
                                                            ₪
                                                        </div>
                                                    </div>
                                                    <div className="rounded-xl border border-[var(--color-border)] dark:border-[var(--color-border)] bg-[var(--color-surface-2)]/50 dark:bg-[var(--color-surface-2)]/40 px-3 py-2.5 sm:col-span-2">
                                                        <div className="text-[11px] font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] mb-1">
                                                            حوض التخليص المستخدم في التوزيع
                                                        </div>
                                                        <div className="font-mono font-bold text-base text-[var(--color-primary)] dark:text-[var(--color-primary)] tabular-nums">
                                                            {Number(preview.clearance_pool_ils ?? 0).toLocaleString()} ₪
                                                            <span className="text-sm font-semibold ms-2 opacity-90">
                                                                ({String(preview.clearance_source ?? "")})
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                                {preview.cost_lines_vs_payments_mismatch ? (
                                                    <div className="aseel-text-ink dark:aseel-text-soft text-xs aseel-bg-panel dark:aseel-bg-panel/40 rounded-lg px-3 py-2 border aseel-border-soft dark:aseel-border-soft">
                                                        مجموع بنود التخليص لا يطابق مجموع الدفعات — راجع الأرقام أو مصدر التكلفة.
                                                    </div>
                                                ) : null}
                                                {hasUsdFreightPreview ? (
                                                    <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft aseel-bg-field/80 dark:aseel-bg-panel/60 px-3 py-2.5 text-xs aseel-text-ink dark:aseel-text-soft space-y-1">
                                                        <div className="font-bold aseel-text-soft dark:aseel-text-soft">
                                                            شحن الشحنة (مرجع الدولار من إجمالي تكلفة الشحن)
                                                        </div>
                                                        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono tabular-nums">
                                                            <span>
                                                                إجمالي USD:{" "}
                                                                {Number(
                                                                    preview.shipment_freight_total_usd ?? 0
                                                                ).toLocaleString(undefined, {
                                                                    minimumFractionDigits: 2,
                                                                    maximumFractionDigits: 2,
                                                                })}
                                                            </span>
                                                            <span>
                                                                مدفوع ومؤكّد USD:{" "}
                                                                {Number(
                                                                    preview.shipment_freight_paid_usd ?? 0
                                                                ).toLocaleString(undefined, {
                                                                    minimumFractionDigits: 2,
                                                                    maximumFractionDigits: 2,
                                                                })}
                                                            </span>
                                                            <span>
                                                                غير مدفوع USD:{" "}
                                                                {Number(
                                                                    preview.shipment_freight_unpaid_usd ?? 0
                                                                ).toLocaleString(undefined, {
                                                                    minimumFractionDigits: 2,
                                                                    maximumFractionDigits: 2,
                                                                })}
                                                            </span>
                                                        </div>
                                                        <p className="text-[11px] leading-relaxed aseel-text-soft dark:aseel-text-soft pt-1 border-t aseel-border-soft dark:aseel-border-soft">
                                                            تكلفة الشحن بالشيكل في المعاينة = (ما دُفع فعلياً ومُؤكَّد
                                                            بالشيكل) + (غير المدفوع بالدولار × سعر «صرف المتبقي
                                                            (الشحن)»). الاستيراد يتطلّب إكمال دفع الشحن بالدولار حتى
                                                            لا تُؤسَّس الفاتورة على تقديرات غير مدفوعة.
                                                        </p>
                                                    </div>
                                                ) : null}
                                                {freightImportBlocked ? (
                                                    <div className="aseel-text-state dark:aseel-text-soft text-xs aseel-bg-panel dark:aseel-bg-panel/40 rounded-lg px-3 py-2.5 border aseel-border-soft dark:aseel-border-soft">
                                                        <strong>لا يمكن استيراد الفواتير:</strong> ما زال هناك{" "}
                                                        <span className="font-mono font-bold">
                                                            $
                                                            {unpaidFreightUsd != null &&
                                                            Number.isFinite(unpaidFreightUsd)
                                                                ? unpaidFreightUsd.toLocaleString(undefined, {
                                                                      minimumFractionDigits: 2,
                                                                      maximumFractionDigits: 2,
                                                                  })
                                                                : "—"}
                                                        </span>{" "}
                                                        شحن دولي غير مدفوع ومؤكّد. أنجز «إجراء الدفع» أو تسجيل
                                                        الدفعة من شاشة الشحنة ثم أعد فتح هذه النافذة.
                                                    </div>
                                                ) : null}
                                                {Array.isArray(preview.deals) && preview.deals.length > 0 ? (
                                                    <div className="overflow-x-auto rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                                        <table className="min-w-full text-xs text-right">
                                                            <thead className="aseel-bg-panel dark:aseel-bg-panel">
                                                                <tr>
                                                                    <th className="px-3 py-2">صفقة</th>
                                                                    <th className="px-3 py-2">حصة قيمة</th>
                                                                    <th className="px-3 py-2">حصة حجم</th>
                                                                    <th className="px-3 py-2">تخليص مخصص ₪</th>
                                                                    <th className="px-3 py-2">شحن مخصص ₪</th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {(preview.deals as Record<string, unknown>[]).map(
                                                                    (row) => (
                                                                        <tr
                                                                            key={String(row.deal_id)}
                                                                            className="border-t aseel-border-soft dark:aseel-border-soft"
                                                                        >
                                                                            <td className="px-3 py-2 font-mono">
                                                                                {String(row.ref_number ?? row.deal_id)}
                                                                            </td>
                                                                            <td className="px-3 py-2">
                                                                                {formatNumber(Number(row.share) * 100, { maxDecimals: 2 })}%
                                                                            </td>
                                                                            <td className="px-3 py-2">
                                                                                {formatNumber(
                                                                                    Number(
                                                                                        row.share_by_volume ??
                                                                                            row.share
                                                                                    ) * 100,
                                                                                    { maxDecimals: 2 }
                                                                                )}
                                                                                %
                                                                            </td>
                                                                            <td className="px-3 py-2">
                                                                                {Number(
                                                                                    row.allocated_clearance_ils ?? 0
                                                                                ).toLocaleString()}
                                                                            </td>
                                                                            <td className="px-3 py-2">
                                                                                {Number(
                                                                                    row.allocated_freight_ils ?? 0
                                                                                ).toLocaleString()}
                                                                            </td>
                                                                        </tr>
                                                                    )
                                                                )}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                ) : null}
                                            </div>
                                        ) : selectedDeals.length > 0 ? (
                                            <p className="text-xs aseel-text-soft">تعذّر تحميل المعاينة</p>
                                        ) : null}
                                    </div>

                                    <div className="p-4 sm:p-8 space-y-4 pb-8">
                                        <h4 className="text-sm font-bold aseel-text-soft uppercase tracking-widest flex items-center gap-2">
                                            <Package className="w-4 h-4" />
                                            الصفقات على شحنة «{shipmentTitleAndNumber(resolvedShipment).title}»
                                        </h4>
                                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border aseel-border-soft px-3 py-2">
                                            <span className="text-xs aseel-text-soft">
                                                المتبقية للتحويل: <b className="aseel-text-ink">{remainingDealIds.length}</b>
                                                {" · "}المحوّلة: <b className="aseel-text-ink">{visibleDeals.length - remainingDealIds.length}</b>
                                            </span>
                                            {remainingDealIds.length > 0 ? (
                                                <button
                                                    type="button"
                                                    onClick={() => setSelectedDeals([...remainingDealIds])}
                                                    className="rounded-lg border aseel-border-soft px-3 py-1.5 text-xs font-bold text-[var(--color-primary)] hover:bg-[var(--color-surface-2)]"
                                                >
                                                    اختيار كل المتبقي
                                                </button>
                                            ) : null}
                                        </div>
                                        {importOptionsError ? (
                                            <div className="rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
                                                {importOptionsError}
                                            </div>
                                        ) : null}
                                        {remainingDealIds.length === 0 && !importOptionsLoading ? (
                                            <p className="text-sm font-semibold text-emerald-700">
                                                تم تحويل جميع صفقات هذه الشحنة. يمكنك فتح كل فاتورة من بطاقتها أدناه.
                                            </p>
                                        ) : selectedDeals.length === 0 ? (
                                            <p className="text-sm aseel-text-soft dark:aseel-text-soft">
                                                اختر صفقة من القائمة أدناه، ثم «استيراد الفواتير».
                                            </p>
                                        ) : null}
                                        {visibleDeals.map((sd) => {
                                            const deal = allDeals.find(
                                                (d) => String(d.id) === String(sd.dealId)
                                            );
                                            const isSelected = selectedDeals.includes(sd.dealId);
                                            const importState = dealImportStates[sd.dealId];
                                            const isConverted = Boolean(importState?.isConverted);
                                            const notesLong = (
                                                deal?.internalNotes ||
                                                sd.notes ||
                                                ""
                                            ).trim();
                                            const displayTitle = effectiveDealTitleForDisplay({
                                                description:
                                                    deal?.dealDescription || sd.dealDescriptionRaw,
                                                notes: notesLong || undefined,
                                                original_offer_number:
                                                    deal?.originalOfferNumber || sd.originalOfferNumber,
                                                ref_number: sd.dealNumber,
                                            });
                                            const hasSqlDescription = hasDedicatedShortDescription({
                                                description:
                                                    deal?.dealDescription || sd.dealDescriptionRaw,
                                                notes: notesLong,
                                                ref_number: sd.dealNumber,
                                            });
                                            const showTermsBlock =
                                                notesLong.length > 0 &&
                                                notesLong.replace(/\s+/g, " ") !==
                                                    displayTitle.replace(/\s+/g, " ");
                                            const termsPreview =
                                                notesLong.length > 220
                                                    ? `${notesLong.slice(0, 217)}…`
                                                    : notesLong;
                                            const localSupplier = supplierLocalFromRow(deal, sd);
                                            const formalSupplier = supplierFormalFromRow(deal, sd);

                                            return (
                                                <div
                                                    key={sd.dealId}
                                                    role="checkbox"
                                                    aria-checked={isSelected}
                                                    aria-disabled={isConverted}
                                                    tabIndex={0}
                                                    onClick={() => handleToggleDeal(sd.dealId)}
                                                    onKeyDown={(e) => {
                                                        if (e.key === "Enter" || e.key === " ")
                                                            handleToggleDeal(sd.dealId);
                                                    }}
                                                    className={`p-4 sm:p-5 rounded-2xl border-2 transition-all duration-300 flex justify-between items-start gap-3 sm:gap-4 group ${
                                                        isConverted ? "cursor-default opacity-75 aseel-border-soft bg-[var(--color-surface-2)]" : "cursor-pointer"
                                                    } ${
                                                        isSelected
                                                            ? "border-[var(--color-border)] bg-[var(--color-surface-2)]/50 dark:bg-[var(--color-surface-2)]/20 shadow-lg shadow-indigo-100/50 dark:shadow-none"
                                                            : "aseel-border-soft dark:aseel-border-soft hover:aseel-border-soft dark:hover:aseel-border-soft"
                                                    }`}
                                                >
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={() => {
                                                            /* selection toggled by clicking the card */
                                                        }}
                                                        tabIndex={-1}
                                                        className="mt-1.5 h-5 w-5 shrink-0 rounded aseel-border-soft text-[var(--color-primary)] focus:ring-[var(--color-primary)] pointer-events-none"
                                                        aria-hidden
                                                        disabled={isConverted}
                                                    />
                                                    <div className="flex items-start gap-3 sm:gap-5 min-w-0 flex-1">
                                                        <div
                                                            className={`w-12 h-12 shrink-0 rounded-xl flex items-center justify-center transition-colors ${
                                                                isSelected
                                                                    ? "bg-[var(--color-primary)] text-white shadow-md"
                                                                    : "aseel-bg-panel dark:aseel-bg-panel aseel-text-soft group-hover:aseel-bg-grid-head"
                                                            }`}
                                                        >
                                                            {isSelected ? (
                                                                <CheckCircle2 className="w-6 h-6" />
                                                            ) : (
                                                                <Package className="w-6 h-6" />
                                                            )}
                                                        </div>
                                                        <div className="min-w-0 space-y-1.5">
                                                            <div>
                                                                <span className="text-[10px] font-bold aseel-text-soft uppercase tracking-wide block mb-0.5">
                                                                    عنوان الصفقة (من بيانات الشحنة + الصفقة)
                                                                </span>
                                                                <div
                                                                    className="font-bold text-base sm:text-lg aseel-text-ink dark:text-white leading-snug break-words"
                                                                    title={displayTitle}
                                                                >
                                                                    {displayTitle}
                                                                </div>
                                                                {!hasSqlDescription &&
                                                                displayTitle === sd.dealNumber ? (
                                                                    <div className="text-[11px] aseel-text-soft dark:aseel-text-soft mt-1">
                                                                        لم يُعثر على وصف عربي في بيانات الصفقة.
                                                                    </div>
                                                                ) : !hasSqlDescription &&
                                                                  displayTitle !== sd.dealNumber ? (
                                                                    <div className="text-[10px] aseel-text-soft mt-1">
                                                                        العنوان مُستخرج من أول سطر عربي في الملاحظات
                                                                    </div>
                                                                ) : null}
                                                                <div className="text-xs aseel-text-soft mt-1 font-mono">
                                                                    رقم الصفقة: {sd.dealNumber}
                                                                </div>
                                                                {showTermsBlock ? (
                                                                    <div className="mt-2 pt-2 border-t aseel-border-soft dark:aseel-border-soft">
                                                                        <span className="text-[10px] font-bold aseel-text-soft uppercase tracking-wide block mb-0.5">
                                                                            شروط وملاحظات (نص طويل)
                                                                        </span>
                                                                        <p
                                                                            className="text-xs aseel-text-soft dark:aseel-text-soft leading-relaxed line-clamp-4 break-words"
                                                                            title={notesLong}
                                                                        >
                                                                            {termsPreview}
                                                                        </p>
                                                                    </div>
                                                                ) : null}
                                                            </div>
                                                            <div>
                                                                <span className="text-[10px] font-bold aseel-text-soft uppercase tracking-wide block mb-0.5">
                                                                    المورد — الاسم المستعار / المحلي
                                                                </span>
                                                                <div className="text-sm font-semibold text-[var(--color-primary)] dark:text-[var(--color-primary)] break-words">
                                                                    {localSupplier}
                                                                </div>
                                                                {formalSupplier ? (
                                                                    <div className="text-xs aseel-text-soft mt-0.5 break-words">
                                                                        الاسم الإنجليزي / المصنع: {formalSupplier}
                                                                    </div>
                                                                ) : null}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    {isConverted ? (
                                                        <button
                                                            type="button"
                                                            onClick={(event) => {
                                                                event.stopPropagation();
                                                                if (importState?.invoiceId) openInNewTab(`/purchase-invoices/${importState.invoiceId}`);
                                                            }}
                                                            className="inline-flex shrink-0 items-center gap-1 rounded-lg border aseel-border-soft px-2.5 py-1.5 text-xs font-bold text-[var(--color-primary)] hover:bg-[var(--color-surface-2)]"
                                                        >
                                                            <ExternalLink className="h-3.5 w-3.5" />
                                                            محوّلة — {importState?.invoiceNumber || `فاتورة #${importState?.invoiceId}`}
                                                        </button>
                                                    ) : null}
                                                    <div className="text-left flex items-center gap-10">
                                                        <div className="text-right">
                                                            <div className="text-[10px] aseel-text-soft uppercase font-bold tracking-wider mb-1">
                                                                المبلغ الإجمالي
                                                            </div>
                                                            <div className="font-mono text-lg font-bold aseel-text-ink dark:aseel-text-soft">
                                                                ${sd.totalAmount?.toLocaleString()}
                                                            </div>
                                                        </div>
                                                        <div
                                                            className={`p-2 rounded-lg transition-colors ${
                                                                isSelected
                                                                    ? "bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/40 text-[var(--color-primary)]"
                                                                    : "aseel-text-soft"
                                                            }`}
                                                        >
                                                            <ChevronRight
                                                                className={`w-5 h-5 transition-transform ${
                                                                    isSelected ? "translate-x-1" : ""
                                                                }`}
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                    </div>

                                    <div className="z-20 p-4 sm:p-6 border-t aseel-border-soft dark:aseel-border-soft flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 shrink-0 aseel-bg-field dark:aseel-bg-panel shadow-[0_-6px_24px_-6px_rgba(0,0,0,0.1)] dark:shadow-[0_-6px_24px_-6px_rgba(0,0,0,0.45)]">
                                        <div className="flex flex-wrap items-center gap-4 text-sm aseel-text-soft dark:aseel-text-soft">
                                            <div className="flex flex-col">
                                                <span className="text-[10px] aseel-text-soft uppercase font-bold tracking-widest">
                                                    صفقات مختارة
                                                </span>
                                                <span className="text-2xl font-black aseel-text-ink dark:text-white tabular-nums">
                                                    {selectedDeals.length}
                                                </span>
                                            </div>
                                            {selectedDeals.length === 0 ? (
                                                <span className="max-w-md aseel-text-soft dark:aseel-text-soft text-xs sm:text-sm">
                                                    اختر صفقة واحدة على الأقل.
                                                </span>
                                            ) : (
                                                <span className="text-xs sm:text-sm aseel-text-soft dark:aseel-text-soft">
                                                    سيتم إنشاء فاتورة شراء (شيكل) لكل صفقة مختارة.
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex flex-col items-stretch sm:items-end gap-2 w-full sm:w-auto sm:min-w-[min(100%,320px)]">
                                            {importFooterHint ? (
                                                <p
                                                    className={`text-xs text-right leading-snug max-w-[min(100%,28rem)] ${
                                                        importFooterHint.tone === "danger"
                                                            ? "aseel-text-state dark:aseel-text-soft font-semibold"
                                                            : "aseel-text-soft dark:aseel-text-soft"
                                                    }`}
                                                >
                                                    {importFooterHint.text}
                                                </p>
                                            ) : null}
                                        <button
                                            type="button"
                                            onClick={() => void handleImportClick()}
                                                disabled={importButtonDisabled}
                                                className="w-full sm:w-auto min-h-[52px] px-8 sm:px-10 py-3.5 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:aseel-bg-grid-head disabled:aseel-text-soft dark:disabled:aseel-bg-panel dark:disabled:aseel-text-soft text-white rounded-2xl font-bold shadow-lg shadow-indigo-200/80 dark:shadow-none transition-all flex items-center justify-center gap-3 active:scale-[0.98]"
                                        >
                                            {importBusy ? (
                                                <Loader2 className="w-5 h-5 animate-spin" />
                                            ) : (
                                                    <ArrowLeftRight className="w-5 h-5 shrink-0" />
                                            )}
                                                {importBusy ? "جاري الاستيراد..." : "استيراد الفواتير (شيكل)"}
                                        </button>
                                        </div>
                                    </div>
                                </div>
                            )
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center p-6 sm:p-12 text-center space-y-6">
                                <div className="w-24 h-24 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 rounded-full flex items-center justify-center">
                                    <ScrollText className="w-10 h-10 text-[var(--color-primary)]" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold aseel-text-ink dark:text-white">
                                        لم يتم اختيار تخليص جمركي
                                    </h3>
                                    <p className="aseel-text-soft max-w-xs mx-auto mt-2">
                                        اختر تخليصاً من القائمة لعرض صفقات الشحنة المرتبطة وإنشاء فواتير
                                        متعددة
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
