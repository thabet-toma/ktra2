import React, { useState } from 'react';
import { Supplier, InvoiceItem } from '../../types';
import { Package, ArrowRight, X, Image as ImageIcon, Calendar, DollarSign, Layers } from 'lucide-react';
import { formatDateValue } from "../../utils/formatDate";

interface SupplierRelatedItemsProps {
  supplier: Supplier;
  data: { item: InvoiceItem, lastPurchaseDate: string, totalQuantity: number, totalSpent: number }[];
  onBack: () => void;
}

export const SupplierRelatedItems: React.FC<SupplierRelatedItemsProps> = ({ supplier, data, onBack }) => {
  const [selectedItem, setSelectedItem] = useState<{ item: InvoiceItem, lastPurchaseDate: string, totalQuantity: number, totalSpent: number } | null>(null);

  return (
    <div className="ktra-bg-field dark:ktra-bg-panel rounded-xl shadow-sm p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4 border-b ktra-border-soft dark:ktra-border-soft pb-4">
        <button onClick={onBack} className="p-2 hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-full transition-colors">
          <ArrowRight className="w-6 h-6 ktra-text-soft" />
        </button>
        <div>
          <h2 className="text-xl font-bold ktra-text-ink dark:text-white">المنتجات الموردة</h2>
          <p className="text-sm ktra-text-soft dark:ktra-text-soft">للمورد: {supplier.tradeName}</p>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border ktra-border-soft dark:ktra-border-soft rounded-lg">
        <table className="w-full text-right text-sm">
          <thead className="ktra-bg-panel dark:ktra-bg-panel/50 ktra-text-ink dark:ktra-text-soft border-b ktra-border-soft dark:ktra-border-soft">
            <tr>
              <th className="px-6 py-4 w-16">#</th>
              <th className="px-6 py-4">الصورة</th>
              <th className="px-6 py-4">اسم المنتج</th>
              <th className="px-6 py-4">التصنيف</th>
              <th className="px-6 py-4">إجمالي الكمية</th>
              <th className="px-6 py-4">إجمالي المدفوع</th>
              <th className="px-6 py-4">آخر شراء</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {data.map((row, index) => (
              <tr 
                key={index} 
                onClick={() => setSelectedItem(row)}
                className="hover:ktra-bg-panel dark:hover:ktra-bg-panel/30 cursor-pointer transition-colors"
              >
                <td className="px-6 py-4 ktra-text-soft">{index + 1}</td>
                <td className="px-6 py-4">
                   {row.item.imageUrls?.[0] ? (
                     <img src={row.item.imageUrls[0]} alt="" className="w-10 h-10 rounded border ktra-border-soft object-cover" />
                   ) : (
                     <div className="w-10 h-10 rounded ktra-bg-panel flex items-center justify-center ktra-text-soft"><ImageIcon className="w-5 h-5" /></div>
                   )}
                </td>
                <td className="px-6 py-4 font-medium ktra-text-ink dark:text-white">
                  {row.item.name}
                </td>
                <td className="px-6 py-4 ktra-text-soft">
                  <span className="ktra-bg-panel dark:ktra-bg-panel px-2 py-1 rounded text-xs">
                    {row.item.categoryName || '-'}
                  </span>
                </td>
                <td className="px-6 py-4">
                   <span className="font-bold">{row.totalQuantity}</span>
                </td>
                <td className="px-6 py-4 font-bold text-green-600">
                   {row.totalSpent.toLocaleString()} $
                </td>
                <td className="px-6 py-4 ktra-text-soft dir-ltr text-right">
                   {formatDateValue(row.lastPurchaseDate)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.length === 0 && (
          <div className="text-center py-12 ktra-text-soft">
            <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا توجد منتجات مرتبطة بهذا المورد</p>
          </div>
        )}
      </div>

      {/* Item Details Modal */}
      {selectedItem && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[70] p-4" onClick={() => setSelectedItem(null)}>
          <div className="ktra-bg-field dark:ktra-bg-panel rounded-xl shadow-xl w-full max-w-lg overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b ktra-border-soft dark:ktra-border-soft flex justify-between items-center ktra-bg-panel dark:ktra-bg-panel/50">
              <h3 className="font-bold text-lg ktra-text-ink dark:text-white truncate">
                {selectedItem.item.name}
              </h3>
              <button onClick={() => setSelectedItem(null)}><X className="w-5 h-5 ktra-text-soft" /></button>
            </div>
            
            <div className="p-6 space-y-4">
                <div className="flex justify-center mb-4">
                    {selectedItem.item.imageUrls?.[0] ? (
                        <img src={selectedItem.item.imageUrls[0]} alt="" className="w-32 h-32 rounded-lg object-cover border" />
                    ) : (
                        <div className="w-32 h-32 rounded-lg ktra-bg-panel flex items-center justify-center"><ImageIcon className="w-12 h-12 ktra-text-soft" /></div>
                    )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <DetailItem icon={<Layers />} label="التصنيف" value={selectedItem.item.categoryName} />
                    <DetailItem icon={<Package />} label="الكمية الكلية من هذا المورد" value={selectedItem.totalQuantity} />
                    <DetailItem icon={<DollarSign />} label="إجمالي المدفوع للمورد" value={`${selectedItem.totalSpent.toLocaleString()} $`} />
                    <DetailItem icon={<Calendar />} label="تاريخ آخر شراء" value={formatDateValue(selectedItem.lastPurchaseDate)} />
                </div>
                
                {selectedItem.item.specifications && (
                    <div className="mt-2">
                        <span className="text-xs ktra-text-soft block mb-1">المواصفات</span>
                        <p className="text-sm ktra-bg-panel dark:ktra-bg-panel p-2 rounded">{selectedItem.item.specifications}</p>
                    </div>
                )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const DetailItem = ({ icon, label, value }: any) => (
  <div>
    <span className="text-xs ktra-text-soft flex items-center gap-1 mb-1">
      {React.cloneElement(icon, { className: "w-3 h-3" })} {label}
    </span>
    <span className="text-sm font-medium ktra-text-ink dark:text-white">
      {value}
    </span>
  </div>
);