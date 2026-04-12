import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Deal, DealItem, PriceOffer, User, DealStatus, Item, Supplier } from '../../types'; // 1. تأكد من استيراد Supplier
import { priceOffersService, itemsService, suppliersService } from '../../services/firestoreService'; // 2. استيراد suppliersService
import { dealsService } from '../../services/dealsService';
import { DealList } from './deals/DealList';
import { DealForm } from './deals/DealForm';
import { DealPrintView } from './deals/DealPrintView';
import {
    Plus, Handshake, Filter, Search, FileInput, TrendingUp,
    DollarSign, Package, CheckCircle, Clock, Users, Sparkles,
    BarChart3, ChevronDown, ChevronUp, RefreshCw, Eye, FileText,
    AlertCircle, Factory, Truck, Calendar, TrendingDown,
    Grid, List, Target, ArrowUpRight, Download, Upload, Settings
} from 'lucide-react';
import { LoadingSpinner } from '../LoadingSpinner';
import { PriceOfferSelectionModal } from './price-offers/PriceOfferSelectionModal';

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
            'manufacturing_started':     'bg-sky-50 text-sky-700 border-sky-200',
            'first_payment_pending':     'bg-orange-50 text-orange-700 border-orange-200',
            'first_payment_done':        'bg-blue-50 text-blue-700 border-blue-200',
            'first_payment_confirmed':   'bg-green-50 text-green-700 border-green-200',
            'production_completed':      'bg-purple-50 text-purple-700 border-purple-200',
            'second_payment_pending':    'bg-orange-50 text-orange-700 border-orange-200',
            'second_payment_done':       'bg-blue-50 text-blue-700 border-blue-200',
            'second_payment_confirmed':  'bg-green-50 text-green-700 border-green-200',
            'shipping_preparation':      'bg-amber-50 text-amber-700 border-amber-200',
            'shipping_in_progress':      'bg-teal-50 text-teal-700 border-teal-200',
            'shipped':                   'bg-teal-100 text-teal-800 border-teal-300',
            'completed':                 'bg-emerald-100 text-emerald-800 border-emerald-200',
            'cancelled':                 'bg-red-50 text-red-700 border-red-200',
        };
        return colors[status] ?? colors['initial'];
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
        { value: 'production_completed', label: 'تم تصنيع', color: 'bg-purple-500' },
        { value: 'second_payment_pending', label: 'دفعة ثانية', color: 'bg-orange-500' },
        { value: 'second_payment_done', label: 'دفعت ثانية', color: 'bg-blue-500' },
        { value: 'second_payment_confirmed', label: 'أكيد ثاني', color: 'bg-green-500' },
        { value: 'shipping_preparation', label: 'تجهيز شحن', color: 'bg-amber-500' },
        { value: 'shipped', label: 'تم شحن', color: 'bg-teal-500' },
        { value: 'completed', label: 'مكتمل', color: 'bg-emerald-500' },
        { value: 'cancelled', label: 'ملغى', color: 'bg-red-500' }
    ];

    if (loading) return <LoadingSpinner />;

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 p-3 md:p-4">
            <div className="max-w-[1600px] mx-auto space-y-4">
                {viewMode === 'list' ? (
                    <>
                        {/* الهيدر وبقية العناصر كما هي ... */}
                        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
                            <div className="p-4 md:p-5">
                                {/* ... (محتوى الهيدر والفلاتر كما هو) ... */}
                                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-gradient-to-r from-blue-100 to-purple-100 dark:from-blue-900/30 dark:to-purple-900/30 rounded-lg">
                                            <Handshake className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <div>
                                            <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                                                إدارة الصفقات
                                            </h1>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">
                                                {stats.total} صفقة • {stats.active} نشطة
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex flex-wrap gap-2">
                                        <button
                                            onClick={() => setShowFilters(!showFilters)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                                        >
                                            <Filter className="w-4 h-4" />
                                            تصفية
                                        </button>
                                        <button
                                            onClick={() => setIsOfferModalOpen(true)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:from-indigo-600 hover:to-purple-600 transition-all"
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
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-lg hover:from-blue-700 hover:to-blue-800 transition-all font-medium"
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
                            {/* ... (نفس كود الإحصائيات السابق) ... */}
                            <div className="bg-gradient-to-r from-blue-50 to-blue-100 dark:from-blue-900/30 dark:to-blue-900/50 p-3 rounded-xl border border-blue-200 dark:border-blue-800/30">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs text-blue-600 dark:text-blue-400">إجمالي الصفقات</p>
                                        <p className="text-lg font-bold text-blue-900 dark:text-blue-300">{stats.total}</p>
                                    </div>
                                    <Target className="w-5 h-5 text-blue-500" />
                                </div>
                            </div>
                            <div className="bg-gradient-to-r from-green-50 to-emerald-100 dark:from-green-900/30 dark:to-emerald-900/50 p-3 rounded-xl border border-green-200 dark:border-green-800/30">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs text-green-600 dark:text-green-400">نشطة</p>
                                        <p className="text-lg font-bold text-green-900 dark:text-green-300">{stats.active}</p>
                                    </div>
                                    <TrendingUp className="w-5 h-5 text-green-500" />
                                </div>
                            </div>
                            <div className="bg-gradient-to-r from-orange-50 to-amber-100 dark:from-orange-900/30 dark:to-amber-900/50 p-3 rounded-xl border border-orange-200 dark:border-orange-800/30">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs text-orange-600 dark:text-orange-400">بانتظار دفع</p>
                                        <p className="text-lg font-bold text-orange-900 dark:text-orange-300">{stats.pendingPayment}</p>
                                    </div>
                                    <Clock className="w-5 h-5 text-orange-500" />
                                </div>
                            </div>
                            <div className="bg-gradient-to-r from-purple-50 to-violet-100 dark:from-purple-900/30 dark:to-violet-900/50 p-3 rounded-xl border border-purple-200 dark:border-purple-800/30">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs text-purple-600 dark:text-purple-400">في التصنيع</p>
                                        <p className="text-lg font-bold text-purple-900 dark:text-purple-300">{stats.inManufacturing}</p>
                                    </div>
                                    <Factory className="w-5 h-5 text-purple-500" />
                                </div>
                            </div>
                            <div className="bg-gradient-to-r from-teal-50 to-cyan-100 dark:from-teal-900/30 dark:to-cyan-900/50 p-3 rounded-xl border border-teal-200 dark:border-teal-800/30">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs text-teal-600 dark:text-teal-400">تم الشحن</p>
                                        <p className="text-lg font-bold text-teal-900 dark:text-teal-300">{stats.shipped}</p>
                                    </div>
                                    <Truck className="w-5 h-5 text-teal-500" />
                                </div>
                            </div>
                            <div className="bg-gradient-to-r from-indigo-50 to-blue-100 dark:from-indigo-900/30 dark:to-blue-900/50 p-3 rounded-xl border border-indigo-200 dark:border-indigo-800/30">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs text-indigo-600 dark:text-indigo-400">القيمة الإجمالية</p>
                                        <p className="text-lg font-bold text-indigo-900 dark:text-indigo-300">
                                            ${(stats.totalValue / 1000).toFixed(1)}K
                                        </p>
                                    </div>
                                    <DollarSign className="w-5 h-5 text-indigo-500" />
                                </div>
                            </div>
                        </div>

                        {/* قائمة الصفقات */}
                        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
                            <div className="p-4 border-b border-gray-100 dark:border-gray-700">
                                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                                    <div className="flex items-center gap-2">
                                        <div className="p-1.5 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                                            <Package className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <div>
                                            <h2 className="font-bold text-gray-900 dark:text-white text-sm">
                                                الصفقات ({filteredDeals.length})
                                            </h2>
                                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                                {statusFilter !== 'all' && `مرشحة حسب: ${statusOptions.find(o => o.value === statusFilter)?.label}`}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs">
                                        {filteredDeals.length !== deals.length && (
                                            <button
                                                onClick={() => { setSearchTerm(''); setStatusFilter('all'); }}
                                                className="flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
                                            >
                                                <RefreshCw className="w-3 h-3" />
                                                إعادة تعيين
                                            </button>
                                        )}
                                        <span className="text-gray-400">|</span>
                                        <span className="text-gray-500 dark:text-gray-400">
                                            آخر تحديث: {new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="p-3">
                                {filteredDeals.length > 0 ? (
                                    <DealList
                                        deals={filteredDeals}
                                        onEdit={handleEdit}
                                        onPrint={(deal) => setDealToPrint(deal)}
                                        onDelete={handleDelete}
                                        // تمرير الموردين
                                        allSuppliers={suppliers}
                                        compactMode={compactMode}
                                    />
                                ) : (
                                    <div className="py-10 text-center">
                                        {/* ... (حالة لا توجد صفقات) ... */}
                                        <div className="inline-flex p-4 bg-gray-100 dark:bg-gray-900 rounded-xl mb-4">
                                            <Search className="w-8 h-8 text-gray-400 dark:text-gray-600" />
                                        </div>
                                        <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-2">
                                            لا توجد صفقات
                                        </h3>
                                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 max-w-xs mx-auto">
                                            {searchTerm
                                                ? `لا توجد صفقات تطابق "${searchTerm}"`
                                                : 'قم بإنشاء أول صفقة أو تغيير عوامل التصفية'}
                                        </p>
                                        <div className="flex gap-2 justify-center">
                                            <button
                                                onClick={() => { setSearchTerm(''); setStatusFilter('all'); }}
                                                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                                            >
                                                عرض الكل
                                            </button>
                                            <button
                                                onClick={handleCreateNew}
                                                className="px-3 py-1.5 text-sm bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-700 hover:to-emerald-700"
                                            >
                                                + صفقة جديدة
                                            </button>
                                        </div>
                                    </div>
                                )}
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
                                            className="px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded text-sm max-w-[260px] truncate"
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
    );
};