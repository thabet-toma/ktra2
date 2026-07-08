import React, { useState } from 'react';
import {
  CreditCard, Calculator, Plus, Trash2, CheckCircle2,
  DollarSign, FileText, ChevronRight, AlertCircle,
  Calendar, UploadCloud, Loader2, Eye, X
} from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { formatMoney } from '@/utils/formatNumber';
import type { LocalPayments } from '@/types';
import {
  clearanceAndLogisticsFeesForGrandTotal,
  invoiceVatBaseIls,
  sumTaxesAndFeesExtras,
} from '@/utils/invoiceTaxesAndFees';

interface Installment {
  id: string;
  installmentNumber: number;
  amount: number;
  status: 'unpaid' | 'paid';
  notes?: string;
  bankSlipUrl?: string;
  paymentDate?: string;
}

interface InstallmentsSectionProps {
  installments: Installment[];
  installmentPlanEnabled: boolean;
  items?: any[];
  discountAmount?: number;
  taxRate?: number;
  shippingCost?: number;
  shippingIncluded?: boolean;
  localPayments?: Partial<LocalPayments> | null;
  onToggleInstallmentPlan: (enabled: boolean) => void;
  onAddInstallment: () => void;
  onRemoveInstallment: (index: number) => void;
  onUpdateInstallment: (index: number, field: string, value: any) => void;
  readOnly?: boolean;
  currency?: 'USD' | 'ILS';
  /** يُفضَّل لفواتير الشيكل ليطابق الملخص الرئيسي (ض.ق.م مبلغ/نسبة + تخليص) */
  grandTotalFromForm?: number;
  /** مبلغ ض.ق.م الفاتورة — لبنود «بعد ض.ق.م» في الرسوم الإضافية */
  mainVatForExtras?: number;
  /** ليطابق أساس ض.ق.م والإجمالي (شحن دولي من التحويل + نقل من metadata) */
  conversionMetadata?: Record<string, unknown> | null;
}

export const InstallmentsSection: React.FC<InstallmentsSectionProps> = ({
  installments,
  installmentPlanEnabled,
  items = [],
  discountAmount = 0,
  taxRate = 0,
  shippingCost = 0,
  shippingIncluded = false,
  localPayments = {} as Partial<LocalPayments>,
  onToggleInstallmentPlan,
  onAddInstallment,
  onRemoveInstallment,
  onUpdateInstallment,
  readOnly = false,
  currency = 'USD',
  grandTotalFromForm,
  mainVatForExtras = 0,
  conversionMetadata = null,
}) => {
  const symbol = currency === 'ILS' ? '₪' : '$';

  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);

  // دالة حساب المدفوعات المحلية
  const calculateTotalLocalPayments = () => {
    const lp: Partial<LocalPayments> = localPayments ?? {};
    if (lp.includedInPrice) return 0;
    if (lp.calculationMethod === 'lump_sum') return lp.lumpSumAmount || 0;
    const subtotal = items.reduce((sum, item) => {
      const qty = item.quantity || 0;
      const price = item.unitPrice || 0;
      const itemDisc = item.itemDiscount || 0;
      return sum + Math.max(0, qty * price - itemDisc);
    }, 0);
    const netAfterDiscount = Math.max(0, subtotal - discountAmount);
    const ship =
      currency === 'ILS' ? 0 : shippingIncluded ? 0 : shippingCost;
    const taxableBaseIls = netAfterDiscount + ship;
    const vatBaseEst = invoiceVatBaseIls(
      taxableBaseIls,
      conversionMetadata,
      lp as LocalPayments
    );
    const mv =
      typeof mainVatForExtras === "number" && Number.isFinite(mainVatForExtras)
        ? Math.max(0, mainVatForExtras)
        : Math.max(0, vatBaseEst * ((taxRate || 0) / 100));
    return (
      clearanceAndLogisticsFeesForGrandTotal(lp as LocalPayments, conversionMetadata) +
      sumTaxesAndFeesExtras(lp, taxableBaseIls, {
        mainVatIls: mv,
        invoiceVatBaseIls: vatBaseEst,
      })
    );
  };

  const totalLocalPayments = calculateTotalLocalPayments();

  // دالة حساب الإجمالي الكلي - تضم كل شيء
  const calculateGrandTotal = () => {
    // حساب إجمالي المنتجات
    const subtotal = items.reduce((sum, item) => {
      const qty = item.quantity || 0;
      const price = item.unitPrice || 0;
      const itemDisc = item.itemDiscount || 0;
      return sum + Math.max(0, (qty * price) - itemDisc);
    }, 0);

    const netAfterDiscount = Math.max(0, subtotal - discountAmount);
    const taxAmount = netAfterDiscount * (taxRate / 100);
    const shipping =
      currency === 'ILS' ? 0 : shippingIncluded ? 0 : shippingCost;

    return netAfterDiscount + taxAmount + shipping + totalLocalPayments;
  };

  const grandTotal =
    typeof grandTotalFromForm === 'number' && Number.isFinite(grandTotalFromForm)
      ? grandTotalFromForm
      : calculateGrandTotal();
  const totalPaidAmount = installments
    .filter(inst => inst.status === 'paid')
    .reduce((sum, inst) => sum + (inst.amount || 0), 0);
  const remainingAmount = grandTotal - totalPaidAmount;
  const progressPercentage = grandTotal > 0 ? Math.round((totalPaidAmount / grandTotal) * 100) : 0;

  // دالة الرفع إلى Cloudinary (نفسها)
  const handleFileUpload = async (file: File, index: number) => {
    if (!file) return;

    const CLOUD_NAME = "YOUR_CLOUD_NAME";
    const UPLOAD_PRESET = "YOUR_UPLOAD_PRESET";

    setUploadingIndex(index);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("upload_preset", UPLOAD_PRESET);

    try {
      const response = await fetch(
        `https://api.cloudinary.com/v1_1/${CLOUD_NAME}/image/upload`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (data.secure_url) {
        onUpdateInstallment(index, 'bankSlipUrl', data.secure_url);
      } else {
        alert("فشل رفع الصورة");
      }
    } catch (error) {
      // console suppressed
      alert("حدث خطأ أثناء رفع الصورة");
    } finally {
      setUploadingIndex(null);
    }
  };
  return (
    <CollapsibleSection
      title="خطة الدفع والتحصيل"
      icon={CreditCard}
      defaultOpen={false}
      className="aseel-border-soft dark:aseel-border-soft/30 overflow-hidden"
    >
      <div className="space-y-5">
        {/* Header: Toggle & Quick Summary */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-gradient-to-r aseel-bg-panel to-[var(--color-primary)] dark:aseel-bg-panel/10 dark:to-[var(--color-primary)]/10 border aseel-border-soft dark:aseel-border-soft/30">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 flex items-center justify-center rounded-xl aseel-bg-field dark:aseel-bg-panel shadow-sm border aseel-border-accent dark:aseel-border-soft">
              <CreditCard className="w-6 h-6 aseel-text-accent dark:aseel-text-soft" />
            </div>
            <div>
              <h4 className="font-bold aseel-text-ink dark:text-white">نظام الدفعات</h4>
              <p className="text-xs aseel-text-soft dark:aseel-text-soft">إدارة الجدولة والتحصيل المالي</p>
              {/* إظهار تلميح عن الشحن والمدفوعات المحلية */}
              {(shippingCost > 0 || totalLocalPayments > 0) && (
                <div className="flex flex-wrap gap-2 mt-1">
                  {shippingCost > 0 && !shippingIncluded && (
                    <span className="text-xs aseel-text-soft dark:aseel-text-soft">
                      يشمل الشحن: {symbol}{shippingCost.toLocaleString()}
                    </span>
                  )}
                  {totalLocalPayments > 0 && !localPayments.includedInPrice && (
                    <span className="text-xs aseel-text-soft dark:aseel-text-soft">
                      ومدفوعات محلية: {symbol}{totalLocalPayments.toLocaleString()}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="hidden sm:flex flex-col items-end">
              <span className="text-xs aseel-text-soft uppercase tracking-wider font-semibold">نسبة التحصيل</span>
              <span className="text-lg font-black aseel-text-accent dark:aseel-text-soft">{progressPercentage}%</span>
            </div>
            <label className="relative inline-flex items-center cursor-pointer scale-110">
              <input
                type="checkbox"
                checked={installmentPlanEnabled}
                onChange={(e) => onToggleInstallmentPlan(e.target.checked)}
                className="sr-only peer"
                disabled={readOnly}
              />
              <div className="w-12 h-6 aseel-bg-grid-head dark:aseel-bg-panel peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:aseel-bg-accent after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:aseel-bg-field after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
            </label>
          </div>
        </div>

        {installmentPlanEnabled && (
          <div className="grid grid-cols-1 gap-6 animate-in fade-in slide-in-from-top-2 duration-300">

            {/* 3-Cards Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                { label: 'إجمالي الفاتورة', value: grandTotal, color: 'aseel-text-ink', bg: 'aseel-bg-field', icon: Calculator },
                { label: 'المبلغ المحصل', value: totalPaidAmount, color: 'text-green-600', bg: 'bg-green-50/50', icon: CheckCircle2 },
                { label: 'المتبقي', value: remainingAmount, color: 'aseel-text-soft', bg: 'aseel-bg-panel/50', icon: AlertCircle },
              ].map((card, i) => (
                <div key={i} className={`${card.bg} dark:aseel-bg-panel/40 p-4 rounded-xl border aseel-border-soft dark:aseel-border-soft shadow-sm flex items-center justify-between`}>
                  <div>
                    <p className="text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">{card.label}</p>
                    <p className={`text-xl font-black ${card.color} dark:text-white`}>
                      {symbol}{formatMoney(card.value)}
                    </p>
                    {card.label === 'إجمالي الفاتورة' && (
                      <p className="text-xs aseel-text-soft mt-1">
                        {shippingCost > 0 && !shippingIncluded && `يشمل الشحن`}
                        {totalLocalPayments > 0 && !localPayments.includedInPrice && ` ومدفوعات محلية`}
                      </p>
                    )}
                  </div>
                  <card.icon className={`w-8 h-8 opacity-20 ${card.color}`} />
                </div>
              ))}
            </div>

            {/* List Header */}
            <div className="flex items-center justify-between border-b aseel-border-soft dark:aseel-border-soft pb-2">
              <h5 className="flex items-center gap-2 font-bold aseel-text-ink dark:aseel-text-soft text-sm">
                <ChevronRight className="w-4 h-4 aseel-text-soft" /> جدولة الدفعات
              </h5>
              {!readOnly && (
                <button
                  onClick={onAddInstallment}
                  className="flex items-center gap-1.5 px-3 py-1.5 aseel-bg-accent hover:aseel-bg-accent text-white rounded-lg text-xs font-bold transition-all shadow-sm active:scale-95"
                >
                  <Plus className="w-3.5 h-3.5" /> إضافة دفعة
                </button>
              )}
            </div>

            {/* Installments Rows */}
            <div className="space-y-3">
              {installments.length === 0 ? (
                <div className="text-center py-10 aseel-bg-panel/50 dark:aseel-bg-panel/20 rounded-2xl border-2 border-dashed aseel-border-soft dark:aseel-border-soft">
                  <Calculator className="w-10 h-10 aseel-text-soft mx-auto mb-2" />
                  <p className="aseel-text-soft text-sm">لا توجد دفعات مجدولة حالياً</p>
                </div>
              ) : (
                installments.map((inst, idx) => (
                  <div
                    key={inst.id}
                    className="group flex flex-col gap-3 p-3 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl hover:shadow-md hover:aseel-border-accent dark:hover:aseel-border-soft/50 transition-all"
                  >
                    {/* الصف الأول: المعلومات الأساسية */}
                    <div className="flex flex-col md:flex-row items-center gap-3">
                      {/* Number */}
                      <div className="flex items-center justify-center w-8 h-8 rounded-lg aseel-bg-panel dark:aseel-bg-panel text-xs font-black aseel-text-soft dark:aseel-text-soft">
                        {inst.installmentNumber}
                      </div>

                      {/* Amount Input */}
                      <div className="relative flex-1 min-w-[140px] w-full">
                        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 aseel-text-soft flex items-center justify-center font-bold text-xs">{symbol}</span>
                        <input
                          type="number"
                          value={inst.amount || ''}
                          onChange={(e) => onUpdateInstallment(idx, 'amount', parseFloat(e.target.value) || 0)}
                          placeholder="المبلغ"
                          disabled={readOnly}
                          className="w-full pr-8 pl-3 py-2 aseel-bg-panel dark:aseel-bg-panel border-none rounded-lg text-sm font-bold focus:ring-2 focus:ring-blue-500 dark:text-white"
                        />
                      </div>

                      {/* Status Select */}
                      <div className="w-full md:w-36">
                        <select
                          value={inst.status}
                          onChange={(e) => onUpdateInstallment(idx, 'status', e.target.value)}
                          disabled={readOnly}
                          className={`w-full py-2 px-3 rounded-lg text-xs font-bold border-none appearance-none cursor-pointer transition-colors ${inst.status === 'paid'
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            : 'aseel-bg-panel aseel-text-ink dark:aseel-bg-panel/30 dark:aseel-text-soft'
                            }`}
                        >
                          <option value="unpaid">⏳ غير مدفوعة</option>
                          <option value="paid">✅ مدفوعة</option>
                        </select>
                      </div>

                      {/* Delete Action */}
                      {!readOnly && (
                        <button
                          onClick={() => onRemoveInstallment(idx)}
                          className="hidden md:block p-2 aseel-text-soft hover:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel/20 rounded-lg transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>

                    {/* الصف الثاني: الملاحظات، التاريخ، الصورة */}
                    <div className="flex flex-col md:flex-row gap-3 pt-2 border-t aseel-border-soft dark:aseel-border-soft/50">

                      {/* Notes Input */}
                      <div className="relative flex-[2]">
                        <FileText className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 aseel-text-soft" />
                        <input
                          type="text"
                          value={inst.notes || ''}
                          onChange={(e) => onUpdateInstallment(idx, 'notes', e.target.value)}
                          placeholder="ملاحظات الدفعة..."
                          disabled={readOnly}
                          className="w-full pr-8 pl-3 py-1.5 aseel-bg-panel dark:aseel-bg-panel border-none rounded-lg text-xs focus:ring-1 focus:ring-blue-500 dark:text-white"
                        />
                      </div>

                      {/* Payment Date Input */}
                      <div className="relative flex-1 min-w-[130px]">
                        <Calendar className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 aseel-text-soft" />
                        <input
                          type="date"
                          value={inst.paymentDate ? inst.paymentDate.split('T')[0] : ''}
                          onChange={(e) => onUpdateInstallment(idx, 'paymentDate', e.target.value)}
                          disabled={readOnly}
                          className="w-full pr-8 pl-2 py-1.5 aseel-bg-panel dark:aseel-bg-panel border-none rounded-lg text-xs focus:ring-1 focus:ring-blue-500 dark:text-white"
                          title="تاريخ الدفع"
                        />
                      </div>

                      {/* Upload Bank Slip */}
                      <div className="flex items-center gap-2">
                        {inst.bankSlipUrl ? (
                          <div className="flex items-center gap-2 bg-green-50 dark:bg-green-900/20 px-2 py-1 rounded-lg border border-green-100 dark:border-green-800">
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                            <span className="text-xs text-green-700 dark:text-green-400">تم الرفع</span>

                            {/* زر معاينة */}
                            <a
                              href={inst.bankSlipUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1 hover:bg-green-200 dark:hover:bg-green-800 rounded transition"
                              title="مشاهدة الصورة"
                            >
                              <Eye className="w-3.5 h-3.5 text-green-700 dark:text-green-400" />
                            </a>

                            {/* زر حذف الصورة */}
                            {!readOnly && (
                              <button
                                onClick={() => onUpdateInstallment(idx, 'bankSlipUrl', '')}
                                className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 rounded transition"
                                title="حذف الصورة"
                              >
                                <X className="w-3.5 h-3.5 aseel-text-soft" />
                              </button>
                            )}
                          </div>
                        ) : (
                          <div className="relative">
                            <input
                              type="file"
                              id={`slip-upload-${idx}`}
                              className="hidden"
                              accept="image/*"
                              onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0], idx)}
                              disabled={readOnly || uploadingIndex === idx}
                            />
                            <label
                              htmlFor={`slip-upload-${idx}`}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-all
                                 ${uploadingIndex === idx
                                  ? 'aseel-bg-panel aseel-text-soft cursor-not-allowed'
                                  : 'aseel-bg-accent-bg aseel-text-accent hover:aseel-bg-accent-bg border aseel-border-accent dark:aseel-bg-panel/20 dark:aseel-text-soft dark:aseel-border-soft'
                                }
                               `}
                            >
                              {uploadingIndex === idx ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <UploadCloud className="w-3.5 h-3.5" />
                              )}
                              <span>{uploadingIndex === idx ? 'جاري الرفع...' : 'سليب البنك'}</span>
                            </label>
                          </div>
                        )}
                      </div>

                      {/* Delete Button Mobile */}
                      {!readOnly && (
                        <button
                          onClick={() => onRemoveInstallment(idx)}
                          className="md:hidden p-2 aseel-text-soft aseel-bg-panel rounded-lg self-end"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Progress Bar Section */}
            {grandTotal > 0 && (
              <div className="mt-2 p-4 rounded-xl aseel-bg-panel dark:aseel-bg-panel/30 border aseel-border-soft dark:aseel-border-soft">
                <div className="flex justify-between items-end mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold aseel-text-soft dark:aseel-text-soft uppercase tracking-tighter">حالة التحصيل</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${progressPercentage === 100 ? 'bg-green-100 text-green-700' : 'aseel-bg-accent-bg aseel-text-accent'}`}>
                      {progressPercentage === 100 ? 'مكتمل' : 'قيد التحصيل'}
                    </span>
                  </div>
                  <span className="text-sm font-black aseel-text-accent dark:aseel-text-soft">{progressPercentage}%</span>
                </div>
                <div className="h-2.5 aseel-bg-grid-head dark:aseel-bg-panel rounded-full overflow-hidden shadow-inner">
                  <div
                    className="h-full bg-gradient-to-r aseel-bg-panel to-[var(--color-primary)] transition-all duration-700 ease-out"
                    style={{ width: `${Math.min(100, progressPercentage)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
};