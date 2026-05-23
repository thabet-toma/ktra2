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
            case 'draft': return `${baseClass} aseel-bg-panel aseel-text-soft aseel-border-soft dark:aseel-bg-panel dark:aseel-text-soft dark:aseel-border-soft`;
            case 'payment_pending': return `${baseClass} aseel-bg-panel aseel-text-ink aseel-border-soft dark:aseel-bg-panel/20 dark:aseel-text-soft dark:aseel-border-soft`;
            case 'partially_paid': return `${baseClass} aseel-bg-accent-bg aseel-text-accent aseel-border-accent dark:aseel-bg-panel/20 dark:aseel-text-soft dark:aseel-border-soft`;
            case 'paid': return `${baseClass} bg-green-50 text-green-700 aseel-border-soft dark:bg-green-900/20 dark:text-green-300 dark:border-green-800`;
            case 'shipped': return `${baseClass} bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)] dark:bg-[var(--color-surface-2)]/20 dark:text-[var(--color-primary)] dark:border-[var(--color-border)]`;
            case 'delivered': return `${baseClass} bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)] dark:bg-[var(--color-surface-2)]/20 dark:text-[var(--color-primary)] dark:border-[var(--color-border)]`;
            case 'cancelled': return `${baseClass} aseel-bg-panel aseel-text-state aseel-border-soft dark:aseel-bg-panel/20 dark:aseel-text-soft dark:aseel-border-soft`;
            default: return `${baseClass} aseel-bg-panel aseel-text-soft`;
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
            <div className="flex flex-col items-center justify-center py-24 aseel-bg-panel/50 dark:aseel-bg-panel/50 rounded-3xl border-2 border-dashed aseel-border-soft dark:aseel-border-soft">
                <div className="p-4 aseel-bg-field dark:aseel-bg-panel rounded-full shadow-sm mb-4">
                    <Truck className="w-12 h-12 aseel-text-soft/50" />
                </div>
                <h3 className="text-xl font-bold aseel-text-ink dark:text-white">لا توجد شحنات حالياً</h3>
                <p className="aseel-text-soft dark:aseel-text-soft mt-2 max-w-sm text-center">
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
                        <tr className="aseel-text-soft dark:aseel-text-soft text-[10px] font-semibold uppercase tracking-wider border-b aseel-border-soft dark:aseel-border-soft">
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
                                    className="aseel-bg-field dark:aseel-bg-panel border-b aseel-border-soft dark:aseel-border-soft/50 hover:aseel-bg-panel dark:hover:aseel-bg-panel/50 transition-all duration-150"
                                >
                                    {/* اسم الشحنة */}
                                    <td className="px-3 py-3">
                                        <div className="flex items-start gap-3">
                                            <div className={`p-2 rounded-lg mt-1 ${shippingType === 'sea' ? 'aseel-bg-accent-bg dark:aseel-bg-panel/20 aseel-text-accent dark:aseel-text-soft' : 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 text-[var(--color-primary)] dark:text-[var(--color-primary)]'}`}>
                                                {shippingType === 'sea' ?
                                                    <Ship className="w-4 h-4" /> :
                                                    <Plane className="w-4 h-4" />
                                                }
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                {/* اسم الشحنة - الجزء الرئيسي */}
                                                <div className="font-bold aseel-text-ink dark:text-white mb-1 flex items-center gap-2">
                                                    <Truck className="w-3 h-3 aseel-text-soft flex-shrink-0" />
                                                    <span className="truncate" title={buildShipmentOptionLabelCamel(shipment)}>
                                                        {buildShipmentOptionLabelCamel(shipment)}
                                                    </span>
                                                </div>

                                                {/* معلومات إضافية */}
                                                <div className="flex flex-wrap gap-2">
                                                    {/* رقم الشحنة */}
                                                    <div className="flex items-center gap-1 text-[10px] aseel-text-soft aseel-bg-panel dark:aseel-bg-panel px-2 py-0.5 rounded">
                                                        <Hash className="w-2.5 h-2.5" />
                                                        <span>{shipment.shipmentNumber}</span>
                                                    </div>

                                                    {/* عدد الصفقات */}
                                                    <div className="flex items-center gap-1 text-[10px] aseel-text-soft aseel-bg-panel dark:aseel-bg-panel px-2 py-0.5 rounded">
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
                                                <Calendar className="w-3 h-3 aseel-text-soft flex-shrink-0" />
                                                <span className="text-[11px] aseel-text-soft dark:aseel-text-soft" title="تاريخ الإنشاء">
                                                    {createdAt ? formatDate(createdAt.toISOString()) : '-'}
                                                </span>
                                            </div>

                                            {/* تاريخ المغادرة */}
                                            {departureDate && (
                                                <div className="flex items-center gap-1">
                                                    <TrendingUp className="w-3 h-3 aseel-text-soft flex-shrink-0" />
                                                    <span className="text-[11px] aseel-text-soft dark:aseel-text-soft" title="تاريخ المغادرة">
                                                        {formatDate(departureDate.toISOString())}
                                                    </span>
                                                </div>
                                            )}

                                            {/* تاريخ الوصول */}
                                            {arrivalDate && (
                                                <div className="flex items-center gap-1">
                                                    <MapPin className="w-3 h-3 text-green-400 flex-shrink-0" />
                                                    <span className="text-[11px] aseel-text-soft dark:aseel-text-soft" title="تاريخ الوصول المتوقع">
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
                                            className="group/agent flex items-center gap-1 px-2 py-1.5 rounded-lg hover:aseel-bg-panel dark:hover:aseel-bg-panel/70 transition-colors w-full text-right"
                                            title={shipment.shippingAgentName}
                                        >
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs aseel-text-ink dark:aseel-text-soft truncate group-hover/agent:aseel-text-accent dark:group-hover/agent:aseel-text-soft transition-colors">
                                                    {shipment.shippingAgentName}
                                                </div>
                                                <div className="text-[10px] aseel-text-soft truncate">
                                                    وكيل شحن
                                                </div>
                                            </div>
                                            <div className="w-1.5 h-1.5 rounded-full aseel-bg-panel flex-shrink-0" />
                                        </button>
                                    </td>

                                    {/* الحجم والوزن */}
                                    <td className="px-2 py-3">
                                        <div className="flex flex-col gap-1 items-center">
                                            <div className="flex items-center gap-1" title="الحجم">
                                                <Box className="w-3 h-3 aseel-text-soft" />
                                                <span className="font-mono font-bold text-sm aseel-text-ink dark:aseel-text-soft">
                                                    {(shipment.deals && shipment.deals.length > 0
                                                        ? shipment.deals.reduce((sum, d) => sum + (Number(d.totalVolume) || 0), 0)
                                                        : Number(shipment.totalVolume) || 0
                                                    ).toFixed(1)}
                                                </span>
                                                <span className="text-[10px] aseel-text-soft">م³</span>
                                            </div>
                                            <div className="flex items-center gap-1" title="الوزن">
                                                <Scale className="w-3 h-3 text-[var(--color-primary)]" />
                                                <span className="font-mono font-bold text-sm aseel-text-ink dark:aseel-text-soft">
                                                    {(shipment.deals && shipment.deals.length > 0
                                                        ? shipment.deals.reduce((sum, d) => sum + (Number(d.totalWeightKg) || 0), 0)
                                                        : Number(shipment.totalWeightKg) || 0
                                                    ).toFixed(0)}
                                                </span>
                                                <span className="text-[10px] aseel-text-soft">كجم</span>
                                            </div>
                                        </div>
                                    </td>

                                    {/* التكلفة */}
                                    <td className="px-2 py-3">
                                        <div className="flex items-center gap-0.5 justify-end">
                                            <DollarSign className="w-3 h-3 text-green-500" />
                                            <span className="font-bold text-lg aseel-text-ink dark:text-white">
                                                {(shipment.totalShippingCostUsd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                            </span>
                                        </div>
                                        {shipment.installmentPlanEnabled && shipment.installments && shipment.installments.length > 0 && (
                                            <div className="text-[10px] aseel-text-soft text-right mt-0.5">
                                                {shipment.installments.filter(i => i.status === 'paid').length}/{shipment.installments.length} دفعة
                                            </div>
                                        )}
                                    </td>

                                    {/* حالة الشحنة */}
                                    <td className="px-2 py-3">
                                        <div className="flex items-center gap-2">
                                            <div className={`p-1.5 rounded-lg ${shippingType === 'sea' ? 'aseel-bg-accent-bg dark:aseel-bg-panel/20' : 'bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20'}`}>
                                                {getShipmentStatusIcon(shipment)}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-xs font-medium aseel-text-ink dark:aseel-text-soft truncate">
                                                    {getShipmentStatusText(shipment)}
                                                </div>
                                                {shipment.shippingInfo?.shipmentStatus?.statusDate && (
                                                    <div className="text-[10px] aseel-text-soft">
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
                                                        className="p-2 aseel-text-soft hover:aseel-text-ink aseel-bg-panel hover:aseel-bg-panel dark:aseel-bg-panel/20 dark:aseel-text-soft dark:hover:aseel-bg-panel/40 rounded-lg transition-colors"
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
                                                        className="p-2 aseel-text-soft hover:aseel-text-ink aseel-bg-panel hover:aseel-bg-panel dark:aseel-bg-panel/20 dark:aseel-text-soft dark:hover:aseel-bg-panel/40 rounded-lg transition-colors"
                                                        title="تتبع الشحنة"
                                                    >
                                                        <Navigation className="w-4 h-4" />
                                                    </a>
                                                )
                                            )}

                                            {/* زر التفاصيل */}
                                            <button
                                                onClick={() => onView(shipment)}
                                                className="p-2 aseel-text-soft hover:aseel-text-ink aseel-bg-panel hover:aseel-bg-panel dark:aseel-bg-panel/20 dark:aseel-text-soft dark:hover:aseel-bg-panel/40 rounded-lg transition-colors"
                                                title="عرض التفاصيل"
                                            >
                                                <Eye className="w-4 h-4" />
                                            </button>

                                            {/* زر التعديل */}
                                            <button
                                                onClick={() => onEdit(shipment)}
                                                className="p-2 aseel-text-accent hover:aseel-text-accent aseel-bg-accent-bg hover:aseel-bg-accent-bg dark:aseel-bg-panel/20 dark:aseel-text-soft dark:hover:aseel-bg-panel/40 rounded-lg transition-colors"
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