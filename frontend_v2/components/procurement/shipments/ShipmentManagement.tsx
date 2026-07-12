/**
 * N6-T2 — ShipmentManagement (L2) — AseelDenseTable لإدارة الشحنات
 * المرجع: task5.md:796 + الإرساليات.txt:6-155
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shipment, User, Supplier } from '../../../types';
import { shipmentsService } from '../../../services/shipmentsService';
import { suppliersService } from '../../../services/firestoreService';
import { Plus, Eye, Edit, Trash2, RefreshCw } from 'lucide-react';
import { LoadingSpinner } from '../../LoadingSpinner';
import { ShipmentDetailView } from './ShipmentDetailView';
import { AseelDenseTable, type DenseColumn } from '../../aseel/AseelDenseTable';
import { useAseelIndexKeymap } from '../../aseel/useAseelIndexKeymap';
import { openInNewTab } from '@/utils/openInNewTab';
import { useConfirm } from '../../../contexts/ConfirmContext';
import { useToast } from '../../../contexts/ToastContext';

interface ShipmentManagementProps {
    currentUser: User;
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

const STATUS_LABELS: Record<string, string> = {
    draft:            'مسودة',
    payment_pending:  'بانتظار الدفع',
    partially_paid:   'مدفوع جزئياً',
    paid:             'مدفوع بالكامل',
    shipped:          'تم الشحن',
    delivered:        'تم التسليم',
    cancelled:        'ملغاة',
};

const STATUS_COLORS: Record<string, string> = {
    draft:           'var(--aseel-ink-soft)',
    payment_pending: 'var(--aseel-warn, #b8800a)',
    partially_paid:  'var(--aseel-warn, #b8800a)',
    paid:            'var(--aseel-ok, #267346)',
    shipped:         'var(--aseel-accent, #1857a4)',
    delivered:       'var(--aseel-ok, #267346)',
    cancelled:       'var(--aseel-danger, #c00)',
};

const fmtAmt = (n: number | undefined) =>
    (n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const fmtDate = (s: string | undefined) => {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString('ar'); } catch { return s; }
};

export const ShipmentManagement: React.FC<ShipmentManagementProps> = ({
    currentUser,
    onOpenAccountingJournal,
}) => {
    const navigate = useNavigate();

    const confirm = useConfirm();
    const toast = useToast();
    const [shipments, setShipments] = useState<Shipment[]>([]);
    const [suppliers, setSuppliers] = useState<Supplier[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [typeFilter, setTypeFilter] = useState<'all' | 'sea' | 'air'>('all');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [viewingShipment, setViewingShipment] = useState<Shipment | null>(null);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        const unsubShipments = shipmentsService.subscribeToShipments((s) => {
            setShipments(s);
            setLoading(false);
        });
        const unsubSuppliers = suppliersService.subscribeToSuppliers((all) => {
            setSuppliers(all.filter(s => s.type === 'shipping_agent'));
        });
        return () => { unsubShipments(); unsubSuppliers(); };
    }, []);

    const filteredShipments = useMemo(() => {
        let result = shipments;
        if (search.trim()) {
            const term = search.toLowerCase();
            result = result.filter(s =>
                s.shipmentNumber?.toLowerCase().includes(term) ||
                s.shipmentName?.toLowerCase().includes(term) ||
                s.shippingAgentName?.toLowerCase().includes(term) ||
                s.agentShipmentNumber?.toLowerCase().includes(term)
            );
        }
        if (typeFilter !== 'all') {
            result = result.filter(s => s.shippingInfo?.shippingType === typeFilter);
        }
        if (statusFilter !== 'all') {
            result = result.filter(s => s.status === statusFilter);
        }
        return result;
    }, [shipments, search, typeFilter, statusFilter]);

    const stats = useMemo(() => ({
        total: shipments.length,
        inTransit: shipments.filter(s => ['shipped'].includes(s.status)).length,
        delivered: shipments.filter(s => s.status === 'delivered').length,
        totalCost: shipments.reduce((sum, s) => sum + (s.totalShippingCostUsd || 0), 0),
    }), [shipments]);

    const handleCreateNew = () => {
        openInNewTab('/import-flow/new');
    };

    const handleEdit = (shipment: Shipment) => {
        openInNewTab(`/import-flow/${encodeURIComponent(String(shipment.id))}`);
    };

    const handleDelete = async (shipmentId: string) => {
        if (!(await confirm({ title: 'حذف الشحنة', message: 'هل أنت متأكد من حذف هذه الشحنة؟' }))) return;
        try {
            await shipmentsService.deleteShipment(shipmentId);
        } catch (error) {
            // console suppressed
            toast('حدث خطأ أثناء حذف الشحنة', 'error');
        }
    };

    const columns: DenseColumn<Shipment>[] = [
        {
            key: 'shipmentNumber',
            header: 'رقم الشحنة',
            width: '130px',
            sortable: true,
            render: (s) => (
                <span>
                    <span style={{ marginLeft: 4 }}>{s.shippingInfo?.shippingType === 'air' ? '✈' : '🚢'}</span>
                    <b style={{ fontFamily: 'monospace' }}>{s.shipmentNumber}</b>
                    {(s.deals?.length || 0) > 0 && (
                        <span style={{ marginRight: 4, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>
                            ({s.deals?.length} صفقة)
                        </span>
                    )}
                </span>
            ),
        },
        {
            key: 'shipmentName',
            header: 'اسم الشحنة',
            sortable: true,
            render: (s) => (
                <span title={s.shipmentName || undefined}>
                    {(s.shipmentName || '').trim() || '—'}
                </span>
            ),
        },
        {
            key: 'shippingAgentName',
            header: 'وكيل الشحن',
            width: '150px',
            render: (s) => <>{s.shippingAgentName || '—'}</>,
        },
        {
            key: 'type',
            header: 'النوع',
            width: '70px',
            align: 'center',
            render: (s) => <>{s.shippingInfo?.shippingType === 'air' ? 'جوي' : 'بحري'}</>,
        },
        {
            key: 'status',
            header: 'الحالة',
            width: '130px',
            render: (s) => (
                <span style={{ color: STATUS_COLORS[s.status] || 'inherit', fontWeight: 500 }}>
                    {STATUS_LABELS[s.status] || s.status}
                </span>
            ),
        },
        {
            key: 'departureDate',
            header: 'المغادرة',
            width: '90px',
            sortable: true,
            render: (s) => <>{fmtDate(s.shippingInfo?.departureDate)}</>,
        },
        {
            key: 'arrivalDate',
            header: 'الوصول',
            width: '90px',
            sortable: true,
            render: (s) => <>{fmtDate(s.shippingInfo?.arrivalDate)}</>,
        },
        {
            key: 'totalShippingCostUsd',
            header: 'التكلفة',
            width: '100px',
            align: 'right',
            numeric: true,
            sortable: true,
            render: (s) => (
                <span style={{ fontFamily: 'monospace' }}>
                    ${fmtAmt(s.totalShippingCostUsd)}
                </span>
            ),
        },
        {
            key: 'actions',
            header: '',
            width: '80px',
            align: 'center',
            render: (s) => (
                <span style={{ display: 'inline-flex', gap: 2 }}>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); setViewingShipment(s); }}
                        title="عرض التفاصيل"
                    >
                        <Eye style={{ width: 13, height: 13 }} />
                    </button>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); handleEdit(s); }}
                        title="تعديل (رحلة الاستيراد)"
                    >
                        <Edit style={{ width: 13, height: 13 }} />
                    </button>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px', color: 'var(--aseel-danger, #c00)' }}
                        onClick={(e) => { e.stopPropagation(); void handleDelete(String(s.id)); }}
                        title="حذف"
                    >
                        <Trash2 style={{ width: 13, height: 13 }} />
                    </button>
                </span>
            ),
        },
    ];

    // N0-T7 — keymap على قائمة الشحنات
    useAseelIndexKeymap({
        CtrlIns: handleCreateNew,
        F6: () => searchInputRef.current?.focus(),
        Escape: () => { setSearch(''); setTypeFilter('all'); setStatusFilter('all'); },
    },
    { enabled: !viewingShipment },
    );

    if (loading) return <LoadingSpinner />;

    return (
        <div dir="rtl" data-skin="aseel" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
            {/* شريط العنوان */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>
                    إدارة الشحنات
                </strong>
                <span className="aseel-status-item">الإجمالي: <b>{stats.total}</b></span>
                <span className="aseel-status-item">في الشحن: <b>{stats.inTransit}</b></span>
                <span className="aseel-status-item">تم التسليم: <b>{stats.delivered}</b></span>
                <span className="aseel-status-item">إجمالي التكلفة: <b>${fmtAmt(stats.totalCost)}</b></span>
                <div style={{ flex: 1 }} />
                <input
                    ref={searchInputRef}
                    className="aseel-input"
                    style={{ width: 190 }}
                    placeholder="بحث بالاسم، رقم الشحنة، الوكيل… (F6)"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                <select
                    className="aseel-input"
                    style={{ width: 120 }}
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value as 'all' | 'sea' | 'air')}
                >
                    <option value="all">كل الأنواع</option>
                    <option value="sea">🚢 بحري</option>
                    <option value="air">✈️ جوي</option>
                </select>
                <select
                    className="aseel-input"
                    style={{ width: 150 }}
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                >
                    <option value="all">كل الحالات</option>
                    {Object.entries(STATUS_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                    ))}
                </select>
                <button
                    className="aseel-toolbtn"
                    onClick={() => { setSearch(''); setTypeFilter('all'); setStatusFilter('all'); }}
                    title="إعادة تعيين الفلاتر"
                >
                    <RefreshCw style={{ width: 14, height: 14 }} />
                </button>
                <button
                    className="aseel-toolbtn"
                    onClick={handleCreateNew}
                    title="تفتح «رحلة الاستيراد» لشحنة جديدة: بيانات ← صفقات ← دفع شحن ← تخليص ← فواتير (Ctrl+Ins)"
                >
                    <Plus style={{ width: 14, height: 14 }} /> شحنة جديدة
                </button>
            </div>

            {/* عقد موحّد مع صفحات التخليص والنقل المحلي: التحرير داخل رحلة الاستيراد */}
            <p style={{ fontSize: 'var(--aseel-fs-sm, 12px)', color: 'var(--aseel-ink-soft)', margin: 0 }}>
                نقرة مزدوجة تفتح <b>ملخص الشحنة</b> · زر التعديل ✎ يفتح <b>«رحلة الاستيراد»</b>
                (الصفقات، دفع الشحن، التخليص، النقل المحلي، الفواتير).
            </p>

            {/* جدول الشحنات */}
            <AseelDenseTable<Shipment>
                columns={columns}
                rows={filteredShipments}
                getRowKey={(s) => s.id}
                loading={loading}
                emptyHint="لا توجد شحنات — اضغط «شحنة جديدة»"
                // فتح الشحنة = ملخصها الواضح؛ «رحلة الاستيراد» من زر التعديل فقط
                onRowDoubleClick={(s) => setViewingShipment(s)}
                footer={
                    filteredShipments.length > 0 ? (
                        <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                            إجمالي التكلفة: <b>${fmtAmt(filteredShipments.reduce((s, r) => s + (r.totalShippingCostUsd || 0), 0))}</b>
                        </span>
                    ) : undefined
                }
            />

            {viewingShipment && (
                <ShipmentDetailView
                    shipment={viewingShipment}
                    onClose={() => setViewingShipment(null)}
                />
            )}
        </div>
    );
};
