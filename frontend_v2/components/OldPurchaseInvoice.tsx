import React, { useState, useEffect, useMemo } from 'react';
import { Invoice, Item, Supplier } from '../types';
import { invoicesService, itemsService, suppliersService } from '../services/firestoreService';
import { Plus, Archive, Package } from 'lucide-react';
import { collection, query, where, orderBy, getDocs, limit, onSnapshot, db } from "../services/sqlApiClient";
import { LoadingSpinner } from './LoadingSpinner';

// New Components
import { OldInvoiceList } from './procurement/old-invoices/OldInvoiceList';
import { OldInvoiceFilters } from './procurement/old-invoices/OldInvoiceFilters';
import { OldInvoiceFormModal } from './procurement/old-invoices/OldInvoiceFormModal';
import { InvoiceDetailsModal } from './procurement/old-invoices/InvoiceDetailsModal';
import { SupplierModal } from './common/SupplierModal';

export const OldPurchaseInvoice: React.FC = () => {
    // --- Data States ---
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);

    // --- Filter States ---
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedSupplierId, setSelectedSupplierId] = useState('');
    const [selectedItemIds, setSelectedItemIds] = useState<string[]>([]);
    const [dateRange, setDateRange] = useState({ start: '', end: '' });

    // --- Modal States ---
    const [showFormModal, setShowFormModal] = useState(false);
    const [editingInvoice, setEditingInvoice] = useState<Invoice | null>(null);
    const [showSupplierModal, setShowSupplierModal] = useState(false);

    // View Details Modal State
    const [showDetailsModal, setShowDetailsModal] = useState(false);
    const [viewingInvoice, setViewingInvoice] = useState<Invoice | null>(null);

    const [convertingInvoice, setConvertingInvoice] = useState<Invoice | null>(null);
    const [isConverting, setIsConverting] = useState(false);

    // بعد دالة handleViewDetails، أضف:
    const handleConvertToMain = (invoice: Invoice) => {
        setConvertingInvoice(invoice);
        setIsConverting(true);

        // تحويل الفاتورة مباشرة
        convertInvoiceToMain(invoice);
    };

    const convertInvoiceToMain = async (invoice: Invoice) => {
        try {
            // إنشاء ID جديد للفاتورة المحولة
            const newInvoiceId = crypto.randomUUID();
            const now = new Date().toISOString();

            // البحث عن المورد
            const supplier = suppliers.find(s => s.id === invoice.supplierId);

            // تحضير بيانات الفاتورة المحولة
            const convertedInvoice: any = {
                ...invoice,
                id: newInvoiceId,
                originalId: invoice.id, // حفظ ID الفاتورة القديمة
                isHistorical: false, // أصبحت فاتورة رئيسية
                status: "incomplete", // حالة افتراضية جديدة
                createdAt: now,
                updatedAt: now,
                convertedFromId: invoice.id, // حفظ مرجع للفاتورة الأصلية
                convertedAt: now,
                convertedBy: "system", // أو ID المستخدم إذا كان متاحاً

                // إضافة الحقول المفقودة بالقيم الافتراضية
                shippingCost: 0,
                shippingIncluded: false,
                shippingMethod: "",
                localPayments: {},
                installmentPlanEnabled: false,
                installments: [],
                alibabaOrderLink: invoice.invoiceLink || "",
                supplierInvoiceNumber: invoice.invoiceNumber || "",

                // معلومات إضافية
                notes: (invoice.notes || "") + "\n---\nتم التحويل من الأرشيف في: " + new Date().toLocaleDateString('ar-EG'),

                // إضافة dealInfo إذا لم يكن موجوداً
                dealInfo: invoice.dealInfo || {
                    createdAt: now,
                    createdBy: "system",
                    updatedAt: now,
                    updatedBy: "system",
                }
            };

            // حفظ الفاتورة المحولة
            await invoicesService.addInvoiceToDb(convertedInvoice);

            // تحديث الفاتورة الأصلية لتسجيل التحويل (اختياري)
            const updatedOriginalInvoice = {
                ...invoice,
                convertedToId: newInvoiceId,
                convertedAt: now
            };
            await invoicesService.updateInvoiceInDb(updatedOriginalInvoice as Invoice);

            // إظهار رسالة نجاح
            alert(`تم تحويل الفاتورة ${invoice.invoiceNumber} إلى فواتير رئيسية بنجاح!`);

            // إعادة تحميل الصفحة بعد ثانيتين لعرض التغييرات
            setTimeout(() => {
                setInvoices(prev => prev.filter(inv => inv.id !== invoice.id));
            }, 2000);

        } catch (error) {
            console.error("Error converting invoice:", error);
            alert("حدث خطأ أثناء تحويل الفاتورة");
        } finally {
            setIsConverting(false);
            setConvertingInvoice(null);
        }
    };

    const handleDeleteInvoice = (invoice: Invoice) => {
        if (!window.confirm(`هل أنت متأكد من الحذف النهائي للفاتورة ${invoice.invoiceNumber}؟\n\nهذا الإجراء لا يمكن التراجع عنه!`)) {
            return;
        }

        // تأكيد إضافي للمبالغ الكبيرة
        if ((invoice.grandTotal || 0) > 1000) {
            const confirmAgain = window.confirm(
                `تنبيه! الفاتورة تحتوي على مبلغ كبير: $${invoice.grandTotal?.toLocaleString()}\n` +
                `هل أنت متأكد تماماً من الحذف النهائي؟`
            );
            if (!confirmAgain) return;
        }

        deleteInvoice(invoice);
    };

    const deleteInvoice = async (invoice: Invoice) => {
        try {
            // إظهار مؤشر التحميل
            const deleteButton = document.querySelector('.delete-loading');
            if (deleteButton) deleteButton.innerHTML = 'جاري الحذف...';

            await invoicesService.deleteInvoiceFromDb(invoice.id);

            // إظهار رسالة نجاح
            alert(`تم حذف الفاتورة ${invoice.invoiceNumber} نهائياً`);

            // إعادة تحميل الصفحة بعد نصف ثانية
            setTimeout(() => {
                setInvoices(prev => prev.filter(inv => inv.id !== invoice.id));
            }, 500);

        } catch (error) {
            console.error("Error deleting invoice:", error);
            alert("حدث خطأ أثناء حذف الفاتورة");
        }
    };

    // --- Data Fetching ---
    useEffect(() => {
        const unsubscribeItems = itemsService.subscribeToItems(setItems);
        const unsubscribeSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);

        // Fetch Archived Invoices
        const q = query(
            collection(db, "invoices"),
            where("isHistorical", "==", true),
            orderBy("createdAt", "desc"),
            limit(50)
        );

        const unsubscribeInvoices = onSnapshot(q, (snapshot) => {
            const data = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Invoice));
            setInvoices(data);
            setLoading(false);
        }, (error) => {
            console.error("Error fetching invoices:", error);
            setLoading(false);
        });

        return () => {
            unsubscribeItems();
            unsubscribeSuppliers();
            unsubscribeInvoices();
        };
    }, []);

    // --- Filtering Logic ---
    const filteredInvoices = useMemo(() => {
        const lowerSearchTerm = searchTerm.toLowerCase().trim();

        return invoices.filter(inv => {
            // Search filter - يبحث في كل شيء
            let matchesSearch = true;
            if (lowerSearchTerm) {
                // البحث في اسم المورد أو الاسم المستعار
                const supplier = suppliers.find(s => s.id === inv.supplierId);
                const supplierMatch =
                    (supplier?.alias || '').toLowerCase().includes(lowerSearchTerm) ||
                    (supplier?.tradeName || '').toLowerCase().includes(lowerSearchTerm);

                matchesSearch =
                    (inv.invoiceNumber || '').toLowerCase().includes(lowerSearchTerm) ||
                    (inv.factoryName || '').toLowerCase().includes(lowerSearchTerm) ||
                    supplierMatch ||
                    // البحث في أسماء المنتجات داخل الفاتورة
                    inv.items?.some(item =>
                        (item.name || '').toLowerCase().includes(lowerSearchTerm)
                    )
                // البحث في رقم المودل داخل الفاتورة
                inv.items?.some(item =>
                    (item.specifications || '').toLowerCase().includes(lowerSearchTerm)
                );
            }

            // Supplier filter
            const matchesSupplier = selectedSupplierId ? inv.supplierId === selectedSupplierId : true;

            // Items filter - يبحث إذا كانت الفاتورة تحتوي على أي من المنتجات المختارة
            const matchesItems = selectedItemIds.length === 0
                ? true
                : selectedItemIds.some(itemId =>
                    inv.items?.some(invoiceItem => invoiceItem.itemId === itemId)
                );

            // Date range filter
            let matchesDate = true;
            if (dateRange.start) {
                matchesDate = matchesDate && (inv.invoiceDate >= dateRange.start);
            }
            if (dateRange.end) {
                matchesDate = matchesDate && (inv.invoiceDate <= dateRange.end);
            }

            return matchesSearch && matchesSupplier && matchesItems && matchesDate;
        });
    }, [invoices, suppliers, searchTerm, selectedSupplierId, selectedItemIds, dateRange]);

    // الحصول على المنتجات التي تطابق البحث
    const filteredItems = useMemo(() => {
        const lowerSearchTerm = searchTerm.toLowerCase().trim();

        return items.filter(item => {
            if (!lowerSearchTerm) return true;

            return (
                (item.name || '').toLowerCase().includes(lowerSearchTerm) ||
                (item.modelNumber || '').toLowerCase().includes(lowerSearchTerm) ||
                (item.categoryName || '').toLowerCase().includes(lowerSearchTerm)
            );
        });
    }, [items, searchTerm]);

    // --- Handlers ---
    const handleCreateNew = () => {
        setEditingInvoice(null);
        setShowFormModal(true);
    };

    const handleEdit = (invoice: Invoice) => {
        setEditingInvoice(invoice);
        setShowFormModal(true);
    };

    const handleViewDetails = (invoice: Invoice) => {
        setViewingInvoice(invoice);
        setShowDetailsModal(true);
    };

    const handleSaveInvoice = async (invoiceData: Partial<Invoice>) => {
        try {
            if (editingInvoice) {
                const updatedInvoice: Invoice = {
                    ...editingInvoice,
                    ...invoiceData
                } as Invoice;
                await invoicesService.updateInvoiceInDb(updatedInvoice);
            } else {
                const newId = crypto.randomUUID();
                const now = new Date().toISOString();

                const newInvoiceData: Omit<Invoice, 'serialNumber'> = {
                    id: newId,
                    createdAt: now,
                    updatedAt: now,
                    status: 'completed',
                    isHistorical: true,
                    ...invoiceData,
                } as Omit<Invoice, 'serialNumber'>;

                if (!newInvoiceData.items) newInvoiceData.items = [];
                if (!newInvoiceData.imageUrls) newInvoiceData.imageUrls = [];

                await invoicesService.addInvoiceToDb(newInvoiceData);
            }
        } catch (error) {
            console.error("Error saving invoice:", error);
            throw error;
        }
    };

    const handleSaveSupplier = async (supplierData: any) => {
        await suppliersService.addSupplierToDb(supplierData);
    };

    // الحصول على العناصر المختارة للعرض
    const selectedItems = useMemo(() => {
        return items.filter(item => selectedItemIds.includes(item.id));
    }, [items, selectedItemIds]);

    // إحصائيات الفلترة
    const filteredItemsCount = useMemo(() => {
        const itemCounts: Record<string, number> = {};
        filteredInvoices.forEach(invoice => {
            invoice.items?.forEach(item => {
                itemCounts[item.itemId] = (itemCounts[item.itemId] || 0) + 1;
            });
        });
        return itemCounts;
    }, [filteredInvoices]);

    // الحصول على المنتجات التي تظهر في نتائج البحث
    const searchResultItems = useMemo(() => {
        if (!searchTerm.trim()) return [];

        const lowerSearchTerm = searchTerm.toLowerCase();
        const resultItems = new Set<string>();

        filteredInvoices.forEach(invoice => {
            invoice.items?.forEach(item => {
                // إذا كان المنتج يطابق البحث
                if (
                    (item.name?.toLowerCase().includes(lowerSearchTerm) ||
                        item.specifications?.toLowerCase().includes(lowerSearchTerm))
                ) {
                    resultItems.add(item.itemId);
                }
            });
        });

        return Array.from(resultItems);
    }, [filteredInvoices, searchTerm]);

    // منتجات مقترحة للفلترة بناءً على البحث
    const suggestedItems = useMemo(() => {
        if (!searchTerm.trim()) return [];

        const lowerSearchTerm = searchTerm.toLowerCase();
        const suggestions = items.filter(item =>
            (item.name?.toLowerCase().includes(lowerSearchTerm) ||
                item.modelNumber?.toLowerCase().includes(lowerSearchTerm)) &&
            !selectedItemIds.includes(item.id)
        ).slice(0, 5); // عرض أول 5 اقتراحات فقط

        return suggestions;
    }, [items, searchTerm, selectedItemIds]);

    if (loading) return <LoadingSpinner />;

    return (
        <div className="p-6 md:p-8 max-w-[1600px] mx-auto space-y-6">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
                        <Archive className="w-8 h-8 text-blue-600" />
                        أرشيف الفواتير القديمة
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-2">
                        إدارة الفواتير السابقة وإدخال البيانات التاريخية
                    </p>
                </div>
                <div className="flex items-center gap-4">
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                        <span className="font-bold text-blue-600 dark:text-blue-400">{filteredInvoices.length}</span>
                        من أصل <span className="font-bold">{invoices.length}</span> فاتورة
                        {selectedItemIds.length > 0 && (
                            <div className="text-xs text-green-600 dark:text-green-400 mt-1">
                                {selectedItems.length} منتج مختار
                            </div>
                        )}
                    </div>
                    <button
                        onClick={handleCreateNew}
                        className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-bold shadow-lg hover:shadow-blue-500/30"
                    >
                        <Plus className="w-5 h-5" />
                        إضافة فاتورة جديدة
                    </button>
                </div>
            </div>

            {/* Filters */}
            <OldInvoiceFilters
                searchTerm={searchTerm}
                onSearchChange={setSearchTerm}
                selectedSupplierId={selectedSupplierId}
                onSupplierChange={setSelectedSupplierId}
                selectedItemIds={selectedItemIds}
                onItemsChange={setSelectedItemIds}
                dateRange={dateRange}
                onDateRangeChange={setDateRange}
                suppliers={suppliers}
                items={filteredItems}
            />

            {/* Search Suggestions */}
            {searchTerm.trim() && suggestedItems.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-blue-100 dark:border-blue-900/30 p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                            <Package className="w-4 h-4 text-blue-500" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                منتجات مطابقة للبحث: "{searchTerm}"
                            </span>
                        </div>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                            {suggestedItems.length} منتج
                        </span>
                    </div>

                    <div className="flex flex-wrap gap-2">
                        {suggestedItems.map(item => (
                            <button
                                key={item.id}
                                onClick={() => {
                                    if (!selectedItemIds.includes(item.id)) {
                                        setSelectedItemIds(prev => [...prev, item.id]);
                                    }
                                }}
                                className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${selectedItemIds.includes(item.id)
                                    ? 'bg-blue-100 dark:bg-blue-900/30 border-blue-300 dark:border-blue-700'
                                    : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20'
                                    }`}
                            >
                                <div className="text-right">
                                    <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                        {item.name}
                                    </div>
                                    {item.modelNumber && (
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            موديل: {item.modelNumber}
                                        </div>
                                    )}
                                </div>
                                {!selectedItemIds.includes(item.id) && (
                                    <Plus className="w-3 h-3 text-blue-500" />
                                )}
                            </button>
                        ))}
                    </div>

                    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            • انقر على منتج لإضافته إلى الفلترة
                            • البحث يشمل: أسماء المنتجات ورقم المودل
                            • تم العثور على {searchResultItems.length} منتج في نتائج البحث
                        </div>
                    </div>
                </div>
            )}

            {/* Filter Summary */}
            {(selectedItemIds.length > 0 || selectedSupplierId || searchTerm || dateRange.start || dateRange.end) && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">ملخص الفلترة:</span>
                            {searchTerm && (
                                <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded">
                                    بحث: "{searchTerm}"
                                </span>
                            )}
                            {selectedSupplierId && (
                                <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 px-2 py-1 rounded">
                                    مورد: {suppliers.find(s => s.id === selectedSupplierId)?.alias || suppliers.find(s => s.id === selectedSupplierId)?.tradeName}
                                </span>
                            )}
                            {dateRange.start && (
                                <span className="text-xs bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] px-2 py-1 rounded">
                                    من: {dateRange.start}
                                </span>
                            )}
                            {dateRange.end && (
                                <span className="text-xs bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] px-2 py-1 rounded">
                                    إلى: {dateRange.end}
                                </span>
                            )}
                        </div>
                        <button
                            onClick={() => {
                                setSearchTerm('');
                                setSelectedSupplierId('');
                                setSelectedItemIds([]);
                                setDateRange({ start: '', end: '' });
                            }}
                            className="text-xs text-red-500 hover:text-red-600 px-2 py-1 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                        >
                            مسح الكل
                        </button>
                    </div>

                    {/* Selected Items Summary */}
                    {selectedItemIds.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">المنتجات المختارة:</span>
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                    تظهر {filteredInvoices.length} فاتورة تحتوي على هذه المنتجات
                                </span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                                {selectedItems.map(item => (
                                    <div
                                        key={item.id}
                                        className="flex items-center justify-between bg-gray-50 dark:bg-gray-900/50 p-2 rounded-lg"
                                    >
                                        <div className="flex items-center gap-2">
                                            <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/30 rounded flex items-center justify-center">
                                                <Package className="w-4 h-4 text-blue-500" />
                                            </div>
                                            <div className="text-right">
                                                <div className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                                                    {item.name}
                                                </div>
                                                <div className="flex flex-col">
                                                    {item.modelNumber && (
                                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                                            موديل: {item.modelNumber}
                                                        </div>
                                                    )}
                                                    <div className="text-xs text-green-600 dark:text-green-400">
                                                        {filteredItemsCount[item.id] || 0} فاتورة
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => setSelectedItemIds(prev => prev.filter(id => id !== item.id))}
                                            className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                                        >
                                            <Plus className="w-3 h-3 rotate-45" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Search Results Info */}
            {searchTerm.trim() && filteredInvoices.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                نتائج البحث عن "{searchTerm}":
                            </span>
                            <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded">
                                {filteredInvoices.length} فاتورة
                            </span>
                            {searchResultItems.length > 0 && (
                                <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 px-2 py-1 rounded">
                                    {searchResultItems.length} منتج مطابق
                                </span>
                            )}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            البحث يشمل: رقم الفاتورة، المورد، أسماء المنتجات، رقم المودل
                        </div>
                    </div>
                </div>
            )}

            {/* List */}
            <OldInvoiceList
                invoices={filteredInvoices}
                suppliers={suppliers}
                onViewDetails={handleViewDetails}
                onEdit={handleEdit}
                onConvertToMain={handleConvertToMain}
                onDelete={handleDeleteInvoice} // إضافة هذا السطر
                allDbItems={items}
            />

            {/* Modals */}
            <OldInvoiceFormModal
                isOpen={showFormModal}
                onClose={() => {
                    setShowFormModal(false);
                    setEditingInvoice(null);
                }}
                initialData={editingInvoice}
                onSave={handleSaveInvoice}
                suppliers={suppliers}
                items={items}
                onAddSupplier={() => setShowSupplierModal(true)}
            />

            <InvoiceDetailsModal
                isOpen={showDetailsModal}
                onClose={() => {
                    setShowDetailsModal(false);
                    setViewingInvoice(null);
                }}
                invoice={viewingInvoice}
                allDbItems={items}
            />

            <SupplierModal
                isOpen={showSupplierModal}
                onClose={() => setShowSupplierModal(false)}
            />
        </div>
    );
};