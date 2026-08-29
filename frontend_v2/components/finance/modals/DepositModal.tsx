import React, { useEffect, useState } from 'react';
import { X, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { accountingApi } from '../../../services/accountingApi';
import { CashBox } from '../../../types';
import { useToast } from '../../../contexts/ToastContext';
import { humanizeThrown } from '../../../utils/drfError';

interface DepositModalProps {
    isOpen: boolean;
    onClose: () => void;
    cashBox: CashBox;
    /** معرّف الصندوق الخادمي — الحركة تُفتاح به لا بمعرّف المرآة. */
    cashBoxLedgerId: number | null;
    /** `in` إيداع · `out` سحب — نمط Odoo «Put money in / Take money out». */
    direction?: 'in' | 'out';
    /** بعد نجاح الحركة، لإعادة تحميل الكشف. */
    onDepositComplete?: () => void;
}

export const DepositModal: React.FC<DepositModalProps> = ({
    isOpen,
    onClose,
    cashBox,
    cashBoxLedgerId,
    direction = 'in',
    onDepositComplete,
}) => {
    const [amount, setAmount] = useState<number | ''>('');
    const [description, setDescription] = useState('');
    const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
    const [isLoading, setIsLoading] = useState(false);
    const toast = useToast();
    const [formError, setFormError] = useState<string | null>(null);

    // النوع مثبَّت صراحةً: `React.FC` هنا غير مفحوص (لا `@types/react` في
    // المشروع)، فالقيمة الافتراضية تتّسع إلى `string` وتسقط عند حدّ الـAPI.
    const dir: 'in' | 'out' = direction === 'out' ? 'out' : 'in';
    const isDeposit = dir === 'in';
    const actionLabel = isDeposit ? 'إيداع' : 'سحب';

    // المكوّن يبقى محمَّلاً بعد الإغلاق (`isOpen` + `return null`)، فحالته تعيش
    // بين فتحة وأخرى — التصفير عند كل فتح يمنع تسرّب مدخلات حركةٍ سابقة.
    useEffect(() => {
        if (!isOpen) return;
        setFormError(null);
        setAmount('');
        setDescription('');
        setDate(new Date().toISOString().split('T')[0]);
    }, [isOpen]);

    if (!isOpen) return null;

    /** T-CASHBOX M6: نداءٌ واحد — الحركة **هي** القيد.
     *
     * كانت خطوتين (حفظٌ في المرآة ثم قيد رأس المال) بلا معاملة تجمعهما، وسقوط
     * الثاني يترك نقداً في الصندوق بلا قيد: دفاترُ ناقصة وتحذيرٌ يطلب من
     * المستخدم أن يكتب القيد بيده. الصندوق الآن حسابٌ في الأستاذ لا رصيدٌ
     * مخزَّن، فليس هناك ما «يُحفظ» خارج القيد أصلاً.
     */
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!amount || amount <= 0 || !description) return;
        if (!cashBoxLedgerId) {
            setFormError('هذا الصندوق بلا حساب في الشجرة — شغّل أمر backfill_cash_boxes أولاً.');
            return;
        }

        setIsLoading(true);
        setFormError(null);
        try {
            await accountingApi.adjustCashBox(cashBoxLedgerId, {
                direction: dir,
                amount: Number(amount),
                date,
                memo: description.trim(),
            });
            toast(`تم تسجيل ال${actionLabel} وقيده في المحاسبة.`, 'success');
            onDepositComplete?.();
            onClose();
        } catch (error) {
            setFormError(humanizeThrown(error, `تعذّر تنفيذ ال${actionLabel}`));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-[var(--color-surface)] rounded-lg p-6 w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold dark:text-white flex items-center">
                        {isDeposit ? (
                            <ArrowDownLeft className="w-5 h-5 ml-2 text-green-600" />
                        ) : (
                            <ArrowUpRight className="w-5 h-5 ml-2 text-red-600" />
                        )}
                        {actionLabel} جديد - {cashBox.name}
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
                            disabled={isLoading}
                            className={`px-4 py-2 text-white rounded-md disabled:opacity-50 ${
                                isDeposit
                                    ? 'bg-green-600 hover:bg-green-700'
                                    : 'bg-red-600 hover:bg-red-700'
                            }`}
                        >
                            {isLoading ? 'جاري التنفيذ...' : `تأكيد ال${actionLabel}`}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
