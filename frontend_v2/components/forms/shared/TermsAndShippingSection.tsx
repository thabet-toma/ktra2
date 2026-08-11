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
    <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] overflow-hidden h-fit">

      {/* Header */}
      <div className="p-3 bg-[var(--color-surface-2)] border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-slate-600 dark:bg-slate-500 rounded-md">
            <Truck className="w-4 h-4 text-white" />
          </div>
          <h3 className="font-bold text-sm text-[var(--color-text)]">الشروط والشحن</h3>
        </div>
      </div>

      {/* Body */}
      <div className="p-3 space-y-3">

        {/* 1. Time & Payment (Grid) */}
        <div className="grid grid-cols-2 gap-2">
          {/* Production Time */}
          <div className="space-y-1">
            <label className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1">
              <Clock className="w-3 h-3" /> وقت الإنتاج
            </label>
            <div className="relative">
              <input
                type="number"
                min="0"
                value={data.productionDays || ''}
                onChange={e => updateField('productionDays', parseFloat(e.target.value))}
                disabled={readOnly}
                className="w-full h-8 pl-2 pr-7 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
                placeholder="0"
              />
              <span className="absolute right-2 top-2 text-[10px] text-[var(--color-text-muted)]">يوم</span>
            </div>
          </div>

          {/* Delivery Time */}
          <div className="space-y-1">
            <label className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1">
              <Calendar className="w-3 h-3" /> التوصيل
            </label>
            <div className="relative">
              <input
                type="number"
                min="0"
                value={data.deliveryDays || ''}
                onChange={e => updateField('deliveryDays', parseFloat(e.target.value))}
                disabled={readOnly}
                className="w-full h-8 pl-2 pr-7 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
                placeholder="0"
              />
              <span className="absolute right-2 top-2 text-[10px] text-[var(--color-text-muted)]">يوم</span>
            </div>
          </div>

          {/* Payment Method */}
          <div className="space-y-1 col-span-2">
            <label className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1">
              <CreditCard className="w-3 h-3" /> طريقة الدفع
            </label>
            <input
              type="text"
              value={data.paymentMethod || ''}
              onChange={e => updateField('paymentMethod', e.target.value)}
              disabled={readOnly}
              className="w-full h-8 px-2 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
              placeholder="مثال: T/T 30% Deposit"
            />
          </div>
        </div>

        <hr className="border-[var(--color-border)]" />

        {/* 2. Shipping Details */}
        <div className="space-y-2">
          {/* Incoterm & Warranty */}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] text-[var(--color-text-muted)]">طريقة الشحن</label>
              <select
                value={data.shippingMethod || ''}
                onChange={e => updateField('shippingMethod', e.target.value)}
                disabled={readOnly}
                className="w-full h-8 px-1 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
              >
                <option value="">اختر...</option>
                {SHIPPING_TERMS.map(term => (
                  <option key={term.code} value={term.code}>{term.code}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1">
                <Shield className="w-3 h-3" /> الضمان (سنة)
              </label>
              <input
                type="number"
                min="0"
                step="0.5"
                value={data.warrantyDuration || ''}
                onChange={e => updateField('warrantyDuration', parseFloat(e.target.value))}
                disabled={readOnly}
                className="w-full h-8 px-2 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
                placeholder="0"
              />
            </div>
          </div>

          {/* Shipping Cost */}
          <div className="bg-[var(--color-surface-2)] p-2 rounded border border-[var(--color-border)]">
            <div className="flex justify-between items-center mb-1.5">
              <label className="text-[10px] font-medium text-[var(--color-text)] flex items-center gap-1" title="الشحن داخل الصين المدفوع للمورد ضمن الصفقة. الشحن الدولي يُدار في الشحنة، لا هنا.">
                <Truck className="w-3 h-3" /> شحن داخل الصين
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
                <span className="text-[10px] text-[var(--color-text-muted)]">متضمن بالسعر</span>
              </label>
            </div>
            <div className="relative">
              <input
                type="number"
                value={data.shippingIncluded ? '' : (data.shippingCost || '')}
                onChange={e => updateField('shippingCost', parseFloat(e.target.value) || 0)}
                disabled={readOnly || data.shippingIncluded}
                className={`w-full h-8 pl-8 pr-2 text-xs border rounded transition-colors ${data.shippingIncluded
                  ? 'bg-[var(--color-surface-3)] text-[var(--color-text-muted)] border-transparent'
                  : 'bg-[var(--color-surface)] border-[var(--color-border)]'}`}
                placeholder={data.shippingIncluded ? "0.00 (متضمن)" : "0.00"}
              />
              <DollarSign className="w-3 h-3 text-[var(--color-text-muted)] absolute left-2 top-2.5" />
            </div>
          </div>
        </div>

        <hr className="border-[var(--color-border)]" />

        {/* 3. Logistics & Certs */}
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1">
            <label className="text-[10px] text-[var(--color-text-muted)] flex gap-1"><Scale className="w-3 h-3" />وزن (kg)</label>
            <input
              type="number"
              value={data.totalWeight || 0}
              onChange={e => updateField('totalWeight', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-7 px-1 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-[var(--color-text-muted)] flex gap-1"><Box className="w-3 h-3" />حجم (CBM)</label>
            <input
              type="number"
              value={data.totalVolume || 0}
              onChange={e => updateField('totalVolume', parseFloat(e.target.value))}
              disabled={readOnly}
              className="w-full h-7 px-1 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-[var(--color-text-muted)] flex gap-1"><BadgeCheck className="w-3 h-3" />شهادات</label>
            <input
              type="text"
              value={data.certificates || ''}
              onChange={e => updateField('certificates', e.target.value)}
              disabled={readOnly}
              placeholder="CE, ROHS"
              className="w-full h-7 px-1 text-xs border border-[var(--color-border)] rounded dark:bg-gray-700"
            />
          </div>
        </div>

        {/* Notes */}
        <div className="pt-1">
          <textarea
            value={data.shipmentNotes || ''}
            onChange={e => updateField('shipmentNotes', e.target.value)}
            className="w-full p-2 text-xs border border-[var(--color-border)] rounded bg-[var(--color-surface-2)] resize-none focus:bg-[var(--color-surface)] transition-colors"
            rows={2}
            placeholder="ملاحظات شحن إضافية..."
            disabled={readOnly}
          />
        </div>

      </div>
    </div>
  );
};