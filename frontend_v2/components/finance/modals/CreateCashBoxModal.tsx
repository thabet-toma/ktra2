import React, { useState } from 'react';
import { X } from 'lucide-react';
import { cashBoxesService } from '../../../services/firestoreService';
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
            await cashBoxesService.createCashBox({
                name,
                currency,
                createdBy: 'manager', // TODO: Get actual user ID
            });
            onClose();
            setName('');
            setCurrency('USD');
        } catch (error) {
            console.error("Error creating cash box:", error);
            alert("حدث خطأ أثناء إنشاء الصندوق");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold dark:text-white">إنشاء صندوق كاش جديد</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
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
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
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
                            className="mr-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md dark:text-gray-300 dark:hover:bg-gray-700"
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
