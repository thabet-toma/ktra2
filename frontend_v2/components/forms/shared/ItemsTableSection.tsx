import React, { useState } from 'react';
import {
  Plus, Trash2, Image as ImageIcon, Package, ShoppingCart,
  DollarSign, Percent, Tag, Copy, CreditCard, Truck,
} from 'lucide-react';
import { SHIPPING_TERMS } from '@/constants/shipping';

// ─── 1. مكون الشروط والشحن ───
interface TermsProps {
  data: any;
  onUpdate: (field: string, value: any) => void;
  readOnly?: boolean;
}

const TermsAndShippingCard: React.FC<TermsProps> = ({ data, onUpdate, readOnly }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden h-full">
      {/* Header */}
      <div className="p-3 bg-gradient-to-r from-blue-50 to-[var(--color-primary)] dark:from-blue-900/20 dark:to-[var(--color-primary)]/20 border-b">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500 rounded-lg">
            <Truck className="w-4 h-4 text-white" />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-white text-sm">الشروط والشحن</h3>
        </div>
      </div>

      {/* Body */}
      <div className="p-3 space-y-3">
        {/* حقول الأيام */}
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="text-xs text-gray-600 dark:text-gray-400">الإنتاج (يوم)</label>
            <input
              type="number" min="0"
              value={data.productionDays || ''}
              onChange={e => onUpdate('productionDays', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
              placeholder="0"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-600 dark:text-gray-400">التوصيل (يوم)</label>
            <input
              type="number" min="0"
              value={data.deliveryDays || ''}
              onChange={e => onUpdate('deliveryDays', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
              placeholder="0"
            />
          </div>
        </div>

        {/* طريقة الدفع والشحن */}
        <div className="space-y-1">
          <label className="text-xs text-gray-600 dark:text-gray-400">طريقة الدفع</label>
          <input
            type="text"
            value={data.paymentMethod || ''}
            onChange={e => onUpdate('paymentMethod', e.target.value)}
            disabled={readOnly}
            className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
            placeholder="T/T 30%"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="text-xs text-gray-600 dark:text-gray-400">طريقة الشحن</label>
            <select
              value={data.shippingMethod || ''}
              onChange={e => onUpdate('shippingMethod', e.target.value)}
              disabled={readOnly}
              className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
            >
              <option value="">اختر...</option>
              {SHIPPING_TERMS.map(t => <option key={t.code} value={t.code}>{t.code}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-600 dark:text-gray-400">ضمان (سنة)</label>
            <input
              type="number" min="0" step="0.5"
              value={data.warrantyDuration || ''}
              onChange={e => onUpdate('warrantyDuration', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
            />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-600 dark:text-gray-400">شهادات</label>
          <input
            type="text"
            value={data.certificates || ''}
            onChange={e => onUpdate('certificates', e.target.value)}
            disabled={readOnly}
            placeholder="CE, ISO"
            className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
          />
        </div>

        {/* تكلفة الشحن */}
        <div className="p-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg border">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-gray-700 dark:text-gray-300">تكلفة الشحن</label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={data.shippingIncluded || false}
                onChange={e => {
                  onUpdate('shippingIncluded', e.target.checked);
                  if (e.target.checked) onUpdate('shippingCost', 0);
                }}
                disabled={readOnly}
                className="w-3 h-3"
              />
              <span className="text-xs text-gray-600 dark:text-gray-400">متضمن</span>
            </label>
          </div>
          <div className="relative">
            <span className="w-3 h-3 text-gray-500 absolute right-2 top-2.5 flex items-center justify-center font-bold text-xs">
              {data.currency === 'ILS' ? '₪' : '$'}
            </span>
            <input
              type="number"
              value={data.shippingIncluded ? '' : (data.shippingCost || '')}
              onChange={e => onUpdate('shippingCost', parseFloat(e.target.value) || 0)}
              disabled={readOnly || data.shippingIncluded}
              className={`w-full h-8 pl-8 pr-2 text-sm border rounded-lg ${data.shippingIncluded
                ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 border-gray-200 dark:border-gray-700'
                : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600'
                }`}
              placeholder={data.shippingIncluded ? "0.00 (متضمن)" : "0.00"}
            />
          </div>
        </div>

        {/* الوزن والحجم */}
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="text-xs text-gray-600 dark:text-gray-400">الوزن (kg)</label>
            <input
              type="number"
              value={data.totalWeight || 0}
              onChange={e => onUpdate('totalWeight', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-gray-600 dark:text-gray-400">الحجم (CBM)</label>
            <input
              type="number"
              value={data.totalVolume || 0}
              onChange={e => onUpdate('totalVolume', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
            />
          </div>
        </div>

        {/* ملاحظات الشحن - مستقلة تماماً */}
        <textarea
          value={data.shipmentNotes || ''}
          onChange={e => onUpdate('shipmentNotes', e.target.value)}
          className="w-full p-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-900/50 resize-none"
          rows={2}
          placeholder="ملاحظات شحن..."
          disabled={readOnly}
        />
      </div>
    </div>
  );
};

// ─── 2. المدفوعات المحلية ───
interface LocalPaymentsCardProps {
  data: any;
  readOnly?: boolean;
  onUpdate: (field: string, value: any) => void;
  totalLocalPayments: number;
}

const LocalPaymentsCard: React.FC<LocalPaymentsCardProps> = ({
  data,
  readOnly,
  onUpdate,
  totalLocalPayments
}) => {
  const handleUpdate = (field: string, value: any) => {
    const updatedData = { ...data, [field]: value };
    if (field === 'calculationMethod') {
      if (value === 'lump_sum') {
        updatedData.customsClearanceFees = 0;
        updatedData.customsDuties = 0;
        updatedData.portFees = 0;
        updatedData.internalShippingFees = 0;
      } else {
        updatedData.lumpSumAmount = 0;
      }
    }
    onUpdate('localPayments', updatedData);
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden h-full">
      <div className="p-3 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary)] dark:from-[var(--color-primary)]/20 dark:to-[var(--color-primary)]/20 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-[var(--color-primary)] rounded-lg">
              <CreditCard className="w-4 h-4 text-white" />
            </div>
            <h3 className="font-semibold text-gray-900 dark:text-white text-sm">المدفوعات المحلية</h3>
          </div>
          <button
            onClick={() => !readOnly && handleUpdate('includedInPrice', !data.includedInPrice)}
            disabled={readOnly}
            className={`text-xs px-2 py-1 rounded-full transition-colors ${data.includedInPrice
              ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
              }`}
          >
            {data.includedInPrice ? 'مشمولة' : 'غير مشمولة'}
          </button>
        </div>
      </div>

      <div className="p-3 space-y-3">
        {!data.includedInPrice && (
          <>
            <div className="flex gap-1 p-1 bg-gray-100 dark:bg-gray-700/50 rounded-lg">
              <button
                onClick={() => handleUpdate('calculationMethod', 'detailed')}
                disabled={readOnly}
                className={`flex-1 py-1.5 text-xs rounded transition-colors ${data.calculationMethod === 'detailed'
                  ? 'bg-white dark:bg-gray-600 text-[var(--color-primary)] dark:text-[var(--color-primary)] font-medium'
                  : 'text-gray-600 dark:text-gray-400'
                  }`}
              >
                تفصيلي
              </button>
              <button
                onClick={() => handleUpdate('calculationMethod', 'lump_sum')}
                disabled={readOnly}
                className={`flex-1 py-1.5 text-xs rounded transition-colors ${data.calculationMethod === 'lump_sum'
                  ? 'bg-white dark:bg-gray-600 text-[var(--color-primary)] dark:text-[var(--color-primary)] font-medium'
                  : 'text-gray-600 dark:text-gray-400'
                  }`}
              >
                مبلغ شامل
              </button>
            </div>

            {data.calculationMethod === 'detailed' ? (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">مخلص جمركي</label>
                  <input
                    type="number"
                    value={data.customsClearanceFees || ''}
                    onChange={(e) => handleUpdate('customsClearanceFees', parseFloat(e.target.value) || 0)}
                    disabled={readOnly}
                    className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">جمارك</label>
                  <input
                    type="number"
                    value={data.customsDuties || ''}
                    onChange={(e) => handleUpdate('customsDuties', parseFloat(e.target.value) || 0)}
                    disabled={readOnly}
                    className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">رسوم ميناء</label>
                  <input
                    type="number"
                    value={data.portFees || ''}
                    onChange={(e) => handleUpdate('portFees', parseFloat(e.target.value) || 0)}
                    disabled={readOnly}
                    className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">شحن داخلي</label>
                  <input
                    type="number"
                    value={data.internalShippingFees || ''}
                    onChange={(e) => handleUpdate('internalShippingFees', parseFloat(e.target.value) || 0)}
                    disabled={readOnly}
                    className="w-full h-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
                    placeholder="0.00"
                  />
                </div>
              </div>
            ) : (
              <div>
                <label className="text-xs text-gray-600 dark:text-gray-400 block mb-1">المبلغ الإجمالي الشامل</label>
                <div className="relative">
                  <input
                    type="number"
                    value={data.lumpSumAmount || ''}
                    onChange={(e) => handleUpdate('lumpSumAmount', parseFloat(e.target.value) || 0)}
                    disabled={readOnly}
                    className="w-full h-8 pl-8 px-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 font-bold"
                    placeholder="0.00"
                  />
                  <span className="text-gray-500 absolute left-2 top-2 text-xs font-bold leading-none">
                    {data.currency === 'ILS' ? '₪' : '$'}
                  </span>
                </div>
              </div>
            )}
          </>
        )}

        <div className="pt-2 border-t border-gray-200 dark:border-gray-700 flex justify-between items-center">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">الإجمالي:</span>
          <span className="font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)] text-lg">
            ${totalLocalPayments.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
};

// ─── 3. الملخص المالي ───
interface FinancialSummaryCardProps {
  subtotal: number;
  discountAmount: number;
  taxRate: number;
  taxAmount: number;
  shippingCost: number;
  shippingIncluded: boolean;
  totalLocalPayments: number;
  localPaymentsIncluded: boolean;
  grandTotal: number;
  paidAmount: number;
  remainingAmount: number;
  readOnly?: boolean;
  onUpdateTax: (value: number) => void;
  onUpdateDiscount: (value: number) => void;
  taxInputMode: 'percentage' | 'amount';
  setTaxInputMode: (mode: 'percentage' | 'amount') => void;
  discountInput: string;
  setDiscountInput: (value: string) => void;
  taxInput: string;
  setTaxInput: (value: string) => void;
  showLocalPayments?: boolean;
  currency?: 'USD' | 'ILS';
}

const FinancialSummaryCard: React.FC<FinancialSummaryCardProps> = ({
  subtotal,
  discountAmount,
  taxRate,
  taxAmount,
  shippingCost,
  shippingIncluded,
  totalLocalPayments,
  localPaymentsIncluded,
  grandTotal,
  paidAmount,
  remainingAmount,
  readOnly,
  onUpdateTax,
  onUpdateDiscount,
  taxInputMode,
  setTaxInputMode,
  discountInput,
  setDiscountInput,
  taxInput,
  setTaxInput,
  showLocalPayments = true,
  currency = 'USD',
}) => {
  const symbol = currency === 'ILS' ? '₪' : '$';
  const handleDiscountUpdate = () => {
    const value = Math.min(subtotal, Math.max(0, parseFloat(discountInput) || 0));
    onUpdateDiscount(value);
  };

  const handleTaxUpdate = () => {
    const value = parseFloat(taxInput) || 0;
    onUpdateTax(value);
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden h-full">
      <div className="p-3 bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-green-500 rounded-lg">
              <DollarSign className="w-4 h-4 text-white" />
            </div>
            <h3 className="font-semibold text-gray-900 dark:text-white text-sm">الملخص المالي</h3>
          </div>
          <div className="text-lg font-bold text-green-600 dark:text-green-400">
            {symbol}{grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      <div className="p-3 space-y-3">
        {/* سعر المنتجات */}
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-700 dark:text-gray-300">سعر المنتجات</span>
          <span className="font-medium text-gray-900 dark:text-white">{symbol}{subtotal.toLocaleString()}</span>
        </div>

        {/* الخصم */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <Tag className="w-3 h-3 text-red-500" />
            <span>الخصم</span>
            {!readOnly && (
              <button
                onClick={() => setDiscountInput(discountAmount.toString())}
                className="text-xs text-blue-500 hover:text-blue-700"
              >
                ✏️
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {!readOnly ? (
              <input
                type="number"
                value={discountInput}
                onChange={(e) => setDiscountInput(e.target.value)}
                onBlur={handleDiscountUpdate}
                onKeyDown={(e) => e.key === 'Enter' && handleDiscountUpdate()}
                className="w-20 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
              />
            ) : (
              <span className={discountAmount > 0 ? "text-red-600 font-medium" : "text-gray-400"}>
                {discountAmount > 0 ? `-${symbol}${discountAmount.toLocaleString()}` : '-'}
              </span>
            )}
          </div>
        </div>

        {/* الضريبة */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <Percent className="w-3 h-3" />
            <span>الضريبة</span>
            {!readOnly && (
              <div className="flex gap-1">
                <button
                  onClick={() => setTaxInputMode('percentage')}
                  disabled={readOnly}
                  className={`text-xs px-2 py-0.5 rounded ${taxInputMode === 'percentage' ? 'bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300' : 'text-gray-500'}`}
                >
                  %
                </button>
                <button
                  onClick={() => setTaxInputMode('amount')}
                  disabled={readOnly}
                  className={`text-xs px-2 py-0.5 rounded ${taxInputMode === 'amount' ? 'bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300' : 'text-gray-500'}`}
                >
                  {symbol}
                </button>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {!readOnly ? (
              <input
                type="number"
                value={taxInput}
                onChange={(e) => setTaxInput(e.target.value)}
                onBlur={handleTaxUpdate}
                onKeyDown={(e) => e.key === 'Enter' && handleTaxUpdate()}
                className="w-20 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
              />
            ) : (
              <span className="font-medium text-gray-900 dark:text-white">
                {taxInputMode === 'percentage'
                  ? `${symbol}${taxAmount.toFixed(2)} (${taxRate}%)`
                  : `${symbol}${taxAmount.toFixed(2)}`
                }
              </span>
            )}
          </div>
        </div>

        {/* الشحن */}
        {(shippingCost > 0 || shippingIncluded) && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-700 dark:text-gray-300">الشحن</span>
            <span className="font-medium">
              {shippingIncluded ? (
                <span className="text-xs text-green-600">متضمن</span>
              ) : `${symbol}${shippingCost.toLocaleString()}`}
            </span>
          </div>
        )}

        {/* المدفوعات المحلية */}
        {showLocalPayments && (totalLocalPayments > 0 || localPaymentsIncluded) && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-700 dark:text-gray-300">مدفوعات محلية</span>
            <span className="font-medium">
              {localPaymentsIncluded ? (
                <span className="text-xs text-green-600">مشمولة</span>
              ) : `+${symbol}${totalLocalPayments.toLocaleString()}`}
            </span>
          </div>
        )}

        <div className="border-t border-gray-200 dark:border-gray-700 my-2"></div>

        {/* الإجمالي */}
        <div className="flex justify-between items-center">
          <span className="font-bold text-gray-900 dark:text-white">الإجمالي</span>
          <span className="text-xl font-bold text-green-600 dark:text-green-400">
            {symbol}{grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>

        <div className="border-t border-gray-200 dark:border-gray-700 my-2"></div>

        {/* المدفوع والمتبقي */}
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-600 dark:text-gray-400">المدفوع</span>
          <span className="font-medium text-green-600 dark:text-green-400">{symbol}{paidAmount.toLocaleString()}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-gray-600 dark:text-gray-400">المتبقي</span>
          <span className="font-medium text-orange-600 dark:text-orange-400">{symbol}{remainingAmount.toLocaleString()}</span>
        </div>

        {/* تقدم الدفع */}
        {grandTotal > 0 && (
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>تقدم الدفع</span>
              <span>{Math.round((paidAmount / grandTotal) * 100)}%</span>
            </div>
            <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 transition-all"
                style={{ width: `${(paidAmount / grandTotal) * 100}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── 4. المكون الرئيسي ───
interface ItemsTableProps {
  items: any[];
  onUpdateItem: (index: number, field: string, value: any) => void;
  onRemoveItem: (index: number) => void;
  onAddItem: () => void;
  onPreviewImage: (url: string) => void;
  supplierId?: string;
  readOnly?: boolean;
  allDbItems?: any[];
  discountAmount?: number;
  taxRate?: number;
  shippingCost?: number;
  shippingIncluded?: boolean;
  payments?: any[];
  localPayments?: any;
  productionDays?: number;
  deliveryDays?: number;
  paymentMethod?: string;
  shippingMethod?: string;
  warrantyDuration?: number;
  totalWeight?: number;
  totalVolume?: number;
  certificates?: string;
  shipmentNotes?: string;
  onUpdateFinancial?: (field: string, value: any) => void;
  showLocalPayments?: boolean;
  showShippingTerms?: boolean;
  taxAmount?: number;
  taxType?: 'percentage' | 'amount';
  currency?: 'USD' | 'ILS';
}

export const ItemsTableSection: React.FC<ItemsTableProps> = ({
  items,
  onUpdateItem,
  onRemoveItem,
  onAddItem,
  onPreviewImage,
  supplierId,
  readOnly = false,
  allDbItems,
  discountAmount = 0,
  taxRate = 0,
  shippingCost = 0,
  shippingIncluded = false,
  payments = [],
  localPayments = {} as any,
  productionDays, deliveryDays, paymentMethod, shippingMethod,
  warrantyDuration, totalWeight, totalVolume, certificates, shipmentNotes,
  onUpdateFinancial,
  showLocalPayments = true,
  showShippingTerms = true,
  taxAmount: propTaxAmount = 0,
  taxType: propTaxType = 'percentage',
  currency = 'USD',
}) => {
  const symbol = currency === 'ILS' ? '₪' : '$';
  const [taxInputMode, setTaxInputMode] = useState<'percentage' | 'amount'>(propTaxType);
  const [taxInput, setTaxInput] = useState(propTaxType === 'amount' ? propTaxAmount.toString() : taxRate.toString());
  const [discountInput, setDiscountInput] = useState(discountAmount.toString());
  const [editingItemDiscountIndex, setEditingItemDiscountIndex] = useState<number | null>(null);
  const [tempItemDiscountValue, setTempItemDiscountValue] = useState<string>("");

  React.useEffect(() => {
    setTaxInputMode(propTaxType);
    setTaxInput(propTaxType === 'amount' ? propTaxAmount.toString() : taxRate.toString());
  }, [propTaxType, propTaxAmount, taxRate]);

  const handleTaxModeChange = (newMode: 'percentage' | 'amount') => {
    setTaxInputMode(newMode);
    onUpdateFinancial?.('taxType', newMode);
    const currentValue = parseFloat(taxInput) || 0;
    if (newMode === 'amount') {
      onUpdateFinancial?.('taxAmount', currentValue);
      onUpdateFinancial?.('taxRate', 0);
    } else {
      onUpdateFinancial?.('taxRate', currentValue);
      onUpdateFinancial?.('taxAmount', 0);
    }
  };

  const termsData = {
    productionDays, deliveryDays, paymentMethod, shippingMethod,
    warrantyDuration, totalWeight, totalVolume, certificates, shipmentNotes,
    shippingCost, shippingIncluded
  };

  const calculateItemTotal = (item: any) => {
    const baseTotal = Number(item.quantity || 0) * Number(item.unitPrice || 0);
    const itemDiscount = parseFloat(item.itemDiscount) || 0;
    return Math.max(0, baseTotal - itemDiscount);
  };

  const subtotal = items.reduce((sum, item) => sum + calculateItemTotal(item), 0);
  const netAfterDiscount = Math.max(0, subtotal - discountAmount);

  const calculateTotalLocalPayments = () => {
    if (!localPayments || localPayments.includedInPrice) return 0;
    if (localPayments.calculationMethod === 'lump_sum') return localPayments.lumpSumAmount || 0;
    if (localPayments.calculationMethod === 'detailed') {
      return (
        (localPayments.customsClearanceFees || 0) +
        (localPayments.customsDuties || 0) +
        (localPayments.portFees || 0) +
        (localPayments.internalShippingFees || 0)
      );
    }
    return 0;
  };

  const totalLocalPayments = showLocalPayments ? calculateTotalLocalPayments() : 0;
  const taxAmount = taxInputMode === 'percentage' ? netAfterDiscount * (taxRate / 100) : (parseFloat(taxInput) || 0);
  const shipping = shippingIncluded ? 0 : shippingCost;
  const grandTotal = netAfterDiscount + taxAmount + shipping + totalLocalPayments;

  const paidAmount = payments.reduce(
    (sum: number, payment: any) => payment.confirmedBySupplier ? sum + (payment.amount || 0) : sum,
    0
  );
  const remainingAmount = grandTotal - paidAmount;

  const handleDiscountUpdate = (value: number) => {
    onUpdateFinancial?.('discountAmount', value);
  };

  const handleTaxUpdate = (value: number) => {
    if (taxInputMode === 'amount') {
      onUpdateFinancial?.('taxType', 'amount');
      onUpdateFinancial?.('taxAmount', value);
      onUpdateFinancial?.('taxRate', 0);
    } else {
      onUpdateFinancial?.('taxType', 'percentage');
      onUpdateFinancial?.('taxRate', value);
      onUpdateFinancial?.('taxAmount', 0);
    }
  };

  const handleLocalPaymentUpdate = (field: string, value: any) => {
    onUpdateFinancial?.(field, value);
  };

  const handleTermsUpdate = (field: string, value: any) => {
    onUpdateFinancial?.(field, value);
  };

  const startEditingItemDiscount = (index: number, currentDiscount: number) => {
    if (readOnly) return;
    setEditingItemDiscountIndex(index);
    setTempItemDiscountValue(currentDiscount ? currentDiscount.toString() : "");
  };

  const commitItemDiscount = (index: number) => {
    const item = items[index];
    const maxDiscount = Number(item.quantity || 0) * Number(item.unitPrice || 0);
    let val = parseFloat(tempItemDiscountValue);
    if (isNaN(val)) val = 0;
    const validDiscount = Math.min(maxDiscount, Math.max(0, val));
    if (validDiscount !== item.itemDiscount) {
      onUpdateItem(index, 'itemDiscount', validDiscount);
    }
    setEditingItemDiscountIndex(null);
  };

  const copyHsCode = (hsCode: string) => {
    navigator.clipboard.writeText(hsCode);
  };

  const visibleSections = [
    true,
    showShippingTerms,
    showLocalPayments,
  ].filter(Boolean).length;

  const gridCols = visibleSections === 3 ? 'lg:grid-cols-3' :
    visibleSections === 2 ? 'lg:grid-cols-2' :
      'lg:grid-cols-1';

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
            <Package className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">المنتجات والأسعار</h3>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-xs bg-gray-100 dark:bg-gray-700 px-2.5 py-1 rounded-full text-gray-700 dark:text-gray-300">
                {items.length} منتج
              </span>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                الإجمالي: ${grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </div>

        <button
          onClick={onAddItem}
          disabled={!supplierId || readOnly}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 text-sm font-medium disabled:opacity-50"
        >
          <Plus className="w-4 h-4" /> إضافة منتج
        </button>
      </div>

      {/* Table Section */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-white dark:bg-gray-800">
        {items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-gray-700 dark:text-gray-300">
                <tr>
                  <th className="px-4 py-3 font-medium min-w-[200px]">الصنف</th>
                  <th className="px-4 py-3 font-medium text-center min-w-[80px]">الكمية</th>
                  <th className="px-4 py-3 font-medium text-center min-w-[100px]">السعر ({symbol})</th>
                  <th className="px-4 py-3 font-medium text-center min-w-[100px]">الإجمالي ({symbol})</th>
                  <th className="px-4 py-3 font-medium text-center min-w-[100px]">الخصم ({symbol})</th>
                  <th className="px-4 py-3 font-medium text-center min-w-[100px]">الرمز الجمركي</th>
                  <th className="px-4 py-3 font-medium text-center min-w-[60px]"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {items.map((item, index) => {
                  const dbItem = allDbItems?.find(d => d.id === item.itemId || d.id === item.id);
                  const displayHsPrimary = item.hsCodePrimary || dbItem?.hsCodePrimary;
                  const itemFinalTotal = calculateItemTotal(item);
                  const itemDiscount = parseFloat(item.itemDiscount) || 0;

                  return (
                    <tr key={item.id || index} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => (item.imageUrls?.[0] || item.factoryImageUrl) && onPreviewImage(item.imageUrls?.[0] || item.factoryImageUrl)}
                            className="w-10 h-10 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center overflow-hidden border border-gray-200 dark:border-gray-600"
                          >
                            {item.imageUrls?.[0] || item.factoryImageUrl ? (
                              <img src={item.imageUrls?.[0] || item.factoryImageUrl} alt={item.name} className="w-full h-full object-cover" />
                            ) : (
                              <ImageIcon className="w-4 h-4 text-gray-400" />
                            )}
                          </button>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-gray-900 dark:text-white truncate">{item.name}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 flex justify-between items-center">
                              <span>{item.categoryName}</span>
                              {item.modelNumber && <span className="text-[10px] bg-gray-100 dark:bg-gray-800 px-1 rounded text-gray-500">{item.modelNumber}</span>}
                            </div>
                            {item.notes && (
                              <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-1 line-clamp-1 italic" title={item.notes}>
                                * {item.notes}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <input
                          type="text" inputMode="decimal"
                          value={item.quantity ?? ''}
                          onChange={(e) => onUpdateItem(index, 'quantity', e.target.value)}
                          disabled={readOnly}
                          className="w-16 p-1.5 text-center border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
                        />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <input
                          type="text" inputMode="decimal"
                          value={item.unitPrice ?? ''}
                          onChange={(e) => onUpdateItem(index, 'unitPrice', e.target.value)}
                          disabled={readOnly}
                          className="w-20 p-1.5 text-center border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700"
                        />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <div className="font-medium text-green-600 dark:text-green-400 text-sm">
                          {symbol}{itemFinalTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {editingItemDiscountIndex === index && !readOnly ? (
                          <input
                            type="number" step="0.01" min="0"
                            value={tempItemDiscountValue}
                            onChange={(e) => setTempItemDiscountValue(e.target.value)}
                            onBlur={() => commitItemDiscount(index)}
                            onKeyDown={(e) => { if (e.key === 'Enter') commitItemDiscount(index); }}
                            className="w-16 p-1.5 text-center border border-gray-300 rounded-lg text-sm bg-white"
                            autoFocus
                          />
                        ) : (
                          <div
                            onClick={() => startEditingItemDiscount(index, item.itemDiscount)}
                            className={`cursor-pointer text-sm ${itemDiscount > 0 ? 'text-red-600 font-medium' : 'text-gray-500'
                              }`}
                          >
                            {itemDiscount > 0 ? `-$${itemDiscount.toFixed(2)}` : 'إضافة'}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {displayHsPrimary ? (
                          <div className="flex items-center justify-center gap-1">
                            <span className="text-xs font-mono bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-2 py-1 rounded border border-blue-200 dark:border-blue-800">
                              {displayHsPrimary}
                            </span>
                            <button
                              onClick={() => copyHsCode(displayHsPrimary)}
                              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                            >
                              <Copy className="w-3 h-3 text-blue-500" />
                            </button>
                          </div>
                        ) : <span className="text-gray-400 text-sm">--</span>}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => onRemoveItem(index)}
                          disabled={readOnly}
                          className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center p-8">
          </div>
        )}
      </div>

      <div className={`grid grid-cols-1 ${gridCols} gap-4`}>
        {showShippingTerms && (
          <TermsAndShippingCard
            data={termsData}
            onUpdate={handleTermsUpdate}
            readOnly={readOnly}
          />
        )}
        {showLocalPayments && (
          <LocalPaymentsCard
            data={localPayments}
            readOnly={readOnly}
            onUpdate={handleLocalPaymentUpdate}
            totalLocalPayments={totalLocalPayments}
          />

        )}
        <FinancialSummaryCard
          subtotal={subtotal}
          discountAmount={discountAmount}
          taxRate={taxRate}
          taxAmount={taxAmount}
          shippingCost={shippingCost}
          shippingIncluded={shippingIncluded}
          totalLocalPayments={totalLocalPayments}
          localPaymentsIncluded={localPayments?.includedInPrice || false}
          grandTotal={grandTotal}
          paidAmount={paidAmount}
          remainingAmount={remainingAmount}
          readOnly={readOnly}
          onUpdateTax={handleTaxUpdate}
          onUpdateDiscount={handleDiscountUpdate}
          taxInputMode={taxInputMode}
          setTaxInputMode={handleTaxModeChange}
          discountInput={discountInput}
          setDiscountInput={setDiscountInput}
          taxInput={taxInput}
          setTaxInput={setTaxInput}
          showLocalPayments={showLocalPayments}
        />
      </div>
    </div>
  );
};