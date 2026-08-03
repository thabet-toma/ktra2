import React, { useState } from 'react';
import { Invoice, Supplier } from '../../types';
import { FileText, Calendar, ArrowRight, Package, DollarSign, Eye, X, Hash } from 'lucide-react';
import { formatDateValue } from "../../utils/formatDate";

interface SupplierRelatedInvoicesProps {
  supplier: Supplier;
  invoices: Invoice[];
  onBack: () => void;
}

export const SupplierRelatedInvoices: React.FC<SupplierRelatedInvoicesProps> = ({ supplier, invoices, onBack }) => {
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  return (
    <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-sm p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4 border-b aseel-border-soft dark:aseel-border-soft pb-4">
        <button onClick={onBack} className="p-2 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-full transition-colors">
          <ArrowRight className="w-6 h-6 aseel-text-soft" />
        </button>
        <div>
          <h2 className="text-xl font-bold aseel-text-ink dark:text-white">سجل فواتير المورد</h2>
          <p className="text-sm aseel-text-soft dark:aseel-text-soft">للمورد: {supplier.tradeName}</p>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border aseel-border-soft dark:aseel-border-soft rounded-lg">
        <table className="w-full text-right text-sm">
          <thead className="aseel-bg-panel dark:aseel-bg-panel/50 aseel-text-ink dark:aseel-text-soft border-b aseel-border-soft dark:aseel-border-soft">
            <tr>
              <th className="px-6 py-4 w-16">#</th>
              <th className="px-6 py-4">رقم الفاتورة</th>
              <th className="px-6 py-4">الرقم التسلسلي</th>
              <th className="px-6 py-4">تاريخ الفاتورة</th>
              <th className="px-6 py-4">عدد البنود</th>
              <th className="px-6 py-4">الحالة</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {invoices.map((inv, index) => (
              <tr 
                key={inv.id} 
                onClick={() => setSelectedInvoice(inv)}
                className="hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 cursor-pointer transition-colors"
              >
                <td className="px-6 py-4 aseel-text-soft">{index + 1}</td>
                <td className="px-6 py-4 font-medium flex items-center gap-2 aseel-text-ink dark:text-white">
                  <FileText className="w-4 h-4 aseel-text-soft" />
                  {inv.invoiceNumber}
                </td>
                <td className="px-6 py-4 font-mono text-xs aseel-text-soft">
                   {inv.serialNumber || '-'}
                </td>
                <td className="px-6 py-4 aseel-text-soft">
                  <div className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {formatDateValue(inv.createdAt)}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className="aseel-bg-accent-bg aseel-text-accent px-2 py-1 rounded-lg text-xs font-bold">
                     {inv.items.length}
                  </span>
                </td>
                <td className="px-6 py-4">
                   <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      inv.status === 'completed' ? 'bg-green-100 text-green-700' : 
                      inv.status === 'deposit_paid' ? 'aseel-bg-panel aseel-text-ink' : 'aseel-bg-panel aseel-text-ink'
                   }`}>
                      {inv.status === 'completed' ? 'مكتملة' : inv.status === 'deposit_paid' ? 'مدفوع عربون' : 'غير مكتملة'}
                   </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {invoices.length === 0 && (
          <div className="text-center py-12 aseel-text-soft">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا توجد فواتير مسجلة لهذا المورد</p>
          </div>
        )}
      </div>

      {/* Invoice Details Modal */}
      {selectedInvoice && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[70] p-4" onClick={() => setSelectedInvoice(null)}>
          <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-xl w-full max-w-2xl overflow-hidden max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center aseel-bg-panel dark:aseel-bg-panel/50">
              <h3 className="font-bold text-lg aseel-text-ink dark:text-white flex items-center gap-2">
                تفاصيل الفاتورة: {selectedInvoice.invoiceNumber}
              </h3>
              <button onClick={() => setSelectedInvoice(null)}><X className="w-5 h-5 aseel-text-soft" /></button>
            </div>
            
            <div className="p-6 overflow-y-auto space-y-6">
                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span className="aseel-text-soft block">تاريخ الإنشاء</span>
                        <span className="font-medium aseel-text-ink dark:text-white">{new Date(selectedInvoice.createdAt).toLocaleString('ar-EG')}</span>
                    </div>
                    <div>
                        <span className="aseel-text-soft block">الوزن الكلي</span>
                        <span className="font-medium aseel-text-ink dark:text-white">{selectedInvoice.totalWeight || 0} كجم</span>
                    </div>
                    <div>
                        <span className="aseel-text-soft block">الحجم الكلي</span>
                        <span className="font-medium aseel-text-ink dark:text-white">{selectedInvoice.totalVolume || 0} م³</span>
                    </div>
                </div>

                <div>
                    <h4 className="font-bold aseel-text-ink dark:text-white mb-2 border-b pb-1">البنود</h4>
                    <div className="aseel-bg-panel dark:aseel-bg-panel rounded-lg p-2">
                        {selectedInvoice.items.map((item, idx) => (
                            <div key={idx} className="flex justify-between items-center p-2 border-b aseel-border-soft dark:aseel-border-soft last:border-0 text-sm">
                                <div>
                                    <p className="font-medium aseel-text-ink dark:text-white">{item.name}</p>
                                    <p className="text-xs aseel-text-soft">{item.categoryName}</p>
                                </div>
                                <div className="text-left">
                                    <p className="font-bold aseel-text-ink dark:text-white">{item.quantity} × {item.unitPrice} $</p>
                                    <p className="text-xs text-green-600 font-bold">= {item.totalPrice} $</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};