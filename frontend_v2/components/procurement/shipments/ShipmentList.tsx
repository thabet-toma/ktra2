import React, { useState } from 'react';
import { Shipment } from '../../../types';
import {
    Truck, Edit, Package, DollarSign, Calendar,
    ExternalLink, Box, Scale, Hash, Ship, Plane,
    Navigation, Anchor, Warehouse, PackageCheck, Clock,
    FileText, User, Layers, TrendingUp, MapPin, Eye
} from 'lucide-react';
import { SupplierViewModal } from '@/components/common/SupplierViewModal';
import { buildShipmentOptionLabelCamel } from '@/utils/shipmentLabel';

interface ShipmentListProps {
    shipments: Shipment[];
    onEdit: (shipment: Shipment) => void;
    onView: (shipment: Shipment) => void;
    onDelete: (shipmentId: string) => void;
    shippingAgents: any[];
}

export const ShipmentList: React.FC<ShipmentListProps> = ({ shipments, onEdit, onView, onDelete, shippingAgents }) => {
    // --- State Management ---
    const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null);
    const [isSupplierModalOpen, setIsSupplierModalOpen] = useState(false);

    // --- Handlers ---
    const handleOpenSupplier = (supplierId: string) => {
        setSelectedSupplierId(supplierId);
        setIsSupplierModalOpen(true);
    };

    const handleCloseSupplier = () => {
        setIsSupplierModalOpen(false);
        setSelectedSupplierId(null);
    };

    // --- Helpers ---
    const getStatusStyle = (status: Shipment['status']) => {
        const baseClass = "px-2 py-1 rounded-full text-[10px] font-medium border flex items-center gap-1 w-fit";
        switch (status) {
            case 'draft': return `${baseClass} bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700`;
            case 'payment_pending': return `${baseClass} bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800`;
            case 'partially_paid': return `${baseClass} bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800`;
            case 'paid': return `${baseClass} bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800`;
            case 'shipped': return `${baseClass} bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)] dark:bg-[var(--color-surface-2)]/20 dark:text-[var(--color-primary)] dark:border-[var(--color-border)]`;
            case 'delivered': return `${baseClass} bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)] dark:bg-[var(--color-surface-2)]/20 dark:text-[var(--color-primary)] dark:border-[var(--color-border)]`;
            case 'cancelled': return `${baseClass} bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800`;
            default: return `${baseClass} bg-gray-50 text-gray-600`;
        }
    };

    const getStatusLabel = (status: Shipment['status']) => {
        switch (status) {
            case 'draft': return 'مسودة';
            case 'payment_pending': return 'بانتظار الدفع';
            case 'partially_paid': return 'مدفوع جزئياً';
            case 'paid': return 'مدفوع بالكامل';
            case 'shipped': return 'تم الشحن';
            case 'delivered': return 'تم التسليم';
            case 'cancelled': return 'ملغاة';
            default: return status;
        }
    };

    /** يطابق عمود Status في SQL (Pending, In-Transit, …) بعد mapShipmentFromSql → lowercase */
    const normalizeLogisticsStatusKey = (raw: string) =>
        raw.toLowerCase().trim().replace(/\s+/g, '-').replace(/_/g, '-');

    const SQL_SHIPMENT_STATUS_AR: Record<string, string> = {
        pending: 'قيد الانتظار',
        'in-transit': 'في الطريق',
        arrived: 'وصلت',
        clearing: 'جاري التخليص الجمركي',
        cleared: 'تم التخليص',
    };

    // دالة لترجمة حالة الشحنة من shippingInfo
    const getShipmentStatusText = (shipment: Shipment) => {
        if (!shipment.shippingInfo?.shipmentStatus?.status) return 'لم تبدأ';

        const statusRaw = shipment.shippingInfo.shipmentStatus.status;
        const coarseKey = normalizeLogisticsStatusKey(statusRaw);
        if (SQL_SHIPMENT_STATUS_AR[coarseKey]) {
            return SQL_SHIPMENT_STATUS_AR[coarseKey];
        }

        const status = statusRaw;
        if (shipment.shippingInfo.shippingType === 'sea') {
            switch (status) {
                case 'agent_warehouse': return 'مستودع وكيل';
                case 'china_customs_clearance': return 'تخليص صين';
                case 'on_board': return 'على السفينة';
                case 'at_sea': return 'في البحر';
                case 'arrived_port': return 'وصل الميناء';
                case 'israel_customs_clearance': return 'تخليص إسرائيل';
                case 'released': return 'مفرج عنها';
                case 'delivered_local': return 'تم التسليم';
                default: return typeof status === 'string' && status.length ? status : '—';
            }
        } else {
            switch (status) {
                case 'agent_warehouse': return 'مستودع وكيل';
                case 'delivered_to_shipping_company': return 'تم التسليم للوكيل';
                case 'china_customs_clearance': return 'تخليص صين';
                case 'departed': return 'انطلقت';
                case 'in_transit': return 'في الطريق';
                case 'arrived_airport': return 'وصل المطار';
                case 'israel_customs_clearance': return 'تخليص إسرائيل';
                case 'released': return 'مفرج عنها';
                case 'delivered_local': return 'تم التسليم';
                default: return typeof status === 'string' && status.length ? status : '—';
            }
        }
    };

    // دالة للحصول على أيقونة حالة الشحنة
    const getShipmentStatusIcon = (shipment: Shipment) => {
        if (!shipment.shippingInfo?.shipmentStatus?.status) return <Clock className="w-3 h-3" />;

        const statusRaw = shipment.shippingInfo.shipmentStatus.status;
        const coarseKey = normalizeLogisticsStatusKey(statusRaw);
        switch (coarseKey) {
            case 'pending':
                return <Clock className="w-3 h-3" />;
            case 'in-transit':
                return <Navigation className="w-3 h-3" />;
            case 'arrived':
                return <Anchor className="w-3 h-3" />;
            case 'clearing':
                return <FileText className="w-3 h-3" />;
            case 'cleared':
                return <PackageCheck className="w-3 h-3" />;
            default:
                break;
        }

        const status = statusRaw;
        if (shipment.shippingInfo.shippingType === 'sea') {
            switch (status) {
                case 'agent_warehouse': return <Warehouse className="w-3 h-3" />;
                case 'china_customs_clearance': return <FileText className="w-3 h-3" />;
                case 'on_board': return <Ship className="w-3 h-3" />;
                case 'at_sea': return <Navigation className="w-3 h-3" />;
                case 'arrived_port': return <Anchor className="w-3 h-3" />;
                case 'israel_customs_clearance': return <FileText className="w-3 h-3" />;
                case 'released': return <PackageCheck className="w-3 h-3" />;
                case 'delivered_local': return <PackageCheck className="w-3 h-3" />;
                default: return <Clock className="w-3 h-3" />;
            }
        } else {
            switch (status) {
                case 'agent_warehouse': return <Warehouse className="w-3 h-3" />;
                case 'delivered_to_shipping_company': return <User className="w-3 h-3" />;
                case 'china_customs_clearance': return <FileText className="w-3 h-3" />;
                case 'departed': return <Plane className="w-3 h-3" />;
                case 'in_transit': return <Navigation className="w-3 h-3" />;
                case 'arrived_airport': return <Plane className="w-3 h-3" />;
                case 'israel_customs_clearance': return <FileText className="w-3 h-3" />;
                case 'released': return <PackageCheck className="w-3 h-3" />;
                case 'delivered_local': return <PackageCheck className="w-3 h-3" />;
                default: return <Clock className="w-3 h-3" />;
            }
        }
    };

    // دالة لتنسيق التاريخ بشكل مختصر
    const formatDate = (dateString?: string) => {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleDateString('ar-EG', {
            day: 'numeric',
            month: 'short'
        });
    };

    // --- Empty State ---
    if (shipments.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-24 bg-gray-50/50 dark:bg-gray-900/50 rounded-3xl border-2 border-dashed border-gray-200 dark:border-gray-800">
                <div className="p-4 bg-white dark:bg-gray-800 rounded-full shadow-sm mb-4">
                    <Truck className="w-12 h-12 text-blue-500/50" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 dark:text-white">لا توجد شحنات حالياً</h3>
                <p className="text-gray-500 dark:text-gray-400 mt-2 max-w-sm text-center">
                    ابدأ بإنشاء شحنة جديدة لتجميع الصفقات وتوزيع التكاليف بشكل منظم.
                </p>
            </div>
        );
    }

    // --- Render ---
    return (
        <>
            <div className="overflow-x-auto pb-4">
                <table className="w-full text-right">
                    <thead>
                        <tr className="text-gray-400 dark:text-gray-500 text-[10px] font-semibold uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
                            <th className="px-3 py-3">الشحنة</th>
                            <th className="px-2 py-3">التواريخ</th>
                            <th className="px-2 py-3">الوكيل</th>
                            <th className="px-2 py-3 text-center">الحجم/الوزن</th>
                            <th className="px-2 py-3">التكلفة</th>
                            <th className="px-2 py-3">الحالة</th>
                            <th className="px-3 py-3 text-left">الإجراءات</th>
                        </tr>
                    </thead>
                    <tbody className="text-xs">
                        {shipments.map((shipment) => {
                            const shippingType = shipment.shippingInfo?.shippingType || 'sea';
                            const shipmentStatus = shipment.shippingInfo?.shipmentStatus?.status;
                            const createdAt = shipment.createdAt ? new Date(shipment.createdAt) : null;
                            const departureDate = shipment.shippingInfo?.departureDate ? new Date(shipment.shippingInfo.departureDate) : null;
                            const arrivalDate = shipment.shippingInfo?.arrivalDate ? new Date(shipment.shippingInfo.arrivalDate) : null;

                            return (
                                <tr
                                    key={shipment.id}
                                    className="bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-all duration-150"
                                >
                                    {/* اسم الشحنة */}
                                    <td className="px-3 py-3">
                                        <div className="flex items-start gap-3">
                                            <div className={`p-2 rounded-lg mt-1 ${shippingType === 'sea' ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400' : 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 text-[var(--color-primary)] dark:text-[var(--color-primary)]'}`}>
                                                {shippingType === 'sea' ?
                                                    <Ship className="w-4 h-4" /> :
                                                    <Plane className="w-4 h-4" />
                                                }
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                {/* اسم الشحنة - الجزء الرئيسي */}
                                                <div className="font-bold text-gray-900 dark:text-white mb-1 flex items-center gap-2">
                                                    <Truck className="w-3 h-3 text-gray-400 flex-shrink-0" />
                                                    <span className="truncate" title={buildShipmentOptionLabelCamel(shipment)}>
                                                        {buildShipmentOptionLabelCamel(shipment)}
                                                    </span>
                                                </div>

                                                {/* معلومات إضافية */}
                                                <div className="flex flex-wrap gap-2">
                                                    {/* رقم الشحنة */}
                                                    <div className="flex items-center gap-1 text-[10px] text-gray-500 bg-gray-50 dark:bg-gray-800 px-2 py-0.5 rounded">
                                                        <Hash className="w-2.5 h-2.5" />
                                                        <span>{shipment.shipmentNumber}</span>
                                                    </div>

                                                    {/* عدد الصفقات */}
                                                    <div className="flex items-center gap-1 text-[10px] text-gray-500 bg-gray-50 dark:bg-gray-800 px-2 py-0.5 rounded">
                                                        <Layers className="w-2.5 h-2.5" />
                                                        <span>{shipment.deals?.length || 0} صفقة</span>
                                                    </div>

                                                    {/* الحالة المالية */}
                                                    <div className={`px-2 py-0.5 rounded text-[10px] font-medium ${getStatusStyle(shipment.status)}`}>
                                                        {getStatusLabel(shipment.status)}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </td>

                                    {/* التواريخ */}
                                    <td className="px-2 py-3">
                                        <div className="space-y-2">
                                            {/* تاريخ الإنشاء */}
                                            <div className="flex items-center gap-1">
                                                <Calendar className="w-3 h-3 text-gray-400 flex-shrink-0" />
                                                <span className="text-[11px] text-gray-600 dark:text-gray-300" title="تاريخ الإنشاء">
                                                    {createdAt ? formatDate(createdAt.toISOString()) : '-'}
                                                </span>
                                            </div>

                                            {/* تاريخ المغادرة */}
                                            {departureDate && (
                                                <div className="flex items-center gap-1">
                                                    <TrendingUp className="w-3 h-3 text-blue-400 flex-shrink-0" />
                                                    <span className="text-[11px] text-gray-600 dark:text-gray-300" title="تاريخ المغادرة">
                                                        {formatDate(departureDate.toISOString())}
                                                    </span>
                                                </div>
                                            )}

                                            {/* تاريخ الوصول */}
                                            {arrivalDate && (
                                                <div className="flex items-center gap-1">
                                                    <MapPin className="w-3 h-3 text-green-400 flex-shrink-0" />
                                                    <span className="text-[11px] text-gray-600 dark:text-gray-300" title="تاريخ الوصول المتوقع">
                                                        {formatDate(arrivalDate.toISOString())}
                                                    </span>
                                                </div>
                                            )}
                                        </div>
                                    </td>

                                    {/* وكيل الشحن */}
                                    <td className="px-2 py-3">
                                        <button
                                            onClick={() => handleOpenSupplier(shipment.shippingAgentId)}
                                            className="group/agent flex items-center gap-1 px-2 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700/70 transition-colors w-full text-right"
                                            title={shipment.shippingAgentName}
                                        >
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs text-gray-700 dark:text-gray-200 truncate group-hover/agent:text-blue-600 dark:group-hover/agent:text-blue-400 transition-colors">
                                                    {shipment.shippingAgentName}
                                                </div>
                                                <div className="text-[10px] text-gray-400 truncate">
                                                    وكيل شحن
                                                </div>
                                            </div>
                                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
                                        </button>
                                    </td>

                                    {/* الحجم والوزن */}
                                    <td className="px-2 py-3">
                                        <div className="flex flex-col gap-1 items-center">
                                            <div className="flex items-center gap-1" title="الحجم">
                                                <Box className="w-3 h-3 text-blue-500" />
                                                <span className="font-mono font-bold text-sm text-gray-700 dark:text-gray-200">
                                                    {(shipment.deals && shipment.deals.length > 0
                                                        ? shipment.deals.reduce((sum, d) => sum + (Number(d.totalVolume) || 0), 0)
                                                        : Number(shipment.totalVolume) || 0
                                                    ).toFixed(1)}
                                                </span>
                                                <span className="text-[10px] text-gray-400">م³</span>
                                            </div>
                                            <div className="flex items-center gap-1" title="الوزن">
                                                <Scale className="w-3 h-3 text-[var(--color-primary)]" />
                                                <span className="font-mono font-bold text-sm text-gray-700 dark:text-gray-200">
                                                    {(shipment.deals && shipment.deals.length > 0
                                                        ? shipment.deals.reduce((sum, d) => sum + (Number(d.totalWeightKg) || 0), 0)
                                                        : Number(shipment.totalWeightKg) || 0
                                                    ).toFixed(0)}
                                                </span>
                                                <span className="text-[10px] text-gray-400">كجم</span>
                                            </div>
                                        </div>
                                    </td>

                                    {/* التكلفة */}
                                    <td className="px-2 py-3">
                                        <div className="flex items-center gap-0.5 justify-end">
                                            <DollarSign className="w-3 h-3 text-green-500" />
                                            <span className="font-bold text-lg text-gray-900 dark:text-white">
                                                {(shipment.totalShippingCostUsd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                            </span>
                                        </div>
                                        {shipment.installmentPlanEnabled && shipment.installments && shipment.installments.length > 0 && (
                                            <div className="text-[10px] text-gray-400 text-right mt-0.5">
                                                {shipment.installments.filter(i => i.status === 'paid').length}/{shipment.installments.length} دفعة
                                            </div>
                                        )}
                                    </td>

                                    {/* حالة الشحنة */}
                                    <td className="px-2 py-3">
                                        <div className="flex items-center gap-2">
                                            <div className={`p-1.5 rounded-lg ${shippingType === 'sea' ? 'bg-blue-50 dark:bg-blue-900/20' : 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20'}`}>
                                                {getShipmentStatusIcon(shipment)}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs font-medium text-gray-700 dark:text-gray-200 truncate">
                                                    {getShipmentStatusText(shipment)}
                                                </div>
                                                {shipment.shippingInfo?.shipmentStatus?.statusDate && (
                                                    <div className="text-[10px] text-gray-400">
                                                        {formatDate(shipment.shippingInfo.shipmentStatus.statusDate)}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </td>

                                    {/* الإجراءات */}
                                    <td className="px-3 py-3 text-left">
                                        <div className="flex items-center gap-1">
                                            {/* زر التتبع */}
                                            {shippingType === 'sea' ? (
                                                (shipment.shippingInfo?.trackingLink ||
                                                    shipment.shippingInfo?.imoNumber ||
                                                    shipment.shippingInfo?.shipName ||
                                                    shipment.shippingInfo?.containerNumber) && (
                                                    <a
                                                        href={
                                                            shipment.shippingInfo?.trackingLink ||
                                                            (shipment.shippingInfo?.imoNumber
                                                                ? `https://www.marinetraffic.com/en/ais/details/ships/imo:${shipment.shippingInfo.imoNumber}`
                                                                : (shipment.shippingInfo?.shipName
                                                                    ? `https://www.vesselfinder.com/vessels?name=${encodeURIComponent(shipment.shippingInfo.shipName)}`
                                                                    : `https://www.track-trace.com/container/item/${shipment.shippingInfo?.containerNumber}`))
                                                        }
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="p-2 text-emerald-600 hover:text-emerald-700 bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:hover:bg-emerald-900/40 rounded-lg transition-colors"
                                                        title="تتبع الشحنة"
                                                    >
                                                        <Navigation className="w-4 h-4" />
                                                    </a>
                                                )
                                            ) : (
                                                shipment.shippingInfo?.airwayBillNumber && (
                                                    <a
                                                        href={`https://www.track-trace.com/aircargo/item/${shipment.shippingInfo.airwayBillNumber}`}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="p-2 text-emerald-600 hover:text-emerald-700 bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:hover:bg-emerald-900/40 rounded-lg transition-colors"
                                                        title="تتبع الشحنة"
                                                    >
                                                        <Navigation className="w-4 h-4" />
                                                    </a>
                                                )
                                            )}

                                            {/* زر التفاصيل */}
                                            <button
                                                onClick={() => onView(shipment)}
                                                className="p-2 text-emerald-600 hover:text-emerald-700 bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-400 dark:hover:bg-emerald-900/40 rounded-lg transition-colors"
                                                title="عرض التفاصيل"
                                            >
                                                <Eye className="w-4 h-4" />
                                            </button>

                                            {/* زر التعديل */}
                                            <button
                                                onClick={() => onEdit(shipment)}
                                                className="p-2 text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:hover:bg-blue-900/40 rounded-lg transition-colors"
                                                title="تعديل الشحنة"
                                            >
                                                <Edit className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            <SupplierViewModal
                isOpen={isSupplierModalOpen}
                onClose={handleCloseSupplier}
                supplierId={selectedSupplierId}
            />
        </>
    );
};