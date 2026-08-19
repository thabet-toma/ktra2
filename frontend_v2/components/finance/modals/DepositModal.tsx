import React, { useEffect, useState } from 'react';
import { X, ArrowDownLeft } from 'lucide-react';
import { cashBoxTransactionsService } from '../../../services/firestoreService';
import { accountingApi } from '../../../services/accountingApi';
import { CashBox } from '../../../types';
import { useToast } from '../../../contexts/ToastContext';
import { humanizeThrown } from '../../../utils/drfError';

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
    const toast = useToast();
    const [formError, setFormError] = useState<string | null>(null);
    const [partialWarning, setPartialWarning] = useState<string | null>(null);

    // المكوّن يبقى محمَّلاً بعد الإغلاق (`isOpen` + `return null`)، فحالته تعيش
    // بين فتحة وأخرى. وبدون هذا التصفير كان تحذيرُ فشلٍ جزئي واحد يقفل زرّ
    // الإرسال **إلى الأبد**: يفتح المستخدم النافذة لإيداع جديد مشروع فيجدها
    // مقفلة تحمل تحذير إيداع قديم، ولا مخرج إلا إعادة تحميل الصفحة.
    useEffect(() => {
        if (!isOpen) return;
        setPartialWarning(null);
        setFormError(null);
        setAmount('');
        setDescription('');
        setReference('');
        setDate(new Date().toISOString().split('T')[0]);
    }, [isOpen]);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!amount || amount <= 0 || !description) return;

        setIsLoading(true);
        setFormError(null);
        setPartialWarning(null);
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
                toast('تم تسجيل الإيداع وقيده في المحاسبة.', 'success');
                onDepositComplete?.();
                onClose();
                setAmount('');
                setDescription('');
                setReference('');
                setDate(new Date().toISOString().split('T')[0]);
            } catch (je) {
                // نجاح جزئي وخطير محاسبياً: النقد دخل الصندوق وقيد رأس المال لم
                // يُسجَّل، فالدفاتر غير متوازنة حتى يتدخّل المستخدم. رسالة عابرة
                // تضيع، فتبقى لافتة ثابتة والنافذة مفتوحة. ولا نصفّر المدخلات كي
                // يُنشئ القيد يدوياً بالأرقام نفسها. الإيداع نفسه محفوظ، فيُقفل
                // زرّ الإرسال منعاً لإيداع مكرّر.
                setPartialWarning(
                    'تم حفظ الإيداع في الصندوق، لكن فشل قيد رأس المال:\n'
                    + humanizeThrown(je, 'تعذّر إنشاء قيد المحاسبة (تحقق من ربط الصندوق وحساب رأس المال والفترة المالية).')
                    + '\n\nالمبلغ في الصندوق ولم يُقيَّد في الدفاتر بعد — أنشئ القيد يدوياً أو أصلح الإعدادات ثم أعد القيد. لا تُعِد الإيداع.'
                );
                onDepositComplete?.();
            }
        } catch (error) {
            // فشل كامل: لا إيداع ولا قيد. المدخلات تبقى ليصحّح ويعيد المحاولة.
            setFormError(humanizeThrown(error, 'تعذّر تنفيذ الإيداع'));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-[var(--color-surface)] rounded-lg p-6 w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold dark:text-white flex items-center">
                        <ArrowDownLeft className="w-5 h-5 ml-2 text-green-600" />
                        إيداع جديد - {cashBox.name}
                    </h2>
                    <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {formError && (
                    <div className="mb-3 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
                        {formError}
                    </div>
                )}
                {partialWarning && (
                    <div className="mb-3 whitespace-pre-line rounded-md border border-amber-300 bg-amber-50 p-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                        {partialWarning}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
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
                        <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
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
                        <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
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
                        <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
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
                            className="mr-2 px-4 py-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] rounded-md"
                        >
                            إلغاء
                        </button>
                        <button
                            type="submit"
                            disabled={isLoading || partialWarning !== null}
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
