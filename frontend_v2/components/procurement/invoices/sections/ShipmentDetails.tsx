import React from 'react';
import { Invoice } from '@/types';
import { Package, Weight, Box, FileText } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';

interface ShipmentDetailsProps {
  formData: Partial<Invoice>;
  setFormData: (data: Partial<Invoice>) => void;
}

export const ShipmentDetails: React.FC<ShipmentDetailsProps> = ({
  formData,
  setFormData
}) => {
  return (
    <CollapsibleSection
      title="تفاصيل الشحن والملاحظات"
      icon={Package}
      defaultOpen={false}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* الوزن والحجم */}
        <div className="space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
              <Weight className="w-4 h-4" />
              الوزن الكلي (كجم)
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={formData.totalWeight || ''}
                onChange={e => setFormData({ ...formData, totalWeight: parseFloat(e.target.value) || 0 })}
                className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder="0.00"
              />
              <span className="text-gray-500 text-sm">kg</span>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
              <Box className="w-4 h-4" />
              الحجم الكلي (م³)
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="0.001"
                value={formData.totalVolume || ''}
                onChange={e => setFormData({ ...formData, totalVolume: parseFloat(e.target.value) || 0 })}
                className="w-full p-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder="0.000"
              />
              <span className="text-gray-500 text-sm">m³</span>
            </div>
          </div>
        </div>

        {/* الملاحظات */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
            <FileText className="w-4 h-4" />
            ملاحظات إضافية للشحن
          </label>
          <textarea
            value={formData.notes || ''}
            onChange={e => setFormData({ ...formData, notes: e.target.value })}
            rows={6}
            className="w-full p-3 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            placeholder="أي ملاحظات أخرى حول الشحن..."
          />
        </div>
      </div>

      {/* معلومات إضافية للشحن */}
      {(formData.totalWeight || formData.totalVolume) && (
        <div className="mt-6 p-4 bg-gray-50 dark:bg-gray-800/30 rounded-lg border">
          <h4 className="font-medium text-gray-800 dark:text-gray-200 mb-3">ملخص الشحن</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {formData.totalWeight && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">الوزن الكلي:</span>
                <span className="font-medium">{formData.totalWeight.toLocaleString()} كجم</span>
              </div>
            )}
            {formData.totalVolume && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">الحجم الكلي:</span>
                <span className="font-medium">{formData.totalVolume.toLocaleString()} م³</span>
              </div>
            )}
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
};