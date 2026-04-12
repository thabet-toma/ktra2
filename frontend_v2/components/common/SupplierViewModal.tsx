import React, { useState, useEffect } from 'react';
import { Supplier } from '@/types';
import { suppliersService } from '@/services/firestoreService';
import {
    X, Building, MapPin, Phone, Mail, MessageSquare,
    DollarSign, Calendar, Factory, Ship,
    Smartphone, Hash, Globe, CreditCard, UserCircle2,
    Copy, ExternalLink, TrendingUp, Clock,
    FileText, Edit // 🟢 1. استيراد أيقونة التعديل
} from 'lucide-react';
import { LoadingSpinner } from '../LoadingSpinner';

interface SupplierViewModalProps {
    isOpen: boolean;
    onClose: () => void;
    supplierId: string | null;
    onEdit?: (supplier: Supplier) => void;
}

const getTypeInfo = (type?: string) => {
    switch (type) {
        case 'factory': return { icon: <Factory className="w-4 h-4" />, text: 'مورد', color: 'text-purple-600 bg-purple-50 border-purple-200' };
        case 'shipping_agent': return { icon: <Ship className="w-4 h-4" />, text: 'وكيل شحن', color: 'text-blue-600 bg-blue-50 border-blue-200' };
        case 'service_provider': return { icon: <FileText className="w-4 h-4" />, text: 'مخلّص جمركي', color: 'text-amber-700 bg-amber-50 border-amber-200' };
        case 'local_company': return { icon: <Building className="w-4 h-4" />, text: 'ناقل محلي', color: 'text-green-700 bg-green-50 border-green-200' };
        case 'international_trader': return { icon: <Globe className="w-4 h-4" />, text: 'مورد دولي', color: 'text-indigo-700 bg-indigo-50 border-indigo-200' };
        default: return { icon: <Building className="w-4 h-4" />, text: 'مورد تجاري', color: 'text-gray-600 bg-gray-50 border-gray-200' };
    }
};

const CopyButton = ({ text }: { text: string }) => (
    <button
        onClick={() => navigator.clipboard.writeText(text)}
        className="p-1 text-gray-400 hover:text-blue-600 transition-colors opacity-0 group-hover:opacity-100"
        title="نسخ"
    >
        <Copy className="w-3 h-3" />
    </button>
);

const DetailRow = ({ icon, label, value, isLink = false, copyable = false }: any) => {
    if (!value) return null;
    return (
        <div className="flex items-start gap-3 py-2 group">
            <div className="mt-0.5 text-gray-400 dark:text-gray-500">{icon}</div>
            <div className="flex-1 min-w-0">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">{label}</p>
                <div className="flex items-center gap-2">
                    {isLink ? (
                        <a href={value} target="_blank" rel="noreferrer" className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline truncate block">
                            {value}
                        </a>
                    ) : (
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{value}</p>
                    )}
                    {copyable && <CopyButton text={value} />}
                </div>
            </div>
        </div>
    );
};

export const SupplierViewModal: React.FC<SupplierViewModalProps> = ({
    isOpen,
    onClose,
    supplierId,
    onEdit // 🟢 استقبال الدالة
}) => {
    const [supplier, setSupplier] = useState<Supplier | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen && supplierId) fetchSupplier();
        else setSupplier(null);
    }, [isOpen, supplierId]);

    const fetchSupplier = async () => {
        if (!supplierId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await suppliersService.getSupplierById(supplierId);
            data ? setSupplier(data) : setError('المورد غير موجود');
        } catch (err) {
            console.error(err);
            setError('حدث خطأ في تحميل البيانات');
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const typeInfo = getTypeInfo(supplier?.type);

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col border border-gray-200 dark:border-gray-700">

                {/* 1. Compact Header */}
                <div className="flex-none bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700 p-4 flex justify-between items-start">
                    <div className="flex gap-4">
                        <div className="relative">
                            {supplier?.logoUrl ? (
                                <img src={supplier.logoUrl} alt="Logo" className="w-16 h-16 rounded-lg border border-gray-200 dark:border-gray-700 object-cover shadow-sm" />
                            ) : (
                                <div className="w-16 h-16 rounded-lg bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 flex items-center justify-center">
                                    <Building className="w-8 h-8 text-gray-400" />
                                </div>
                            )}
                            <div className={`absolute -bottom-2 -right-2 px-2 py-0.5 rounded text-[10px] font-bold border ${typeInfo.color} shadow-sm`}>
                                {typeInfo.text}
                            </div>
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white leading-tight">
                                {supplier?.tradeName}
                            </h2>
                            {supplier?.alias && (
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 font-medium">
                                    ({supplier.alias})
                                </p>
                            )}
                            <div className="flex items-center gap-3 mt-2">
                                <span className="inline-flex items-center gap-1 text-xs text-gray-500 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                                    <Hash className="w-3 h-3" /> {supplier?.supplierId}
                                </span>
                                {supplier?.country && (
                                    <span className="inline-flex items-center gap-1 text-xs text-gray-500 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                                        <Globe className="w-3 h-3" /> {supplier.country}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* 🟢 3. أزرار التحكم (تعديل + إغلاق) */}
                    <div className="flex items-center gap-2">
                        {onEdit && supplier && (
                            <button
                                onClick={() => onEdit(supplier)}
                                className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-full transition-colors"
                                title="تعديل المورد"
                            >
                                <Edit className="w-5 h-5" />
                            </button>
                        )}
                        <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full text-gray-400 transition-colors">
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* 2. Scrollable Body (نفس الكود السابق تماماً) */}
                <div className="flex-1 overflow-y-auto">
                    {loading ? (
                        <div className="h-64 flex items-center justify-center"><LoadingSpinner /></div>
                    ) : error ? (
                        <div className="p-8 text-center text-red-500">{error}</div>
                    ) : supplier ? (
                        <div className="grid grid-cols-1 md:grid-cols-12 min-h-full">
                            {/* ... نفس محتوى البودي السابق ... */}
                            <div className="md:col-span-4 bg-gray-50/80 dark:bg-gray-900/50 border-l border-gray-200 dark:border-gray-700 p-5 space-y-6">
                                {/* Contact, Address, Sales Rep */}
                                <div>
                                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                        <Phone className="w-3 h-3" /> معلومات الاتصال
                                    </h3>
                                    <div className="space-y-1 bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-100 dark:border-gray-700 shadow-sm">
                                        <DetailRow icon={<Mail className="w-4 h-4" />} label="البريد الإلكتروني" value={supplier.email} copyable />
                                        <div className="border-t border-gray-50 dark:border-gray-700 my-1"></div>
                                        <DetailRow icon={<Phone className="w-4 h-4" />} label="الهاتف" value={supplier.phone} copyable />
                                        <div className="border-t border-gray-50 dark:border-gray-700 my-1"></div>
                                        <DetailRow icon={<Smartphone className="w-4 h-4" />} label="الجوال" value={supplier.mobile} copyable />
                                    </div>
                                </div>
                                {/* ... (باقي المحتوى) ... */}
                                {(supplier.street || supplier.city) && (
                                    <div>
                                        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                            <MapPin className="w-3 h-3" /> العنوان
                                        </h3>
                                        <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-100 dark:border-gray-700 shadow-sm text-sm text-gray-700 dark:text-gray-300">
                                            <p className="font-medium">{supplier.street}</p>
                                            <p className="text-gray-500 mt-1">
                                                {[supplier.city, supplier.region, supplier.postalCode, supplier.country].filter(Boolean).join('، ')}
                                            </p>
                                        </div>
                                    </div>
                                )}
                                {(supplier.salesRepName || supplier.salesRepPhone) && (
                                    <div>
                                        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                            <UserCircle2 className="w-3 h-3" /> مندوب المبيعات
                                        </h3>
                                        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg p-3 border border-blue-100 dark:border-blue-800/50">
                                            <div className="flex items-center gap-3 mb-2">
                                                <div className="w-8 h-8 rounded-full bg-blue-200 dark:bg-blue-700 flex items-center justify-center text-blue-700 dark:text-blue-200 font-bold text-xs">
                                                    {supplier.salesRepName?.charAt(0)}
                                                </div>
                                                <div>
                                                    <p className="font-bold text-sm text-gray-900 dark:text-white">{supplier.salesRepName}</p>
                                                    <p className="text-xs text-gray-500">مندوب المصنع</p>
                                                </div>
                                            </div>
                                            {supplier.salesRepPhone && (
                                                <div className="flex items-center gap-2 text-xs bg-white/60 dark:bg-black/20 p-1.5 rounded">
                                                    <Smartphone className="w-3 h-3 text-gray-400" />
                                                    <span className="font-mono text-gray-700 dark:text-gray-300">{supplier.salesRepPhone}</span>
                                                    <CopyButton text={supplier.salesRepPhone} />
                                                </div>
                                            )}
                                            {supplier.salesRepWechat && (
                                                <div className="flex items-center gap-2 text-xs bg-white/60 dark:bg-black/20 p-1.5 rounded mt-1">
                                                    <MessageSquare className="w-3 h-3 text-green-500" />
                                                    <span className="font-mono text-gray-700 dark:text-gray-300">{supplier.salesRepWechat}</span>
                                                    <CopyButton text={supplier.salesRepWechat} />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="md:col-span-8 p-5 space-y-6">
                                <div className="grid grid-cols-3 gap-3">
                                    <div className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
                                        <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
                                            <DollarSign className="w-3.5 h-3.5" />
                                            <span>العملة المعتمدة</span>
                                        </div>
                                        <p className="text-lg font-bold text-gray-900 dark:text-white">{supplier.currency || 'ILS'}</p>
                                    </div>
                                    <div className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm relative overflow-hidden">
                                        <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
                                            <CreditCard className="w-3.5 h-3.5" />
                                            <span>الرصيد الافتتاحي</span>
                                        </div>
                                        <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
                                            {supplier.openingBalance?.toLocaleString()}
                                        </p>
                                        <div className="absolute right-0 top-0 p-1 opacity-10">
                                            <TrendingUp className="w-12 h-12" />
                                        </div>
                                    </div>
                                    <div className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
                                        <div className="flex items-center gap-2 text-gray-500 text-xs mb-1">
                                            <Calendar className="w-3.5 h-3.5" />
                                            <span>تاريخ الرصيد</span>
                                        </div>
                                        <p className="text-sm font-semibold text-gray-900 dark:text-white">
                                            {supplier.balanceDate ? new Date(supplier.balanceDate).toLocaleDateString('ar-EG') : '-'}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex-1 flex flex-col min-h-[200px]">
                                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                                        <FileText className="w-3 h-3" /> الملاحظات والتفاصيل
                                    </h3>
                                    <div className="flex-1 bg-amber-50/50 dark:bg-amber-900/10 rounded-lg border border-amber-100 dark:border-amber-800/30 p-4 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                                        {supplier.notes || (
                                            <span className="text-gray-400 italic">لا توجد ملاحظات مسجلة لهذا المورد.</span>
                                        )}
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100 dark:border-gray-700">
                                    <div className="flex items-center gap-2 text-xs text-gray-400">
                                        <Clock className="w-3 h-3" />
                                        <span>تاريخ الإنشاء: {new Date(supplier.createdAt).toLocaleDateString('ar-EG')}</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs text-gray-400">
                                        <Clock className="w-3 h-3" />
                                        <span>آخر تحديث: {new Date(supplier.updatedAt).toLocaleDateString('ar-EG')}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
};