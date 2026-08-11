
import React from 'react';
import { AppView } from '../../types';
import { PlusCircle, FileText, Users, ShoppingCart, Truck } from 'lucide-react';

interface QuickActionsProps {
    onNavigate: (view: AppView, targetId?: string) => void;
    userRole: string;
}

export const QuickActions: React.FC<QuickActionsProps> = ({ onNavigate, userRole }) => {
    return (
        <div className="bg-[var(--color-surface)] rounded-2xl shadow-sm border border-[var(--color-border)] p-6">
            <h3 className="text-lg font-bold text-[var(--color-text)] mb-4">إجراءات سريعة</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <button
                    onClick={() => onNavigate('tasks')}
                    className="flex flex-col items-center justify-center p-4 rounded-xl bg-[var(--color-surface-2)] hover:bg-blue-50 dark:hover:bg-blue-900/20 border border-[var(--color-border)] transition-all group"
                >
                    <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 mb-3 group-hover:scale-110 transition-transform">
                        <PlusCircle className="w-6 h-6" />
                    </div>
                    <span className="text-sm font-medium text-[var(--color-text)]">مهمة جديدة</span>
                </button>

                {(userRole === 'manager' || userRole === 'procurement') && (
                    <>
                        <button
                            onClick={() => onNavigate('purchase-invoices')}
                            className="flex flex-col items-center justify-center p-4 rounded-xl bg-[var(--color-surface-2)] hover:bg-[var(--color-primary-hover)] dark:hover:bg-[var(--color-primary-hover)]/20 border border-[var(--color-border)] transition-all group"
                        >
                            <div className="p-3 rounded-full bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] mb-3 group-hover:scale-110 transition-transform">
                                <FileText className="w-6 h-6" />
                            </div>
                            <span className="text-sm font-medium text-[var(--color-text)]">فاتورة شراء</span>
                        </button>

                        <button
                            onClick={() => onNavigate('deals-management')}
                            className="flex flex-col items-center justify-center p-4 rounded-xl bg-[var(--color-surface-2)] hover:bg-green-50 dark:hover:bg-green-900/20 border border-[var(--color-border)] transition-all group"
                        >
                            <div className="p-3 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 mb-3 group-hover:scale-110 transition-transform">
                                <ShoppingCart className="w-6 h-6" />
                            </div>
                            <span className="text-sm font-medium text-[var(--color-text)]">صفقة جديدة</span>
                        </button>
                    </>
                )}

                <button
                    onClick={() => onNavigate('shipments-management')}
                    className="flex flex-col items-center justify-center p-4 rounded-xl bg-[var(--color-surface-2)] hover:bg-orange-50 dark:hover:bg-orange-900/20 border border-[var(--color-border)] transition-all group"
                >
                    <div className="p-3 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 mb-3 group-hover:scale-110 transition-transform">
                        <Truck className="w-6 h-6" />
                    </div>
                    <span className="text-sm font-medium text-[var(--color-text)]">تتبع الشحنات</span>
                </button>
            </div>
        </div>
    );
};
