import React, { useState } from 'react';
import { Item, Category, SubCategory } from '@/types';
// أضفنا أيقونة Layers للتصنيف الفرعي
import { Search, Plus, Image as ImageIcon, MoreHorizontal, Eye, Edit2, Copy, Trash2, X, FileText, Users, Tag, Layers } from 'lucide-react';

interface ItemsListProps {
    items: Item[];
    categories: Category[];
    subCategories: SubCategory[];
    onAddNew: () => void;
    onEdit: (item: Item) => void;
    onView: (item: Item) => void;
    onDelete: (id: string) => void;
    onDuplicate: (item: Item) => void;
    onOpenCategoryModal: () => void;
    onOpenBrandModal: () => void;
    // 👇 إضافة هذه الدالة
    onOpenSubCategoryModal: () => void;
    onViewInvoices: (item: Item) => void;
    onViewSuppliers: (item: Item) => void;
    onToggleActive: (item: Item) => void;
    onActivateAll?: () => Promise<void>;
}

export const ItemsList: React.FC<ItemsListProps> = ({
    items, categories, subCategories,
    onAddNew, onEdit, onView, onDelete, onDuplicate,
    onOpenCategoryModal, onOpenBrandModal,
    onOpenSubCategoryModal, // 👈 استقبال الدالة هنا
    onViewInvoices, onViewSuppliers, onToggleActive, onActivateAll
}) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string>('all');
    const [selectedSubCategory, setSelectedSubCategory] = useState<string>('all');
    const [actionModalItem, setActionModalItem] = useState<Item | null>(null);

    // 🟢 فلترة القائمة المنسدلة للفرعي
    const availableSubCategories = subCategories.filter(
        sub =>
            selectedCategory === "all" ||
            String(sub.categoryId ?? "") === String(selectedCategory)
    );

    // 🟢 فلترة البيانات في الجدول (مقارنة معرفات كنص لتفادي اختلاف string vs number بين Firestore والواجهة)
    const filteredItems = items.filter(item => {
        const matchesSearch =
            item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            item.modelNumber?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            item.specifications.toLowerCase().includes(searchTerm.toLowerCase());

        const catId = item.categoryId != null && item.categoryId !== '' ? String(item.categoryId) : '';
        const subId = item.subCategoryId != null && item.subCategoryId !== '' ? String(item.subCategoryId) : '';
        const matchesCategory =
            selectedCategory === 'all' || catId === String(selectedCategory);
        const matchesSubCategory =
            selectedSubCategory === 'all' || subId === String(selectedSubCategory);

        return matchesSearch && matchesCategory && matchesSubCategory;
    });

    return (
        <div className="space-y-6">
            {/* Top Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <h1 className="text-2xl font-bold aseel-text-ink dark:text-white">إدارة الأصناف</h1>
                <div className="flex flex-wrap gap-2">
                    {/* زر تفعيل الكل */}
                    {onActivateAll && (
                        <button onClick={onActivateAll} className="flex items-center gap-2 px-3 py-2 bg-green-50 text-green-700 border aseel-border-soft rounded-lg text-sm hover:bg-green-100 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800">
                            تفعيل الكل للمتجر
                        </button>
                    )}

                    {/* زر إضافة تصنيف رئيسي */}
                    <button onClick={onOpenCategoryModal} className="flex items-center gap-2 px-3 py-2 aseel-bg-field dark:aseel-bg-panel border dark:aseel-border-soft rounded-lg text-sm dark:text-white hover:aseel-bg-panel">
                        <Tag className="w-4 h-4" /> تصنيف رئيسي +
                    </button>

                    {/* 👇 زر إضافة تصنيف فرعي (الجديد) */}
                    <button onClick={onOpenSubCategoryModal} className="flex items-center gap-2 px-3 py-2 aseel-bg-field dark:aseel-bg-panel border dark:aseel-border-soft rounded-lg text-sm dark:text-white hover:aseel-bg-panel">
                        <Layers className="w-4 h-4" /> تصنيف فرعي +
                    </button>

                    {/* زر إضافة ماركة */}
                    <button onClick={onOpenBrandModal} className="flex items-center gap-2 px-3 py-2 aseel-bg-field dark:aseel-bg-panel border dark:aseel-border-soft rounded-lg text-sm dark:text-white hover:aseel-bg-panel">
                        <Tag className="w-4 h-4" /> ماركة +
                    </button>

                    <button onClick={onAddNew} className="px-4 py-2 aseel-btn-primary flex items-center gap-2 shadow-sm">
                        <Plus className="w-4 h-4" /> صنف جديد
                    </button>
                </div>
            </div>

            {/* Filters Bar */}
            <div className="aseel-bg-field dark:aseel-bg-panel p-4 rounded-xl shadow-sm flex flex-col md:flex-row gap-4">
                <div className="relative flex-1">
                    <Search className="absolute right-3 top-1/2 -translate-y-1/2 aseel-text-soft w-5 h-5" />
                    <input
                        type="text"
                        placeholder="بحث..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pr-10 pl-4 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                    />
                </div>

                {/* 🟢 فلتر الفئة الرئيسية */}
                <select
                    value={selectedCategory}
                    onChange={(e) => {
                        setSelectedCategory(e.target.value);
                        setSelectedSubCategory('all');
                    }}
                    className="px-4 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white w-full md:w-48"
                >
                    <option value="all">كل التصنيفات</option>
                    {categories.map(cat => <option key={cat.id} value={cat.id}>{cat.name}</option>)}
                </select>

                {/* 🟢 فلتر الفئة الفرعية */}
                <select
                    value={selectedSubCategory}
                    onChange={(e) => setSelectedSubCategory(e.target.value)}
                    className="px-4 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white w-full md:w-48"
                >
                    <option value="all">كل الفرعي</option>
                    {availableSubCategories.map(sub => <option key={sub.id} value={sub.id}>{sub.name}</option>)}
                </select>
            </div>

            {/* Table */}
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm border aseel-border-soft dark:aseel-border-soft overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-right text-sm">
                        <thead className="aseel-bg-panel dark:aseel-bg-panel/50 aseel-text-ink dark:aseel-text-soft border-b dark:aseel-border-soft">
                            <tr>
                                <th className="px-6 py-4">الصورة</th>
                                <th className="px-6 py-4">الصنف</th>
                                <th className="px-6 py-4">التصنيف</th>
                                <th className="px-6 py-4">الماركة</th>
                                <th className="px-6 py-4">الكمية</th>
                                <th className="px-6 py-4">المتجر</th>
                                <th className="px-6 py-4"></th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                            {filteredItems.map(item => (
                                <tr
                                    key={item.id}
                                    onClick={(e) => setActionModalItem(item)}
                                    className="hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 cursor-pointer"
                                >
                                    <td className="px-6 py-4">
                                        {item.imageUrls?.[0] ?
                                            <img src={item.imageUrls[0]} className="w-10 h-10 rounded object-cover" alt="" /> :
                                            <div className="w-10 h-10 aseel-bg-panel dark:aseel-bg-panel rounded flex items-center justify-center"><ImageIcon className="w-5 h-5 aseel-text-soft" /></div>
                                        }
                                    </td>
                                    <td className="px-6 py-4 font-medium aseel-text-ink dark:text-white">
                                        <div>{item.name}</div>
                                        <div className="text-xs aseel-text-soft">{item.modelNumber}</div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex flex-col">
                                            <span className="aseel-text-ink dark:text-white font-medium">{item.categoryName}</span>
                                            {/* 🟢 عرض التصنيف الفرعي */}
                                            {item.subCategoryName && (
                                                <span className="text-xs aseel-text-soft flex items-center gap-1">
                                                    <span className="w-1.5 h-1.5 rounded-full aseel-bg-grid-head"></span>
                                                    {item.subCategoryName}
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 aseel-text-soft dark:aseel-text-soft">{item.brandName || '-'}</td>
                                    <td className="px-6 py-4">{item.quantity}</td>
                                    <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                                        <button
                                            onClick={() => onToggleActive(item)}
                                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${item.isActive ? 'aseel-bg-accent' : 'aseel-bg-grid-head dark:aseel-bg-panel'
                                                }`}
                                        >
                                            <span
                                                className={`inline-block h-4 w-4 transform rounded-full aseel-bg-field transition-transform ${item.isActive ? 'translate-x-1' : 'translate-x-6'
                                                    }`}
                                            />
                                        </button>
                                    </td>
                                    <td className="px-6 py-4"><MoreHorizontal className="w-5 h-5 aseel-text-soft" /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Action Modal */}
            {actionModalItem && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4" onClick={() => setActionModalItem(null)}>
                    <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-xl w-full max-w-sm overflow-hidden" onClick={e => e.stopPropagation()}>
                        <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel/50 flex justify-between items-center">
                            <h3 className="font-bold aseel-text-ink dark:text-white truncate">{actionModalItem.name}</h3>
                            <button onClick={() => setActionModalItem(null)}><X className="w-5 h-5 aseel-text-soft" /></button>
                        </div>
                        <div className="p-2 space-y-1">
                            <button onClick={() => { onView(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg text-right">
                                <div className="p-2 bg-green-100 text-green-600 rounded-lg"><Eye className="w-5 h-5" /></div>
                                <div><div className="font-bold dark:text-white">عرض الصنف</div></div>
                            </button>
                            <button onClick={() => { onViewInvoices(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg text-right">
                                <div className="p-2 aseel-bg-accent-bg aseel-text-accent rounded-lg"><FileText className="w-5 h-5" /></div>
                                <div><div className="font-bold dark:text-white">الفواتير</div></div>
                            </button>
                            <button onClick={() => { onViewSuppliers(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg text-right">
                                <div className="p-2 bg-[var(--color-surface-2)] text-[var(--color-primary)] rounded-lg"><Users className="w-5 h-5" /></div>
                                <div><div className="font-bold dark:text-white">الموردين</div></div>
                            </button>
                            <div className="h-px aseel-bg-panel dark:aseel-bg-panel my-2" />
                            <button onClick={() => { onEdit(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg text-right">
                                <div className="p-2 aseel-bg-panel aseel-text-soft rounded-lg"><Edit2 className="w-5 h-5" /></div>
                                <div className="font-bold dark:text-white">تعديل</div>
                            </button>
                            <button onClick={() => { onDuplicate(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg text-right">
                                <div className="p-2 bg-[var(--color-surface-2)] text-[var(--color-primary)] rounded-lg"><Copy className="w-5 h-5" /></div>
                                <div className="font-bold dark:text-white">نسخ</div>
                            </button>
                            <button onClick={() => { onDelete(actionModalItem.id); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:aseel-bg-panel dark:hover:aseel-bg-panel/20 rounded-lg text-right aseel-text-state">
                                <div className="p-2 aseel-bg-panel aseel-text-state rounded-lg"><Trash2 className="w-5 h-5" /></div>
                                <div className="font-bold">حذف</div>
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};