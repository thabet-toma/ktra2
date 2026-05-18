import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Shipment, User, Supplier, Deal } from '../../../types';
import { shipmentsService } from '../../../services/shipmentsService';
import { suppliersService } from '../../../services/firestoreService';
import { dealsService } from '../../../services/dealsService';
import {
    Plus, Truck, Edit, Eye, Trash2
} from 'lucide-react';
import { LoadingSpinner } from '../../LoadingSpinner';
import { ShipmentForm } from './ShipmentForm';
import { ShipmentDetailView } from './ShipmentDetailView';
import { DataGrid, Toolbar, StatusBadge, Button } from '../../ui';

interface ShipmentManagementProps {
    currentUser: User;
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

export const ShipmentManagement: React.FC<ShipmentManagementProps> = ({
    currentUser,
    onOpenAccountingJournal,
}) => {
    const navigate = useNavigate();
    const location = useLocation();
    const newFormInitRef = useRef(false);

    const shipmentsPathMatch = useMemo(() => {
        const path = (location.pathname || '/').replace(/\/$/, '') || '/';
        if (path !== '/shipments' && !path.startsWith('/shipments/')) return null;
        if (path === '/shipments') return { mode: 'list' as const };
        const m = path.match(/^\/shipments\/(.+)$/);
        const seg = m ? decodeURIComponent(m[1]) : '';
        if (seg === 'new') return { mode: 'new' as const };
        if (!seg) return { mode: 'list' as const };
        return { mode: 'shipment' as const, id: seg };
    }, [location.pathname]);

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
        const path = (location.pathname || '/').replace(/\/$/, '') || '/';
        const onShipmentsRoute = path === '/shipments' || path.startsWith('/shipments/');
        if (!onShipmentsRoute) {
            navigate('/shipments', { replace: true });
        }
    }, [location.pathname, navigate]);

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

    /** مزامنة قائمة/نموذج الشحنة مع الراوت `/shipments` و `/shipments/:id` و `/shipments/new` */
    useEffect(() => {
        if (!shipmentsPathMatch) return;
        if (shipmentsPathMatch.mode === 'list') {
            newFormInitRef.current = false;
            setViewMode('list');
            setCurrentShipment(null);
            return;
        }
        if (shipmentsPathMatch.mode === 'shipment') {
            const id = shipmentsPathMatch.id;
            if (shipments.length === 0) return;
            const target = shipments.find((s) => String(s.id) === String(id));
            if (target) {
                setCurrentShipment({ ...target });
                setViewMode('form');
            } else {
                navigate('/shipments', { replace: true });
            }
            return;
        }
        if (newFormInitRef.current) return;
        newFormInitRef.current = true;
        void (async () => {
            try {
                const shipmentNumber = await shipmentsService.getNextShipmentNumber();
                setCurrentShipment({
                    shipmentNumber,
                    status: 'draft',
                    deals: [],
                    totalShippingCostUsd: 0,
                    totalVolume: 0,
                });
                setViewMode('form');
            } catch (e) {
                console.error(e);
                newFormInitRef.current = false;
                navigate('/shipments', { replace: true });
            }
        })();
    }, [shipmentsPathMatch, shipments, navigate]);

    const handleCreateNew = () => {
        newFormInitRef.current = false;
        navigate('/shipments/new');
    };

    const handleEdit = (shipment: Shipment) => {
        navigate(`/shipments/${encodeURIComponent(String(shipment.id))}`);
    };

    const handleView = (shipment: Shipment) => {
        setViewingShipment(shipment);
    };

    const handleDelete = async (shipmentId: string) => {
        if (window.confirm('هل أنت متأكد من حذف هذه الشحنة؟')) {
            try {
                await shipmentsService.deleteShipment(shipmentId);
                const path = (location.pathname || '/').replace(/\/$/, '') || '/';
                const m = path.match(/^\/shipments\/(.+)$/);
                const seg = m ? decodeURIComponent(m[1]) : '';
                if (seg && seg !== 'new' && String(seg) === String(shipmentId)) {
                    navigate('/shipments', { replace: true });
                }
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
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-[var(--color-surface)] p-6 rounded-2xl shadow-sm border border-[var(--color-border)]">
                            <div>
                                <h1 className="text-[var(--font-size-xl)] font-bold text-[var(--color-text)] flex items-center gap-3">
                                    <Truck className="w-8 h-8 text-[var(--color-primary)]" />
                                    إدارة الشحنات
                                </h1>
                                <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)] mt-1">تتبع توزيع تكاليف الشحن على الصفقات المكتملة</p>
                            </div>
                            <Button
                                onClick={handleCreateNew}
                                icon={<Plus className="w-5 h-5" />}
                            >
                                إنشاء شحنة جديدة
                            </Button>
                        </div>

<div className="bg-[var(--color-surface)] rounded-2xl shadow-sm border border-[var(--color-border)]">
                            <Toolbar
                                search={searchTerm}
                                onSearch={setSearchTerm}
                                searchPlaceholder="بحث عن شحنة..."
                                filters={
                                    <>
                                        <select
                                            value={typeFilter}
                                            onChange={(e) => {
                                                setTypeFilter(e.target.value as 'all' | 'sea' | 'air');
                                                setDetailedStatusFilter('all');
                                            }}
                                            className="h-7 px-2 text-[var(--font-size-sm)] rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:border-[var(--color-primary)]"
                                        >
                                            <option value="all">كل أنواع الشحن</option>
                                            <option value="sea">🚢 بحري</option>
                                            <option value="air">✈️ جوي</option>
                                        </select>

                                        {typeFilter === 'sea' && (
                                            <select
                                                value={detailedStatusFilter}
                                                onChange={(e) => setDetailedStatusFilter(e.target.value)}
                                                className="h-7 px-2 text-[var(--font-size-sm)] rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:border-[var(--color-primary)]"
                                            >
                                                <option value="all">حالة الشحنة (الكل)</option>
                                                <option value="agent_warehouse">وكيل الشحن</option>
                                                <option value="china_customs_clearance">جمارك الصين</option>
                                                <option value="on_board">على السفينة</option>
                                                <option value="at_sea">في البحر</option>
                                                <option value="arrived_port">وصلت الميناء</option>
                                                <option value="israel_customs_clearance">جمارك Israel</option>
                                                <option value="released">مفرج عنها</option>
                                                <option value="delivered_local">تم التسليم</option>
                                            </select>
                                        )}

                                        {typeFilter === 'air' && (
                                            <select
                                                value={detailedStatusFilter}
                                                onChange={(e) => setDetailedStatusFilter(e.target.value)}
                                                className="h-7 px-2 text-[var(--font-size-sm)] rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:border-[var(--color-primary)]"
                                            >
                                                <option value="all">حالة الشحنة (الكل)</option>
                                                <option value="agent_warehouse">وكيل الشحن</option>
                                                <option value="delivered_to_shipping_company">لشركة الشحن</option>
                                                <option value="china_customs_clearance">جمارك الصين</option>
                                                <option value="departed">انطلقت</option>
                                                <option value="in_transit">في الطريق</option>
                                                <option value="arrived_airport">وصلت المطار</option>
                                                <option value="israel_customs_clearance">جمارك Israel</option>
                                                <option value="released">مفرج عنها</option>
                                                <option value="delivered_local">تم التسليم</option>
                                            </select>
                                        )}

                                        <select
                                            value={paymentFilter}
                                            onChange={(e) => setPaymentFilter(e.target.value)}
                                            className="h-7 px-2 text-[var(--font-size-sm)] rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:border-[var(--color-primary)]"
                                        >
                                            <option value="all">كل حالات الدفع</option>
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
                                                className="h-7 px-2 text-[var(--font-size-sm)] text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 rounded-md transition-colors"
                                            >
                                                تفريغ الفلاتر
                                            </button>
                                        )}
                                    </>
                                }
                                actions={
                                    <div className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
                                        {filteredShipments.length} شحنة
                                    </div>
                                }
                            />

                            <DataGrid
                                columns={[
                                    {
                                        key: 'shipmentNumber',
                                        header: 'الشحنة',
                                        width: '180px',
                                        render: (row: Shipment) => {
                                            const shippingType = row.shippingInfo?.shippingType || 'sea';
                                            const dealsCount = row.deals?.length || 0;
                                            return (
                                                <div className="flex items-center gap-2 py-1">
                                                    <div className={`p-1 rounded ${shippingType === 'sea' ? 'bg-[var(--color-primary)]/10' : 'bg-[var(--color-primary)]/10'}`}>
                                                        <span className="text-[var(--font-size-xs)]">{shippingType === 'sea' ? '🚢' : '✈️'}</span>
                                                    </div>
                                                    <div className="flex flex-col">
                                                        <span className="text-[var(--font-size-sm)] font-medium text-[var(--color-text)]">{row.shipmentNumber}</span>
                                                        <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{dealsCount} صفقة</span>
                                                    </div>
                                                </div>
                                            );
                                        }
                                    },
                                    {
                                        key: 'shippingAgentName',
                                        header: 'الوكيل',
                                        width: '140px',
                                        render: (row: Shipment) => (
                                            <span className="text-[var(--font-size-sm)] text-[var(--color-text)]">{row.shippingAgentName || '-'}</span>
                                        )
                                    },
                                    {
                                        key: 'status',
                                        header: 'الحالة',
                                        width: '120px',
                                        render: (row: Shipment) => {
                                            const statusMap: Record<string, string> = {
                                                draft: 'مسودة',
                                                payment_pending: 'بانتظار الدفع',
                                                partially_paid: 'مدفوع جزئياً',
                                                paid: 'مدفوع بالكامل',
                                                shipped: 'تم الشحن',
                                                delivered: 'تم التسليم',
                                                cancelled: 'ملغاة'
                                            };
                                            return <StatusBadge status={statusMap[row.status] || row.status} />;
                                        }
                                    },
                                    {
                                        key: 'departureDate',
                                        header: 'تاريخ المغادرة',
                                        width: '120px',
                                        sortable: true,
                                        render: (row: Shipment) => {
                                            const date = row.shippingInfo?.departureDate
                                                ? new Date(row.shippingInfo.departureDate).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short' })
                                                : '-';
                                            return <span className="text-[var(--font-size-sm)] text-[var(--color-text)]">{date}</span>;
                                        }
                                    },
                                    {
                                        key: 'arrivalDate',
                                        header: 'تاريخ الوصول',
                                        width: '120px',
                                        sortable: true,
                                        render: (row: Shipment) => {
                                            const date = row.shippingInfo?.arrivalDate
                                                ? new Date(row.shippingInfo.arrivalDate).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short' })
                                                : '-';
                                            return <span className="text-[var(--font-size-sm)] text-[var(--color-text)]">{date}</span>;
                                        }
                                    },
                                    {
                                        key: 'totalShippingCostUsd',
                                        header: 'التكلفة',
                                        width: '100px',
                                        align: 'end' as const,
                                        sortable: true,
                                        render: (row: Shipment) => (
                                            <span className="text-[var(--font-size-sm)] font-medium text-[var(--color-text)]">
                                                ${(row.totalShippingCostUsd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                            </span>
                                        )
                                    },
                                    {
                                        key: 'actions',
                                        header: 'الإجراءات',
                                        width: '120px',
                                        align: 'center' as const,
                                        render: (row: Shipment) => (
                                            <div className="flex items-center justify-center gap-0.5 py-1">
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleView(row); }}
                                                    className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:bg-[var(--color-primary)]/10 rounded transition-colors"
                                                    title="عرض التفاصيل"
                                                >
                                                    <Eye className="w-3.5 h-3.5" />
                                                </button>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleEdit(row); }}
                                                    className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:bg-[var(--color-primary)]/10 rounded transition-colors"
                                                    title="تعديل"
                                                >
                                                    <Edit className="w-3.5 h-3.5" />
                                                </button>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDelete(String(row.id)); }}
                                                    className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 rounded transition-colors"
                                                    title="حذف"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        )
                                    }
                                ]}
                                data={filteredShipments}
                                keyField="id"
                                emptyMessage="لا توجد شحنات"
                                onRowClick={(row) => handleView(row)}
                                rowClassName={() => 'h-8'}
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
                        onCancel={() => {
                            setViewMode('list');
                            setCurrentShipment(null);
                            navigate('/shipments');
                        }}
                        onSave={(shipmentId) => {
                            navigate(`/shipments/${encodeURIComponent(shipmentId)}`, {
                                replace: true,
                            });
                        }}
                        currentUser={currentUser}
                        onOpenAccountingJournal={onOpenAccountingJournal}
                    />
                )}
            </div>
        </div>
    );
};
