import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Deal, DealItem, PriceOffer, User, DealStatus, Item, Supplier } from '../../types'; // 1. تأكد من استيراد Supplier
import { priceOffersService, itemsService, suppliersService } from '../../services/firestoreService'; // 2. استيراد suppliersService
import { dealsService } from '../../services/dealsService';
import { DealForm } from './deals/DealForm';
import { DealPrintView } from './deals/DealPrintView';
import {
    Plus, Handshake, Filter, Search, FileInput, TrendingUp,
    DollarSign, Package, CheckCircle, Clock, Users, Sparkles,
    BarChart3, ChevronDown, ChevronUp, RefreshCw, Eye, FileText,
    AlertCircle, Factory, Truck, Calendar, TrendingDown,
    Grid, List, Target, ArrowUpRight, Download, Upload, Settings,
    Printer, Edit2, Trash2
} from 'lucide-react';
import { LoadingSpinner } from '../LoadingSpinner';
import { PriceOfferSelectionModal } from './price-offers/PriceOfferSelectionModal';
import { DataGrid, Toolbar, StatusBadge as UIStatusBadge } from '../../components/ui';

interface DealManagementProps {
    currentUser: User;
    /** فتح قيد اليومية من شاشة الصفقة — null = قيد جديد للترحيل اليدوي */
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

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
    const [items, setItems] = useState<Item[]>([]);

    // 3. إضافة State للموردين
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);

    const [currentDeal, setCurrentDeal] = useState<Partial<Deal> | null>(null);
    const [dealToPrint, setDealToPrint] = useState<Deal | null>(null);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [filteredDeals, setFilteredDeals] = useState<Deal[]>([]);
    const [showFilters, setShowFilters] = useState(false);
    const [isOfferModalOpen, setIsOfferModalOpen] = useState(false);
    const [viewStyle, setViewStyle] = useState<'grid' | 'list'>('grid');
    const [compactMode, setCompactMode] = useState(true);

    const getStatusColor = (status: DealStatus): string => {
        const colors: Record<string, string> = {
            'initial':                   'bg-gray-100 text-gray-700 border-gray-200',
            'manufacturing_started':     'bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]',
            'first_payment_pending':     'bg-orange-50 text-orange-700 border-orange-200',
            'first_payment_done':        'bg-blue-50 text-blue-700 border-blue-200',
            'first_payment_confirmed':   'bg-green-50 text-green-700 border-green-200',
            'production_completed':      'bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]',
            'second_payment_pending':    'bg-orange-50 text-orange-700 border-orange-200',
            'second_payment_done':       'bg-blue-50 text-blue-700 border-blue-200',
            'second_payment_confirmed':  'bg-green-50 text-green-700 border-green-200',
            'shipping_preparation':      'bg-amber-50 text-amber-700 border-amber-200',
            'shipping_in_progress':      'bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]',
            'shipped':                   'bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]',
            'completed':                 'bg-emerald-100 text-emerald-800 border-emerald-200',
            'cancelled':                 'bg-red-50 text-red-700 border-red-200',
        };
        return colors[status] ?? colors['initial'];
    };

    const getStatusBadgeVariant = (status: string): string => {
        const variantMap: Record<string, string> = {
            'initial': 'neutral',
            'manufacturing_started': 'primary',
            'first_payment_pending': 'warning',
            'first_payment_done': 'primary',
            'first_payment_confirmed': 'success',
            'production_completed': 'primary',
            'second_payment_pending': 'warning',
            'second_payment_done': 'primary',
            'second_payment_confirmed': 'success',
            'shipping_preparation': 'warning',
            'shipping_in_progress': 'primary',
            'shipped': 'primary',
            'completed': 'success',
            'cancelled': 'danger',
        };
        return variantMap[status] || 'muted';
    };

    useEffect(() => {
        const path = (location.pathname || '/').replace(/\/$/, '') || '/';
        const onDealsRoute = path === '/deals' || path.startsWith('/deals/');
        if (!onDealsRoute) {
            navigate('/deals', { replace: true });
        }
    }, [location.pathname, navigate]);

    // جلب البيانات
    useEffect(() => {
        const unsubDeals = dealsService.subscribeToDeals((fetchedDeals) => {
            setDeals(fetchedDeals);
        });
        const unsubOffers = priceOffersService.subscribeToPriceOffers((offers) => {
            setPriceOffers(offers.filter(o =>
                o.status === 'approved_for_shipping' ||
                o.status === 'under_discussion'
            ));
        });
        const unsubItems = itemsService.subscribeToItems(setItems);

        // 4. جلب الموردين
        const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);

        setLoading(false);

        return () => {
            unsubDeals();
            unsubOffers();
            unsubItems();
            unsubSuppliers(); // تنظيف الاشتراك
        };
    }, []);

    // قراءة ?ref=D-XXXX للانتقال من صفحة قيد اليومية
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
            // إن وُجد ?ref= وتوفرت الصفقات → ابحث وافتح
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
                console.error(e);
                newFormInitRef.current = false;
                navigate('/deals', { replace: true });
            }
        })();
    }, [dealsPathMatch, deals, location.state, navigate, dealRefFromQuery]);

    // تصفية الصفقات
    useEffect(() => {
        let result = deals;

        if (searchTerm.trim()) {
            const term = searchTerm.toLowerCase();
            result = result.filter(deal =>
                deal.dealNumber?.toLowerCase().includes(term) ||
                deal.dealDescription?.toLowerCase().includes(term) ||
                deal.factoryName?.toLowerCase().includes(term) ||
                deal.originalOfferNumber?.toLowerCase().includes(term) ||
                deal.supplierSnapshot?.tradeName?.toLowerCase().includes(term) ||
                deal.supplierSnapshot?.alias?.toLowerCase().includes(term) ||
                deal.supplierSnapshot?.legalName?.toLowerCase().includes(term) ||
                deal.items?.some(item =>
                    item.name?.toLowerCase().includes(term) ||
                    item.categoryName?.toLowerCase().includes(term)
                )
            );
        }

        if (statusFilter !== 'all') {
            result = result.filter(deal => deal.status === statusFilter);
        }

        setFilteredDeals(result);
    }, [deals, searchTerm, statusFilter]);

    // Handlers
    const handleStatusChange = async (deal: Deal, newStatus: DealStatus) => {
        if (deal.status === newStatus) return;
        try {
            await dealsService.updateDealStatus(
                deal.id,
                newStatus,
                currentUser.id,
                currentUser.name,
                currentUser.role || 'user'
            );
        } catch (error) {
            console.error('Error updating status:', error);
            alert('فشل تحديث حالة الصفقة');
        }
    };

    const handleCreateNew = () => {
        newFormInitRef.current = false;
        navigate('/deals/new');
    };

    const handleCreateFromPriceOffer = async (priceOfferId: string) => {
        setIsOfferModalOpen(false);
        try {
            setLoading(true);
            const selectedOffer = priceOffers.find(o => o.id === priceOfferId);
            if (!selectedOffer) return;

            const dealNumber = await dealsService.getNextDealNumber();

            const dealData: Partial<Deal> = {
                priceOfferId: selectedOffer.id,
                originalOfferNumber: selectedOffer.offerNumber,
                dealNumber: dealNumber,
                supplierId: selectedOffer.supplierId,
                factoryName: selectedOffer.factoryName || "",
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
            console.error('Error:', error);
            alert('حدث خطأ أثناء التحضير');
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (deal: Deal) => {
        window.open(
            `${window.location.origin}/deals/${encodeURIComponent(deal.id)}`,
            '_blank',
            'noopener,noreferrer'
        );
    };

    const handleSave = async () => {
        setViewMode('list');
        setCurrentDeal(null);
        navigate('/deals');
    };

    const handleDelete = async (dealId: string) => {
        try {
            await dealsService.deleteDeal(dealId);
        } catch (error) {
            console.error('Error deleting deal:', error);
            alert('فشل حذف الصفقة');
        }
    };

    // إحصائيات مختصرة
    const stats = {
        total: deals.length,
        active: deals.filter(d => !['completed', 'cancelled'].includes(d.status)).length,
        pendingPayment: deals.filter(d => ['first_payment_pending', 'second_payment_pending'].includes(d.status)).length,
        inManufacturing: deals.filter(d => ['manufacturing_started', 'first_payment_confirmed', 'second_payment_confirmed'].includes(d.status)).length,
        shipped: deals.filter(d => ['shipped', 'completed'].includes(d.status)).length,
        totalValue: deals.reduce((sum, d) => sum + (d.totalAmount || 0), 0),
        pendingAmount: deals.reduce((sum, d) => sum + (d.remainingAmount || 0), 0)
    };

    // خيارات التصفية
    const statusOptions = [
        { value: 'all', label: 'الكل', count: deals.length },
        { value: 'initial', label: 'أولية', color: 'bg-gray-500' },
        { value: 'first_payment_pending', label: 'دفعة أولى', color: 'bg-orange-500' },
        { value: 'first_payment_done', label: 'دفعت أولى', color: 'bg-blue-500' },
        { value: 'first_payment_confirmed', label: 'أكيد أول', color: 'bg-green-500' },
        { value: 'production_completed', label: 'تم تصنيع', color: 'bg-[var(--color-primary)]' },
        { value: 'second_payment_pending', label: 'دفعة ثانية', color: 'bg-orange-500' },
        { value: 'second_payment_done', label: 'دفعت ثانية', color: 'bg-blue-500' },
        { value: 'second_payment_confirmed', label: 'أكيد ثاني', color: 'bg-green-500' },
        { value: 'shipping_preparation', label: 'تجهيز شحن', color: 'bg-amber-500' },
        { value: 'shipped', label: 'تم شحن', color: 'bg-[var(--color-primary)]' },
        { value: 'completed', label: 'مكتمل', color: 'bg-emerald-500' },
        { value: 'cancelled', label: 'ملغى', color: 'bg-red-500' }
    ];

    if (loading) return <LoadingSpinner />;

    return (
        <>
            <style>{`
                .deal-data-grid table tr { height: 34px; }
                .deal-data-grid table td { padding: 4px 8px; font-size: var(--font-size-sm); }
                .deal-data-grid table th { padding: 6px 8px; font-size: var(--font-size-sm); font-weight: 600; }
                .deal-data-grid table { border-collapse: collapse; }
            `}</style>
            <div className="min-h-screen p-3 md:p-4" style={{ backgroundColor: 'var(--color-background)' }}>
            <div className="max-w-[1600px] mx-auto space-y-4">
                {viewMode === 'list' ? (
                    <>
                        <div className="rounded-xl shadow-lg" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
                            <div className="p-4 md:p-5">
                                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 rounded-lg" style={{ backgroundColor: 'var(--color-primary-light)' }}>
                                            <Handshake className="w-6 h-6" style={{ color: 'var(--color-primary)' }} />
                                        </div>
                                        <div>
                                            <h1 className="text-xl font-bold" style={{ color: 'var(--color-text)' }}>
                                                إدارة الصفقات
                                            </h1>
                                            <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                                                {stats.total} صفقة • {stats.active} نشطة
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex flex-wrap gap-2">
                                        <button
                                            onClick={() => setShowFilters(!showFilters)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors hover:opacity-90"
                                            style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                                        >
                                            <Filter className="w-4 h-4" />
                                            تصفية
                                        </button>
                                        <button
                                            onClick={() => setIsOfferModalOpen(true)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-all hover:opacity-90"
                                            style={{ background: 'linear-gradient(90deg, var(--color-primary), var(--color-primary-dark))', color: 'white' }}
                                        >
                                            <FileInput className="w-4 h-4" />
                                            من عرض
                                            {priceOffers.length > 0 && (
                                                <span className="bg-white/20 text-xs px-1.5 rounded-full">
                                                    {priceOffers.length}
                                                </span>
                                            )}
                                        </button>
                                        <button
                                            onClick={handleCreateNew}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-all hover:opacity-90 font-medium"
                                            style={{ background: 'linear-gradient(90deg, var(--color-success), var(--color-success-dark, var(--color-success)))', color: 'white' }}
                                        >
                                            <Plus className="w-4 h-4" />
                                            صفقة جديدة
                                        </button>
                                    </div>
                                </div>

                                <div className="flex flex-col sm:flex-row gap-3">
                                    {/* <div className="flex-1 relative">
                                        <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                                        <input
                                            type="text"
                                            placeholder="ابحث برقم الصفقة، المورد، المنتج..."
                                            value={searchTerm}
                                            onChange={(e) => setSearchTerm(e.target.value)}
                                            className="w-full p-2.5 pr-10 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                        />
                                    </div> */}

                                    {/* <div className="flex gap-2">
                                        <div className="flex bg-gray-100 dark:bg-gray-700 p-1 rounded-lg">
                                            <button
                                                onClick={() => setViewStyle('grid')}
                                                className={`p-1.5 rounded-md ${viewStyle === 'grid' ? 'bg-white dark:bg-gray-800 shadow-sm' : ''}`}
                                            >
                                                <Grid className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => setViewStyle('list')}
                                                className={`p-1.5 rounded-md ${viewStyle === 'list' ? 'bg-white dark:bg-gray-800 shadow-sm' : ''}`}
                                            >
                                                <List className="w-4 h-4" />
                                            </button>
                                        </div>
                                        <button
                                            onClick={() => setCompactMode(!compactMode)}
                                            className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
                                            title={compactMode ? "وضع موسع" : "وضع مضغوط"}
                                        >
                                            <Settings className="w-4 h-4" />
                                        </button>
                                    </div> */}
                                </div>

                                {showFilters && (
                                    <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                                        <div className="flex flex-wrap gap-2">
                                            {statusOptions.map((option) => (
                                                <button
                                                    key={option.value}
                                                    onClick={() => setStatusFilter(option.value)}
                                                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-full transition-all ${statusFilter === option.value
                                                        ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-700'
                                                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                                                        }`}
                                                >
                                                    <span className={`w-2 h-2 rounded-full ${option.color}`}></span>
                                                    {option.label}
                                                    {option.count && (
                                                        <span className="text-xs bg-white/50 dark:bg-gray-800/50 px-1.5 rounded-full">
                                                            {option.count}
                                                        </span>
                                                    )}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* البطاقات الإحصائية (Stats) */}
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                            <div className="p-3 rounded-xl" style={{ background: 'linear-gradient(135deg, var(--color-primary-light), var(--color-primary-lighter))', border: '1px solid var(--color-primary)' }}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs" style={{ color: 'var(--color-primary)' }}>إجمالي الصفقات</p>
                                        <p className="text-lg font-bold" style={{ color: 'var(--color-primary-dark)' }}>{stats.total}</p>
                                    </div>
                                    <Target className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
                                </div>
                            </div>
                            <div className="p-3 rounded-xl" style={{ background: 'linear-gradient(135deg, var(--color-success-light), var(--color-success-lighter))', border: '1px solid var(--color-success)' }}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs" style={{ color: 'var(--color-success)' }}>نشطة</p>
                                        <p className="text-lg font-bold" style={{ color: 'var(--color-success-dark)' }}>{stats.active}</p>
                                    </div>
                                    <TrendingUp className="w-5 h-5" style={{ color: 'var(--color-success)' }} />
                                </div>
                            </div>
                            <div className="p-3 rounded-xl" style={{ background: 'linear-gradient(135deg, var(--color-warning-light), var(--color-warning-lighter))', border: '1px solid var(--color-warning)' }}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs" style={{ color: 'var(--color-warning)' }}>بانتظار دفع</p>
                                        <p className="text-lg font-bold" style={{ color: 'var(--color-warning-dark)' }}>{stats.pendingPayment}</p>
                                    </div>
                                    <Clock className="w-5 h-5" style={{ color: 'var(--color-warning)' }} />
                                </div>
                            </div>
                            <div className="p-3 rounded-xl" style={{ background: 'linear-gradient(135deg, var(--color-purple-light, #f3e8ff), var(--color-purple-lighter, #ede9fe))', border: '1px solid var(--color-purple, #a855f7)' }}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs" style={{ color: 'var(--color-purple-dark, #9333ea)' }}>في التصنيع</p>
                                        <p className="text-lg font-bold" style={{ color: 'var(--color-purple-dark, #7e22ce)' }}>{stats.inManufacturing}</p>
                                    </div>
                                    <Factory className="w-5 h-5" style={{ color: 'var(--color-purple, #a855f7)' }} />
                                </div>
                            </div>
                            <div className="p-3 rounded-xl" style={{ background: 'linear-gradient(135deg, var(--color-teal-light, #ccfbf1), var(--color-teal-lighter, #99f6e4))', border: '1px solid var(--color-teal, #14b8a6)' }}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs" style={{ color: 'var(--color-teal-dark, #0d9488)' }}>تم الشحن</p>
                                        <p className="text-lg font-bold" style={{ color: 'var(--color-teal-dark, #0f766e)' }}>{stats.shipped}</p>
                                    </div>
                                    <Truck className="w-5 h-5" style={{ color: 'var(--color-teal, #14b8a6)' }} />
                                </div>
                            </div>
                            <div className="p-3 rounded-xl" style={{ background: 'linear-gradient(135deg, var(--color-info-light), var(--color-info-lighter))', border: '1px solid var(--color-info)' }}>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs" style={{ color: 'var(--color-info)' }}>القيمة الإجمالية</p>
                                        <p className="text-lg font-bold" style={{ color: 'var(--color-info-dark)' }}>
                                            ${(stats.totalValue / 1000).toFixed(1)}K
                                        </p>
                                    </div>
                                    <DollarSign className="w-5 h-5" style={{ color: 'var(--color-info)' }} />
                                </div>
                            </div>
                        </div>

                        {/* قائمة الصفقات */}
                        <div className="rounded-xl shadow-lg" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
                            <div className="p-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                                    <div className="flex items-center gap-2">
                                        <div className="p-1.5 rounded-lg" style={{ backgroundColor: 'var(--color-primary-light)' }}>
                                            <Package className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />
                                        </div>
                                        <div>
                                            <h2 className="font-bold text-sm" style={{ color: 'var(--color-text)' }}>
                                                الصفقات ({filteredDeals.length})
                                            </h2>
                                            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                                                {statusFilter !== 'all' && `مرشحة حسب: ${statusOptions.find(o => o.value === statusFilter)?.label}`}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs">
                                        {filteredDeals.length !== deals.length && (
                                            <button
                                                onClick={() => { setSearchTerm(''); setStatusFilter('all'); }}
                                                className="flex items-center gap-1 px-2 py-1 rounded-lg hover:opacity-90"
                                                style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)' }}
                                            >
                                                <RefreshCw className="w-3 h-3" />
                                                إعادة تعيين
                                            </button>
                                        )}
                                        <span style={{ color: 'var(--color-text-muted)' }}>|</span>
                                        <span style={{ color: 'var(--color-text-muted)' }}>
                                            آخر تحديث: {new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="p-3 deal-data-grid">
                                <div className="border border-[var(--color-border)] rounded-lg overflow-hidden" style={{ backgroundColor: 'var(--color-surface)' }}>
                                    <Toolbar
                                        search={searchTerm}
                                        onSearch={setSearchTerm}
                                        searchPlaceholder="بحث برقم الصفقة، المورد، المنتج..."
                                        filters={
                                            <div className="flex items-center gap-1">
                                                <button
                                                    onClick={() => setStatusFilter('all')}
                                                    className={`px-2 py-1 text-xs rounded transition-colors ${statusFilter === 'all' ? 'bg-[var(--color-primary)] text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'}`}
                                                >
                                                    الكل
                                                </button>
                                                {statusOptions.slice(1).slice(0, 6).map((opt) => (
                                                    <button
                                                        key={opt.value}
                                                        onClick={() => setStatusFilter(opt.value)}
                                                        className={`px-2 py-1 text-xs rounded transition-colors ${statusFilter === opt.value ? 'bg-[var(--color-primary)] text-white' : 'bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-hover)]'}`}
                                                    >
                                                        {opt.label}
                                                    </button>
                                                ))}
                                            </div>
                                        }
                                        actions={
                                            <button
                                                onClick={handleCreateNew}
                                                className="flex items-center gap-1 px-2 py-1 text-xs bg-[var(--color-primary)] text-white rounded hover:opacity-90 transition-opacity"
                                            >
                                                <Plus className="w-3 h-3" />
                                                صفقة جديدة
                                            </button>
                                        }
                                    />
                                    {filteredDeals.length > 0 ? (
                                        <DataGrid
                                            columns={[
                                                {
                                                    key: 'dealNumber',
                                                    header: 'رقم الصفقة',
                                                    width: '100px',
                                                    sortable: true,
                                                },
                                                {
                                                    key: 'partner_name',
                                                    header: 'المورد',
                                                    render: (deal: Deal) => {
                                                        const supplier = suppliers.find(s => s.id === deal.supplierId);
                                                        if (supplier) {
                                                            return supplier.alias && supplier.alias.trim() !== ''
                                                                ? `${supplier.tradeName} (${supplier.alias})`
                                                                : supplier.tradeName;
                                                        }
                                                        return deal.factoryName || 'غير محدد';
                                                    },
                                                },
                                                {
                                                    key: 'status',
                                                    header: 'الحالة',
                                                    width: '120px',
                                                    render: (deal: Deal) => {
                                                        const statusLabel = statusOptions.find(o => o.value === deal.status)?.label || deal.status;
                                                        const variant = getStatusBadgeVariant(deal.status);
                                                        return <UIStatusBadge status={variant} />;
                                                    },
                                                },
                                                {
                                                    key: 'totalAmount',
                                                    header: 'المبلغ',
                                                    width: '110px',
                                                    sortable: true,
                                                    align: 'end',
                                                    render: (deal: Deal) => {
                                                        const amount = deal.totalAmount || 0;
                                                        return <span className="font-mono text-[var(--color-text)]">${amount.toLocaleString()}</span>;
                                                    },
                                                },
                                                {
                                                    key: 'createdAt',
                                                    header: 'التاريخ',
                                                    width: '100px',
                                                    sortable: true,
                                                    render: (deal: Deal) => {
                                                        if (!deal.createdAt) return '-';
                                                        const date = new Date(deal.createdAt);
                                                        if (isNaN(date.getTime())) return '-';
                                                        return date.toLocaleDateString('ar-EG', { day: '2-digit', month: '2-digit', year: '2-digit' });
                                                    },
                                                },
                                                {
                                                    key: 'actions',
                                                    header: '',
                                                    width: '100px',
                                                    align: 'end',
                                                    render: (deal: Deal, idx: number) => (
                                                        <div className="flex items-center justify-end gap-1">
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); handleEdit(deal); }}
                                                                className="p-1 rounded hover:bg-[var(--color-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
                                                                title="تعديل"
                                                            >
                                                                <Edit2 className="w-3.5 h-3.5" />
                                                            </button>
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); setDealToPrint(deal); }}
                                                                className="p-1 rounded hover:bg-[var(--color-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
                                                                title="طباعة"
                                                            >
                                                                <Printer className="w-3.5 h-3.5" />
                                                            </button>
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); handleDelete(deal.id); }}
                                                                className="p-1 rounded hover:bg-[var(--color-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-danger)]"
                                                                title="حذف"
                                                            >
                                                                <Trash2 className="w-3.5 h-3.5" />
                                                            </button>
                                                        </div>
                                                    ),
                                                },
                                            ]}
                                            data={filteredDeals}
                                            keyField="id"
                                            onRowClick={(deal) => handleEdit(deal)}
                                            rowClassName={() => 'hover:bg-[var(--color-hover)] transition-colors'}
                                        />
                                    ) : (
                                        <div className="py-10 text-center" style={{ backgroundColor: 'var(--color-surface)' }}>
                                            <div className="inline-flex p-4 rounded-xl mb-4" style={{ backgroundColor: 'var(--color-background)' }}>
                                                <Search className="w-8 h-8 text-[var(--color-text-muted)]" />
                                            </div>
                                            <h3 className="font-medium mb-2" style={{ color: 'var(--color-text)' }}>
                                                لا توجد صفقات
                                            </h3>
                                            <p className="text-sm mb-4 max-w-xs mx-auto" style={{ color: 'var(--color-text-muted)' }}>
                                                {searchTerm
                                                    ? `لا توجد صفقات تطابق "${searchTerm}"`
                                                    : 'قم بإنشاء أول صفقة أو تغيير عوامل التصفية'}
                                            </p>
                                            <div className="flex gap-2 justify-center">
                                                <button
                                                    onClick={() => { setSearchTerm(''); setStatusFilter('all'); }}
                                                    className="px-3 py-1.5 text-sm rounded transition-colors"
                                                    style={{ backgroundColor: 'var(--color-primary)', color: 'white' }}
                                                >
                                                    عرض الكل
                                                </button>
                                                <button
                                                    onClick={handleCreateNew}
                                                    className="px-3 py-1.5 text-sm rounded transition-colors"
                                                    style={{ backgroundColor: 'var(--color-success)', color: 'white' }}
                                                >
                                                    + صفقة جديدة
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Modal اختيار العرض */}
                        <PriceOfferSelectionModal
                            isOpen={isOfferModalOpen}
                            onClose={() => setIsOfferModalOpen(false)}
                            onSelect={handleCreateFromPriceOffer}
                            offers={priceOffers}
                            compactMode={compactMode}
                        />
                    </>
                ) : (
                    // ... (نمط الـ Form) ...
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                        <div className="p-4 border-b border-gray-100 dark:border-gray-700">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <button
                                        onClick={() => {
                                            setViewMode('list');
                                            setCurrentDeal(null);
                                            navigate('/deals');
                                        }}
                                        className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                                    >
                                        <ArrowUpRight className="w-5 h-5 text-gray-500 rotate-180" />
                                    </button>
                                    <h1 className="font-bold text-gray-900 dark:text-white">
                                        {currentDeal?.id ? 'تعديل الصفقة' : 'صفقة جديدة'}
                                    </h1>
                                    {currentDeal?.dealNumber && (
                                        <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-sm">
                                            {currentDeal.dealNumber}
                                        </span>
                                    )}
                                    {currentDeal?.originalOfferNumber && (
                                        <span
                                            title={currentDeal.originalOfferNumber}
                                            className="px-2 py-1 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] rounded text-sm max-w-[260px] truncate"
                                        >
                                            {currentDeal.originalOfferNumber}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
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
                            compactMode={compactMode}
                            onOpenAccountingJournal={onOpenAccountingJournal}
                        />
                    </div>
                )}
            </div>
            {/* Print View Overlay */}
            {/* Print View Overlay */}
            {dealToPrint && (
                <div className="fixed inset-0 z-50 bg-white overflow-y-auto">
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
        </>
    );
};