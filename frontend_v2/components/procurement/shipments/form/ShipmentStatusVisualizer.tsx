import React from 'react';
import {
    Building2, Ship, Anchor, ArrowRight, CheckCircle2,
    Box, Plane, Truck, FileText, Warehouse
} from 'lucide-react';

interface ShipmentStatusVisualizerProps {
    type: 'sea' | 'air';
    currentStatus: string;
}

export const ShipmentStatusVisualizer: React.FC<ShipmentStatusVisualizerProps> = ({ type, currentStatus }) => {

    // تعريف الخطوات بناءً على الكود الخاص بك
    const seaSteps = [
        { id: 'agent_warehouse', label: 'مستودع الوكيل', icon: Warehouse },
        { id: 'china_customs_clearance', label: 'جمارك الصين', icon: FileText },
        { id: 'on_board', label: 'على السفينة', icon: Ship },
        { id: 'at_sea', label: 'في البحر', icon: Anchor },
        { id: 'arrived_port', label: 'وصلت الميناء', icon: ArrowRight },
        { id: 'israel_customs_clearance', label: 'جمارك إسرائيل', icon: FileText },
        { id: 'released', label: 'مفرج عنها', icon: CheckCircle2 },
        { id: 'delivered_local', label: 'تم التسليم محليا', icon: Box },
    ];

    const airSteps = [
        { id: 'agent_warehouse', label: 'مستودع الوكيل', icon: Warehouse },
        { id: 'delivered_to_shipping_company', label: 'شركة الشحن', icon: Building2 },
        { id: 'china_customs_clearance', label: 'جمارك الصين', icon: FileText },
        { id: 'departed', label: 'انطلقت', icon: Plane },
        { id: 'in_transit', label: 'في الطريق', icon: Truck },
        { id: 'arrived_airport', label: 'وصلت المطار', icon: ArrowRight },
        { id: 'israel_customs_clearance', label: 'جمارك إسرائيل', icon: FileText },
        { id: 'released', label: 'مفرج عنها', icon: CheckCircle2 },
        { id: 'delivered_local', label: 'تم التسليم', icon: Box },
    ];

    const steps = type === 'sea' ? seaSteps : airSteps;

    // تحديد موقع الحالة الحالية
    const currentIndex = steps.findIndex(s => s.id === currentStatus);
    const activeIndex = currentIndex === -1 ? 0 : currentIndex;

    // حساب نسبة التقدم للشريط الملون
    // (activeIndex / (steps.length - 1)) * 100
    const progressPercent = Math.min(100, Math.max(0, (activeIndex / (steps.length - 1)) * 100));

    return (
        <div className="w-full py-6 px-4 overflow-x-auto">
            <div className="relative min-w-[700px]">

                {/* خط الخلفية الرمادي */}
                <div className="absolute top-1/2 left-0 right-0 h-1 aseel-bg-grid-head dark:aseel-bg-panel -translate-y-1/2 rounded-full z-0"></div>

                {/* خط التقدم الملون */}
                <div
                    className="absolute top-1/2 h-1 aseel-bg-accent -translate-y-1/2 rounded-full z-0 transition-all duration-700 ease-out"
                    style={{
                        right: 0, // RTL
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
                                        w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-300 relative aseel-bg-field dark:aseel-bg-panel
                                        ${isCurrent
                                            ? 'aseel-border-accent aseel-text-accent scale-110 shadow-lg ring-4 ring-blue-50 dark:ring-blue-900/30 z-20'
                                            : isCompleted
                                                ? 'aseel-border-accent aseel-text-accent'
                                                : 'aseel-border-soft aseel-text-soft dark:aseel-border-soft'
                                        }
                                    `}
                                >
                                    <Icon className="w-5 h-5" />
                                </div>

                                {/* النص */}
                                <div className={`
                                    absolute top-12 text-[10px] font-bold text-center w-20 transition-all
                                    ${isCurrent
                                        ? 'aseel-text-accent dark:aseel-text-soft scale-110'
                                        : isCompleted
                                            ? 'aseel-text-ink dark:aseel-text-soft'
                                            : 'aseel-text-soft dark:aseel-text-soft'
                                    }
                                `}>
                                    {step.label}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
            {/* مساحة فارغة في الأسفل للنصوص */}
            <div className="h-8"></div>
        </div>
    );
};