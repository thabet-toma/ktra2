import React, { useState, useEffect, useMemo } from 'react';
import { Item, Category, SubCategory, Brand, Invoice, Supplier, User } from '@/types';
import {
    itemsService, categoriesService,
    brandsService, invoicesService, suppliersService
} from '@/services/firestoreService';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ItemsList } from '@/components/items/ItemsList';
import { ItemForm } from '@/components/items/ItemForm';
import { RelatedInvoices } from '@/components/items/RelatedInvoices';
import { RelatedSuppliers } from '@/components/items/RelatedSuppliers';
import { CategoryModal, SubCategoryModal, BrandModal } from '@/components/items/ItemModals';
import { getInvoicesByItem, getSuppliersByItem } from '@/services/itemServiceHelpers';
import {
    ArrowRight, ExternalLink, ImageIcon, Edit2, Copy,
    Package, FileText, Users, X, Eye, Trash2,
    ChevronRight, Hash, Tag, BookOpen, Layers,
    BarChart3, Calendar, Globe, Box,
    Type,
    ShoppingCart,
    Store
} from 'lucide-react';
import { subCategoriesService } from '@/services/subCategoriesService';

interface ItemsManagementProps {
    user: User;
}

export const ItemsManagement: React.FC<ItemsManagementProps> = ({ user }) => {
    // Data State
    const [items, setItems] = useState<Item[]>([]);
    const [categories, setCategories] = useState<Category[]>([]);
    const [subCategories, setSubCategories] = useState<SubCategory[]>([]);
    const [brands, setBrands] = useState<Brand[]>([]);
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [loading, setLoading] = useState(true);

    const [activeTab, setActiveTab] = useState<'procurement' | 'store'>('procurement');


    // View State
    const [viewMode, setViewMode] = useState<'list' | 'edit' | 'view' | 'invoices' | 'suppliers'>('list');
    const [selectedItem, setSelectedItem] = useState<Item | null>(null);
    const [currentItem, setCurrentItem] = useState<Partial<Item>>({});

    // Modals State
    const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
    const [isSubCategoryModalOpen, setIsSubCategoryModalOpen] = useState(false);
    const [isBrandModalOpen, setIsBrandModalOpen] = useState(false);

    // Stats State
    const [stats, setStats] = useState({
        totalItems: 0,
        withImages: 0,
        withHSCode: 0,
        outOfStock: 0
    });

    useEffect(() => {
        const unsubItems = itemsService.subscribeToItems(setItems);
        const unsubCats = categoriesService.subscribeToCategories(setCategories);
        const unsubSubCats = subCategoriesService.subscribeToSubCategories(setSubCategories);
        const unsubBrands = brandsService.subscribeToBrands(setBrands);
        const unsubInvoices = invoicesService.subscribeToInvoices(setInvoices);
        const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);

        setLoading(false);

        return () => {
            unsubItems(); unsubCats(); unsubSubCats(); unsubBrands();
            unsubInvoices(); unsubSuppliers();
        };
    }, []);

    useEffect(() => {
        if (items.length > 0) {
            const withImages = items.filter(item =>
                item.imageUrls && item.imageUrls.length > 0 && item.imageUrls[0]
            ).length;
            const withHSCode = items.filter(item => item.hsCodePrimary).length;
            const outOfStock = items.filter(item => (item.quantity || 0) <= 0).length;

            setStats({
                totalItems: items.length,
                withImages,
                withHSCode,
                outOfStock
            });
        }
    }, [items]);

    /** الأصناف من SQL تحمل category_name بينما التصنيفات قد تكون فقط في Firestore — ندمج الاثنين للفلاتر */
    const categoriesForFilter = useMemo(() => {
        const map = new Map<string, Category>();
        for (const c of categories) {
            if (c?.id) map.set(String(c.id), { ...c, id: String(c.id) });
        }
        for (const item of items) {
            const id =
                item.categoryId != null && String(item.categoryId).trim() !== ""
                    ? String(item.categoryId).trim()
                    : "";
            const name = (item.categoryName || "").trim();
            if (!id && !name) continue;
            const key = id || `name:${name}`;
            if (!map.has(key)) {
                map.set(key, {
                    id: id || key,
                    name: name || (id ? `تصنيف #${id}` : "—"),
                });
            } else if (id && name) {
                const cur = map.get(key)!;
                if (!cur.name || cur.name.startsWith("تصنيف #")) cur.name = name;
            }
        }
        return Array.from(map.values()).sort((a, b) =>
            (a.name || "").localeCompare(b.name || "", "ar")
        );
    }, [categories, items]);

    const subCategoriesForFilter = useMemo(() => {
        const map = new Map<string, SubCategory>();
        for (const s of subCategories) {
            if (s?.id)
                map.set(String(s.id), {
                    ...s,
                    id: String(s.id),
                    categoryId: String(s.categoryId || ""),
                });
        }
        for (const item of items) {
            const id =
                item.subCategoryId != null &&
                String(item.subCategoryId).trim() !== ""
                    ? String(item.subCategoryId).trim()
                    : "";
            const name = (item.subCategoryName || "").trim();
            if (!id && !name) continue;
            const cid = String(item.categoryId || "");
            const key = id || `name:${name}:${cid}`;
            if (!map.has(key)) {
                map.set(key, {
                    id: id || key,
                    name: name || (id ? `فرعي #${id}` : "—"),
                    categoryId: cid,
                });
            }
        }
        return Array.from(map.values()).sort((a, b) =>
            (a.name || "").localeCompare(b.name || "", "ar")
        );
    }, [subCategories, items]);

    const handleCreateNew = () => {
        setCurrentItem({
            imageUrls: ['', '', ''],
            quantity: 0,
            hsCodePrimary: '',
            specifications: ''
        });
        setViewMode('edit');
    };

    const handleEditItem = (item: Item) => {
        const images = [...(item.imageUrls || [])];
        while (images.length < 3) images.push('');
        setCurrentItem({ ...item, imageUrls: images });
        setViewMode('edit');
    };

    const handleDeleteItem = async (id: string) => {
        if (confirm('هل أنت متأكد من حذف هذا الصنف؟ لا يمكن التراجع عن هذا الإجراء.')) {
            await itemsService.deleteItemFromDb(id);
        }
    };

    const handleDuplicateItem = async (item: Item) => {
        const newItem = {
            ...item,
            id: crypto.randomUUID(),
            name: `${item.name} (نسخة)`,
            modelNumber: item.modelNumber ? `${item.modelNumber}-COPY` : '',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };
        await itemsService.addItemToDb(newItem);
    };

    const handleViewDetails = (item: Item) => {
        setSelectedItem(item);
        setViewMode('view');
    };

    const handleViewInvoices = (item: Item) => {
        setSelectedItem(item);
        setViewMode('invoices');
    };

    const handleViewSuppliers = (item: Item) => {
        setSelectedItem(item);
        setViewMode('suppliers');
    };

    const handleToggleActive = async (item: Item) => {
        try {
            await itemsService.updateItemInDb({
                ...item,
                isActive: !item.isActive
            });
        } catch (error) {
            console.error("Error toggling active status:", error);
            alert("فشل تحديث حالة الصنف");
        }
    };

    const handleActivateAll = async () => {
        if (!confirm("هل أنت متأكد من تفعيل جميع الأصناف للمتجر؟ سيظهر كل المخزون للعملاء.")) return;

        setLoading(true);
        try {
            // we have all items in state 'items'
            const updates = items.map(item => {
                if (!item.isActive) {
                    return itemsService.updateItemInDb({ ...item, isActive: true });
                }
                return Promise.resolve();
            });
            await Promise.all(updates);
            alert("تم تفعيل جميع الأصناف بنجاح");
        } catch (error) {
            console.error("Error activating all items:", error);
            alert("حدث خطأ أثناء التفعيل الجماعي");
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <LoadingSpinner />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
            <div className="container mx-auto px-4 py-6">
                {/* Main Content */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl overflow-hidden border border-gray-100 dark:border-gray-700">
                    {viewMode === 'list' && (
                        <ItemsList
                            items={items}
                            categories={categoriesForFilter}
                            subCategories={subCategoriesForFilter}
                            onAddNew={handleCreateNew}
                            onEdit={handleEditItem}
                            onView={handleViewDetails}
                            onViewInvoices={handleViewInvoices}
                            onViewSuppliers={handleViewSuppliers}
                            onDelete={handleDeleteItem}
                            onDuplicate={handleDuplicateItem}
                            onOpenCategoryModal={() => setIsCategoryModalOpen(true)}
                            onOpenSubCategoryModal={() => setIsSubCategoryModalOpen(true)}
                            onOpenBrandModal={() => setIsBrandModalOpen(true)}
                            onToggleActive={handleToggleActive}
                            onActivateAll={handleActivateAll}
                        />
                    )}

                    {viewMode === 'edit' && (
                        <div className="p-6">
                            <ItemForm
                                initialItem={currentItem}
                                categories={categories}
                                subCategories={subCategories}
                                brands={brands}
                                user={user}
                                onCancel={() => setViewMode('list')}
                                onSave={() => setViewMode('list')}
                                onOpenCategoryModal={() => setIsCategoryModalOpen(true)}
                                onOpenSubCategoryModal={() => setIsSubCategoryModalOpen(true)}
                                onOpenBrandModal={() => setIsBrandModalOpen(true)}
                            />
                        </div>
                    )}
                    {viewMode === 'view' && selectedItem && (
                        <div className="flex flex-col h-full bg-white dark:bg-gray-800">
                            {/* Compact Header Bar */}
                            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => setViewMode('list')}
                                        className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
                                    >
                                        <ArrowRight className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                                    </button>
                                    <div>
                                        <h2 className="text-lg font-bold text-gray-900 dark:text-white leading-tight">
                                            {selectedItem.name}
                                        </h2>
                                        <div className="flex items-center gap-2 text-xs text-gray-500">
                                            <span className="bg-gray-200 dark:bg-gray-700 px-1.5 py-0.5 rounded text-gray-700 dark:text-gray-300">
                                                {selectedItem.modelNumber || 'بدون موديل'}
                                            </span>
                                            <span>|</span>
                                            <span className={selectedItem.isActive ? "text-green-600 font-medium" : "text-red-500"}>
                                                {selectedItem.isActive ? 'نشط في المتجر' : 'غير نشط'}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => handleEditItem(selectedItem)}
                                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded flex items-center gap-1"
                                    >
                                        <Edit2 className="w-3 h-3" /> تعديل
                                    </button>
                                    <button
                                        onClick={() => handleDuplicateItem(selectedItem)}
                                        className="px-3 py-1.5 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white text-xs font-medium rounded flex items-center gap-1"
                                    >
                                        <Copy className="w-3 h-3" /> نسخ
                                    </button>
                                </div>
                            </div>

                            {/* Dense Content Grid */}
                            <div className="flex-1 overflow-y-auto p-0">
                                <div className="grid grid-cols-12 h-full min-h-[500px]">

                                    {/* Right Column: Images (Shared) - 4 Columns */}
                                    <div className="col-span-12 md:col-span-4 lg:col-span-3 border-l border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/30 p-3">
                                        <div className="sticky top-0 space-y-3">
                                            {/* Main Image */}
                                            <div className="aspect-square w-full bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
                                                {selectedItem.imageUrls?.[0] ? (
                                                    <img
                                                        src={selectedItem.imageUrls[0]}
                                                        className="w-full h-full object-contain"
                                                        alt="Main"
                                                    />
                                                ) : (
                                                    <div className="w-full h-full flex items-center justify-center text-gray-400">
                                                        <ImageIcon className="w-10 h-10" />
                                                    </div>
                                                )}
                                            </div>

                                            {/* Thumbnails */}
                                            <div className="grid grid-cols-3 gap-2">
                                                {selectedItem.imageUrls?.slice(1).map((url, i) => (
                                                    <div key={i} className="aspect-square bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 overflow-hidden">
                                                        {url && <img src={url} className="w-full h-full object-cover" alt={`Sub ${i}`} />}
                                                    </div>
                                                ))}
                                            </div>

                                            {/* Quick Actions for View */}
                                            <div className="grid grid-cols-2 gap-2 pt-2">
                                                <button
                                                    onClick={() => handleViewInvoices(selectedItem)}
                                                    className="flex flex-col items-center justify-center p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                                                >
                                                    <FileText className="w-4 h-4 text-emerald-600 mb-1" />
                                                    <span className="text-[10px] text-gray-600 dark:text-gray-300">الفواتير</span>
                                                </button>
                                                <button
                                                    onClick={() => handleViewSuppliers(selectedItem)}
                                                    className="flex flex-col items-center justify-center p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                                                >
                                                    <Users className="w-4 h-4 text-orange-600 mb-1" />
                                                    <span className="text-[10px] text-gray-600 dark:text-gray-300">الموردون</span>
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Left Column: Data Tabs - 8 Columns */}
                                    <div className="col-span-12 md:col-span-8 lg:col-span-9 flex flex-col">

                                        {/* Tabs Header */}
                                        <div className="flex border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 sticky top-0 z-10">
                                            <button
                                                onClick={() => setActiveTab('procurement')}
                                                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors ${activeTab === 'procurement'
                                                    ? 'border-blue-600 text-blue-600 bg-blue-50/50 dark:bg-blue-900/10'
                                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                                                    }`}
                                            >
                                                <ShoppingCart className="w-4 h-4" />
                                                بيانات المشتريات
                                            </button>
                                            <button
                                                onClick={() => setActiveTab('store')}
                                                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors ${activeTab === 'store'
                                                    ? 'border-[var(--color-border)] text-[var(--color-primary)] bg-[var(--color-surface-2)]/50 dark:bg-[var(--color-surface-2)]/10'
                                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                                                    }`}
                                            >
                                                <Store className="w-4 h-4" />
                                                بيانات المتجر
                                            </button>
                                        </div>

                                        {/* Tab Content */}
                                        <div className="p-4 bg-white dark:bg-gray-800 flex-1">

                                            {/* 🟦 Procurement Tab */}
                                            {activeTab === 'procurement' && (
                                                <div className="space-y-4">
                                                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                                        <InfoItem label="التصنيف الرئيسي" value={selectedItem.categoryName} />
                                                        <InfoItem label="التصنيف الفرعي" value={selectedItem.subCategoryName} />
                                                        <InfoItem label="الماركة" value={selectedItem.brandName} />
                                                        <InfoItem label="الكمية الحالية" value={selectedItem.quantity} highlight />
                                                        <InfoItem label="HS Code (Primary)" value={selectedItem.hsCodePrimary} monospace />
                                                        <InfoItem label="HS Code (Alt)" value={selectedItem.hsCodeAlternative} monospace />
                                                    </div>

                                                    <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
                                                        <h4 className="text-xs font-bold text-gray-500 uppercase mb-2 flex items-center gap-1">
                                                            <BookOpen className="w-3 h-3" /> المواصفات التقنية
                                                        </h4>
                                                        <div className="bg-gray-50 dark:bg-gray-900/50 p-3 rounded text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap border border-gray-100 dark:border-gray-700">
                                                            {selectedItem.specifications || 'لا توجد مواصفات مسجلة'}
                                                        </div>
                                                    </div>

                                                    <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
                                                        <h4 className="text-xs font-bold text-gray-500 uppercase mb-2 flex items-center gap-1">
                                                            <Layers className="w-3 h-3" /> ملاحظات داخلية
                                                        </h4>
                                                        <p className="text-sm text-gray-600 dark:text-gray-400">
                                                            {selectedItem.notes || '-'}
                                                        </p>
                                                    </div>
                                                </div>
                                            )}

                                            {/* 🟪 Store Tab */}
                                            {activeTab === 'store' && (
                                                <div className="space-y-4">
                                                    {/* Store Summary Card */}
                                                    <div className="bg-gradient-to-r from-[var(--color-primary)] to-white dark:from-[var(--color-primary)]/20 dark:to-gray-800 border border-[var(--color-border)] dark:border-[var(--color-border)]/30 rounded-lg p-4">
                                                        <div className="flex items-start justify-between">
                                                            <div>
                                                                <p className="text-xs text-[var(--color-primary)] dark:text-[var(--color-primary)] font-medium mb-1">اسم العرض في المتجر</p>
                                                                <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                                                                    {selectedItem.storeName || selectedItem.name}
                                                                </h3>
                                                            </div>
                                                            <div className="text-left bg-white dark:bg-gray-800 px-4 py-2 rounded-lg border border-[var(--color-border)] dark:border-[var(--color-border)]/30 shadow-sm">
                                                                <p className="text-xs text-gray-500 mb-1">سعر البيع</p>
                                                                <p className="text-lg font-bold text-green-600 dark:text-green-400 flex items-center gap-1">
                                                                    {selectedItem.salePrice ? selectedItem.salePrice.toLocaleString() : '0'}
                                                                    <span className="text-xs font-normal text-gray-500">ILS</span>
                                                                </p>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="grid grid-cols-2 gap-3">
                                                        <InfoItem label="حالة الظهور" value={selectedItem.isActive ? "نشط" : "مخفي"} />
                                                        <InfoItem label="الكمية المتاحة للبيع" value={selectedItem.quantity} />
                                                    </div>

                                                    <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
                                                        <h4 className="text-xs font-bold text-gray-500 uppercase mb-2 flex items-center gap-1">
                                                            <Type className="w-3 h-3" /> وصف المتجر (الوصف التسويقي)
                                                        </h4>
                                                        <div className="bg-[var(--color-surface-2)]/50 dark:bg-[var(--color-surface-2)]/10 p-3 rounded text-sm text-gray-800 dark:text-gray-200 leading-relaxed whitespace-pre-wrap border border-[var(--color-border)] dark:border-[var(--color-border)]/20 min-h-[100px]">
                                                            {selectedItem.storeDescription || 'لا يوجد وصف مخصص للمتجر. سيتم استخدام المواصفات الافتراضية.'}
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>

                                        {/* Compact Footer Metadata */}
                                        <div className="px-4 py-2 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 text-[10px] text-gray-400 flex justify-between">
                                            <span>ID: {selectedItem.id}</span>
                                            <div className="flex gap-3">
                                                <span>Created: {new Date(selectedItem.createdAt).toLocaleDateString('en-GB')}</span>
                                                <span>Updated: {new Date(selectedItem.updatedAt).toLocaleDateString('en-GB')}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}


                    {viewMode === 'invoices' && selectedItem && (
                        <RelatedInvoices
                            item={selectedItem}
                            invoices={getInvoicesByItem(invoices, selectedItem.id)}
                            onBack={() => setViewMode('list')}
                        />
                    )}

                    {viewMode === 'suppliers' && selectedItem && (
                        <RelatedSuppliers
                            item={selectedItem}
                            data={getSuppliersByItem(invoices, suppliers, selectedItem.id)}
                            onBack={() => setViewMode('list')}
                        />
                    )}
                </div>
            </div>

            {/* Modals */}
            <CategoryModal
                isOpen={isCategoryModalOpen}
                onClose={() => setIsCategoryModalOpen(false)}
                onSuccess={() => { }}
            />
            <SubCategoryModal
                isOpen={isSubCategoryModalOpen}
                onClose={() => setIsSubCategoryModalOpen(false)}
                onSuccess={() => { }}
                categories={categories}
                initialCategoryId={currentItem.categoryId}
            />
            <BrandModal
                isOpen={isBrandModalOpen}
                onClose={() => setIsBrandModalOpen(false)}
                onSuccess={() => { }}
            />
        </div>
    );
};

const InfoItem = ({ label, value, highlight = false, monospace = false }: any) => (
    <div className="bg-gray-50 dark:bg-gray-900/50 p-2 rounded border border-gray-100 dark:border-gray-700">
        <p className="text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">{label}</p>
        <p className={`text-sm font-semibold text-gray-900 dark:text-white truncate ${highlight ? 'text-blue-600 dark:text-blue-400' : ''} ${monospace ? 'font-mono' : ''}`}>
            {value || '-'}
        </p>
    </div>
);