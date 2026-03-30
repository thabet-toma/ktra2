import React from 'react';
import { Invoice, Item } from '../../types';
import { FileText, Calendar, ArrowRight, Package } from 'lucide-react';

interface RelatedInvoicesProps {
  item: Item;
  invoices: Invoice[];
  onBack: () => void;
}

export const RelatedInvoices: React.FC<RelatedInvoicesProps> = ({ item, invoices, onBack }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 space-y-6">
      <div className="flex items-center gap-4 border-b border-gray-200 dark:border-gray-700 pb-4">
        <button onClick={onBack} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors">
          <ArrowRight className="w-6 h-6 text-gray-500" />
        </button>
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">سجل فواتير الشراء</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">للصنف: {item.name}</p>
        </div>
      </div>

      <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg">
        <table className="w-full text-right text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/50 text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="px-6 py-4 w-16">#</th>
              <th className="px-6 py-4">رقم الفاتورة</th>
              <th className="px-6 py-4">المورد / المصنع</th>
              <th className="px-6 py-4">تاريخ الفاتورة</th>
              <th className="px-6 py-4">الكمية المشتراة</th>
              <th className="px-6 py-4">سعر الوحدة</th>
              <th className="px-6 py-4">الإجمالي</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
            {invoices.map((inv, index) => {
              const invoiceItem = inv.items.find(i => i.itemId === item.id);
              return (
                <tr key={inv.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="px-6 py-4 text-gray-500">{index + 1}</td>
                  <td className="px-6 py-4 font-medium flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-500" />
                    {inv.invoiceNumber}
                  </td>
                  <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                    {inv.factoryName || 'مورد غير محدد'}
                  </td>
                  <td className="px-6 py-4 text-gray-500">
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {new Date(inv.createdAt).toLocaleDateString('en-GB')}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="bg-blue-50 text-blue-700 px-2 py-1 rounded-lg text-xs font-bold">
                       {invoiceItem?.quantity}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                     {invoiceItem?.unitPrice} $
                  </td>
                  <td className="px-6 py-4 font-bold">
                     {invoiceItem?.totalPrice.toLocaleString()} $
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {invoices.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا توجد فواتير شراء لهذا الصنف</p>
          </div>
        )}
      </div>
    </div>
  );
};