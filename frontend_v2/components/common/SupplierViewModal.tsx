import React, { useState, useEffect } from 'react';
import { Supplier } from '@/types';
import { suppliersService } from '@/services/firestoreService';
import {
    Building, Phone, Mail,
    DollarSign, Factory, Ship,
    Smartphone, Hash, Globe, CreditCard,
    FileText, Edit
} from 'lucide-react';
import { LoadingSpinner } from '../LoadingSpinner';
import { AseelSidePanel } from '../aseel/AseelSidePanel';
import { EntityActivityLog } from '../activity/EntityActivityLog';
import { formatDateValue } from "../../utils/formatDate";

interface SupplierViewModalProps {
    isOpen: boolean;
    onClose: () => void;
    supplierId: string | null;
    onEdit?: (supplier: Supplier) => void;
}

const getTypeInfo = (type?: string) => {
    switch (type) {
        case 'factory': return { icon: <Factory className="w-4 h-4" />, text: 'مورد', color: 'text-[var(--color-primary)] bg-[var(--color-surface-2)] border-[var(--color-border)]' };
        case 'shipping_agent': return { icon: <Ship className="w-4 h-4" />, text: 'وكيل شحن', color: 'text-blue-600 bg-blue-50 border-blue-200' };
        case 'service_provider': return { icon: <FileText className="w-4 h-4" />, text: 'مخلّص جمركي', color: 'text-amber-700 bg-amber-50 border-amber-200' };
        case 'local_company': return { icon: <Building className="w-4 h-4" />, text: 'ناقل محلي', color: 'text-green-700 bg-green-50 border-green-200' };
        case 'international_trader': return { icon: <Globe className="w-4 h-4" />, text: 'مورد دولي', color: 'text-[var(--color-primary)] bg-[var(--color-surface-2)] border-[var(--color-border)]' };
        default: return { icon: <Building className="w-4 h-4" />, text: 'مورد تجاري', color: 'text-[var(--color-text-muted)] bg-[var(--color-surface-2)] border-[var(--color-border)]' };
    }
};

const DetailRow = ({ icon, label, value, isLink = false }: any) => {
    if (!value) return null;
    return (
        <div className="flex items-start gap-3 py-2 group">
            <div className="mt-0.5 text-[var(--color-text-muted)]">{icon}</div>
            <div className="flex-1 min-w-0">
                <p className="text-xs text-[var(--color-text-muted)] mb-0.5">{label}</p>
                <div className="flex items-center gap-2">
                    {isLink ? (
                        <a href={value} target="_blank" rel="noreferrer" className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline truncate block">
                            {value}
                        </a>
                    ) : (
                        <p className="text-sm font-medium text-[var(--color-text)] truncate">{value}</p>
                    )}
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
            // console suppressed
            setError('حدث خطأ في تحميل البيانات');
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const typeInfo = getTypeInfo(supplier?.type);

    return (
        <AseelSidePanel open={isOpen} onClose={onClose} title={supplier?.tradeName || 'المورد'} width={520}>
            <div className="flex flex-col h-full">

                {/* Header Section */}
                <div className="flex-none border-b border-[var(--color-border)] pb-3 flex justify-between items-start">
                    <div className="flex gap-3">
                        <div className="relative">
                            {supplier?.logoUrl ? (
                                <img src={supplier.logoUrl} alt="Logo" className="w-12 h-12 rounded-lg border border-[var(--color-border)] object-cover shadow-sm" />
                            ) : (
                                <div className="w-12 h-12 rounded-lg bg-[var(--color-surface-2)] border border-[var(--color-border)] flex items-center justify-center">
                                    <Building className="w-6 h-6 text-[var(--color-text-muted)]" />
                                </div>
                            )}
                            <div className={`absolute -bottom-2 -right-2 px-2 py-0.5 rounded text-[10px] font-bold border ${typeInfo.color} shadow-sm`}>
                                {typeInfo.text}
                            </div>
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-[var(--color-text)] leading-tight">
                                {supplier?.tradeName}
                            </h2>
                            {supplier?.alias && (
                                <p className="text-sm text-[var(--color-text-muted)] mt-0.5 font-medium">
                                    ({supplier.alias})
                                </p>
                            )}
                            <div className="flex items-center gap-2 mt-1">
                                <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-muted)] bg-[var(--color-surface-3)] px-2 py-0.5 rounded">
                                    <Hash className="w-3 h-3" /> {supplier?.supplierId}
                                </span>
                                {supplier?.country && (
                                    <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-muted)] bg-[var(--color-surface-3)] px-2 py-0.5 rounded">
                                        <Globe className="w-3 h-3" /> {supplier.country}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {onEdit && supplier && (
                        <button
                            onClick={() => onEdit(supplier)}
                            className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/30 rounded-full transition-colors"
                            title="تعديل المورد"
                        >
                            <Edit className="w-4 h-4" />
                        </button>
                    )}
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto mt-3 space-y-4" style={{ minHeight: 0 }}>
                    {loading ? (
                        <div className="h-32 flex items-center justify-center"><LoadingSpinner /></div>
                    ) : error ? (
                        <div className="p-4 text-center text-red-500">{error}</div>
                    ) : supplier ? (
                        <>
                            {/* Contact Info */}
                            <div className="space-y-2">
                                <h3 className="text-xs font-bold text-[var(--color-text-muted)] uppercase tracking-wider">معلومات الاتصال</h3>
                                <div className="space-y-1 bg-[var(--color-surface)] rounded-lg p-3 border border-[var(--color-border)]">
                                    <DetailRow icon={<Mail className="w-4 h-4" />} label="البريد الإلكتروني" value={supplier.email} />
                                    <DetailRow icon={<Phone className="w-4 h-4" />} label="الهاتف" value={supplier.phone} />
                                    <DetailRow icon={<Smartphone className="w-4 h-4" />} label="الجوال" value={supplier.mobile} />
                                </div>
                            </div>

                            {/* Address */}
                            {(supplier.street || supplier.city) && (
                                <div>
                                    <h3 className="text-xs font-bold text-[var(--color-text-muted)] uppercase tracking-wider mb-2">العنوان</h3>
                                    <div className="bg-[var(--color-surface)] rounded-lg p-3 border border-[var(--color-border)] text-sm">
                                        <p className="font-medium">{supplier.street}</p>
                                        <p className="text-[var(--color-text-muted)] mt-1">
                                            {[supplier.city, supplier.region, supplier.postalCode, supplier.country].filter(Boolean).join('، ')}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {/* Balance */}
                            <div className="grid grid-cols-2 gap-2">
                                <div className="p-3 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg">
                                    <div className="flex items-center gap-2 text-[var(--color-text-muted)] text-xs mb-1">
                                        <DollarSign className="w-3.5 h-3.5" />
                                        <span>العملة</span>
                                    </div>
                                    <p className="text-lg font-bold text-[var(--color-text)]">{supplier.currency || 'ILS'}</p>
                                </div>
                                <div className="p-3 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg">
                                    <div className="flex items-center gap-2 text-[var(--color-text-muted)] text-xs mb-1">
                                        <CreditCard className="w-3.5 h-3.5" />
                                        <span>الرصيد الافتتاحي</span>
                                    </div>
                                    <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">
                                        {supplier.openingBalance?.toLocaleString()}
                                    </p>
                                </div>
                            </div>

                            {/* Notes */}
                            {supplier.notes && (
                                <div>
                                    <h3 className="text-xs font-bold text-[var(--color-text-muted)] uppercase tracking-wider mb-2">ملاحظات</h3>
                                    <div className="bg-amber-50/50 dark:bg-amber-900/10 rounded-lg border border-amber-100 dark:border-amber-800/30 p-3 text-sm whitespace-pre-wrap leading-relaxed">
                                        {supplier.notes}
                                    </div>
                                </div>
                            )}

                            <EntityActivityLog
                                partnerId={supplierId || supplier.supplierId}
                                title="سجل نشاطات المستخدمين"
                            />

                            {/* Footer meta */}
                            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[var(--color-border)] text-xs text-[var(--color-text-muted)]">
                                <span>تاريخ الإنشاء: {formatDateValue(supplier.createdAt)}</span>
                                <span>آخر تحديث: {formatDateValue(supplier.updatedAt)}</span>
                            </div>
                        </>
                    ) : null}
                </div>
            </div>
        </AseelSidePanel>
    );
};
