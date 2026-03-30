
import React from 'react';
import { AppView } from '../../types';
import { PlusCircle, FileText, Users, ShoppingCart, Truck } from 'lucide-react';

interface QuickActionsProps {
    onNavigate: (view: AppView) => void;
    userRole: string;
}

export const QuickActions: React.FC<QuickActionsProps> = ({ onNavigate, userRole }) => {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">إجراءات سريعة</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <button
                    onClick={() => onNavigate('tasks')}
                    className="flex flex-col items-center justify-center p-4 rounded-xl bg-gray-50 dark:bg-gray-900/50 hover:bg-blue-50 dark:hover:bg-blue-900/20 border border-gray-200 dark:border-gray-700 transition-all group"
                >
                    <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 mb-3 group-hover:scale-110 transition-transform">
                        <PlusCircle className="w-6 h-6" />
                    </div>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">مهمة جديدة</span>
                </button>

                {(userRole === 'manager' || userRole === 'procurement') && (
                    <>
                        <button
                            onClick={() => onNavigate('purchase-invoices')}
                            className="flex flex-col items-center justify-center p-4 rounded-xl bg-gray-50 dark:bg-gray-900/50 hover:bg-purple-50 dark:hover:bg-purple-900/20 border border-gray-200 dark:border-gray-700 transition-all group"
                        >
                            <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 mb-3 group-hover:scale-110 transition-transform">
                                <FileText className="w-6 h-6" />
                            </div>
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">فاتورة شراء</span>
                        </button>

                        <button
                            onClick={() => onNavigate('deals-management')}
                            className="flex flex-col items-center justify-center p-4 rounded-xl bg-gray-50 dark:bg-gray-900/50 hover:bg-green-50 dark:hover:bg-green-900/20 border border-gray-200 dark:border-gray-700 transition-all group"
                        >
                            <div className="p-3 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 mb-3 group-hover:scale-110 transition-transform">
                                <ShoppingCart className="w-6 h-6" />
                            </div>
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">صفقة جديدة</span>
                        </button>
                    </>
                )}

                <button
                    onClick={() => onNavigate('shipments-management')}
                    className="flex flex-col items-center justify-center p-4 rounded-xl bg-gray-50 dark:bg-gray-900/50 hover:bg-orange-50 dark:hover:bg-orange-900/20 border border-gray-200 dark:border-gray-700 transition-all group"
                >
                    <div className="p-3 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 mb-3 group-hover:scale-110 transition-transform">
                        <Truck className="w-6 h-6" />
                    </div>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">تتبع الشحنات</span>
                </button>
            </div>
        </div>
    );
};
