import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import logisticsService from '../../services/logisticsService';
import accountingService from '../../services/accountingService';
import cloudinaryService from '../../services/cloudinaryService';

// ── Lucide-style SVG icons (inline, no dependency needed) ──────────────────
const Icon = ({ d, size = 16, color = 'currentColor', className = '' }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24"
        fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d={d} />
    </svg>
);
const SaveIcon = () => <Icon d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z M17 21v-8H7v8 M7 3v5h8" />;
const ChevronLeftIcon = () => <Icon d="M15 18l-6-6 6-6" />;
const InfoIcon = () => <Icon d="M12 20h9 M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />;
const PackageIcon = () => <Icon d="M12 2l9 4.9V17L12 22l-9-4.9V7L12 2z M12 22V12 M12 12L3 7.1 M12 12l9-4.9" />;
const CreditCardIcon = () => <Icon d="M1 4h22v16H1z M1 10h22" />;
const FileTextIcon = () => <Icon d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8" />;
const PlusIcon = () => <Icon d="M12 5v14 M5 12h14" />;
const TrashIcon = () => <Icon d="M3 6h18 M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6 M10 11v6 M14 11v6 M9 6V4h6v2" />;
const FactoryIcon = () => <Icon d="M2 20V9l6-5 6 5V20H2z M14 20v-8l6-5v13 M6 20v-5h4v5" />;
const CalendarIcon = () => <Icon d="M3 4h18v18H3z M8 4V2 M16 4V2 M3 10h18" />;
const LinkIcon = () => <Icon d="M15 7h3a5 5 0 0 1 0 10h-3 M9 17H6A5 5 0 0 1 6 7h3 M8 12h8" />;
const UploadIcon = () => <Icon d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12" />;
const WalletIcon = () => <Icon d="M21 12V7H5a2 2 0 0 1 0-4h14v4 M3 5v14a2 2 0 0 0 2 2h16v-5 M18 12a2 2 0 0 0 0 4h3v-4z" />;
const AlertIcon = () => <Icon d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01" />;
const CheckIcon = () => <Icon d="M20 6L9 17l-5-5" />;
const EyeIcon = () => <Icon d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z" />;

// ── Status helpers matching the EXACT original design ──────────────────────
const OP_STATUSES = {
    Open: { label: 'أولية', cls: 'bg-gray-100 text-gray-700 border-gray-200' },
    Manufacturing: { label: 'قيد التصنيع', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
    ReadyToShip: { label: 'تجهيز الشحن', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
    Shipping: { label: 'جاري الشحن', cls: 'bg-teal-50 text-teal-700 border-teal-200' },
    Clearance: { label: 'تخليص جمركي', cls: 'bg-purple-50 text-purple-700 border-purple-200' },
    Delivered: { label: 'تم التسليم', cls: 'bg-green-50 text-green-700 border-green-200' },
    Closed: { label: 'ملغاة', cls: 'bg-red-50 text-red-700 border-red-200' },
};
const PAY_STATUSES = {
    Unpaid: { label: 'غير مدفوعة', cls: 'bg-red-50 text-red-700 border-red-200' },
    'Partially Paid': { label: 'مدفوعة جزئياً', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
    'Fully Paid': { label: 'مدفوعة كلياً', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
};

// ── CollapsibleSection — matches original exactly ─────────────────────────
const CollapsibleSection = ({ title, icon: IconComp, children, defaultOpen = true }) => {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm mb-4">
            <button
                onClick={() => setOpen(!open)}
                className="w-full flex justify-between items-center px-5 py-3.5 text-right border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors rounded-t-xl"
            >
                <span className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100">
                    {IconComp && <IconComp />}
                    {title}
                </span>
                <span className="text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
            </button>
            {open && <div className="p-5">{children}</div>}
        </div>
    );
};

// ── Main DealForm ─────────────────────────────────────────────────────────
const DealForm = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const isEdit = !!id;

    const [activeTab, setActiveTab] = useState('info');
    const [partners, setPartners] = useState([]);
    const [products, setProducts] = useState([]);
    const [saving, setSaving] = useState(false);
    const [uploading, setUploading] = useState(false);

    const [formData, setFormData] = useState({
        ref_number: '', description: '', partner: '', partner_name: '',
        original_offer_number: '', supplier_invoice_number: '', pi_number: '',
        alibaba_link: '', notes: '', certificates: '', factory_name: '',
        order_date: new Date().toISOString().split('T')[0],
        order_status: 'Open', payment_status: 'Unpaid',
        incoterms: 'FOB', shipping_method: 'Sea', payment_method: 'T/T 30%',
        production_days: 0, delivery_days: 0, warranty_duration: 0,
        total_cbm: 0, total_weight_kg: 0,
        currency_rate: 3.75, shipping_cost_estimate: 0,
        discount_amount: 0, tax_rate: 0, tax_amount: 0, tax_type: 'percentage',
        is_shipping_included: false,
        items: [], payments: []
    });

    useEffect(() => { loadData(); }, [id]);

    const loadData = async () => {
        try {
            const [pData, prData] = await Promise.all([
                accountingService.getPartners(),
                logisticsService.getProducts()
            ]);
            setPartners(pData.filter(p => !p.is_customer));
            setProducts(prData);
            if (isEdit) {
                const deal = await logisticsService.getDeal(id);
                if (deal) {
                    if (!deal.items) deal.items = [];
                    if (!deal.payments) deal.payments = [];
                    setFormData(deal);
                }
            }
        } catch (e) { console.error(e); }
    };

    // ── Calculations ────────────────────────────────────────────────────
    const calcSubtotal = () => (formData.items || []).reduce((s, i) => s + Number(i.quantity || 0) * Number(i.unit_price || 0), 0);
    const calcDiscount = () => Number(formData.discount_amount || 0);
    const calcTax = () => {
        const base = Math.max(0, calcSubtotal() - calcDiscount());
        if (formData.tax_type === 'amount') return Number(formData.tax_amount || 0);
        return base * (Number(formData.tax_rate || 0) / 100);
    };
    const calcShipping = () => formData.is_shipping_included ? 0 : Number(formData.shipping_cost_estimate || 0);
    const calcTotal = () => Math.max(0, calcSubtotal() - calcDiscount()) + calcTax() + calcShipping();
    const totalAmount = calcTotal();
    const paidAmount = (formData.payments || []).filter(p => ['Paid', 'Confirmed'].includes(p.status)).reduce((s, p) => s + Number(p.amount || 0), 0);
    const remainingAmount = Math.max(0, totalAmount - paidAmount);
    const payPct = totalAmount > 0 ? (paidAmount / totalAmount) * 100 : 0;

    // ── Save ─────────────────────────────────────────────────────────────
    const handleSave = async () => {
        setSaving(true);
        try {
            const payload = { ...formData, total_amount: totalAmount.toFixed(2) };
            if (isEdit) { await logisticsService.updateDeal(id, payload); alert('✅ تم تحديث الصفقة'); }
            else { await logisticsService.createDeal(payload); navigate('/logistics/deals'); }
        } catch (e) { alert('❌ فشل الحفظ: ' + (e.response?.data ? JSON.stringify(e.response.data) : e.message)); }
        finally { setSaving(false); }
    };

    // ── Items ─────────────────────────────────────────────────────────────
    const addItem = () => setFormData(p => ({ ...p, items: [...p.items, { product: '', quantity: 1, unit_price: 0, notes: '' }] }));
    const changeItem = (i, f, v) => {
        const items = [...formData.items];
        items[i][f] = v;
        if (f === 'product') { const pr = products.find(p => p.id === v); items[i].product_name = pr?.name_ar || ''; }
        setFormData(p => ({ ...p, items }));
    };
    const removeItem = (i) => { const items = [...formData.items]; items.splice(i, 1); setFormData(p => ({ ...p, items })); };

    // ── Payments ──────────────────────────────────────────────────────────
    const addPayment = () => {
        const n = (formData.payments?.length || 0) + 1;
        setFormData(p => ({ ...p, payments: [...(p.payments || []), { payment_number: n, title: `دفعة ${n}`, percentage: 0, amount: 0, amount_local: 0, status: 'Pending', due_date: '', claim_doc: '', bank_swift_image: '' }] }));
    };
    const changePayment = (i, f, v) => {
        const payments = [...formData.payments];
        const pay = payments[i];
        const total = calcTotal();
        pay[f] = v;
        if (f === 'percentage') { pay.amount = (total * (parseFloat(v) / 100)).toFixed(2); pay.amount_local = (Number(pay.amount) * Number(formData.currency_rate || 3.75)).toFixed(2); }
        else if (f === 'amount') { pay.percentage = total > 0 ? ((parseFloat(v) / total) * 100).toFixed(2) : 0; pay.amount_local = (parseFloat(v) * Number(formData.currency_rate || 3.75)).toFixed(2); }
        setFormData(p => ({ ...p, payments }));
    };
    const removePayment = (i) => { const payments = [...formData.payments]; payments.splice(i, 1); setFormData(p => ({ ...p, payments })); };

    const uploadFile = async (i, type, file) => {
        if (!file) return;
        setUploading(true);
        try {
            const r = await cloudinaryService.uploadFile(file);
            const payments = [...formData.payments];
            payments[i][type === 'claim' ? 'claim_doc' : 'bank_swift_image'] = r.url;
            if (type === 'claim' && payments[i].status === 'Pending') payments[i].status = 'ClaimUploaded';
            setFormData(p => ({ ...p, payments }));
        } catch { alert('❌ فشل رفع الملف'); }
        finally { setUploading(false); }
    };

    // ── Status badges ─────────────────────────────────────────────────────
    const opCfg = OP_STATUSES[formData.order_status] || OP_STATUSES.Open;
    const payCfg = PAY_STATUSES[formData.payment_status] || PAY_STATUSES.Unpaid;

    // ── Input helpers ─────────────────────────────────────────────────────
    const set = (f, v) => setFormData(p => ({ ...p, [f]: v }));
    const field = (label, key, type = 'text', extra = {}) => (
        <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500 dark:text-gray-400 font-medium text-right">{label}</label>
            <input
                type={type} value={formData[key] || ''}
                onChange={e => set(key, e.target.value)}
                className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-right bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                {...extra}
            />
        </div>
    );
    const select = (label, key, options) => (
        <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500 dark:text-gray-400 font-medium text-right">{label}</label>
            <select
                value={formData[key] || ''} onChange={e => set(key, e.target.value)}
                className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-right bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
            >
                {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
        </div>
    );

    const tabs = [
        { key: 'info', label: 'المعلومات', Icon: InfoIcon },
        { key: 'items', label: 'المنتجات', Icon: PackageIcon, badge: formData.items?.length || 0 },
        { key: 'payments', label: 'الدفعات', Icon: CreditCardIcon, badge: formData.payments?.length || 0 },
        { key: 'documents', label: 'المرفقات', Icon: FileTextIcon },
    ];

    return (
        <div dir="rtl" className="bg-gray-50 dark:bg-gray-900 min-h-screen p-4 md:p-6">

            {/* ── TOP HEADER (sticky like original) ── */}
            <div className="sticky top-0 z-20 bg-gray-50/95 dark:bg-gray-900/95 backdrop-blur py-3 border-b border-gray-200 dark:border-gray-800 mb-6">
                {/* Row 1: Title + Statuses + Actions */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-3">

                    {/* Left: Back + Title */}
                    <div className="flex items-center gap-3">
                        <button onClick={() => navigate('/logistics/deals')}
                            className="p-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 transition-colors">
                            <ChevronLeftIcon />
                        </button>
                        <div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <h1 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                    <span className="text-blue-600 text-sm"><InfoIcon /></span>
                                    {formData.ref_number ? `صفقة #${formData.ref_number}` : 'صفقة جديدة'}
                                </h1>
                                {formData.original_offer_number && (
                                    <span className="bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-xs px-2 py-0.5 rounded-full font-medium border border-purple-200 flex items-center gap-1">
                                        <FileTextIcon /> عرض #{formData.original_offer_number}
                                    </span>
                                )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-gray-500 dark:text-gray-400">
                                <span className="flex items-center gap-1">
                                    <FactoryIcon />
                                    <span className="font-medium text-blue-600 dark:text-blue-400">
                                        {formData.partner_name || formData.factory_name || 'يرجى اختيار المورد'}
                                    </span>
                                </span>
                                <span className="text-gray-300">|</span>
                                <span className="flex items-center gap-1">
                                    <CalendarIcon />
                                    {formData.order_date || new Date().toLocaleDateString('ar-EG')}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Right: Statuses + Save */}
                    <div className="flex gap-2 items-center">
                        {/* Operational Status Badge */}
                        <select value={formData.order_status} onChange={e => set('order_status', e.target.value)}
                            className={`px-2 py-1 rounded text-xs font-medium border cursor-pointer focus:outline-none ${opCfg.cls}`}>
                            {Object.entries(OP_STATUSES).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
                        </select>
                        {/* Payment Status Badge */}
                        <select value={formData.payment_status} onChange={e => set('payment_status', e.target.value)}
                            className={`px-2 py-1 rounded text-xs font-medium border cursor-pointer focus:outline-none ${payCfg.cls}`}>
                            {Object.entries(PAY_STATUSES).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
                        </select>
                        <button
                            onClick={handleSave} disabled={saving}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 text-sm font-medium transition-colors">
                            {saving ? (
                                <><div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" /> جاري الحفظ...</>
                            ) : (<><SaveIcon /> حفظ</>)}
                        </button>
                    </div>
                </div>

                {/* Row 2: Tabs (matching original exactly) */}
                <div className="flex border-b border-gray-200 dark:border-gray-700">
                    {tabs.map(t => (
                        <button key={t.key} onClick={() => setActiveTab(t.key)}
                            className={`flex-1 py-2 text-sm font-medium border-b-2 transition-colors flex items-center justify-center gap-1.5 ${activeTab === t.key ? 'border-blue-500 text-blue-600 dark:text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'}`}>
                            <t.Icon />
                            {t.label}
                            {t.badge !== undefined && t.badge > 0 && (
                                <span className="bg-blue-100 text-blue-700 text-xs px-1.5 rounded-full">{t.badge}</span>
                            )}
                        </button>
                    ))}
                </div>
            </div>

            {/* ── KPI STATS (matching original grid exactly) ── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-6">
                <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg border border-blue-100 dark:border-blue-800/30">
                    <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">القيمة الإجمالية</p>
                    <p className="text-lg font-bold text-blue-900 dark:text-blue-300">${totalAmount.toLocaleString()}</p>
                </div>
                <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg border border-green-100 dark:border-green-800/30">
                    <p className="text-xs text-green-600 dark:text-green-400 font-medium">المدفوع</p>
                    <p className="text-lg font-bold text-green-900 dark:text-green-300">${paidAmount.toLocaleString()}</p>
                </div>
                <div className="bg-amber-50 dark:bg-amber-900/20 p-3 rounded-lg border border-amber-100 dark:border-amber-800/30">
                    <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">المتبقي</p>
                    <p className="text-lg font-bold text-amber-900 dark:text-amber-300">${remainingAmount.toLocaleString()}</p>
                </div>
                <div className="bg-purple-50 dark:bg-purple-900/20 p-3 rounded-lg border border-purple-100 dark:border-purple-800/30">
                    <p className="text-xs text-purple-600 dark:text-purple-400 font-medium">نسبة الدفع</p>
                    <div className="flex items-center justify-between">
                        <p className="text-lg font-bold text-purple-900 dark:text-purple-300">{payPct.toFixed(1)}%</p>
                        <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${Math.min(payPct, 100)}%` }} />
                        </div>
                    </div>
                </div>
            </div>

            {/* ══════════════════ TAB: INFO ══════════════════ */}
            {activeTab === 'info' && (
                <div>
                    {/* Basic Info */}
                    <CollapsibleSection title="معلومات الصفقة الأساسية" icon={InfoIcon}>
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                            <div className="flex flex-col gap-1">
                                <label className="text-xs text-gray-500 font-medium text-right">المورد / المصنع</label>
                                <select value={formData.partner || ''} onChange={e => {
                                    const p = partners.find(x => String(x.id) === String(e.target.value));
                                    set('partner', e.target.value);
                                    set('partner_name', p?.name || '');
                                    set('factory_name', p?.name || '');
                                }} className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-right bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all">
                                    <option value="">-- اختر المورد --</option>
                                    {partners.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                                </select>
                            </div>
                            {field('رقم الصفقة / المرجعي', 'ref_number')}
                            {field('رقم الفاتورة (Supplier Invoice)', 'supplier_invoice_number')}
                            {field('رقم العرض الأصلي', 'original_offer_number')}
                            {field('تاريخ الصفقة', 'order_date', 'date')}
                            {field('PI Number', 'pi_number')}
                            <div className="sm:col-span-2 flex flex-col gap-1">
                                {field('الوصف / اسم الصفقة', 'description')}
                            </div>
                            <div className="sm:col-span-2 flex flex-col gap-1">
                                <label className="text-xs text-gray-500 font-medium text-right flex items-center gap-1 justify-end">
                                    <LinkIcon /> رابط علي بابا (Alibaba Order Link)
                                </label>
                                <input type="url" value={formData.alibaba_link || ''} onChange={e => set('alibaba_link', e.target.value)}
                                    className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-right bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-orange-400 transition-all" />
                            </div>
                            <div className="sm:col-span-2 flex flex-col gap-1">
                                <label className="text-xs text-gray-500 font-medium text-right">ملاحظات داخلية</label>
                                <textarea value={formData.notes || ''} onChange={e => set('notes', e.target.value)} rows={2}
                                    className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-right bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all" />
                            </div>
                        </div>
                    </CollapsibleSection>

                    {/* Terms & Shipping */}
                    <CollapsibleSection title="شروط الشحن والتسليم" icon={() => <span>🚚</span>}>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                            {select('Incoterms', 'incoterms', ['FOB','EXW','CIF','CFR','DAP','DDP','FCA'].map(v => ({ value: v, label: v })))}
                            {select('طريقة الشحن', 'shipping_method', ['Sea','Air','Land','Express'].map(v => ({ value: v, label: v })))}
                            {select('طريقة الدفع', 'payment_method', ['T/T 30%','T/T 50%','L/C','D/P','D/A','Cash'].map(v => ({ value: v, label: v })))}
                            {field('أيام الإنتاج', 'production_days', 'number')}
                            {field('أيام الشحن / التسليم', 'delivery_days', 'number')}
                            {field('مدة الضمان (أشهر)', 'warranty_duration', 'number')}
                            {field('الوزن الكلي (CBM)', 'total_cbm', 'number')}
                            {field('الوزن الكلي (Kg)', 'total_weight_kg', 'number')}
                            <div className="cols-span-2 sm:col-span-2">
                                {field('الشهادات المطلوبة (Certificates)', 'certificates')}
                            </div>
                        </div>
                    </CollapsibleSection>

                    {/* Financial Summary */}
                    <CollapsibleSection title="الملخص المالي" icon={() => <span>💰</span>}>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                            {field('سعر الصرف (ILS/USD)', 'currency_rate', 'number')}
                            {field('تكلفة الشحن التقديرية ($)', 'shipping_cost_estimate', 'number')}
                            {field('الخصم ($)', 'discount_amount', 'number')}
                            {field('الضريبة %', 'tax_rate', 'number')}
                        </div>
                        {/* Summary Bar (like original) */}
                        <div className="mt-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-4 py-3 flex flex-wrap gap-4 text-sm">
                            <span className="text-gray-600 dark:text-gray-300">قيمة البضاعة: <strong className="text-blue-700">${calcSubtotal().toFixed(2)}</strong></span>
                            <span className="text-gray-600">-خصم: <strong className="text-red-600">${calcDiscount().toFixed(2)}</strong></span>
                            <span className="text-gray-600">+ضريبة: <strong className="text-green-600">${calcTax().toFixed(2)}</strong></span>
                            <span className="text-gray-600">+شحن: <strong className="text-amber-600">${calcShipping().toFixed(2)}</strong></span>
                            <span className="font-bold text-blue-800 dark:text-blue-300">الإجمالي: ${totalAmount.toFixed(2)}</span>
                        </div>
                    </CollapsibleSection>
                </div>
            )}

            {/* ══════════════════ TAB: ITEMS ══════════════════ */}
            {activeTab === 'items' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                    <div className="flex justify-between items-center px-5 py-3.5 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
                            <PackageIcon /> قائمة المنتجات والبضائع
                        </span>
                        <div className="flex items-center gap-3">
                            <span className="text-xs text-gray-400">{formData.items?.length || 0} منتج • الإجمالي: <strong>${calcSubtotal().toFixed(2)}</strong></span>
                            <button onClick={addItem}
                                className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors">
                                <PlusIcon /> إضافة منتج
                            </button>
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-gray-50 dark:bg-gray-700">
                                <tr>
                                    {['#','المنتج','الكمية','السعر ($)','الإجمالي ($)','ملاحظات',''].map(h => (
                                        <th key={h} className="px-3 py-2.5 text-right text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-600">{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {(formData.items || []).map((item, i) => (
                                    <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                        <td className="px-3 py-2 text-gray-400 text-xs">{i + 1}</td>
                                        <td className="px-3 py-2">
                                            <select value={item.product || ''} onChange={e => changeItem(i, 'product', e.target.value)}
                                                className="w-full min-w-[160px] border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                                                <option value="">-- اختر منتجاً --</option>
                                                {products.map(p => <option key={p.id} value={p.id}>{p.name_ar} ({p.sku || '-'})</option>)}
                                            </select>
                                        </td>
                                        <td className="px-3 py-2">
                                            <input type="number" value={item.quantity} onChange={e => changeItem(i, 'quantity', e.target.value)} min="0"
                                                className="w-20 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-center text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                        </td>
                                        <td className="px-3 py-2">
                                            <input type="number" value={item.unit_price} onChange={e => changeItem(i, 'unit_price', e.target.value)} min="0"
                                                className="w-24 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-center text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                        </td>
                                        <td className="px-3 py-2 font-semibold text-gray-800 dark:text-gray-200">
                                            ${(Number(item.quantity || 0) * Number(item.unit_price || 0)).toFixed(2)}
                                        </td>
                                        <td className="px-3 py-2">
                                            <input type="text" value={item.notes || ''} onChange={e => changeItem(i, 'notes', e.target.value)} placeholder="ملاحظة..."
                                                className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                        </td>
                                        <td className="px-3 py-2">
                                            <button onClick={() => removeItem(i)} className="text-red-400 hover:text-red-600 transition-colors"><TrashIcon /></button>
                                        </td>
                                    </tr>
                                ))}
                                {!formData.items?.length && (
                                    <tr><td colSpan={7} className="text-center py-10 text-gray-400 text-sm italic">لا توجد منتجات — اضغط «إضافة منتج»</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                    {formData.items?.length > 0 && (
                        <div className="px-5 py-3 bg-gray-900 text-white flex flex-wrap gap-5 text-sm rounded-b-xl justify-end">
                            <span>المجموع: <strong>${calcSubtotal().toFixed(2)}</strong></span>
                            <span>-خصم: <strong className="text-red-400">${calcDiscount().toFixed(2)}</strong></span>
                            <span>+ضريبة: <strong className="text-green-400">${calcTax().toFixed(2)}</strong></span>
                            <span>+شحن: <strong className="text-amber-400">${calcShipping().toFixed(2)}</strong></span>
                            <span className="text-lg font-bold">= ${totalAmount.toFixed(2)}</span>
                        </div>
                    )}
                </div>
            )}

            {/* ══════════════════ TAB: PAYMENTS ══════════════════ */}
            {activeTab === 'payments' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                    <div className="flex justify-between items-center flex-wrap gap-2 px-5 py-3.5 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
                            <CreditCardIcon /> جدول الدفعات
                        </span>
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded-full">مدفوع: ${paidAmount.toFixed(2)}</span>
                            <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full">متبقي: ${remainingAmount.toFixed(2)}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full border ${Math.abs(totalAmount - (formData.payments||[]).reduce((s,p)=>s+Number(p.amount||0),0)) < 0.5 ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
                                فرق: ${(totalAmount - (formData.payments||[]).reduce((s,p)=>s+Number(p.amount||0),0)).toFixed(2)}
                            </span>
                            <button onClick={addPayment} className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors">
                                <PlusIcon /> إضافة دفعة
                            </button>
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-blue-50 dark:bg-blue-900/20">
                                <tr>
                                    {['#','الوصف','الاستحقاق','النسبة %','المبلغ ($)','المبلغ (₪)','الحالة','مستندات',''].map(h => (
                                        <th key={h} className="px-3 py-2.5 text-right text-xs font-semibold text-blue-700 dark:text-blue-300 border-b border-blue-100">{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {(formData.payments || []).map((pay, i) => {
                                    const statusCls = pay.is_posted ? 'bg-green-100 text-green-700' : pay.status === 'Paid' || pay.status === 'Confirmed' ? 'bg-green-100 text-green-700' : pay.status === 'ClaimUploaded' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600';
                                    return (
                                        <tr key={i} className={`hover:bg-gray-50 dark:hover:bg-gray-700/30 ${pay.is_posted ? 'bg-green-50/30' : ''}`}>
                                            <td className="px-3 py-2 text-gray-400 text-xs font-semibold">{i + 1}</td>
                                            <td className="px-3 py-2">
                                                <input type="text" value={pay.title || ''} onChange={e => changePayment(i, 'title', e.target.value)}
                                                    className="w-28 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-right bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                            </td>
                                            <td className="px-3 py-2">
                                                <input type="date" value={pay.due_date || ''} onChange={e => changePayment(i, 'due_date', e.target.value)}
                                                    className="w-32 border border-gray-200 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                            </td>
                                            <td className="px-3 py-2">
                                                <input type="number" value={pay.percentage || 0} onChange={e => changePayment(i, 'percentage', e.target.value)} min="0" max="100"
                                                    className="w-16 border border-gray-200 rounded-lg px-2 py-1.5 text-center text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                            </td>
                                            <td className="px-3 py-2">
                                                <input type="number" value={pay.amount || 0} onChange={e => changePayment(i, 'amount', e.target.value)} min="0"
                                                    className="w-24 border border-gray-200 rounded-lg px-2 py-1.5 text-center font-semibold text-sm bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                                            </td>
                                            <td className="px-3 py-2 text-gray-500 font-mono text-xs">{Number(pay.amount_local || 0).toLocaleString()} ₪</td>
                                            <td className="px-3 py-2">
                                                <div className="flex flex-col gap-1">
                                                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusCls}`}>
                                                        {pay.is_posted ? '✓ مرحلة' : pay.status === 'Paid' ? 'مدفوعة' : pay.status === 'Confirmed' ? 'مؤكدة' : pay.status === 'ClaimUploaded' ? 'مطالبة' : 'معلقة'}
                                                    </span>
                                                    <select value={pay.status || 'Pending'} onChange={e => changePayment(i, 'status', e.target.value)}
                                                        className="text-xs border border-gray-200 rounded px-1 py-0.5 bg-white dark:bg-gray-700 focus:outline-none">
                                                        <option value="Pending">معلقة</option>
                                                        <option value="ClaimUploaded">مطالبة مرفوعة</option>
                                                        <option value="Paid">مدفوعة</option>
                                                        <option value="Confirmed">مؤكدة</option>
                                                    </select>
                                                </div>
                                            </td>
                                            <td className="px-3 py-2">
                                                <div className="flex items-center gap-1">
                                                    <label title="رفع مطالبة" className={`cursor-pointer p-1 rounded ${pay.claim_doc ? 'text-blue-600 bg-blue-50' : 'text-gray-400 hover:text-blue-500'}`}>
                                                        <input hidden type="file" onChange={e => uploadFile(i, 'claim', e.target.files[0])} />
                                                        <FileTextIcon />
                                                    </label>
                                                    <label title="رفع سليب" className={`cursor-pointer p-1 rounded ${pay.bank_swift_image ? 'text-green-600 bg-green-50' : 'text-gray-400 hover:text-green-500'}`}>
                                                        <input hidden type="file" onChange={e => uploadFile(i, 'swift', e.target.files[0])} />
                                                        <UploadIcon />
                                                    </label>
                                                    {pay.id && !pay.is_posted && (pay.status === 'Paid' || pay.status === 'Confirmed') && (
                                                        <button title="ترحيل محاسبي" onClick={async () => {
                                                            if (window.confirm('هل تريد ترحيل الدفعة وإنشاء قيد محاسبي؟')) {
                                                                try { await logisticsService.postPaymentToAccounting(id, pay.id); alert('✅ تم'); loadData(); }
                                                                catch (e) { alert('❌ ' + e.message); }
                                                            }
                                                        }} className="p-1 text-indigo-600 hover:bg-indigo-50 rounded">
                                                            <WalletIcon />
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-3 py-2">
                                                <button onClick={() => removePayment(i)} className="text-red-400 hover:text-red-600"><TrashIcon /></button>
                                            </td>
                                        </tr>
                                    );
                                })}
                                {!formData.payments?.length && (
                                    <tr><td colSpan={9} className="text-center py-8 text-gray-400 text-sm italic">لم يتم إضافة دفعات — اضغط «إضافة دفعة»</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ══════════════════ TAB: DOCUMENTS ══════════════════ */}
            {activeTab === 'documents' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {[{ label: 'رفع Proforma Invoice / Quote', icon: '📄' }, { label: 'رفع ملفات PDF أخرى', icon: '📎' }].map((it, i) => (
                            <label key={i} className="flex flex-col items-center justify-center border-2 border-dashed border-gray-200 rounded-xl p-8 cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-all group">
                                <input hidden type="file" multiple />
                                <span className="text-4xl mb-2">{it.icon}</span>
                                <span className="text-sm text-gray-600 group-hover:text-blue-600 font-medium">{it.label}</span>
                                <span className="text-xs text-gray-400 mt-1">انقر للاختيار</span>
                            </label>
                        ))}
                    </div>
                    <div className="mt-4">
                        <label className="text-xs text-gray-500 font-medium">ملاحظات الشحن</label>
                        <textarea value={formData.shipment_notes || ''} onChange={e => set('shipment_notes', e.target.value)} rows={3} placeholder="ملاحظات خاصة بالشحنة..."
                            className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-right bg-white dark:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                </div>
            )}

            {/* Uploading indicator */}
            {uploading && (
                <div className="fixed bottom-5 right-5 bg-gray-900/90 text-white px-4 py-2.5 rounded-xl flex items-center gap-2 shadow-xl text-sm z-50">
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    جاري رفع الملف...
                </div>
            )}
        </div>
    );
};

export default DealForm;
