import React, { useState, useEffect } from 'react';
import { Invoice, InvoiceItem, Item, Supplier, SupplierItemPrice, DealInvoiceInfo } from '../../../types';
import {
    X, Save, FileText, Paperclip, ImageIcon, Trash2,
    Calculator, ExternalLink, Building // ✅ تمت إضافة Building
} from 'lucide-react';
import { cloudinaryService } from '@/services/cloudinaryService';
import { SupplierSearch } from './SupplierSearch';
import { ItemSearchModal } from '../price-offers/ItemSearchModal';
import { ItemsTableSection } from '../../forms/shared/ItemsTableSection';
import { collection, query, where, orderBy, getDocs, limit, db } from "../../../services/sqlApiClient";

interface OldInvoiceFormModalProps {
    isOpen: boolean;
    onClose: () => void;
    initialData?: Invoice | null;
    onSave: (invoiceData: Partial<Invoice>) => Promise<void>;
    suppliers: Supplier[];
    items: Item[];
    onAddSupplier: () => void;
}

export const OldInvoiceFormModal: React.FC<OldInvoiceFormModalProps> = ({
    isOpen,
    onClose,
    initialData,
    onSave,
    suppliers,
    items,
    onAddSupplier
}) => {
    // Basic Info
    const [invoiceDate, setInvoiceDate] = useState('');
    const [invoiceNumber, setInvoiceNumber] = useState('');
    const [invoiceLink, setInvoiceLink] = useState('');

    // Supplier State
    const [supplierId, setSupplierId] = useState('');
    const [factoryName, setFactoryName] = useState('');
    const [supplierSearch, setSupplierSearch] = useState('');

    // Items
    const [invoiceItems, setInvoiceItems] = useState<InvoiceItem[]>([]);

    // Money
    const [discount, setDiscount] = useState(0);
    const [taxRate, setTaxRate] = useState(0);
    const [taxAmountState, setTaxAmountState] = useState(0);
    const [taxType, setTaxType] = useState<'percentage' | 'amount'>('percentage');
    const [shippingCost, setShippingCost] = useState(0);
    const [shippingIncluded, setShippingIncluded] = useState(false);

    // Shipping & Terms
    const [productionDays, setProductionDays] = useState<number | undefined>(undefined);
    const [deliveryDays, setDeliveryDays] = useState<number | undefined>(undefined);
    const [paymentMethod, setPaymentMethod] = useState('');
    const [shippingMethod, setShippingMethod] = useState('');
    const [warrantyDuration, setWarrantyDuration] = useState<number | undefined>(undefined);
    const [certificates, setCertificates] = useState('');
    const [totalWeight, setTotalWeight] = useState<number | undefined>(undefined);
    const [totalVolume, setTotalVolume] = useState<number | undefined>(undefined);
    const [shipmentNotes, setShipmentNotes] = useState('');

    // Metadata
    const [notes, setNotes] = useState('');
    const [imageUrls, setImageUrls] = useState<string[]>([]);
    const [pdfFiles, setPdfFiles] = useState<Array<{ name: string; url: string; size: number; type: string }>>([]);

    // UI State
    const [isSaving, setIsSaving] = useState(false);
    const [uploadingImages, setUploadingImages] = useState(false);
    const [uploadingPdfs, setUploadingPdfs] = useState(false);
    const [showItemSearchModal, setShowItemSearchModal] = useState(false);
    const [currentItemIndex, setCurrentItemIndex] = useState<number | null>(null);
    const [itemSearchQuery, setItemSearchQuery] = useState('');

    // Load initial data
    useEffect(() => {
        if (isOpen && initialData) {
            setInvoiceDate(initialData.invoiceDate || '');
            setInvoiceNumber(initialData.invoiceNumber || '');
            setInvoiceLink(initialData.invoiceLink || '');
            setSupplierId(initialData.supplierId);
            setFactoryName(initialData.factoryName || '');
            // ⚠️ تعديل: لا نضع الاسم في البحث عند التحميل، المكون سيعرض الاسم بناءً على ID
            setSupplierSearch('');

            // Set Items
            if (initialData.items) {
                setInvoiceItems(initialData.items);
            }

            setNotes(initialData.notes || '');
            setImageUrls(initialData.imageUrls || []);

            // Handle PDFs
            const pdfs = initialData.pdfFiles?.map(f => ({
                name: f.name || 'document.pdf',
                url: f.url,
                size: f.size || 0,
                type: f.type || 'application/pdf'
            })) || [];
            setPdfFiles(pdfs);

            setDiscount(initialData.discountAmount || 0);
            setTaxRate(initialData.taxRate || 0);
            setTaxAmountState(initialData.taxAmount || 0);
            setTaxType(initialData.taxType || 'percentage');
            setShippingCost(initialData.shippingCost || 0);
            setShippingIncluded(initialData.shippingIncluded || false);

            if (initialData.dealInfo) {
                setProductionDays(initialData.dealInfo.productionDays);
                setDeliveryDays(initialData.dealInfo.deliveryDays);
                setPaymentMethod(initialData.dealInfo.paymentMethod || '');
                setShippingMethod(initialData.dealInfo.shippingMethod || '');
                setWarrantyDuration(initialData.dealInfo.warrantyDuration);
                setCertificates(initialData.dealInfo.certificates || '');
                setShipmentNotes(initialData.dealInfo.shipmentNotes || '');
            }
            setTotalWeight(initialData.totalWeight);
            setTotalVolume(initialData.totalVolume);
        } else if (isOpen) {
            // Reset form for new entry
            resetForm();
        }
    }, [isOpen, initialData]);

    const resetForm = () => {
        setInvoiceDate(new Date().toISOString().split('T')[0]);
        setInvoiceNumber('');
        setInvoiceLink('');
        setSupplierId('');
        setFactoryName('');
        setSupplierSearch('');
        setInvoiceItems([]);
        setNotes('');
        setImageUrls([]);
        setPdfFiles([]);
        setDiscount(0);
        setTaxRate(0);
        setTaxAmountState(0);
        setTaxType('percentage');
        setShippingCost(0);
        setShippingIncluded(false);
        setProductionDays(undefined);
        setDeliveryDays(undefined);
        setPaymentMethod('');
        setShippingMethod('');
        setWarrantyDuration(undefined);
        setCertificates('');
        setTotalWeight(undefined);
        setTotalVolume(undefined);
        setShipmentNotes('');
    };

    // Helper: Fetch last price
    const fetchLastPrice = async (itemId: string, currentSupplierId: string) => {
        if (!itemId || !currentSupplierId) return 0;
        try {
            const q = query(
                collection(db, "supplier_prices"),
                where("supplierId", "==", currentSupplierId),
                where("itemId", "==", itemId),
                orderBy("date", "desc"),
                limit(1)
            );
            const snapshot = await getDocs(q);
            if (!snapshot.empty) {
                const data = snapshot.docs[0].data() as SupplierItemPrice;
                return data.price || 0;
            }
        } catch (error) {
            console.error("Error fetching last price:", error);
        }
        return 0;
    };

    // ---- Handlers ----

    // ✅ تحديث دالة اختيار المورد لتتوافق مع المكون الجديد
    const handleSelectSupplier = (id: string) => {
        setSupplierId(id);
        const supplier = suppliers.find(s => s.id === id);
        if (supplier) {
            setFactoryName(supplier.tradeName);
            // ✅ نصفر البحث، لأن المكون سيعرض "البطاقة الصغيرة" للمورد المختار داخلياً
            setSupplierSearch('');
        }
    };

    // Item Management
    const addLineItem = () => {
        const newItem: InvoiceItem = {
            id: crypto.randomUUID(),
            itemId: '',
            name: '',
            categoryId: '',
            categoryName: '',
            specifications: '',
            imageUrls: [],
            quantity: 1,
            unitPrice: 0,
            totalPrice: 0
        };
        setInvoiceItems([...invoiceItems, newItem]);
        setCurrentItemIndex(invoiceItems.length);
        setItemSearchQuery('');
        setShowItemSearchModal(true);
    };

    const updateItem = (index: number, field: keyof InvoiceItem, value: any) => {
        const newItems = [...invoiceItems];
        const item = { ...newItems[index], [field]: value };

        if (field === 'quantity' || field === 'unitPrice') {
            item.totalPrice = (Number(item.quantity) || 0) * (Number(item.unitPrice) || 0);
        }

        newItems[index] = item;
        setInvoiceItems(newItems);
    };

    const removeItem = (index: number) => {
        setInvoiceItems(invoiceItems.filter((_, i) => i !== index));
    };

    const handleSelectItem = async (item: Item, lastPrice?: number) => {
        if (currentItemIndex === null) return;

        const newItems = [...invoiceItems];
        const invoiceItem = newItems[currentItemIndex];

        invoiceItem.itemId = item.id;
        invoiceItem.name = item.name;
        invoiceItem.categoryName = item.categoryName;
        invoiceItem.specifications = item.specifications || '';
        invoiceItem.imageUrls = item.imageUrls || [];
        invoiceItem.hsCodePrimary = item.hsCodePrimary;

        // Set Price
        if (lastPrice && lastPrice > 0) {
            invoiceItem.unitPrice = lastPrice;
        } else if (supplierId) {
            const price = await fetchLastPrice(item.id, supplierId);
            if (price > 0) {
                invoiceItem.unitPrice = price;
            }
        }

        invoiceItem.totalPrice = (Number(invoiceItem.quantity) || 0) * (Number(invoiceItem.unitPrice) || 0);

        setInvoiceItems(newItems);
        setShowItemSearchModal(false);
        setCurrentItemIndex(null);
    };

    // File Uploads
    const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files || e.target.files.length === 0) return;
        setUploadingImages(true);
        const files: File[] = Array.from(e.target.files);
        const newUrls: string[] = [];

        try {
            for (const file of files) {
                if (!file.type.startsWith('image/')) continue;
                const imageUrl = await cloudinaryService.uploadImage(file);
                if (imageUrl) newUrls.push(imageUrl);
            }
            setImageUrls(prev => [...prev, ...newUrls]);
        } catch (error) {
            console.error("Error uploading images:", error);
            alert("فشل رفع الصور");
        } finally {
            setUploadingImages(false);
            e.target.value = '';
        }
    };

    const convertFileToBase64 = (file: File): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = error => reject(error);
        });
    };

    const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files || e.target.files.length === 0) return;
        setUploadingPdfs(true);
        const files: File[] = Array.from(e.target.files);
        const newPdfFiles: Array<{ name: string; url: string; size: number; type: string }> = [];

        try {
            for (const file of files) {
                if (file.type !== 'application/pdf') {
                    alert(`الملف ${file.name} ليس PDF.`);
                    continue;
                }
                const base64Data = await convertFileToBase64(file);
                newPdfFiles.push({
                    name: file.name,
                    url: base64Data,
                    size: file.size,
                    type: file.type
                });
            }
            setPdfFiles(prev => [...prev, ...newPdfFiles]);
        } catch (error) {
            console.error("Error uploading PDF files:", error);
            alert("حدث خطأ أثناء معالجة ملفات PDF");
        } finally {
            setUploadingPdfs(false);
            e.target.value = '';
        }
    };

    // Totals Calculation
    const subtotal = invoiceItems.reduce((sum, item) => sum + item.totalPrice, 0);
    const afterDiscount = Math.max(0, subtotal - discount);

    let taxAmount = 0;
    if (taxType === 'amount') {
        taxAmount = taxAmountState || 0;
    } else {
        taxAmount = (afterDiscount * taxRate) / 100;
    }

    const grandTotal = afterDiscount + taxAmount;

    // Submit
    const handleSubmit = async () => {
        if (!invoiceDate || !supplierId || !invoiceNumber || invoiceItems.length === 0) {
            alert('يرجى تعبئة الحقول الأساسية: التاريخ، المورد، رقم الفاتورة، وبند واحد على الأقل.');
            return;
        }

        setIsSaving(true);
        try {
            const invoiceData: Partial<Invoice> = {
                invoiceDate,
                invoiceNumber,
                invoiceLink,
                supplierId,
                factoryName,
                items: invoiceItems,
                notes,
                imageUrls,
                pdfFiles,
                subtotal,
                taxRate,
                taxAmount,
                grandTotal,
                shippingCost,
                shippingIncluded,
                totalWeight,
                totalVolume,
                dealInfo: {
                    productionDays,
                    deliveryDays,
                    paymentMethod,
                    shippingMethod,
                    warrantyDuration,
                    certificates,
                    shipmentNotes,
                    createdBy: initialData?.dealInfo?.createdBy || ''
                } as DealInvoiceInfo,
                isHistorical: true
            };

            await onSave(invoiceData);
            onClose();
        } catch (error) {
            console.error(error);
            alert('حدث خطأ أثناء الحفظ');
        } finally {
            setIsSaving(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4 overflow-y-auto">
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-6xl my-8 flex flex-col relative">
                {/* Header */}
                <div className="sticky top-0 bg-white dark:bg-gray-800 p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center z-20 rounded-t-2xl">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                            <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                                {initialData ? 'تعديل فاتورة مؤرشفة' : 'إضافة فاتورة قديمة للأرشيف'}
                            </h2>
                            <p className="text-sm text-gray-500 dark:text-gray-400">
                                {initialData ? `رقم الفاتورة: ${initialData.invoiceNumber}` : 'إدخال بيانات فاتورة سابقة لغرض الأرشفة ومتابعة الأسعار'}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                        <X className="w-6 h-6 text-gray-500" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6 md:p-8 space-y-8 overflow-y-auto max-h-[calc(100vh-150px)]">

                    {/* Top Row: Basic Info & Supplier */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div className="space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                        تاريخ الفاتورة *
                                    </label>
                                    <input
                                        type="date"
                                        value={invoiceDate}
                                        onChange={(e) => setInvoiceDate(e.target.value)}
                                        className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                        رقم الفاتورة *
                                    </label>
                                    <input
                                        type="text"
                                        value={invoiceNumber}
                                        onChange={(e) => setInvoiceNumber(e.target.value)}
                                        placeholder="مثال: 00123"
                                        className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                    رابط الفاتورة (اختياري)
                                </label>
                                <div className="relative">
                                    <ExternalLink className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                    <input
                                        type="url"
                                        value={invoiceLink}
                                        onChange={(e) => setInvoiceLink(e.target.value)}
                                        placeholder="https://example.com/invoice/123"
                                        className="w-full pr-10 pl-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-left"
                                        dir="ltr"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* ✅ قسم اختيار المورد بالتنسيق الجديد */}
                        <div className="space-y-1.5">
                            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                                <Building className="w-3.5 h-3.5 text-blue-600" />
                                المورد / المصنع <span className="text-red-500">*</span>
                            </label>
                            <SupplierSearch
                                suppliers={suppliers}
                                selectedSupplierId={supplierId}
                                supplierSearch={supplierSearch}
                                onSearchChange={setSupplierSearch}
                                onSelectSupplier={handleSelectSupplier}
                                onClearSupplier={() => {
                                    setSupplierId('');
                                    setFactoryName('');
                                    setSupplierSearch('');
                                }}
                                type="factory"
                                onOpenAddModal={onAddSupplier} // اختياري: إذا أردت تفعيل زر الإضافة
                            />
                        </div>
                    </div>

                    {/* Items Table */}
                    <ItemsTableSection
                        items={invoiceItems}
                        onUpdateItem={(index, field, value) => updateItem(index, field as keyof InvoiceItem, value)}
                        onRemoveItem={removeItem}
                        onAddItem={addLineItem}
                        onPreviewImage={() => { }}
                        allDbItems={items}
                        discountAmount={discount}
                        taxRate={taxRate}
                        taxAmount={taxAmountState}
                        taxType={taxType}
                        shippingCost={shippingCost}
                        shippingIncluded={shippingIncluded}
                        productionDays={productionDays}
                        deliveryDays={deliveryDays}
                        paymentMethod={paymentMethod}
                        shippingMethod={shippingMethod}
                        warrantyDuration={warrantyDuration}
                        certificates={certificates}
                        totalWeight={totalWeight}
                        totalVolume={totalVolume}
                        shipmentNotes={shipmentNotes}
                        onUpdateFinancial={(field, value) => {
                            if (field === 'taxRate') setTaxRate(value);
                            if (field === 'taxAmount') setTaxAmountState(value);
                            if (field === 'taxType') setTaxType(value);

                            const setters: Record<string, Function> = {
                                discountAmount: setDiscount,
                                shippingCost: setShippingCost,
                                shippingIncluded: setShippingIncluded,
                                productionDays: setProductionDays,
                                deliveryDays: setDeliveryDays,
                                paymentMethod: setPaymentMethod,
                                shippingMethod: setShippingMethod,
                                warrantyDuration: setWarrantyDuration,
                                certificates: setCertificates,
                                totalWeight: setTotalWeight,
                                totalVolume: setTotalVolume,
                                shipmentNotes: setShipmentNotes
                            };
                            if (setters[field]) setters[field](value);
                        }}
                    />

                    {/* Footer Section ... (بقية الكود كما هو) */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        <div className="lg:col-span-2 space-y-6">
                            {/* Notes */}
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                    ملاحظات
                                </label>
                                <textarea
                                    rows={3}
                                    value={notes}
                                    onChange={(e) => setNotes(e.target.value)}
                                    className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 focus:ring-2 focus:ring-blue-500"
                                    placeholder="ملاحظات إضافية..."
                                />
                            </div>

                            {/* Attachments */}
                            <div className="bg-gray-50 dark:bg-gray-900/30 p-6 rounded-xl border border-gray-200 dark:border-gray-700">
                                <h4 className="font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                    <Paperclip className="w-5 h-5 text-gray-500" /> المرفقات
                                </h4>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                                    {/* Image Upload */}
                                    <label className={`
                                        flex flex-col items-center justify-center p-4 border-2 border-dashed rounded-xl cursor-pointer transition-all
                                        ${uploadingImages ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-green-500 hover:bg-green-50 dark:border-gray-600 dark:hover:bg-gray-800'}
                                     `}>
                                        <ImageIcon className={`w-8 h-8 mb-2 ${uploadingImages ? 'text-green-500 animate-pulse' : 'text-gray-400'}`} />
                                        <span className="text-sm font-medium text-gray-600 dark:text-gray-300">
                                            {uploadingImages ? 'جاري الرفع...' : 'رفع صور'}
                                        </span>
                                        <input type="file" multiple accept="image/*" className="hidden" onChange={handleImageUpload} disabled={uploadingImages} />
                                    </label>

                                    {/* PDF Upload */}
                                    <label className={`
                                        flex flex-col items-center justify-center p-4 border-2 border-dashed rounded-xl cursor-pointer transition-all
                                        ${uploadingPdfs ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-500 hover:bg-blue-50 dark:border-gray-600 dark:hover:bg-gray-800'}
                                     `}>
                                        <FileText className={`w-8 h-8 mb-2 ${uploadingPdfs ? 'text-blue-500 animate-pulse' : 'text-gray-400'}`} />
                                        <span className="text-sm font-medium text-gray-600 dark:text-gray-300">
                                            {uploadingPdfs ? 'جاري الرفع...' : 'رفع PDF'}
                                        </span>
                                        <input type="file" multiple accept=".pdf,application/pdf" className="hidden" onChange={handlePdfUpload} disabled={uploadingPdfs} />
                                    </label>
                                </div>

                                {/* File List */}
                                <div className="space-y-3">
                                    {imageUrls.map((url, i) => (
                                        <div key={i} className="flex items-center justify-between p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
                                            <div className="flex items-center gap-3">
                                                <img src={url} alt="Attachment" className="w-10 h-10 rounded object-cover" />
                                                <span className="text-sm truncate max-w-[150px]">Image {i + 1}</span>
                                            </div>
                                            <button onClick={() => setImageUrls(prev => prev.filter((_, idx) => idx !== i))} className="text-red-500 hover:bg-red-50 p-1 rounded">
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ))}
                                    {pdfFiles.map((file, i) => (
                                        <div key={i} className="flex items-center justify-between p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
                                            <div className="flex items-center gap-3">
                                                <FileText className="w-8 h-8 text-red-500" />
                                                <div className="text-sm">
                                                    <div className="font-medium truncate max-w-[150px]">{file.name}</div>
                                                    <div className="text-xs text-gray-400">{(file.size / 1024).toFixed(1)} KB</div>
                                                </div>
                                            </div>
                                            <button onClick={() => setPdfFiles(prev => prev.filter((_, idx) => idx !== i))} className="text-red-500 hover:bg-red-50 p-1 rounded">
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* Totals Box */}
                        <div className="bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg h-fit">
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
                                <Calculator className="w-6 h-6 text-blue-600" /> ملخص الفاتورة
                            </h3>

                            <div className="space-y-4">
                                <div className="flex justify-between py-2 border-b dark:border-gray-700">
                                    <span className="text-gray-600 dark:text-gray-400">المجموع الفرعي</span>
                                    <span className="font-bold">{subtotal.toLocaleString()} $</span>
                                </div>
                                <div className="flex justify-between items-center py-2 border-b dark:border-gray-700">
                                    <label className="text-sm text-gray-600 dark:text-gray-400">خصم ($)</label>
                                    <input
                                        type="number"
                                        value={discount}
                                        onChange={e => setDiscount(parseFloat(e.target.value) || 0)}
                                        className="w-24 px-2 py-1 text-right border rounded bg-white dark:bg-gray-700"
                                    />
                                </div>
                                <div className="flex justify-between items-center py-2 border-b dark:border-gray-700">
                                    <label className="text-sm text-gray-600 dark:text-gray-400">الضريبة ({taxType === 'amount' ? '$' : '%'})</label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="number"
                                            value={taxType === 'amount' ? taxAmountState : taxRate}
                                            onChange={e => {
                                                const val = parseFloat(e.target.value) || 0;
                                                if (taxType === 'amount') setTaxAmountState(val);
                                                else setTaxRate(val);
                                            }}
                                            className="w-16 px-2 py-1 text-right border rounded bg-white dark:bg-gray-700"
                                        />
                                        <span className="text-xs text-gray-500">
                                            {taxType === 'percentage' ? `(${taxAmount.toLocaleString()} $)` : `(${taxRate} %)`}
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div className="pt-4 flex justify-between items-center text-xl font-bold">
                                <span>الإجمالي</span>
                                <span className="text-blue-600 dark:text-blue-400">{grandTotal.toLocaleString()} $</span>
                            </div>
                        </div>

                        <button
                            onClick={handleSubmit}
                            disabled={isSaving}
                            className="w-full mt-6 flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl hover:shadow-lg disabled:opacity-50 transition-all font-bold"
                        >
                            {isSaving ? <div className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full" /> : <Save className="w-5 h-5" />}
                            {initialData ? 'حفظ التعديلات' : 'أرشفة الفاتورة'}
                        </button>
                    </div>
                </div>

                {/* Item Search Modal */}
                <ItemSearchModal
                    isOpen={showItemSearchModal}
                    onClose={() => setShowItemSearchModal(false)}
                    onSelectItem={handleSelectItem}
                    items={items}
                    supplierId={supplierId}
                />
            </div>
        </div>
    );
};