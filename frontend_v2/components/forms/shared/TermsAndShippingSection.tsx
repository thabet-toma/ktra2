import React from 'react';
import {
  Clock, CreditCard, Truck, Shield, FileText,
  Scale, Box, BadgeCheck, DollarSign, Calendar
} from 'lucide-react';
import { SHIPPING_TERMS } from '@/constants/shipping';

interface TermsProps {
  data: any;
  setData: (data: any) => void;
  readOnly?: boolean;
}

export const TermsAndShippingSection: React.FC<TermsProps> = ({
  data, setData, readOnly
}) => {

  const updateField = (field: string, value: any) => {
    setData((prev: any) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden h-fit">

      {/* Header */}
      <div className="p-3 bg-gradient-to-r from-orange-50 to-amber-50 dark:from-orange-900/20 dark:to-amber-900/20 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-orange-500 rounded-md">
            <Truck className="w-4 h-4 text-white" />
          </div>
          <h3 className="font-bold text-sm text-gray-900 dark:text-white">الشروط والشحن</h3>
        </div>
      </div>

      {/* Body */}
      <div className="p-3 space-y-3">

        {/* 1. Time & Payment (Grid) */}
        <div className="grid grid-cols-2 gap-2">
          {/* Production Time */}
          <div className="space-y-1">
            <label className="text-[10px] text-gray-500 flex items-center gap-1">
              <Clock className="w-3 h-3" /> وقت الإنتاج
            </label>
            <div className="relative">
              <input
                type="number"
                min="0"
                value={data.productionDays || ''}
                onChange={e => updateField('productionDays', parseFloat(e.target.value))}
                disabled={readOnly}
                className="w-full h-8 pl-2 pr-7 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
                placeholder="0"
              />
              <span className="absolute right-2 top-2 text-[10px] text-gray-400">يوم</span>
            </div>
          </div>

          {/* Delivery Time */}
          <div className="space-y-1">
            <label className="text-[10px] text-gray-500 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> التوصيل
            </label>
            <div className="relative">
              <input
                type="number"
                min="0"
                value={data.deliveryDays || ''}
                onChange={e => updateField('deliveryDays', parseFloat(e.target.value))}
                disabled={readOnly}
                className="w-full h-8 pl-2 pr-7 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
                placeholder="0"
              />
              <span className="absolute right-2 top-2 text-[10px] text-gray-400">يوم</span>
            </div>
          </div>

          {/* Payment Method */}
          <div className="space-y-1 col-span-2">
            <label className="text-[10px] text-gray-500 flex items-center gap-1">
              <CreditCard className="w-3 h-3" /> طريقة الدفع
            </label>
            <input
              type="text"
              value={data.paymentMethod || ''}
              onChange={e => updateField('paymentMethod', e.target.value)}
              disabled={readOnly}
              className="w-full h-8 px-2 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
              placeholder="مثال: T/T 30% Deposit"
            />
          </div>
        </div>

        <hr className="border-gray-100 dark:border-gray-700" />

        {/* 2. Shipping Details */}
        <div className="space-y-2">
          {/* Incoterm & Warranty */}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] text-gray-500">طريقة الشحن</label>
              <select
                value={data.shippingMethod || ''}
                onChange={e => updateField('shippingMethod', e.target.value)}
                disabled={readOnly}
                className="w-full h-8 px-1 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
              >
                <option value="">اختر...</option>
                {SHIPPING_TERMS.map(term => (
                  <option key={term.code} value={term.code}>{term.code}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-gray-500 flex items-center gap-1">
                <Shield className="w-3 h-3" /> الضمان (سنة)
              </label>
              <input
                type="number"
                min="0"
                step="0.5"
                value={data.warrantyDuration || ''}
                onChange={e => updateField('warrantyDuration', parseFloat(e.target.value))}
                disabled={readOnly}
                className="w-full h-8 px-2 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
                placeholder="0"
              />
            </div>
          </div>

          {/* Shipping Cost */}
          <div className="bg-gray-50 dark:bg-gray-900/50 p-2 rounded border border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-center mb-1.5">
              <label className="text-[10px] font-medium text-gray-700 dark:text-gray-300 flex items-center gap-1">
                <Truck className="w-3 h-3" /> تكلفة الشحن
              </label>
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={data.shippingIncluded || false}
                  onChange={e => {
                    updateField('shippingIncluded', e.target.checked);
                    if (e.target.checked) updateField('shippingCost', 0);
                  }}
                  disabled={readOnly}
                  className="w-3 h-3 text-blue-600 rounded"
                />
                <span className="text-[10px] text-gray-500">متضمن بالسعر</span>
              </label>
            </div>
            <div className="relative">
              <input
                type="number"
                value={data.shippingIncluded ? '' : (data.shippingCost || '')}
                onChange={e => updateField('shippingCost', parseFloat(e.target.value) || 0)}
                disabled={readOnly || data.shippingIncluded}
                className={`w-full h-8 pl-8 pr-2 text-xs border rounded transition-colors ${data.shippingIncluded
                  ? 'bg-gray-100 text-gray-400 border-transparent'
                  : 'bg-white border-gray-300 dark:bg-gray-700 dark:border-gray-600'}`}
                placeholder={data.shippingIncluded ? "0.00 (متضمن)" : "0.00"}
              />
              <DollarSign className="w-3 h-3 text-gray-400 absolute left-2 top-2.5" />
            </div>
          </div>
        </div>

        <hr className="border-gray-100 dark:border-gray-700" />

        {/* 3. Logistics & Certs */}
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1">
            <label className="text-[10px] text-gray-500 flex gap-1"><Scale className="w-3 h-3" />وزن (kg)</label>
            <input
              type="number"
              value={data.totalWeight || 0}
              onChange={e => updateField('totalWeight', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-7 px-1 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-gray-500 flex gap-1"><Box className="w-3 h-3" />حجم (CBM)</label>
            <input
              type="number"
              value={data.totalVolume || 0}
              onChange={e => updateField('totalVolume', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-7 px-1 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-gray-500 flex gap-1"><BadgeCheck className="w-3 h-3" />شهادات</label>
            <input
              type="text"
              value={data.certificates || ''}
              onChange={e => updateField('certificates', e.target.value)}
              disabled={readOnly}
              placeholder="CE, ROHS"
              className="w-full h-7 px-1 text-xs border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
            />
          </div>
        </div>

        {/* Notes */}
        <div className="pt-1">
          <textarea
            value={data.shipmentNotes || ''}
            onChange={e => updateField('shipmentNotes', e.target.value)}
            className="w-full p-2 text-xs border border-gray-300 rounded bg-gray-50 dark:bg-gray-700/50 dark:border-gray-600 resize-none focus:bg-white transition-colors"
            rows={2}
            placeholder="ملاحظات شحن إضافية..."
            disabled={readOnly}
          />
        </div>

      </div>
    </div>
  );
};