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

    const currentStatuses = shippingInfo.shippingType === 'sea' ? seaStatuses : airStatuses;
    const currentIndex = currentStatuses.indexOf(shippingInfo.shipmentStatus?.status || 'agent_warehouse');
    const progressPercentage = ((currentIndex + 1) / currentStatuses.length) * 100;

    const renderTrackingButtons = () => {
        if (shippingInfo.shippingType === 'sea') {
            return (
                <div className="flex flex-wrap gap-2 mt-2">
                    {shippingInfo.trackingLink ? (
                        <a href={shippingInfo.trackingLink} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 bg-emerald-600 text-white rounded-lg text-xs font-bold shadow-sm hover:bg-emerald-700 text-center flex items-center justify-center gap-2">
                            <Navigation className="w-3 h-3" /> تتبع مباشر
                        </a>
                    ) : (
                        <>
                            {(shippingInfo.imoNumber || shippingInfo.shipName) && (
                                <a href={`https://www.marinetraffic.com/en/ais/index/search/all/keyword:${shippingInfo.imoNumber || shippingInfo.shipName}`} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 bg-[#004e82] text-white rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2">
                                    <Ship className="w-3 h-3" /> MarineTraffic
                                </a>
                            )}
                            {shippingInfo.containerNumber && (
                                <a href={`https://www.track-trace.com/container/item/${shippingInfo.containerNumber}`} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 bg-blue-50 text-blue-700 border border-blue-200 rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2">
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
                    <a href={`https://www.track-trace.com/aircargo/item/${shippingInfo.airwayBillNumber}`} target="_blank" rel="noopener noreferrer" className="flex-1 py-2 px-3 bg-blue-600 text-white rounded-lg text-xs font-bold text-center flex items-center justify-center gap-2">
                        <Plane className="w-3 h-3" /> تتبع الشحنة الجوية
                    </a>
                </div>
            )
        }
        return null;
    };

    return (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
            <h3 className="text-lg font-bold dark:text-white mb-6 flex items-center gap-2">
                <Truck className="w-5 h-5 text-blue-500" /> معلومات الشحن التفصيلية
            </h3>

            {/* Type Toggle */}
            <div className="flex gap-2 mb-6">
                <button type="button" onClick={() => setShippingInfo(prev => ({ ...prev, shippingType: 'sea' }))}
                    className={`flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all ${shippingInfo.shippingType === 'sea' ? 'bg-blue-600 text-white shadow-lg' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
                    <Ship className="w-4 h-4" /> بحري
                </button>
                <button type="button" onClick={() => setShippingInfo(prev => ({ ...prev, shippingType: 'air' }))}
                    className={`flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all ${shippingInfo.shippingType === 'air' ? 'bg-blue-600 text-white shadow-lg' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
                    <Plane className="w-4 h-4" /> جوي
                </button>
            </div>

            {/* Details Form */}
            <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">شركة الشحن</label>
                        <input type="text" value={shippingInfo.internationalShippingCompany || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, internationalShippingCompany: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" placeholder="اسم الشركة" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{shippingInfo.shippingType === 'sea' ? 'اسم السفينة' : 'رقم الرحلة'}</label>
                        <input type="text" value={shippingInfo.shippingType === 'sea' ? shippingInfo.shipName : shippingInfo.flightNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, [shippingInfo.shippingType === 'sea' ? 'shipName' : 'flightNumber']: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" />
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">المغادرة</label>
                        <input type="date" value={shippingInfo.departureDate?.split('T')[0] || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, departureDate: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">الوصول</label>
                        <input type="date" value={shippingInfo.arrivalDate?.split('T')[0] || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, arrivalDate: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg" />
                    </div>
                </div>

                {shippingInfo.shippingType === 'sea' ? (
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">رقم الكونتينر</label>
                            <input type="text" value={shippingInfo.containerNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, containerNumber: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg font-mono" />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">رقم البوليصة (B/L)</label>
                            <input type="text" value={shippingInfo.billOfLadingNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, billOfLadingNumber: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg font-mono" />
                        </div>
                    </div>
                ) : (
                    <div>
                        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">رقم البوليصة (AWB)</label>
                        <input type="text" value={shippingInfo.airwayBillNumber || ''} onChange={(e) => setShippingInfo(prev => ({ ...prev, airwayBillNumber: e.target.value }))} className="w-full p-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg font-mono" />
                    </div>
                )}

                {/* Tracking Links */}
                {renderTrackingButtons()}

                {/* Uploads */}
                <div className="pt-3 border-t border-gray-100 dark:border-gray-700">
                    <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                        <Upload className="w-3 h-3 inline mr-1" />
                        {shippingInfo.shippingType === 'sea' ? 'بوليصة الشحن (B/L)' : 'بوليصة الشحن الجوي (AWB)'}
                    </label>
                    <div className="flex gap-2">
                        <input type="file" accept=".pdf" onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0], shippingInfo.shippingType === 'sea' ? 'billOfLading' : 'airwayBill')} className="flex-1 text-xs bg-gray-50 p-2 rounded-lg" disabled={uploadingFile} />
                        {(shippingInfo.billOfLadingFile || shippingInfo.airwayBillFile) && (
                            <a href={shippingInfo.billOfLadingFile || shippingInfo.airwayBillFile} target="_blank" className="px-3 py-2 bg-blue-100 text-blue-600 rounded-lg text-xs font-bold flex items-center gap-1"><FileText className="w-3 h-3" /> فتح الملف</a>
                        )}
                    </div>
                </div>
            </div>

            {/* 🟢 Status Management Section (Restored) */}
            <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <h4 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
                    <Truck className="w-4 h-4 text-blue-500" /> حالة الشحنة
                </h4>

                {/* Current Status Badge */}
                {shippingInfo.shipmentStatus && (
                    <div className={`mb-4 p-3 rounded-xl border flex justify-between items-center ${shippingInfo.shipmentStatus.completed ? 'bg-green-50 border-green-200 text-green-700' : 'bg-blue-50 border-blue-200 text-blue-700'} dark:bg-opacity-20`}>
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
                            {new Date(shippingInfo.shipmentStatus.statusDate).toLocaleDateString('en-GB')}
                        </div>
                    </div>
                )}

                {/* Status Buttons Grid */}
                <div className="grid grid-cols-4 gap-2 mb-4">
                    {currentStatuses.map((statusKey) => (
                        <button
                            key={statusKey}
                            type="button"
                            onClick={() => handleShipmentStatusChange(statusKey)}
                            className={`p-2 rounded-lg text-xs font-medium flex flex-col items-center justify-center gap-1 transition-all h-16
                                ${shippingInfo.shipmentStatus?.status === statusKey
                                    ? 'bg-blue-600 text-white shadow-md transform scale-105'
                                    : 'bg-gray-50 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                                }`}
                        >
                            {getStatusIcon(statusKey)}
                            <span className="text-[10px] text-center leading-tight">{getStatusText(statusKey)}</span>
                        </button>
                    ))}
                </div>

                {/* Add Note Button */}
                <button
                    type="button"
                    onClick={() => {
                        const notes = prompt('أدخل ملاحظات إضافية:');
                        if (notes) handleShipmentStatusChange(shippingInfo.shipmentStatus?.status || 'agent_warehouse', notes);
                    }}
                    className="w-full py-2 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-lg text-xs font-medium hover:bg-gray-200 transition-colors flex items-center justify-center gap-2"
                >
                    <span>📝</span> إضافة ملاحظات
                </button>

                {/* Progress Bar */}
                <div className="mt-4">
                    <div className="flex justify-between items-center mb-1 text-xs text-gray-500">
                        <span>التقدم</span>
                        <span>{Math.round(progressPercentage)}%</span>
                    </div>
                    <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                            className={`h-full transition-all duration-500 ${progressPercentage === 100 ? 'bg-green-500' : 'bg-blue-500'}`}
                            style={{ width: `${progressPercentage}%` }}
                        />
                    </div>
                </div>
            </div>

            {/* Timeline Section */}
            <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <h4 className="text-xs font-bold text-gray-500 mb-3 uppercase">إعدادات المسار (Incoterms)</h4>
                <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">من (نقطة الاستلام)</label>
                        <div className="p-2 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-lg text-sm font-bold border border-blue-100 dark:border-blue-800">
                            {shippingInfo.fromTerm || '---'}
                        </div>
                    </div>
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">إلى (نقطة التسليم)</label>
                        <select
                            value={shippingInfo.toTerm || 'DDP'}
                            onChange={(e) => setShippingInfo(prev => ({ ...prev, toTerm: e.target.value }))}
                            className="w-full p-2 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 rounded-lg text-sm font-bold border border-emerald-100 dark:border-emerald-800 outline-none"
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