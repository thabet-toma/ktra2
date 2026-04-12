// components/shipments/ShipmentDetailView.tsx
import React, { useState, useEffect, useMemo } from 'react';
import { Shipment, Deal } from '../../../types';
import { dealsService } from '../../../services/dealsService';
import { effectiveDealTitleForDisplay } from '../../../utils/dealTitleDisplay';
import {
    Truck, Ship, Plane, Calendar, Package, DollarSign,
    FileText, User, Hash, Box, Scale, Navigation,
    Printer, MapPin, Clock,
    AlertCircle, Building, Globe,
    ExternalLink, TrendingUp,
    CreditCard
} from 'lucide-react';
import { format } from 'date-fns';
import { ar } from 'date-fns/locale';

interface ShipmentDetailViewProps {
    shipment: Shipment;
    onClose: () => void;
}

export const ShipmentDetailView: React.FC<ShipmentDetailViewProps> = ({ shipment, onClose }) => {
    const [isPrinting, setIsPrinting] = useState(false);
    const [liveDeals, setLiveDeals] = useState<Deal[]>([]);

    useEffect(() => {
        return dealsService.subscribeToDeals(setLiveDeals);
    }, []);

    /** صفوف الصفقات مع دمج أحدث بيانات من SQL (نفس شاشة الصفقة) */
    const resolvedShipmentDeals = useMemo(() => {
        const rows = shipment.deals || [];
        return rows.map((row) => {
            const live = liveDeals.find((d) => String(d.id) === String(row.dealId));
            if (!live) return row;
            const notesMerged = (live.internalNotes || row.notes || "").trim();
            const descRaw =
                String(live.dealDescription || row.dealDescriptionRaw || "").trim() || undefined;
            return {
                ...row,
                dealNumber: live.dealNumber,
                originalOfferNumber: live.originalOfferNumber || row.originalOfferNumber || "",
                totalAmount: live.totalAmount,
                totalVolume: Number(live.totalVolume || 0),
                totalWeightKg: Number(live.totalWeightKg ?? live.totalWeight ?? 0),
                dealDescriptionRaw: descRaw,
                notes: notesMerged || row.notes,
                displayTitle: effectiveDealTitleForDisplay({
                    description: live.dealDescription || row.dealDescriptionRaw,
                    notes: notesMerged || row.notes,
                    original_offer_number: live.originalOfferNumber || row.originalOfferNumber,
                    ref_number: live.dealNumber || row.dealNumber,
                }),
            };
        });
    }, [shipment.deals, liveDeals]);

    // --- Helpers ---
    const formatDate = (dateString?: string) => {
        if (!dateString) return 'غير محدد';
        try {
            return format(new Date(dateString), 'dd/MM/yyyy', { locale: ar });
        } catch {
            return 'غير صالح';
        }
    };

    const formatDateTime = (dateString?: string) => {
        if (!dateString) return 'غير محدد';
        try {
            return format(new Date(dateString), 'dd/MM/yyyy HH:mm', { locale: ar });
        } catch {
            return 'غير صالح';
        }
    };

    const getStatusColor = (status: Shipment['status']) => {
        switch (status) {
            case 'draft': return 'bg-gray-100 text-gray-700';
            case 'payment_pending': return 'bg-yellow-100 text-yellow-700';
            case 'partially_paid': return 'bg-blue-100 text-blue-700';
            case 'paid': return 'bg-green-100 text-green-700';
            case 'shipped': return 'bg-indigo-100 text-indigo-700';
            case 'delivered': return 'bg-teal-100 text-teal-700';
            case 'cancelled': return 'bg-red-100 text-red-700';
            default: return 'bg-gray-100 text-gray-700';
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

    const getShipmentStatusText = () => {
        if (!shipment.shippingInfo?.shipmentStatus?.status) return 'لم تبدأ';
        const status = shipment.shippingInfo.shipmentStatus.status;
        if (shipment.shippingInfo.shippingType === 'sea') {
            switch (status) {
                case 'agent_warehouse': return 'في مستودع وكيل الشحن';
                case 'china_customs_clearance': return 'تخليص جمارك الصين';
                case 'on_board': return 'على ظهر السفينة';
                case 'at_sea': return 'في البحر';
                case 'arrived_port': return 'وصلت الميناء';
                case 'israel_customs_clearance': return 'تخليص جمارك إسرائيل';
                case 'released': return 'مفرج عنها';
                case 'delivered_local': return 'تم التسليم محلياً';
                default: return status;
            }
        } else {
            switch (status) {
                case 'agent_warehouse': return 'في مستودع وكيل الشحن';
                case 'delivered_to_shipping_company': return `تم التسليم لشركة الشحن`;
                case 'china_customs_clearance': return 'تخليص جمارك الصين';
                case 'departed': return 'انطلقت';
                case 'in_transit': return 'في الطريق';
                case 'arrived_airport': return 'وصلت المطار';
                case 'israel_customs_clearance': return 'تخليص جمارك إسرائيل';
                case 'released': return 'مفرج عنها';
                case 'delivered_local': return 'تم التسليم محلياً';
                default: return status;
            }
        }
    };

    const calculateProgress = () => {
        if (!shipment.shippingInfo?.shipmentStatus?.status) return 0;
        const status = shipment.shippingInfo.shipmentStatus.status;
        const statuses = shipment.shippingInfo.shippingType === 'sea'
            ? ['agent_warehouse', 'china_customs_clearance', 'on_board', 'at_sea', 'arrived_port', 'israel_customs_clearance', 'released', 'delivered_local']
            : ['agent_warehouse', 'delivered_to_shipping_company', 'china_customs_clearance', 'departed', 'in_transit', 'arrived_airport', 'israel_customs_clearance', 'released', 'delivered_local'];
        const index = statuses.indexOf(status);
        return index >= 0 ? Math.round(((index + 1) / statuses.length) * 100) : 0;
    };

    const calculatePaymentProgress = () => {
        if (!shipment.installments || shipment.installments.length === 0) {
            return shipment.status === 'paid' ? 100 : 0;
        }
        const paidAmount = shipment.installments
            .filter(inst => inst.status === 'paid')
            .reduce((sum, inst) => sum + (inst.amount || 0), 0);
        const totalAmount = shipment.installments.reduce((sum, inst) => sum + (inst.amount || 0), 0);
        return totalAmount > 0 ? Math.round((paidAmount / totalAmount) * 100) : 0;
    };

    const handlePrint = () => {
        setIsPrinting(true);
        setTimeout(() => {
            window.print();
            setIsPrinting(false);
        }, 100);
    };

    // --- Data Extraction ---
    const shippingInfo = shipment.shippingInfo;
    const isSea = shippingInfo?.shippingType === 'sea';
    const shipmentNumber = shipment.agentShipmentNumber || shipment.shipmentNumber;
    const totalDeals = resolvedShipmentDeals.length || 0;
    const totalCost = shipment.totalShippingCostUsd || 0;
    const totalVolume =
        resolvedShipmentDeals.length > 0
            ? resolvedShipmentDeals.reduce((sum, d) => sum + (Number(d.totalVolume) || 0), 0)
            : Number(shipment.totalVolume) || 0;
    const totalWeight =
        resolvedShipmentDeals.length > 0
            ? resolvedShipmentDeals.reduce((sum, d) => sum + (Number(d.totalWeightKg) || 0), 0)
            : Number(shipment.totalWeightKg) || 0;

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 print:p-0">
            <div className="bg-white dark:bg-gray-900 rounded-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col print:max-h-none print:max-w-none print:rounded-none print:shadow-none print:bg-white">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700 print:hidden">
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-xl ${isSea ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' : 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'}`}>
                            {isSea ? <Ship className="w-6 h-6" /> : <Plane className="w-6 h-6" />}
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                                {shipment.shipmentName || `شحنة ${shipmentNumber}`}
                            </h2>
                            <p className="text-sm text-gray-500">تفاصيل الشحنة #{shipmentNumber}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handlePrint}
                            disabled={isPrinting}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                        >
                            <Printer className="w-4 h-4" />
                            {isPrinting ? 'جاري الطباعة...' : 'طباعة'}
                        </button>
                        <button
                            onClick={onClose}
                            className="px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                        >
                            إغلاق
                        </button>
                    </div>
                </div>

                {/* Main Content */}
                <div className="flex-1 overflow-y-auto p-6 print:p-8">
                    {/* Print Header (for printing only) */}
                    <div className="hidden print:block mb-8 border-b pb-4">
                        <div className="flex justify-between items-start">
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900">
                                    {shipment.shipmentName || `شحنة ${shipmentNumber}`}
                                </h1>
                                <p className="text-gray-600">تقرير تفصيلي للشحنة #{shipmentNumber}</p>
                            </div>
                            <div className="text-right">
                                <div className="text-sm text-gray-500">تاريخ الطباعة: {formatDate(new Date().toISOString())}</div>
                                <div className="text-sm text-gray-500">الوقت: {format(new Date(), 'HH:mm')}</div>
                            </div>
                        </div>
                    </div>

                    {/* Main Info Grid */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                        {/* Column 1: Basic Info */}
                        <div className="space-y-6">
                            {/* Shipment Type Card */}
                            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                    <Truck className="w-4 h-4" />
                                    معلومات الشحنة الأساسية
                                </h3>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">رقم الشحنة:</span>
                                        <span className="font-bold text-gray-900 dark:text-white font-mono">{shipmentNumber}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">نوع الشحن:</span>
                                        <span className={`flex items-center gap-1 px-2 py-1 rounded ${isSea ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}`}>
                                            {isSea ? <Ship className="w-3 h-3" /> : <Plane className="w-3 h-3" />}
                                            {isSea ? 'بحري' : 'جوي'}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">الحالة:</span>
                                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(shipment.status)}`}>
                                            {getStatusLabel(shipment.status)}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">تاريخ الإنشاء:</span>
                                        <span className="font-medium text-gray-900 dark:text-white">
                                            {formatDateTime(shipment.createdAt)}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Shipping Agent Card */}
                            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                    <Building className="w-4 h-4" />
                                    وكيل الشحن
                                </h3>
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <User className="w-4 h-4 text-gray-400" />
                                        <span className="font-medium text-gray-900 dark:text-white">{shipment.shippingAgentName}</span>
                                    </div>
                                    <div className="text-sm text-gray-600 dark:text-gray-400">
                                        المعرف: <span className="font-mono">{shipment.shippingAgentId}</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Column 2: Dates & Schedule */}
                        <div className="space-y-6">
                            {/* Schedule Card */}
                            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4 border border-blue-100 dark:border-blue-800">
                                <h3 className="text-sm font-semibold text-blue-700 dark:text-blue-300 mb-3 flex items-center gap-2">
                                    <Calendar className="w-4 h-4" />
                                    الجدول الزمني
                                </h3>
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <TrendingUp className="w-4 h-4 text-blue-500" />
                                            <span className="text-gray-600 dark:text-gray-400">تاريخ المغادرة:</span>
                                        </div>
                                        <span className="font-bold text-blue-700 dark:text-blue-300">
                                            {shippingInfo.departureDate ? formatDate(shippingInfo.departureDate) : 'غير محدد'}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <MapPin className="w-4 h-4 text-green-500" />
                                            <span className="text-gray-600 dark:text-gray-400">تاريخ الوصول المتوقع:</span>
                                        </div>
                                        <span className="font-bold text-green-700 dark:text-green-300">
                                            {shippingInfo.arrivalDate ? formatDate(shippingInfo.arrivalDate) : 'غير محدد'}
                                        </span>
                                    </div>
                                    <div className="pt-2 border-t border-blue-100 dark:border-blue-800">
                                        <div className="text-xs text-blue-600 dark:text-blue-400 font-medium mb-1">مدة الشحن المتوقعة</div>
                                        {shippingInfo.departureDate && shippingInfo.arrivalDate ? (
                                            <div className="text-sm text-gray-700 dark:text-gray-300">
                                                {(() => {
                                                    const dep = new Date(shippingInfo.departureDate);
                                                    const arr = new Date(shippingInfo.arrivalDate);
                                                    const diffTime = Math.abs(arr.getTime() - dep.getTime());
                                                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                                                    return `${diffDays} يوم`;
                                                })()}
                                            </div>
                                        ) : (
                                            <div className="text-sm text-gray-500">غير محددة</div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Current Status Card */}
                            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                    <Clock className="w-4 h-4" />
                                    الحالة الحالية
                                </h3>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">حالة الشحنة:</span>
                                        <span className="font-medium text-gray-900 dark:text-white">
                                            {getShipmentStatusText()}
                                        </span>
                                    </div>
                                    {shippingInfo.shipmentStatus?.statusDate && (
                                        <div className="flex items-center justify-between">
                                            <span className="text-gray-600 dark:text-gray-400">تاريخ التحديث:</span>
                                            <span className="text-sm text-gray-500">
                                                {formatDate(shippingInfo.shipmentStatus.statusDate)}
                                            </span>
                                        </div>
                                    )}
                                    {shippingInfo.shipmentStatus?.notes && (
                                        <div className="bg-yellow-50 dark:bg-yellow-900/20 p-2 rounded-lg">
                                            <div className="text-xs text-yellow-700 dark:text-yellow-300 font-medium mb-1">ملاحظات:</div>
                                            <div className="text-sm text-gray-700 dark:text-gray-300">{shippingInfo.shipmentStatus.notes}</div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Column 3: Metrics */}
                        <div className="space-y-6">
                            {/* Financial Summary */}
                            <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-xl p-4 border border-emerald-100 dark:border-emerald-800">
                                <h3 className="text-sm font-semibold text-emerald-700 dark:text-emerald-300 mb-3 flex items-center gap-2">
                                    <DollarSign className="w-4 h-4" />
                                    الملخص المالي
                                </h3>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">التكلفة الإجمالية:</span>
                                        <span className="font-bold text-lg text-emerald-700 dark:text-emerald-300">
                                            ${totalCost.toLocaleString()}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">عدد الصفقات:</span>
                                        <span className="font-bold text-gray-900 dark:text-white">{totalDeals}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">الحجم الإجمالي:</span>
                                        <span className="font-bold text-gray-900 dark:text-white">
                                            {totalVolume.toFixed(1)} م³
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">الوزن الإجمالي:</span>
                                        <span className="font-bold text-gray-900 dark:text-white">
                                            {totalWeight.toLocaleString()} كجم
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Progress Bars */}
                            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                    <TrendingUp className="w-4 h-4" />
                                    تقدم التنفيذ
                                </h3>
                                <div className="space-y-4">
                                    {/* Shipment Progress */}
                                    <div>
                                        <div className="flex justify-between items-center mb-1">
                                            <span className="text-xs text-gray-600 dark:text-gray-400">تقدم الشحنة</span>
                                            <span className="text-xs font-medium">{calculateProgress()}%</span>
                                        </div>
                                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                            <div
                                                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                                style={{ width: `${calculateProgress()}%` }}
                                            ></div>
                                        </div>
                                    </div>

                                    {/* Payment Progress */}
                                    <div>
                                        <div className="flex justify-between items-center mb-1">
                                            <span className="text-xs text-gray-600 dark:text-gray-400">تقدم الدفع</span>
                                            <span className="text-xs font-medium">{calculatePaymentProgress()}%</span>
                                        </div>
                                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                            <div
                                                className="bg-green-600 h-2 rounded-full transition-all duration-300"
                                                style={{ width: `${calculatePaymentProgress()}%` }}
                                            ></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Detailed Information Sections */}
                    <div className="space-y-6">
                        {/* Shipping Details Section */}
                        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                            <div className="border-b border-gray-200 dark:border-gray-700 p-4">
                                <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                                    <Globe className="w-5 h-5" />
                                    تفاصيل الشحن
                                </h3>
                            </div>
                            <div className="p-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {/* Shipping Company Info */}
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                                            <Building className="w-4 h-4" />
                                            شركة الشحن الدولية
                                        </h4>
                                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                                            <div className="text-gray-900 dark:text-white font-medium">{shippingInfo?.internationalShippingCompany || 'غير محدد'}</div>
                                        </div>
                                    </div>

                                    {/* Ship/Flight Info */}
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                                            {isSea ? <Ship className="w-4 h-4" /> : <Plane className="w-4 h-4" />}
                                            {isSea ? 'معلومات السفينة' : 'معلومات الرحلة'}
                                        </h4>
                                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                                            {isSea ? (
                                                <>
                                                    <div className="mb-2">
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">اسم السفينة:</span>
                                                        <div className="font-medium text-gray-900 dark:text-white">{shippingInfo?.shipName || 'غير محدد'}</div>
                                                    </div>
                                                    <div className="mb-2">
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">رقم IMO:</span>
                                                        <div className="font-mono text-gray-900 dark:text-white">{shippingInfo?.imoNumber || 'غير محدد'}</div>
                                                    </div>
                                                    <div>
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">رقم الكونتينر:</span>
                                                        <div className="font-mono text-gray-900 dark:text-white">{shippingInfo?.containerNumber || 'غير محدد'}</div>
                                                    </div>
                                                </>
                                            ) : (
                                                <>
                                                    <div className="mb-2">
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">رقم الرحلة:</span>
                                                        <div className="font-mono text-gray-900 dark:text-white">{shippingInfo?.flightNumber || 'غير محدد'}</div>
                                                    </div>
                                                    <div>
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">رقم البوليصة الجوية:</span>
                                                        <div className="font-mono text-gray-900 dark:text-white">{shippingInfo?.airwayBillNumber || 'غير محدد'}</div>
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    </div>

                                    {/* Document Numbers */}
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                                            <FileText className="w-4 h-4" />
                                            المستندات والأرقام
                                        </h4>
                                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                                            {isSea ? (
                                                <>
                                                    <div className="mb-2">
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">رقم البوليصة (B/L):</span>
                                                        <div className="font-mono text-gray-900 dark:text-white">{shippingInfo?.billOfLadingNumber || 'غير محدد'}</div>
                                                    </div>
                                                    {shippingInfo?.billOfLadingFile && (
                                                        <a
                                                            href={shippingInfo.billOfLadingFile}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm"
                                                        >
                                                            <ExternalLink className="w-3 h-3" />
                                                            عرض بوليصة الشحن
                                                        </a>
                                                    )}
                                                </>
                                            ) : (
                                                <>
                                                    <div className="mb-2">
                                                        <span className="text-gray-600 dark:text-gray-400 text-xs">رقم البوليصة الجوية:</span>
                                                        <div className="font-mono text-gray-900 dark:text-white">{shippingInfo?.airwayBillNumber || 'غير محدد'}</div>
                                                    </div>
                                                    {shippingInfo?.airwayBillFile && (
                                                        <a
                                                            href={shippingInfo.airwayBillFile}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm"
                                                        >
                                                            <ExternalLink className="w-3 h-3" />
                                                            عرض بوليصة الشحن الجوي
                                                        </a>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    </div>

                                    {/* Tracking Section */}
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                                            <Navigation className="w-4 h-4" />
                                            التتبع
                                        </h4>
                                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                                            <div className="space-y-2">
                                                {shippingInfo?.trackingLink && (
                                                    <a
                                                        href={shippingInfo.trackingLink}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="flex items-center gap-2 text-emerald-600 hover:text-emerald-700 font-medium"
                                                    >
                                                        <Navigation className="w-4 h-4" />
                                                        رابط التتبع المباشر
                                                    </a>
                                                )}
                                                {isSea ? (
                                                    <>
                                                        {(shippingInfo?.imoNumber || shippingInfo?.shipName) && (
                                                            <div className="flex flex-wrap gap-2 mt-2">
                                                                {shippingInfo?.imoNumber && (
                                                                    <a
                                                                        href={`https://www.marinetraffic.com/en/ais/details/ships/imo:${shippingInfo.imoNumber}`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-lg text-sm hover:bg-blue-200 transition-colors"
                                                                    >
                                                                        <Ship className="w-3 h-3" />
                                                                        MarineTraffic
                                                                    </a>
                                                                )}
                                                                {shippingInfo?.shipName && !shippingInfo?.imoNumber && (
                                                                    <a
                                                                        href={`https://www.vesselfinder.com/vessels?name=${encodeURIComponent(shippingInfo.shipName)}`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-lg text-sm hover:bg-blue-200 transition-colors"
                                                                    >
                                                                        <Ship className="w-3 h-3" />
                                                                        VesselFinder
                                                                    </a>
                                                                )}
                                                                {shippingInfo?.containerNumber && (
                                                                    <a
                                                                        href={`https://www.track-trace.com/container/item/${shippingInfo.containerNumber}`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="inline-flex items-center gap-1 px-3 py-1 bg-emerald-100 text-emerald-700 rounded-lg text-sm hover:bg-emerald-200 transition-colors"
                                                                    >
                                                                        <Box className="w-3 h-3" />
                                                                        تتبع الحاوية
                                                                    </a>
                                                                )}
                                                            </div>
                                                        )}
                                                    </>
                                                ) : (
                                                    shippingInfo?.airwayBillNumber && (
                                                        <a
                                                            href={`https://www.track-trace.com/aircargo/item/${shippingInfo.airwayBillNumber}`}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="inline-flex items-center gap-1 px-3 py-1 bg-purple-100 text-purple-700 rounded-lg text-sm hover:bg-purple-200 transition-colors"
                                                        >
                                                            <Plane className="w-3 h-3" />
                                                            تتبع الشحن الجوي
                                                        </a>
                                                    )
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Deals Summary */}
                        {resolvedShipmentDeals.length > 0 && (
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                                <div className="border-b border-gray-200 dark:border-gray-700 p-4">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                                        <Package className="w-5 h-5" />
                                        ملخص الصفقات ({totalDeals})
                                    </h3>
                                </div>
                                <div className="p-4">
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm">
                                            <thead className="bg-gray-50 dark:bg-gray-700">
                                                <tr className="text-right text-gray-600 dark:text-gray-300">
                                                    <th className="px-3 py-2">رقم الصفقة</th>
                                                    <th className="px-3 py-2">رقم العرض</th>
                                                    <th className="px-3 py-2">الحجم</th>
                                                    <th className="px-3 py-2">الوزن</th>
                                                    <th className="px-3 py-2">التكلفة الموزعة</th>
                                                    <th className="px-3 py-2">الإضافات</th>
                                                    <th className="px-3 py-2">المجموع</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {resolvedShipmentDeals.map((deal) => (
                                                    <tr key={deal.dealId} className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                                        <td className="px-3 py-2">
                                                            <div className="font-medium text-gray-900 dark:text-white leading-snug">
                                                                {deal.displayTitle && deal.displayTitle !== deal.dealNumber ? (
                                                                    <>
                                                                        <span className="block">{deal.displayTitle}</span>
                                                                        <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                                                                            {deal.dealNumber}
                                                                        </span>
                                                                    </>
                                                                ) : (
                                                                    deal.dealNumber
                                                                )}
                                                            </div>
                                                        </td>
                                                        <td className="px-3 py-2">
                                                            <div className="font-mono text-gray-700 dark:text-gray-300">{deal.originalOfferNumber}</div>
                                                        </td>
                                                        <td className="px-3 py-2 text-center">
                                                            <div className="text-gray-700 dark:text-gray-300">{(deal.totalVolume || 0).toFixed(1)} م³</div>
                                                        </td>
                                                        <td className="px-3 py-2 text-center">
                                                            <div className="text-gray-700 dark:text-gray-300">{(deal.totalWeightKg || 0).toLocaleString()} كجم</div>
                                                        </td>
                                                        <td className="px-3 py-2 text-center">
                                                            <div className="font-medium text-blue-600 dark:text-blue-400">
                                                                ${(deal.distributedCost || 0).toLocaleString()}
                                                            </div>
                                                        </td>
                                                        <td className="px-3 py-2 text-center">
                                                            <div className="text-red-600 dark:text-red-400">
                                                                ${(deal.extraCosts || 0).toLocaleString()}
                                                            </div>
                                                        </td>
                                                        <td className="px-3 py-2 text-center">
                                                            <div className="font-bold text-gray-900 dark:text-white">
                                                                ${((deal.distributedCost || 0) + (deal.extraCosts || 0)).toLocaleString()}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ))}
                                                <tr className="bg-gray-50 dark:bg-gray-700 font-bold">
                                                    <td colSpan={4} className="px-3 py-3 text-left">
                                                        المجاميع
                                                    </td>
                                                    <td className="px-3 py-3 text-center text-blue-600 dark:text-blue-400">
                                                        ${resolvedShipmentDeals.reduce((sum, d) => sum + (d.distributedCost || 0), 0).toLocaleString()}
                                                    </td>
                                                    <td className="px-3 py-3 text-center text-red-600 dark:text-red-400">
                                                        ${resolvedShipmentDeals.reduce((sum, d) => sum + (d.extraCosts || 0), 0).toLocaleString()}
                                                    </td>
                                                    <td className="px-3 py-3 text-center text-gray-900 dark:text-white">
                                                        ${resolvedShipmentDeals.reduce((sum, d) => sum + (d.distributedCost || 0) + (d.extraCosts || 0), 0).toLocaleString()}
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Payment Information */}
                        {shipment.installments && shipment.installments.length > 0 && (
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                                <div className="border-b border-gray-200 dark:border-gray-700 p-4">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                                        <CreditCard className="w-5 h-5" />
                                        خطة الدفعات ({shipment.installments.length} دفعة)
                                    </h3>
                                </div>
                                <div className="p-4">
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                        {shipment.installments.map((installment, index) => (
                                            <div key={installment.id} className={`border rounded-lg p-3 ${installment.status === 'paid' ? 'border-green-200 bg-green-50 dark:bg-green-900/20' : 'border-gray-200 bg-gray-50 dark:bg-gray-700/50'}`}>
                                                <div className="flex justify-between items-start mb-2">
                                                    <div className="flex items-center gap-2">
                                                        <div className={`w-2 h-2 rounded-full ${installment.status === 'paid' ? 'bg-green-500' : 'bg-gray-400'}`}></div>
                                                        <span className="font-medium text-gray-900 dark:text-white">دفعة #{installment.installmentNumber}</span>
                                                    </div>
                                                    <span className={`px-2 py-0.5 rounded-full text-xs ${installment.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                                                        {installment.status === 'paid' ? 'مدفوعة' : 'غير مدفوعة'}
                                                    </span>
                                                </div>
                                                <div className="space-y-1">
                                                    <div className="flex justify-between text-sm">
                                                        <span className="text-gray-600 dark:text-gray-400">المبلغ:</span>
                                                        <span className="font-bold text-gray-900 dark:text-white">${installment.amount?.toLocaleString()}</span>
                                                    </div>
                                                    <div className="flex justify-between text-sm">
                                                        <span className="text-gray-600 dark:text-gray-400">النسبة:</span>
                                                        <span className="text-gray-700 dark:text-gray-300">{installment.percentage}%</span>
                                                    </div>
                                                    {installment.notes && (
                                                        <div className="text-xs text-gray-500 mt-1">
                                                            ملاحظات: {installment.notes}
                                                        </div>
                                                    )}
                                                    {installment.dueDate && (
                                                        <div className="text-xs text-gray-500">
                                                            تاريخ الاستحقاق: {formatDate(installment.dueDate)}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Footer Notes */}
                    <div className="mt-8 p-4 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 print:hidden">
                        <div className="text-sm text-gray-600 dark:text-gray-400">
                            <div className="flex items-center gap-2 mb-2">
                                <AlertCircle className="w-4 h-4" />
                                <span className="font-medium">ملاحظات:</span>
                            </div>
                            <ul className="list-disc list-inside space-y-1 text-xs">
                                <li>يجب تحديث حالة الشحنة بعد كل مرحلة من مراحل الشحن</li>
                                <li>يتم تحديث التكاليف الإضافية عند وجود مصاريف غير متوقعة</li>
                                <li>جميع المبالغ بالدولار الأمريكي (USD)</li>
                                <li>التواريخ حسب توقيت الصين المحلي</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};