import React, { useState } from 'react';
import { Item, Category, SubCategory, Brand, User } from '@/types';
import { itemsService } from '@/services/firestoreService';
import { cloudinaryService } from '@/services/cloudinaryService';

import { ArrowRight, Plus, Shield, Save, Upload, X, Loader2, StoreIcon } from 'lucide-react';
import { AseelTabs } from '../aseel';

interface ItemFormProps {
    initialItem: Partial<Item>;
    categories: Category[];
    subCategories: SubCategory[];
    brands: Brand[];
    user: User;
    onCancel: () => void;
    onSave: () => void;
    onOpenCategoryModal: () => void;
    onOpenSubCategoryModal: () => void;
    onOpenBrandModal: () => void;
}

export const ItemForm: React.FC<ItemFormProps> = ({
    initialItem, categories, subCategories, brands, user,
    onCancel, onSave, onOpenCategoryModal, onOpenSubCategoryModal, onOpenBrandModal
}) => {
    const [currentItem, setCurrentItem] = useState<Partial<Item>>(initialItem);
    const [uploadingImages, setUploadingImages] = useState<boolean[]>([false, false, false]);

    const [activeTab, setActiveTab] = useState<'details' | 'store'>('details');


    // التحقق من صلاحيات المستخدم للرمز الجمركي
    const canEditHSCode = user.role === 'manager' || user.role === 'procurement';

    // 🟢 فلترة الفئات الفرعية بناءً على الفئة الرئيسية المختارة
    const filteredSubCategories = subCategories.filter(
        sub => sub.categoryId === currentItem.categoryId
    );

    const handleSave = async () => {
        if (!currentItem.name || !currentItem.categoryId) {
            alert('يرجى تعبئة الحقول الأساسية (الاسم والتصنيف)');
            return;
        }

        const selectedCat = categories.find(c => c.id === currentItem.categoryId);
        const selectedSubCat = subCategories.find(s => s.id === currentItem.subCategoryId);
        const selectedBrand = brands.find(b => b.id === currentItem.brandId);

        const itemData: any = {
            ...currentItem,
            id: currentItem.id || crypto.randomUUID(),
            categoryName: selectedCat?.name || '',
            subCategoryName: selectedSubCat?.name || '', // حفظ اسم الفئة الفرعية
            brandName: selectedBrand?.name || '',
            specifications: currentItem.specifications || '', // إضافة المواصفات
            imageUrls: (currentItem.imageUrls || []).filter(url => url && url.trim() !== ''),
            quantity: currentItem.quantity ?? 0,
            hsCodePrimary: currentItem.hsCodePrimary || '',
            hsCodeAlternative: currentItem.hsCodeAlternative || '', // حفظ HS Code الاحتياطي
            createdAt: currentItem.createdAt || new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };

        try {
            if (currentItem.id) {
                await itemsService.updateItemInDb(itemData);
            } else {
                await itemsService.addItemToDb(itemData);
            }
            onSave();
        } catch (error) {
            // console suppressed
            alert("حدث خطأ أثناء الحفظ");
        }
    };

    const handleImageUpload = async (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files || e.target.files.length === 0) return;
        const newUploading = [...uploadingImages];
        newUploading[index] = true;
        setUploadingImages(newUploading);

        try {
            const url = await cloudinaryService.uploadImage(e.target.files[0]);
            const newImages = [...(currentItem.imageUrls || ['', '', ''])];
            newImages[index] = url;
            setCurrentItem(prev => ({ ...prev, imageUrls: newImages }));
        } catch (error) {
            alert("فشل رفع الصورة");
        } finally {
            newUploading[index] = false;
            setUploadingImages(newUploading);
        }
    };

    return (
        <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b aseel-border-soft dark:aseel-border-soft">
                <div className="flex items-center gap-3">
                    <button onClick={onCancel} className="p-2 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-full transition-colors">
                        <ArrowRight className="w-5 h-5 aseel-text-soft" />
                    </button>
                    <div>
                        <h1 className="text-xl font-bold dark:text-white">
                            {currentItem.id ? 'تعديل الصنف' : 'إضافة صنف جديد'}
                        </h1>
                        <p className="text-xs aseel-text-soft dark:aseel-text-soft">
                            {activeTab === 'details' ? 'بيانات التوريد والمواصفات' : 'بيانات العرض في المتجر'}
                        </p>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                    {/* 📷 Shared Section: Images (Always Visible) */}
                    <div className="lg:col-span-3 space-y-4">
                        <label className="block text-sm font-medium mb-2 dark:aseel-text-soft">صور الصنف</label>
                        <div className="space-y-3">
                            {(currentItem.imageUrls || ['', '', '']).map((url, index) => (
                                <div key={index} className="relative aspect-square aseel-bg-panel dark:aseel-bg-panel rounded-lg border border-dashed aseel-border-soft dark:aseel-border-soft overflow-hidden hover:aseel-border-soft transition-colors group">
                                    {url ? (
                                        <>
                                            <img src={url} alt="" className="w-full h-full object-cover" />
                                            <button
                                                onClick={() => {
                                                    const newImages = [...(currentItem.imageUrls || [])];
                                                    newImages[index] = '';
                                                    setCurrentItem({ ...currentItem, imageUrls: newImages });
                                                }}
                                                className="absolute top-1 right-1 p-1 aseel-bg-panel text-white rounded shadow-sm opacity-0 group-hover:opacity-100 transition-opacity"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </>
                                    ) : (
                                        <label className="flex flex-col items-center justify-center w-full h-full cursor-pointer">
                                            {uploadingImages[index] ? <Loader2 className="animate-spin aseel-text-soft" /> : <Upload className="w-6 h-6 aseel-text-soft" />}
                                            <span className="text-xs aseel-text-soft mt-2">صورة {index + 1}</span>
                                            <input type="file" accept="image/*" className="hidden" onChange={(e) => handleImageUpload(index, e)} />
                                        </label>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* 📝 Form Content Area */}
                    <div className="lg:col-span-9">
                        <AseelTabs
                            activeTab={activeTab}
                            onTabChange={(key) => setActiveTab(key as 'details' | 'store')}
                            tabs={[
                                {
                                    key: 'details',
                                    label: 'المشتريات',
                                    content: (
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                            {/* Basic Info Group */}
                                            <div className="md:col-span-2 aseel-bg-panel dark:aseel-bg-panel/50 p-4 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                                <h3 className="text-sm font-bold aseel-text-ink dark:text-white mb-3">البيانات الأساسية</h3>
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">اسم الصنف (مشتريات) *</label>
                                                        <input
                                                            type="text"
                                                            value={currentItem.name || ''}
                                                            onChange={(e) => setCurrentItem({ ...currentItem, name: e.target.value })}
                                                            className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white focus:ring-2 focus:ring-blue-500"
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">رقم الموديل</label>
                                                        <input
                                                            type="text"
                                                            value={currentItem.modelNumber || ''}
                                                            onChange={(e) => setCurrentItem({ ...currentItem, modelNumber: e.target.value })}
                                                            className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white dir-ltr text-right"
                                                        />
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Categorization Group */}
                                            <div className="md:col-span-2 aseel-bg-panel dark:aseel-bg-panel/50 p-4 rounded-lg border aseel-border-soft dark:aseel-border-soft">
                                                <h3 className="text-sm font-bold aseel-text-ink dark:text-white mb-3">التصنيف والماركة</h3>
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">التصنيف الرئيسي *</label>
                                                        <div className="flex gap-1">
                                                            <select
                                                                value={currentItem.categoryId || ''}
                                                                onChange={(e) => setCurrentItem({ ...currentItem, categoryId: e.target.value, subCategoryId: '' })}
                                                                className="flex-1 px-2 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                                                            >
                                                                <option value="">اختر...</option>
                                                                {categories.map(cat => <option key={cat.id} value={cat.id}>{cat.name}</option>)}
                                                            </select>
                                                            <button type="button" onClick={onOpenCategoryModal} className="p-2 aseel-bg-grid-head dark:aseel-bg-panel rounded"><Plus className="w-4 h-4" /></button>
                                                        </div>
                                                    </div>

                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">التصنيف الفرعي</label>
                                                        <div className="flex gap-1">
                                                            <select
                                                                value={currentItem.subCategoryId || ''}
                                                                onChange={(e) => setCurrentItem({ ...currentItem, subCategoryId: e.target.value })}
                                                                disabled={!currentItem.categoryId}
                                                                className="flex-1 px-2 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white disabled:opacity-50"
                                                            >
                                                                <option value="">اختر...</option>
                                                                {filteredSubCategories.map(sub => <option key={sub.id} value={sub.id}>{sub.name}</option>)}
                                                            </select>
                                                            <button type="button" onClick={onOpenSubCategoryModal} disabled={!currentItem.categoryId} className="p-2 aseel-bg-grid-head dark:aseel-bg-panel rounded disabled:opacity-50"><Plus className="w-4 h-4" /></button>
                                                        </div>
                                                    </div>

                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">الماركة</label>
                                                        <div className="flex gap-1">
                                                            <select
                                                                value={currentItem.brandId || ''}
                                                                onChange={(e) => setCurrentItem({ ...currentItem, brandId: e.target.value })}
                                                                className="flex-1 px-2 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                                                            >
                                                                <option value="">اختر...</option>
                                                                {brands.map(brand => <option key={brand.id} value={brand.id}>{brand.name}</option>)}
                                                            </select>
                                                            <button type="button" onClick={onOpenBrandModal} className="p-2 aseel-bg-grid-head dark:aseel-bg-panel rounded"><Plus className="w-4 h-4" /></button>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Logistics Group */}
                                            <div>
                                                <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">الكمية (المخزون)</label>
                                                <input
                                                    type="number"
                                                    value={currentItem.quantity || 0}
                                                    onChange={(e) => setCurrentItem({ ...currentItem, quantity: parseInt(e.target.value) || 0 })}
                                                    className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white font-mono"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-medium mb-1 flex items-center gap-2 dark:aseel-text-soft">
                                                    HS Code Primary
                                                    {!canEditHSCode && <Shield className="w-3 h-3 aseel-text-soft" />}
                                                </label>
                                                <input
                                                    type="text"
                                                    value={currentItem.hsCodePrimary || ''}
                                                    onChange={(e) => setCurrentItem({ ...currentItem, hsCodePrimary: e.target.value })}
                                                    disabled={!canEditHSCode}
                                                    className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white font-mono disabled:opacity-60"
                                                />
                                            </div>

                                            <div className="md:col-span-2">
                                                <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">المواصفات التقنية</label>
                                                <textarea
                                                    value={currentItem.specifications || ''}
                                                    onChange={(e) => setCurrentItem({ ...currentItem, specifications: e.target.value })}
                                                    rows={4}
                                                    className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white resize-none"
                                                    placeholder="المواصفات الفنية التفصيلية..."
                                                />
                                            </div>
                                        </div>
                                    )
                                },
                                {
                                    key: 'store',
                                    label: 'المتجر',
                                    content: (
                                        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                            <div className="bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/10 p-4 rounded-lg border border-[var(--color-border)] dark:border-[var(--color-border)]/20">
                                                <div className="flex items-center gap-2 mb-4 text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                                                    <StoreIcon className="w-5 h-5" />
                                                    <h3 className="font-bold">بيانات العرض في المتجر</h3>
                                                </div>

                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                    <div className="md:col-span-2">
                                                        <div className="flex justify-between">
                                                            <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">اسم الصنف في المتجر</label>
                                                            <button
                                                                type="button"
                                                                onClick={() => setCurrentItem({ ...currentItem, storeName: currentItem.name })}
                                                                className="text-[10px] aseel-text-accent hover:underline"
                                                            >
                                                                نسخ الاسم من المشتريات
                                                            </button>
                                                        </div>
                                                        <input
                                                            type="text"
                                                            value={currentItem.storeName || ''}
                                                            onChange={(e) => setCurrentItem({ ...currentItem, storeName: e.target.value })}
                                                            className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white focus:border-[var(--color-border)]"
                                                            placeholder="الاسم الذي سيظهر للعميل..."
                                                        />
                                                    </div>

                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">سعر البيع (شيكل)</label>
                                                        <div className="relative">
                                                            <input
                                                                type="number"
                                                                value={currentItem.salePrice || 0}
                                                                onChange={(e) => setCurrentItem({ ...currentItem, salePrice: parseFloat(e.target.value) || 0 })}
                                                                className="w-full pl-3 pr-10 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white font-bold text-green-600"
                                                            />
                                                            <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                                                                <span className="aseel-text-soft text-xs">₪</span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div>
                                                        <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">حالة الصنف في المتجر</label>
                                                        <div className="flex items-center gap-3 h-full">
                                                            <label className="flex items-center gap-2 cursor-pointer">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={currentItem.isActive || false}
                                                                    onChange={(e) => setCurrentItem({ ...currentItem, isActive: e.target.checked })}
                                                                    className="w-4 h-4 text-[var(--color-primary)] rounded"
                                                                />
                                                                <span className="text-sm dark:aseel-text-soft">مفعل (يظهر للعملاء)</span>
                                                            </label>
                                                        </div>
                                                    </div>

                                                    <div className="md:col-span-2">
                                                        <div className="flex justify-between">
                                                            <label className="block text-xs font-medium mb-1 dark:aseel-text-soft">وصف المتجر (تسويقي)</label>
                                                            <button
                                                                type="button"
                                                                onClick={() => setCurrentItem({ ...currentItem, storeDescription: currentItem.specifications })}
                                                                className="text-[10px] aseel-text-accent hover:underline"
                                                            >
                                                                نسخ من المواصفات
                                                            </button>
                                                        </div>
                                                        <textarea
                                                            value={currentItem.storeDescription || ''}
                                                            onChange={(e) => setCurrentItem({ ...currentItem, storeDescription: e.target.value })}
                                                            rows={5}
                                                            className="w-full px-3 py-2 text-sm rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                                                            placeholder="اكتب وصفاً جذاباً للعميل..."
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                }
                            ]}
                        />
                    </div>
                </div>
            </div>

            {/* Footer Actions */}
            <div className="px-6 py-4 border-t aseel-border-soft dark:aseel-border-soft flex justify-end gap-3 aseel-bg-panel dark:aseel-bg-panel rounded-b-xl">
                <button onClick={onCancel} className="px-4 py-2 text-sm aseel-text-soft hover:aseel-bg-field border border-transparent hover:aseel-border-soft rounded-lg transition-all">
                    إلغاء
                </button>
                <button onClick={handleSave} className="px-6 py-2 aseel-bg-accent hover:aseel-bg-accent text-white text-sm font-medium rounded-lg shadow-sm flex items-center gap-2 transition-all">
                    <Save className="w-4 h-4" /> حفظ التغييرات
                </button>
            </div>
        </div>
    );
};