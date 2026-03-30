import React, { useState, useEffect } from "react";
import { Shipment, Deal, User, Invoice } from "@/types";
import { shipmentsService } from "@/services/shipmentsService";
import { dealsService } from "@/services/dealsService";
import { prepareInvoiceFromDeal } from "@/utils/invoiceConversionUtils";
import {
    Search,
    X,
    Truck,
    ChevronRight,
    AlertCircle,
    TrendingUp,
    CheckCircle2,
    Package,
    ArrowLeftRight
} from "lucide-react";

interface ShipmentImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImport: (invoices: Partial<Invoice>[]) => void;
    currentUser: User;
}

export const ShipmentImportModal: React.FC<ShipmentImportModalProps> = ({
    isOpen,
    onClose,
    onImport,
    currentUser,
}) => {
    const [shipments, setShipments] = useState<Shipment[]>([]);
    const [allDeals, setAllDeals] = useState<Deal[]>([]);
    const [searchTerm, setSearchTerm] = useState("");
    const [showOnlyDraft, setShowOnlyDraft] = useState(false);

    const [selectedShipment, setSelectedShipment] = useState<Shipment | null>(null);
    const [selectedDeals, setSelectedDeals] = useState<string[]>([]);

    // Exchange Rates
    const [shipmentRemainingRate, setShipmentRemainingRate] = useState<number>(3.6);
    const [dealRemainingRate, setDealRemainingRate] = useState<number>(3.6);

    useEffect(() => {
        if (isOpen) {
            const unsubShipments = shipmentsService.subscribeToShipments(setShipments);
            const unsubDeals = dealsService.subscribeToDeals(setAllDeals);
            return () => {
                unsubShipments();
                unsubDeals();
            };
        }
    }, [isOpen]);

    if (!isOpen) return null;

    const filteredShipments = shipments.filter(s => {
        const matchesSearch = s.shipmentNumber.toLowerCase().includes(searchTerm.toLowerCase()) ||
            s.shippingAgentName.toLowerCase().includes(searchTerm.toLowerCase());
        if (showOnlyDraft) return matchesSearch && s.status === 'draft';
        return matchesSearch;
    });

    const handleSelectShipment = (shipment: Shipment) => {
        setSelectedShipment(shipment);
        setSelectedDeals([]); // Reset selected deals
    };

    const handleToggleDeal = (dealId: string) => {
        setSelectedDeals(prev =>
            prev.includes(dealId) ? prev.filter(id => id !== dealId) : [...prev, dealId]
        );
    };

    const handleImportClick = () => {
        if (!selectedShipment) return;
        if (selectedDeals.length === 0) {
            alert("الرجاء اختيار صفقة واحدة على الأقل");
            return;
        }

        const importedInvoices: Partial<Invoice>[] = selectedDeals.map(dealId => {
            const deal = allDeals.find(d => d.id === dealId);
            if (!deal) return null;
            return prepareInvoiceFromDeal(deal, selectedShipment, dealRemainingRate, shipmentRemainingRate);
        }).filter(inv => inv !== null) as Partial<Invoice>[];

        onImport(importedInvoices);
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-white dark:bg-gray-900 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden border border-gray-100 dark:border-gray-800">
                {/* Header */}
                <div className="px-8 py-6 bg-gradient-to-r from-blue-600 to-indigo-700 text-white flex justify-between items-center shrink-0">
                    <div>
                        <h2 className="text-2xl font-bold flex items-center gap-3">
                            <Truck className="w-7 h-7" />
                            استيراد فواتير من شحنة
                        </h2>
                        <p className="text-blue-100 text-sm mt-1">اختر الشحنة والصفقات لتحويلها إلى فواتير بالشيقل</p>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/20 rounded-xl transition-colors">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex flex-1 overflow-hidden">
                    {/* Left Panel: Shipment List */}
                    <div className="w-1/3 border-l border-gray-100 dark:border-gray-800 flex flex-col bg-gray-50/50 dark:bg-gray-800/50">
                        <div className="p-4 space-y-3 shrink-0">
                            <div className="relative">
                                <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                                <input
                                    type="text"
                                    placeholder="بحث برقم الشحنة أو الوكيل..."
                                    className="w-full pr-10 pl-4 py-2.5 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 transition-all outline-none"
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                />
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-2 space-y-2 custom-scrollbar">
                            {filteredShipments.map(s => (
                                <button
                                    key={s.id}
                                    onClick={() => handleSelectShipment(s)}
                                    className={`w-full text-right p-4 rounded-2xl border transition-all duration-200 group ${selectedShipment?.id === s.id
                                            ? 'bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-200 dark:shadow-none'
                                            : 'bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-md'
                                        }`}
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <span className="font-bold text-lg">{s.shipmentNumber}</span>
                                        <span className={`text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wider font-semibold ${selectedShipment?.id === s.id ? 'bg-white/20 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                                            }`}>
                                            {s.status}
                                        </span>
                                    </div>
                                    <div className={`text-sm flex items-center gap-2 ${selectedShipment?.id === s.id ? 'text-blue-100' : 'text-gray-500'}`}>
                                        <Truck className="w-3.5 h-3.5 opacity-70" />
                                        {s.shippingAgentName}
                                    </div>
                                    <div className="mt-3 flex gap-4 text-xs opacity-80">
                                        <span className="flex items-center gap-1">
                                            <Package className="w-3 h-3" />
                                            {s.deals?.length || 0} صفقات
                                        </span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Right Panel: Details and Config */}
                    <div className="flex-1 flex flex-col bg-white dark:bg-gray-900">
                        {selectedShipment ? (
                            <>
                                <div className="p-8 border-b border-gray-100 dark:border-gray-800 bg-blue-50/30 dark:bg-blue-900/10">
                                    <div className="flex justify-between items-end">
                                        <div>
                                            <h3 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                                تجهيز الاستيراد: {selectedShipment.shipmentNumber}
                                            </h3>
                                            <p className="text-gray-500 text-sm mt-1">حدد الصفقات التي تريد تحويلها لفواتير وأدخل أسعار الصرف للمبالغ المتبقية</p>
                                        </div>
                                        <div className="flex gap-4">
                                            <div className="text-left">
                                                <label className="block text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">سعر صرف المتبقي (الصفقات)</label>
                                                <div className="relative">
                                                    <TrendingUp className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-blue-500" />
                                                    <input
                                                        type="number"
                                                        step="0.001"
                                                        className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl pr-10 pl-4 py-2 w-32 font-bold text-blue-600 outline-none focus:ring-2 focus:ring-blue-500"
                                                        value={dealRemainingRate}
                                                        onChange={(e) => setDealRemainingRate(parseFloat(e.target.value))}
                                                    />
                                                </div>
                                            </div>
                                            <div className="text-left">
                                                <label className="block text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">سعر صرف المتبقي (الشحن)</label>
                                                <div className="relative">
                                                    <TrendingUp className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-indigo-500" />
                                                    <input
                                                        type="number"
                                                        step="0.001"
                                                        className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl pr-10 pl-4 py-2 w-32 font-bold text-indigo-600 outline-none focus:ring-2 focus:ring-indigo-500"
                                                        value={shipmentRemainingRate}
                                                        onChange={(e) => setShipmentRemainingRate(parseFloat(e.target.value))}
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto p-8 space-y-4">
                                    <h4 className="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                        <Package className="w-4 h-4" />
                                        الصفقات المتوفرة في الشحنة
                                    </h4>
                                    {selectedShipment.deals.map(sd => {
                                        const deal = allDeals.find(d => d.id === sd.dealId);
                                        const isSelected = selectedDeals.includes(sd.dealId);

                                        return (
                                            <div
                                                key={sd.dealId}
                                                onClick={() => handleToggleDeal(sd.dealId)}
                                                className={`p-5 rounded-2xl border-2 cursor-pointer transition-all duration-300 flex justify-between items-center group ${isSelected
                                                        ? 'border-blue-500 bg-blue-50/50 dark:bg-blue-900/20 shadow-lg shadow-blue-100/50 dark:shadow-none'
                                                        : 'border-gray-100 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700'
                                                    }`}
                                            >
                                                <div className="flex items-center gap-5">
                                                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${isSelected ? 'bg-blue-500 text-white shadow-md' : 'bg-gray-100 dark:bg-gray-800 text-gray-400 group-hover:bg-gray-200'
                                                        }`}>
                                                        {isSelected ? <CheckCircle2 className="w-6 h-6" /> : <Package className="w-6 h-6" />}
                                                    </div>
                                                    <div>
                                                        <div className="font-bold text-lg dark:text-white">{sd.dealNumber}</div>
                                                        <div className="text-gray-500 text-sm">{deal?.factoryName || '---'}</div>
                                                    </div>
                                                </div>
                                                <div className="text-left flex items-center gap-10">
                                                    <div className="text-right">
                                                        <div className="text-[10px] text-gray-400 uppercase font-bold tracking-wider mb-1">المبلغ الإجمالي</div>
                                                        <div className="font-mono text-lg font-bold text-gray-700 dark:text-gray-200">${sd.totalAmount?.toLocaleString()}</div>
                                                    </div>
                                                    <div className={`p-2 rounded-lg transition-colors ${isSelected ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600' : 'text-gray-300'}`}>
                                                        <ChevronRight className={`w-5 h-5 transition-transform ${isSelected ? 'translate-x-1' : ''}`} />
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>

                                <div className="p-8 border-t border-gray-100 dark:border-gray-800 flex justify-between items-center shrink-0 bg-gray-50/50 dark:bg-gray-800/20">
                                    <div className="flex gap-6">
                                        <div className="flex flex-col">
                                            <span className="text-[10px] text-gray-400 uppercase font-bold tracking-widest">المختارة</span>
                                            <span className="text-2xl font-black text-gray-900 dark:text-white">{selectedDeals.length}</span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={handleImportClick}
                                        disabled={selectedDeals.length === 0}
                                        className="px-10 py-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white rounded-2xl font-bold shadow-xl shadow-blue-200 dark:shadow-none transition-all flex items-center gap-3 active:scale-95"
                                    >
                                        <ArrowLeftRight className="w-5 h-5" />
                                        استيراد وتحويل لشيقل
                                    </button>
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center p-20 text-center space-y-6">
                                <div className="w-24 h-24 bg-blue-50 dark:bg-blue-900/20 rounded-full flex items-center justify-center">
                                    <Truck className="w-10 h-10 text-blue-500" />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">لم يتم اختيار شحنة</h3>
                                    <p className="text-gray-500 max-w-xs mx-auto mt-2">يرجى تحديد شحنة من القائمة الجانبية لعرض الصفقات المتاحة للاستيراد</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
