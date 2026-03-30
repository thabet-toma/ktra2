import React, { useState, useEffect } from 'react';
import { Shipment, User, Supplier, Deal } from '../../../types';
import { shipmentsService } from '../../../services/shipmentsService';
import { suppliersService } from '../../../services/firestoreService';
import { dealsService } from '../../../services/dealsService';
import {
    Plus, Truck, Search
} from 'lucide-react';
import { LoadingSpinner } from '../../LoadingSpinner';
import { ShipmentForm } from './ShipmentForm';
import { ShipmentList } from './ShipmentList';
import { ShipmentDetailView } from './ShipmentDetailView';

interface ShipmentManagementProps {
    currentUser: User;
}

export const ShipmentManagement: React.FC<ShipmentManagementProps> = ({ currentUser }) => {
    const [viewMode, setViewMode] = useState<'list' | 'form'>('list');
    const [shipments, setShipments] = useState<Shipment[]>([]);
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [deals, setDeals] = useState<Deal[]>([]);
    const [currentShipment, setCurrentShipment] = useState<Partial<Shipment> | null>(null);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [typeFilter, setTypeFilter] = useState<'all' | 'sea' | 'air'>('all');
    const [detailedStatusFilter, setDetailedStatusFilter] = useState<string>('all');
    const [paymentFilter, setPaymentFilter] = useState<string>('all');
    const [filteredShipments, setFilteredShipments] = useState<Shipment[]>([]);
    const [viewingShipment, setViewingShipment] = useState<Shipment | null>(null);

    useEffect(() => {
        const unsubShipments = shipmentsService.subscribeToShipments(setShipments);

        const unsubSuppliers = suppliersService.subscribeToSuppliers((allSuppliers) => {
            setSuppliers(allSuppliers.filter(s => s.type === 'shipping_agent'));
        });

        const unsubDeals = dealsService.subscribeToDeals((allDeals) => {
            setDeals(allDeals.filter(d => d.status === 'completed'));
        });

        setLoading(false);
        return () => {
            unsubShipments();
            unsubSuppliers();
            unsubDeals();
        };
    }, []);

    useEffect(() => {
        let result = shipments;
        if (searchTerm.trim()) {
            const term = searchTerm.toLowerCase();
            result = result.filter(s =>
                s.shipmentNumber?.toLowerCase().includes(term) ||
                s.shippingAgentName?.toLowerCase().includes(term) ||
                s.agentShipmentNumber?.toLowerCase().includes(term)
            );
        }
        if (statusFilter !== 'all') {
            result = result.filter(s => s.status === statusFilter);
        }
        if (typeFilter !== 'all') {
            result = result.filter(s => s.shippingInfo?.shippingType === typeFilter);
        }
        if (detailedStatusFilter !== 'all') {
            result = result.filter(s => s.shippingInfo?.shipmentStatus?.status === detailedStatusFilter);
        }
        if (paymentFilter !== 'all') {
            // تصفية بناءً على حالة الدفع (قد تكون جزءاً من الحالة العامة أو تعتمد على التفاصيل)
            result = result.filter(s => {
                if (paymentFilter === 'paid') return s.status === 'paid';
                if (paymentFilter === 'partially_paid') return s.status === 'partially_paid';
                if (paymentFilter === 'unpaid') return s.status === 'draft' || s.status === 'payment_pending';
                if (paymentFilter === 'payment_pending') return s.status === 'payment_pending';
                return true;
            });
        }
        setFilteredShipments(result);
    }, [shipments, searchTerm, statusFilter, typeFilter, detailedStatusFilter, paymentFilter]);

    const handleCreateNew = async () => {
        const shipmentNumber = await shipmentsService.getNextShipmentNumber();
        setCurrentShipment({
            shipmentNumber,
            status: 'draft',
            deals: [],
            totalShippingCostUsd: 0,
            totalVolume: 0
        });
        setViewMode('form');
    };

    const handleEdit = (shipment: Shipment) => {
        setCurrentShipment({ ...shipment });
        setViewMode('form');
    };

    const handleView = (shipment: Shipment) => {
        setViewingShipment(shipment);
    };

    const handleDelete = async (shipmentId: string) => {
        if (window.confirm('هل أنت متأكد من حذف هذه الشحنة؟')) {
            try {
                await shipmentsService.deleteShipment(shipmentId);
            } catch (error) {
                console.error("Error deleting shipment:", error);
                alert("حدث خطأ أثناء حذف الشحنة");
            }
        }
    };

    if (loading) return <LoadingSpinner />;

    return (
        <div className="min-h-screen bg-transparent p-4 md:p-6">
            <div className="max-w-[1600px] mx-auto space-y-6">
                {viewMode === 'list' ? (
                    <>
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
                                    <Truck className="w-8 h-8 text-blue-600" />
                                    إدارة الشحنات
                                </h1>
                                <p className="text-gray-500 dark:text-gray-400 mt-1">تتبع توزيع تكاليف الشحن على الصفقات المكتملة</p>
                            </div>
                            <button
                                onClick={handleCreateNew}
                                className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-500/20 font-bold"
                            >
                                <Plus className="w-5 h-5" />
                                إنشاء شحنة جديدة
                            </button>
                        </div>

                        <div className="bg-white dark:bg-gray-800 p-4 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
                            <div className="flex flex-col md:flex-row gap-4 mb-6">
                                <div className="flex-1 relative">
                                    <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
                                    <input
                                        type="text"
                                        placeholder="بحث عن شحنة..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="w-full pr-10 py-3 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                    />
                                </div>
                                <select
                                    value={typeFilter}
                                    onChange={(e) => {
                                        setTypeFilter(e.target.value as any);
                                        setDetailedStatusFilter('all');
                                    }}
                                    className="px-4 py-3 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-xl outline-none shadow-sm transition-all text-sm"
                                >
                                    <option value="all">� كل أنواع الشحن</option>
                                    <option value="sea">🚢 بحري</option>
                                    <option value="air">✈️ جوي</option>
                                </select>

                                {/* فلاتر الحالات التفصيلية - تظهر بناءً على النوع */}
                                {typeFilter === 'sea' && (
                                    <select
                                        value={detailedStatusFilter}
                                        onChange={(e) => setDetailedStatusFilter(e.target.value)}
                                        className="px-4 py-3 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-xl outline-none shadow-sm transition-all text-sm border-blue-200 focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="all">📍 حالة الشحنة (الكل)</option>
                                        <option value="agent_warehouse">وكيل الشحن</option>
                                        <option value="china_customs_clearance">🇨🇳 جمارك الصين</option>
                                        <option value="on_board">🚢 على السفينة</option>
                                        <option value="at_sea">🌊 في البحر</option>
                                        <option value="arrived_port">⚓ وصلت الميناء</option>
                                        <option value="israel_customs_clearance">🇮🇱 جمارك إسرائيل</option>
                                        <option value="released">🔓 مفرج عنها</option>
                                        <option value="delivered_local">📦 تم التسليم</option>
                                    </select>
                                )}

                                {typeFilter === 'air' && (
                                    <select
                                        value={detailedStatusFilter}
                                        onChange={(e) => setDetailedStatusFilter(e.target.value)}
                                        className="px-4 py-3 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-xl outline-none shadow-sm transition-all text-sm border-purple-200 focus:ring-2 focus:ring-purple-500"
                                    >
                                        <option value="all">📍 حالة الشحنة (الكل)</option>
                                        <option value="agent_warehouse">وكيل الشحن</option>
                                        <option value="delivered_to_shipping_company">🤝 لشركة الشحن</option>
                                        <option value="china_customs_clearance">🇨🇳 جمارك الصين</option>
                                        <option value="departed">✈️ انطلقت</option>
                                        <option value="in_transit">🚚 في الطريق</option>
                                        <option value="arrived_airport">🛬 وصلت المطار</option>
                                        <option value="israel_customs_clearance">🇮🇱 جمارك إسرائيل</option>
                                        <option value="released">🔓 مفرج عنها</option>
                                        <option value="delivered_local">📦 تم التسليم</option>
                                    </select>
                                )}

                                <select
                                    value={paymentFilter}
                                    onChange={(e) => setPaymentFilter(e.target.value)}
                                    className="px-4 py-3 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 rounded-xl outline-none shadow-sm transition-all text-sm focus:ring-2 focus:ring-blue-500/20"
                                >
                                    <option value="all">💳 كل حالات الدفع</option>
                                    <option value="unpaid">غير مدفوع</option>
                                    <option value="payment_pending">بانتظار الدفع</option>
                                    <option value="partially_paid">مدفوع جزئياً</option>
                                    <option value="paid">مدفوع بالكامل</option>
                                </select>

                                {(statusFilter !== 'all' || typeFilter !== 'all' || detailedStatusFilter !== 'all' || paymentFilter !== 'all' || searchTerm !== '') && (
                                    <button
                                        onClick={() => {
                                            setStatusFilter('all');
                                            setTypeFilter('all');
                                            setDetailedStatusFilter('all');
                                            setPaymentFilter('all');
                                            setSearchTerm('');
                                        }}
                                        className="px-4 py-3 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl transition-colors text-sm font-medium"
                                    >
                                        تفريغ الفلاتر
                                    </button>
                                )}
                            </div>

                            <div className="flex items-center justify-between mb-4 px-1">
                                <div className="text-sm text-gray-500 dark:text-gray-400">
                                    نتائج البحث: <span className="font-bold text-blue-600">{filteredShipments.length}</span> شحنة
                                </div>
                            </div>

                            <ShipmentList
                                shipments={filteredShipments}
                                onEdit={handleEdit}
                                onView={handleView}
                                onDelete={handleDelete}
                                shippingAgents={suppliers}
                            />
                        </div>

                        {viewingShipment && (
                            <ShipmentDetailView
                                shipment={viewingShipment}
                                onClose={() => setViewingShipment(null)}
                            />
                        )}
                    </>
                ) : (
                    <ShipmentForm
                        shipment={currentShipment}
                        onCancel={() => setViewMode('list')}
                        onSave={() => setViewMode('list')}
                        currentUser={currentUser}
                    />
                )}
            </div>
        </div>
    );
};
