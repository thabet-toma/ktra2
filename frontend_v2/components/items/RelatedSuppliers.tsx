import React, { useState } from 'react';
import { Supplier, Item } from '../../types';
import { Building, Phone, ArrowRight, ShoppingCart, X, Mail, MapPin, Hash, Wallet, Globe } from 'lucide-react';

interface RelatedSuppliersProps {
  item: Item;
  data: { supplier: Supplier, lastPurchaseDate: string, totalQuantity: number }[];
  onBack: () => void;
}

export const RelatedSuppliers: React.FC<RelatedSuppliersProps> = ({ item, data, onBack }) => {
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4 border-b border-gray-200 dark:border-gray-700 pb-4">
        <button onClick={onBack} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors">
          <ArrowRight className="w-6 h-6 text-gray-500" />
        </button>
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">موردو الصنف</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">للصنف: {item.name}</p>
        </div>
      </div>

      {/* Table View */}
      <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg">
        <table className="w-full text-right text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/50 text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="px-6 py-4 w-16">#</th>
              <th className="px-6 py-4">اسم المورد</th>
              <th className="px-6 py-4">رقم المورد</th>
              <th className="px-6 py-4">معلومات الاتصال</th>
              <th className="px-6 py-4">الكمية المشتراة</th>
              <th className="px-6 py-4">آخر شراء</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
            {data.map(({ supplier, lastPurchaseDate, totalQuantity }, index) => (
              <tr 
                key={supplier.id} 
                onClick={() => setSelectedSupplier(supplier)}
                className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors cursor-pointer group"
              >
                <td className="px-6 py-4 text-gray-500">{index + 1}</td>
                <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                  <div className="flex items-center gap-2">
                    <Building className="w-4 h-4 text-blue-500" />
                    {supplier.tradeName}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-1 rounded text-xs font-mono">
                    {supplier.supplierId}
                  </span>
                </td>
                <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                  <div className="flex flex-col gap-1">
                     {supplier.phone && <div className="flex items-center gap-1"><Phone className="w-3 h-3" /> {supplier.phone}</div>}
                     {supplier.email && <div className="flex items-center gap-1"><Mail className="w-3 h-3" /> {supplier.email}</div>}
                  </div>
                </td>
                <td className="px-6 py-4">
                   <span className="font-bold text-gray-900 dark:text-white">{totalQuantity}</span>
                </td>
                <td className="px-6 py-4 text-gray-500 dir-ltr text-right">
                   {new Date(lastPurchaseDate).toLocaleDateString('en-GB')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.length === 0 && (
            <div className="text-center py-12 text-gray-500">
              <ShoppingCart className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>لم يتم شراء هذا الصنف من أي مورد مسجل</p>
            </div>
        )}
      </div>

      {/* Supplier Details Modal */}
      {selectedSupplier && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[70] p-4" onClick={() => setSelectedSupplier(null)}>
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-900/50">
              <h3 className="font-bold text-lg text-gray-900 dark:text-white flex items-center gap-2">
                <Building className="w-5 h-5 text-blue-600" />
                {selectedSupplier.tradeName}
              </h3>
              <button onClick={() => setSelectedSupplier(null)} className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
               <div className="grid grid-cols-2 gap-4">
                  <DetailItem icon={<Hash />} label="رقم المورد" value={selectedSupplier.supplierId} />
                  <DetailItem icon={<Wallet />} label="الرصيد الافتتاحي" value={`${selectedSupplier.openingBalance} ${selectedSupplier.currency}`} />
                  <DetailItem icon={<Phone />} label="الهاتف" value={selectedSupplier.phone || '-'} />
                  <DetailItem icon={<Phone />} label="الجوال" value={selectedSupplier.mobile || '-'} />
                  <DetailItem icon={<Mail />} label="البريد الإلكتروني" value={selectedSupplier.email || '-'} fullWidth />
                  <DetailItem icon={<Globe />} label="البلد/المدينة" value={`${selectedSupplier.country || ''} - ${selectedSupplier.city || ''}`} fullWidth />
                  <DetailItem icon={<MapPin />} label="العنوان" value={selectedSupplier.street || '-'} fullWidth />
               </div>

               {selectedSupplier.notes && (
                 <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
                   <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">ملاحظات:</p>
                   <p className="text-sm text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 p-3 rounded-lg">
                     {selectedSupplier.notes}
                   </p>
                 </div>
               )}
            </div>
            
            <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex justify-end">
              <button onClick={() => setSelectedSupplier(null)} className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:opacity-90">
                إغلاق
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const DetailItem = ({ icon, label, value, fullWidth = false }: any) => (
  <div className={`flex flex-col ${fullWidth ? 'col-span-2' : ''}`}>
    <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1 mb-1">
      {React.cloneElement(icon, { className: "w-3 h-3" })} {label}
    </span>
    <span className="text-sm font-medium text-gray-900 dark:text-white break-words">
      {value}
    </span>
  </div>
);