import React, { useState } from 'react';
import { X, ArrowDownLeft } from 'lucide-react';
import { cashBoxTransactionsService } from '../../../services/firestoreService';
import { accountingApi } from '../../../services/accountingApi';
import { CashBox } from '../../../types';

interface DepositModalProps {
    isOpen: boolean;
    onClose: () => void;
    cashBox: CashBox;
    /** بعد نجاح الإيداع وقيد رأس المال (أو إن فشل القيد فقط بعد حفظ الصندوق) */
    onDepositComplete?: () => void;
}

export const DepositModal: React.FC<DepositModalProps> = ({
    isOpen,
    onClose,
    cashBox,
    onDepositComplete,
}) => {
    const [amount, setAmount] = useState<number | ''>('');
    const [description, setDescription] = useState('');
    const [reference, setReference] = useState('');
    const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
    const [isLoading, setIsLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!amount || amount <= 0 || !description) return;

        setIsLoading(true);
        try {
            const txId = await cashBoxTransactionsService.addTransaction({
                cashBoxId: cashBox.id,
                type: 'deposit',
                amount: Number(amount),
                currency: cashBox.currency,
                description,
                reference,
                date,
                createdBy: 'manager', // TODO: Get actual user ID
            });
            try {
                await accountingApi.postCashBoxDepositJournal({
                    external_id: cashBox.id,
                    amount: Number(amount),
                    transaction_date: date,
                    description: description.trim(),
                    firestore_transaction_id: txId,
                });
            } catch (je) {
                // console suppressed
                const msg =
                    je instanceof Error
                        ? je.message
                        : 'تعذّر إنشاء قيد المحاسبة (تحقق من ربط الصندوق وحساب رأس المال والفترة المالية).';
                alert(
                    `تم حفظ الإيداع في الصندوق، لكن فشل قيد رأس المال:\n${msg}\n\nيمكنك إنشاء القيد يدوياً أو إعادة المحاولة بعد إصلاح الإعدادات.`
                );
            }
            onDepositComplete?.();
            onClose();
            // Reset form
            setAmount('');
            setDescription('');
            setReference('');
            setDate(new Date().toISOString().split('T')[0]);
        } catch (error) {
            // console suppressed
            alert("حدث خطأ أثناء عملية الإيداع");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold dark:text-white flex items-center">
                        <ArrowDownLeft className="w-5 h-5 ml-2 text-green-600" />
                        إيداع جديد - {cashBox.name}
                    </h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            المبـلغ ({cashBox.currency})
                        </label>
                        <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={amount}
                            onChange={(e) => setAmount(Number(e.target.value))}
                            className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white font-bold text-lg"
                            placeholder="0.00"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            التاريخ
                        </label>
                        <input
                            type="date"
                            value={date}
                            onChange={(e) => setDate(e.target.value)}
                            className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            الوصف (السبب / الملاحظات)
                        </label>
                        <input
                            type="text"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            placeholder="مثال: رصيد افتتاحي"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            مرجع (اختياري)
                        </label>
                        <input
                            type="text"
                            value={reference}
                            onChange={(e) => setReference(e.target.value)}
                            className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            placeholder="رقم فاتورة، رقم صفقة..."
                        />
                    </div>

                    <div className="flex justify-end pt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="mr-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md dark:text-gray-300 dark:hover:bg-gray-700"
                        >
                            إلغاء
                        </button>
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
                        >
                            {isLoading ? 'جاري التنفيذ...' : 'تأكيد الإيداع'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
