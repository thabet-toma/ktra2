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
import { Plus, FileInput, Printer, Edit2, Trash2, RefreshCw } from 'lucide-react';
import { LoadingSpinner } from '../LoadingSpinner';
import { PriceOfferSelectionModal } from './price-offers/PriceOfferSelectionModal';
import { AseelDenseTable, type DenseColumn } from '../aseel/AseelDenseTable';
import { useAseelIndexKeymap } from '../aseel/useAseelIndexKeymap';

interface DealManagementProps {
    currentUser: User;
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

const STATUS_LABELS: Record<string, string> = {
    initial:                  'أولية',
    manufacturing_started:    'بدأ التصنيع',
    first_payment_pending:    'دفعة أولى',
    first_payment_done:       'دفعت أولى',
    first_payment_confirmed:  'أكيد أول',
    production_completed:     'تم التصنيع',
    second_payment_pending:   'دفعة ثانية',
    second_payment_done:      'دفعت ثانية',
    second_payment_confirmed: 'أكيد ثاني',
    shipping_preparation:     'تجهيز شحن',
    shipping_in_progress:     'شحن قيد التنفيذ',
    shipped:                  'تم الشحن',
    completed:                'مكتمل',
    cancelled:                'ملغى',
};

const STATUS_COLORS: Record<string, string> = {
    initial:                  'var(--aseel-ink-soft)',
    manufacturing_started:    'var(--aseel-accent, #1857a4)',
    first_payment_pending:    'var(--aseel-warn, #b8800a)',
    first_payment_done:       'var(--aseel-accent, #1857a4)',
    first_payment_confirmed:  'var(--aseel-ok, #267346)',
    production_completed:     'var(--aseel-accent, #1857a4)',
    second_payment_pending:   'var(--aseel-warn, #b8800a)',
    second_payment_done:      'var(--aseel-accent, #1857a4)',
    second_payment_confirmed: 'var(--aseel-ok, #267346)',
    shipping_preparation:     'var(--aseel-warn, #b8800a)',
    shipping_in_progress:     'var(--aseel-accent, #1857a4)',
    shipped:                  'var(--aseel-accent, #1857a4)',
    completed:                'var(--aseel-ok, #267346)',
    cancelled:                'var(--aseel-danger, #c00)',
};

const fmtAmt = (n: number) =>
    n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtDate = (s: string | undefined) => {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString('ar'); } catch { return s; }
};

export const DealManagement: React.FC<DealManagementProps> = ({
    currentUser,
    onOpenAccountingJournal,
}) => {
    const navigate = useNavigate();
    const location = useLocation();
    const newFormInitRef = useRef(false);

    const dealsPathMatch = useMemo(() => {
        const path = (location.pathname || '/').replace(/\/$/, '') || '/';
        if (path !== '/deals' && !path.startsWith('/deals/')) return null;
        if (path === '/deals') return { mode: 'list' as const };
        const m = path.match(/^\/deals\/(.+)$/);
        const seg = m ? decodeURIComponent(m[1]) : '';
        if (seg === 'new') return { mode: 'new' as const };
        if (!seg) return { mode: 'list' as const };
        return { mode: 'deal' as const, id: seg };
    }, [location.pathname]);

    const [viewMode, setViewMode] = useState<'list' | 'form'>('list');
    const [deals, setDeals] = useState<Deal[]>([]);
    const [priceOffers, setPriceOffers] = useState<PriceOffer[]>([]);
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [currentDeal, setCurrentDeal] = useState<Partial<Deal> | null>(null);
    const [dealToPrint, setDealToPrint] = useState<Deal | null>(null);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [isOfferModalOpen, setIsOfferModalOpen] = useState(false);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        const path = (location.pathname || '/').replace(/\/$/, '') || '/';
        if (path !== '/deals' && !path.startsWith('/deals/')) {
            navigate('/deals', { replace: true });
        }
    }, [location.pathname, navigate]);

    useEffect(() => {
        const unsubDeals = dealsService.subscribeToDeals((fetchedDeals) => {
            setDeals(fetchedDeals);
            setLoading(false);
        });
        const unsubOffers = priceOffersService.subscribeToPriceOffers((offers) => {
            setPriceOffers(offers.filter(o =>
                o.status === 'approved_for_shipping' || o.status === 'under_discussion'
            ));
        });
        const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
        return () => { unsubDeals(); unsubOffers(); unsubSuppliers(); };
    }, []);

    const dealRefFromQuery = useMemo(() => {
        const p = new URLSearchParams(location.search);
        return p.get('ref') || '';
    }, [location.search]);

    useEffect(() => {
        if (!dealsPathMatch) return;
        if (dealsPathMatch.mode === 'list') {
            newFormInitRef.current = false;
            setViewMode('list');
            setCurrentDeal(null);
            if (dealRefFromQuery && deals.length > 0) {
                const target = deals.find(
                    d => String(d.dealNumber).toUpperCase() === dealRefFromQuery.toUpperCase()
                );
                if (target) {
                    setCurrentDeal({ ...target });
                    setViewMode('form');
                }
            }
            return;
        }
        if (dealsPathMatch.mode === 'deal') {
            const id = dealsPathMatch.id;
            if (deals.length === 0) return;
            const target = deals.find((d) => String(d.id) === String(id));
            if (target) {
                setCurrentDeal({ ...target });
                setViewMode('form');
            } else {
                navigate('/deals', { replace: true });
            }
            return;
        }
        const draft = (location.state as { draftDeal?: Partial<Deal> } | null)?.draftDeal;
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
    }, [dealsPathMatch, deals, location.state, navigate, dealRefFromQuery]);

    const filteredDeals = useMemo(() => {
        let result = deals;
        if (search.trim()) {
            const term = search.toLowerCase();
            result = result.filter(deal =>
                deal.dealNumber?.toLowerCase().includes(term) ||
                deal.dealDescription?.toLowerCase().includes(term) ||
                deal.factoryName?.toLowerCase().includes(term) ||
                deal.originalOfferNumber?.toLowerCase().includes(term) ||
                deal.supplierSnapshot?.tradeName?.toLowerCase().includes(term) ||
                deal.supplierSnapshot?.alias?.toLowerCase().includes(term) ||
                suppliers.find(s => s.id === deal.supplierId)?.name?.toLowerCase().includes(term) ||
                deal.items?.some(item =>
                    item.name?.toLowerCase().includes(term) ||
                    item.categoryName?.toLowerCase().includes(term)
                )
            );
        }
        if (statusFilter !== 'all') {
            result = result.filter(deal => deal.status === statusFilter);
        }
        return result;
    }, [deals, search, statusFilter, suppliers]);

    const stats = useMemo(() => ({
        total: deals.length,
        active: deals.filter(d => !['completed', 'cancelled'].includes(d.status)).length,
        completed: deals.filter(d => d.status === 'completed').length,
        totalValue: deals.reduce((s, d) => s + (d.totalAmount || 0), 0),
    }), [deals]);

    const handleCreateNew = () => {
        newFormInitRef.current = false;
        navigate('/deals/new');
    };

    const handleCreateFromPriceOffer = async (priceOfferId: string) => {
        setIsOfferModalOpen(false);
        const selectedOffer = priceOffers.find(o => o.id === priceOfferId);
        if (!selectedOffer) return;
        try {
            const dealNumber = await dealsService.getNextDealNumber();
            const dealData: Partial<Deal> = {
                priceOfferId: selectedOffer.id,
                originalOfferNumber: selectedOffer.offerNumber,
                dealNumber,
                supplierId: selectedOffer.supplierId,
                factoryName: selectedOffer.factoryName || '',
                totalAmount: selectedOffer.grandTotal,
                remainingAmount: selectedOffer.grandTotal,
                subtotal: selectedOffer.subtotal,
                shippingCost: selectedOffer.shippingCost || 0,
                status: 'initial',
                internalNotes: selectedOffer.internalNotes || '',
                items: selectedOffer.items?.map(item => ({
                    ...item,
                    id: crypto.randomUUID(),
                    itemId: item.itemId || item.id,
                } as DealItem)) || [],
                payments: [],
                statusHistory: [{
                    status: 'initial',
                    timestamp: new Date().toISOString(),
                    notes: 'تم إنشاء الصفقة من عرض السعر',
                    changedBy: currentUser.id
                }],
                quoteImages: selectedOffer.quote_images || [],
                quotePdfs: selectedOffer.quote_pdfs || []
            };
            newFormInitRef.current = false;
            navigate('/deals/new', { state: { draftDeal: dealData } });
        } catch (error) {
            // console suppressed
        }
    };

    const handleEdit = (deal: Deal) => {
        // الأصل: يفتح في تاب جديد كي لا يفقد المستخدم سياق القائمة
        window.open(
            `${window.location.origin}/deals/${encodeURIComponent(deal.id)}`,
            '_blank',
            'noopener,noreferrer',
        );
    };

    const handleSave = () => {
        setViewMode('list');
        setCurrentDeal(null);
        navigate('/deals');
    };

    const handleDelete = async (dealId: string) => {
        if (!window.confirm('حذف الصفقة؟')) return;
        try {
            await dealsService.deleteDeal(dealId);
        } catch (error) {
            // console suppressed
            alert('فشل حذف الصفقة');
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
            width: '140px',
            render: (d) => (
                <span style={{ color: STATUS_COLORS[d.status] || 'inherit', fontWeight: 500 }}>
                    {STATUS_LABELS[d.status] || d.status}
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
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); handleEdit(d); }}
                        title="تعديل"
                    >
                        <Edit2 style={{ width: 13, height: 13 }} />
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

    return (
        <div dir="rtl" data-skin="aseel" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
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
                    className="aseel-input"
                    style={{ width: 200 }}
                    placeholder="بحث برقم الصفقة، المورد، المنتج… (F6)"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                {/* فلتر الحالة */}
                <select
                    className="aseel-input"
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
                    className="aseel-toolbtn"
                    onClick={() => { setSearch(''); setStatusFilter('all'); }}
                    title="إعادة تعيين الفلاتر"
                >
                    <RefreshCw style={{ width: 14, height: 14 }} />
                </button>
                <button
                    className="aseel-toolbtn"
                    onClick={() => setIsOfferModalOpen(true)}
                    title="إنشاء من عرض سعر"
                >
                    <FileInput style={{ width: 14, height: 14 }} />
                    {priceOffers.length > 0 && <span style={{ marginRight: 2 }}>({priceOffers.length})</span>}
                    من عرض
                </button>
                <button
                    className="aseel-toolbtn"
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
                onRowDoubleClick={(d) => handleEdit(d)}
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
