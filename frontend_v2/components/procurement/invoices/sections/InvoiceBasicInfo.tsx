import React, { useState, useEffect } from "react";
import { Supplier, Invoice, DealInvoiceInfo } from "@/types";
import {
  Hash,
  CheckCircle,
  Link as LinkIcon,
  FileText,
  Calendar,
  Building,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Tag,
  AlignLeft,
} from "lucide-react";
import { SupplierSearch } from "@/components/procurement/old-invoices/SupplierSearch";

interface InvoiceBasicInfoProps {
  data: Partial<Invoice>;
  setData: (data: Partial<Invoice>) => void;
  suppliers: Supplier[];
  readOnly?: boolean;
  items?: any[];
  /** task16 C9: فتح مودال إضافة مورد inline من حقل البحث عن المورد */
  onOpenAddSupplier?: () => void;
}

export const InvoiceBasicInfo: React.FC<InvoiceBasicInfoProps> = ({
  data,
  setData,
  suppliers,
  readOnly,
  items = [],
  onOpenAddSupplier,
}) => {
  const [supplierSearch, setSupplierSearch] = useState("");
  const [showDetails, setShowDetails] = useState(false);

  // دالة مساعدة للحصول على dealInfo بأمان
  const getDealInfo = (): Partial<DealInvoiceInfo> => {
    return data.dealInfo || {};
  };

  // --- الحسابات ---
  const calculateGrandTotal = () => {
    let subtotal = 0;
    const currentItems = items.length > 0 ? items : data.items || [];

    if (currentItems.length > 0) {
      subtotal = currentItems.reduce((sum: number, item: any) => {
        const qty = parseFloat(String(item.quantity)) || 0;
        const price = parseFloat(String(item.unitPrice)) || 0;
        const itemDiscount = parseFloat(String(item.itemDiscount)) || 0;
        return sum + Math.max(0, qty * price - itemDiscount);
      }, 0);
    } else {
      subtotal = parseFloat(String(data.subtotal)) || 0;
    }

    const discountAmount = parseFloat(String(data.discountAmount)) || 0;
    const netAfterDiscount = Math.max(0, subtotal - discountAmount);
    const taxRate = parseFloat(String(data.taxRate)) || 0;
    const taxAmount = netAfterDiscount * (taxRate / 100);
    const shippingCost = data.shippingIncluded ? 0 : parseFloat(String(data.shippingCost)) || 0;

    const localPayments = data.localPayments || {};
    let totalLocalPayments = 0;

    if (localPayments.includedInPrice !== true) {
      if (localPayments.calculationMethod === 'lump_sum') {
        totalLocalPayments = parseFloat(String(localPayments.lumpSumAmount)) || 0;
      } else if (localPayments.calculationMethod === 'detailed') {
        totalLocalPayments =
          (parseFloat(String(localPayments.customsClearanceFees)) || 0) +
          (parseFloat(String(localPayments.customsDuties)) || 0) +
          (parseFloat(String(localPayments.portFees)) || 0) +
          (parseFloat(String(localPayments.internalShippingFees)) || 0);
      }
    }

    return { grandTotal: netAfterDiscount + taxAmount + shippingCost + totalLocalPayments };
  };

  useEffect(() => {
    const totals = calculateGrandTotal();
    if (data.grandTotal !== totals.grandTotal) {
      setData({ ...data, grandTotal: totals.grandTotal });
    }
  }, [data.localPayments, data.items, data.discountAmount, data.taxRate, data.shippingCost, data.shippingIncluded]);

  const grandTotal = calculateGrandTotal().grandTotal;

  const handleSelectSupplier = (id: string) => {
    const supplier = suppliers.find((s) => s.id === id);
    setData({
      ...data,
      supplierId: id,
      factoryName: supplier?.tradeName || "",
    });
  };

  return (
    <div className="space-y-4">
      {/* ================= القسم الرئيسي ================= */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start">
        {/* 1. المورد */}
        <div className="md:col-span-5 space-y-1">
          <label className="text-xs font-semibold aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
            <Building className="w-3 h-3 aseel-text-soft" />
            المورد <span className="aseel-text-soft">*</span>
          </label>
          <div className="h-10">
            <SupplierSearch
              suppliers={suppliers}
              selectedSupplierId={data.supplierId}
              supplierSearch={supplierSearch}
              onSearchChange={setSupplierSearch}
              onSelectSupplier={handleSelectSupplier}
              onClearSupplier={() => setData({ ...data, supplierId: "", factoryName: "" })}
              onOpenAddModal={readOnly ? undefined : onOpenAddSupplier}
              type="factory"
            />
          </div>
        </div>

        {/* 2. التاريخ */}
        <div className="md:col-span-4 space-y-1">
          <label className="text-xs font-semibold aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
            <Calendar className="w-3 h-3 aseel-text-soft" />
            التاريخ
          </label>
          <input
            type="date"
            value={data.invoiceDate ? data.invoiceDate.split("T")[0] : new Date().toISOString().split("T")[0]}
            onChange={(e) => setData({ ...data, invoiceDate: e.target.value })}
            disabled={readOnly}
            className="w-full h-10 px-3 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-orange-500"
          />
        </div>

        {/* T-DUE: متى يُدفع للمورّد — كان الحقل على فاتورة البيع وحدها، فجانب
            الشراء بلا «استحقاق» أصلاً: لا تقرير أعمارٍ صادق ولا شارة «متأخرة».
            المهلة تشتقّ التاريخ، والتاريخ الصريح يسمو عليها (الخادم يحسمها). */}
        <div className="md:col-span-3 space-y-1">
          <label className="text-xs font-semibold aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
            <Calendar className="w-3 h-3 aseel-text-soft" />
            الاستحقاق
          </label>
          <input
            type="date"
            data-testid="purchase-due-date"
            value={data.dueDate ? String(data.dueDate).split("T")[0] : ""}
            onChange={(e) => setData({ ...data, dueDate: e.target.value || null })}
            disabled={readOnly}
            title="تاريخ استحقاق الدفع — يُشتقّ من المهلة إن تُرك فارغاً"
            className="w-full h-10 px-3 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-orange-500"
          />
        </div>

        <div className="md:col-span-2 space-y-1">
          <label className="text-xs font-semibold aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
            مهلة السداد (يوم)
          </label>
          <input
            type="number"
            min="0"
            data-testid="purchase-payment-terms"
            value={data.paymentTermsDays ?? ""}
            onChange={(e) => setData({
              ...data,
              paymentTermsDays: e.target.value === "" ? null : Number(e.target.value),
            })}
            disabled={readOnly}
            placeholder="30"
            title="مثال: 30 = تُستحقّ بعد 30 يوماً من تاريخ الفاتورة"
            className="w-full h-10 px-3 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel text-sm focus:ring-1 focus:ring-orange-500"
          />
        </div>

        {/* 3. الحالة */}
        <div className="md:col-span-3 space-y-1">
          <label className="text-xs font-semibold aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
            <CheckCircle className="w-3 h-3 text-green-500" />
            الحالة
          </label>
          <select
            value={data.status || "incomplete"}
            onChange={(e) => setData({ ...data, status: e.target.value as any })}
            disabled={readOnly}
            className={`w-full h-10 px-3 border rounded-lg text-sm font-medium focus:ring-1 focus:ring-blue-500 ${data.status === 'completed'
              ? 'bg-green-50 text-green-700 aseel-border-soft dark:bg-green-900/20 dark:border-green-800'
              : 'aseel-bg-panel aseel-text-ink aseel-border-soft dark:aseel-bg-panel dark:aseel-border-soft'
              }`}
          >
            <option value="incomplete">غير مكتملة</option>
            <option value="completed">مكتملة</option>
          </select>
        </div>

        {/* 4. وصف الفاتورة — حقل متعدد الأسطر مثل وصف الصفقة */}
        <div className="md:col-span-12 space-y-1">
          <label className="text-xs font-semibold aseel-text-soft dark:aseel-text-soft flex items-center gap-1">
            <Tag className="w-3 h-3 text-[var(--color-primary)]" />
            وصف الفاتورة (عنوان عربي / ملخص)
          </label>
          <textarea
            value={data.invoiceName || ""}
            onChange={(e) => setData({ ...data, invoiceName: e.target.value })}
            disabled={readOnly}
            rows={4}
            className="w-full min-h-[5.5rem] px-3 py-2 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel text-sm leading-relaxed focus:ring-1 focus:ring-[var(--color-primary)] placeholder-gray-400 resize-y"
            placeholder="مثال: مجموعة إنفيرتر — نفس أسلوب وصف الصفقة بالعربي"
          />
        </div>
      </div>

      {/* ================= زر التفاصيل ================= */}
      <div className="flex items-center justify-between border-t aseel-border-soft dark:aseel-border-soft pt-2">
        <div className="text-sm font-bold aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
          <span className="aseel-text-soft font-normal">الإجمالي:</span>
          <span className="text-lg text-green-600">
            {data.currency === 'ILS' ? '₪' : '$'}
            {grandTotal.toLocaleString()}
          </span>
        </div>

        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-1.5 text-xs font-medium aseel-text-accent hover:aseel-text-accent dark:aseel-text-soft transition-colors aseel-bg-accent-bg dark:aseel-bg-panel/30 px-3 py-1.5 rounded-full"
        >
          {showDetails ? (
            <>إخفاء التفاصيل الإضافية <ChevronUp className="w-3.5 h-3.5" /></>
          ) : (
            <>إظهار الروابط والملاحظات وأرقام الفواتير <ChevronDown className="w-3.5 h-3.5" /></>
          )}
        </button>
      </div>

      {/* ================= التفاصيل المخفية ================= */}
      {showDetails && (
        <div className="aseel-bg-panel dark:aseel-bg-panel/50 rounded-xl p-4 border aseel-border-soft dark:aseel-border-soft animate-in fade-in slide-in-from-top-2 duration-200 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* رقم الفاتورة */}
            <div className="space-y-1">
              <label className="text-xs aseel-text-soft block">رقم الفاتورة (النظام)</label>
              <div className="relative">
                <Hash className="absolute right-3 top-2.5 w-4 h-4 aseel-text-soft" />
                <input
                  type="text"
                  value={data.invoiceNumber || ""}
                  readOnly
                  className="w-full h-9 pr-9 pl-3 aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded text-xs aseel-text-soft font-mono"
                  placeholder="تلقائي"
                />
              </div>
            </div>

            {/* رقم فاتورة المورد */}
            <div className="space-y-1">
              <label className="text-xs aseel-text-soft block">رقم فاتورة المورد (PI)</label>
              <div className="relative">
                <FileText className="absolute right-3 top-2.5 w-4 h-4 aseel-text-soft" />
                <input
                  type="text"
                  value={data.supplierInvoiceNumber || ""}
                  onChange={(e) => setData({ ...data, supplierInvoiceNumber: e.target.value })}
                  className="w-full h-9 pr-9 pl-3 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded text-sm focus:aseel-border-soft focus:ring-1 focus:ring-blue-500"
                  placeholder="مثال: PI-2025-001"
                />
              </div>
            </div>

            {/* رابط علي بابا */}
            <div className="space-y-1">
              <label className="text-xs aseel-text-soft block">رابط الطلبية (علي بابا)</label>
              <div className="relative flex gap-2">
                <div className="relative w-full">
                  <LinkIcon className="absolute right-3 top-2.5 w-4 h-4 aseel-text-soft" />
                  <input
                    type="url"
                    value={getDealInfo().alibabaOrderLink || data.alibabaOrderLink || ""}
                    onChange={(e) => {
                      const val = e.target.value;
                      const currentDealInfo = data.dealInfo || {};
                      setData({
                        ...data,
                        alibabaOrderLink: val,
                        dealInfo: { ...currentDealInfo, alibabaOrderLink: val } as DealInvoiceInfo,
                      });
                    }}
                    className="w-full h-9 pr-9 pl-3 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded text-sm focus:aseel-border-soft focus:ring-1 focus:ring-orange-500 text-left ltr"
                    placeholder="https://..."
                  />
                </div>
                {(getDealInfo().alibabaOrderLink || data.alibabaOrderLink) && (
                  <button
                    onClick={() => window.open(getDealInfo().alibabaOrderLink || data.alibabaOrderLink, "_blank")}
                    className="h-9 w-9 flex items-center justify-center aseel-bg-panel aseel-text-soft rounded hover:aseel-bg-grid-head"
                    title="فتح الرابط"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* الملاحظات الداخلية - التعديل الجوهري هنا */}
          <div className="space-y-1">
            <label className="text-xs aseel-text-soft flex items-center gap-1">
              <AlignLeft className="w-3 h-3" />
              ملاحظات داخلية
            </label>
            <textarea
              // ✅✅ استخدام ?? بدلاً من || لمنع القفز إلى الحقل الاحتياطي عند مسح النص
              value={getDealInfo().internalNotes ?? data.notes ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                const currentDealInfo = data.dealInfo || {};
                setData({
                  ...data,
                  notes: val, // حفظ نسخة في الجذر للأمان
                  dealInfo: { ...currentDealInfo, internalNotes: val } as DealInvoiceInfo, // المصدر الأساسي
                });
              }}
              rows={2}
              className="w-full p-2 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg text-sm focus:aseel-border-soft focus:ring-1 focus:ring-blue-500"
              placeholder="اكتب أي ملاحظات خاصة هنا..."
            />
          </div>
        </div>
      )}
    </div>
  );
};