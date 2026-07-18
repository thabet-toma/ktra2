import React, { useState } from 'react';
import { Supplier } from '@/types';
import {
  Hash,
  Link as LinkIcon,
  FileText,
  Calendar,
  Building,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  AlignLeft,
  Tag
} from 'lucide-react';
import { SupplierModal } from '@/components/common/SupplierModal';
import { SupplierSearch } from '@/components/procurement/old-invoices/SupplierSearch';
import { SupplierViewModal } from '@/components/common/SupplierViewModal';

interface BasicInfoProps {
  data: any;
  setData: (data: any) => void;
  suppliers: Supplier[];
  readOnly?: boolean;
  isDeal?: boolean;
  onStatusChangeRequest?: (newStatus: string) => void;
  onSupplierAdded?: (newSupplier: Supplier) => void;
  onAddSupplier?: () => void;
  dealsService?: any;
  items?: any[];
}

export const BasicInfoSection: React.FC<BasicInfoProps> = ({
  data,
  setData,
  suppliers,
  readOnly,
  isDeal,
  onStatusChangeRequest,
  onSupplierAdded,
  onAddSupplier,
  items = [],
}) => {
  // للتحكم بفتح وإغلاق مودال الإضافة/التعديل
  const [showSupplierModal, setShowSupplierModal] = useState(false);

  // لتخزين المورد المراد تعديله
  const [supplierToEdit, setSupplierToEdit] = useState<Supplier | null>(null);

  const [supplierSearch, setSupplierSearch] = useState('');
  const [showDetails, setShowDetails] = useState(true);
  const [isGeneratingNumber, setIsGeneratingNumber] = useState(false);

  // للتحكم بفتح مودال العرض
  const [viewingSupplierId, setViewingSupplierId] = useState<string | null>(null);

  // دالة فتح عرض بيانات المورد (للمشاهدة فقط مبدئياً)
  const handleViewSupplier = (supplierId: string) => {
    setViewingSupplierId(supplierId);
  };

  // دالة التعامل مع طلب تعديل المورد (سواء من البحث أو من مودال العرض)
  const handleEditSupplierRequest = (supplier: Supplier) => {
    // 1. أغلق مودال العرض إذا كان مفتوحاً
    setViewingSupplierId(null);

    // 2. جهز البيانات للتعديل
    setSupplierToEdit(supplier);

    // 3. افتح مودال التعديل
    setShowSupplierModal(true);
  };

  // دالة إضافة مورد جديد
  const handleAddNewSupplier = () => {
    setSupplierToEdit(null); // تصفير البيانات
    if (onAddSupplier) {
      onAddSupplier();
    } else {
      setShowSupplierModal(true);
    }
  };

  // --- الحسابات (نفس الكود السابق) ---
  const calculateGrandTotal = () => {
    if (data.totalAmount !== undefined && data.totalAmount > 0) {
      return data.totalAmount;
    }

    let subtotal = 0;
    const currentItems = items.length > 0 ? items : (data.items || []);

    if (currentItems.length > 0) {
      subtotal = currentItems.reduce((sum: number, item: any) => {
        const qty = parseFloat(item.quantity) || 0;
        const price = parseFloat(item.unitPrice) || 0;
        const itemDiscount = parseFloat(item.itemDiscount) || 0;
        const itemTotal = Math.max(0, (qty * price) - itemDiscount);
        return sum + itemTotal;
      }, 0);
    } else {
      subtotal = parseFloat(data.subtotal) || 0;
    }

    const discountAmount = parseFloat(data.discountAmount) || 0;
    const shippingCost = data.shippingIncluded ? 0 : (parseFloat(data.shippingCost) || 0);
    const netAfterDiscount = Math.max(0, subtotal - discountAmount);

    let taxAmount = 0;
    if (data.taxType === 'amount') {
      taxAmount = parseFloat(data.taxAmount) || 0;
    } else {
      const taxRate = parseFloat(data.taxRate) || 0;
      taxAmount = netAfterDiscount * (taxRate / 100);
    }

    return netAfterDiscount + taxAmount + shippingCost;
  };

  const grandTotal = calculateGrandTotal();

  const handleSelectSupplier = (id: string) => {
    const supplier = suppliers.find(s => s.id === id);
    setData((prev: any) => ({
      ...prev,
      supplierId: id,
      factoryName: supplier?.tradeName || ''
    }));
    setSupplierSearch('');
  };

  const getSupplierDisplayName = (supplier: Supplier): string => {
    if (supplier.alias && supplier.alias.trim() !== '') {
      return supplier.alias;
    }
    if (supplier.tradeName && supplier.tradeName.trim() !== '') {
      return supplier.tradeName;
    }
    if (supplier.salesRepName && supplier.salesRepName.trim() !== '') {
      return supplier.salesRepName;
    }
    return '';
  };

  const enhancedSuppliers = suppliers.map(supplier => ({
    ...supplier,
    displayName: getSupplierDisplayName(supplier)
  }));

  return (
    <div className="space-y-4">

      {/* ================= القسم الرئيسي ================= */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start">

        {/* 1. المورد */}
        <div className="md:col-span-5 space-y-1">
          <label className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
            <Building className="w-3 h-3 text-blue-500" />
            المورد <span className="text-red-500">*</span>
          </label>
          <div className="h-10">
            <SupplierSearch
              suppliers={enhancedSuppliers}
              selectedSupplierId={data.supplierId}
              supplierSearch={supplierSearch}
              onSearchChange={setSupplierSearch}
              onSelectSupplier={handleSelectSupplier}
              onClearSupplier={() => {
                setData((prev: any) => ({ ...prev, supplierId: '', factoryName: '' }));
                setSupplierSearch('');
              }}
              // عند طلب إضافة جديد
              onOpenAddModal={handleAddNewSupplier}
              // عند طلب العرض (أيقونة العين)
              onViewSupplier={handleViewSupplier}
              type="factory"
            />
          </div>
        </div>

        {/* 2. وصف الصفقة → يُحفظ في SQL description (مصدر العنوان في الشحنة والتخليص والفواتير) */}
        <div className="md:col-span-4 space-y-1">
          <label className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
            <Tag className="w-3 h-3 text-[var(--color-primary)]" />
            وصف الصفقة
          </label>
          <input
            type="text"
            value={data.dealDescription ?? ''}
            onChange={e =>
              setData((prev: any) => ({ ...prev, dealDescription: e.target.value }))
            }
            disabled={readOnly}
            className="w-full h-10 px-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm focus:ring-1 focus:ring-[var(--color-primary)] placeholder-gray-400"
            placeholder="مثال: طلبية أجهزة كهربائية..."
          />
        </div>

        {/* 3. التاريخ */}
        <div className="md:col-span-3 space-y-1">
          <label className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
            <Calendar className="w-3 h-3 text-orange-500" />
            التاريخ
          </label>
          <input
            type="date"
            value={data.dealDate ? data.dealDate.split('T')[0] : new Date().toISOString().split('T')[0]}
            onChange={e => setData((prev: any) => ({ ...prev, dealDate: e.target.value }))}
            disabled={readOnly}
            className="w-full h-10 px-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm focus:ring-1 focus:ring-orange-500"
          />
        </div>
      </div>

      {/* ================= التفاصيل الإضافية ================= */}
      <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700 pt-2">
        <div className="text-sm font-bold text-gray-700 dark:text-gray-300 flex items-center gap-2">
          <span className="text-gray-500 font-normal">الإجمالي :</span>
          <span className="text-lg text-green-600">${grandTotal.toLocaleString()}</span>
        </div>

        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 transition-colors bg-blue-50 dark:bg-blue-900/30 px-3 py-1.5 rounded-full"
        >
          {showDetails ? (
            <>إخفاء التفاصيل الإضافية <ChevronUp className="w-3.5 h-3.5" /></>
          ) : (
            <>إظهار رقم الصفقة والروابط <ChevronDown className="w-3.5 h-3.5" /></>
          )}
        </button>
      </div>

      {showDetails && (
        <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 border border-gray-100 dark:border-gray-700 animate-in fade-in slide-in-from-top-2 duration-200 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* رقم الصفقة */}
            <div className="space-y-1">
              <label className="text-xs text-gray-500 block">
                {isDeal ? 'رقم الصفقة' : 'رقم العرض'}
              </label>
              <div className="relative">
                <Hash className="absolute right-3 top-2.5 w-4 h-4 text-gray-400" />
                <div className="w-full h-9 pr-9 pl-3 flex items-center bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded text-xs text-gray-500 font-mono">
                  {data.dealNumber || (isGeneratingNumber ? "جاري التوليد..." : "تلقائي عند الحفظ")}
                </div>
              </div>
            </div>

            {/* رقم عرض السعر (مرجعي) — ليس وصف الصفقة */}
            {isDeal ? (
              <div className="space-y-1">
                <label className="text-xs text-gray-500 block">رقم عرض السعر (مرجعي)</label>
                <div className="relative">
                  <FileText className="absolute right-3 top-2.5 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="مثال: OF-2024-001"
                    value={data.originalOfferNumber || ''}
                    onChange={e =>
                      setData((prev: any) => ({ ...prev, originalOfferNumber: e.target.value }))
                    }
                    disabled={readOnly}
                    className="w-full h-9 pr-9 pl-3 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-sm focus:ring-1 focus:ring-[var(--color-primary)] font-mono"
                  />
                </div>
              </div>
            ) : null}

            {/* رقم فاتورة المورد */}
            <div className="space-y-1">
              <label className="text-xs text-gray-500 block">رقم فاتورة المورد (PI)</label>
              <div className="relative">
                <FileText className="absolute right-3 top-2.5 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="PI Number"
                  value={data.supplierInvoiceNumber || ''}
                  onChange={e => setData((prev: any) => ({ ...prev, supplierInvoiceNumber: e.target.value }))}
                  disabled={readOnly}
                  className="w-full h-9 pr-9 pl-3 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-sm focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* رابط علي بابا */}
            <div className="space-y-1">
              <label className="text-xs text-gray-500 block">رابط علي بابا</label>
              <div className="relative flex gap-2">
                <div className="relative w-full">
                  <LinkIcon className="absolute right-3 top-2.5 w-4 h-4 text-gray-400" />
                  <input
                    type="url"
                    placeholder="https://..."
                    value={data.alibabaOrderLink || ''}
                    onChange={e => setData((prev: any) => ({ ...prev, alibabaOrderLink: e.target.value }))}
                    disabled={readOnly}
                    className="w-full h-9 pr-9 pl-3 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-sm focus:ring-1 focus:ring-orange-500 text-left ltr"
                  />
                </div>
                {data.alibabaOrderLink && (
                  <button
                    onClick={() => window.open(data.alibabaOrderLink, '_blank', 'noopener,noreferrer')}
                    className="h-9 w-9 flex items-center justify-center bg-orange-100 text-orange-600 rounded hover:bg-orange-200"
                    title="فتح الرابط"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* الملاحظات الداخلية */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500 flex items-center gap-1">
              <AlignLeft className="w-3 h-3" />
              ملاحظات داخلية
            </label>
            <textarea
              value={data.internalNotes || ''}
              onChange={e => setData((prev: any) => ({ ...prev, internalNotes: e.target.value }))}
              rows={2}
              disabled={readOnly}
              className="w-full p-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-1 focus:ring-blue-500"
              placeholder="اكتب أي ملاحظات إضافية هنا..."
            />
          </div>
        </div>
      )}

      {/* ================= المودالات ================= */}
      <SupplierModal
        isOpen={showSupplierModal}
        onClose={() => {
          setShowSupplierModal(false);
          setSupplierToEdit(null);
        }}
        onSaveSuccess={(savedSupplier) => {
          if (onSupplierAdded) onSupplierAdded(savedSupplier);
          setData((prev: any) => ({
            ...prev,
            supplierId: savedSupplier.id,
            factoryName: savedSupplier.tradeName || '',
          }));
          setSupplierSearch('');
        }}
        editingSupplier={supplierToEdit}
      />

      <SupplierViewModal
        isOpen={viewingSupplierId !== null}
        onClose={() => setViewingSupplierId(null)}
        supplierId={viewingSupplierId}
        onEdit={(supplier) => {
          setViewingSupplierId(null);
          setSupplierToEdit(supplier);
          setShowSupplierModal(true);
        }}
      />
    </div>
  );
};
