import React, { useState, useEffect, useRef } from "react";
import { PriceOffer, PriceOfferStatus, Supplier, Item } from "../../../types";
import { ImagePreviewModal } from "./ImagePreviewModal";
import { ItemSearchModal } from "./ItemSearchModal";
import { cloudinaryService } from "@/services/cloudinaryService";
import { SHIPPING_TERMS } from "@/constants/shipping";
import {
  FileText,
  Save,
  Hash as HashIcon,
  Package,
  CheckCircle,
  List,
  Plus,
  Trash2,
  DollarSign,
  Image as ImageIcon,
  X,
  Truck,
  Paperclip,
  Download,
  ExternalLink,
  Calculator,
  Receipt,
  Info,
  ChevronLeft,
  Search,
  User,
  PlusCircle,
  Percent,
  Tag,
  Building,
  Factory,
} from "lucide-react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { ItemsTableSection } from "@/components/forms/shared/ItemsTableSection";
import { SupplierModal } from "@/components/common/SupplierModal";
import { SupplierSearch } from "../old-invoices/SupplierSearch";
import { FinancialSummarySection } from "@/components/forms/shared/FinancialSummarySection";

interface PriceOfferFormProps {
  currentOffer: Partial<PriceOffer>;
  setCurrentOffer: React.Dispatch<React.SetStateAction<Partial<PriceOffer>>>;
  suppliers: Supplier[];
  items: Item[];
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  readOnly?: boolean;
  isNew?: boolean;
  onSupplierAdded?: (newSupplier: Supplier) => void;
  onAddSupplier?: () => void;
}

export const PriceOfferForm: React.FC<PriceOfferFormProps> = ({
  currentOffer,
  setCurrentOffer,
  suppliers,
  items,
  onSave,
  onCancel,
  saving,
  readOnly = false,
  isNew = false,
  onSupplierAdded,
  onAddSupplier,
}) => {
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [showItemSearch, setShowItemSearch] = useState(false);
  const [showSupplierModal, setShowSupplierModal] = useState(false);
  const [isCreatingSupplier, setIsCreatingSupplier] = useState(false);

  // File Upload State
  const [uploadingImages, setUploadingImages] = useState(false);
  const [uploadingPdfs, setUploadingPdfs] = useState(false);

  // Supplier search state
  const [supplierSearch, setSupplierSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  const handleSelectSupplier = (id: string) => {
    const supplier = suppliers.find((s) => s.id === id);
    setCurrentOffer((prev) => ({
      ...prev,
      supplierId: id,
      factoryName: supplier?.tradeName || "",
    }));
  };

  const handleAddSupplier = async (newSupplier: Supplier) => {
    setIsCreatingSupplier(true);
    try {
      if (onSupplierAdded) {
        await onSupplierAdded(newSupplier);
        setCurrentOffer((prev) => ({
          ...prev,
          supplierId: newSupplier.id,
          factoryName: newSupplier.tradeName,
        }));
        setShowSupplierModal(false);
      }
    } catch (error) {
      console.error("Error adding supplier:", error);
    } finally {
      setIsCreatingSupplier(false);
    }
  };

  // File Upload Helpers
  const convertFileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = (error) => reject(error);
    });
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploadingImages(true);
    const files: File[] = Array.from(e.target.files);
    const newUrls: string[] = [];

    try {
      for (const file of files) {
        if (!file.type.startsWith("image/")) continue;
        const imageUrl = await cloudinaryService.uploadImage(file);
        if (imageUrl) newUrls.push(imageUrl);
      }
      setCurrentOffer((prev) => ({
        ...prev,
        quote_images: [...(prev.quote_images || []), ...newUrls],
      }));
    } catch (error) {
      console.error("Error uploading images:", error);
      alert("فشل رفع الصور");
    } finally {
      setUploadingImages(false);
      e.target.value = "";
    }
  };

  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploadingPdfs(true);
    const files: File[] = Array.from(e.target.files);
    const newPdfFiles: Array<{
      name: string;
      url: string;
      size: number;
      type: string;
    }> = [];

    try {
      for (const file of files) {
        if (file.type !== "application/pdf") {
          alert(`الملف ${file.name} ليس PDF.`);
          continue;
        }
        const base64Data = await convertFileToBase64(file);
        newPdfFiles.push({
          name: file.name,
          url: base64Data,
          size: file.size,
          type: file.type,
        });
      }
      setCurrentOffer((prev) => ({
        ...prev,
        quote_pdfs: [...(prev.quote_pdfs || []), ...newPdfFiles],
      }));
    } catch (error) {
      console.error("Error uploading PDF files:", error);
      alert("حدث خطأ أثناء معالجة ملفات PDF");
    } finally {
      setUploadingPdfs(false);
      e.target.value = "";
    }
  };

  // Recalculate Totals
  const recalculateTotals = (updatedFields: Partial<PriceOffer> = {}) => {
    const nextOffer = { ...currentOffer, ...updatedFields };
    const itemsSubtotal = (nextOffer.items || []).reduce(
      (sum, item) => sum + (item.totalPrice || 0),
      0
    );
    const validShipping = nextOffer.shippingIncluded
      ? 0
      : nextOffer.shippingCost || 0;
    const afterDiscount = Math.max(
      0,
      itemsSubtotal - (nextOffer.discountAmount || 0)
    );
    const taxableBase = afterDiscount + validShipping;

    let taxAmount = 0;
    if (nextOffer.taxType === 'amount') {
      taxAmount = nextOffer.taxAmount || 0;
    } else {
      taxAmount = taxableBase * ((nextOffer.taxRate || 0) / 100);
    }

    const grandTotal = taxableBase + taxAmount;

    setCurrentOffer((prev) => ({
      ...prev,
      ...updatedFields,
      subtotal: itemsSubtotal,
      taxAmount,
      grandTotal,
    }));
  };

  const handleAddItem = () => {
    if (!currentOffer.supplierId) {
      alert("يرجى اختيار المورد أولاً للبحث عن الأسعار المناسبة.");
      return;
    }
    setShowItemSearch(true);
  };

  const onSelectItem = (item: Item, lastPrice?: number) => {
    const newItem = {
      id: crypto.randomUUID(),
      itemId: item.id,
      name: item.name,
      categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || item.modelNumber || "",
      hsCodePrimary: item.hsCodePrimary,
      modelNumber: item.modelNumber, // 🟢 Add this line
      imageUrls: item.imageUrls || [],
      quantity: 1,
      unitPrice: lastPrice || 0,
      totalPrice: lastPrice || 0,
      factoryImageUrl: item.imageUrls?.[0] || "",
    };

    const updatedItems = [...(currentOffer.items || []), newItem];
    recalculateTotals({ items: updatedItems });
    setShowItemSearch(false);
  };

  const handleUpdateItem = (index: number, field: string, value: any) => {
    const updatedItems = [...(currentOffer.items || [])];
    const item = { ...updatedItems[index], [field]: value };

    if (field === "quantity" || field === "unitPrice") {
      const qty = field === "quantity" ? Number(value) : Number(item.quantity);
      const price =
        field === "unitPrice" ? Number(value) : Number(item.unitPrice);
      item.totalPrice = qty * price;
    }

    updatedItems[index] = item;
    recalculateTotals({ items: updatedItems });
  };

  const handleRemoveItem = (index: number) => {
    const updatedItems = (currentOffer.items || []).filter(
      (_, i) => i !== index
    );
    recalculateTotals({ items: updatedItems });
  };

  // Handle financial updates
  const handleFinancialUpdate = (field: string, value: any) => {
    // ⭐ إذا كان التحديث متعلق بالضريبة، احسب الإجمالي يدوياً
    if (field === 'taxType' || field === 'taxAmount' || field === 'taxRate') {
      setCurrentOffer((prev) => {
        const updated = { ...prev, [field]: value };
        const items = updated.items || [];

        const itemsSubtotal = items.reduce((sum, item) => sum + (item.totalPrice || 0), 0);
        const validShipping = updated.shippingIncluded ? 0 : (updated.shippingCost || 0);
        const afterDiscount = Math.max(0, itemsSubtotal - (updated.discountAmount || 0));
        const taxableBase = afterDiscount + validShipping;

        let taxAmount = 0;
        if (updated.taxType === 'amount') {
          taxAmount = updated.taxAmount || 0;
        } else {
          taxAmount = taxableBase * ((updated.taxRate || 0) / 100);
        }

        const grandTotal = taxableBase + taxAmount;

        return {
          ...updated,
          subtotal: itemsSubtotal,
          taxAmount,
          grandTotal,
        };
      });
      return;
    }

    // للحقول الأخرى، استخدم recalculateTotals
    recalculateTotals({ [field]: value });
  };

  const getPageTitle = () => {
    if (readOnly) return "عرض السعر";
    if (isNew) return "إنشاء عرض سعر جديد";
    return `تعديل عرض السعر ${currentOffer.offerNumber || ""}`;
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-gray-200 dark:border-gray-700 bg-gradient-to-r from-blue-50 to-white dark:from-blue-950 dark:to-gray-900">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-100 dark:bg-blue-900/40 rounded-xl">
              <FileText className="w-7 h-7 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white">
                {getPageTitle()}
              </h1>
              {currentOffer.offerNumber && (
                <div className="mt-1 flex items-center gap-2">
                  <span className="text-sm font-mono bg-blue-100 dark:bg-blue-800/40 text-blue-700 dark:text-blue-300 px-3 py-1 rounded-full">
                    {currentOffer.offerNumber}
                  </span>
                  {readOnly && (
                    <span className="text-xs bg-green-100 dark:bg-green-800/40 text-green-700 dark:text-green-300 px-2 py-0.5 rounded">
                      عرض فقط
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex gap-3 w-full sm:w-auto">
            <button
              onClick={onCancel}
              className="flex-1 sm:flex-none px-5 py-2.5 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors flex items-center justify-center gap-2"
            >
              <ChevronLeft className="w-5 h-5 rtl:rotate-180" />
              رجوع
            </button>

            {!readOnly && (
              <button
                onClick={onSave}
                disabled={saving}
                className="flex-1 sm:flex-none px-6 py-2.5 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center justify-center gap-2 shadow-md disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    جاري الحفظ...
                  </>
                ) : (
                  <>
                    <Save className="w-5 h-5" />
                    حفظ العرض
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="p-6 md:p-8 space-y-8">
        {/* 1. Basic Info - Supplier & Offer Details */}
        {/* 1. Basic Info - Supplier & Offer Details */}
        <CollapsibleSection
          title="معلومات العرض الأساسية"
          icon={Info}
          defaultOpen={true}
        >
          <div className="space-y-6">
            {/* المورد - بارز في الأعلى */}
            {/* 1. قسم المورد - عريض في الأعلى */}
            <div className="bg-gradient-to-r from-blue-50 to-blue-100 dark:from-blue-950 dark:to-blue-900 p-6 rounded-2xl border border-blue-200 dark:border-blue-800 shadow-sm">
              <h3 className="text-lg font-semibold text-blue-800 dark:text-blue-300 mb-4 flex items-center gap-2">
                <Building className="w-5 h-5" />
                المورد / المصنع
              </h3>
              <SupplierSearch
                suppliers={suppliers}
                selectedSupplierId={currentOffer.supplierId}
                supplierSearch={supplierSearch}
                onSearchChange={setSupplierSearch}
                onSelectSupplier={handleSelectSupplier}
                onClearSupplier={() => {
                  setCurrentOffer((prev: any) => ({ ...prev, supplierId: '', factoryName: '' }));
                  setSupplierSearch('');
                }}
                onOpenAddModal={() => {
                  if (onAddSupplier) onAddSupplier();
                  else setShowSupplierModal(true);
                }}

                type="factory"
              />
            </div>

            {/* الحقول الرئيسية */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* اسم العرض / الفاتورة */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  <div className="flex items-center gap-2">
                    <Receipt className="w-5 h-5 text-blue-600" />
                    اسم العرض / الفاتورة *
                  </div>
                </label>
                <input
                  type="text"
                  value={currentOffer.offerNumber || ""}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      offerNumber: e.target.value,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-base"
                  placeholder="أدخل اسم العرض (مثال: عرض ABC - مارس 2025)"
                />
              </div>

              {/* حالة العرض */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  <div className="flex items-center gap-2">
                    <CheckCircle className="w-5 h-5 text-green-600" />
                    حالة العرض
                  </div>
                </label>
                <select
                  value={currentOffer.status || "initial"}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      status: e.target.value as PriceOfferStatus,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-base"
                >
                  <option value="initial">أولية</option>
                  <option value="pending_info">بانتظار المعلومات</option>
                  <option value="under_discussion">تحت المناقشة</option>
                  <option value="approved_for_shipping">معتمد للشراء</option>
                  <option value="rejected">مرفوضة</option>
                </select>
              </div>
            </div>
          </div>
        </CollapsibleSection>

        {/* 2. Products */}
        <CollapsibleSection
          title="المنتجات والبنود"
          icon={Package}
          defaultOpen={true}
        >
          <ItemsTableSection
            items={currentOffer.items || []}
            onUpdateItem={(index, field, value) =>
              handleUpdateItem(index, field, value)
            }
            onRemoveItem={handleRemoveItem}
            onAddItem={handleAddItem}
            onPreviewImage={(url) => setPreviewImage(url)}
            supplierId={currentOffer.supplierId}
            readOnly={readOnly}
            allDbItems={items}
            discountAmount={currentOffer.discountAmount || 0}
            taxRate={currentOffer.taxRate || 0}
            taxAmount={currentOffer.taxAmount || 0}
            taxType={currentOffer.taxType || 'percentage'}
            shippingCost={currentOffer.shippingCost || 0}
            shippingIncluded={currentOffer.shippingIncluded || false}
            onUpdateFinancial={handleFinancialUpdate}
            productionDays={currentOffer.productionDays}
            deliveryDays={currentOffer.deliveryDays}
            paymentMethod={currentOffer.paymentMethod}
            shippingMethod={currentOffer.shippingMethod}
            warrantyDuration={currentOffer.warrantyDuration}
            totalWeight={currentOffer.totalWeight}
            totalVolume={currentOffer.totalVolume}
            certificates={currentOffer.certificates}
            shipmentNotes={currentOffer.shipmentNotes}
            showLocalPayments={false}
          />
        </CollapsibleSection>


        {/* 4. Shipping & Terms */}
        {/* <CollapsibleSection
          title="الشروط والشحن"
          icon={Truck}
          defaultOpen={false}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"> */}
        {/* Production & Delivery */}
        {/* <div className="space-y-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  وقت الإنتاج (أيام)
                </label>
                <input
                  type="number"
                  min="0"
                  value={currentOffer.productionDays || ""}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      productionDays: parseInt(e.target.value) || 0,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  وقت التوصيل (أيام)
                </label>
                <input
                  type="number"
                  min="0"
                  value={currentOffer.deliveryDays || ""}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      deliveryDays: parseInt(e.target.value) || 0,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div> */}

        {/* Payment & Warranty */}
        {/* <div className="space-y-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  طريقة الدفع
                </label>
                <input
                  type="text"
                  placeholder="مثال: T/T 30%"
                  value={currentOffer.paymentMethod || ""}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      paymentMethod: e.target.value,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  مدة الضمان (سنوات)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={currentOffer.warrantyDuration || ""}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      warrantyDuration: parseFloat(e.target.value) || 0,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div> */}

        {/* Shipping Method & Cost */}
        {/* <div className="space-y-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  طريقة الشحن (Incoterm)
                </label>
                <select
                  value={currentOffer.shippingMethod || ""}
                  onChange={(e) =>
                    setCurrentOffer((prev) => ({
                      ...prev,
                      shippingMethod: e.target.value,
                    }))
                  }
                  disabled={readOnly}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">-- اختر Incoterm --</option>
                  {SHIPPING_TERMS.map((term) => (
                    <option key={term.code} value={term.code}>
                      {term.code} - {term.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  تكلفة الشحن ($)
                </label>
                <div className="relative">
                  <input
                    type="number"
                    value={currentOffer.shippingCost || ""}
                    onChange={(e) =>
                      handleFinancialUpdate(
                        "shippingCost",
                        parseFloat(e.target.value) || 0
                      )
                    }
                    disabled={readOnly || currentOffer.shippingIncluded}
                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 pl-8"
                  />
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                    $
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="checkbox"
                    id="shippingIncluded"
                    checked={currentOffer.shippingIncluded || false}
                    onChange={(e) =>
                      handleFinancialUpdate(
                        "shippingIncluded",
                        e.target.checked
                      )
                    }
                    disabled={readOnly}
                    className="w-4 h-4 text-blue-600 rounded cursor-pointer"
                  />
                  <label
                    htmlFor="shippingIncluded"
                    className="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer"
                  >
                    الشحن متضمن في السعر
                  </label>
                </div>
              </div>
            </div>
          </div>
        </CollapsibleSection> */}

        {/* 5. Attachments */}
        <CollapsibleSection
          title="المرفقات والملفات"
          icon={Paperclip}
          defaultOpen={false}
        >
          {/* Images */}
          <div className="mb-8">
            <h4 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <ImageIcon className="w-5 h-5 text-blue-600" />
              صور العرض
              {uploadingImages && (
                <span className="text-sm text-blue-500 animate-pulse ml-2">
                  (جاري الرفع...)
                </span>
              )}
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {currentOffer.quote_images?.map((url, i) => (
                <div
                  key={i}
                  className="group relative aspect-square bg-gray-100 dark:bg-gray-800 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-all"
                >
                  <img
                    src={url}
                    alt={`Quote ${i}`}
                    className="w-full h-full object-cover cursor-pointer hover:scale-105 transition-transform"
                    onClick={() => setPreviewImage(url)}
                  />
                  {!readOnly && (
                    <button
                      onClick={() =>
                        setCurrentOffer((prev) => ({
                          ...prev,
                          quote_images: prev.quote_images?.filter(
                            (_, idx) => idx !== i
                          ),
                        }))
                      }
                      className="absolute top-2 right-2 p-2 bg-red-500/90 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
              {!readOnly && (
                <label className="flex flex-col items-center justify-center border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl cursor-pointer hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-all aspect-square">
                  <PlusCircle className="w-10 h-10 text-gray-400 mb-2" />
                  <span className="text-sm text-gray-500">إضافة صور</span>
                  <input
                    type="file"
                    className="hidden"
                    accept="image/*"
                    multiple
                    onChange={handleImageUpload}
                    disabled={uploadingImages}
                  />
                </label>
              )}
            </div>
          </div>

          {/* PDFs */}
          <div>
            <h4 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5 text-red-600" />
              ملفات PDF
              {uploadingPdfs && (
                <span className="text-sm text-blue-500 animate-pulse ml-2">
                  (جاري الرفع...)
                </span>
              )}
            </h4>
            <div className="space-y-3">
              {currentOffer.quote_pdfs?.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-xl hover:border-blue-300 transition-colors"
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-lg">
                      <FileText className="w-6 h-6 text-red-600 dark:text-red-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{file.name}</p>
                      <p className="text-sm text-gray-500">
                        {file.size
                          ? `${(file.size / 1024).toFixed(1)} KB`
                          : "غير معروف"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <a
                      href={file.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                      title="عرض / تحميل"
                    >
                      <ExternalLink className="w-5 h-5" />
                    </a>
                    {!readOnly && (
                      <button
                        onClick={() =>
                          setCurrentOffer((prev) => ({
                            ...prev,
                            quote_pdfs: prev.quote_pdfs?.filter(
                              (_, idx) => idx !== i
                            ),
                          }))
                        }
                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        title="حذف"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {!readOnly && (
                <label className="flex items-center justify-center p-6 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl cursor-pointer hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-all">
                  <PlusCircle className="w-8 h-8 text-gray-400 mr-3" />
                  <span className="text-gray-600 dark:text-gray-300 font-medium">
                    إضافة ملف PDF
                  </span>
                  <input
                    type="file"
                    className="hidden"
                    accept="application/pdf"
                    multiple
                    onChange={handlePdfUpload}
                    disabled={uploadingPdfs}
                  />
                </label>
              )}
            </div>
          </div>
        </CollapsibleSection>
      </div>

      {/* Modals */}
      {previewImage && (
        <ImagePreviewModal
          url={previewImage}
          onClose={() => setPreviewImage(null)}
        />
      )}

      <ItemSearchModal
        isOpen={showItemSearch}
        onClose={() => setShowItemSearch(false)}
        onSelectItem={onSelectItem}
        items={items}
        supplierId={currentOffer.supplierId}
      />

      <SupplierModal
        isOpen={showSupplierModal}
        onClose={() => setShowSupplierModal(false)}
      />
    </div>
  );
};
