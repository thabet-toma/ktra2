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
    <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm p-6 space-y-6">
      <div className="flex items-center gap-4 border-b aseel-border-soft dark:aseel-border-soft pb-4">
        <button onClick={onBack} className="p-2 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-full transition-colors">
          <ArrowRight className="w-6 h-6 aseel-text-soft" />
        </button>
        <div>
          <h2 className="text-xl font-bold aseel-text-ink dark:text-white">سجل فواتير الشراء</h2>
          <p className="text-sm aseel-text-soft dark:aseel-text-soft">للصنف: {item.name}</p>
        </div>
      </div>

      <div className="overflow-x-auto border aseel-border-soft dark:aseel-border-soft rounded-lg">
        <table className="w-full text-right text-sm">
          <thead className="aseel-bg-panel dark:aseel-bg-panel/50 aseel-text-ink dark:aseel-text-soft border-b aseel-border-soft dark:aseel-border-soft">
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
                <tr key={inv.id} className="hover:aseel-bg-panel dark:hover:aseel-bg-panel/30">
                  <td className="px-6 py-4 aseel-text-soft">{index + 1}</td>
                  <td className="px-6 py-4 font-medium flex items-center gap-2">
                    <FileText className="w-4 h-4 aseel-text-soft" />
                    {inv.invoiceNumber}
                  </td>
                  <td className="px-6 py-4 aseel-text-soft dark:aseel-text-soft">
                    {inv.factoryName || 'مورد غير محدد'}
                  </td>
                  <td className="px-6 py-4 aseel-text-soft">
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {new Date(inv.createdAt).toLocaleDateString('en-GB')}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="aseel-bg-accent-bg aseel-text-accent px-2 py-1 rounded-lg text-xs font-bold">
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
          <div className="text-center py-12 aseel-text-soft">
            <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا توجد فواتير شراء لهذا الصنف</p>
          </div>
        )}
      </div>
    </div>
  );
};