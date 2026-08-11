/**
 * N6-T1 — DealManagement (L1) — AseelDenseTable لإدارة الصفقات
 * المرجع: task5.md:795 + الإرساليات.txt:1-34
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Deal, DealItem, PriceOffer, User, Supplier } from '../../types';
import { priceOffersService, suppliersService } from '../../services/firestoreService';
import { dealsService } from '../../services/dealsService';
import { DealForm } from './deals/DealForm';
import { DealPrintView } from './deals/DealPrintView';
import { Plus, FileInput, Printer, Trash2, RefreshCw, Ship } from 'lucide-react';
import { LoadingSpinner } from '../LoadingSpinner';
import { PriceOfferSelectionModal } from './price-offers/PriceOfferSelectionModal';
import { convertSupplierQuotationToImportDeal } from '../../services/procurementDocumentsApi';
import { CreateShipmentFromDealsModal } from '../import-flow/CreateShipmentFromDealsModal';
import { FirstDealWizard } from './deals/FirstDealWizard';
import { Sparkles } from 'lucide-react';
import { AseelDenseTable, type DenseColumn } from '../aseel/AseelDenseTable';
import { useAseelIndexKeymap } from '../aseel/useAseelIndexKeymap';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import { getShippingWorkflowLabel } from '../../utils/shippingWorkflowLabels';
import { AseelErrorState } from '../aseel';

interface DealManagementProps {
    currentUser: User;
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

/**
 * توحيد لغة الحالة (قرار معماري — مراجعة الاستيراد ج3):
 * SQL لا يخزّن إلا 4 حالات دورة حياة (Open/Shipped/Closed/Cancelled) تُشتق
 * آلياً من مراحل الشحن؛ قائمة الـ14 حالة القديمة كانت وهمية — لا يمكن أن تعود
 * من الخادم فكانت خيارات فلترة ميتة. «الحقيقة» التشغيلية = shipping_workflow_status
 * (عمود «المرحلة»)، ودورة الحياة = هذه الأربع، والدفع بُعد مالي مستقل داخل الصفقة.
 */
const STATUS_LABELS: Record<string, string> = {
    initial:   'مفتوحة',
    shipped:   'تم الشحن',
    completed: 'مكتملة',
    cancelled: 'ملغاة',
};

const STATUS_COLORS: Record<string, string> = {
    initial:   'var(--aseel-ink-soft)',
    shipped:   'var(--aseel-accent, #1857a4)',
    completed: 'var(--aseel-ok, #267346)',
    cancelled: 'var(--aseel-danger, #c00)',
};

import { formatMoney } from "@/utils/formatNumber";
import { formatDateValue } from "../../utils/formatDate";
const fmtAmt = (n: number) => formatMoney(n);

const fmtDate = (s: string | undefined) => {
    if (!s) return '—';
    return formatDateValue(s);
};

export const DealManagement: React.FC<DealManagementProps> = ({
    currentUser,
    onOpenAccountingJournal,
}) => {
    const navigate = useNavigate();
    const location = useLocation();
    const newFormInitRef = useRef(false);

    /**
     * URL = مصدر الحقيقة الوحيد للوضع:
     *   /deals            → قائمة
     *   /deals/new        → صفقة جديدة
     *   /deals/{id}       → تعديل (النموذج)
     *   /deals/{id}/view  → تقرير/طباعة
     */
    const dealsPathMatch = useMemo(() => {
        const path = (location.pathname || '/').replace(/\/$/, '') || '/';
        if (path !== '/deals' && !path.startsWith('/deals/')) return null;
        if (path === '/deals') return { mode: 'list' as const };
        const m = path.match(/^\/deals\/([^/]+)(\/view)?$/);
        if (!m) return { mode: 'list' as const };
        const seg = decodeURIComponent(m[1]);
        if (seg === 'new') return { mode: 'new' as const };
        if (m[2]) return { mode: 'view' as const, id: seg };
        return { mode: 'edit' as const, id: seg };
    }, [location.pathname]);

    const confirm = useConfirm();
    const toast = useToast();
    const [viewMode, setViewMode] = useState<'list' | 'form' | 'view'>('list');
    const [deals, setDeals] = useState<Deal[]>([]);
    const [priceOffers, setPriceOffers] = useState<PriceOffer[]>([]);
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [currentDeal, setCurrentDeal] = useState<Partial<Deal> | null>(null);
    const [dealToPrint, setDealToPrint] = useState<Deal | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [reloadKey, setReloadKey] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);
    const [hasNextPage, setHasNextPage] = useState(false);
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [isOfferModalOpen, setIsOfferModalOpen] = useState(false);
    const [isShipmentModalOpen, setIsShipmentModalOpen] = useState(false);
    // G12: معالِج أول صفقة (مستخدم جديد) — 3 خطوات مبسّطة.
    const [showWizard, setShowWizard] = useState(false);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    // G3: أُزيل حارس «أعِد التوجيه إلى /deals لأي مسار غير /deals». كان يشتعل
    // أثناء الانتقال بعيداً عن الشاشة (زر «ابدأ الشحن الدولي» → /import-flow/new)
    // بينما DealManagement ما زال مركّباً، فيُجهض التنقّل ويُرجع لقائمة الصفقات
    // (كان يتطلّب reload). طبّع مسارات /deals المشوّهة يتكفّل به dealsPathMatch أصلاً،
    // ومزامنة الـURL مع deals-management يضمنها App + المُنقّلات الصريحة.

    useEffect(() => {
        if (dealsPathMatch?.mode !== 'list') {
            setLoading(false);
            return;
        }
        let cancelled = false;
        setLoading(true);
        const timer = window.setTimeout(() => {
            void dealsService.listDealsPage({
                page: 1,
                pageSize: 50,
                search,
                status: statusFilter,
            }).then((result) => {
                if (cancelled) return;
                setDeals(result.deals);
                setTotalCount(result.count);
                setHasNextPage(result.hasNext);
                setCurrentPage(1);
                setLoadError(null);
            }).catch((error) => {
                if (!cancelled) {
                    setLoadError(error instanceof Error ? error.message : 'تعذّر تحميل الصفقات.');
                }
            }).finally(() => {
                if (!cancelled) setLoading(false);
            });
        }, 250);
        return () => { cancelled = true; window.clearTimeout(timer); };
    }, [dealsPathMatch?.mode, reloadKey, search, statusFilter]);

    useEffect(() => {
        const unsubOffers = priceOffersService.subscribeToPriceOffers((offers) => {
            setPriceOffers(offers.filter(o =>
                o.offerType === 'incoming_offer' && o.status === 'approved_for_shipping'
            ));
        }, 'import');
        const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
        return () => { unsubOffers(); unsubSuppliers(); };
    }, []);

    const dealRefFromQuery = useMemo(() => {
        const p = new URLSearchParams(location.search);
        return p.get('ref') || '';
    }, [location.search]);

    /**
     * حارس ضد قلب الوضع: كل تحديث لمصفوفة deals (تحديث عند التركيز، إعادة
     * تحميل بعد عملية…) يعيد تشغيل هذا الـ effect. بدون الحارس كان الوضع يُفرض
     * من جديد فيُقلب المستخدم من «تعديل» إلى «عرض» فجأة (البق المبلَّغ).
     * كل مسار يُعالَج مرة واحدة فقط؛ تغيير المسار وحده يعيد المعالجة.
     */
    const handledPathRef = useRef<string | null>(null);
    useEffect(() => {
        if (!dealsPathMatch) return;
        const pathKey = location.pathname + location.search;
        if (dealsPathMatch.mode === 'list') {
            if (dealRefFromQuery) {
                // رابط قديم ?ref=D-0001 → نحوله لمسار العرض الصريح
                const target = deals.find(
                    d => String(d.dealNumber).toUpperCase() === dealRefFromQuery.toUpperCase()
                );
                if (target) {
                    navigate(`/deals/${encodeURIComponent(target.id)}/view`, { replace: true });
                } else if (handledPathRef.current !== pathKey && !loading) {
                    handledPathRef.current = pathKey;
                    newFormInitRef.current = false;
                    setViewMode('list');
                    setCurrentDeal(null);
                }
                return;
            }
            if (handledPathRef.current === pathKey) return;
            handledPathRef.current = pathKey;
            newFormInitRef.current = false;
            setViewMode('list');
            setCurrentDeal(null);
            return;
        }
        if (dealsPathMatch.mode === 'edit' || dealsPathMatch.mode === 'view') {
            if (handledPathRef.current === pathKey) return;
            handledPathRef.current = pathKey;
            setLoading(true);
            void dealsService.getDeal(String(dealsPathMatch.id)).then((target) => {
                setCurrentDeal({ ...target });
                setViewMode(dealsPathMatch.mode === 'view' ? 'view' : 'form');
                setLoadError(null);
            }).catch((error) => {
                setLoadError(error instanceof Error ? error.message : 'تعذّر فتح الصفقة.');
                handledPathRef.current = null;
                navigate('/deals', { replace: true });
            }).finally(() => setLoading(false));
            return;
        }
        const draft = (location.state as { draftDeal?: Partial<Deal> } | null)?.draftDeal;
        handledPathRef.current = pathKey;
        if (draft) {
            newFormInitRef.current = true;
            setCurrentDeal(draft);
            setViewMode('form');
            navigate('/deals/new', { replace: true, state: {} });
            return;
        }
        if (newFormInitRef.current) return;
        newFormInitRef.current = true;
        void (async () => {
            try {
                const dealNumber = await dealsService.getNextDealNumber();
                setCurrentDeal({
                    dealNumber,
                    status: 'initial',
                    remainingAmount: 0,
                    items: [],
                    subtotal: 0,
                    shippingCost: 0,
                    discountAmount: 0,
                    taxRate: 0,
                    taxAmount: 0,
                    payments: [],
                    statusHistory: [],
                    quoteImages: [],
                    quotePdfs: []
                });
                setViewMode('form');
            } catch (e) {
                // console suppressed
                newFormInitRef.current = false;
                navigate('/deals', { replace: true });
            }
        })();
    }, [dealsPathMatch, deals, loading, location.state, location.pathname, location.search, navigate, dealRefFromQuery]);

    const filteredDeals = useMemo(() => {
        return deals;
    }, [deals]);

    const stats = useMemo(() => ({
        total: totalCount,
        active: deals.filter(d => !['completed', 'cancelled'].includes(d.status)).length,
        completed: deals.filter(d => d.status === 'completed').length,
        totalValue: deals.reduce((s, d) => s + (d.totalAmount || 0), 0),
    }), [deals, totalCount]);

    const handleCreateNew = () => {
        newFormInitRef.current = false;
        navigate('/deals/new');
    };

    const handleCreateFromPriceOffer = async (priceOfferId: string) => {
        setIsOfferModalOpen(false);
        const selectedOffer = priceOffers.find(o => o.id === priceOfferId);
        if (!selectedOffer) return;
        try {
            const match = /^quote-(\d+)$/.exec(selectedOffer.id);
            if (!match) throw new Error('عرض الاستيراد المحدد غير مرتبط بقاعدة البيانات.');
            const result = await convertSupplierQuotationToImportDeal(Number(match[1]));
            navigate(`/deals/${encodeURIComponent(String(result.deal.id))}`);
        } catch (error) {
            setLoadError(error instanceof Error ? error.message : 'تعذّر تحويل العرض إلى طلبية استيراد.');
        }
    };

    /** فتح الصفقة — تُفتح على وضع العرض، والتحرير من زر «تحرير» داخلها. */
    const openDeal = (deal: Deal) => {
        // الأصل: يفتح في تاب جديد كي لا يفقد المستخدم سياق القائمة
        window.open(
            `${window.location.origin}/deals/${encodeURIComponent(deal.id)}`,
            '_blank',
            'noopener,noreferrer',
        );
    };

    const reloadDeals = async () => {
        setReloadKey((key) => key + 1);
    };

    const loadMoreDeals = async () => {
        if (!hasNextPage || loading) return;
        setLoading(true);
        try {
            const nextPage = currentPage + 1;
            const result = await dealsService.listDealsPage({
                page: nextPage, pageSize: 50, search, status: statusFilter,
            });
            setDeals((rows) => [...rows, ...result.deals]);
            setCurrentPage(nextPage);
            setHasNextPage(result.hasNext);
            setTotalCount(result.count);
        } catch (error) {
            setLoadError(error instanceof Error ? error.message : 'تعذّر تحميل المزيد.');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = () => {
        setViewMode('list');
        setCurrentDeal(null);
        navigate('/deals');
        void reloadDeals();
    };

    const handleDelete = async (dealId: string) => {
        if (!(await confirm({ title: 'حذف الصفقة', message: 'حذف الصفقة؟' }))) return;
        try {
            await dealsService.deleteDeal(dealId);
            setDeals(prev => prev.filter(d => String(d.id) !== String(dealId)));
        } catch (error) {
            // console suppressed
            toast('فشل حذف الصفقة', 'error');
        }
    };

    const columns: DenseColumn<Deal>[] = [
        {
            key: 'dealNumber',
            header: 'رقم الصفقة',
            width: '110px',
            sortable: true,
            render: (d) => <b style={{ fontFamily: 'monospace' }}>{d.dealNumber || '—'}</b>,
        },
        {
            key: 'supplier',
            header: 'المورد',
            render: (d) => {
                const sup = suppliers.find(s => s.id === d.supplierId);
                if (sup) return <>{sup.alias && sup.alias.trim() ? `${sup.tradeName} (${sup.alias})` : sup.tradeName}</>;
                return <>{d.factoryName || d.supplierSnapshot?.tradeName || '—'}</>;
            },
        },
        {
            key: 'description',
            header: 'الوصف',
            render: (d) => <span style={{ color: 'var(--aseel-ink-soft)' }}>{d.dealDescription || '—'}</span>,
        },
        {
            key: 'status',
            header: 'الحالة',
            width: '160px',
            render: (d) => (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <span style={{ color: STATUS_COLORS[d.status] || 'inherit', fontWeight: 500 }}>
                        {STATUS_LABELS[d.status] || d.status}
                    </span>
                    {/* «تحولت إلى فاتورة» — رابط بجانب الحالة يفتح فاتورة الشراء الناتجة */}
                    {d.linkedInvoice && (
                        <button
                            type="button"
                            onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/purchase-invoices/${d.linkedInvoice!.id}`);
                            }}
                            title="فتح الفاتورة الناتجة عن الصفقة"
                            style={{
                                color: 'var(--aseel-accent, #2563eb)',
                                textDecoration: 'underline',
                                fontWeight: 500,
                                fontSize: '0.72rem',
                                background: 'none',
                                border: 'none',
                                padding: 0,
                                cursor: 'pointer',
                            }}
                        >
                            ↗ تحولت إلى فاتورة{d.linkedInvoice.invoiceNumber ? ` #${d.linkedInvoice.invoiceNumber}` : ''}
                        </button>
                    )}
                </span>
            ),
        },
        {
            key: 'stage',
            header: 'المرحلة',
            width: '150px',
            render: (d) => (
                <span style={{ color: 'var(--aseel-ink-soft)' }} title="مرحلة الشحن والتصنيع (مصدر الحقيقة التشغيلي)">
                    {d.status === 'cancelled' || !d.shippingWorkflowStatus ? '—' : getShippingWorkflowLabel(d.shippingWorkflowStatus)}
                </span>
            ),
        },
        {
            key: 'totalAmount',
            header: 'المبلغ',
            width: '110px',
            align: 'right',
            numeric: true,
            sortable: true,
            render: (d) => <span style={{ fontFamily: 'monospace' }}>${fmtAmt(d.totalAmount || 0)}</span>,
        },
        {
            key: 'remainingAmount',
            header: 'المتبقي',
            width: '100px',
            align: 'right',
            numeric: true,
            render: (d) => {
                const rem = d.remainingAmount || 0;
                return (
                    <span style={{ fontFamily: 'monospace', color: rem > 0 ? 'var(--aseel-warn, #b8800a)' : 'var(--aseel-ok, #267346)' }}>
                        ${fmtAmt(rem)}
                    </span>
                );
            },
        },
        {
            key: 'createdAt',
            header: 'التاريخ',
            width: '90px',
            sortable: true,
            render: (d) => <>{fmtDate(d.createdAt)}</>,
        },
        {
            key: 'actions',
            header: '',
            width: '90px',
            align: 'center',
            render: (d) => (
                <span style={{ display: 'inline-flex', gap: 2 }}>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); setDealToPrint(d); }}
                        title="طباعة"
                    >
                        <Printer style={{ width: 13, height: 13 }} />
                    </button>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px', color: 'var(--aseel-danger, #c00)' }}
                        onClick={(e) => { e.stopPropagation(); void handleDelete(d.id); }}
                        title="حذف"
                    >
                        <Trash2 style={{ width: 13, height: 13 }} />
                    </button>
                </span>
            ),
        },
    ];

    // N0-T7 — keymap على قائمة الصفقات (list mode فقط)
    useAseelIndexKeymap(
        {
            CtrlIns: handleCreateNew,
            F6: () => searchInputRef.current?.focus(),
            Escape: () => { setSearch(''); setStatusFilter('all'); },
        },
        { enabled: viewMode === 'list' && !dealToPrint && !isOfferModalOpen },
    );

    if (loading) return <LoadingSpinner />;
    if (loadError && deals.length === 0) {
        return <AseelErrorState message={loadError} onRetry={() => {
            setLoading(true);
            setReloadKey((key) => key + 1);
        }} />;
    }

    // وضع النموذج
    if (viewMode === 'form' && currentDeal) {
        return (
            <DealForm
                deal={currentDeal}
                priceOffers={priceOffers}
                currentUser={currentUser}
                onSave={handleSave}
                onCancel={() => {
                    setViewMode('list');
                    setCurrentDeal(null);
                    navigate('/deals');
                }}
                compactMode={true}
                onOpenAccountingJournal={onOpenAccountingJournal}
            />
        );
    }

    if (viewMode === 'view' && currentDeal) {
        return (
            <DealPrintView
                deal={currentDeal as Deal}
                supplier={suppliers.find(s => s.id === currentDeal.supplierId)}
                currentUser={currentUser}
                onClose={() => {
                    setViewMode('list');
                    setCurrentDeal(null);
                    navigate('/deals');
                }}
                onEdit={() => {
                    // «تعديل البيانات» → مسار التعديل الصريح؛ الـ effect يفتح النموذج
                    navigate(`/deals/${encodeURIComponent(String(currentDeal.id))}`);
                }}
            />
        );
    }

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
            {/* شريط العنوان والأدوات */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>
                    إدارة الصفقات
                </strong>
                <span className="aseel-status-item">الإجمالي: <b>{stats.total}</b></span>
                <span className="aseel-status-item">نشطة: <b>{stats.active}</b></span>
                <span className="aseel-status-item">مكتمل: <b>{stats.completed}</b></span>
                <span className="aseel-status-item">القيمة: <b>${(stats.totalValue / 1000).toFixed(1)}K</b></span>
                <div style={{ flex: 1 }} />
                {/* بحث (F6 = focus) */}
                <input
                    ref={searchInputRef}
                    className="aseel-input aseel-print-hidden"
                    style={{ width: 200 }}
                    placeholder="بحث برقم الصفقة، المورد، المنتج… (F6)"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                {/* فلتر الحالة */}
                <select
                    className="aseel-input aseel-print-hidden"
                    style={{ width: 150 }}
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                >
                    <option value="all">كل الحالات</option>
                    {Object.entries(STATUS_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                    ))}
                </select>
                <button
                    className="aseel-toolbtn aseel-print-hidden"
                    onClick={() => { setSearch(''); setStatusFilter('all'); void reloadDeals(); }}
                    title="تحديث القائمة وإعادة تعيين الفلاتر"
                >
                    <RefreshCw style={{ width: 14, height: 14 }} />
                </button>
                <button
                    className="aseel-toolbtn aseel-print-hidden"
                    onClick={() => setIsOfferModalOpen(true)}
                    title="إنشاء من عرض سعر"
                >
                    <FileInput style={{ width: 14, height: 14 }} />
                    {priceOffers.length > 0 && <span style={{ marginRight: 2 }}>({priceOffers.length})</span>}
                    من عرض
                </button>
                <button
                    className="aseel-toolbtn aseel-print-hidden"
                    onClick={() => setIsShipmentModalOpen(true)}
                    title="إنشاء شحنة من صفقات جاهزة للشحن (اختيار متعدد)"
                >
                    <Ship style={{ width: 14, height: 14 }} /> شحنة من الصفقات
                </button>
                <button
                    className="aseel-toolbtn aseel-print-hidden"
                    onClick={() => setShowWizard(true)}
                    title="معالِج موجّه لإنشاء أول صفقة (3 خطوات مبسّطة)"
                >
                    <Sparkles style={{ width: 14, height: 14 }} /> معالِج الصفقة
                </button>
                <button
                    className="aseel-toolbtn aseel-print-hidden"
                    onClick={handleCreateNew}
                    title="صفقة جديدة (Ctrl+Ins)"
                >
                    <Plus style={{ width: 14, height: 14 }} /> صفقة جديدة
                </button>
            </div>

            {/* جدول الصفقات */}
            <AseelDenseTable<Deal>
                columns={columns}
                rows={filteredDeals}
                getRowKey={(d) => d.id}
                loading={loading}
                emptyHint="لا توجد صفقات — اضغط «صفقة جديدة»"
                onRowDoubleClick={(d) => openDeal(d)}
                footer={
                    filteredDeals.length > 0 ? (
                        <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                            إجمالي: <b>${fmtAmt(filteredDeals.reduce((s, d) => s + (d.totalAmount || 0), 0))}</b>
                            {' • '}
                            متبقي: <b>${fmtAmt(filteredDeals.reduce((s, d) => s + (d.remainingAmount || 0), 0))}</b>
                        </span>
                    ) : undefined
                }
            />
            {hasNextPage && (
                <button className="aseel-toolbtn aseel-print-hidden" onClick={() => void loadMoreDeals()}>
                    تحميل المزيد ({deals.length} من {totalCount})
                </button>
            )}

            {/* M1 — إنشاء شحنة من صفقات جاهزة (اختيار متعدد) */}
            <CreateShipmentFromDealsModal
                isOpen={isShipmentModalOpen}
                onClose={() => setIsShipmentModalOpen(false)}
                onCreated={(shipmentId) => {
                    setIsShipmentModalOpen(false);
                    // افتح رحلة الاستيراد للشحنة الجديدة في تبويب جديد (يحفظ سياق القائمة)
                    window.open(
                        `${window.location.origin}/import-flow/${encodeURIComponent(String(shipmentId))}`,
                        '_blank',
                        'noopener,noreferrer',
                    );
                }}
                // G4: مخرج «شحنة فارغة» — كان مدعوماً في المودال لكنه غير موصّل، فالحالة
                // الفارغة كانت طريقاً مسدوداً (نص يذكر شحنة فارغة بلا زر). يفتح شاشة شحنة
                // جديدة (تعمل SPA بلا reload بعد إصلاح G3).
                onCreateEmpty={() => {
                    setIsShipmentModalOpen(false);
                    navigate('/import-flow/new');
                }}
            />

            {/* G12: معالِج أول صفقة */}
            <FirstDealWizard
                isOpen={showWizard}
                onClose={() => setShowWizard(false)}
                suppliers={suppliers}
                onCreated={(dealId) => {
                    setShowWizard(false);
                    navigate(`/deals/${encodeURIComponent(dealId)}`);
                }}
            />

            {/* Modal اختيار العرض */}
            <PriceOfferSelectionModal
                isOpen={isOfferModalOpen}
                onClose={() => setIsOfferModalOpen(false)}
                onSelect={(id) => void handleCreateFromPriceOffer(id)}
                offers={priceOffers}
                compactMode={true}
            />

            {/* Print View Overlay */}
            {dealToPrint && (
                <div style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'white', overflowY: 'auto' }}>
                    <DealPrintView
                        deal={dealToPrint}
                        supplier={suppliers.find(s => s.id === dealToPrint.supplierId)}
                        currentUser={currentUser}
                        onClose={() => setDealToPrint(null)}
                        onEdit={() => {
                            setDealToPrint(null);
                            navigate(`/deals/${encodeURIComponent(dealToPrint.id)}`);
                        }}
                    />
                </div>
            )}
        </div>
    );
};
