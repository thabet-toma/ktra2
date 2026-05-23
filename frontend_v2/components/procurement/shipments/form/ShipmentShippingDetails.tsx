import React from 'react';
import {
    Ship, Plane, Truck, Box, FileText, Upload,
    Navigation, Calendar, CheckCircle2, Clock,
    Anchor, Building2, ArrowRight
} from 'lucide-react';
import { SHIPPING_TERMS } from '../../../../constants/shipping';
import { ShipmentTimeline } from '../ShipmentTimeline';
import { ShipmentStatusVisualizer } from './ShipmentStatusVisualizer';

interface ShipmentShippingDetailsProps {
    shippingInfo: any;
    setShippingInfo: (data: any) => void;
    handleFileUpload: (file: File, type: 'billOfLading' | 'airwayBill') => void;
    uploadingFile: boolean;
    handleShipmentStatusChange: (status: string, notes?: string) => void;
}

export const ShipmentShippingDetails: React.FC<ShipmentShippingDetailsProps> = ({
    shippingInfo, setShippingInfo, handleFileUpload, uploadingFile, handleShipmentStatusChange
}) => {

    // --- Helpers ---
    const getStatusText = (status: string) => {
        if (shippingInfo.shippingType === 'sea') {
            switch (status) {
                case 'agent_warehouse': return 'مستودع الوكيل';
                case 'china_customs_clearance': return 'جمارك الصين';
                case 'on_board': return 'على السفينة';
                case 'at_sea': return 'في البحر';
                case 'arrived_port': return 'وصلت الميناء';
                case 'israel_customs_clearance': return 'جمارك إسرائيل';
                case 'released': return 'مفرج عنها';
                case 'delivered_local': return 'تم التسليم';
                default: return status;
            }
        } else {
            switch (status) {
                case 'agent_warehouse': return 'مستودع الوكيل';
                case 'delivered_to_shipping_company': return 'شركة الشحن';
                case 'china_customs_clearance': return 'جمارك الصين';
                case 'departed': return 'انطلقت';
                case 'in_transit': return 'في الطريق';
                case 'arrived_airport': return 'وصلت المطار';
                case 'israel_customs_clearance': return 'جمارك إسرائيل';
                case 'released': return 'مفرج عنها';
                case 'delivered_local': return 'تم التسليم';
                default: return status;
            }
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'agent_warehouse': return <Building2 className="w-4 h-4" />;
            case 'on_board': return <Ship className="w-4 h-4" />;
            case 'at_sea': return <Anchor className="w-4 h-4" />;
            case 'departed': return <Plane className="w-4 h-4" />;
            case 'arrived_port': case 'arrived_airport': return <ArrowRight className="w-4 h-4" />;
            case 'released': return <CheckCircle2 className="w-4 h-4" />;
            case 'delivered_local': return <Box className="w-4 h-4" />;
            default: return <Clock className="w-4 h-4" />;
        }
    };

    // القوائم لحساب شريط التقدم
    const seaStatuses = ['agent_warehouse', 'china_customs_clearance', 'on_board', 'at_sea', 'arrived_port', 'israel_customs_clearance', 'released', 'delivered_local'];
    const airStatuses = ['agent_warehouse', 'delivered_to_shipping_company', 'china_customs_clearance', 'departed', 'in_transit', 'arrived_airport', 'israel_customs_clearance', 'released', 'delivered_local'];
    /** تُحدَّد تلقائياً عند حفظ فاتورة المشتريات (إطلاق / تسليم محلي) */
    const routeStatusesManualOnly = new Set<string>(['released', 'delivered_local']);

    const currentStatuses = shippingInfo.shippingType === 'sea' ? seaStatuses : airStatuses;
    const currentIndex = currentStatuses.indexOf(shippingInfo.shipmentStatus?.status || 'agent_warehouse');
    const progressPercentage = ((currentIndex + 1) / currentStatuses.length) * 100;

    const formatStatusDate = (raw: string | undefined) => {
        if (!raw || !String(raw).trim()) return '—';
        const d = new Date(raw);
        if (Number.isNaN(d.getTime())) return '—';
        return d.toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' });
    };

    const renderTrackingButtons = () => {
        if (shippingInfo.shippingType === 'sea') {
            return (
                <div className="flex flex-wrap gap-2 mt-2">
                    {shippingInfo.trackingLink ? (
                        <a href={shippingInfo.trackingLink} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 aseel-bg-panel text-white rounded-lg text-xs font-bold shadow-sm hover:aseel-bg-panel text-center flex items-center justify-center gap-2">
                            <Navigation className="w-3 h-3" /> تتبع مباشر
                        </a>
                    ) : (
                        <>
                            {(shippingInfo.imoNumber || shippingInfo.shipName) && (
                                <a href={`https://www.marinetraffic.com/en/ais/index/search/all/keyword:${shippingInfo.imoNumber || shippingInfo.shipName}`} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 bg-[var(--color-primary-dark,#004e82)] text-white rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2">
                                    <Ship className="w-3 h-3" /> MarineTraffic
                                </a>
                            )}
                            {shippingInfo.containerNumber && (
                                <a href={`https://www.track-trace.com/container/item/${shippingInfo.containerNumber}`} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 aseel-bg-accent-bg aseel-text-accent border aseel-border-accent rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2">
                                    <Box className="w-3 h-3" /> تتبع الحاوية
                                </a>
                            )}
                        </>
                    )}
                </div>
            );
        }
        // للجوي
        if (shippingInfo.shippingType === 'air' && shippingInfo.airwayBillNumber) {
            return (
                <div className="flex mt-2">
                    <a href={`https://www.track-trace.com/aircargo/item/${shippingInfo.airwayBillNumber}`} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 aseel-bg-accent text-white rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2">
                        <Plane className="w-3 h-3" /> تتبع الشحنة الجوية
                    </a>
                </div>
            )
        }
        return null;
    };

    return (
        <div className="aseel-bg-field dark:aseel-bg-panel p-6 rounded-2xl shadow-sm border aseel-border-soft dark:aseel-border-soft">
            <h3 className="text-lg font-bold dark:text-white mb-6 flex items-center gap-2">
                <Truck className="w-5 h-5 aseel-text-soft" /> معلومات الشحن التفصيلية
            </h3>

            {/* Type Toggle */}
            <div className="flex gap-2 mb-6">
                <button type="button" onClick={() => setShippingInfo(prev => ({ ...prev, shippingType: 'sea' }))}
                    className={`flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all ${shippingInfo.shippingType === 'sea' ? 'aseel-bg-accent text-white shadow-lg' : 'aseel-bg-panel aseel-text-soft dark:aseel-bg-panel dark:aseel-text-soft'}`}>
                    <Ship className="w-4 h-4" /> بحري
                </button>
                <button type="button" onClick={() => setShippingInfo(prev => ({ ...prev, shippingType: 'air' }))}
                    className={`flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all ${shippingInfo.shippingType === 'air' ? 'aseel-bg-accent text-white shadow-lg' : 'aseel-bg-panel aseel-text-soft dark:aseel-bg-panel dark:aseel-text-soft'}`}>
                    <Plane className="w-4 h-4" /> جوي
                </button>
            </div>

            {/* Details Form */}
            <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">شركة الشحن</label>
                        <input type="text" value={shippingInfo.internationalShippingCompany || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, internationalShippingCompany: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg" placeholder="اسم الشركة" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">{shippingInfo.shippingType === 'sea' ? 'اسم السفينة' : 'رقم الرحلة'}</label>
                        <input type="text" value={shippingInfo.shippingType === 'sea' ? shippingInfo.shipName : shippingInfo.flightNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, [shippingInfo.shippingType === 'sea' ? 'shipName' : 'flightNumber']: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg" />
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">المغادرة</label>
                        <input type="date" value={shippingInfo.departureDate?.split('T')[0] || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, departureDate: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">الوصول</label>
                        <input type="date" value={shippingInfo.arrivalDate?.split('T')[0] || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, arrivalDate: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg" />
                    </div>
                </div>

                {shippingInfo.shippingType === 'sea' ? (
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">رقم الكونتينر</label>
                            <input type="text" value={shippingInfo.containerNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, containerNumber: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg font-mono" />
                        </div>
                        <div>
                            <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">رقم البوليصة (B/L)</label>
                            <input type="text" value={shippingInfo.billOfLadingNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, billOfLadingNumber: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg font-mono" />
                        </div>
                    </div>
                ) : (
                    <div>
                        <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">رقم البوليصة (AWB)</label>
                        <input type="text" value={shippingInfo.airwayBillNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, airwayBillNumber: e.target.value }))} className="w-full p-2 text-sm aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg font-mono" />
                    </div>
                )}

                {/* Tracking Links */}
                {renderTrackingButtons()}

                {/* Uploads */}
                <div className="pt-3 border-t aseel-border-soft dark:aseel-border-soft">
                    <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">
                        <Upload className="w-3 h-3 inline mr-1" />
                        {shippingInfo.shippingType === 'sea' ? 'بوليصة الشحن (B/L)' : 'بوليصة الشحن الجوي (AWB)'}
                    </label>
                    <div className="flex gap-2">
                        <input type="file" accept=".pdf" onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0], shippingInfo.shippingType === 'sea' ? 'billOfLading' : 'airwayBill')} className="flex-1 text-xs aseel-bg-panel p-2 rounded-lg" disabled={uploadingFile} />
                        {(shippingInfo.billOfLadingFile || shippingInfo.airwayBillFile) && (
                            <a href={shippingInfo.billOfLadingFile || shippingInfo.airwayBillFile} target="_blank" className="px-3 py-2 aseel-bg-accent-bg aseel-text-accent rounded-lg text-xs font-bold flex items-center gap-1"><FileText className="w-3 h-3" /> فتح الملف</a>
                        )}
                    </div>
                </div>
            </div>

            {/* 🟢 Status Management Section (Restored) */}
            <div className="mt-6 pt-6 border-t aseel-border-soft dark:aseel-border-soft">
                <h4 className="text-sm font-bold aseel-text-ink dark:aseel-text-soft mb-4 flex items-center gap-2">
                    <Truck className="w-4 h-4 aseel-text-soft" /> حالة الشحنة
                </h4>

                {/* Current Status Badge */}
                {shippingInfo.shipmentStatus && (
                    <div className={`mb-4 p-3 rounded-xl border flex justify-between items-center ${shippingInfo.shipmentStatus.completed ? 'bg-green-50 aseel-border-soft text-green-700' : 'aseel-bg-accent-bg aseel-border-accent aseel-text-accent'} dark:bg-opacity-20`}>
                        <div>
                            <div className="font-bold flex items-center gap-2">
                                {getStatusIcon(shippingInfo.shipmentStatus.status)}
                                {getStatusText(shippingInfo.shipmentStatus.status)}
                            </div>
                            {shippingInfo.shipmentStatus.notes && (
                                <p className="text-xs mt-1 opacity-80">{shippingInfo.shipmentStatus.notes}</p>
                            )}
                        </div>
                        <div className="text-xs opacity-70 font-mono">
                            {formatStatusDate(shippingInfo.shipmentStatus.statusDate)}
                        </div>
                    </div>
                )}

                {/* Status Buttons Grid */}
                <div className="grid grid-cols-4 gap-2 mb-4">
                    {currentStatuses.map((statusKey) => {
                        const autoOnly = routeStatusesManualOnly.has(statusKey);
                        const isCurrent = shippingInfo.shipmentStatus?.status === statusKey;
                        return (
                        <button
                            key={statusKey}
                            type="button"
                            disabled={autoOnly}
                            title={autoOnly ? 'تُحدَّد تلقائياً عند حفظ فاتورة مرتبطة بالصفقة' : undefined}
                            onClick={() => !autoOnly && handleShipmentStatusChange(statusKey)}
                            className={`p-2 rounded-lg text-xs font-medium flex flex-col items-center justify-center gap-1 transition-all h-16
                                ${isCurrent
                                    ? 'aseel-bg-accent text-white shadow-md transform scale-105'
                                    : autoOnly
                                        ? 'aseel-bg-panel dark:aseel-bg-panel/80 aseel-text-soft dark:aseel-text-soft cursor-not-allowed opacity-75'
                                        : 'aseel-bg-panel dark:aseel-bg-panel/50 aseel-text-soft dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel'
                                }`}
                        >
                            {getStatusIcon(statusKey)}
                            <span className="text-[10px] text-center leading-tight">{getStatusText(statusKey)}</span>
                        </button>
                        );
                    })}
                </div>

                {/* Add Note Button */}
                <button
                    type="button"
                    onClick={() => {
                        const notes = prompt('أدخل ملاحظات إضافية:');
                        if (notes) handleShipmentStatusChange(shippingInfo.shipmentStatus?.status || 'agent_warehouse', notes);
                    }}
                    className="w-full py-2 aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft rounded-lg text-xs font-medium hover:aseel-bg-grid-head transition-colors flex items-center justify-center gap-2"
                >
                    <span>📝</span> إضافة ملاحظات
                </button>

                {/* Progress Bar */}
                <div className="mt-4">
                    <div className="flex justify-between items-center mb-1 text-xs aseel-text-soft">
                        <span>التقدم</span>
                        <span>{Math.round(progressPercentage)}%</span>
                    </div>
                    <div className="w-full h-2 aseel-bg-grid-head dark:aseel-bg-panel rounded-full overflow-hidden">
                        <div
                            className={`h-full transition-all duration-500 ${progressPercentage === 100 ? 'bg-green-500' : 'aseel-bg-accent-bg'}`}
                            style={{ width: `${progressPercentage}%` }}
                        />
                    </div>
                </div>
            </div>

            {/* Timeline Section */}
            <div className="mt-6 pt-6 border-t aseel-border-soft dark:aseel-border-soft">
                <h4 className="text-xs font-bold aseel-text-soft mb-3 uppercase">إعدادات المسار (Incoterms)</h4>
                <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                        <label className="block text-xs aseel-text-soft mb-1">من (نقطة الاستلام)</label>
                        <div className="p-2 aseel-bg-accent-bg dark:aseel-bg-panel/20 aseel-text-accent dark:aseel-text-soft rounded-lg text-sm font-bold border aseel-border-soft dark:aseel-border-soft">
                            {shippingInfo.fromTerm || '---'}
                        </div>
                    </div>
                    <div>
                        <label className="block text-xs aseel-text-soft mb-1">إلى (نقطة التسليم)</label>
                        <select
                            value={shippingInfo.toTerm || 'DDP'}
                            onChange={(e) => setShippingInfo(prev => ({ ...prev, toTerm: e.target.value }))}
                            className="w-full p-2 aseel-bg-panel dark:aseel-bg-panel/20 aseel-text-ink dark:aseel-text-soft rounded-lg text-sm font-bold border aseel-border-soft dark:aseel-border-soft outline-none"
                        >
                            {SHIPPING_TERMS.map(term => (
                                <option key={term.code} value={term.code}>{term.code}</option>
                            ))}
                        </select>
                    </div>
                </div>
            </div>
        </div>
    );
};