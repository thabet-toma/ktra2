import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Invoice, InvoiceItem, Item, Supplier, SupplierItemPrice, DealInvoiceInfo } from '../../../types';
import {
    X, Save, FileText, Paperclip, Trash2,
    Calculator, ExternalLink, Building, // ✅ تمت إضافة Building
} from 'lucide-react';
import { cloudinaryService } from '@/services/cloudinaryService';
import { FileDropZone } from '../../ui/FileDropZone';
import { useToast } from '../../../contexts/ToastContext';
import { humanizeThrown } from '../../../utils/drfError';
import { SupplierSearch } from './SupplierSearch';
import { ItemSearchModal } from '../price-offers/ItemSearchModal';
import { ItemsTableSection } from '../../forms/shared/ItemsTableSection';
import { collection, query, where, orderBy, getDocs, limit, db } from "../../../services/sqlApiClient";
import { useDocumentDraft } from '../../../hooks/useDocumentDraft';
import { DocumentDraftBanners } from '../../shared/DocumentDraftBanners';
import { formatTimeValue } from '../../../utils/formatDate';

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
    const toast = useToast();

    // ISSUE #121: علامة «لُمِس» — تُرفَع مزامنةً داخل كل معالج تعديل مستخدم فعليّ
    // (لا داخل useEffect؛ راجع تعليق `useDocumentDraft.ts` نفسه).
    const [touched, setTouched] = useState(false);
    const markTouched = () => setTouched(true);

    /** يملأ النموذج من فاتورةٍ أرشيفية قائمة — تحميلٌ لا لمسٌ. مشتركةٌ بين فتح
     *  المودال العادي (`initialData`) و«تراجع» عن مسودّةٍ لنفس الفاتورة. */
    const populateFromInvoice = (data: Invoice) => {
        setInvoiceDate(data.invoiceDate || '');
        setInvoiceNumber(data.invoiceNumber || '');
        setInvoiceLink(data.invoiceLink || '');
        setSupplierId(data.supplierId);
        setFactoryName(data.factoryName || '');
        // ⚠️ تعديل: لا نضع الاسم في البحث عند التحميل، المكون سيعرض الاسم بناءً على ID
        setSupplierSearch('');

        // Set Items
        setInvoiceItems(data.items || []);

        setNotes(data.notes || '');
        setImageUrls(data.imageUrls || []);

        // Handle PDFs — الحقل غير معلَنٍ على نوع `Invoice` (فجوةٌ سابقة على هذه
        // المهمة: البيانات الفعلية القادمة من الخادم/الأرشيف تحمله رغم ذلك)،
        // فيُقرأ بأمانٍ عبر Cast ضيّق بدل تعديل النوع خارج نطاق المهمة.
        const pdfs = (data as unknown as { pdfFiles?: Array<{ name?: string; url: string; size?: number; type?: string }> }).pdfFiles?.map(f => ({
            name: f.name || 'document.pdf',
            url: f.url,
            size: f.size || 0,
            type: f.type || 'application/pdf'
        })) || [];
        setPdfFiles(pdfs);

        setDiscount(data.discountAmount || 0);
        setTaxRate(data.taxRate || 0);
        setTaxAmountState(data.taxAmount || 0);
        setTaxType(data.taxType || 'percentage');
        setShippingCost(data.shippingCost || 0);
        setShippingIncluded(data.shippingIncluded || false);

        if (data.dealInfo) {
            setProductionDays(data.dealInfo.productionDays);
            setDeliveryDays(data.dealInfo.deliveryDays);
            setPaymentMethod(data.dealInfo.paymentMethod || '');
            setShippingMethod(data.dealInfo.shippingMethod || '');
            setWarrantyDuration(data.dealInfo.warrantyDuration);
            setCertificates(data.dealInfo.certificates || '');
            setShipmentNotes(data.dealInfo.shipmentNotes || '');
        } else {
            setProductionDays(undefined);
            setDeliveryDays(undefined);
            setPaymentMethod('');
            setShippingMethod('');
            setWarrantyDuration(undefined);
            setCertificates('');
            setShipmentNotes('');
        }
        setTotalWeight(data.totalWeight);
        setTotalVolume(data.totalVolume);
    };

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
        setTouched(false);
    };

    // Load initial data — تحميلٌ متزامنٌ من props (initialData جاهزة في الذاكرة
    // بلا fetch)، فينفّذ بالكامل قبل أن تصل استعادةُ المسودّة غير المتزامنة
    // (IndexedDB) — لا سباقَ إذن، والاستعادة (إن أهّلتها) تكتب فوق هذا التحميل
    // لاحقاً كالمعتاد (ISSUE #121 الدرس ٢).
    useEffect(() => {
        if (isOpen && initialData) {
            populateFromInvoice(initialData);
            setTouched(false);
        } else if (isOpen) {
            // Reset form for new entry
            resetForm();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, initialData]);

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
            // console suppressed
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
        markTouched();
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
        markTouched();
    };

    const updateItem = (index: number, field: keyof InvoiceItem, value: any) => {
        const newItems = [...invoiceItems];
        const item = { ...newItems[index], [field]: value };

        if (field === 'quantity' || field === 'unitPrice') {
            item.totalPrice = (Number(item.quantity) || 0) * (Number(item.unitPrice) || 0);
        }

        newItems[index] = item;
        setInvoiceItems(newItems);
        markTouched();
    };

    const removeItem = (index: number) => {
        setInvoiceItems(invoiceItems.filter((_, i) => i !== index));
        markTouched();
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
        markTouched();
    };

    // File Uploads — الاختيار والسحب واللصق (Ctrl+V) صارت كلها داخل `FileDropZone`،
    // وفحص النوع والحجم يقع فيها، فما يصل إلى هاتين الدالتين مقبول أصلاً.
    const uploadImageFiles = async (files: File[]) => {
        setUploadingImages(true);
        const newUrls: string[] = [];
        try {
            for (const file of files) {
                const imageUrl = await cloudinaryService.uploadImage(file);
                if (imageUrl) newUrls.push(imageUrl);
            }
            setImageUrls(prev => [...prev, ...newUrls]);
            if (newUrls.length > 0) markTouched();
        } catch (error) {
            // console suppressed
            toast('فشل رفع الصور.', 'error');
        } finally {
            setUploadingImages(false);
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

    const addPdfFiles = async (files: File[]) => {
        if (files.length === 0) return;
        setUploadingPdfs(true);
        const newPdfFiles: Array<{ name: string; url: string; size: number; type: string }> = [];

        try {
            for (const file of files) {
                const base64Data = await convertFileToBase64(file);
                newPdfFiles.push({
                    name: file.name,
                    url: base64Data,
                    size: file.size,
                    type: file.type
                });
            }
            setPdfFiles(prev => [...prev, ...newPdfFiles]);
            markTouched();
        } catch (error) {
            // console suppressed
            toast('حدث خطأ أثناء معالجة ملفات PDF.', 'error');
        } finally {
            setUploadingPdfs(false);
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

    /* ISSUE #121: مسودّة محلية (IndexedDB، issue #118) — هذه الشاشةُ مودالٌ يبقى
     * مُركَّباً طوال عمر الصفحة الأمّ (`isOpen` يتحكّم بالعرض فقط)، ويحرّر فاتورةً
     * أرشيفية قائمة (`initialData`) أو ينشئ جديدة. `docId`/`docUpdatedAt` من
     * `initialData` مباشرةً — الفاتورة الأرشيفية تحمل `updatedAt` حقيقياً من
     * الخادم دائماً (خلافاً لبعض شاشات هذه الدفعة)، فلا فجوة هنا. لا مفهوم
     * «ترحيل» لفاتورةٍ أرشيفية (isPosted: false دائماً). الحمولة كائنٌ خفيف
     * يكفي وحده لإعادة بناء النموذج — تستثني المجاميع المُشتقّة (subtotal/
     * taxAmount/grandTotal) لأنها تُحسَب من البنود نفسها، لا تُخزَّن. */
    const draftPayload = useMemo(
        () => ({
            invoiceDate, invoiceNumber, invoiceLink, supplierId, factoryName,
            invoiceItems, notes, imageUrls, pdfFiles,
            discount, taxRate, taxAmountState, taxType, shippingCost, shippingIncluded,
            productionDays, deliveryDays, paymentMethod, shippingMethod,
            warrantyDuration, certificates, totalWeight, totalVolume, shipmentNotes,
        }),
        [
            invoiceDate, invoiceNumber, invoiceLink, supplierId, factoryName,
            invoiceItems, notes, imageUrls, pdfFiles,
            discount, taxRate, taxAmountState, taxType, shippingCost, shippingIncluded,
            productionDays, deliveryDays, paymentMethod, shippingMethod,
            warrantyDuration, certificates, totalWeight, totalVolume, shipmentNotes,
        ],
    );

    type OldInvoiceDraftPayload = typeof draftPayload;

    const onRestoreDraft = useCallback((restored: OldInvoiceDraftPayload) => {
        setInvoiceDate(restored.invoiceDate);
        setInvoiceNumber(restored.invoiceNumber);
        setInvoiceLink(restored.invoiceLink);
        setSupplierId(restored.supplierId);
        setFactoryName(restored.factoryName);
        setSupplierSearch('');
        setInvoiceItems(restored.invoiceItems);
        setNotes(restored.notes);
        setImageUrls(restored.imageUrls);
        setPdfFiles(restored.pdfFiles);
        setDiscount(restored.discount);
        setTaxRate(restored.taxRate);
        setTaxAmountState(restored.taxAmountState);
        setTaxType(restored.taxType);
        setShippingCost(restored.shippingCost);
        setShippingIncluded(restored.shippingIncluded);
        setProductionDays(restored.productionDays);
        setDeliveryDays(restored.deliveryDays);
        setPaymentMethod(restored.paymentMethod);
        setShippingMethod(restored.shippingMethod);
        setWarrantyDuration(restored.warrantyDuration);
        setCertificates(restored.certificates);
        setTotalWeight(restored.totalWeight);
        setTotalVolume(restored.totalVolume);
        setShipmentNotes(restored.shipmentNotes);
        // استعادةٌ من مسودّة تعني اختلافاً عن آخر نسخة محفوظة/الشاشة الفارغة —
        // تُسجَّل «ملموسة».
        setTouched(true);
    }, []);

    const draftApi = useDocumentDraft<OldInvoiceDraftPayload>({
        docType: 'old_purchase_invoice',
        docId: initialData?.id ?? null,
        payload: draftPayload,
        isTouched: touched,
        onRestore: onRestoreDraft,
        isPosted: false,
        docUpdatedAt: initialData?.updatedAt ?? null,
    });
    const { draftSavedAt, draftSaveFailed, discardDraft } = draftApi;

    /* ISSUE #120: الحارسُ مقلوب — يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ فعلاً. */
    useEffect(() => {
        const handleBeforeUnload = (e: BeforeUnloadEvent) => {
            if (draftSaveFailed) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, [draftSaveFailed]);

    /** «تراجع» على شريط الاستعادة: يعيد النموذج إلى آخر نسخةٍ محفوظة (أو
     *  الحالة الفارغة لفاتورةٍ جديدة) ويمسح المسودّة. */
    const handleUndoDraft = useCallback(() => {
        if (initialData) populateFromInvoice(initialData);
        else resetForm();
        setTouched(false);
        void discardDraft();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialData, discardDraft]);

    // Submit
    const handleSubmit = async () => {
        if (!invoiceDate || !supplierId || !invoiceNumber || invoiceItems.length === 0) {
            toast("يرجى تعبئة الحقول الأساسية: التاريخ، المورد، رقم الفاتورة، وبند واحد على الأقل.", "error");
            return;
        }

        setIsSaving(true);
        try {
            const invoiceData = {
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
            // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
            void discardDraft();
        } catch (error) {
            // console suppressed
            // السبب الحقيقي بدل جملة عامة؛ النافذة تبقى مفتوحة بمدخلاتها.
            toast(humanizeThrown(error, "تعذّر حفظ الفاتورة"), "error");
        } finally {
            setIsSaving(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4 overflow-y-auto">
            <div className="ktra-bg-field dark:ktra-bg-panel rounded-2xl shadow-2xl w-full max-w-6xl my-8 flex flex-col relative">
                {/* Header */}
                <div className="sticky top-0 ktra-bg-field dark:ktra-bg-panel p-6 border-b ktra-border-soft dark:ktra-border-soft flex justify-between items-center z-20 rounded-t-2xl">
                    <div className="flex items-center gap-3">
                        <div className="p-2 ktra-bg-accent-bg dark:ktra-bg-panel/30 rounded-lg">
                            <FileText className="w-6 h-6 ktra-text-accent dark:ktra-text-soft" />
                        </div>
                        <div>
                            <h2 className="text-2xl font-bold ktra-text-ink dark:text-white">
                                {initialData ? 'تعديل فاتورة مؤرشفة' : 'إضافة فاتورة قديمة للأرشيف'}
                            </h2>
                            <p className="text-sm ktra-text-soft dark:ktra-text-soft">
                                {initialData ? `رقم الفاتورة: ${initialData.invoiceNumber}` : 'إدخال بيانات فاتورة سابقة لغرض الأرشفة ومتابعة الأسعار'}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg">
                        <X className="w-6 h-6 ktra-text-soft" />
                    </button>
                </div>

                <DocumentDraftBanners draft={draftApi} onApplyDraft={onRestoreDraft} onUndo={handleUndoDraft} isTouched={touched} />

                {/* Content */}
                <div className="p-6 md:p-8 space-y-8 overflow-y-auto max-h-[calc(100vh-150px)]">

                    {/* Top Row: Basic Info & Supplier */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div className="space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-semibold ktra-text-ink dark:ktra-text-soft mb-2">
                                        تاريخ الفاتورة *
                                    </label>
                                    <input
                                        type="date"
                                        value={invoiceDate}
                                        onChange={(e) => { setInvoiceDate(e.target.value); markTouched(); }}
                                        className="w-full px-4 py-3 rounded-lg border ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel ktra-text-ink dark:text-white focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-semibold ktra-text-ink dark:ktra-text-soft mb-2">
                                        رقم الفاتورة *
                                    </label>
                                    <input
                                        type="text"
                                        data-testid="old-invoice-number"
                                        value={invoiceNumber}
                                        onChange={(e) => { setInvoiceNumber(e.target.value); markTouched(); }}
                                        placeholder="مثال: 00123"
                                        className="w-full px-4 py-3 rounded-lg border ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel ktra-text-ink dark:text-white focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-semibold ktra-text-ink dark:ktra-text-soft mb-2">
                                    رابط الفاتورة (اختياري)
                                </label>
                                <div className="relative">
                                    <ExternalLink className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 ktra-text-soft" />
                                    <input
                                        type="url"
                                        value={invoiceLink}
                                        onChange={(e) => { setInvoiceLink(e.target.value); markTouched(); }}
                                        placeholder="https://example.com/invoice/123"
                                        className="w-full pr-10 pl-4 py-3 rounded-lg border ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel ktra-text-ink dark:text-white focus:ring-2 focus:ring-blue-500 text-left"
                                        dir="ltr"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* ✅ قسم اختيار المورد بالتنسيق الجديد */}
                        <div className="space-y-1.5">
                            <label className="block text-xs font-semibold ktra-text-ink dark:ktra-text-soft flex items-center gap-1.5">
                                <Building className="w-3.5 h-3.5 ktra-text-accent" />
                                المورد / المصنع <span className="ktra-text-soft">*</span>
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
                                    markTouched();
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
                            markTouched();
                        }}
                    />

                    {/* Footer Section ... (بقية الكود كما هو) */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        <div className="lg:col-span-2 space-y-6">
                            {/* Notes */}
                            <div>
                                <label className="block text-sm font-semibold ktra-text-ink dark:ktra-text-soft mb-2">
                                    ملاحظات
                                </label>
                                <textarea
                                    rows={3}
                                    value={notes}
                                    onChange={(e) => { setNotes(e.target.value); markTouched(); }}
                                    className="w-full px-4 py-3 rounded-lg border ktra-border-soft dark:ktra-border-soft ktra-bg-field dark:ktra-bg-panel focus:ring-2 focus:ring-blue-500"
                                    placeholder="ملاحظات إضافية..."
                                />
                            </div>

                            {/* Attachments */}
                            <div className="ktra-bg-panel dark:ktra-bg-panel/30 p-6 rounded-xl border ktra-border-soft dark:ktra-border-soft">
                                <h4 className="font-bold ktra-text-ink dark:text-white mb-4 flex items-center gap-2">
                                    <Paperclip className="w-5 h-5 ktra-text-soft" /> المرفقات
                                </h4>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                                    {/* Image Upload */}
                                    <FileDropZone
                                        onFiles={(files) => { void uploadImageFiles(files); }}
                                        accept="image"
                                        multiple
                                        busy={uploadingImages}
                                        variant="compact"
                                        hint="صور: اضغط، اسحب، أو الصق (Ctrl+V)"
                                    />

                                    {/* PDF Upload */}
                                    <FileDropZone
                                        onFiles={(files) => { void addPdfFiles(files); }}
                                        accept="pdf"
                                        multiple
                                        busy={uploadingPdfs}
                                        variant="compact"
                                        hint="PDF: اضغط أو اسحب الملف إلى هنا"
                                    />
                                </div>

                                {/* File List */}
                                <div className="space-y-3">
                                    {imageUrls.map((url, i) => (
                                        <div key={i} className="flex items-center justify-between p-2 ktra-bg-field dark:ktra-bg-panel rounded border ktra-border-soft dark:ktra-border-soft">
                                            <div className="flex items-center gap-3">
                                                <img src={url} alt="Attachment" className="w-10 h-10 rounded object-cover" />
                                                <span className="text-sm truncate max-w-[150px]">Image {i + 1}</span>
                                            </div>
                                            <button onClick={() => { setImageUrls(prev => prev.filter((_, idx) => idx !== i)); markTouched(); }} className="ktra-text-soft hover:ktra-bg-panel p-1 rounded">
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ))}
                                    {pdfFiles.map((file, i) => (
                                        <div key={i} className="flex items-center justify-between p-2 ktra-bg-field dark:ktra-bg-panel rounded border ktra-border-soft dark:ktra-border-soft">
                                            <div className="flex items-center gap-3">
                                                <FileText className="w-8 h-8 ktra-text-soft" />
                                                <div className="text-sm">
                                                    <div className="font-medium truncate max-w-[150px]">{file.name}</div>
                                                    <div className="text-xs ktra-text-soft">{(file.size / 1024).toFixed(1)} KB</div>
                                                </div>
                                            </div>
                                            <button onClick={() => { setPdfFiles(prev => prev.filter((_, idx) => idx !== i)); markTouched(); }} className="ktra-text-soft hover:ktra-bg-panel p-1 rounded">
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* Totals Box */}
                        <div className="bg-gradient-to-b ktra-bg-panel to-white dark:ktra-bg-panel dark:ktra-bg-panel p-6 rounded-xl border ktra-border-soft dark:ktra-border-soft shadow-lg h-fit">
                            <h3 className="text-xl font-bold ktra-text-ink dark:text-white mb-6 flex items-center gap-2">
                                <Calculator className="w-6 h-6 ktra-text-accent" /> ملخص الفاتورة
                            </h3>

                            <div className="space-y-4">
                                <div className="flex justify-between py-2 border-b dark:ktra-border-soft">
                                    <span className="ktra-text-soft dark:ktra-text-soft">المجموع الفرعي</span>
                                    <span className="font-bold">{subtotal.toLocaleString()} $</span>
                                </div>
                                <div className="flex justify-between items-center py-2 border-b dark:ktra-border-soft">
                                    <label className="text-sm ktra-text-soft dark:ktra-text-soft">خصم ($)</label>
                                    <input
                                        type="number"
                                        value={discount}
                                        onChange={e => { setDiscount(parseFloat(e.target.value) || 0); markTouched(); }}
                                        className="w-24 px-2 py-1 text-right border rounded ktra-bg-field dark:ktra-bg-panel"
                                    />
                                </div>
                                <div className="flex justify-between items-center py-2 border-b dark:ktra-border-soft">
                                    <label className="text-sm ktra-text-soft dark:ktra-text-soft">الضريبة ({taxType === 'amount' ? '$' : '%'})</label>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="number"
                                            value={taxType === 'amount' ? taxAmountState : taxRate}
                                            onChange={e => {
                                                const val = parseFloat(e.target.value) || 0;
                                                if (taxType === 'amount') setTaxAmountState(val);
                                                else setTaxRate(val);
                                                markTouched();
                                            }}
                                            className="w-16 px-2 py-1 text-right border rounded ktra-bg-field dark:ktra-bg-panel"
                                        />
                                        <span className="text-xs ktra-text-soft">
                                            {taxType === 'percentage' ? `(${taxAmount.toLocaleString()} $)` : `(${taxRate} %)`}
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div className="pt-4 flex justify-between items-center text-xl font-bold">
                                <span>الإجمالي</span>
                                <span className="ktra-text-accent dark:ktra-text-soft">{grandTotal.toLocaleString()} $</span>
                            </div>
                        </div>

                        <button
                            onClick={handleSubmit}
                            disabled={isSaving}
                            className="w-full mt-6 flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r ktra-bg-panel to-[var(--color-primary)] text-white rounded-xl hover:shadow-lg disabled:opacity-50 transition-all font-bold"
                        >
                            {isSaving ? <div className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full" /> : <Save className="w-5 h-5" />}
                            {initialData ? 'حفظ التعديلات' : 'أرشفة الفاتورة'}
                        </button>
                        {/* issue #109 §٦: مؤشّر دائم كي لا يضغط المستخدم «حفظ» احتياطاً كل دقيقة. */}
                        {draftSavedAt && (
                            <p className="text-xs text-center ktra-text-soft mt-2" data-testid="draft-saved-indicator">
                                مسودة محلية — حُفظ {formatTimeValue(draftSavedAt)}
                            </p>
                        )}
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