import React from 'react';
import {
    Building2, Ship, Anchor, ArrowRight, CheckCircle2,
    Box, Plane, Truck, FileCheck, Warehouse
} from 'lucide-react';

interface ShipmentStatusTimelineProps {
    type: 'sea' | 'air';
    currentStatus: string;
}

export const ShipmentStatusTimeline: React.FC<ShipmentStatusTimelineProps> = ({ type, currentStatus }) => {

    // تعريف الخطوات بناءً على النوع
    const seaSteps = [
        { id: 'agent_warehouse', label: 'مستودع الوكيل', icon: Warehouse },
        { id: 'china_customs_clearance', label: 'جمارك الصين', icon: FileCheck },
        { id: 'on_board', label: 'على السفينة', icon: Ship },
        { id: 'at_sea', label: 'في البحر', icon: Anchor },
        { id: 'arrived_port', label: 'وصلت الميناء', icon: ArrowRight },
        { id: 'israel_customs_clearance', label: 'جمارك إسرائيل', icon: FileCheck },
        { id: 'released', label: 'مفرج عنها', icon: CheckCircle2 },
        { id: 'delivered_local', label: 'تم التسليم', icon: Box },
    ];

    const airSteps = [
        { id: 'agent_warehouse', label: 'مستودع الوكيل', icon: Warehouse },
        { id: 'delivered_to_shipping_company', label: 'شركة الشحن', icon: Building2 },
        { id: 'china_customs_clearance', label: 'جمارك الصين', icon: FileCheck },
        { id: 'departed', label: 'انطلقت', icon: Plane },
        { id: 'in_transit', label: 'في الطريق', icon: Truck }, // أو طائرة ثانية
        { id: 'arrived_airport', label: 'وصلت المطار', icon: ArrowRight },
        { id: 'israel_customs_clearance', label: 'جمارك إسرائيل', icon: FileCheck },
        { id: 'released', label: 'مفرج عنها', icon: CheckCircle2 },
        { id: 'delivered_local', label: 'تم التسليم', icon: Box },
    ];

    const steps = type === 'sea' ? seaSteps : airSteps;

    // تحديد موقع الحالة الحالية
    const currentIndex = steps.findIndex(s => s.id === currentStatus);
    const activeIndex = currentIndex === -1 ? 0 : currentIndex;

    // حساب نسبة التقدم للشريط الخلفي
    const progressPercent = (activeIndex / (steps.length - 1)) * 100;

    return (
        <div className="w-full py-8 px-2 overflow-x-auto">
            <div className="relative min-w-[800px]"> {/* min-w لضمان عدم انضغاط العناصر في الشاشات الصغيرة جداً */}

                {/* خط الخلفية الرمادي */}
                <div className="absolute top-1/2 left-0 right-0 h-1.5 bg-gray-200 dark:bg-gray-700 -translate-y-1/2 rounded-full z-0"></div>

                {/* خط التقدم الملون */}
                <div
                    className="absolute top-1/2 h-1.5 bg-gradient-to-l from-blue-500 to-green-500 -translate-y-1/2 rounded-full z-0 transition-all duration-700 ease-out"
                    style={{
                        right: 0, // لأننا في وضع RTL
                        width: `${progressPercent}%`
                    }}
                ></div>

                {/* الخطوات */}
                <div className="relative z-10 flex justify-between w-full">
                    {steps.map((step, index) => {
                        const isCompleted = index <= activeIndex;
                        const isCurrent = index === activeIndex;
                        const Icon = step.icon;

                        return (
                            <div key={step.id} className="flex flex-col items-center group">
                                {/* الدائرة والأيقونة */}
                                <div
                                    className={`
                                        w-12 h-12 rounded-full flex items-center justify-center border-4 transition-all duration-300 relative
                                        ${isCurrent
                                            ? 'bg-blue-600 border-blue-100 dark:border-blue-900 text-white scale-125 shadow-lg shadow-blue-500/30'
                                            : isCompleted
                                                ? 'bg-green-500 border-white dark:border-gray-800 text-white shadow-md'
                                                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 text-gray-400'
                                        }
                                    `}
                                >
                                    <Icon className={`w-5 h-5 ${isCurrent ? 'animate-pulse' : ''}`} />

                                    {/* تأثير النبض للحالة الحالية */}
                                    {isCurrent && (
                                        <span className="absolute inset-0 rounded-full border-2 border-blue-500 animate-ping opacity-75"></span>
                                    )}
                                </div>

                                {/* النص */}
                                <div className={`
                                    mt-4 text-xs font-bold text-center w-24 px-1 py-1 rounded-lg transition-all
                                    ${isCurrent
                                        ? 'text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 scale-110'
                                        : isCompleted
                                            ? 'text-green-700 dark:text-green-400'
                                            : 'text-gray-400 dark:text-gray-500'
                                    }
                                `}>
                                    {step.label}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};