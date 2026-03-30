import React, { useState, useEffect } from 'react';
import { Plus, Wallet, ArrowRightLeft } from 'lucide-react';
import { CashBox } from '../../types';
import { cashBoxesService } from '../../services/firestoreService';
import { CreateCashBoxModal } from './modals/CreateCashBoxModal';

interface CashBoxListProps {
    onSelectCashBox: (cashBox: CashBox) => void;
}

export const CashBoxList: React.FC<CashBoxListProps> = ({ onSelectCashBox }) => {
    const [cashBoxes, setCashBoxes] = useState<CashBox[]>([]);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const unsubscribe = cashBoxesService.subscribeToCashBoxes((data) => {
            setCashBoxes(data);
            setLoading(false);
        });
        return () => unsubscribe();
    }, []);

    if (loading) {
        return <div className="flex justify-center items-center h-64">Loading...</div>;
    }

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold dark:text-white">صناديق الكاش</h1>
                    <p className="text-gray-500 dark:text-gray-400">إدارة الصناديق وحركة الأموال</p>
                </div>
                <button
                    onClick={() => setIsCreateModalOpen(true)}
                    className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                >
                    <Plus className="w-5 h-5 ml-2" />
                    صندوق جديد
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {cashBoxes.map((box) => (
                    <div
                        key={box.id}
                        className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 hover:shadow-md transition cursor-pointer"
                        onClick={() => onSelectCashBox(box)}
                    >
                        <div className="flex justify-between items-start mb-4">
                            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                                <Wallet className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                            </div>
                            <span className={`px-2 py-1 text-xs font-semibold rounded-full 
                ${box.currency === 'USD' ? 'bg-green-100 text-green-800' :
                                    box.currency === 'ILS' ? 'bg-blue-100 text-blue-800' : 'bg-purple-100 text-purple-800'}`}>
                                {box.currency}
                            </span>
                        </div>

                        <h3 className="text-lg font-bold dark:text-white mb-1">{box.name}</h3>
                        <p className="text-sm text-gray-500 mb-4">تم الإنشاء: {new Date(box.createdAt).toLocaleDateString('ar-EG')}</p>

                        <div className="flex justify-between items-end border-t border-gray-100 dark:border-gray-700 pt-4">
                            <div>
                                <p className="text-xs text-gray-400 mb-1">الرصيد الحالي</p>
                                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                                    {box.currentBalance.toLocaleString()} <span className="text-sm font-normal text-gray-500">{box.currency}</span>
                                </p>
                            </div>
                            <div className="text-blue-600 hover:text-blue-700 text-sm font-medium flex items-center">
                                كشف حساب <ArrowRightLeft className="w-4 h-4 mr-1" />
                            </div>
                        </div>
                    </div>
                ))}

                {cashBoxes.length === 0 && (
                    <div className="col-span-full flex flex-col items-center justify-center p-12 text-gray-400 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl">
                        <Wallet className="w-12 h-12 mb-4 opacity-50" />
                        <p>لا توجد صناديق كاش حالياً</p>
                        <button
                            onClick={() => setIsCreateModalOpen(true)}
                            className="mt-4 text-blue-600 font-medium hover:underline"
                        >
                            إنشاء أول صندوق
                        </button>
                    </div>
                )}
            </div>

            <CreateCashBoxModal
                isOpen={isCreateModalOpen}
                onClose={() => setIsCreateModalOpen(false)}
            />
        </div>
    );
};
