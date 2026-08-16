import React, { useState, useEffect } from 'react';
import { Supplier } from '../../types';
import { suppliersService } from '../../services/firestoreService';
import { cloudinaryService } from '../../services/cloudinaryService';
import { FileDropZone } from '../ui/FileDropZone';
import { LoadingSpinner } from '../LoadingSpinner';
import {
    X, Save, Building, User, MapPin, Wallet, ImageIcon, ArrowRight, Tag, Edit2, AlertTriangle
} from 'lucide-react';
import { SUPPLIER_TYPES } from '../../constants/supplierConstants';

interface SupplierModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSaveSuccess?: (supplier: Supplier) => void;
    editingSupplier?: Supplier | null;

}

export const SupplierModal: React.FC<SupplierModalProps> = ({
    isOpen,
    onClose,
    onSaveSuccess,
    editingSupplier
}) => {
    const [currentSupplier, setCurrentSupplier] = useState<Partial<Supplier>>({});
    const [error, setError] = useState<string | null>(null);
    const [uploadingLogo, setUploadingLogo] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (isOpen) {
            if (editingSupplier) {
                setCurrentSupplier({ ...editingSupplier });
            } else {
                // Return to default empty state
                setCurrentSupplier({
                    tradeName: '',
                    email: '',
                    phone: '',
                    mobile: '',
                    salesRepName: '',
                    salesRepWechat: '',
                    salesRepPhone: '',
                    street: '',
                    city: '',
                    region: '',
                    postalCode: '',
                    country: '',
                    currency: 'ILS',
                    openingBalance: 0,
                    notes: '',
                    logoUrl: '',
                    balanceDate: new Date().toISOString().split('T')[0],
                    type: 'factory'
                });
            }
            setError(null);
        }
    }, [isOpen, editingSupplier]);

    const uploadLogoFile = async (file: File) => {
        setUploadingLogo(true);
        try {
            const url = await cloudinaryService.uploadImage(file);
            setCurrentSupplier(prev => ({ ...prev, logoUrl: url }));
        } catch (error) {
            setError('فشل رفع الشعار');
        } finally {
            setUploadingLogo(false);
        }
    };

    // الاختيار والسحب واللصق (Ctrl+V) صارت كلها داخل `FileDropZone` أدناه، ولا تُسجَّل
    // منطقة اللصق إلا والنافذة مفتوحة لأن المكوّن نفسه لا يُركَّب قبل ذلك.
    if (!isOpen) return null;

    const handleSave = async () => {
        // 1. التحقق الأساسي (الاسم التجاري)
        if (!currentSupplier.tradeName?.trim()) {
            setError('الاسم التجاري مطلوب');
            return;
        }

        setSaving(true);
        setError(null);

        try {
            // ==========================================
            // 🛑 فحص التكرار (إيميل، هاتف، جوال)
            // ==========================================
            const uniquenessCheck = await suppliersService.checkSupplierUniqueness(
                {
                    email: currentSupplier.email,
                    phone: currentSupplier.phone,
                    mobile: currentSupplier.mobile
                },
                editingSupplier?.id // تمرير المعرف في حالة التعديل لاستثنائه
            );

            if (!uniquenessCheck.isUnique) {
                let errorMessage = 'هناك بيانات مكررة!';

                switch (uniquenessCheck.field) {
                    case 'email':
                        errorMessage = `البريد الإلكتروني "${currentSupplier.email}" مستخدم بالفعل للمورد: ${uniquenessCheck.existingName}`;
                        break;
                    case 'phone':
                        errorMessage = `رقم الهاتف "${currentSupplier.phone}" مستخدم بالفعل للمورد: ${uniquenessCheck.existingName}`;
                        break;
                    case 'mobile':
                        errorMessage = `رقم الجوال "${currentSupplier.mobile}" مستخدم بالفعل للمورد: ${uniquenessCheck.existingName}`;
                        break;
                }

                setError(errorMessage);
                setSaving(false);
                return; // ⛔ إيقاف الحفظ
            }
            // ==========================================

            let savedSupplier: Supplier;

            if (editingSupplier) {
                // Update Logic
                const supplierToUpdate: Supplier = {
                    ...editingSupplier,
                    ...currentSupplier as Supplier,
                    updatedAt: new Date().toISOString()
                };
                await suppliersService.updateSupplierInDb(supplierToUpdate);
                savedSupplier = supplierToUpdate;
            } else {
                // Create Logic
                const { id, supplierId, ...newSupplierData } = currentSupplier;
                const createdSupplier = await suppliersService.addSupplierToDb(newSupplierData as any);
                savedSupplier = createdSupplier;
            }

            if (onSaveSuccess) {
                onSaveSuccess(savedSupplier);
            }
            onClose();
        } catch (error: unknown) {
            // console suppressed
            const msg = error instanceof Error && error.message
                ? error.message
                : 'حدث خطأ أثناء الحفظ';
            setError(msg.length > 200 ? `${msg.slice(0, 200)}…` : msg);
        } finally {
            setSaving(false);
        }
    };
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
            <div className="bg-[var(--color-surface)] rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto border border-[var(--color-border)]">

                {/* Header */}
                <div className="p-6 border-b border-[var(--color-border)] flex justify-between items-center sticky top-0 bg-[var(--color-surface)] z-10">
                    <div>
                        <h2 className="text-xl font-bold text-[var(--color-text)] flex items-center gap-2">
                            {editingSupplier ? <Edit2 className="w-5 h-5" /> : <Building className="w-5 h-5 text-blue-500" />}
                            {editingSupplier ? 'تعديل بيانات المورد' : 'إضافة مورد جديد'}
                        </h2>
                        <p className="text-sm text-[var(--color-text-muted)] mt-1">
                            {editingSupplier ? 'قم بتعديل بيانات المورد الحالية' : 'أدخل بيانات المورد الأساسية وجهات الاتصال'}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] rounded-full transition-colors"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 space-y-8">
                    {error && (
                        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400 flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    {/* Logo Section */}
                    <div className="flex items-start gap-6 p-6 bg-[var(--color-surface-2)] rounded-xl border border-[var(--color-border)] border-dashed">
                        <div className="relative w-24 h-24 flex-shrink-0">
                            <div className="w-full h-full rounded-full border-2 border-dashed border-[var(--color-border)] flex items-center justify-center overflow-hidden bg-[var(--color-surface)]">
                                {currentSupplier.logoUrl ? (
                                    <img src={currentSupplier.logoUrl} alt="Logo" className="w-full h-full object-cover" />
                                ) : uploadingLogo ? (
                                    <LoadingSpinner />
                                ) : (
                                    <ImageIcon className="w-8 h-8 text-[var(--color-text-muted)]" />
                                )}
                            </div>
                            {currentSupplier.logoUrl && (
                                <button
                                    onClick={() => setCurrentSupplier(prev => ({ ...prev, logoUrl: '' }))}
                                    className="absolute -top-1 -right-1 bg-red-500 text-white p-1 rounded-full shadow-lg hover:bg-red-600 transition-colors"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            )}
                        </div>
                        <div className="flex-1">
                            <h3 className="font-bold text-[var(--color-text)] mb-1">شعار الشركة</h3>
                            <p className="text-sm text-[var(--color-text-muted)] mb-4">
                                يفضل استخدام صورة مربعة بحجم 500x500 بكسل. الصيغ المدعومة: PNG, JPG
                            </p>
                            <FileDropZone
                                onFiles={(files) => { void uploadLogoFile(files[0]); }}
                                accept="image"
                                busy={uploadingLogo}
                                variant="compact"
                                hint="اضغط لاختيار الشعار، اسحبه إلى هنا، أو الصق (Ctrl+V)"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

                        {/* Basic Info */}
                        <div className="lg:col-span-3">
                            <h3 className="text-lg font-bold text-[var(--color-text)] mb-4 flex items-center gap-2 border-b border-[var(--color-border)] pb-2">
                                <Building className="w-5 h-5 text-blue-500" />
                                المعلومات الأساسية
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">الاسم التجاري <span className="text-red-500">*</span></label>
                                    <input
                                        type="text"
                                        value={currentSupplier.tradeName || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, tradeName: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                        placeholder="اسم الشركة أو المورد"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">الاسم المستعار</label>
                                    <input
                                        type="text"
                                        value={currentSupplier.alias || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, alias: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                        placeholder="اسم بديل للعرض"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5 flex items-center gap-2">
                                        <Tag className="w-4 h-4 text-blue-500" />
                                        نوع المورد <span className="text-red-500">*</span>
                                    </label>
                                    <select
                                        value={currentSupplier.type || 'factory'}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, type: e.target.value as any })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    >
                                        {SUPPLIER_TYPES.map(opt => (
                                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">البريد الإلكتروني</label>
                                    <input
                                        type="email"
                                        value={currentSupplier.email || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, email: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">رقم الهاتف</label>
                                    <input
                                        type="tel"
                                        value={currentSupplier.phone || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, phone: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">رقم الجوال</label>
                                    <input
                                        type="tel"
                                        value={currentSupplier.mobile || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, mobile: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Sales Rep */}
                        <div className="lg:col-span-3">
                            <h3 className="text-lg font-bold text-[var(--color-text)] mb-4 flex items-center gap-2 border-b border-[var(--color-border)] pb-2">
                                <User className="w-5 h-5 text-green-500" />
                                بيانات المندوب
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">اسم المندوب</label>
                                    <input
                                        type="text"
                                        value={currentSupplier.salesRepName || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, salesRepName: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">WeChat ID</label>
                                    <input
                                        type="text"
                                        value={currentSupplier.salesRepWechat || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, salesRepWechat: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">جوال المندوب</label>
                                    <input
                                        type="tel"
                                        value={currentSupplier.salesRepPhone || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, salesRepPhone: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Address */}
                        <div className="lg:col-span-3">
                            <h3 className="text-lg font-bold text-[var(--color-text)] mb-4 flex items-center gap-2 border-b border-[var(--color-border)] pb-2">
                                <MapPin className="w-5 h-5 text-[var(--color-primary)]" />
                                العنوان
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">البلد</label>
                                    <input
                                        type="text"
                                        value={currentSupplier.country || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, country: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">المدينة</label>
                                    <input
                                        type="text"
                                        value={currentSupplier.city || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, city: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                    />
                                </div>
                                <div className="md:col-span-2">
                                    <label className="block text-sm font-medium mb-1.5">العنوان التفصيلي</label>
                                    <input
                                        type="text"
                                        value={currentSupplier.street || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, street: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Financial */}
                        <div className="lg:col-span-3">
                            <h3 className="text-lg font-bold text-[var(--color-text)] mb-4 flex items-center gap-2 border-b border-[var(--color-border)] pb-2">
                                <Wallet className="w-5 h-5 text-yellow-500" />
                                البيانات المالية
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">العملة</label>
                                    <select
                                        value={currentSupplier.currency || 'ILS'}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, currency: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                    >
                                        <option value="ILS">ILS - شيكل إسرائيلي جديد</option>
                                        <option value="USD">USD - دولار أمريكي</option>
                                        <option value="EUR">EUR - يورو</option>
                                        <option value="CNY">CNY - يوان صيني</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">الرصيد الافتتاحي</label>
                                    <input
                                        type="number"
                                        value={currentSupplier.openingBalance || 0}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, openingBalance: parseFloat(e.target.value) || 0 })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">تاريخ الرصيد</label>
                                    <input
                                        type="date"
                                        value={currentSupplier.balanceDate || new Date().toISOString().split('T')[0]}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, balanceDate: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1.5">حد الائتمان</label>
                                    <input
                                        type="number"
                                        value={currentSupplier.creditLimit || ''}
                                        onChange={e => setCurrentSupplier({ ...currentSupplier, creditLimit: parseFloat(e.target.value) || 0 })}
                                        className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)]"
                                        placeholder="0.00"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="p-6 border-t border-[var(--color-border)] bg-[var(--color-surface-2)] rounded-b-xl flex justify-end gap-3 sticky bottom-0">
                    <button
                        onClick={onClose}
                        className="px-6 py-2.5 bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text)] rounded-lg hover:bg-[var(--color-surface-2)] font-medium transition-colors"
                    >
                        إلغاء
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-blue-500/30"
                    >
                        {saving ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                جاري الحفظ...
                            </>
                        ) : (
                            <>
                                <Save className="w-4 h-4" />
                                حفظ البيانات
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};
