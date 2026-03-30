import React from 'react';
import { ShieldCheck, Truck, Anchor, Building2, Gavel, Coins } from 'lucide-react';
import { LocalPayments } from '@/types';

interface NISLocalPaymentsProps {
    data: LocalPayments;
    onUpdate: (field: string, value: any) => void;
    readOnly?: boolean;
}

export const NISLocalPayments: React.FC<NISLocalPaymentsProps> = ({ data, onUpdate, readOnly }) => {
    const fields = [
        { id: 'customsClearanceFees', label: 'المخلص الجمركي', icon: ShieldCheck, color: 'text-blue-500' },
        { id: 'customsDuties', label: 'رسوم الجمارك', icon: Gavel, color: 'text-rose-500' },
        { id: 'portFees', label: 'رسوم الميناء', icon: Anchor, color: 'text-cyan-500' },
        { id: 'internalShippingFees', label: 'شحن داخلي', icon: Truck, color: 'text-amber-500' },
        { id: 'palestinianTaxCustoms', label: 'جمركة الضرائب', icon: Building2, color: 'text-emerald-500' },
    ];

    const handleUpdate = (field: string, val: string) => {
        onUpdate('localPayments', { ...data, [field]: parseFloat(val) || 0 });
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-emerald-100 dark:border-emerald-900/30 overflow-hidden shadow-sm">
            <div className="bg-emerald-50 dark:bg-emerald-900/20 px-4 py-2 border-b border-emerald-100 dark:border-emerald-800/30 flex items-center justify-between">
                <h3 className="text-xs font-bold text-emerald-800 dark:text-emerald-400 flex items-center gap-1.5 font-bold">
                    <Coins className="w-3.5 h-3.5" />
                    المدفوعات المحلية (ILS)
                </h3>
                <span className="text-[10px] text-emerald-600 dark:text-emerald-500 font-medium bg-white dark:bg-emerald-950/50 px-2 py-0.5 rounded-full border border-emerald-200/50">
                    تضاف للإجمالي
                </span>
            </div>

            <div className="p-3 grid grid-cols-2 sm:grid-cols-5 gap-2">
                {fields.map((f) => (
                    <div key={f.id} className="relative group">
                        <div className="absolute top-2 right-2 flex items-center gap-1">
                            <f.icon className={`w-3 h-3 ${f.color}`} />
                            <span className="text-[9px] font-bold text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                {f.label}
                            </span>
                        </div>
                        <input
                            type="number"
                            value={(data[f.id as keyof LocalPayments] as number) || ''}
                            onChange={(e) => handleUpdate(f.id, e.target.value)}
                            disabled={readOnly}
                            className="w-full pt-6 pb-1.5 px-2 text-sm font-black text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 rounded-xl focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 transition-all outline-none text-center"
                            placeholder="0"
                        />
                    </div>
                ))}
            </div>
        </div>
    );
};
