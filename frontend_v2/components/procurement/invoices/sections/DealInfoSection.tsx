import React from 'react';
import { DealInvoiceInfo, Invoice } from '@/types';
import { Factory, Truck, FileText, Calendar, Clock, CheckCircle, XCircle } from 'lucide-react';

interface DealInfoSectionProps {
  dealInfo: DealInvoiceInfo;
  formData: Partial<Invoice>;
  onUpdateDealInfo: (field: string, value: any) => void;
}

export const DealInfoSection: React.FC<DealInfoSectionProps> = ({
  dealInfo,
  formData,
  onUpdateDealInfo
}) => {
  return (
    <div className="border aseel-border-accent dark:aseel-border-soft rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r aseel-bg-panel aseel-bg-panel dark:aseel-bg-panel dark:aseel-bg-panel px-6 py-4 border-b aseel-border-accent dark:aseel-border-soft">
        <h3 className="text-lg font-semibold aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
          <Factory className="w-5 h-5" />
          معلومات الصفقة المرتبطة
          {formData.dealNumber && (
            <span className="text-sm aseel-bg-accent-bg aseel-text-ink dark:aseel-bg-panel dark:aseel-text-soft px-2 py-1 rounded">
              {formData.dealNumber}
            </span>
          )}
        </h3>
      </div>

      <div className="p-6 space-y-6">
        {/* Basic Deal Info */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Deal Status */}
          <div className="space-y-2">
            <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
              <CheckCircle className="w-4 h-4" />
              حالة الصفقة الأصلية
            </label>
            <select
              value={dealInfo.originalStatus || ''}
              onChange={(e) => onUpdateDealInfo('originalStatus', e.target.value)}
              className="w-full p-2 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white"
            >
              <option value="">اختر الحالة</option>
              <option value="initial">أولية</option>
              <option value="manufacturing_started">بدء التصنيع</option>
              <option value="production_completed">تم التصنيع</option>
              <option value="shipping_in_progress">جاري الشحن</option>
              <option value="shipped">تم الشحن</option>
              <option value="completed">مكتملة</option>
              <option value="cancelled">ملغاة</option>
            </select>
          </div>

          {/* Deal Date */}
          <div className="space-y-2">
            <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              تاريخ الصفقة
            </label>
            <input
              type="date"
              value={dealInfo.dealDate || ''}
              onChange={(e) => onUpdateDealInfo('dealDate', e.target.value)}
              className="w-full p-2 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white"
            />
          </div>

          {/* Shipping Method */}
          <div className="space-y-2">
            <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
              <Truck className="w-4 h-4" />
              طريقة الشحن
            </label>
            <input
              type="text"
              value={dealInfo.shippingMethod || ''}
              onChange={(e) => onUpdateDealInfo('shippingMethod', e.target.value)}
              className="w-full p-2 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white"
              placeholder="EXW, FOB, CIF..."
            />
          </div>
        </div>

        {/* Timeline Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Production Timeline */}
          <div className="space-y-4 p-4 aseel-bg-panel dark:aseel-bg-panel/30 rounded-lg border">
            <h4 className="font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
              <Clock className="w-4 h-4" />
              الجدول الزمني للإنتاج
            </h4>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm aseel-text-soft dark:aseel-text-soft">أيام الإنتاج</label>
                  <input
                    type="number"
                    value={dealInfo.productionDays || ''}
                    onChange={(e) => onUpdateDealInfo('productionDays', parseInt(e.target.value) || 0)}
                    className="w-full p-2 border rounded-lg dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                  />
                </div>
                <div>
                  <label className="text-sm aseel-text-soft dark:aseel-text-soft">أيام التسليم</label>
                  <input
                    type="number"
                    value={dealInfo.deliveryDays || ''}
                    onChange={(e) => onUpdateDealInfo('deliveryDays', parseInt(e.target.value) || 0)}
                    className="w-full p-2 border rounded-lg dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                  />
                </div>
              </div>
              {dealInfo.startedProductionAt && (
                <div className="text-sm">
                  <span className="aseel-text-soft dark:aseel-text-soft">بدء الإنتاج: </span>
                  <span className="font-medium">{new Date(dealInfo.startedProductionAt).toLocaleDateString('ar-SA')}</span>
                </div>
              )}
            </div>
          </div>

          {/* Payment Dates */}
          <div className="space-y-4 p-4 aseel-bg-panel dark:aseel-bg-panel/30 rounded-lg border">
            <h4 className="font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              تواريخ الدفع
            </h4>
            <div className="space-y-3">
              <div>
                <label className="text-sm aseel-text-soft dark:aseel-text-soft">تاريخ الدفعة الأولى</label>
                <input
                  type="date"
                  value={dealInfo.firstPaymentDate || ''}
                  onChange={(e) => onUpdateDealInfo('firstPaymentDate', e.target.value)}
                  className="w-full p-2 border rounded-lg dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                />
              </div>
              {dealInfo.completedAt && (
                <div className="text-sm">
                  <span className="aseel-text-soft dark:aseel-text-soft">تاريخ الإكمال: </span>
                  <span className="font-medium">{new Date(dealInfo.completedAt).toLocaleDateString('ar-SA')}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Alibaba Link */}
        <div className="space-y-2">
          <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
            <FileText className="w-4 h-4" />
            رابط طلبية علي بابا
          </label>
          <input
            type="url"
            value={dealInfo.alibabaOrderLink || ''}
            onChange={(e) => onUpdateDealInfo('alibabaOrderLink', e.target.value)}
            className="w-full p-2 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white"
            placeholder="https://..."
          />
          {dealInfo.alibabaOrderLink && (
            <p className="text-xs aseel-text-accent dark:aseel-text-soft">
              <a href={dealInfo.alibabaOrderLink} target="_blank" rel="noopener noreferrer" className="hover:underline">
                انقر لفتح الرابط
              </a>
            </p>
          )}
        </div>

        {/* Internal Notes */}
        <div className="space-y-2">
          <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft flex items-center gap-2">
            <FileText className="w-4 h-4" />
            الملاحظات الداخلية للصفقة
          </label>
          <textarea
            value={dealInfo.internalNotes || ''}
            onChange={(e) => onUpdateDealInfo('internalNotes', e.target.value)}
            rows={4}
            className="w-full p-3 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white"
            placeholder="ملاحظات الصفقة الداخلية..."
          />
        </div>
      </div>
    </div>
  );
};