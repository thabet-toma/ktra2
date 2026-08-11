import React, { useState } from 'react';
import { X } from 'lucide-react';
import { cashBoxesService } from '../../../services/firestoreService';
import { accountingApi } from '../../../services/accountingApi';
import { Currency } from '../../../types';

interface CreateCashBoxModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const CreateCashBoxModal: React.FC<CreateCashBoxModalProps> = ({ isOpen, onClose }) => {
    const [name, setName] = useState('');
    const [currency, setCurrency] = useState<Currency>('USD');
    const [isLoading, setIsLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!name) return;

        setIsLoading(true);
        try {
            const boxId = await cashBoxesService.createCashBox({
                name,
                currency,
                createdBy: 'manager', // TODO: Get actual user ID
            });
            try {
                await accountingApi.registerCashBoxLedger({
                    external_id: boxId,
                    name,
                    currency_code: currency,
                });
                alert(
                    "✅ تم إنشاء الصندوق.\n\nفي المحاسبة: وُلد له تلقائياً حساب في شجرة الحسابات بنفس اسم الصندوق (تحت مجموعة النقدية)، ويُستخدم في قيود الدفع."
                );
            } catch (glErr) {
                console.warn("Cash box GL link failed:", glErr);
                const m = glErr instanceof Error ? glErr.message : String(glErr);
                alert(
                    "تم إنشاء الصندوق فقط.\n\nلم يُنشأ حسابه في الشجرة بعد:\n" +
                        m +
                        "\n\nافتح «تعديل» على هذا الصندوق واضغط «إنشاء حساب في الشجرة»، أو تأكد من وجود حساب أب للصناديق (مثل 1110) وتسجيل الدخول للـ API."
                );
            }
            onClose();
            setName('');
            setCurrency('USD');
        } catch (error) {
            // console suppressed
            alert("حدث خطأ أثناء إنشاء الصندوق");
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
                            <option value="USD">USD - دولار أمريكي</option>
                            <option value="ILS">ILS - شيكل إسرائيلي</option>
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
