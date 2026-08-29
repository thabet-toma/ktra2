import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { accountingApi } from '../../../services/accountingApi';
import { Currency } from '../../../types';
import { useToast } from '../../../contexts/ToastContext';
import { humanizeThrown } from '../../../utils/drfError';

interface CreateCashBoxModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const CreateCashBoxModal: React.FC<CreateCashBoxModalProps> = ({ isOpen, onClose }) => {
    const toast = useToast();
    const [name, setName] = useState('');
    const [currency, setCurrency] = useState<Currency>('ILS');
    const [isLoading, setIsLoading] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);

    useEffect(() => {
        if (!isOpen) return;
        setFormError(null);
        setName('');
        setCurrency('ILS');
    }, [isOpen]);

    if (!isOpen) return null;

    /** T-CASHBOX M2: نداءٌ واحد — الخادم يكتب الصندوق وحسابَه ووثيقة مرآته ذرّياً.
     *
     * كان هنا نداءان (وثيقة الصندوق ثم حسابه في الشجرة) بلا معاملة تجمعهما،
     * فسقوطُ الثاني يترك صندوقاً بلا حساب: مالٌ يتحرّك بلا وجهٍ في الدفاتر.
     * ولذلك كانت الشاشة تحمل حالة «نجاح جزئي» تُقفل الزرّ وتطلب إصلاحاً يدوياً
     * من نافذة التعديل — كلّها سقطت مع سقوط سببها.
     */
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!name) return;

        setIsLoading(true);
        setFormError(null);
        try {
            await accountingApi.createCashBox({ name, currency_code: currency });
            toast(
                "تم إنشاء الصندوق، ووُلد له حساب في شجرة الحسابات بنفس الاسم تحت مجموعة النقدية.",
                'success'
            );
            onClose();
            setName('');
            setCurrency('ILS');
        } catch (error) {
            setFormError(humanizeThrown(error, "تعذّر إنشاء الصندوق"));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-[var(--color-surface)] rounded-lg p-6 w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <div>
                        <h2 className="text-xl font-bold dark:text-white">إنشاء صندوق كاش جديد</h2>
                        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                            يُنشأ الصندوق هنا، ويُنشأ له تلقائياً حساب في شجرة المحاسبة بنفس الاسم (حساب نقدية).
                        </p>
                    </div>
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
                            اسم الصندوق
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            placeholder="مثال: الخزنة الرئيسية (دولار)"
                            required
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
                            العملة
                        </label>
                        <select
                            value={currency}
                            onChange={(e) => setCurrency(e.target.value as Currency)}
                            className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        >
                            <option value="ILS">ILS - شيكل إسرائيلي</option>
                            <option value="USD">USD - دولار أمريكي</option>
                            <option value="JOD">JOD - دينار أردني</option>
                        </select>
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
                            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                        >
                            {isLoading ? 'جاري الإنشاء...' : 'إنشاء الصندوق'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
