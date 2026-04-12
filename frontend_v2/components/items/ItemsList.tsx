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
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">إدارة الأصناف</h1>
                <div className="flex flex-wrap gap-2">
                    {/* زر تفعيل الكل */}
                    {onActivateAll && (
                        <button onClick={onActivateAll} className="flex items-center gap-2 px-3 py-2 bg-green-50 text-green-700 border border-green-200 rounded-lg text-sm hover:bg-green-100 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800">
                            تفعيل الكل للمتجر
                        </button>
                    )}

                    {/* زر إضافة تصنيف رئيسي */}
                    <button onClick={onOpenCategoryModal} className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg text-sm dark:text-white hover:bg-gray-50">
                        <Tag className="w-4 h-4" /> تصنيف رئيسي +
                    </button>

                    {/* 👇 زر إضافة تصنيف فرعي (الجديد) */}
                    <button onClick={onOpenSubCategoryModal} className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg text-sm dark:text-white hover:bg-gray-50">
                        <Layers className="w-4 h-4" /> تصنيف فرعي +
                    </button>

                    {/* زر إضافة ماركة */}
                    <button onClick={onOpenBrandModal} className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg text-sm dark:text-white hover:bg-gray-50">
                        <Tag className="w-4 h-4" /> ماركة +
                    </button>

                    <button onClick={onAddNew} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2 shadow-sm">
                        <Plus className="w-4 h-4" /> صنف جديد
                    </button>
                </div>
            </div>

            {/* Filters Bar */}
            <div className="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm flex flex-col md:flex-row gap-4">
                <div className="relative flex-1">
                    <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
                    <input
                        type="text"
                        placeholder="بحث..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pr-10 pl-4 py-2 rounded-lg border dark:bg-gray-900 dark:border-gray-700 dark:text-white"
                    />
                </div>

                {/* 🟢 فلتر الفئة الرئيسية */}
                <select
                    value={selectedCategory}
                    onChange={(e) => {
                        setSelectedCategory(e.target.value);
                        setSelectedSubCategory('all');
                    }}
                    className="px-4 py-2 rounded-lg border dark:bg-gray-900 dark:border-gray-700 dark:text-white w-full md:w-48"
                >
                    <option value="all">كل التصنيفات</option>
                    {categories.map(cat => <option key={cat.id} value={cat.id}>{cat.name}</option>)}
                </select>

                {/* 🟢 فلتر الفئة الفرعية */}
                <select
                    value={selectedSubCategory}
                    onChange={(e) => setSelectedSubCategory(e.target.value)}
                    className="px-4 py-2 rounded-lg border dark:bg-gray-900 dark:border-gray-700 dark:text-white w-full md:w-48"
                >
                    <option value="all">كل الفرعي</option>
                    {availableSubCategories.map(sub => <option key={sub.id} value={sub.id}>{sub.name}</option>)}
                </select>
            </div>

            {/* Table */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-right text-sm">
                        <thead className="bg-gray-50 dark:bg-gray-900/50 text-gray-700 dark:text-gray-300 border-b dark:border-gray-700">
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
                                    className="hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer"
                                >
                                    <td className="px-6 py-4">
                                        {item.imageUrls?.[0] ?
                                            <img src={item.imageUrls[0]} className="w-10 h-10 rounded object-cover" alt="" /> :
                                            <div className="w-10 h-10 bg-gray-100 dark:bg-gray-700 rounded flex items-center justify-center"><ImageIcon className="w-5 h-5 text-gray-400" /></div>
                                        }
                                    </td>
                                    <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                                        <div>{item.name}</div>
                                        <div className="text-xs text-gray-500">{item.modelNumber}</div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex flex-col">
                                            <span className="text-gray-900 dark:text-white font-medium">{item.categoryName}</span>
                                            {/* 🟢 عرض التصنيف الفرعي */}
                                            {item.subCategoryName && (
                                                <span className="text-xs text-gray-500 flex items-center gap-1">
                                                    <span className="w-1.5 h-1.5 rounded-full bg-gray-300"></span>
                                                    {item.subCategoryName}
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">{item.brandName || '-'}</td>
                                    <td className="px-6 py-4">{item.quantity}</td>
                                    <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                                        <button
                                            onClick={() => onToggleActive(item)}
                                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${item.isActive ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
                                                }`}
                                        >
                                            <span
                                                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${item.isActive ? 'translate-x-1' : 'translate-x-6'
                                                    }`}
                                            />
                                        </button>
                                    </td>
                                    <td className="px-6 py-4"><MoreHorizontal className="w-5 h-5 text-gray-400" /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Action Modal */}
            {actionModalItem && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4" onClick={() => setActionModalItem(null)}>
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-sm overflow-hidden" onClick={e => e.stopPropagation()}>
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex justify-between items-center">
                            <h3 className="font-bold text-gray-900 dark:text-white truncate">{actionModalItem.name}</h3>
                            <button onClick={() => setActionModalItem(null)}><X className="w-5 h-5 text-gray-500" /></button>
                        </div>
                        <div className="p-2 space-y-1">
                            <button onClick={() => { onView(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-right">
                                <div className="p-2 bg-green-100 text-green-600 rounded-lg"><Eye className="w-5 h-5" /></div>
                                <div><div className="font-bold dark:text-white">عرض الصنف</div></div>
                            </button>
                            <button onClick={() => { onViewInvoices(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-right">
                                <div className="p-2 bg-blue-100 text-blue-600 rounded-lg"><FileText className="w-5 h-5" /></div>
                                <div><div className="font-bold dark:text-white">الفواتير</div></div>
                            </button>
                            <button onClick={() => { onViewSuppliers(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-right">
                                <div className="p-2 bg-purple-100 text-purple-600 rounded-lg"><Users className="w-5 h-5" /></div>
                                <div><div className="font-bold dark:text-white">الموردين</div></div>
                            </button>
                            <div className="h-px bg-gray-100 dark:bg-gray-700 my-2" />
                            <button onClick={() => { onEdit(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-right">
                                <div className="p-2 bg-orange-100 text-orange-600 rounded-lg"><Edit2 className="w-5 h-5" /></div>
                                <div className="font-bold dark:text-white">تعديل</div>
                            </button>
                            <button onClick={() => { onDuplicate(actionModalItem); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg text-right">
                                <div className="p-2 bg-indigo-100 text-indigo-600 rounded-lg"><Copy className="w-5 h-5" /></div>
                                <div className="font-bold dark:text-white">نسخ</div>
                            </button>
                            <button onClick={() => { onDelete(actionModalItem.id); setActionModalItem(null); }} className="w-full flex items-center gap-3 p-3 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg text-right text-red-600">
                                <div className="p-2 bg-red-100 text-red-600 rounded-lg"><Trash2 className="w-5 h-5" /></div>
                                <div className="font-bold">حذف</div>
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};