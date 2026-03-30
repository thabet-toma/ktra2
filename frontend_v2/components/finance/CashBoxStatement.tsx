import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  ArrowDownLeft,
  ArrowUpRight,
  Ban,
} from 'lucide-react';
import { CashBox, CashBoxTransaction } from '../../types';
import { cashBoxTransactionsService } from '../../services/firestoreService';
import { DepositModal } from './modals/DepositModal';

interface CashBoxStatementProps {
  cashBox: CashBox;
  onBack: () => void;
}

/* =========================
   Helpers
========================= */

const formatDate = (dateString: string) => {
  const date = new Date(dateString);

  const dayName = date.toLocaleDateString('ar-EG', { weekday: 'long' });
  const datePart = date.toLocaleDateString('en-GB');
  const timePart = date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  });

  return { dayName, datePart, timePart };
};

export const CashBoxStatement: React.FC<CashBoxStatementProps> = ({
  cashBox,
  onBack,
}) => {
  const [transactions, setTransactions] = useState<CashBoxTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);

  useEffect(() => {
    const unsubscribe =
      cashBoxTransactionsService.subscribeToTransactions(
        cashBox.id,
        (data) => {
          setTransactions(data);
          setLoading(false);
        }
      );

    return () => unsubscribe();
  }, [cashBox.id]);

  const getTransactionIcon = (type: string) => {
    switch (type) {
      case 'deposit':
        return <ArrowDownLeft className="w-5 h-5 text-green-600" />;
      case 'withdrawal':
        return <ArrowUpRight className="w-5 h-5 text-red-600" />;
      default:
        return <Ban className="w-5 h-5 text-gray-500" />;
    }
  };

  const getTransactionLabel = (type: string) => {
    switch (type) {
      case 'deposit':
        return 'إيداع';
      case 'withdrawal':
        return 'سحب';
      case 'adjustment':
        return 'تسوية';
      default:
        return type;
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* ================= Header ================= */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center">
          <button
            onClick={onBack}
            className="p-2 ml-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition"
          >
            <ArrowLeft className="w-6 h-6 dark:text-white" />
          </button>

          <div>
            <h1 className="text-2xl font-bold dark:text-white">
              {cashBox.name}
            </h1>
            <p className="text-sm text-gray-500">كشف حساب الصندوق</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-left">
            <p className="text-xs text-gray-500">الرصيد الحالي</p>
            <p className="text-2xl font-bold text-blue-600">
              {cashBox.currentBalance.toLocaleString()}
              <span className="text-sm mr-1">
                {cashBox.currency}
              </span>
            </p>
          </div>

          <button
            onClick={() => setIsDepositModalOpen(true)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition flex items-center"
          >
            <ArrowDownLeft className="w-4 h-4 ml-2" />
            إيداع
          </button>
        </div>
      </div>

      {/* ================= Table ================= */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-right text-sm">
            <thead className="bg-gray-100 dark:bg-gray-900 text-gray-600 dark:text-gray-400 text-xs uppercase">
              <tr>
                <th className="px-4 py-3">التاريخ</th>
                <th className="px-4 py-3">النوع</th>
                <th className="px-6 py-3">الوصف</th>
                <th className="px-4 py-3">المرجع</th>
                <th className="px-4 py-3">دائن / مدين</th>
                <th className="px-4 py-3">الرصيد</th>
                <th className="px-4 py-3">بواسطة</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {loading ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-10 text-center text-gray-500"
                  >
                    جاري التحميل...
                  </td>
                </tr>
              ) : transactions.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-10 text-center text-gray-500"
                  >
                    لا توجد حركات حتى الآن
                  </td>
                </tr>
              ) : (
                transactions.map((tx) => {
                  const { dayName, datePart, timePart } =
                    formatDate(tx.date);

                  return (
                    <tr
                      key={tx.id}
                      className="hover:bg-blue-50 dark:hover:bg-gray-700/40 transition"
                    >
                      {/* Date */}
                      <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                        <div className="flex flex-col leading-tight">
                          <span className="font-semibold">
                            {dayName}
                          </span>
                          <span className="text-xs">
                            {datePart}
                          </span>
                          <span className="text-xs text-gray-400">
                            {timePart}
                          </span>
                        </div>
                      </td>

                      {/* Type */}
                      <td className="px-4 py-3">
                        <div className="flex items-center">
                          <div
                            className={`p-1.5 rounded-full ml-2
                              ${
                                tx.type === 'deposit'
                                  ? 'bg-green-100'
                                  : tx.type === 'withdrawal'
                                  ? 'bg-red-100'
                                  : 'bg-gray-100'
                              }`}
                          >
                            {getTransactionIcon(tx.type)}
                          </div>
                          <span className="font-medium">
                            {getTransactionLabel(tx.type)}
                          </span>
                        </div>
                      </td>

                      {/* Description */}
                      <td
                        className="px-6 py-3 max-w-[300px] truncate"
                        title={tx.description}
                      >
                        {tx.description}
                      </td>

                      {/* Reference */}
                      <td
                        className="px-4 py-3 text-xs text-gray-500 font-mono truncate max-w-[140px]"
                        title={tx.reference}
                      >
                        {tx.reference || '-'}
                      </td>

                      {/* Amount */}
                      <td
                        className={`px-4 py-3 font-bold
                          ${
                            tx.type === 'deposit'
                              ? 'text-green-600'
                              : 'text-red-600'
                          }`}
                      >
                        {tx.type === 'deposit' ? '+' : '-'}
                        {tx.amount.toLocaleString()}
                      </td>

                      {/* Balance */}
                      <td className="px-4 py-3 font-bold dark:text-white">
                        {tx.balanceAfter?.toLocaleString() ?? '-'}
                      </td>

                      {/* Created By */}
                      <td
                        className="px-4 py-3 text-xs text-gray-400 truncate max-w-[120px]"
                        title={tx.createdBy}
                      >
                        {tx.createdBy}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ================= Deposit Modal ================= */}
      <DepositModal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
        cashBox={cashBox}
      />
    </div>
  );
};
